"""Run a prepared VisDrone-DET canvas stream through the on-board reference
probe with a chosen HEF, in the fresh_node era: the node is stopped for the
run and restarted in its current profile afterwards (finally). Never touches
the live model file.
"""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
CTL = ROOT / 'hosts' / 'hailo15l' / 'fresh_tracking_ctl.sh'
OPTS = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5']
HOST = 'root@10.0.0.1'
PROFILE_FILES = {'start': 'perception.json', 'start-letterbox': 'perception-letterbox.json',
                 'start-tiles': 'perception-tiles.json', 'start-follow': 'perception-follow.json',
                 'start-aerial': 'perception-aerial.json', 'start-follow-native': 'perception-follow-native.json',
                 'start-follow-native-compare': 'perception-follow-native-compare.json'}


def remote(cmd, **kw):
    return subprocess.run(['ssh', *OPTS, HOST, cmd], capture_output=True,
                          check=kw.pop('check', True), **kw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('probe', type=pathlib.Path)
    p.add_argument('prepared', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--hef', type=pathlib.Path, required=True, help='Local HEF to run (transferred as a candidate)')
    p.add_argument('--restart-profile', default='start-tiles', choices=sorted(PROFILE_FILES),
                   help='ctl action to restore the fresh node (must match the running profile)')
    p.add_argument('--replay-timeout', type=int, default=1800)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    for name in ('source.nv12', 'regions.json', 'manifest.json'):
        if not (a.prepared / name).exists():
            raise SystemExit(f'missing {name} in {a.prepared}')
    hef_sha = hashlib.sha256(a.hef.read_bytes()).hexdigest()
    # The node must be running the profile we will restore, or the restore would silently switch it.
    profile_file = PROFILE_FILES[a.restart_profile]
    if remote(f'cmp -s /opt/garuda-fresh/current.json /opt/garuda-fresh/{profile_file}', timeout=10,
              check=False).returncode != 0:
        raise SystemExit(f'board is not running {profile_file}; pass the matching --restart-profile')
    stage = remote('mktemp -d /tmp/garuda-visdrone.XXXXXX', timeout=10, text=True).stdout.strip()
    if not stage.startswith('/tmp/garuda-visdrone.') or any(c.isspace() for c in stage):
        raise SystemExit('unexpected stage dir')
    config = json.loads(remote('cat /opt/hailo-yolo11/coco-postprocess.json', timeout=10).stdout)
    config['detection_threshold'] = .05
    (a.output / 'post.json').write_text(json.dumps(config, indent=2))
    subprocess.run(['scp', *OPTS, str(a.probe), str(a.prepared / 'regions.json'),
                    str(a.output / 'post.json'), str(a.hef), f'{HOST}:{stage}/'], check=True, timeout=300)
    board_sha = remote(f'sha256sum {stage}/{a.hef.name}', timeout=30, text=True).stdout.split()[0]
    if board_sha != hef_sha:
        raise SystemExit('transferred HEF hash mismatch')
    parsed = remote(f'hailortcli parse-hef {stage}/{shlex.quote(a.hef.name)}', timeout=15, text=True).stdout
    # The HEF's NV12 input must match the preparation's network size (640x640 unless the regions
    # carry network_w/network_h, e.g. 1280x736): HailoRT prints the packed tensor as height/2 x width x 3.
    first = json.loads((a.prepared / 'regions.json').read_text())[0]
    nw, nh = first.get('network_w', 640), first.get('network_h', 640)
    if 'HAILO15L' not in parsed or f'NV12({nh // 2}x{nw}x3)' not in parsed or 'number of classes: 80' not in parsed:
        raise SystemExit(f'HEF must be a 15L NV12 {nw}x{nh} 80-class NMS model (preparation network size)')
    (a.output / 'hef-parse.txt').write_text(parsed)
    evidence = dict(stage=stage, hef=str(a.hef), hef_sha256=hef_sha,
                    probe_sha256=hashlib.sha256(a.probe.read_bytes()).hexdigest(),
                    preparation=json.loads((a.prepared / 'manifest.json').read_text()))
    stopped = False
    try:
        subprocess.run(['bash', str(CTL), 'stop'], check=True, timeout=60)
        stopped = True
        started = time.monotonic()
        with (a.prepared / 'source.nv12').open('rb') as source:
            result = remote(f'LD_BIND_NOW=1 {stage}/{shlex.quote(a.probe.name)} {stage}/{shlex.quote(a.hef.name)} '
                            f'{stage}/regions.json {stage}/post.json {stage}/letterbox.jsonl letterbox',
                            stdin=source, timeout=a.replay_timeout, check=False)
        evidence['replay_wall_seconds_including_streaming'] = time.monotonic() - started
        (a.output / 'stdout.log').write_bytes(result.stdout)
        (a.output / 'stderr.log').write_bytes(result.stderr)
        result.check_returncode()
        (a.output / 'letterbox.jsonl').write_bytes(remote(f'cat {stage}/letterbox.jsonl', timeout=300).stdout)
        (a.output / 'regions.json').write_bytes((a.prepared / 'regions.json').read_bytes())
        remote(f'rm -rf {stage}', timeout=30, check=False)
    finally:
        try:
            if stopped:
                restored=subprocess.run(['bash', str(CTL), a.restart_profile], check=False, timeout=120)
                evidence['restore_returncode']=restored.returncode
                evidence['restored_profile'] = a.restart_profile if restored.returncode==0 else None
                restored.check_returncode()
        finally:
            (a.output / 'run.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps({k: v for k, v in evidence.items() if k != 'preparation'}, indent=2))


if __name__ == '__main__':
    main()
