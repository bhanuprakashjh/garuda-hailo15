"""Compare exact full-range float reference, retained DFC stages and optional device replay."""
import argparse
import hashlib
import json
import pathlib
import numpy as np
import onnxruntime as ort
from score_4k_tiles import ANNOTATIONS, iou, map_box

def exact_rgb(data, width=640, height=640):
    if width < 2 or height < 2 or width % 2 or height % 2 or len(data) != width*height*3//2:
        raise ValueError('invalid packed NV12 dimensions/bytes')
    p = np.frombuffer(data,dtype=np.uint8).astype(np.float32)
    y = p[:width*height].reshape(height,width)
    uv = p[width*height:].reshape(height//2,width)
    u = uv[:,::2].repeat(2,0).repeat(2,1)-128
    v = uv[:,1::2].repeat(2,0).repeat(2,1)-128
    # Same full-range affine operation as the model script, deliberately no
    # uint8 rounding or clipping between conversion and normalization.
    return np.stack([y+1.4*v,y-.343*u-.711*v,y+1.765*u],-1)

def matching(region, detections):
    result = []
    for d in detections:
        if d['class_id'] != 67:
            continue
        b = map_box(region,d)
        if b is not None:
            overlap = iou(b,ANNOTATIONS[region['source_frame']])
            result.append(dict(score=float(d['score']),iou=overlap,box=b))
    return result

def nms(ds):
    kept = []
    for d in sorted(ds,key=lambda d:d['score'],reverse=True):
        b = [d[k] for k in ('x1','y1','x2','y2')]
        if not any(iou(b,[k[q] for q in ('x1','y1','x2','y2')])>.7 for k in kept):
            kept.append(d)
    return kept

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('work',type=pathlib.Path)
    p.add_argument('output',type=pathlib.Path)
    p.add_argument('--device-replay',type=pathlib.Path)
    a = p.parse_args()
    regions = json.loads((a.work/'regions.json').read_text())
    raw = (a.work/'test-inputs.nv12').read_bytes()
    size = 614400
    if len(raw)!=len(regions)*size:
        raise ValueError('Test input count mismatch')
    options = ort.SessionOptions();options.intra_op_num_threads=2
    session = ort.InferenceSession(str(a.work/'source.onnx'),options,providers=['CPUExecutionProvider'])
    stages = {}
    hashes = {}
    for name in ('fp-infer','quant-infer'):
        path = a.work/(name+'-outputs.npy')
        if path.exists():
            array = np.load(path)
            if array.shape != (len(regions),80,5,100) or not np.isfinite(array).all():
                raise ValueError('Unexpected DFC NMS output shape/values')
            stages[name]=array
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    device = None
    if a.device_replay:
        device_regions=json.loads((a.device_replay/'regions.json').read_text())
        indices=[]
        for region in regions:
            matches=[i for i,r in enumerate(device_regions) if r==region]
            if len(matches)!=1:
                raise ValueError('Device replay must contain exactly one copy of each tested region')
            indices.append(matches[0])
        all_device=[json.loads(s) for s in (a.device_replay/'letterbox.jsonl').read_text().splitlines()]
        if len(all_device)!=len(device_regions):
            raise ValueError('Device output count mismatch')
        for i,pred in enumerate(all_device):
            if pred['frame']!=i:
                raise ValueError('Wrong device output order')
        device=[dict(all_device[i],frame=j,device_index=i) for j,i in enumerate(indices)]
        device_raw=(a.device_replay/'network-inputs.nv12').read_bytes()
        if len(device_raw)!=len(device_regions)*size or b''.join(device_raw[i*size:(i+1)*size] for i in indices)!=raw:
            raise ValueError('Device DSP inputs differ from emulation test inputs')
    rows=[]
    for index,r in enumerate(regions):
        rgb=exact_rgb(raw[index*size:(index+1)*size])
        output=session.run(None,{session.get_inputs()[0].name:rgb.transpose(2,0,1)[None]/255})[0][0].T
        ds=[]
        for row in output:
            if row[71]<.05:
                continue
            x,y,w,h=row[:4]
            ds.append(dict(class_id=67,score=float(row[71]),x1=float((x-w/2)/640),y1=float((y-h/2)/640),
                           x2=float((x+w/2)/640),y2=float((y+h/2)/640)))
        comparisons={'onnx_exact_full':matching(r,nms(ds))}
        for name,array in stages.items():
            ds=[dict(class_id=67,y1=float(d[0]),x1=float(d[1]),y2=float(d[2]),x2=float(d[3]),score=float(d[4]))
                for d in array[index,67].T if d[4]>=.05]
            comparisons[name]=matching(r,ds)
        if device is not None:
            if device[index]['frame']!=index:
                raise ValueError('Wrong device order')
            comparisons['device']=matching(r,device[index]['detections'])
        best={name:max((d['score'] for d in ds if d['iou']>=.5),default=None) for name,ds in comparisons.items()}
        result=dict(index=index,source_frame=r['source_frame'],method=r['method'],best_phone_score_iou05=best,candidates=comparisons)
        rows.append(result)
        print(json.dumps({k:v for k,v in result.items() if k!='candidates'}))
    a.output.write_text(json.dumps(dict(scope='Nine held-out oracle crops, not tracking/COCO accuracy; NMS threshold .05, match IoU .5.',
        input_sha256=hashlib.sha256(raw).hexdigest(),stage_output_hashes=hashes,rows=rows),indent=2))

if __name__=='__main__':
    main()
