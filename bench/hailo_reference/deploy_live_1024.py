"""Owner-authorized bench deployment: full-frame 1024, no tiles or ROI detector.

Keeps the running binary, tracker/re-ID policy, sensor and IQ files unchanged.
Stages isolated camera settings/model, atomically switches current.json, and
restores the previous config on failed startup or bounded health validation.
No boot changes, recording, dependency install or flight commands.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import urllib.request

from audit_phone_input import ROOT, EXPECTED_NODE, EXPECTED_CONFIG, EXPECTED_HEF
from recorded_input_campaign import sha
from run_local_capture_trial import snapshot, ssh

HOST='root@10.0.0.1'
BASE='/opt/garuda-fresh'
CANDIDATE_SHA='bb9fe29b984e296be1cf15c8b934aca7514428ed2d1d4cc54f6bd11017efab43'


def state():
    with urllib.request.urlopen('http://10.0.0.1:8099/api/state',timeout=3) as f:return json.load(f)


def configuration(current, media, profile, app, stage):
    cfg=copy.deepcopy(current);new_media=copy.deepcopy(media)
    new_profile=copy.deepcopy(profile);new_app=copy.deepcopy(app)
    if cfg['frame_w']!=1280 or cfg['frame_h']!=720 or cfg.get('native_stream'):
        raise ValueError('unexpected baseline geometry')
    cfg.update(hef=stage+'/model.hef',medialib_config=stage+'/medialib.json',profile='GarudaFresh1024Full',
        input_w=1024,input_h=576,input_geometry='letterbox',managed_detection=False,
        detection_tiles=False,tiles_when_unlocked=False,target_roi='off',target_roi_hef=stage+'/model.hef',
        # 1024 NV12 +720p source exceeds the existing2MiB diagnostic packet cap.
        # Keep that guard: network-only diagnostic capture; re-ID still owns its source cache.
        capture_source=False)
    streams=new_app['application_input_streams']['resolutions']
    matches=[s for s in streams if s['stream_id']==cfg['ai_stream']]
    if len(matches)!=1 or (matches[0]['width'],matches[0]['height'])!=(640,640):
        raise ValueError('unexpected frontend AI stream')
    matches[0].update(width=1024,height=576,scaling_mode='LETTERBOX_MIDDLE')
    new_profile['application_settings']=stage+'/application.json'
    new_media['default_profile']=cfg['profile']
    new_media['profiles'].append(dict(name=cfg['profile'],config_file=stage+'/profile.json'))
    return {'candidate.json':cfg,'medialib.json':new_media,'profile.json':new_profile,'application.json':new_app}


def healthy(s):
    diag=s['diag'];embedding=diag['person_embedding']
    # The deployed publisher omits these sections when the respective detector
    # object is absent. Also verify the actual current.json hash against the
    # generated full-view config below; absence alone is not a model-shape check.
    tiles=diag.get('detection_tiles',dict(enabled=False,managed_detection=False,detector_passes_this_frame=1))
    roi=diag.get('target_roi',dict(mode='off',inferences=0))
    return (s.get('timestamp_valid') is True and s['age_ms']<500 and
        not tiles['enabled'] and not tiles.get('managed_detection',True) and
        tiles.get('detector_passes_this_frame')==1 and roi['mode']=='off' and roi.get('inferences',0)==0 and
        not tiles.get('faulted',False) and not roi.get('faulted',False) and
        not embedding.get('faulted',False) and not diag['capture_stream']['active'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path);p.add_argument('--hef',type=Path,required=True)
    a=p.parse_args()
    if sha(a.hef)!=CANDIDATE_SHA:raise ValueError('wrong candidate model')
    before=snapshot(HOST);initial=state()
    if (before['node_sha256']!=EXPECTED_NODE or before['config_sha256']!=EXPECTED_CONFIG or
        not before['native_running'] or before['replay_running'] or before['mavros_running'] or
        before['free_bytes']<700*1024*1024 or initial['diag']['capture_stream']['active'] or
        initial['diag']['input_capture'].get('remaining',0)):
        raise ValueError('baseline/resource/recording guard')
    a.output.mkdir(parents=True,exist_ok=False)
    def read(path,name):
        raw=ssh(HOST,'cat '+shlex.quote(path))+'\n'
        (a.output/name).write_text(raw)
        return json.loads(raw)
    # Preserve the exact bytes (including whitespace) for a hash-identical rollback.
    subprocess.run(['scp','-q',HOST+':'+BASE+'/current.json',str(a.output/'previous-current.json')],check=True,timeout=20)
    if sha(a.output/'previous-current.json')!=EXPECTED_CONFIG:raise ValueError('baseline changed')
    current=json.loads((a.output/'previous-current.json').read_text())
    media=read(current['medialib_config'],'previous-medialib.json')
    path=next(x['config_file'] for x in media['profiles'] if x['name']==current['profile'])
    profile=read(path,'previous-profile.json')
    app=read(profile['application_settings'],'previous-application.json')
    protected=[BASE+'/garuda-fresh-tracking',current['hef'],current['person_reid_hef'],
        current['medialib_config'],path,profile['application_settings'],profile['iq_settings'],
        profile['sensor_config'],profile['stabilizer_settings'],current['postprocess_config']]
    def hashes():return {path:ssh(HOST,'sha256sum '+shlex.quote(path)).split()[0] for path in protected}
    protected_before=hashes()
    if protected_before[current['hef']]!=EXPECTED_HEF:raise ValueError('baseline model changed')
    stage=ssh(HOST,'mktemp -d /opt/garuda-fresh/live-1024.XXXXXX')
    if not re.fullmatch(r'/opt/garuda-fresh/live-1024\.[A-Za-z0-9]{6}',stage):raise ValueError('unexpected stage')
    configs=configuration(current,media,profile,app,stage)
    for name,value in configs.items():(a.output/name).write_text(json.dumps(value,indent=2)+'\n')
    files=[a.output/name for name in (*configs,'previous-current.json')]
    subprocess.run(['scp','-q',*map(str,files),HOST+':'+stage+'/'],check=True,timeout=30)
    subprocess.run(['scp','-q',str(a.hef),HOST+':'+stage+'/model.hef'],check=True,timeout=60)
    staged={f.name:sha(f) for f in files};staged['model.hef']=CANDIDATE_SHA
    for name,digest in staged.items():
        if ssh(HOST,'sha256sum '+stage+'/'+name).split()[0]!=digest:raise ValueError('staging mismatch')
    ctl=ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh';env=dict(os.environ,GARUDA_H15L_HOST=HOST)
    def lifecycle(action):
        return subprocess.run(['bash',str(ctl),action],env=env,check=True,capture_output=True,text=True,timeout=45).stdout
    def activate(name):
        ssh(HOST,f'cp {stage}/{name} {stage}/activate.json && mv {stage}/activate.json {BASE}/current.json')
    result=dict(before=before,initial_state=initial,stage=stage,staged_sha256=staged,protected_before=protected_before,
        scope='owner-authorized live bench trial, not product/flight qualification',success=False)
    lifecycle_attempted=False
    try:
        if snapshot(HOST)['config_sha256']!=EXPECTED_CONFIG or state()['diag']['capture_stream']['active']:
            raise ValueError('baseline/recording changed while staging')
        lifecycle_attempted=True
        lifecycle('stop');activate('candidate.json')
        result['startup']=lifecycle('start-current')
        samples=[]
        for _ in range(20):
            samples.append(state());time.sleep(1)
        (a.output/'health.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
        result['protected_after']=hashes();result['after']=snapshot(HOST)
        result['log']=ssh(HOST,'tail -c 16000 /tmp/garuda-fresh.log')
        result['isp_controls']=ssh(HOST,'v4l2-ctl -d /dev/video0 --get-ctrl=isp_ae_enable,isp_ae_integration_time,isp_ae_gain,isp_3dnr_enable,isp_3dnr_mode,isp_3dnr_strength')
        result['success']=(all(healthy(s) for s in samples) and
            samples[-1]['sequence']>samples[0]['sequence'] and
            all(s['stream_id']==samples[0]['stream_id'] for s in samples) and
            result['protected_after']==protected_before and
            result['after']['config_sha256']==staged['candidate.json'] and
            result['after']['native_running'] and not result['after']['mavros_running'] and
            'effective input=1024x576' in result['log'])
        if not result['success']:raise RuntimeError('live health/shape/provenance check failed')
    except BaseException as error:
        result['error']=repr(error)
        if lifecycle_attempted:
            try:result['failure_log']=ssh(HOST,'tail -c 16000 /tmp/garuda-fresh.log')
            except Exception as log_error:result['failure_log_error']=repr(log_error)
            try:
                lifecycle('stop');activate('previous-current.json');result['rollback_startup']=lifecycle('start-current')
                result['rollback']=snapshot(HOST)
            except BaseException as rollback_error:result['rollback_error']=repr(rollback_error)
        raise
    finally:
        (a.output/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('success','stage','after','startup')},indent=2))


if __name__=='__main__':main()
