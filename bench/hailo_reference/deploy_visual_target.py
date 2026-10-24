"""Explicitly requested visual-phone live trial; guarded binary/config rollback.

No model, ISP, recording, dependency, boot or flight-controller changes.
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

from deploy_live_1024 import state, healthy as base_healthy
from recorded_input_campaign import sha
from run_local_capture_trial import snapshot, ssh
from visual_target_board_probe import EXPECTED_NODE, EXPECTED_CONFIG

ROOT=Path(__file__).resolve().parents[2]
HOST='root@10.0.0.1'
BASE='/opt/garuda-fresh'


def configuration(current):
    if (current['input_w'],current['input_h'])!=(1024,576) or current.get('managed_detection') or current.get('detection_tiles') or current['target_roi']!='off':
        raise ValueError('requires existing full-frame1024 baseline')
    if current['tracking'].get('visual_phone_tracking',False):raise ValueError('already enabled')
    candidate=copy.deepcopy(current)
    candidate['tracking']['visual_phone_tracking']=True
    return candidate


def healthy(s):
    d=s['diag'];pair=d.get('source_pairing',{})
    return (base_healthy(s) and isinstance(d.get('camera_motion',{}).get('visual_target'),dict)
        and pair.get('matched',0)>0 and pair.get('invalid',0)==0
        and d.get('rejected_frames',0)==0 and not d.get('input_capture',{}).get('remaining',0))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();before=snapshot(HOST);initial=state()
    if (before['node_sha256']!=EXPECTED_NODE or before['config_sha256']!=EXPECTED_CONFIG
        or not before['native_running'] or before['replay_running'] or before['mavros_running']
        or before['free_bytes']<512*1024*1024 or initial['diag']['capture_stream']['active']
        or initial['diag']['input_capture'].get('remaining',0)):
        raise ValueError('baseline/resource/recording guard')
    evidence=json.loads((ROOT/'bench/results/2026-09-27-visual-target/final-check-v2.json').read_text())
    if any(sha(ROOT/path)!=h for path,h in evidence['source_sha256'].items()):
        raise ValueError('tested source changed')
    a.out.mkdir(parents=True,exist_ok=False)
    subprocess.run(['scp','-q',HOST+':'+BASE+'/current.json',str(a.out/'previous-current.json')],check=True,timeout=20)
    if sha(a.out/'previous-current.json')!=EXPECTED_CONFIG:raise ValueError('config changed')
    current=json.loads((a.out/'previous-current.json').read_text());candidate=configuration(current)
    (a.out/'candidate.json').write_text(json.dumps(candidate,indent=2)+'\n')
    media=json.loads(ssh(HOST,'cat '+shlex.quote(current['medialib_config'])))
    profile_path=next(x['config_file'] for x in media['profiles'] if x['name']==current['profile'])
    profile=json.loads(ssh(HOST,'cat '+shlex.quote(profile_path)))
    protected=[current['hef'],current['person_reid_hef'],current['medialib_config'],profile_path,
        profile['application_settings'],profile['iq_settings'],profile['sensor_config'],
        profile['stabilizer_settings'],current['postprocess_config']]
    def hashes():return {path:ssh(HOST,'sha256sum '+shlex.quote(path)).split()[0] for path in protected}
    protected_before=hashes()
    if protected_before[current['hef']]!='bb9fe29b984e296be1cf15c8b934aca7514428ed2d1d4cc54f6bd11017efab43':
        raise ValueError('unexpected model')
    stage=ssh(HOST,'mktemp -d /opt/garuda-fresh/live-visual.XXXXXX')
    if not re.fullmatch(r'/opt/garuda-fresh/live-visual\.[A-Za-z0-9]{6}',stage):raise ValueError('unexpected stage')
    subprocess.run(['scp','-q',str(a.binary),HOST+':'+stage+'/candidate-node'],check=True,timeout=45)
    subprocess.run(['scp','-q',str(a.out/'candidate.json'),HOST+':'+stage+'/candidate.json'],check=True,timeout=20)
    expected_node=sha(a.binary);expected_config=sha(a.out/'candidate.json')
    for name,h in [('candidate-node',expected_node),('candidate.json',expected_config)]:
        if ssh(HOST,'sha256sum '+stage+'/'+name).split()[0]!=h:raise ValueError('staging mismatch')
    # Factory Yocto image has no ldd wrapper; ask the dynamic loader directly,
    # with exactly the library path used by the existing service launcher.
    deps=ssh(HOST,'LD_TRACE_LOADED_OBJECTS=1 LD_LIBRARY_PATH=/opt/garuda-fresh/lib '+stage+'/candidate-node')
    if 'not found' in deps:raise ValueError('missing dependency')
    ssh(HOST,f'cp -p {BASE}/garuda-fresh-tracking {stage}/previous-node && cp -p {BASE}/current.json {stage}/previous-current.json')
    for name,h in [('previous-node',EXPECTED_NODE),('previous-current.json',EXPECTED_CONFIG)]:
        if ssh(HOST,'sha256sum '+stage+'/'+name).split()[0]!=h:raise ValueError('backup mismatch')
    ctl=ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh';env=dict(os.environ,GARUDA_H15L_HOST=HOST)
    def lifecycle(action):
        return subprocess.run(['bash',str(ctl),action],env=env,check=True,capture_output=True,text=True,timeout=45).stdout
    def activate(node,config):
        ssh(HOST,f'cp -p {stage}/{node} {stage}/activate-node && mv {stage}/activate-node {BASE}/garuda-fresh-tracking && '
            f'cp -p {stage}/{config} {stage}/activate.json && mv {stage}/activate.json {BASE}/current.json')
    result=dict(success=False,before=before,initial=initial,stage=stage,dependencies=deps,
        protected_before=protected_before,candidate_node_sha256=expected_node,candidate_config_sha256=expected_config,
        source_sha256=evidence['source_sha256'],scope='owner-requested live visual-phone trial; not flight qualification')
    attempted=False
    try:
        recheck=snapshot(HOST);s=state()
        if (recheck['node_sha256']!=EXPECTED_NODE or recheck['config_sha256']!=EXPECTED_CONFIG or
            s['diag']['capture_stream']['active'] or s['diag']['input_capture'].get('remaining',0)):
            raise ValueError('baseline/recording changed during staging')
        attempted=True;lifecycle('stop');activate('candidate-node','candidate.json')
        result['startup']=lifecycle('start-current');print('Candidate started; checking live health.',flush=True)
        samples=[]
        for _ in range(25):samples.append(state());time.sleep(1)
        (a.out/'health.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
        result['after']=snapshot(HOST);result['protected_after']=hashes()
        result['log']=ssh(HOST,'tail -c 16000 /tmp/garuda-fresh.log')
        result['isp_controls']=ssh(HOST,'v4l2-ctl -d /dev/video0 --get-ctrl=isp_ae_enable,isp_ae_integration_time,isp_ae_gain,isp_3dnr_enable,isp_3dnr_mode,isp_3dnr_strength')
        result['success']=(all(healthy(s) for s in samples) and samples[-1]['sequence']>samples[0]['sequence']
            and all(s['stream_id']==samples[0]['stream_id'] for s in samples)
            and result['protected_after']==protected_before
            and result['after']['node_sha256']==expected_node and result['after']['config_sha256']==expected_config
            and result['after']['native_running'] and not result['after']['mavros_running']
            and 'effective input=1024x576' in result['log'])
        if not result['success']:raise RuntimeError('live health/provenance check failed')
    except BaseException as error:
        result['error']=repr(error)
        if attempted:
            try:result['failure_log']=ssh(HOST,'tail -c 16000 /tmp/garuda-fresh.log')
            except Exception as e:result['failure_log_error']=repr(e)
            try:
                lifecycle('stop');activate('previous-node','previous-current.json')
                result['rollback_startup']=lifecycle('start-current');result['rollback']=snapshot(HOST)
                result['rollback_verified']=result['rollback']['node_sha256']==EXPECTED_NODE and result['rollback']['config_sha256']==EXPECTED_CONFIG and result['rollback']['native_running']
            except BaseException as e:result['rollback_error']=repr(e)
        raise
    finally:(a.out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('success','stage','after')},indent=2))


if __name__=='__main__':main()
