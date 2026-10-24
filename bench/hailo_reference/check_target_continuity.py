"""Fail a recorded replay with control-valid zero-overlap target boxes.

Evaluation only: truth never enters tracking. This gate is necessary, not
sufficient: it rejects catastrophic localization and vacuous never-acquired
runs, but does not certify identity, recovery, or latency performance.
"""
import argparse
import json
import math
from pathlib import Path
from score_4k_tiles import iou


def check(rows, manifest, select_frame):
    truth = {t['index']: t['box'] for t in manifest['targets']}
    correct = 0
    violations = []
    previous = -1
    for row in rows:
        index = row['source_index']
        if type(index) is not int or index <= previous or index not in truth:
            raise ValueError('invalid, reordered, or unlabelled source frame')
        previous = index
        if index < select_frame:
            continue
        lock = row['output']['lock']
        if type(lock.get('control_valid')) is not bool:
            raise ValueError('invalid control validity flag')
        if not lock['control_valid']:
            continue
        box = lock.get('box')
        if not box:
            raise ValueError('control-valid output has no box')
        x,y,w,h = truth[index]
        values=[box[k] for k in ('x','y','w','h')]+[x,y,w,h]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
            raise ValueError('nonfinite or invalid geometry')
        if box['w'] <= 0 or box['h'] <= 0:
            raise ValueError('invalid output geometry')
        if w <= 0 or h <= 0:
            raise ValueError('control-valid frame has unscorable truth')
        overlap = iou([box['x'],box['y'],box['x']+box['w'],box['y']+box['h']],
                      [x,y,x+w,y+h])
        correct += overlap >= .5
        if overlap == 0:
            violations.append(dict(source_index=index, track_id=lock.get('track_id'),
                                   reason=lock.get('reason'), box=box, truth=[x,y,w,h]))
    return dict(passed=correct>0 and not violations,
                valid_on_target_frames=correct, zero_overlap_control_frames=len(violations),
                violations=violations, no_demonstrated_target_tracking=correct==0,
                scope='Recorded control-valid geometry versus SOT truth; no vehicle commands or identity certification')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    args=parser.parse_args()
    run=json.loads((args.run_directory/'run.json').read_text())
    if run.get('returncode') != 0:
        raise ValueError('replay did not complete successfully')
    manifest=json.loads((Path(run['prepared'])/'manifest.json').read_text())
    if manifest['source_sha256'] != run['source_sha256']:
        raise ValueError('source manifest does not match replay')
    rows=[]
    for line in (args.run_directory/'outputs.jsonl').read_text().splitlines():
        # Hailo initialization text is allowed, malformed JSON evidence is not.
        if not line.lstrip().startswith('{'):
            continue
        row=json.loads(line)
        if 'source_index' in row:
            rows.append(row)
    if not rows:
        raise ValueError('no replay frames')
    result=check(rows,manifest,run['trial']['select_frame'])
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
