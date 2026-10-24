# Hailo-15L Perception Node — F1 Lock Core (locked-target tracker, part 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The lock becomes a dedicated locked-target tracker instead of a borrowed multi-object-tracker id: identity and observation are separate, windows are in milliseconds from the ISP clock, prediction never reaches the screen, re-acquisition is guarded (never "best same-class box"), ambiguity is reported instead of resolved, and the published fields let a follow controller act only on a fresh visual observation. Measured by a lock-focused harness over the owner's routines.

**Architecture:** A new core-library component `garuda::lock::LockCore` owns the locked target. Per frame it receives the frame's ISP timestamp (ms) and the detections of that frame (all classes, with the multi-object tracker's ids as hints) and returns an `Output` (state, identity_locked, observation_valid, quality, obs_age_ms, uncertainty_px, the published box or none). Motion is a set of scalar constant-velocity Kalman filters on centre and size; the covariance drives a progressive search gate. Association scores candidates inside the gate on detector confidence, motion consistency, size/aspect consistency, class (soft) and id (soft); the winner must clear a threshold AND beat the runner-up by a margin, else the frame is UNCERTAIN (OCCLUDED within the occlusion window, REACQUIRING after it, LOST after expiry). The node keeps both multi-object engines for pre-lock ids and display; the existing `LockResolver` keeps click/target/auto-acquire candidate selection and hands the chosen detection to `LockCore::lock()`. Snapshot v2 gains the new `lock` fields; the shim passes them through. Visual tracking between detections (F2), appearance templates (F3), the DSP ROI (F4), click-frame sync and overlay (F5), ego-motion (F6) are later plans.

**Tech Stack:** C++17, CMake, nlohmann/json; no new dependency in F1 (OpenCV 4.5.5 is on the image and in the SDK for F2). Python 3 for the harness.

**Spec:** `docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md` §8.2 "Locked-target tracker" (added 2026-09-04 from the owner's direction and the design review in session) and §8.1.

## Global Constraints

- Time, not frames: every window is milliseconds from the frame's ISP timestamp (`mlb->isp_timestamp_ns / 1e6`); a run at 25 fps and one at 30 fps behave the same in wall-clock terms. Frame-count parameters do not exist in `LockCore`.
- Prediction never reaches the screen: the published box is the Kalman-smoothed box only when CONFIRMED; the last confirmed box (frozen) while OCCLUDED or REACQUIRING; none when LOST or NONE.
- No automatic re-lock on class+confidence: a candidate must lie inside the motion gate (Mahalanobis on the centre with the current covariance), pass the size/aspect check, and win the composite score by the ambiguity margin; class and id are soft terms. Full-frame candidates (outside the gate) are considered only in REACQUIRING, only with class match AND size consistency, and still subject to the margin; F3 adds appearance to this path.
- Ambiguity is reported: two candidates within the margin → no association this frame (state OCCLUDED/REACQUIRING by elapsed time), `quality` reflects it.
- `observation_valid = (state == CONFIRMED && obs_age_ms <= control_valid_ms)`; `identity_locked = state != LOST && state != NONE`. A future follow controller must gate on `observation_valid` only.
- Defaults (config block `lock`): `occlusion_ms 500`, `reacquire_ms 3000`, `expire_ms 10000`, `control_valid_ms 150`, `gate_sigma 3.0`, `min_score 0.5`, `ambiguity_ratio 1.3`, `size_tol 0.5` (relative w/h change tolerated per association), `q_acc_std 600.0` (process noise as white-noise acceleration std, px/s²; Ruling 2 lowered it from 1500: Q = σ_a²·[dt⁴/4, dt³/2; dt³/2, dt²] per axis — AMENDED during execution, Ruling 1: the earlier `q_pos 200` gave a ~17 px gate right after a lock), `p0_vel_std 400.0` (initial velocity std at lock, px/s — so a 20 px/frame mover is inside the gate from the first prediction), `gate_max_px 300.0` (cap on the gate radius so the search stays local; beyond it only the REACQUIRING out-of-gate path applies — Ruling 2), `r_pos 25.0` (measurement noise px²), `q_size 50.0`, `r_size 100.0`, weights `w_conf 0.25, w_motion 0.35, w_size 0.15, w_class 0.15, w_id 0.10`.
- Snapshot schema: v2 keeps every existing field; `lock` gains `state` (string), `identity_locked`, `observation_valid`, `quality` (0..1), `obs_age_ms`, `uncertainty_px`; `lock.id` keeps reporting the multi-object id last associated (or null), `lock.class` the locked class, `lock.coasting` = `!observation_valid && identity_locked` (portal compatibility). The golden `tests/golden/snapshot_v2.json` is regenerated from `tests/golden/mono_state_ref.py`? NO — the Pi's builder does not know these fields; the snapshot golden test compares the SUBSET of fields the Pi emits (assert the new fields are additive: the test parses both and checks Pi-fields equality) — see Task 2.
- Threading unchanged: `LockCore` lives in the detection callback thread; commands only set pending state under `state.mu`.
- Rule 1 for every number in docs; rule 9 red-team; rule 6 no new dependency. Board rules as in earlier plans (writes under `/opt/garuda` etc.; anchored pkill only; no reboot; do not touch the Pi). Branch `feat/hailo15l-kalman-tracker` (continued; the tracking line of work), worktree `.claude/worktrees/feat-hailo15l-detector`, from the Kalman plan's docs commit d6b98f3. Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_015dfMKyBmLK5bdtwfFmzgHq`.

---

## File structure

```
services/garuda-perception/
  include/garuda/lock_core.hpp        # garuda::lock — State, Obs, Params, Output, LockCore
  src/lock_core.cpp                   # scalar CV Kalman filters, gate, scoring, state machine
  tests/test_lock_core.cpp            # synthetic timestamped sequences
  include/garuda/snapshot.hpp / src/snapshot.cpp   # new lock fields (additive)
  tests/test_snapshot.cpp             # additive-fields check against the Pi golden
  src/node_main.cpp                   # LockCore per frame; resolver hands over the pick; config block `lock`
  config/*.json                       # `lock` block (defaults) in every perception*.json
  shim/garuda_mono_shim.py            # passthrough (verify nothing filters lock fields)
bench/evidence/2026-09-04-lock-core/lock_metrics.py   # the lock-focused harness over captures
hosts/hailo15l/README.md              # "Lock core" section
```

---

### Task 1: `LockCore` in the core library, golden-free but sequence-tested

**Files:**
- Create: `include/garuda/lock_core.hpp`, `src/lock_core.cpp`, `tests/test_lock_core.cpp`
- Modify: `CMakeLists.txt` (core sources), `tests/CMakeLists.txt`

**Interfaces:**
- Produces:
  ```cpp
  namespace garuda::lock {
  enum class State { NONE, CONFIRMED, OCCLUDED, REACQUIRING, LOST };
  const char* state_name(State);                                     // "none","confirmed","occluded","reacquiring","lost"
  struct Obs { int id; std::string cls; double conf; double x, y, w, h; };   // frame pixels, top-left + size; id -1 if none
  struct Params { double occlusion_ms = 500, reacquire_ms = 3000, expire_ms = 10000, control_valid_ms = 150;
                  double gate_sigma = 3.0, min_score = 0.5, ambiguity_ratio = 1.3, size_tol = 0.5;
                  double q_acc_std = 600.0, p0_vel_std = 400.0, gate_max_px = 300.0, r_pos = 25.0, q_size = 50.0, r_size = 100.0;
                  double w_conf = 0.25, w_motion = 0.35, w_size = 0.15, w_class = 0.15, w_id = 0.10;
                  int frame_w = 1280, frame_h = 720; };
  struct Box { double x, y, w, h; };
  struct Output { State state = State::NONE; bool identity_locked = false, observation_valid = false;
                  double quality = 0.0, obs_age_ms = 0.0, uncertainty_px = 0.0;
                  std::optional<Box> box; std::string cls; int last_id = -1; };
  class LockCore {
  public:
      explicit LockCore(const Params& p = Params{});
      void lock(const Obs& target, double ts_ms);          // start: filters initialised at the target, state CONFIRMED, templates (F3) later
      void unlock();                                       // state NONE
      Output update(double ts_ms, const std::vector<Obs>& dets);   // one frame; dets may be empty
      const Output& last() const;
  };
  }
  ```
- Kalman filters: two independent scalar constant-velocity filters (cx, cy) with state (p, v), initial covariance diag(r_pos, p0_vel_std²), white-noise-acceleration process noise from `q_acc_std`, measurement noise `r_pos`; two scalar random-walk filters (w, h) with `q_size`/`r_size`. `predict(dt_s)`; `correct(z)`. `uncertainty_px = sqrt(max(var_cx, var_cy))`. Gate: `d² = ((cx_det-cx_pred)²/var_cx + (cy_det-cy_pred)²/var_cy) <= gate_sigma²`. Size check: `|w_det - w_pred|/w_pred <= size_tol` and same for h.
- Scoring for a gated candidate: `score = w_conf*conf + w_motion*exp(-d²/2) + w_size*(1 - min(1, |w_det-w_pred|/w_pred)) + w_class*(cls==locked_cls) + w_id*(id==last_id && id>=0)`. Winner if `score >= min_score` and (no runner-up or `score >= ambiguity_ratio * runner_up`). On a win: correct filters, state CONFIRMED, `last_id = id`, `quality = score`, `obs_age_ms = 0`. On no win: filters predict only; `obs_age_ms = ts - last_confirmed_ts`; state OCCLUDED if `obs_age_ms <= occlusion_ms`, REACQUIRING if `<= reacquire_ms + occlusion_ms`… precisely: OCCLUDED while `obs_age_ms <= occlusion_ms`; REACQUIRING while `occlusion_ms < obs_age_ms <= expire_ms`; LOST after `expire_ms` (`identity_locked=false`, box none). In REACQUIRING only, candidates outside the gate are also scored if `cls == locked_cls` and the size check passes, with `w_motion` term computed from the true `d²` (so far ones score low); the margin rule applies; `reacquire_ms` bounds how long the widened search runs before the core stops considering out-of-gate candidates (after it, only in-gate candidates until expiry).
  - **AMENDED 2026-09-04 (final-fix wave, Ruling 11 — spec §8.2 wins over the paragraph above).** Association is **two-stage**, not one pooled margin test over both sets. Stage 1 scores the IN-GATE candidates and applies `min_score` + the ambiguity margin **among themselves**. Stage 2 — the widened, out-of-gate search described above, now judged against its own floor `min_score_widened` (unset = `min_score`) with the margin applied **within that pool only** — runs ONLY if stage 1 found nothing plausible at all (empty pool, or nothing clearing `min_score`). An **ambiguous** stage 1 ends the frame in OCCLUDED/REACQUIRING and does **not** consult stage 2. Pooling the two let a far same-class object veto a good local match. Also amended (Ruling 14): while coasting, the predicted centre is clamped to the frame (`Params.frame_w/frame_h`) so a walk-out target re-entering at the edge it left by is still covered by the local gate — the ruling's own `[-gate_max_px, frame_w + gate_max_px]` region was not usable, see `docs/decisions.md`.
- `quality` when not confirmed = `max(0, 1 - obs_age_ms / expire_ms)` scaled by 0.5 (never above 0.5 without an observation).
- Published box: CONFIRMED → the filtered (cx,cy,w,h) converted to top-left; OCCLUDED/REACQUIRING → the last confirmed box; LOST/NONE → none. The predicted centre is used internally only.

- [ ] **Step 1: Write the failing tests** — `tests/test_lock_core.cpp` (assert style), synthetic sequences with explicit timestamps (dt 40 ms = 25 fps, and the same sequences at 33.3 ms = 30 fps must give the same state transitions at the same wall-clock times, ±one frame):
  1. lock + steady detections → CONFIRMED every frame, box follows within 1 px after 5 frames, `observation_valid` true, `obs_age_ms` 0.
  2. gap of 400 ms → OCCLUDED, box frozen (equal to the last confirmed box, bit-exact), `observation_valid` false, `identity_locked` true; detection returns near the prediction → CONFIRMED with the same identity.
  3. gap of 2 s → REACQUIRING; a same-class detection far away (outside the gate) with high conf → NOT taken while OCCLUDED; taken in REACQUIRING only if size-consistent and unambiguous; a second equally good candidate → no association (state stays REACQUIRING), `quality` < 0.5.
  4. gap > 10 s → LOST, box none, `identity_locked` false; a later detection does not auto-lock.
  5. two persons crossing: candidates A (locked) and B with similar scores within the ambiguity ratio → no association for those frames (OCCLUDED), then A alone → CONFIRMED with `last_id` A; B never becomes the lock.
  6. class flicker: the locked target's detections alternate labels person/chair with the same box → stays CONFIRMED (class is soft), `cls` stays the locked class.
  7. a fast mover: constant velocity 20 px/frame → predictions stay within the gate; a 3-frame gap → the returning detection at the extrapolated position is associated, and the frozen box during the gap did NOT move.
  8. the published box never leaves the frame: lock near the edge, gap, prediction beyond the frame → the frozen box is the last confirmed one (inside).
  9. `state_name` strings.
  Register `lock_core` in ctest.
- [ ] **Step 2: Run to verify they fail** — missing header.
- [ ] **Step 3: Implement** `src/lock_core.cpp` per the interface above (scalar KFs in an anonymous namespace; `update()` = predict all filters with `dt` from the last `update`/`lock` timestamp (clamped to [0, 1] s), gather candidates, score, transition, fill `Output`).
- [ ] **Step 4: Build + ctest** — 11/11, zero warnings.
- [ ] **Step 5: Commit** — `feat(perception): LockCore — time-based locked-target tracker with guarded re-acquisition and frozen output`.

---

### Task 2: Snapshot fields, node integration, config, deploy, verify

**Files:**
- Modify: `include/garuda/snapshot.hpp`, `src/snapshot.cpp`, `tests/test_snapshot.cpp`, `src/node_main.cpp`, every `config/perception*.json` (add the `lock` block with the defaults), `shim/garuda_mono_shim.py` (only if it filters fields), `hosts/hailo15l/README.md`

- [ ] **Step 1: Snapshot** — `SnapshotState` gains `lock_state` (string, default "none"), `lock_identity_locked`, `lock_observation_valid`, `lock_quality`, `lock_obs_age_ms`, `lock_uncertainty_px`; **AMENDED 2026-09-04 (final-fix wave, Rulings 10/13): plus `lock_epoch` (int, the lock generation — what makes a re-lock distinguishable from tracker id churn) and `lock_box` (`{x,y,w,h}` or null — `LockCore`'s own published box, which the plan omitted although README/ROUTINES/the harness all described it as published);** `build_snapshot_json` emits them inside `lock` next to `id/class/coasting`. `tests/test_snapshot.cpp`: keep the existing Pi-golden comparison but compare only the keys present in the golden (the new keys are additive) and add an assertion that the new keys exist with the right types. ctest green.
- [ ] **Step 2: Node** — parse the `lock` block into `garuda::lock::Params` (frame_w/h from the node's); construct `LockCore` next to the tracker/resolver (det_sink thread). Per frame, after the engine step: build `std::vector<garuda::lock::Obs>` from this frame's records (`id`, `cls`, `conf`, box; for the mono engine use `tracker.tracks()` live ones (tsu==0) — coasting records are NOT observations; for the hailo engine the live records), `ts_ms = isp_timestamp_ns / 1e6` (fallback: steady clock ms if the timestamp is 0 — log once). Lock hand-over: when the resolver's step yields a NEW `lock_id` (auto-acquire, click, re-acquire) that differs from `LockCore`'s current identity while `LockCore` is NONE or LOST → `core.lock(obs_of_that_id, ts_ms)`; when the resolver's lock is cleared by a target change → `core.unlock()`. While `LockCore` is CONFIRMED/OCCLUDED/REACQUIRING, the resolver's re-acquire rule is NOT applied to the published lock (the core owns it) — keep the resolver running for its candidate bookkeeping, but the snapshot's `lock` fields come from `LockCore::update()`: `lock.id = out.last_id`, `lock.class = out.cls`, `lock.coasting = identity_locked && !observation_valid`, plus the new fields; tracks list unchanged. Log state transitions once each (not per frame).
  - **AMENDED 2026-09-04 (final-fix wave):** `lock.id` is null (and `class` empty) whenever `!identity_locked` (M5); a click seeds the core ONLY from the clicked id's own live `Obs`, on every path, and blocks the generic hand-over for that frame (Ruling 12/I4 — the earlier rule covered only the "core already holds an identity" case); a zero `isp_timestamp_ns` under a live lock extends the ISP series by one nominal frame interval instead of switching to `steady_clock` (M2); transition logging is rate-limited per direction (M4).
- [ ] **Step 3: Configs + README** — the `lock` block (defaults) in `perception.json`, `perception-yolov8n.json`, `perception-yolov8m.json`; README "Lock core" section (states, fields, windows in ms, what a follow controller may use).
- [ ] **Step 4: Build, deploy, verify** — native ctest green; cross-build zero warnings; deploy the yolov8m (person, Kalman engine) config; with the owner present (the controller coordinates): `/api/state` shows `lock.state` moving CONFIRMED → OCCLUDED (walk out) → REACQUIRING → CONFIRMED (walk back within 3 s) → LOST (stay out > 10 s), `obs_age_ms` counting in ms, `uncertainty_px` growing while out, the frozen box unchanged while OCCLUDED/REACQUIRING — paste the polls with timestamps. Then deploy the default (yolo26m mono) config and confirm the same fields work with the mono engine (one poll).
- [ ] **Step 5: Commit** — `feat(hailo15l): LockCore in the node — time-based lock states published, resolver hands over the pick, prediction never published`.

---

### Task 3: The lock-focused harness and the bench

- [x] **Step 1:** `bench/evidence/2026-09-04-lock-core/lock_metrics.py`: over a timestamped SSE capture (the M1 capture script format) compute: identity switches (changes of `lock.id` while `identity_locked`) — **AMENDED 2026-09-04 (final-fix wave, Ruling 10/I2): SPLIT into `relocks` (changes of `lock.epoch`, excluding the capture's first non-zero epoch — the gate column, and the only one "false relocks" aliases) and `id_churn` (changes of `lock.id` within one epoch while `identity_locked` — the tracker renumbering the same object, which the core is designed to ride through, so not a failure). A capture without `epoch` reports n/a for both. Also amended: the off-screen-boxes metric reads `lock.box`, not the locked id's `tracks[]` entry (Ruling 13/I5)** — number of LOST events, time-to-reacquire (OCCLUDED/REACQUIRING → CONFIRMED durations: min/mean/max), fraction of states with `observation_valid`, fraction CONFIRMED/OCCLUDED/REACQUIRING/LOST, off-screen published boxes (count of boxes outside 0..frame — must be 0), max `uncertainty_px`, and for single-target routines "false relocks" = identity switches (by construction any switch is false). Print a one-line row like the earlier comparison scripts. Runs on the earlier captures too (the fields absent → reports "n/a").
- [x] **Step 2:** With the owner: the person walk routine (still 5 s; fast across and back ×2; out 3 s; back; fast in place 10 s; still) under the person profile, and the phone routine under the yolov8m all-classes (`classification_id -1`) config with the lock on the phone — record both captures and run the harness; paste rows. Compare with yesterday's rows in the tracker-engine section (identity switches and lock-None fraction are the comparable columns). **Done for routines 1/2/4 (runs 6/8/9b); routine 3 (two-person swap) skipped, no second person available; the phone routine (routine 5) was still capturing at closing-docs time and stays `TBD-bench`.**
- [x] **Step 3:** benchlog section `## 2026-09-04 — Hailo-15L SBC: Lock core (F1) — time-based locked-target tracking` with conditions, the harness rows, findings, red-team (owner-paced, no visual tracking yet so gaps still cost, single scene), `TBD-bench` for F2's effect. decisions.md entry; CLAUDE.md §7 one sentence; spec §8.2 status line. Commit `bench(hailo15l): lock core F1 run`.

**Executed (2026-09-04, closing docs round).** Four on-board fix rounds ran against real captures
between this plan's Task 2 completion and the numbers now in the benchlog: round 1 (commits
`2659a18`, `40f15f8` — auto-acquire confidence/edge gating, variance-aware size gate, `lock.box`
centre off-screen metric, Ruling 16), round 2 (`f027924`, `83b600c` — auto-acquire/re-acquire streak
gating, Ruling 18), round 3 (`330eaec`, `ef6d50c`, `217fb04` — relative position/size gates, same-id
relaxation, `min_score_widened` 0.40, Ruling 19), and round 4 (`7d059ff`, `258dc4c`, `47fb866` —
follow-but-don't-learn on same-id-only matches, band-dependent score floor, `reacquire_ms` 9500,
operator-event logging, Ruling 20). The final measured captures (routine 1 run 6, routine 2 run 9b,
routine 4 run 8) are on `217fb04`/`47fb866`; routine 3 was skipped and routine 5 (phone) stayed
`TBD-bench` at closing-docs time. Numbers: `bench/benchlog.md` 2026-09-04 "Hailo-15L SBC: F1 lock
core"; rulings: `docs/decisions.md` 2026-09-04 same title, Rulings 15–21.

---

## Self-review

- Spec coverage: §8.2 items 3 (frozen output), 5 (identity vs observation, published fields), 6 (time-based), 2 (guarded re-acquisition, ambiguity) → T1/T2; item 8 (harness) → T3; items 1 (visual tracker), 4 (templates), the ROI, click sync, ego-motion → later plans, named in the header.
- Placeholders: none; the state machine, scoring, defaults and tests are specified.
- Type consistency: `garuda::lock::{State, Obs, Params, Box, Output, LockCore}` used identically in T1–T3; snapshot field names `lock_state`, `lock_identity_locked`, `lock_observation_valid`, `lock_quality`, `lock_obs_age_ms`, `lock_uncertainty_px` in T2 and the harness reads `lock.state`, `lock.identity_locked`, `lock.observation_valid`, `lock.quality`, `lock.obs_age_ms`, `lock.uncertainty_px`.
