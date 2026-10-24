"""Compute real OSNet person embeddings for a VisDrone-SOT probe run, on the board.

For every frame, every person detection the probe produced (full view, corner
tiles, oracle ROI; deduplicated, best `--max-per-frame` by confidence) is
cropped from the prepared canvas NV12 exactly as the node crops it
(`garuda::fresh::resize_nv12_crop`: even-aligned box, bilinear to 128x256,
packed NV12) and streamed to `garuda-embedding-probe` with the OSNet HEF,
which returns the 512-value descriptor per crop. Output rows pair each
descriptor with its frame and canvas box so `sot_to_replay.py --embeddings`
can attach them to the replay detections. The node is stopped for the probe
run and restored afterwards, as `run_visdrone_det.py` does.
"""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess
import time

import numpy as np

from run_visdrone_det import CTL, HOST, OPTS, PROFILE_FILES, remote
from score_visdrone_det import LABEL_GROUP, aggregate, load_results
from sot_to_replay import CANVAS_W, CANVAS_H, frame_planes

CROP_W, CROP_H = 128, 256
CROP_BYTES = CROP_W * CROP_H * 3 // 2
PROBE_FRAME_LIMIT = 4096


def _resample(src, dw, dh):
    """Bilinear resample of an (h, w, channels) uint8 array to (dh, dw, channels), mirroring the node."""
    h, w = src.shape[:2]
    sy = np.clip((np.arange(dh) + .5) * h / dh - .5, 0, h - 1)
    sx = np.clip((np.arange(dw) + .5) * w / dw - .5, 0, w - 1)
    ya, xa = sy.astype(int), sx.astype(int)
    yb, xb = np.minimum(ya + 1, h - 1), np.minimum(xa + 1, w - 1)
    fy, fx = (sy - ya)[:, None, None], (sx - xa)[None, :, None]
    s = src.astype(np.float64)
    top = (1 - fx) * s[ya][:, xa] + fx * s[ya][:, xb]
    bottom = (1 - fx) * s[yb][:, xa] + fx * s[yb][:, xb]
    return np.floor((1 - fy) * top + fy * bottom + .5).astype(np.uint8)


def crop_nv12(y_plane, uv_plane, box):
    """resize_nv12_crop port: box (x, y, w, h) normalized on the canvas -> packed 128x256 NV12 bytes."""
    x, y, w, h = box
    height, width = y_plane.shape
    x0 = int(np.floor(min(max(x, 0), 1) * width / 2)) * 2
    y0 = int(np.floor(min(max(y, 0), 1) * height / 2)) * 2
    x1 = int(np.ceil(min(max(x + w, 0), 1) * width / 2)) * 2
    y1 = int(np.ceil(min(max(y + h, 0), 1) * height / 2)) * 2
    if x1 <= x0 or y1 <= y0:
        raise ValueError('empty person crop')
    luma = _resample(y_plane[y0:y1, x0:x1][:, :, None], CROP_W, CROP_H)
    chroma = uv_plane[y0//2:y1//2, x0:x1].reshape((y1-y0)//2, (x1-x0)//2, 2)
    chroma = _resample(chroma, CROP_W//2, CROP_H//2)
    return luma.tobytes() + chroma.tobytes()


def candidates(entry, max_per_frame, min_conf):
    """Person boxes worth a descriptor: union of full view, aggregated tiles and ROI, deduplicated."""
    seen, out = set(), []
    pool = entry['full'] + aggregate(entry['full'] + entry['corners']) + entry.get('roi', [])
    for d in sorted(pool, key=lambda d: -d['score']):
        key = tuple(round(v, 2) for v in d['box'])
        if d['label'] != 'person' or d['score'] < min_conf or key in seen:
            continue
        seen.add(key)
        out.append(d)
        if len(out) >= max_per_frame:
            break
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('prepared', type=pathlib.Path)
    p.add_argument('results', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path, help='directory for embeddings.jsonl and run.json')
    p.add_argument('--probe', type=pathlib.Path, default=pathlib.Path('/tmp/garuda-fresh-deploy/h15l/garuda-embedding-probe'))
    p.add_argument('--hef', type=pathlib.Path, default=pathlib.Path('/media/bhanu1234/Development/hailo15/models/osnet_x1_0_hailo15l_v5.3.0.hef'))
    p.add_argument('--model-id', default='osnet_x1_0-hailo15l-5.3.0-sha256:49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7')
    p.add_argument('--max-per-frame', type=int, default=12)
    p.add_argument('--min-conf', type=float, default=0.15)
    p.add_argument('--restart-profile', default='start-tiles', choices=sorted(PROFILE_FILES))
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    per_image, _ = load_results(a.results)
    manifest = json.loads((a.prepared / 'manifest.json').read_text())
    crops, rows = [], []
    with (a.prepared / 'source.nv12').open('rb') as source:
        for t in manifest['targets']:
            entry = per_image.get(t['index'])
            if not entry:
                continue
            chosen = candidates(entry, a.max_per_frame, a.min_conf)
            if not chosen:
                continue
            y_plane, uv_plane = frame_planes(source, t['index'])
            for d in chosen:
                x1, y1, x2, y2 = d['box']
                crops.append(crop_nv12(y_plane, uv_plane, (x1/CANVAS_W, y1/CANVAS_H, (x2-x1)/CANVAS_W, (y2-y1)/CANVAS_H)))
                rows.append(dict(frame=t['index'], box=d['box'], label=d['label'], score=d['score']))
    hef_sha = hashlib.sha256(a.hef.read_bytes()).hexdigest()
    profile_file = PROFILE_FILES[a.restart_profile]
    if remote(f'cmp -s /opt/garuda-fresh/current.json /opt/garuda-fresh/{profile_file}', timeout=10, check=False).returncode != 0:
        raise SystemExit(f'board is not running {profile_file}; pass the matching --restart-profile')
    stage = remote('mktemp -d /tmp/garuda-visdrone.XXXXXX', timeout=10, text=True).stdout.strip()
    if not stage.startswith('/tmp/garuda-visdrone.') or any(c.isspace() for c in stage):
        raise SystemExit('unexpected stage dir')
    subprocess.run(['scp', *OPTS, str(a.probe), str(a.hef), f'{HOST}:{stage}/'], check=True, timeout=300)
    if remote(f'sha256sum {stage}/{a.hef.name}', timeout=30, text=True).stdout.split()[0] != hef_sha:
        raise SystemExit('transferred HEF hash mismatch')
    evidence = dict(stage=stage, hef=str(a.hef), hef_sha256=hef_sha, model_id=a.model_id,
                    probe_sha256=hashlib.sha256(a.probe.read_bytes()).hexdigest(),
                    crops=len(crops), frames_with_crops=len({r['frame'] for r in rows}),
                    crop_geometry='resize_nv12_crop port: even-aligned box, bilinear 128x256, packed NV12',
                    max_per_frame=a.max_per_frame, min_conf=a.min_conf, batches=[])
    embeddings, stopped = [], False
    try:
        subprocess.run(['bash', str(CTL), 'stop'], check=True, timeout=60)
        stopped = True
        cmd = (f'LD_BIND_NOW=1 {stage}/{shlex.quote(a.probe.name)} {stage}/{shlex.quote(a.hef.name)} - '
               f'{shlex.quote(a.model_id)}')
        for start in range(0, len(crops), PROBE_FRAME_LIMIT):
            batch = crops[start:start+PROBE_FRAME_LIMIT]
            began = time.monotonic()
            result = remote(cmd, input=b''.join(batch), timeout=1800, check=False)
            lines = [json.loads(l) for l in result.stdout.decode().splitlines() if l.startswith('{')]
            if result.returncode or len(lines) != len(batch):
                (a.output / 'probe-stderr.log').write_bytes(result.stderr)
                raise SystemExit(f'probe batch failed: {len(lines)}/{len(batch)} rows, rc {result.returncode}')
            embeddings += lines
            evidence['batches'].append(dict(crops=len(batch), wall_s=round(time.monotonic()-began, 1),
                                            summary=result.stderr.decode().strip().splitlines()[-1]))
        remote(f'rm -rf {stage}', timeout=30, check=False)
    finally:
        try:
            if stopped:
                subprocess.run(['bash', str(CTL), a.restart_profile], check=False, timeout=120)
                evidence['restored_profile'] = a.restart_profile
        finally:
            (a.output / 'run.json').write_text(json.dumps(evidence, indent=2))
    with (a.output / 'embeddings.jsonl').open('w') as out:
        for row, e in zip(rows, embeddings):
            out.write(json.dumps(dict(row, model=e['model'], values=e['embedding'], raw_norm=e['raw_norm']))+'\n')
    print(json.dumps({k: v for k, v in evidence.items() if k != 'batches'}))


if __name__ == '__main__':
    main()
