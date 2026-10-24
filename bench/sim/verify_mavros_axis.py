"""Offline assertions over measured telemetry and post-MAVROS wire evidence."""
import argparse
import json
import math
import pathlib
from mavros_evidence import json_lines


def verify(directory):
    data=json.loads((directory/'axis.json').read_text())
    rows=data['rows'];events=data['events']
    wire=json_lines(directory/'mavros-events.jsonl')
    def nearest(t):return min(rows,key=lambda r:abs(r['elapsed']-t))
    def displacement(start,end):
        a,b=nearest(start),nearest(end)
        return [b['position'][i]-a['position'][i] for i in (0,1)]
    north=displacement(7,9.5);east=displacement(10,12.5)
    errors=[abs(math.degrees(math.atan2(math.sin(r['requested_yaw']-r['yaw']),
               math.cos(r['requested_yaw']-r['yaw'])))) for r in rows
               if 5<r['elapsed']<7 and r['requested_yaw'] is not None]
    moving=[r for r in wire if r.get('kind')=='wire' and r['allowed'] and r['moving']]
    checks=dict(yaw_within_2deg=bool(errors) and max(errors)<2,
                north_positive=len(rows)>0 and north[0]>.3 and abs(north[1])<.25,
                east_positive=east[1]>.3 and abs(east[0])<.25,
                actual_motion_packets=bool(moving),
                no_forwarded_expired_motion=all(r['host_ns']<r['deadline_ns'] for r in moving),
                final_disarmed=bool(rows) and not rows[-1]['armed'],
                no_emergency_fallback=not any(r.get('kind')=='emergency_direct_land' for r in wire))
    fault=next((e for e in events if e['event'].startswith('fault_')),None)
    response=None
    if fault:
        after=[r for r in rows if r['t_ns']/1e9>fault['t']+.1 and r['mode']!=6]
        response=after[0]['t_ns']/1e9-fault['t'] if after else None
        checks['offboard_exit_within_3s']=response is not None and response<3
        checks['no_motion_after_fault_100ms']=not any(r['host_ns']/1e9>fault['t']+.1 for r in moving)
    return dict(scope='Owned PX4 SITL, actual on-board ROS/MAVROS; explicit axis input, no perception claim',
                passed=all(checks.values()),checks=checks,north_displacement_ne_m=north,
                east_displacement_ne_m=east,settled_max_yaw_error_deg=max(errors) if errors else None,
                forwarded_motion_packets=len(moving),offboard_exit_after_fault_s=response)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path)
    a=p.parse_args();result=verify(a.directory)
    (a.directory/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
