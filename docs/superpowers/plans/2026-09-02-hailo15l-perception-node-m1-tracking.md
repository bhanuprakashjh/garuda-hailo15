# Hailo-15L Perception Node — M1 (tracking and lock parity) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The board's perception node tracks detections across frames exactly as garuda-mono does on the Pi — ByteTrack ids that persist, a lock that coasts through misses and re-acquires, click-to-lock that sticks, target-class auto-acquire — so the portal's Tracking view behaves like the Pi's; in parallel, the yolo26m detector is recompiled for the 15L and benchmarked (not integrated).

**Architecture:** Two small C++ units join `garuda_perception_core`: a line-for-line port of mono's lean ByteTrack (`bytetrack.py`) and a port of mono's lock/coast/re-acquire and click/target rules (inline in `garuda_mono.py`). Both are proven by golden tests generated from byte-identical reference copies of the Python. `node_main.cpp`'s detection callback feeds the tracker, applies the lock rules, and publishes tracks with real ids and `coasting`; commands update the resolver under the existing mutex. The shim and the portal need no change. Milestone order is re-sequenced (tracking before the detector) and recorded in the spec changelog.

**Tech Stack:** C++17, CMake, nlohmann/json (vendored), Python 3 (golden generation), Ultralytics 8.4.115 + Hailo DFC 5.3.0 in `/media/bhanu1234/Development/hailo-export/venv` (detector recompile, background), `hailortcli` on the board.

**Spec:** `docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md` §4 steps 3–4 (tracking/lock), §5 (models, bench gate), §8 (milestones — this plan re-sequences M1/M2; see Task 8).

## Global Constraints

- Tracker parameters are mono's, verbatim: `ByteTracker(high_thr=0.4, low_thr=0.12, iou_thr=0.3, max_lost=25, min_hits=2)`; `REACQ = 5` coasting frames before yielding to a live same-class track; default target class `"person"`; detections below `CONF = 0.15` never reach the tracker (the stock post-process already floors at 0.38, so this is a no-op until M2's detector).
- Parity is a test: every tracker/lock behaviour is compared against the Python reference on identical inputs (golden JSON). Reference copies are byte-identical to `feat/portal-tracking` sources and never edited.
- Snapshot schema unchanged (v2). `tracks[].id` = ByteTrack id, `tracks[].coasting` = `time_since_update > 0`, `lock.id/class/coasting` per mono; `distance` stays invalid (depth is M3).
- Node: boxes stay in 1280×720 px; thread discipline unchanged (tracker + resolver live in the detection callback thread; commands only set pending state under `state.mu`).
- Rule 1: no performance figure anywhere unless from a run on the board recorded in `bench/benchlog.md` with conditions. Rule 6: no new dependency (the recompile uses existing tools).
- Branch `feat/hailo15l-tracking` in a worktree, based on `feat/hailo15l-perception` (M0, PR #1). Board `root@10.0.0.1`; PC profile `nmcli con up h15-link`; service `/etc/init.d/garuda-perception`; deploy `hosts/hailo15l/deploy.sh`. Anchored `pkill -f` only; never `pkill -x` long names; never a `pkill -f` pattern that matches your own shell.
- Commit trailer on every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_015dfMKyBmLK5bdtwfFmzgHq`.

---

## File structure

```
services/garuda-perception/
  include/garuda/bytetrack.hpp      # Det, Track, ByteTracker (port of bytetrack.py)
  src/bytetrack.cpp
  include/garuda/lock.hpp           # LockResolver (port of mono's lock/coast/re-acquire + click/target)
  src/lock.cpp
  src/node_main.cpp                 # det_sink feeds tracker + resolver; commands set pending click/target
  tests/golden/bytetrack_ref.py     # byte-identical copy of feat/portal-tracking:services/garuda-track/bytetrack.py
  tests/golden/mono_lock_ref.py     # mono's lock/click/target rules lifted verbatim (functions), origin cited
  tests/golden/make_track_golden.py # scenario -> golden JSON via the references
  tests/golden/track_scenario.json  # generated, committed
  tests/golden/track_golden.json    # generated, committed
  tests/test_bytetrack.cpp
  tests/test_lock.cpp
models/
  yolo26m_h15l.md                   # model card for the recompiled detector (no numbers except benchlog refs)
hosts/hailo15l/
  build_yolo26m_h15l.sh             # the recompile recipe (PC), idempotent
```

---

### Task 0: Kick off the detector recompile in the background (PC)

**Files:**
- Create: `hosts/hailo15l/build_yolo26m_h15l.sh`

**Interfaces:**
- Produces: `/media/bhanu1234/Development/hailo-export/work-h15l/yolo26m_hailo_model/yolo26m.hef` (target `hailo15l`, 640×640 input, level-2 PTQ, 1024 calibration images from `datasets/depth-calib.yaml`) and a log `work-h15l/export_yolo26m_h15l.log`. Task 7 consumes it.

- [ ] **Step 1: Write the recipe (mirrors `models/build_yolo26_depth_hef.sh`, separate work dir so the 10H artifact is never overwritten)**

`hosts/hailo15l/build_yolo26m_h15l.sh`:
```bash
#!/usr/bin/env bash
# Recompile yolo26m for the Hailo-15L (640x640, level-2 PTQ, 1024 calib images). Runs on the PC (DFC never on-device).
# Idempotent: re-running reuses the copied weights and overwrites only work-h15l/. Takes tens of minutes on the RTX 3060.
set -euo pipefail
ROOT=${GARUDA_HAILO_EXPORT:-/media/bhanu1234/Development/hailo-export}
W="$ROOT/work-h15l"; mkdir -p "$W" "$ROOT/tmp"
export TMPDIR="$ROOT/tmp" XDG_CACHE_HOME="$ROOT/.cache"
[ -f "$W/yolo26m.pt" ] || cp "$ROOT/work/yolo26m.pt" "$W/yolo26m.pt"
cd "$W"
"$ROOT/venv/bin/yolo" export model=yolo26m.pt format=hailo name=hailo15l imgsz=640 data="$ROOT/datasets/depth-calib.yaml" 2>&1 | tee "$W/export_yolo26m_h15l.log"
echo "HEF + metadata in: $W/yolo26m_hailo_model/"
```

- [ ] **Step 2: Start it detached and confirm it is running**

Run:
```bash
chmod +x hosts/hailo15l/build_yolo26m_h15l.sh
nohup hosts/hailo15l/build_yolo26m_h15l.sh > /media/bhanu1234/Development/hailo-export/work-h15l-launch.log 2>&1 < /dev/null &
sleep 30; tail -5 /media/bhanu1234/Development/hailo-export/work-h15l-launch.log
```
Expected: Ultralytics banner, `hailo export requires INT8 quantization`, then `Hailo HW architecture: hailo15l` within a few minutes. If it prints `hailo10h`, stop the process (its pid from `pgrep -f "^/media/bhanu1234/Development/hailo-export/venv/bin/python.*yolo export"` — anchored) and report BLOCKED: the `name=` argument did not select the target.

- [ ] **Step 3: Commit the recipe** — `git add hosts/hailo15l/build_yolo26m_h15l.sh && git commit -m "feat(hailo15l): yolo26m recompile recipe for hailo15l (background job; artifact consumed by the bench task)"` + trailer.

---

### Task 1: Reference copies, scenario, and golden generator (Python)

**Files:**
- Create: `services/garuda-perception/tests/golden/bytetrack_ref.py` (byte-identical copy), `mono_lock_ref.py`, `make_track_golden.py`, `track_scenario.json`, `track_golden.json`

**Interfaces:**
- Produces: `track_scenario.json` = `{"frames": [ {"dets": [[x,y,w,h,label,conf], ...], "click": [cx,cy] | null, "target": "cls" | null }, ... ]}`; `track_golden.json` = `{"frames": [ {"tracks": [[id,label,x,y,w,h,conf,coasting], ...], "lock_id": int|null, "lock_class": str, "coasting": bool}, ... ]}`. Track order = the reference's `alive` order.

- [ ] **Step 1: Reference copy of the tracker**

Run: `git show feat/portal-tracking:services/garuda-track/bytetrack.py > services/garuda-perception/tests/golden/bytetrack_ref.py` (from the worktree root; plain command) and verify `git show feat/portal-tracking:services/garuda-track/bytetrack.py | diff - services/garuda-perception/tests/golden/bytetrack_ref.py` prints nothing.

- [ ] **Step 2: Lift mono's lock/click/target rules verbatim into functions**

`services/garuda-perception/tests/golden/mono_lock_ref.py` (the bodies are lifted from `feat/portal-tracking:hosts/pi5/garuda_mono.py` lines 229–249 and 487–512 — keep the expressions identical; only the surrounding function scaffolding is new):
```python
"""Reference for the C++ LockResolver: mono's lock/coast/re-acquire loop and click/target handlers,
lifted verbatim from feat/portal-tracking:hosts/pi5/garuda_mono.py (loop body lines 229-249, POST handlers 487-512).
Constants as mono runs them: MAX_LOST=25, REACQ=5, default class "person"."""
MAX_LOST, REACQ = 25, 5

def step_lock(tracker, lid, want_cls):
    """One frame after tracker.update(): returns (lid, coasting, alive) exactly as mono computes them."""
    alive = [t for t in tracker.tracks if t.confirmed and t.time_since_update <= MAX_LOST]
    locked = next((t for t in alive if t.track_id == lid), None) if lid is not None else None
    if locked is None and want_cls:
        cands = [t for t in alive if t.cls == want_cls]
        if cands:
            locked = max(cands, key=lambda t: (t.time_since_update == 0, t.conf))
    elif locked is not None and locked.time_since_update > REACQ and want_cls:
        live = [t for t in alive if t.cls == want_cls and t.time_since_update == 0]
        if live:
            locked = max(live, key=lambda t: t.conf)
    lid = locked.track_id if locked is not None else None
    coasting = (locked.time_since_update > 0) if locked is not None else False
    return lid, coasting, alive

def click(tracks_full, cx, cy):
    """mono's /api/mono_click: prefer the smallest box under the click, else the nearest centre. Returns (tid, label) or None."""
    picked, best_key = None, None
    for tid, lbl, x, y, w, h, *_ in tracks_full:
        inside = (x <= cx <= x + w) and (y <= cy <= y + h)
        d2 = (x + w / 2 - cx) ** 2 + (y + h / 2 - cy) ** 2
        key = (0, w * h) if inside else (1, d2)
        if best_key is None or key < best_key:
            best_key, picked = key, (tid, lbl)
    return picked

def tracks_full_of(alive):
    return [(t.track_id, t.cls, t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3], float(t.conf), t.time_since_update > 0) for t in alive]
```

- [ ] **Step 3: Scenario builder + golden generator**

`services/garuda-perception/tests/golden/make_track_golden.py`:
```python
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
# 7) second person vanishes for 7 frames while the first is live -> after REACQ frames the lock jumps to the live one
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
```
Run: `python3 services/garuda-perception/tests/golden/make_track_golden.py` — Expected: `68 frames -> .../track_golden.json`. Sanity-check the golden by eye: frame 1 has one track id 1 (confirmed at min_hits=2), frames 14–16 show `coasting: true` with `lock_id: 1`, frame 20's `lock_id` is 2, by frame 30 `lock_id` is back to 1, frame 31 has `lock_id: null` with `lock_class: "vehicle"`, and frames 35+ lock the vehicle track; the last frames have `tracks: []` and `lock_id: null`.

- [ ] **Step 4: Commit** — `git add services/garuda-perception/tests/golden && git commit -m "test(perception): tracker/lock parity references (byte-identical bytetrack, mono lock rules) + scenario golden"` + trailer.

---

### Task 2: ByteTrack port with golden test

**Files:**
- Create: `services/garuda-perception/include/garuda/bytetrack.hpp`, `src/bytetrack.cpp`, `tests/test_bytetrack.cpp`
- Modify: `services/garuda-perception/CMakeLists.txt` (core sources), `tests/CMakeLists.txt`

**Interfaces:**
- Produces:
  ```cpp
  namespace garuda {
  struct Det { double x, y, w, h; std::string label; double conf; };
  struct Track {
      int track_id; double bbox[4]; std::string cls; double conf;
      double vel[2]; double last_x, last_y; int age, hits, time_since_update; int min_hits;
      bool confirmed() const { return hits >= min_hits; }
  };
  class ByteTracker {
  public:
      ByteTracker(double high_thr = 0.5, double low_thr = 0.1, double iou_thr = 0.3, int max_lost = 30, int min_hits = 3);
      std::vector<const Track*> update(const std::vector<Det>& dets);   // returns live+confirmed tracks (same as Python)
      const std::vector<Track>& tracks() const;                          // all kept tracks, in Python's list order
  };
  double iou_xywh(const double a[4], const double b[4]);
  }
  ```

- [ ] **Step 1: Write the failing test**

`services/garuda-perception/tests/test_bytetrack.cpp`:
```cpp
#undef NDEBUG
#include "garuda/bytetrack.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>

// Tracker-only parity: replay the scenario and compare the alive set (confirmed && tsu<=25) per frame with the golden's
// tracks (id, label, bbox, conf, coasting). Lock fields are checked by test_lock.
int main(int argc, char** argv) {
    assert(argc == 3);
    nlohmann::json sc, gd; std::ifstream(argv[1]) >> sc; std::ifstream(argv[2]) >> gd;
    garuda::ByteTracker tr(0.4, 0.12, 0.3, 25, 2);
    size_t n = sc["frames"].size(); assert(n == gd["frames"].size());
    for (size_t i = 0; i < n; ++i) {
        std::vector<garuda::Det> dets;
        for (auto& d : sc["frames"][i]["dets"]) if (d[5].get<double>() >= 0.15)
            dets.push_back({d[0], d[1], d[2], d[3], d[4].get<std::string>(), d[5]});
        tr.update(dets);
        std::vector<const garuda::Track*> alive;
        for (auto& t : tr.tracks()) if (t.confirmed() && t.time_since_update <= 25) alive.push_back(&t);
        auto& want = gd["frames"][i]["tracks"];
        if (alive.size() != want.size()) { std::cerr << "frame " << i << ": " << alive.size() << " tracks, golden " << want.size() << "\n"; return 1; }
        for (size_t k = 0; k < alive.size(); ++k) {
            auto& w = want[k]; const garuda::Track* t = alive[k];
            bool ok = t->track_id == w[0].get<int>() && t->cls == w[1].get<std::string>()
                   && std::fabs(t->bbox[0] - w[2].get<double>()) < 1e-9 && std::fabs(t->bbox[1] - w[3].get<double>()) < 1e-9
                   && std::fabs(t->bbox[2] - w[4].get<double>()) < 1e-9 && std::fabs(t->bbox[3] - w[5].get<double>()) < 1e-9
                   && std::fabs(t->conf - w[6].get<double>()) < 1e-9 && (t->time_since_update > 0) == w[7].get<bool>();
            if (!ok) { std::cerr << "frame " << i << " track " << k << " mismatch: id " << t->track_id << " vs " << w[0] << "\n"; return 1; }
        }
    }
    // unit cases from the Pi's test_bytetrack.py
    garuda::ByteTracker t2(0.5, 0.1, 0.3, 30, 1);
    std::vector<double> vx;
    for (int x = 0; x < 50; x += 10) { auto out = t2.update({{(double)x, 0, 20, 20, "0", 0.9}}); assert(out.size() == 1 && out[0]->track_id == 1); vx.push_back(out[0]->vel[0]); }
    assert(vx[0] == 0.0); for (size_t i = 1; i < vx.size(); ++i) assert(vx[i] == 10.0);   // steady displacement, not oscillating
    garuda::ByteTracker t3(0.5, 0.1, 0.3, 2, 1); t3.update({{0, 0, 20, 20, "0", 0.9}});
    std::vector<const garuda::Track*> last; for (int i = 0; i < 4; ++i) last = t3.update({});
    assert(last.empty());                                                                // culled after max_lost
    std::cout << "bytetrack parity ok (" << n << " frames)\n"; return 0;
}
```
CMake (tests): `add_executable(test_bytetrack test_bytetrack.cpp)`, link `garuda_perception_core`, `add_test(NAME bytetrack COMMAND test_bytetrack ${CMAKE_CURRENT_SOURCE_DIR}/golden/track_scenario.json ${CMAKE_CURRENT_SOURCE_DIR}/golden/track_golden.json)`.

- [ ] **Step 2: Run to verify it fails** — Expected: `garuda/bytetrack.hpp: No such file or directory`.

- [ ] **Step 3: Implement (a faithful port; comments cite the Python line each block mirrors)**

`include/garuda/bytetrack.hpp`:
```cpp
#pragma once
#include <string>
#include <vector>
namespace garuda {
struct Det { double x, y, w, h; std::string label; double conf; };
struct Track {
    int track_id; double bbox[4]; std::string cls; double conf;
    double vel[2]; double last_x, last_y; int age, hits, time_since_update; int min_hits;
    bool confirmed() const { return hits >= min_hits; }
    void predict();                                            // bytetrack.py Track.predict
    void update(const double b[4], const std::string& c, double s); // bytetrack.py Track.update
};
double iou_xywh(const double a[4], const double b[4]);
class ByteTracker {
public:
    ByteTracker(double high_thr = 0.5, double low_thr = 0.1, double iou_thr = 0.3, int max_lost = 30, int min_hits = 3);
    std::vector<const Track*> update(const std::vector<Det>& dets);
    const std::vector<Track>& tracks() const { return m_tracks; }
private:
    double m_high, m_low, m_iou; int m_max_lost, m_min_hits; int m_next_id = 1;
    std::vector<Track> m_tracks;
};
}
```

`src/bytetrack.cpp`:
```cpp
#include "garuda/bytetrack.hpp"
#include <algorithm>
#include <set>
#include <tuple>
namespace garuda {
double iou_xywh(const double a[4], const double b[4]) {                       // _iou
    double x1 = std::max(a[0], b[0]), y1 = std::max(a[1], b[1]);
    double x2 = std::min(a[0] + a[2], b[0] + b[2]), y2 = std::min(a[1] + a[3], b[1] + b[3]);
    double inter = std::max(0.0, x2 - x1) * std::max(0.0, y2 - y1);
    double uni = a[2] * a[3] + b[2] * b[3] - inter;
    return uni > 0 ? inter / uni : 0.0;
}
void Track::predict() { bbox[0] += vel[0]; bbox[1] += vel[1]; age += 1; time_since_update += 1; }
void Track::update(const double b[4], const std::string& c, double s) {
    double nx = b[0], ny = b[1];
    vel[0] = nx - last_x; vel[1] = ny - last_y;                                  // displacement since last update
    last_x = nx; last_y = ny;
    bbox[0] = nx; bbox[1] = ny; bbox[2] = b[2]; bbox[3] = b[3];
    cls = c; conf = s; hits += 1; time_since_update = 0;
}
ByteTracker::ByteTracker(double h, double l, double i, int ml, int mh) : m_high(h), m_low(l), m_iou(i), m_max_lost(ml), m_min_hits(mh) {}

// _greedy_match: pairs sorted by descending IoU (ties: Python sorts tuples (v, ti, di) descending -> larger ti, then larger di first)
static void greedy_match(const std::vector<Track*>& tracks, const std::vector<const Det*>& dets, double thr,
                         std::vector<std::pair<int,int>>& matches, std::set<int>& ut, std::set<int>& ud) {
    std::vector<std::tuple<double,int,int>> pairs;
    for (int ti = 0; ti < (int)tracks.size(); ++ti)
        for (int di = 0; di < (int)dets.size(); ++di) {
            double b[4] = {dets[di]->x, dets[di]->y, dets[di]->w, dets[di]->h};
            double v = iou_xywh(tracks[ti]->bbox, b);
            if (v >= thr) pairs.emplace_back(v, ti, di);
        }
    std::sort(pairs.begin(), pairs.end(), [](auto& a, auto& b) { return a > b; });   // Python: pairs.sort(reverse=True)
    for (int i = 0; i < (int)tracks.size(); ++i) ut.insert(i);
    for (int i = 0; i < (int)dets.size(); ++i) ud.insert(i);
    for (auto& [v, ti, di] : pairs) if (ut.count(ti) && ud.count(di)) { matches.emplace_back(ti, di); ut.erase(ti); ud.erase(di); }
}

std::vector<const Track*> ByteTracker::update(const std::vector<Det>& dets) {
    for (auto& t : m_tracks) t.predict();
    std::vector<const Det*> high, low;
    for (auto& d : dets) { if (d.conf >= m_high) high.push_back(&d); else if (d.conf >= m_low) low.push_back(&d); }
    std::vector<Track*> all; for (auto& t : m_tracks) all.push_back(&t);
    std::vector<std::pair<int,int>> m1; std::set<int> ut, ud;
    greedy_match(all, high, m_iou, m1, ut, ud);                                       // stage 1
    for (auto& [ti, di] : m1) { double b[4] = {high[di]->x, high[di]->y, high[di]->w, high[di]->h}; all[ti]->update(b, high[di]->label, high[di]->conf); }
    std::vector<Track*> rem; for (int i : ut) rem.push_back(all[i]);                  // set iteration ascending == Python set order for small ints
    std::vector<std::pair<int,int>> m2; std::set<int> ut2, ud2;
    greedy_match(rem, low, m_iou, m2, ut2, ud2);                                      // stage 2
    for (auto& [ti, di] : m2) { double b[4] = {low[di]->x, low[di]->y, low[di]->w, low[di]->h}; rem[ti]->update(b, low[di]->label, low[di]->conf); }
    for (int di : ud) {                                                               // births (ascending di == Python set order)
        const Det* d = high[di]; Track t{};
        t.track_id = m_next_id++; t.bbox[0] = d->x; t.bbox[1] = d->y; t.bbox[2] = d->w; t.bbox[3] = d->h;
        t.cls = d->label; t.conf = d->conf; t.vel[0] = t.vel[1] = 0.0; t.last_x = d->x; t.last_y = d->y;
        t.age = 1; t.hits = 1; t.time_since_update = 0; t.min_hits = m_min_hits; m_tracks.push_back(t);
    }
    m_tracks.erase(std::remove_if(m_tracks.begin(), m_tracks.end(), [&](const Track& t) { return t.time_since_update > m_max_lost; }), m_tracks.end());
    std::vector<const Track*> out; for (auto& t : m_tracks) if (t.time_since_update == 0 && t.confirmed()) out.push_back(&t);
    return out;
}
}
```
Two parity notes to honour in the port: (a) Python's `ut`/`ud` are sets of small ints iterated in ascending order — `std::set<int>` matches; (b) `pairs.sort(reverse=True)` on `(v, ti, di)` tuples — the comparator above sorts descending on the whole tuple, which is what Python does. Add `src/bytetrack.cpp` to the core library sources.

- [ ] **Step 4: Run tests** — Expected: `bytetrack ... Passed` printing `bytetrack parity ok (68 frames)`. If a frame mismatches, print both sides' track lists for that frame and compare with the Python by running `python3 tests/golden/make_track_golden.py` with a debug print — do not loosen tolerances.

- [ ] **Step 5: Commit** — `feat(perception): ByteTrack port (line-for-line from mono's bytetrack.py) with 68-frame golden parity test`.

---

### Task 3: Lock resolver port with golden test

**Files:**
- Create: `services/garuda-perception/include/garuda/lock.hpp`, `src/lock.cpp`, `tests/test_lock.cpp`
- Modify: CMake lists

**Interfaces:**
- Produces:
  ```cpp
  namespace garuda {
  struct LockResult { std::optional<int> lock_id; std::string lock_class; bool coasting; std::vector<const Track*> alive; };
  class LockResolver {                       // port of garuda_mono.py lines 229-249 (step) and 487-512 (click/target)
  public:
      LockResolver(int max_lost = 25, int reacq = 5, std::string default_class = "person");
      LockResult step(const ByteTracker& tracker);                     // after tracker.update() each frame
      bool click(double cx, double cy);                                // uses the tracks published by the previous step(); returns picked?
      void set_target(const std::string& cls);                         // sets class (empty -> "person"), clears the lock
      std::optional<int> lock_id() const; const std::string& target_class() const;
  };
  }
  ```

- [ ] **Step 1: Write the failing test** — `tests/test_lock.cpp` replays the scenario through `ByteTracker` + `LockResolver`, applying `target` then `click` before `update` exactly as `make_track_golden.py` does, and asserts per frame `lock_id`, `lock_class`, `coasting` against the golden (and the alive list length as a cross-check). Register as test `lock` with the two golden paths.

- [ ] **Step 2: Run to verify it fails** — missing header.

- [ ] **Step 3: Implement**

`src/lock.cpp` core (`step`):
```cpp
LockResult LockResolver::step(const ByteTracker& tracker) {
    LockResult r; r.lock_class = m_class;
    for (auto& t : tracker.tracks()) if (t.confirmed() && t.time_since_update <= m_max_lost) r.alive.push_back(&t);   // alive
    const Track* locked = nullptr;
    if (m_lid) for (auto* t : r.alive) if (t->track_id == *m_lid) { locked = t; break; }
    if (!locked && !m_class.empty()) {                                   // acquire best of class: live first, then conf
        for (auto* t : r.alive) if (t->cls == m_class) {
            if (!locked) { locked = t; continue; }
            bool tl = t->time_since_update == 0, ll = locked->time_since_update == 0;
            if (std::make_pair(tl, t->conf) > std::make_pair(ll, locked->conf)) locked = t;   // Python max(key=(tsu==0, conf)) keeps the FIRST max
        }
    } else if (locked && locked->time_since_update > m_reacq && !m_class.empty()) {
        const Track* best = nullptr;
        for (auto* t : r.alive) if (t->cls == m_class && t->time_since_update == 0 && (!best || t->conf > best->conf)) best = t;
        if (best) locked = best;
    }
    m_lid = locked ? std::optional<int>(locked->track_id) : std::nullopt;
    r.lock_id = m_lid; r.coasting = locked ? locked->time_since_update > 0 : false;
    m_prev.clear(); for (auto* t : r.alive) m_prev.push_back({t->track_id, t->cls, {t->bbox[0], t->bbox[1], t->bbox[2], t->bbox[3]}});
    return r;
}
```
Parity detail: Python's `max()` returns the first maximal element; the comparisons above use strict `>` so ties keep the earlier track — same behaviour. `click()` implements the `(0, w*h)` / `(1, d2)` key with the same strict `<` ordering and, on a pick, sets `m_lid` and `m_class = label`. `set_target(cls)` sets `m_class = cls.empty() ? "person" : cls` and clears `m_lid`.

- [ ] **Step 4: Run tests** — `lock ... Passed`; all frames match, including the click at frame 20, the re-acquire by frame 30, the cleared lock at 31, the vehicle auto-acquire, and the final death.

- [ ] **Step 5: Commit** — `feat(perception): lock/coast/re-acquire + click/target resolver ported from garuda_mono.py, golden-tested`.

---

### Task 4: Node integration — persistent tracks and lock on the board

**Files:**
- Modify: `services/garuda-perception/src/node_main.cpp`, `config/perception.json` (add `"track": {"high_thr":0.4,"low_thr":0.12,"iou_thr":0.3,"max_lost":25,"min_hits":2,"reacq":5,"conf_floor":0.15,"default_class":"person"}`)

**Interfaces:**
- Consumes: `ByteTracker`, `LockResolver`. Produces: snapshots whose `tracks[].id` persist across frames with `coasting`, and `lock` per mono; commands `lock_point` → pending click, `target` → pending class, both consumed in the detection callback under `state.mu`.

- [ ] **Step 1: Wire it** — in `det_sink`: build `std::vector<Det>` from the ROI detections (px, label, conf; drop `conf < conf_floor`), `tracker.update(dets)`, then under `state.mu` apply pending target/click (`resolver.set_target`, `resolver.click(x, y)`), then `auto lr = resolver.step(tracker)`; fill `s.tracks` from `lr.alive` (`{id, cls, conf, bbox..., coasting = tsu>0}`), `s.lock_id = lr.lock_id`, `s.lock_class = lr.lock_class`, `s.lock_coasting = lr.coasting`. The `target` command handler stores the class in `state.pending_target` (empty string allowed → "person" per mono); `lock_point` stores the point. Remove the M0 per-frame index ids and the M0 point-in-box lock. Keep the scaling comment.
- [ ] **Step 2: Cross-build, deploy (`hosts/hailo15l/deploy.sh`), verify on the board with a person in view** (the operator stands in front of the camera; if nobody is available, use the laptop with the traffic video and the `vehicle` class):
  ```bash
  curl -s http://10.0.0.1:8098/api/state | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['lock'], [(t['id'],t['label'],t['coasting']) for t in d['tracks']])"
  # expect: lock id set automatically (default class person) and stable ids across repeated calls
  curl -s -X POST "http://10.0.0.1:8098/api/mono_target?class=vehicle"   # lock clears if no vehicle
  curl -s -X POST "http://10.0.0.1:8098/api/mono_click?x=<cx>&y=<cy>"    # centre of a visible box -> lock.id == that id, class follows
  ```
  Then have the person step out of frame for ~1 s and back: `lock.coasting` turns true while out (≤25 frames), the id survives, and the tracks list shows `coasting: true`. Paste raw outputs.
- [ ] **Step 3: Commit** — `feat(perception): tracker + lock in the node — persistent ids, coast/re-acquire, click/target parity`.

---

### Task 5: Portal check and the tracking clip for future replay

- [ ] **Step 1:** With the portal running on the PC against the board (README procedure incl. the `ssh -N -L 8098:127.0.0.1:8098` forward), confirm in the Tracking tab: click a person → the highlight persists; walk out and back → dimmed (coasting) then restored; change the class dropdown to one the stock model lacks → lock clears. Record what was observed in `hosts/hailo15l/README.md` under "Tracking parity check (M1)".
- [ ] **Step 2 (cheap, enables the spec's file-source replay later):** add a config flag `"dump_nv12": {"path": "", "frames": 0}` to the node; when set, `det_sink` writes the first N `sink0` NV12 frames (Y then UV planes, stride-packed) to the path and logs `dumped N frames to <path>`; document the resulting file layout (640×384 NV12, 30 fps) in the README. Capture a 10 s clip with a person walking in and out to `/opt/garuda/state/clip-640x384.nv12`, copy it to the PC under `/media/bhanu1234/Development/hailo15/clips/` (not committed; note the path in decisions.md).
- [ ] **Step 3: Commit** — docs + the dump flag.

---

### Task 6: Bench — tracking cost and behaviour, recorded

- [ ] **Step 1:** 10-minute run as in M0's Task 11 (same commands), with the tracker active and a person moving in/out of view for at least the first two minutes: record `frames=` lines, CPU (`top` with the corrected grep), thermal, RAM, and from the SSE capture the count of frames with `lock.coasting == true` and the set of distinct `lock.id` values seen (a small Python tally over the captured `data:` lines). Numbers verbatim into `bench/benchlog.md` under `## 2026-09-xx — Hailo-15L SBC: M1 tracking parity`, beside the M0 numbers for the same node without the tracker (rule 9: state the scene and that the person's movement is not reproducible).
- [ ] **Step 2:** `bench/versions.md` sub-entry (node commit, unchanged toolchain), `docs/decisions.md` (what the port taught: Python `max()` first-max semantics, set-order parity, the click-uses-previous-frame rule), `CLAUDE.md` §7 one line.
- [ ] **Step 3: Commit** — `bench(hailo15l): M1 tracking parity run`.

---

### Task 7: Detector artifact — check, benchmark, model card (no integration)

- [ ] **Step 1:** Confirm Task 0 finished: `tail -3 /media/bhanu1234/Development/hailo-export/work-h15l/export_yolo26m_h15l.log` shows `export success` and `ls -l work-h15l/yolo26m_hailo_model/yolo26m.hef`; `hailortcli parse-hef` on the PC is not available — copy the HEF to the board (`/opt/garuda/models/yolo26m_h15l.hef`) and run `hailortcli parse-hef` there: paste the input/output shapes (expect 640×640 NV12 input and six raw heads).
- [ ] **Step 2:** With the service stopped (`/etc/init.d/garuda-perception stop`), `hailortcli benchmark /opt/garuda/models/yolo26m_h15l.hef -t 15` — full output verbatim into the M1 benchlog section beside the stock yolov8n/s numbers; then `start` the service.
- [ ] **Step 3:** `models/yolo26m_h15l.md` model card: source weights (`yolo26m.pt`, Ultralytics 8.4.115, AGPL-3.0 — bench/eval only, `not-product-cleared`), DFC 5.3.0, target `hailo15l`, imgsz 640, level-2 PTQ, calibration set `depth-calib.yaml` (1024 images), the recipe path, the benchlog reference for numbers, and "integration = M2 (post-process port)". If Task 0 failed, the card records the failure and the log excerpt, and Step 2 is skipped.
- [ ] **Step 4: Commit** — `models(hailo15l): yolo26m recompiled for hailo15l — parse + benchmark recorded, not integrated`.

---

### Task 8: Spec re-sequencing and memory

- [ ] **Step 1:** Spec changelog line dated on the day: "Milestones re-sequenced after M0 (owner decision 2026-09-02): M1 = tracking and lock parity; M2 = our yolo26m detector + post-process; M3 = depth, calibration, distance; M4 = packaging and the Pi-vs-15L delta table." Update §8's numbered list to match (keep each milestone's text).
- [ ] **Step 2:** Update `~/.claude/projects/-media-bhanu1234-Development-GARUDASDK/memory/h15-kickoff-2026-09-01.md` (M1 done, branch, what changed, next = M2 plan) and the MEMORY.md index line.
- [ ] **Step 3: Commit** — `docs: spec milestone re-sequencing (tracking first)`.

---

## Self-review

- **Spec coverage:** §4 step 3 (ByteTrack + lock FSM "ported line for line", coast, 5-frame re-acquire, `select_by_point`) → Tasks 1–4; note mono's real lock logic is the inline loop in `garuda_mono.py`, not `garuda-track/lock_fsm.py` (which mono does not use) — the plan ports what the owner verified. §5 measurement → Tasks 6–7; §7 unit parity + integration replay groundwork → Tasks 1–3, 5; §8 re-sequencing → Task 8. Depth/distance stay invalid by design (M3).
- **Placeholders:** none; the only conditional (Task 0 failing) has its branch in Task 7.
- **Type consistency:** `Det{x,y,w,h,label,conf}` and `Track` fields are used identically in Tasks 2–4; `LockResult` fields match Task 4's snapshot mapping; JSON scenario/golden layouts match between Task 1's generator and Tasks 2–3's tests; config keys in Task 4 are the only new config.
