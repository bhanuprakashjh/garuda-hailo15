# Physical camera, ISP/DSP and native ROS checkpoint — 2026-09-13

Read alongside [the preceding ROS/MAVROS campaign](2026-09-13-ros2-mavros-campaign.md).
Scope: civilian people/vehicle following, bench and simulation only. The phone
was a small-target pixel-width proxy, not the intended application.

## What changed in this checkpoint

- Added a reproducible, read-only installed-camera audit, with hashes of the
  resolved configuration files and referenced denoising models.
- Added native TCP feed -> ROS 2 topic -> same-board freshness observer. The
  original capture/sample times, stream identity and boot clock are preserved.
  These observations do not travel through the PC before entering ROS.
- Staged three observer files in the existing separate ROS userspace on the
  15L and ran it against the actual camera. No MAVROS publisher, vehicle service,
  arbitrary endpoint or camera-control connection exists in this observer.
- Added tests for source/clock mismatch, stale/cached observations, source age
  charging, bounded packet parsing, selected-profile resolution and zoom geometry.

No detector weights, desk executable, camera settings, system libraries, boot
configuration or GUI were changed. No training run, AI-ISP activation or physical
camera-driven PX4/Gazebo demonstration was completed in this checkpoint.

## Installed capability versus current use

Evidence: `bench/results/2026-09-13-camera-isp/installed-audit.json`.
This resolves `current.json` -> selected **GarudaFreshLetterbox** profile, not
the first profile in the media configuration.

| Feature | Verified on this installed 15L/IMX678 setup | What remains unproven |
| --- | --- | --- |
| Digital zoom | Application configuration exposes ROI/magnification modes; active profile has zoom disabled | Actual crop placement, geometry and timing after enabling it |
| AI low-light ISP | Stock `AI_ISP_Gen1_Basic` profile and matching `pre_isp_hdm_678_h15l.hef` are present | Performance and tracking quality when enabled alongside YOLO11s/OSNet |
| Current AI denoising | Selected daylight IQ file has `denoise.enabled=false` | This is configured state, not an independent live ISP-register readback |
| Exposure | Live V4L readback: automatic AE enabled, integration time 33.006 ms | Motion blur causality; no controlled moving-target exposure comparison in this checkpoint |
| DSP crop/resize | Our C++ region detector calls `dsp_crop_and_resize_letterbox` | Native-4K detector ROI path; current region detector is limited to 1280×720 sources |
| Stabilization | Vendor configuration exists; do not infer a calibrated gyro/IMU or usable stabilization from a JSON switch | Motion compensation with correct camera calibration and timestamps |
| Optical zoom | A configuration field exists | Presence of an actuated zoom lens; a software field is not hardware proof |

The active application produces 640×640 letterboxed and 1280×720 streams,
configured at 20 FPS; preview is configured at 10 FPS. These are settings, not
measured detector throughput. Managed detection, ROI assistance, search tiles
and up to six person embeddings are enabled in the existing desk configuration.

The important distinction: current tracking ROI inference crops the already
reduced 1280×720 source. It is **not** a crop of the original 3840×2160 pixels.
Native `DmaImage` can represent larger images, but `RegionDetector`, source-frame
pairing and application geometry must be reviewed together before changing this.
Increasing only a size constant does not establish a correct 4K path.

The installed low-light profile includes Bayer neural denoising with feedback
and a matching IMX678 model. Its auto-exposure configuration allows a long
shutter. Better-looking static images therefore must not be equated with better
moving-target evidence. AI denoising also uses an inference model; shared compute
and memory effects alongside detection/re-identification require measurement.
Do not run the installed `setup_imx715_ai_isp.sh` for this IMX678 camera.

## Measurements and limits

The audit made 46 HTTP state samples over a requested five seconds, with no
selected target. Capture-to-read age: minimum **210.081360 ms**, median
**292.070640 ms**, maximum **434.484640 ms**. These are an uncontrolled scene
spot check, not a motion-recall benchmark. The audited gain was 12.8828125;
auto-exposure can change gain between readbacks.

This source age already exceeds the follow consumer's 200 ms limit in that
sample. Moving observations locally into ROS does not repair upstream latency.
The existing desk viewer's 500 ms freshness setting must not expand the
controller's stricter limit.

First on-board ROS observer run: 200 status ticks, 249 native snapshots received,
124 ROS messages consumed before a deliberate five-second publication freeze,
zero native transport errors. No target was selected and no motion eligibility
was demonstrated. Final reported capture age after the freeze was 5294.203520 ms;
it was not rebased to a new timestamp. Both initial and final-code repeat logs
are retained. See benchlog for final repeat results.

Unit tests, rather than this unselected live run, demonstrate the eligible ->
expired transition: a selected synthetic envelope expires at its original
capture + 200 ms deadline, including when repeated or the feed becomes silent.
Do not present this as an actual selected-person camera loss test.

## Where the end-to-end system stands

| Boundary | Evidence/state |
| --- | --- |
| IMX678 -> native YOLO11/tracker | Running existing desk pipeline; latency/robustness gates still fail |
| Native camera -> on-board ROS | New read-only path executed on actual 15L; no PC perception round trip |
| On-board ROS/MAVROS -> guarded PX4 simulator | Previously tested, with axis and transport-loss evidence |
| Joined native-camera -> ROS authority -> MAVROS -> PX4/Gazebo | **Not joined by this observer**; requires operator-permit/identity and exact-publication safety binding |
| Gazebo drone camera -> 15L -> ROS/MAVROS -> PX4 | Previous rendered-camera experiments exist; simple-person scene only |
| Aerial people/vehicles | Existing VisDrone regressions expose failures; not robust or flight-qualified |

The next integration must consume the local ROS observation in the authority,
not echo it through the PC. Preserve source expiry, lock/stream/epoch identity,
explicit new Follow permission after a selection/source change, zero motion on
stale input, and the guarded simulator's exact-publication deadline checks.
The observer intentionally cannot grant a follow permit.

A stationary physical camera and recorded aerial video can demonstrate bounded
simulated heading response, not visual closed-loop recentering. Keep translation
disabled without valid metric range. Gazebo's drone-mounted camera must supply
the closed-loop visual test. Real FC bench tests and real flight are later gates.

## Ordered camera experiments

These are planned comparisons, not claimed results. Preserve the working
configuration and record capture timestamps, all settings and both successful
and failed sequences. Reject a candidate that looks better but makes evidence
older or creates wrong-target locks.

1. **Exposure and latency baseline.** Compare current AE with bounded 10 ms and
   5 ms exposures under repeatable lighting and motion. Read back actual shutter
   and gain. Independently compare full-view and adaptive detector schedules.
   Do not change confidence, exposure and detector schedule in the same ablation.
2. **Pre-downscale crop.** Establish the actual sensor-to-inference transform.
   Compare full view with native-resolution target ROIs; keep a wide acquisition
   path for re-entry. Use DSP crop/letterbox before the information-losing resize.
   Do not blindly enable global digital zoom for following: it removes peripheral
   search coverage and changes the image-to-angle relationship.
3. **Zoom geometry.** Test 1×, 1.5× and 2× as candidate settings only, within
   verified API support. Record original sensor ROI, scaling, padding and effective
   intrinsics. In an ideal pinhole model, centred crop HFOV is
   `2*atan(tan(full_HFOV/2)/magnification)`, not `full_HFOV/magnification`.
   A geometry change invalidates old selection coordinates and controller
   calibration; require new selection/Follow permission.
4. **AI low light.** Use the installed IMX678/H15L profile/model in a separate
   compatible experiment configuration. Match short exposure and output geometry
   for off/on tests. Measure blur/ghosting, small-object recall, capture-to-control
   age, compute contention and identity errors. Check stock profile version
   compatibility instead of copying its complete application settings blindly.
5. **DSP and stabilization.** Profile DMA copies, crop/resize and detector passes
   separately. Consider stabilization only after calibration, crop compensation
   and sensor/gyro availability are established. Do not enable sharpening, DIS,
   denoising and zoom together without isolated evidence.

## Dataset and SIL campaign still to execute

- Use VisDrone DET train for aerial detector adaptation; val remains a development
  regression set because it already influenced tuning. Reserve an untouched
  test-dev campaign for final detector evaluation; verify sequence overlap if
  mixing DET, MOT and SOT sources. Do not randomly split neighbouring video frames.
- Preserve all ten original DET labels for scoring. Make explicit person/vehicle
  control-label mappings. A ten-class model requires decoder and HEF/NMS contract
  changes; the current region decoder explicitly assumes 80 COCO classes.
- Do not train detection on SOT boxes as though they annotate every object.
  SOT/MOT serve temporal identity, occlusion, re-entry and distraction evaluation.
- Use the existing `bench/hailo_reference` preparation/scoring runners; do not
  create a second inconsistent RGB/NV12 conversion. Keep original datasets intact.
- Report source and actual network target pixel widths in bins (<8, 8–16,
  16–32, >=32), recall, wrong-target control, reacquisition correctness, longest
  gaps, and p50/p95 capture-to-command age. Size bins are analysis definitions,
  not assertions that all objects in each bin are detectable.
- Freeze source ONNX -> floating-point -> quantized -> HEF parity inputs before
  a model deployment. Calibration must not use held-out evaluation data.
- Run simulator source stall, ROS/tunnel loss, selection change, telemetry loss,
  re-entry and operator Hold/Land with actual forwarded MAVLink evidence.

No new datasets were downloaded, no model was trained, and no benchmark gate
was relaxed during this checkpoint. Existing Python/ROS dependencies were reused;
no new dependency or product-license clearance is implied.

## Reproduction

From this worktree, the audit can run without installing it on the board:

```sh
ssh -oBatchMode=yes root@10.0.0.1 'python3 - --sample-seconds 5' < hosts/hailo15l/camera_audit.py
python3 -m unittest discover -s hosts/hailo15l -p test_camera_audit.py -v
python3 -m unittest discover -s hosts/hailo15l/ros2 -p test_native_camera.py -v
```

Observer staging is included in `hosts/hailo15l/ros2/deploy_nodes.sh`. Obtain the
board boot ID from `/proc/sys/kernel/random/boot_id`, then run inside its existing
ROS rootfs with `GARUDA_SIM=1`, `/bin/bash /opt/garuda/run_camera_observe.sh`,
`--clock-domain linux.monotonic:<current-board-boot-id> --seconds 10 --freeze-after 5`.
Use the current ID; the recorded ID is intentionally not reusable after reboot.
The script uses local-only ROS domain 73 and exits after its bounded duration.

## Structural review and strongest counterargument

This phase adds one audit and a deliberately read-only ROS ingress/observer;
no second simulator, GUI or perception implementation. Reuse the existing
freshness contract and simulator authority for the subsequent integration.

Strongest counterargument: a correct transport can faithfully deliver poor,
late detections. Neither the installed AI-ISP model nor a ROS topic proves
robust tracking. The unselected live test cannot establish selected-target
loss/reacquisition or flight response. Those gates remain explicitly open.

## Primary references

- [Hailo Media Library](https://github.com/hailo-ai/hailo-media-library): public
  integrated capture, image enhancement and inference interfaces; installed
  configuration hashes above take precedence over current upstream defaults.
- [Hailo camera configurations](https://github.com/hailo-ai/hailo-camera-configurations):
  sensor/application-specific tuning profiles.
- [Ultralytics VisDrone DET documentation](https://docs.ultralytics.com/datasets/detect/visdrone):
  detection split and class definitions; DET images are not a substitute for MOT
  identity tests or a closed-loop camera simulation.
