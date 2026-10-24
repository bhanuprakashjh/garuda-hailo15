"""Recorded same-weights resolution A/B; never deploys the candidate to live.

Streams one source frame at a time from PC. No tracker, training, new recording,
flight commands, ISP changes, or ground-truth-driven crop selection.
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
import urllib.request

from recorded_input_campaign import sha, stream_probe
from audit_phone_input import ROOT, EXPECTED_NODE, EXPECTED_CONFIG, EXPECTED_HEF
from run_local_capture_trial import snapshot, ssh
from score_4k_tiles import map_box, iou
from score_recorded_input import merge

BASELINE = '/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef'
AERIAL = Path('/media/bhanu1234/Development/hailo-export/visdrone-sot-replay-20260912-roi')
OLD = ROOT/'bench/results/2026-09-27-recorded-input'


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    phone = [r for r in json.loads((OLD/'phone-regions.json').read_text()) if r['method'] != 'recorded_roi']
    checked = set()
    for r in phone:
        path = Path(r['pixels'])
        if path not in checked:
            if path.stat().st_size != 1382400 or sha(path) != r['source_sha256']:
                raise ValueError('phone source changed')
            checked.add(path)
    aerial = []
    for name, cls in [('uav0000245_00001_s', 2), ('uav0000115_00606_s', 2), ('uav0000024_00000_s', 0)]:
        folder = AERIAL/name
        m = json.loads((folder/'manifest.json').read_text())
        source = folder/'source.nv12'
        if m['canvas'] != [1280, 720] or source.stat().st_size != m['frames']*1382400 or sha(source) != m['source_sha256']:
            raise ValueError('aerial source provenance mismatch')
        for index in range(0, m['frames'], 16):
            target = m['targets'][index]
            if target['index'] != index:
                raise ValueError('target/frame mismatch')
            x,y,w,h = target['box']
            aerial.append(dict(clip=name, source_frame=index, method='full', source_w=1280, source_h=720,
                x=0,y=0,w=1280,h=720,full_frame=True,pixels=str(source),offset=index*1382400,
                source_sha256=m['source_sha256'],class_id=cls,annotation=[x,y,x+w,y+h]))
    for name, rows in [('phone',phone),('aerial',aerial)]:
        (out/(name+'-regions.json')).write_text(json.dumps(rows,indent=2)+'\n')
    (out/'annotations.json').write_bytes((OLD/'annotations.json').read_bytes())
    print(json.dumps(dict(phone_regions=len(phone),aerial_frames=len(aerial))),flush=True)


def run(out, probe, hef):
    if (out/'run.json').exists():
        raise ValueError('refusing to overwrite a completed/failed run')
    before = snapshot('root@10.0.0.1')
    if (before['node_sha256'] != EXPECTED_NODE or before['config_sha256'] != EXPECTED_CONFIG or
        not before['native_running'] or before['replay_running'] or before['mavros_running'] or
        before['free_bytes'] < 512*1024*1024 + hef.stat().st_size):
        raise ValueError('baseline/resource guard')
    with urllib.request.urlopen('http://10.0.0.1:8099/api/state',timeout=5) as f:
        if json.load(f)['diag']['capture_stream']['active']:
            raise ValueError('recording active')
    if ssh('root@10.0.0.1','sha256sum '+BASELINE).split()[0] != EXPECTED_HEF:
        raise ValueError('baseline HEF changed')
    stage = ssh('root@10.0.0.1','mktemp -d /opt/garuda-fresh/resolution-audit.XXXXXX')
    if not re.fullmatch(r'/opt/garuda-fresh/resolution-audit\.[A-Za-z0-9]{6}',stage):
        raise ValueError('unexpected stage')
    files=[probe,hef,out/'phone-regions.json',out/'aerial-regions.json']
    hashes={p.name:sha(p) for p in files}
    subprocess.run(['scp','-q',*map(str,files),'root@10.0.0.1:'+stage+'/'],check=True,timeout=90)
    for name,digest in hashes.items():
        if ssh('root@10.0.0.1','sha256sum '+stage+'/'+name).split()[0] != digest:
            raise ValueError('staging hash mismatch')
    result=dict(before=before,stage=stage,staged_sha256=hashes,baseline_hef_sha256=EXPECTED_HEF,
        scope='same recorded source pixels and weights; fixed geometry; no tracking or live FPS qualification')
    ctl=ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh'
    env=dict(os.environ,GARUDA_H15L_HOST='root@10.0.0.1')
    try:
        subprocess.run(['bash',str(ctl),'stop'],env=env,check=True,timeout=30)
        for dataset in ('phone','aerial'):
            rows=json.loads((out/(dataset+'-regions.json')).read_text())
            for width,model in [(640,BASELINE),(1024,stage+'/'+hef.name)]:
                stream_probe(stage,dataset+'-'+str(width),rows,out,hef=model,manifest=dataset)
    finally:
        try:
            p=subprocess.run(['bash',str(ctl),'start-current'],env=env,capture_output=True,text=True,timeout=40)
            result.update(restore_returncode=p.returncode,restore_stdout=p.stdout,restore_stderr=p.stderr)
            result['after']=snapshot('root@10.0.0.1')
            result['live_hef_after']=ssh('root@10.0.0.1','sha256sum '+BASELINE).split()[0]
            result['live_unchanged']=all(result['after'][k]==before[k] for k in ('node_sha256','config_sha256')) and result['live_hef_after']==EXPECTED_HEF
        finally:
            (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['live_unchanged'] or result['restore_returncode'] or not result['after']['native_running']:
        raise RuntimeError('restoration failed')


def predictions(out,dataset,width):
    rows=json.loads((out/(dataset+'-regions.json')).read_text())
    ps=[json.loads(s) for s in (out/(dataset+'-'+str(width)+'.jsonl')).read_text().splitlines()]
    if len(rows)!=len(ps): raise ValueError('incomplete predictions')
    for i,(r,p) in enumerate(zip(rows,ps)):
        if p['frame']!=i or (p['network_w'],p['network_h']) != (width,640 if width==640 else 576):
            raise ValueError('wrong order/network dimensions')
        yield dict(r,network_w=p['network_w'],network_h=p['network_h']),p


def detections(r,p,cls):
    ds=[]
    for d in p['pre_filter']:
        if d['class_id']!=cls or d['fixed_cut']:continue
        b=map_box(r,d)
        if b is None:continue
        if r['method'].startswith('corner') and (b[2]-b[0])*(b[3]-b[1])/(r['source_w']*r['source_h'])>.05:continue
        ds.append(dict(box=b,score=d['score'],region=r['method']))
    return ds


def timing(ps):
    values=[sum(p[k] for k in ('source_copy_ms','dsp_ms','input_copy_ms','inference_ms')) for p in ps]
    return dict(samples=len(values),median_ms=statistics.median(values),mean_ms=statistics.mean(values),
                p95_ms=sorted(values)[int((len(values)-1)*.95)])


def score(out):
    annotations=json.loads((out/'annotations.json').read_text())
    report=dict(scope='Detection only; paired saved pixels. Phone truth sparse/approximate, aerial SOT one labelled target. Not independent held-out validation or live tracking.',phone={},aerial={})
    old_regions=json.loads((OLD/'phone-regions.json').read_text())
    old_predictions=[json.loads(s) for s in (OLD/'phone.jsonl').read_text().splitlines()]
    if len(old_regions)!=len(old_predictions):raise ValueError('incomplete archived baseline')
    old={(r['clip'],r['source_frame'],r['method']):p for r,p in zip(old_regions,old_predictions)}
    current=list(predictions(out,'phone',640))
    report['baseline_repeat']=dict(regions=len(current),
        exact_pre_filter_matches=sum(p['pre_filter']==old[r['clip'],r['source_frame'],r['method']]['pre_filter'] for r,p in current),
        exact_post_filter_matches=sum(p['detections']==old[r['clip'],r['source_frame'],r['method']]['detections'] for r,p in current))
    for width in (640,1024):
        phone=list(predictions(out,'phone',width))
        for mode in ('full','five_tile'):
            groups=defaultdict(list)
            for r,p in phone:
                if mode=='full' and r['method']!='full':continue
                groups[r['clip'],r['source_frame']].append((r,p))
            for clip in ('fast180','recent4'):
                details=[]; times=[]
                for (name,index),pairs in sorted(groups.items()):
                    if name!=clip:continue
                    ds=merge([d for r,p in pairs for d in detections(r,p,67)])
                    truth=annotations[clip].get(str(index))
                    details.append(dict(frame=index,truth=truth,detections=ds))
                    times.append(sum(sum(p[k] for k in ('source_copy_ms','dsp_ms','input_copy_ms','inference_ms')) for r,p in pairs))
                metrics={}
                for floor in (.15,.4,.5):
                    metrics[str(floor)]=dict(any_phone=sum(any(d['score']>=floor for d in row['detections']) for row in details),
                        matched=sum(any(d['score']>=floor and iou(d['box'],row['truth'])>=.5 for d in row['detections']) for row in details if row['truth']),
                        unmatched_boxes=sum(sum(d['score']>=floor and iou(d['box'],row['truth'])<.5 for d in row['detections']) for row in details if row['truth']))
                report['phone'][f'{clip}-{width}-{mode}']=dict(frames=len(details),labelled=sum(bool(row['truth']) for row in details),
                    thresholds=metrics,median_stage_sum_ms=statistics.median(times),rows=details)
        grouped=defaultdict(list)
        for r,p in predictions(out,'aerial',width):grouped[r['clip']].append((r,p))
        for clip,pairs in grouped.items():
            details=[]
            for r,p in pairs:
                ds=detections(r,p,r['class_id'])
                details.append(dict(frame=r['source_frame'],truth=r['annotation'],best_score=max((d['score'] for d in ds if iou(d['box'],r['annotation'])>=.5),default=0)))
            report['aerial'][f'{clip}-{width}']=dict(frames=len(details),
                matched={str(f):sum(row['best_score']>=f for row in details) for f in (.15,.4,.5)},timing=timing([p for _,p in pairs]),rows=details)
    with (out/'summary.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({kind:{k:{a:b for a,b in v.items() if a!='rows'} for k,v in report[kind].items()} for kind in ('phone','aerial')},indent=2))


def float_check(out, work):
    import numpy as np
    import onnxruntime as ort
    from score_controlled_yolo11 import exact_rgb
    parity=json.loads((work/'export-parity.json').read_text())
    model=work/'yolo11s-1024x576.onnx'
    if not parity['passed'] or sha(model)!=next(e['sha256'] for e in parity['exports'] if e['width']==1024):
        raise ValueError('unverified float export')
    inputs=work/'dsp-inputs'
    run=json.loads((inputs/'run.json').read_text())
    raw=(inputs/'network.nv12').read_bytes()
    if sha(inputs/'network.nv12')!=run['network_sha256']:raise ValueError('DSP pixels changed')
    rs=json.loads((inputs/'regions.json').read_text());size=1024*576*3//2
    if len(raw)!=len(rs)*size:raise ValueError('DSP length mismatch')
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    session=ort.InferenceSession(str(model),opts,providers=['CPUExecutionProvider'])
    if session.get_inputs()[0].shape!=[1,3,576,1024]:raise ValueError('wrong float input shape')
    rows=[]
    for index,r in enumerate(rs):
        if r['method']!='full' and not r['method'].startswith('corner'):continue
        tensor=exact_rgb(raw[index*size:(index+1)*size],1024,576).transpose(2,0,1)[None]/255
        pred=session.run(None,{'images':tensor})[0]
        if pred.shape!=(1,84,12096) or not np.isfinite(pred).all():raise ValueError('invalid float output')
        matches=[]
        for candidate in pred[0].T:
            if candidate[71]<.05:continue
            x,y,w,h=candidate[:4]
            d=dict(x1=float((x-w/2)/1024),x2=float((x+w/2)/1024),y1=float((y-h/2)/576),y2=float((y+h/2)/576))
            b=map_box(r,d)
            if b is not None and iou(b,r['annotation'])>=.5:matches.append(float(candidate[71]))
        rows.append(dict(frame=r['source_frame'],method=r['method'],best_pre_nms_phone_score=max(matches,default=None)))
    report=dict(scope='Four retained exposures; best matching pre-NMS proposals at IoU .5, score >= .05. Not deployment equivalence or tracking.',
        onnx_sha256=sha(model),network_sha256=run['network_sha256'],rows=rows)
    with (out/'float-check.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))


def verify(out):
    def state():
        with urllib.request.urlopen('http://10.0.0.1:8099/api/state',timeout=5) as f:return json.load(f)
    first=state();time.sleep(2);last=state()
    board=snapshot('root@10.0.0.1')
    hef=ssh('root@10.0.0.1','sha256sum '+BASELINE).split()[0]
    controls=ssh('root@10.0.0.1','v4l2-ctl -d /dev/video0 --get-ctrl=isp_ae_enable,isp_ae_integration_time,isp_ae_gain,isp_3dnr_enable,isp_3dnr_mode,isp_3dnr_strength')
    capture=last['diag']['capture_stream']
    advancing=bool(last['stream_id']) and first['stream_id']==last['stream_id'] and last['sequence']>first['sequence']
    passed=(board['node_sha256']==EXPECTED_NODE and board['config_sha256']==EXPECTED_CONFIG and hef==EXPECTED_HEF and
        board['native_running'] and not board['replay_running'] and not board['mavros_running'] and
        not capture['active'] and advancing and last['timestamp_valid'])
    sources=['hosts/hailo15l/crop_probe.cpp','hosts/hailo15l/region_probe.cpp',
        'hosts/hailo15l/region_detector.cpp','hosts/hailo15l/dsp_crop.cpp',
        'services/garuda-tracking/src/search_region.cpp','services/garuda-tracking/tests/test_search_region.cpp']
    sources+=['bench/hailo_reference/'+name+'.py' for name in ('export_resolution_candidate','build_resolution_trial',
        'build_controlled_yolo11','audit_phone_input','recorded_input_campaign','resolution_campaign',
        'score_controlled_yolo11','score_4k_tiles','test_resolution_campaign','test_phone_input_audit')]
    result=dict(passed=bool(passed),board=board,hef_sha256=hef,isp_controls=controls,
        live_states=[{k:s[k] for k in ('stream_id','sequence','timestamp_valid')} for s in (first,last)],
        capture_stream=capture,source_sha256={p:sha(ROOT/p) for p in sources},
        summary_sha256=sha(out/'summary.json'),uname_pc=subprocess.check_output(['uname','-a'],text=True).strip())
    with (out/'final-check.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
    if not passed:raise RuntimeError('final live health/provenance check failed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run','score','float-check','verify']);p.add_argument('output',type=Path)
    p.add_argument('--probe',type=Path);p.add_argument('--hef',type=Path)
    p.add_argument('--work',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.output)
    elif a.action=='run':
        if not a.probe or not a.hef:p.error('run requires --probe and --hef')
        run(a.output,a.probe,a.hef)
    elif a.action=='float-check':
        if not a.work:p.error('float-check requires --work')
        float_check(a.output,a.work)
    elif a.action=='verify':verify(a.output)
    else:score(a.output)


if __name__=='__main__':main()
