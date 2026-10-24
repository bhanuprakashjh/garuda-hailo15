"""Score a paired detector A/B sequence replay: per-frame class presence,
miss-gap statistics and inference waits for two models on identical inputs.

Presence of any 'cell phone' / 'person' box after tile merge is a proxy — there
is no per-frame ground truth, so mislocalized detections are not distinguished.
Detector-only comparison: no tracker, no live FPS, decoded H264 inputs.
"""
import argparse
import json
import pathlib
import statistics

from score_4k_tiles import map_box, nms

PHONE, PERSON = 67, 0


def frame_series(results):
    """Merge each source frame's tile detections; return ordered per-frame rows."""
    rs = json.loads((results/'regions.json').read_text())
    ps = [json.loads(s) for s in (results/'letterbox.jsonl').read_text().splitlines()]
    if len(rs) != len(ps):
        raise ValueError('Missing results')
    groups, waits = {}, {}
    for index, (r, pred) in enumerate(zip(rs, ps)):
        if pred['frame'] != index or pred['preprocessing'] != 'letterbox':
            raise ValueError('Unexpected prediction order/mode')
        frame = r['source_frame']
        waits.setdefault(frame, []).append(pred['infer_wait_ms'])
        for d in pred['detections']:
            box = map_box(r, d)
            if box is not None:
                groups.setdefault(frame, []).append(dict(class_id=d['class_id'],
                    label=d['label'], score=d['score'], box=box))
    series = []
    for frame in sorted(waits):
        merged = nms(groups.get(frame, []))
        best = {}
        for d in merged:
            best[d['class_id']] = max(best.get(d['class_id'], 0.0), d['score'])
        series.append(dict(frame=frame, phone=best.get(PHONE, 0.0),
                           person=best.get(PERSON, 0.0),
                           wait_ms=sum(waits[frame]), tiles=len(waits[frame])))
    return series


def gap_lengths(hits):
    """Lengths of consecutive-miss runs in a boolean hit sequence."""
    gaps, run = [], 0
    for hit in hits:
        if hit:
            if run:
                gaps.append(run)
            run = 0
        else:
            run += 1
    if run:
        gaps.append(run)
    return gaps


def summarize(series, thresholds=(0.15, 0.5)):
    out = dict(frames=len(series))
    for cls in ('phone', 'person'):
        scores = [row[cls] for row in series]
        cls_out = {}
        for t in thresholds:
            hits = [s >= t for s in scores]
            gaps = gap_lengths(hits)
            cls_out[str(t)] = dict(detected=sum(hits),
                rate=round(sum(hits)/len(hits), 4) if hits else None,
                max_gap=max(gaps, default=0), gaps_ge_5=sum(g >= 5 for g in gaps))
        hit_scores = [s for s in scores if s >= thresholds[0]]
        cls_out['conf_on_hits'] = dict(
            mean=round(statistics.fmean(hit_scores), 4) if hit_scores else None,
            median=round(statistics.median(hit_scores), 4) if hit_scores else None)
        out[cls] = cls_out
    waits = sorted(row['wait_ms'] for row in series)
    out['frame_wait_ms'] = dict(mean=round(statistics.fmean(waits), 2),
        median=round(statistics.median(waits), 2),
        p95=round(waits[int(len(waits)*0.95)-1], 2), max=round(waits[-1], 2))
    return out


def paired(series_a, series_b, thresholds=(0.15, 0.5)):
    if [r['frame'] for r in series_a] != [r['frame'] for r in series_b]:
        raise ValueError('Replays cover different frames')
    out = {}
    for cls in ('phone', 'person'):
        cls_out = {}
        for t in thresholds:
            a_only = b_only = both = neither = 0
            for ra, rb in zip(series_a, series_b):
                a, b = ra[cls] >= t, rb[cls] >= t
                a_only += a and not b
                b_only += b and not a
                both += a and b
                neither += not a and not b
            cls_out[str(t)] = dict(a_only=a_only, b_only=b_only, both=both, neither=neither)
        out[cls] = cls_out
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('results_a', type=pathlib.Path)
    p.add_argument('results_b', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--label-a', default='a')
    p.add_argument('--label-b', default='b')
    a = p.parse_args()
    series_a, series_b = frame_series(a.results_a), frame_series(a.results_b)
    result = dict(
        scope='Per-frame class presence after tile merge, not IoU-verified recall. '
              'Detector-only replay of decoded H264; no tracker; waits are sequential '
              'per-tile inference sums, not live FPS.',
        labels={'a': a.label_a, 'b': a.label_b},
        a=summarize(series_a), b=summarize(series_b),
        paired=paired(series_a, series_b),
        series={'a': series_a, 'b': series_b})
    a.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('labels', 'a', 'b', 'paired')}, indent=2))


if __name__ == '__main__':
    main()
