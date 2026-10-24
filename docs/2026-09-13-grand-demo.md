# Grand demo: physical camera, aerial footage, ROS 2, PX4 and Gazebo

Latest deployed fixes and measured limitations:
[movement geometry and ROS/MAVROS dispatch](2026-09-13-movement-fixes.md).
The subsequent [frozen dataset rerun and redesigned console](2026-09-13-dataset-rerun-and-console.md)
reproduced the weak aerial results; it does not supersede them with a pass.

## Visible experience

Open **http://127.0.0.1:8100/** on this PC. The native Gazebo desktop application
is launched alongside the local console, in the same owned simulator partition.
The console presents:

- physical camera, recorded aerial footage, or Gazebo drone-camera pixels;
- a Gazebo world-camera view beside the input video;
- selected **Target identity**, separate from temporary track IDs;
- target-centred 1×/2×/4× display inspection;
- actual on-board ROS input message count, frame sequence and age;
- requested setpoint, MAVROS publication, actually forwarded MAVLink values,
  rejection status and age, plus PX4 altitude/heading response;
- Take off, Follow, Hold, Land, Release and a bounded perception pause;
- an apparent-size reference readout, explicitly not a metric distance.

This is the existing Python/HTML local console, not a cloud website or a mocked
drone animation. No new dependencies. Sites workflow retained the local-only
architecture and functional operator layout. Browser opening was attempted but
the environment reported `No browser is available`; no browser click/layout QA
claim. HTTP/API and JavaScript syntax checks were used. The actual Gazebo GUI
process was launched and stayed alive during tested runs; its render warnings
and logs are retained, rather than asserting a screenshot was inspected.

## Three deliberately different modes

| Mode | Pixel origin | What the drone response means | Horizontal translation |
| --- | --- | --- | --- |
| Live | Actual IMX678 -> existing native YOLO11/OSNet tracker | Bounded heading response to a selected person; fixed desk camera cannot recenter itself | Disabled |
| Replay | Existing verified aerial NV12 sequence -> actual 15L inference | Bounded response to recorded detections; recording cannot react to drone movement | Disabled |
| Gazebo camera | Drone-mounted rendered RGBD -> actual 15L inference | Real visual closed loop: vehicle movement changes subsequent images | Uses exact-paired simulated depth; not physical monocular ranging |

For live mode the capture path is:

```text
IMX678 -> native YOLO11 / selected identity -> board-local ROS snapshot topic
                                                |
                                    on-board freshness / identity authority
                                                |
                               MAVROS /setpoint_raw/local (ROS ENU)
                                                |
                          SSH tunnel -> guarded actual MAVLink packet -> PX4 SITL
                                                                             |
                                                                       Gazebo vehicle
```

The PC still supplies operator permits and an independent final command gate.
It also reads camera snapshots/JPEGs for the display and supervisory check.
The board's perception input does **not** depend on echoing those images or
snapshots through the PC. This is not PC-independent onboard autonomy.

The request must match the board's source, producer, selection epoch and stable
lock identity. Board-local source deadlines are never rebased. Camera mode
computes heading from the local box, with the operator's latched reference and
declared HFOV; it does not integrate an unchanging image error indefinitely.
The absolute response offset is capped at ±30°, yaw rate at 0.8 rad/s, and XY
velocity remains zero. These are configured simulation limits, not benchmarks.
The actual packet must match its originating publication and unexpired permit.

## How to launch

Use this worktree. ROS scripts must first be staged with
`bash hosts/hailo15l/ros2/deploy_nodes.sh` when no owned ROS run is active.
Choose a new output directory on every run; evidence is not overwritten.

```sh
# Live desk camera; does not stop or replace the native detector.
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh live /tmp/garuda-live-demo-01

# Fully closed-loop rendered camera; temporarily lends the board NPU to this run.
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh gazebo /tmp/garuda-gazebo-demo-01

# Existing recorded car sequence, actual Hailo inference and simulator response.
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh replay /tmp/garuda-replay-demo-01 \
  /media/bhanu1234/Development/hailo-export/visdrone-sot-replay-20260912-roi/uav0000115_00606_s
```

All modes launch `gz sim -g` against the owned server's unique `GZ_PARTITION`.
The server and PX4 are owned child processes, not an arbitrary FC endpoint.
The launcher refuses a second PX4 instance. Stop/land the current run before
changing modes; do not switch the source while flying. Replay/Gazebo mode pauses
the desk pipeline and restores its unchanged configuration on exit, clearing
the old selection. Live mode leaves the camera running on exit.

## Demonstration script

1. Start live mode. Show the camera, Gazebo world and advancing ROS input count.
   Point out that PX4 is disarmed and no movement is authorized.
2. Stand fully in view and select the person using an ID card. The physical
   camera's JPEG and snapshot are independently published, so its overlay and
   inspection crop are labelled **approximate**, not exactly source-paired.
3. Take off in simulation. Confirm actual PX4 offboard hover and forwarded zero
   XY/yaw commands. Select **Follow** only with a verified fresh target.
4. Move left/right. Compare requested heading, board publication, forwarded yaw
   command and actual PX4 heading. A held/rejected command must stay visible;
   do not hide the freshness gate to make the demonstration look smooth.
5. Step out, return, and test occlusion. Explain temporary track IDs versus the
   persistent selected identity. A new selection/producer requires Follow again.
6. Use display inspection zoom. Set framing reference on a fully visible fresh
   target; move nearer/farther without changing pose. Show relative scale only.
7. Press Hold and Land; verify disarm. Then switch to replay and show the same
   video/command/vehicle views. Finally use Gazebo-camera mode for genuine
   visual-feedback following and the injected perception pause/recovery test.

The live pause button pauses the PC's supervisory camera delivery, not the
physical sensor. The board continues to see native frames, but the PC permit
expires and the command path holds. A native process kill, ROS loss, tunnel
loss and stale telemetry are distinct fault tests; do not conflate them.

## Relative distance with one camera

Yes, apparent target size provides a **relative distance cue**, under assumptions.
For a fixed focal length and unchanged visible target height, the pinhole model
gives approximately `Z / Z_reference = pixel_height_reference / pixel_height`.
This follows from the calibrated projection model in the
[OpenCV camera geometry reference](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html).
It is not an independently measured range in metres.

Aspect ratio alone does not give distance: an object can retain the same shape
at many distances. We use height fraction for scale and aspect change as an
unreliability check. The new diagnostic rejects edge-clipped boxes, stale or
unverified targets, invalid geometry and large pose/aspect changes. The
reference resets after producer/selection/geometry changes and survives a
temporary MOT ID change within the same selected identity.

These checks cannot resolve all failures: crouching, partial occlusion, detector
box jitter, perspective and camera tilt can change apparent height without a
distance change. The current readout **does not authorize translation**. Display
zoom cannot alter its input; it always uses the original tracking coordinates.

A subsequent simulation-only scale-hold controller can try to maintain a
reference size, with speed/displacement bounds and uncertainty holds. Validate
against Gazebo depth as an independent reference without feeding that depth to
the monocular controller. Safe separation in metres and obstacle clearance on a
real drone need validated ranging/geometry and separate collision safeguards;
bounding-box size alone does not establish either.

## Zoom, ISP and detector work still open

**Implemented now:** target-centred display crop. It adds no sensor detail and
does not change detector input. Existing DSP ROI inference still uses a reduced
1280×720 source. No claim of completed native-4K target zoom or AI-ISP improvement.

Next implementation order:

1. Expose a native-resolution paired source alongside the wide view. Review
   source-buffer bounds, DMA copies, RegionDetector geometry and exact timestamps
   together; do not merely enlarge one allocation or upscale the 720p preview.
2. Crop the native source with DSP before resizing to the model. Map every box
   back into one stable sensor/image coordinate system. Retain wide acquisition
   for re-entry. Budget ROI/global passes against original capture-age expiry.
3. Make crop/FOV/intrinsic changes explicit. A global digital zoom narrows search
   coverage; changing zoom must not masquerade as target approach in scale-hold.
4. Compare full-view/adaptive schedules and 10 ms/5 ms/AE exposures independently
   under repeatable motion/lighting. Compare the installed matching IMX678 AI
   denoiser off/on with fixed exposure and output geometry. Measure capture age,
   recall, wrong-target locks and compute contention, not just picture brightness.
5. Fine-tune/compile an aerial detector only after a frozen native-pixel baseline.
   Preserve original VisDrone classes; current HEF decoder assumes 80 COCO classes,
   so a ten-class model requires an explicit compatible decoder/class-map change.

See [the installed ISP audit](2026-09-13-camera-isp-and-native-ros.md) for model
hashes, current settings, limitations and the full camera experiment matrix.

## Dataset validation and acceptance

Use existing DET, SOT and MOT data for their distinct purposes: DET for detection,
SOT/MOT for temporal identity and re-entry. Do not treat SOT's one labelled object
as a complete detection annotation or randomly split adjacent video frames.
Existing validation has already informed tuning; it is regression evidence,
not untouched final evaluation. A reserved test-dev set and sequence-overlap
audit remain to be prepared before claiming generalization.

Retain footage/input hashes, initial selection, labels used only for offline
scoring, model/configuration hashes and full failed runs. Report target pixel
size, recall, identity switches/wrong-target commands, hold duration, recovery,
capture-to-command age and **actual forwarded packets**, not only host intents.

Before calling this a grand-demo pass, require: visible real person response,
repeatable return to the correct selected identity, original-deadline holds,
operator Hold/Land, and a complete closed-loop Gazebo test. A few forwarded
packets on an aerial clip is not robust aerial following. No real-FC or flight
qualification follows from these bench checks.

Actual results, failures and final deployed source hashes are recorded in
`bench/benchlog.md`, `bench/versions.md` and `bench/results/2026-09-13-grand-demo/`.

## Checkpoint after the unattended dataset work

The physical-person test produced **27.07° actual heading span**, 128 forwarded
motion packets, then Hold/Land/disarm. The final rendered-camera repeat produced
**7.85 m** maximum displacement, held during the injected perception pause,
recovered and disarmed. These are measured demonstrations, not a flight sign-off.
Framing reference was accepted at1.0x once; approach/retreat accuracy is untested.

The expanded11-sequence real-Hailo replay acquired only3 targets. Native-pixel
tiles on the same64 DET images improved person recall28.39%→31.41% at .15
confidence, but false positives12.891→16.219 per image and region inference-wait
sum128.53→222.39ms also rose. At .5 confidence person recall remained11.18% vs
12.01%. Source images max1920x1080, not4K. No live detector configuration was
changed to chase this regression subset; all failed runs were preserved.

Priorities for the next implementation/test phase:

1. **Explain acquisition failure at the click.** Keep the confirmed-track rule,
   but distinguish no detection, low confidence, missing descriptor and geometry
   rejection. Some targets have near-continuous raw detections yet never select.
   Test manual initial clicks separately from automated frame15 replay clicks.
2. **Budget native ROI, not an all-tile loop.** A fast wide pass keeps search and
   re-entry coverage; selective original-source crops add detail only while the
   original capture deadline permits. Cancel stale work, never extend its lease.
   Validate source mapping/stream identity before joining this to live authority.
3. **Address aerial model mismatch.** Freeze a sequence-separated train/calibration/
   evaluation manifest before fine-tuning. Current validation has already been
   used for development. A ten-class VisDrone HEF requires a deliberate decoder
   and class-map port, not swapping it into the80-class COCO parser.
4. **Qualify identity and faults.** Crowds/crossings/occlusion/re-entry with independent
   annotations; log wrong-target command time, capture-to-command age and holds.
   Repeat ROS loss, native-source loss, tunnel loss and operator takeover with
   the selected target; preserve original publication/permit deadlines.
5. **Then physical readiness.** Independently validated ranging and obstacle
   safeguards, sensor/extrinsic/clock validation, bounded HIL/propellers-removed
   tests, explicit real-FC authorization. No real flight from this desk result.

Reproduce the new detector comparison using a new output directory each time:

```sh
python3 bench/hailo_reference/prepare_visdrone_det.py DATASET_DIR INPUT_720 --sample-count 64
python3 bench/hailo_reference/prepare_visdrone_det.py DATASET_DIR INPUT_NATIVE --sample-count 64 --native-pixels
# Stop the owned simulator before borrowing the NPU; current desk profile must match.
python3 bench/hailo_reference/run_visdrone_det.py /tmp/garuda-reference-build/hailo-preprocess-probe INPUT_720 RESULT_720 --hef CONTROLLED_HEF --restart-profile start-follow
python3 bench/hailo_reference/run_visdrone_det.py /tmp/garuda-reference-build/hailo-preprocess-probe INPUT_NATIVE RESULT_NATIVE --hef CONTROLLED_HEF --restart-profile start-follow
python3 bench/hailo_reference/dataset_campaign_report.py RESULT_720 --paired-native RESULT_NATIVE --archive NEW_ARCHIVE
```

For SOT, `follow_campaign.py --modes fullview --frames 240 --sequences ...`
uses all explicitly named prepared clips. `dataset_campaign_report.py CAMPAIGN`
adds exact offline publication/expiry duration scoring to retained outputs,
including skipped source frames. Its truth interpolation assumption and declared
source timing are not a live control measurement. The evidence README explains
report versions, hashes and failed cases.

Final restoration verification caught and fixed a launcher false-success bug:
repeated binaries in the board's RAM-backed `/tmp` exhausted the non-CMA startup
reserve. The eleven campaign directories were moved to persistent storage, not
deleted; no memory limits were relaxed. Camera start now requires advancing
native snapshots, and future causal replay staging uses persistent disk. Earlier
`restored_profile`/zero return codes alone are not proof of camera recovery;
the evidence README records the failure and the corrected lifecycle smoke.

## Primary launch/control references

- [Gazebo Harmonic GUI](https://gazebosim.org/docs/harmonic/gui/) and
  [separate server/client invocation](https://gazebosim.org/libs/sim/).
- [PX4 offboard requirements](https://docs.px4.io/v1.17/en/flight_modes/offboard):
  retain the controller-liveness/failsafe requirements; do not bypass preflight
  health checks or force-arm to obtain a demonstration.
