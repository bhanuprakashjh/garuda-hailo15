"""Separate host intention from actual motion forwarded after on-board MAVROS."""
import argparse
import collections
import json
import pathlib
from verify_gazebo_follow import summarize
from mavros_evidence import json_lines


def verify(directory):
    host=summarize(directory)
    rows=json_lines(directory/'mavros-events.jsonl')
    forwarded=[r for r in rows if r.get('kind')=='wire' and r['allowed'] and r['moving']]
    rejected=[r for r in rows if r.get('kind')=='wire' and not r['allowed'] and r['moving']]
    checks=dict(host_contract=host['checks_passed'],actual_mavros_motion=bool(forwarded),
        no_expired_motion=all(r['host_ns']<r['deadline_ns'] for r in forwarded),
        no_emergency_direct_land=not any(r.get('kind')=='emergency_direct_land' for r in rows))
    if any('origin_deadline_ns' in r for r in forwarded):
        checks['original_lease_not_renewed']=all(type(r.get('origin_deadline_ns')) is int and r['host_ns']<r['origin_deadline_ns'] for r in forwarded)
    return dict(passed=all(checks.values()),checks=checks,host=host,
        forwarded_motion_packets=len(forwarded),rejected_motion_packets=len(rejected),
        ros_reasons=dict(collections.Counter(r['reason'] for r in rows if r.get('kind')=='setpoint')),
        limits=['Wire packets are not independent inference observations',
                'Host non-hover ticks are not executed motion ticks',
                'No crowd identity or physical flight qualification'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path)
    a=p.parse_args();result=verify(a.directory)
    (a.directory/'mavros-verified.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
