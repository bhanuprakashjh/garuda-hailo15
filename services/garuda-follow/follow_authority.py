"""Follow authority: the one place that decides whether a follow command may
drive the vehicle (spec 2026-09-12 §2 Phase B, after PixEagle's supervisor).

Sits between the tracker's published target and any consumer. Owns a session
(the lock's stable id + selection epoch) and a state:

  IDLE         no session — nothing selected
  ACTIVE       verified observation, command passes through
  COASTING     target coasting/occluded on the SAME session: hover, budgeted
  REACQUIRING  tracker verifying a returning candidate: hover, budgeted
  HANDOFF      budget exhausted, target lost, session changed or operator
               abort: hover; re-engages on the next verified observation of a
               session, except after an operator abort (sticky until resume)

Rules that never bend: prediction is never command-eligible (COASTING and
REACQUIRING publish zero velocities, not the last command); every intent
carries a TTL after which the consumer must fall back to its own safe default;
a session change (new lock.id or epoch) drives only once verified, never silently;
budgets are dual — time and the separation a walking target could open, both
conservative bounds, not measurements. Execution mode defaults to PREVIEW
(intents are computed and logged, never sent); LIVE is an explicit request and,
for now, simulation only.
"""
from dataclasses import dataclass
import math

MS = 1_000_000


@dataclass(frozen=True)
class AuthorityConfig:
    coast_time_ms: int = 1500          # hover this long on the same session before HANDOFF
    assumed_target_speed_mps: float = 1.5   # a walk; bounds separation growth while coasting
    max_separation_growth_m: float = 2.0    # distance budget: speed x coast time, capped here
    intent_ttl_ms: int = 150           # consumer must hover once an intent is older than this
    reacquire_time_ms: int = 4000      # allow the tracker's re-acquire this long
    execution: str = "preview"         # preview | live


@dataclass(frozen=True)
class CommandIntent:
    t_ns: int
    ttl_ns: int
    state: str
    reason: str
    lock_id: object
    epoch: object
    forward_vel: float
    vertical_vel: float
    yaw_rate: float
    command_eligible: bool
    execution: str
    source_id: str = ""
    stream_id: str = ""
    sequence: int | None = None

    def expired(self, now_ns):
        return (type(now_ns) is not int or type(self.t_ns) is not int or type(self.ttl_ns) is not int
                or self.ttl_ns <= 0 or now_ns < self.t_ns or now_ns >= self.t_ns + self.ttl_ns)

    def to_dict(self):
        return dict(self.__dict__, frame="body", units="m/s, rad/s")


def target_view(snapshot):
    """The few lock fields the authority reasons about, from a fresh snapshot."""
    lock = snapshot["lock"]
    return dict(state=lock.get("state"), reason=lock.get("reason"), lock_id=lock.get("id"),
                epoch=lock.get("epoch"), control_valid=bool(lock.get("control_valid")),
                observation_valid=lock.get("observation_valid") is True,
                source_id=snapshot.get("source_id", ""), stream_id=snapshot.get("stream_id", ""),
                sequence=snapshot.get("sequence"))


class FollowAuthority:
    STATES = ("IDLE", "ACTIVE", "COASTING", "REACQUIRING", "HANDOFF")

    def __init__(self, config=None):
        self.cfg = config or AuthorityConfig()
        if self.cfg.execution not in ("preview", "live"):
            raise ValueError("execution must be preview or live")
        if any(type(v) is not int for v in (self.cfg.coast_time_ms,self.cfg.intent_ttl_ms,self.cfg.reacquire_time_ms)):
            raise ValueError("authority time budgets must be integer milliseconds")
        if any(not math.isfinite(v) or v <= 0 for v in (self.cfg.coast_time_ms, self.cfg.intent_ttl_ms, self.cfg.reacquire_time_ms,
                                 self.cfg.assumed_target_speed_mps, self.cfg.max_separation_growth_m)):
            raise ValueError("authority budgets must be positive")
        self.state = "IDLE"
        self.session = None            # (lock_id, epoch)
        self.since_ns = None           # when the current non-ACTIVE state began
        self.last_active_ns = None
        self.handoff_reason = None
        self.aborted = False
        self.transitions = []
        self.last_update_ns = -1
        self.producer = None
        self.last_sequence = None
        self.observation_deadline = None

    def _enter(self, state, reason, now_ns):
        if state != self.state:
            self.transitions.append((now_ns, self.state, state, reason))
            self.transitions = self.transitions[-2048:]
            self.state = state
            self.since_ns = now_ns

    def _hover(self, now_ns, reason, eligible=False):
        return CommandIntent(now_ns, self.cfg.intent_ttl_ms*MS, self.state, reason, *(self.session or (None, None)),
                             0.0, 0.0, 0.0, eligible, self.cfg.execution)

    def abort(self, now_ns, reason="operator_abort"):
        """Operator abort: the only sticky HANDOFF — nothing re-engages until resume()."""
        self.aborted = True
        self.handoff_reason = reason
        self._enter("HANDOFF", reason, now_ns)

    def resume(self, now_ns):
        if self.aborted:
            self.aborted = False
            self.handoff_reason = None
            self.session = None
            self._enter("IDLE", "operator_resume", now_ns)

    def _budget_exhausted(self, now_ns):
        elapsed_s = (now_ns - self.last_active_ns) / 1e9 if self.last_active_ns is not None else math.inf
        if self.state == "REACQUIRING":
            # The tracker is verifying a re-detected candidate: separation is no longer
            # unobserved, only the verification time is bounded.
            return elapsed_s * 1000 > self.cfg.reacquire_time_ms
        separation = self.cfg.assumed_target_speed_mps * elapsed_s
        return elapsed_s * 1000 > self.cfg.coast_time_ms or separation > self.cfg.max_separation_growth_m

    def _handoff(self, now_ns, reason):
        self.handoff_reason = reason
        self._enter("HANDOFF", reason, now_ns)
        return self._hover(now_ns, reason)

    def update(self, view, command, now_ns):
        """view: target_view(snapshot); command: FollowCommand from the controller (or None).

        A verified observation (tracker `tracking`, control-valid, controller command valid)
        of a session always drives — including straight out of a budget HANDOFF on the same
        session, and on the first verified observation of a NEW session (the operator chose
        it). Only an operator abort stays put until resume().
        """
        if type(now_ns) is not int or now_ns < 0:
            raise ValueError("invalid authority clock")
        if now_ns < self.last_update_ns:
            return self._handoff(self.last_update_ns, "receiver_clock_regressed")
        self.last_update_ns = now_ns
        if self.aborted:
            return self._hover(now_ns, self.handoff_reason or "operator_abort")
        session = (view["lock_id"], view["epoch"]) if (view["lock_id"] is not None and
                    type(view.get("epoch")) is int and view["epoch"]>0) else None
        producer = (view.get("source_id", ""), view.get("stream_id", ""))
        seq = view.get("sequence")
        if self.producer is not None and producer != self.producer:
            self.producer = producer; self.last_sequence = None; self.observation_deadline = None
            self.session = None
            return self._handoff(now_ns, "producer_changed")
        self.producer = producer
        deadline = view.get("expires_ns", command.t_ns + self.cfg.intent_ttl_ms*MS if command else now_ns)
        if type(deadline) is not int:
            return self._handoff(now_ns, "invalid_observation_deadline")
        if seq is not None:
            if type(seq) is not int or seq < 1 or (self.last_sequence is not None and seq < self.last_sequence):
                return self._handoff(now_ns, "source_out_of_order")
            if seq == self.last_sequence and self.observation_deadline is not None:
                deadline = min(deadline, self.observation_deadline)
            self.last_sequence, self.observation_deadline = seq, deadline
        verified = (session is not None and view["state"] == "tracking" and view["control_valid"] is True
                    and view.get("observation_valid") is True and command is not None and command.valid
                    and type(command.t_ns) is int and 0 <= now_ns-command.t_ns < self.cfg.intent_ttl_ms*MS
                    and now_ns < deadline and all(math.isfinite(v) for v in
                        (command.forward_vel, command.vertical_vel, command.yaw_rate))
                    and abs(command.forward_vel)<=2 and abs(command.vertical_vel)<=1 and abs(command.yaw_rate)<=.8)
        if verified:
            reason = "session_changed" if (self.session is not None and session != self.session) else "verified_observation"
            self.session = session
            self.last_active_ns = now_ns
            self._enter("ACTIVE", reason, now_ns)
            ttl = min(self.cfg.intent_ttl_ms*MS, deadline-now_ns,
                      command.t_ns+self.cfg.intent_ttl_ms*MS-now_ns)
            return CommandIntent(now_ns, ttl, "ACTIVE", reason, *session,
                                 command.forward_vel, command.vertical_vel, command.yaw_rate, True, self.cfg.execution,
                                 *producer, seq)
        if session is None or view["state"] in ("none",):
            if self.session is not None:
                self.session = None
                return self._handoff(now_ns, "selection_cleared")
            self._enter("IDLE", "no_selection", now_ns)
            return self._hover(now_ns, "no_selection")
        if self.session is None:
            self._enter("IDLE", "awaiting_verified_observation", now_ns)
            return self._hover(now_ns, "awaiting_verified_observation")
        if session != self.session:
            # Unverified observation of a changed session: hold (the old session stays on
            # record so the switch is reported as session_changed once verified).
            return self._handoff(now_ns, "awaiting_verified_observation")
        if view["state"] == "lost" and view["reason"] not in ("watching_for_return",):
            return self._handoff(now_ns, "target_" + (view["reason"] or "lost"))
        if self.state == "HANDOFF":
            # Budget already exhausted on this session: stay handed off (no flapping
            # back through COASTING) until a verified observation re-engages.
            return self._hover(now_ns, self.handoff_reason or "handoff")
        self._enter("REACQUIRING" if view["state"] in ("reacquiring", "lost") else "COASTING",
                    "target_" + (view["reason"] or view["state"] or "unobserved"), now_ns)
        if self._budget_exhausted(now_ns):
            return self._handoff(now_ns, "coast_budget_exhausted")
        return self._hover(now_ns, "target_" + (view["reason"] or view["state"] or "unobserved"))
