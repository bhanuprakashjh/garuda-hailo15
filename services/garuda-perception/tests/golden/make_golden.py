#!/usr/bin/env python3
"""Golden snapshot from the Pi's builder so the C++ port is tested for parity, not by eye.
Reference copy: mono_state_ref.py is byte-identical to feat/portal-tracking:hosts/pi5/mono_state.py"""
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location("mono_state", pathlib.Path(__file__).with_name("mono_state_ref.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
state = {"tracks_full": [(7, "person", 100.0, 50.0, 40.0, 120.0, 0.91, False),
                         (9, "vehicle", 600.0, 300.0, 200.0, 90.0, 0.55, True)],
         "class": "person", "raw": 2.31}
extras = {"age_ms": 33, "lock_id": 7, "lock_coasting": False, "est_m": 2.4, "valid": True,
          "depth_engine": "y26d", "detector_mode": "primary", "prompt": [], "cal_n": 3,
          "fit": "a=1.00 b=0.00", "frame_w": 1280, "frame_h": 720}
out = pathlib.Path(__file__).with_name("snapshot_v2.json")
out.write_text(json.dumps(m.build_snapshot(state, extras), sort_keys=True, separators=(",", ":")) + "\n")
print(out)
