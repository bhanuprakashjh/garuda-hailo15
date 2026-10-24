# Fresh drone tracking — delivery correction

The original request was an independent fresh object/person tracking stack for a drone on
Hailo-15L. The owner's “well i expected more” rejects closing that request after basic phone
retention. The goal is reopened. Existing measurements remain useful; their scope does not expand.

## Gaps established by inspecting the implementation

- `Tracker::update` and `snapshot` bind target identity to a short-lived detector track. After
  expiry the selected identity is discarded. There is no durable target appearance model or
  verified long-occlusion re-identification.
- `describe` is a72-bin colour/luminance histogram, with no learned embedding. Similar-looking
  subjects and changing backgrounds are not adequately evaluated.
- `MotionEstimator::update` fits one translation on a160x90 image with an8-pixel search. Rotation,
  scale, rolling-shutter motion and large camera movement are not modelled.
- Small objects are detected only from the full-frame640x640 input. There is no high-resolution
  target ROI inference or measured local/full-frame scheduling strategy.
- JPEGs and detector snapshots are asynchronous. Capturing their latest values together is not
  synchronized ground truth. Model-presence counts cannot establish tracking accuracy or identity
  retention. No annotated trajectory evaluation or matched Pi/15L comparison has been delivered.
- The new image_target output does not connect to existing SDK message contracts and garuda-follow.
  There is no demonstrated closed-loop simulation using the new board tracker.
- A storage-read stall was recovered, not explained. The32/128MiB diagnostic limits mitigate one
  plausible pressure source. Sustained platform validation and fault behaviour are unfinished.

The repository's earlier perception spec section8.1 explicitly calls tracking/follow the main
line; section8.2 calls for a target owner independent of incidental detector IDs and target ROI.
These requirements inform the fresh design; the old implementation need not be copied. The user
rejected template bridging as a substitute for fixing recognition, so that is not the deliverable.

## Work that must replace the previous completion bar

1. **A reproducible accuracy baseline.** Record frame identifiers with the exact model input and
   observations, stream recordings to the PC with bounded board memory, annotate the visible
   target and occlusions, and compare models/trackers on the same footage. Report localization,
   ID switches, false reacquisitions, lost time and reacquisition delay alongside latency and
   memory. Phone and person must both be represented; include camera movement and distractors.
2. **A stronger target pipeline.** Select model/input resolution using that evidence; implement
   and evaluate high-resolution target ROI with periodic full-frame verification. Give target
   identity its own appearance history and a conservative reacquisition policy. Evaluate learned
   appearance for people and suitable object features, including their licensing, NPU scheduling
   and CPU/memory costs. Evaluate rotation/scale-aware camera motion. Choose the design on measured
   results, not on the claim that hand-written code is inherently a fresh improvement.
3. **Actual SDK integration.** Define the target observation contract in interfaces/, preserving
   source clock, frame, validity, age, identity epoch and uncertainty. Connect it to the existing
   follow path in simulation and prove target loss, stale feed and identity ambiguity cannot
   produce continuing follow commands. Range remains unavailable until supported by calibrated
   evidence; box size alone does not become metres.
4. **A complete board demonstration.** One documented build/start/rollback path, understandable
   selection/loss behaviour, sustained run and resource/fault measurements, and a comparison with
   the existing Pi/15L baseline. Do not use another brief success report to close all these gates.

## Execution boundaries

The currently functioning board profile is the baseline. Reversible local work and read-only
inspection can continue while scope emphasis is clarified. No flight hardware is present;
repository rules require simulated endpoints for any new controller integration. No boot,
partition or driver configuration changes are part of this correction. No new dependency or
performance claim is selected merely by naming a model or algorithm here.

Owner emphasis is pending: stronger tracking, complete integration, or deeper model/camera
investigation. These change sequencing, not the requirement to deliver a coherent working stack.

## Progress after reopening — 2026-09-10

The baseline gap list above records the starting state. A learned person `TargetOwner` is now
implemented separately from MOT association, with immutable anchor, bounded recent history,
provenance checks and elapsed-time reacquisition. It is integrated behind the optional
`learned_person_identity` config. The host's pinned OSNet adapter ran concurrently with YOLOv8m
on the board; a software interruption expired control and then reacquired a new MOT ID in the
same identity epoch. Default behavior remains the previously working phone profile.

Seven identity/crop scenarios, the 21 existing tracking scenarios, transport tests, sanitizers,
SDK cross-build and native ARM execution pass. The 40-second follow-up stayed within the 200ms
freshness budget. These are implementation/integration checks, not an annotated identity accuracy
result. The model probe contains one person only. High-resolution DSP ROI, real distractor and
occlusion evidence, sustained load, camera-motion upgrades, SDK/follow simulation and matched Pi
comparison remain unfinished. See README and `learned-person-identity.json` for measured details.

Next: get exact synchronized evaluation inputs onto the PC with bounded board buffering; compare
full-frame vs actual high-resolution ROI on the same phone movement. Extend the learned person
bench to real occlusion and distractors before choosing identity thresholds or a default profile.

### DSP diagnostic and SDK/follow integration

The DMA-backed DSP crop adapter and bounded search planner now pass native/ARM
checks. Thirty-two actual DSP inputs from eight frozen phone annotations were run
through four existing HEFs and a float reference. Tight oracle-centered crops did
not consistently improve recognition, so local-only ROI inference is not enabled.
See `bench/results/2026-09-10-fresh-tracking/roi-diagnostic/`. This sparse oracle
diagnostic does not close the synchronized trajectory/accuracy requirement.

`interfaces/garuda_interfaces/target_observation.py` and the fresh follow adapter now
preserve source process/clock identity, frame, age, epoch, uncertainty and validity.
Two deterministic 500-tick loops run the actual C++ tracker through this contract
into the existing visual servo and kinematics. They converge and HOLD on occlusion,
ambiguity, source freeze, excessive delivery delay and changed selection. A real
blocked-HTTP test proves polling cannot stall the expiry tick. The board now emits
session/clock metadata; its unselected live feed parsed and held in a 15-second run.

This closes the missing pure SDK/follow integration implementation and synthetic
fault proof, not a flight demonstration or selected live perception/control accuracy
evaluation. Full-frame/ROI accuracy selection, learned object identity, camera-motion
improvement, synchronized streamed trajectories, physical distractors/occlusion,
sustained platform measurements and matched Pi comparison still need evidence.

### Rotation and scale compensation

An optional ORB/RANSAC background estimator now transforms track position, velocity
and uncertainty before association. Weak or localized support returns invalid motion.
The dependency-free translation mode remains default. Native, sanitizer and ARM checks
pass, including feeding the estimated transform into the actual selected-phone tracker.
On fourteen recorded images with nine generated transforms each, the ARM estimator
accepted 123/126 cases with maximum accepted error 2.1954 pixels at 640×360. These are
synthetic transforms, not measured physical camera trajectories. A 60-second empty-scene
live run processed 20.0004 frames/s with p95 age 157.54 ms; frequent low-support rejection
and additional CPU cost prevent default promotion without target-active evidence.
The working baseline was restored. See `CAMERA_MOTION.md` and its linked evidence.

This closes the missing rotation/scale implementation, not real camera-motion accuracy,
combined ReID/motion latency, learned phone identity or the full delivery requirement.

### Ground-truth scoring and same-input tracker comparison

`bench/fresh_target_score.py` now verifies complete exact-input recordings and joins
reviewed physical-target annotations by sequence, timestamp and pixel hash. It reports
detector recall, target localization, physical switches separately from MOT ID churn,
false reacquisitions, epoch mismatches, visible lost time and censored recovery episodes.
Unknown annotations and missing frame intervals do not become successful tracking time.
`fresh_target_replay.py` runs every recorded input through the actual C++ tracker with
one initial class selection, preserving source inputs and recording candidate hashes.

Eleven new scenarios pass, including an actual C++ dropout/recovery fixture with independently
specified expected durations. The saved 600-frame stream passes integrity and replay;
all its unreviewed accuracy denominators remain null. This delivers evaluation tooling,
not the still-missing annotated target-active dataset or model/identity accuracy result.
See `EVALUATION.md`. No board profile or runtime was changed for this phase.

### Paired higher-resolution input

The optional capture path now pairs every sampled detector input with the existing
1280×720 ISP-processed stream by exact integer exposure timestamp. Four owned source
frames bound history; missing requested pairs abort rather than substituting nearby
images. Both images share one bounded packet and are independently hashed on the PC.
Annotations and alternate predictions bind both hashes. No borrowed DMA buffers escape.

On the board, 600 consecutive pairs (1,198,080,000 bytes) transferred over 29.9334 seconds
with all 1,200 hashes verified and no timestamp mismatches, sequence gaps or pairing misses. The
enclosing 40-second run processed 20.0253 fps, with zero rejects; capture-period p95
HTTP image age was 147.09 ms. Source pairing, transport and geometry checks also run
natively, with sanitizers and on ARM. The original phone binary/profile was restored.

This closes the missing same-exposure source-frame recording path. It does not close
target-active ROI detector selection, phone identity or camera/ISP causality: the run
was a dark empty scene. See `CAPTURE.md` and the paired-stream evidence report.

### Synchronized stream and longer platform run

The optional loopback capture service now transfers exact detector NV12 pixels and
their own callback's detections/tracker response to the PC with a fixed two-frame
queue plus one in flight. It writes no board capture files, checks non-CMA memory
admission, and terminates on a slow reader/overflow rather than silently dropping
middle samples. The PC enforces frame/capture correspondence, hashes and completion.
On the board, 600 consecutive inputs (351.56 MiB) transferred over 29.93 seconds with
all correspondence/hash checks passing. The concurrent 40-second camera run stayed
near 20 fps with zero rejects and p95 image age 141.16 ms. See `CAPTURE.md`.

A separate 10-minute ordinary phone-profile run achieved 20.0003 fps, zero HTTP errors
or rejected frames, and maximum observed image age 179.25 ms. Resource sampling for
10 minutes found stable RSS around 80 MiB, at least 310 MiB non-CMA headroom and maximum
sampled temperature 80.415°C. Both runs were dark empty-scene tests with no selected
target. The streaming plumbing and baseline load are now measured; annotated
target-active accuracy, physical distractors/occlusion, high-resolution source-frame
pairing, camera motion, learned object identity and matched Pi comparison remain.

### Learned object appearance candidate

The shared Hailo NV12 embedding adapter now supports explicit input geometry while
preserving the OSNet defaults. The factory CLIP ViT-B/32 image encoder was run on
17 pinned JPEG-derived crops: eight prior phone views, seven physical-phone
alternatives, one printed-phone stress example and an exact duplicate. Median NPU
inference was 20.084 ms plus 5.796 ms median CPU crop; the person adapter reproduced
all 38 previous 512D outputs exactly. Wrong-model geometry rejected before inference
and the subsequent OSNet call recovered normally. The baseline camera was restored.

CLIP offers an experimental appearance cue, but same-phone and cross-phone cosine
ranges overlap across reference views; a printed phone also scores highly. No live
phone identity gate is enabled from this evidence. The implementation/probe and
reproducible diagnostic are complete; reliable learned phone identity, hard
distractor/trajectory evaluation and detector-plus-encoder load remain open. See
the [model card](../../models/clip_h15l.md) and
[measured evidence](../../bench/results/2026-09-10-fresh-tracking/object-embedding/README.md).
