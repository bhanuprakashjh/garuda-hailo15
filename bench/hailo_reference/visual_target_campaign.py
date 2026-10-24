"""Frozen recorded-pixel visual bridge A/B; no live camera or board mutations."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from resolution_campaign import predictions, detections
from score_4k_tiles import iou

ROOT=Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def phone_inputs():
    campaign=ROOT/'bench/results/2026-09-27-resolution-1024'
    capture=ROOT/'bench/local-baselines/20260922-phone-motion/fast-motion-pc-01'
    lines=[]
    for r,p in predictions(campaign,'phone',1024):
        if r['clip']!='fast180' or r['method']!='full':continue
        index=r['source_frame'];pixels=Path(r['pixels'])
        if pixels.stat().st_size!=1382400 or digest(pixels)!=r['source_sha256']:
            raise ValueError('source integrity failure')
        m=json.loads((capture/f'{index:06}.json').read_text());frame=m['frame']
        frame['detections']=[d for d in frame['detections'] if d['label']!='cell phone']
        for d in detections(r,p,67):
            x,y,x2,y2=d['box']
            frame['detections'].append(dict(box=dict(x=x/1280,y=y/720,w=(x2-x)/1280,h=(y2-y)/720),
                confidence=d['score'],label='cell phone',region_id=0,region_full_frame=True))
        lines.append(dict(frame=frame,pixels=str(pixels)))
        if index==15:
            b=m['output']['lock']['box']
            lines.append(dict(cmd='lock_point',x=b['x']+b['w']/2,y=b['y']+b['h']/2,
                sequence=frame['sequence'],now_ms=frame['now_ms']))
    if len(lines)!=181:raise ValueError('incomplete clip')
    return lines


def score(outputs,truth):
    counts=Counter();checks=[];run=longest=0;timings=[]
    for i,o in enumerate(outputs):
        if i<=15:continue
        lock=o['lock'];counts[lock['reason']]+=1
        valid=lock['control_valid'];counts['valid']+=valid
        run=0 if valid else run+1;longest=max(longest,run)
        timings.append(o['visual']['elapsed_ms'])
        if str(i) in truth:
            overlap=None
            if valid:
                b=lock['box'];overlap=iou([b['x'],b['y'],b['x']+b['w'],b['y']+b['h']],truth[str(i)])
            counts['labelled']+=1
            counts['labelled_correct']+=overlap is not None and overlap>=.5
            counts['labelled_wrong']+=overlap is not None and overlap<.5
            checks.append(dict(frame=i,iou=overlap,valid=valid,reason=lock['reason']))
    return dict(counts=dict(counts),longest_missing_frames=longest,labelled=checks,
        visual_median_ms=statistics.median(timings),visual_p95_ms=sorted(timings)[int(.95*(len(timings)-1))])


def aerial_regressions(binary,out):
    """Flag isolation on recorded cars. Not evidence that visual tracking helps cars."""
    report={}
    for name in ('uav0000245_00001_s','uav0000115_00606_s'):
        archive=ROOT/'bench/results/2026-09-27-drone-detail'/(name+'-fullview')
        folder=Path('/media/bhanu1234/Development/hailo-export/visdrone-sot-replay-20260912-roi')/name
        manifest=json.loads((folder/'manifest.json').read_text());source=folder/'source.nv12'
        if digest(source)!=manifest['source_sha256']:raise ValueError('aerial integrity failure')
        records=[json.loads(s) for s in (archive/'outputs.jsonl').read_text().splitlines()]
        trial=json.loads((archive/'trial.json').read_text());lines=[];selected=False
        for row in records:
            o=row['output'];ds=[]
            for d in row['raw_detections']:
                ds.append(dict(box={k:d[k] for k in ('x','y','w','h')},label=d['label'],confidence=d['confidence'],
                    region_id=d.get('region_id',-1),region_full_frame=d.get('region_id')==4))
            frame=dict(sequence=o['sequence'],capture_ms=o['capture_monotonic_ms'],now_ms=o['publish_monotonic_ms'],
                timestamp_valid=o['timestamp_valid'],detections=ds)
            lines.append(dict(frame=frame,pixels=str(source),offset=row['source_index']*1382400))
            if row['source_index']>=trial['select_frame'] and not selected:
                lines.append(dict(cmd='lock_point',x=trial['x'],y=trial['y'],sequence=frame['sequence'],now_ms=frame['now_ms']))
                selected=True
        cfg=out/(name+'-tracking.json')
        cfg.write_text(json.dumps(json.loads((archive/'profile.json').read_text())['tracking']))
        payload=''.join(json.dumps(x)+'\n' for x in lines);results={}
        for mode in ('baseline','candidate'):
            proc=subprocess.run([str(binary),str(cfg),mode],input=payload,text=True,capture_output=True,check=True,timeout=90)
            (out/(name+'-'+mode+'.jsonl')).write_text(proc.stdout)
            rows=[json.loads(s) for s in proc.stdout.splitlines()]
            acks=[r for r in rows if 'ok' in r]
            if acks!=[{'ok':True}]:raise ValueError('aerial selection failed '+str(acks))
            results[mode]=[{k:v for k,v in r.items() if k!='visual'} for r in rows if 'ok' not in r]
        report[name]=dict(frames=len(records),selected=True,source_sha256=manifest['source_sha256'],
            exact_core_parity=results['baseline']==results['candidate'])
        if not report[name]['exact_core_parity']:raise ValueError('non-phone regression')
    (out/'aerial-regressions.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


def render(out):
    """Offline review artifacts; display duration follows capture timestamps."""
    import cv2
    import numpy as np
    captures=[r for r in map(json.loads,(out/'inputs.jsonl').read_text().splitlines()) if 'frame' in r]
    rows={mode:[r for r in map(json.loads,(out/(mode+'.jsonl')).read_text().splitlines()) if 'lock' in r]
          for mode in ('baseline','candidate')}
    video=cv2.VideoWriter(str(out/'comparison.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(1280,400))
    if not video.isOpened():raise RuntimeError('video encoder unavailable')
    crops=[];review=[];written=0
    start=captures[15]['frame']['capture_ms']
    try:
        for i in range(15,len(captures)):
            raw=np.fromfile(captures[i]['pixels'],np.uint8).reshape(1080,1280)
            image=cv2.cvtColor(raw,cv2.COLOR_YUV2BGR_NV12);panels=[]
            for mode in ('baseline','candidate'):
                panel=cv2.resize(image,(640,360));lock=rows[mode][i]['lock']
                visual=lock['reason']=='visual_observed';color=(255,210,0) if visual else (0,230,0)
                if lock['control_valid']:
                    b=lock['box'];x,y,w,h=[round(b[k]/2) for k in ('x','y','w','h')]
                    cv2.rectangle(panel,(x,y),(x+w,y+h),color,2)
                panel=cv2.copyMakeBorder(panel,40,0,0,0,cv2.BORDER_CONSTANT)
                cv2.putText(panel,mode.upper()+'  '+lock['reason'],(10,26),0,.55,color if lock['control_valid'] else (0,120,255),1)
                panels.append(panel)
            joined=np.hstack(panels)
            cv2.putText(joined,f'Frame {i} | recorded cadence | not live',(10,390),0,.5,(255,255,255),1)
            end=captures[i+1]['frame']['capture_ms'] if i+1<len(captures) else captures[i]['frame']['capture_ms']+200
            target=round((end-start)*25/1000)
            while written<target:video.write(joined);written+=1
            lock=rows['candidate'][i]['lock']
            if lock['reason']=='visual_observed':
                b=lock['box'];x,y,w,h=[round(b[k]) for k in ('x','y','w','h')]
                left=max(0,min(1040,x+w//2-120));top=max(0,min(520,y+h//2-100))
                crop=image[top:top+200,left:left+240].copy()
                cv2.rectangle(crop,(x-left,y-top),(x+w-left,y+h-top),(0,220,255),1)
                cv2.putText(crop,str(i),(8,22),0,.65,(0,255,0),2);crops.append(crop)
                review.append(dict(frame=i,box=b,crop=[left,top,240,200]))
    finally:video.release()
    for page in range((len(crops)+19)//20):
        ims=crops[20*page:20*(page+1)]
        while len(ims)%4:ims.append(np.zeros_like(ims[0]))
        cv2.imwrite(str(out/f'visual-review-{page}.jpg'),np.vstack([np.hstack(ims[i:i+4]) for i in range(0,len(ims),4)]))
    (out/'visual-review.json').write_text(json.dumps(dict(scope='Qualitative candidate-aware review, not blind ground truth',frames=review),indent=2)+'\n')


def short_phone_checks(binary,out):
    """Two untouched short captures; acquisition from detections, no truth/reset."""
    report={}
    for name in ('garuda-fresh-input-868132492454','garuda-fresh-input-868156973667'):
        folder=ROOT/'bench/local-baselines/20260922-phone-motion'/name
        files=sorted(p for p in folder.glob('*.json') if p.stem.isdigit());lines=[];hashes={}
        for path in files:
            m=json.loads(path.read_text());pixels=path.with_suffix('.nv12')
            if pixels.stat().st_size!=640*640*3//2 or m['geometry']!='letterbox':raise ValueError('unexpected old capture geometry')
            hashes[pixels.name]=digest(pixels)
            if not lines:lines.append(dict(cmd='target',**{'class':'cell phone'},now_ms=m['frame']['capture_ms']))
            lines.append(dict(frame=m['frame'],pixels=str(pixels),width=640,height=640,
                letterbox=True,display_width=1280,display_height=720))
        results={};payload=''.join(json.dumps(r)+'\n' for r in lines)
        for mode in ('baseline','candidate'):
            proc=subprocess.run([str(binary),str(out/'tracking.json'),mode],input=payload,text=True,capture_output=True,check=True,timeout=30)
            (out/(name+'-'+mode+'.jsonl')).write_text(proc.stdout)
            rows=[json.loads(s) for s in proc.stdout.splitlines()]
            if rows.pop(0)!={'ok':True} or len(rows)!=12:raise ValueError('short capture replay failed')
            acquired=next((i for i,r in enumerate(rows) if r['lock']['control_valid']),None)
            results[mode]=dict(first_acquired_frame=acquired,valid=sum(r['lock']['control_valid'] for r in rows),
                visual=sum(r['lock']['reason']=='visual_observed' for r in rows))
        report[name]=dict(frames=12,pixel_sha256=hashes,results=results)
    (out/'short-phone-checks.json').write_text(json.dumps(dict(scope='Untuned short capture checks; no independent labels, not a fast-motion qualification',clips=report),indent=2)+'\n')
    print(json.dumps({k:v['results'] for k,v in report.items()},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--regressions',action='store_true')
    p.add_argument('--render',action='store_true')
    p.add_argument('--short-phone',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    lines=phone_inputs();payload=''.join(json.dumps(r)+'\n' for r in lines)
    (a.out/'inputs.jsonl').write_text(payload)
    profile=ROOT/'bench/results/2026-09-27-live-1024-final/candidate.json'
    cfg=json.loads(profile.read_text())['tracking'];config=a.out/'tracking.json'
    config.write_text(json.dumps(cfg,indent=2)+'\n')
    truth=json.loads((ROOT/'bench/results/2026-09-27-resolution-1024/annotations.json').read_text())['fast180']
    report=dict(scope='Fast180 development clip; full-frame1024 phone predictions, original non-phone detections and timestamps. Fixed schedule, sparse approximate labels; not live or flight qualification.',
        profile_sha256=digest(profile),binary_sha256=digest(a.binary),inputs_sha256=digest(a.out/'inputs.jsonl'))
    for mode in ('baseline','candidate'):
        proc=subprocess.run([str(a.binary),str(config),mode],input=payload,text=True,capture_output=True,check=True,timeout=90)
        (a.out/(mode+'.jsonl')).write_text(proc.stdout)
        rows=[json.loads(s) for s in proc.stdout.splitlines()]
        if len(rows)!=181 or rows.pop(16)!={'ok':True}:raise ValueError('selection/count failure')
        report[mode]=score(rows,truth)
    (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if a.regressions:aerial_regressions(a.binary,a.out)
    if a.render:render(a.out)
    if a.short_phone:short_phone_checks(a.binary,a.out)


if __name__=='__main__':main()
