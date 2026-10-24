"""Time- and identity-gated adapter for the existing visual servo controller.

No vehicle I/O. Call tick on every control cycle, including during feed loss.
ingest takes request/response timestamps on the SAME receiver monotonic clock.
The entire request RTT is charged as a conservative transport upper bound.
"""
from dataclasses import dataclass, replace
import math
from follow_controller import FollowConfig, compute
from garuda_interfaces import FollowCommand, TargetObservation, Track


@dataclass(frozen=True)
class FollowDecision:
    command: FollowCommand
    source_id: str
    stream_id: str
    epoch: int
    sequence: int | None
    observation_age_upper_ns: int | None
    position_std_fraction: float | None
    expires_local_ns: int | None
    bound_observation: TargetObservation | None

    def to_dict(self):
        return {**self.__dict__, "command": self.command.to_dict(),
                "bound_observation": self.bound_observation.to_dict() if self.bound_observation else None,
                "range_available": False,
                "receiver_clock": "local.monotonic", "mode": "simulation_only"}


class FreshFollow:
    def __init__(self, source_id, stream_id, epoch, *, config=None,
                 max_age_ns=200_000_000, max_position_std=.12, framing_translation=False):
        if not source_id or not stream_id or type(epoch) is not int or epoch <= 0:
            raise ValueError("explicit source, producer instance and selected epoch required")
        if type(max_age_ns) is not int or not 0 < max_age_ns <= 200_000_000 or not 0 < max_position_std <= .12:
            raise ValueError("invalid follow freshness/uncertainty bound")
        self.identity = (source_id, stream_id, epoch)
        self.cfg = replace(config or FollowConfig())
        if any(type(v) not in (int,float) or not math.isfinite(v) or v < 0 for v in vars(self.cfg).values()):
            raise ValueError("nonfinite or negative follow configuration")
        if not (0 < self.cfg.min_height_frac < self.cfg.max_height_frac <= 1 and
                0 <= self.cfg.min_confidence <= 1 and 0 <= self.cfg.desired_height_frac <= 1 and
                self.cfg.deadzone <= .5 and self.cfg.max_yaw_rate <= .8 and
                self.cfg.max_forward_vel <= 2 and self.cfg.max_vertical_vel <= 1):
            raise ValueError("follow configuration exceeds simulation limits")
        # Default fresh integration centers yaw only. Framing translation is a
        # separately requested simulation experiment, never a metric-range estimate.
        if not framing_translation:
            self.cfg.forward_gain = self.cfg.vertical_gain = 0.
        self.max_age_ns, self.max_std = max_age_ns, max_position_std
        self.current = None
        self.last_packet = None
        self.last_source = None
        self.deadline = None
        self.last_receive = -1
        self.last_tick = -1
        self.reason = "waiting_for_selected_identity"

    def reject(self, reason):
        self.current = None
        self.reason = reason
        return False

    def ingest(self, observation: TargetObservation, request_started_ns: int, received_ns: int):
        if any(type(v) is not int or v < 0 for v in (request_started_ns, received_ns)) or received_ns < request_started_ns:
            return self.reject("invalid_receiver_clock")
        if received_ns < self.last_receive or received_ns < self.last_tick:
            return self.reject("receiver_clock_regressed")
        self.last_receive = received_ns
        o = observation
        if o.identity != self.identity:
            return self.reject("identity_binding_changed")
        old = self.last_source
        if old is not None:
            if o.clock_domain != old.clock_domain:
                return self.reject("source_clock_changed")
            if (o.sequence < old.sequence or o.publish_ns < old.publish_ns or o.sample_ns < old.sample_ns or
                (o.sequence == old.sequence and o.capture_ns != old.capture_ns) or
                (o.sequence > old.sequence and o.capture_ns <= old.capture_ns)):
                return self.reject("source_out_of_order")
        rtt = received_ns-request_started_ns
        source_age = max(o.sample_ns-o.capture_ns, o.observation_age_ns)
        remaining = min(o.valid_for_ns, min(self.max_age_ns, o.freshness_ns)-source_age)-rtt
        deadline = received_ns+max(0, remaining)
        if old is not None and old.sequence == o.sequence and self.deadline is not None:
            deadline = min(deadline, self.deadline)  # cached/repeated frame never renews its lease
        self.last_source, self.deadline = o, deadline
        self.last_packet = (o, received_ns, source_age+rtt)
        if not (o.timestamp_valid and o.observation_valid and o.control_valid and o.state == "tracking"):
            return self.reject("target_"+o.reason)
        if o.position_std_fraction > self.max_std:
            return self.reject("target_uncertain")
        if remaining <= 0 or deadline <= received_ns:
            return self.reject("target_expired")
        self.current = self.last_packet
        self.reason = "tracking"
        return True

    def tick(self, now_ns):
        if type(now_ns) is not int or now_ns < 0:
            raise ValueError("invalid receiver tick timestamp")
        if now_ns < max(self.last_tick, self.last_receive):
            self.reject("receiver_clock_regressed")
        self.last_tick = max(self.last_tick, now_ns)
        o, age = None, None
        if self.last_packet is not None:
            o, received, initial_age = self.last_packet
            age = initial_age+max(0, now_ns-received)
            if self.current is not None and (now_ns >= self.deadline or age >= self.max_age_ns):
                self.reject("target_expired")
        if self.current is None:
            cmd = FollowCommand(now_ns, None, 0., 0., 0., False, self.reason)
        else:
            target = Track(o.track_id, -1, o.label, o.bbox, o.confidence, time_since_update=0)
            cmd = compute(target, (1, 1), self.cfg, t_ns=now_ns)
        return FollowDecision(cmd, *self.identity, o.sequence if o else None, age,
                              o.position_std_fraction if o else None, self.deadline, o)
