"""Paired fixed-frame replay regression, not identity or flight certification.

Truth is consumed only by this offline scorer. Same-class detector evidence is
kept separate from raw overlap so a wrong-class box cannot excuse tracking loss.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics

from run_causal_replay import sha
from score_4k_tiles import iou


def xyxy(box):
    if len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box):
        raise ValueError('invalid geometry')
    x, y, w, h = box
    if w <= 0 or h <= 0:
        raise ValueError('unscorable geometry')
    return [x, y, x + w, y + h]


def evaluate(rows, manifest, select_frame, label, control_confidence):
    width, height = manifest['canvas']
    if any(type(v) is not int or v <= 0 for v in (width, height)):
        raise ValueError('invalid canvas')
    if (not label or type(control_confidence) not in (int, float) or
            not math.isfinite(control_confidence) or not 0 <= control_confidence <= 1):
        raise ValueError('invalid target class or control floor')
    truth = {}
    for target in manifest['targets']:
        index = target['index']
        if type(index) is not int or index < 0 or index in truth:
            raise ValueError('invalid or duplicate truth index')
        truth[index] = xyxy(target['box'])
    result = {}
    previous = -1
    for row in rows:
        index = row['source_index']
        if type(index) is not int or index <= previous or index not in truth:
            raise ValueError('invalid, reordered or unlabelled source index')
        previous = index
        if index < select_frame:
            continue
        lock = row['output']['lock']
        valid = lock['control_valid']
        if type(valid) is not bool:
            raise ValueError('invalid control validity')
        overlap = 0.
        if valid:
            overlap = iou(xyxy([lock['box'][k] for k in ('x', 'y', 'w', 'h')]), truth[index])
        on = valid and overlap >= .5
        best_any = best_class = best_usable = 0.
        for detection in row['raw_detections']:
            conf = detection['confidence']
            if type(conf) not in (int, float) or not math.isfinite(conf) or not 0 <= conf <= 1:
                raise ValueError('invalid detection confidence')
            normalized = xyxy([detection[k] for k in ('x', 'y', 'w', 'h')])
            hit = iou([v * scale for v, scale in zip(normalized, (width, height, width, height))], truth[index])
            best_any = max(best_any, hit)
            if detection['label'] == label:
                best_class = max(best_class, hit)
                if conf >= control_confidence:
                    best_usable = max(best_usable, hit)
        if on:
            category = 'on_target'
        elif valid:
            category = 'valid_off_target_with_usable_detection' if best_usable >= .5 else 'valid_off_target_without_usable_detection'
        elif best_usable >= .5:
            category = 'refused_despite_usable_detection'
        elif best_class >= .5:
            category = 'same_class_detection_below_control_floor'
        elif best_any >= .5:
            category = 'only_wrong_class_overlap'
        else:
            category = 'no_raw_box_at_iou_0_5'
        age = row['age_ms']
        if type(age) not in (int, float) or not math.isfinite(age) or age < 0:
            raise ValueError('invalid measured age')
        result[index] = dict(on_target=on, off_target=valid and not on,
                             zero_overlap=valid and overlap == 0, iou=overlap,
                             age_ms=age,
                             timely_on_target=on and age < 200, reason=lock['reason'],
                             category=category, best_class_iou=best_class,
                             best_usable_iou=best_usable)
    if not result:
        raise ValueError('empty evaluation interval')
    return result


def compare(baseline, candidate):
    if baseline.keys() != candidate.keys():
        raise ValueError('processed frame sets differ; not a paired fixed-input comparison')
    def counts(rows):
        return dict(frames=len(rows), **{key: sum(r[key] for r in rows.values()) for key in
                    ('on_target', 'off_target', 'zero_overlap', 'timely_on_target')},
                    processing_plus_assumed_age_ms_median=statistics.median(r['age_ms'] for r in rows.values()),
                    categories=dict(Counter(r['category'] for r in rows.values())))
    a, b = counts(baseline), counts(candidate)
    gained = [i for i in baseline if candidate[i]['on_target'] and not baseline[i]['on_target']]
    lost = [i for i in baseline if baseline[i]['on_target'] and not candidate[i]['on_target']]
    introduced_bad = [i for i in baseline if candidate[i]['off_target'] and not baseline[i]['off_target']]
    # A conservative improvement screen, deliberately stronger than the earlier
    # zero-overlap-only check. Never-acquired and fewer-but-less-useful outputs
    # cannot pass. This does not authorize deployment.
    nonregression = (b['on_target'] >= a['on_target'] and b['on_target'] > 0 and b['zero_overlap'] == 0 and
              b['off_target'] <= a['off_target'] and
              b['timely_on_target'] >= a['timely_on_target'] and not lost and not introduced_bad)
    passed = nonregression and b['on_target'] > a['on_target']
    return dict(paired_frames=len(baseline), baseline=a, candidate=b,
                gained_on_target_indices=gained, lost_on_target_indices=lost,
                introduced_off_target_indices=introduced_bad,
                quality_nonregression_screen_passed=nonregression,
                conservative_improvement_screen_passed=passed,
                deployment_qualified=False,
                scope='SOT overlap and declared-age replay regression; not persistent identity or live latency')


def load(directory, label):
    run = json.loads((directory / 'run.json').read_text())
    if run.get('returncode') != 0 or not run.get('profile_unchanged'):
        raise ValueError('incomplete replay or changed live profile')
    if run.get('was_running') and run.get('restore_returncode') != 0:
        raise ValueError('live restoration failed')
    if run['trial'].get('fixed_stride', 0) <= 0:
        raise ValueError('requires labelled fixed-stride replay')
    manifest_path = Path(run['prepared']) / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    run['evaluation_manifest_sha256'] = sha(manifest_path)
    if run['source_sha256'] != manifest['source_sha256']:
        raise ValueError('source manifest mismatch')
    profile = json.loads((directory / 'profile.json').read_text())
    if sha(directory / 'profile.json') != run['profile_sha256']:
        raise ValueError('profile checksum mismatch')
    rows = []
    for line in (directory / 'outputs.jsonl').read_text().splitlines():
        if not line.lstrip().startswith('{'):
            continue  # preserve/ignore Hailo startup text, not malformed JSON
        row = json.loads(line)
        if 'source_index' in row:
            rows.append(row)
    expected = list(range(0, run['trial']['frames'], run['trial']['fixed_stride']))
    if [row['source_index'] for row in rows] != expected:
        raise ValueError('incomplete or reordered fixed-stride output')
    return run, evaluate(rows, manifest, run['trial']['select_frame'], label,
                         profile['tracking'].get('control_confidence', .4))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--label', required=True, help='annotated target class, explicitly supplied by evaluator')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    a, baseline = load(args.baseline, args.label)
    b, candidate = load(args.candidate, args.label)
    if (a['source_sha256'] != b['source_sha256'] or a['trial'] != b['trial'] or
            a['evaluation_manifest_sha256'] != b['evaluation_manifest_sha256']):
        raise ValueError('source or trial protocol differs')
    result = compare(baseline, candidate)
    result['provenance'] = {name: dict(directory=str(path), binary_sha256=run['binary_sha256'],
        profile_sha256=run['profile_sha256'], output_sha256=sha(path / 'outputs.jsonl'))
        for name, path, run in [('baseline', args.baseline, a), ('candidate', args.candidate, b)]}
    result['source_sha256'] = a['source_sha256']
    result['evaluation_manifest_sha256'] = a['evaluation_manifest_sha256']
    result['scorer_sha256'] = sha(Path(__file__))
    result['detection_evidence_scope'] = 'Usable means same class, IoU>=0.5 and control confidence floor; not proof of identity/association eligibility'
    result['per_frame'] = [dict(index=i, baseline=baseline[i], candidate=candidate[i]) for i in baseline]
    if args.output:
        with args.output.open('x') as output:
            json.dump(result, output, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'per_frame'}, indent=2))
    return 0 if result['conservative_improvement_screen_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
