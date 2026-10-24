"""Simulator-only ROS/MAVROS wire/sign/30-degree and link-loss qualification.

Explicit axis-test mode bypasses perception, never flight safety/ownership.
Separate from visual follow evidence. No real FC endpoint accepted.
"""
import argparse
import json
import math
import os
import pathlib
import signal
import time
from gazebo_follow import launch, bridge
from remote_mavros import RemoteMavrosVehicle
from mavros_evidence import snapshot


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--px4',default='/media/bhanu1234/Development/PX4-Autopilot')
    p.add_argument('--fault',choices=('none','requests','ros'),default='none')
    a=p.parse_args()
    if os.environ.get('GARUDA_SIM')!='1':raise PermissionError('simulation only')
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'versions.json').write_text(json.dumps(snapshot(pathlib.Path(__file__).resolve().parents[2]),indent=2)+'\n')
    os.environ['GARUDA_PX4_BUILD']=str(pathlib.Path(a.px4)/'build/px4_sitl_default')
    os.environ['GZ_PARTITION']='garuda-mavros-axis-'+str(os.getpid())
    proc=gz=vehicle=None;logs=[];rows=[];events=[]
    started=time.monotonic();prime=ready=reference=fault_at=land_at=None
    armed_once=False;heartbeat=0.;next_tick=started
    try:
        proc,gz,logs=launch(a,dict(os.environ),a.out)
        vehicle=RemoteMavrosVehicle(sim_pid=proc.pid,directory=a.out,axis_test=True)
        while time.monotonic()-started<150:
            now=time.monotonic()
            if now<next_tick:vehicle.poll();time.sleep(min(.005,next_tick-now));continue
            next_tick=max(next_tick+.05,now)
            vehicle.poll()
            if now-heartbeat>1:
                vehicle._verify_simulator()
                vehicle.m.mav.heartbeat_send(vehicle.mavutil.mavlink.MAV_TYPE_GCS,
                    vehicle.mavutil.mavlink.MAV_AUTOPILOT_INVALID,0,0,vehicle.mavutil.mavlink.MAV_STATE_ACTIVE)
                heartbeat=now
            if vehicle.offset is None or vehicle.pos is None:continue
            if prime is None:prime=now
            if not armed_once and vehicle.ready_to_arm and b'Ready for takeoff!' in (a.out/'px4.log').read_bytes():
                vehicle.arm();vehicle.set_offboard();armed_once=True
                events.append(dict(event='arm_offboard_requested',t=now))
            if armed_once and ready is None and vehicle.armed and vehicle.mode==6 and abs(vehicle.pos[2]+2)<.25:
                ready=now;reference=vehicle.yaw
                events.append(dict(event='hover_confirmed',t=now,reference_yaw=reference))
            elapsed=now-ready if ready is not None else 0.
            yaw=0.;vn=ve=0.
            if ready is not None:
                target=reference+math.pi/6
                error=math.atan2(math.sin(target-vehicle.yaw),math.cos(target-vehicle.yaw))
                yaw=max(-.5,min(.5,error*2))
                if 7<=elapsed<9:vn=.4
                if 10<=elapsed<12:ve=.4
                if a.fault!='none' and elapsed>=14 and fault_at is None:
                    fault_at=now;events.append(dict(event='fault_'+a.fault,t=now))
                    if a.fault=='ros':vehicle.child.terminate()
                if a.fault=='none' and elapsed>=16 and land_at is None:
                    vehicle.land();land_at=now;events.append(dict(event='land_requested',t=now))
            if fault_at is None and land_at is None:
                vehicle.send_setpoint(bridge.Setpoint(vn,ve,-2.,yaw,False),int((now-started)*1000))
            rows.append(dict(t_ns=time.monotonic_ns(),elapsed=elapsed,armed=vehicle.armed,mode=vehicle.mode,
                position=list(vehicle.pos),yaw=vehicle.yaw,requested_yaw=reference+math.pi/6 if reference is not None else None,
                fault=fault_at is not None))
            if (fault_at is not None or land_at is not None) and not vehicle.armed:
                events.append(dict(event='disarm_observed',t=now));break
            if ready is None and now-started>60:raise TimeoutError('MAVROS takeoff not achieved')
        if not rows or rows[-1]['armed']:raise TimeoutError('disarm not observed')
    finally:
        if vehicle:
            if vehicle.armed:
                vehicle.emergency_land()
                until=time.monotonic()+20
                while vehicle.armed and time.monotonic()<until:time.sleep(.1);vehicle.poll()
                events.append(dict(event='emergency_cleanup',armed=vehicle.armed))
            vehicle.close()
        for child in (proc,gz):
            if child and child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except Exception:os.killpg(child.pid,signal.SIGKILL);child.wait()
        for f in logs:f.close()
        (a.out/'axis.json').write_text(json.dumps(dict(scope='Explicit axis test, no perception',fault=a.fault,rows=rows,events=events),indent=2))
    settled=[r for r in rows if 5<r['elapsed']<7 and r['requested_yaw'] is not None]
    maximum=max((abs(math.degrees(math.atan2(math.sin(r['requested_yaw']-r['yaw']),math.cos(r['requested_yaw']-r['yaw'])))) for r in settled),default=None)
    success=maximum is not None and maximum<2 and not rows[-1]['armed'] and not any(e['event']=='emergency_cleanup' for e in events)
    report=dict(scope='30 degree ROS/MAVROS simulator response; not detector or physical FC validation',
        settled_max_error_deg=maximum,final_disarmed=not rows[-1]['armed'],passed=success,events=events)
    (a.out/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not success:raise SystemExit(1)


if __name__=='__main__':main()
