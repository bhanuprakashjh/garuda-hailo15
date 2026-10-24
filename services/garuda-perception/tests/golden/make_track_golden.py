#!/usr/bin/env python3
"""Deterministic scenario -> golden through the references (bytetrack_ref + mono_lock_ref).
Commands are applied like mono: a click sets lid+class from the PREVIOUS frame's tracks_full (the handler reads
_state["tracks_full"]); a target change sets the class and clears the lock; then the frame's detections are tracked.
Scenario exercises: birth/confirm (min_hits=2), two objects, a low-conf second-stage match, a 3-frame miss (coast),
a >REACQ coast with a live same-class track (re-acquire jump), a click on the second person, a target change to
'vehicle' with no vehicle (lock cleared, nothing acquired), then a vehicle appearing (auto-acquire), and >MAX_LOST death."""
import importlib.util, json, pathlib
here = pathlib.Path(__file__).resolve().parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, here / f"{name}.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bt, ref = load("bytetrack_ref"), load("mono_lock_ref")

def box(x, y, w=120, h=260): return [float(x), float(y), float(w), float(h)]
frames = []
def F(dets, click=None, target=None): frames.append({"dets": dets, "click": click, "target": target})
# 1) one person walking right, confirms on frame 2
for i in range(6):  F([box(100 + 10 * i, 300) + ["person", 0.9]])
# 2) second person appears far away; first keeps id
for i in range(6, 12): F([box(100 + 10 * i, 300) + ["person", 0.9], box(900, 320) + ["person", 0.85]])
# 3) first person only weakly detected for two frames (second-stage low-conf match keeps the id)
for i in range(12, 14): F([box(100 + 10 * i, 300) + ["person", 0.2], box(900, 320) + ["person", 0.85]])
# 4) first person missing 3 frames (coast, no re-acquire: 3 <= REACQ)
for i in range(14, 17): F([box(900, 320) + ["person", 0.85]])
# 5) first person back
for i in range(17, 20): F([box(100 + 10 * i, 300) + ["person", 0.9], box(900, 320) + ["person", 0.85]])
# 6) click on the second person -> lock jumps to it (frame 20 click uses frame 19's tracks)
F([box(300, 300) + ["person", 0.9], box(900, 320) + ["person", 0.85]], click=[960.0, 450.0])
for i in range(21, 24): F([box(300 + 10 * i, 300) + ["person", 0.9], box(900, 320) + ["person", 0.85]])
# 7) second person (locked by the block-6 click) vanishes for 7 frames. The "live one" the lock
# re-acquires onto here is NOT track 1 (the original first-person track): the first-person box jumps
# 300->510 at frame 21, losing IoU with track 1 (which keeps coasting from here on) and spawning a new
# track 3 (confirms frame 22, min_hits=2). After REACQ frames of the locked track being lost, the lock
# jumps to the live track 3.
for i in range(24, 31): F([box(300 + 10 * i, 300) + ["person", 0.9]])
# 8) target class -> vehicle with none in view: lock cleared, nothing acquired
F([box(600, 300) + ["person", 0.9]], target="vehicle")
for i in range(32, 34): F([box(600 + 10 * i, 300) + ["person", 0.9]])
# 9) a vehicle appears -> auto-acquired after it confirms
for i in range(34, 40): F([box(600, 300) + ["person", 0.9], box(400, 500, 400, 200) + ["vehicle", 0.7]])
# 10) everything gone for MAX_LOST+2 frames -> tracks die, lock -> None
for i in range(40, 68): F([])
(here / "track_scenario.json").write_text(json.dumps({"frames": frames}, indent=1) + "\n")

bt.Track._next = 1
tracker = bt.ByteTracker(high_thr=0.4, low_thr=0.12, iou_thr=0.3, max_lost=ref.MAX_LOST, min_hits=2)
lid, want, prev_tf, out = None, "person", [], []
for fr in frames:
    if fr["target"] is not None:
        want, lid = fr["target"] or "person", None
    if fr["click"] is not None:
        p = ref.click(prev_tf, fr["click"][0], fr["click"][1])
        if p is not None: lid, want = p[0], p[1]
    tracker.update([((d[0], d[1], d[2], d[3]), d[4], float(d[5])) for d in fr["dets"] if d[5] >= 0.15])
    lid, coasting, alive = ref.step_lock(tracker, lid, want)
    tf = ref.tracks_full_of(alive); prev_tf = tf
    out.append({"tracks": [list(t) for t in tf], "lock_id": lid, "lock_class": want, "coasting": coasting})
(here / "track_golden.json").write_text(json.dumps({"frames": out}, indent=1) + "\n")
print(len(frames), "frames ->", here / "track_golden.json")
