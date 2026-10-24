#!/usr/bin/env python3
"""Score paired crop outputs against the frozen sparse phone annotations; no tracking claims."""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = max(0, a[2]-a[0])*max(0, a[3]-a[1]) + max(0, b[2]-b[0])*max(0, b[3]-b[1]) - intersection
    return intersection/union if union > 0 else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('regions', type=Path)
    ap.add_argument('predictions', type=Path)
    args = ap.parse_args()
    regions = json.loads(args.regions.read_text())
    predictions = [json.loads(s) for s in args.predictions.read_text().splitlines()]
    if len(regions) != len(predictions):
        raise ValueError('region/prediction count mismatch')
    details, by_mode = [], defaultdict(list)
    for index, (r, p) in enumerate(zip(regions, predictions)):
        if p['frame'] != index:
            raise ValueError('prediction frame order mismatch')
        scale = min(640/r['w'], 640/r['h'])
        # The probe's supported regions are full 1280x720 or square; padding is exact and even.
        pad_x, pad_y = (640-r['w']*scale)/2, (640-r['h']*scale)/2
        scale_x = scale_y = scale
        if p.get('preprocessing') == 'stretch':
            scale_x, scale_y, pad_x, pad_y = 640/r['w'], 640/r['h'], 0, 0
        candidates = []
        for d in p['detections']:
            if d['class_id'] != 67:
                continue
            box = [r['x']+(d['x1']*640-pad_x)/scale_x, r['y']+(d['y1']*640-pad_y)/scale_y,
                   r['x']+(d['x2']*640-pad_x)/scale_x, r['y']+(d['y2']*640-pad_y)/scale_y]
            box = [max(0, min(r['source_w'] if k % 2 == 0 else r['source_h'], v)) for k, v in enumerate(box)]
            candidates.append({'score': d['score'], 'box_xyxy': box, 'iou': iou(box, r['annotation_xyxy'])})
        item = {'file': r['file'], 'mode': r['mode'], 'clipped': r['clipped'], 'candidates': candidates,
                'matched_score_iou_0.5': max((d['score'] for d in candidates if d['iou'] >= .5), default=None)}
        details.append(item);by_mode[r['mode']].append(item)
    summary = {}
    for mode, rows in by_mode.items():
        summary[mode] = {}
        for split, selected in [('fully_inside', [r for r in rows if not r['clipped']]), ('clipped', [r for r in rows if r['clipped']])]:
            summary[mode][split] = {'frames': len(selected), 'at_threshold': {
                str(threshold): {'matched_at_iou_0.5': sum(r['matched_score_iou_0.5'] is not None and r['matched_score_iou_0.5'] >= threshold for r in selected),
                    'unmatched_phone_boxes': sum(d['score'] >= threshold and d['iou'] < .5 for r in selected for d in r['candidates'])}
                for threshold in (.15, .38, .4, .5)}}
    print(json.dumps({'scope': 'Sparse oracle-centered crop diagnostic. Approximate manual boxes; no identity, trajectory or drone accuracy claim.',
                      'iou_threshold': .5, 'summary': summary, 'details': details}, indent=2))

if __name__ == '__main__':
    main()
