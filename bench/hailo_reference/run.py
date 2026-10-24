"""Run the stock SDK comparison on saved, prepared images and restore the phone profile."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('probe', type=Path)
p.add_argument('prepared', type=Path)
p.add_argument('baseline', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
a.output.mkdir(exist_ok=False)
ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@10.0.0.1']
def remote(command):
    return subprocess.run(ssh + [command], check=True, capture_output=True, text=True, timeout=30).stdout
def ctl(action):
    subprocess.run(['bash', str(root / 'hosts/hailo15l/fresh_tracking_ctl.sh'), action], check=True, timeout=30)
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

hash_command = 'sha256sum /opt/garuda-fresh/garuda-fresh-tracking /opt/garuda-fresh/current.json'
before = remote(hash_command + '; cmp -s /opt/garuda-fresh/current.json /opt/garuda-fresh/perception-yolov8m-phone.json')
stage = remote('mktemp -d /tmp/garuda-sdk-reference.XXXXXX').strip()
if not stage.startswith('/tmp/garuda-sdk-reference.') or '\n' in stage:
    raise RuntimeError('unexpected staging path')
config = json.loads((root / 'hosts/hailo15l/fresh/postprocess.json').read_text())
config['detection_threshold'] = .05
config['max_boxes'] = 10000
(a.output / 'post.json').write_text(json.dumps(config, indent=2) + '\n')
subprocess.run(['scp', str(a.probe), str(a.prepared / 'regions.json'), str(a.output / 'post.json'), 'root@10.0.0.1:' + stage + '/'], check=True)
hef = '/opt/garuda-fresh/models/yolov11m_hailo15l_v5.3.0.hef'
evidence = {'before': before, 'board_stage': stage, 'probe_sha256': digest(a.probe),
            'source_sha256': digest(a.prepared / 'source.nv12'), 'regions_sha256': digest(a.prepared / 'regions.json'),
            'baseline_sha256': digest(a.baseline),
            'runtime_hashes': remote('sha256sum ' + hef + ' /usr/lib/libhailo_analytics.so.1.12.0 /usr/lib/libmedialib.so.1.12.0 /usr/lib/hailo-post-processes/libyolo_hailortpp_post.so')}
try:
    ctl('stop')
    with (a.prepared / 'source.nv12').open('rb') as inputs:
        result = subprocess.run(ssh + ['LD_BIND_NOW=1 ' + stage + '/hailo-reference-probe ' + hef + ' ' + stage + '/regions.json ' + stage + '/post.json ' + stage + '/output.jsonl'], stdin=inputs, capture_output=True, timeout=90)
    (a.output / 'stdout.log').write_bytes(result.stdout)
    (a.output / 'stderr.log').write_bytes(result.stderr)
    evidence['returncode'] = result.returncode
    result.check_returncode()
    raw = remote('cat ' + stage + '/output.jsonl')
    (a.output / 'reference.jsonl').write_text(raw)
finally:
    ctl('start-phone')
    evidence['after'] = remote(hash_command)
    evidence['restored_hashes_match'] = evidence['before'] == evidence['after']
    (a.output / 'run.json').write_text(json.dumps(evidence, indent=2) + '\n')

reference = [json.loads(line) for line in raw.splitlines()]
baseline = [json.loads(line) for line in a.baseline.read_text().splitlines()]
regions = json.loads((a.prepared / 'regions.json').read_text())
if len(reference) != len(baseline) or len(reference) != len(regions):
    raise ValueError('frame count mismatch')
differences = []
maximum = 0.
for i, (ref, base) in enumerate(zip(reference, baseline)):
    if ref['frame'] != i or base['frame'] != i:
        raise ValueError('frame ordering mismatch')
    key = lambda d: (-d['score'], d['x1'], d['y1'])
    actual = sorted((d for d in ref['detections'] if d['class_id'] == 67), key=key)
    expected = sorted((d for d in base['detections'] if d['class_id'] == 67), key=key)
    if len(actual) != len(expected):
        differences.append({'frame': i, 'reference_count': len(actual), 'baseline_count': len(expected)})
        continue
    delta = max((abs(x[k]-y[k]) for x,y in zip(actual,expected) for k in ('score','x1','y1','x2','y2')), default=0.)
    maximum = max(maximum, delta)
    if delta > 1e-6:
        differences.append({'frame': i, 'max_difference': delta})
comparison = {'frames': len(reference), 'pixel_differences': sum(r['pixel_differences'] for r in reference),
              'max_pixel_difference': max(r['max_pixel_difference'] for r in reference),
              'phone_output_max_abs_difference': maximum, 'phone_output_differences_above_1e_6': differences}
(a.output / 'comparison.json').write_text(json.dumps(comparison, indent=2) + '\n')
score = subprocess.run([sys.executable, str(root / 'bench/fresh_roi_score.py'), str(a.prepared / 'regions.json'), str(a.output / 'reference.jsonl')], check=True, capture_output=True, text=True)
(a.output / 'reference-score.json').write_text(score.stdout)
print(json.dumps(comparison, indent=2))
