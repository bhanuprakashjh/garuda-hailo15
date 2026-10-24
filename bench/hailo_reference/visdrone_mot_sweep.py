"""VisDrone-MOT re-acquire sweep: many targets, one protocol, one table.

For every sequence in a VisDrone-MOT split, the longest-lived pedestrians
(category 1/2) become lock targets; each gets a target-only drop of
`--drop-s` seconds centred on its span (ground-truth camera motion attached,
idealized appearance so the crowd-flag path can bind), replayed with
re-acquire ON (crowd flag on) and OFF. Reports per case and in aggregate:
re-acquired?, latency, control-valid frames, wrong-identity frames ON vs OFF.
Idealized appearance = a mechanism test of the gates and radius, not of the
board's descriptors (see the 2026-09-12 VisDrone-MOT README).
"""
import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def pedestrians(annotation):
    spans = {}
    for line in annotation.read_text().splitlines():
        if not line.strip():
            continue
        f = [int(v) for v in line.strip().rstrip(',').split(',')]
        if f[6] == 0 or f[7] not in (1, 2):
            continue
        s = spans.setdefault(f[1], [f[0], f[0], 0])
        s[0], s[1], s[2] = min(s[0], f[0]), max(s[1], f[0]), s[2] + 1
    return spans


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, **kw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('sequences', type=pathlib.Path, help='VisDrone2019-MOT-*/sequences')
    p.add_argument('replay', type=pathlib.Path, help='garuda-track-replay binary')
    p.add_argument('workdir', type=pathlib.Path)
    p.add_argument('--out', type=pathlib.Path, required=True)
    p.add_argument('--rate', type=float, default=30.0)
    p.add_argument('--targets-per-sequence', type=int, default=3)
    p.add_argument('--min-frames', type=int, default=150)
    p.add_argument('--drop-s', type=float, default=2.5)
    p.add_argument('--lock-frame', type=int, default=15)
    a = p.parse_args()
    a.workdir.mkdir(parents=True, exist_ok=True)
    crowd = a.workdir / 'crowd-on.json'; crowd.write_text('{"reacquire_appearance_crowd": true}')
    off = a.workdir / 'off.json'; off.write_text('{"reacquire_window_ms": 0}')
    cases = []
    for seq in sorted(a.sequences.iterdir()):
        annotation = seq.parent.parent / 'annotations' / (seq.name + '.txt')
        spans = pedestrians(annotation)
        picked = sorted(((v[2], gid, v) for gid, v in spans.items() if v[2] >= a.min_frames and v[0] <= a.lock_frame),
                        reverse=True)[:a.targets_per_sequence]
        for count, gid, (first, last, n) in picked:
            mid_s = (first + last) / 2 / a.rate
            window = f'{mid_s - a.drop_s/2:.2f},{mid_s + a.drop_s/2:.2f}'
            prefix = a.workdir / f'{seq.name}-gid{gid}'
            for f in a.workdir.glob(prefix.name + '*'):
                f.unlink()
            conv = run([sys.executable, str(HERE / 'mot_to_replay.py'), str(seq), str(prefix) + '.jsonl', '--format', 'visdrone',
                        '--rate', str(a.rate), '--lock-gid', str(gid), '--lock-frame', str(a.lock_frame),
                        '--drop-target', window, '--appearance', '--camera-motion', 'gt'])
            case = dict(sequence=seq.name, gid=gid, frames_present=n, span=[first, last], drop_window_s=window)
            for name, cfg in (('on', crowd), ('off', off)):
                out = a.workdir / f'{prefix.name}-{name}.out.jsonl'
                with out.open('w') as fh:
                    subprocess.run([str(a.replay), str(prefix) + '.jsonl', str(cfg)], stdout=fh, check=True)
                score = json.loads(run([sys.executable, str(HERE / 'score_lock_replay.py'), str(out), str(prefix) + '.truth.jsonl']).stdout)
                outage = next((o for o in score['outages'] if o['outage_ms'] >= a.drop_s * 1000 * 0.9), None)
                case[name] = dict(control_valid=score['control_valid_frames'], wrong_id=score['wrong_identity_frames'],
                                  correct=score['verdicts'].get('correct', 0),
                                  reacquired=bool(outage and outage['reacquired']),
                                  latency_ms=None if not outage or outage['latency_ms'] is None else round(outage['latency_ms']),
                                  wrong_bind=bool(outage and outage['wrong_identity']))
            cases.append(case)
            print(f"{seq.name} gid {gid:4d} n={n:4d} drop {window}: ON reacquired={case['on']['reacquired']} "
                  f"lat={case['on']['latency_ms']} ctrl={case['on']['control_valid']} wrong={case['on']['wrong_id']} | "
                  f"OFF ctrl={case['off']['control_valid']} wrong={case['off']['wrong_id']}")
    locked = [c for c in cases if c['off']['control_valid'] > 0]   # the click took (target confirmed at the lock frame)
    agg = dict(cases=len(cases), locked=len(locked), never_locked=[f"{c['sequence']}:{c['gid']}" for c in cases if c not in locked],
               reacquired=sum(c['on']['reacquired'] for c in locked),
               wrong_bind=sum(c['on']['wrong_bind'] for c in locked),
               latency_ms=sorted(c['on']['latency_ms'] for c in locked if c['on']['latency_ms'] is not None),
               control_valid_on=sum(c['on']['control_valid'] for c in locked), control_valid_off=sum(c['off']['control_valid'] for c in locked),
               wrong_id_on=sum(c['on']['wrong_id'] for c in locked), wrong_id_off=sum(c['off']['wrong_id'] for c in locked),
               wrong_id_added=sum(c['on']['wrong_id'] - c['off']['wrong_id'] for c in locked))
    a.out.write_text(json.dumps(dict(protocol=dict(rate=a.rate, drop_s=a.drop_s, lock_frame=a.lock_frame, appearance='idealized',
                                                   camera_motion='gt', crowd_flag=True), aggregate=agg, cases=cases), indent=1))
    print(json.dumps(agg))


if __name__ == '__main__':
    main()
