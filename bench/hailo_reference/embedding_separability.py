"""How well does a descriptor separate the annotated target from other people?

Reads a garuda-track-replay input (detections carrying `embedding` and/or
`appearance`) and its truth sidecar. For every frame where a person
detection sits on the target (IoU >= 0.5), records the descriptor distance
(a) from the target's first descriptor (anchor, as TargetOwner keeps it),
(b) from the previous target descriptor (drift), and (c) from every other
person in the same frame. Reports medians and the fraction of other-person
pairs that would pass the gate (0.25 for embeddings = IdentityConfig
max_anchor_distance; 0.55 for histograms = appearance_gate). Same
computation the histogram finding used, so the two descriptors compare.
"""
import argparse
import json
import math
import pathlib


def iou(a, b):
    ax2, ay2, bx2, by2 = a['x']+a['w'], a['y']+a['h'], b['x']+b['w'], b['y']+b['h']
    w, h = max(0, min(ax2, bx2)-max(a['x'], b['x'])), max(0, min(ay2, by2)-max(a['y'], b['y']))
    inter = w*h
    union = a['w']*a['h']+b['w']*b['h']-inter
    return inter/union if union > 0 else 0


def embedding_distance(a, b):
    """1 - cosine similarity, as garuda::fresh::embedding_distance."""
    dot = sum(x*y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(y*y for y in b))
    return 1 - max(-1, min(1, dot/(na*nb))) if na > 1e-12 and nb > 1e-12 else float('inf')


def histogram_distance(a, b):
    """Bhattacharyya, as garuda::fresh::appearance_distance."""
    return math.sqrt(max(0, 1-min(1, sum(math.sqrt(x*y) for x, y in zip(a, b)))))


DESCRIPTORS = {'embedding': (lambda d: d['embedding']['values'] if d.get('embedding') else None, embedding_distance, .25),
               'appearance': (lambda d: d.get('appearance'), histogram_distance, .55)}


def analyse(frames, truth, kind):
    get, dist, gate = DESCRIPTORS[kind]
    anchor, previous = None, None
    to_anchor, drift, others = [], [], []
    for f in frames:
        t = truth.get(f['sequence'])
        if not t or not t['target']:
            continue
        persons = [d for d in f['detections'] if d['label'] == 'person' and get(d) is not None]
        on = [d for d in persons if iou(d['box'], t['target']) >= .5]
        if not on:
            continue
        target = max(on, key=lambda d: iou(d['box'], t['target']))
        v = get(target)
        if anchor is None:
            anchor = v
        else:
            to_anchor.append(dist(anchor, v))
            drift.append(dist(previous, v))
        previous = v
        for d in persons:
            if d is not target and iou(d['box'], t['target']) < .3:
                others.append(dist(v, get(d)))
    def stats(xs):
        xs = sorted(x for x in xs if math.isfinite(x))
        return dict(n=len(xs), median=round(xs[len(xs)//2], 3) if xs else None, max=round(xs[-1], 3) if xs else None,
                    under_gate=round(sum(x <= gate for x in xs)/len(xs), 3) if xs else None)
    return dict(descriptor=kind, gate=gate, target_vs_anchor=stats(to_anchor), target_frame_to_frame=stats(drift),
                target_vs_other_persons=stats(others))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay_input', type=pathlib.Path)
    p.add_argument('truth', type=pathlib.Path)
    p.add_argument('--out', type=pathlib.Path)
    a = p.parse_args()
    frames = [json.loads(l) for l in a.replay_input.read_text().splitlines() if l.strip()]
    frames = [f for f in frames if 'detections' in f]
    truth = {t['sequence']: t for t in (json.loads(l) for l in a.truth.read_text().splitlines() if l.strip())}
    report = {kind: analyse(frames, truth, kind) for kind in DESCRIPTORS
              if any(DESCRIPTORS[kind][0](d) is not None for f in frames for d in f['detections'])}
    text = json.dumps(report, indent=2)
    if a.out:
        a.out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
