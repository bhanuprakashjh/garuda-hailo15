# Independent audit of the Hailo-15L follow handoff

2026-09-13. Reviewed commit `237ae7bae4bd9755ad095ed041bf10ab00d9dc9c` on
`feat/hailo15l-fresh-tracking`. Read the handoff first, then `CLAUDE.md` and
the relevant decisions, implementation, evaluation tools and evidence.

## Verdict

Keep this project and the controlled YOLO11s as the phone-demo baseline.
There is real, reproducible progress, but the evidence does **not** establish
robust end-to-end aerial follow. Do not promote the board bridge as the next
milestone. First repair and measure acquisition-to-ROI handover, preserve
pixels for identity, and make the replay exercise the actual live scheduler.

The likely remaining failures are not explained by a single YOLO version:
the detector, crop scheduler, input resolution, association and identity
verification have different limits. A stable `lock.id` alone does not prove
that the box remains on the selected individual.

This was a diagnostic review. No board files, camera settings, selection,
running process, HEF, product code, or FC parameters were changed. No vehicle
commands or new PX4 sessions were launched. New files/log entries document
the audit; they are not a deployment or a commit.

## What was independently verified

- The requested worktree was clean at audit start, at `237ae7b`. It is
  **204** commits ahead of master at this tip; the handoff's 203 refers to
  the preceding implementation tip. The main checkout separately has
  existing untracked files and is not clean.
- Board SSH and `/api/state` work. Running PID 20153's `/proc/20153/exe`,
  the installed executable and the host deployment executable all hash to
  `3c99fbc963e4efbcfb43c7a92207d96e16aab0ee8d7415c08e0f2460653f9e02`.
- Active `current.json` matches the follow configuration described in the
  handoff. Board YOLO11s SHA is
  `aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58`;
  OSNet SHA is
  `49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7`.
- Actual configured streams: sink0 **640×640 letterbox**, sink1
  **1280×720**, both configured at **20 fps**. Sensor profile points to the
  IMX678 4K profile. The tile/ROI source is sink1, not native 4K pixels.
  Historical 25 fps observations are not the current configured rate.
- A read-only 20-sample watch spanned 9.4876 s and 57 processed sequences:
  6.0078 updates/s, age median 364.3402 ms, maximum 438.8204 ms. All samples
  were `tiled`; rejected frames remained zero. The selected phone was
  already `lost / reacquire_window_expired`. OSNet and ROI counters did not
  advance during this watch. This is a searching-state sample, not a
  person-in-view or locked-ROI throughput benchmark.
- Rebuilt the native tracking library/replay from current source in an
  isolated scratch directory: **7/7 CTest targets passed**. Python follow
  tests: **20 passed**; bridge: **5 passed**; tracking: **45 passed, one
  adapter module skipped** because its staging environment was absent.
  VisDrone-tool tests: **15 passed** after supplying `PYTHONPATH`.
- Recounted the raw 2,165 region predictions per HEF for the 433-frame
  phone recording. At score 0.15: old 191 frames, controlled 322; at 0.5:
  old 129, controlled 200. Median summed tile waits: 94.3890 vs 122.14532 ms.
  These match the archived A/B report. This measures **phone-class presence**,
  not annotated target recall or live FPS.
- Recomputed **both complete 548-image VisDrone DET reports** from the raw
  predictions and archived preparation annotations. Both metric dictionaries
  exactly match `bench/results/2026-09-12-visdrone-det/score.json`.
- Recounted all five saved SITL tick logs. Nominal: 801 follow ticks, 800
  ACTIVE, median settled distance 5.699 m and absolute framing error 0.03305.
  Target loss: 26 COASTING and 34 HANDOFF ticks. Stall: 39 hover ticks.
  The saved numbers check out, but perception was synthetic.

Limits: no new NPU dataset inference, full SOT/OSNet replay, ARM rebuild,
live target-selection test, motion trial or SITL execution was performed.
SOT conclusions below combine source review and saved scores; they are not
claimed as new on-board reproductions. Host/board versions and these runs
are recorded in `bench/versions.md` and `bench/benchlog.md`.

## Findings, ranked by what should change next

### 1. High: acquisition can remove the evidence needed to sustain the lock

`hosts/hailo15l/fresh_node.cpp:326` disables tiles once a current target ID
is present outside none/lost. The next frame uses the coarse full-view
detector plus an optional ROI. However:

- `fresh_node.cpp:378` allows ROI only when the current frame is at most
  **100 ms** old; `services/garuda-tracking/src/search_region.cpp:78`
  independently enforces the same hard-coded limit.
- `RoiAssist::plan`, lines 91–102, requires recent matching full-view
  detections and stops after **400 ms** without them. It cannot start if
  such primary evidence was never established in the assist state.
- ROI needs a previous usable box and tracking/qualified coasting state;
  it is not an independent visual tracker that keeps searching through
  every identity-refusal state.

An isolated probe linked to the freshly built library used the same valid
small-person target over 20 frames: primary detections and 60 ms age produced
10 ROI requests; primary detections and 101 ms age produced **zero**; no
primary detections and 60 ms age produced **zero**. Existing tests also
confirm ROI-only detections cannot renew the 400 ms deadline.

Thus a target visible only at tile scale can be acquired and then lose
the very detection scale that found it. This is a code-supported failure
mechanism, not a claim that it caused every observed dropout.

Recommendation: an explicit handover state that seeds the target ROI from
the accepted acquisition observation and verifies repeated local evidence
before retiring acquisition coverage. Keep periodic global search and
identity/drift checks. Separate the permission to *search pixels* from the
permission to *command motion*. Do not simply extend all timeouts or allow
unbounded ROI-only self-confirmation. Measure the deadline budget and make
skip reasons distinguishable (`age_budget`, `no_primary`, `no_target`, etc.).

### 2. High: live identity uses fewer pixels than the offline evidence

At `fresh_node.cpp:322`, `image` becomes the content of the 640×640
letterbox: **640×360**. Both `describe(image, ...)` and
`person_embedding->infer(image, ...)` use that content, including for boxes
found by the higher-resolution tiles/ROI. The paired 1280×720 source is
available but is not used for OSNet.

Conversely, `bench/hailo_reference/embed_visdrone_sot.py` builds OSNet crops
from the **1280×720 canvas**. The resampling recipe is similar, but the
input pixels are not equivalent. Relative to the live identity input,
the offline source has twice the linear resolution and four times the
pixel area. This is geometry, not an accuracy claim.

Recommendation: first compare byte-traceable, same-timestamp OSNet crops
from the live 640×360 content and the already-paired 1280×720 image. Then
test retaining a higher-resolution ISP branch for target crops, including
native 4K if its bandwidth/copy costs fit. Keep the detector input 640² for
this comparison. Do not conclude that a different ReID model is required
until crop quality and preprocessing parity have been tested.

### 3. High: offline follow results do not exercise the live feedback loop

`sot_to_replay.py` and `run_sot_replays.py` use:

- ground-truth-centred ROI regions, and ground truth to decide whether
  primary evidence is recent;
- ROI merging before lock and without the live ROI cadence/deadlines;
- an assumed **30 fps** stream and default **10 ms** latency;
- static single/five/roi flavours, not the live tiles-to-ROI transition;
- different descriptor coverage and source resolution from the live node.

The MOT mechanism experiments additionally use idealized appearance,
ground-truth detections and, in the sweep, ground-truth camera motion.
Those are useful unit/mechanism experiments, not robust identity evidence.
The eleven-sequence SOT expansion is labelled **histogram/default config**,
not eleven sequences of the final live OSNet follow configuration.

Recommendation: a causal replay in which the actual prior tracker output
chooses the next crop, the scheduler consumes measured time, stale frames
are dropped, and the same embedding budget/pixel source/config are used.
Truth must be available to the scorer only after initialization, not to
the ROI planner. Retain oracle results as a labelled comparison, not a
live-performance claim. Use held-out clips for threshold selection checks.

### 4. High before bridge work: simulation safeguards are incomplete

The simulation is explicitly synthetic in its README and source; the
handoff's phrase "from the tracker's output" overstates that integration.
`bench/sim/followme_sitl.py:perceive` projects a known world target and
constructs `identity_verified` itself. It does not run YOLO or Tracker.

Additional concrete issues:

- `run_scenario(..., execution='preview')` still reaches `vehicle.arm()`
  and `set_offboard()`; only setpoint sends are conditional. LAND calls
  are also outside that execution check. A fake-vehicle/no-network probe
  reproduced **ARM invoked in preview**.
- `FollowAuthority.update` checks `control_valid` and `command.valid`,
  but not `observation_valid`, command age or sequence. It stamps a fresh
  intent timestamp on each update. A pure probe resubmitted an unchanged
  command timestamped zero at 1 s and 6 s: both yielded eligible nonzero
  setpoints, even with `observation_valid=False` and preview execution.
  This does not show the current board emits contradictory flags; it shows
  this proposed authority/consumer boundary does not enforce its contract.
- `setpoint_from_intent` does not enforce preview mode or reject future
  timestamps. `target_view` drops source/stream/clock identity. The older
  `FreshFollow` already contains stricter identity/age/duplicate-frame
  checks, but the new SITL chain bypasses it.
- An environment flag plus an arbitrary UDP endpoint is **not network
  isolation from real hardware**. The default binds all interfaces. The
  statement that nothing here can reach a real FC is not enforced.
- The publisher-failure scenario raises a synthetic send exception while
  leaving LAND delivery available. It does not prove behaviour on actual
  total link loss, where the LAND command may also be undeliverable.

Recommendation: reuse the validated freshness adapter, carry producer
identity and original observation deadlines end to end, make preview
strictly no-I/O, and isolate SITL to a verified local endpoint/process.
Test duplicate observations, process restart, future timestamps, no
telemetry, command rejection, and full transport loss with fake transports
before new SITL runs. FC-side loss behaviour must be tested independently:
[PX4's official offboard documentation](https://docs.px4.io/main/en/flight_modes/offboard)
specifies the proof-of-life timeout and configured offboard-loss action;
an application cannot assume its last LAND request was received.

### 5. Medium: two deferred geometry defects are reproducible now

- `SearchRegion::cuts_object` compares network coordinates against outer
  image edges rather than letterbox content edges. A box touching the
  interior top edge of a lower 768×432 tile maps to network y=0.21875 and
  is **not rejected** with margin 0.08.
- `aggregate_tile_detections` sorts by confidence and suppresses by
  containment without considering which box is the fragment. A contained
  0.9-confidence fragment of height 0.1 suppresses the 0.8-confidence
  full-person box of height 0.4; the probe retained only the fragment.

Recommendation: correct content-space boundary tests and make duplicate
resolution aware of crop provenance/truncation. Regression cases must also
preserve two real overlapping people; globally preferring larger boxes is
not a sufficient fix.

### 6. Medium: acquisition work and locking inflate latency

The primary AI-stage YOLO pass already ran before the sink callback. In
search mode, that callback runs **five additional** sequential inferences
and discards the primary detections: six YOLO passes per processed search
frame, not five total. All of that work, ROI and OSNet run under
`tracking_mutex`. `RegionDetector::infer` also copies the source image for
each region. Therefore the reported tile inference sum is not the complete
pipeline cost, and publishing/selection can wait for inference work.

Recommendation: one bounded inference scheduler, snapshot/request ownership
under a short lock, inference outside the lock, and sequence/epoch checks
when committing results. Avoid duplicate full-view work only after proving
pixel/mapping parity: the current primary and paired-source resize paths
are not automatically byte-identical. Profile source copies before raising
source resolution. No FPS gain is asserted until measured.

## Corrections to the handoff's interpretation of evidence

- Controlled YOLO11s is better on the phone recording, not uniformly
  superior on aerial data. Recomputed five-tile person recall at 16–32 px
  is **0.2102 controlled vs 0.2302 old**; at 32–64 px it is **0.5770 vs
  0.5773**. Controlled five-tile FP/image is lower, 11.394 vs 12.301.
  Preserve that tradeoff rather than saying "no regression" categorically.
- "Nothing under 16 px" is too absolute: controlled five-tile person
  recall there is **63/2628 = 0.0240**. It is very poor, not zero.
  The SOT table also contains detected/locked targets listed at 20–24 px,
  so "below 25 px invisible at any scale" is not a supported universal rule.
- SOT `control_valid_off_target` means the target IoU test failed. With no
  other identities annotated it does **not**, by itself, prove every such
  frame is an identity switch rather than inaccurate localization.
  Similarly, `on_target_rate` can include non-control-valid coasting boxes.
- The margin 0.04 sweep trades availability for more off-target frames:
  e.g. 024/five **21 → 32**, not a strict safety improvement. It was tuned
  on the reported sequences; generalization remains unverified.
- The raw A/B score explicitly says class presence, so the stronger
  conclusion "the detector is no longer the constraint" is not established
  for fast motion, small targets, or different scenes.

## Proposed implementation order and acceptance gates

1. **Preserve this baseline and repair the test contract.** Keep current
   model/config hashes and rollback. Add the reproduced cases as regression
   tests; distinguish detector misses, ROI ineligibility, association
   switches, identity refusals and stale publication in telemetry.
2. **Fix geometry and the tiles-to-ROI handover.** Verify tile-only targets
   can enter sustained local tracking without a forced coarse-detector
   failure. Maintain bounded search and refuse motion on unverified evidence.
3. **Restore identity pixels and measure scheduling.** A/B same-frame
   640×360 vs paired 1280×720 OSNet crops first; then higher-resolution
   target crops. Remove unnecessary copies/inferences with parity tests.
4. **Run causal replay plus one structured desk recording.** Use fixed
   initial selection, fast lateral movement/rotation, target becoming
   smaller, occlusion/return, and a bystander crossing where available.
   Report target IoU, wrong-person binds, verified observation availability,
   longest gap, recovery time, crop usage and frame age separately.
   New live results and numerical acceptance thresholds: **TBD-bench**.
5. **Only if those checks leave a tracking gap, evaluate a visual/template
   tracker in shadow mode.** It can propose ROI location between detector
   observations; it must not silently become identity or motion authority.
   Test a stronger/domain-appropriate ReID model only against crop-quality-
   matched baselines. Vehicles need a separate identity evaluation: person
   OSNet does not solve look-alike car selection.
6. **Harden the sim boundary, then connect real perception to PC-side
   preview/SITL.** Recorded detections can test transport/freshness and state
   handling, but a prerecorded image cannot close a visual feedback loop
   responding to vehicle motion. A rendered sensor or appropriate
   hardware-in-loop setup is needed for that claim. Board/real-FC bridge
   work remains a later, separately validated step.

## Reproduction notes

Fresh native build and the isolated C++ probe are retained at
`/media/bhanu1234/Development/hailo-export/scratch-independent-audit-20260913.ypRHV2`.
The probe source is `audit_probe.cpp`; it links the just-built
`libgaruda_tracking.a`. It changes no library source.

```sh
cmake -S services/garuda-tracking -B <audit-build> -DCMAKE_BUILD_TYPE=Release -DGARUDA_TRACKING_OPENCV=OFF
cmake --build <audit-build> -j2
ctest --test-dir <audit-build> --output-on-failure
GARUDA_REPLAY_BIN=<audit-build>/garuda-track-replay python3 -m unittest discover -s services/garuda-tracking/tests -p 'test_*.py'
GARUDA_REPLAY_BIN=<audit-build>/garuda-track-replay python3 -m unittest discover -s services/garuda-follow/tests -p 'test_*.py'
python3 -m unittest discover -s services/garuda-bridge/tests -p 'test_*.py'
PYTHONPATH=bench/hailo_reference python3 -m pytest -q bench/hailo_reference/test_visdrone_tools.py
```

The first VisDrone test invocation failed collection without its import
path; it passed once supplied. The initial Python run skipped replay tests
until the fresh binary was supplied. These setup failures were not product
fixes. No existing benchmark output was overwritten.
