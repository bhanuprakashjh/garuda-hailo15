# Follow-me platform plan + tracker re-acquire hardening — design

2026-09-12. Owner directive: study PixEagle, PX4-ROS2-Gazebo-YOLOv8 and
Autonomous-Drone-Positioning (cangozpi), produce the implementation plan for
this platform, then start with tracker hardening (re-acquire), tested against
recorded video and available datasets.

Scope of this spec: the full platform phase plan (A–E) at design level, and
the Phase A tracker re-acquire hardening at implementation level. Phases B–D
each get their own spec before implementation.

## 1. What the reference repos actually teach

Full study notes summarized; clones under
`/media/bhanu1234/Development/hailo-export/reference-repos/`.

**PixEagle (Apache-2.0)** — the only one with a real tracker→follower loop,
and the main design source. Worth adopting as ideas:
- A **command-authority supervisor** separate from tracker and controller
  (`ACTIVE / COASTING / REACQUIRING / HANDOFF_PENDING`, reason code on every
  transition; session epochs invalidate stale async decisions).
- Re-acquire discipline: candidates ranked by fused score, **refused when
  best − runner-up is inside an ambiguity margin**; after long loss a
  candidate is **tentative** for N confirmation frames and never
  command-eligible while tentative; physical sanity gates (area ratio within
  [1/2.5, 2.5], exit-edge constraint).
- **Prediction is never command-eligible** — Kalman output only seeds the
  re-detection search (local ROI ladder expanding to full-frame).
- Offboard discipline: fixed-rate publisher with a TTL — stale intent
  publishes safe defaults, never the old command; bounded coasting budgeted
  by min(time, distance); circuit breaker + COMMAND_PREVIEW mode.
- Testing habits: failure scenarios as a versioned artifact (target loss,
  video stall, link loss, operator abort, publish failure); tracker
  benchmarked **with recovery disabled** on fixed clips; deterministic
  PTS-paced replay.

**PX4-ROS2-Gazebo-YOLOv8 (no licence — ideas only)** — detection and control
are never connected; its value is the minimal sim recipe: PX4 SITL launches
Gazebo (`PX4_GZ_MODEL=x500_depth`), one `ros_gz_bridge` topic as the camera
seam (`/camera`), `MicroXRCEAgent udp4 -p 8888` + `px4_msgs` for offboard,
a 40-line scripted moving target giving analytic ground truth, and a manual
MAVSDK channel kept alive beside autonomy. Anti-patterns noted: unpinned PX4
clone, sleep-based orchestration, per-tick subprocess control.

**cangozpi capstone (unlicensed; vendored YOLOv5 is GPLv3 — ideas only)** —
perception and control share no state (the negative lesson), but its MAVROS
scripts demonstrate the OFFBOARD entry ritual PX4 requires: prime setpoints
before mode change, keep publishing ≥2 Hz forever, handle RC-loss failsafe
explicitly, and never go silent on target loss.

Licence note (rule 6): no code is copied from any of the three. PixEagle is
Apache-2.0 and safe to borrow parameter values and state-machine shapes from;
the other two contribute lessons only. Ultralytics/AGPL stays out of
`services/` (bench/eval allowance unchanged). MOT17 labels are used for local
evaluation only and are not committed to the repo.

## 2. Platform phase plan

The 2026-09-12 A/B replay moved the bottleneck: the detector is validated on
the recorded sequence; the tracker's terminal loss is now the binding
constraint. Phases, in order, each gated on measured numbers:

- **A — Tracker re-acquire hardening (this spec, implemented now).**
  Class-generic, gated re-acquire in `garuda::fresh::Tracker`, evaluated on
  recorded phone video and MOT17 ground-truth identities.
- **B — Continuity supervisor + follow intent (next spec).** A
  `FollowAuthority` unit between the tracker snapshot and any consumer:
  states ACTIVE/COASTING/REACQUIRING/HANDOFF, dual time+distance coast
  budget, TTL'd typed `CommandIntent` (body-frame velocities + yaw rate),
  COMMAND_PREVIEW as the default execution mode. Pure C++, testable by
  replay; no PX4 dependency yet.
- **C — Sim-in-the-loop (spec after B).** PX4 SITL + Gazebo + uXRCE-DDS on
  the PC, pinned PX4 release; the perception side replays recorded or
  Gazebo-bridged frames; scripted moving target for analytic error; the
  PixEagle failure-scenario list becomes our checked-in suite. Everything
  behind `GARUDA_SIM=1` per repo rule; nothing arms without it.
- **D — Board bridge.** `garuda-bridge` publishes the follow intent over
  uXRCE-DDS from the Hailo-15L node, with the OFFBOARD discipline above;
  real-FC sessions remain explicit and parameter-listed (rule 12).
- **E — Gates.** Added to CLAUDE.md §5 when B lands: lock-recovery and
  follow-error numbers measured in sim before any live-vehicle work.

## 3. Phase A design — re-acquire in `garuda::fresh::Tracker`

### Current behavior (measured baselines, 2026-09-12)

The tracker deliberately never resurrects an expired selected track
("returning after a long gap can never resurrect the selected ID"), except
via the person-only embedding `TargetOwner`. Baselines with the current code:

- Recorded phone video (controlled-HEF detections, 433 frames, class armed):
  states tracking 96 / coasting 99 / lost 235; one acquisition, no recovery
  for the final ~15.7 s although the phone is detected on 74 % of frames.
- MOT17-02-FRCNN gt-driven, lock on identity 19, scripted outages: a 1.0 s
  outage recovers in-place (coast); a 3.0 s outage is terminal — 266 frames
  lost, 0 wrong-identity frames.

### Change

Add a bounded, gated re-acquire layer for the selected target, active only
when the learned-person `TargetOwner` is not active. The "expire before
association" invariant is untouched: expired tracks stay dead, and ordinary
association can never rebind the lock. Re-acquire is an explicit layer that
may bind the lock to a **new** track id under all of the following gates
(defaults in parentheses; all configurable through the existing
`tracking` JSON config):

On loss (selected track expired or lock marked lost), the tracker retains a
`LostTarget` memory: label, last filtered box, appearance histogram copy,
loss time, and the set of track ids alive at loss. The remembered box is
advanced by usable camera motion each frame. Memory expires after
`reacquire_window_ms` (7000 — the Ruling 33 lesson from the kalman branch).

A candidate track qualifies only if ALL hold:
1. same label; confirmed, observed this frame, not ambiguous;
2. confidence ≥ `birth_confidence` (0.5);
3. its id was **born after the loss** or is the lost id itself — an id alive
   while the target was still tracked is by construction a different object
   (kalman-branch Ruling 32);
4. size plausibility: width and height ratios vs the remembered box within
   `reacquire_size_ratio` (2.5) either way;
5. position plausibility: center within a radius that starts at
   `reacquire_radius` (2.0 × remembered box extent) and grows by
   `reacquire_radius_growth` (2.0 extents/second; raised from 0.5 on
   2026-09-12 after VisDrone-MOT replays showed a walking person seen from
   above leaving the 0.5/s radius within a second — the box extent is a
   footprint there, and even a forward view covers ~1–2 body heights per
   second at a walk) up to full frame — PixEagle's expanding search,
   applied as a gate; the radius is a recall knob, identity stays with
   gate 6;
6. appearance: when both the memory and the candidate carry histograms,
   Bhattacharyya distance ≤ `appearance_gate` (reuse, 0.55);
7. uniqueness: exactly one qualifying candidate this frame, and when
   several tracks pass gates 1–5 the best fused score must beat the
   runner-up by `ambiguity_margin` (reuse, 0.08) or the frame is refused.

A qualifying candidate becomes **pending**: target state publishes
`reacquiring`, `control_valid` stays false. Binding happens only after
`reacquire_hits` (3) qualifying frames of the SAME candidate id within
`reacquire_confirm_ms` (600), with gaps ≤ `reacquire_gap_ms` (250). Any
different candidate or gate failure resets the pending state. On binding the
target id is rebound, epoch is unchanged (same user selection), and normal
tracking resumes. `unlock()` and new selections clear the memory.

States: `lost` (memory live, no candidate) → `reacquiring` (pending) →
`tracking`; after `reacquire_window_ms` the state is `lost` with reason
`reacquire_window_expired` and reselection is required, exactly as today.

### Acceptance (measured, recorded in bench evidence)

- MOT17 gt suite: the 3 s outage recovers with correct identity within
  1 s of the target's return; **wrong-identity frames stay 0** across all
  sequences and outage patterns (the metric that must not move).
- Recorded phone video (controlled stream): control-valid frames increase
  materially over the 96-frame baseline with zero identity errors
  (target number measured, not promised).
- Existing `test_tracking.cpp` suite still passes unchanged except where a
  test asserts terminal loss, which gains a disabled-reacquire variant
  (`reacquire_window_ms` may be set to 0 to disable the feature entirely,
  preserving today's behavior).

### Test plan

Unit (TDD, `test_tracking.cpp` style): memory creation on expiry; born-after
-loss refusal of a pre-existing id; size/radius/appearance gate refusals;
ambiguity refusal with two lookalikes; N-of-M confirmation with reset on
candidate switch; window expiry; motion-compensated memory; disable switch.

Replay (deterministic, committed tools): `make_replay_input.py` (recorded
A/B detections → replay), `mot_to_replay.py` (MOT17 gt with visibility as
confidence, scripted drop windows, lock command, truth sidecar),
`score_lock_replay.py` (per-frame identity verdicts, outage recovery
latency, wrong-identity count). Evidence lands in
`bench/results/2026-09-12-reacquire/`.

## 3a. Phase A follow-ups (owner-directed 2026-09-12, after live board test)

Live board validation (letterbox + controlled HEF) exposed two things the
owner ruled on directly:

1. **5-tile detection, not single 640².** The fresh_node ran one 640²
   inference on the 1080p-downscaled stream, which under-resolves a phone on
   the 4K camera; the measured re-acquire failure on the phone's second
   return was weak return detection (conf 0.18–0.50), not the tracker. The
   node must adopt the stock five-tile layout (four 60 %×60 % corner crops +
   one full view, each letterboxed to 640, class-aware IoU-0.3 aggregation)
   feeding the same `garuda::fresh` re-acquire tracker. Reuse the node's
   existing `RegionDetector` crop→infer→map path, run it over the five tile
   regions of the paired source, aggregate, then track. ~5× sequential
   inference (~120 ms/frame) is the accepted cost, matching the stock path.

2. **Stable lock id across re-acquire.** Re-acquire rebinds to a new MOT
   track id, which reads as "lost it, grabbed a new one." The lock must
   present ONE persistent identifier from selection through every re-acquire.
   Design: a `lock_id` assigned once when a selection first succeeds,
   preserved across re-acquire, reset on unlock; the underlying MOT id stays
   available as `lock.track_id` (selection still references MOT ids). Owner
   chose stable-id + the existing gates (no mandatory appearance), since the
   phone has only a colour histogram that changes under rotation.

## 4. Datasets

- Primary: the 2026-09-11 phone-motion recording (both HEF detection
  streams, already extracted) and the owner-paced fast-motion captures.
- External: MOT17 labels (public detections + gt + visibility), downloaded
  to `hailo-export/datasets/MOT17Labels/`; gt visibility drives honest
  occlusion modeling. Not committed. Licence: MOTChallenge data is released
  under CC BY-NC-SA 3.0 — used here for local, non-commercial evaluation
  only; never redistributed with the repo and never used to train anything
  that ships (rule 6).
- Later (Phase C): VisDrone-MOT for drone-viewpoint sequences, and Gazebo
  scripted targets for analytic ground truth.
