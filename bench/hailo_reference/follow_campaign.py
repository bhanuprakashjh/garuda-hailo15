"""Reproducible bench campaign; no FC I/O, no training on evaluation clips.

Every schedule sees the same source sequence and initial point. Its measured
processing cost determines skipped frames; processed subsets are NOT identical.
Exact-pixel model parity is a separate experiment using retained DSP tensors.
"""
import argparse
import collections
import json
import pathlib
import subprocess
import sys

from run_causal_replay import ROOT, sha
from score_4k_tiles import iou


def diagnose(rows, manifest):
    truth = {t['index']: t['box'] for t in manifest['targets']}
    reasons = collections.Counter()
    detected = fresh = off = 0
    times = collections.defaultdict(list)
    for row in rows:
        x, y, w, h = truth[row['source_index']]
        expected = [x/1280, y/720, (x+w)/1280, (y+h)/720]
        detected += any(iou([d['x'],d['y'],d['x']+d['w'],d['y']+d['h']],expected)>=.5
                        for d in row.get('raw_detections', []))
        lock = row['output']['lock']
        reasons[lock.get('reason', 'unknown')] += 1
        b = lock.get('box')
        overlap = iou([b['x']/1280,b['y']/720,(b['x']+b['w'])/1280,(b['y']+b['h'])/720],expected) if b else 0
        eligible = lock.get('control_valid', False) and row['age_ms'] < 200
        fresh += eligible and overlap >= .5
        off += eligible and overlap < .5
        for name, value in row.get('stage_ms', {}).items():
            times[name].append(value)
    return dict(processed=len(rows), raw_target_overlap_hits=detected,
                fresh_on_target_processed=fresh, fresh_off_target_processed=off,
                rejection_reasons=dict(reasons),
                stage_median_ms={k:sorted(v)[len(v)//2] for k,v in times.items()},
                scope='Overlap, not identity certification; includes acquisition; raw hit is class-agnostic diagnostic.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-root', type=pathlib.Path, required=True)
    p.add_argument('--binary', type=pathlib.Path, required=True)
    p.add_argument('--out', type=pathlib.Path, required=True)
    p.add_argument('--frames', type=int, default=240)
    p.add_argument('--modes', nargs='+', choices=['fullview','fullview_roi','adaptive'], default=['fullview','fullview_roi','adaptive'])
    p.add_argument('--sequences', nargs='+', default=['uav0000086_00870_s','uav0000024_00000_s','uav0000115_00606_s'])
    p.add_argument('--select-retry-ms', type=float, default=0., help='passed to run_causal_replay; 0 keeps the frozen one-click protocol')
    p.add_argument('--fixed-stride', type=int, default=0, help='passed to run_causal_replay; 0 keeps timing-driven scheduling')
    p.add_argument('--select-retry-any', action='store_true', help='passed to run_causal_replay')
    p.add_argument('--defer-person-embeddings-on-car', action='store_true',
                   help='labelled opt-in scheduling ablation; live profiles are not modified')
    p.add_argument('--car-recovery-detection-veto', action='store_true',
                   help='labelled opt-in recovery evidence ablation; never changes live profiles')
    p.add_argument('--base-profile', type=pathlib.Path, default=ROOT/'hosts/hailo15l/fresh/perception-follow.json',
                   help='node profile the per-mode configs derive from; a candidate HEF trial passes a copy of the '
                        'follow profile whose hef/target_roi_hef point at the candidate already staged on the board')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    profile = json.loads(a.base_profile.read_text())
    if a.defer_person_embeddings_on_car:
        profile['defer_person_embeddings_on_car'] = True
    if a.car_recovery_detection_veto:
        profile['tracking']['car_recovery_detection_veto'] = True
    (a.out/'base-profile.json').write_text(json.dumps(dict(profile,base_profile=str(a.base_profile),
                                                              base_profile_sha256=sha(a.base_profile)),indent=2))
    results = []
    for sequence in a.sequences:
        for mode in a.modes:
            config = a.out/(mode+'.json')
            config.write_text(json.dumps(dict(profile,bench_schedule=mode),indent=2))
            directory = a.out/(sequence+'-'+mode)
            command = [sys.executable,str(ROOT/'bench/hailo_reference/run_causal_replay.py'),
                       str(a.prepared_root/sequence),'--binary',str(a.binary),'--profile',str(config),
                       '--out',str(directory),'--frames',str(a.frames),'--select-retry-ms',str(a.select_retry_ms),
                       '--fixed-stride',str(a.fixed_stride)]+(['--select-retry-any'] if a.select_retry_any else [])
            with (a.out/(sequence+'-'+mode+'.log')).open('x') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            rows=[]
            for line in (directory/'outputs.jsonl').read_text().splitlines():
                try: row=json.loads(line)
                except ValueError: continue
                if isinstance(row,dict) and 'source_index' in row: rows.append(row)
            manifest=json.loads((a.prepared_root/sequence/'manifest.json').read_text())
            result=dict(sequence=sequence,mode=mode,source_sha256=manifest['source_sha256'],
                        score=json.loads((directory/'score.json').read_text()),diagnostic=diagnose(rows,manifest))
            results.append(result)
            (a.out/'summary.json').write_text(json.dumps(dict(binary_sha256=sha(a.binary),results=results),indent=2))
            print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
