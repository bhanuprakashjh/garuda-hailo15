# Garuda fresh tracking

**Current desk-board checkpoint (2026-09-11):** [YOLO11 r2 experiment and handoff](../../docs/2026-09-11-hailo15l-checkpoint.md).
The separate project viewer at port 8099 imports Hailo tracks for all COCO classes,
with viewer-only selection and latched loss. R2 tests letterboxing and low-score
association; it is not validated flight tracking. The [integration history](HAILO_BASELINE.md)
and prior person/phone baselines are preserved. The custom stack documented below
is not the current board pipeline.

**Status: baseline implementation; larger delivery incomplete.** The owner rejected the previous
completion assessment. [Remaining delivery](DELIVERY.md) covers the missing capability and validation.

The stack now includes [exact-input streaming capture](CAPTURE.md) and
[SDK/follow integration with a simulated closed loop](../garuda-follow/README.md).
The [accuracy evaluator](EVALUATION.md) joins reviewed target identities to exact inputs
and measures detector misses, physical switches, lost time and sampled recovery delay.
The ordinary phone profile completed a ten-minute empty-scene run at 20 fps with zero
rejected frames; 600 consecutive exact model inputs also streamed to the PC without
board capture files. These validate integration and baseline load, not target accuracy.
The [DSP crop/model diagnostic](../../bench/results/2026-09-10-fresh-tracking/roi-diagnostic/README.md)
did not justify enabling tight crops as the phone detector's default input.

An independent C++17 object/person tracking stack for the Hailo-15L drone companion.
Live IMX678 → Hailo YOLO → tracking → target validity → browser preview is running on the bench.
YOLO11s was person-tested; the current phone candidate uses YOLOv8m with verified letterboxing.
The owner reported good person tracking and confirmed that phone lock now survives movement outside the body outline after the input-geometry correction. This remains a bench prototype; measured results and limitations are below.

The implementation is on branch `feat/hailo15l-fresh-tracking`,
based on `9582f1d`. The tracker, appearance/motion code, and target policy are new.
The existing Hailo media/inference stages, detector artifact, TCP feed, JPEG encoder, and
basic viewer transport are reused. The old ByteTrack, SDK tracker, and LockCore are not used
by the fresh executable.

## Run and build

From the repository/worktree root:

```bash
bash hosts/hailo15l/build_fresh_tracking.sh
bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-phone
```

Viewer: **http://10.0.0.1:8099/**. Click a box, or choose **target: person** / **target: phone**.
Class selection acquires only when exactly one confirmed object of that class is visible. **Clear target** unlocks.
With the default profile, after a target expires, select again; another person is never automatically substituted.
The optional learned-person mode described below retains identity separately from the detector ID.

```bash
# YOLOv8m phone candidate (stop before switching profiles):
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
bash hosts/hailo15l/fresh_tracking_ctl.sh start-phone
# start = YOLO11s stretch; start-letterbox = YOLO11s letterbox comparison
bash hosts/hailo15l/fresh_tracking_ctl.sh status
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
bash hosts/hailo15l/fresh_tracking_ctl.sh restore
```

`restore` stops the fresh process and starts the previous perception service.
The running bench version uses an isolated installation at `/opt/garuda-fresh`.
Boot startup still belongs to the existing service; these scripts do not modify boot configuration.
Only one pipeline may own the camera at a time.

Build output defaults to `/tmp/garuda-fresh/{native,h15l}`.
Overrides: `GARUDA_FRESH_BUILD`, `GARUDA_H15L_SDK`,
`GARUDA_H15L_HOST`. Staging expects the existing cached YOLO11s and YOLOv8m Hailo-15L HEFs,
and verifies its SHA-256. See the staging script for the cache path.

## Tracking and target behavior

- Class-aware, globally optimal assignment with separate high-confidence association and
  low-confidence recovery. Low-confidence detections cannot create new tracks.
- Four constant-velocity Kalman filters track box center and size in normalized full-FOV
  coordinates. Lifecycle timers use capture time and local monotonic time, not frame counts.
- A central-ROI NV12 color/luminance histogram provides appearance evidence. Appearance is
  updated only on high-confidence, unambiguous matches.
- Background block matching estimates inter-frame image translation. Low texture, competing
  matches, insufficient spatial coverage, or inconsistent motion produce no compensation.
- Similar competing associations cause an ambiguity hold. Class changes cannot transfer an ID.
- Track confirmation needs both elapsed time and repeated observations. Memory, detections,
  assignment size, click history, and recording queues are bounded.
- A selected target holds one track identity. Short gaps can recover that ID; expiry requires
  an explicit new selection. Epoch changes identify new selections.
- Clicks reference the displayed snapshot sequence and its historical boxes. Selection also
  requires that the same track is still freshly observed (200 ms). Displayed selection intent may be
  up to 1000 ms old. A clearly smaller, different-class box fully inside larger boxes can be
  selected (phone inside person); overlapping same-class objects remain ambiguous.
- Missing/invalid timestamps, stale/reordered frames, weak observations, ambiguity, and excessive
  position uncertainty suppress target validity. Heartbeats and the local shim expire validity
  even when inference stops or the C++ process freezes.

Configuration is in [the Hailo profile](../../hosts/hailo15l/fresh/perception.json).
The initial freshness budget is 200 ms and coast expiry is 1200 ms. These are configured policy
limits, not claims that the system is suitable for a particular aircraft or flight speed.

## Interface

`GET /api/state` and `GET /api/events` return a v2 display-compatible envelope
tagged `tracker_contract: garuda.fresh.v1`. State names differ from the old lock engine:
`none`, `acquiring`, `tracking`, `ambiguous`, `coasting`, `lost`.

`lock.control_valid` is the observation gate. `image_target` exposes its own
`valid` plus normalized center `u,v` and box width/height fractions.
This is image-space perception, not a flight command or metric range. Depth reports unavailable.
A downstream controller must also enforce its own link/transport deadline and aircraft constraints.

Commands:

```text
POST /api/mono_target?class=person
POST /api/select?id=1&sequence=123
POST /api/mono_click?x=640&y=360&sequence=123
POST /api/unlock
```

Pixels refer to `frame.width/height`; core boxes and motion are normalized.
Capture/publish timestamps are board-local `CLOCK_MONOTONIC`.
The shim must run on the same board; these timestamps cannot be compared directly to a PC clock.
The shim reduces `valid_for_ms` with elapsed time. Remote consumers must additionally account
for transport uncertainty; a cached boolean is not a continuing authorization to move.

The original person profile uses 640×640 stretch. The comparison and phone profiles use
centered letterboxing (640×360 content with 140 px top/bottom padding). Explicit inverse geometry
maps detector boxes and image-feature sampling into the same full-FOV coordinates.
Preview JPEG and detection snapshots are independent streams; click history aligns the boxes,
but the displayed JPEG is not frame-synchronized to those boxes.

## Reproduce and test

The build script runs the fresh C++ suite, Python HTTP/replay tests, and ARM cross-build.
No NumPy, OpenCV, or Python Hailo bindings are needed.

```bash
cmake -S services/garuda-tracking -B /tmp/fresh-native
cmake --build /tmp/fresh-native -j2
ctest --test-dir /tmp/fresh-native --output-on-failure
GARUDA_REPLAY_BIN=/tmp/fresh-native/garuda-track-replay \
  python3 -m unittest discover -s services/garuda-tracking/tests -p 'test_*.py' -v

gzip -dc services/garuda-tracking/tests/fixtures/h15l-person-20260910.jsonl.gz |
  /tmp/fresh-native/garuda-track-replay - \
    services/garuda-tracking/tests/fixtures/h15l-person-20260910.config.json
```

The fixture contains real detector boxes and image histograms, not video or face embeddings.
Its final successful target command has no following frame; the final frame correctly remains
lost until that command is applied to the next observation.

To record another run, copy the node config and set `record_path` to a file under
`/tmp`, then start the node with that config. `record_limit` bounds the number of
frame/command rows. Overflow stops recording at a prefix and sets `diag.record_failed`;
limit completion sets `diag.record_limit_reached`. Check both fields before using a capture.
The file is opened afresh at node startup. Save its exact tracking config with the recording.

```bash
python3 bench/fresh_tracking_bench.py --seconds 60 --output /tmp/fresh-live.jsonl
```

## Measured validation — 2026-09-10

See [bench results](../../bench/results/2026-09-10-fresh-tracking/) and the corresponding
entries in [benchlog](../../bench/benchlog.md) and [versions](../../bench/versions.md).

| Check | Result |
|---|---|
| Native C++ scenarios | 21 passed |
| Diagnostic memory/storage budget | Native test passed; oversized capture rejected and 2-frame capture completed on board |
| Python transport/replay tests | 8 passed, including the real board recording |
| Address/undefined-behavior sanitizers | Passed |
| Existing perception CTest suite | 14 passed |
| Hailo-15L native pipeline | Cross-built and run on the board |
| Live measurement | 60.02 s; 1496 HTTP samples; 20.00 processed frames/s |
| Capture-to-HTTP frame age | Median 84.84 ms; p95 124.21 ms; max 147.47 ms |
| Normal-run frame rejections / HTTP errors / validity violations | 0 / 0 / 0 |
| Selected-target samples | 765 tracking; the first 731 samples had no selection |
| Real process pause | Valid before; invalid at the 350 ms check; old target lost after resume |
| Native/ARM replay | 2202 rows; zero semantic mismatches |
| CPU/RSS spot sample | 60.9% of one CPU; 83,872 KiB RSS (`ps` lifetime sample) |
| Die temperature spot sample | 58.511 °C |

The first live build exposed an SDK scheduling mismatch: job_limit=1 with scheduler_threshold=4
and its 100 ms timeout. The source pool filled and the tracker rejected delayed frames.
Explicit threshold=1 and timeout=10 ms fixed that observed backlog. The board exports these
builder methods. The freshness gate was retained throughout.

These are short bench measurements with one person, not a controlled tracking-accuracy benchmark
or a flight test. The owner reported “it tracked well.” The 60 s capture establishes actual
throughput/age/continuity in that scene; it does not establish identity accuracy in crowds.

## Phone detector investigation — 2026-09-10

The owner rejected a proposed image-based bridge as a workaround. That undeployed experiment
was removed. No template tracker, extra prediction validity, or relaxed tracking threshold
is present in the live candidate.

Three Hailo-15L HEFs were run on **the same 59 images**, bypassing the tracker entirely.
At confidence ≥0.15, centered-letterbox phone detection counts were YOLO11s **1/59**,
YOLO11m **12/59**, YOLOv8m **50/59**. At confidence ≥0.5 they were **0/59**, **1/59**,
and **8/59**. All three detected the person at ≥0.5 in all 59 images.
These are detector-presence counts, not annotated recall or general accuracy.
The JPEG-derived inputs also differ from raw ISP buffers. See the full
[comparison and hashes](../../bench/results/2026-09-10-fresh-tracking/model-comparison.json).

The YOLOv8m phone trial keeps birth=0.5, control=0.4, recovery=0.15 and the same target policy.
After the preprocessing correction below, its 30 s live check measured 19.98 processed fps,
frame age median 101.09 ms / p95 142.06 ms / max 159.71 ms, zero rejected frames and HTTP errors. No target was selected during that timing
measurement; this does not establish phone lock continuity. The model comparison favors
YOLOv8m for these poses but still shows substantial low-confidence recognition.

A first float-reference check and a confirmed preprocessing bug are described below. Next model
work needs annotated poses and negative scenes before selecting model replacement, representative
quantization calibration, or phone-specific fine-tuning. A larger model alone was not sufficient.

Reproduce the detector comparison (PC prepare requires Pillow/numpy; deployed tracker does not):

```bash
python3 bench/fresh_model_bench.py capture /tmp/phone-test --seconds 60
python3 bench/fresh_model_bench.py prepare /tmp/phone-test --stride 4
# Cross-build creates /tmp/garuda-fresh/h15l/garuda-model-probe.
# Copy the probe and packed *.nv12 inputs to the board, then pause the live pipeline.
# On board, for each pinned NV12/NMS-by-class HEF and input geometry:
/tmp/garuda-model-probe /path/to/model.hef /tmp/letterbox.nv12 0.05 > /tmp/result.jsonl
# PC: inspect results and overlays; presence alone is not correctness.
python3 bench/fresh_model_bench.py summarize /path/to/result.jsonl
```

The probe checks input shape, 80-class NMS layout, finite outputs, file boundaries and Hailo status.
All six model/geometry output files are retained compressed in bench/results; original test
images remain local and their hashes are retained in model-input-manifest.json.

## Actual input/ISP diagnosis and correction

The owner reported that phone lock failed beyond the person's box and questioned the camera/ISP.
Raw NV12 capture revealed a bug in the trial: the pixels were **stretched**, while the tracker
applied an inverse **letterbox** transform and sampled appearance from a letterbox content view.
The SDK retains stream dimensions/scaling when switching profiles. Startup had initialized the
default stretch profile before requesting the letterbox profile, so the resize mode stayed stretched.

Startup now initializes directly with the requested default profile, verifies the effective
stream configuration, and checks actual padding pixels before accepting each frame.
All20 post-fix captures showed exactly140 black Y rows above/below640×360 content and neutral UV.
Earlier live letterbox/YOLOv8m reports are annotated as invalid geometry trials; their timing
data remain measured, and the separately prepared offline Python-letterbox comparison remains valid.

[Diagnosis and evidence](../../bench/results/2026-09-10-fresh-tracking/camera-input-diagnosis.json).
The unit suite includes the stretched-pixels/letterbox-config regression.
The corrected30s run measured19.98fps, p95frame age142.06ms, zero rejections/errors.
No target was selected during this timing run. The owner subsequently reported “It keeps the lock now” for the outside-body test; see the confirmation below.

The actual ISP metadata showed32991–33006µs exposure (about1/30s).
This can blur movement but is not proof that it caused the static recognition failures.
Exposure, noise reduction and factory camera profiles have not been changed.
There is no person-containment gate in detection/association.

On20 of the exact pre-fix captured inputs, phone presence at≥.15 was10/20 on live Hailo and
11/20 with official YOLOv8m ONNX on CPU; correcting aspect ratio on the PC gave16/20.
At≥.5 those counts were4/20,7/20,10/20. This does not establish a quantization defect:
colour conversion, padding, and checkpoint provenance need controlled matching, and the samples
lack human bounding-box annotations. The reference harness is `bench/fresh_reference_bench.py`.
Raw camera imagery remains local; hashes, metadata and prediction outputs are retained.

For input diagnostics, send a command to board TCP8982:
`{"cmd":"capture_input","frames":60,"every":10}`. The response names a unique directory under
`/tmp/garuda-fresh-input-*` with packed NV12, associated detection/output metadata, and the most
recent preview JPEG. Preview JPEG is explicitly **not frame-synchronized**.
`diag.input_capture` reports remaining/written/error. Capture is off until commanded; maximum120
frames, queue4; file IO is outside the tracking mutex. Additional byte and memory budgets below can reject a request before this count limit. It is a bench feature, not a throughput test.

## Motion-filter regression and board profile

A synthetic phone trajectory retained identity through the person's boundary but lost it after
an abrupt reversal. The center filter's acceleration standard deviation was 0.4 normalized
frame units/s²; its covariance became too small to accept the returning detection. Center
acceleration is now configurable as `position_acceleration_std`, default 1.0; size process
noise, confidence, freshness, appearance and geometric gates are unchanged. Reversal and
nearby-phone identity tests pass, including withholding validity when a different-looking phone
replaces the target. The core suite now has 21 scenarios; Python tests and ASAN/UBSAN pass.

A sweep of 0.4, 1, 2, 3, 4 and 6 used the same 6000 corrected camera frames with a synthetic
one-shot phone selection command. Values ≥1 retained the synthetic trajectory; 1 preserved
seven confirmed phone IDs and 711 valid target frames in the recording. All values lost the
selected ID at frame 1676. This fixes a reproduced motion-model limitation but does **not**
establish improved phone recognition or solve the owner's live failure. Values ≥3 increased
confirmed phone IDs in that recording and were not selected. Counts are not identity accuracy.
Board profiles explicitly retain the previously tested 0.4 value; the new 1.0 library default remains an opt-in bench change for those profiles. The current binary includes diagnostic guards and the geometry correction.
See [motion comparison](../../bench/results/2026-09-10-fresh-tracking/motion-filter-comparison.json).

## Owner confirmation and diagnostic recovery

The owner answered **“It keeps the lock now”** after the corrected outside-body phone test.
We saved 145 preview JPEGs spanning about 38 seconds. A later instrumented capture had no selected
identity (913 none,9 acquiring samples), so it does not independently measure the owner's reported
lock continuity. The assistant selected phone near the end of that capture. See
[owner report and model comparison](../../bench/results/2026-09-10-fresh-tracking/owner-phone-confirmation.json).

On the same37 sampled movement images, phone presence at≥0.5 was YOLO11s9, YOLO11m12 and YOLOv8m13;
at≥0.15 it was16,23,23. YOLOv8m float reference gave21 and28 respectively. These are unannotated
presence counts, not recall, identity accuracy or proof of quantization loss. Difficult poses remain.

The diagnostic run encountered a board storage-read stall: serial traces showed MMC waits and
file-page faults across the ISP service, tracker, SSH and login. RAM-backed files occupied about
444MiB, while free memory outside CMA was about32MiB. Memory/page-cache pressure is a plausible
contributor, but the storage/controller root cause is unproven. Sync and read-only remount completed;
a reboot restored access. PC JPEGs were preserved; the unfinished board-only raw capture was lost.
See [recovery evidence](../../bench/results/2026-09-10-fresh-tracking/storage-stall-recovery.json).

Recording is now **off by default**. When explicitly enabled, JSONL recording stops at32MiB;
raw diagnostic files have a cumulative128MiB allowance per node run. Preflight estimates and
per-write checks retain128MiB of filesystem space and estimated general-purpose available memory
(`MemAvailable - CmaFree`). Missing counters reject diagnostics. These guards protect the bench
from diagnostic accumulation; they do not establish a fix for an unidentified storage defect.
Archive captures on the PC before starting another diagnostic session; the cumulative byte
allowance resets on node restart. A50-frame capture with every20 spans about50seconds at20fps,
subject to the admission budget.

The guarded build ran on the board:120-frame request rejected,2-frame request completed;
post-recovery30s check measured19.99fps, p95age142.52ms, zero HTTP errors/rejected frames/validity
violations. All745 samples were acquiring with no visible eligible target; this is a recovery and
timing check, not a new lock-continuity result. Native21 scenarios plus diagnostic-budget test,
Python8, ASAN/UBSAN and SDK build passed. Factory exposure/denoise and boot startup are unchanged.

## Remaining limits

- Color histograms are weak appearance cues, not learned re-identification. Similar clothing,
  lighting changes, partial-body detections, and overlapping people remain difficult.
- Camera compensation estimates translation only. Rotation, large parallax, scale change, or
  motion outside its search window can cause a hold. It is not IMU/VIO compensation.
- Person behavior and the corrected outside-body phone behavior were owner-tested. Phone confidence
  remains pose-dependent; annotated MOT metrics, two-person crowd identity validation, aerial views
  and long thermal/storage endurance remain TBD-bench.
- Metric distance, gimbal control, MAVLink/PX4 output, obstacle avoidance, and flight validation
  are not implemented in this service. No motor/arming path is present.
- The viewer inherits the isolated-bench HTTP transport and has no authentication. It is not
  a public network service.

## Sources and licensing

The new project code is BSD-3-Clause. The core uses the C++ standard library; JSON uses the
repository's existing MIT-licensed nlohmann header. Existing JPEG and Hailo SDK licensing remains
as documented in the perception service. The YOLO11s detector is **not-product-cleared** under
the existing bench/evaluation model policy. No model weights are committed here.

Design references, not copied tracker implementations:
[ByteTrack](https://arxiv.org/abs/2110.06864) for recovery from lower-score detections and
[BoT-SORT](https://arxiv.org/abs/2206.14651) for combining motion, appearance, and camera motion.
The actual deployed Hailo API was verified against the installed SDK headers and board symbols,
rather than assuming that current Python PCIe examples support the Hailo-15L SoC.

## Experimental learned person identity — 2026-09-10

The optional `learned_person_identity` mode gives the selected person its own immutable learned
appearance anchor and up to 8 recent descriptors, independent of the transient MOT ID. Identity
memory lasts 10 seconds after the last verified observation. A different-ID/long-gap return needs
at least 3 observations over 120ms, with a maximum 150ms inter-observation gap. Both the original
anchor and recent appearance must match; a similar runner-up or missing/incompatible descriptor
withholds control. These thresholds are **bench starting points, not calibrated identity accuracy**.
Phones and other classes still use the baseline policy. No appearance feature alone supplies range.

The Hailo host adapter runs the pinned OSNet HEF on the same local VDevice group as the detector.
It crops the current 640×360 full-FOV content, bilinearly resizes NV12 to128×256, dequantizes 512
outputs and L2-normalizes them. The preprocessing revision is part of every descriptor's model tag.
This CPU crop path is **not** the planned higher-resolution DSP target detector. The NPU adapter
and model remain host-side bench components; see [model card](../../models/osnet_h15l.md).

To stage the experimental mode (stop the fresh service first, as required by the staging script):

```bash
bash models/fetch_osnet_h15l.sh
bash hosts/hailo15l/build_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
GARUDA_FRESH_REID_HEF=/media/bhanu1234/Development/hailo15/models/osnet_x1_0_hailo15l_v5.3.0.hef \
  bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-person-reid
# Open :8099 and select target: person. Startup never selects an identity itself.
# Return to the baseline tracking policy:
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
bash hosts/hailo15l/fresh_tracking_ctl.sh start-phone
```

The 40-second one-person run measured19.98 processed frames/s,127.25ms median /161.96ms p95 /
190.69ms maximum HTTP-observed image age, with 0 rejected frames and0 validity-invariant violations.
805 embeddings completed with 0 failures or skipped requests. An earlier 60-second run intentionally
paused the node for2 seconds: the selected identity survived while control expired, then returned
under MOT id 2 with the original epoch 1. That demonstrates software-gap recovery in one scene;
it does not establish correct identity after physical occlusion or among lookalike people.

The first combined attempt failed because the adapter used a HailoRT service device and the SDK
used a local device. Both now use the same local group. The first successful60-second run also
had stale viewer updates before the intentional pause. We removed unused frame JSON serialization,
shared immutable track descriptors instead of copying them into display history, and instrumented
publication timing. The subsequent40-second result is encouraging, not a controlled attribution of
which change reduced latency. The working baseline binary/profile was restored after these tests.

Evidence: [learned-person report](../../bench/results/2026-09-10-fresh-tracking/learned-person-identity.json).
Native/ARM tests cover wrong identity, ambiguous candidates, immutable-anchor drift, elapsed
reacquisition, descriptor provenance, stale time, expiry, new MOT ID, and NV12 stride/chroma/crop
geometry.21 existing tracking scenarios, 7 identity/crop scenarios, diagnostic-budget checks and 8
Python transport/replay tests pass; the C++ checks also pass ASan/UBSan and run on the board.

Subsequent work adds the [SDK follow contract and simulation](../garuda-follow/README.md),
[bounded exact-input capture](CAPTURE.md), and experimental
[camera rotation/scale compensation](CAMERA_MOTION.md). Their linked reports separate
synthetic and empty-scene checks from target-active accuracy. Annotated distractor and
physical-occlusion trials, learned phone appearance, measured ROI selection, combined
sustained load and a matched Pi comparison remain. [Full delivery remains open](DELIVERY.md).
