"""Pure parts of the simulation offboard bridge; no MAVLink, no GARUDA_SIM."""
import math
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "garuda-follow"))
import sim_offboard_bridge as bridge
from follow_authority import CommandIntent

MS = 1_000_000


def intent(t_ns=1000*MS, ttl_ms=150, eligible=True, fwd=1.0, yaw=0.2):
    return CommandIntent(t_ns, ttl_ms*MS, "ACTIVE" if eligible else "COASTING", "x", 4, 4, fwd, 0.0, yaw, eligible, "live")


class BridgeTests(unittest.TestCase):
    def test_preview_future_nonfinite_and_overspeed_are_rejected(self):
        from dataclasses import replace
        for candidate in (replace(intent(),execution="preview"),intent(t_ns=2000*MS),
                          intent(fwd=float('nan')),intent(fwd=3.0)):
            self.assertTrue(bridge.setpoint_from_intent(candidate,0.,-3.,1100*MS).hover)

    def test_preview_runner_has_no_vehicle_io(self):
        import importlib.util,tempfile
        from unittest.mock import patch
        path=pathlib.Path(__file__).resolve().parents[3]/"bench/sim/followme_sitl.py"
        spec=importlib.util.spec_from_file_location("preview_test",path)
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as out, patch.object(runner,"launch_px4",side_effect=AssertionError("PX4 launch")), \
                patch.object(runner.bridge,"MavlinkVehicle",side_effect=AssertionError("vehicle I/O")):
            result=runner.run_scenario("nominal",1,pathlib.Path(out),"preview")
        self.assertFalse(result["vehicle_io"])
    def test_body_forward_rotates_with_heading(self):
        self.assertEqual(bridge.body_to_ned(1.0, 0.0), (1.0, 0.0))
        n, e = bridge.body_to_ned(1.0, math.pi/2)
        self.assertAlmostEqual(n, 0.0)
        self.assertAlmostEqual(e, 1.0)

    def test_stale_or_ineligible_intent_is_a_hover_never_the_last_command(self):
        sp = bridge.setpoint_from_intent(intent(), yaw=0.0, hold_z_ned=-3.0, now_ns=1100*MS)
        self.assertEqual((sp.vn, sp.ve, sp.yaw_rate, sp.z_ned, sp.hover), (1.0, 0.0, 0.2, -3.0, False))
        for stale in (bridge.setpoint_from_intent(intent(), 0.0, -3.0, 1200*MS),          # TTL expired
                      bridge.setpoint_from_intent(intent(eligible=False), 0.0, -3.0, 1100*MS),
                      bridge.setpoint_from_intent(None, 0.0, -3.0, 1100*MS)):
            self.assertEqual((stale.vn, stale.ve, stale.yaw_rate, stale.hover), (0.0, 0.0, 0.0, True))
            self.assertEqual(stale.z_ned, -3.0)          # altitude is still held

    def test_type_mask_keeps_velocity_altitude_and_yaw_rate(self):
        mask = bridge.Setpoint(0, 0, -3, 0, True).type_mask()
        for kept in (bridge.IGNORE_VX, bridge.IGNORE_VY, bridge.IGNORE_PZ, bridge.IGNORE_YAW_RATE):
            self.assertFalse(mask & kept)
        for ignored in (bridge.IGNORE_PX, bridge.IGNORE_PY, bridge.IGNORE_VZ, bridge.IGNORE_YAW):
            self.assertTrue(mask & ignored)

    def test_discipline_primes_then_engages_and_breaker_lands(self):
        d = bridge.OffboardDiscipline(prime_s=2.0, breaker_failures=3)
        self.assertEqual(d.tick(0), "PRIMING")
        self.assertEqual(d.tick(int(1.9e9)), "PRIMING")
        self.assertEqual(d.tick(int(2.0e9)), "ENGAGE")
        d.engaged()
        self.assertEqual(d.publish_result(True), "ENGAGED")
        d.publish_result(False); d.publish_result(False)
        self.assertEqual(d.state, "ENGAGED")
        self.assertEqual(d.publish_result(False), "LANDING")
        self.assertEqual(d.publish_result(True), "LANDING")          # a breaker does not reset itself

    def test_vehicle_refuses_without_the_sim_gate_and_non_udp_endpoints(self):
        env = dict(os.environ)
        os.environ.pop("GARUDA_SIM", None)
        try:
            with self.assertRaises(PermissionError):
                bridge.MavlinkVehicle("udpin:0.0.0.0:14540")
            os.environ["GARUDA_SIM"] = "1"
            with self.assertRaises(ValueError):
                bridge.MavlinkVehicle("/dev/ttyUSB0")
            for endpoint in ("udpin:0.0.0.0:14540","udpout:10.0.0.1:14540"):
                with self.assertRaises(ValueError):bridge.MavlinkVehicle(endpoint)
            with self.assertRaises(PermissionError):bridge.MavlinkVehicle("udpin:127.0.0.1:14540")
        finally:
            os.environ.clear(); os.environ.update(env)


if __name__ == "__main__":
    unittest.main()
