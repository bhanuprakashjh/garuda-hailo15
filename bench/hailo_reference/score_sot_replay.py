"""Score a garuda-track-replay run on a single-object (SOT) truth sidecar.

SOT truth has the target every frame and no bystanders, so the questions are
hold and recovery, not identity: after the lock fires, how many frames is the
published lock box on the target (IoU >= 0.5), how often does the tracker
declare the target lost, how long until it is back on the target, and how
many control-valid frames point somewhere else (the follow-me failure that
matters — the vehicle would steer at it).
"""
import argparse
import json
import pathlib

from score_lock_replay import judge


def score(outputs, truth_rows, lock_sequence):
    by_sequence = {o['sequence']: o for o in outputs if o.get('v') == 2 and 'lock' in o}
    frames = []
    for r in truth_rows:
        if r['sequence'] < lock_sequence:
            continue
        o = by_sequence.get(r['sequence'])
        if o is None:
            raise ValueError(f"missing replay output for sequence {r['sequence']}")
        box = o['lock']['box']
        lock_box = None if box is None else dict(
            x=box['x']/o['frame']['width'], y=box['y']/o['frame']['height'],
            w=box['w']/o['frame']['width'], h=box['h']/o['frame']['height'])
        frames.append(dict(sequence=r['sequence'], capture_ms=r['capture_ms'], state=o['lock']['state'],
                           control_valid=o['lock']['control_valid'], verdict=judge(lock_box, r)))
    states, verdicts = {}, {}
    for f in frames:
        states[f['state']] = states.get(f['state'], 0)+1
        verdicts[f['verdict']] = verdicts.get(f['verdict'], 0)+1
    # Loss episodes: runs of frames not on target after having been on target.
    episodes, run_start, seen_correct = [], None, False
    for i, f in enumerate(frames):
        on_target = f['verdict'] == 'correct'
        if on_target:
            seen_correct = True
            if run_start is not None:
                episodes.append(dict(start_ms=frames[run_start]['capture_ms'], end_ms=f['capture_ms'],
                                     duration_ms=f['capture_ms']-frames[run_start]['capture_ms'],
                                     states=sorted({g['state'] for g in frames[run_start:i]}), recovered=True))
                run_start = None
        elif seen_correct and run_start is None:
            run_start = i
    if run_start is not None:
        episodes.append(dict(start_ms=frames[run_start]['capture_ms'], end_ms=None,
                             duration_ms=frames[-1]['capture_ms']-frames[run_start]['capture_ms'],
                             states=sorted({g['state'] for g in frames[run_start:]}), recovered=False))
    n = len(frames)
    return dict(frames_after_lock=n, lock_sequence=lock_sequence, states=states, verdicts=verdicts,
                on_target_rate=round(verdicts.get('correct', 0)/n, 4) if n else None,
                control_valid_frames=sum(f['control_valid'] for f in frames),
                control_valid_off_target=sum(f['control_valid'] and f['verdict'] != 'correct' for f in frames),
                loss_episodes=len(episodes), recovered_episodes=sum(e['recovered'] for e in episodes),
                longest_loss_ms=max((e['duration_ms'] for e in episodes), default=0), episodes=episodes)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay_output', type=pathlib.Path)
    p.add_argument('truth', type=pathlib.Path)
    p.add_argument('--lock-sequence', type=int, required=True)
    p.add_argument('--out', type=pathlib.Path)
    a = p.parse_args()
    outputs = [json.loads(s) for s in a.replay_output.read_text().splitlines()
               if s.strip().startswith('{') and '"v"' in s]
    truth_rows = [json.loads(s) for s in a.truth.read_text().splitlines()]
    result = score(outputs, truth_rows, a.lock_sequence)
    text = json.dumps(result, indent=2)
    if a.out:
        a.out.write_text(text)
    print(json.dumps({k: v for k, v in result.items() if k != 'episodes'}))


if __name__ == '__main__':
    main()
