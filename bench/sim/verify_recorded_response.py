"""Recorded pixels are an open-loop heading-response test, never visual pursuit."""
import argparse
import json
import math
import pathlib
from mavros_evidence import json_lines


def verify(directory):
    rows=json_lines(directory/'ticks.jsonl')
    events=json_lines(directory/'mavros-events.jsonl')
    sources={r['source']['sequence']:r['source'] for r in rows if r['source']}
    moving=[r for r in events if r.get('kind')=='wire' and r['allowed'] and r['moving']]
    desired=[s['heading_response_ned'] for s in sources.values() if s.get('heading_response_ned') is not None]
    expired=[r for r in rows if r['source'] and r['t_ns']-r['source']['ingress_ns']>=200_000_000]
    followed=[r for r in rows if r['following'] and r['flight']=='Hover / offboard']
    checks=dict(final_disarmed=bool(rows) and not rows[-1]['armed'],
        no_translation=all(abs(r['setpoint']['vn'])<1e-6 and abs(r['setpoint']['ve'])<1e-6 for r in rows),
        no_wire_translation=all(abs(r['vn'])<1e-6 and abs(r['ve'])<1e-6 for r in moving),
        expired_source_holds=bool(expired) and all(r['setpoint']['hover'] for r in expired),
        target_selected=any(s['output']['lock']['id'] is not None for s in sources.values()),
        heading_response_requested=bool(desired),actual_mavros_motion=bool(moving),
        no_expired_motion=all(r['host_ns']<r['deadline_ns'] for r in moving),
        no_emergency_direct_land=not any(r.get('kind')=='emergency_direct_land' for r in events))
    return dict(scope='Real recorded aerial NV12 -> 15L HEF -> board ROS/MAVROS -> PX4 heading response; NOT closed-loop',
        passed=all(checks.values()),acceptance_scope='Minimum protocol response only; does NOT mean a usable demonstration',
        checks=checks,unique_inference_frames=len(sources),
        forwarded_motion_packets=len(moving),expired_source_ticks=len(expired),
        requested_heading_span_deg=math.degrees(max(desired)-min(desired)) if desired else None,
        actual_follow_heading_span_deg=math.degrees(max(r['yaw'] for r in followed)-min(r['yaw'] for r in followed)) if followed else None,
        limits=['Playback 20 FPS and HFOV 1.2 radians are declared assumptions for these runs',
                'One fixed initial click; no per-frame labels supplied',
                'Pixel recording does not respond to drone motion',
                'EOF is expected to hold, not recover'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path)
    a=p.parse_args();result=verify(a.directory)
    (a.directory/'replay-verified.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
