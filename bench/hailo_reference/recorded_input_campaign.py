"""Bounded recorded-pixel region audit. Streams pixels; never records new camera data.

Only stages a probe/JSON on eMMC. Original camera is restored in finally. The
native comparison uses decoded H264 plus a DSP720 approximation, not raw ISP720.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import urllib.request

from audit_phone_input import ROOT, BOXES, EXPECTED_NODE, EXPECTED_CONFIG, EXPECTED_HEF
from run_local_capture_trial import snapshot, ssh
from score_4k_tiles import ANNOTATIONS


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def layouts(w, h):
    return [(f'corner{i}', x, y, w*3//5, h*3//5, False)
            for i, (x, y) in enumerate([(0, 0), (w*2//5, 0), (0, h*2//5), (w*2//5, h*2//5)])] + [('full', 0, 0, w, h, True)]


def prepare(out):
    rows = []
    base = ROOT/'bench/local-baselines'
    for name, pixels, metadata, indices in [
        ('fast180', base/'20260922-phone-motion/fast-motion-pc-01', base/'20260922-phone-motion/fast-motion-pc-01', range(180)),
        ('recent4', base/'20260927-image-path', base/'20260927-phone-schedule/live-candidate-01-metadata', BOXES)]:
        for index in indices:
            path = pixels/f'{index:06d}.source.nv12'
            meta = json.loads((metadata/f'{index:06d}.json').read_text())
            if path.stat().st_size != 1382400 or sha(path) != meta['source_image']['sha256']:
                raise ValueError('source provenance mismatch')
            definitions = layouts(1280, 720)
            roi = meta['target_roi'].get('region')
            if roi:
                definitions.append(('recorded_roi', roi['x'], roi['y'], roi['w'], roi['h'], False))
            for method, x, y, w, h, full in definitions:
                rows.append(dict(clip=name, source_frame=index, method=method, source_w=1280, source_h=720,
                                 x=x, y=y, w=w, h=h, full_frame=full, pixels=str(path), offset=0,
                                 source_sha256=meta['source_image']['sha256'],
                                 exposure_us=meta['isp_ae_integration_time'], timestamp_ns=meta['isp_timestamp_ns']))
    native = Path('/media/bhanu1234/Development/hailo-export/yolo11-controlled.m6W0K2/board-prepared')
    manifest = json.loads((native/'manifest.json').read_text())
    if sha(native/'source.nv12') != manifest['source_sha256']:
        raise ValueError('native source hash mismatch')
    old = json.loads((native/'regions.json').read_text())
    native_rows = []
    for frame, box in ANNOTATIONS.items():
        index = next(i for i, r in enumerate(old) if r['source_frame'] == frame)
        defs = layouts(3840, 2160)
        for side in (960, 1920, 2880):
            if side > 2160:
                continue
            cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
            x = int(min(max(cx-side/2, 0), 3840-side))//6*6
            y = int(min(max(cy-side/2, 0), 2160-side))//6*6
            defs.append((f'oracle{side}', x, y, side, side, False))
        for method, x, y, w, h, full in defs:
            native_rows.append(dict(clip='native3', source_frame=frame, method=method,
                                    source_w=3840, source_h=2160, x=x, y=y, w=w, h=h, full_frame=full,
                                    pixels=str(native/'source.nv12'), offset=index*3840*2160*3//2,
                                    annotation=box, source_sha256=manifest['source_sha256']))
    for name, definitions in [('phone', rows), ('native', native_rows)]:
        if not 1 <= len(definitions) <= 2048:
            raise ValueError('probe region bound')
        (out/(name+'-regions.json')).write_text(json.dumps(definitions, indent=2)+'\n')
    return rows, native_rows


def stream_probe(stage, name, rows, out, via=False, *, hef=None, manifest=None):
    errors = []
    with (out/(name+'.jsonl')).open('xb') as stdout, (out/(name+'.stderr')).open('xb') as stderr:
        manifest = manifest or ('native' if name.startswith('native') else 'phone')
        hef = hef or '/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef'
        import shlex
        command = 'LD_LIBRARY_PATH=/opt/garuda-fresh/lib ' + ' '.join(map(shlex.quote,
            [stage+'/garuda-region-probe', hef, '-', stage+'/'+manifest+'-regions.json', '--audit']))
        if via:
            command += ' --via720'
        proc = subprocess.Popen(['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@10.0.0.1', command],
                                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
        def feed():
            try:
                for row in rows:
                    size = row['source_w']*row['source_h']*3//2
                    with open(row['pixels'], 'rb') as f:
                        f.seek(row['offset'])
                        raw = f.read(size)
                    if len(raw) != size:
                        raise ValueError('short source pixels')
                    proc.stdin.write(raw)
                proc.stdin.close()
            except Exception as e:
                errors.append(str(e))
                try: proc.stdin.close()
                except OSError: pass
        worker = threading.Thread(target=feed, daemon=True)
        worker.start()
        try:
            rc = proc.wait(timeout=480)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        finally:
            worker.join(timeout=5)
        if rc or errors or worker.is_alive():
            raise RuntimeError(f'{name} failed: rc={rc} feed={errors}')
    predictions = [json.loads(x) for x in (out/(name+'.jsonl')).read_text().splitlines()]
    if len(predictions) != len(rows) or any(p['frame'] != i for i, p in enumerate(predictions)):
        raise ValueError('incomplete or reordered probe results')
    print(json.dumps(dict(completed=name, regions=len(rows))), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--native-only', action='store_true', help='new isolated native pair run; do not overwrite a failed run')
    a = parser.parse_args()
    before = snapshot('root@10.0.0.1')
    if (before['node_sha256'] != EXPECTED_NODE or before['config_sha256'] != EXPECTED_CONFIG or
        not before['native_running'] or before['replay_running'] or before['mavros_running'] or
        before['free_bytes'] < 512*1024*1024):
        raise ValueError('baseline/resource guard')
    with urllib.request.urlopen('http://10.0.0.1:8099/api/state', timeout=5) as f:
        if json.load(f)['diag']['capture_stream']['active']:
            raise ValueError('recording active')
    a.output.mkdir(parents=True, exist_ok=False)
    phone, native = prepare(a.output)
    stage = ssh('root@10.0.0.1', 'mktemp -d /opt/garuda-fresh/recorded-audit.XXXXXX')
    if not re.fullmatch(r'/opt/garuda-fresh/recorded-audit\.[A-Za-z0-9]{6}', stage):
        raise ValueError('unexpected stage')
    files = [a.probe, a.output/'phone-regions.json', a.output/'native-regions.json']
    hashes = {p.name: sha(p) for p in files}
    subprocess.run(['scp', '-q', *map(str, files), 'root@10.0.0.1:'+stage+'/'], check=True, timeout=60)
    for name, digest in hashes.items():
        if ssh('root@10.0.0.1', 'sha256sum '+stage+'/'+name).split()[0] != digest:
            raise ValueError('staging hash mismatch')
    if ssh('root@10.0.0.1', 'sha256sum /opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef').split()[0] != EXPECTED_HEF:
        raise ValueError('HEF changed')
    result = dict(before=before, stage=stage, staged_sha256=hashes, hef_sha256=EXPECTED_HEF,
                  scope='recorded pixels; fixed regions; no causal tracker/scheduler or flight qualification')
    ctl = ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh'
    env = dict(os.environ, GARUDA_H15L_HOST='root@10.0.0.1')
    try:
        subprocess.run(['bash', str(ctl), 'stop'], env=env, check=True, timeout=30)
        if not a.native_only:
            stream_probe(stage, 'phone', phone, a.output)
        stream_probe(stage, 'native-direct', native, a.output)
        stream_probe(stage, 'native-via720', native, a.output, via=True)
    finally:
        try:
            p = subprocess.run(['bash', str(ctl), 'start-current'], env=env, capture_output=True, text=True, timeout=40)
            result.update(restore_returncode=p.returncode, restore_stdout=p.stdout, restore_stderr=p.stderr)
            result['after'] = snapshot('root@10.0.0.1')
            result['live_unchanged'] = all(result['after'][k] == before[k] for k in ('node_sha256', 'config_sha256'))
        finally:
            (a.output/'run.json').write_text(json.dumps(result, indent=2)+'\n')
    if not result['live_unchanged'] or result['restore_returncode']:
        raise RuntimeError('restoration failed')


if __name__ == '__main__':
    main()
