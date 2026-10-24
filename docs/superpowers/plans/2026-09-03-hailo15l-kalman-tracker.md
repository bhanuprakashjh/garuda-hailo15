# Hailo-15L Perception Node — Kalman tracker engine (follow-grade tracking) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second tracker engine on the board, selected by config, that uses the SDK's Kalman tracker (the one the stock demo runs) so that a small fast target (a hand-held phone today, a person seen from a drone tomorrow) keeps its id across detection gaps and a coasting box never flies off-screen; measured against today's three phone runs.

**Architecture:** `tracker.engine` selects `"mono"` (the existing ByteTrack port, Pi parity) or `"hailo"`. For `"hailo"` the pipeline gains the SDK's `TrackerStage` between the post-process and the detection callback (leaky, queue 1); the stage attaches a `HailoUniqueID` to each detection. A small core-library adapter (`HailoTrackAdapter`) turns per-frame `(id, label, conf, box)` lists into track records with `time_since_update`, keeping a missing id alive for `keep_lost_frames` with its box FROZEN at the last seen position (coasting = missing this frame). The lock resolver gains a record-based `step()` so both engines feed the same lock/coast/re-acquire/click/target rules; the ByteTrack path is unchanged and its golden tests stay green. Tracker parameters come from a `tracker.hailo` config block applied through the SDK's `HailoTracker` singleton setters.

**Tech Stack:** C++17, CMake (native tests + cross-build with the Hailo-15L SDK), nlohmann/json, `hailo_analytics` `TrackerStage` + `hailo_postprocess_tools` `HailoTracker` (board SDK), the M1 capture/timeline scripts for the bench.

**Spec:** `docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md` §8.1 (follow roadmap) — this plan implements the tracker half of "follow" early, on the owner's decision of 2026-09-03 (~16:00) after the yolov8m A/B (`bench/benchlog.md` "yolov8m A/B for small-object tracking") showed the detector is not the cause of runaway coasting boxes.

## Global Constraints

- **Amended after the final review (2026-09-04):** this plan defined no pass/fail gate (ids per minute, lock jumps, gap survival) and did not require committing the captures it tallies — both are corrected in the fix wave and the F1 plan carries explicit metrics (its harness).

- The `"mono"` engine is untouched in behaviour: `tests/test_bytetrack.cpp` and `tests/test_lock.cpp` (golden parity with the Pi) stay green; the resolver's existing `step(const ByteTracker&)` keeps its semantics and becomes a thin wrapper over the new record-based `step`.
- Coasting boxes under the `"hailo"` engine never move: a missing id is reported with its last seen box, `coasting: true`, for at most `keep_lost_frames` frames, then dropped. No velocity extrapolation in our layer (the Kalman prediction inside the SDK tracker is for association only). **AMENDED after the final review (2026-09-04): false as stated — the SDK's prediction also decides which tracks are EMITTED: an unmatched track is still emitted with its last matched box for up to `keep_tracked_frames` frames, so our layer sees it as live. The follow profile therefore sets `keep_tracked_frames 0` (fix wave); the adapter's freeze then starts on the first missed frame.**
- Snapshot schema unchanged (v2). Threading contract unchanged: adapter and resolver live in the detection callback thread; commands only set pending state under `state.mu`.
- SDK facts (verified in the headers): `hailo_analytics/pipeline/ai/tracker_stage.hpp` — `TrackerStageBuild::create().set_stage_name(...).set_queue_size_opt(n).set_leaky_opt(bool).set_classification_id(int).set_block_non_tracked_classification_id(bool).buildptr()`; the stage owns a tracker named `"hailo_tracker"` created with default `HailoTrackerParams` at `init()`. `hailo_postprocess_tools/tracking/hailo_tracker.hpp` — `HailoTracker::GetInstance()` with `set_kalman_distance(name, f)`, `set_iou_threshold(name, f)`, `set_init_iou_threshold(name, f)`, `set_keep_tracked_frames(name, n)`, `set_keep_new_frames(name, n)`, `set_keep_lost_frames(name, n)`; defaults `DEFAULT_KALMAN_DISTANCE 0.7f`, `DEFAULT_IOU_THRESHOLD 0.8f`, `DEFAULT_INIT_IOU_THRESHOLD 0.9f`, `DEFAULT_KEEP_FRAMES 5`, `DEFAULT_STD_WEIGHT_POSITION 0.01`, `DEFAULT_STD_WEIGHT_VELOCITY 0.001`. `hailo_postprocess_tools/objects/hailo_common.hpp:179` — `get_hailo_unique_id(HailoROIPtr)` returns the `HailoUniqueID` objects attached to a detection (a `HailoDetection` is a `HailoROI`); `HailoUniqueID::get_id()`.
- Rule 1: every number in docs from a pasted run with conditions; Rule 6: no new dependency (the SDK libraries are on the image); Rule 9: red-team on the measurement.
- Board `root@10.0.0.1`; writes only under `/opt/garuda/`, the init script, rc links, `/var/run`, `/tmp`; deploy via `hosts/hailo15l/deploy.sh` (`GARUDA_PERCEPTION_CONFIG=<file>` selects the config); never `pkill -x`; only anchored `pkill -f "^..."`; never a pattern matching your own shell; do not reboot; do not touch the Pi, the portal, or the SSH tunnel on the PC. Cross-build: source `/media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux`; `cmake -S services/garuda-perception -B services/garuda-perception/build-h15l -G Ninja -DCMAKE_TOOLCHAIN_FILE=$OECORE_NATIVE_SYSROOT/usr/share/cmake/OEToolchainConfig.cmake -DGARUDA_BUILD_NODE=ON -DGARUDA_BUILD_TESTS=OFF`; zero `warning:` lines. Native: `build-x86` at the worktree root, ctest 9 → 10 tests.
- Branch `feat/hailo15l-kalman-tracker` (worktree `.claude/worktrees/feat-hailo15l-detector`), from the M2 head 952a636 + the A/B commit 68ccd3c. Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_015dfMKyBmLK5bdtwfFmzgHq`.

---

## File structure

```
services/garuda-perception/
  include/garuda/track_record.hpp      # garuda::track::TrackRecord — the engine-neutral per-frame record the resolver consumes
  include/garuda/lock.hpp / src/lock.cpp  # LockResult step(const std::vector<TrackRecord>&); step(const ByteTracker&) wraps it
  include/garuda/hailo_track_adapter.hpp / src/hailo_track_adapter.cpp  # HailoTrackAdapter (ids -> records, frozen coasting)
  src/node_main.cpp                    # engine switch; TrackerStage; unique-id read; adapter; params via the singleton
  config/perception-yolov8m.json       # tracker.engine "hailo" + tracker.hailo block (the drone-follow profile)
  config/perception.json               # tracker.engine "mono" (explicit; default when absent)
  tests/test_hailo_track_adapter.cpp   # sequences: gap+return same id, return new id, keep_lost expiry, class switch, min_hits
  tests/test_lock.cpp                  # unchanged golden replay + one case through the record-based step
hosts/hailo15l/README.md               # tracker engines section
bench/benchlog.md                      # Kalman A/B section
```

---

### Task 1: Engine-neutral records, the adapter, the resolver's record-based step (native, tested)

**Files:**
- Create: `include/garuda/track_record.hpp`, `include/garuda/hailo_track_adapter.hpp`, `src/hailo_track_adapter.cpp`, `tests/test_hailo_track_adapter.cpp`
- Modify: `include/garuda/lock.hpp`, `src/lock.cpp`, `tests/test_lock.cpp`, `CMakeLists.txt` (core sources), `tests/CMakeLists.txt`

**Interfaces:**
- Produces:
  ```cpp
  namespace garuda::track {
  struct TrackRecord { int id; std::string cls; double conf; double bbox[4]; int time_since_update; bool confirmed; };
  struct IdDet { int id; std::string label; double conf; double x, y, w, h; };          // one detection carrying the SDK's unique id
  class HailoTrackAdapter {
  public:
      HailoTrackAdapter(int keep_lost_frames = 5, int min_hits = 1);
      // One frame: the detections seen now (with ids). Returns records for every id seen now (tsu=0, its box) and
      // every id missing for 1..keep_lost_frames frames (tsu=k, the LAST SEEN box unchanged); ids missing longer are dropped.
      // confirmed = hits >= min_hits (hits counts frames in which the id was seen). Order: by first-seen order (stable).
      std::vector<TrackRecord> update(const std::vector<IdDet>& seen);
  };
  // LockResolver gains:
  LockResult step(const std::vector<TrackRecord>& records);   // alive = confirmed && tsu <= max_lost, in the given order; rules unchanged
  LockResult step(const ByteTracker& tracker);                // builds records from tracker.tracks() and calls the above (behaviour identical)
  }
  ```
  `LockResult::alive` (a vector of `const Track*`) is replaced by `std::vector<TrackRecord> alive` (copies) so both engines share it; update `node_main.cpp`'s snapshot fill in Task 2 accordingly (in this task, only the tests and the resolver change).

- [ ] **Step 1: Write the failing tests** — `tests/test_hailo_track_adapter.cpp` (assert style as the other tests):
  - gap and return with the same id: frames `[A@x=100]`, `[]`, `[]`, `[A@x=130]` with keep_lost 5 → frame 2 and 3 report A with `tsu` 1, 2 and box x=100 (frozen), frame 4 reports A `tsu` 0 at x=130;
  - expiry: A seen once then absent 6 frames with keep_lost 5 → present (coasting) for frames 2..6, absent from frame 7;
  - return with a new id: A, then B at the same place after A expired → B is a distinct record, A gone;
  - min_hits 2: an id seen once is `confirmed=false` until its second sighting;
  - class switch on the same id (the SDK may relabel): the record's `cls` follows the latest sighting;
  - order stability: ids report in first-seen order across frames.
  In `tests/test_lock.cpp`, after the golden replay, add one case: build records by hand (two persons, one coasting with tsu 3) and check `step(records)` acquires the live one, and that `step(tracker)` and `step(records-built-from-that-tracker)` give identical `lock_id/lock_class/coasting` on one golden frame. Register `hailo_track_adapter` in ctest.
- [ ] **Step 2: Run to verify they fail** — missing headers.
- [ ] **Step 3: Implement** — `HailoTrackAdapter` keeps `std::vector<Entry{ id, cls, conf, bbox[4], tsu, hits, first_seen_seq }>`; `update()` marks all entries missing (tsu+1), then for each seen det: find by id → refresh (tsu=0, hits+1, box/cls/conf) or append; then drop entries with `tsu > keep_lost`; return records in `first_seen_seq` order. `LockResolver::step(records)` is the existing body with `alive` built from records (`confirmed && tsu <= m_max_lost`), and `m_prev` (click targets) filled from the alive records. `step(const ByteTracker&)` converts `tracks()` to records (`id=track_id, cls, conf, bbox, tsu=time_since_update, confirmed=confirmed()`) and calls it.
- [ ] **Step 4: Build + ctest** — 10/10 (the two golden tests unchanged and green), zero warnings.
- [ ] **Step 5: Commit** — `feat(perception): engine-neutral track records, HailoTrackAdapter (frozen coasting), record-based lock step`.

---

### Task 2: Node integration — `tracker.engine`, the SDK TrackerStage, params, deploy, verify

**Files:**
- Modify: `src/node_main.cpp`, `config/perception.json` (add `"tracker": {"engine": "mono"}`), `config/perception-yolov8m.json` (add the `tracker` block below), `hosts/hailo15l/README.md` (tracker engines section)

**Interfaces:**
- Config: `"tracker": {"engine": "hailo", "hailo": {"kalman_distance": 0.7, "iou_threshold": 0.8, "init_iou_threshold": 0.9, "keep_tracked_frames": 5, "keep_new_frames": 5, "keep_lost_frames": 75, "min_hits": 1}}`; defaults = the SDK header defaults with `keep_lost_frames` 75 (matches the M1 coast window at ~25-30 fps) and `min_hits` 1. `engine` absent → `"mono"`.

- [ ] **Step 1: Pipeline** — when `engine == "hailo"`: build `auto tracker = TrackerStageBuild::create().set_stage_name("tracker").set_queue_size_opt(1).set_leaky_opt(true).set_classification_id(-1).set_block_non_tracked_classification_id(false).buildptr();` and connect `post → tracker → det_sink` instead of `post → det_sink` (mono path unchanged). After the pipeline is built (and before start, or at the first frame if the tracker does not exist yet — verify by reading the stage's `init()` behaviour in the header comments and by testing on the board: if a setter throws/ignores because `"hailo_tracker"` is not registered yet, apply the setters from the first `det_sink` frame instead, once), apply the config via `HailoTracker::GetInstance().set_kalman_distance("hailo_tracker", v)`, `set_iou_threshold`, `set_init_iou_threshold`, `set_keep_tracked_frames`, `set_keep_new_frames`, `set_keep_lost_frames`. Log the applied values once.
- [ ] **Step 2: Callback** — in `det_sink`, for `engine == "hailo"`: for each detection, read its unique id (`hailo_common::get_hailo_unique_id(det)`; skip detections without one, count them and log once), build `IdDet{id, label, conf, x,y,w,h}` in frame pixels (same mapping as today), `records = adapter.update(dets)`, then the unchanged pending-command handling, `lr = resolver.step(records)`; fill the snapshot from `lr.alive` (`Track{id, cls, conf, bbox, coasting = tsu > 0}`), lock fields as before. For `engine == "mono"`: the existing ByteTrack path, now through `resolver.step(tracker)` → identical output. The `conf_floor` guard stays before both.
- [ ] **Step 3: Configs** — `perception.json` gets `"tracker": {"engine": "mono"}`; `perception-yolov8m.json` gets the hailo block above.
- [ ] **Step 4: Build, deploy, verify** — native 10/10; cross-build zero warnings; `GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8m.json hosts/hailo15l/deploy.sh`; the log shows the applied tracker params and the stage in the pipeline; `/api/state` polled ~10× over a minute shows tracks with ids (paste); with the owner present, ask nothing — record what is seen. Then verify the mono path still works: deploy the default config (`hosts/hailo15l/deploy.sh`) and paste one state; then redeploy the yolov8m/hailo config and leave the board on it.
- [ ] **Step 5: README** — "Tracker engines" section: the switch, the hailo block and its meaning, frozen coasting, which config uses which, rollback.
- [ ] **Step 6: Commit** — `feat(hailo15l): tracker.engine "hailo" — SDK Kalman TrackerStage + frozen-coast adapter behind the mono lock rules; yolov8m config uses it`.

---

### Task 3: Bench — the phone routine against today's three runs, and docs

- [ ] **Step 1:** With the owner at the bench (the controller coordinates the routine: still 5 s; slow side-to-side 10 s; fast 10 s; out 3 s; back, still 5 s), capture 90 s with `bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py` and run the comparison script used in the yolov8m A/B section (`bench/benchlog.md`, "Three runs" block — reproduce its exact columns: phone ids, lock ids, no-phone states, coasting entries, x range, live conf mean, box w mean, longest lock, age max) on the new capture and the three earlier captures (paths in that section). Paste the four-row table verbatim.
- [ ] **Step 2:** `bench/benchlog.md`: `## 2026-09-03 — Hailo-15L SBC: Kalman tracker engine (SDK TrackerStage) vs mono's tracker, phone routine` — conditions (commit, config, params applied as logged), the table, what changed (ids, off-frame boxes must be absent by construction — state the measured x range), lock stability, snapshot age; red-team (owner-paced routine; single scene; frozen coasting hides motion during gaps by design; the SDK tracker's internals are not ours to inspect; keep_lost 75 vs the M1 window; the stretched yolov8m input). `docs/decisions.md` entry (why a second engine; the SDK tracker facts; what was measured). `CLAUDE.md` §7 one sentence. Spec §8.1: one sentence that the tracker half of "follow" landed early.
- [ ] **Step 3: Commit** — `bench(hailo15l): Kalman tracker engine A/B on the phone routine`.

---

## Self-review

- Spec coverage: §8.1 follow (tracker part) → T1–T3; mono parity preserved (constraint) → T1 tests; measurement → T3.
- Placeholders: none; the only unknown (setter timing vs stage init) has an explicit verification path in T2 Step 1.
- Type consistency: `TrackRecord{id,cls,conf,bbox[4],time_since_update,confirmed}`, `IdDet{id,label,conf,x,y,w,h}`, `HailoTrackAdapter(keep_lost_frames, min_hits).update()`, `LockResolver::step(records)` used identically in T1 and T2; `LockResult::alive` as records in both.
