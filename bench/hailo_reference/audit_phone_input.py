"""Bounded diagnostic of four retained phone exposures, not a tracking benchmark.

Reuses existing DSP crop and raw HEF probes, pauses/restores current camera in
finally, never replaces a live model/profile. Oracle crops are diagnostic only.
Manual approximate visible-phone boxes were inspected before these predictions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'bench'))
from run_local_capture_trial import snapshot, ssh

BOXES={0:[598,537,648,639],7:[614,412,664,512],8:[614,405,664,509],12:[633,305,678,401]}
EXPECTED_NODE='0ad699771eb5e1c7fa4b73d373f1be0cc9f5685019ae86724d7f5142c5855124'
EXPECTED_CONFIG='12578dc59850faa29865335f2e17583146fc3bbf08e65d5618aa81aeea7ea333'
EXPECTED_HEF='aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source,metadata,out,network_size=(640,640)):
    nw,nh=network_size
    if any(v<320 or v>1920 or v%32 for v in (nw,nh)):
        raise ValueError('invalid network size')
    regions=[]
    out.mkdir(parents=True,exist_ok=False)
    with (out/'source.nv12').open('xb') as stream:
        for index,box in BOXES.items():
            meta=json.loads((metadata/f'{index:06d}.json').read_text())
            pixels=(source/f'{index:06d}.source.nv12').read_bytes()
            if len(pixels)!=1280*720*3//2 or hashlib.sha256(pixels).hexdigest()!=meta['source_image']['sha256']:
                raise ValueError('source pixel provenance mismatch')
            defs=[('full',0,0,1280,720,True)]
            defs += [(f'corner{k}',x,y,768,432,False) for k,(x,y) in enumerate([(0,0),(512,0),(0,288),(512,288)])]
            for side in (640,320):
                cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
                x=int(min(max(cx-side/2,0),1280-side))//2*2
                y=int(min(max(cy-side/2,0),720-side))//2*2
                defs.append((f'oracle{side}',x,y,side,side,False))
            roi=meta['target_roi'].get('region')
            if roi:defs.append(('recorded_roi',roi['x'],roi['y'],roi['w'],roi['h'],False))
            for method,x,y,w,h,full in defs:
                regions.append(dict(source_frame=index,method=method,source_w=1280,source_h=720,
                                    x=x,y=y,w=w,h=h,full_frame=full,annotation=box,network_w=nw,network_h=nh,
                                    isp_timestamp_ns=meta['isp_timestamp_ns'],exposure_us=meta['isp_ae_integration_time']))
                stream.write(pixels)
    (out/'regions.json').write_text(json.dumps(regions,indent=2)+'\n')
    return regions


def run(args):
    before=snapshot(args.host)
    if (before['node_sha256']!=EXPECTED_NODE or before['config_sha256']!=EXPECTED_CONFIG or
        not before['native_running'] or before['replay_running'] or before['mavros_running'] or
        before['free_bytes']<700*1024*1024):raise ValueError('baseline/resource guard failed')
    if tuple(args.network_size)!=(640,640) and not args.dsp_only:
        raise ValueError('non640 audit requires --dsp-only; frozen model is640')
    regions=prepare(args.source,args.metadata,args.output,args.network_size)
    result=dict(before=before,scope='same saved pixels; oracle crops are NOT deployable tracking results',
                regions=len(regions),network_size=args.network_size,dsp_only=args.dsp_only,
                source_sha256=sha(args.output/'source.nv12'),profile_modified=False)
    stage=ssh(args.host,'mktemp -d /opt/garuda-fresh/input-audit.XXXXXX')
    if not re.fullmatch(r'/opt/garuda-fresh/input-audit\.[A-Za-z0-9]{6}',stage):raise ValueError('unexpected stage')
    result['stage']=stage
    probes=[args.build/'garuda-crop-probe',args.build/'garuda-model-probe']
    files=[*probes,args.output/'regions.json',args.output/'source.nv12']
    result['staged_sha256']={p.name:sha(p) for p in files}
    subprocess.run(['scp','-q',*map(str,files),args.host+':'+stage+'/'],check=True,timeout=60)
    for p in files:
        if ssh(args.host,'sha256sum '+stage+'/'+p.name).split()[0]!=result['staged_sha256'][p.name]:
            raise ValueError('staging hash mismatch')
    hef='/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef'
    if ssh(args.host,'sha256sum '+hef).split()[0]!=EXPECTED_HEF:raise ValueError('HEF changed')
    result['hef_sha256']=EXPECTED_HEF
    ctl=ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh'
    stopped=False
    try:
        stopped=True  # restoration also attempted if stop partially fails
        subprocess.run(['bash',str(ctl),'stop'],check=True,timeout=30)
        commands=[
            ('crop',f'{stage}/garuda-crop-probe {stage}/source.nv12 {stage}/regions.json {stage}/network.nv12 {stage}/crop.jsonl'),
            ('model',f'{stage}/garuda-model-probe {hef} {stage}/network.nv12 0.05')]
        for name,command in commands[:1] if args.dsp_only else commands:
            proc=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',args.host,
                                 'LD_LIBRARY_PATH=/opt/garuda-fresh/lib '+command],capture_output=True,timeout=90)
            (args.output/(name+'.stdout')).write_bytes(proc.stdout)
            (args.output/(name+'.stderr')).write_bytes(proc.stderr)
            result[name+'_returncode']=proc.returncode
            proc.check_returncode()
        subprocess.run(['scp','-q',args.host+':'+stage+'/network.nv12',args.host+':'+stage+'/crop.jsonl',
                        str(args.output)+'/'],check=True,timeout=30)
        result['network_sha256']=sha(args.output/'network.nv12')
        if ssh(args.host,'sha256sum '+stage+'/network.nv12').split()[0]!=result['network_sha256']:
            raise ValueError('network pixel transfer mismatch')
    finally:
        try:
            if stopped:
                restored=subprocess.run(['bash',str(ctl),'start-current'],capture_output=True,text=True,timeout=40)
                result['restore_returncode']=restored.returncode
                result['restore_stdout']=restored.stdout;result['restore_stderr']=restored.stderr
            result['after']=snapshot(args.host)
            result['live_unchanged']=all(result['after'][k]==before[k] for k in ('node_sha256','config_sha256'))
        finally:
            (args.output/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['live_unchanged'] or result.get('restore_returncode')!=0:raise RuntimeError('restoration failed')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='root@10.0.0.1')
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--network-size',type=int,nargs=2,default=(640,640),metavar=('W','H'))
    p.add_argument('--dsp-only',action='store_true')
    a=p.parse_args()
    if a.host!='root@10.0.0.1':raise ValueError('this retained-exposure audit is scoped to the bench board')
    run(a)
