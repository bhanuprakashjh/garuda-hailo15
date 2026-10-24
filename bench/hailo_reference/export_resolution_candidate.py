"""Bench-only/not-product-cleared YOLO11s shape export with frozen-weight parity.

Uses already installed Ultralytics (AGPL) only in the evaluation environment.
Does not train, download weights, install dependencies, or alter a live model.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import numpy_helper
import onnxruntime as ort
import torch
from ultralytics import YOLO

from score_controlled_yolo11 import exact_rgb


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--pixels',type=Path,required=True)
    a=p.parse_args()
    if sha(a.reference)!='0a44c5050d77a27abb971979e8399ab6084db18b0ffc7781e312171543efef8e':
        raise ValueError('wrong deployed float source')
    a.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(2)
    model=YOLO(str(a.checkpoint)).model.float().eval()
    model.fuse(verbose=False)
    state=model.state_dict()
    reference=onnx.load(str(a.reference))
    weights={x.name:numpy_helper.to_array(x) for x in reference.graph.initializer if x.name in state}
    mismatches=[k for k,v in weights.items() if not np.array_equal(v,state[k].cpu().numpy())]
    unverified=[k for k,_ in model.named_parameters() if k not in weights]
    if mismatches or unverified or len(weights)<170:
        raise ValueError(f'weights mismatch={mismatches}; unverified={unverified}')
    head=model.model[-1];head.export=True;head.format='onnx';head.dynamic=False
    outputs=[]
    for w,h in ((640,640),(1024,576)):
        destination=a.output/f'yolo11s-{w}x{h}.onnx'
        with torch.no_grad():
            example=torch.zeros(1,3,h,w)
            model(example)
            torch.onnx.export(model,example,str(destination),opset_version=13,dynamo=False,
                              input_names=['images'],output_names=['output0'],do_constant_folding=True)
        exported=onnx.load(str(destination));onnx.checker.check_model(exported)
        outputs.append(dict(path=str(destination),sha256=sha(destination),width=w,height=h))
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    old=ort.InferenceSession(str(a.reference),opts,providers=['CPUExecutionProvider'])
    new=ort.InferenceSession(outputs[0]['path'],opts,providers=['CPUExecutionProvider'])
    raw=a.pixels.read_bytes();size=640*640*3//2
    if len(raw)%size or len(raw)<4*size:raise ValueError('invalid retained network pixels')
    parity=[]
    for index in (0,4,16,23):
        if (index+1)*size>len(raw):raise ValueError('missing parity frame')
        tensor=exact_rgb(raw[index*size:(index+1)*size]).transpose(2,0,1)[None].astype(np.float32)/255
        x=old.run(None,{'images':tensor})[0];y=new.run(None,{'images':tensor})[0]
        if x.shape!=y.shape or x.shape!=(1,84,8400):raise ValueError('output shape mismatch')
        row=dict(index=index,max_box_difference_px=float(np.abs(x[:,:4]-y[:,:4]).max()),
                 max_class_score_difference=float(np.abs(x[:,4:]-y[:,4:]).max()))
        row['pass']=row['max_box_difference_px']<.05 and row['max_class_score_difference']<.0001
        parity.append(row)
    result=dict(scope='same fused weights; four full-output same-pixel640 checks; no accuracy or speed claim',
                license='existing Ultralytics AGPL bench-only/not-product-cleared',
                checkpoint_sha256=sha(a.checkpoint),reference_sha256=sha(a.reference),
                exact_parameter_tensors=len(weights),unverified_parameters=unverified,
                exports=outputs,parity=parity,passed=all(r['pass'] for r in parity),
                versions=dict(torch=torch.__version__,onnx=onnx.__version__,onnxruntime=ort.__version__))
    (a.output/'export-parity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    if not result['passed']:raise RuntimeError('640 output parity failed; do not compile candidate')


if __name__=='__main__':main()
