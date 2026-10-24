"""Fresh stack transport/replay contracts; no Hailo hardware or third-party Python modules."""
import gzip
import importlib.util
import json
import os
import pathlib
import subprocess
import threading
import unittest
import urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fresh_shim", ROOT / "fresh_shim.py")
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)

def snapshot(capture=1000, publish=1010):
    return {"v": 2, "tracker_contract": "garuda.fresh.v1", "sequence": 9,
            "capture_monotonic_ms": capture, "publish_monotonic_ms": publish,
            "timestamp_valid": True, "freshness_budget_ms": 200, "valid_for_ms": 190,
            "tracks": [{"id": 1, "coasting": False}],
            "lock": {"id": 1, "state": "tracking", "control_valid": True,
                     "observation_valid": True, "obs_age_ms": 10},
            "image_target": {"valid": True}}

class FreshTransportTests(unittest.TestCase):
    def test_cached_validity_expires_without_new_frame(self):
        raw = json.dumps(snapshot()).encode()
        self.assertTrue(json.loads(shim.age_snapshot(raw, 1050))["lock"]["control_valid"])
        stale = json.loads(shim.age_snapshot(raw, 1250))
        self.assertFalse(stale["lock"]["control_valid"])
        self.assertFalse(stale["lock"]["observation_valid"])
        self.assertFalse(stale["image_target"]["valid"])
        self.assertEqual(stale["lock"]["obs_age_ms"], 250)
        self.assertTrue(stale["tracks"][0]["coasting"])
        self.assertTrue(json.loads(raw)["lock"]["control_valid"])

    def test_bad_or_different_clock_fails_closed(self):
        for raw, now in ((b"junk", 1000), (b"{}", 1000),
                         (json.dumps(snapshot()).encode(), 900),
                         (json.dumps(snapshot()).encode(), float("nan"))):
            self.assertFalse(json.loads(shim.age_snapshot(raw, now))["lock"]["control_valid"])

    def test_unobserved_lock_keeps_the_node_reason_while_the_frame_is_fresh(self):
        # The identity owner reports occluded with valid_for_ms 0; sampled 50 ms after publish
        # the FRAME is fresh, so the node's reason must survive (only frame staleness relabels).
        snap = snapshot()
        snap["valid_for_ms"] = 0
        snap["lock"].update({"state": "occluded", "reason": "selected_identity_not_observed",
                             "control_valid": False, "observation_valid": False, "track_id": None})
        aged = json.loads(shim.age_snapshot(json.dumps(snap).encode(), 1060))
        self.assertFalse(aged["lock"]["control_valid"])
        self.assertEqual(aged["lock"]["reason"], "selected_identity_not_observed")
        self.assertEqual(aged["lock"]["state"], "occluded")
        stale = json.loads(shim.age_snapshot(json.dumps(snap).encode(), 1250))   # frame itself too old
        self.assertEqual(stale["lock"]["reason"], "source_stale")

    def test_remaining_budget_is_respected(self):
        snap = snapshot()
        snap["valid_for_ms"] = 5
        self.assertFalse(json.loads(shim.age_snapshot(json.dumps(snap).encode(), 1020))["lock"]["control_valid"])

    def test_http_and_frame_referenced_commands(self):
        class Feed:
            @property
            def snap(self):
                return shim.age_snapshot(json.dumps(snapshot(1, 2)).encode())
        class Commands:
            def __init__(self): self.requests = []
            def call(self, request):
                self.requests.append(request)
                return {"ok": True}
        commands = Commands()
        server = shim.base.ShimHTTPServer(("127.0.0.1", 0), shim.base.make_handler(Feed(), commands))
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(url + "/api/state", timeout=2) as response:
                self.assertFalse(json.load(response)["lock"]["control_valid"])
            req = urllib.request.Request(url + "/api/mono_click?x=140&y=80&sequence=9", method="POST")
            with urllib.request.urlopen(req, timeout=2) as response:
                self.assertTrue(json.load(response)["ok"])
            self.assertEqual(commands.requests[-1], {"cmd": "lock_point", "x": 140., "y": 80., "sequence": 9})
            with urllib.request.urlopen(urllib.request.Request(url + "/api/unlock", method="POST"), timeout=2):
                pass
            self.assertEqual(commands.requests[-1], {"cmd": "unlock"})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_sse_ages_state_even_without_node_updates(self):
        feed = shim.FreshFeed.__new__(shim.FreshFeed)
        feed.lock = threading.Lock(); feed.cv = threading.Condition(feed.lock)
        feed.snap_seq = 1; feed.snap = json.dumps(snapshot(1, 2)).encode()
        data, seq, changed = feed.wait_snap(1, timeout=.001)
        self.assertTrue(changed); self.assertEqual(seq, 1)
        self.assertFalse(json.loads(data)["lock"]["control_valid"])

class ReplayTests(unittest.TestCase):
    def run_replay(self, rows):
        binary = os.environ.get("GARUDA_REPLAY_BIN")
        if not binary: self.skipTest("GARUDA_REPLAY_BIN is not set")
        return subprocess.run([binary, "-"], input="".join(json.dumps(row) + "\n" for row in rows),
                              text=True, capture_output=True, timeout=5)

    def test_real_executable_replay_and_camera_stall(self):
        rows = []
        for seq, timestamp in enumerate((1000, 1060, 1120), 1):
            rows.append({"sequence": seq, "capture_ms": timestamp, "now_ms": timestamp + 10,
                         "timestamp_valid": True,
                         "detections": [{"box": {"x": .3, "y": .2, "w": .1, "h": .4},
                                         "label": "person", "confidence": .9}]})
        rows += [{"cmd": "select", "id": 1, "sequence": 3, "now_ms": 1130},
                 {"heartbeat_ms": 1140}, {"heartbeat_ms": 1500}, {"heartbeat_ms": 2500}]
        result = self.run_replay(rows)
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(outputs[-3]["lock"]["control_valid"])
        self.assertFalse(outputs[-2]["lock"]["control_valid"])
        self.assertEqual(outputs[-1]["lock"]["state"], "lost")

    def test_recorded_h15l_person_and_process_stall(self):
        binary = os.environ.get("GARUDA_REPLAY_BIN")
        if not binary: self.skipTest("GARUDA_REPLAY_BIN is not set")
        fixtures = ROOT / "tests" / "fixtures"
        with gzip.open(fixtures / "h15l-person-20260910.jsonl.gz", "rt") as f:
            recording = f.read()
        result = subprocess.run([binary, "-", str(fixtures / "h15l-person-20260910.config.json")],
                                input=recording, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = [j for line in result.stdout.splitlines() if "tracks" in (j := json.loads(line))]
        self.assertEqual(sum(not f["accepted"] for f in frames), 5)  # queued stale frames after SIGSTOP
        locked = [f for f in frames if f["lock"]["control_valid"]]
        self.assertGreater(len(locked), 900)
        # The lock id is stable across the stall + re-acquire; only the
        # underlying MOT track_id changes (one re-acquire => exactly two).
        self.assertEqual({f["lock"]["id"] for f in locked}, {1})
        self.assertEqual({f["lock"]["track_id"] for f in locked}, {1, 2})
        lost = [f for f in frames if f["lock"]["state"] == "lost"]
        self.assertTrue(lost)
        self.assertTrue(all(not f["lock"]["control_valid"] for f in lost))
        self.assertTrue(any(f["lock"]["state"] == "reacquiring" for f in frames))
        self.assertEqual(frames[-1]["lock"]["state"], "tracking")  # re-acquired by the end

    def test_replay_rejects_invalid_sequence(self):
        result = self.run_replay([{"sequence": -1, "capture_ms": 1, "now_ms": 2,
                                   "timestamp_valid": True, "detections": []}])
        self.assertNotEqual(result.returncode, 0); self.assertIn("positive integer", result.stderr)

if __name__ == "__main__": unittest.main()
