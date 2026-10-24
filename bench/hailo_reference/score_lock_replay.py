"""Score a garuda-track-replay run against ground-truth target identity.

Inputs: the replay's stdout JSONL (one output per input row) and the
.truth.jsonl sidecar from mot_to_replay.py (or the same shape from another
converter). Judges, per frame where the lock publishes a box, whether that box
covers the true target (IoU >= 0.5), a DIFFERENT annotated object (identity
error — the failure re-acquire hardening must never introduce), or nothing.
Reports state timeline, identity errors, and per-outage re-acquire latency.
"""
import argparse
import json
import pathlib


def iou(a, b):
    ax2, ay2 = a['x']+a['w'], a['y']+a['h']
    bx2, by2 = b['x']+b['w'], b['y']+b['h']
    w = max(0.0, min(ax2, bx2)-max(a['x'], b['x']))
    h = max(0.0, min(ay2, by2)-max(a['y'], b['y']))
    inter = w*h
    union = a['w']*a['h']+b['w']*b['h']-inter
    return inter/union if union > 0 else 0.0


def judge(lock_box, truth):
    """Classify one frame: correct / wrong_identity / unmatched / no_box."""
    if lock_box is None:
        return 'no_box'
    if truth['target'] and iou(lock_box, truth['target']) >= 0.5:
        return 'correct'
    if any(iou(lock_box, other) >= 0.5 for other in truth['others']):
        return 'wrong_identity'
    return 'unmatched'


def outages(truth_rows, min_visibility=0.25):
    """(start_index, end_index) spans where the true target is absent/invisible/dropped."""
    spans, start = [], None
    for i, r in enumerate(truth_rows):
        gone = r['dropped'] or not r['target'] or r['target']['visibility'] < min_visibility
        if gone and start is None:
            start = i
        if not gone and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(truth_rows)))
    return spans


def score(outputs, truth_rows, min_visibility=0.25):
    if len(outputs) < len(truth_rows):
        raise ValueError('Replay output shorter than truth')
    frames = []
    by_sequence = {}
    for o in outputs:
        if o.get('v') == 2 and 'lock' in o:
            by_sequence[o['sequence']] = o
    for r in truth_rows:
        o = by_sequence.get(r['sequence'])
        if o is None:
            raise ValueError(f"missing replay output for sequence {r['sequence']}")
        box = o['lock']['box']
        lock_box = None if box is None else dict(
            x=box['x']/o['frame']['width'], y=box['y']/o['frame']['height'],
            w=box['w']/o['frame']['width'], h=box['h']/o['frame']['height'])
        frames.append(dict(sequence=r['sequence'], capture_ms=r['capture_ms'],
            state=o['lock']['state'], control_valid=o['lock']['control_valid'],
            verdict=judge(lock_box, r)))
    states, verdicts = {}, {}
    for f in frames:
        states[f['state']] = states.get(f['state'], 0)+1
        verdicts[f['verdict']] = verdicts.get(f['verdict'], 0)+1
    locked = [f for f in frames if f['state'] not in ('none', 'acquiring')]
    recoveries = []
    for start, end in outages(truth_rows, min_visibility):
        if end >= len(frames) or not any(f['sequence'] <= truth_rows[start]['sequence'] and
                                         f['verdict'] == 'correct' for f in frames):
            continue
        back_ms = truth_rows[end]['capture_ms']
        after = [f for f in frames[end:] if f['control_valid']]
        first = next(iter(after), None)
        recoveries.append(dict(
            outage_start_ms=truth_rows[start]['capture_ms'], outage_end_ms=back_ms,
            outage_ms=back_ms-truth_rows[start]['capture_ms'],
            reacquired=first is not None and first['verdict'] == 'correct',
            wrong_identity=first is not None and first['verdict'] == 'wrong_identity',
            latency_ms=None if first is None else first['capture_ms']-back_ms))
    correct = verdicts.get('correct', 0)
    return dict(frames=len(frames), locked_frames=len(locked),
        states=states, verdicts=verdicts,
        control_valid_frames=sum(1 for f in frames if f['control_valid']),
        correct_while_control_valid=sum(1 for f in frames if f['control_valid'] and f['verdict'] == 'correct'),
        wrong_identity_frames=verdicts.get('wrong_identity', 0),
        correct_rate=round(correct/len(frames), 4) if frames else None,
        outages=recoveries)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay_output', type=pathlib.Path)
    p.add_argument('truth', type=pathlib.Path)
    p.add_argument('--min-visibility', type=float, default=0.25)
    p.add_argument('--out', type=pathlib.Path)
    a = p.parse_args()
    outputs = [json.loads(s) for s in a.replay_output.read_text().splitlines()
               if s.strip().startswith('{') and '"v"' in s]
    truth_rows = [json.loads(s) for s in a.truth.read_text().splitlines()]
    result = score(outputs, truth_rows, a.min_visibility)
    text = json.dumps(result, indent=2)
    if a.out:
        a.out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
