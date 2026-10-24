#!/usr/bin/env python3
"""Independent log checks, not a certificate of detection accuracy or real flight."""
import argparse
from collections import Counter
import hashlib
import gzip
import json
import math
import pathlib
import statistics


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round((len(ordered)-1)*fraction)] if ordered else None


def summarize(directory):
    ticks_path = directory/'ticks.jsonl'
    if not ticks_path.exists():
        ticks_path = directory/'ticks.jsonl.gz'
    raw = gzip.decompress(ticks_path.read_bytes()) if ticks_path.suffix == '.gz' else ticks_path.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    events_path = directory/'events.jsonl'
    if events_path.exists():event_bytes=events_path.read_bytes()
    elif events_path.with_suffix('.jsonl.gz').exists():event_bytes=gzip.decompress(events_path.with_suffix('.jsonl.gz').read_bytes())
    else:event_bytes=None
    events = ([json.loads(line) for line in event_bytes.splitlines()] if event_bytes is not None
              else json.loads((directory/'events.json').read_text()))
    failures = []
    source = {r['source']['sequence']: r['source'] for r in rows if r['source']}
    moving = [r for r in rows if any(abs(r['setpoint'][k]) > 1e-6 for k in ('vn', 've', 'yaw_rate'))]
    follow = [r for r in rows if r['following'] and r['flight'] == 'Hover / offboard']
    for r in (row for row in rows if not row['setpoint']['hover']):
        s, intent, sp = r['source'], r['intent'], r['setpoint']
        if not r['following'] or not s or not s['output']['lock']['control_valid']:
            failures.append('motion_without_verified_selected_target')
            continue
        if not intent or not intent['command_eligible'] or not intent['t_ns'] <= r['t_ns'] < intent['t_ns']+intent['ttl_ns']:
            failures.append('expired_or_ineligible_command')
        if intent and any(intent[key] != s['output'][key] for key in ('source_id', 'stream_id', 'sequence')):
            failures.append('command_source_mismatch')
        if not 0 <= r['t_ns']-s['ingress_ns'] < 200_000_000:
            failures.append('stale_motion')
        if math.hypot(sp['vn'], sp['ve']) > 1.001 or abs(sp['yaw_rate']) > .8:
            failures.append('command_limit_exceeded')
        if math.hypot(sp['vn'], sp['ve']) > 1e-6 and (not s['depth_paired'] or s['range_m'] is None):
            failures.append('translation_without_paired_depth')
    stalls = [e['monotonic_ns'] for e in events if e['kind'] == 'operator' and e['detail'] == 'video_stall']
    stall_checks = []
    for event in stalls:
        window = [r for r in rows if event+250_000_000 <= r['t_ns'] <= event+1_800_000_000]
        held = bool(window) and all(r['setpoint']['hover'] for r in window)
        recovered = any(not r['setpoint']['hover'] for r in rows if event+2_500_000_000 < r['t_ns'] < event+12_000_000_000)
        stall_checks.append(dict(t_ns=event, evaluated_ticks=len(window), held=held, recovered=recovered))
        if not held:
            failures.append('video_stall_did_not_hold')
        if not recovered:
            failures.append('video_stall_did_not_recover')
    if not rows or rows[-1]['armed']:
        failures.append('final_disarm_not_observed')
    if not moving:
        failures.append('no_visual_follow_motion_observed')
    if not stalls:
        failures.append('stall_scenario_not_executed')
    positions = [r['position_ned'] for r in follow]
    displacement = max((math.hypot(p[0]-positions[0][0], p[1]-positions[0][1]) for p in positions), default=0.)
    intervals = [(b['t_ns']-a['t_ns'])/1e6 for a, b in zip(rows, rows[1:])]
    def dist(values):
        return dict(median=statistics.median(values) if values else None, p95=percentile(values, .95))
    report = dict(scope='Real Gazebo pixels / Hailo YOLO11 + OSNet / PX4 visual SIL; no ground-truth identity audit',
        ticks=len(rows), unique_inference_frames=len(source), motion_ticks=len(moving),
        follow_ticks=len(follow), follow_nonhover_ticks=sum(not r['setpoint']['hover'] for r in follow),
        ingress_result_ms=dist([s['roundtrip_ms'] for s in source.values()]),
        inference_ms=dist([s['age_ms'] for s in source.values()]),
        control_tick_ms=dist(intervals), rtf=dist([r['rtf'] for r in rows if r['rtf'] is not None]),
        max_follow_displacement_m=displacement,
        selected_states=dict(Counter(s['output']['lock']['state'] for s in source.values())),
        paired_depth_frames=sum(s['depth_paired'] for s in source.values()),
        video_stall=stall_checks, final_disarmed=bool(rows) and not rows[-1]['armed'],
        failures=dict(Counter(failures)), checks_passed=not failures,
        ticks_sha256=hashlib.sha256(raw).hexdigest(),
        limits=['PC-ingress freshness, not certified exposure age',
                'No independent wrong-identity ground truth', 'No outdoor or physical-flight validation',
                'Simple single-person scene; no crossing/occlusion qualification'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    args = parser.parse_args()
    result = summarize(args.directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['checks_passed'] else 1)
