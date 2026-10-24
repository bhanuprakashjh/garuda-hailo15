"""Score fixed-pixel filter ablation and native detail probes; no new ISP experiment."""
import argparse
import hashlib
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import subprocess

from audit_phone_input import ROOT
from score_4k_tiles import map_box, iou
from score_phone_input_audit import border_rejected


def load(root, prefix, manifest):
    regions = json.loads((root/(manifest+'-regions.json')).read_text())
    predictions = [json.loads(x) for x in (root/(prefix+'.jsonl')).read_text().splitlines()]
    if len(regions) != len(predictions) or any(p['frame'] != i for i,p in enumerate(predictions)):
        raise ValueError('incomplete or reordered predictions')
    return list(zip(regions, predictions))


def phones(r, p, policy, floor=.15):
    out = []
    for d in p['pre_filter']:
        if d['class_id'] != 67 or d['score'] < floor:
            continue
        cut = border_rejected(r,d,.015) if r['method']=='recorded_roi' else d[policy+'_cut']
        b = map_box(r,d)
        if cut or b is None:
            continue
        if r['method'].startswith('corner') and (b[2]-b[0])*(b[3]-b[1])/(r['source_w']*r['source_h'])>.05:
            continue
        out.append(dict(box=b, score=d['score'], region=r['method']))
    return out


def merge(ds):
    kept=[]
    for d in sorted(ds,key=lambda x:x['score'],reverse=True):
        if not any(d['region']!=k['region'] and iou(d['box'],k['box'])>.3 for k in kept):
            kept.append(d)
    return kept


def summarize_phone(root, rows, annotations):
    grouped=defaultdict(list)
    for r,p in rows: grouped[(r['clip'],r['source_frame'])].append((r,p))
    result={};changes=[]
    for clip in ('fast180','recent4'):
        result[clip]={}
        for policy in ('fixed','relative'):
            counts=Counter();details=[]
            for (name,index), pairs in sorted(grouped.items()):
                if name!=clip:continue
                ds=merge([d for r,p in pairs if r['method']!='recorded_roi' for d in phones(r,p,policy)])
                counts['frames']+=1
                for floor in (.15,.4,.5):
                    counts['any_phone_at_'+str(floor)]+=any(d['score']>=floor for d in ds)
                truth=annotations[clip].get(str(index))
                if truth:
                    counts['labelled']+=1
                    for floor in (.15,.4,.5):
                        counts['matched_at_'+str(floor)]+=any(d['score']>=floor and iou(d['box'],truth)>=.5 for d in ds)
                        counts['unmatched_boxes_at_'+str(floor)]+=sum(d['score']>=floor and iou(d['box'],truth)<.5 for d in ds)
                    details.append(dict(frame=index, boxes=ds, truth=truth))
            result[clip][policy]=dict(counts=counts,labelled_rows=details)
        for (name,index),pairs in sorted(grouped.items()):
            if name!=clip:continue
            for r,p in pairs:
                if not r['method'].startswith('corner'):continue
                for d in p['pre_filter']:
                    if d['class_id']==67 and d['score']>=.15 and d['fixed_cut'] and not d['relative_cut']:
                        changes.append(dict(clip=clip,frame=index,method=r['method'],score=d['score'],box=map_box(r,d)))
    return dict(scope='five-tile detection availability on all saved exposures, not deployed adaptive schedule; sparse manual truth',
                clips=result, newly_admitted_phone_boxes=changes)


def native_summary(root):
    out=[]
    direct=load(root,'native-direct','native');via=load(root,'native-via720','native')
    for (r,a),(s,b) in zip(direct,via):
        if r!=s:raise ValueError('unpaired geometry')
        scores={}
        for name,p in [('direct',a),('via720',b)]:
            ds=[d for d in p['pre_filter'] if d['class_id']==67 and
                map_box(r,d) is not None and iou(map_box(r,d),r['annotation'])>=.5]
            scores[name]=max((d['score'] for d in ds),default=None)
        out.append(dict(frame=r['source_frame'],method=r['method'],scores=scores))
    return dict(scope='same decoded4K exposure and exactly equal field of view; DSP720 approximation of ISP720; oracle windows; not tracking',rows=out)


def replay(root, rows, binary, annotations, profile):
    capture=ROOT/'bench/local-baselines/20260922-phone-motion/fast-motion-pc-01'
    groups=defaultdict(list)
    for r,p in rows:
        if r['clip']=='fast180':groups[r['source_frame']].append((r,p))
    cfg=json.loads(profile.read_text())['tracking']
    (root/'replay-tracking.json').write_text(json.dumps(cfg,indent=2)+'\n')
    results={}
    for policy in ('fixed','relative'):
        lines=[]
        for index in range(180):
            m=json.loads((capture/f'{index:06d}.json').read_text());frame=m['frame']
            frame['detections']=[d for d in frame['detections'] if d['label']!='cell phone']
            ds=[]
            for r,p in groups[index]:
                if r['method'].startswith('corner') and m['detection_tiles']['reason']!='tiled':continue
                ds.extend(phones(r,p,policy))
            for d in merge(ds):
                x,y,x2,y2=d['box'];method=d['region']
                frame['detections'].append(dict(box=dict(x=x/1280,y=y/720,w=(x2-x)/1280,h=(y2-y)/720),
                    label='cell phone',confidence=d['score'],appearance=None,
                    region_id=4 if method=='full' else (int(method[-1]) if method.startswith('corner') else 5),
                    region_full_frame=method=='full'))
            lines.append(json.dumps(dict(frame=frame,pixels=str(capture/f'{index:06d}.source.nv12'))))
            if index==15:
                box=m['output']['lock']['box']
                if not m['output']['lock']['control_valid']:raise ValueError('selection not observed')
                lines.append(json.dumps(dict(cmd='lock_point',x=box['x']+box['w']/2,y=box['y']+box['h']/2,
                                            sequence=frame['sequence'],now_ms=frame['now_ms'])))
        proc=subprocess.run([str(binary),str(root/'replay-tracking.json')],input='\n'.join(lines)+'\n',text=True,
                            capture_output=True,check=True,timeout=60)
        (root/(policy+'-core.jsonl')).write_text(proc.stdout)
        outputs=[json.loads(x) for x in proc.stdout.splitlines()]
        if len(outputs)!=181:raise ValueError('unexpected replay count')
        ack=outputs.pop(16)
        if ack!={'ok':True}:raise ValueError('selection failed '+str(ack))
        counts=Counter();checks=[]
        for i,o in enumerate(outputs):
            if i<=15:continue
            counts[o['lock']['reason']]+=1
            counts['control_valid']+=o['lock']['control_valid']
            truth=annotations['fast180'].get(str(i))
            if truth and o['lock']['control_valid']:
                b=o['lock']['box'];overlap=iou([b['x'],b['y'],b['x']+b['w'],b['y']+b['h']],truth)
                checks.append(dict(frame=i,iou=overlap))
        results[policy]=dict(counts=counts,labelled_control_valid=checks)
    return dict(scope='fixed recorded schedule/ROIs/timestamps and non-phone detections; recomputed phone appearance; select15; not adaptive/live tracking qualification',
                profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),policies=results)


def isp_inventory(rows):
    frames={}
    for r,_ in rows:frames[(r['clip'],r['source_frame'])]=r
    exposures=Counter(r['exposure_us'] for r in frames.values())
    telemetry={};keys={}
    for name in ('desk-exposure15ms','desk-3dnr-off','desk-gap500'):
        path=Path('/tmp/garuda-live-review-prichT')/(name+'.jsonl')
        if not path.exists():
            telemetry[name]=dict(available=False);continue
        count=0;missing=0;ids=set();times=[];digest=hashlib.sha256()
        with path.open('rb') as f:
            for line in f:
                digest.update(line);j=json.loads(line);s=j['state'];count+=1
                if 'capture_monotonic_ms' not in s or not s.get('sequence'):
                    missing+=1;continue
                ids.add((s.get('clock_domain'),s.get('stream_id'),s.get('sequence')))
                times.append(s['capture_monotonic_ms'])
        keys[name]=ids
        telemetry[name]=dict(available=True,path=str(path),sha256=digest.hexdigest(),rows=count,
                             unique_states=len(ids),missing_frame_state=missing,
                             capture_ms_min=min(times) if times else None,capture_ms_max=max(times) if times else None,
                             paired_pixel_frames=False)
    overlap=len(keys.get('desk-3dnr-off',set()) & keys.get('desk-gap500',set()))
    return dict(exposure_us_counts=exposures,telemetry=telemetry,off_gap500_shared_states=overlap,
                conclusion='No matched short-exposure/NR-on-off pixel comparison in these retained inputs. Settings cannot be changed retrospectively; do not treat overlapping telemetry as independent trials.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('--native',type=Path);p.add_argument('--replay',type=Path)
    p.add_argument('--profile',type=Path)
    a=p.parse_args();rows=load(a.root,'phone','phone');annotations=json.loads((a.root/'annotations.json').read_text())
    if a.replay and not a.profile:p.error('--replay requires an explicit frozen --profile')
    report=dict(phone=summarize_phone(a.root,rows,annotations),isp=isp_inventory(rows))
    if a.native:report['native']=native_summary(a.native)
    if a.replay:report['core']=replay(a.root,rows,a.replay,annotations,a.profile)
    with (a.root/'summary.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({clip:{p:v['counts'] for p,v in d.items()} for clip,d in report['phone']['clips'].items()},indent=2))
    if 'native' in report:print(json.dumps(report['native'],indent=2))
    if 'core' in report:print(json.dumps(report['core'],indent=2))


if __name__=='__main__':main()
