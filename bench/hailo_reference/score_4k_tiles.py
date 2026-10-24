"""Map letterboxed tile detections to source, merge, and score sparse phone boxes."""
import argparse
import collections
import json
import pathlib

# Manually reviewed on 960x540 previews BEFORE viewing replay predictions.
# Approximate visible phone extents, multiplied by four to native coordinates.
ANNOTATIONS = {90: [337*4, 190*4, 414*4, 338*4],
               360: [219*4, 214*4, 270*4, 337*4],
               630: [521*4, 248*4, 583*4, 383*4]}

def iou(a, b):
    inter = max(0, min(a[2], b[2])-max(a[0], b[0]))*max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
    return inter/union if union > 0 else 0

def map_box(r, d):
    # Network input of the HEF the region was run through: 640x640 unless the preparation
    # recorded network_w/network_h (e.g. 1280x736 single-pass model).
    nw, nh = r.get('network_w', 640), r.get('network_h', 640)
    scale = min(nw/r['w'], nh/r['h'])
    cw, ch = r['w']*scale, r['h']*scale
    # Supported comparison crops have exact even-sized letterbox content.
    if cw % 2 or ch % 2:
        raise ValueError('Unsupported rounding geometry')
    px, py = (nw-cw)/2, (nh-ch)/2
    x1, y1 = max(px, d['x1']*nw), max(py, d['y1']*nh)
    x2, y2 = min(px+cw, d['x2']*nw), min(py+ch, d['y2']*nh)
    if x2 <= x1 or y2 <= y1:
        return None
    return [r['x']+(x1-px)/scale, r['y']+(y1-py)/scale,
            r['x']+(x2-px)/scale, r['y']+(y2-py)/scale]

def nms(ds):
    kept = []
    for d in sorted(ds, key=lambda d: d['score'], reverse=True):
        if not any(d['class_id'] == k['class_id'] and iou(d['box'], k['box']) > .5 for k in kept):
            kept.append(d)
    return kept

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('results', type=pathlib.Path)
    a = p.parse_args()
    rs = json.loads((a.results/'regions.json').read_text())
    ps = [json.loads(s) for s in (a.results/'letterbox.jsonl').read_text().splitlines()]
    if len(rs) != len(ps):
        raise ValueError('Missing results')
    groups = collections.defaultdict(list)
    times = collections.defaultdict(list)
    for index, (r, pred) in enumerate(zip(rs, ps)):
        if pred['frame'] != index or pred['preprocessing'] != 'letterbox':
            raise ValueError('Unexpected prediction order/mode')
        key = (r['source_frame'], r['method'])
        times[key].append(pred['infer_wait_ms'])
        for d in pred['detections']:
            box = map_box(r, d)
            if box is not None:
                groups[key].append(dict(class_id=d['class_id'], label=d['label'],
                    score=d['score'], box=box, tile=index))
    report = []
    for (frame, method), waits in sorted(times.items()):
        ds = nms(groups[(frame, method)])
        phones = [dict(d, iou=iou(d['box'], ANNOTATIONS[frame])) for d in ds if d['class_id'] == 67]
        report.append(dict(frame=frame, method=method, inputs=len(waits),
            annotation=ANNOTATIONS[frame], inference_wait_sum_ms=sum(waits),
            phone_candidates=phones, matched_at_iou_05={str(t): any(d['score'] >= t and d['iou'] >= .5 for d in phones) for t in (.15, .38, .5)},
            all_detections=ds))
    result = dict(scope='Three sparse manual phone boxes, not recall, tracking or live FPS. Timings exclude crop/resize and transport; baseline frontend resize is approximated with bilinear DSP.',
        class_aware_nms_iou=.5, rows=report)
    (a.results/'score.json').write_text(json.dumps(result, indent=2))
    for r in report:
        print(json.dumps({k:v for k,v in r.items() if k not in ('all_detections', 'phone_candidates')}))

if __name__ == '__main__':
    main()
