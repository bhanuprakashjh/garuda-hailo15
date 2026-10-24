"""Convert a sequence-replay result directory (regions + per-tile predictions)
into garuda-track-replay input JSONL: merged per-frame detections on the real
capture clock, with an optional class-arming command prologue.

Detections carry no appearance/embedding (they come from stored predictions,
not pixels), so replays exercise the tracker's geometric and temporal logic.
"""
import argparse
import gzip
import json
import pathlib

from score_4k_tiles import map_box, nms


def read_predictions(results):
    plain, packed = results/'letterbox.jsonl', results/'letterbox.jsonl.gz'
    opener = plain.read_text if plain.exists() else None
    if opener is None:
        with gzip.open(packed, 'rt') as f:
            text = f.read()
    else:
        text = opener()
    return [json.loads(s) for s in text.splitlines()]


def merged_frames(results, floor):
    """Yield (source_frame, source_timestamp_ns, [detection dicts]) in order."""
    rs = json.loads((results/'regions.json').read_text())
    ps = read_predictions(results)
    if len(rs) != len(ps):
        raise ValueError('Missing results')
    groups, stamps = {}, {}
    for index, (r, pred) in enumerate(zip(rs, ps)):
        if pred['frame'] != index or pred['preprocessing'] != 'letterbox':
            raise ValueError('Unexpected prediction order/mode')
        frame = r['source_frame']
        stamps[frame] = int(r['source_timestamp_ns'])
        for d in pred['detections']:
            box = map_box(r, d)
            if box is not None:
                groups.setdefault(frame, []).append(dict(class_id=d['class_id'],
                    label=d['label'], score=d['score'], box=box))
    for frame in sorted(stamps):
        kept = [d for d in nms(groups.get(frame, [])) if d['score'] >= floor]
        yield frame, stamps[frame], kept


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('results', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--floor', type=float, default=0.05)
    p.add_argument('--source-width', type=int, default=3840)
    p.add_argument('--source-height', type=int, default=2160)
    p.add_argument('--arm-class', help='Emit a target-class arming command before the first frame')
    p.add_argument('--latency-ms', type=float, default=10.0,
                   help='Deterministic capture-to-update latency for now_ms')
    a = p.parse_args()
    rows, base = [], None
    sequence = 0
    for frame, stamp, dets in merged_frames(a.results, a.floor):
        if base is None:
            base = stamp
            if a.arm_class:
                rows.append(dict(cmd='target', cls=a.arm_class, now_ms=0.0))
        sequence += 1
        capture_ms = (stamp-base)/1e6
        rows.append(dict(sequence=sequence, capture_ms=capture_ms,
            now_ms=capture_ms+a.latency_ms, timestamp_valid=True,
            source_frame=frame,
            detections=[dict(box=dict(x=d['box'][0]/a.source_width,
                                      y=d['box'][1]/a.source_height,
                                      w=(d['box'][2]-d['box'][0])/a.source_width,
                                      h=(d['box'][3]-d['box'][1])/a.source_height),
                             label=d['label'], confidence=min(1.0, d['score']))
                        for d in dets]))
    if not rows:
        raise ValueError('No frames converted')
    with a.output.open('x') as out:
        for row in rows:
            if 'cmd' in row:
                out.write(json.dumps({'cmd': row['cmd'], 'class': row['cls'],
                                      'now_ms': row['now_ms']})+'\n')
            else:
                out.write(json.dumps(row)+'\n')
    frames = sequence
    print(json.dumps(dict(frames=frames, floor=a.floor, armed=a.arm_class or None)))


if __name__ == '__main__':
    main()
