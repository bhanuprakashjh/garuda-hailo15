"""Oracle native-crop probe streams for one VisDrone-SOT sequence.

Question answered: how much does the detector gain when the target ROI is cut
from the ORIGINAL pixels instead of the node's 1280x720 copy? Two prepared
directories, both consumable by `run_visdrone_det.py` (source.nv12 +
regions.json + manifest.json):

* `native`  — frames at their original size (bottom row dropped when the
  height is odd; NV12 needs even dimensions), one full-frame letterbox region
  per frame plus one square window per requested side, centred on the
  annotated box (oracle: the live planner centres on the tracker's own box).
  A 640 window is the RoiAssist planner's minimum side at native pixels; a
  320 window is the same pixels shown to the detector at twice the size.
* `subset720` — the first N frames of an existing 720p preparation
  (`prepare_visdrone_sot.py --roi`) with only the full view and the oracle
  ROI kept per frame: the current full-view and ROI paths, same frames.

Same RGB->NV12 transform as every other probe stream (inverse SDK full-range
matrix, 2x2 chroma mean). Nothing here is committed: datasets stay outside
the repo.
"""
import argparse
import hashlib
import json
import pathlib

from PIL import Image

from prepare_visdrone_det import even_floor, packed_full_nv12
from prepare_visdrone_sot import oracle_roi

CANVAS_FRAME_BYTES = 1280 * 720 * 3 // 2


def read_boxes(path):
    boxes = []
    for line in path.read_text().splitlines():
        line = line.strip().rstrip(',')
        if line:
            boxes.append([float(v) for v in line.split(',')][:4])
    return boxes


def centred_window(box, side, w, h):
    """Even-aligned square of `side` pixels centred on box (x, y, w, h), clamped inside w x h."""
    if side > min(w, h):
        raise ValueError('window does not fit')
    x, y, bw, bh = box
    cx, cy = x + bw / 2, y + bh / 2
    rx = even_floor(min(max(cx - side / 2, 0), w - side))
    ry = even_floor(min(max(cy - side / 2, 0), h - side))
    return dict(x=rx, y=ry, w=side, h=side, full_frame=False)


def prepare_native(sequence, annotations, out, frames, stride, sides):
    files = sorted(sequence.glob('*.jpg'))
    boxes = read_boxes(annotations)
    if len(files) != len(boxes):
        raise SystemExit(f'{len(files)} images vs {len(boxes)} boxes')
    indices = list(range(0, min(frames, len(files)), stride))
    out.mkdir(parents=True, exist_ok=False)
    first = Image.open(files[0]).convert('RGB')
    w, h = even_floor(first.width), even_floor(first.height)
    regions, targets, digest = [], [], hashlib.sha256()
    with (out / 'source.nv12').open('wb') as stream:
        for index in indices:
            image = Image.open(files[index]).convert('RGB')
            if (image.width, image.height) != (first.width, first.height):
                raise SystemExit('frame size changed inside the sequence')
            packed = packed_full_nv12(image.crop((0, 0, w, h))).tobytes()
            stream.write(packed)
            digest.update(packed)
            box = boxes[index]
            regions.append(dict(source_w=w, source_h=h, x=0, y=0, w=w, h=h, full_frame=True, reuse_source=False,
                                via_1080p=False, method='native_full', tile=0, image_index=index))
            for tile, side in enumerate(sides, start=1):
                regions.append(dict(source_w=w, source_h=h, **centred_window(box, side, w, h), reuse_source=True,
                                    via_1080p=False, method=f'native_{side}', tile=tile, image_index=index))
            targets.append(dict(index=index, file=files[index].name, box=box))
    (out / 'regions.json').write_text(json.dumps(regions))
    manifest = dict(sequence=str(sequence), canvas=[w, h], frame_size=[first.width, first.height], scale=1.0,
                    offset=[0, 0], frames=len(indices), inputs=len(regions), source_sha256=digest.hexdigest(),
                    targets=targets, images=[dict(index=t['index'], file=t['file'], width=w, height=h, scale=1.0,
                                                  offset_x=0, offset_y=0, gt=[]) for t in targets],
                    windows=sides, stride=stride,
                    conversion='original pixels (odd bottom row dropped); RGB->NV12 via inverse SDK full-range '
                               'matrix, 2x2 chroma mean (controlled HEF calibration transform)',
                    licence='VisDrone2019 (AISKYEYE, Tianjin University) — research use; frames not committed')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    return manifest


def prepare_subset720(prepared, out, frames, stride):
    manifest = json.loads((prepared / 'manifest.json').read_text())
    regions = json.loads((prepared / 'regions.json').read_text())
    if not manifest.get('oracle_roi'):
        raise SystemExit('720p preparation lacks the oracle ROI regions (prepare_visdrone_sot.py --roi)')
    keep_frames = set(range(0, min(frames, manifest['frames']), stride))
    out.mkdir(parents=True, exist_ok=False)
    kept, digest = [], hashlib.sha256()
    with (prepared / 'source.nv12').open('rb') as source, (out / 'source.nv12').open('wb') as stream:
        for index in range(manifest['frames']):
            frame = source.read(CANVAS_FRAME_BYTES)
            if len(frame) != CANVAS_FRAME_BYTES:
                raise SystemExit('short 720p source')
            if index not in keep_frames:
                continue
            stream.write(frame)
            digest.update(frame)
            per_frame = [r for r in regions if r['image_index'] == index and
                         (r['full_frame'] or r.get('method') == 'oracle_roi')]
            if len(per_frame) != 2 or per_frame[0]['full_frame'] is not True:
                raise SystemExit(f'unexpected region set for frame {index}')
            per_frame[0] = dict(per_frame[0], reuse_source=False, method='canvas_full')
            per_frame[1] = dict(per_frame[1], reuse_source=True, method='canvas_roi640')
            kept.extend(per_frame)
    targets = [t for t in manifest['targets'] if t['index'] in keep_frames]
    (out / 'regions.json').write_text(json.dumps(kept))
    subset = dict(manifest, frames=len(targets), inputs=len(kept), source_sha256=digest.hexdigest(), targets=targets,
                  images=[i for i in manifest['images'] if i['index'] in keep_frames], stride=stride,
                  subset_of=str(prepared), oracle_roi=True)
    (out / 'manifest.json').write_text(json.dumps(subset, indent=1))
    return subset


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='mode', required=True)
    n = sub.add_parser('native')
    n.add_argument('sequence', type=pathlib.Path)
    n.add_argument('annotations', type=pathlib.Path)
    n.add_argument('out', type=pathlib.Path)
    n.add_argument('--sides', type=int, nargs='+', default=[640, 320])
    s = sub.add_parser('subset720')
    s.add_argument('prepared', type=pathlib.Path)
    s.add_argument('out', type=pathlib.Path)
    for q in (n, s):
        q.add_argument('--frames', type=int, default=240)
        q.add_argument('--stride', type=int, default=1)
    a = p.parse_args()
    if a.mode == 'native':
        for side in a.sides:
            if side < 64 or side % 2:
                raise SystemExit('window sides must be even and >= 64')
        m = prepare_native(a.sequence, a.annotations, a.out, a.frames, a.stride, a.sides)
    else:
        m = prepare_subset720(a.prepared, a.out, a.frames, a.stride)
    print(json.dumps({k: m[k] for k in ('frames', 'inputs', 'canvas', 'source_sha256')}))


if __name__ == '__main__':
    main()
