"""Same-DSP-pixel HEF/float comparison; sparse manual boxes, not tracking accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort
from score_controlled_yolo11 import exact_rgb
from score_4k_tiles import map_box, iou


def border_rejected(r,d,margin):
    if r['full_frame']:return False
    scale=min(640/r['w'],640/r['h']);cw,ch=r['w']*scale,r['h']*scale
    left=(d['x1']*640-(640-cw)/2)/cw;right=(d['x2']*640-(640-cw)/2)/cw
    top=(d['y1']*640-(640-ch)/2)/ch;bottom=(d['y2']*640-(640-ch)/2)/ch
    return ((r['x']>0 and left<=margin) or (r['y']>0 and top<=margin) or
            (r['x']+r['w']<r['source_w'] and right>=1-margin) or
            (r['y']+r['h']<r['source_h'] and bottom>=1-margin))


def gray_padding(raw,r):
    """Change ONLY neutral letterbox luma; a float-only sensitivity diagnostic."""
    data=np.frombuffer(raw,dtype=np.uint8).copy()
    if data.size!=640*640*3//2:raise ValueError('invalid NV12 size')
    scale=min(640/r['w'],640/r['h']);cw,ch=int(r['w']*scale),int(r['h']*scale)
    px,py=(640-cw)//2,(640-ch)//2
    if any(v%2 for v in (cw,ch,px,py)):raise ValueError('unaligned padding')
    mask=np.ones((640,640),dtype=bool);mask[py:py+ch,px:px+cw]=False
    y=data[:640*640].reshape(640,640);uv=data[640*640:].reshape(320,640)
    if np.any(y[mask]!=0) or np.any(uv[mask[::2]]!=128):raise ValueError('unexpected DSP padding')
    y[mask]=114
    return data.tobytes()


def score(probe,onnx,out):
    onnx_sha=hashlib.sha256(onnx.read_bytes()).hexdigest()
    if onnx_sha!='0a44c5050d77a27abb971979e8399ab6084db18b0ffc7781e312171543efef8e':
        raise ValueError('not the frozen float source')
    regions=json.loads((probe/'regions.json').read_text())
    device=[json.loads(x) for x in (probe/'model.stdout').read_text().splitlines()]
    data=(probe/'network.nv12').read_bytes();size=640*640*3//2
    if len(data)!=len(regions)*size or len(device)!=len(regions):raise ValueError('count mismatch')
    opts=ort.SessionOptions();opts.intra_op_num_threads=4
    model=ort.InferenceSession(str(onnx),opts,providers=['CPUExecutionProvider'])
    if model.get_inputs()[0].shape!=[1,3,640,640]:raise ValueError('unexpected ONNX input')
    report=[]
    for index,(r,actual) in enumerate(zip(regions,device)):
        if actual['frame']!=index:raise ValueError('wrong frame order')
        raw=data[index*size:(index+1)*size]
        predictions=[('hef',actual['detections'])]
        for variant,pixels in [('float',raw),('float_gray114',gray_padding(raw,r))]:
            rgb=exact_rgb(pixels);tensor=rgb.transpose(2,0,1)[None].astype(np.float32)/255
            output=model.run(None,{model.get_inputs()[0].name:tensor})[0]
            if output.shape!=(1,84,8400):raise ValueError('unexpected ONNX output')
            ds=[]
            for v in output[0].T:
                conf=float(v[4+67])
                if conf<.05:continue
                cx,cy,w,h=map(float,v[:4])
                ds.append(dict(class_id=67,score=conf,x1=(cx-w/2)/640,y1=(cy-h/2)/640,
                               x2=(cx+w/2)/640,y2=(cy+h/2)/640))
            predictions.append((variant,ds))
        candidates={}
        for source,detections in predictions:
            matched=[]
            for d in detections:
                box=map_box(r,d)
                if d['class_id']!=67 or box is None or iou(box,r['annotation'])<.5:continue
                matched.append(dict(score=d['score'],source_box=box,iou=iou(box,r['annotation']),
                                    rejected_at_008=bool(border_rejected(r,d,.08)),
                                    rejected_at_0015=bool(border_rejected(r,d,.015))))
            candidates[source]=sorted(matched,key=lambda d:d['score'],reverse=True)
        report.append(dict(source_frame=r['source_frame'],method=r['method'],region=r,
                           tensor_sha256=hashlib.sha256(raw).hexdigest(),matches=candidates))
    result=dict(scope='four reviewed 720p exposures; approximate manual boxes; oracle crop; not native4K or tracking qualification',
                float_source_sha256=onnx_sha,onnxruntime_version=ort.__version__,
                conversion='exact SDK full-range affine, no intermediate clipping/rounding, divide by255',
                gray_padding_scope='float-only change to padding Y114; no altered-content or HEF-gray test',
                rows=report)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    for r in report:
        h=r['matches']['hef'];f=r['matches']['float']
        print(json.dumps(dict(frame=r['source_frame'],method=r['method'],hef=h[0] if h else None,
                              float_score=f[0]['score'] if f else None,
                              float_gray114=r['matches']['float_gray114'][0]['score'] if r['matches']['float_gray114'] else None)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('probe',type=Path);p.add_argument('onnx',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();score(a.probe,a.onnx,a.output)
