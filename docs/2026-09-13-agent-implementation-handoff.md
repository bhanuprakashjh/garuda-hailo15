# Hailo-15L tracking, ROS 2, PX4 and Gazebo: implementation handoff

> Later update (2026-09-13 18:45): the live native app is now
> `d150568ddeb27862…` (tracker input NMS at IoU 0.5 and non-blocking row ambiguity, commits
> `383b764`, `affd705` and the follow-up docs commit), profile unchanged. Root cause, exact-
> profile A/B and the resolution of the 024 five-tile 0.41 → 0.01 question are in
> `bench/results/2026-09-13-tracker-duplicates/README.md` and the benchlog entries of
> 2026-09-13 17:40 and 18:40. The §3 checksum table below predates this deployment; the
> previous binary is kept at `/opt/garuda-fresh/backups/tracker-fix-20260913/`.

Prepared 2026-09-13, approximately 17:02–17:10 Asia/Kolkata. Implementation
checkpoint: `a0277e2`, branch `feat/hailo15l-fresh-tracking`. This document is
the entry point for the next agent. It consolidates the previous reports and
the latest camera/zoom UI fixes. Read this, then `CLAUDE.md` and the relevant
dated entries in `docs/decisions.md`. Earlier reports describe historical
states; their claims of no ROS, no Gazebo, an older binary, or a disarmed demo
must not be treated as current state.

## 1. User objective and current outcome

The user wants a convincing, technically defensible follow-me demonstration
for people and vehicles: real camera or aerial footage → actual Hailo inference
and target identity → ROS 2 and MAVROS **on the Hailo-15L** → PX4 software in the
loop → the actual Gazebo application, with a GUI showing pixels, selected
identity, messages/commands, and the simulated drone's response. The mobile
phone was a proxy for a small distant target, not the final application.

The requested experience also includes target zoom, loss/re-entry, a possible
monocular relative-distance cue, and dataset-based validation. The user prefers
implementation and verification over repeated permission questions, wants
controls beside the video, and has asked us to work from recordings/datasets
where possible rather than repeatedly requiring a person in front of the camera.

Implemented: actual native camera tracking; stable selected identity; board-local
ROS camera ingress; board ROS/MAVROS command publication; guarded PX4/Gazebo
simulation; three input modes; local console; display crop zoom; relative-size
diagnostic; recorded and rendered regression harnesses; retained evidence.

Not completed: robust aerial/crowd tracking, native-4K ROI inference, validated
AI-ISP motion improvements, aerial model fine-tuning, standalone onboard control
without the PC, real-flight-controller integration/qualification, physical
metric ranging, collision avoidance, or real-flight validation. Dataset results
remain weak. A working command route does not establish tracking robustness.

**Addendum 2026-09-14 (overnight, after this document):** the aerial model
fine-tuning above is now done and measured — VisDrone + COCO fine-tuned YOLO11s
("mixed e11") deployed as a separate, hash-pinned **aerial profile**
(`perception-aerial.json`, `fresh_tracking_ctl.sh start-aerial`), node
`4666ffe8…` with the ROI-merge cap fix, desk profile unchanged. Eleven-clip
result moved from 3/11 → 6/11 clips acquired (single view) and 4/11 → 6/11
(adaptive); 13–17 px targets, click refusals on 053/317 and identity ambiguity
in walking groups (024) still fail. Read `docs/2026-09-13-session-summary-and-aerial-gap.md`
§6, `docs/decisions.md` 2026-09-14 and `bench/results/2026-09-13-aerial-detector/README.md`
before touching the detector or profiles; §11–12 below predate this.
**2026-09-15:** the native-pixel target crop (third 3840×2160 frontend stream, ROI + OSNet
crops from sensor pixels) is built and gated (`perception-follow-native{,-compare}.json`,
`target_roi_native_context`, `native_max_window_px`) but **not shipped on the desk**: measured
equal to today's crop at the same scale and better only for targets under ~40 px (six frames),
see `bench/results/2026-09-15-native-crop/README.md` and decisions 2026-09-15. Node `124cc94f…`
is on the board running the unchanged desk profile. **The demo console** now takes
`run_grand_demo.sh replay|gazebo … --aerial` (aerial HEF, wide caps, 1500/2000 schedule on the
merge-fixed stream binary, staged by `stage_sim_stream.sh`) and names the model and schedule it
runs; in replay mode no profile passes the 200 ms receiver gate because of PC transport
(`bench/results/2026-09-15-demo-aerial/README.md`), so §11's launch recipe still yields a
heading-response demo, not motion, until board-side ingress exists.

## 2. Workspace and verified live state

Work only in:

```text
/media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking
```

The main checkout is `/media/bhanu1234/Development/GARUDASDK`, branch `master`
at `2322c1b`; this implementation has not been merged there. Other worktrees
contain earlier Pi, perception and tracker work. Do not switch to them accidentally.
The implementation worktree was clean at `a0277e2` before this documentation edit.

Read-only checks during this handoff verified:

- Console: `http://127.0.0.1:8100/`; status: `/api/state`.
- Board: passwordless `ssh root@10.0.0.1`, via PC Ethernet profile `h15-link`.
- Native desk UI: `http://10.0.0.1:8099/`.
- Actual camera source: `hailo15l.imx678`, 1280×720 tracking coordinates.
- The live console was running with `--live-camera --transport mavros-15l --gui`.
- **The simulator was in `Hover / offboard`, Follow enabled**, with a selected
  person. An observed stable selected identity was 3, associated MOT track 9.
  This is a transient snapshot, not a state guarantee for the next session.
- Gazebo server, Gazebo desktop client and owned PX4 SITL processes were running.
- `real_hardware_commands=false`; no physical flight controller is connected.
- Live events repeatedly alternate fresh FOLLOW and expiry-related HOLD. The
  GUI fixes do not eliminate these upstream freshness gaps.
- Physical JPEG/overlay pairing remains approximate (`overlay_matched=false`).
- Apparent-size reference was invalid in the sampled scene because the box
  approached/clipped the image edge. Physical metric range was unavailable.

Observed process IDs, useful only as historical diagnostics: runner 549984,
Gazebo server 550029, PX4 550030, Gazebo GUI 550031. Re-resolve ownership before
acting on any PID. No process was stopped or control action sent for this handoff.

Current run evidence directory:

```text
/media/bhanu1234/Development/hailo-export/dataset-rerun-20260913/live-console
```

HTML and JavaScript are read from disk for each HTTP request, so refresh loads
UI changes without a simulator restart. The already-running process's startup
`versions.json` predates subsequent UI edits; use git/file hashes to identify
the currently served frontend. Do not imply that an old run snapshot captures
the latest UI source.

## 3. Hardware, models and installed versions

This is a **Hailo-15L SBC**, IMX678 camera, not a Hailo-15H and not the Pi/Hailo-10H.
The board uses stock VPSP 1.12.0 / HailoRT 5.3.0. Current work did not upgrade it
to 5.4. The older Pi experiment is a separate device/software stack.

ROS 2 Jazzy and MAVROS are installed in a separate Ubuntu Noble ARM64 userspace
at `/opt/garuda-ros-jazzy`; native Yocto/Hailo libraries remain outside it. This
is a bench chroot, not Docker, not a security boundary, and not a completed
Yocto/meta-ros product port. See [ROS deployment record](2026-09-13-ros2-mavros-campaign.md)
and [dependency record](dependencies/ros2-mavros-bench.md). Rootfs installation
is already done; do not reinstall it as a routine resume action.

Board checksums independently re-read over SSH during this handoff:

| Installed file | SHA256 |
| --- | --- |
| `/opt/garuda-fresh/garuda-fresh-tracking` | `3851ef019716dfa7f5ed36f219ea557cfb81cbd0820dd9e021f1431c5514a2d3` |
| `/opt/garuda-fresh/current.json` | `ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d` |
| `/opt/garuda-sim/garuda-causal-stream-diagnostics` | `ae28949f61da8498d35738a2ef3002f1b71d122709a76de84f641808f91bba9d` |
| `/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef` | `aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58` |
| `/opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef` | `49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7` |
| `/opt/garuda-fresh/models/yolov8m_hailo15l_v5.3.0.hef` (installed alternative) | `fe7a956375a1667e3d2fac58f546814453018ae4d9ad5fe33560f11d2117c947` |

The active detector is the **controlled YOLO11s HEF**, not YOLO8. An earlier
staging bug deployed an old HEF under a misleading claim; hash verification is
therefore essential. Model filenames alone are insufficient evidence.

PC SDK: `/media/bhanu1234/Development/hailo15/sdk`.
PX4 checkout: `/media/bhanu1234/Development/PX4-Autopilot`.
Exact historic build/software versions are retained per run in evidence archives.

## 4. System architecture and input modes

### Live physical camera

```text
IMX678 → ISP / paired NV12 → native YOLO11s + tracker + OSNet identity
                                      │
                  board TCP snapshot feed (8981)
                       ├─ board-local ROS /garuda/camera/native_snapshot
                       │       → board PerceptionAuthority + operator permit
                       │       → MAVROS /mavros/setpoint_raw/local
                       │       → owned SSH tunnel / PC packet gate → PX4 SITL
                       │                                                   │
                       └─ PC supervisory state + JPEG preview         Gazebo vehicle
                                      │                                    │
                                      └──────── local console ──────────────┘
```

The perception input reaches ROS locally on the board without being echoed
through the PC. The PC is still required for operator permits, supervisory
checks, the final packet gate, display and simulation. This is not independent
onboard autonomy. The board snapshot feed and command port are 8981 and 8982.

| Mode | Input | Meaning of vehicle motion | Translation |
| --- | --- | --- | --- |
| `live` | Physical IMX678, existing native desk detector | Bounded heading response; the fixed camera cannot recenter itself | Zero commanded XY |
| `replay` | Prepared aerial NV12 footage, real 15L inference | Bounded heading response; recorded frames cannot react to the drone | Zero commanded XY |
| `gazebo` | Drone-mounted rendered camera, real 15L inference | Closed visual feedback loop: motion changes subsequent pixels | Uses exactly paired simulated depth |

The GUI's Gazebo overview is actual simulated world imagery. The large image
is the selected input mode, not necessarily the drone-mounted camera.
Real-camera and replay heading is relative to a latched reference, bounded
to ±30°, with yaw-rate limit 0.8 rad/s. These are configured limits, not measured
performance. A centered recording need not produce a 30° excursion.

## 5. Native detection, tracking and selected identity

Primary source files:

| Component | Location |
| --- | --- |
| Native capture/inference/publisher orchestration | `hosts/hailo15l/fresh_node.cpp` |
| DSP region crop, letterbox and YOLO output decoding | `hosts/hailo15l/region_detector.{cpp,hpp}` |
| Embedding support | `hosts/hailo15l/person_embedding.hpp`, `image_embedding.{cpp,hpp}` |
| Tracker and measured/filtered geometry | `services/garuda-tracking/src/tracker.cpp` |
| Stable person identity | `services/garuda-tracking/src/target_owner.cpp` |
| Search/ROI geometry and tiles | `services/garuda-tracking/src/search_region.cpp`, `tiling.cpp` |
| Source frame pairing | `services/garuda-tracking/src/source_pairing.cpp` |
| Native desk HTTP shim and tuning | `services/garuda-tracking/fresh_shim.py`, `fresh_tuning.py`, `fresh_tuning.html` |
| Actual recorded-pixel pipeline | `hosts/hailo15l/causal_replay.cpp` |
| Versioned follow configuration | `hosts/hailo15l/fresh/perception-follow.json` |

The full view is 1280×720 NV12, letterboxed to 640×640 for YOLO. Search uses
full view plus four overlapping corner regions; locked tracking uses full view
with optional target ROI assist, with periodic global evidence for small targets.
Large targets can stay on single-pass inference. Tiles are acquisition/detail
assistance, not independent trackers. A handover can perform five global passes
plus a local ROI; diagnostics report the actual pass count.

Implemented correctness fixes include letterbox-padding removal in cut-edge
checks, provenance-aware fragment aggregation, consistent coordinate mapping,
full-body preference over contained crop fragments, and small-object-only corner
contributions. Separate detections from the same region are retained.

Exact paired source images feed histogram and OSNet crops. The managed node can
wait at most 40 ms for the matching exposure; its cache holds at most four
1280×720 frames. It does not substitute a nearby exposure. Corner batches copy
the source once. NPU work no longer holds the publisher/selection mutex; a
selection-generation change discards in-flight results from the previous choice.

Matched observed tracks now publish the **current detector box**, while the
Kalman state remains available for association/prediction. `filtered_box` exposes
that filtered geometry and `box_source=detector_measurement` identifies observed
geometry. Previously the filtered size/position could overshoot while still
being labelled observed. Predicted/coasting boxes do not grant fresh control.

Person identity uses OSNet; `lock.id` is the persistent selected identity,
`lock.track_id` is the temporary MOT association and can change after occlusion.
Re-entry is gated by positive evidence and ambiguity checks. Color histograms
proved unreliable as person identity in aerial scenes; they remain relevant
to association/non-person behavior. Descriptor-aware ordinary association was
tested and regressed, so its optional gate remains off. Do not silently enable it.

Active profile values, verified against board `current.json`:

| Setting | Value |
| --- | --- |
| Coordinate frame / network tensor | 1280×720 / 640×640 letterbox |
| Tracked classes | person, car, bicycle, motorcycle, dog, cell phone |
| Tracker freshness / coast / confirm | 500 / 1200 / 120 ms |
| Maximum observation gap | 500 ms |
| Birth / control / low confidence | 0.5 / 0.4 / 0.15 |
| Track / detection caps | 64 / 128 |
| Learned person identity | enabled |
| Identity memory | 30,000 ms |
| Identity continuation / reacquisition gaps | 500 / 500 ms |
| Identity ambiguity margin | 0.04 |
| Target ROI mode / age / global window | assist / 400 ms / 1600 ms |
| Managed detection / detection tiles / tiles when unlocked | all enabled |
| ROI cut margin / tile cut margin / corner max area | 0.015 / 0.08 / 0.05 |
| Person embedding cap / age | 6 per frame / 500 ms |
| JPEG preview | configured 10 FPS, quality 75 |

Configured FPS is not measured throughput. The class filter explains why the
console does not display every possible COCO category. The current parser has
an 80-class COCO assumption; a VisDrone ten-class HEF needs decoder/class-map work.

## 6. ROS, command authority and deadlines

Important files:

- `hosts/hailo15l/ros2/native_camera.py`: local packet parsing, source/clock and
  identity validation, preserved capture deadlines.
- `hosts/hailo15l/ros2/native_camera_observe.py`: read-only ingress observer.
- `hosts/hailo15l/ros2/mavros_node.py`: board ROS request/authority/publication.
- `hosts/hailo15l/ros2/run_board.sh`, `mavros.yaml`: runtime configuration.
- `services/garuda-follow/perception_authority.py`, `fresh_follow.py`,
  `fresh_target_adapter.py`, `follow_authority.py`, `follow_controller.py`:
  observation parsing, identity/session authority and command intents.
- `bench/sim/remote_mavros.py`, `mavros_contract.py`: owned transport,
  publication bindings, expiry and final packet checks.
- `services/garuda-bridge/sim_offboard_bridge.py`: simulation bridge/ownership
  boundaries and explicit cleanup behavior.

ROS domain 73, CycloneDDS, loopback discovery. Request envelope topic:
`/garuda/bench_request`; native source topic: `/garuda/camera/native_snapshot`;
setpoint topic: `/mavros/setpoint_raw/local`; services:
`/mavros/cmd/arming`, `/mavros/set_mode`. The bench envelope is JSON, not a
finished typed product interface. MAVROS connects to board loopback
`tcp://127.0.0.1:5760` through the owned SSH tunnel/PC relay. There is no exposed
real serial or arbitrary LAN FC endpoint in these demo launchers.

The observation binding includes source ID, stream/producer, selection epoch
and stable lock identity. Board clock domain contains the current Linux boot
ID. Original capture age and transport bounds are charged; receiving or
repeating a snapshot does not make it new evidence. Clock conversion uses
bounded assumptions, not a claim of PTP/exposure synchronization.

Keep these budgets distinct:

| Budget | Meaning |
| --- | --- |
| 500 ms | Native tracker/viewer freshness and browser selection window |
| 200 ms | Maximum observation age for the follow consumer |
| ≤150 ms | Command intent TTL, additionally bounded by original observation expiry |
| 750 ms | Browser status-connection presentation timeout |

Board request acceptance now triggers immediate evaluation/publication and
resets the normal 50 ms watchdog timer. It does not renew the request lease.
TCP_NODELAY and reduced repeated PX4-log reads remove avoidable scheduling work.

Moving MAVLink packets must bind once to the actual ROS publication's timestamp
and original deadline. A newer request cannot renew an old packet. Because
packet and JSON evidence arrive on separate channels, the relay can wait up to
10 ms for missing publication metadata, with at most 16 pending packets. HOLD
or identity/source change clears them. Unknown, duplicate, contradictory and
expired packets remain rejected. A final expiry check immediately precedes the
PX4 write; evidence logging occurs afterward. This measures a software dispatch
boundary, not physical actuator latency. Requalify timestamp binding if MAVROS changes.

ROS uses ENU while the controller/wire representation includes NED conventions;
axis/sign evidence exists. Do not insert an extra swap/sign inversion.
Service acceptance is not flight-mode completion: telemetry confirms transitions.
Ordinary arm/mode/land use MAVROS. Direct emergency LAND is a separately logged
cleanup fallback and cannot count as successful MAVROS landing.

## 7. GUI implementation and latest regressions fixed

Files: `bench/sim/follow_console.html`, `follow_console.js`, `gazebo_console.py`;
state and action handling in `gazebo_follow.py`. The server is loopback-only,
enforces the expected Host and same-origin POST, caps action body size, and
enqueues actions rather than writing vehicle commands from HTTP handlers.

Endpoints: `/`, `/follow_console.js`, `/api/state`, `/api/action`,
`/frame.jpg?sequence=...`, `/overview.jpg`. An expired image returns 410.
Responses use `Cache-Control: no-store`. Use the exact `127.0.0.1` URL.

The layout has one dominant input image; Gazebo overview and controls sit on
the right. Select → Take off → Follow describes the workflow. Selection alone
does not enable motion. Identity retention, fresh PC request, and the last
forwarded/rejected packet are separate panels. Diagnostics expose ages, box
provenance, identity distances, ROS messages and command values. Events and
display inspection are expandable. There is no cloud hosting dependency.

Frontend behavior:

- Poll state every 150 ms; update age/presentation every 100 ms.
- Link terminal (side column, added 2026-09-13 19:35): `bench/sim/link_log.py` keeps a bounded
  log of transitions on the relay — PC requests to the board ROS 2 node (arm / offboard / land /
  setpoint hover↔move), the node's responses (ready, service results from `/mavros/cmd/arming`
  and `/mavros/set_mode`, rejections, holds, `/mavros/setpoint_raw/local` publications when the
  ENU values or reason change), the PC packet gate (every rejection with its reason, forwards
  on hover↔move transitions, `COMMAND_LONG` / `SET_MODE` relayed to PX4) and PX4's answers
  (`STATUSTEXT`, `COMMAND_ACK`, heartbeat mode/arming changes). `RemoteMavrosVehicle.status()`
  serves the last 80 entries as `mavros.link_log`; the console appends unseen ids
  (`newLinkEntries()`, unit-tested) and shows motion packets/s with the forwarded/rejected
  counters in the panel head. Steady 20 Hz traffic is deliberately not printed line by line.
- Heading dial (world panel, added 2026-09-13 19:25): a top-down drone glyph rotated to
  `heading_deg` (PX4 yaw, 0° = north, clockwise) with a dashed ghost arrow at
  `requested_heading_deg`; the pure helper `headingDial()` in `follow_console.js` is unit-tested
  in `test_follow_console.js`. It shows nothing rotated when disconnected. Added because in live
  mode the follow response is yaw only and a symmetric quad yawing ±30° is invisible in the
  fixed overview camera.
- Charge HTTP request elapsed time conservatively and age deadlines between polls.
- Bind image metadata, overlay and selection to the displayed source sequence.
- Physical JPEG and detection snapshot publication are independent; pairing is
  approximate even though the native inference source pairing is exact.
- Stable target buttons support selection; the canvas receives image clicks.
- Failed/old images cannot authorize a new selection merely because the latest
  state arrived. Hold/Land are not blocked by a pending selection acknowledgement.
- Main frame loads use two persistent image elements and `onload` opacity swaps.
  The previous visible frame stays in place while the next image loads. This
  implementation uses `onload`; it does not explicitly call `HTMLImageElement.decode()`.

Recent bug sequence, important to avoid repeating:

1. The original main image was replaced per JPEG, and the entire image dimmed
   whenever age crossed 200 ms. `eb77f9f` added two image buffers and removed
   visible dimming through CSS overrides.
2. That fix gave the images z-index 1 but left the canvas at the default layer.
   The detector was still producing person tracks, but images hid boxes and
   intercepted clicks. `a0277e2` establishes a local stacking context, images
   at 1 with `pointer-events:none`, overlay at 2, and frame notice at 3.
3. Zoom still blinked because `inspectTarget()` cleared its canvas on every
   render, including age ≥200 ms. `a0277e2` retains the last crop during a gap
   and labels it `Holding last crop · waiting for a fresh target frame.`
   It redraws only for a new displayed frame/crop/magnification and clears
   on target release/change, identity expiry or producer change.

Zoom cache variables are `zoomOwner` and `zoomFrame`. The current owner key is
source, stream and lock ID; it does not include selection epoch or image geometry.
Review that key if introducing same-ID epoch changes or variable source geometry.
The main loader has pending-request/generation guards and a one-second timeout;
timeout/source-switch races have not been comprehensively browser-tested.

Verification after these fixes used actual headless Chrome against the live
console: loaded image buffers, painted overlay pixels above the images, and
the canvas returned by hit testing. Zoom sampling observed fresh and held states
without blanking after its first crop. Blocking status requests in that isolated
browser retained the crop and displayed holding/disconnected messages. These
were ad hoc CDP checks, not committed browser test scripts. Existing Node
presentation assertions and syntax checks passed. Earlier reports saying
browser QA was unavailable predate this verification. No new user movement
trial or detector-accuracy claim follows from these UI checks.

## 8. Zoom, relative distance and ISP: precise scope

Implemented zoom is a target-centered **display crop** at 1×/2×/4×. It does not
change sensor pixels, NPU input, FOV calibration, or the tracking/control box.
It cannot recover information lost in downscaling.

`bench/sim/relative_framing.py` reports apparent relative distance:
reference height fraction / current height fraction. It checks fresh verified
tracking, valid geometry, roughly 1% image-edge clearance and aspect-ratio
change within 0.7–1.3 of the reference. The reference resets on source, stream,
epoch, identity or frame-size changes. It is not metres and does not authorize
translation. Partial bodies, crouching, occlusion and changing zoom can invalidate
the inference even if an image looks plausible.

The installed-camera audit found digital-zoom configuration and the matching
IMX678/H15L AI denoising model/profile. At that audit the active daylight profile
had denoising disabled, AE enabled and a 33.006 ms integration readback. Those
are historical audit values; read actual exposure/gain again before experiments.
The app streams were configured at 20 FPS and JPEG at 10 FPS. The latest UI
changes did not alter camera settings, models, board OS or ROS packages.

Current DSP ROI operates on **already reduced 1280×720 pixels**, not the full
3840×2160 sensor image. Native-resolution pairing, buffer sizing, coordinate
transforms and region detector support must change together to implement 4K ROI.
The requested 1280×736 was not the deployed geometry: the current implementation
is 1280×720 with 640×640 letterboxing. No sensor-binning mode was proven/activated.
Do not use an IMX715 setup script on IMX678 just because it mentions AI-ISP.

Audit code: `hosts/hailo15l/camera_audit.py`.
Full report: [camera/ISP and native ROS](2026-09-13-camera-isp-and-native-ros.md).
Its statement that native ROS was not yet joined to MAVROS is historical; the
later grand-demo integration completed that join.

## 9. Measured tests and what they establish

All figures below are copied from retained reports, not newly run during this
documentation task. Preserve failed cases and read each experiment's scope.

### Rendered-camera movement/dispatch regression

Evidence: `bench/results/2026-09-13-movement-fix/gazebo-final/`.
Actual rendered pixels → Hailo → board ROS/MAVROS → PX4/Gazebo:

- 588 unique inference frames; 334 forwarded / 4 rejected motion packets.
- No expired motion at the final dispatch check.
- 8.066426 m follow displacement in the simple rendered scene.
- All 31 evaluated perception-pause ticks held; recovered and ended disarmed.
- First-request-to-returned-publication-report median 6.233834 ms, p95
  17.616438 ms across 988 requests; this is not exposure-to-actuation latency.

The four rejected packets remained rejected. An earlier run uncovered the
cross-channel ordering race; a long historical interactive log also exposed
the late final-dispatch issue. These are unpaired scenes/workloads, so their
before/after latency or displacement is not a controlled accuracy comparison.

### Frozen eleven-clip aerial SOT rerun

Evidence: `bench/results/2026-09-13-dataset-rerun/sot/`.
Same prepared sources, model/profile, initial selection at source frame 15,
first 240 frames or clip end, declared 50 ms source period and 50 ms source age.
Measured processing cost determines skipped frames. These are replay timing
assumptions, not measured camera exposure or recovered source-video FPS.

| Metric | Baseline | Movement-fix rerun |
| --- | --- | --- |
| Acquired clips | 3/11 | 3/11 |
| Source frames | 2567 | 2567 |
| Processed frames | 723 | 724 |
| Fresh on-target outputs | 98 | 99 |
| Fresh off-target outputs | 2 | 1 |
| Eligible on-target duration | 3694.666 ms | 3703.431 ms |
| Eligible off-target duration | 31.955 ms | 32.113 ms |
| Evaluated timeline | 120100 ms | 120100 ms |

Eligible on-target means IoU ≥0.5, control-valid, and within 200 ms. About 3.08%
eligible on-target time is poor. Fewer off-target output rows did not reduce
off-target duration. Overlap is not independently certified person identity.
Both runs acquired only sequences 086, 115 and 245.

Critical clue: sequence 024 had raw target overlap on 59/60 processed frames
but never selected. At source 16, the published confirmed track began at
x643.11 while the fixed click was x617.62. Nearby raw boxes were not published
confirmed tracks. Investigate confirmation/association/selection separately
from detector absence. Do not alter the frozen click protocol and call it the
same comparison; a manual-selection variant is a separate test.

### Detector-only 64-image comparison

Evidence: `bench/results/2026-09-13-dataset-rerun/det-paired/`.

| Input/schedule | Person recall @.15 | Vehicle recall @.15 | FP/image @.15 | Person recall @.5 |
| --- | --- | --- | --- | --- |
| Reduced 720p, 5 passes | 28.39% | 59.88% | 12.891 | 11.18% |
| Original pixels, 9 passes | 31.41% | 61.17% | 16.219 | 12.01% |

Metrics reproduced the baseline exactly. Summed per-image inference waits were
129.497160 ms and 222.895820 ms; these exclude crop/transfer/tracking/exposure.
Original images were at most 1920×1080, not 4K. This is not equal-compute
evaluation, and the extra detail did not establish overall robust tracking.

### Recorded car through board ROS/MAVROS and PX4

Evidence: `bench/results/2026-09-13-dataset-rerun/replay-car/`.
Clip 115, one fixed click (661,396), fullview, requested 25 s scenario:
135 inference frames; 25 forwarded / 3 rejected motion packets; zero expired
motion at final dispatch. Actual heading span 0.918517°, requested 0.645235°;
376/420 follow ticks HOLD, 289 lost. Final disarm and zero translation commands.
This passes minimal protocol response checks, not a useful aerial follow demo.

### Other retained evidence and limitations

- Earlier headless SIH tests used the actual native tracker but synthetic
  detections/appearance. They test authority/fault behavior, not YOLO accuracy.
- Real board MAVROS axis tests established N/E/yaw signs, telemetry completion
  and loss behavior. One fault test combined ROS session and tunnel loss;
  it did not independently isolate the two.
- Earlier physical-camera demonstration recorded a 27.07° heading span, but
  this does not establish fast-motion, crowded-scene or outdoor robustness.
- Historical exact-pixel model parity used nine retained phone crops. These
  were oracle crops, not full-view or held-out aerial evaluation.
- The simulator RGB adapter was corrected from limited-range to the controlled
  model's full-range NV12 convention. This does not prove an ISP color-range bug.
- Existing VisDrone validation has influenced development and is not untouched
  final evaluation. Separate train/calibration/test data and sequence overlap
  checks remain necessary. SOT annotations are not exhaustive DET labels.

## 10. Evidence, data and reproducibility locations

Reports in read order:

1. This document.
2. [Movement geometry/dispatch](2026-09-13-movement-fixes.md).
3. [Frozen rerun and console](2026-09-13-dataset-rerun-and-console.md).
4. [Grand demo architecture and procedure](2026-09-13-grand-demo.md).
5. [Camera/ISP audit](2026-09-13-camera-isp-and-native-ros.md).
6. [Board ROS/MAVROS campaign](2026-09-13-ros2-mavros-campaign.md).
7. [Earlier audited follow fixes/SIL](2026-09-13-follow-fixes-and-sil.md).
8. [Original detailed history](2026-09-13-hailo15l-follow-handoff.md).

Git evidence: `bench/results/2026-09-13-{follow-fixes,ros2-mavros,camera-isp,grand-demo,movement-fix,dataset-rerun}/`.
Measurements and versions: `bench/benchlog.md`, `bench/versions.md`.
Large input pixels stay outside git:

```text
/media/bhanu1234/Development/hailo-export/datasets/visdrone/
/media/bhanu1234/Development/hailo-export/visdrone-sot-replay-20260912-roi/
/media/bhanu1234/Development/hailo-export/visdrone-sot-embeddings-20260912/
/media/bhanu1234/Development/hailo-export/dataset-rerun-20260913/
/media/bhanu1234/Development/hailo-export/movement-fix-20260913/build/
/media/bhanu1234/Development/hailo-export/grand-demo-20260913-interactive/
```

Use archived `run.json`, `trial.json`, `profile.json`, manifest/checksums,
raw output JSONL and verifier reports to reconstruct each exact experiment.
Core harnesses are `bench/hailo_reference/{follow_campaign,run_causal_replay,
prepare_visdrone_det,run_visdrone_det,dataset_campaign_report,score_causal_timeline}.py`.
Simulation evidence tooling includes `mavros_evidence.py`, `control_path_report.py`,
`grand_demo_report.py`, `verify_mavros_visual.py`, `verify_recorded_response.py`,
`verify_mavros_axis.py`, `verify_follow_sitl.py` under `bench/sim/`.

## 11. Resume, launch, verify and deploy

Start with read-only state inspection; the user may still be using the demo:

```sh
cd /media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking
git status --short
curl -fsS http://127.0.0.1:8100/api/state
bash hosts/hailo15l/fresh_tracking_ctl.sh status
ssh -oBatchMode=yes root@10.0.0.1 'sha256sum /opt/garuda-fresh/garuda-fresh-tracking /opt/garuda-fresh/current.json'
```

Do not launch a competing simulator. Hold/Land and stop the existing owned run
before mode changes or ROS deployment. Launcher refuses an existing PX4 and
an already-existing evidence output path. Choose a new directory for each run.
The following are examples for a future explicitly chosen run, not commands
executed while writing this handoff:

```sh
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh live /tmp/garuda-next-live-01
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh gazebo /tmp/garuda-next-gazebo-01
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh replay /tmp/garuda-next-replay-01 \
  /media/bhanu1234/Development/hailo-export/visdrone-sot-replay-20260912-roi/uav0000115_00606_s \
  --auto-demo --duration 25 --initial-point 661 396
```

Live mode leaves the native desk pipeline running. Gazebo/replay borrow the
NPU and restore the desk profile afterward, clearing old selection. Restoration
must be verified by advancing snapshots, not only a successful exit code.
Use `verify_recorded_response.py RUN_DIR` for recorded footage and
`verify_mavros_visual.py RUN_DIR` for rendered-camera feedback. They check
different claims. Automated mode may arm the owned simulator; read its flags.

Frozen eleven-clip SOT rerun command template, after releasing the NPU from any
owned simulator, using a new persistent output directory:

```sh
python3 bench/hailo_reference/follow_campaign.py \
  --prepared-root /media/bhanu1234/Development/hailo-export/visdrone-sot-replay-20260912-roi \
  --binary /media/bhanu1234/Development/hailo-export/movement-fix-20260913/build/h15l/garuda-causal-replay \
  --out /media/bhanu1234/Development/hailo-export/next-sot-regression-01 \
  --modes fullview --frames 240 --sequences \
  uav0000024_00000_s uav0000029_01102_s uav0000053_00264_s uav0000054_00000_s \
  uav0000086_00870_s uav0000092_00575_s uav0000092_01150_s uav0000115_00606_s \
  uav0000245_00001_s uav0000317_00000_s uav0000317_02945_s
```

For DET reruns, reuse exact prepared inputs/HEF from archived `run.json`; inspect
`run_visdrone_det.py --help` and retain its `--restart-profile start-follow`
restoration behavior. Do not regenerate a different sample and call it frozen.

Relevant local checks:

```sh
node --check bench/sim/follow_console.js
node bench/sim/test_follow_console.js
python3 -m unittest discover -s bench/sim -p 'test_*.py'
python3 -m unittest discover -s hosts/hailo15l/ros2 -p 'test_native_camera.py'
git diff --check
```

Last recorded broader movement-fix verification: 7 native CTest targets,
46 tracking Python tests, 24 follow tests, 7 bridge tests, 45 simulator tests,
8 native-camera tests and an exact-SDK ARM build. Counts describe that checkpoint,
not fresh runs performed for this documentation change. The latest UI changes
received Node checks and the live Chrome checks described above.

Build and stage only when native code changes are intended:

```sh
export GARUDA_FRESH_BUILD=/media/bhanu1234/Development/hailo-export/next-fresh-build-01
bash /media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking/hosts/hailo15l/build_fresh_tracking.sh
sha256sum "$GARUDA_FRESH_BUILD/h15l/garuda-fresh-tracking"
```

The build script performs native tests then sources the installed VPSP SDK and
cross-builds native app/probes/causal replay. Check exit codes and exact outputs.
`stage_fresh_tracking.sh` refuses a running desk node. It requires the intended
`GARUDA_FRESH_BUILD` and, for this identity profile, `GARUDA_FRESH_REID_HEF`
pointing to `/media/bhanu1234/Development/hailo15/models/osnet_x1_0_hailo15l_v5.3.0.hef`.
Stop the owned simulator first, preserve current config/backups, then stop/stage/
start the native app and verify actual running/installed hashes and advancing
frames. `start-current` preserves the selected profile; `start-follow` selects
the repository follow profile. Do not confuse them when tuning is present.

For ROS source changes, `bash hosts/hailo15l/ros2/deploy_nodes.sh` stages scripts
inside `/opt/garuda-ros-jazzy/opt/garuda` and refuses an active ROS runner.
It is separate from native executable/model deployment. Frontend-only changes
need no board deployment or camera restart.

Rollback artifacts are recoverable:

- `/opt/garuda-fresh/backups/movement-fix-20260913/`: prior native app/profile/log.
- `/opt/garuda-sim/garuda-causal-stream-diagnostics.before-movement-fix-20260913`.
- PC original backup: `hailo-export/follow-fixes-20260913/rollback/garuda-fresh-before.tar`.

Rollback with the simulator stopped and preserve current artifacts first. Use
a separate checkout for older ROS code (movement-fix parent `f8ea55e`), rather
than resetting this worktree. Do not reflash the board as routine troubleshooting.

## 12. Priorities for the next agent

1. **Confirm the user's current visual experience.** Boxes and click layer were
   browser-checked, and zoom no longer blanks across timing gaps. Check whether
   residual complaints mean pixel flicker, overlay color changes, held crop,
   JPEG/box misalignment or actual target loss. These are different mechanisms.
2. **Diagnose acquisition failures from frozen recordings.** Instrument raw box
   → confidence/confirmation → descriptor → published track → click acceptance
   → identity owner. Start with SOT 024. Add reasoned diagnostics rather than
   loosening all gates or moving the ground-truth click each frame.
3. **Reduce measured upstream age.** Searching/global tiles, embedding coverage,
   copies and motion processing can exceed 200 ms. Current live FOLLOW/HOLD
   toggles remain visible. Profile stages and cancel stale work; do not conceal
   the issue by extending control deadlines or labeling held frames fresh.
4. **Implement native-pixel ROI with correct geometry and bounded scheduling.**
   Preserve wide acquisition/re-entry; pair the original exposure; crop before
   destructive downscaling; map outputs into one stable coordinate system.
   Record FOV/intrinsics/ROI transforms and invalidate old references on changes.
5. **Validate model adaptation only after a frozen baseline.** Sequence-separated
   train/calibration/evaluation, class mapping, exact preprocessing parity and
   original/quantized/HEF checks. No aerial model has been newly trained here.
6. **Run controlled physical motion and identity tests.** Slow lateral motion,
   quick reversal, approach/crouch, partial exit/return, competing person and
   occlusion. Compare measured box, identity gap, capture age, request, actual
   wire command and PX4 heading. Log failures and wrong-target command time.
7. **Exposure/ISP ablations.** Compare bounded 10 ms/5 ms/current AE separately
   from detector schedule, then matching IMX678 denoising off/on with fixed
   geometry/exposure. Measure blur/ghosting, recall, age and compute contention.
8. **Standalone and real-FC readiness later.** Typed interfaces, onboard authority
   without the PC relay, qualified clocks/geometry, independent transport loss
   tests, actual identified FC firmware/endpoint and explicit hardware bench
   procedure. Current scripts accept simulator endpoints only. Do not call the
   current implementation real-FC-ready or flight-ready.

## 13. Operational pitfalls and scope boundaries

- Use an explicit working directory or absolute paths. A previous failed build
  from a wrong cwd staged an old binary with new config and stopped the camera.
- Board `/tmp` is RAM-backed. Repeated staged binaries exhausted startup reserve;
  prior campaign directories were moved to persistent storage. Current replay
  staging uses persistent storage. Do not fill `/tmp` with model/replay copies.
- Large PC replay/embedding artifacts belong under `hailo-export`, not root `/tmp`.
- Restore checks must observe advancing camera sequences; a launched PID is
  insufficient. Follow the existing lifecycle scripts, not ad hoc duplicate nodes.
- Do not use broad `pkill -f` patterns: they previously matched the invoking shell.
- Keep all vehicle I/O behind `GARUDA_SIM=1` and owned simulator endpoints. There
  is no real FC on this desk, and this handoff does not authorize adding one.
- Preserve original datasets, evidence and failed trials. Never count skipped
  frames, oracle crops or a verifier filename as successful tracking evidence.
- Old reports contain superseded open items and numerical snapshots. Prefer
  this file for current implementation and the actual source/evidence for detail.
- No new dependencies, camera settings, board packages, simulation commands or
  detector weights were introduced in the final overlay/zoom/documentation work.

## 14. Recent commit map

| Commit | Change |
| --- | --- |
| `2915825` | Actual Hailo/Gazebo visual demo and local console |
| `6ecca6c` | Detector schedule comparison and full-range simulator pixels |
| `b770169` | ROS 2/MAVROS on 15L with expiring simulation commands |
| `189470f` | ROS/MAVROS evidence and unresolved tracking gates |
| `e10bb40` | ISP audit and native on-board ROS ingress |
| `35f912d` | Native camera ROS authority joined to Gazebo console |
| `f8ea55e` | Frozen aerial regressions and verified camera restoration |
| `69d09c9` | Measured boxes, ROS scheduling, metadata wait, final deadline gate |
| `a8da6c8` | Console redesign and separate presentation JS |
| `464e987` | Frozen dataset rerun, retained negative results |
| `eb77f9f` | Main-camera image buffering; introduced overlay stacking regression |
| `a0277e2` | Overlay/click layering corrected; zoom retained through freshness gaps |

The next agent should be able to start with this file, inspect current state,
and continue a bounded outstanding item without repeating deployment, losing
the running session, or treating incomplete tracking validation as a pass.
