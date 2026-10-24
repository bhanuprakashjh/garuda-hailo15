# Hailo-15L follow-tracking campaign — brief for an outside reviewer (2026-09-05)

Written so that a model or engineer with no access to this repo can judge the work and advise on
the next steps. Every number below was measured on the bench and is recorded in
`bench/benchlog.md`; nothing is estimated. Where something is *not* measured it says so.

## 1. What this is

Garuda SDK is a companion-computer autonomy stack for drones. The bench has two devices:

- **Pi 5 + Hailo-10H (40 TOPS)** — the original dev tier. Runs `garuda-mono`: YOLO26m detection
  every frame, a ByteTrack port with click-to-lock, monocular depth. On this device a hand-held
  phone tracked "immaculately" (owner's word) with a narrow-FOV Camera Module 3.
- **Hailo-15L SBC** (4× Cortex-A53, 2 GB RAM, a much smaller NPU than the 10H, IMX678 4K sensor
  behind a very wide lens, HailoRT / firmware 5.3.0) — the product-tier proxy. This campaign
  builds the perception node on it.

**Main goal, set by the owner on 2026-09-04:** object detection + tracking + *follow* on the
drone. VIO and mapping are parked. The flight controller (a PIC32CZ CA90 running PX4) is a
separate board; the node must publish a target the FC can follow, never run the inner loop.

## 2. The node on the SBC (branch `feat/hailo15l-kalman-tracker`, 70 commits over master)

Pipeline (Hailo `hailo_analytics` on the SBC): ISP → DSP resize to the detector input (640×640,
**stretched** from 16:9) → NPU detector → on-chip NMS → multi-object tracker → our node →
snapshot JSON + JPEG feed → a Python shim → browser GUI (SSE box stream 30 Hz, MJPEG 30 fps).

- **Detectors tried** (all Hailo model-zoo 5.3.0 compiles for hailo15l; Ultralytics AGPL upstream,
  bench-only): yolo26m (own post-process plugin), yolov8m, yolov11m, yolov11s. Follow profile is
  now **yolov11s** (owner decision 2026-09-04 after the A/B in §4).
- **Multi-object tracker engines**: (a) the ByteTrack port from the Pi ("mono"); (b) the SDK's
  JDE Kalman `TrackerStage` ("hailo"), class-agnostic one-to-one LAPJV assignment; can be
  restricted to one class (`classification_id`). The follow profile is person-only.
- **Lock core (F1, new)** — `garuda::lock::LockCore`, a dedicated locked-target tracker on top of
  whichever engine runs:
  - states NONE → CONFIRMED → OCCLUDED → REACQUIRING → LOST, all windows in **milliseconds** from
    the ISP timestamp (occlusion 500 ms, widened search until expiry, expiry 10 000 ms);
  - constant-velocity Kalman on the box centre, white-noise-acceleration process noise, used
    **only for gating and search**; measurement noise scaled to the box (10 % of size), gate floor
    15 % of the box, gate cap 300 px; a relative size model (size noise 15 %, growth 50 %/s);
  - candidate scoring = 0.25·conf + 0.35·motion + 0.15·size + 0.15·class + 0.10·same-tracker-id,
    ambiguity margin 1.3 (two close candidates → no choice), floor 0.5 in CONFIRMED/OCCLUDED and
    0.4 while REACQUIRING; two-stage association (in-gate pool first, out-of-gate pool only if the
    first yields nothing);
  - hard rules added after live failures: a different class is accepted only with tracker-id
    continuity; a new id must be within a 1.6 size ratio; a candidate accepted only through the
    same-id relaxation updates position but not size;
  - **prediction never reaches the screen**: the published box is the smoothed box when
    CONFIRMED, the last confirmed box frozen while OCCLUDED/REACQUIRING, none when LOST.
    Published fields: `state, identity_locked, observation_valid, quality, obs_age_ms,
    uncertainty_px, epoch, box, id, class`. Flight follow may act only on `observation_valid`.
- **Resolver** (click / class auto-acquire) feeds the core; auto-acquire needs conf ≥ 0.5, the box
  clear of the left/right edges, and 5 gated frames within the last 15.
- **Adapter fixes on the SDK tracker output**: same-class duplicate suppression (a box ≥ 80 %
  inside a larger one is dropped; IoU ≥ 0.6 keeps the higher confidence), a birth gate (a track is
  emitted only after one detection ≥ 0.4), and a class allow-list per config.

## 3. Bench method

Owner-paced routines in a small lit room, SBC on a desk, owner alone. The PC records the node's
snapshot stream with wall-clock timestamps; a harness (`bench/evidence/2026-09-04-lock-core/
lock_metrics.py`) computes state fractions, misses while the engine had a live box
(`core_miss_live`), re-locks (epoch changes), class switches, id churn, expiries, re-acquisition
times, off-screen boxes. Two more tools give detector-side statistics (live-box rate, confidence,
ids, duplicate boxes) and lock-box jumpiness. Every capture is committed gzipped. Replay tests feed
committed captures through the core (regression guards, not independent evidence).

Red-team caveats that apply to everything below: single operator, no ground truth beyond the
owner's own reading, one run per condition unless stated, ~10–30 Hz sampling of a 30 fps node, a
mesh-backed chair that never fully occludes, and fixes derived from the same captures that the
replay tests use.

## 4. What was measured

**Person, follow profile (yolov8m at the time), 2026-09-04:**

| Routine | Confirmed | Core misses while live | Re-locks | Expiries | Longest re-acquisition | Notes |
|---|---|---|---|---|---|---|
| Walk-out / return, before fixes (run 5) | 62 % | 29 % | 4 | 1 | 10.5 s | three gate failures, see §5 |
| Walk-out / return, after round 3 (run 6, 69 s) | 89 % | 0 % | 0 | 0 | 1.8 s | tracker renumbered the owner 6×, ridden through |
| Fast lateral (run 8, 313 s) | 99 % | 0.2 % | 1* | 0 | 0.5 s | *one operator click; 41 tracker id changes ridden through |
| Occlusion behind a chair (run 9b, 80 s) | 26 %† | 0 % | 0 | 1‡ | 0.9 s | †room empty for half the window; ‡owner left the frame > 10 s |
| Two-person swap | not run (no second person; an informal run was "ok", not measured) |
| Person, yolov11s, round 7 (150 s) | 99 % | 0 % | 0 | 0 | 0.8 s | one id change |

**Phone (all classes tracked, click-locked):**

| Condition | Detector live-box rate | Median conf | Tracker ids | Lock result |
|---|---|---|---|---|
| yolov8m, 2026-09-04, first 2 min of movement | 37 % | 0.55 | 38 in 2 min | held through all 38 ids; then a **silent false lock** (§5) |
| yolov11s, 2026-09-05 (round 8), 2 min | 32 % (60 % in the first minute) | 0.59 | 17 | 0 class switches, 0 misses while live; 6 box jumps > 80 px, all at gap ends (max 322 px); two 10-s expiries during a deliberate hide; **one automatic re-lock** |

**Detector A/B on the phone (2026-09-04, 75 s each, one owner-paced run per model, same
stretched input):**

| Model | Frames with a phone box | Median conf | Still phase | Moving phase | Hailo zoo mAP / fps |
|---|---|---|---|---|---|
| yolov8m | 44 % | 0.32 | 41 % | 47 % | 49.6 / 39.7 |
| yolov11m | 47 % | 0.67 | 17 % | 63 % | 50.7 / 33.4 |
| yolov11s | 71 % | 0.56 | 92 % | 61 % | 46.1 / 86.7 |

The person was detected at 0.86–0.92 under all three. The still-phase spread (17 % vs 92 %) cannot
be attributed to the model alone; a repeat with the phone in a stand, three interleaved runs per
model, is owed before the choice is final.

**Other measured facts:** the published lock box moves a median 0.0–0.5 px per frame while
confirmed; duplicate person boxes went from common to 0 % and id churn from 41/5 min to 2/2 min
after the adapter dedupe; the node saturates one A53 (100 % of one core; whole SoC ~42 % busy);
SoC 83 °C after 7 h (the board hung once the previous morning after an 85 °C reading — cause
unproven), 70 °C after a night at 30 fps.

## 5. Failure modes found live, and what was done

1. **Edge sliver lock** — auto-acquire took a 29×194 px, conf-0.17 sliver as the owner entered;
   the size gate then rejected every larger box for 10 s. Fix: auto-acquire needs conf ≥ 0.5 and a
   box clear of the frame edges.
2. **Junk-track lock in the dark** — a chair read as a person at ~0.2 with one frame ≥ 0.5. Fix: a
   streak of gated frames (now 5 of the last 15).
3. **Converged gate tighter than box jitter** — a 650 px person box's centre jumps 40–60 px when
   an arm moves; the converged gate was ~10–17 px. Fix: measurement noise scaled to box size, gate
   floor, true innovation-covariance gate.
4. **Size reference frozen on a partial box** — the owner walked toward the camera and tripled in
   width in 1.4 s; the absolute size model refused it for 10 s. Fix: relative size model plus a
   relaxation for a live box carrying the core's own tracker id.
5. **Lone re-entry candidate rejected** — a new tracker id at conf 0.82 scored 0.45 < 0.5 in the
   widened stage. Fix: widened floor 0.4.
6. **Head-only box learned as the size** during a 6-s hide behind a mesh chair, then the full
   body was unrecognisable. Fix: relaxed matches update position only; the widened floor applies
   to in-gate candidates while REACQUIRING; the widened window lasts to expiry.
7. **Silent false lock** — after the phone left, the core hopped across different-class boxes at
   scores 0.40–0.56 and settled on a static suitcase (conf 0.9) for twelve minutes while publishing
   "cell phone"; the re-lock metric and the class field were both blind. Fix: different class
   needs tracker-id continuity, size ratio cap 1.6 for new ids, the published class follows the
   winner, the harness counts class switches. Verified by replay and by the 2026-09-05 run.
8. **Two ids on one person** — the detector emits a full-body and a torso box; the SDK tracker
   births both. Fix: containment/IoU dedupe on the emitted tracks.
9. **Clutter and no re-lock** — under all classes the tracker births tracks from any detection
   (handbag 0.17); after a lost phone the consecutive-streak rule never re-fired. Fix: birth gate
   0.4, 5-of-15 streak, class allow-list.
10. **Found by an outside review of this brief (2026-09-05), fixed as round 9** — five defects in
    the code, and one in how it is being watched. (a) The display gates (birth conf, duplicate
    dedupe) also decided what the lock core could see, so a locked object dipping below the birth
    confidence became invisible to the tracker whose job is to ride that out — the core now takes
    all live detections, while a *new* lock still requires a published one. (b) The dedupe deleted
    a person standing behind a nearer person, because containment cannot distinguish that from one
    person detected twice — an established track (≥ 10 published frames) and the locked id are now
    exempt, duplicate births are not. (c) The widened, full-frame re-acquisition stage accepted a
    *new* tracker id: a lone same-class object 900 px away at confidence 0.41 took the lock
    outright, and with no appearance model nothing in the frame could say otherwise. The first fix
    (round 9) refused every such candidate and **cost real recovery** — the committed occlusion
    capture's 6-second hide stopped recovering and the phone replay fell from 0.82 to 0.19 — so it
    was re-ruled (round 10). Such a candidate is now accepted only if its tracker id was **born
    after the target was lost** (an id that was alive while the target was still confirmed is by
    construction a different object, which removes the classic two-person swap with no appearance
    model), it is the only out-of-gate candidate that frame, its confidence clears 0.5, and the
    target has been missing no more than 5 s. The occlusion capture recovers fully again; the phone
    capture does not, because that 5 s ceiling misses one 6392 ms re-acquisition — a single constant,
    measured and left to the owner (`bench/benchlog.md`, "Round 10"). (d) Expiry advanced only when
    `update()` was called, so a stalled pipeline could resume 11 s later and carry on as if nothing
    had happened — expiry is now elapsed time. (e) `control_valid_ms` was parsed and never used;
    the snapshot now publishes `lock.control_valid`, which is what a follow controller must gate
    on. (f) **Not a code defect and not fixed here**: the PC portal on `:8080` re-tracks the
    board's tracks with its own ByteTrack and its own target, so every judgement of the lock so far
    has been made through a second tracker. The shim now serves a board-truth viewer at
    `http://<board>:8098/`; fixing the portal belongs to the portal branch.

## 6. What the owner sees, and why

The owner's judgement is that the SBC pipeline looks "much lower fidelity" than the Pi, and that
the phone lock is "all over the place". What the captures show is that the *published* phone
observations are intermittent — a live phone box in 32 % of rows on the 2026-09-05 run, with gaps
up to 8.6 s — and that on every row where the engine did hold a live box for the locked id the core
was CONFIRMED (`core_miss_live` 0 %, 884 rows). The lock box freezes during a gap (by design) and
jumps when a detection returns somewhere else, all six of the >80 px jumps landing on an id change.

**Conclusion, stated no further than the evidence reaches:** published phone observations are
intermittent, and the lock core accepts the observations it receives. Raw detector recall, physical
identity retention, and displayed tracking accuracy remain to be isolated and measured.

(Two things make that conclusion narrower than it looks. First, "the engine had a live box" is
measured from the node's own published `tracks[]`, which is downstream of the class allow-list, the
birth gate and the duplicate dedupe — so it is not a measurement of the detector. Second, until
2026-09-05 nobody had *seen* the board's lock at all: the owner has been watching the PC portal,
which re-tracks the board's tracks with its own ByteTrack and its own target. See §5 item 10.)

Hypotheses for the detector gap, none yet tested in isolation: the 16:9→square stretch of the
detector input (the Pi letterboxed); the 15L quantised compile versus the 10H's; sensor/ISP noise
indoors; the small NPU forcing 640 px input. The owner disputes field-of-view as a cause (he fills
the frame more here than on the Pi).

## 7. Planned next steps (spec §8.2 of the perception-node design)

- **F2 visual tracker between detections** — sparse optical flow on the target patch every frame
  on the CPU, so the box follows the object's own pixels across detector gaps (a measurement, not a
  prediction). Recommended next; the owner has not yet said go.
- **F4 zoom window** — the DSP crops a region around the lock and feeds the detector a higher-
  resolution view. The crop itself is free (the DSP is already resizing), but the inference is not:
  it costs nothing extra only if the crop *replaces* the full-frame inference, and a scheme that
  runs both alternates frames between them or needs NPU headroom the 15L may not have. The lever
  for small and distant targets, with that caveat attached.
- **F3 appearance templates** (colour signature) — required before any multi-person scene can be
  trusted; today only the ambiguity margin protects the widened window.
- **F5 click–frame sync + on-board overlay**; **F6 ego-motion** from the ISP's global motion
  vectors before the camera flies.
- Range (mono depth port or ToF), then a **follow controller** against a simulated FC first
  (PixEagle, Apache-2.0, is the reference design; PX4's FOLLOW_TARGET path is the candidate FC
  hook, unverified).
- Bench: repeat the A/B properly; letterbox vs stretch; float-vs-HEF on dumped frames; profile
  the one-core saturation; a fan on the board.

## 8. Questions for the reviewer

1. Is the lock-core design (time-based states, prediction never published, guarded two-stage
   re-acquisition, class hard-gate without appearance) sound for a drone follow target, and what
   would you change before F3 exists?
2. Given a detector that sees a moving phone in 30–60 % of frames, is F2 (optical flow between
   detections) the right next lever, or should F4 (zoom crop) or a detector-side change (letterbox,
   a different compile, a small-object model) come first?
3. The widened search now runs until the 10-s expiry with floor 0.4 and only an ambiguity margin
   as protection. Where would you set the risk line for a multi-person scene?
4. The SDK tracker flips between two ids on one moving phone frame by frame. Is it better to
   replace the multi-object tracker under the lock core with something simpler, or keep riding
   through id churn as the core does now?
5. The node saturates one A53 while the DSP and NPU do the heavy work. What would you profile
   first?
6. The evaluation is owner-paced with no ground truth. What is the cheapest protocol that would
   make these numbers defensible (fixtures, repeats, a phone in a stand, recorded clips replayed
   through the whole pipeline)?
7. Anything in §5 that looks like a symptom of a deeper modelling error rather than a tuning gap?

## 9. Where things are

- Branch `feat/hailo15l-kalman-tracker` (tip `4f962a0`, clean), not yet merged; the owner has to
  choose merge / PR / keep.
- Board: Hailo-15L SBC at 10.0.0.1, running the committed phone-demo config
  (`services/garuda-perception/config/perception-yolov11s-phone.json`, person + cell phone). The
  follow profile is `perception-yolov11s.json`.
- The 2026-09-05 phone capture behind §4's yolov11s row and §6's numbers:
  `bench/evidence/2026-09-04-lock-core/run13_round8_phone_reacquire.txt.gz` (3071 rows / 120 s);
  the three tool rows are in `bench/benchlog.md`, "2026-09-05 — phone lock on the round-8
  phone-demo config (run r8_phone_a)".
- **The board's own view of its lock is `http://10.0.0.1:8098/`** (the shim's index page, round 9).
  The PC portal on `:8080` re-tracks and must not be used to judge the lock until the portal branch
  consumes the board's `lock` object.
- Evidence: `bench/benchlog.md` sections dated 2026-09-03/04/05, captures and tools under
  `bench/evidence/2026-09-04-lock-core/`; design: `docs/superpowers/specs/2026-09-02-hailo15l-
  perception-node-design.md` §8.2; decisions: `docs/decisions.md` (Rulings 1–25 of 2026-09-04,
  26–31 of 2026-09-05); code: `services/garuda-perception/` (`lock_core.*`, `lock.*`,
  `hailo_track_adapter.*`, `node_main.cpp`).
