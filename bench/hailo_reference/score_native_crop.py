"""Score oracle native-crop probe runs against the annotated target, per region method.

Input: `run_visdrone_det.py` output directories (regions.json + letterbox.jsonl +
run.json) made from `prepare_native_crop.py` preparations. For every frame and
region method the best person detection by IoU with the annotated box is taken;
a frame counts as detected at a floor when that IoU is >= 0.5 and the score
reaches the floor. Boxes are mapped from the letterboxed 640 input back to the
region's source pixels with FrameGeometry::make rounding (content = lround).
Also reported: the median score of the matches, and how many person boxes
overlap the target at IoU >= 0.3 per frame (duplicates that block a click).
"""
import argparse
import gzip
import json
import pathlib
import statistics

FLOORS = (0.15, 0.4, 0.5)
TRACKED = ('person', 'car', 'bicycle', 'motorcycle', 'dog', 'cell phone', 'truck', 'bus')   # follow profile classes + the vehicle labels a van draws


def map_box(r, d):
    scale = min(640 / r['w'], 640 / r['h'])
    cw, ch = round(r['w'] * scale), round(r['h'] * scale)
    px, py = (640 - cw) // 2, (640 - ch) // 2
    x1, y1 = max(px, d['x1'] * 640), max(py, d['y1'] * 640)
    x2, y2 = min(px + cw, d['x2'] * 640), min(py + ch, d['y2'] * 640)
    if x2 <= x1 or y2 <= y1:
        return None
    return [r['x'] + (x1 - px) / scale, r['y'] + (y1 - py) / scale,
            r['x'] + (x2 - px) / scale, r['y'] + (y2 - py) / scale]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0


def predictions(results):
    plain, packed = results / 'letterbox.jsonl', results / 'letterbox.jsonl.gz'
    text = plain.read_text() if plain.exists() else gzip.open(packed, 'rt').read()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def score(results):
    run = json.loads((results / 'run.json').read_text())
    manifest = run['preparation']
    regions = json.loads((results / 'regions.json').read_text())
    preds = predictions(results)
    if len(regions) != len(preds):
        raise SystemExit(f'{results}: {len(regions)} regions vs {len(preds)} predictions')
    truth = {t['index']: t['box'] for t in manifest['targets']}
    # SOT annotates one target of any class (317a is a rider, 317b a van), and the node's click is
    # class-agnostic, so score the best box of ANY tracked label as well as the person-only view.
    per_method = {}
    for index, (r, pred) in enumerate(zip(regions, preds)):
        if pred['frame'] != index:
            raise SystemExit('prediction order mismatch')
        method = r.get('method', 'full' if r['full_frame'] else 'crop')
        x, y, w, h = truth[r['image_index']]
        gt = [x, y, x + w, y + h]
        best, best_any, best_label, overlapping = None, None, None, 0
        for d in pred['detections']:
            if d['label'] not in TRACKED:
                continue
            box = map_box(r, d)
            if box is None:
                continue
            o = iou(box, gt)
            if o >= 0.3:
                overlapping += 1
            if o >= 0.5:
                if d['label'] == 'person' and (best is None or d['score'] > best):
                    best = d['score']
                if best_any is None or d['score'] > best_any:
                    best_any, best_label = d['score'], d['label']
        m = per_method.setdefault(method, dict(frames=0, matches=[], matches_any=[], labels=[], overlapping=[],
                                               detected={f: 0 for f in FLOORS}, detected_any={f: 0 for f in FLOORS}))
        m['frames'] += 1
        m['overlapping'].append(overlapping)
        if best is not None:
            m['matches'].append(best)
            for f in FLOORS:
                if best >= f:
                    m['detected'][f] += 1
        if best_any is not None:
            m['matches_any'].append(best_any)
            m['labels'].append(best_label)
            for f in FLOORS:
                if best_any >= f:
                    m['detected_any'][f] += 1
    out = {}
    for method, m in per_method.items():
        labels = {}
        for label in m['labels']:
            labels[label] = labels.get(label, 0) + 1
        out[method] = dict(frames=m['frames'],
                           person_recall={str(f): round(m['detected'][f] / m['frames'], 3) for f in FLOORS},
                           any_class_recall={str(f): round(m['detected_any'][f] / m['frames'], 3) for f in FLOORS},
                           detected_person={str(f): m['detected'][f] for f in FLOORS},
                           detected_any={str(f): m['detected_any'][f] for f in FLOORS},
                           person_match_score_median=round(statistics.median(m['matches']), 3) if m['matches'] else None,
                           any_match_score_median=round(statistics.median(m['matches_any']), 3) if m['matches_any'] else None,
                           best_label_frames=dict(sorted(labels.items(), key=lambda kv: -kv[1])),
                           overlapping_boxes_mean=round(statistics.mean(m['overlapping']), 2),
                           frames_with_2plus_overlapping=sum(1 for c in m['overlapping'] if c >= 2))
    return dict(results=str(results), hef_sha256=run['hef_sha256'], sequence=manifest['sequence'],
                frames=manifest['frames'], target_first_box=manifest['targets'][0]['box'], methods=out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('results', type=pathlib.Path, nargs='+')
    p.add_argument('--out', type=pathlib.Path)
    a = p.parse_args()
    scored = [score(r) for r in a.results]
    if a.out:
        a.out.write_text(json.dumps(dict(scope='oracle native-crop probe; person recall at IoU>=0.5 vs the annotated '
                                               'SOT box per region method; no tracker, no identity', runs=scored),
                                    indent=1))
    for s in scored:
        seq = pathlib.Path(s['sequence']).name
        for method, m in s['methods'].items():
            pr, ar = m['person_recall'], m['any_class_recall']
            print(f"{seq} {s['hef_sha256'][:8]} {method:14s} frames {m['frames']:3d}  "
                  f"person@.15/.4/.5 {pr['0.15']:.3f}/{pr['0.4']:.3f}/{pr['0.5']:.3f}  "
                  f"any@.15/.4/.5 {ar['0.15']:.3f}/{ar['0.4']:.3f}/{ar['0.5']:.3f}  "
                  f"median {m['any_match_score_median']}  labels {m['best_label_frames']}  "
                  f"overlap {m['overlapping_boxes_mean']} (2+ on {m['frames_with_2plus_overlapping']})")


if __name__ == '__main__':
    main()
