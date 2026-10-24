"""Bounded replay on the verified R2 board; restore the same viewer in finally."""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess
import time
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('probe', type=pathlib.Path)
p.add_argument('prepared', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
p.add_argument('--native-pid', type=int, required=True)
p.add_argument('--dump-inputs', action='store_true', help='Save exact DSP output NV12 buffers for software comparison')
p.add_argument('--candidate-hef', type=pathlib.Path, help='Replay an isolated experimental HEF; never changes the live model')
p.add_argument('--replay-timeout', type=int, default=240, help='Seconds for streaming plus inference; raise for full-sequence replays')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
opts = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o',
    'UserKnownHostsFile=/media/bhanu1234/Development/GARUDASDK/.local/board-backups/20260911-stock-baseline/known_hosts-stock']
def remote(cmd, **kw):
    return subprocess.run(['ssh', *opts, 'root@10.0.0.1', cmd],
        capture_output=True, check=kw.pop('check', True), **kw)
native = '/opt/hailo-experiment/r2/camera-viewer-server'
hef = '/opt/hailo-yolo11/models/yolov11s_hailo15l_v5.3.0.hef'
verify = f'test "$(readlink /proc/{a.native_pid}/exe)" = {native}'
remote(verify, timeout=10)
environ = remote(f'cat /proc/{a.native_pid}/environ', timeout=10).stdout.split(b'\0')
required = [b'GARUDA_LETTERBOX=1', b'GARUDA_LOW_SCORE=1', b'GARUDA_RECORD_ENABLE=1',
    b'LD_LIBRARY_PATH=/opt/hailo-experiment/r2/lib']
if not all(v in environ for v in required):
    raise ValueError('Unexpected viewer environment; refusing to stop')
model_hash = remote('sha256sum '+hef, timeout=10, text=True).stdout.split()[0]
# Live model since the 2026-09-11 controlled-HEF deployment; see docs/decisions.md.
if model_hash != 'aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58':
    raise ValueError('Unexpected HEF')
stage = remote('mktemp -d /tmp/garuda-4k-replay.XXXXXX', timeout=10, text=True).stdout.strip()
if not stage.startswith('/tmp/garuda-4k-replay.') or any(c.isspace() for c in stage):
    raise ValueError('Unexpected stage')
config = json.loads(remote('cat /opt/hailo-yolo11/coco-postprocess.json', timeout=10).stdout)
config['detection_threshold'] = .05
(a.output/'post.json').write_text(json.dumps(config, indent=2))
subprocess.run(['scp', *opts, str(a.probe), str(a.prepared/'regions.json'), str(a.output/'post.json'),
    'root@10.0.0.1:'+stage+'/'], check=True, timeout=60)
evidence = dict(stage=stage, model_sha256=model_hash, native_pid_before=a.native_pid,
    preparation=json.loads((a.prepared/'manifest.json').read_text()),
    probe_sha256=hashlib.sha256(a.probe.read_bytes()).hexdigest())
if a.candidate_hef:
    candidate_hash = hashlib.sha256(a.candidate_hef.read_bytes()).hexdigest()
    subprocess.run(['scp', *opts, str(a.candidate_hef), 'root@10.0.0.1:'+stage+'/candidate.hef'], check=True, timeout=60)
    hef = stage+'/candidate.hef'
    if remote('sha256sum '+hef,timeout=10,text=True).stdout.split()[0] != candidate_hash:
        raise ValueError('Transferred candidate hash mismatch')
    parsed = remote('hailortcli parse-hef '+hef,timeout=15,text=True).stdout
    if 'HAILO15L' not in parsed or 'NV12(320x640x3)' not in parsed or 'number of classes: 80' not in parsed:
        raise ValueError('Candidate must be 15L NV12 640-square, 80-class NMS model')
    (a.output/'candidate-parse.txt').write_text(parsed)
    evidence['live_model_sha256'] = model_hash
    evidence['model_sha256'] = candidate_hash
    evidence['candidate_source'] = str(a.candidate_hef.resolve())
stopped = False
try:
    remote(verify + f' && kill -TERM {a.native_pid}', timeout=10)
    stopped = True
    remote(f'for n in 1 2 3 4 5 6 7 8 9 10; do test ! -e /proc/{a.native_pid}/exe && exit 0; sleep 1; done; exit 1', timeout=15)
    started = time.monotonic()
    dump_arg = f' {stage}/network-inputs.nv12' if a.dump_inputs else ''
    with (a.prepared/'source.nv12').open('rb') as source:
        result = remote(f'LD_BIND_NOW=1 {stage}/{shlex.quote(a.probe.name)} {hef} {stage}/regions.json {stage}/post.json {stage}/letterbox.jsonl letterbox{dump_arg}',
            stdin=source, timeout=a.replay_timeout, check=False)
    evidence['replay_wall_seconds_including_streaming'] = time.monotonic()-started
    (a.output/'stdout.log').write_bytes(result.stdout)
    (a.output/'stderr.log').write_bytes(result.stderr)
    result.check_returncode()
    (a.output/'letterbox.jsonl').write_bytes(remote(f'cat {stage}/letterbox.jsonl', timeout=120).stdout)
    (a.output/'regions.json').write_bytes((a.prepared/'regions.json').read_bytes())
    if a.dump_inputs:
        data = remote(f'cat {stage}/network-inputs.nv12', timeout=30).stdout
        if len(data) != len(json.loads((a.prepared/'regions.json').read_text()))*640*640*3//2:
            raise ValueError('Unexpected network dump size')
        (a.output/'network-inputs.nv12').write_bytes(data)
        evidence['network_inputs_sha256'] = hashlib.sha256(data).hexdigest()
finally:
    try:
        if stopped:
            # Do not start another viewer unless the stopped PID has actually exited.
            remote(f'test ! -e /proc/{a.native_pid}/exe', timeout=10)
            cmd = f'cd /home/root/apps; nohup env LD_LIBRARY_PATH=/opt/hailo-experiment/r2/lib LD_BIND_NOW=1 WEBSERVER_CONSOLE_LOG_LEVEL=info GARUDA_LETTERBOX=1 GARUDA_LOW_SCORE=1 GARUDA_RECORD_ENABLE=1 {native} >/tmp/garuda-r2-4k-replay-restored.log 2>&1 </dev/null & echo $!'
            evidence['restored_pid'] = remote(cmd, timeout=10, text=True).stdout.strip()
            for attempt in range(30):
                try:
                    req = urllib.request.Request('http://10.0.0.1/ai_pipeline', data=b'{"active":"Detection"}',
                        method='PATCH', headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        evidence['restored_pipeline'] = json.load(response)
                    break
                except (OSError, ValueError):
                    if attempt == 29:
                        raise
                    time.sleep(1)
    finally:
        (a.output/'run.json').write_text(json.dumps(evidence, indent=2))
print(json.dumps(evidence, indent=2))
