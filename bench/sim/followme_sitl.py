#!/usr/bin/env python3
"""Sim-in-the-loop follow-me: PX4 SITL (SIH quad, headless) <- MAVLink offboard
<- FollowAuthority <- FreshFollow <- native tracker (synthetic detections), or
desk-board camera envelopes in yaw-only transport-in-loop mode.

SAFETY GATE: refuses without GARUDA_SIM=1 (the bridge enforces it too) and
only talks UDP to a local PX4 SITL. Nothing here reaches hardware.

Scenarios (each a fresh PX4 instance, `--duration` seconds after takeoff):
  nominal          follow a target walking an arc at 0.8 m/s
  target_loss      the target is not observed for 3 s (occlusion) at t=15 s
  video_stall      no perception frames at all for 2 s at t=15 s (TTL expiry)
  abort            operator abort at t=15 s, resume at t=20 s
  publish_failure  setpoint publishing fails from t=15 s: breaker -> LAND
  link_loss        stop all setpoints at t=15 s; observe PX4 failsafe WITHOUT LAND
Outputs one JSON per scenario with the tick log and a summary, plus the PX4
console log excerpt. Numbers are simulation results, not vehicle measurements.
"""
import argparse
import json
import math
import os
import pathlib
import random
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "garuda-follow"))
sys.path.insert(0, str(ROOT / "services" / "garuda-bridge"))
sys.path.insert(0, str(ROOT / "interfaces"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from follow_authority import AuthorityConfig, FollowAuthority          # noqa: E402
from follow_controller import FollowConfig, compute                    # noqa: E402
from projection import project                                         # noqa: E402
from garuda_interfaces import Track                                    # noqa: E402
import sim_offboard_bridge as bridge                                   # noqa: E402
from perception_sources import NativeTrackerSource, BoardSource

PX4_BUILD = pathlib.Path(os.environ.get("GARUDA_PX4_BUILD", "/media/bhanu1234/Development/PX4-Autopilot/build/px4_sitl_default"))
RATE_HZ = 20.0
HOLD_Z = -3.0            # NED: 3 m above the origin
HFOV = 1.2
TARGET_SIZE = 6.0        # projection's size proxy (see sim_kinematics.target_bbox)
SCENARIOS = ("nominal", "target_loss", "video_stall", "abort", "publish_failure", "link_loss")


def launch_px4(log_path):
    rootfs = PX4_BUILD / "rootfs"
    env = dict(os.environ, PX4_SIM_MODEL="sihsim_quadx", HEADLESS="1")
    log = open(log_path, "wb")
    proc = subprocess.Popen(["../bin/px4", "-d", "-s", "etc/init.d-posix/rcS"], cwd=str(rootfs), env=env,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if b"Ready for takeoff" in pathlib.Path(log_path).read_bytes():
            return proc, log
        if proc.poll() is not None:
            break
    proc.kill(); log.close()
    raise RuntimeError("PX4 SITL did not report ready")


def target_world(t):
    """Scripted walk: north at 0.8 m/s along a gentle arc, starting 6 m ahead."""
    return 6.0 + 0.8 * t, 2.0 + 2.0 * math.sin(0.2 * t)


def perceive(vehicle, target, rng_noise, scenario, t):
    """Synthetic tracker view + controller command from the drone pose and the world target."""
    n, e, d = vehicle.pos
    bbox = project(target, (n, e), vehicle.yaw, hfov=HFOV, target_size=TARGET_SIZE)
    if scenario == "target_loss" and 15.0 <= t < 18.0:
        bbox = None
    if bbox is not None:
        x, y, w, h = bbox
        x += rng_noise.gauss(0, 0.005); h = max(0.02, h + rng_noise.gauss(0, 0.003))
        bbox = (x, y, w, h)
    if bbox is None:
        view = dict(state="occluded", reason="selected_identity_not_observed", lock_id=1, epoch=1,
                    control_valid=False, observation_valid=False)
        return view, None, None
    view = dict(state="tracking", reason="identity_verified", lock_id=1, epoch=1, control_valid=True, observation_valid=True)
    track = Track(id=1, class_id=0, label="person", bbox=bbox, confidence=0.9, hits=10, age=10, time_since_update=0)
    return view, track, bbox


def run_scenario(scenario, duration, out_dir, execution, seed=1, perception="synthetic", tracker_binary=None,
                 board_url="http://10.0.0.1:8099/api/state"):
    if execution == "preview":
        return run_preview(scenario,duration,out_dir,seed)
    if execution != "live" or os.environ.get("GARUDA_SIM") != "1":
        raise PermissionError("live execution requires GARUDA_SIM=1")
    out_dir.mkdir(parents=True, exist_ok=True)
    px4_log = out_dir / f"{scenario}-px4.log"
    if px4_log.exists() or (out_dir/f"{scenario}.json").exists():
        raise FileExistsError("use a fresh output directory; existing SIL evidence is preserved")
    proc, log = launch_px4(px4_log)
    rows, summary = [], dict(scenario=scenario, execution=execution, rate_hz=RATE_HZ, hold_z_ned=HOLD_Z)
    source=None
    summary['perception']=perception
    summary['scope']={'synthetic':'synthetic projected observations',
        'tracker':'real native Tracker and FreshFollow; synthetic detections/appearance',
        'board':'real camera envelopes, yaw-only transport-in-loop; not rendered visual closed-loop'}[perception]
    try:
        vehicle = bridge.MavlinkVehicle("udpin:127.0.0.1:14540",sim_pid=proc.pid)
        cfg = FollowConfig(desired_height_frac=0.15, forward_gain=20.0, yaw_gain=2.0, max_forward_vel=2.0, max_yaw_rate=0.8,
                           min_height_frac=0.02)
        if perception=="tracker":source=NativeTrackerSource(tracker_binary,cfg)
        elif perception=="board":source=BoardSource(board_url,cfg)
        authority = FollowAuthority(AuthorityConfig(coast_time_ms=1500, reacquire_time_ms=4000, execution=execution))
        discipline = bridge.OffboardDiscipline(prime_s=2.0, breaker_failures=5)
        rng_noise = random.Random(seed)
        t_start = time.monotonic()
        phase, follow_t0, boot0 = "takeoff", None, time.monotonic()
        intent, next_tick = None, time.monotonic()
        aborted_at = resumed_at = None
        while True:
            now = time.monotonic()
            if now < next_tick:
                time.sleep(min(0.005, next_tick - now)); continue
            next_tick += 1.0 / RATE_HZ
            now_ns = int(now * 1e9)
            vehicle.poll()
            if vehicle.pos is None:
                if now-t_start>30:raise TimeoutError("no position telemetry")
                continue
            state = discipline.tick(now_ns)
            if state == "ENGAGE":
                vehicle.arm(); vehicle.set_offboard(); discipline.engaged()
            n, e, d = vehicle.pos
            t = now - t_start
            if phase == "takeoff":
                if t>30:raise TimeoutError("simulator did not confirm takeoff")
                sp = bridge.Setpoint(0.0, 0.0, HOLD_Z, 0.0, True)
                if vehicle.armed and vehicle.mode==bridge.PX4_MAIN_MODE_OFFBOARD and abs(d - HOLD_Z) < 0.4 and t > 4.0:
                    phase, follow_t0 = "follow", now
                    summary["takeoff_s"] = round(t, 2)
                target = None; view = None; bbox = None
            else:
                ft = now - follow_t0
                target = target_world(ft) if perception!="board" else None
                if scenario == "abort" and ft >= 15.0 and aborted_at is None:
                    authority.abort(now_ns); aborted_at = ft
                if scenario == "abort" and ft >= 20.0 and resumed_at is None:
                    authority.resume(now_ns); resumed_at = ft
                stalled = scenario == "video_stall" and 15.0 <= ft < 17.0
                if not stalled:
                    if perception!="board":
                        view, track, bbox = perceive(vehicle, target, rng_noise, scenario, ft)
                    else:view=track=bbox=None
                    if perception=="tracker":source.update(bbox,now_ns)
                    elif perception=="synthetic":
                        cmd = compute(track, (1, 1), cfg, t_ns=now_ns) if track is not None else None
                        intent = authority.update(view, cmd, now_ns)
                if source:
                    intent=source.tick(now_ns)
                    if source.pipeline:authority=source.pipeline.authority
                    now_ns=time.monotonic_ns()
                sp = bridge.setpoint_from_intent(intent, vehicle.yaw, HOLD_Z, now_ns)
                if ft >= duration:
                    break
            ok = True
            if execution == "live":
                try:
                    if scenario == "publish_failure" and phase == "follow" and (now - follow_t0) >= 15.0:
                        raise OSError("simulated publish failure")
                    if not (scenario=="link_loss" and phase=="follow" and now-follow_t0>=15):
                        vehicle.send_setpoint(sp, int((now - boot0) * 1000))
                except OSError:
                    ok = False
            if discipline.publish_result(ok) == "LANDING":
                summary["breaker_tripped_at_s"] = round(now - follow_t0, 2) if follow_t0 else None
                vehicle.land()
                break
            dist = math.hypot(target[0] - n, target[1] - e) if target else None
            rows.append(dict(t=round(t, 3), phase=phase, n=round(n, 3), e=round(e, 3), d=round(d, 3), yaw=round(vehicle.yaw, 4),
                             target=None if target is None else [round(target[0], 3), round(target[1], 3)],
                             distance=None if dist is None else round(dist, 3),
                             framing=None if bbox is None else round(bbox[0] + bbox[2] / 2 - 0.5, 4),
                             authority=authority.state, eligible=bool(intent and intent.command_eligible and not intent.expired(now_ns)),
                             hover=sp.hover, vn=round(sp.vn, 3), ve=round(sp.ve, 3), yaw_rate=round(sp.yaw_rate, 3),
                             armed=vehicle.armed, mode=vehicle.mode, discipline=discipline.state))
        # land and record PX4's reaction (mode, altitude) for a few seconds
        if scenario!="link_loss":vehicle.land()
        land_t0 = time.monotonic()
        # PX4 may choose RTL on offboard loss (including a return-height climb).
        # Observe that configured response through disarm; do not inject LAND
        # just to shorten the test or silently change failsafe parameters.
        while time.monotonic() - land_t0 < (120.0 if scenario=="link_loss" else 20.0):
            vehicle.poll(); time.sleep(0.05)
            if vehicle.pos is not None:
                rows.append(dict(t=round(time.monotonic() - t_start, 3), phase="landing", n=round(vehicle.pos[0], 3), e=round(vehicle.pos[1], 3),
                                 d=round(vehicle.pos[2], 3), yaw=round(vehicle.yaw, 4), target=None, distance=None, framing=None,
                                 authority=authority.state, eligible=False, hover=True, vn=0.0, ve=0.0, yaw_rate=0.0,
                                 armed=vehicle.armed, mode=vehicle.mode, discipline=discipline.state))
                if not vehicle.armed:break
        landing = [r for r in rows if r["phase"] == "landing"]
        summary["landing"] = dict(rows=len(landing), mode_auto_seen=any(r["mode"] == bridge.PX4_MAIN_MODE_AUTO for r in landing),
                                  altitude_start=landing[0]["d"] if landing else None, altitude_end=landing[-1]["d"] if landing else None,
                                  armed_end=landing[-1]["armed"] if landing else None)
    finally:
        if isinstance(source,BoardSource):
            summary['board_samples']=source.samples
            summary['board_transport_errors']=source.errors
        if source:source.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
    follow = [r for r in rows if r["phase"] == "follow"]
    active = [r for r in follow if r["authority"] == "ACTIVE" and r["framing"] is not None]
    settled = [r for r in active if r["t"] - (follow[0]["t"] if follow else 0) > 10.0]
    def pct(xs, q):
        xs = sorted(xs); return round(xs[int(q * (len(xs) - 1))], 3) if xs else None
    states = {}
    for r in follow:
        states[r["authority"]] = states.get(r["authority"], 0) + 1
    summary.update(
        ticks=len(rows), follow_ticks=len(follow), states=states,
        first_active_s=next((round(r["t"] - follow[0]["t"], 2) for r in follow if r["authority"] == "ACTIVE"), None),
        framing_abs_median=pct([abs(r["framing"]) for r in settled], 0.5), framing_abs_p95=pct([abs(r["framing"]) for r in settled], 0.95),
        distance_median=pct([r["distance"] for r in settled], 0.5), distance_p95=pct([r["distance"] for r in settled], 0.95),
        distance_final=follow[-1]["distance"] if follow else None,
        hover_ticks=sum(r["hover"] for r in follow), eligible_ticks=sum(r["eligible"] for r in follow),
        max_speed_cmd=pct([math.hypot(r["vn"], r["ve"]) for r in follow], 1.0),
        offboard_seen=any(r["mode"] == bridge.PX4_MAIN_MODE_OFFBOARD for r in rows), armed_seen=any(r["armed"] for r in rows),
        offboard_loss_without_land=any(r['phase']=='follow' and r['t']-follow[0]['t']>16 and
            r['mode']!=bridge.PX4_MAIN_MODE_OFFBOARD for r in follow) if scenario=='link_loss' and follow else None,
        transitions=[(round(t / 1e9 - t_start, 2), a, b, why) for (t, a, b, why) in authority.transitions],
        aborted_at_s=aborted_at, resumed_at_s=resumed_at)
    (out_dir / f"{scenario}.json").write_text(json.dumps(dict(summary=summary, rows=rows), indent=1))
    print(json.dumps(summary))
    return summary


def run_preview(scenario,duration,out_dir,seed=1):
    """Pure controller preview. Never launches PX4, opens MAVLink or arms anything."""
    from types import SimpleNamespace
    vehicle=SimpleNamespace(pos=(0.,0.,HOLD_Z),yaw=0.)
    authority=FollowAuthority(AuthorityConfig(execution="preview"))
    rng=random.Random(seed);rows=[]
    for step in range(int(duration*RATE_HZ)):
        t=step/RATE_HZ;now=int(t*1e9)
        view,track,_=perceive(vehicle,target_world(t),rng,scenario,t)
        cmd=compute(track,(1,1),FollowConfig(),t_ns=now) if track else None
        intent=authority.update(view,cmd,now)
        sp=bridge.setpoint_from_intent(intent,0.,HOLD_Z,now)
        assert sp.hover and sp.vn==sp.ve==sp.yaw_rate==0
        rows.append(dict(t=t,intent=intent.to_dict(),transport="disabled"))
    summary=dict(scenario=scenario,execution="preview",ticks=len(rows),vehicle_io=False)
    out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/f"{scenario}-preview.json").write_text(json.dumps(dict(summary=summary,rows=rows),indent=1))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenario", default="nominal", choices=SCENARIOS + ("all",))
    p.add_argument("--duration", type=float, default=40.0)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--execution", default="preview", choices=("live", "preview"))
    p.add_argument("--perception",default="tracker",choices=("synthetic","tracker","board"))
    p.add_argument("--tracker-binary",type=pathlib.Path,
        default=pathlib.Path(os.environ.get("GARUDA_REPLAY_BIN","/tmp/garuda-fresh-deploy/native/garuda-track-replay")))
    p.add_argument("--board-url",default="http://10.0.0.1:8099/api/state")
    a = p.parse_args()
    if not 0<a.duration<=600:
        p.error("duration must be 0..600 seconds")
    if a.execution=="live" and os.environ.get("GARUDA_SIM") != "1":
        sys.exit("REFUSED: GARUDA_SIM=1 not set — this arms and commands a (simulated) vehicle")
    for scenario in (SCENARIOS if a.scenario == "all" else (a.scenario,)):
        run_scenario(scenario, a.duration, a.out, a.execution,perception=a.perception,
                     tracker_binary=a.tracker_binary,board_url=a.board_url)


if __name__ == "__main__":
    main()
