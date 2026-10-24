"""Summarize recorded scheduling costs, not counterfactual speed or accuracy.

Metadata-only: does not validate image hashes or replace qualify_capture.py.
Groups same-frame measured costs by actual detector-pass count. The next source
interval is reported separately; it is not equated with processing latency.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics


def stats(values):
    return dict(count=len(values), median=statistics.median(values) if values else None,
                max=max(values) if values else None)


def analyze(records):
    if not records:
        raise ValueError('empty capture')
    groups = defaultdict(lambda: defaultdict(list))
    reasons, transitions = Counter(), []
    previous = None
    producer = None
    intervals = []
    for index, meta in enumerate(records):
        frame, output, diag = meta['frame'], meta['output'], meta['detection_tiles']
        seq, capture = frame['sequence'], frame['capture_ms']
        identity = tuple(meta[k] for k in ('recording_id', 'source_id', 'stream_id', 'clock_domain'))
        if (meta['sample_index'] != index or type(seq) is not int or seq < 1 or
            type(capture) not in (int, float) or not math.isfinite(capture) or capture < 0 or
            output['sequence'] != seq or output['capture_monotonic_ms'] != capture or
            diag['sequence'] != seq or (producer is not None and producer != identity)):
            raise ValueError('metadata correspondence mismatch')
        producer = identity
        passes = diag['detector_passes_this_frame']
        if type(passes) is not int or not 1 <= passes <= 16:
            raise ValueError('invalid detector pass count')
        group = groups[str(passes)]
        for name in ('processing_wall_ms', 'corner_wall_ms', 'capture_to_update_ms'):
            value = diag[name]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid stage timing')
            group[name].append(value)
        reasons[diag['schedule_reason']] += 1
        if previous is not None:
            prior_frame, prior_output, prior_diag = previous['frame'], previous['output'], previous['detection_tiles']
            if seq != prior_frame['sequence'] + 1 or capture <= prior_frame['capture_ms']:
                raise ValueError('requires contiguous increasing tracker updates')
            interval = capture - prior_frame['capture_ms']
            intervals.append(interval)
            groups[str(prior_diag['detector_passes_this_frame'])]['next_source_interval_ms'].append(interval)
            if prior_output['lock']['reason'] != 'observed' and passes >= 5:
                transitions.append(dict(sample_index=index, sequence=seq,
                                        previous_reason=prior_output['lock']['reason'],
                                        schedule_reason=diag['schedule_reason'],
                                        processing_wall_ms=diag['processing_wall_ms']))
        previous = meta
    return dict(scope='recorded metadata timing correlation only; no image-integrity, accuracy or candidate-speed claim',
                frames=len(records), source_elapsed_ms=records[-1]['frame']['capture_ms']-records[0]['frame']['capture_ms'],
                source_interval_ms=stats(intervals), schedule_reasons=dict(reasons),
                by_detector_passes={k: {name: stats(values) for name, values in g.items()} for k, g in groups.items()},
                broad_search_after_unobserved=transitions,
                tracking_accuracy_qualified=False, counterfactual_speed_measured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.capture.glob('[0-9][0-9][0-9][0-9][0-9][0-9].json'))
    payloads = [p.read_bytes() for p in paths]
    result = analyze([json.loads(p) for p in payloads])
    result['metadata_sha256'] = hashlib.sha256(b''.join(payloads)).hexdigest()
    result['capture'] = str(args.capture.resolve())
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
