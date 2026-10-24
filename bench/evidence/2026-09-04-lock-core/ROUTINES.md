# F1 lock core — owner routines

Five owner-paced routines to run on the board with `lock_metrics.py`
(`bench/evidence/2026-09-04-lock-core/lock_metrics.py`) once the board and owner are both available
(currently deferred — see `bench/benchlog.md`'s F1 section and this task's report). Two are named
verbatim in `.superpowers/sdd/2026-09-04-hailo15l-lock-core/task-3-brief.md` Step 2 (**person walk**,
**phone**); the other two (**occlusion behind an object**, **two-person swap**) are the physical,
on-board analogues of two of the state-machine scenarios `task-1-brief.md`'s Step 1 already
specifies and Task 1's unit tests already cover synthetically (`tests/test_lock_core.cpp`) — running
them for real validates that the deployed board behaves the way the synthetic tests already proved
the code does, which is a different (and still open) question. **Fast lateral** is the "fast
across and back" segment already inside the brief's person-walk routine, called out here as its own
row because it feeds a metric (`max uncertainty_px` under real motion, not synthetic) the rest of
the walk routine doesn't isolate. Nothing below is a new requirement beyond what those two briefs
already specify — this file only organises them per-routine, operator action, expected capture
shape, and which `lock_metrics.py` column each one is *for*.

Capture method for all five (per `task-3-brief.md`): PC-side timestamped SSE,
`bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py <url> <seconds> <outfile>`
against `http://10.0.0.1:8098/api/events` (shim cap 10 Hz), then
`python3 bench/evidence/2026-09-04-lock-core/lock_metrics.py <outfile>`.

**Click once, at the start of each capture — never mid-capture.** The SSE feed is sampled at 10 Hz,
so a click that re-locks the target between two samples is indistinguishable from the system silently
switching the lock by itself: both appear as one row's `lock.epoch`/`lock.id` differing from the
previous row's. A mid-capture click therefore writes an operator action into the `re-locks` column,
which is the column these routines exist to drive to zero. If a re-lock is genuinely needed mid-run,
stop the capture, click, and start a new one.

**Reading `re-locks` afterwards: an epoch change with no LOST row before it is an OPERATOR action.**
`LockCore` bumps `lock.epoch` only in `lock()`, and the node calls `lock()` on exactly three paths: a
click, a `target` command (both of which first `unlock()`), and the hand-over after the core has gone
`none`/`lost`. So a capture that shows the epoch change *following* a `lost` row is the system
re-locking on its own — the failure these routines measure — whereas one with no `lost` row before it
(or a bare `none` row with no epoch change at all) is a click or a `target` command that the operator
made. **From the on-board fix round 4 commit onwards the node logs both**, unthrottled, at the point
they are applied:

```
lock: click (640,360) -> id 25
lock: click (640,360) -> no track
lock: target 'person'
lock: target cleared
```

so `grep -a "^lock: \(click\|target\)" /var/log/garuda-perception.log` next to the capture settles
it directly instead of by inference. Before that commit neither was logged, which is why the
fast-lateral run's single unlock at rel. 401.58 s (core `none`, no `lost`, no epoch change) could only
be attributed to "a click or a target command" and not to which.

---

## 1. Walk-out/return

**Source:** `task-3-brief.md` Step 2's person-walk routine, first three phases: *"still 5 s; fast
across and back ×2; out 3 s; back"* — this row covers the "out 3 s; back" phase specifically (the
"fast across and back" phase is routine 4, below). Design analogue:
`task-1-brief.md` Step 1, test 2 (a 400 ms–few-second gap, OCCLUDED → CONFIRMED with the same
identity), already passing synthetically per Task 1's report.

**Config:** the person profile (`config/perception-yolov8m.json`, `classification_id: 1`,
Kalman/hailo tracker engine — the deployed default per CLAUDE.md §7's 2026-09-03 note).

**What the operator does:** stand in frame 5 s (baseline); walk fully out of frame for ~3 s; walk
back in and stand still.

**What the capture should show:**
- `lock.state`: `confirmed` → `occluded` → (`reacquiring` only if the 3 s exceeds `occlusion_ms`'s
  500 ms default, which it will) → `confirmed` again, with **the same `lock.id`** before and after
  the gap.
- `lock.identity_locked` stays `true` throughout the gap (never drops to `false` mid-occlusion —
  only `lost`/`none` do that).
- `lock.box` — LockCore's own published box — stays frozen at the last confirmed position through
  the gap and inside the frame; the `tracks[]` entry matching `lock.id`, if the underlying tracker
  keeps a coasting one alive, is a SEPARATE box (the engine's own extrapolation) and may well drift
  off-frame. See routine 2 for the sharper version of this check.
- `obs_age_ms` climbs from 0 during the gap and resets to 0 the frame the target returns;
  `uncertainty_px` grows monotonically during the gap (no predict step runs backwards).

**Feeds:** `re-locks` (must be 0 — the whole point of this routine is confirming the lock survives a
real 3 s gap, not just a synthetic one; a non-zero `id churn` here is fine and even expected, it
means the tracker underneath renumbered the returning person and LockCore held on regardless),
`time-to-reacquire` (this routine's own
occlusion episode contributes one min/mean/max sample), `LOST events` (must be 0 — 3 s is well
under the 10 s `expire_ms` default), state fractions (occluded/reacquiring % should be small and
proportional to the 3 s gap against the routine's total span).

---

## 2. Occlusion behind an object

**Source:** design analogue of `task-1-brief.md` Step 1, tests 2/3 (gap → OCCLUDED/REACQUIRING →
recovers) **and** test 8 (*"the published box never leaves the frame: lock near the edge, gap,
prediction beyond the frame → the frozen box is the last confirmed one (inside)"*), which is
exactly the bench-level claim `lock_metrics.py`'s off-screen-boxes counter checks for. Not literally
named in `task-3-brief.md` Step 2, but this is the on-board case that stress-tests it: unlike
walking fully out of frame (routine 1), occlusion behind furniture keeps the target's *last visible
position* well inside the frame, so a bug that let the frozen box drift (rather than staying
bit-exact at the last confirmed box, per `hosts/hailo15l/README.md` §10's state table) would show
up here as a published box that has moved from where it was last actually seen — something routine
1's "gone from frame entirely" case cannot distinguish from correct behaviour.

**Config:** same person profile as routine 1.

**What the operator does:** walk behind a static object in the room (furniture, a doorway edge)
that fully occludes the camera's view of them for 2–4 s, without leaving the frame's field of view
on either side of the object, then re-emerge on the same or the opposite side.

**What the capture should show:**
- `lock.state`: `confirmed` → `occluded` → (`reacquiring` if the occlusion runs past 500 ms) →
  `confirmed`, same `lock.id`.
- `lock.box` stays bit-exact at the position last seen going into the occlusion — near the object,
  not extrapolated toward where the target would be if still moving, and never at the frame edge/off
  it. (The `tracks[]` entry at the same id, where the engine keeps one, is the engine's own coasting
  box and is expected to differ — under the mono engine ByteTrack extrapolates it every frame. That
  difference is worth eyeballing in this capture; measuring it is Recommendation 4's separate
  mono-engine run, still deferred.)

**Feeds:** `off-screen published boxes` (read off `lock.box`, counted when its **centre** leaves the
frame — a box merely overhanging an edge is normal for a target at the edge of frame, and run 1
produced 109 such rows for a person who had genuinely walked out; this is the routine specifically
designed to give the metric something real to check against, beyond the "obviously not off-screen
because they never left the visible half of the room" case in routine 1 — expected 0, per the
brief's own bar), `time-to-reacquire`, `observation_valid` fraction (should dip during the
occlusion, recover after).

---

## 3. Two-person swap

**Source:** design analogue of `task-1-brief.md` Step 1, test 5 (*"two persons crossing: candidates
A (locked) and B with similar scores within the ambiguity ratio → no association for those frames
(OCCLUDED), then A alone → CONFIRMED with `last_id` A; B never becomes the lock"*) — the physical,
on-board version of exactly the ambiguity scenario the spec's own "Why" section (§8.2) names as F1's
reason to exist (*"the resolver takes the highest-confidence live object of the same class anywhere
in the frame, which transferred the lock silently"*), and the concrete failure the 2026-09-03
Kalman-tracker A/B (`bench/benchlog.md`) actually observed (the 22-id person run, the id sequence
`1 -> 234 -> 284 -> 234 -> 285 -> 301`).

**Config:** person profile; requires a second person at the bench.

**What the operator does:** the locked person (A) and a second person (B) walk toward each other and
cross paths close enough that their boxes overlap or come close for a few frames, then separate
again with A continuing to be visible.

**What the capture should show:**
- **`lock.id` must never become B's id at any point** — during the crossing, `lock.state` should
  read `occluded`/`reacquiring` (ambiguous or briefly unmatched) rather than silently confirming on
  whichever of A/B scored higher that frame.
- Once separated, `lock.state` returns to `confirmed` with the **original** `last_id` (A's id).

**Feeds:** `re-locks` / `false relocks` — this is the single most direct test of the metric the whole
F1 effort exists to drive to zero (see `lock_metrics.py`'s own docstring: a false relock during a
single-target routine is by construction any re-lock; a two-person routine is deliberately NOT
single-target for the crossing window itself, so a human read of the capture against the state
trace, not the automated single-target "any re-lock is false" shortcut, is what confirms whether a
re-lock — if one occurs — actually went to B). `id churn` is the companion read: churn with the
epoch unchanged means the lock stayed on A while the tracker renumbered her, which is the success
case, not a switch to B.
Also feeds `time-to-reacquire` (the ambiguity window, if any, is itself a short occlusion episode).

---

## 4. Fast lateral

**Source:** `task-3-brief.md` Step 2 person-walk routine's *"fast across and back ×2"* and *"fast in
place 10 s"* phases. Design analogue: `task-1-brief.md` Step 1, test 7 (*"a fast mover: constant
velocity 20 px/frame → predictions stay within the gate; a 3-frame gap → the returning detection at
the extrapolated position is associated, and the frozen box during the gap did NOT move"*), and the
Kalman/gate tuning history in `docs/decisions.md`/`lock_core.hpp`'s own `Params` comment
(`q_acc_std`/`p0_vel_std`/`gate_max_px`, Rulings 1–2) — this routine is the real-motion version of
exactly the mover speed those Rulings were tuned against.

**Config:** person profile.

**What the operator does:** walk (or jog, within the room's space) quickly across the frame and
back, twice; then move rapidly in place (side-to-side, not translating) for 10 s.

**What the capture should show:**
- `lock.state` stays `confirmed` through the fast motion (should not spuriously drop to `occluded`
  just because the target moved quickly between frames — that would indicate the gate is too tight
  for real-world speeds even though it passed the synthetic 20 px/frame test).
- `uncertainty_px` should stay low while `confirmed` (the filter is being corrected every frame) and
  only grow if a genuine miss occurs during the fast segment.
- If a brief miss does occur (motion blur, a frame where the detector drops the box), the frozen box
  during that gap must not have "moved" relative to where it was last confirmed — the miss should
  recover to the same id once a detection reappears near the (fast) predicted position, not fall
  back to OCCLUDED/REACQUIRING taking longer than the walk-out routine's gaps of similar duration.

**Feeds:** `max uncertainty_px` (real-motion ceiling, to compare against the synthetic fixture's and
against future gate-tuning changes), state fractions (confirmed % should stay high despite the fast
motion), `time-to-reacquire` if any miss occurs.

---

## 5. Phone routine

**Source:** `task-3-brief.md` Step 2, verbatim: *"the phone routine under the yolov8m all-classes
config (`classification_id -1`) with the lock on the phone."*

**Config:** `config/perception-yolov8m.json` with `classification_id` **removed or set to `-1`**
(all classes tracked, not the person-only profile) — the exact configuration the 2026-09-03 A/B
section (`bench/benchlog.md`) ran under (`phone_kalman2.txt`), which is the capture this routine is
explicitly meant to be compared against (dispatch: *"identity switches and lock-None fraction are
the comparable columns"*).

**What the operator does:** the same phone-movement routine as the 2026-09-03 A/B session (hold and
move a cell phone across the frame, varying distance/angle), with the operator explicitly
click-locking the phone (not letting auto-acquire pick whatever class scores highest).

**What the capture should show:** whether F1 actually fixes the class-agnostic-competition churn
`docs/decisions.md`'s 2026-09-04 entry (I2) root-caused in the class-agnostic JDE tracker — i.e.
whether `lock.id`/`lock.class` now hold steady on "cell phone" through the routine instead of
flipping across `{cell phone, knife, tv}` the way `phone_kalman2.txt` did (894 rows, lock class set
`{knife, cell phone, tv}`, null lock on 381/894 rows — `bench/benchlog.md` 2026-09-03 "Kalman
tracker engine" section, Findings).

**Feeds:** `re-locks` / `false relocks` (the primary before/after comparison — F1's job is to make
this near-zero where the pre-F1 resolver-based lock could not; the companion `id churn` column is
where the phone's `{cell phone, knife, tv}` renumbering will now show up WITHOUT counting as a
failure, which is exactly the distinction yesterday's single "identity switches" column could not
draw), state fraction `none`+`lost`
combined (the comparable metric to yesterday's raw "lock None" count/fraction column in
`compare_phone_runs.py`'s output — not a literal same-column diff, since `lock_metrics.py`'s state
fractions distinguish `none` from `lost` where the old resolver-based `lock.id is null` check could
not), `time-to-reacquire` (small-object reacquisition, the specific case the A/B found "unsolved by
either [tracker] engine" — CLAUDE.md §7's 2026-09-03 note), `off-screen published boxes` (`lock.box`
must stay in frame; small, fast-moving objects are exactly where the ENGINE's coasting extrapolation
is most likely to run away off-frame — `lock_metrics.py`'s docstring cites `phone.txt` track id 35,
x=-9092, as a real pre-F1 example — so this routine is also where the two boxes are most likely to
visibly disagree).

---

## What this file does not cover

Per `docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md` §8.2, F2 (visual
tracker), F3 (appearance templates), F4 (locked-object ROI), F5 (click–frame sync), and F6
(ego-motion) are later plans — none of these five routines exercise them, and none of
`lock_metrics.py`'s metrics are designed to measure them (e.g. there is no appearance-drift metric,
because F3 doesn't exist yet). Re-running these same five routines once F2+ land is expected to
change some of these numbers (notably time-to-reacquire and off-screen boxes, once a visual tracker
can hold the box between full-frame detections) — that comparison is future work, not part of this
task.
