"""Convert VisDrone2019-DET splits into an Ultralytics dataset that keeps the COCO 80-class head.

The deployed stack (HEF NMS config, post-process labels, tracker class filter) assumes the
COCO class ids, so the aerial fine-tune maps VisDrone categories onto those ids instead of
training a ten-class head:

    pedestrian(1), people(2)  -> person(0)      car(4), van(5) -> car(2)
    bicycle(3)                -> bicycle(1)     motor(10)      -> motorcycle(3)
    bus(9)                    -> bus(5)         truck(6)       -> truck(7)
    ignored(0), tricycle(7), awning-tricycle(8), others(11), score==0 rows -> dropped

Dropping a category makes its pixels background for training; that is the same choice the
official VisDrone-to-YOLO conversion makes for ignored regions. Images are symlinked, labels
are normalised xywh clipped to the image, and a data YAML with all 80 COCO names is written.
VisDrone is research-use: nothing here is committed except this tool."""
import argparse
import json
import pathlib
import sys

from PIL import Image

COCO = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
        'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
        'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
        'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
        'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
        'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
        'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard',
        'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase',
        'scissors', 'teddy bear', 'hair drier', 'toothbrush']
VISDRONE_TO_COCO = {1: 0, 2: 0, 3: 1, 4: 2, 5: 2, 10: 3, 9: 5, 6: 7}


def convert_rows(rows, width, height):
    """VisDrone annotation rows -> list of (coco_id, cx, cy, w, h) normalised, plus a drop count."""
    out, dropped = [], 0
    for row in rows:
        f = [v for v in row.strip().rstrip(',').split(',') if v != '']
        if len(f) < 6:
            continue
        x, y, w, h = (float(v) for v in f[:4])
        score = int(float(f[4])) if len(f) > 4 else 1
        category = int(float(f[5])) if len(f) > 5 else 0
        coco = VISDRONE_TO_COCO.get(category)
        if score == 0 or coco is None or w <= 0 or h <= 0:
            dropped += 1
            continue
        x0, y0 = max(0., x), max(0., y)
        x1, y1 = min(float(width), x + w), min(float(height), y + h)
        if x1 - x0 < 1 or y1 - y0 < 1:
            dropped += 1
            continue
        out.append((coco, (x0 + x1) / 2 / width, (y0 + y1) / 2 / height, (x1 - x0) / width, (y1 - y0) / height))
    return out, dropped


def convert_split(split_root, out_root, name):
    images_in = split_root / 'images'
    ann_in = split_root / 'annotations'
    images_out = out_root / name / 'images'
    labels_out = out_root / name / 'labels'
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)
    counts = dict(images=0, boxes=0, dropped=0, per_class={})
    for image in sorted(images_in.glob('*.jpg')):
        with Image.open(image) as im:
            width, height = im.size
        rows = (ann_in / (image.stem + '.txt')).read_text().splitlines() if (ann_in / (image.stem + '.txt')).exists() else []
        boxes, dropped = convert_rows(rows, width, height)
        link = images_out / image.name
        if not link.exists():
            link.symlink_to(image.resolve())
        (labels_out / (image.stem + '.txt')).write_text(''.join(f'{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n' for c, cx, cy, w, h in boxes))
        counts['images'] += 1
        counts['boxes'] += len(boxes)
        counts['dropped'] += dropped
        for c, *_ in boxes:
            counts['per_class'][COCO[c]] = counts['per_class'].get(COCO[c], 0) + 1
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('train', type=pathlib.Path, help='VisDrone2019-DET-train directory (images/, annotations/)')
    p.add_argument('val', type=pathlib.Path, help='VisDrone2019-DET-val directory')
    p.add_argument('out', type=pathlib.Path, help='output dataset root (never inside the repo)')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    summary = {name: convert_split(root, a.out, name) for name, root in (('train', a.train), ('val', a.val))}
    (a.out / 'visdrone-coco.yaml').write_text(
        f"path: {a.out.resolve()}\ntrain: train/images\nval: val/images\nnames:\n" + ''.join(f'  {i}: {n}\n' for i, n in enumerate(COCO)))
    (a.out / 'conversion-summary.json').write_text(json.dumps(dict(mapping=VISDRONE_TO_COCO, splits=summary), indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
