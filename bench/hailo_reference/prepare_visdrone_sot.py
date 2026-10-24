"""Prepare one VisDrone-SOT sequence as a probe replay stream.

Same canvas and NV12 transform as `prepare_visdrone_det.py` (1280x720, the
node's tile source; inverse SDK full-range matrix), every frame written in
order with the five-tile regions (first region streams the frame, the other
four `reuse_source`), so one probe run yields both the single-tile (full
view) and five-tile detections for the whole sequence. The manifest records
the single annotated target box per frame in canvas pixels; SOT ships no
other objects and no frame rate.
"""
import argparse
import hashlib
import json
import math
import pathlib

from PIL import Image

from prepare_visdrone_det import CANVAS_W, CANVAS_H, five_tile_layout, packed_full_nv12, place_on_canvas


def oracle_roi(gt_xywh, w, h, context=2.5, minimum_side=640):
    """SearchPlanner::next with position_std 0 (the RoiAssist planner: context
    2.5, minimum side 640): a square crop around the annotated target, or the
    full frame when the crop would not fit. Oracle because the live planner
    centres on the tracker's own box, not the annotation."""
    x, y, bw, bh = gt_xywh
    extent = max(bw, bh)
    needed = context * extent
    if needed > min(w, h) or minimum_side > min(w, h):
        return dict(x=0, y=0, w=w, h=h, full_frame=True)
    side = max(minimum_side, int(math.ceil(needed / 2)) * 2)
    cx, cy = x + bw / 2, y + bh / 2
    rx = int(min(max(cx - side / 2, 0), w - side) / 2) * 2
    ry = int(min(max(cy - side / 2, 0), h - side) / 2) * 2
    return dict(x=rx, y=ry, w=side, h=side, full_frame=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('sequence', type=pathlib.Path, help='VisDrone2019-SOT-*/sequences/<name>')
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--limit', type=int, default=0, help='first N frames only (0 = all)')
    p.add_argument('--roi', action='store_true',
                   help='add a sixth region per frame: the oracle target-ROI crop (RoiAssist planner geometry)')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    frames = sorted(a.sequence.glob('*.jpg'))
    if a.limit:
        frames = frames[:a.limit]
    annotation = a.sequence.parent.parent / 'annotations' / (a.sequence.name + '.txt')
    boxes = [[int(v) for v in line.strip().split(',')] for line in annotation.read_text().splitlines() if line.strip()]
    if len(boxes) < len(frames):
        raise SystemExit(f'{len(boxes)} annotations for {len(frames)} frames')
    attributes = a.sequence.parent.parent / 'attributes' / (a.sequence.name + '_attr.txt')
    regions, targets = [], []
    digest = hashlib.sha256()
    size = None
    with (a.output / 'source.nv12').open('xb') as out:
        for index, file in enumerate(frames):
            image = Image.open(file).convert('RGB')
            if size is None:
                size = image.size
            elif image.size != size:
                raise SystemExit('frame size changed mid-sequence')
            canvas, scale, ox, oy = place_on_canvas(image)
            data = packed_full_nv12(canvas).tobytes()
            out.write(data)
            digest.update(data)
            for tile, r in enumerate(five_tile_layout(CANVAS_W, CANVAS_H)):
                regions.append(dict(source_w=CANVAS_W, source_h=CANVAS_H, **r, reuse_source=tile > 0,
                                    via_1080p=False, method='five_tile', tile=tile, image_index=index))
            x, y, w, h = boxes[index]
            target = [x*scale+ox, y*scale+oy, w*scale, h*scale]
            if a.roi:
                regions.append(dict(source_w=CANVAS_W, source_h=CANVAS_H, **oracle_roi(target, CANVAS_W, CANVAS_H),
                                    reuse_source=True, via_1080p=False, method='oracle_roi', tile=5, image_index=index))
            targets.append(dict(index=index, file=file.name, box=target))
    manifest = dict(sequence=str(a.sequence.resolve()), canvas=[CANVAS_W, CANVAS_H], frame_size=list(size),
                    scale=scale, offset=[ox, oy], frames=len(frames), inputs=len(regions),
                    source_sha256=digest.hexdigest(), targets=targets,
                    attributes=attributes.read_text().strip() if attributes.exists() else None,
                    images=[dict(index=t['index'], file=t['file'], width=size[0], height=size[1], scale=scale,
                                 offset_x=ox, offset_y=oy, gt=[]) for t in targets],
                    tile_layout=five_tile_layout(CANVAS_W, CANVAS_H), oracle_roi=a.roi,
                    conversion='PIL bilinear fit to canvas, letterbox pad 114; RGB->NV12 via inverse SDK '
                               'full-range matrix, 2x2 chroma mean (controlled HEF calibration transform)',
                    licence='VisDrone2019 (AISKYEYE, Tianjin University) — research use; frames not committed')
    (a.output / 'regions.json').write_text(json.dumps(regions))
    (a.output / 'manifest.json').write_text(json.dumps(manifest))
    print(json.dumps(dict(frames=len(frames), inputs=len(regions), frame_size=size, scale=scale,
                          source_sha256=digest.hexdigest())))


if __name__ == '__main__':
    main()
