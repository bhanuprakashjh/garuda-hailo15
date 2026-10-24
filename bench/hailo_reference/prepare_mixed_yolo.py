"""Assemble a mixed Ultralytics dataset: VisDrone-DET train (already converted to COCO ids by
prepare_visdrone_yolo.py) plus COCO val2017 with its native 80-class YOLO labels.

Why: fine-tuning on VisDrone alone forgets everything COCO taught the head about close-range
people and every class absent from aerial footage (measured 2026-09-13: the epoch-1 aerial
model found the desk person at the 0.5 floor in 1 of 433 recorded frames and the phone in 0).
Keeping a COCO sample in every epoch holds the 80-class head while the aerial data adds the
small-object recall. Validation stays VisDrone-val (the aerial signal); the desk scene is
checked separately on the board with the recorded A/B replay.

Images are symlinked, labels copied; nothing under the datasets tree is committed."""
import argparse
import json
import pathlib
import shutil
import sys

from prepare_visdrone_yolo import COCO


def link_split(images, labels_dir, out_root, name, tag):
    images_out = out_root / name / 'images'
    labels_out = out_root / name / 'labels'
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)
    n = boxes = 0
    for image in images:
        label = labels_dir / (image.stem + '.txt')
        if not label.exists():
            continue
        link = images_out / f'{tag}-{image.name}'
        if not link.exists():
            link.symlink_to(image.resolve())
        shutil.copyfile(label, labels_out / f'{tag}-{image.stem}.txt')
        n += 1
        boxes += sum(1 for line in label.read_text().splitlines() if line.strip())
    return dict(images=n, boxes=boxes)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('visdrone', type=pathlib.Path, help='output of prepare_visdrone_yolo.py (train/, val/)')
    p.add_argument('coco_images', type=pathlib.Path, help='COCO val2017 image directory')
    p.add_argument('coco_labels', type=pathlib.Path, help='YOLO labels for those images (coco2017labels val2017)')
    p.add_argument('out', type=pathlib.Path)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    summary = dict(
        visdrone_train=link_split(sorted((a.visdrone / 'train' / 'images').iterdir()), a.visdrone / 'train' / 'labels', a.out, 'train', 'vd'),
        coco_val2017_train=link_split(sorted(a.coco_images.glob('*.jpg')), a.coco_labels, a.out, 'train', 'coco'),
        visdrone_val=link_split(sorted((a.visdrone / 'val' / 'images').iterdir()), a.visdrone / 'val' / 'labels', a.out, 'val', 'vd'))
    (a.out / 'mixed-coco.yaml').write_text(
        f"path: {a.out.resolve()}\ntrain: train/images\nval: val/images\nnames:\n" + ''.join(f'  {i}: {n}\n' for i, n in enumerate(COCO)))
    (a.out / 'conversion-summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
