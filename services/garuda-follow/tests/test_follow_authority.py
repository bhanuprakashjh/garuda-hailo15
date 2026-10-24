"""FollowAuthority: session, states, budgets, TTL — pure logic, replay-driven."""
import gzip
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "interfaces"))
from follow_authority import AuthorityConfig, CommandIntent, FollowAuthority, target_view
from garuda_interfaces import FollowCommand

MS = 1_000_000


def view(state="tracking", reason="identity_verified", lock_id=4, epoch=4, control_valid=True):
    return dict(state=state, reason=reason, lock_id=lock_id, epoch=epoch, control_valid=control_valid,
                observation_valid=control_valid)


def command(valid=True, fwd=0.4, yaw=0.1, t_ns=0):
    return FollowCommand(t_ns=t_ns, target_id=94, yaw_rate=yaw, forward_vel=fwd, vertical_vel=0.0,
                         valid=valid, reason="tracking" if valid else "no target")


class AuthorityTests(unittest.TestCase):
    def test_session_opens_only_on_a_verified_observation(self):
        a = FollowAuthority()
        i = a.update(view(state="coasting", control_valid=False), command(False, t_ns=1000*MS), 1000*MS)
        self.assertEqual((a.state, i.command_eligible), ("IDLE", False))
        i = a.update(view(), command(t_ns=1100*MS), 1100*MS)
        self.assertEqual((a.state, i.state, i.command_eligible, i.forward_vel, i.yaw_rate), ("ACTIVE", "ACTIVE", True, 0.4, 0.1))
        self.assertEqual(i.execution, "preview")

    def test_prediction_is_never_command_eligible_and_coast_is_budgeted(self):
        a = FollowAuthority(AuthorityConfig(coast_time_ms=1000))
        a.update(view(), command(t_ns=1000*MS), 1000*MS)
        i = a.update(view(state="coasting", reason="missing_or_stale_observation", control_valid=False), command(False, t_ns=1300*MS), 1300*MS)
        self.assertEqual((a.state, i.command_eligible, i.forward_vel, i.yaw_rate), ("COASTING", False, 0.0, 0.0))
        i = a.update(view(state="occluded", reason="selected_identity_not_observed", control_valid=False), command(False, t_ns=1900*MS), 1900*MS)
        self.assertEqual(a.state, "COASTING")
        i = a.update(view(state="occluded", reason="selected_identity_not_observed", control_valid=False), command(False, t_ns=2100*MS), 2100*MS)
        self.assertEqual((a.state, i.reason), ("HANDOFF", "coast_budget_exhausted"))
        n = len(a.transitions)
        i = a.update(view(state="occluded", reason="selected_identity_not_observed", control_valid=False), command(False, t_ns=2150*MS), 2150*MS)
        self.assertEqual((a.state, i.reason, len(a.transitions)), ("HANDOFF", "coast_budget_exhausted", n))   # no flapping
        # the same session, verified again, re-engages straight out of a budget handoff
        i = a.update(view(), command(t_ns=2200*MS), 2200*MS)
        self.assertEqual((a.state, i.command_eligible), ("ACTIVE", True))

    def test_distance_budget_can_trip_before_the_time_budget(self):
        a = FollowAuthority(AuthorityConfig(coast_time_ms=5000, assumed_target_speed_mps=2.0, max_separation_growth_m=1.0))
        a.update(view(), command(t_ns=1000*MS), 1000*MS)
        i = a.update(view(state="coasting", control_valid=False), command(False, t_ns=1400*MS), 1400*MS)
        self.assertEqual(a.state, "COASTING")
        i = a.update(view(state="coasting", control_valid=False), command(False, t_ns=1600*MS), 1600*MS)   # 0.6 s x 2 m/s > 1 m
        self.assertEqual((a.state, i.reason), ("HANDOFF", "coast_budget_exhausted"))

    def test_reacquire_gets_its_own_budget_and_resumes_on_the_same_session(self):
        a = FollowAuthority(AuthorityConfig(coast_time_ms=500, reacquire_time_ms=3000))
        a.update(view(), command(t_ns=1000*MS), 1000*MS)
        i = a.update(view(state="reacquiring", reason="verifying_returning_identity", control_valid=False), command(False, t_ns=2500*MS), 2500*MS)
        self.assertEqual((a.state, i.command_eligible), ("REACQUIRING", False))
        i = a.update(view(), command(t_ns=2700*MS), 2700*MS)          # same lock.id + epoch: back to ACTIVE
        self.assertEqual((a.state, i.command_eligible), ("ACTIVE", True))

    def test_session_change_and_lost_are_handoffs(self):
        a = FollowAuthority()
        a.update(view(), command(t_ns=1000*MS), 1000*MS)
        i = a.update(view(lock_id=5, epoch=5, control_valid=False, state="coasting"), command(False, t_ns=1100*MS), 1100*MS)
        self.assertEqual((a.state, i.reason, i.command_eligible), ("HANDOFF", "awaiting_verified_observation", False))
        i = a.update(view(lock_id=5, epoch=5), command(t_ns=1200*MS), 1200*MS)      # operator re-clicked someone: verified -> drives
        self.assertEqual((a.state, i.reason, i.command_eligible, i.lock_id), ("ACTIVE", "session_changed", True, 5))
        b = FollowAuthority()
        b.update(view(), command(t_ns=1000*MS), 1000*MS)
        i = b.update(view(state="lost", reason="identity_memory_expired", control_valid=False), command(False, t_ns=1100*MS), 1100*MS)
        self.assertEqual((b.state, i.reason), ("HANDOFF", "target_identity_memory_expired"))
        c = FollowAuthority()
        c.update(view(), command(t_ns=1000*MS), 1000*MS)
        c.abort(1050*MS)
        i = c.update(view(), command(t_ns=1100*MS), 1100*MS)
        self.assertEqual((c.state, i.reason, i.command_eligible), ("HANDOFF", "operator_abort", False))
        c.resume(1150*MS)
        i = c.update(view(), command(t_ns=1200*MS), 1200*MS)
        self.assertEqual((c.state, i.command_eligible), ("ACTIVE", True))

    def test_intent_ttl(self):
        a = FollowAuthority(AuthorityConfig(intent_ttl_ms=100))
        i = a.update(view(), command(t_ns=1000*MS), 1000*MS)
        self.assertFalse(i.expired(1099*MS))
        self.assertTrue(i.expired(1101*MS))
        d = i.to_dict()
        self.assertEqual((d["frame"], d["state"], d["execution"]), ("body", "ACTIVE", "preview"))

    def test_missing_epoch_and_fractional_ttl_fail_closed(self):
        for epoch in (None,0,True,"1"):
            self.assertFalse(FollowAuthority().update(view(epoch=epoch),command(),0).command_eligible)
        with self.assertRaises(ValueError):FollowAuthority(AuthorityConfig(intent_ttl_ms=1.5))

    def test_live_execution_is_explicit(self):
        self.assertEqual(FollowAuthority(AuthorityConfig(execution="live")).cfg.execution, "live")
        with self.assertRaises(ValueError):
            FollowAuthority(AuthorityConfig(execution="hardware"))

    def test_replay_of_the_first_live_session(self):
        # bench/results/2026-09-12-visdrone-sot/live-follow-20260912-2205.jsonl.gz: the owner
        # locked himself, walked out 0.2-3.6 s four times (re-identified on the same lock.id),
        # then was away 12.4 s (identity memory expired) and re-clicked (new lock.id).
        path = pathlib.Path(__file__).resolve().parents[3] / "bench/results/2026-09-12-visdrone-sot/live-follow-20260912-2205.jsonl.gz"
        if not path.exists():
            self.skipTest("live capture not present")
        rows = [json.loads(l) for l in gzip.open(path, "rt") if l.strip()]
        a = FollowAuthority(AuthorityConfig(coast_time_ms=1500, reacquire_time_ms=4000))
        states, eligible, handoffs = [], 0, []
        for r in rows:
            v = target_view(r)
            cmd = command(valid=v["control_valid"], t_ns=int(r["capture_monotonic_ms"] * MS))
            i = a.update(v, cmd, int(r["capture_monotonic_ms"] * MS))
            states.append(a.state)
            eligible += i.command_eligible
            if i.reason.startswith("coast_budget") or i.reason in ("session_changed", "target_identity_memory_expired"):
                handoffs.append(i.reason)
        # ACTIVE only while the tracker was control-valid (one eligible intent per ACTIVE row);
        # the 3.6 s absence exhausts the 1.5 s coast budget (a HANDOFF), the 0.2-0.7 s ones do
        # not; the operator's re-click is a session change.
        self.assertEqual(eligible, states.count("ACTIVE"))
        # This historical diagnostic capture stripped observation_valid, epoch and
        # producer identity. It is no longer acceptable control evidence.
        self.assertEqual(eligible, 0)

    def test_invalid_and_repeated_evidence_cannot_renew_motion(self):
        from dataclasses import replace
        a=FollowAuthority(AuthorityConfig(execution="live"))
        v=view();v.update(sequence=1,source_id="camera",stream_id="boot1")
        cmd=command(t_ns=1000*MS)
        self.assertTrue(a.update(v,cmd,1000*MS).command_eligible)
        self.assertFalse(a.update(v,cmd,1200*MS).command_eligible)
        self.assertFalse(a.update(v,replace(cmd,t_ns=1200*MS),1200*MS).command_eligible)
        v["sequence"]=2;v["observation_valid"]=False
        self.assertFalse(a.update(v,replace(cmd,t_ns=1250*MS),1250*MS).command_eligible)
        v["observation_valid"]=True;v["sequence"]=3
        self.assertFalse(a.update(v,replace(cmd,t_ns=2000*MS),1300*MS).command_eligible)
        v["stream_id"]="boot2"
        self.assertEqual(a.update(v,command(t_ns=1400*MS),1400*MS).reason,"producer_changed")


if __name__ == "__main__":
    unittest.main()
