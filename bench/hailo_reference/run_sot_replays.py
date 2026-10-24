"""Drive one VisDrone-SOT sequence through the tracker: convert, replay, score.

The lock is a click on the annotated target. A click only takes on a
confirmed live track, so the driver moves the click later in steps until
the tracker accepts it (a person would click again), and records the frame
it finally took on — or that no click ever took, with the detector's
confidence on the target as the explanation. Each accepted flavour
(single / five) is then replayed under three tracker configs: default,
`reacquire_appearance_crowd` on, re-acquire off.
"""
import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, **kw)


def convert(prepared, results, prefix, rate, lock_after, embeddings=None):
    for f in prefix.parent.glob(prefix.name + '*'):
        f.unlink()
    cmd = [sys.executable, str(HERE / 'sot_to_replay.py'), str(prepared), str(results), str(prefix),
           '--rate', str(rate), '--lock-after', str(lock_after)]
    if embeddings:
        cmd += ['--embeddings', str(embeddings)]
    out = run(cmd, cwd=str(HERE))
    return json.loads(out.stdout.strip().splitlines()[-1])


def lock_took(replay_output, lock_sequence):
    """The command response follows the frame it was issued after."""
    rows = [json.loads(l) for l in replay_output.read_text().splitlines() if l.strip()]
    for i, r in enumerate(rows):
        if r.get('v') == 2 and r.get('sequence') == lock_sequence and i+1 < len(rows) and 'ok' in rows[i+1]:
            return bool(rows[i+1]['ok'])
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay', type=pathlib.Path, help='garuda-track-replay binary')
    p.add_argument('prepared', type=pathlib.Path)
    p.add_argument('results', type=pathlib.Path, help='probe results dir for the sequence')
    p.add_argument('workdir', type=pathlib.Path, help='where replay inputs/outputs go')
    p.add_argument('--out', type=pathlib.Path, required=True, help='summary JSON')
    p.add_argument('--rate', type=float, default=30.0)
    p.add_argument('--lock-after', type=int, default=15)
    p.add_argument('--lock-step', type=int, default=15)
    p.add_argument('--lock-tries', type=int, default=40)
    p.add_argument('--config', action='append', default=[],
                   help='name=path of a tracker config override (repeatable); "default" always runs')
    p.add_argument('--embeddings', type=pathlib.Path, help='embed_visdrone_sot.py embeddings.jsonl to attach')
    p.add_argument('--flavours', default='single,five,roi', help='comma-separated subset to (re)run')
    p.add_argument('--lock-config', default='default',
                   help='config the click must be accepted under (e.g. identity: the clicked track needs a descriptor)')
    p.add_argument('--merge-summary', type=pathlib.Path,
                   help='existing summary JSON whose other flavours are kept when only a subset is re-run')
    a = p.parse_args()
    a.workdir.mkdir(parents=True, exist_ok=True)
    name = a.prepared.name
    configs = {'default': None}
    for spec in a.config:
        k, v = spec.split('=', 1)
        configs[k] = pathlib.Path(v)
    if a.lock_config not in configs:
        raise SystemExit(f'--lock-config {a.lock_config} is not one of {sorted(configs)}')
    summary = dict(sequence=name, rate=a.rate, embeddings=str(a.embeddings) if a.embeddings else None,
                   lock_config=a.lock_config, flavours={})
    if a.merge_summary and a.merge_summary.exists():
        summary['flavours'] = json.loads(a.merge_summary.read_text()).get('flavours', {})
    for flavour in a.flavours.split(','):
        # One conversion writes every flavour; each flavour keeps its own directory so the
        # click retry for one never deletes the other's accepted inputs and outputs.
        work = a.workdir / flavour
        work.mkdir(exist_ok=True)
        lock_after, conversion, accepted = a.lock_after, None, False
        for _ in range(a.lock_tries):
            conversion = convert(a.prepared, a.results, work / name, a.rate, lock_after, a.embeddings)
            if flavour not in conversion['detector_on_target']:
                conversion = None
                break   # this run has no ROI regions
            if flavour not in conversion['lock_frame']:
                break
            trial = work / f'{name}-{flavour}-locktrial.out.jsonl'
            lock_cfg = configs[a.lock_config]
            with trial.open('w') as fh:
                subprocess.run([str(a.replay), str(work / f'{name}-{flavour}.jsonl')] + ([str(lock_cfg)] if lock_cfg else []),
                               stdout=fh, check=True)
            if lock_took(trial, conversion['lock_frame'][flavour]):
                accepted = True
                break
            lock_after = conversion['lock_frame'][flavour] + a.lock_step
        if conversion is None:
            continue
        entry = dict(detector_on_target=conversion['detector_on_target'][flavour],
                     lock_frame=conversion['lock_frame'].get(flavour), lock_accepted=accepted, runs={})
        if accepted:
            lock_sequence = conversion['lock_frame'][flavour]
            for cname, cfg in configs.items():
                out = work / f'{name}-{flavour}-{cname}.out.jsonl'
                with out.open('w') as fh:
                    subprocess.run([str(a.replay), str(work / f'{name}-{flavour}.jsonl')] + ([str(cfg)] if cfg else []),
                                   stdout=fh, check=True)
                score = run([sys.executable, str(HERE / 'score_sot_replay.py'), str(out), str(work / f'{name}.truth.jsonl'),
                             '--lock-sequence', str(lock_sequence), '--out', str(work / f'{name}-{flavour}-{cname}.score.json')],
                            cwd=str(HERE))
                entry['runs'][cname] = json.loads(score.stdout)
        summary['flavours'][flavour] = entry
    a.out.write_text(json.dumps(summary, indent=2))
    for flavour, e in summary['flavours'].items():
        d = e['detector_on_target']
        print(f"{name} {flavour:6s} detector on target {d['detected']}/{d['frames']} conf median {d['conf_median']} "
              f">=0.5 in {d['frames_at_or_above_birth']} | lock frame {e['lock_frame']} accepted {e['lock_accepted']}")
        for cname, s in e['runs'].items():
            print(f"   {cname:7s} on-target {s['on_target_rate']} states {s['states']} | ctrl-valid {s['control_valid_frames']} "
                  f"off-target-while-valid {s['control_valid_off_target']} | losses {s['loss_episodes']} recovered {s['recovered_episodes']} "
                  f"longest {s['longest_loss_ms']:.0f} ms")


if __name__ == '__main__':
    main()
