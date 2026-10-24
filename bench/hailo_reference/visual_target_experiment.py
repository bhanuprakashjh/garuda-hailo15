"""Offline algorithm exploration. Never writes to the board or uses truth to reset.

This is a development diagnostic, not the deployable implementation. Sparse
phone labels are scoring-only. The initial box is the recorded user selection.
"""
import argparse
import json
from pathlib import Path
import time
import cv2
import numpy as np
from resolution_campaign import predictions, detections
from score_4k_tiles import iou


class Localizer:
    def __init__(self):
        self.box = None
        self.template = None
        self.verified_ms = -1

    def seed(self, image, box, stamp):
        x,y,x2,y2 = np.rint(box).astype(int)
        if x < 0 or y < 0 or x2 > image.shape[1] or y2 > image.shape[0]:
            return False
        patch = image[y:y2,x:x2]
        if min(patch.shape) < 8 or patch.std() < 8:
            return False
        self.template = patch.copy()
        self.box = [x,y,x2,y2]
        self.verified_ms = stamp
        return True

    def locate(self, image, stamp):
        if self.box is None or stamp-self.verified_ms > 750:
            return None, dict(reason='expired')
        x,y,x2,y2 = self.box
        w,h = x2-x,y2-y
        radius = max(w,h)*2
        left,top = max(0,int(x-radius)),max(0,int(y-radius))
        right,bottom = min(image.shape[1],int(x2+radius)),min(image.shape[0],int(y2+radius))
        search = image[top:bottom,left:right]
        candidates = []
        for scale in (.8,.9,1.,1.1,1.2):
            tw,th = round(w*scale),round(h*scale)
            if tw > search.shape[1] or th > search.shape[0] or min(tw,th)<8:
                continue
            template = cv2.resize(self.template,(tw,th))
            result = cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED)
            for _ in range(2):
                _,score,_,loc = cv2.minMaxLoc(result)
                bx,by = loc
                candidates.append((score,[left+bx,top+by,left+bx+tw,top+by+th]))
                result[max(0,by-th//2):by+th//2+1,max(0,bx-tw//2):bx+tw//2+1] = -1
        candidates.sort(reverse=True)
        score,box = candidates[0]
        second = max((s for s,b in candidates[1:] if iou(box,b)<.2),default=-1)
        valid = score >= .65 and score-second >= .08
        if valid:
            self.box = box
        return box if valid else None,dict(score=score,margin=score-second,reason='matched' if valid else 'weak_or_ambiguous')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    campaign=root/'bench/results/2026-09-27-resolution-1024'
    capture=root/'bench/local-baselines/20260922-phone-motion/fast-motion-pc-01'
    truth=json.loads((campaign/'annotations.json').read_text())['fast180']
    inputs=[(r,p) for r,p in predictions(campaign,'phone',1024) if r['clip']=='fast180' and r['method']=='full']
    tracker=Localizer(); rows=[]
    for r,p in inputs:
        index=r['source_frame']
        if index<15:continue
        raw=np.fromfile(r['pixels'],np.uint8)
        gray=raw[:1280*720].reshape(720,1280)
        gray=cv2.resize(gray,(640,360),interpolation=cv2.INTER_AREA)
        stamp=r['timestamp_ns']/1e6
        ds=[dict(box=[v/2 for v in d['box']],score=d['score']) for d in detections(r,p,67) if d['score']>=.4]
        if index==15:
            b=json.loads((capture/'000015.json').read_text())['output']['lock']['box']
            seed=[b['x']/2,b['y']/2,(b['x']+b['w'])/2,(b['y']+b['h'])/2]
            assert tracker.seed(gray,seed,stamp)
            box=seed; diag=dict(reason='selected'); source='selected'
            elapsed=0
        else:
            start=time.perf_counter()
            box,diag=tracker.locate(gray,stamp)
            source='visual' if box else 'missing'
            # Reverification only through overlap with current independent visual evidence.
            nearby=[d for d in ds if box is not None and iou(d['box'],box)>=.3]
            if len(nearby)==1:
                box=nearby[0]['box']
                tracker.seed(gray,box,stamp)
                source='detector'
            elapsed=(time.perf_counter()-start)*1000
        box=[float(v*2) for v in box] if box else None
        gt=truth.get(str(index))
        rows.append(dict(frame=index,box=box,source=source,diag=diag,ms=elapsed,
            iou=iou(box,gt) if box and gt else None,
            detector_match=any(iou([v*2 for v in d['box']],gt)>=.5 for d in ds) if gt else None))
    report=dict(rows=rows,accepted=sum(r['box'] is not None for r in rows),
        correct=sum(r['iou'] is not None and r['iou']>=.5 for r in rows),
        wrong=sum(r['iou'] is not None and r['iou']<.5 for r in rows),
        median_ms=float(np.median([r['ms'] for r in rows])))
    with args.out.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
    print([(r['frame'],r['source'],r['iou'],r['diag']) for r in rows if r['detector_match'] is not None])


if __name__=='__main__':
    cv2.setNumThreads(1)
    main()
