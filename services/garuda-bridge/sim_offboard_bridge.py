"""Simulation-only offboard bridge: CommandIntent -> PX4 offboard setpoints over MAVLink.

SAFETY GATE (CLAUDE.md rules 5/12): `main()`/`MavlinkVehicle` refuse to run
without GARUDA_SIM=1, explicit loopback UDP and a running local PX4 executable
PID. Do not forward that loopback endpoint to hardware. A hardware bridge is
a separate, later unit behind the same `OffboardDiscipline`.

OFFBOARD discipline (spec 2026-09-12 §1, PX4 requirement): prime setpoints
for `prime_s` before requesting arm + OFFBOARD; keep publishing at a fixed
rate forever; an expired or missing intent publishes the SAFE DEFAULT (hover:
zero velocity, hold altitude), never the last command; a run of publish
failures trips a circuit breaker that requests LAND and stops.
Execution mode `preview` computes and logs setpoints without sending them.
"""
import math
import os
import time
import pathlib
from dataclasses import dataclass

# MAVLink SET_POSITION_TARGET_LOCAL_NED type_mask bits (1 = ignore)
IGNORE_PX, IGNORE_PY, IGNORE_PZ = 1, 2, 4
IGNORE_VX, IGNORE_VY, IGNORE_VZ = 8, 16, 32
IGNORE_AX, IGNORE_AY, IGNORE_AZ = 64, 128, 256
FORCE, IGNORE_YAW, IGNORE_YAW_RATE = 512, 1024, 2048
PX4_MAIN_MODE_OFFBOARD = 6
PX4_MAIN_MODE_AUTO, PX4_SUB_MODE_AUTO_LAND = 4, 6


@dataclass(frozen=True)
class Setpoint:
    """Mixed setpoint: velocity-controlled horizontal follow, position-held altitude, yaw rate."""
    vn: float
    ve: float
    z_ned: float
    yaw_rate: float
    hover: bool

    def type_mask(self):
        # keep vx, vy, pz, yaw_rate; ignore px, py, vz, accelerations, yaw
        return IGNORE_PX | IGNORE_PY | IGNORE_VZ | IGNORE_AX | IGNORE_AY | IGNORE_AZ | IGNORE_YAW


def body_to_ned(forward, yaw):
    """Body-forward speed at heading `yaw` (rad, 0 = north) -> (north, east) velocities."""
    return forward * math.cos(yaw), forward * math.sin(yaw)


def setpoint_from_intent(intent, yaw, hold_z_ned, now_ns):
    """Safe default unless the intent is fresh AND command-eligible."""
    if (intent is None or intent.expired(now_ns) or not intent.command_eligible or intent.execution != "live"
            or not all(math.isfinite(v) for v in (yaw, hold_z_ned, intent.forward_vel, intent.vertical_vel, intent.yaw_rate))
            or abs(intent.forward_vel)>2 or abs(intent.vertical_vel)>1 or abs(intent.yaw_rate)>.8):
        return Setpoint(0.0, 0.0, hold_z_ned, 0.0, True)
    vn, ve = body_to_ned(intent.forward_vel, yaw)
    return Setpoint(vn, ve, hold_z_ned, intent.yaw_rate, False)


class OffboardDiscipline:
    """Pure state: PRIMING -> ENGAGED -> (LANDING on breaker). Time in ns."""

    def __init__(self, prime_s=2.0, breaker_failures=5):
        self.prime_ns = int(prime_s * 1e9)
        self.breaker_failures = breaker_failures
        self.started_ns = None
        self.state = "PRIMING"
        self.failures = 0
        self.sent = 0

    def tick(self, now_ns):
        if self.started_ns is None:
            self.started_ns = now_ns
        if self.state == "PRIMING" and now_ns - self.started_ns >= self.prime_ns:
            self.state = "ENGAGE"        # caller arms + requests OFFBOARD exactly once
        return self.state

    def engaged(self):
        self.state = "ENGAGED"

    def publish_result(self, ok):
        if ok:
            self.failures = 0
            self.sent += 1
        else:
            self.failures += 1
            if self.failures >= self.breaker_failures and self.state != "LANDING":
                self.state = "LANDING"
        return self.state


class MavlinkVehicle:
    """Thin pymavlink wrapper; loopback + local simulator PID + GARUDA_SIM required."""

    def __init__(self, endpoint="udpin:127.0.0.1:14540", source_system=200, *, sim_pid=None):
        if os.environ.get("GARUDA_SIM") != "1":
            raise PermissionError("REFUSED: GARUDA_SIM=1 not set — this bridge commands arming/offboard")
        parts = endpoint.split(":")
        if (len(parts)!=3 or parts[0] not in ("udpin", "udpout") or parts[1]!="127.0.0.1"
                or not parts[2].isdigit() or not 1024<=int(parts[2])<=65535):
            raise ValueError("simulation bridge accepts explicit IPv4 loopback UDP endpoints only")
        self.sim_pid = sim_pid
        self._verify_simulator()
        from pymavlink import mavutil
        self.mavutil = mavutil
        self.m = mavutil.mavlink_connection(endpoint, source_system=source_system)
        self.hb = self.m.wait_heartbeat(timeout=30)
        if self.hb is None:
            raise TimeoutError("no heartbeat from the simulator")
        if self.hb.autopilot != mavutil.mavlink.MAV_AUTOPILOT_PX4:
            raise PermissionError("heartbeat is not from PX4")
        self.peer=(self.hb.get_srcSystem(),self.hb.get_srcComponent())
        self.m.target_system,self.m.target_component=self.peer
        self.pos = None        # (n, e, d)
        self.yaw = 0.0
        self.armed = False
        self.mode = None
        self.last_position = self.last_attitude = self.last_heartbeat = 0.0

    def _verify_simulator(self):
        if type(self.sim_pid) is not int or self.sim_pid<=0:
            raise PermissionError("an owned local PX4 simulator PID is required")
        expected = pathlib.Path(os.environ.get("GARUDA_PX4_BUILD",
            "/media/bhanu1234/Development/PX4-Autopilot/build/px4_sitl_default"))/"bin/px4"
        try:
            actual=pathlib.Path(f"/proc/{self.sim_pid}/exe").resolve(strict=True)
            if actual!=expected.resolve(strict=True):
                raise PermissionError("PID is not the configured local PX4 SITL executable")
            status=pathlib.Path(f"/proc/{self.sim_pid}/status").read_text()
            parent=next(int(line.split()[1]) for line in status.splitlines() if line.startswith("PPid:"))
            if parent!=os.getpid():
                raise PermissionError("local PX4 process is not owned by this runner")
        except FileNotFoundError as e:
            raise PermissionError("local simulator is not running") from e

    def poll(self, max_msgs=200):
        for _ in range(max_msgs):
            msg = self.m.recv_match(blocking=False)
            if msg is None:
                break
            if (msg.get_srcSystem(),msg.get_srcComponent())!=self.peer:
                continue
            if hasattr(self, 'on_message'):
                self.on_message(msg)
            t = msg.get_type()
            if t == "LOCAL_POSITION_NED":
                self.pos = (msg.x, msg.y, msg.z)
                self.last_position = time.monotonic()
            elif t == "ATTITUDE":
                self.yaw = msg.yaw
                self.last_attitude = time.monotonic()
            elif t == "HEARTBEAT":
                self.last_heartbeat = time.monotonic()
                self.armed = bool(msg.base_mode & self.mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                self.mode = (msg.custom_mode >> 16) & 0xFF

    def send_setpoint(self, sp, boot_ms, **_bench_metadata):
        self._verify_simulator()
        if (not all(math.isfinite(v) for v in (sp.vn,sp.ve,sp.z_ned,sp.yaw_rate))
                or math.hypot(sp.vn,sp.ve)>2.001 or abs(sp.yaw_rate)>.8):
            raise ValueError("invalid simulation setpoint")
        if time.monotonic()-min(self.last_position,self.last_attitude)>.5:
            raise OSError("simulator telemetry stale")
        self.m.mav.set_position_target_local_ned_send(
            boot_ms, self.m.target_system, self.m.target_component,
            self.mavutil.mavlink.MAV_FRAME_LOCAL_NED, sp.type_mask(),
            0.0, 0.0, sp.z_ned, sp.vn, sp.ve, 0.0, 0.0, 0.0, 0.0, 0.0, sp.yaw_rate)

    def arm(self):
        self._verify_simulator()
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     self.mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)

    def set_offboard(self):
        self._verify_simulator()
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     self.mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                                     self.mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                     PX4_MAIN_MODE_OFFBOARD, 0, 0, 0, 0, 0)

    def land(self):
        self._verify_simulator()
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     self.mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                                     self.mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                     PX4_MAIN_MODE_AUTO, PX4_SUB_MODE_AUTO_LAND, 0, 0, 0, 0)
