"""Paired 15L replay; stop only the verified diagnostic viewer and restore in finally."""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess
import sys
import time
import urllib.request

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('probe',type=pathlib.Path)
p.add_argument('prepared',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
p.add_argument('--native-pid',type=int,required=True)
a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
root=pathlib.Path(__file__).resolve().parents[2]
known='/media/bhanu1234/Development/GARUDASDK/.local/board-backups/20260911-stock-baseline/known_hosts-stock'
opts=['-o','BatchMode=yes','-o','ConnectTimeout=5','-o','UserKnownHostsFile='+known]
ssh=['ssh',*opts,'root@10.0.0.1']
def remote(cmd,**kwargs):
    return subprocess.run(ssh+[cmd],check=kwargs.pop('check',True),capture_output=True,**kwargs)
native='/opt/hailo-diagnostics/r1/camera-viewer'
remote(f'test "$(readlink /proc/{a.native_pid}/exe)" = {native}',timeout=10)
stage=remote('mktemp -d /tmp/garuda-preprocess.XXXXXX',text=True,timeout=10).stdout.strip()
if not stage.startswith('/tmp/garuda-preprocess.') or any(c.isspace() for c in stage):raise ValueError('invalid stage')
config=json.loads(remote('cat /opt/hailo-yolo11/coco-postprocess.json',text=True,timeout=10).stdout)
config['detection_threshold']=.05
(a.output/'post.json').write_text(json.dumps(config,indent=2))
subprocess.run(['scp',*opts,str(a.probe),str(a.prepared/'regions.json'),str(a.output/'post.json'),
                'root@10.0.0.1:'+stage+'/'],check=True,timeout=60)
hef='/opt/hailo-yolo11/models/yolov11s_hailo15l_v5.3.0.hef'
evidence={'stage':stage,'source_sha256':hashlib.sha256((a.prepared/'source.nv12').read_bytes()).hexdigest(),
          'regions_sha256':hashlib.sha256((a.prepared/'regions.json').read_bytes()).hexdigest(),
          'model_hash':remote('sha256sum '+hef,text=True,timeout=10).stdout.strip(),
          'scope':'Sparse annotated stored frames; not live-motion or identity validation.'}
try:
    remote(f'test "$(readlink /proc/{a.native_pid}/exe)" = {native} && kill -TERM {a.native_pid}',timeout=10)
    remote(f'for n in 1 2 3 4 5 6 7 8 9 10; do test ! -e /proc/{a.native_pid}/exe && exit 0; sleep 1; done; exit 1',timeout=15)
    for mode in ('stretch','letterbox'):
        with (a.prepared/'source.nv12').open('rb') as source:
            cmd=f'LD_BIND_NOW=1 {stage}/{shlex.quote(a.probe.name)} {hef} {stage}/regions.json {stage}/post.json {stage}/{mode}.jsonl {mode}'
            result=remote(cmd,stdin=source,timeout=120,check=False)
        (a.output/(mode+'.stdout.log')).write_bytes(result.stdout)
        (a.output/(mode+'.stderr.log')).write_bytes(result.stderr)
        result.check_returncode()
        (a.output/(mode+'.jsonl')).write_bytes(remote(f'cat {stage}/{mode}.jsonl',timeout=20).stdout)
        score=subprocess.run([sys.executable,str(root/'bench/fresh_roi_score.py'),str(a.prepared/'regions.json'),str(a.output/(mode+'.jsonl'))],check=True,capture_output=True)
        (a.output/(mode+'-score.json')).write_bytes(score.stdout)
finally:
    # Only this known manual viewer is restarted. Adapter reconnects without changes.
    cmd=f'cd /home/root/apps; nohup env LD_LIBRARY_PATH=/opt/hailo-diagnostics/r1/lib WEBSERVER_CONSOLE_LOG_LEVEL=info LD_BIND_NOW=1 {native} >/tmp/garuda-diagnostics-r1-replay-restored.log 2>&1 </dev/null & echo $!'
    try:
        evidence['restored_pid']=remote(cmd,timeout=10,text=True).stdout.strip()
        for attempt in range(30):
            try:
                request=urllib.request.Request('http://10.0.0.1/ai_pipeline',
                    data=b'{"active":"Detection"}', method='PATCH',
                    headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=15) as response:
                    evidence['restored_pipeline']=json.load(response)
                break
            except (OSError,ValueError) as error:
                if attempt==29:
                    evidence['restore_error']=str(error)
                    raise
                time.sleep(1)
    finally:
        (a.output/'run.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence,indent=2))
