# bench/benchlog.md — measured results only

## 2026-09-28 — live phone recording uuZEjY: expired selection

24/24 network-only samples saved to board eMMC; pixel hashes/dimensions and
sample/sequence/producer identity checks pass. 11.500073 s span, every10 processed
frames. All24 control-invalid: reacquire_window_expired; visual uninitialized
and never used. Phone detections in8 samples, so detections alone did not revive
expired selection. Loss transition predates first saved frame: not a valid
live visual-bridge qualification. All pixels reviewed; evidence and limitations:
results/2026-09-28-live-visual-recordings/uuZEjY/README.md. Original retained.
Postcheck capture inactive/no error, native running, same node/config hashes;
no replay/MAVROS, no runtime changes. Next trial needs active selection at capture.

Rules: every number here comes from a harness/command actually run on this bench, with date
and a matching `versions.md` snapshot. No estimates. Unmeasured = `TBD-bench`.

---

## 2026-09-28 — visual-phone tracker enabled on board (owner requested)

Staged tested native build and enabled only tracking.visual_phone_tracking;
full-frame1024 HEF, person re-ID, thresholds and camera/ISP files unchanged.
Active node76718b88...cf378, config572dcddb...f76d1. Both previous binary and
exact current.json backed up in /opt/garuda-fresh/live-visual.KfoiRI.
25 startup samples sequence7→489: age min/median/max84.97184/127.28768/
171.01444ms; rejected0, source-pair missing0/invalid0, matched490. Visual
diagnostics present but no phone selected, so these are stream health results,
not loaded visual tracking or fast-motion qualification. No new recording/FC.
9CTest and3 deployment guard tests pass. Initial preflight lacked ldd; used
dynamic-loader tracing instead, no service change during that failed attempt.
Evidence and exact rollback: results/2026-09-28-live-visual-enabled/README.md.

## 2026-09-27 — selected-phone image measurements, recorded proof (not deployed)

Implemented an optional C++ visual localizer and explicit selected-target
measurement path, including the native adapter. Default off; current live1024
binary/config/model and ISP unchanged. No new recording or FC activity.

Fast180 fixed-input replay, user selection15, 164 subsequent frames:
baseline72 versus candidate147 control-valid observations; longest missing run
36 versus4 frames (valid-to-valid brackets6000.094 versus766.672ms). Sparse
checkpoint IoU>=.5:7/16 versus14/16; wrong accepted checkpoint boxes0 in both.
All37 final visual-only boxes inspected on the saved pixels, on the phone;
not independent dense annotation. Source/candidate changes were developed on
this clip, so it is not a holdout result.

On-board CPU replay beside unchanged live camera: final visual localization
plus seed refresh median8.79752ms,p95 15.65616ms. First accurate640 search
rejected for cost78.96904ms/296.49464ms;320 direct search20.29460/47.39068ms;
final coarse-to-fine147 valid frames preserved. Live loaded latency TBD-bench.
Host/ARM validity/state/reason/ID/source decisions identical on180 frames;
maximum box numeric difference2.274e-13px. Two drone-car traces192+97 frames
have exact core parity flag off/on (phone-only isolation, not drone gains).
Two untuned12-frame phone clips unchanged; no visual bridges exercised.

9CTest suites pass;68trackingPython tests,1skip;24follow and7simulation bridge
tests pass. Exact SDK native adapter and replay cross-build succeeded.
Strongest objection: sparse labels, reused development clip, no real lookalike
occlusion or live enabled-candidate qualification. Keep feature off until a
supervised live canary measures latency and wrong locks. Existing recovery,
person identity and non-phone classes are retained. Full artifacts, replay
video, guards, provenance, failed iterations and reproduction:
`results/2026-09-27-visual-target/README.md`.

## 2026-09-27 — owner-authorized live 1024 full-frame deployment

Supersedes the earlier "not promoted" operational status only: owner explicitly
requested a live trial; recorded accuracy conclusions remain unchanged.
Existing binary retained; candidate HEFbb9fe29b...ab43 staged in
`/opt/garuda-fresh/live-1024.8GsSQc`. Active config26d38d7c...6175 selects direct
frontend1024x576 input, no managed detector, no tiles, no target-ROI detector.
Tracker/re-ID/thresholds, sensor/IQ/NR settings and old model/config files retained.

20 startup API samples: sequence8→390, timestamp-valid throughout, rejected
frames0; API age min/median/max64.29816/98.56556/154.18212ms, all<500ms. Runtime log
confirms1024x576; MJPEG responds. Not a tracking or loaded-latency benchmark.
No recording/replay/MAVROS; eMMCfree2707730432bytes. AE33006us,3DNR1/mode1/strength127.

First attempt automatically rolled back on the existing2MiB paired-recording
guard:1024 input plus720p source exceeds it. Kept the guard and disabled paired
diagnostic capture for this profile; re-ID still has its paired source cache.
Second attempt ran correctly but verifier expected absent disabled-tile fields;
corrected/regression-tested that check after safe automatic rollback. Third
attempt passed. No guard increase, binary replacement or unrelated tuning.

Red-team: smoke shows liveness/configuration only, not improved phone identity
tracking; direct frontend resize is not identical to recorded720p→DSP input;
exposure remains33ms. User motion validation pending. Full hashes, health samples,
failure records and exact rollback: `results/2026-09-27-live-1024-final/README.md`.

## 2026-09-27 — same-weights 1024x576 YOLO11s: modest gains, not promoted

Owner-approved higher-input-resolution experiment; recorded footage only.
Existing checkpoint's175 learned parameter tensors match the deployed float
source exactly; four full640 output tensors also match exactly. Exported1024x576,
same1024-image calibration list/recipe, DFC5.3.0/Hailo15L build successful.
Candidate HEF SHA256 `bb9fe29b984e296be1cf15c8b934aca7514428ed2d1d4cc54f6bd11017efab43`.
Measured preparation/parse/PTQ/compile wall times42.565/17.756/514.330/462.827s;
12 compiled contexts. Existing AGPL export dependency remains bench-only.

Actual DSP/NPU replay:184 saved phone exposures ×5 fixed windows ×2models,
plus166 sampled VisDrone frames ×2models =2172 evaluations. All completed.
Repeated640 phone baseline matches previous920 raw and filtered prediction
arrays exactly. Fixed thresholds/border filter, same source pixels, no oracle
crop selection or mixed-in relative-boundary candidate.

Full-view matching at score>=.4, IoU>=.5 (640→1024):

- Fast phone sparse labels:11/18→13/18; all180 exposure phone availability
  115/180→120/180. Median measured copy+DSP+input-copy+inference25.71962→32.67206ms.
- Four recent difficult phone exposures:0/4→0/4.
- Drone car245:17/48→23/48; car115:21/25→21/25; person024:84/93→85/93.
- Five-tile phone availability135/180→137/180; labelled15/18→16/18;
  median isolated five-pass stage sum129.92282→163.26506ms.
- At weak.15 threshold, unmatched phone boxes on18 labelled frames increase
  1→9 in the five-tile comparison. At.4, both have zero on that sparse subset.

Decision: do not replace live detector. The1024 single-pass candidate remains
behind current640 five-tile detection coverage despite its lower per-frame
compute cost. Causal tracker/scheduler identity and age comparison remains
TBD-bench; direct4K→1024 ISP path also TBD-bench. No live-FPS or tracking claim.

Red-team: approximate sparse phone labels and reused development data; fixed
crops, no ground-truth identity evaluation, only sampled SOT frames (one labelled
target), no camera/re-ID contention or thermal series. Timing excludes capture,
transport, queues and tracking; five-pass probes repeat source copies. Retained
720p pixels cannot establish gains from bypassing the initial4K downscale or
changing exposure/NR. The float1024 reference also retains weak/missing phone
detections, so resolution alone is not supported as the failure's complete cause.

No production model/config/ISP change or flight command. Original node/profile/
HEF protected hashes preserved and camera advancing376→388 after restoration.
No active recording/replay/MAVROS; eMMCfree2734161920bytes.8CTest,70benchPython,
68trackingPython(1skip) PASS. Full evidence/reproduction:
`results/2026-09-27-resolution-1024/README.md`; environment in versions.md.

## 2026-07-31 — garuda-follow: mono follow-me SITL closed loop PASS

`services/garuda-follow/sitl_followme.py` (`GARUDA_SIM=1` gated) run in the ROS 2 Jazzy
container on the Pi against PX4 SITL (`sihsim_quadx`) on the PC over the Phase-5 uXRCE bridge.
A **synthetic** subject at world (6, 4, −2) m is projected into the drone's simulated camera;
the real `follow_controller.compute` drives offboard setpoints (mixed: altitude-hold on Z,
follow velocity on X/Y, yaw-rate for heading). The **real perception path** (CM3 → tracker →
controller command) is proven separately in the portal — not claimed here.

| Metric | Value |
|---|---|
| Framing error (start → converged) | **0.901 → 0.008** (held < 0.03 for ~50 s to end) |
| Time to framing error < 0.09 | ~11 s (took off to 3 m hold altitude first) |
| Drone final pose (NED) | ~(5.1, 3.2) m, alt 3.00 m, yaw ~0.6–0.8 rad — facing/framing the target |
| Commands at convergence | vx/vy → ±0.01 m/s (controller settles, no chatter) |
| `GARUDA_SIM` gate (no flag) | refuses: "REFUSED: GARUDA_SIM=1 not set …", exit 1 |

**Scope / honesty (rule 1 + rule 9):**
- Synthetic target, simulated flight — the drone's static bench camera cannot physically
  follow a moving sim drone, so this proves the *control loop closes and holds*; the *real
  detector/tracker on live video* is the portal's job.
- Mono: framing = bearing (yaw) + bbox-size proxy for range. No metric depth; `vz` from the
  2D projection is a no-op, so altitude is held by a position-Z setpoint, not vision. True
  vertical framing needs ToF or the GS stereo pair.
- Two live-integration fixes surfaced only by running against real PX4 (the pure logic —
  32 unit tests incl. a deterministic convergence + reacquisition proof — was already green):
  (1) pose read from `/fmu/out/vehicle_odometry` because this firmware (47ce421) publishes
  `vehicle_local_position` under the versioned name `vehicle_local_position_v1` that the
  container's `px4_msgs` doesn't match; (2) takeoff + altitude-hold via a mixed
  position/velocity setpoint (a velocity-only follow controller assumes an already-flying
  drone). Also: `EKF2_GPS_CTRL` had persisted to 0 from the P5 failsafe demo — reset to 7.
- Safety: nothing arms real hardware; `GARUDA_SIM` gated; a lost/invalid target commands a
  hover (altitude-hold, zero horizontal velocity), never a chase — the covariance/validity
  discipline from the P5 VIO-freeze finding, applied to following.

### Same day — deterministic convergence test (dev PC, not a hardware measurement)

`services/garuda-follow/tests/test_convergence.py` drives the **real**
`follow_controller.compute()` against a minimal drone+world-target simulator
(`sim_kinematics.py`) — no PX4, no hardware, fully deterministic. This is a unit test
(reproducible via `pytest services/garuda-follow/tests/test_convergence.py -v` on any dev PC
or in CI), not a bench measurement; recorded here per rule 1 so every number cited in docs
traces to this log. Provenance: the test file itself (see also
`.superpowers/sdd/2026-07-30-garuda-follow/task-5-report.md`, which first recorded these
figures).

| Test | Metric | Value |
|---|---|---|
| `test_follow_loop_converges_and_holds` | Framing error, start → end (400 ticks, 20 s sim time) | **0.907 → 0.028** (`errs[0]=0.9068`, `errs[-1]=0.0280`; tail avg over last 20 ticks = 0.0280 — held, not a transient dip) |
| `test_reacquires_when_target_enters_fov` | Framing error, on re-acquisition → after 100 more real-controller ticks | **0.838 → 0.057** (`err0=0.8381`, `err1=0.0567`) |

Scope: both numbers come from stdlib-deterministic arithmetic (no randomness), so re-running
the test reproduces them exactly — this is disclosed as dev-PC/CI unit-test math, distinct
from the SITL entry above (a real PX4 run) and from any hardware benchmark elsewhere in this
log.

---

## 2026-07-29 — P1: NPU sanity (partial)

Versions snapshot: `versions.md` 2026-07-29 Trixie entry.

| Item | Result |
|---|---|
| `hailortcli fw-control identify` | **PASS** — Device Architecture HAILO10H, FW 5.1.1 (release,app) |
| `lspci` Hailo enumeration | PASS — `0001:01:00.0 Co-processor: Hailo Technologies Ltd. Device 45c4 (rev 01)` |
| `vcgencmd get_throttled` at identify time | `0x0` (idle) |
| Model-zoo detection fps on sample video | **PASS — 75.95 fps** (see video-pipeline subsection) |
| LLM prompt via hailo-ollama | **PASS** (see LLM subsection below) |

Caveats (rule 9 red-team, to resolve before ticking the P1 gate):
- Kernel 6.18.34 + h10 5.1.1 from the same repo snapshot — coupling currently consistent;
  re-verify identify after any kernel change (rule 11).

### Same day, later — NPU benchmark on charger power

Power provenance: the first run below predates user confirmation of the charger swap — its
source is uncertain (likely still PC USB-C; it held `0x0` and 5.04 V regardless). The run was
repeated on **confirmed USB-C PD charger** power (model/wattage unrecorded): **FPS 76.24**,
temp mean 53.7 °C / max 59.5 °C, post-load `throttled=0x0`, rail 5.049 V — consistent across
both sources. Identify/install earlier ran on PC USB-C power (trivial load, `0x0` throughout).

| Measurement | Value |
|---|---|
| `hailortcli benchmark /usr/share/hailo-models/yolov8m_h10.hef` | **FPS: 76.23** |
| NPU temperature during run | mean 53.4 °C, max 59.5 °C |
| `get_throttled` after run | `0x0` — no under-voltage/throttle events since boot, incl. during load |
| 5 V rail (`pmic_read_adc EXT5V_V`) after run | 5.041 V |
| On-device power measurement | not supported on this device |

**Scope note (rule 1):** 76.23 fps is NPU streaming throughput on synthetic inputs — NOT the
"sample video" end-to-end number the §5 gate asks for (that includes decode + pre/post). The
gate stays unticked until a video-pipeline run is measured.

### Same day, later — LLM via hailo-ollama (P1 item PASS)

Setup: `hailo-gen-ai-model-zoo` 5.1.1 deb (dev-public.hailo.ai, 7.6 MB), `hailo-ollama`
server on :8000, model `qwen2:1.5b` pulled (1.68 GB, sha256-verified). Charger power.

| Measurement | Value |
|---|---|
| Prompt | "In one sentence, what is a Kalman filter?" |
| Response | coherent, correct one-sentence definition — PASS |
| `eval_count` | 39 tokens |
| `total_duration` (server-side) | 5.13 s |
| Wall time incl. first model load to NPU | 14.75 s |

Note: server reports no separate `eval_duration`, so tokens/s is not cleanly derivable —
raw values recorded instead. Catalog also offers `deepseek_r1_distill_qwen:1.5b`,
`llama3.2:3b`, `qwen2.5-coder:1.5b`, `qwen2.5-instruct:1.5b`.

### Same day, later — end-to-end video pipeline (P1 gate measurement)

Pipeline (on-Pi, GStreamer/tappas): `filesrc detection0.mp4 (Hailo example street clip,
2.3 MB, ~25 s @30 fps) → decodebin → videoconvert/scale → RGB 640×640 → hailonet
yolov8m_h10.hef → hailofilter libyolo_hailortpp_post.so → fakesink` — decode + preprocess +
inference + postprocess all included. Charger power.

| Run | Result | Verdict |
|---|---|---|
| 1st: sink sync enabled (mistake) | avg 30.09 fps, current flat 30.00 | DISCARDED — measured the file's playback clock, not capacity |
| 2nd: sync=false | avg 76.85 fps, 0 drops | TAINTED — `get_throttled=0x50000` sticky (UV + throttle occurred somewhere since boot) |
| 3rd: fresh boot, sync=false | **avg 75.95 fps, 0 drops**, flags `0x0` before AND after, rail 5.040 V | **COUNTED — gate PASS (≥30 required, 2.5× margin)** |

End-to-end ≈ NPU-only (75.95 vs 76.24) ⇒ NPU-bound; A76 decode/pre/post keeps up at this clip size.

**Rule 9 red-team (strongest case the result is wrong, addressed):**
- *Thermally throttled?* Flags `0x0` pre/post counted run; comparable NPU load peaked 59.5 °C.
- *Underpowered?* Real concern — run 2's boot window logged a genuine UV event (`0x50000`) on
  this unverified PD charger. Addressed by reboot + clean re-run (`0x0`→`0x0`). Constraint
  stands: obtain/verify a true 5 V/5 A supply before P6 concurrent-load work.
- *Clock-sync artefact?* Run 1 was exactly that — caught (avg == file fps, current flat 30.00)
  and discarded; counted run is 2.5× file rate, incompatible with clock-lock.
- *Cherry-picked input?* One ~640p 30 fps clip. Sufficient for the P1 sanity gate as written;
  NOT evidence for 1080p/other codecs (decode cost rises). Untested territory noted.
- *Anything else running?* Fresh boot; hailo-ollama server not running (died with reboot).

**P1 gate: TICKED 2026-07-29.**

---

## 2026-07-29 — P2 start: CM3 first light

CM3 (IMX708, module ID 0x0301) detected on CAM/DISP 0 after cable debug. Root cause of
initial non-detection: cable orientation/seating (forced `dtoverlay=imx708` probe showed I2C
`-5` no-ACK on both ports until a correctly-oriented, fully-seated attach; then clean probe).
Diagnostic overlays removed after success; detection re-verified via stock `camera_auto_detect=1`.

| Item | Result |
|---|---|
| `rpicam-hello --list-cameras` | imx708, modes 1536×864@120.13 / 2304×1296@56.03 / 4608×2592@14.35 (fps as reported by libcamera) |
| `rpicam-still` 4608×2592 capture | PASS — real image verified on PC |
| Remaining P2 gate items | GS pair trigger/jitter/soak — blocked on IMX296 hardware |

### 2026-07-30 — CM3 delivered-frame metrics (harness: `bench/cm3-stream-metrics.sh`)

30 s per mode, raw YUV420 → /dev/null (no encode), PTS-trace analysis, drop = gap >1.5×
frame period. `throttled=0x0` before and after the full run.

| Mode | Frames | Delivered fps | Drops | Max gap |
|---|---|---|---|---|
| 1536×864 @120 | 3581 | 120.12 | 0 | 8.33 ms (=1 period) |
| 2304×1296 @56 | 1670 | 56.02 | 0 | 17.86 ms (=1 period) |
| 4608×2592 @14 | 412 | 14.00 | 0 | 71.41 ms (=1 period) |

Max gap equal to exactly one nominal frame period in every mode ⇒ zero delivery jitter
beyond frame quantisation in these windows. Scope: 30 s windows, idle bench — the P2 1-hour
no-drop soak remains a separate, longer test (and its gate wording targets the GS pair).

---

## 2026-07-30 — P4/P5 groundwork: ROS 2 Jazzy container + cross-boundary DDS PASS

`garuda/ros-jazzy` built on the Pi from committed `hosts/pi5/Dockerfile.ros-jazzy`
(never interactively modified — decisions.md rule). Proof: talker and listener in two
separate containers, `--network=host --ipc=host`, CycloneDDS both ends — listener received
from message 1 (no discovery loss), steady 1 Hz. Foundation for PX4 SITL bridge work.

### Same day, later — P5 bridge topology PASS: PX4 SITL (PC) ↔ ROS 2 (Pi) over Ethernet

Faithful dress rehearsal of the real topology (FC is a separate box across a cable):
PX4 SITL + SIH quad on the PC, uXRCE-DDS client → Micro XRCE-DDS Agent in container on the
Pi (UDP 8888 over the direct link), px4_msgs decoding in the Jazzy container.

| Item | Result |
|---|---|
| XRCE session establishment | PASS — client 10.42.0.1 connected ~1.5 s after agent start |
| `/fmu` topics visible on Pi | **69** (out + in, incl. the visual-odometry inputs P5 needs) |
| Typed echo `/fmu/out/vehicle_attitude` | PASS — live SIH quaternion decoded via px4_msgs |

Next (task 4): publish VehicleOdometry → `/fmu/in/vehicle_visual_odometry`, confirm EKF2
fusion, then the covariance-failsafe demo (the actual P5 gate).

### Same day, later — P5 odometry → EKF2 external-vision fusion PASS

`bench/ev_odom_pub.py` (rclpy, 30 Hz stationary NED pose, 0.01 m² position variance,
quality 100) in the Jazzy container on the Pi → `/fmu/in/vehicle_visual_odometry` →
SITL on PC with `EKF2_EV_CTRL=3` (h+v position).

| Check | Result |
|---|---|
| `px4-listener vehicle_visual_odometry` | message arriving ~20 ms fresh, fields intact |
| uXRCE timesync | PASS — ROS timestamps translated into PX4 clock domain |
| `estimator_status_flags` | **`cs_ev_pos: True`, `cs_ev_hgt: True`** (yaw/vel False as configured) |

Remaining for the P5 gate: the VIO-kill → covariance-failsafe demonstration (scripted
scenario with the vehicle armed in simulation), and eventually the same pipeline against
the real CA90. All motion is SITL-simulated on the PC; nothing on this bench arms hardware.

### 2026-07-30 — accidental finding: confidently-wrong EV feed diverges EKF2 (kilometre-scale)

During an offboard flight demo (1 km circuit), the earlier stationary EV publisher was left
running: 30 Hz "position = origin, variance 0.01, quality 100" while GPS reported real motion.
Result: estimator divergence — `vehicle_local_position` reached z = **+1013 m** (a kilometre
below home) with commanded altitude never past 120 m, horizontal estimate pinned near origin.
Recovered by stopping the stale publisher and restarting SITL (fresh estimator).

**Why this matters (P5 failsafe evidence):** a stale-but-confident VIO stream is worse than a
dead one — it doesn't trigger timeout-based failsafes and actively poisons the filter. This is
precisely why the architecture gates failsafe on **odometry covariance/validity, not link
liveness** (CLAUDE.md §1). The covariance-failsafe demo must include this scenario: not just
VIO-kill, but VIO-freeze (last pose repeated with unchanged covariance).

### 2026-07-30 — P5 failsafe scenarios (SITL, vision-primary navigation)

Setup: SITL restarted **vision-primary** (`EKF2_GPS_CTRL=0`, `EKF2_EV_CTRL=3`,
`EKF2_HGT_REF=0` baro). `bench/failsafe_demo.py` on the Pi is the sole position source
(echo-EKF healthy feed, 20 Hz); offboard setpoints stream throughout, so reactions are
attributable to vision alone. Sabotage at t=25 s mid-circuit, observation to t=60 s.

| Scenario | PX4 reaction | Verdict |
|---|---|---|
| **VIO-kill** (feed stops) | `Failsafe: blind land` + `Failsafe activated` within seconds; controlled descent 15 m→ground; disarm | **CAUGHT** — FC-side timeout works for dead feeds |
| **VIO-freeze** (stale pose, fresh timestamps, covariance unchanged) | **No failsafe for the full 35 s window** — nav_state stayed OFFBOARD, estimate pinned at freeze point while setpoints marched on; physical vehicle dragged away (est. read 1.5 km out, 30–50 m/s, once the feed finally died and dead-reckoning unwound); failsafe only fired when the script exited and freeze degraded into kill | **NOT CAUGHT** — FC-side liveness detection is provably insufficient |

**Architecture consequence (the actual finding):** the FC cannot detect frozen VIO on its
own — staleness/degradation detection MUST live on the companion. The `garuda-vio` failsafe
contract: detect own tracking degradation/staleness, inflate reported covariance (or mark
invalid / stop publishing) so the FC's covariance gate fires. This scenario pair becomes the
permanent regression harness for that contract. P5 gate itself stays unticked — its wording
requires the real CA90; the SITL half of the phase is complete.

### 2026-07-30 — P4 groundwork: Basalt VIO baseline on Pi 5 (TUM-VI room1)

Full details + provenance: `datasets/baselines/tumvi_room1_pi5_basalt.md`. Headline: **2821
frames in 46.3 s = 61.0 fps (3.4× real-time), RMS ATE 0.1104 m**, flags `0x0` before/after
(reboot-cleaned; the -j2 build had tripped `0x50000` on the PD charger — third UV strike for
this supply). Per-stage timings TBD-bench.

**EuRoC MH_01 (same day, after ETH outage workaround): RMS ATE 0.0783 m vs published
desktop 0.07 m = 1.12× — the plan's "within 2×" criterion PASSES.** 43.0 fps / 2.1×
real-time, flags `0x0`→`0x0`. The P4 phase gate itself (live ≥20 Hz front end, ≥200 Hz pose,
<20 ms latency) awaits the GS camera pair.

### 2026-07-30 — live camera → NPU detection PASS (garuda-inference seed)

`rpicam-vid --post-process-file hailo_yolov8_inference.json` (auto-selected
`yolov8m_h10.hef` on HAILO10H): live CM3 stream, YOLOv8m on-NPU, boxes drawn.
Verified detection: **person 85%** on a frontal subject. Delivered 291 frames / 20 s at
1536×864 @15 fps requested ⇒ ≈14.6 fps, no under-rate from inference load (NPU has ~5×
headroom per P1). Findings: the hailo postproc stages run only on the **video** pipeline —
`rpicam-still` loads them but inference never engages ("HailoRT not ready!", no boxes);
a hard scene (inverted monitor, cable clutter) yields zero detections while the pipeline is
healthy — absence of boxes is not evidence of a dead pipeline. Next for `garuda-inference`:
structured detections (class/bbox/conf on the middleware) instead of drawn pixels.

---

## 2026-07-29 — P3 start: first PTP offset numbers (point-to-point, SW-timestamped GM)

Topology: PC (`ptp4l -i eno1 -S -m`, **software timestamps** — NIC has no PHC) as
grandmaster ↔ direct cable ↔ Pi `eth0` (linuxptp 4.2, hardware timestamps,
`--hwts_filter=full`, slave-only, transient unit `garuda-ptp4l-client`).
Harness: `bench/ptp-offset-stats.sh`, 60 s servo settle excluded, then 300 s window.

| Measurement | Value |
|---|---|
| Samples | 304 (1/s sync) |
| Mean offset | **−8.8 ns** |
| RMS offset | **3595 ns (3.60 µs)** |
| Min / Max | −8907 ns / +7644 ns |
| Path delay (steady) | ~20.8 µs |

Caveats (structural, known before measuring):
- GM end is software-timestamped — its jitter dominates; this number is NOT the Pi's
  hardware-PTP capability and does NOT test the sub-µs point-to-point target. That waits
  for a HW-timestamping peer (LAN966x TSN switch EVB or CA90).
- RP1 quirk (symptom→fix, rule 4): RX hardware filter modes are `none|all` only; ptp4l's
  default PTP-specific filter request leaves SYNC unstamped ("received SYNC without
  timestamp"). Fix: `--hwts_filter=full`. Must carry into garuda-time config.

---

## 2026-07-30 — garuda-portal V1 deployed to bench

Versions snapshot: `versions.md` 2026-07-29 Trixie entry (2026-07-30 addendum: python3-opencv,
portal/configd units). `hosts/pi5/install.sh` `[5/5]` step deployed `/opt/garuda/{garuda-portal,
garuda-configd,garuda-inference}` from `services/` (staged via rsync to
`garuda@10.42.0.128:/home/garuda/garuda-sdk-deploy/`), installed
`hosts/pi5/units/garuda-{portal,configd}.service`, and replaced the bench transient unit
`garuda-cam-portal` (same camera, same `:8080`) with `garuda-portal.service`.

### Readiness report (`GET /api/readiness/report`, first run after deploy)

| Check | Status | Evidence |
|---|---|---|
| `npu.identify` | pass | `identify: HAILO10H` |
| `power.flags` | pass | `get_throttled=0x0` |
| `power.supply5a` | warn | supply not verified 5V/5A (bench charger has prior UV strikes) |
| `thermals` | pass | SoC 45.0 C |
| `services.core` | warn | `garuda-inference=down, garuda-cam-portal=down` |
| `storage.space` | pass | 222.1 GB free |
| `bridge.session` | na | no FC endpoint configured |
| `simgate.status` | pass | portal sends no arming commands (by design) |

**Overall: caution** — `services.core` warns because `garuda-inference` is on-demand (not a
persistent unit; started/stopped by `InferenceManager` on request) and the old
`garuda-cam-portal` no longer exists (by design, replaced). `power.supply5a` is the permanent
bench advisory and does not by itself demote overall status per the readiness rule.
`bridge.session` reads `na` even though `bridge.agent_port` was set below — the check keys
on `bridge.agent_ip`, which was not set in this session (correct per `readiness.py` logic,
not a bug).

### E2E checklist (curl from the PC against `http://10.42.0.128:8080`)

| # | Check | Result |
|---|---|---|
| 1 | `GET /` | **200**, body contains all seven `id="panel-*"` (overview, camera, inference, calibration, readiness, settings, system) |
| 2 | `GET /api/health` | **200** — `{"throttled": "0x0", "temp_c": 43.3, "npu": "HAILO10H", "services": {"garuda-inference": false, "garuda-cam-portal": false}, "disk_free_gb": 222.1, "camera_mode": "stream", ...}` |
| 3 | `GET /api/stream` | first 200 bytes contain `--frame` boundary + JPEG magic `ffd8ff` — camera confirmed live (rpicam-vid child under the portal) |
| 4 | `GET /api/models` | **200** — `["resnet_v1_50_h10.hef", "yolov11m_h10.hef", "yolov5n_seg_h10.hef", "yolov8m_h10.hef", "yolov8m_pose_h10.hef", "yolov8s_pose_h10.hef"]` (contains `yolov8m_h10.hef`) |
| 5 | `PUT /api/config {"key":"bridge.agent_port","value":8888}` | `{"ok": true, "detail": "ok", "result": {"bridge.agent_port": 8888}}`; `GET /api/config` confirms `{"bridge.agent_port": 8888}` |
| 6 | `PUT /api/config {"key":"evil.key","value":1}` | `{"ok": false, "detail": "config key not whitelisted: 'evil.key'", "result": null}` |
| 7 | `systemctl is-active garuda-portal garuda-configd` | `active` / `active` |
| 8 | `journalctl -u garuda-configd` audit trail | `ACCEPT {"op":"config.set",...bridge.agent_port...} :: set`, `ACCEPT {"op":"config.get",...} :: get`, `REJECT {"op":"config.set",...evil.key...} :: config key not whitelisted: 'evil.key'` |

**8/8 E2E checks green.** Full command+output transcript:
`.superpowers/sdd/2026-07-30-garuda-portal-v1/task-9-report.md`.

### Idempotency re-run (install.sh run a second time, same session)

Re-ran `hosts/pi5/install.sh` on the Pi unchanged. Result: apt step reported
"Upgrading: 0, Installing: 0, Removing: 0" (opencv/hailo packages already newest), unit
install/`daemon-reload`/`enable --now` produced no errors and **no "Created symlink" lines**
(already enabled), `systemctl show garuda-portal garuda-configd -p ActiveEnterTimestamp` was
**identical before and after** the re-run (`Thu 2026-07-30 14:13:34 BST` both services,
both runs) — proof the re-run converged without restarting either service. `bridge.agent_port`
config set from the E2E pass survived the re-run untouched. `hailortcli fw-control identify`
and `vcgencmd get_throttled` (`0x0`) sanity checks still passed at the tail of the re-run.

Deviations from the task brief: none. `python3-opencv` was already present on the bench
image before this deploy (pulled in earlier as a dependency of `rpicam-apps-opencv-postprocess`
/ tappas packages) — `install.sh` still declares it explicitly in its own apt list per the
brief, and apt correctly reports it "already the newest version" on both runs.
- Single 5-min window, bench idle; no load/thermal stress during capture.

---

## 2026-08-02 — garuda-mask: native Hailo YOLOv5n-seg dynamic-masking service (Task 1, hybrid ORB-SLAM3+YOLO plan)

Versions: kernel `6.18.34+rpt-rpi-2712`, `hailo_platform` 5.1.1 / py 3.13.5, Hailo `HAILO10H` FW 5.1.1,
OpenCV 4.10.0. Model: `/usr/share/hailo-models/yolov5n_seg_h10.hef` (+ `yolov5seg.json`), input
640×640×3 UINT8; outputs conv63 160×160×32 (proto) + 3 det heads 351ch. Probe input: `calib/captures/pair11_L.png`
(1280×800 rectified-left tile). Plan: `docs/superpowers/plans/2026-08-02-hybrid-orbslam3-yolo-masking.md`.

**Unit tests (hardware-free, on-bench, `python3 tests/test_mask.py`):** 5/5 PASS — dynamic-class
mask union/resize/dilate + latest-wins mmap IPC (`MaskIPC`).

**Decode validation (rule 2 — verified, not assumed):** on-CPU YOLOv5-seg decode returns real COCO
classes `['chair','person']` (not garbage), and geometry is correct — the `person` box center
(0.91, 0.32 of frame) matches its assembled mask centroid (0.94, 0.32). No coordinate bug. The probe
image is *adversarial* (a person holding the checkerboard, face/torso occluded): the detector fired
`person` on a background garment and missed the occluded centre human — i.e. the pipeline faithfully
masks what YOLO detects; it does **not** yet prove detection quality on a clean VIO scene.

**Timing (synchronous single-frame, mean of 15 after warmup):**

| Stage | Time | Rate |
|---|---|---|
| NPU infer only (`hailortcli`-equiv, blocking `run()`) | **83.8 ms** | 12 fps |
| CPU decode + NMS + mask assembly | **3.1 ms** | — |
| End-to-end (infer→dynamic mask) | **86.9 ms** | **11.5 fps** |

Exact objectness-gate optimization (gate cells on `obj > score_thr` before per-class sigmoid — loss-free
since `score = obj·cls ≤ obj`) cut end-to-end 125 → 87 ms with **identical** detections. Thermals during
runs: 47–49 °C, `get_throttled=0x0`.

**Red-team (rule 9):**
- The bottleneck is **NPU single-shot latency** (83.8 ms of the 86.9), *not* CPU postproc (3.1 ms). This is
  a 4-context seg model run **synchronously** (one blocking `run()` per frame) — it is NOT the streamed
  throughput number. P1's `yolov8m` hit 76 fps via `hailortcli benchmark` (pipelined). A pipelined/async
  masker should beat 11.5 fps; `TBD-bench`. 11.5 fps is the honest synchronous figure as built today.
- Detection quality on a real walking-person VIO clip is **unproven** (`TBD-bench`) — the adversarial probe
  only validates the decode/geometry/IPC path.
- Licence: `yolov5n-seg` is GPL-3.0 (Ultralytics). BENCH/EVAL only under the 2026-08-02 relaxation; masks
  consumed behind `IFrontEnd`, tagged `not-product-cleared`. Our masker code (`services/garuda-mask/`,
  `hosts/pi5/hailo_yolo_seg.py`) is original.
- The `garuda-depth` service holds the NPU exclusively (`HAILO_OUT_OF_PHYSICAL_DEVICES` if both run) — it was
  stopped for these runs and restarted after; the persistent masker will need depth stopped.

---

## 2026-08-02 — ORB-SLAM3 stereo builds + runs on Pi 5: EuRoC MH_01 go/no-go (Task 2, hybrid plan)

**The go/no-go gate for the whole hybrid.** ORB-SLAM3 stereo built in an aarch64 **Ubuntu-22.04 / GCC-11
container** on the Pi (dodging bare-metal GCC 14 — see decisions.md), headless (`bUseViewer=false`),
benchmarked on EuRoC **MH_01** (3682 stereo pairs, 752×480).

- Image: `garuda/orbslam3:bench` (3.29 GB). ORB-SLAM3 SHA `4452a3c4ab75`. Pangolin v0.6, OpenCV 4.5.4,
  Eigen 3.4 (all in-container). Host: Trixie, kernel 6.18.34, GCC 14.2 (NOT used for the build).
- Dockerfile/build.sh/run_euroc.sh: `hosts/pi5/orbslam3/`. stereo_euroc patched headless + to print
  per-frame tracking time (this ORB-SLAM3 rev collects `vTimesTrack` but never prints it, and wall-clock
  is meaningless — the example `usleep()`s to real-time 20 fps playback).

**Front-end tracking rate (the metric; per-frame `TrackStereo` time, playback-sleep excluded):**

| Measure | Value |
|---|---|
| median tracking time | **41.96 ms → 23.8 fps** |
| mean tracking time | **43.85 ms → 22.8 fps** |
| keyframes (MH_01) | 153 |
| wall clock (incl. vocab load + 20 fps playback sleeps) | 214.3 s (run 2), 237.9 s (run 1) |

**Verdict: PASS the P4 ≥20 Hz front-end bar** — ~22.8 fps tracking, achieved *even while thermally
throttled*. Better than the research forecast (single-digit-to-low-teens for Pi-class feature SLAM); the
Pi 5's 2.4 GHz A76 + modest 752×480 stereo carry it. ORB-SLAM3 stereo is viable on this bench → proceed to
the mask seam (Task 3).

**Red-team (rule 9):**
- **Thermally throttled.** Peak 84.5 °C (near the 85 °C hard limit); `get_throttled` ended `0xe0000`
  = arm-freq-capped + throttled + soft-temp-limit all *occurred* (bit 3 active at peak). **No under-voltage**
  (power OK). So 22.8 fps is a THROTTLED figure — unthrottled is higher, but sustained runs on the passive
  heatsink (CLAUDE.md §2) throttle, so ~22.8 fps is the realistic *sustained* rate. Clearing 20 Hz while
  throttled is the encouraging part.
- **Tracking-thread rate only.** The full P4 gate also wants ≥200 Hz pose + <20 ms latency — NOT met here:
  this is stereo-only (no IMU), so there's no high-rate inertial pose. Stereo-visual pose is frame-rate-bound.
- **EuRoC is ideal** (indoor, well-lit, 752×480, machine-hall). Live OV9281 stereo (different res, real
  conditions) is `TBD-bench`.
- **Accuracy — MEASURED (resolves the TBD).** SE(3)-aligned (Umeyama, no scale — stereo is metric) vs the
  EuRoC vicon groundtruth, 3638/3682 poses associated within 20 ms: **ATE RMSE = 4.66 cm** (mean 3.73 cm,
  median ~3.5 cm, max 15.0 cm) over an 80.5 m loop. Near the ORB-SLAM3 paper's *desktop* MH_01 figure
  (~3–4 cm) — so accuracy holds on the Pi. Note this trajectory run was HARD-throttled (warm start → 86.7 °C,
  ARM clock capped to 1500 MHz, `0xe0006`), i.e. accuracy survived even worst-case thermal conditions.
  Aligner `~/align_ate.py` on the bench; visualized at the trajectory-viewer artifact (2026-08-02).
  Still `TBD-bench`: live OV9281 accuracy (EuRoC is an ideal indoor set).
- Licence: ORB-SLAM3 GPL-3.0, BENCH/EVAL only, behind `IFrontEnd`, not-product-cleared (2026-08-02 relaxation).
- **⚠ MEASUREMENT CONTAMINATION (found post-hoc): `garuda-depth` was running at ~266 % CPU (2.6 cores)
  throughout every ORB-SLAM3 run above.** `camarray_depth_explorer.py` (restarted after Task 1) was doing
  continuous SGBM/point-cloud depth — so ORB-SLAM3's 3 threads shared only ~1.4 free cores of the Pi's 4,
  and the depth load added constant heat that worsened the throttling. **All figures above (22.8 fps, ATE
  4.66 cm, 86.7 °C) are therefore PESSIMISTIC** — clean (depth stopped, cooled) ORB-SLAM3 stereo will be
  faster and cooler. Verdict only strengthens: PASS was achieved CPU-starved + throttled. Depth stopped
  2026-08-02; a clean uncontaminated re-run is `TBD-bench`.

---

## 2026-08-02 — Task 3: clean-room dynamic-mask seam wired into ORB-SLAM3 (hybrid join proven)

The NPU masker (Task 1) → ORB-SLAM3 extractor (Task 2) join. Clean-room seam
(`hosts/pi5/orbslam3/patches/orbextractor_mask.py`) revives ORB-SLAM3's vestigial `_mask` param and
drops keypoints whose original-res position (`pt * scaleFactor[level]`) falls in a dynamic region,
before orientation/descriptors. Baked into the Dockerfile; verified with `feature_mask_demo`.

- **Proof (feature_mask_demo on `pair11_L`, fed the live Hailo `yolov5n-seg` dynamic mask):**
  `unmasked=1203` keypoints → `masked=1129` → **74 dropped** — exactly the keypoints inside the masked
  region (mask coverage 4.6 % + 12 px dilation). Before/after visualized (mask-seam artifact).
- End-to-end path confirmed: **Hailo YOLOv5-seg (NPU) → dilated dynamic mask → ORB extractor rejects
  keypoints there → clean features to tracking.** The NPU does masking only; CPU does the SLAM.
- **Red-team:** the demo image is adversarial — the masker tagged a background garment as "person"
  (not the checkerboard-occluded human), a Task-1 *detection* quirk. The *seam* is exact regardless (drops
  wherever mask>0). A full masked-vs-unmasked *trajectory/ATE* delta needs a real dynamic clip (moving
  person crossing a mapped scene) → `TBD-bench` (best captured live with the OV9281 pair, Task 4).
- Licence: ORB-SLAM3 GPL-3.0 + YOLOv5 GPL-3.0, BENCH/EVAL, behind `IFrontEnd`, not-product-cleared.

---

## 2026-08-03 — Live SLAM on OV9281 CamArray: root-caused to POOR STEREO APPEARANCE (not software)

Task 4 live attempt: recorded live stereo clips (selfie + room-facing, 87 & 275 frames), rectified via
proven `stereo_rig` maps, ran ORB-SLAM3. **It never tracks — only ~25 stereo map points per frame.**
Instrumented `Frame::ComputeStereoMatches` (counters on the match funnel) to pin it definitively:

```
N≈1206 left kp → rowOK≈1202 → maxU≈1202 → descPass≈40 → final≈20
```

- **Rectification is FINE:** rowOK≈1202 (right kp present on the same row band); best descriptor matches
  sit at **dy≈0** at every vertical search band. Not a calibration/vertical-alignment problem.
- **The collapse is descriptor/appearance matching:** only ~40/1200 keypoints pass the ORB Hamming
  threshold; **median best same-row Hamming ≈ 100/256 (near-random 128)**. Even a ±60-row search finds
  only 251/1500 good matches. SGBM density is only **28.9%** (vs 76% on earlier close high-contrast
  captures). Both descriptor AND intensity stereo matching fail → the two cameras produce poorly-
  correlated local image appearance.
- **Optics differ:** left image is **~20% sharper** than right (Laplacian-variance ratio 1.1–1.2 across
  frames) — a focus/lens mismatch. CLAHE/histogram-matching and wider vertical search do NOT recover it.

**Conclusion: the OV9281 CamArray is not a good stereo-SLAM pair** (geometric calib is fine, RMS 1.26px,
but photometric/appearance correspondence is too poor for dense stereo matching). This matches CLAUDE.md
§2: the OV9281 CamArray is earmarked "inference/tracking/VLM dev only"; the **IMX296 GS pair (sourcing) is
"the ONLY VIO-grade cameras."** Live stereo SLAM was always intended for the IMX296, not this quad.

**Software is proven & ready** (EuRoC 22.8 fps / ATE 4.66 cm; masker; seam; live tooling all work) —
re-run live on the IMX296 pair when it arrives. Possible interim: refocus the right lens and re-test.

**FOLLOW-UP (same day): refocus tested, does NOT fix it.** Built `hosts/pi5/camarray_focus.py` (live
sharpness meter). Owner manually focused both lenses — sharpness went **118/99 (mismatched) → ~600/~580
(both sharp AND matched)**, confirmed via `hosts/pi5/check_stereo_match.py`. **But stereo descriptor
matching was UNCHANGED: descPass ≈25/1200, median best-Hamming ≈101 (near-random).** Denoising (Gaussian
3/5, NLmeans) doesn't help either. So the OV9281 pair's poor correspondence is **NOT** focus, photometry,
noise, vertical alignment, L/R order, or config — it's fundamental to the hardware (mismatched cheap
optics/sensors). **Definitive: the OV9281 CamArray cannot do stereo SLAM; the IMX296 GS pair is the path.**
Silver lining: the better/matched focus helps the OV9281's actual jobs (depth/tracking/inference).

> **⚠️ 2026-08-03 — THIS "HARDWARE" CONCLUSION IS RETRACTED. See correction entry below. The OV9281
> stereo failure is a CALIBRATION + L/R-swap bug in our setup, NOT a sensor limit. The prior measurement
> only checked descriptor matching UNDER the (broken) rectification, so it read "random" — the assumed-good
> rectification was itself the bug.**

---

## 2026-08-03 — CORRECTION: OV9281 stereo failure is CALIBRATION, not hardware (root-cause redone)

Owner pushed back ("not convinced IMX improves tracking — must be something in the implementation"). Redid
the root-cause with controlled tests (scripts in scratchpad: `stereo_corr_battery.py`, `dydx_diag.py`,
`recover_pose.py`; copies on bench `~/`). Clean bench: `garuda-depth` off, no throttle. **The earlier
"near-random descriptors / hardware" verdict was WRONG.** Evidence:

- **Our pipeline is correct.** Identical stereo-correspondence funnel on EuRoC (control) = 765/1000 good
  matches, median Hamming 27, disparity +7 px — healthy. And OUR `rectify_clip.py` stored maps produce
  **bit-identical** results to an independent `cv2.stereoRectify` → our rectification code is not the bug.
- **The OV9281 pair IS valid stereo.** Free descriptor matching (BFMatcher crossCheck, no epipolar
  constraint) on OV9281 cam0↔cam1: **~900 matches, median Hamming 26** (≈ EuRoC's 23), and **80% fit a
  single fundamental matrix** (543/679 RANSAC inliers). Random/incompatible images cannot do that. The
  descriptors correspond and one rigid two-view geometry explains the pair.
- **The stored calibration mis-rectifies it.** With `camarray_stereo.yaml` (R,T), true correspondences land
  **113 px off their epipolar rows** (frac|dy|<2 = 0.00) at **negative disparity** — so ORB-SLAM3's same-row
  stereo search rejects ~all of them → "Fail to track." The earlier `check_stereo_match.py` measured
  Hamming *under this broken rectification* (comparing wrong points on the same row) → the misleading ~100
  "near-random" reading.
- **Correct geometry fixes it.** Recovering the true relative pose from the matches (essential matrix,
  542 inliers) and rectifying from THAT drops median |dy| **113 px → 1.3 px** (frac|dy|<2: 0.00 → 0.65).
  Recovered baseline dir/rotation differ from the stored calib (rot 7.5° vs ~1.3°), and disparity is
  negative → **the pair is also L/R-swapped** (cf. the existing `garuda_stereo_swap.yaml`/`room1_swap`).
- **Verdict:** OV9281 stereo is blocked by (a) a wrong/mismatched stereo calibration (`rms_stereo` was 1.26
  px — already a smell) and (b) L/R tile-order swap. **FIXABLE in software** — recalibrate the actual
  recorded pair with correct L/R order, verify |dy|≈0 after rectification, re-run ORB-SLAM3. **IMX296 is NOT
  required for stereo to work** (it remains the better VIO sensor, but the current wall is our setup).
- **END-TO-END CONFIRMED (same day):** rebuilt room1 with extrinsics recovered from the images (pooled
  essential matrix over the clip, 3894 inliers) + corrected L/R order (`~/build_corrected_clip.py` →
  `euroc_live/room1_fixed` + `cam.yaml`), then ran `stereo_euroc`. **Result: `Map 0 has 21 KFs`** — vs
  **1 KF** (never initialised) on every wrong-calib run. ORB-SLAM3 now initialises and maps the OV9281 pair.
  Tracking still drops on 43/87 frames ("Less than 15 matches") because the image-recovered rectification is
  loose (median |dy| 8.4 px, not sub-pixel; pooled essential-matrix E-inlier rate only 32%, hinting the two
  cams may not be perfectly rigid frame-to-frame → possible lack of hardware sync). 15.97 fps @1280×800
  (consistent with the pixel sweep). **This proves OV9281 stereo SLAM works once geometry is right (1→21
  KFs by fixing ONLY calib+swap).** Durable fix = proper checkerboard recalibration with correct L/R order
  and good coverage → sub-pixel rectification → continuous tracking (`TBD-bench`). If residual looseness is
  desync, that's the one place a hardware-synced pair (IMX296 external trigger) genuinely helps.
- **RECALIBRATION ATTEMPTED (same day) — existing checkerboard captures are UNUSABLE.** Found the captures
  (`calib/captures/pair*_{L,R}.png`, 80 pairs, 68 both-detected 9×6). Re-ran the project `stereo_calibrate.py`
  → reproduces stored calib exactly (mono RMS 1.17/1.26, stereo 1.26 px). BUT that calibration **does not
  rectify its own captures**: median checkerboard-corner |dy| after rectification = **126 px** (should be ~0),
  via both the stored R1/R2/P1/P2 and a fresh `stereoRectify(R,T)`. Low reported reproj-RMS + non-rectifying
  extrinsics = the pipeline converged to a self-consistent-but-wrong solution (its iterative outlier drop from
  68→51 pairs hid it). A clean-room `stereoCalibrate` on all 68 pairs (bypassing the script) gives **stereo
  RMS 29.7 px** and a garbage baseline (169 mm, huge Z) → **the L/R corner correspondences are fundamentally
  inconsistent** (mispaired captures, or L/R not simultaneous). Corner first-row-direction was consistent
  (0/68 flipped), so it's not a simple 180° flip. **Conclusion: recalibration from existing data is
  impossible — needs a fresh, well-diversified checkerboard shoot with verified-simultaneous L/R.**
- **BUT room1's own geometry is valid and rigid.** Per-frame essential-matrix recovery over room1 is stable
  (inter-cam rotation 7.9° ± 0.4°, low spread → NOT desync; the pair has a fixed real ~7.9° rotation the
  checkerboard calib wrongly reported as 1.7°). So **scene/self-calibration is the working path** (already
  proved: 21 KFs). Options forward: (a) bundle-adjust the room1-recovered extrinsics to sub-pixel → clean
  ORB-SLAM3 track without any checkerboard; (b) re-shoot a proper checkerboard calibration. Sensor is fine.

## 2026-08-04 — scene self-calibration of OV9281 room1 + the true ceiling (sync, not sensor/intrinsics)

Owner picked scene self-calibration. `~/self_calib.py` (scratchpad copy): pooled **21,941** stereo
correspondences over 43 room1 frames, estimated one essential matrix, refined R,t by numpy Gauss-Newton on
Sampson error, auto-fixed the L/R swap, rebuilt `euroc_live/room1_selfcal` + yaml. Clean run (garuda-depth
stopped, `0x0`). Result:

- Recovered inter-cam rotation **7.55°** (checkerboard calib wrongly said 1.7°), median stereo |dy| **3.0 px**
  (down from 113 px with the broken calib). **ORB-SLAM3: `Map 0 has 25 KFs`** (was 1 KF broken; 21 KFs with
  the loose image-recovered version), 28/87 frames drop, 1 map reset. 15.9 fps @1280×800. So: **maps and
  tracks intermittently — a big step from dead, but not yet clean continuous tracking.**
- **GN refinement did not reduce the residual** (Sampson RMS 3.3e-3 → 3.3e-3) → the extrinsics are already
  optimal; the ~3 px is NOT a pose error.
- **Ceiling attribution (perframe_vs_global.py):** per-frame OWN-pose rectification reaches **0–1 px** on good
  frames (frame 26: 0.0 px, frame 16: 1.0 px) → **the intrinsics ARE capable of sub-pixel rectification, so
  they are not the limiter.** But a single GLOBAL pose plateaus at ~3 px, and per-frame recovered rotation
  varies ±0.4° (≈ several px). Net: the wall on a single fixed calibration is **per-frame geometry variation**
  — most consistent with **mild desync** (OV9281 CamArray L/R not tightly triggered → during motion the pair
  is captured at slightly different instants, so effective stereo geometry drifts frame-to-frame). Caveat:
  own-pose partly overfits its own points; a **static-scene capture** would confirm desync definitively
  (if still ~3 px static → intrinsics; if it tightens → desync).
- **Corrected full picture:** (1) the dominant failure was a grossly BROKEN calibration (extrinsics + swap) —
  fixing it took ORB-SLAM3 from 1 → 25 KFs; owner's "it's the implementation" was right. (2) Descriptors and
  intrinsics are fine (sub-pixel achievable). (3) The remaining ceiling to CLEAN continuous tracking is
  capture **synchronization** — and THAT is the specific, legitimate reason a hardware-triggered GS pair
  (IMX296 + XTR trigger) is needed for production VIO. NOT "cheap optics / random descriptors" (that verdict
  was wrong). Durable path: synced IMX296 pair + a proper checkerboard calibration → EuRoC-class (<1 px) →
  clean tracking. `TBD-bench`: static-scene desync confirmation; IMX296 live when it arrives.

> **⚠️ 2026-08-04 LATER — THE "DESYNC CONFIRMED" CONCLUSION BELOW IS RETRACTED.** A follow-up motion-scaling
> test (`~/motion_corr.py`) refutes desync: stereo |dy| does NOT scale with camera motion speed
> (corr r = −0.03), the slowest-third frames are actually WORSE (8.2 px) than the fastest-third (3.3 px), and
> the fit intercept is 5.1 px — nowhere near the static 0.24 px floor. Desync predicts the opposite (dy ∝ speed,
> intercept ≈ static floor). So the static-vs-one-moving-clip comparison was NOT valid proof of desync; the
> static 0.24 px is a narrow single-viewpoint case (self-cal pose fit+evaluated on ~identical frames), and
> room1's ~3–8 px misfit is viewpoint/calibration-dependent, NOT motion-induced. **We CANNOT conclude a
> sensor/sync issue. Most likely: no good stereo calibration exists yet (checkerboard set broken; scene
> self-cal from room1 too ill-conditioned to pin the fixed rig geometry). Next: a proper fresh checkerboard
> calibration is required before any sensor/sync claim.** Owner flagged the over-reach; correct call.

### 2026-08-04 — static-scene desync test: CONFIRMED (the OV9281 ceiling is sync, not the sensor) [RETRACTED — see note above]

Captured 25 stereo pairs from the STATIONARY OV9281 (`~/static_capture.py` → `euroc_live/static1`,
garuda-depth stopped) and compared per-frame geometry stability + rectified |dy| vs the moving room1 clip
(`~/static_analysis.py`, both scratchpad copies):

| clip | scene motion | inter-cam rotation | rectified \|dy\| (single global calib) |
|---|---|---|---|
| **static** | 7.8 gray/frame | **2.36° ± 0.33°** | **0.24 px** |
| moving (room1) | 11.2 gray/frame | 7.73° ± 0.70° | 2.99 px |

- **On a static scene the OV9281 pair rectifies to 0.24 px — sub-pixel, EuRoC-class.** The ~3 px wall appears
  ONLY under motion. **Definitive: the tracking ceiling is motion-induced desync** (L/R captured at slightly
  different instants; during motion that injects ego-parallax the fixed rectification can't track).
- **Tell:** the recovered "inter-camera rotation" itself inflates 2.36° (static) → 7.73° (moving) — that extra
  ~5° is ego-rotation between the two unsynchronized grabs. So room1's self-cal 7.55° was motion-contaminated;
  the true rig rotation is ~2.4°. (Also why the checkerboard calib's ~1.7° was in the right ballpark yet
  still non-rectifying — its captures had their own pairing/quality problems.)
- **FINAL, COMPLETE picture of the whole OV9281-stereo saga:** (1) the sensor/optics are excellent — static
  rectification 0.24 px, descriptors match at Hamming ~26; the original "cheap optics / random descriptors /
  hardware wall" verdict was fully WRONG and is retracted. (2) The calibration was genuinely broken (extrinsics
  + swap) → fixing it took ORB-SLAM3 1 → 25 KFs. (3) The one remaining, real limit is **capture
  synchronization** — proven by the static test. **This is the exact, specific engineering reason the product
  needs a hardware-triggered global-shutter pair (IMX296 + 1.8 V XTR trigger): not image quality, but
  simultaneity.** For static/slow scenes the OV9281 is already sub-pixel. Software desync compensation is
  possible in principle (know δt + IMU) but hardware sync is the clean fix.
- **P4/VIO implication:** the IMX296 GS pair remains the product path — now for the correct reason (sync), and
  with confidence it will work (a synced, well-calibrated pair rectifies like the static 0.24 px → EuRoC-class
  → clean tracking). OV9281 CamArray = fine for its assigned jobs (detection/tracking/depth/VLM) and for
  static/slow stereo, not for dynamic stereo VIO.

### 2026-08-04 — DEFINITIVE (controlled still-then-move clip): calibration was the blocker; OV9281 tracks clean

Owner flagged both prior over-swings ("desync confirmed" and "desync refuted") and asked for a controlled
motion test. Captured ONE clip, camera still then moved, same scene (`euroc_live/move1`, 207 pairs @5 fps,
owner did the motion). Classified every frame by measured inter-frame motion; fit stereo geometry from the
STILL frames only (desync-clean); measured rectification |dy| per motion bin (`~/move_analysis.py`); rebuilt
the clip with that still-fit calibration and ran ORB-SLAM3 (`~/build_move.py`). Scratchpad copies of both.
**This supersedes the room1 numbers and BOTH 2026-08-04 desync claims above.**

- **Still-fit rig geometry 2.41°** (matches the 2.36° static test; NOT room1's motion-contaminated 7.55°).
- **|dy| vs motion (same scene, same calib):** still 0.00 px → slow 1.20 → med 1.58 → fast(23.6px/frame)
  **1.86 px**; `dy ≈ 0.108·motion`, r=0.61, intercept ≈ 0. **Real desync exists (~10–16 ms L/R offset) but is
  SMALL — ≤~2 px even at fast handheld motion, inside ORB-SLAM3's scale-dependent stereo band.**
- **ORB-SLAM3 on the still-fit clip: 2/207 fail-to-track (~1 %), 17 KFs — clean continuous tracking** (2 early
  resets = the 88 opening still frames, no parallax). vs room1's motion-contaminated calib: 28/87 (~32 %).
  **The calibration was the blocker, full stop.**
- **FINAL verified conclusion (retracts every earlier verdict):** (1) OV9281 sensor/optics fine — descriptors
  match, still rectification 0.00 px. (2) The whole failure was a **broken/contaminated stereo calibration**
  (checkerboard set unusable; self-cal MUST be fit from STILL frames — moving frames poison the geometry).
  Correct calib → **OV9281 does dynamic stereo SLAM at ~1 % frame loss.** (3) Small real desync (~10–16 ms,
  ≤2 px) is a **precision refinement**, not a blocker; IMX296 + XTR trigger removes it for best accuracy but
  is NOT required for working tracking. **Owner's original instinct — "implementation, not the sensor; IMX296
  isn't the fix" — was correct.** Prior "hardware wall / random descriptors" AND my "must-have sync" verdicts
  are both wrong/retracted.
- **Method note (future OV9281 self-cal):** fit extrinsics from STILL frames only — fitting from a moving clip
  inflates recovered inter-cam rotation by ego-motion (2.4° → 7.5°) and wrecks rectification.
- `TBD-bench`: ATE on a self-cal OV9281 run (needs groundtruth); IMX296 live (now expected to just work).

- Rule-9 note: this is exactly the failure rule 9 guards against — an assumed-correct component (rectification)
  was the bug, and measuring "through" it produced a confident-but-wrong "hardware" verdict.

---

## 2026-08-03 — ORB-SLAM3 stereo, 2nd public dataset: TUM-VI room1 (fisheye) + cross-dataset viewer

Second public-dataset validation of the same `garuda/orbslam3:bench` stereo binary, on a **harder** set:
TUM-VI **room1** (`dataset-room1_512_16`, 2821 stereo pairs, **512×512 fisheye — KannalaBrandt8**, handheld,
**no IMU used** — pure stereo). Runner `~/run_tumvi.sh` on the bench stops `garuda-depth` first, so this is a
**depth-stopped run** (unlike the contaminated EuRoC runs above). Model `stereo_tum_vi` patched headless
(`System::STEREO,false`); already prints median/mean track time. Config path `Examples/Stereo/TUM-VI.yaml`.

- **Config bug fixed (upstream ORB-SLAM3):** shipped `Examples/Stereo/TUM-VI.yaml` writes
  `Camera.overlappingBegin/End` where the settings loader requires `Camera1.overlappingBegin/End`
  (the Stereo-Inertial variant has it right) → `stereo_tum_vi` aborted with "required parameter does not
  exist". Fixed the prefix (`s/^Camera.overlapping/Camera1.overlapping/`) and committed into the bench image.

**Front-end tracking rate** (per-frame `TrackStereo`, playback-sleep excluded):

| metric | value |
|---|---|
| median tracking time | **52.42 ms → 19.1 fps** |
| mean tracking time | **52.37 ms → 19.1 fps** |
| keyframes | 178 KFs, 1 map (no track loss — all 2821 frames tracked) |

Slower than EuRoC's 22.8 fps as expected: fisheye (KannalaBrandt8) unprojection is costlier than pinhole.
**Still clears the P4 ≥20 Hz bar? — NO, 19.1 < 20 Hz on this handheld fisheye set.** EuRoC (22.8) clears it;
TUM-VI fisheye sits just under. Honest read: front-end rate is camera-model- and scene-dependent; the GS
IMX296 pair (global-shutter pinhole, the actual product camera) is closer to the EuRoC regime than the
fisheye. Recorded as a data point, not a gate pass/fail.

- **Accuracy — MEASURED.** SE(3)-aligned (Umeyama, no scale) vs TUM-VI **mocap0** groundtruth,
  2773/2821 poses associated within 20 ms: **ATE RMSE = 7.79 cm** (mean 7.59 cm, max 14.01 cm) over a
  **146.4 m** handheld trajectory. `datasets/euroc_ate.py` used unchanged (TUM-VI mocap0 = same ns +
  first-4-column layout as EuRoC GT; est/GT timestamps both in ns and aligned — verified before trusting).
- **Red-team (rule 9):** 7.79 cm is *pure-stereo, no-IMU* on fisheye. The ORB-SLAM3 paper's room1 numbers
  are **stereo-INERTIAL** (~cm) — NOT comparable; IMU tightly constrains scale/rotation that pure stereo
  must recover visually. So 7.79 cm is a fair pure-stereo figure, not a regression vs the paper. Larger
  than EuRoC's 4.66 cm because: (a) handheld = faster/shakier motion than the EuRoC MAV, (b) fisheye
  periphery is lower-resolution per solid-angle, (c) no inertial aid. Thermals/`get_throttled` **not
  captured for this run** → not claimed.
- **Cross-dataset viewer built** (user request "make a way to view the data set and the slam output on a
  page"): interactive 3D orbit trajectory (est coloured by per-pose error vs dashed groundtruth), readout
  panel (ATE/fps/KFs/pathlen), and cam0 sample frames — EuRoC MH_01 + TUM-VI room1, dataset toggle.
  Self-contained HTML Artifact; all figures pulled from measured runs. Builder scripts in scratchpad
  (`make_traj_json.py`, frame sampler) — trajectory JSON is regenerable from `f_*.txt` + GT via
  `datasets/euroc_ate.py`'s alignment.
- Licence unchanged: ORB-SLAM3 GPL-3.0, BENCH/EVAL only, behind `IFrontEnd`, not-product-cleared.

---

## 2026-08-03 — pixel-density → ORB-SLAM3 front-end cost sweep (OV9281, our camera)

Answering "how much do our extra pixels cost?" Public sets are LOW-res on purpose (EuRoC 0.36 MP,
TUM-VI 0.26 MP); our OV9281 is 1.02 MP/tile (2.8×/3.9× their pixels), IMX296 1.58 MP (4.4×/6.0×). Ran the
same rectified OV9281 clip (`euroc_live/room1_rect`, 87 pairs, 1280×800) through the bench `stereo_euroc` at
3 scales, **`ORBextractor.nFeatures` fixed at 1200** to isolate the per-pixel extraction/pyramid cost from
the fixed descriptor/match cost. Runner `~/ov_sweep.sh` (scales images + intrinsics, keeps physical
baseline). **Clean run: `garuda-depth` off, 58.7 → 62.6 °C, `get_throttled=0x0` throughout — no
contamination, no throttle.**

| scale | resolution | MP | median track ms | front-end fps |
|---|---|---|---|---|
| 1.00 | 1280×800 | 1.024 | **60.88** | **16.2** |
| 0.75 | 960×600 | 0.576 | 39.91 | 24.2 |
| 0.50 | 640×400 | 0.256 | 26.87 | 35.7 |

- **4× the pixels (0.256 → 1.024 MP) = 2.27× the front-end time** (35.7 → 16.2 fps). Sub-linear because a
  fixed ~15 ms/frame (1200-feature descriptors + stereo-match attempts + per-frame overhead) doesn't scale
  with pixels; only the pyramid+FAST extraction does.
- **Linear fit (this Pi, A76, nFeatures=1200, no BA):** `front-end median ms ≈ 15.1 + 44.4 × MP`
  (fixed 15 ms + 44 ms/MP). Predicts OV9281-full 16.5 fps (measured 16.2 ✓), and **IMX296-full 1.58 MP →
  ~11.7 fps** — i.e. running the product camera at native res would sit well under 20 Hz. **Argues to
  downscale IMX296 toward the ~0.3–0.5 MP EuRoC/TUM-VI regime** (keep global shutter + sync, shed pixels).
- **⚠ These fps are extraction+match ONLY — tracking never converges** ("Fail to track local map!" on all 87
  frames × every scale; `Map 0 has 1 KF`), so local-map/BA cost is absent. On a sequence that *tracks* add
  BA overhead → real fps lower (cf. EuRoC 0.36 MP tracked at 22.8 fps *with* BA vs the model's ~32 fps
  front-end-only at that pixel count; the gap ≈ the BA cost). So the model is a front-end floor on cost.
- **Bonus finding (reconfirms `dafdb70`):** tracking fails identically at 640×400, 960×600, 1280×800 —
  **downscaling does NOT rescue the OV9281's near-random stereo descriptor matching. Resolution-independent
  → hardware, as root-caused. IMX296 GS pair remains the only stereo-SLAM path.**
- Scripts: `~/ov_sweep.sh` on bench (scratchpad copy `ov_sweep.sh`); yaml `hosts/pi5/orbslam3/garuda_rect.yaml`.

## 2026-08-04 — S1 garuda-track: live detect + track + click-to-lock on the CM3 (perception core)

`services/garuda-track`: CM3 IMX708 → Hailo YOLOv8m (reuses garuda-inference's GStreamer pipeline) →
vendored ByteTrack (MIT) → lock FSM → `TrackedObjects` mmap IPC, plus a click-to-lock overlay (:8092 MJPEG).
Built subagent-driven (Tasks 1–5, pure logic, each spec+quality reviewed) + controller-led bench integration
(Tasks 6–8). Plan/spec: `docs/superpowers/{plans,specs}/2026-08-04-garuda-track-*`.

Measured on this Pi, garuda-depth + portal stopped (single-tenant camera/NPU), headless (`--view-port 0`):

| metric | value |
|---|---|
| front-end fps (capture→detect→track) | **median 29.6** (samples 28.3–29.8) |
| process CPU (1 core) | median 69 %, peak 70 % |
| SoC temp peak | 51.6 °C |
| `vcgencmd get_throttled` | **0x0** (no throttle) |

- 29.6 fps is the camera→detect→track rate; the NPU running yolov8m alone is 76 fps (P1), so the front end is
  bound by capture + GStreamer + tracking, not the NPU. Real Hailo labels (person/chair/backpack) via
  `get_label()`. With the :8092 overlay+click view on, ~29.5 fps (overlay/JPEG cost negligible).
- **Click-to-lock validated live:** clicking a detected target → `LOCKED(id)`; unlock → `SEARCHING`. The
  `TrackedObjects` IPC is readable by a separate consumer (the seam S2/distance + S4/follow will plug into).
- Single-tenant camera/NPU: `hosts/pi5/run_track.sh` stops garuda-depth + portal first (idempotent).
- Licence-clean: ByteTrack (MIT, vendored), OpenCV (Apache-2.0), Hailo (LGPL-dyn) — no GPL.
- Harness: `hosts/pi5/track_bench.py`. Scope note: this is S1 (detection+track+lock); distance (S2), obstacle
  sectors (S3), follow/avoid control (S4) are separate sub-projects, not measured here.

## 2026-08-04 — Depth-panel CPU spike diagnosed + fixed (opt-in panel + depth fps cap)

Symptom (user): "the moment I lock a target CPU shoots to 90%"; "even the NPU-based distance
measurement spikes CPU to 90%; object tracking alone when locked is 30%." Root-caused live (top -bn1,
ss, /api/current) — NOT the lock. Two independent causes:

1. **Auto-loaded SGBM depth panel.** The portal was auto-embedding the garuda-depth `/stream` (:8097)
   in the tracking view. garuda-depth computes only while a viewer is connected; that one browser
   viewer pinned **SGBM at ~190% CPU (2 cores)** on top of detection. Verified: exactly 1 ESTAB
   connection to :8097 (the browser) ↔ garuda-depth at 190%.
2. **No fps cap on the depth loop.** Every engine — NPU included — rectifies + colorizes + JPEG-encodes
   a full depth map per frame, all CPU, and the loop ran flat-out. The NPU only shortcuts `infer()`.

Measured on this Pi (1 :8097 viewer + CM3 tracking running):

| state | garuda-depth CPU | system load |
|---|---|---|
| SGBM (CPU), flat-out | ~190 % (2 cores) | ~5.8 |
| garuda-inference (tracking) alone, locked | ~110 % (1 core ≈ 30 % of 4) | — |
| **fast_depth (NPU) @ 6 fps cap** | **40 % (0.4 core)** | **1.79** |

- fast_depth NPU infer capability is **126 fps** (meter); a distance readout needs a few fps, so the
  uncapped rectify/colorize/encode wrapper was the hog. Cap → 0.4 core.
- SGBM is genuinely compute-bound at ~6 fps end-to-end (rectify+disparity+colorize+encode of a 640×400
  map from a 5120-wide GREY capture), so the fps cap is a no-op for it — SGBM stays ~2 cores. Use an NPU
  engine, not SGBM, for live depth alongside tracking.
- Red-team: `vcgencmd get_throttled` read **0xe0000** after the overload — sticky bits 17-19
  (freq-cap / throttle / soft-temp-limit *have occurred*), low bits 0x0 (not now), bit 16 clear (no
  under-voltage ever). So the passively-cooled Pi *did* throttle under the ~5.8 overload — the very
  condition removed here. Post-fix idle 65.9 °C.

Fixes shipped (deployed to bench + repo):
- `services/garuda-portal/static/{index.html,app.js,style.css}`: depth panel is **opt-in, off by
  default** (Off / SGBM·CPU / StereoNet·NPU / fast_depth·NPU buttons). Tracking/locking alone no longer
  starts any depth compute; leaving inference forces the panel off so no viewer leaks.
- `hosts/pi5/camarray_depth_explorer.py`: `DEPTH_FPS_CAP` (default 6, `GARUDA_DEPTH_FPS` env) throttles
  the whole compute+encode chain.

Not yet solved (needs P0): per-*target* distance. garuda-depth reads the OV9281 stereo pair and reports
center-of-frame distance; it is not calibrated to the CM3 that does the tracking, so it cannot yet give
the tracked object's distance. Needs the CM3↔OV9281 extrinsic calibration on a rigid mount (deferred).

## 2026-08-04 — S2 stereo target-range (Option B): metric distance of the locked target

Feature: detect + single-target lock + range entirely in `garuda-depth` on the OV9281 stereo pair
(yolov8m on the rectified LEFT → best instance of the locked class → bbox-ROI disparity → Z=f·B/d),
surfaced in the portal "Target Range" tab (click-to-lock + badged metric distance). Plan/spec:
`docs/superpowers/{plans,specs}/2026-08-04-stereo-target-range*`. NPU decision: `docs/decisions.md`.

NPU findings (Task-1 spike, this Pi, HailoRT 5.1.1):
- yolov8m_h10 solo **36.2 fps**; NMS output parses to a per-class list.
- **Cross-process NPU sharing FAILS** (`HAILO_OUT_OF_PHYSICAL_DEVICES`); the multi-process service
  daemon is not packaged → chose Option B (single process). **Intra-process** sharing works:
  fast_depth (NPU depth) **115 fps** + range concurrent on the shared vdevice, no wedge.

Measured (`hosts/pi5/range_bench.py`, office chair at an UNMEASURED distance — precision only):

| metric | value |
|---|---|
| hit rate (valid readings) @ conf 0.3 | **48/48 = 100 %** |
| distance median / min / max | 1.648 / 1.426 / 1.734 m |
| distance std (precision) | **0.103 m** (~6 % at 1.65 m) |
| garuda-depth CPU (range active) | **~0.70 core** (idle when cleared) |
| SoC temp | 60.9 °C |
| `vcgencmd get_throttled` | 0xe0000 — sticky freq/throttle/soft-temp bits from an earlier overload; low bits **0x0** (not throttling now), bit 16 clear (no under-voltage) |

- **Accuracy vs ground truth = TBD-bench** — needs a target at a tape-measured distance (the run below).
- Grayscale OV9281 lowers yolov8m confidence (a chair sat ~0.40–0.53) → conf floor set to 0.3 for a
  steady lock; a 1.5 s UI hold smooths residual flicker.
- Red-team (rule 9): the 0.103 m spread is dominated by the chair's large, soft bbox (ROI disparity
  varies as the box breathes) and by there being **2** overlapping chair detections; a compact,
  well-separated target should tighten it. The distance is not yet ground-truthed — do NOT treat the
  ~1.65 m as validated until the tape-measure run lands here.

## 2026-08-07 — YOLO26-depth metric monocular depth on Hailo-10H (garuda-mono)

- Built `yolo26n-depth.hef` for hailo10h on the x86 bench PC (Ultralytics 8.4.115 `format=hailo`,
  DFC 5.3.0 from AI SW Suite 2026-04; compile 13m48s CPU-only). First YOLO26-depth HEF on this bench.
- Pi self-test (`hailo_yolo26_depth.py`, CM3 still frame 1280x720): output 192x192 metric map,
  **30 ms/inference**; room scene read min 2.19 m / med 2.62 m / max 3.37 m — plausible scale,
  NOT ground-truthed (tape-measure run = TBD-bench).
- garuda-mono with YOLO26 detect (every frame) + YOLO26-depth (every 3rd frame):
  **14.5 fps distinct processed frames over 12 s** = camera-limited (CAM_FPS=15) — the loop keeps up.
  CPU ~4% total, temp 63.7 °C, no throttle.
- Caveats (rule 9): HEF calibrated on only 4 auto-downloaded images at DFC optimization_level=1
  (QAT finetune + level-2 algos OOM-killed a 14 GB x86 box; disabled — see decisions.md).
  Quantization accuracy is therefore a lower bound; production build needs ~1024 representative
  calib images and a bigger-RAM/GPU box. Metric accuracy vs tape = TBD-bench.

## 2026-08-07 (evening) — yolo26m-depth PRODUCTION HEF (1024-img calib, level-2 PTQ) — probe gate PASS

- Built `yolo26m-depth.hef` (31.9 MB, 768x768 in, 192x192 out) on the x86 PC with the GPU restored
  (driver 580.173.02): DFC optimization_level=2, a16 outputs, 1024 calibration images (256 live CM3
  frames + 768 SUN RGB-D val). QAT finetune DISABLED — GPU OOM at batch 8/4/2 on the 6 GB RTX 3060
  (decisions.md); PTQ-only. Layer Noise Analysis stats skipped (GPU OOM, warning only). Wall time
  ~40 min end-to-end, ~26 min of it allocator/compile (log timestamps 17:04 LNA -> 17:33 HEF).
- Probe gate (collapsed-HEF check), on-Pi standalone run on a live CM3 bench frame (cm3_0150.jpg):
  depth min 0.96 / med 1.28 / max 2.80 m, **logit std 0.263** vs the ~0.04 collapse signature — PASS.
- Deployed: HEF -> Pi `~/garuda-sdk-deploy/models/yolo26m-depth_hailo_model/`, `Y26D_HEF` switched,
  drop-in `GARUDA_MONO_DEPTH=y26d`, cal reset, service active.
- Red-team (rule 9): the probe frame comes from the same static bench scene as 256 of the 1024
  calib images — the spread could flatter the calib distribution. Move-test on unseen viewpoints
  + tape-measure accuracy run required before trusting the metric scale. Both = TBD-bench.

## 2026-09-02 — Hailo-15L SBC: M0 pipeline proven

M0 pipeline (`services/garuda-perception`, node commit `4ebd020`, branch `feat/hailo15l-perception`)
running under `/etc/init.d/garuda-perception` on the Hailo-15L SBC (`root@10.0.0.1`). Versions
snapshot: `bench/versions.md` 2026-09-02 M0 sub-entry (SDK/poky 4.0.23, HailoRT 5.3.0, HEF
`hailo_yolov8n_384_640.hef`).

### Step 1 — NPU benchmarks (`hailortcli benchmark`, node STOPPED, -t 15 s each)

Command:
```
ssh root@10.0.0.1 '/etc/init.d/garuda-perception stop; sleep 2; for h in hailo_yolov8n_384_640 hailo_yolov8s_384_640; do echo "== $h"; hailortcli benchmark /home/root/apps/shared/resources/$h.hef -t 15 2>&1; echo "----DONE $h----"; done; echo "== thermal_zone0 after"; cat /sys/class/thermal/thermal_zone0/temp'
```

Full output verbatim (unfiltered — this HailoRT build's `benchmark` prints only a minimal Summary
block, so a grep for `FPS|Latency|hw_only|streaming` would have dropped nothing extra; recording
the complete block anyway per the controller's instruction):
```
garuda-perception stopped
== hailo_yolov8n_384_640
Measurement power is not supported
Measurement current is not supported

=======
Summary
=======
hailo_yolov8n_384_640: FPS: 249.08
[integrated]:
  temperature: mean=52.58 min=47.84 max=53.45
----DONE hailo_yolov8n_384_640----
== hailo_yolov8s_384_640
Measurement power is not supported
Measurement current is not supported

=======
Summary
=======
hailo_yolov8s_384_640: FPS: 122.01
[integrated]:
  temperature: mean=55.65 min=51.38 max=56.39
----DONE hailo_yolov8s_384_640----
== thermal_zone0 after
54313
```

| HEF | FPS (`hailortcli benchmark`, solo on NPU, 15 s, node/shim stopped) |
|---|---|
| `hailo_yolov8n_384_640.hef` | **249.08** |
| `hailo_yolov8s_384_640.hef` | **122.01** |

Conditions: node and shim were both stopped for the entire benchmark (no contention with the
pipeline). NPU-internal temperature climbed mean 52.58 -> 55.65 °C across the two back-to-back
15 s runs; SoC `thermal_zone0` immediately after both = 54313 m°C (54.313 °C). These are
solo-on-the-NPU `hailortcli` numbers, not the deployed pipeline's end-to-end throughput — that is
Step 2's `frames=` figure below, which uses only the yolov8n HEF, inside the full
frontend -> detect -> post -> sink pipeline, sharing the 4x A53 CPU with ISP and JPEG-encode work.

### Step 2 — End-to-end 10-minute run (node + shim running, live IMX678 camera)

Readiness confirmed before starting the timed run: `/etc/init.d/garuda-perception status` showed
`/var/run/garuda-perception.pid running (pid 1074)` and `/var/run/garuda-mono-shim.pid running
(pid 1102)`; `curl -s -m 3 http://10.0.0.1:8098/api/state` answered with `"v":2`.

Start-of-run board state:
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; free -m; uptime'
Wed Sep  2 15:31:28 UTC 2026
53857
               total        used        free      shared  buff/cache   available
Mem:            1913         386        1368          11         158        1448
Swap:              0           0           0
 15:31:28 up 15 min,  0 users,  load average: 1.56, 1.47, 1.01
```

PC-side 10-minute SSE script output (the brief's exact script, run against
`http://10.0.0.1:8098/api/events` from this worktree):
```
SSE snapshots in 600 s: 1480 (2.47/s, throttled at 10 Hz); age_ms p50=91 p95=121
54616
               total        used        free      shared  buff/cache   available
Mem:            1913         389        1363          11         160        1445
 15:41:32 up 26 min,  0 users,  load average: 1.95, 1.80, 1.39
162
```
The trailing `162` is `grep -c . /var/log/garuda-perception.log` at that instant — the count of
*every* line in the file (starter begin/done + service banners from three earlier stop/start
cycles this boot are mixed in), not a count of `frames=` lines; see the node-fps figure below for
the real frame count.

End-of-run board recheck, ~4 min after the SSE script's own window closed:
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; free -m; uptime; /etc/init.d/garuda-perception status'
Wed Sep  2 15:45:09 UTC 2026
54414
               total        used        free      shared  buff/cache   available
Mem:            1913         388        1363          11         161        1445
Swap:              0           0           0
 15:45:09 up 29 min,  0 users,  load average: 1.99, 1.84, 1.48
/var/run/garuda-perception.pid running (pid 1074)
/var/run/garuda-mono-shim.pid running (pid 1102)
/var/run/garuda-perception-starter.pid finished
```

**Node's own processed-frame rate** — `frames=<n> fps=<n/10>`, printed every 10 s from the detect
callback (Task 7); this is the pipeline's real throughput, not the SSE line count above. Extracted
with:
```
ssh root@10.0.0.1 "awk '/starter begin \(pid 1071\)/{f=1} f' /var/log/garuda-perception.log | grep '^frames='"
```
106 lines, covering this run's session from `starter begin (pid 1071)` at 15:27:36 UTC through the
log fetch at 15:45:06 UTC — a window that fully contains the 600 s timed run (15:31:28-15:41:28
UTC). Full block:
```
frames=278 fps=27.8
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=299 fps=29.9
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=299 fps=29.9
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=301 fps=30.1
frames=299 fps=29.9
```
Computed from the raw fps values above (n=106): **min=27.8** (first post-start line, a startup
transient), **max=30.1**, **mean=30.01**.

CPU samples (`top -b -n 3 -d 5` on the board), three points across the run:

Start of run, literal brief pattern `grep -E "garuda-percept|python3|Cpu"` (drops the node's own
row — see red-team below):
```
%Cpu(s): 20.9 us,  7.5 sy,  0.0 ni, 71.6 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
 1102 root      20   0  543252  19040   8056 S   0.0   1.0   0:01.74 python3
%Cpu(s): 17.1 us,  6.0 sy,  0.0 ni, 75.5 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1102 root      20   0  543252  19040   8056 S   1.0   1.0   0:01.79 python3
%Cpu(s): 17.5 us,  6.8 sy,  0.0 ni, 74.5 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1102 root      20   0  543252  19040   8056 S   1.2   1.0   0:01.85 python3
```
Same moment, corrected pattern `grep -E "garuda-pe|python3|Cpu"`:
```
%Cpu(s): 15.9 us,  8.7 sy,  0.0 ni, 75.4 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
 1074 root      20   0 2286860  72180  47084 S  47.1   3.7   2:18.29 garuda-pe+
 1102 root      20   0  543252  19040   8056 S   0.0   1.0   0:01.98 python3
%Cpu(s): 15.7 us,  7.1 sy,  0.0 ni, 75.9 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1074 root      20   0 2274708  72180  47084 S  49.4   3.7   2:20.77 garuda-pe+
 1102 root      20   0  543252  19040   8056 S   0.6   1.0   0:02.01 python3
%Cpu(s): 15.8 us,  7.3 sy,  0.0 ni, 75.7 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1074 root      20   0 2286860  72180  47084 S  50.7   3.7   2:23.31 garuda-pe+
 1102 root      20   0  543252  19040   8056 S   1.0   1.0   0:02.06 python3
```
Mid-run (15:36:34 UTC, corrected pattern), plus thermal at the same instant:
```
Wed Sep  2 15:36:34 UTC 2026
%Cpu(s): 21.1 us,  7.0 sy,  0.0 ni, 71.8 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
 1074 root      20   0 2274708  73168  47084 S  56.2   3.7   4:32.16 garuda-pe+
 1102 root      20   0  543252  19040   8056 S   0.0   1.0   0:03.82 python3
%Cpu(s): 16.5 us,  7.2 sy,  0.0 ni, 75.0 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1074 root      20   0 2274708  73168  47084 S  50.2   3.7   4:34.68 garuda-pe+
 1102 root      20   0  543252  19040   8056 S   0.6   1.0   0:03.85 python3
%Cpu(s): 17.2 us,  6.2 sy,  0.0 ni, 75.3 id,  0.1 wa,  1.1 hi,  0.2 si,  0.0 st
 1074 root      20   0 2286860  73168  47084 S  50.4   3.7   4:37.21 garuda-pe+
 1102 root      20   0  543252  19040   8056 S   1.0   1.0   0:02.06 python3
---
53857
```
End of run (~15:45:1x UTC, after the timed window closed, corrected pattern):
```
%Cpu(s): 11.6 us, 10.1 sy,  0.0 ni, 75.4 id,  0.0 wa,  1.4 hi,  1.4 si,  0.0 st
 1074 root      20   0 2286860  73428  47084 S  50.0   3.7   9:16.22 garuda-pe+
 1102 root      20   0  543252  19012   8056 S   6.2   1.0   0:07.46 python3
%Cpu(s): 15.9 us,  6.6 sy,  0.0 ni, 76.4 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1074 root      20   0 2274708  73428  47084 S  50.0   3.7   9:18.73 garuda-pe+
 1102 root      20   0  543252  19012   8056 S   0.6   1.0   0:07.49 python3
%Cpu(s): 15.6 us,  7.2 sy,  0.0 ni, 75.8 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 1074 root      20   0 2286860  73428  47084 S  50.2   3.7   9:21.25 garuda-pe+
 1102 root      20   0  543252  19012   8056 S   0.6   1.0   0:07.52 python3
```
Node (`garuda-pe+`, pid 1074) held **~47-56 %** of one A53 core throughout the run; shim
(`python3`, pid 1102) stayed near **0-1 %**, with one 6.2 % blip at the last sample. System-wide
`%Cpu(s)` `id` stayed 71-76 % the whole run — no CPU saturation on this 4x A53 board.

**Camera scene.** IMX678 pointed at a person standing close to the camera (bbox spans nearly the
full 720 px frame height, width ~490-505 px of a 1280 px-wide frame, positioned right-of-centre)
for at least the ~15:29-15:31 UTC period sampled below; by the 15:45:09 UTC recheck the person had
left frame (`"tracks":[]`). No vehicle was ever in view. One representative non-empty snapshot
(`GET /api/state`, ~15:30 UTC):
```json
{"age_ms":33,"cal":{"fit":null,"n":0},"depth_engine":"y26d","detector":{"mode":"primary","prompt":[]},"distance":{"est_m":null,"raw_m":null,"valid":false},"frame":{"height":720,"width":1280},"gesture":{"held_ms":0,"name":null,"track_id":null},"lock":{"class":"","coasting":false,"id":null},"tracks":[{"coasting":false,"conf":0.8676218390464783,"h":719.9089965820313,"id":0,"label":"person","w":503.45489501953125,"x":777.7996826171875,"y":-1.0589790344238281}],"v":2}
```
No other consumer (camera viewer, portal) was running on the board during the run — verified with
`ps -ef` (only `garuda-perception` pid 1074 and `garuda_mono_shim.py` pid 1102 present) both before
starting the timed window and after.

### Red-team (rule 9)

- **SSE rate (2.47/s) is far below its own 10 Hz throttle, not just below the node's 30 fps.** The
  shim paces the SSE stream to at most `SSE_MAX_HZ=10` (`shim/garuda_mono_shim.py`) whenever a new
  detect snapshot is available, and snapshots are published at ~30 Hz per the `frames=` log, so
  ~10/s was the naive expectation — measured was ~2.5/s. Root cause not investigated (out of scope
  for this recording task); recorded as measured, not explained. Do not use the SSE count for
  anything but confirming the throttle is active at all, and do not treat 2.47/s as the node's
  frame rate — `frames=` above is that number.
- `age_ms` p50=91/p95=121 ms is the sawtooth of the 4-deep detect queue per the task brief's
  caveat, not a latency measurement — not compared against any target here.
- **`top`'s COMMAND column truncates `garuda-perception` to `garuda-pe+`.** The brief's literal
  grep pattern `"garuda-percept"` therefore matches nothing, and every CPU sample under that
  pattern silently drops the node's own row (only `python3`/`Cpu` lines survive) — the same
  "grep may drop lines" risk the controller flagged for `hailortcli benchmark`, realized here on a
  different command. Recorded both the literal-pattern output and a corrected-pattern (`garuda-pe`)
  rerun so the node's own CPU number is not lost.
- Thermal stayed essentially flat: 53.857 °C at run start -> 54.616 °C at the 600 s mark -> 54.414
  °C four minutes later. Documented idle baseline (`bench/versions.md` 2026-09-02 bring-up entry):
  39.4 °C. Idle 39.4 °C and this run's 53.857-54.616 °C range are stated here side by side, with no
  computed delta (rule 1 — no derived figures). No runaway, and no fps degradation visible in the
  `frames=` log across the run (consistently
  29.9-30.1 fps after the first transient line). No throttle-status register/command exists for
  this SoC in our tooling yet, so "no throttling" here is inferred from flat fps, not a direct
  hardware read.
- Board clock read real 2026 dates throughout (deploy.sh sets it at deploy time); the "reads 2018
  after a cold power-on" caveat did not apply because the board was only stopped/started this task,
  never power-cycled.
- The `/stream` MJPEG endpoint (sink1, 1280x720 JPEG) returned HTTP 200 with 0 body bytes on every
  attempt during this task, both from the PC and from the board's own localhost (`curl` to
  `127.0.0.1:8098/stream` on the board itself, same result) — the AI-detect path (sink0, JSON
  snapshots via `/api/events`/`/api/state`) that this task's numbers and scene description rely on
  was unaffected. Not investigated or fixed here (out of scope for a numbers-recording task);
  flagged as a concern for whoever picks up M1's viewer/portal work.
- **Boot-to-answer was not re-measured here** — this run started the service via `stop`/`start` on
  an already-booted board, not a cold reboot. The only boot-to-answer observations on record are
  Task 10's, and they are quoted verbatim below rather than compressed into a range, because the
  poll granularity is the dominant term in every one of them.

  Round 4, reboot cycle 1 (PC side, `curl -s -m 3 http://10.0.0.1:8098/api/state` on a 10 s tick):
  ```
  reboot issued at 14:53:55
  no answer yet at 10s
  STATE_UP after 23s
  ```
  Board side, the complete post-boot `/var/log/garuda-perception.log` (`/var/log` is tmpfs, so this
  is the whole record, not a tail):
  ```
  Wed Sep  2 14:54:03 UTC 2026 starter begin (pid 508)
  Wed Sep  2 14:54:05 UTC 2026 starter done: node 523, shim 576
  ```

  Round 4, reboot cycle 2:
  ```
  reboot issued at 14:56:19
  no answer yet at 10s
  STATE_UP after 23s
  ```
  ```
  Wed Sep  2 14:56:18 UTC 2026 starter begin (pid 510)
  Wed Sep  2 14:56:20 UTC 2026 starter done: node 525, shim 578
  ```

  Round 5, reboot:
  ```
  reboot issued at 15:15:18
  no answer yet at 10s
  no answer yet at 23s
  STATE_UP after 33s
  ```
  ```
  Wed Sep  2 15:15:30 UTC 2026 starter begin (pid 511)
  Wed Sep  2 15:15:32 UTC 2026 starter done: node 526, shim 572
  ```

  **Caveat — read every `STATE_UP after Ns` as an upper bound, not a measurement.** The PC polled
  `/api/state` every 10 s, so `STATE_UP after 23s` (round 4) and `after 33s` (round 5) are simply
  the first tick that got an answer; the true time-to-answer lies somewhere in the preceding 10 s
  window — between 13 s and 23 s in round 4, between 23 s and 33 s in round 5. Nothing here
  measures it more finely, and no single figure should be quoted as "the" boot-to-answer time. The
  `starter begin` / `starter done` lines are board-side and exact, but they are on the board's own
  clock, not the PC's — round 4 cycle 2 shows `starter begin` at 14:56:18 against a PC-side
  "reboot issued at 14:56:19", so the two sides are not directly subtractable either. Source:
  `.superpowers/sdd/2026-09-02-hailo15l-perception-node-m0/task-10-report.md`, rounds 4 and 5 (SDD
  workspace, git-ignored).
- The camera scene was a person in an otherwise-static room, not the stock model's other three
  classes (car/bus/truck per the M0 spec); detection quality on non-person classes remains
  untested on this board.

### Addendum — SSE/MJPEG re-measured after shim fix f882b67

The SSE rate (2.47/s) and the 0-byte `/stream` observation recorded above were both taken against
a broken feed reader: `garuda_mono_shim.py`'s `Feed._run` used `socket.recv(n, MSG_WAITALL)` on a
socket with a 5 s timeout, and CPython's `MSG_WAITALL` can return short once a timeout is set (the
node's own confirmed case: a 129061-byte `J` frame came back as 65531 bytes — controller
reproduction from the PC against the live node, 2026-09-02; raw output committed at
`bench/evidence/2026-09-02-shim-short-read.txt`, also in the Task 11 report) — every short read
made `Feed._run` see `len(p) != ln`, break, and reconnect roughly every 0.5 s, so `/stream` never
completed a single frame and SSE was starved to sub-Hz bursts between reconnects. Fixed in
`f882b67` (`services/garuda-perception/shim/garuda_mono_shim.py`) by replacing the three
`MSG_WAITALL` calls (type byte, length header, payload) with a `recv_exact(sock, n)` loop that
accumulates exactly `n` bytes; deployed to the board and the service restarted (node pid 1512,
shim pid 1540) before this re-measurement.

Re-measured on the PC with the exact commands below (10 s window each, run back-to-back
immediately after the fix was deployed):

```
$ curl -s -N -m 10 -o /tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/sse10.txt http://10.0.0.1:8098/api/events
[exit 28 — curl's own -m 10 timeout firing as designed, not a failure]
$ grep -c "^data:" /tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/sse10.txt
100
```
SSE cap is `SSE_MAX_HZ=10` (`garuda_mono_shim.py`) — **100 `data:` lines in a 10 s window = exactly
10.0/s**, i.e. the shim is now hitting its own throttle cap continuously, not starving at ~2.5/s.

```
$ curl -s -N -m 10 -o /tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/stream10.bin http://10.0.0.1:8098/stream
[exit 28 — curl's own -m 10 timeout firing as designed, not a failure]
$ grep -ac "^--frame" /tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/stream10.bin
141
```
MJPEG cap is `MJPEG_MAX_FPS=15` (`garuda_mono_shim.py`) — **141 `--frame` boundaries in a 10 s
window = 14.1/s**, close to (just under) the 15 fps cap, and no longer 0 bytes. Captured file size
18835177 bytes (~18.8 MB) over the 10 s window, confirming real JPEG payloads are now flowing.

Conclusion: this was a genuine shim bug, not a node-side or measurement artefact — the node's own
numbers recorded above (`hailortcli benchmark` FPS, the `frames=` log, CPU, thermal, RAM) were
unaffected throughout and stand as originally recorded.

---

## 2026-09-03 — Hailo-15L SBC: M1 tracking parity

M1 perception node (`services/garuda-perception`, node commit `b87caed`, branch
`feat/hailo15l-tracking`) already running under `/etc/init.d/garuda-perception` on the Hailo-15L
SBC (`root@10.0.0.1`) — **not redeployed, restarted, or reconfigured for this task**; measured as
it ran. Adds ByteTrack + mono's lock/coast/re-acquire rules in the node (ported from
`hosts/pi5/garuda_mono.py`) on top of the M0 pipeline. One deliberate change from M0: the
detector's NMS score threshold is now `track.conf_floor` = **0.15** (`config/perception.json`
`track.conf_floor`), where M0 ran the detector's threshold at 0.30 — see `docs/decisions.md`
2026-09-03 for why (ByteTrack's low-score association band needs sub-high_thr detections to
re-associate against). Versions snapshot: `bench/versions.md` 2026-09-03 sub-entry (SDK/HailoRT/
image unchanged from the 2026-09-02 M0 entry).

**Controller ruling (owner absent, ~02:30 IST local / 2026-09-02 evening UTC, nobody at the
bench):** run the timed 10-minute window now with the scene as-is (empty — no person, same as M0's
own end-of-run recheck), and record that plainly. The person walk-in/out run the task brief also
calls for is **not done here** — see the ADDENDUM PENDING block at the end of this section.

### Conditions (before starting the timed window)

Command:
```
ssh root@10.0.0.1 'uptime; date; cat /sys/class/thermal/thermal_zone0/temp; free -m | sed -n 2p; pgrep -af garuda-perception | grep -v pgrep; md5sum /opt/garuda/bin/garuda-perception 2>/dev/null; cat /opt/garuda/perception.json 2>/dev/null | head -40'
```
(Path adapted from the brief's guess per `hosts/hailo15l/deploy.sh`: the binary is
`/opt/garuda/bin/garuda-perception`, the config is `/opt/garuda/perception.json`, not
`/opt/garuda/config/perception.json`.)

Output verbatim:
```
 19:46:36 up  4:31,  0 users,  load average: 1.71, 1.54, 1.55
Wed Sep  2 19:46:36 UTC 2026
55021
Mem:            1913         397        1312          11         203        1436
3511 /opt/garuda/bin/garuda-perception --config /opt/garuda/perception.json
ca3513114674957c26ec88399140f02a  /opt/garuda/bin/garuda-perception
{
  "medialib_config": "/opt/garuda/medialib/garuda_medialib_config.json",
  "profile": "Garuda",
  "ai_stream": "sink0",
  "jpeg_stream": "sink1",
  "hef": "/home/root/apps/shared/resources/hailo_yolov8n_384_640.hef",
  "postprocess_so": "/usr/lib/hailo-post-processes/libyolo_hailortpp_post.so",
  "postprocess_config": "/home/root/apps/shared/resources/configs/yolov8.json",
  "feed_port": 8971,
  "command_port": 8972,
  "jpeg_fps": 15,
  "jpeg_quality": 80,
  "frame_w": 1280,
  "frame_h": 720,
  "track": {
    "high_thr": 0.4,
    "low_thr": 0.12,
    "iou_thr": 0.3,
    "max_lost": 25,
    "min_hits": 2,
    "reacq": 5,
    "conf_floor": 0.15,
    "default_class": "person"
  },
  "dump_nv12": {
    "path": "",
    "frames": 0
  }
}
```
`pgrep -af` shows a single node process, pid 3511. `/etc/init.d/garuda-perception status` (run
separately) confirmed both `/var/run/garuda-perception.pid running (pid 3511)` and
`/var/run/garuda-mono-shim.pid running (pid 3539)`.

PC-side git HEAD (`git rev-parse HEAD` in this worktree): `b87caed5c601d6673037178c4780d36aae72a8b2`
(branch `feat/hailo15l-tracking`, matches the node commit deployed on the board).

PC-side processes confirmed running and left alone throughout (`ps -ef`): the SSH tunnel
`ssh -f -N -L 8098:127.0.0.1:8098 root@10.0.0.1` (pid 481436, started an earlier session) and
`services/garuda-portal/portal.py` on `:8080` (from worktree `feat+portal-tracking`, started an
earlier session, `GARUDA_MONO_URL=http://127.0.0.1:8098`). Neither was touched, restarted, or
queried by this task beyond this `ps -ef` confirmation.

`GET /api/state` immediately before the timed window (empty-scene confirmation):
```
{"age_ms":40,"cal":{"fit":null,"n":0},"depth_engine":"y26d","detector":{"mode":"primary","prompt":[]},"distance":{"est_m":null,"raw_m":null,"valid":false},"frame":{"height":720,"width":1280},"gesture":{"held_ms":0,"name":null,"track_id":null},"lock":{"class":"person","coasting":false,"id":null},"tracks":[],"v":2}
```

### Step 1 — 10-minute run (node + shim running, live IMX678 camera, EMPTY SCENE)

SSE capture command (PC), run against the M0/brief target endpoint:
```
curl -s -m 600 -o /tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/m1-bench/sse600.txt http://10.0.0.1:8098/api/events
```
started 2026-09-02 19:46:54 UTC (curl process launch, confirmed against the board's own clock
below), run in the background; ended when curl's own `-m 600` timeout fired (process gone from
`ps -ef` by 19:57:25 UTC, i.e. the full 600 s elapsed as designed — not a failure). Captured file:
1,925,989 bytes, 11,956 lines (5,978 `data:` events) — tally in Step 2 below.

Start-of-run board state:
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; free -m; uptime'
Wed Sep  2 19:47:03 UTC 2026
55021
               total        used        free      shared  buff/cache   available
Mem:            1913         397        1311          11         204        1436
Swap:              0           0           0
 19:47:03 up  4:31,  0 users,  load average: 1.66, 1.55, 1.55
```

Mid-run board state (~5 min in):
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp'
Wed Sep  2 19:52:01 UTC 2026
55122
```

End-of-run board state (after the SSE capture's own 600 s window closed):
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; free -m; uptime; /etc/init.d/garuda-perception status'
Wed Sep  2 19:57:34 UTC 2026
55021
               total        used        free      shared  buff/cache   available
Mem:            1913         398        1309          11         206        1435
Swap:              0           0           0
 19:57:34 up  4:42,  0 users,  load average: 1.27, 1.53, 1.55
/var/run/garuda-perception.pid running (pid 3511)
/var/run/garuda-mono-shim.pid running (pid 3539)
/var/run/garuda-perception-starter.pid finished
```
Post-run confirmation the node was never redeployed/restarted during this task: pid stayed 3511
throughout (start, mid, end), and `md5sum /opt/garuda/bin/garuda-perception` re-checked after the
run still reads `ca3513114674957c26ec88399140f02a` — identical to the pre-run value above.

**Node's own processed-frame rate** — `frames=<n> fps=<n/10>`, same log line as M0 (Task 7),
extracted with:
```
ssh root@10.0.0.1 "awk '/starter begin \(pid 3507\)/{f=1} f' /var/log/garuda-perception.log | grep '^frames='"
```
90 lines, covering this run's session from `starter begin (pid 3507)` at 19:42:35 UTC through the
log fetch at ~19:58 UTC — a window that fully contains the 600 s timed run
(19:46:54-19:56:54 UTC). Full block:
```
frames=278 fps=27.8
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=299 fps=29.9
frames=299 fps=29.9
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=299 fps=29.9
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=299 fps=29.9
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=299 fps=29.9
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
frames=300 fps=30.0
frames=301 fps=30.1
```
Computed from the raw fps values above (n=90): **min=27.8** (first post-start line, a startup
transient, same value as M0's), **max=30.1**, **mean=30.00**.

CPU samples (`top -b -n 3 -d 5` on the board), three points across the run, both the brief's
literal grep pattern and M0's corrected pattern (same `garuda-pe+` truncation applies here):

Start of run, literal pattern `grep -E "garuda-percept|python3|Cpu"` (drops the node's own row,
same as M0):
```
%Cpu(s): 18.8 us,  4.3 sy,  0.0 ni, 75.4 id,  0.0 wa,  1.4 hi,  0.0 si,  0.0 st
 3539 root      20   0  248096  17336   8012 S   0.0   0.9   0:06.32 python3
%Cpu(s): 16.6 us,  7.0 sy,  0.0 ni, 75.0 id,  0.0 wa,  1.1 hi,  0.3 si,  0.0 st
 3539 root      20   0  248096  17336   8012 S   2.4   0.9   0:06.44 python3
%Cpu(s): 17.4 us,  6.8 sy,  0.0 ni, 74.4 id,  0.0 wa,  1.1 hi,  0.2 si,  0.0 st
 3539 root      20   0  248096  17336   8012 S   2.6   0.9   0:06.57 python3
```
Same moment, corrected pattern `grep -E "garuda-pe|python3|Cpu"`:
```
%Cpu(s): 13.2 us,  8.8 sy,  0.0 ni, 76.5 id,  0.0 wa,  1.5 hi,  0.0 si,  0.0 st
 3511 root      20   0 2286904  78240  47072 S  50.0   4.0   2:25.02 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   6.2   0.9   0:06.62 python3
%Cpu(s): 17.0 us,  7.0 sy,  0.0 ni, 74.6 id,  0.0 wa,  1.1 hi,  0.3 si,  0.0 st
 3511 root      20   0 2274752  78240  47072 S  50.4   4.0   2:27.55 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   2.4   0.9   0:06.74 python3
%Cpu(s): 17.0 us,  6.0 sy,  0.0 ni, 75.6 id,  0.1 wa,  1.1 hi,  0.3 si,  0.0 st
 3511 root      20   0 2274752  78240  47072 S  49.6   4.0   2:30.04 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   2.4   0.9   0:06.86 python3
```
Mid-run (~19:52 UTC, corrected pattern):
```
%Cpu(s): 19.4 us,  9.7 sy,  0.0 ni, 69.4 id,  0.0 wa,  1.4 hi,  0.0 si,  0.0 st
 3511 root      20   0 2274752  78240  47072 S  50.0   4.0   4:52.23 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   6.2   0.9   0:13.34 python3
%Cpu(s): 17.0 us,  6.1 sy,  0.0 ni, 75.5 id,  0.0 wa,  1.1 hi,  0.3 si,  0.0 st
 3511 root      20   0 2286904  78240  47072 S  50.8   4.0   4:54.78 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   2.2   0.9   0:13.45 python3
%Cpu(s): 17.4 us,  5.6 sy,  0.0 ni, 75.6 id,  0.0 wa,  1.1 hi,  0.3 si,  0.0 st
 3511 root      20   0 2274752  78240  47072 S  50.8   4.0   4:57.33 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   2.4   0.9   0:13.57 python3
```
End of run (~19:57 UTC, corrected pattern):
```
%Cpu(s): 14.3 us,  8.6 sy,  0.0 ni, 75.7 id,  0.0 wa,  1.4 hi,  0.0 si,  0.0 st
 3511 root      20   0 2286904  78240  47072 S  47.1   4.0   7:22.74 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   5.9   0.9   0:20.07 python3
%Cpu(s): 16.4 us,  6.2 sy,  0.0 ni, 76.0 id,  0.0 wa,  1.1 hi,  0.3 si,  0.0 st
 3511 root      20   0 2274752  78240  47072 S  50.7   4.0   7:25.28 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   2.0   0.9   0:20.17 python3
%Cpu(s): 16.7 us,  5.6 sy,  0.0 ni, 76.4 id,  0.0 wa,  1.1 hi,  0.3 si,  0.0 st
 3511 root      20   0 2286904  78240  47072 S  49.2   4.0   7:27.75 garuda-pe+
 3539 root      20   0  248096  17336   8012 S   2.0   0.9   0:20.27 python3
```
Node (`garuda-pe+`, pid 3511) held **~47-51 %** of one A53 core throughout the run (empty scene,
tracker/lock code running every frame but with nothing to track); shim (`python3`, pid 3539)
stayed near **0-6 %**, blipping to 6.2 % at both the start and end samples (same blip pattern M0
saw once). System-wide `%Cpu(s)` `id` stayed 69-77 % the whole run — no CPU saturation.

**SSE tally.** Tally script and full output (including first/last 5 `data:` lines) committed at
`bench/evidence/2026-09-03-m1-sse-tally.txt`; raw capture (1.9 MB) kept only in the scratchpad at
`/tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/m1-bench/sse600.txt`
(not committed, per instructions). Script output verbatim:
```
total data: lines = 5978
frames with non-empty tracks = 0
frames with lock.coasting == true = 0
distinct lock.id values seen = []
age_ms count=5978 min=32 max=125
```
Every one of the 5,978 SSE snapshots in this run showed `"tracks":[]` and
`"lock":{"coasting":false,"id":null,...}` — the scene was empty for the entire 10 minutes (see
Step 1 intro and the pre-run `/api/state` sample above), so this tally is the tracker/lock code's
**idle cost signature on this run**, not evidence it can track or lock anything. `age_ms` ranged
32-125 ms across the run (min/max only, no percentile computed here — the tally script does not
sort for percentiles).

### Comparison — M0 (no tracker, conf_floor 0.30) vs M1 (tracker in node, conf_floor 0.15)

| Metric | M0 (2026-09-02, this file, quoted line refs) | M1 (2026-09-03, this section) |
|---|---|---|
| Node commit / detector conf threshold | `4ebd020`, NMS floor 0.30 (implicit, no `track` stage) | `b87caed`, NMS floor = `track.conf_floor` = 0.15 |
| `frames=` sample count (n) | 106 (benchlog.md:1005 "106 lines, covering this run's session") | 90 |
| `frames=` min/max/mean fps | min=27.8, max=30.1, mean=30.01 (benchlog.md:1116-1117 "Computed from the raw fps values above (n=106): **min=27.8** ... **max=30.1**, **mean=30.01**") | min=27.8, max=30.1, mean=30.00 |
| Node CPU (`garuda-pe+`) | ~47-56 % of one A53 core (benchlog.md:1170 "Node (`garuda-pe+`, pid 1074) held **~47-56 %** of one A53 core throughout the run") | ~47-51 % of one A53 core (this run's three `top` samples) |
| Shim CPU (`python3`) | near 0-1 %, one 6.2 % blip at the last sample (benchlog.md:1170-1171 "shim (`python3`, pid 1102) stayed near **0-1 %**, with one 6.2 % blip at the last sample") | near 0-6 %, 6.2 % blips at both the start and end samples |
| System-wide `%Cpu(s)` idle | 71-76 % (benchlog.md:1172 "System-wide `%Cpu(s)` `id` stayed 71-76 % the whole run") | 69-77 % |
| SSE rate | 2.47/s pre-fix (benchlog.md:973 "SSE snapshots in 600 s: 1480 (2.47/s..."); 10.0/s post shim-fix `f882b67` re-measurement over a 10 s window (benchlog.md:1299-1300 "100 `data:` lines in a 10 s window = exactly 10.0/s") | 5,978 `data:` lines over the ~598 s the curl connection was held ≈ 10.0/s (post-fix shim, same fix already deployed) |
| Thermal (start / mid / end, `thermal_zone0` m°C) | 53857 (benchlog.md:963) / 53857 at 15:36:34 (benchlog.md:1156, "plus thermal at the same instant") / 54414 (benchlog.md:989) — plus 54616 at the SSE-script's own 15:41:32 checkpoint (benchlog.md:974) | 55021 / 55122 / 55021 |
| Board uptime (start / end) | up 15 min / up 29 min (benchlog.md:967, 993) | up 4:31 / up 4:42 |
| Scene | Person in view for part of the run, empty by the end (M0 §"Camera scene", benchlog.md:1174-1181) | Empty the entire run (this section) |
| `tracks`/`lock` in `/api/state` and SSE | Non-empty during the person portion (benchlog.md:1180 sample) | Always empty/null (this run) |

### Red-team (rule 9)

- **This is the tracker's cost floor on an empty scene, not its typical cost.** With zero tracks
  alive for the entire 10 minutes, the ByteTrack/lock code in the node ran its cheapest path every
  frame (no association, no coast/re-acquire branch ever taken, `click()`'s loop over `m_prev` was
  never exercised with more than an empty vector). The CPU number above (~47-51 % of one core) is a
  **lower bound** on what M1 costs with people in frame — it says nothing about the association,
  IoU-matching, or coast/re-acquire cost, which is exactly the cost path the owner-approved brief
  wanted characterised and which the ADDENDUM PENDING run below still owes.
- **The detector's NMS score floor changed 0.30 -> 0.15 between M0 and M1** (see
  `docs/decisions.md` 2026-09-03), so post-process (NMS) load is also different between the two
  rows of the comparison table above — a lower threshold means NMS considers more candidate boxes
  per frame. This comparison is therefore **node-vs-node** (M0's whole pipeline vs M1's whole
  pipeline, including the intentional detector-threshold change), **not tracker-only** — the CPU
  delta cannot be attributed to the tracker code in isolation.
- **Board temperature and uptime differ from M0's own run** and neither run controls for the
  other: M0's thermal run was 53857-54616 m°C (`thermal_zone0`) on a board up only 15-29 minutes
  since a fresh reboot (close to the post-reboot idle baseline of 39.4 °C in `bench/versions.md`
  2026-09-02); this M1 run was 55021-55122 m°C on a board up 4:31-4:42 with an unknown thermal and
  load history in between (this task did not audit what ran on the board between M0's Task 11 and
  now). Both ranges are stated here side by side with no computed delta between them (rule 1 — no
  derived figures); whether the higher M1 reading is board soak/history or the tracker's added
  compute cannot be separated without an isolated A/B (same board state, tracker on vs off), which
  was not run here.
- **The shim's SSE rate cap hides the node's own rate.** As in M0, the SSE stream is paced to
  `SSE_MAX_HZ=10` regardless of how fast the node actually produces snapshots (per the `frames=`
  log, ~30/s here too); this run's ~10.0/s SSE rate confirms the post-fix shim is hitting its
  throttle continuously (matching M0's own post-fix addendum measurement), not that the node
  slowed down. `frames=` above is the only authoritative node-rate figure in this section, exactly
  as flagged in M0's red-team.
- **Empty-scene tally cannot exercise the metrics the brief actually wants.** "Frames with
  `lock.coasting == true`" and "distinct `lock.id` values seen" are both trivially 0/`{}` with no
  track ever alive — this is a valid, honestly-reported measurement of the idle case, but it is not
  informative about coast/re-acquire behaviour, which requires an actual track to go quiet and come
  back. That is the explicit purpose of the ADDENDUM PENDING run below.
- **No non-person class was in view**, same limitation M0 recorded (stock model's other classes
  untested on this board); `track.default_class` is `"person"` in the deployed config, so even the
  addendum run will only exercise the person path.
- **`dump_nv12` is configured but disabled** (`"path": ""`, `"frames": 0` in the config dump
  above) — it had no effect on this run's numbers; noted only because it appears in the config
  block quoted above and a reader might otherwise wonder.
- The controller ruling to run at ~02:30 local with nobody at the bench means this section's scene
  (empty) was a forced condition, not a choice to skip the person scenario — recorded here per the
  brief's own rule-9 instruction ("state the scene and that the person's movement is not
  reproducible").

### ADDENDUM PENDING (owner presence required) — person walk-in/out run

Not run in this task (controller ruling above: nobody at the bench). To complete the task brief's
Step 1 in full, when the owner is present:

1. Confirm the node is still the same build (repeat the Conditions block's `pgrep -af` +
   `md5sum /opt/garuda/bin/garuda-perception` check above; if it differs, this addendum is invalid
   until reconciled).
2. Start the SSE capture exactly as in Step 1:
   `curl -s -m 600 -o <scratchpad>/m1-bench/sse600-addendum.txt http://10.0.0.1:8098/api/events`
3. Have a person move in and out of the IMX678's view for at least the first two minutes of the
   600 s window (per the task brief), then leave the scene as-is (in or out of view, either is
   fine) for the remainder.
4. Sample `top -b -n 3 -d 5` on the board three times across the run (start/mid/end), both grep
   patterns, exactly as in Step 1.
5. Record board conditions (date, thermal, `free -m`, `uptime`) at start/mid/end, exactly as in
   Step 1.
6. Extract the `frames=` window with the same `awk`/`grep` command against the then-current
   `starter begin (pid N)` anchor.
7. Run `tally_sse.py` (committed alongside the evidence file referenced above, or re-derive it —
   it is ~50 lines) against the new capture; report total `data:` count, frames with non-empty
   `tracks`, frames with `lock.coasting == true`, and the set of distinct `lock.id` values seen —
   this last one is the number this addendum exists to produce: with a person walking in and out,
   `lock.id` should show at least one non-null value, and re-entry after the person leaves and
   returns (if within `max_lost`=25 frames) should either keep the same id (re-acquire) or mint a
   new one (fresh track) — record which, verbatim from the tally, without editorializing.
8. Add a new subsection here (or a new dated section) with those numbers, not overwriting this
   run's empty-scene numbers — the two are different scenes and both are worth keeping.
9. Watch for class flips on the locked track: the greedy matcher (`bytetrack.cpp`) is IoU-only and
   `Track::update` overwrites `cls` on every match, so with the score floor at 0.15 a low-confidence
   box of a *different* class can relabel a locked track's `cls` if it wins the IoU match — this is
   faithful to mono's own behaviour, but more likely to be seen on the board than it was in M0
   (higher NMS floor, no tracker). If `lock.class`/a track's `label` changes without a `target`
   command or a re-acquire event, record it here rather than treating it as a bug to silently fix.

### ADDENDUM 2026-09-03 (owner present) — coast window measured, then tuned: `max_lost` 25→75, `reacq` 5→15

Owner at the bench 10:45–10:57 local. Node binary unchanged (the b0ea29b build already running);
between the two captures only `config/perception.json` `track.max_lost` / `track.reacq` changed
(deployed with `hosts/hailo15l/deploy.sh` at 10:48, service restarted; node log after the restart:
`frames=301 fps=30.1`). **Protocol: this is NOT the 600 s run of the ADDENDUM PENDING block above**
— no `top`/thermal/`free` samples were taken, so the CPU-with-person numbers that block asks for
are still pending. This addendum answers only the behaviour question the owner raised in the portal
("person 75 after going off screen"): how long does the locked person coast, and does the id survive?

Method: PC-side wall-clock timestamp per SSE snapshot from `http://10.0.0.1:8098/api/events`
(`sse_capture.py`; the shim caps SSE at 10 Hz, so times are ±0.1 s), then `timeline.py` prints
every change of (lock id, lock coasting, track ids, coasting ids) and every coasting episode of the
LOCKED track with its outcome. Scripts and the filtered timelines:
`bench/evidence/2026-09-03-m1-coast-window.txt` (+ `-scripts/`). Owner's routine each time:
in view 5 s; out ~1 s; back 5 s; out ~3 s; back 5 s; out ~10 s; back (fully out of the IMX678's
view — a first "after" attempt where the owner stayed partly in frame produced no coasting at all
and was discarded; noted in the evidence file).

BEFORE — `max_lost=25`, `reacq=5` (mono's values), 150 s capture started 10:45:35, episodes verbatim:
```
  id 27 coasted 0.80s -> TRACK DIED (lock None)
  id 31 coasted 0.90s -> TRACK DIED (lock None)
  id 34 coasted 0.80s -> TRACK DIED (lock None)
  id 37 coasted 0.80s -> TRACK DIED (lock None)
  id 39 coasted 0.20s -> SURVIVED (same id 39 live again)
  id 39 coasted 0.10s -> SURVIVED (same id 39 live again)
  id 39 coasted 0.80s -> TRACK DIED (lock None)
  id 41 coasted 0.81s -> TRACK DIED (lock None)
snapshots: 1496 span: 150.1s
```

AFTER — `max_lost=75`, `reacq=15`, 240 s capture started 10:53:04, episodes verbatim:
```
  id 15 coasted 2.41s -> TRACK DIED (lock None)
  id 18 coasted 0.10s -> SURVIVED (same id 18 live again)
  id 18 coasted 2.61s -> TRACK DIED (lock None)
  id 20 coasted 0.10s -> SURVIVED (same id 20 live again)
  id 20 coasted 1.81s -> LOCK MOVED to live id 25 (re-acquire rule; coasted id 20 not returned)
  id 25 coasted 0.20s -> SURVIVED (same id 25 live again)
  id 25 coasted 0.10s -> SURVIVED (same id 25 live again)
  id 25 coasted 0.70s -> LOCK MOVED to live id 31 (re-acquire rule; coasted id 25 not returned)
  id 31 coasted 0.50s -> LOCK MOVED to live id 32 (re-acquire rule; coasted id 31 not returned)
  id 32 coasted 0.50s -> LOCK MOVED to live id 33 (re-acquire rule; coasted id 32 not returned)
snapshots: 2392 span: 240.0s
```

What the two captures show, without editorializing beyond the lines above:
- With mono's 25 frames, every absence of about a second or more ended the track at 0.80–0.90 s
  of coasting (25 frames at the board's ~30 detection fps) and the lock dropped to `None`; the
  next appearance was a new id (27, 31, 34, 37, 39, 41 in sequence). 0.1–0.2 s flickers kept the id.
- With 75 frames the coasts ran to 2.41 s and 2.61 s before the track died; 0.1–0.2 s flickers
  kept the id as before.
- Re-entering the frame at a different position mints a new track even inside the window: the
  matcher is IoU-only against the velocity-predicted box (mono's behaviour, unchanged); the
  re-acquire rule then moved the lock to the live person 0.5–1.8 s into the coast (`reacq=15`
  frames = 0.5 s at 30 fps; the 1.81 s case is the first live same-class track appearing that late).
- No class flip of the locked person track was seen in either capture (item 9 above); face tracks
  come and go as separate ids throughout and never took the lock (`lock.class` stayed `person`).
- Rule 9: the 1/3/10 s absences were paced by the owner, not a timer, so per-absence durations are
  not recoverable from these captures — only the coast durations above are measured. The SSE
  10 Hz cap bounds every time here to ±0.1 s. The choice of 75/15 is "about 2.5 s / 0.5 s" for
  this board; mono's own wall-clock window on the Pi was not measured (its detection rate is not
  recorded in this repo), so this is a board tuning, not a matched value (`docs/decisions.md`
  2026-09-03 "validation").

### ADDENDUM 2026-09-03 — what the stock post-process actually floors at (evidence gap closed)

The `24dca06` fix (see this section's intro and `docs/decisions.md` 2026-09-03) sets the detect
stage's NMS score threshold to `track.conf_floor` (0.15) so ByteTrack's low-score association band
is fed candidates below the tracker's own historical NMS floor. That fix says nothing about what
the stock post-process plugin itself floors detections at — recorded here.

Command and verbatim output:
```
$ ssh root@10.0.0.1 'date; cat /home/root/apps/shared/resources/configs/yolov8.json'
Wed Sep  2 20:47:36 UTC 2026
{
    "iou_threshold": 0.9,
    "detection_threshold": 0.38,
    "output_activation": "none",
    "label_offset": 1,
    "max_boxes": 10000,
    "labels": ["unlabeled", "person", "vehicle", "face", "license_plate"]
}
```
(This is the exact `postprocess_config` path `config/perception.json` passes to
`PostprocessStageBuild` — confirmed by reading `services/garuda-perception/src/node_main.cpp` and
`services/garuda-perception/config/perception.json`, both of which point at
`/home/root/apps/shared/resources/configs/yolov8.json`.)

**Which threshold binds:** `detection_threshold: 0.38` is the post-process's own confidence floor,
applied before the NMS-score-threshold fix in `24dca06` (0.15) or the tracker's own floors
(`track.low_thr`=0.12, `track.conf_floor`=0.15) ever see a detection. 0.38 > 0.15 > 0.12, so the
post-process discards everything ByteTrack's low-confidence re-association band exists to use —
**the low band is INERT, not live, until M2 (the post-process port) replaces this config.** Per
the task's own instruction this post-process config is **not** changed here — M2 owns it.

## 2026-09-03 — Hailo-15L SBC: yolo26m from the Hailo model zoo (v5.3.0/hailo15l) — parse + benchmark

Context: the M1 plan's detector recompile (Task 0/7) was OOM-killed three times on the PC
(`models/yolo26m_h15l.md`). While researching the M2 decode port it turned out the Pi's production
`yolo26m.hef` was never compiled locally either — it came pre-built from Hailo's model zoo — and the
zoo publishes the same model for `hailo15l`. Fetched and measured; the local recompile is now optional.

Conditions: board = Hailo-15L SBC, stock image 1.12.0, HailoRT 5.3.0; perception service STOPPED for
the benchmark (`/etc/init.d/garuda-perception stop`, restarted right after — `frames=277 fps=27.7`
in the node log on restart, feed answering). PC-side download + md5, verbatim:

```
$ curl -sI https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/yolo26m.hef
HTTP/1.1 200 OK  Content-Length: 22388736
$ md5sum yolo26m_hailo15l_v5.3.0.hef
3aef604ab89ddaf9ecb4cefa9c6ea8af
```

`hailortcli parse-hef /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef` on the board, verbatim:

```
HEF Compatible for: HAILO15L
HEF Compiler Version: 5.3.0
Network group name: yolo26m, Multi Context - Number of contexts: 17
    Network name: yolo26m/yolo26m
        VStream infos:
            Input  yolo26m/input_layer1 UINT8, NV12(320x640x3)
            Output yolo26m/conv71 UINT16, NHWC(80x80x4)
            Output yolo26m/conv87 UINT16, NHWC(40x40x4)
            Output yolo26m/conv101 UINT16, NHWC(20x20x4)
            Output yolo26m/conv74 UINT16, NHWC(80x80x80)
            Output yolo26m/conv90 UINT16, NHWC(40x40x80)
            Output yolo26m/conv104 UINT16, NHWC(20x20x80)
```

`hailortcli benchmark /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef -t 15` on the board
(same grep as the M0 runs: `grep -E "FPS|Latency|hw_only|streaming"`), verbatim, with the thermal
zone before/after (`/sys/class/thermal/thermal_zone0/temp`, milli-°C) and the board's clock:

```
== conditions: Thu Sep  3 05:50:23 UTC 2026 uptime:up 14:34,  0 users,  load average: 1.38, 1.65, 1.68 thermal_mC:48040
yolo26m: FPS: 25.97
== thermal after: 55375
```

For comparison, the stock HEFs measured the same way in the M0 section of this file:
`hailo_yolov8n_384_640: FPS: 249.08` (line 922) and `hailo_yolov8s_384_640: FPS: 122.01` (line 933).

Red-team (rule 9): one 15 s run, no repeat; the board had been up 14.5 h running the perception
node until 3 s before the benchmark (thermal 48.0 °C at start, 55.4 °C after), so this is a warm
board, not a cold one; `hailortcli benchmark` measures the NPU path only (no ISP, no decode, no
tracker) — the end-to-end rate with the M2 decode in the node is `TBD-bench` until M2 runs it; the
17-context HEF means the 15L switches contexts per frame, so this number is specific to the 15L and
must not be quoted for the 15H (CLAUDE.md §7). The model is the zoo's generic COCO calibration, not
our `depth-calib.yaml` set; accuracy on our scenes is unmeasured.

## 2026-09-03 — Hailo-15L SBC: M2 yolo26m detector

M2 perception node (`services/garuda-perception`, deployed node commit `8c82367`, branch
`feat/hailo15l-detector`) already running under `/etc/init.d/garuda-perception` on the Hailo-15L
SBC (`root@10.0.0.1`) — **not redeployed, restarted, or reconfigured for this task**; measured as
it ran. Replaces M1's stock `hailo_yolov8n_384_640.hef` + `libyolo_hailortpp_post.so` path with
the Hailo model-zoo `yolo26m` HEF (this file's own "yolo26m from the Hailo model zoo" section
above, md5 `3aef604ab89ddaf9ecb4cefa9c6ea8af`) and our own post-process plugin
`libyolo26_post.so` (Task 3/4), letterboxed 640x640 (`LETTERBOX_MIDDLE`) input instead of M0/M1's
640x384 stretched input. `track.conf_floor` stays 0.15 (unchanged from M1), but the plugin's own
`conf_thresh` (also 0.15) now actually matches it at the post-process stage — M1's stock
post-process floored at 0.38 regardless of `conf_floor`, so this is the change that makes
ByteTrack's low-confidence re-association band live (`docs/decisions.md` 2026-09-03 "(M2)";
`hosts/hailo15l/README.md` §8 "What changes for a portal user vs M1"). Versions snapshot:
`bench/versions.md` 2026-09-03 "M2 yolo26m detector deployed" sub-entry (SDK/HailoRT/image
unchanged from the 2026-09-02 M0 entry).

**Scene:** the owner was at the bench earlier in the session; this run's window (08:20:23-08:30:23
UTC) caught a person continuously in the IMX678's view for the entire 600 s, plus a populated
background (books, suitcases, a chair, a refrigerator) — see the SSE tally below. No walk-in/out
routine was performed or requested for this task; the run is reported as the scene actually was,
not as an engineered coast-window test (that behaviour was already characterised in the M1
section's "ADDENDUM 2026-09-03 (owner present) — coast window").

### Conditions (before starting the timed window)

Command (as given in this task's brief):
```
ssh root@10.0.0.1 'uptime; date; cat /sys/class/thermal/thermal_zone0/temp; free -m | sed -n 2p; pgrep -af garuda-perception | grep -v pgrep; md5sum /opt/garuda/bin/garuda-perception /opt/garuda/lib/libyolo26_post.so /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef; cat /opt/garuda/yolo26_post.json | head -12; grep -o "\"hef\"[^,]*" /opt/garuda/perception.json'
```
Output verbatim:
```
 08:19:46 up 17:04,  0 users,  load average: 3.13, 2.68, 2.43
Thu Sep  3 08:19:46 UTC 2026
69134
Mem:            1913         437        1216          11         260        1395
8208 /opt/garuda/bin/garuda-perception --config /opt/garuda/perception.json
48a86c417d9d68a0cb90885970b03823  /opt/garuda/bin/garuda-perception
46eba70477207c7eb1d9ff3fdd61fe8d  /opt/garuda/lib/libyolo26_post.so
3aef604ab89ddaf9ecb4cefa9c6ea8af  /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef
{
  "conf_thresh": 0.15,
  "iou_thresh": 0.5,
  "in_w": 640,
  "in_h": 640,
  "frame_w": 1280,
  "frame_h": 720,
  "mode": "letterbox",
  "tensor_prefix": "yolo26m/",
  "box_tensors": [
    "conv71",
    "conv87",
"hef": "/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef"
```

`/etc/init.d/garuda-perception status` and the full `perception.json`, run together:
```
$ ssh root@10.0.0.1 '/etc/init.d/garuda-perception status; cat /opt/garuda/perception.json'
/var/run/garuda-perception.pid running (pid 8208)
/var/run/garuda-mono-shim.pid running (pid 8271)
/var/run/garuda-perception-starter.pid finished
{
  "medialib_config": "/opt/garuda/medialib/garuda_medialib_config.json",
  "profile": "Garuda",
  "ai_stream": "sink0",
  "jpeg_stream": "sink1",
  "hef": "/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef",
  "postprocess_so": "/opt/garuda/lib/libyolo26_post.so",
  "postprocess_config": "/opt/garuda/yolo26_post.json",
  "feed_port": 8971,
  "command_port": 8972,
  "jpeg_fps": 15,
  "jpeg_quality": 80,
  "frame_w": 1280,
  "frame_h": 720,
  "track": {
    "high_thr": 0.4,
    "low_thr": 0.12,
    "iou_thr": 0.3,
    "max_lost": 75,
    "min_hits": 2,
    "reacq": 15,
    "conf_floor": 0.15,
    "default_class": "person"
  },
  "dump_nv12": {
    "path": "",
    "frames": 0,
    "width": 640,
    "height": 640
  }
}
```
`track.max_lost`/`track.reacq` (75/15) are the M1 addendum's tuned values, unchanged here — this
task did not touch tracker config, only measured the M2 detector sitting underneath it.

PC-side git HEAD (`git rev-parse HEAD` in this worktree): `25d7bd11ca718e5fb7c8c3940ffc938afe8da46a`
(branch `feat/hailo15l-detector`). This is one commit ahead of the deployed node commit `8c82367`;
`git show --stat 25d7bd1` confirms the only files touched are under
`services/garuda-perception/tests/` (a golden-test addition), so the running binary is unaffected.

PC-side processes confirmed running and left alone throughout (`ps -ef`): the SSH tunnel
`ssh -f -N -L 8098:127.0.0.1:8098 root@10.0.0.1` (pid 770054) and
`services/garuda-portal/portal.py` on `:8080` (pid 481450, from worktree `feat+portal-tracking`,
`GARUDA_MONO_URL=http://127.0.0.1:8098`). Neither was touched, restarted, or queried by this task
beyond this `ps -ef` confirmation.

`GET /api/state` shortly before the timed window (confirms the scene is populated, a person plus
several background objects, before the run even starts):
```
$ curl -s -m 5 http://10.0.0.1:8098/api/state
{"age_ms":848,"cal":{"fit":null,"n":0},"depth_engine":"y26d","detector":{"mode":"primary","prompt":[]},"distance":{"est_m":null,"raw_m":null,"valid":false},"frame":{"height":720,"width":1280},"gesture":{"held_ms":0,"name":null,"track_id":null},"lock":{"class":"person","coasting":false,"id":1},"tracks":[{"coasting":false,"conf":0.9727977514266968,"id":1,"label":"person",...},{"conf":0.29638367891311646,"id":2,"label":"book",...},{"conf":0.4405946135520935,"id":3,"label":"book",...},{"conf":0.33636924624443054,"id":4,"label":"suitcase",...},{"conf":0.28914543986320496,"id":5,"label":"book",...},{"conf":0.4315222501754761,"id":42,"label":"book",...},{"conf":0.4144589304924011,"id":43,"label":"book",...},{"conf":0.17374055087566376,"id":44,"label":"refrigerator",...},{"conf":0.4209299087524414,"id":49,"label":"chair",...}],"v":2}
```
(track fields elided with `...` here for width; full untruncated JSON lines of this shape are in
the SSE tally evidence file referenced below.)

### Step 1 — 10-minute run (node + shim running, live IMX678 camera, PERSON + OBJECTS IN VIEW)

SSE capture command (PC), run in the background via `nohup` (per this task's instructions —
never a foreground sleep/capture longer than 60 s):
```
$ cd /tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/m2-bench
$ nohup curl -s -m 600 -o sse600.txt http://10.0.0.1:8098/api/events > curl.log 2>&1 &
launched pid 816938 (curl child pid 816939)
```
started 2026-09-03 08:20:23 UTC (background launch, confirmed against `ps -ef` at 08:20:29 showing
the curl process live), run for its own `-m 600` timeout; ended when curl exited on its own
(confirmed gone from `ps -ef` by 08:30:37 UTC, i.e. the full 600 s elapsed as designed — not a
failure). Captured file: 10,918,303 bytes, 11,938 lines (5,969 `data:` events) — tally below.

Start-of-run board state (`ps -ef` confirmation + board date/thermal/free/uptime, taken together):
```
$ ps -ef | grep "curl -s -m 600"
bhanu1234  816939  816938  0 13:50 ?  curl -s -m 600 -o sse600.txt http://10.0.0.1:8098/api/events
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; free -m; uptime'
Thu Sep  3 08:20:29 UTC 2026
69387
               total        used        free      shared  buff/cache   available
Mem:            1913         436        1216          11         260        1396
Swap:              0           0           0
 08:20:30 up 17:04,  0 users,  load average: 2.80, 2.64, 2.44
```

CPU samples (`top -b -n 3 -d 5` on the board), three points across the run, both the brief's
literal grep pattern and M1's corrected pattern (same `garuda-pe+` truncation applies here):

Start of run, corrected pattern `grep -E "garuda-pe|python3|Cpu"`:
```
%Cpu(s): 34.8 us,  9.1 sy,  0.0 ni, 54.5 id,  0.0 wa,  1.5 hi,  0.0 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 105.9   3.5  16:33.01 garuda-pe+
 8271 root      20   0  248096  18288   8048 S   5.9   0.9   0:21.98 python3
%Cpu(s): 31.6 us,  9.0 sy,  0.0 ni, 56.6 id,  0.0 wa,  2.4 hi,  0.4 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 115.6   3.5  16:38.80 garuda-pe+
 8271 root      20   0  248096  18288   8048 S   2.6   0.9   0:22.11 python3
%Cpu(s): 31.6 us,  9.8 sy,  0.0 ni, 55.9 id,  0.0 wa,  2.3 hi,  0.4 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 115.5   3.5  16:44.60 garuda-pe+
 8271 root      20   0  248096  18288   8048 S   2.6   0.9   0:22.24 python3
```
Same moment, literal pattern `grep -E "garuda-percept|python3|Cpu"` (drops the node's own row,
same truncation as M0/M1):
```
%Cpu(s): 33.3 us, 11.6 sy,  0.0 ni, 52.2 id,  0.0 wa,  1.4 hi,  1.4 si,  0.0 st
 8271 root      20   0  248096  18288   8048 S   0.0   0.9   0:22.45 python3
%Cpu(s): 30.9 us,  9.5 sy,  0.0 ni, 57.1 id,  0.0 wa,  2.2 hi,  0.4 si,  0.0 st
 8271 root      20   0  248096  18288   8048 S   2.8   0.9   0:22.59 python3
%Cpu(s): 31.7 us,  9.2 sy,  0.0 ni, 56.3 id,  0.0 wa,  2.4 hi,  0.4 si,  0.0 st
 8271 root      20   0  248096  18288   8048 S   2.6   0.9   0:22.72 python3
```

Mid-run (~08:25 UTC, corrected pattern), with thermal at the same instant:
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp'
Thu Sep  3 08:25:31 UTC 2026
70096
$ ssh root@10.0.0.1 'top -b -n 3 -d 5 | grep -E "garuda-pe|python3|Cpu"'
%Cpu(s): 29.9 us, 11.9 sy,  0.0 ni, 56.7 id,  0.0 wa,  1.5 hi,  0.0 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 112.5   3.5  22:08.05 garuda-pe+
 8271 root      20   0  248096  18288   8048 S   6.2   0.9   0:29.98 python3
%Cpu(s): 30.8 us,  9.8 sy,  0.0 ni, 56.6 id,  0.0 wa,  2.4 hi,  0.4 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 115.5   3.5  22:13.85 garuda-pe+
 8271 root      20   0  248096  18288   8048 S   2.6   0.9   0:30.11 python3
%Cpu(s): 31.8 us,  9.3 sy,  0.0 ni, 56.2 id,  0.0 wa,  2.3 hi,  0.4 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 116.2   3.5  22:19.67 garuda-pe+
 8271 root      20   0  248096  18288   8048 S   3.0   0.9   0:30.26 python3
```

End of run (~08:31 UTC, corrected pattern), board state and init.d status just before:
```
$ ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; free -m; uptime; /etc/init.d/garuda-perception status'
Thu Sep  3 08:30:45 UTC 2026
69843
               total        used        free      shared  buff/cache   available
Mem:            1913         436        1216          11         260        1395
Swap:              0           0           0
 08:30:45 up 17:15,  0 users,  load average: 2.79, 2.52, 2.47
/var/run/garuda-perception.pid running (pid 8208)
/var/run/garuda-mono-shim.pid running (pid 8271)
/var/run/garuda-perception-starter.pid finished
$ ssh root@10.0.0.1 'top -b -n 3 -d 5 | grep -E "garuda-pe|python3|Cpu"'
%Cpu(s): 28.4 us, 13.4 sy,  0.0 ni, 55.2 id,  0.0 wa,  3.0 hi,  0.0 si,  0.0 st
 8208 root      20   0 2673896  69220  47020 S 111.8   3.5  28:30.43 garuda-pe+
 8271 root      20   0  248096  18412   8048 S   5.9   0.9   0:39.35 python3
%Cpu(s): 30.1 us, 10.5 sy,  0.0 ni, 56.7 id,  0.0 wa,  2.3 hi,  0.4 si,  0.0 st
 8208 root      20   0 2686048  69220  47020 S 115.7   3.5  28:36.24 garuda-pe+
 8271 root      20   0  248096  18412   8048 S   2.6   0.9   0:39.48 python3
%Cpu(s): 31.2 us,  9.8 sy,  0.0 ni, 56.3 id,  0.0 wa,  2.3 hi,  0.4 si,  0.0 st
 8208 root      20   0 2673896  69220  47020 S 115.1   3.5  28:42.02 garuda-pe+
 8271 root      20   0  248096  18412   8048 S   2.4   0.9   0:39.60 python3
```

Post-run confirmation the node was never redeployed/restarted during this task: pid stayed 8208
throughout (start, mid, end), and re-checking `md5sum` after the run:
```
$ ssh root@10.0.0.1 'pgrep -af garuda-perception | grep -v pgrep; md5sum /opt/garuda/bin/garuda-perception /opt/garuda/lib/libyolo26_post.so /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef'
8208 /opt/garuda/bin/garuda-perception --config /opt/garuda/perception.json
48a86c417d9d68a0cb90885970b03823  /opt/garuda/bin/garuda-perception
46eba70477207c7eb1d9ff3fdd61fe8d  /opt/garuda/lib/libyolo26_post.so
3aef604ab89ddaf9ecb4cefa9c6ea8af  /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef
```
all three md5s identical to the pre-run values above.

Across all 9 `top` samples above (3 start-corrected + 3 mid + 3 end; the 3 start-literal samples
drop the node's own row), node (`garuda-pe+`, pid 8208) held **~106-116 %** of one A53 core
(min 105.9, max 116.2 — roughly double M1's ~47-51 %, see the comparison table below); shim
(`python3`, pid 8271) stayed near **0-6 %** across all 12 samples (min 0.0, max 6.2 — same
blip-at-sample-boundary pattern M0/M1 saw). System-wide `%Cpu(s)` `id` ranged **52.2-57.1 %**
across all 12 samples — noticeably lower than M1's 69-77 %, i.e. less headroom, but still no
saturation (never near 0).

**Node's own processed-frame rate** — `frames=<n> fps=<n/10>`, same log line as M0/M1, extracted
with:
```
ssh root@10.0.0.1 "awk '/starter begin \(pid 8204\)/{f=1} f' /var/log/garuda-perception.log | grep '^frames='"
```
150 lines, covering this run's session from `starter begin (pid 8204)` at 08:06:21 UTC through the
log fetch at ~08:31 UTC — a window that fully contains the 600 s timed run (08:20:23-08:30:23 UTC).
Full block:
```
frames=233 fps=23.3
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=257 fps=25.7
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=258 fps=25.8
```
Computed from the raw fps values above with a small script (`n=150`):
```
$ python3 -c "
vals = []
with open('frames_window.txt') as f:
    for line in f:
        fps = float(line.strip().split('fps=')[1])
        vals.append(fps)
print('n=%d min=%.1f max=%.1f mean=%.4f' % (len(vals), min(vals), max(vals), sum(vals)/len(vals)))
"
n=150 min=23.3 max=25.8 mean=25.7387
```
**min=23.3** (first post-start line, a startup transient, same pattern as M0/M1's first-line
transient), **max=25.8**, **mean=25.7387**. This closes the "`TBD-bench` until M2 runs it" gap
left open in this file's own zoo-HEF section above (line 1869) — the end-to-end node rate
(25.7387 fps mean) sits within about 1 % of the NPU-only ceiling measured there (25.97 fps,
line 1859), i.e. the post-process decode + ByteTrack + lock code riding on top of the 17-context
HEF add negligible rate cost beyond the NPU's own per-frame context-switch bound.

**SSE tally.** Extended tally script and full output (including first/last 5 `data:` lines, plus a
supplementary person-presence/lock-id/track-count check) committed at
`bench/evidence/2026-09-03-m2-sse-tally.txt`; raw capture (10.9 MB) kept only in the scratchpad at
`/tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/m2-bench/sse600.txt`
(not committed, per instructions). Script output verbatim:
```
total data: lines = 5969
frames with non-empty tracks = 5969
frames with >=2 tracks = 5969
frames with lock.coasting == true = 0
distinct lock.id values seen = [1]
distinct labels seen across all tracks = ['book', 'cell phone', 'chair', 'person', 'refrigerator', 'suitcase']
age_ms count=5969 min=836 max=892
```
Supplementary check (same capture, a second small script — see the evidence file for source):
```
n= 5969 person_present_frames= 5969 lock_id_counts= {1: 5969} min_tracks= 8 max_tracks= 12
```
**Every one of the 5,969 SSE snapshots in this run had a non-empty `tracks[]`** (min 8, max 12
tracks per frame) **and `"label":"person"` in every single frame** — the owner was continuously in
the IMX678's view for the entire 600 s window, not intermittently. The lock acquired track id `1`
(the person) and **never changed and never coasted** for the whole run — `lock.coasting` was
`false` and `lock.id` was `1` on all 5,969 snapshots — because the person never left the frame, so
neither the coast nor the re-acquire path was exercised here (that behaviour remains characterised
only in the M1 section's owner-present coast-window addendum, not repeated by this run). Six
distinct COCO labels were seen across all tracks in the run (`book`, `cell phone`, `chair`,
`person`, `refrigerator`, `suitcase`) — the multi-class capability M1's stock detector did not
have (M1 could only ever emit `person`/`face`). `age_ms` (time from the ISP's own frame timestamp
to when `det_sink` serves the snapshot, `node_main.cpp:243`) ranged 836-892 ms across the run —
roughly 7-27x M1's 32-125 ms range (`bench/evidence/2026-09-03-m1-sse-tally.txt`,
`bench/benchlog.md:1614`); this is a striking difference, addressed in the red-team below.

### Comparison — M1 (stock detector + our tracker) vs M2 (our detector + our tracker) vs the zoo-HEF NPU-only ceiling

| Metric | M1 (2026-09-03, this file, quoted line refs) | M2 (2026-09-03, this section) |
|---|---|---|
| Detector / post-process | `hailo_yolov8n_384_640.hef` + stock `libyolo_hailortpp_post.so`, `detection_threshold` 0.38 (post-process's own floor, above `track.conf_floor`=0.15 — low band inert; benchlog.md:1811-1816) | Hailo-zoo `yolo26m.hef` + our `libyolo26_post.so`, `conf_thresh`=0.15 (matches `track.conf_floor` — low band live) |
| Input geometry | 640x384 stretched | 640x640 letterboxed (`LETTERBOX_MIDDLE`, DSP pads Y=0 black) |
| `frames=` sample count (n) | 90 (benchlog.md:1453 "90 lines, covering this run's session") | 150 |
| `frames=` min/max/mean fps | min=27.8, max=30.1, mean=30.00 (benchlog.md:1548-1549) | min=23.3, max=25.8, mean=25.7387 |
| zoo NPU-only ceiling (`hailortcli benchmark`, no ISP/decode/tracker) | not measured against M1's stock geometry in this file | 25.97 fps (benchlog.md:1859 "yolo26m: FPS: 25.97") — M2's own `frames=` mean is ~1 % below this ceiling |
| Node CPU (`garuda-pe+`) | ~47-51 % of one A53 core (benchlog.md:1600) | ~106-116 % of one A53 core (this run's 9 `top` samples) |
| Shim CPU (`python3`) | near 0-6 %, blips to 6.2 % at start/end (benchlog.md:1601-1602) | near 0-6 %, blips to 6.2 % at start/mid/end (this run's 12 samples) |
| System-wide `%Cpu(s)` idle | 69-77 % (benchlog.md:1603) | 52.2-57.1 % (this run's 12 samples) |
| SSE rate | 5,978 `data:` lines over ~598 s ≈ 10.0/s (benchlog.md:1633) | 5,969 `data:` lines over ~598 s ≈ 9.98/s (same shim cap) |
| Thermal (start / mid / end, `thermal_zone0` m°C) | 55021 / 55122 / 55021 (benchlog.md:1634) | 69134 (pre-run) / 70096 (mid) / 69843 (end) |
| Board uptime (start / end) | up 4:31 / up 4:42 (benchlog.md:1635) | up 17:04 (pre-run) / up 17:15 (end) |
| Scene | Empty the entire run (benchlog.md:1636) | Person + 5-8 background objects in every one of the 5,969 frames (this section's tally) |
| `tracks`/`lock` in SSE | Always empty/null (benchlog.md:1637) | Non-empty every frame; `lock.id`=1 the whole run, never coasted; 6 distinct labels seen |
| `age_ms` (snapshot staleness) | min=32 max=125 (`bench/evidence/2026-09-03-m1-sse-tally.txt`, benchlog.md:1614) | min=836 max=892 (this run's tally) |

### Red-team (rule 9)

- **The post stage's CPU is not comparable with M1's stock plugin, because M2's post stage now
  does the decode M1's post stage never did.** M1's `libyolo_hailortpp_post.so` reads an
  already-NMS'd `nms_postprocess` tensor the HEF itself produces; M2's `libyolo26_post.so`
  dequantises six raw UINT16 heads, runs the full Pi-parity box/class decode, and does its own
  NMS (`docs/decisions.md` 2026-09-03 "(M2)"). The ~106-116 % vs ~47-51 % node-CPU gap in the
  comparison table therefore mixes at least three changed variables (decode work newly on this
  core, a bigger 640x640 input, a 17-context HEF vs the stock HEF's smaller context count) — it is
  **not** a clean "how much does decode cost" number, and no isolated A/B (same HEF, plugin
  decode on vs off) was run to separate them.
- **The node's rate is bounded by the 17-context model; the NPU-only benchmark is the ceiling,
  not a floor to beat.** M2's `frames=` mean (25.7387 fps) sits within ~1 % of the standalone
  `hailortcli benchmark` figure for the same HEF (25.97 fps, line 1859) — meaning the full
  pipeline (ISP, decode, NMS, tracker, JSON serialisation) adds essentially no throughput cost on
  top of the NPU's own context-switch-bound rate. This is a genuinely good result, but it also
  means **the model's own multi-context compile is the hard ceiling**: nothing this node does
  (or could do) makes it faster than ~26 fps on this board without a different HEF compile.
- **Warm board, long uptime — not a cold-start number.** This run's thermal ranged 69134-70096
  m°C (`thermal_zone0`), on a board up 17:04-17:15 with an unaudited load history since the last
  reboot (the same caveat M1's own red-team raised about its 55021-55122 m°C reading on a
  4:31-4:42 uptime). The two runs' absolute thermal readings are **not comparable** to each other
  as a "M2 runs hotter" claim — different uptimes, different unaudited history — only the M2 vs M1
  CPU-percentage numbers (which are load-relative, not absolute-temperature) support that
  comparison.
- **Detections depend on the scene, and this run's scene was rich, not sparse.** Every frame had
  8-12 tracks (a person plus five recurring background objects — books, a suitcase, a chair, a
  refrigerator — that the stock M1 detector could never emit at all, since it only ever produces
  `person`/`face`). This is **not** a "worst case" or "typical case" number — it is what this one
  scene, on this one run, produced with the 0.15 floor live; a different scene (empty, or with
  different objects) would produce different track counts and label sets, exactly as M1's own
  empty-scene run produced zero.
- **The 0.15 floor is live, so the tracker sees many low-confidence boxes, and the tally's track
  counts reflect that.** Several of the recurring detections in the tally's first/last-5 lines sit
  well under 0.3 confidence (e.g. `"suitcase"` at conf 0.16-0.28 in various frames) — these are
  exactly the sub-`high_thr` (0.4) detections `track.low_thr`=0.12 was designed to admit into
  ByteTrack's second-pass association, now that M2's plugin floor (0.15) actually lets them
  through the post-process. The 8-12 tracks/frame in this run's tally is therefore inflated
  relative to what a naive "how many real objects are in this room" count would give — several of
  those ids are the same physical book/suitcase re-detected at fluctuating low confidence, not
  8-12 independent high-confidence objects. `min_hits`=2 (confirmed-track gate, unchanged from M1)
  is still the mechanism preventing single-frame noise from ever reaching `tracks[]`, but does
  nothing to suppress a *persistently* low-confidence real object from acquiring and keeping an id.
- **The letterbox pad is black (Y=0) on this board, versus grey 114 on the Pi's software
  letterbox — an unmeasured accuracy difference.** `hosts/hailo15l/README.md` §8 "Pad-colour
  observation" measured this directly (padding rows constant at `(0,0,0.0)` min/max/mean); the
  Pi's own yolo26m deployment (and its calibration/behaviour characterisation) was done against
  grey-padded input. Nothing in this run measures whether black vs grey padding changes detection
  behaviour near the letterbox boundary — flagged, not measured, here.
- **`age_ms` (836-892 ms) is far higher than M1's (32-125 ms) — root-caused and fixed, not left
  open.** See "ADDENDUM 2026-09-03 — snapshot-age regression: mechanism and fix" at the end of this
  section: a standing queue backlog (the camera's 30 fps sink0 feed vs the yolo26m HEF's ~25.74 fps
  ceiling) explains the gap, and the fix there is measured before (836-892 ms) and after (110-194
  ms) on this same board.
- **No coast/re-acquire exercise in this run.** Because the person never left the frame, this run
  adds nothing to the coast/re-acquire characterisation already recorded in the M1 section's
  owner-present addendum (`max_lost`=75, `reacq`=15, unchanged here) — it only confirms the locked
  track stayed stable and did not spuriously flip class or id while continuously visible under the
  new detector.
- **`dump_nv12` is configured but disabled** (`"path": ""`, `"frames": 0` in the config dump
  above) — it had no effect on this run's numbers; noted only because it appears in the config
  block quoted above and a reader might otherwise wonder.

### ADDENDUM 2026-09-03 — snapshot-age regression: mechanism and fix

**Mechanism — INFERRED FROM THE SDK HEADERS (`hailo_analytics/pipeline/core/queue.hpp:58`,
`hailo_analytics/pipeline/ai/ai_stage.hpp`, `hailo_analytics/pipeline/ai/postprocess_stage.hpp:74`),
NOT MEASURED PER STAGE.** The camera drives sink0 at 30 fps; the yolo26m HEF's own multi-context
compile bounds the detect stage at ~25.74 fps (this file's own "yolo26m from the Hailo model zoo"
section, `hailortcli benchmark` FPS: 25.97, and the M2 section's own `frames=` mean 25.7387). Every
queue between the camera and `det_sink` defaulted to BLOCKING, not leaky
(`pipeline/core/queue.hpp:58`'s `Queue` constructor default `leaky = false`), and each such queue is
only ever popped from at the detector's slower ~25.74 fps rate while the camera keeps pushing at 30
fps — so every one of these queues fills once at start-up and then stays full: detect's own input
queue (`set_queue_size(4)`, `ai_stage.hpp`'s `HailortAsyncStage`) + up to 4 in-flight jobs
(`set_job_limit(4)`) + the post stage's input queue (`postprocess_stage.hpp:74`'s builder default
`size_t queue_size = 5`, unset by this node) + `det_sink`'s own queue (1, already leaky) + the
medialib's sink0 buffer pool (`pool_max_buffers: 20`, `hosts/hailo15l/medialib/make_profile.py`) — a
standing backlog of frames waiting in FIFO order, not a per-stage processing-latency increase. This
is arithmetic inferred from reading the headers and the node's own stage-builder calls; no per-stage
queue-depth counter was read at runtime to confirm the backlog sits exactly where this reasoning
places it.

**Fix.** Two levers, both applied together (see git history on branch `feat/hailo15l-detector` for
this task's commits):
1. `hosts/hailo15l/medialib/make_profile.py` — the "Garuda" (M2) profile's sink0 `framerate` 30→25
   (matching the detector's own ceiling, so the medialib stops overproducing frames the detect stage
   can never keep up with) and `pool_max_buffers` 20→6 (less depth for the backlog to hide in even
   if it does form). The "GarudaYolov8n" rollback profile is untouched (the stock HEF matches the
   camera's 30 fps).
2. `services/garuda-perception/src/node_main.cpp` — detect's own queue `set_queue_size(4)`→`(2)`,
   and the post stage given `.set_queue_size_opt(1).set_leaky_opt(true)` (both exist on
   `PostprocessStageBuild::Builder`, confirmed in `postprocess_stage.hpp:118-119`).

**One planned sub-change was found IMPOSSIBLE on this board's currently-flashed image and was
dropped, not silently substituted.** The original plan also called for `detect->set_leaky(true)`
(`HailortAsyncStage` derives from `ThreadedStage`, whose `set_leaky(bool)` is declared public in
`pipeline/core/stage.hpp:256`). This is a real, exported symbol in the SDK's own (cross-compile-time)
`libhailo_analytics.so` — the cross-build linked cleanly — but the Hailo-15L SBC's DEPLOYED
`/usr/lib/libhailo_analytics.so.1.12.0` does not export it. Verified directly on the board:
```
$ ssh root@10.0.0.1 'nm -D --defined-only /usr/lib/libhailo_analytics.so.1.12.0 2>/dev/null | c++filt | grep -i "Queue::set_leaky\|ThreadedStage::set_leaky"'
(no output, exit code 1)
```
every other `ThreadedStage` method (`add_subscriber`, `set_end_of_stream`, `send_to_subscribers`,
`push`, `stop`, `start`, `add_queue`, ...) IS present — only `set_leaky` (and even the more basic
`Queue::set_leaky(bool)`) is missing, so this is a header/runtime version skew on this board's
image, not a naming difference (rule: "If a name differs in the headers, use the header's name and
say so" does not apply here — the name is identical; the symbol is simply absent from the deployed
`.so`). Deploying the change once *without* dropping the call reproduced the exact failure, captured
verbatim from the board's own log:
```
Thu Sep  3 09:26:16 UTC 2026 starter begin (pid 8661)
/opt/garuda/bin/garuda-perception: symbol lookup error: /opt/garuda/bin/garuda-perception: undefined symbol: _ZN15hailo_analytics8pipeline13ThreadedStage9set_leakyEb
Thu Sep  3 09:26:17 UTC 2026 node exited during startup (attempt 1/10)
```
(repeated for 10 attempts, then `node failed to start after 10 attempts`). The `detect->set_leaky(true)`
call was removed (the `set_queue_size(2)` change on the same stage does NOT need this symbol — it is
a constructor-time parameter, not a post-hoc setter — and was kept); this repo does not have write
access to `/usr/lib/*` on the board (writes are scoped to `/opt/garuda`, the init script, rc links,
`/var/run`, `/tmp`) so replacing the board's `libhailo_analytics.so` was not an option considered.
Rebuilt and redeployed with the call removed; the node started cleanly on the next attempt (see the
after-measurement below).

**Before/after measurement, same board, same node binary otherwise.** Both captures used the same
script as this section's own SSE tally (`bench/evidence/2026-09-03-m2-sse-tally.txt`'s
`tally_sse_m2.py`), run for ≥60 s (not the file's own 600 s M2 run) per this task's instructions.

*Before (baseline, node commit `8c82367`/`25d7bd1` as already deployed and measured earlier in this
file's M2 section — not redeployed for this baseline capture):*
```
$ cd <scratchpad>/m2-fix/before
$ nohup curl -s -m 65 -o base_sse.txt http://10.0.0.1:8098/api/events > curl.log 2>&1 &
launched pid 834466
```
started 2026-09-03 09:14:02 UTC, ran the full 65 s. Tally (`python3 tally_sse_m2.py base_sse.txt`):
```
total data: lines = 647
frames with non-empty tracks = 647
frames with >=2 tracks = 647
frames with lock.coasting == true = 0
distinct lock.id values seen = [377]
distinct labels seen across all tracks = ['book', 'cell phone', 'person', 'refrigerator', 'suitcase']
age_ms count=647 min=847 max=887
```
Scene: **person present** (track id 224, label `person`, conf ~0.96-0.97 throughout; the lock had
acquired a different object, `cell phone` id 377, first-seen in this window — the person itself was
tracked but not the locked target). Node's own `frames=` rate, same log line as the M2 run above,
tail sample taken at the same time as the SSE capture:
```
$ ssh root@10.0.0.1 'tail -n 40 /var/log/garuda-perception.log'
[40 lines of frames=NNN fps=NN.N]
$ python3 -c "... mean of the 40 fps values ..."
n=40 min=25.7 max=25.8 mean=25.7400
```
MJPEG count over 30 s:
```
$ curl -s -m 30 http://10.0.0.1:8098/stream | grep -c --binary-files=text "Content-Type: image/jpeg"
386
```

*After (this task's fix, cross-built, deployed via `hosts/hailo15l/deploy.sh`, node restarted —
new pid 9034; one earlier deploy of the fix, still containing the `detect->set_leaky(true)` call,
crash-looped as shown above and was superseded by this one):*
```
$ hosts/hailo15l/deploy.sh
Thu Sep  3 09:29:43 UTC 2026
garuda-perception stopped
yolo26m HEF already on board and md5-verified, skipping copy
garuda-perception stopped
garuda-perception: starting in background (log: /var/log/garuda-perception.log)
/var/run/garuda-perception.pid running (pid 9034)
/var/run/garuda-mono-shim.pid running (pid 9097)
/var/run/garuda-perception-starter.pid finished
deployed to root@10.0.0.1
```
Plugin init line + steady `frames=` lines confirming the fix took effect (mean dropping from 25.74
to ~25.0 fps, matching the profile's new `framerate: 25`, not ~25.7 — proof the media library
honoured the per-stream framerate rather than ignoring it):
```
$ ssh root@10.0.0.1 'tail -n 40 /var/log/garuda-perception.log'
yolo26_post: conf=0.150 iou=0.50 net=640x640 frame=1280x720 mode=letterbox prefix=yolo26m/ dump=/0
garuda-perception running (feed 8971, cmd 8972)
Thu Sep  3 09:29:52 UTC 2026 starter done: node 9034, shim 9097
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
frames=227 fps=22.7
frames=251 fps=25.1
frames=251 fps=25.1
[...]
```
Full post-redeploy `frames=` window (`awk '/starter begin (pid 9030)/{f=1} f' | grep '^frames='`):
```
n=23 min=22.7 max=25.1 mean=24.9565
```
(**min=22.7** is the first post-start line, the same startup-transient pattern the M0/M1/M2 sections
above already documented; excluding just that one line, n=22 min=24.9 max=25.1 **mean=25.0591** —
essentially exactly the profile's configured 25 fps.)

SSE capture, same command and script as the baseline, run after the node had settled (~90 s after
restart):
```
$ nohup curl -s -m 65 -o after_sse.txt http://10.0.0.1:8098/api/events > curl.log 2>&1 &
launched pid 840510
```
started 2026-09-03 09:31:41 UTC, ran the full 65 s. Tally:
```
total data: lines = 647
frames with non-empty tracks = 647
frames with >=2 tracks = 647
frames with lock.coasting == true = 0
distinct lock.id values seen = []
distinct labels seen across all tracks = ['book', 'refrigerator', 'suitcase']
age_ms count=647 min=110 max=194
```
Scene: **no person present** this time (`api/state` around this capture showed `"lock":{"class":
"person","coasting":false,"id":null}` — no track currently satisfies the default `person` target —
and the labels list above confirms no `person`/`cell phone` track appeared in any of the 647
frames). This is a DIFFERENT scene from the baseline capture (the owner was in view for the baseline,
not for this one, ~17 minutes later) — flagged in the red-team below, not glossed over.

MJPEG count over 30 s (control — sink1 is untouched by this fix, expected unchanged within noise):
```
$ curl -s -m 30 http://10.0.0.1:8098/stream | grep -c --binary-files=text "Content-Type: image/jpeg"
375
```
(386 before vs 375 after — a ~3% difference, within normal capture-to-capture noise for a
15 fps-capped, network-served MJPEG stream; sink1's own `framerate`/`pool_max_buffers` were not
touched by either lever above.)

**Result: `age_ms` max dropped from 887 ms to 194 ms (min 847→110 ms), a ~4.6x reduction.** This is
close to, but not strictly inside, the "~150 ms" acceptance target in this task's brief — 194 ms is
44 ms (~29%) above it. The fix was NOT a "barely moves" result (the brief's fallback condition for
reverting the profile numbers and isolating the two levers), so per the brief's own instructions both
levers were kept together and this was not decomposed further; a stricter bound would need a third,
unspecified lever (e.g. a smaller `pool_max_buffers` than 6, or a smaller detect/post queue depth
than 2/1) that was not part of this task's mandated numeric changes and was not tried.

**Throughput cost.** Baseline `frames=` mean 25.7400 (n=40) vs after-fix steady-state mean 25.0591
(n=22, excluding the startup transient) — a ~2.6% throughput reduction, consistent with capping
sink0 at the profile's new 25 fps rather than letting it run at the camera's native 30 fps (which the
detector could never actually keep up with anyway; the effective end-to-end detection rate barely
moved, since the detector's own ceiling was already ~25.74 fps).

**Red-team (rule 9).**
- **Single scene each side, and the two scenes DIFFER** (person present, baseline; no person, after)
  — see above. `age_ms` is the ISP-timestamp-to-served-snapshot age, which this task's own mechanism
  argument ties to QUEUE DEPTH (a function of framerate mismatch and buffer/queue sizes), not scene
  content (track count, tracked labels) — so the scene change is not expected to explain the ~700 ms
  swing by itself, but no isolated same-scene before/after pair was captured to rule out a
  scene-dependent contribution entirely.
- **≥60 s captures, not the 600 s the M1/M2 sections used.** This task's brief specifically calls for
  a ≥60 s capture, not a repeat of the full 10-minute runs above; 647 SSE samples per side is far
  fewer than the M2 section's 5,969, so the min/max range here is a smaller sample and could miss a
  rarer, larger age_ms excursion that a longer run would catch.
- **The queue-depth arithmetic above is INFERRED FROM THE SDK HEADERS, not measured per stage** — no
  runtime instrumentation was added to read any individual queue's actual occupancy; the mechanism
  argument (which queue fills, by how much, in what order) is a plausible reconstruction from reading
  `queue.hpp`, `ai_stage.hpp`, and `postprocess_stage.hpp`'s declared defaults and this node's own
  builder calls, not a profiled decomposition.
- **The board's `libhailo_analytics.so.1.12.0` lacking `ThreadedStage::set_leaky`/`Queue::set_leaky`
  was discovered by reproducing a crash, not anticipated** — this means the deployed fix relies on
  fewer levers (queue sizes + profile framerate/pool) than the mechanism section originally called
  for (which also wanted detect's own queue made leaky); the ~4.6x improvement was achieved without
  that lever, which is worth noting as evidence the framerate/pool_max_buffers change on the profile
  did most of the work (the `frames=` mean dropping to ~25.0 exactly, not ~25.7, supports this: the
  medialib itself is now the rate limiter, not just a blocking queue backing up behind the detector).
- **Board state was not reset between baseline and after** (same board uptime lineage, ~18 h up
  throughout; thermal 68477-69236 m°C across both captures, not meaningfully different) — thermal/
  load history is not a plausible confound for a queue-depth effect this large and this immediate
  (it changed within seconds of the redeploy, not gradually), but is noted for completeness.

## 2026-09-03 — Hailo-15L SBC: yolov8m A/B for small-object (cell phone) tracking

Owner's hypothesis (in session, ~15:45 local): the tracking trouble with a hand-held phone comes from
the slow yolo26m; a faster yolov8-class model should track better. Test: same 90 s hand-held phone
routine (still 5 s; slow side-to-side 10 s; fast 10 s; out of view 3 s; back, still 5 s), owner at
the bench, three configurations, each captured with the PC-side timestamped SSE script
(`bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py`, shim cap 10 Hz). Branch
`feat/hailo15l-yolov8-ab`. Node binary = the M2 head build (952a636).

Zoo HEF fetched: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/yolov8m.hef`,
18558976 bytes, md5 `8eef4ca967752c54799dd2fb5cd14dcf`, on the board at
`/opt/garuda/models/yolov8m_hailo15l_v5.3.0.hef`. `hailortcli parse-hef`, verbatim:

```
HEF Compatible for: HAILO15L
HEF Compiler Version: 5.3.0
Network group name: yolov8m, Multi Context - Number of contexts: 13
    Network name: yolov8m/yolov8m
        VStream infos:
            Input  yolov8m/input_layer1 UINT8, NV12(320x640x3)
            Output yolov8m/yolov8_nms_postprocess FLOAT32, HAILO NMS BY CLASS(number of classes: 80, maximum bounding boxes per class: 100, maximum frame size: 160320)
            Operation:
                Op YOLOV8
                Name: YOLOV8-Post-Process
                Score threshold: 0.200
                IoU threshold: 0.70
                Classes: 80
                Max bboxes per class: 100
                Image height: 640
                Image width: 640
```

`hailortcli benchmark /opt/garuda/models/yolov8m_hailo15l_v5.3.0.hef -t 15` with the service stopped,
verbatim (thermal in milli-°C before/after):

```
== Thu Sep  3 10:20:41 UTC 2026 thermal_mC:54920 uptime:up 19:05,  0 users,  load average: 2.02, 2.30, 2.33
yolov8m: FPS: 39.67
== thermal after: 63266
```

Configuration for the A/B: `config/perception-yolov8m.json` (stock `libyolo_hailortpp_post.so` with
`config/yolov8m_post.json` = 81 labels "unlabeled"+COCO-80, `detection_threshold` 0.15; the HEF's own
baked NMS carries score 0.20 / IoU 0.70 — the effective floor is whichever HailoRT honours, unmeasured),
media-library profile `GarudaYolov8m` (sink0 640x640 STRETCHED, framerate 30, pool 6; stretch, not
letterbox, because the stock post-process normalises to the network input and the node's `xmin*frame_w`
mapping is only valid for a stretch), same tracker parameters as the M2 config (75/15).

Three runs, one per configuration, same routine, tallied from the captures (cell-phone tracks only;
"no-phone states" = SSE snapshots with no cell-phone track; "coasting entries" = phone tracks with
`coasting: true` summed over snapshots; x range = min/max of phone box x in a 0–1280 frame; "longest
lock" = the longest run of snapshots with an unchanged non-null `lock.id`), verbatim output of the
comparison script:

```
yolo26m 75/15    n=897  90.0s | phone ids 12 | lock ids 10 | no-phone states 269 (29%) | coasting entries 356 | x range [-11478,  2956] | live conf mean 0.67 | box w mean 103 px | longest lock  15.1s | age max 194
yolo26m 25/5     n=897  90.0s | phone ids 22 | lock ids 16 | no-phone states 243 (27%) | coasting entries 250 | x range [ -2608,  6630] | live conf mean 0.65 | box w mean  99 px | longest lock  23.0s | age max 193
yolov8m 75/15    n=897  90.0s | phone ids 35 | lock ids 11 | no-phone states 312 (34%) | coasting entries 718 | x range [ -4244,  8117] | live conf mean 0.65 | box w mean 103 px | longest lock  34.0s | age max 151
```

Reading: the detector is not the cause. The phone (about 100 px wide in the 1280-wide frame, so 50 px
in the 640 network input) is undetected in 27–34% of states with either model; every gap becomes a
coasting box whose x leaves the frame by thousands of pixels in all three runs (the tracker's velocity
is the raw displacement between two matches applied once per frame — mono's own rule, amplified by
gaps); each flight ends in a new id. yolov8m holds the lock longest (34.0 s) and has the lowest
snapshot age (151 ms max) but the most phone ids (35) and coasting entries (718).

Red-team (rule 9): three runs of one routine paced by the owner, not a timer — per-phase durations
differ between runs; the owner's distance and motion are not reproducible; the phone size varies
(box w mean 99–103 px); yolov8m ran on a STRETCHED input (aspect distorted 1.78:1) while yolo26m ran
letterboxed — this alone could change small-object recall; the NMS floor for yolov8m may be 0.20
(baked) rather than the configured 0.15; the person track was stable in all runs (not tallied here).
`TBD-bench`: the same routine on the Pi (mono) — the owner reports it worked well there; not measured.

## 2026-09-03 — Hailo-15L SBC: Kalman tracker engine (SDK TrackerStage) vs mono's tracker — phone and person routines

Owner at the bench through the 2026-09-03 afternoon/evening running the SDK Kalman engine
(`hosts/hailo15l/README.md` §9) against the phone routine from the A/B section above and a new
person (walk) routine, across several sessions as the engine gained fixes. All captures: PC-side
wall-clock-timestamped SSE (`bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py`
against `http://10.0.0.1:8098/api/events`, shim cap 10 Hz). This section tallies every session with
two newly written scripts (the yolov8m A/B section's own comparison script was a one-off, not
checked in) — `bench/evidence/2026-09-03-tracker-engine-captures/compare_phone_runs.py` and
`compare_person_runs.py` — verified to reproduce the A/B section's own three-run numbers bit-for-bit
except a systematic +0.1 s on "longest lock" (timestamp-interval vs frame-count method; not
investigated further) before being trusted on the new captures.

Conditions, one row per capture, node binary = the commit noted (each is a C++ change requiring a
rebuild+redeploy; timestamps below are commit-author IST, matched against each capture's local time
in session):

| capture | engine / detector | gates | classes | node commit | local time |
|---|---|---|---|---|---|
| `phone.txt` | mono / yolo26m, letterboxed | `max_lost=75 reacq=15` | n/a | pre-A/B baseline | 15:26 |
| `phone25.txt` | mono / yolo26m, letterboxed | `max_lost=25 reacq=5` (mono's original) | n/a | pre-A/B baseline | 15:30 |
| `phone_y8m.txt` | mono / yolov8m, stretched 640×640, stock post-process | `max_lost=75 reacq=15` | n/a | `68ccd3c` | 15:52 |
| `phone_kalman.txt` | **hailo** / yolov8m, stretched | `kalman_distance=0.7 iou=0.8 init_iou=0.9 keep 5/5/75` | **all (-1)** | `4ac8b9f` | 16:41 — **DISCARDED: routine not performed** |
| `phone_kalman2.txt` | **hailo** / yolov8m, stretched | `kalman_distance=0.7 iou=0.8 init_iou=0.9 keep 5/5/75` | **all (-1)** | `4ac8b9f` | ~17:12 |
| `phone_kalman_loose.txt` | **hailo** / yolov8m, stretched | `kalman_distance=0.9 iou=0.4 init_iou=0.6` (scratchpad-only override, not committed) | **all (-1)** | `4ac8b9f` | 17:14 |
| `person_kalman.txt` | **hailo** / yolov8m, stretched | same as `phone_kalman2` | **all (-1)** | `4ac8b9f` | 17:21 |
| `person_kalman_cls.txt` | **hailo** / yolov8m, stretched | same gates | **person only (`classification_id=1`)** + majority-vote label fix | `87dd48d` | 17:40 |
| `person_kalman_cls2.txt` | **hailo** / yolov8m, stretched | same gates | person only | `87dd48d` | 17:46 |
| `person_kalman_cls3.txt` | **hailo** / yolov8m, stretched | same gates | person only | `87dd48d` (branch HEAD) | 20:57 |

Config source for each row: `services/garuda-perception/config/perception-yolov8m.json` at the
commit noted (`git show <commit>:services/garuda-perception/config/perception-yolov8m.json` —
verified: no `tracker` key at `68ccd3c`; `tracker.engine:"hailo"` with no `classification_id` key
at `4ac8b9f`; `classification_id:1` added at `87dd48d`, matching the deployed HEAD config verbatim).
The loose-gate row is the only one run from a scratchpad-only config override
(`GARUDA_PERCEPTION_CONFIG` pointed at a file outside the repo — never committed).

2026-09-04 fix round (I3): `phone_kalman.txt`, `phone_kalman2.txt`, `phone_kalman_loose.txt`, and
`person_kalman.txt` — the four captures referenced only by scratchpad path when this section was
first written — are now committed gzipped under
`bench/evidence/2026-09-03-tracker-engine-captures/` as `<name>.txt.gz`; the table above still uses
each capture's bare logical name (matching the comparison scripts' own labels and the prose below),
but every one of those four now resolves to a committed `.gz` file, not a scratchpad path.
`compare_phone_runs.py`/`compare_person_runs.py` open `.gz` inputs transparently.

`phone_kalman.txt` (started 16:41:19 local, 90 s) is **discarded: routine not performed (no
phone/person tracks in 897 snapshots)** — controller context, stated verbatim as such: the owner
had not yet started the phone routine during this capture (it ran ~30 min later, as
`phone_kalman2.txt`), so it contains no phone and no person tracks — the exact same situation as
`person_kalman_cls2.txt` below. Verified independently in this fix round
(`python3 -c` over the file): `n=897 nulls=897 lockclasses={'person'} labels seen={'tv',
'backpack', 'toilet', 'chair', 'suitcase', 'handbag'}` — no `cell phone`, no `person` label
anywhere in the capture, `lock.id` null on every single snapshot. Committed gzipped (2026-09-04 fix
round, I3): `bench/evidence/2026-09-03-tracker-engine-captures/phone_kalman.txt.gz` (352,446 bytes,
`ls -l`); `compare_phone_runs.py` now opens `.gz` inputs transparently (`gzip.open`), so this row is
reproduced straight from the committed file, not a scratchpad path.
Kept in the phone table below (row 4 of 6) precisely because it tallies cleanly to all-zero/n-a
rather than being silently dropped — `compare_phone_runs.py` was made tolerant of a capture with
zero cell-phone tracks for this fix round (prints `n/a` for x range / live conf mean / box w mean
instead of crashing on an empty-list mean).

Aside, unrelated to the 2026-09-03 session but noted here as current board state — controller's
morning check, 2026-09-04 08:37, verbatim:
```
$ ssh root@10.0.0.1 'tail -1 /var/log/garuda-perception.log; uptime | sed "s/.*up/up/"; cat /sys/class/thermal/thermal_zone0/temp; free -m | sed -n 2p'
frames=301 fps=30.1
up 1 day, 11:51,  0 users,  load average: 1.67, 1.78, 1.85
85069
Mem:            1913         406        1057          19         449        1410
```
Board up 1 day 11:51, 85.07 °C (hot; no cooling change made — CLAUDE.md §2, this board's cooling is
whatever the stock SBC provides, not evaluated here), node still running at 30.1 fps, 406 MB used /
1913 MB total.

### Phone routine — 6 rows, `compare_phone_runs.py`, verbatim

```
yolo26m 75/15    n=897    90.0s | phone ids  12 | lock ids  10 | no-phone states  269 (29%) | coasting entries  356 | x range [ -11478,    2956] | live conf mean 0.67 | box w mean 103 px | longest lock  15.2s | age max  194
yolo26m 25/5     n=897    90.0s | phone ids  22 | lock ids  16 | no-phone states  243 (27%) | coasting entries  250 | x range [  -2608,    6630] | live conf mean 0.65 | box w mean  99 px | longest lock  23.1s | age max  193
yolov8m 75/15    n=897    90.0s | phone ids  35 | lock ids  11 | no-phone states  312 (34%) | coasting entries  718 | x range [  -4244,    8117] | live conf mean 0.65 | box w mean 103 px | longest lock  34.1s | age max  151
hailo kalman (pre-routine) n=897    90.0s | phone ids   0 | lock ids   0 | no-phone states  897 (100%) | coasting entries    0 | x range [    n/a,    n/a] | live conf mean  n/a | box w mean n/a px | longest lock   0.0s | age max  152
hailo kalman default n=894    89.7s | phone ids  37 | lock ids  15 | no-phone states   29 ( 3%) | coasting entries  793 | x range [    263,    1097] | live conf mean 0.47 | box w mean 138 px | longest lock  15.2s | age max  157
hailo kalman loose n=1494  150.0s | phone ids 111 | lock ids  36 | no-phone states  281 (18%) | coasting entries 2732 | x range [     73,    1245] | live conf mean 0.49 | box w mean 104 px | longest lock  56.3s | age max  156
```

`hailo kalman (pre-routine)` (`phone_kalman.txt`) is the discarded row above — 897/897 no-phone
states, all-zero/n-a everywhere, because the routine had not started (verified: zero `cell phone`
and zero `person` labels anywhere in the capture, see the discard note above). `hailo kalman loose`
ran 150.0 s of capture, not 90.0 s like the other rows — flagged in the red-team below, not
normalised away.

### Person routine — 4 rows, `compare_person_runs.py`, verbatim

```
hailo kalman all-classes (walk) n=1494  150.0s | person ids  22 | live-person states 1493 (99%) | no-person states    1 | lock coasting   37 | lock None    0 | x range [     -4,    1147] | age max  157
hailo kalman all-classes (walk) lock id sequence: 1 -> 234 -> 284 -> 234 -> 285 -> 301
hailo kalman person-only (sit) n=1495  150.0s | person ids   1 | live-person states 1495 (100%) | no-person states    0 | lock coasting    0 | lock None    0 | x range [    244,     313] | age max  152
hailo kalman person-only (sit) lock id sequence: 1
hailo kalman person-only (empty) n=1495  150.0s | person ids   0 | live-person states    0 ( 0%) | no-person states 1495 | lock coasting    0 | lock None 1495 | x range [    n/a,    n/a] | age max  151
hailo kalman person-only (empty) lock id sequence: None
hailo kalman person-only (walk-out) n=1794  180.1s | person ids   2 | live-person states  208 (11%) | no-person states 1561 | lock coasting   25 | lock None 1561 | x range [    451,    1202] | age max  151
hailo kalman person-only (walk-out) lock id sequence: 375 -> None
```

`person_kalman_cls2.txt` ("empty") is a discarded/null result — zero person tracks the entire
150.0 s (owner not in view for this capture) — kept in the table only to show the profile behaves
correctly when there is nothing to track (100% no-person states, lock None throughout), not as a
tracking measurement. (2026-09-04, M6 fix: the "empty" row's x range was previously printed as a
fake `[0, 0]` — `compare_person_runs.py` now prints `n/a` for a capture with zero person-labelled
tracks, matching `compare_phone_runs.py`'s existing convention; regenerated verbatim above and in
`bench/evidence/2026-09-03-tracker-engine-captures/person_tally.txt`, no other row changed.)

### Findings

- **One class-agnostic tracker, one-to-one assignment, fragments ids on class flicker (corrected
  2026-09-04 — this bullet replaces an earlier, wrong "per-class association" claim; the JDE tracker
  source, `src/tracking/jde_tracker/`, has no class anywhere in its association).** The tracker runs
  one global one-to-one LAPJV assignment across every detection in a frame regardless of label, so
  with `classification_id=-1` an overlapping other-class detection on the same physical object
  (chair/suitcase/tv boxes on a person) competes for that object's track slot in the SAME assignment
  problem as the correct detection, and can steal it (wrong-class box keeps the id) or split it
  (real detection goes unmatched, mints a new id); `classification_id` fixes this not by enabling
  per-class matching but by removing the competition — only that one class's detections are ever
  handed to the tracker at all. `phone_kalman2.txt` and `person_kalman.txt` both ran with all
  classes tracked at once (`classification_id` absent → node default `-1`,
  `hosts/hailo15l/README.md` §9). Verbatim (`python3 -c` over each capture, counting distinct
  `lock.class` values and `lock.id is None` states — lock class set and null-lock count per capture,
  one line per file):
  ```
  phone_kalman2.txt        n=894  null lock=381  lock classes seen={'knife', 'cell phone', 'tv'}
  person_kalman.txt        n=1494 null lock=0    lock classes seen={'person'}
  person_kalman_cls.txt    n=1495 null lock=0    lock classes seen={'person'}
  person_kalman_cls2.txt   n=1495 null lock=1495 lock classes seen={'person'}
  person_kalman_cls3.txt   n=1794 null lock=1561 lock classes seen={'person'}
  ```
  `phone_kalman2.txt`'s lock class flips across `{cell phone, knife, tv}` with `lock.id` null for
  381 of 894 states; `person_kalman.txt`'s lock class never leaves `person`, but its lock id
  sequence above (`1 -> 234 -> 284 -> 234 -> 285 -> 301`) is 5 jumps in one 150 s walk with
  `lock None` never occurring (0 states) — the lock kept moving to a *different* live id rather than
  going empty, consistent with the class-agnostic assignment losing the person's detection to a
  competing class's box for one frame (README §9's "Field finding") rather than the label merely
  flickering on a surviving id (the separate bug `18af174`'s majority-vote fix addresses). Sharper
  evidence of the churn, verified independently in the 2026-09-04 fix round (`python3 -c` over
  `person_kalman.txt`): **22 distinct person-labelled ids appear within just the first 61 s** of
  that capture's 150 s span, with no new id in the remaining ~89 s — the churn is front-loaded, not
  spread evenly through the walk. Both captures predate `18af174`/`87dd48d` (commit `4ac8b9f` was on
  the board for both — table above) — i.e. these are exactly the two captures that motivated those
  two fixes, not a regression found afterward.
- **Loose gates (`kalman_distance=0.9 iou=0.4 init_iou=0.6`) churn more per unit time than the
  default gates**, even though its capture ran longer (150.0 s vs 89.7 s, so raw counts are not
  directly comparable): phone ids/s 0.74 (111/150.0) vs default's 0.41 (37/89.7); lock ids/s 0.24
  (36/150.0) vs 0.17 (15/89.7); coasting entries/s 18.2 (2732/150.0) vs 8.8 (793/89.7); no-phone
  states 18% vs 3%. The one column that is nominally larger for loose gates in absolute terms —
  "longest lock" (56.3 s vs 15.2 s) — is not read as an improvement: with looser association
  thresholds (a wider Kalman-distance gate, a lower IoU floor) the tracker accepts weaker matches,
  so a longer unchanged-id run is at least as consistent with a sticky mismatch as with a truly
  stable lock; this run is not annotated with ground truth, so which it is stays unmeasured. This is
  one board-only setting, not a sweep (red-team below).
- **Person-only classification (`classification_id=1`) plus the majority-vote label fix produces
  exactly one id while the target is present and static:** `person_kalman_cls.txt` — 1 person id,
  100% live-person states, 0 lock-None states, 150.0 s. This is the intended demo-style behaviour
  (README §9): everything that is not `person` is still detected but never becomes a track.
- **The phone montage suggests why the Pi's own phone routine "worked well" (owner report, prior
  TBD-bench above) while this board's does not, but this is the controller's inference from a
  detector-input dump, not a measurement made on the Pi.** Source: the 300-frame raw NV12 dump
  (`lbdump.nv12`, 184,320,000 bytes, 640×640, yolov8m stretched profile, owner moving the phone) and
  `lb_montage.png` (a 2×2 montage of its frames 30/90/150/210) both kept in the scratchpad — neither
  copied in (2,170,543 bytes for the montage, over this section's 2 MB copy-in limit; the raw dump
  is 184 MB) —
  `/tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/2a21f19e-5fb6-4e5f-9942-59eeea5039f4/scratchpad/coast/lb_montage.png`
  and `.../lbdump.nv12`. Committed instead:
  `bench/evidence/2026-09-03-tracker-engine-captures/inspect_lbdump.py` (reads the Y plane of frames
  30/120/240 of the dump), independently re-run in this fix round against the same dump and matched
  the controller's original output exactly (`inspect_lbdump_output.txt`):
  ```
  frames 300
  30 Y mean content rows 140-499: 104.1, padding row0: 223, min/max content 0/253
  120 Y mean content rows 140-499: 104.0, padding row0: 227, min/max content 0/253
  240 Y mean content rows 140-499: 104.0, padding row0: 228, min/max content 0/252
  ```
  Caveat on "rows 140-499": that band is the letterbox *content* band of the M2 (yolo26m) profile,
  used here as a convenient fixed slice — but this dump is from the **stretched** yolov8m profile,
  which has no letterbox bars, so `padding row0` (223, 227, 228 — clearly not near-zero) is actually
  content too; the printed mean is over the middle rows of a fully stretched frame, not a
  letterboxed one. The "~40 px" phone width itself is **the controller's visual estimate from
  `lb_montage.png`, not a measurement** — no bounding box or pixel count was extracted from the
  dump. With that caveat: the phone reads as small and dark in the montage (black-backed, fingers
  over most of it) against a mid-grey scene (Y mean ~104). The CM3's field of view on the Pi is
  narrower than this board's wide 4K Theia lens at the same subject distance, so the same phone
  would occupy more of the Pi's frame — the controller's stated reason the two boards' behaviour
  differs is optical, not a tracker-logic difference, but this was not cross-measured (no matching
  Pi dump exists in this session, and the phone-width claim above is a visual estimate, not
  measured).
- **AREA interpolation is unsupported on this board's DSP resize path** — unrelated to the tracker
  engine itself but hit again while working this branch's medialib profile
  (`hosts/hailo15l/medialib/make_profile.py`, tried and reverted 2026-09-03), quoted verbatim from
  that file's comment:
  ```
  [hailodsp] [error] [resize.cpp:980] [dsp_telescopic_multi_crop_and_resize_perf] Error:
  Interpolation type (2) not supported
  ```
  and the pipeline produced no frames while it was selected (no `frames=` log line, `/api/state`
  stuck at "no snapshot yet"). `hosts/hailo15l/README.md` §6 "Resize interpolation method" has the
  full writeup; noted here because it is the same DSP the owner's proposed zoom-window follow
  approach (`docs/decisions.md` below, spec §8.1 M5) would depend on.

Red-team (rule 9): every routine (phone and person/walk) was paced by the owner, not a timer —
per-phase durations and distances are not reproducible across captures, and the "walk" and
"phone" routines were each run once per configuration, not repeated; captures happened across a
single afternoon/evening (15:26–20:57) with unrecorded and presumably changing light; two of the
four person captures are not informative as *tracking* measurements — `person_kalman_cls.txt` is a
static sit (1 id, no motion to track) and `person_kalman_cls2.txt` has no person in view at all
(discarded above) — leaving only `person_kalman_cls3.txt` (present 0–21 s, then walked out and did
not return) as a person-only capture with any motion, and even that is an exit, not a full walk;
single scene throughout (this bench, these furnishings); the SDK Kalman tracker's internal
association math beyond the mechanism now read from its source (`src/tracking/jde_tracker/`: one
class-agnostic tracker, one-to-one LAPJV assignment across every detection regardless of label,
corrected 2026-09-04 — see the Findings bullet above and `hosts/hailo15l/README.md` §9; `std::map`
auto-vivify on the setters) — the exact LAPJV cost weighting itself — is not ours to inspect
further, so "why" a specific id fragments is inferred from the association-vs-flicker pattern in the
data plus the now-confirmed class-agnostic-competition mechanism, not from stepping the SDK's code
line by line; the loose-gate row is one hand-picked alternative setting, not a sweep, and its capture
ran at a different duration than every other row (flagged above, not corrected for beyond the
per-second rates given); the phone-vs-CM3-FOV explanation above is an inference from a still-frame
montage, not a controlled two-board comparison; **frozen coasting hides motion during gaps by
design** (`HailoTrackAdapter::update()` freezes a coasting entry's box at its last-seen value,
README §9) — so "coasting entries" and "longest lock" measure how long an id/box survives a gap,
not how well the target was tracked *during* the gap, and a long "longest lock" can include long
frozen stretches where the box was simply not moving with the target; **`keep_lost_frames=75`
(SDK) and mono's `max_lost=75` (frames) are numerically equal but their semantics are not shown
equivalent** — one is the SDK's own internal keep/re-association window (implementation and
threshold behaviour not inspected beyond the auto-vivify and class-agnostic-assignment facts already
read from source), the other is mono's ByteTrack coast counter; matching the number does not
establish the two engines coast the same way, and this was not tested (e.g. by comparing coast
survival at gap lengths near 2.5 s across both engines under identical conditions); **the yolov8m
rows (all `hailo`-engine rows, plus `phone_y8m.txt`) run on a STRETCHED 640×640 input while the
yolo26m rows are letterboxed** — already flagged in the yolov8m A/B section above for the
mono-engine comparison, and it applies here too: aspect distortion could change small-object recall
independently of which tracker engine is in front of it, so the phone table's yolo26m-vs-hailo-engine
comparison carries the same detector-input confound as the yolo26m-vs-yolov8m one. **Undisclosed
confounds found in the 2026-09-04 review (I4):** the mono rows in the yolov8m A/B section above ran
`track.min_hits 2` plus ByteTrack's own `high_thr 0.4` birth gate, while every hailo-engine row here
ran `min_hits 1` with no confidence gate on a new track's birth, so the "no-phone states" column is
not an apples-to-apples comparison between engines — the live-conf mean gap (0.47 hailo vs 0.65
mono) is the fingerprint of that gate difference, not necessarily a detection-quality one. Separately,
every hailo-engine row in this section was captured before I1's `keep_tracked_frames` fix
(2026-09-04, `hosts/hailo15l/README.md` §9), so up to 5 frames per real gap were silently re-emitted
as live rather than counted as coasting — this section's "coasting entries" and "no-phone/no-person
states" columns for the hailo rows undercount real gaps relative to what the fixed config would now
report.

`TBD-bench`: a genuine walking-person routine captured under the person-only (`classification_id=1`)
profile — every capture taken under that profile so far is either static (`person_kalman_cls.txt`),
empty (`person_kalman_cls2.txt`), or a one-way exit (`person_kalman_cls3.txt`), so "does the
person-only profile hold an id through a real walk, coast, and return" is unanswered. The Pi's own
phone run (mono engine, Hailo-10H) remains `TBD-bench` from the A/B section above — still not run.

## 2026-09-04 — Hailo-15L SBC: F1 lock core (time-based locked-target tracking) — harness built, on-board run pending

Offline half of Task 3 of the F1 lock-core plan (`docs/superpowers/plans/2026-09-04-hailo15l-lock-core.md`,
`.superpowers/sdd/2026-09-04-hailo15l-lock-core/task-3-brief.md`). The board has been unreachable
since before this task started (link lost 2026-09-04 09:17:52 per the owner, `hosts/hailo15l/README.md`
§10 "Verification", last checked by Task 2 at 2026-09-04 10:37:37 IST — not re-checked in this task,
per this task's own instruction not to touch the board) — so this entry records the harness and
routines built, with every board-derived number `TBD-bench`, not a live run.

### Setup

- **Branch/commit:** `feat/hailo15l-kalman-tracker`, HEAD `0a138c3`. F1 lock-core commits (Task 1 core
  library + Task 2 node integration, in order): `e06a78e` (LockCore: time-based locked-target tracker
  with guarded re-acquisition and frozen output), `fa71db9` (Ruling 1: white-noise-acceleration gate),
  `c2ee44b` (Ruling 2: cap the gating variance), `6284b93` (25/30 fps-equivalence test coverage),
  `777e826` (LockCore wired into the node — time-based lock states published, resolver hands over the
  pick, prediction never published), `0a138c3` (Ruling 5: click-diff hand-over locks the clicked id's
  own live Obs). Full detail: `.superpowers/sdd/2026-09-04-hailo15l-lock-core/task-1-report.md` and
  `task-2-report.md`. **Fix round 2 (the final-fix wave, below) adds four more commits on the same
  branch** — the lock core's two-stage association/widened floor/coast clamp/epoch, the node's
  `lock.epoch`+`lock.box` publish and click handling, this harness's own fixes, and the docs; see
  `final-fix-report.md` in the same directory for the commit SHAs.
- **Config:** every shipped config (`config/perception.json`, `config/perception-yolov8n.json`,
  `config/perception-yolov8m.json`) carries the identical `lock` block, all header defaults verbatim
  (`git show 0a138c3:services/garuda-perception/config/perception-yolov8m.json`, confirmed byte-identical
  across the three files): `occlusion_ms 500, reacquire_ms 3000, expire_ms 10000, control_valid_ms 150,
  gate_sigma 3.0, min_score 0.5, min_score_widened 0.5, ambiguity_ratio 1.3, size_tol 0.5,
  gate_max_px 300, q_acc_std 600, p0_vel_std 400, r_pos 25, q_size 50, r_size 100, w_conf 0.25,
  w_motion 0.35, w_size 0.15, w_class 0.15, w_id 0.10` (`min_score_widened` added by fix round 2,
  below; still byte-identical across the three files).
- **Profile:** routines 1–4 (`bench/evidence/2026-09-04-lock-core/ROUTINES.md`) run under the person
  profile (`config/perception-yolov8m.json`, `classification_id: 1`, hailo/Kalman tracker engine —
  the deployed default per CLAUDE.md §7's 2026-09-03 note). Routine 5 (phone) runs under the same file
  with `classification_id` removed/`-1` (all classes), matching the 2026-09-03 A/B's
  `phone_kalman2.txt` configuration, so the two are comparable.
- **Harness:** `bench/evidence/2026-09-04-lock-core/lock_metrics.py` (re-locks, tracker id churn
  ridden through, false relocks, LOST events, time-to-reacquire min/mean/max plus
  untimed-reacquisition count, observation_valid fraction, per-state fractions, off-screen published
  boxes read off `lock.box`, max `uncertainty_px`; reads `.gz` transparently; "n/a" for any field a
  capture lacks). Verified against a hand-derived synthetic fixture (`synthetic_capture.txt.gz` +
  `synth_capture.py`, 19 rows exercising every metric — fix round 1 added a 3-row episode for the
  direct CONFIRMED→REACQUIRING jump case; fix round 2 (below) added `lock.epoch`/`lock.box` to every
  row and one explicit re-lock — numbers derived by hand in `test_lock_metrics.py`'s own comments)
  and against a real pre-F1 capture
  (`bench/evidence/2026-09-03-tracker-engine-captures/phone.txt`) to confirm the "n/a" branches work
  end to end on genuine (if pre-F1) board output, not just the synthetic fixture. Self-test output,
  verbatim (`python3 -m pytest bench/evidence/2026-09-04-lock-core/test_lock_metrics.py -v`, post fix
  round 2 — 10 tests):
  ```
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_synthetic_capture_full_metrics PASSED [ 10%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_synthetic_capture_via_gz_matches_plain PASSED [ 20%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_pre_f1_capture_reports_na_for_every_lock_core_metric PASSED [ 30%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_f1_capture_without_epoch_or_box_reports_na_for_those_columns_only PASSED [ 40%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_offscreen_uses_lock_box_and_states_the_default_frame PASSED [ 50%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_unknown_state_string_is_an_assertion_error_naming_it PASSED [ 60%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_untimed_reacquisition_when_capture_starts_mid_episode PASSED [ 70%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_lost_or_none_clears_the_reacquire_anchor PASSED [ 80%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_empty_capture_reports_placeholder_not_a_crash PASSED [ 90%]
  bench/evidence/2026-09-04-lock-core/test_lock_metrics.py::test_real_pre_f1_capture_does_not_crash PASSED [100%]

  ============================== 10 passed in 0.09s ==============================
  ```
  Running the harness directly against the synthetic fixture (post fix round 2 column shape:
  `relocks`/`id churn` in place of the single "id switches", and off-screen boxes read off
  `lock.box`. This fixture's episode 4, at t=1.60–1.80, is the direct CONFIRMED→REACQUIRING-jump
  regression case fix round 1 added, and its 0.20s duration is correctly counted as the third
  episode; `relocks 1` is the explicit epoch 1→2 re-lock at t=1.30, `id churn 1` the 5→6 renumbering
  inside epoch 1 at t=0.60):
  ```
  synthetic_capture.txt.gz                 n=19       1.8s | states none/confirmed/occluded/reacquiring/lost = 10%/42%/15%/21%/10% | obs_valid  42% | relocks  1 (false relocks  1) | id churn  1 | LOST events  1 | reacq min/mean/max 0.20/0.23/0.30s (3 eps, 0 untimed) | off-screen boxes    1 | max uncertainty_px  30.00
  synthetic_capture.txt.gz                 reacquire durations (s): 0.30, 0.20, 0.20
  synthetic_capture.txt.gz                 off-screen at t=0.40
  ```
  And against that same real pre-F1 capture (every lock-core column n/a, including — as of fix round
  2 — off-screen boxes, which now needs `lock.box` and so cannot be computed on a pre-F1 capture at
  all):
  ```
  bench/evidence/2026-09-03-tracker-engine-captures/phone.txt n=897     90.0s | states n/a (pre-F1 capture) | obs_valid n/a | relocks n/a (false relocks n/a) | id churn n/a | LOST events n/a | reacq n/a (0 eps, 0 untimed) | off-screen boxes  n/a | max uncertainty_px n/a
  ```
  (Before fix round 2 this row read `off-screen boxes 88` — 88 rows where `phone.txt`'s `tracks[]`
  entry matching that row's `lock.id` was fully off the 1280×720 frame. Those 88 were real, but they
  measured the TRACKER ENGINE's coasting extrapolation, not the lock core's published box; see the
  red-team paragraph and `lock_metrics.py`'s own docstring.)
- **Owner routines:** `bench/evidence/2026-09-04-lock-core/ROUTINES.md` — walk-out/return, occlusion
  behind an object, two-person swap, fast lateral, phone routine — each with operator action, expected
  capture shape, and which harness column it feeds; provenance for each traced to
  `task-3-brief.md`/`task-1-brief.md` (two routines verbatim from the brief, two derived from Task 1's
  own state-machine test scenarios, one verbatim).

### Results — closing round, 2026-09-04 (routines 1, 2, 4, 5 measured; 3 skipped)

Routines 1/2/4 below are the FINAL on-board captures of the F1 lock-core plan (run 6, run 9b, run 8
respectively — the numbers of intermediate diagnostic/failed attempts stay in the run-by-run history
below, unchanged). Table columns per the closing-docs brief: routine, run, build, n/duration,
confirmed %, `core_miss_live`, relocks, id churn, LOST events, reacq max, off-screen boxes, max
`uncertainty_px`.

| routine | run | build | n / duration | confirmed % | core_miss_live | relocks (false relocks) | id churn | LOST events | reacq max (s) | off-screen | max uncertainty_px |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1. walk-out/return | 6 | `217fb04` | 684 / 68.6 s | 89% | 0% (1/616) | 0 (0) | 6 | 0 | 1.81 | 0 | 195.59 |
| 2. occlusion behind an object | 9b | `47fb866` | 800 / 80.2 s | 26% | 0% (0/213) | 0 (0) | 0 | 1 | 0.90 | 0 | 2129.14 |
| 3. two-person swap | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` | `TBD-bench` |
| 4. fast lateral | 8 | `217fb04` | 3123 / 313.5 s | 99% | 0% (6/3103) | 1 (1) | 41 | 0 | 0.50 | 0 | 47.24 |
| 5. phone (all-classes) | 10e | `097bfad` | 3494 / 120.0 s | 68% | 7% (182/2567) | 0 (0) | 44 | 0 | 6.43 | 0 | 1082.69 |

Row 3 (**skipped**): owner, 2026-09-04 13:20 — "no second person today"; stays `TBD-bench` with that
reason, not a measured zero.

**Row 5 is filled but it is NOT a pass — read the "Run 10e" entry below before using any of it.**
The window is rel. 97.5–217.5 s of run 10e (`f1_r10e_phone_B120`, the moving-phone window), and its
last ~70 s already contains the silent false lock that round 5 fixes: at rel. 165.71 s the core
settled on a static `chair`/`suitcase` box and stayed `confirmed` on it for the rest of the 900 s
capture. Every column in the row is therefore an over-statement of how well the *phone* was tracked,
and the two columns that would normally catch that — `relocks 0` and the false-relocks alias — are
structurally blind to it (the whole walk happened inside one epoch, and the build published the class
frozen at `lock()`). The `class switches` column added in round 5 exists for exactly this and also
reads 0 here, because this capture's build could not publish a class change at all. Cited alongside
it: `f1_r10e_phone_A` (rel. 78.3–93.7 s, the acquisition struggle) and `f1_r10e_phone_B`
(rel. 97.5–900 s, the whole post-lock stretch, whose 95 % `confirmed` is ~735 s of suitcase).

(**confirmed %** is the `confirmed` state fraction from the harness's states line. **core_miss_live**
= rows where the underlying tracker engine had a LIVE box for the locked id but `LockCore` reported no
observation that frame (Ruling 19) — the metric M-A/M-B/M-C's fix targeted; 0 % on all three measured
routines. **re-locks** = `lock.epoch` changes, the column "false relocks" aliases on these
single-target routines; **id churn** = `lock.id` changes within one epoch while `identity_locked` —
the tracker underneath renumbering the same object, which `LockCore` is *supposed* to ride through, so
a non-zero value here is not itself a failure. **Since on-board fix round 5 the "false relocks" alias
is `relocks + class_switches`, not `relocks` alone** — run 10e is why; see below.)

**Harness rows, re-run for this closing round** (verbatim `python3 lock_metrics.py <file>.gz` against
the committed captures below — identical to the controller's rows in
`.superpowers/sdd/2026-09-04-hailo15l-lock-core/closing-docs-brief.md`, confirmed by direct comparison):

```
run6_routine1_walk.txt.gz                n=684     68.6s | states none/confirmed/occluded/reacquiring/lost =  7%/89%/ 1%/ 1%/ 0% | obs_valid  89% | core_miss_live   0% (1/616) | relocks  0 (false relocks  0) | id churn  6 | LOST events  0 | reacq min/mean/max 0.20/0.63/1.81s (4 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 195.59
run8_routine4_lateral.txt.gz             n=3123   313.5s | states none/confirmed/occluded/reacquiring/lost =  0%/99%/ 0%/ 0%/ 0% | obs_valid  99% | core_miss_live   0% (6/3103) | relocks  1 (false relocks  1) | id churn 41 | LOST events  0 | reacq min/mean/max 0.20/0.27/0.50s (11 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px  47.24
run9b_routine2_occlusion.txt.gz          n=800     80.2s | states none/confirmed/occluded/reacquiring/lost = 54%/26%/ 2%/12%/ 3% | obs_valid  26% | core_miss_live   0% (0/213) | relocks  0 (false relocks  0) | id churn  0 | LOST events  1 | reacq min/mean/max 0.20/0.44/0.90s (6 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 2129.14
```

Captures: `bench/evidence/2026-09-04-lock-core/run6_routine1_walk.txt.gz`,
`run8_routine4_lateral.txt.gz`, `run9b_routine2_occlusion.txt.gz` (gzipped from
`sse_capture_flush.py` captures, trimmed to the active window with `trim_capture.py`, both scripts
now committed alongside them).

**Comparison against run 5 (routine 1, pre-round-3 build `83b600c`, this section below):** confirmed
62 % → 89 %, `core_miss_live` 29 % → 0 %, relocks 4 → 0, LOST events 1 → 0, reacq max 10.54 s →
1.81 s — the three round-3 gate fixes (M-A/M-B/M-C) hold on a fresh capture, not just the replay of
run 5's own fixture. Run 6 itself shows the tracker underneath still renumbering the owner 6 times at
close range (boxes ~780 px wide); `LockCore` rode through every one (0 relocks) — id churn continuing
while relocks stays 0 is the fix's own definition of success (Ruling 10/I2), not a regression.

**Update, 2026-09-04 closing round, on the "Comparison against yesterday's tracker-engine section"
paragraph below (kept as originally written for the record):** routines 1 and 4 are now measured.
Both show `id churn` continuing under F1 (6 and 41 respectively — the same kind of tracker-level
renumbering `person_kalman.txt` recorded pre-F1 as 5 lock-id jumps in one 150 s walk) while `relocks`
stayed 0 and 1 — the question the pre-F1 numbers could not answer on their own, whether the
*published* lock ever silently jumps to a different object, reads no on both measured routines (run
8's one relock is attributed to an operator action, not the tracker — see the red-team paragraph
below). Routine 5, the direct analogue of `phone_kalman2.txt`'s cross-class lock flip
(`{knife, cell phone, tv}`), is now run — see "Run 10e" below, and note that it reproduced the
cross-class flip in a *worse* form: not a lock that flickers between classes, but one that walks onto
a different-class object and holds it silently while still publishing the original class.

Comparison against yesterday's tracker-engine section (`phone_kalman2.txt`: n=894, null lock=381,
lock classes `{knife, cell phone, tv}`; `person_kalman.txt`: id sequence
`1 -> 234 -> 284 -> 234 -> 285 -> 301`, 5 jumps in one 150 s walk): routine 5 is now run, and the
pre-F1 capture's own signal — `lock classes {knife, cell phone, tv}`, i.e. the published class
*changing* — turns out to be the signal F1 removed by freezing `lock.class` at `lock()`. Run 10e's
lock class column reads `{cell phone: 23323}` for a capture that spent twelve minutes on a suitcase.
Round 5 restores it (Ruling 22.3). The walk portion of routines 1/4 is measured (runs 6 and 8).

### The Kalman branch's pending I1 verification is folded into this round's on-board run

`docs/decisions.md`'s 2026-09-04 "final-fix wave" entry and `hosts/hailo15l/README.md` §9's own
"2026-09-04 fix" note both record I1 (`tracker.hailo.keep_tracked_frames: 0`) as deployed-in-config
but never board-verified: the claim is that an unmatched strack now drops straight to Lost on the very
next miss (instead of the JDE stage silently re-activating it as if freshly seen for up to 5 frames),
so `HailoTrackAdapter`'s `coasting` flag (`time_since_update > 0`) should flip `true` on the first
snapshot after a real miss, not up to 5 frames late. Routines 1 and 2 above (walk-out/return, occlusion
behind an object) are precisely a real out-of-frame/occlusion gap under the deployed
`config/perception-yolov8m.json` (which carries the `keep_tracked_frames: 0` fix), so their captures
double as I1's own confirmation — a `tracks[]` entry for the about-to-be-lost id still reading
`coasting: false` one or more frames after `lock.state` has already moved to `occluded` would mean I1
did not deploy as intended, since `LockCore`'s own occlusion clock (`obs_age_ms`) is independent of and
runs strictly no later than the underlying tracker's own miss detection. No separate on-board session
is needed for I1 beyond running routines 1/2 of this section.

### Red-team (rule 9)

- **Owner-paced, not timer-paced**, same caveat as every prior routine-based section this bench has
  produced (2026-09-03 tracker-engine A/B, M1 coast-window): per-phase durations and distances will
  not be exactly reproducible run to run, and each routine will be run once per configuration, not
  repeated — variance across repeated identical routines stays unmeasured.
- **No visual tracker yet (F2, spec §8.2).** Every gap in these routines is a real detector miss with
  no visual-tracker safety net bridging it — the numbers this round produces are a floor for F1 alone,
  not the eventual F1+F2 answer; re-running the same five routines once F2 lands is expected to change
  time-to-reacquire and off-screen-box numbers (already flagged in ROUTINES.md's own closing note).
- **Two of the five routines are not literally named in `task-3-brief.md`'s Step 2** (occlusion behind
  an object, two-person swap) — they are this task's own derivation from Task 1's synthetic
  state-machine test list (`task-1-brief.md` tests 2/3/5 and 8), chosen because they are the physical
  analogues of scenarios already proven correct in isolation (`tests/test_lock_core.cpp`) but never
  exercised against real board timing/detector noise. If the owner runs a materially different
  two-person or occlusion scenario than what ROUTINES.md describes, the mapping from capture to
  "which design scenario this validates" may not hold as cleanly as stated there.
- **The off-screen-published-boxes metric now reads `lock.box`** — `LockCore`'s own published box,
  added to the snapshot in fix round 2 (review finding I5). Before that it read the `tracks[]` entry
  whose `id` matched the row's `lock.id`, because the core's box was not in the snapshot at all; that
  reading measured the TRACKER ENGINE's coasting box (ByteTrack extrapolates it every frame under the
  mono engine, `src/bytetrack.cpp`; the hailo adapter freezes it) — a separate, pre-existing behaviour
  rather than anything F1 does, which is why it fired on 88 rows of a pre-F1 capture. The column now
  measures what the state table in `hosts/hailo15l/README.md` §10 actually promises. Two consequences
  worth stating: (a) a pre-F1 capture can no longer produce this number at all (it reads `n/a`), so
  there is no before/after comparison for this column; (b) the *engine's* box is still what a viewer
  drawing `tracks[]` sees, and whether the two disagree in practice is unmeasured — capturing one
  mono-engine run alongside the hailo runs to see that difference in real data is in the deferred list
  below.
- **The harness has only been run against one hand-built synthetic fixture and old pre-F1 captures —
  never against a real F1-format capture.** The synthetic fixture's field names/shapes were copied
  verbatim from `snapshot.cpp`'s emitted keys and `task-2-report.md`'s documented shape, not guessed,
  but this is still inference from source, not proof the harness parses genuine board JSON correctly;
  the on-board round is what actually closes this gap.
- **F2's effect on this section's own numbers:** `TBD-bench` — F2 (visual tracker) does not exist yet,
  so there is nothing to compare against.

### Deferred to the on-board round (nothing here is a number yet)

1. **Whether `isp_timestamp_ns` is ever 0 mid-stream**, as opposed to only on the very first frames.
   The node assumes the latter; fix round 2 made a zero timestamp under a live lock extend the ISP
   series by one nominal frame interval rather than jumping to `steady_clock` (review finding M2), but
   whether the case occurs at all on this board is unverified (rule 2). The node logs
   `lock: isp_timestamp_ns is 0 this frame ...` once — grep the service log after each routine and
   record here whether it appeared, and if so at what point in the run.
2. **One mono-engine capture alongside the hailo runs** (review Recommendation 4), so the difference
   between `lock.box` (frozen while coasting) and the same id's `tracks[]` box (ByteTrack's
   extrapolation) is visible in real data rather than argued from source.
3. **`tracker.hailo.keep_tracked_frames: 0`** — the Kalman branch's own pending I1 verification, which
   routines 1 and 2 already double as (see the section above).

### Fix round 1 (2026-09-04, task review)

**Finding (Minor):** `lock_metrics.py`'s reacquire-duration timer only armed on a
CONFIRMED→OCCLUDED transition. A capture that jumps straight from CONFIRMED to REACQUIRING between
two sampled rows — a dropped SSE line, or a sampling gap wide enough that `occlusion_ms` had already
elapsed before the next poll — never armed the timer, so the later recovery to CONFIRMED was
silently un-timed AND un-counted (not even reflected as an episode), with nothing in the output to
show it had happened.

**Fix:** the timer now arms on the first row that leaves CONFIRMED for EITHER OCCLUDED or
REACQUIRING. The duration's start is the **previous CONFIRMED row's own timestamp**, not the row
where the miss is first observed — chosen because it matches `LockCore`'s own `obs_age_ms` anchor
(`lock_core.cpp`: time since the last confirmed correction, not time since the first miss a sparse
sampler happened to observe), so a dropped/late sample no longer shortens the measured duration. An
episode whose start cannot be attributed to any known CONFIRMED row (the capture opens mid-episode)
is tracked as `untimed_reacquisitions` if it recovers, rather than dropped or fabricating a start
time. The synthetic fixture gained a 3-row episode (t=1.60–1.80, `synth_capture.py`) exercising the
direct-jump case directly, and a new dedicated test,
`test_untimed_reacquisition_when_capture_starts_mid_episode`, covers the mid-capture-start case.
Full detail: `.superpowers/sdd/2026-09-04-hailo15l-lock-core/task-3-report.md`'s "Fix round 1"
section.

**Effect on this round's numbers:** none of the `TBD-bench` placeholders above are numbers yet, so
nothing here needed correcting; this fix only changes what the harness will compute once real
captures exist. The self-test output and harness-run pastes earlier in this section are the
post-fix-round-2 versions (10 tests, the `relocks`/`id churn` split and the `lock.box`-based
off-screen column).

### Run 1 (c07945c, pre-fix) — edge-entry failure

First real on-board capture, board back up 2026-09-04: routine 1 (walk-out/return) under
`config/perception-yolov8m.json`, 1495 rows / 150 s, PC-side timestamped SSE at 10 Hz. Capture
committed as `bench/evidence/2026-09-04-lock-core/run1_walk_prefix.txt.gz`. Harness row **as produced
by c07945c's harness** (verbatim; the results table above stays `TBD-bench` — this is a diagnostic
run, not the gate run):

```
n=1495 150.0s | states none/confirmed/occluded/reacquiring/lost = 54%/3%/2%/13%/26% | obs_valid 3% | relocks 1 (false relocks 1) | id churn 1 | LOST events 1 | reacq min/mean/max 0.20/0.56/1.20s (7 eps, 1 untimed) | off-screen boxes 109 | max uncertainty_px 4439.38
```

**Mechanism.** At 81.6 s the resolver auto-acquired id 1 on a 29×194 px, conf 0.17 sliver of the owner
still entering at the right edge (x=1251, so x+w = 1280 exactly), and `LockCore` took that as its size
reference; over the next 0.8 s the owner's box grew 56×220 → 79×238 → 97×255 → 170×431 → 201×563 →
293×713, every one of which failed the then-fixed size gate (`|w − ref|/ref ≤ size_tol 0.5`, i.e.
±14.5 px around 29 px), so nothing could ever associate, the reference stayed frozen on the sliver, the
widened stage (also size-gated) never matched either, `uncertainty_px` climbed to 4439 and the lock
decayed to LOST at `obs_age_ms` 10000 before a fresh, healthy lock on id 2 (quality 0.96,
`uncertainty_px` 3.2). Node log for the episode: `none -> confirmed`, `confirmed -> occluded (33)`,
`occluded -> reacquiring (533)`, `reacquiring -> lost (10000)`.

**Fix (on-board fix round 1, Ruling 16).** (1) The resolver may now auto-acquire only a candidate with
`conf >= auto_min_conf` (0.5) whose box is clear of the left/right frame edges by
`auto_edge_margin_frac * frame_w` (0.02 → 25.6 px) — that sliver fails both halves; an explicit click
is never gated. (2) The core's size gate is variance-aware,
`max(size_tol·ref, gate_sigma·sqrt(size_var + r_size))`, so a small or stale reference relaxes with
`obs_age` instead of locking the core out (derived tolerances in `hosts/hailo15l/README.md` §10). (3)
The off-screen metric now counts a `lock.box` whose **centre** has left the frame: those 109 rows were
the legitimately-frozen last-confirmed box of a target that had walked out at the right edge,
overhanging the boundary by a few px. Re-running the fixed harness over the same committed capture
reproduces every other column and turns that one to 0 — the only column the harness change moves:

```
run1_walk_prefix.txt.gz n=1495   150.0s | states none/confirmed/occluded/reacquiring/lost = 54%/ 3%/ 2%/13%/26% | obs_valid   3% | relocks  1 (false relocks  1) | id churn  1 | LOST events  1 | reacq min/mean/max 0.20/0.56/1.20s (7 eps, 1 untimed) | off-screen boxes    0 | max uncertainty_px 4439.38
```

**Honest limit of fix (2):** with the shipped `q_size` (50 px²/s) the variance term reaches only
~42–56 px, so it rescues a small-reference lock from a *plausible* size change but not from run 1's
several-fold growth — re-associating at the 97×255 row would have needed ~68 px of tolerance at 167 ms.
Run 1 is prevented by fix (1), not by fix (2); `tests/test_lock_core.cpp` case 19b replays the capture's
own rows and pins that boundary rather than claiming a recovery. If a future capture shows a legitimate
lock going stale this way, the lever is `q_size` (a config value), not the formula.

### Run 2 (40f15f8) — junk-track lock

Second on-board capture, same routine and profile, 1196 rows / 120 s, committed as
`bench/evidence/2026-09-04-lock-core/run2_walk_junklock.txt.gz`. Harness row (verbatim; the results
table above stays `TBD-bench` — this run measured nothing about the owner):

```
n=1196 120.0s | states none/confirmed/occluded/reacquiring/lost = 42%/19%/29%/7%/0% | obs_valid 19% | relocks 0 (false relocks 0) | id churn 0 | LOST events 0 | reacq min/mean/max 0.20/0.42/1.51s (114 eps, 0 untimed) | off-screen boxes 0 | max uncertainty_px 1582.17
```

**Mechanism.** Before the owner entered, the person profile was already carrying several persistent
low-confidence "person" tracks on static room objects (ids 7, 22, 23, 25 — conf 0.15–0.37, boxes
105×78 to 317×620 around x 318–650, y 79–214, mostly engine-coasting); at 51.01 s one of them (id 25,
151×103 at 649,193) flickered over `auto_min_conf` for a single frame, passed run 1's conf+edge gate on
that one frame, and `LockCore` locked it. Because that track kept flickering back within ≤1.5 s it
never reached `expire_ms`, so the lock never expired (0 re-locks, 0 LOST, 114 tiny reacquire episodes)
and the owner was never locked at all. Row classification (`f1_classify.py`): occluded/engine-coasting
29.0 %, confirmed/engine-live 20.0 %, reacquiring/engine-coasting 5.9 %. Note the 10 Hz SSE sampling
never caught the ≥0.5 frame itself — the sampled rows around the acquisition read 0.24, 0.19, 0.17,
0.25 — but the gate was wired and live (the board log printed its parameters at startup, and the
resolver would not otherwise have taken a conf-0.16 track).

**Fix (on-board fix round 2, Ruling 18).** The resolver's auto-acquire now also requires the candidate
to have passed the conf+edge gate on `auto_min_streak` **consecutive live frames** (default 5, ~170 ms
at 30 fps): one frame over the threshold is a flicker, not evidence. The streak resets on any frame
where the id is absent, coasting, or fails the gate, which also makes auto-acquire live-only. The same
conf+edge+streak test now gates the resolver's **re-acquire jump** (a coasting lock moving to the best
live same-class track after `reacq` frames), which could otherwise hand the lock to the same junk
flicker; `LockCore`'s own re-acquisition is a separate mechanism and is unchanged. Clicks remain
ungated. Deployed as commit `f027924`.

**What this does not fix:** the room still produces those low-confidence "person" tracks, and a junk
track that holds conf ≥ 0.5 for five straight live frames would still be acquirable. If run 3 shows
that, the levers are `auto_min_conf`, `auto_min_streak` (both config), or the detector/tracker floor —
not this gate's shape.

### Fix round 2 (2026-09-04, whole-branch review — the final-fix wave)

Four findings in this section's scope (the full list, including the lock-core and node changes, is in
`docs/decisions.md`'s F1 entry and `.superpowers/sdd/2026-09-04-hailo15l-lock-core/final-fix-report.md`):

- **I1 — the reacquire-duration anchor survived a LOST/NONE reset.** `lock_metrics.py` cleared the
  in-progress episode on a `lost`/`none` row but kept `last_confirmed_t`, so an episode opening after
  a reset with no CONFIRMED row in between was timed from a CONFIRMED row *before* the reset. On the
  review's five-row shape (CONFIRMED t=0 → LOST 20.0 → NONE 20.1 → OCCLUDED 20.2 → CONFIRMED 20.5 —
  realistic at 10 Hz sampling, where a re-lock that misses on its next sampled frame looks exactly
  like this) the harness reported a 20.5 s time-to-reacquire; the correct answer is no duration and
  one untimed reacquisition. **This is the one fix that would have written a wrong number into this
  table** had the board been up before it landed. Now a `lost`/`none` row clears the anchor too, with
  the five-row case as a test.
- **I2 — "identity switches" could not tell a false re-lock from id churn.** Split into `re-locks`
  (`lock.epoch` changes) and `id churn` (`lock.id` changes within one epoch), with "false relocks"
  aliasing `re-locks` only. The old single column counted the failure F1 prevents and the success F1
  delivers as the same event, so a *high* number on routine 5 could have been a good result read as a
  bad one. The table above carries both columns.
- **I5 — the off-screen column measured the wrong box.** See the red-team paragraph above.
- **M9 — harness/routine hygiene:** ROUTINES.md now says click once at the start and never
  mid-capture (at 10 Hz a mid-capture click is indistinguishable from a silent re-lock, and would land
  in the `re-locks` column), and an unrecognised `lock.state` string is now an assertion error naming
  the value instead of a row silently left out of fractions documented to sum to 1.0.

**Effect on this round's numbers:** again none — every cell above is still `TBD-bench`. What changed
is what the columns will *mean* when the board is back: `re-locks` is the gate column, `id churn` is
diagnostic, and the off-screen column is about `lock.box`, not the tracker engine's box.

### Run 5 (83b600c) — routine 1 measured: three core gate failures

First measured routine-1 run with the owner actually in view and the room lit, under
`config/perception-yolov8m.json` (person profile, hailo/Kalman engine), 1196 rows / 120 s of PC-side
timestamped SSE at 10 Hz. Capture committed as
`bench/evidence/2026-09-04-lock-core/run5_routine1_walk.txt.gz`. Harness row **as produced by
83b600c's harness** (verbatim; the results table above stays `TBD-bench` — this is a diagnostic run,
not the gate run):

```
f1_r1_walk.txt n=1196   120.0s | states none/confirmed/occluded/reacquiring/lost =  0%/62%/12%/25%/ 0% | obs_valid  62% | relocks  4 (false relocks  4) | id churn  3 | LOST events  1 | reacq min/mean/max 0.20/1.09/10.54s (36 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 2104.47
```

Row classification (`bench/evidence/2026-09-04-lock-core/classify_rows.py`, verbatim) — every row by
`lock.state` × whether the tracker engine had a LIVE / coasting / no box for the locked id:

```
confirmed/engine-live            742   62.0%
reacquiring/engine-live          187   15.6%
occluded/engine-live             119    9.9%
reacquiring/track-gone            74    6.2%
reacquiring/engine-coasting       40    3.3%
occluded/engine-coasting          32    2.7%
lost                               2    0.2%
```

**So on 306 of the 1048 rows where the engine had a live box for the locked id (29 %), the core
reported no observation.** `obs_valid 62%` on its own looks like a detector problem; it was not. That
split is now a harness column (`core_miss_live`, Ruling 19.6), so re-running the round-3 harness over
the same committed capture reproduces every other column and adds it — the only column the harness
change moves:

```
run5_routine1_walk.txt.gz                n=1196   120.0s | states none/confirmed/occluded/reacquiring/lost =  0%/62%/12%/25%/ 0% | obs_valid  62% | core_miss_live  29% (306/1048) | relocks  4 (false relocks  4) | id churn  3 | LOST events  1 | reacq min/mean/max 0.20/1.09/10.54s (36 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 2104.47
```

**Three mechanisms** (each read off the capture with `rows.py`; row times are seconds into the
capture):

- **M-A, converged position gate tighter than detector box jitter** (rows 11.85–13.15): with the
  owner standing still in a ≈650×650 px box, arm movement swung the engine's box width
  643 → 760 → 727 → 684 → 759 → 774 → 640 and its centre 40–60 px frame to frame, while
  `uncertainty_px` was 3.2 (converged) and the gate ~10 px — so the same id's live box was rejected
  until the gate regrew (100–400 ms), giving the `confirmed -> occluded (33) [+4 suppressed]` runs in
  the node log.
- **M-B, size reference frozen on a partial box with a hard, slowly-growing size gate** (rows
  42.77–52.81): the core re-confirmed on a 169×537 partial box at the right edge, then the owner
  walked toward the camera and the same live id 1309 (conf 0.80–0.90) went 231×717, 279×719, 327×715,
  428×716, 515×715, 594×715 within 1.4 s — every one of them outside the ~43–79 px the absolute
  `q_size` granted — so nothing associated for the full 10 s and the lock hit LOST at 52.81 (the
  `reacq max 10.54s` above).
- **M-C, widened-stage floor rejecting the only candidate** (rows 66.56–75.10): id 1309 died as the
  owner left frame and she re-entered as NEW id 1316 at conf 0.82–0.93, size 269×716 against a
  409×666 reference (size OK) and the only live person in the room, scoring ≈0.45 against
  `min_score_widened` 0.5 — so the core sat in REACQUIRING for 9 s until expiry and the resolver then
  re-locked, counted as one of the 4 false relocks.

**Fix (on-board fix round 3, Ruling 19 — `docs/decisions.md`).** Every tolerance in the core that was
absolute is now relative to the box: position measurement noise `max(sqrt(r_pos), r_pos_frac·ref)`
per axis with the gate a Mahalanobis test against `S = min(P, cap) + R` and a radius floor of
`gate_min_frac·max(w,h)`; size measurement/process noise `max(r_size, (r_size_frac·ref)²)` and
`max(q_size, (q_size_frac·ref)²)` px²/s; a `same_id_gate_mult` (2.0) relaxation of both the position
gate and the size tolerance for a LIVE candidate carrying the core's own `last_id`; and
`min_score_widened` 0.5 → 0.40. Derived tolerance tables are in `hosts/hailo15l/README.md` §10.

**Replay of this capture through the fixed core** (`tests/test_lock_replay.cpp` over
`tests/fixtures/lock_replay_routine1.json`, all 1196 rows, live tracks only, node parity —
**a replay number, not an on-board measurement**, and a weaker gate than the live pipeline because
the 10 Hz SSE sampling makes every inter-frame gap ~3× the real one at 25–30 fps):

```
lock_replay: locked id 1309 at t=0 ms (row 0 of 1196)
lock_replay: CONFIRMED on 1144 of 1161 rows carrying a live conf>=0.50 track = 0.9854
lock_replay: id 1316 first live at t=65559 ms, core CONFIRMED on it at t=65960 ms (delta 401 ms)
lock_replay: LOST rows 0 (first at t=-1 ms)
```

Before the fix, the same replay on the same fixture: `CONFIRMED on 539 of 1161 ... = 0.4643`, id 1316
never taken, `LOST rows 445`.

**Results table: unchanged, still `TBD-bench`.** Run 5 is a diagnostic run of a build with three
known gate bugs; run 6, on the fixed build, is what fills it.

**Red team on the fix.** (a) The replay is the *same capture the fix was derived from*, so 0.9854 is
a regression guard, not independent evidence — run 6 must be a fresh capture. (b) It is also coarser
than the live pipeline (10 Hz vs 25–30 fps), so it exercises wider gates than the board will.
(c) Relaxing gates trades false negatives for false positives: this capture had one person in it and
therefore says nothing about the two-person swap (routine 3), where a looser gate is exactly the risk
— the ambiguity margin is unchanged and is what must hold there. (d) `min_score_widened` 0.40 is now
met on the weights alone (`w_size + w_class + w_id = 0.40`) by an out-of-gate, same-id,
exactly-size-matched candidate at any confidence; it still has to match the locked class, pass the
size gate, be inside the widened window and beat the ambiguity margin, but that floor is thinner than
it looks and routine 5 (all classes) is where it would show.

**(d) is what happened.** Routine 5 was run (run 10e, below) and the thin floor showed exactly there —
though in-gate rather than out-of-gate, via round 4's Ruling 20b, and with the *class* check being the
protection that turned out not to exist (it was a soft score term, not a gate). Round 5 makes it one.


### Run 7 (217fb04) — routine 2: 3-s hide PASS, 6-s hide FAIL (size contamination)

Routine 2 (occlusion behind a chair) on the round-3 build, under `config/perception-yolov8m.json`
(person profile, hailo/Kalman engine). Capture committed as
`bench/evidence/2026-09-04-lock-core/run7_routine2_occlusion.txt.gz` — **2961 rows / 297.2 s**; note
this is a snapshot of a capture that was still running, so it is longer than the 2137-row read the
round-4 brief quoted. Harness row (verbatim, round-3 harness over the committed snapshot):

```
run7_routine2_occlusion.txt.gz           n=2961   297.2s | states none/confirmed/occluded/reacquiring/lost =  0%/95%/ 0%/ 3%/ 0% | obs_valid  95% | core_miss_live   0% (4/2817) | relocks  1 (false relocks  1) | id churn  6 | LOST events  1 | reacq min/mean/max 0.20/0.98/2.81s (4 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 2091.13
```

**`core_miss_live` reads 0 % here, and that is the point:** round 3's column asks whether the core
refused a box the ENGINE still had live for the locked id. Run 7's failure is a different shape — the
engine had *dropped* the id by then, and the owner came back under a new one — so the mechanism this
round fixes is invisible to it. The single `relocks 1` / `LOST events 1` in the row above is the whole
failure, 10 s of it.

**The 3-second hide — PASS.** Rows 174.10–176.82 (`rows.py`, verbatim):

```
 174.10 occluded    id=25   ep=2 age=   133 unc=   30.5 q=0.49 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.20 occluded    id=25   ep=2 age=   200 unc=   34.8 q=0.49 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.30 occluded    id=25   ep=2 age=   300 unc=   42.1 q=0.49 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.40 occluded    id=25   ep=2 age=   367 unc=   47.3 q=0.48 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.50 occluded    id=25   ep=2 age=   467 unc=   55.7 q=0.48 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.61 reacquiring id=25   ep=2 age=   600 unc=   67.8 q=0.47 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.71 reacquiring id=25   ep=2 age=   700 unc=   77.5 q=0.46 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.81 reacquiring id=25   ep=2 age=   767 unc=   84.2 q=0.46 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 174.91 reacquiring id=25   ep=2 age=   867 unc=   94.6 q=0.46 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.01 reacquiring id=25   ep=2 age=  1000 unc=  109.3 q=0.45 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.11 reacquiring id=25   ep=2 age=  1133 unc=  124.7 q=0.44 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.21 reacquiring id=25   ep=2 age=  1233 unc=  136.7 q=0.44 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.31 reacquiring id=25   ep=2 age=  1267 unc=  140.7 q=0.44 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.41 reacquiring id=25   ep=2 age=  1400 unc=  157.5 q=0.43 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.51 reacquiring id=25   ep=2 age=  1533 unc=  174.9 q=0.42 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.61 reacquiring id=25   ep=2 age=  1600 unc=  183.8 q=0.42 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.71 reacquiring id=25   ep=2 age=  1700 unc=  197.4 q=0.41 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.81 reacquiring id=25   ep=2 age=  1800 unc=  211.4 q=0.41 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 175.91 reacquiring id=25   ep=2 age=  1867 unc=  220.9 q=0.41 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 176.01 reacquiring id=25   ep=2 age=  2000 unc=  240.4 q=0.40 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C 27:per 0.24 997,0 192x716C
 176.11 reacquiring id=25   ep=2 age=  2100 unc=  255.3 q=0.39 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C
 176.21 reacquiring id=25   ep=2 age=  2233 unc=  275.7 q=0.39 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C
 176.31 reacquiring id=25   ep=2 age=  2333 unc=  291.3 q=0.38 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C
 176.41 reacquiring id=25   ep=2 age=  2400 unc=  301.9 q=0.38 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C
 176.51 reacquiring id=25   ep=2 age=  2467 unc=  312.6 q=0.38 box=1132,103 148x495   | 25:per 0.51 1144,102 136x470C
 176.62 reacquiring id=25   ep=2 age=  2600 unc=  334.3 q=0.37 box=1132,103 148x495   | 
 176.72 reacquiring id=25   ep=2 age=  2733 unc=  356.6 q=0.36 box=1132,103 148x495   | 
 176.82 confirmed   id=28   ep=2 age=     0 unc=   49.0 q=0.55 box=1125,88 155x625    | 28:per 0.36 1124,87 155x629
```

The owner (id 25, 148x495 at x=1132, mid-distance) ducks; the engine coasts id 25 for ~2 s and then
drops it; she re-emerges as a NEW id 28 at conf 0.36, 155x625, and the widened stage takes it 2.7 s
after the last observation. This is round 3 working as designed.

**The 6-second hide — FAIL.** Rows 181.03–182.34, the mechanism (`rows.py`, verbatim):

```
 181.03 occluded    id=28   ep=2 age=    33 unc=   13.7 q=0.50 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.82 338,-2 321x271
 181.13 occluded    id=28   ep=2 age=   133 unc=   18.7 q=0.49 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.58 52,-20 607x464
 181.23 occluded    id=28   ep=2 age=   267 unc=   27.0 q=0.49 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.16 307,7 286x273C
 181.33 occluded    id=28   ep=2 age=   333 unc=   31.7 q=0.48 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.16 307,7 286x273C
 181.43 occluded    id=28   ep=2 age=   467 unc=   41.9 q=0.48 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.16 307,7 286x273C
 181.53 reacquiring id=28   ep=2 age=   600 unc=   53.1 q=0.47 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.16 307,7 286x273C
 181.63 reacquiring id=28   ep=2 age=   633 unc=   56.1 q=0.47 box=421,2 276x159      | 28:per 0.54 394,-2 279x156C 30:per 0.16 307,7 286x273C
 181.73 occluded    id=28   ep=2 age=    33 unc=   14.8 q=0.50 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
 181.84 occluded    id=28   ep=2 age=   133 unc=   18.7 q=0.49 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
 181.94 occluded    id=28   ep=2 age=   200 unc=   22.2 q=0.49 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
 182.04 occluded    id=28   ep=2 age=   300 unc=   28.5 q=0.49 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
 182.14 occluded    id=28   ep=2 age=   433 unc=   38.3 q=0.48 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
 182.24 reacquiring id=28   ep=2 age=   533 unc=   46.5 q=0.47 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
 182.34 reacquiring id=28   ep=2 age=   633 unc=   55.3 q=0.47 box=495,-3 152x129     | 28:per 0.50 505,0 149x128C 30:per 0.16 307,7 286x273C
```

and rows 189.77–192.38, the consequence (`rows.py`, verbatim; the ~7.4 s of unbroken
`reacquiring ... box=495,-3 152x129` between the two excerpts is elided for length and reproducible
with `rows.py <capture> 182.34 189.77`):

```
 189.87 reacquiring id=28   ep=2 age=  8133 unc= 1549.1 q=0.09 box=495,-3 152x129     | 31:per 0.39 493,-9 312x501C 32:per 0.19 1032,469 30x51C 33:per 0.64 461,-0 306x276
 189.97 reacquiring id=28   ep=2 age=  8267 unc= 1586.0 q=0.09 box=495,-3 152x129     | 31:per 0.39 493,-9 312x501C 32:per 0.19 1032,469 30x51C 33:per 0.69 347,-2 350x257
 190.07 reacquiring id=28   ep=2 age=  8400 unc= 1623.2 q=0.08 box=495,-3 152x129     | 31:per 0.39 493,-9 312x501C 32:per 0.19 1032,469 30x51C 33:per 0.31 294,1 354x258
 190.17 reacquiring id=28   ep=2 age=  8467 unc= 1641.9 q=0.08 box=495,-3 152x129     | 31:per 0.39 493,-9 312x501C 32:per 0.19 1032,469 30x51C 33:per 0.74 222,-22 430x481
 190.27 reacquiring id=28   ep=2 age=  8567 unc= 1670.1 q=0.07 box=495,-3 152x129     | 31:per 0.39 493,-9 312x501C 32:per 0.19 1032,469 30x51C 33:per 0.73 212,-11 400x573
 190.38 reacquiring id=28   ep=2 age=  8633 unc= 1688.9 q=0.07 box=495,-3 152x129     | 31:per 0.39 493,-9 312x501C 32:per 0.19 1032,469 30x51C 33:per 0.65 216,3 398x567
 190.47 reacquiring id=28   ep=2 age=  8733 unc= 1717.4 q=0.06 box=495,-3 152x129     | 31:per 0.19 250,-1 369x474C 32:per 0.19 1032,469 30x51C 33:per 0.62 234,6 372x637
 190.58 reacquiring id=28   ep=2 age=  8867 unc= 1755.6 q=0.06 box=495,-3 152x129     | 31:per 0.69 243,1 360x546 32:per 0.19 1032,469 30x51C 33:per 0.62 234,6 372x637C
 190.68 reacquiring id=28   ep=2 age=  8967 unc= 1784.4 q=0.05 box=495,-3 152x129     | 31:per 0.66 235,-1 362x568 32:per 0.19 1032,469 30x51C 33:per 0.62 234,6 372x637C
 190.78 reacquiring id=28   ep=2 age=  9033 unc= 1803.7 q=0.05 box=495,-3 152x129     | 31:per 0.66 235,-1 362x568C 32:per 0.19 1032,469 30x51C 33:per 0.61 220,6 376x669
 190.88 reacquiring id=28   ep=2 age=  9133 unc= 1832.8 q=0.04 box=495,-3 152x129     | 31:per 0.16 224,3 372x425 32:per 0.19 1032,469 30x51C 33:per 0.63 215,5 379x598
 190.98 reacquiring id=28   ep=2 age=  9267 unc= 1871.8 q=0.04 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.67 210,-0 382x579
 191.08 reacquiring id=28   ep=2 age=  9400 unc= 1911.0 q=0.03 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.64 221,4 371x518
 191.18 reacquiring id=28   ep=2 age=  9500 unc= 1940.7 q=0.02 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.70 229,-11 362x665
 191.28 reacquiring id=28   ep=2 age=  9567 unc= 1960.5 q=0.02 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.70 235,4 354x592
 191.38 reacquiring id=28   ep=2 age=  9633 unc= 1980.4 q=0.02 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.72 237,3 352x583
 191.48 reacquiring id=28   ep=2 age=  9767 unc= 2020.5 q=0.01 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.56 227,-8 369x700
 191.58 reacquiring id=28   ep=2 age=  9867 unc= 2050.6 q=0.01 box=495,-3 152x129     | 31:per 0.16 224,3 372x425C 33:per 0.59 232,5 370x615
 191.68 lost        id=None ep=2 age= 10000 unc= 2091.1 q=0.00 box=-                  | 31:per 0.35 295,-1 326x257 33:per 0.27 244,4 367x569C
 191.78 lost        id=None ep=2 age= 10100 unc= 2091.1 q=0.00 box=-                  | 31:per 0.72 322,-2 314x277 33:per 0.27 244,4 367x569C
 191.88 lost        id=None ep=2 age= 10133 unc= 2091.1 q=0.00 box=-                  | 31:per 0.63 338,-1 300x271 33:per 0.27 244,4 367x569C
 191.98 lost        id=None ep=2 age= 10267 unc= 2091.1 q=0.00 box=-                  | 31:per 0.18 472,2 186x133C 33:per 0.27 244,4 367x569C
 192.08 lost        id=None ep=2 age= 10367 unc= 2091.1 q=0.00 box=-                  | 31:per 0.18 472,2 186x133C 33:per 0.27 244,4 367x569C
 192.18 lost        id=None ep=2 age= 10500 unc= 2091.1 q=0.00 box=-                  | 31:per 0.18 472,2 186x133C 33:per 0.27 244,4 367x569C
 192.28 lost        id=None ep=2 age= 10633 unc= 2091.1 q=0.00 box=-                  | 31:per 0.18 472,2 186x133C 33:per 0.27 244,4 367x569C 34:per 0.59 571,1 227x272
```

**Mechanism.** As the owner crouched, the engine kept id 28 alive on the shrinking, HEAD-ONLY box
above the chair back — the published lock box goes 297x716 → 210x413 → 224x313 → 276x159 → 152x129
over about a second — and the core, which had every reason to follow it (same tracker id, in gate),
also **learned it as the target's size**. When she stood up again as ids 30/31/33 (conf 0.16–0.35,
321x271, 326x257, 367x569 at x≈244–338) those boxes were 110–150 px from the frozen box, i.e. IN
gate, but scored only ~0.45: the size term is 0 against a 152x129 reference, and the in-gate floor was
`min_score` 0.5, not the widened 0.40 — which applied only OUT of gate and only until
`occlusion_ms + reacquire_ms` = 3.5 s, long past. Nothing could be taken, `obs_age_ms` ran to 10000,
LOST at 191.68, and the resolver re-locked as epoch 3 on id 34 at 192.38 (the `relocks 1` above).

**Fix (on-board fix round 4, Ruling 20 — `docs/decisions.md`).** (a) A candidate admitted only by the
same-id relaxation corrects POSITION but not SIZE, so a transiently-shrunken box can be followed but
not learned. (b) While REACQUIRING, every candidate — in-gate included — is scored against
`min_score_widened` (0.40) rather than `min_score` (0.5); CONFIRMED and OCCLUDED keep `min_score`.
(c) `reacquire_ms` 3000 → 9500, so the widened, full-frame search stays open for the whole
REACQUIRING band instead of closing 6.5 s before the lock expires.

**Replay of this capture through the fixed core** (`tests/test_lock_replay2.cpp` over
`tests/fixtures/lock_replay_routine2.json`, the rel. 170–205 s window, 348 rows, live tracks only,
node parity — **a replay number, not an on-board measurement**, and a weaker gate than the live
pipeline because the 10 Hz SSE sampling makes every inter-frame gap ~3x the real one):

```
lock_replay2: locked id 25 at t=89 ms (row 0 of 348)
lock_replay2: 3s hide  — id 28 first live t=6816 ms, CONFIRMED t=6816 ms (delta 0 ms)
lock_replay2: 6s hide  — first live conf>=0.25 person t=14949 ms, CONFIRMED t=14949 ms (delta 0 ms) on id 31
lock_replay2: size reference entering the re-emergence: 324.9x381.4
lock_replay2: LOST rows 0 (first at t=-1 ms)
```

Before the fix, the same replay against 217fb04's core (same fixture, same anchors; `ref_w`/`ref_h`
omitted because that build's `Output` has no such field):

```
3s hide: id 28 live t=6816 CONFIRMED t=6816 (delta 0)
6s hide: return t=14949 CONFIRMED t=-1 (delta -1) id -1
LOST rows 139 (first t=21079)
```

**Which of the three changes actually does it** (same replay, same fixture, parameters overridden one
at a time; (a) has no config switch so every row includes it):

```
round 4 defaults (a+b+c)               6s-hide CONFIRMED t= 14949 (delta     0) id  31 | LOST rows   0 (first     -1)
a+b, reacquire_ms 3000 (no c)          6s-hide CONFIRMED t=    -1 (delta    -1) id  -1 | LOST rows 139 (first  21079)
a+c, widened floor 0.5 (b inert)       6s-hide CONFIRMED t= 18061 (delta  3112) id  31 | LOST rows   0 (first     -1)
a only                                 6s-hide CONFIRMED t=    -1 (delta    -1) id  -1 | LOST rows 139 (first  21079)
```

So **(c) is what prevents the LOST** and **(b) is what turns a 3.1 s recovery into an immediate one**;
(a) changes nothing on this capture by itself.

**Results table: unchanged, still `TBD-bench`.** Run 7 is a diagnostic run of a build with a known
gate bug; the gate run is still owed.

**Red team on the fix.**
- **(a) does not do what its rationale claims on this capture, and the ablation above proves it.** The
  contamination in run 7 was *gradual* — the box shrank 716 → 698 → 475 → 372 → 277 → 271 px over
  about a second (rows 179.93–180.53), and with `q_size_frac` 0.5 a 625 px reference tolerates
  ±380–470 px of change per frame, so **every one of those steps passed the STRICT size gate** and
  was learned legitimately. (a) only bites on a single large jump. It is still the right rule — the
  unit test (case 20) shows it holding a 155x625 reference through the capture's own two head boxes
  at the board's 30 fps cadence — but on this capture the outcome is carried entirely by (b) and (c).
  **The open question this leaves for a Ruling 21: the strict size tolerance is so wide for a large
  reference that "strict" and "relaxed" barely differ there.** The lever is `q_size_frac`, and it
  should be decided from a bench run, not from this paragraph.
- **(c) opens the widened, full-frame search for the entire 10 s life of a lock.** On a single-person
  routine that is pure gain. On routine 3 (two-person swap) it is the main new risk: for 9.5 s
  instead of 3 s, any same-class, size-consistent box anywhere in frame is a candidate. The
  ambiguity margin (`ambiguity_ratio` 1.3, unchanged) is the only thing refusing them, and appearance
  (F3) — the real answer — is not built.
- **(b) lowers the in-gate floor from 0.5 to 0.40 for the whole reacquiring band.** Combined with
  (c) that is the loosest the core has ever been between 0.5 s and 10 s of obs_age. The
  counter-argument is that the alternative is measured: on 217fb04 the strict floor cost a whole
  6-second occlusion with the target standing in plain view.
- **All three replay numbers come from the capture the fix was derived from.** Run 8 on the fixed
  build, on a fresh routine 2 *and* routine 3, is what would actually test this.

### Run 6 (217fb04) — routine 1 re-measured: PASS

Fresh routine-1 (walk-out/return) capture on the round-3 build, person profile, owner alone in a lit
room. Long flushed capture `f1_r6_walk_long.txt` (600 s, mostly empty room — attempt 1 found the room
empty and was superseded) trimmed to the active window with `trim_capture.py`, committed as
`bench/evidence/2026-09-04-lock-core/run6_routine1_walk.txt.gz` (684 rows / 68.6 s). Harness row
(verbatim, pasted above in "Results"):

```
run6_routine1_walk.txt.gz                n=684     68.6s | states none/confirmed/occluded/reacquiring/lost =  7%/89%/ 1%/ 1%/ 0% | obs_valid  89% | core_miss_live   0% (1/616) | relocks  0 (false relocks  0) | id churn  6 | LOST events  0 | reacq min/mean/max 0.20/0.63/1.81s (4 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 195.59
```

**No 3-second full absence is visible in this particular capture** — the owner stayed partly detected
at the frame edge, or the walk-out was shorter than the routine calls for; this is a note about what
this specific run exercised, not a harness limitation. What the capture does show: the underlying
tracker renumbered the owner 6 times at close range (boxes ~780 px wide, arm/body movement swinging
the box), and `LockCore` rode through every one of them — 0 relocks, 0 `core_miss_live`. Against run 5
(same routine, pre-round-3 build `83b600c`): confirmed 62 % → 89 %, `core_miss_live` 29 % → 0 %,
relocks 4 → 0, LOST events 1 → 0, reacq max 10.54 s → 1.81 s. This is the first fresh-capture
confirmation of the round-3 fix (M-A/M-B/M-C) — run 5's own replay (0.9854 confirmed) was a regression
guard on the capture the fix was derived from; run 6 is independent evidence.

### Run 8 (217fb04) — routine 4 fast lateral: PASS, one attributed operator relock

Fast-lateral routine plus roughly 4 minutes of the owner moving about at close range, same build and
profile. Rows ≥215 s of the long routine-2 capture (`f1_r7_occl_long.txt`) were re-used for this
routine (the capture ran continuously across both routines); committed as
`bench/evidence/2026-09-04-lock-core/run8_routine4_lateral.txt.gz` (3123 rows / 313.5 s). Harness row
(verbatim, pasted above in "Results"):

```
run8_routine4_lateral.txt.gz             n=3123   313.5s | states none/confirmed/occluded/reacquiring/lost =  0%/99%/ 0%/ 0%/ 0% | obs_valid  99% | core_miss_live   0% (6/3103) | relocks  1 (false relocks  1) | id churn 41 | LOST events  0 | reacq min/mean/max 0.20/0.27/0.50s (11 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px  47.24
```

Confirmed 99 %, `core_miss_live` 0.2 % (6/3103), 0 LOST events, max `uncertainty_px` 47.24 px, reacq
max 0.5 s. `id churn 41` is the SDK tracker splitting the close-range owner into two alternating ids —
`LockCore` rode through all 41 without a relock. The single `relocks 1` is an `unlock()` at relative
401.58 s: core state went to NONE with no preceding LOST row and no epoch-change-by-expiry pattern —
only a click or a `target` command produces that shape, and the node did not start logging operator
commands (`lock: click ...` / `lock: target ...`) until commit `7d059ff`, which postdates this
capture. It is therefore **attributed** to an operator action (the owner or controller clicking or
issuing a target command during the close-range portion of the routine), not to the tracker — see the
red-team paragraph below for why this attribution is not proven by a log line.

### Run 9b (47fb866) — routine 2 re-run: PASS, no full occlusion produced

Second occlusion-routine capture on the round-4 build: three hides behind the office chair (planned
counts 3 s, 6 s, 9 s — the routine that run 7's 6-second hide had failed on the round-3 build).
Trimmed from `f1_r9b_occl_long.txt` to the active window, committed as
`bench/evidence/2026-09-04-lock-core/run9b_routine2_occlusion.txt.gz` (800 rows / 80.2 s). Harness row
(verbatim, pasted above in "Results"):

```
run9b_routine2_occlusion.txt.gz          n=800     80.2s | states none/confirmed/occluded/reacquiring/lost = 54%/26%/ 2%/12%/ 3% | obs_valid  26% | core_miss_live   0% (0/213) | relocks  0 (false relocks  0) | id churn  0 | LOST events  1 | reacq min/mean/max 0.20/0.44/0.90s (6 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 2129.14
```

**The chair's mesh back never fully occluded the owner** — coasting boxes at conf 0.15–0.6 persisted
through every hide, so no full 9-second (or even 6-second) occlusion exists in this data; the round-4
fix's actual target scenario (a real multi-second full occlusion recovering on the same id) is
regression-tested only by the run-7 replay (`lock_replay2`, above), not re-proven on a fresh full
occlusion here. What this run does show: every hide that did occur recovered on the SAME id within
0.9 s (6 reacquire episodes, min/mean/max 0.20/0.44/0.90 s), and the single LOST event is the owner
walking out of frame at the end of the routine and not returning within the 10 s expiry window — by
design, not a failure of the occlusion fix.

### Run 10e (`097bfad`) — phone: detector starvation and a silent false lock

Routine 5, the phone routine, on the all-classes config. **This is the run that found the F1 lock
core's worst failure so far, and the run whose harness row would have been read as a pass.** Capture:
`bench/evidence/2026-09-04-lock-core/run10e_routine5_phone.txt.gz`, 900 s at ~29 rows/s (the shim's
`SSE_MAX_HZ` was raised 10 → 30 for this run — see `hosts/hailo15l/README.md` §9). Windows cut with
`cut_windows.py` (committed next to the capture): `A:78.3:93.7`, `B120:97.5:217.5`, `B:97.5:901` —
re-cutting with those exact specs reproduces the three files byte-for-byte.

Harness rows and detector statistics, verbatim (`lock_metrics.py` and `phone_detect_stats.py`, both
committed in that directory). **These rows are from the round-4 harness, before `class switches`
existed; re-running today's harness over the same windows adds `class switches  0` to each and
changes nothing else, because this capture's build published the class frozen at `lock()`:**

```
f1_r10e_phone_A.txt n=447     15.4s | states none/confirmed/occluded/reacquiring/lost =  0%/10%/19%/69%/ 0% | obs_valid  10% | core_miss_live  23% (14/59) | relocks  1 (false relocks  1) | id churn  6 | LOST events  1 | reacq min/mean/max 0.07/0.35/1.72s (12 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 2083.13
cell phone   live-box rows  28.6% | live conf median 0.27 mean 0.33 max 0.79 | distinct ids 8 | rows with >=2 live boxes 4.5%
person       live-box rows 100.0% | live conf median 0.91

f1_r10e_phone_B120.txt n=3494   120.0s | states none/confirmed/occluded/reacquiring/lost =  0%/68%/15%/15%/ 0% | obs_valid  68% | core_miss_live   7% (182/2567) | relocks  0 (false relocks  0) | id churn 44 | LOST events  0 | reacq min/mean/max 0.07/0.36/6.43s (116 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 1082.69
cell phone   live-box rows  36.7% | live conf median 0.55 mean 0.54 max 0.92 | distinct ids 38 | rows with >=2 live boxes 7.2%
person       live-box rows 100.0% | live conf median 0.90

f1_r10e_phone_B.txt n=23323  802.5s | states none/confirmed/occluded/reacquiring/lost =  0%/95%/ 2%/ 2%/ 0% | obs_valid  95% | core_miss_live   0% (182/22396) | relocks  0 (false relocks  0) | id churn 44 | LOST events  0 | reacq min/mean/max 0.07/0.36/6.43s (116 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px 1082.69
cell phone   live-box rows   5.9% | live conf median 0.55 mean 0.53 max 0.92 | distinct ids 47 | rows with >=2 live boxes 1.1%
person       live-box rows  20.2% | live conf median 0.90
```

**Detector starvation (window A, the acquisition struggle).** In the 15.4 s before the lock settled,
the detector had a live `cell phone` box on only **28.6 %** of rows at a median confidence of **0.27**
(max 0.79), handing out **8** distinct ids for it and producing two live boxes for the same object on
4.5 % of rows — while the owner's own `person` box was live on **100 %** of rows at median 0.91. The
core spent 69 % of that window `reacquiring` with 1 LOST event and 1 relock. Nothing about the lock
core explains those numbers: yolo26m at 640×640 simply does not see a hand-held phone reliably, and
every lock-side metric in this routine sits downstream of that. The same starvation is why `id churn`
reaches 44 in window B — the tracker renumbers an object the detector keeps losing.

**The false lock (window B).** Window B's **95 % `confirmed` is a false lock for roughly 735 of its
802 s.** The lock held the moving phone through ids 125/136 until rel. ~146 s. The phone then left or
was hidden, and the core — `reacquiring`, with round 4's widened floor 0.40 applying in-gate
(Ruling 20b) — hopped across DIFFERENT-CLASS in-gate candidates at quality 0.40–0.56: id 140, 144,
145, 146, 147 (`remote`), 149 (`remote`) / 150 (`cell phone` — the same physical object detected as
both), 161, 160, 176, and at **rel. 165.71 s settled on id 163**, a static box labelled
`chair`/`suitcase`, conf 0.84–0.92, 229×270 px at (343,447). It stayed `confirmed` on that box until
the capture ended at 900 s, publishing `lock.class = "cell phone"` the whole time.

The id-change listing, verbatim
(`python3 bench/evidence/2026-09-04-lock-core/rows.py run10e_routine5_phone.txt.gz 140 166 | awk '{ if ($3 != prev) { print; prev = $3 } }'`
— one line per change of the published `lock.id`, the core's own state on the left, that frame's whole
`tracks[]` on the right, `C` marking a coasting entry):

```
 140.01 occluded    id=136  ep=3 age=   100 unc=   12.6 q=0.49 box=866,232 127x168    | 7:pot 0.30 1,562 152x158 18:per 0.94 440,75 535x644 83:pot 0.19 0,528 272x191 119:sci 0.18 54,208 291x235 122:cha 0.16 423,194 224x94C 124:cha 0.28 286,282 251x436 125:cel 0.66 867,231 124x168 126:cha 0.55 352,195 295x518 130:cha 0.19 312,141 121x214C 135:han 0.18 611,612 156x107C 136:rem 0.38 866,231 125x169
 140.04 confirmed   id=125  ep=3 age=     0 unc=   10.9 q=0.84 box=868,232 125x168    | 7:pot 0.28 1,560 152x160 18:per 0.94 441,74 535x646 83:pot 0.22 0,528 272x190 119:sci 0.20 54,208 291x235 122:cha 0.16 423,195 224x93 124:cha 0.38 284,283 252x436 125:cel 0.78 867,231 124x168 126:cha 0.49 356,194 290x518 130:cha 0.19 312,141 121x214C 135:han 0.18 611,612 156x107C 136:rem 0.38 866,231 125x169C
 140.21 confirmed   id=136  ep=3 age=     0 unc=   10.6 q=0.70 box=868,232 126x169    | 7:pot 0.33 1,562 152x157 18:per 0.94 441,76 537x644 83:pot 0.19 -0,528 275x191 119:sci 0.18 55,208 290x236 122:cha 0.15 423,195 226x94 124:cha 0.45 282,283 255x433 125:cel 0.19 867,232 127x168C 126:cha 0.41 297,194 352x512 130:cha 0.19 312,141 121x214C 135:han 0.18 611,612 156x107C 136:rem 0.80 868,232 126x169
 140.30 confirmed   id=125  ep=3 age=     0 unc=   10.5 q=0.85 box=868,232 127x169    | 7:pot 0.29 1,562 152x157 18:per 0.94 440,76 539x643 83:pot 0.20 -1,527 274x192 119:sci 0.26 55,208 291x235 122:cha 0.17 423,194 225x94C 124:cha 0.32 283,283 255x435 125:cel 0.81 868,232 128x169 126:cha 0.56 358,194 284x516 130:cha 0.19 312,141 121x214C 135:han 0.18 611,612 156x107C 136:rem 0.20 869,232 126x169C
 140.37 confirmed   id=136  ep=3 age=     0 unc=    9.1 q=0.69 box=868,232 127x169    | 7:pot 0.37 1,562 152x157 18:per 0.94 441,76 536x644 83:pot 0.20 2,533 272x185 119:sci 0.26 55,208 291x235C 122:cha 0.17 423,194 225x94C 124:cha 0.26 283,283 254x435 125:cel 0.79 868,232 128x168C 126:cha 0.53 355,195 291x515 130:cha 0.19 312,141 121x214C 135:han 0.19 611,615 155x105C 136:rem 0.76 869,232 126x169
 140.54 confirmed   id=125  ep=3 age=     0 unc=    9.5 q=0.84 box=869,232 128x169    | 7:pot 0.31 1,561 153x158 18:per 0.94 441,77 540x644 83:pot 0.21 0,531 274x188 119:sci 0.17 56,208 290x234 122:cha 0.17 423,194 225x94C 124:cha 0.33 284,283 252x435 125:cel 0.78 870,231 128x169 126:cha 0.53 356,194 288x517 130:cha 0.19 312,141 121x214C 135:han 0.19 611,615 155x105C 136:cel 0.17 869,232 129x168C
 140.98 confirmed   id=136  ep=3 age=     0 unc=    9.2 q=0.79 box=872,234 128x168    | 7:pot 0.32 1,562 150x157 18:per 0.94 440,79 540x641 83:pot 0.19 -0,527 274x192 119:sci 0.18 55,208 291x235C 122:cha 0.23 424,196 224x93C 124:cha 0.26 284,284 255x434 125:cel 0.52 872,234 127x168C 126:cha 0.52 356,195 288x515 135:han 0.23 610,615 157x105 136:cel 0.55 871,234 128x168
 141.74 confirmed   id=125  ep=3 age=     0 unc=   11.1 q=0.78 box=860,218 137x174    | 7:pot 0.27 1,562 153x157 18:per 0.94 442,81 539x639 83:pot 0.23 -0,530 273x189 119:sci 0.23 55,208 291x235 122:cha 0.26 424,195 221x93 124:cha 0.48 282,282 261x436 125:cel 0.54 861,218 136x170 126:cha 0.39 283,194 364x517 135:han 0.19 614,614 152x106C 136:rem 0.17 856,217 141x182C
 142.21 confirmed   id=136  ep=3 age=     0 unc=    9.3 q=0.86 box=857,227 129x168    | 7:pot 0.27 1,562 151x158 18:per 0.94 440,74 529x646 83:pot 0.18 0,527 275x192 119:sci 0.22 55,208 291x234 122:cha 0.18 423,195 225x93C 124:cha 0.29 286,283 249x434 125:cel 0.75 857,227 130x169C 126:cha 0.51 359,194 287x519 135:han 0.16 611,613 153x107C 136:cel 0.84 857,228 128x167
 142.30 confirmed   id=125  ep=3 age=     0 unc=    9.6 q=0.86 box=856,228 129x167    | 7:pot 0.27 1,561 153x158 18:per 0.94 441,73 528x647 83:pot 0.21 0,528 276x191 119:sci 0.21 56,208 290x235 122:cha 0.18 423,195 225x93C 124:cha 0.29 286,283 250x435 125:cel 0.85 857,228 129x167 126:cha 0.53 362,194 284x517 135:han 0.16 611,613 153x107C 136:cel 0.19 857,228 127x168C
 143.44 confirmed   id=136  ep=3 age=     0 unc=   12.7 q=0.84 box=866,235 131x168    | 7:pot 0.29 1,561 151x158 18:per 0.94 441,75 537x646 83:pot 0.20 1,530 272x189 119:sci 0.16 55,208 291x235 122:cha 0.28 422,195 225x94C 124:cha 0.40 281,283 256x436 125:cel 0.17 865,235 132x168C 126:cha 0.45 298,195 353x514 135:han 0.16 611,613 153x107C 136:cel 0.75 866,235 130x168
 144.04 confirmed   id=125  ep=3 age=     0 unc=   12.1 q=0.83 box=866,234 131x168    | 7:pot 0.20 1,561 152x158 18:per 0.94 440,74 538x644 83:pot 0.20 -0,526 274x193 119:sci 0.15 55,208 291x234 122:cha 0.22 424,195 222x93 124:cha 0.29 286,283 251x436 125:cel 0.74 865,235 132x167 126:cha 0.46 357,195 283x520 135:han 0.18 611,611 153x108C 136:cel 0.62 866,235 130x167C
 144.14 confirmed   id=136  ep=3 age=     0 unc=   10.3 q=0.83 box=865,234 131x168    | 7:pot 0.32 1,562 151x157 18:per 0.93 439,74 539x645 83:pot 0.21 0,526 270x192 119:sci 0.19 54,209 291x235C 122:cha 0.22 424,195 222x93C 124:cha 0.32 284,283 253x436 125:cel 0.63 865,234 130x168C 126:cha 0.52 340,195 304x520 135:han 0.17 607,612 158x108C 136:cel 0.72 865,233 131x168
 144.71 confirmed   id=125  ep=3 age=     0 unc=   14.9 q=0.83 box=865,233 129x168    | 7:pot 0.30 1,562 152x157 18:per 0.94 442,68 534x652 83:pot 0.21 3,542 272x176 119:sci 0.23 55,208 291x235C 122:cha 0.27 424,195 223x94 124:cha 0.47 285,283 252x436 125:cel 0.72 865,234 129x168 126:cha 0.30 355,195 290x519 135:han 0.17 607,612 158x108C 136:cel 0.26 863,233 131x168C
 146.48 confirmed   id=140  ep=3 age=     0 unc=   17.5 q=0.41 box=981,248 67x127     | 7:pot 0.29 1,563 152x156 18:per 0.92 443,68 583x651 83:pot 0.21 1,537 271x182 119:sci 0.17 55,209 289x235C 122:cha 0.16 402,194 174x91C 124:cha 0.27 157,194 420x513 125:cel 0.29 840,198 104x169C 126:cha 0.43 335,195 240x507 135:han 0.29 600,612 158x107C 136:cel 0.38 858,229 131x169C 139:cha 0.16 312,141 117x215C 140:cel 0.58 985,252 63x124 141:kni 0.24 984,251 63x124 142:sci 0.24 986,229 57x135C
 148.71 confirmed   id=144  ep=3 age=     0 unc=   15.9 q=0.53 box=562,213 110x145    | 7:pot 0.25 1,565 154x155 18:per 0.89 333,73 498x646 83:pot 0.19 3,537 268x183 119:sci 0.17 55,209 289x235C 122:cha 0.15 429,199 137x91C 124:cha 0.27 154,192 426x520C 126:cha 0.27 281,200 287x452C 140:kni 0.40 726,243 124x173C 141:cel 0.27 919,214 96x149C 143:cha 0.18 158,193 772x525C 144:cel 0.67 560,207 109x143 145:cel 0.20 565,210 115x197C
 148.87 confirmed   id=145  ep=3 age=     0 unc=    9.5 q=0.62 box=512,192 113x178    | 7:pot 0.21 1,564 151x156 18:per 0.91 331,68 505x651 83:pot 0.20 2,532 266x187 119:sci 0.17 55,209 289x235C 122:cha 0.15 429,199 137x91C 124:cha 0.27 154,192 426x520C 126:cha 0.27 281,200 287x452C 140:kni 0.40 726,243 124x173C 141:cel 0.27 919,214 96x149C 143:cha 0.18 158,193 772x525C 144:cel 0.24 521,198 112x161C 145:cel 0.58 510,194 114x199
 149.54 confirmed   id=146  ep=3 age=     0 unc=   18.4 q=0.52 box=304,147 129x238    | 7:pot 0.24 1,564 152x155 18:per 0.92 266,48 624x671 83:pot 0.24 -0,538 271x182 122:cha 0.29 447,178 118x209C 124:cha 0.27 154,192 426x520C 126:cha 0.27 281,200 287x452C 140:kni 0.40 726,243 124x173C 141:cel 0.27 919,214 96x149C 143:cha 0.16 174,460 621x260C 144:cel 0.24 521,198 112x161C 145:cel 0.43 447,179 117x210C 146:hai 0.30 303,140 131x244
 149.93 confirmed   id=147  ep=3 age=     0 unc=   10.7 q=0.51 box=269,171 119x222    | 7:pot 0.15 1,565 152x155 18:per 0.92 244,52 646x667 83:pot 0.23 -1,538 272x184 122:cha 0.29 447,178 118x209C 124:cha 0.27 154,192 426x520C 126:cha 0.27 281,200 287x452C 140:kni 0.40 726,243 124x173C 143:cha 0.16 174,460 621x260C 144:cel 0.24 521,198 112x161C 145:cel 0.43 447,179 117x210C 146:rem 0.24 280,173 118x222C 147:rem 0.27 276,174 119x221
 151.76 confirmed   id=149  ep=3 age=     0 unc=   21.9 q=0.40 box=477,199 123x201    | 7:pot 0.23 1,563 154x156 18:per 0.92 328,61 557x657 83:pot 0.19 1,528 269x192 143:cha 0.16 176,452 713x267C 146:rem 0.24 280,173 118x222C 147:rem 0.18 53,219 284x226C 148:bot 0.19 281,462 42x32C 149:cel 0.42 479,200 124x200 150:cel 0.22 457,198 130x203C
 155.16 confirmed   id=150  ep=3 age=     0 unc=   15.2 q=0.56 box=462,218 104x179    | 7:pot 0.19 1,564 153x155 18:per 0.90 321,117 496x601 83:pot 0.31 2,553 270x165 143:cha 0.15 271,452 594x267C 149:rem 0.45 467,220 102x176C 150:cel 0.29 470,223 101x175 151:rem 0.23 591,186 116x213C
 155.43 confirmed   id=149  ep=3 age=     0 unc=    8.8 q=0.65 box=494,245 85x161     | 7:pot 0.26 1,564 151x155 18:per 0.88 321,147 503x573 83:pot 0.21 3,534 271x185 143:cha 0.15 271,452 594x267C 149:rem 0.74 498,246 83x158 150:cel 0.62 491,245 85x160C 151:rem 0.23 591,186 116x213C
 158.90 confirmed   id=161  ep=3 age=     0 unc=   15.9 q=0.41 box=205,223 136x180    | 7:pot 0.16 1,562 157x157 18:per 0.90 168,156 653x564 83:pot 0.31 3,535 272x184 143:cha 0.21 398,220 172x388C 149:cel 0.30 581,229 85x159C 151:rem 0.34 582,228 86x166C 152:per 0.19 448,151 186x155 153:ben 0.17 790,411 137x118C 154:cha 0.20 354,220 521x402C 155:tv 0.16 798,258 65x122C 156:han 0.17 680,419 117x89C 157:cel 0.28 483,315 88x59C 158:cel 0.16 484,317 63x57C 159:tv 0.18 310,142 130x214C 160:hai 0.32 191,220 149x202C 161:hai 0.44 202,222 139x181
 159.75 occluded    id=160  ep=3 age=    33 unc=   13.6 q=0.50 box=232,241 113x171    | 7:pot 0.17 1,564 153x156 18:per 0.89 194,161 632x559 83:pot 0.23 2,529 271x191 143:cha 0.21 398,220 172x388C 149:cel 0.30 581,229 85x159C 151:rem 0.34 582,228 86x166C 152:per 0.15 448,153 199x156 154:cha 0.20 354,220 521x402C 156:han 0.17 680,419 117x89C 157:cel 0.28 483,315 88x59C 158:cel 0.16 484,317 63x57C 159:tv 0.17 311,141 130x219C 160:hai 0.17 227,243 116x165 161:hai 0.55 227,243 115x164 162:ben 0.16 670,467 254x111C
 159.90 confirmed   id=161  ep=3 age=     0 unc=    8.7 q=0.58 box=226,243 117x164    | 7:pot 0.17 1,560 155x160 18:per 0.90 196,161 628x558 83:pot 0.39 0,526 276x192 143:cha 0.21 398,220 172x388C 149:cel 0.30 581,229 85x159C 151:rem 0.34 582,228 86x166C 152:per 0.17 448,154 207x153C 154:cha 0.20 354,220 521x402C 156:han 0.17 680,419 117x89C 157:cel 0.28 483,315 88x59C 158:cel 0.16 484,317 63x57C 159:tv 0.18 312,141 130x217 160:hai 0.51 224,246 117x163C 161:hai 0.41 223,243 117x165 162:ben 0.16 670,467 254x111C
 160.00 confirmed   id=160  ep=3 age=     0 unc=    9.0 q=0.54 box=223,240 114x168    | 7:pot 0.24 1,563 153x155 18:per 0.89 199,163 626x557 83:pot 0.31 2,543 271x174 149:cel 0.30 581,229 85x159C 151:rem 0.34 582,228 86x166C 152:per 0.18 448,154 204x150 154:cha 0.20 354,220 521x402C 157:cel 0.28 483,315 88x59C 158:cel 0.16 484,317 63x57C 159:tv 0.20 312,141 128x218 160:hai 0.27 220,240 115x170 161:hai 0.23 222,240 111x168C 162:ben 0.16 670,467 254x111C
 164.63 confirmed   id=176  ep=3 age=     0 unc=   16.9 q=0.46 box=586,373 135x285    | 7:pot 0.21 1,564 151x154 18:per 0.93 502,153 524x565 83:pot 0.28 2,550 267x167 152:per 0.19 527,228 124x211C 159:tv 0.17 311,142 127x217 163:cha 0.68 268,292 367x424 166:cha 0.19 368,295 253x365C 167:toi 0.18 1170,561 108x159C 168:rem 0.17 666,245 105x198C 169:cha 0.52 590,375 138x284C 170:cel 0.27 637,243 123x204C 171:sci 0.16 55,209 288x234C 172:per 0.15 562,148 218x144C 173:sci 0.15 56,213 290x403C 174:cha 0.74 439,208 184x94 175:cha 0.16 557,211 92x73 176:cel 0.73 586,372 135x288
 165.71 confirmed   id=163  ep=3 age=     0 unc=   28.3 q=0.40 box=343,447 229x270    | 7:pot 0.32 1,564 150x155 18:per 0.90 461,140 604x578 83:pot 0.15 3,563 314x157 152:per 0.17 619,237 275x132C 159:tv 0.17 311,141 130x221C 163:cha 0.84 336,452 237x267 166:cha 0.27 538,370 156x288C 168:rem 0.17 666,245 105x198C 169:cha 0.23 551,367 156x290C 170:cel 0.27 637,243 123x204C 171:sci 0.21 56,208 288x236C 172:per 0.15 562,148 218x144C 173:sci 0.15 56,213 290x403C 174:cha 0.22 626,233 97x71 175:cha 0.19 560,210 88x74C 176:cel 0.15 550,368 153x289C 177:sui 0.29 296,361 146x347 178:sui 0.18 348,450 287x269C 179:rem 0.15 1122,340 18x16C
```

Read the class abbreviations on the right: `cel` = cell phone, `rem` = remote, `kni` = knife,
`hai` = hair drier, `cha` = chair, `sui` = suitcase. The walk is visible as the core's `id=` column
stepping through objects whose live box on that same row carries a different class each time, ending
on `163:cha 0.84` at 165.71 s.

**Mechanisms.** (1) **Class was a soft 0.15 score term**, so a high-confidence box of any class could
win on `w_conf·conf + w_motion·exp(-d²/2)` alone. (2) **The relative size model** (`q_size_frac` 0.5
per second) legitimately tolerates a ~2.3× wider box after a few seconds unobserved — right for a
person walking toward the camera, wrong for "anything roughly over there". (3) **Ruling 20b's in-gate
floor 0.40 while `reacquiring`**, which is what let quality-0.40 candidates win at all.

**This round's fix (on-board fix round 5, Ruling 22, `docs/decisions.md`).** A **class gate** — a
different-class candidate is eligible only if it carries the core's own tracker id, in any state and
in either stage; a hard **`size_ratio_max` 1.6** on different-id candidates, applied on top of the
variance-aware tolerance; and **`lock.class` now publishes the class of the last associated
observation**, so a class change is visible at all. The accepted cost of the class gate, stated
plainly: an object the detector re-labels under a NEW id is not re-acquired until a same-class
detection appears again — telling that apart from a different object nearby needs appearance matching
(F3, not built).

**Replay evidence, before and after** (`services/garuda-perception/tests/test_lock_replay_phone.cpp`
over `tests/fixtures/lock_replay_phone.json`, the rel. 97.5–200.0 s window, 2981 rows). Both blocks
are that test's own printed output, on the pre-fix build and after:

```
pre-fix  (097bfad):
  CONFIRMED on 758 of 946 rows carrying a live 'cell phone' box in 0-48500 ms = 0.8013
  cross-class CONFIRMED (different class AND different id) = 12 (first at t=5888 ms on id 116, class 'remote')
  rows CONFIRMED on the false-lock id 163 = 958
  final row t=102441 ms state=confirmed last_id=163 winner class 'suitcase'

post-fix (this round):
  CONFIRMED on 771 of 946 rows carrying a live 'cell phone' box in 0-48500 ms = 0.8150 (pre-fix 0.8013, floor 0.7813)
  cross-class CONFIRMED (different class AND different id) = 0
  rows CONFIRMED on the false-lock id 163 = 0
  final row t=102441 ms state=lost last_id=188 winner class '-'
```

The phone half does not regress (0.8013 → 0.8150 — **not** a claim that the fix improves phone
tracking; the fix removes candidates, and the small rise is one capture's worth of the core no longer
being dragged away from a phone box by a nearby different-class one, well inside what a single
capture can show). After the fix the lock **expires** once the phone is genuinely gone, which is the
correct outcome and the one the pre-fix run replaced with twelve minutes of suitcase.

**Red team (rule 9).**

- **The F1 metrics table's `relocks` column was blind to this failure.** The entire walk happened
  inside one epoch, so `relocks` read 0 and "false relocks", which aliased `relocks`, read 0 with it.
  `id churn` did move (44) but is documented as a *success* metric, so a reader following the
  documentation would have taken it as evidence the core rode through churn correctly. **`class
  switches` is added this round** and the false-relocks alias is now `relocks + class_switches` — but
  see the next point.
- **`class_switches` cannot retro-detect this capture.** The build that produced run 10e published
  `lock.class` frozen at `lock()`, so the column reads 0 over `run10e_routine5_phone.txt.gz` even with
  today's harness. It only works on captures from round 5 onward. No attempt is made to reconstruct
  it from `tracks[]`; that would be inventing a number.
- **The fix is validated by replaying the capture it was derived from.** Same caveat as rounds 3 and
  4: `test_lock_replay_phone` is a regression guard, not independent evidence the class gate and the
  ratio cap generalise. An independent phone capture on the round-5 build is owed.
- **The class gate's cost is untested on real data.** No capture in this round contains "the target
  disappears and returns under a new id with a different label" — the case the gate now refuses. Its
  cost is argued from the mechanism, not measured.
- **`size_ratio_max` 1.6 is derived, not measured.** It comes from the geometry a fast approach or
  retreat needs within a 10 s lock lifetime, not from any capture. Whether a real routine ever needs
  more than 1.6 on a *different* id is unknown.
- **One routine, one capture, one build.** Routine 5 was run once, and the fix rounds are serial:
  nothing here isolates the round-5 changes from rounds 3 and 4 on live hardware.

### Conditions (routines 1, 2, 4 — runs 6, 8, 9b; routine 5 — run 10e)

- **Room/light/distance:** owner alone in a small, lit room (light on from run 5 onward — runs 1–4
  were in a darker room; not recorded whether light level was otherwise controlled), SBC on the desk
  at approximately 0.6 m height, IMX678 wide lens, 1280×720 published frame.
- **Config per run:** all three runs (6, 8, 9b) used `config/perception-yolov8m.json`, person profile
  (`classification_id 1`), hailo/Kalman tracker engine — the identical `lock` block documented in this
  section's "Setup" above, with the round-3/round-4 changes (relative gates, same-id relaxation,
  `min_score_widened` 0.40, `reacquire_ms` 9500) already deployed.
- **Board build per run:** run 6 and run 8 on `217fb04` (round 3); run 9b on `47fb866` (round 4, the
  final commit of the fix wave); **run 10e on `097bfad`**.
- **Thermal/load sample.** One read-only sample taken during this closing-docs round (2026-09-04,
  `ssh root@10.0.0.1 'date; cat /sys/class/thermal/thermal_zone0/temp; uptime'`), NOT taken during the
  routine captures themselves — this is a point sample after the fact, not a per-run thermal log:
  ```
  Fri Sep  4 12:14:43 UTC 2026
  84310
   12:14:43 up  5:58,  0 users,  load average: 1.26, 1.69, 1.77
  ```
  84310 m°C = 84.3 °C; uptime 5 h 58 m since the board's last boot; load average 1.26/1.69/1.77 on a
  4-core A53. **The board's clock read within 6 seconds of the PC's own UTC clock at sample time**
  (`date -u` on the PC: `Fri Sep 4 12:14:49 UTC 2026`) — this contradicts an earlier working
  assumption (recorded in this round's own closing-docs brief) that the board's RTC runs "~3.5 h
  ahead of the PC"; that assumption does not hold for this sample, and no explanation for the
  discrepancy (NTP sync since, a corrected RTC, or the earlier assumption itself having been wrong) is
  recorded here — stated as observed, not reconciled. No `vcgencmd`-style throttling reading exists on
  this board (that command is Raspberry Pi-specific); the thermal-zone temperature and `uptime` load
  average are the only load/thermal signal available.
- **Phone routine (routine 5 / run 10e):** not recorded whether the room/light/distance conditions
  matched routines 1/2/4 — the phone routine is a different physical setup (a phone held in hand, not
  the owner's own body). Its config was a **scratch copy** of `config/perception-yolov8m.json` with
  `classification_id -1` (all COCO classes tracked) and `jpeg_fps 30`, deployed for that routine only
  and **not** committed; the committed configs keep their own `jpeg_fps`. The PC-side shim ran with
  `SSE_MAX_HZ = 30.0` (raised from 10.0 for this run and committed in round 5), so the capture samples
  at ~29 rows/s rather than the ~10 rows/s of every earlier run in this section — durations and
  fractions from run 10e are therefore **not** sample-rate-comparable with runs 1–9b. The owner made
  7 clicks over the routine; the first phone lock is the board log's
  `lock: click (319,315) -> id 71`.
- **Board CPU/thermal during run 10e's configuration.** One `top -bn1` sample, taken 2026-09-04
  13:02:35 board time with `jpeg_fps 30`, SSE 30 Hz and one SSE client connected:
  `garuda-perception 100.0 %CPU` (one of the four A53s saturated), `isp_media_server 29.4 %`,
  `%Cpu(s) 33.3 us / 8.7 sy / 56.5 id`, load average 2.13, `thermal_zone0 83197` m°C (83.2 °C).
  **No before-sample at 10 Hz / 15 fps exists** (rule 1 — it was never taken and none is invented),
  so this says nothing about the cost of the rate change itself. That the node saturates one core is
  an **open item: profile it** — detector, post-process, JPEG encode and SSE fan-out are all inside
  that 100 % and none has been attributed.

### Red-team, closing round (rule 9)

- **Owner-paced, no independent ground truth.** Every routine is timed and shaped by the owner in the
  moment; the only record of "did the owner actually hide for 6 s / walk out for 3 s / move fast
  laterally" is the owner's own sense of having done it, cross-checked against the capture after the
  fact. There is no external timer, marker, or second camera confirming routine timing or owner
  position independent of the same detector/tracker pipeline being evaluated.
- **A single person was in the room for every measured routine.** Routine 3 (two-person swap) — the
  one routine that would exercise the ambiguity margin and the round-4 widened-to-expiry window
  (`reacquire_ms` 9500) against a second same-class candidate — was not run (owner: "no second person
  today"). Everything this round measured about the widened search window and the ambiguity margin is
  therefore from a single-target scene; the two-person risk flagged in this section's own red-team
  paragraphs on runs 5 and 7 (above) remains unaddressed by data.
- **The mesh-backed chair never produced a full occlusion.** In both the routine-2 attempts that used
  it (run 7's 6-second hide, run 9b's three hides), coasting boxes at conf 0.15–0.6 persisted through
  the hide because the chair's mesh back is partially see-through to the detector. The round-4 fix's
  10-second expiry window has therefore only been exercised on this board by the owner leaving the
  frame entirely (run 9b's single LOST event, and run 7 before the fix), never by a genuinely full,
  multi-second object occlusion of a still-present target.
- **~10 Hz SSE sampling undercounts sub-100 ms events.** The capture script polls the snapshot stream
  at roughly 10 Hz; any state transition, association, or brief detector flicker faster than about
  100 ms can fall entirely between two sampled rows. Reacquire durations at or near the 0.20 s floor
  (the minimum reported across all three runs) are likely quantized by the sampling interval rather
  than measuring the true recovery latency, and the same applies to `id churn` counts — a rapid
  double-switch between samples reads as one. **This applies to runs 1–9b only.** Run 10e was taken
  after the shim's `SSE_MAX_HZ` was raised to 30 and samples at ~29 rows/s, near the pipeline's own
  frame rate — which is also why its `id churn` (44) and reacquire-episode count (116) are not
  comparable with the earlier runs' at all: it is seeing roughly three times as many rows per second.
- **The relocks column was blind to run 10e's false lock, and the column added to fix that cannot see
  it either.** The twelve-minute walk onto a suitcase happened inside one epoch, so `relocks` — and
  the "false relocks" alias built on it — read 0. Round 5 adds `class_switches` and redefines the
  alias as `relocks + class_switches`, but the metric depends on `lock.class` being able to change,
  which it could not on the build that produced run 10e; the new column reads 0 over that capture
  too. **Every routine-5 number in the table above therefore comes from a capture whose own
  false-lock detector does not work.** Only a fresh capture on a round-5 build can close this.
- **The round-3 and round-4 fixes were derived from runs 5 and 7, and the only replay tests that
  exist reuse those same captures.** `lock_replay`/`lock_replay2` (in the "Run 5" and "Run 7" sections
  above) are regression guards proving the fixed code still handles the exact sequence that motivated
  the fix — they are not independent evidence the fix generalises. Run 6 is independent evidence for
  the round-3 fix (a fresh routine-1 capture); run 9b is a fresh routine-2 capture but, per the point
  above, never produced the full occlusion the round-4 fix targets, so the round-4 fix's core claim
  (recovery from a real multi-second full occlusion) still rests only on the run-7 replay.
- **Run 8's one relock is attributed to an operator action with no log line proving it.** The node did
  not start logging click/target commands until commit `7d059ff`, which postdates run 8's capture; the
  attribution (a click or target command, not a tracker-internal event) rests on the shape of the
  transition (NONE with no preceding LOST row, no epoch-change-by-expiry pattern) matching the two
  known `unlock()` call sites, not on direct evidence from this capture.
- **The person profile (`classification_id 1`) was used for routines 1/2/4 (runs 6/8/9b); the
  all-classes config (`classification_id -1`) was used for routine 5 (run 10e) only.** No routine in
  this round tests the person profile and the all-classes config under otherwise-identical conditions,
  so any difference between routine 5's numbers and routines 1/2/4's cannot be attributed to the
  profile alone — the target class, size, typical motion, the `jpeg_fps` setting and the SSE sample
  rate all differ too.
- **Routine 5's headline problem is the detector, not the lock core.** yolo26m at 640×640 held a live
  `cell phone` box on 28.6 % of rows (window A) and 5.9 % (window B) at median confidence 0.27–0.55,
  against 100 % / median 0.91 for the owner's own `person` box on the same frames. Every lock-side
  number for this routine sits downstream of that, and no amount of gate tuning can fix a target the
  detector does not see — F4 (DSP-cropped ROI for small objects) is the planned answer and is not
  built.
- **No `vcgencmd`-style throttling reading exists on this board.** The one thermal/load number this
  round has (`thermal_zone0/temp`, `uptime` load average, above) is a single point sample taken after
  the routines, not a per-run log; whether any routine ran under thermal throttling is unrecorded.

### What F1 measured, and what it did not (2026-09-04 closing round)

**Measured:** across three fresh, owner-run, single-target routines (walk-out/return, occlusion behind
an object, fast lateral) on the round-3/round-4 build, `LockCore` held its published identity through
6 and 41 tracker-level id renumberings respectively without a false relock; recovered from every
partial occlusion/hide it was actually given within 0.9 s; and produced exactly one relock across all
three routines, attributed (not proven) to an operator action rather than a tracker failure. The
round-3 gate fixes (M-A/M-B/M-C) are now confirmed on an independent fresh capture (run 6), not just
the run-5 replay they were derived from.

**Not measured:** a real multi-second full occlusion (the mesh chair never produced one — the
round-4 fix's core scenario is still only replay-tested on run 7's own capture); the two-person
ambiguity/widened-search-window risk (routine 3 skipped, no second person available); any
visual-tracking bridge across a detector gap (F2 does not exist yet, so every gap measured here is a
raw detector miss); appearance-based re-identification (F3); DSP-cropped ROI for small/distant targets
(F4); click-to-frame timing races (F5); and ego-motion compensation (F6) — none of the F2–F6
capabilities this spec's §8.2 defines have been built, so this round is a floor for F1 alone.

**Routine 5 (phone) is now run, and it moved from "not measured" to "measured and failed".** Run 10e
exposed a silent false lock — twelve minutes `confirmed` on a static suitcase while publishing
`cell phone` — that on-board fix round 5 (Ruling 22) addresses with a class gate, a hard size-ratio
cap and a truthful `lock.class`. **What is still not measured about it:** a phone routine on the
round-5 build (the fix is validated only by replaying run 10e's own capture); the class gate's cost
(a target that returns under a new id *and* a new label is now refused, and no capture contains that
case); whether `size_ratio_max` 1.6 is ever too tight on real data (the value is derived from
geometry, not measured); and small-object detection itself, which is the routine's actual bottleneck
(5.9–28.6 % live-box rows) and needs F4, not a lock-core change.

**Next** (spec §8.2 order the owner chooses among): F2 visual tracker, F4 DSP ROI for small objects,
F3 appearance, F5 click–frame sync, F6 ego-motion; routine 3 (two-person swap) still to be measured
once a second person is available, and routine 5 to be re-run on a round-5 build.

### Round 6 — duplicate same-class tracks

Re-reading run 8's own committed capture
(`bench/evidence/2026-09-04-lock-core/run8_routine4_lateral.txt.gz`, already the source of that run's
`id churn 41`) turned up the mechanism: at rel. ~110.4 s the frame carries TWO live `person` records on
the one owner, id 38 box `(193,124,819,595)` and id 39 box `(195,125,655,594)` — id 39 wholly inside
id 38 — and this full-body/torso pair recurs for most of the routine's close-range portion. The
yolo26m HEF's baked NMS does not suppress a box mostly contained inside another same-class box, so the
SDK's one-to-one LAPJV tracker births a second track for the torso detection; `keep_lost_frames 75`
then keeps both ids alive for up to 2.5 s and whichever box a frame's one real detection resembles
wins that frame's id, producing the alternation `id churn` counts.

Fix (Ruling 23): `HailoTrackAdapter::update()` now dedupes its own LIVE (`time_since_update == 0`),
same-class output before returning it — a smaller live box ≥80 % covered by a larger live box of the
same class is dropped (`tracker.hailo.dedupe_containment`, default `0.8`); failing that, a same-class
pair with IoU ≥60 % keeps only the higher-confidence record (`tracker.hailo.dedupe_iou`, default
`0.6`). Coasting records are excluded from both comparisons in either direction. New unit tests
(`tests/test_hailo_track_adapter.cpp`, cases 7–12) cover: full containment (only the larger emitted),
~50 % containment (both emitted, below both thresholds), an IoU-0.626/conf-0.9-vs-0.6 pair (the
higher-confidence one emitted), a different-class overlap (both emitted, never compared), a coasting
duplicate (neither record affected), and both thresholds at `0` (rule fully disabled) — all pass
inside the existing `hailo_track_adapter` ctest binary, and the full suite stays 14/14
(`cmake --build services/garuda-perception/build-x86 -j4 && ctest --test-dir
services/garuda-perception/build-x86`), the pre-existing cases in that file unchanged. Cross-build to
`services/garuda-perception/build-h15l` is clean (zero `warning:` lines). `config/perception-yolov8m.json`
(the only committed config running the `hailo` engine) now sets both fields to the code defaults;
`config/perception.json`/`config/perception-yolov8n.json` run the `mono` engine and carry no
`tracker.hailo` block to add them to.

Deployed to the board 2026-09-04; the new params show on the startup line
(`/var/log/garuda-perception.log`):

```
tracker.engine=hailo classification_id=1 kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=0 keep_new_frames=5 keep_lost_frames=75 min_hits=1 dedupe_containment=0.80 dedupe_iou=0.60
```

**Live measurement (run 11, 2026-09-04 evening): PASS.** Fresh 120 s capture, owner in view, the
committed person profile (`config/perception-yolov8m.json`), build `36dd640` (this fix) on the board:

```
f1_r11_dedupe.txt n=3485   120.0s | states none/confirmed/occluded/reacquiring/lost =  0%/100%/ 0%/ 0%/ 0% | obs_valid 100% | core_miss_live   0% (0/3485) | relocks  0 (false relocks  0) | id churn  2 | class switches  0 | LOST events  0 | reacq min/mean/max  n/a / n/a / n/a (0 eps, 0 untimed) | off-screen boxes    0 | max uncertainty_px  26.47
person       live-box rows 100.0% | live conf median 0.92 mean 0.91 max 0.93 | distinct ids 2 | rows with >=2 live boxes 0.0%
```

(`bench/evidence/2026-09-04-lock-core/run11_round6_dedupe.txt.gz`; `lock_metrics.py` and
`phone_detect_stats.py run11_round6_dedupe.txt.gz person 0 99999` reproduce these rows exactly.)
100 % `confirmed`, 100 % `obs_valid`, zero relocks, zero class switches, zero LOST events — the
close-range full-body/torso alternation run 8 measured did not reproduce here. `id churn 2` is not
zero, so the underlying SDK tracker still renumbered the owner twice in 120 s, but `LockCore` held
its one identity through both with no false relock, which is the fix's actual claim (dedupe removes
the *duplicate* box, not tracker id churn itself). Against the pre-fix baselines: run 8 (routine 4,
fast lateral, close-range, the capture the fix was derived from) measured `id churn 41` over 313.5 s
(0.131 churns/s); run 6 (routine 1, walk-out/return, not a close-range routine) measured `id churn 6`
over 68.6 s (0.087 churns/s). Run 11's 2/120.0 s = 0.017 churns/s is the lowest rate of the three and,
being a fresh close-range capture rather than a replay of run 8's own file, is independent evidence
the dedupe fix generalises — but the three runs are three different routines at three different
durations, not the same routine re-run before/after, so the rate comparison is suggestive, not a
controlled before/after.

### Hailo-15L SBC: detector A/B on the phone — yolov8m vs yolov11m vs yolov11s (2026-09-04 evening)

**Conditions.** One owner-paced 75 s routine per model, run once each, in the order yolov11m →
yolov8m → yolov11s, back to back, room lit, board build `73f85f8`. Each run used an all-classes
scratch copy of the model's committed `services/garuda-perception/config/perception-yolov*.json`
(`tracker.hailo.classification_id` forced to `-1`, `jpeg_fps` forced to `30`) made by
`bench/evidence/2026-09-04-lock-core/mk_allclasses.py`, so the phone shows up as a normal `cell
phone` box instead of being filtered out by the shipped person-only profile. Capture is the SSE shim
at its 30 Hz cap. Phone held still at arm's length roughly 0–25 s, then moved slowly and then
quickly through the remaining ~50 s; a person (the owner) was in frame throughout as a stability
reference. Same 640×640 stretched input for all three models (no letterbox variant tested this
round).

Captures: `bench/evidence/2026-09-04-lock-core/ab_yolov11m_phone.txt.gz`,
`ab_yolov8m_phone.txt.gz`, `ab_yolov11s_phone.txt.gz`. Harness: `lock_metrics.py` reports `n/a`
throughout (all-classes capture, no `lock` semantics exercised) so the numbers below are all
`phone_detect_stats.py <file> "cell phone" <t0> <t1>` — full window `0 75`, still window `3 25`,
moving window `25 75`.

```
ab_yolov11m.txt 0–75: cell phone live-box rows 47.2% | conf median 0.67 mean 0.61 max 0.91 | distinct ids 18 | dup 0.0% ; still 3–25: 17.1% / 0.33 ; moving 25–75: 63.3% / 0.69 ; person 100% / 0.90
ab_yolov8m.txt  0–75: cell phone live-box rows 43.7% | conf median 0.32 mean 0.42 max 0.92 | distinct ids 16 | dup 0.4% ; still 3–25: 40.9% / 0.27 ; moving 25–75: 47.4% / 0.38 ; person 100% / 0.90
ab_yolov11s.txt 0–75: cell phone live-box rows 71.3% | conf median 0.56 mean 0.52 max 0.93 | distinct ids 26 | dup 3.3% ; still 3–25: 91.6% / 0.50 ; moving 25–75: 60.6% / 0.62 ; person 100% / 0.86 ; node fps 30.1 ; thermal_zone0 73232
```

(committed as `bench/evidence/2026-09-04-lock-core/ab_yolov11m_phone.txt.gz`,
`ab_yolov8m_phone.txt.gz`, `ab_yolov11s_phone.txt.gz` respectively; re-run through
`phone_detect_stats.py` off the gzipped files, these rows reproduce exactly.)

| model | live phone-box rows (0–75 s) | median conf | distinct ids | dup rows (≥2 live boxes) | still (3–25 s) | moving (25–75 s) |
|---|---|---|---|---|---|---|
| yolov8m | 43.7 % | 0.32 | 16 | 0.4 % | 40.9 % / 0.27 | 47.4 % / 0.38 |
| yolov11m | 47.2 % | 0.67 | 18 | 0.0 % | 17.1 % / 0.33 | 63.3 % / 0.69 |
| yolov11s | 71.3 % | 0.56 | 26 | 3.3 % | 91.6 % / 0.50 | 60.6 % / 0.62 |

(still/moving cells are "live-box rows % / median conf", same as the pasted rows above; `person`
held 100 % live-box rows at median conf 0.90/0.90/0.86 across the three runs, the stability reference
for the routine, not a detector result being compared.)

Hailo's own model-zoo numbers for these three HEFs (quoted as Hailo's, not measured on this bench —
mAP float/quantised, fps): yolov8m 49.6/48.8, 39.7 fps; yolov11m 50.7/49.5, 33.4 fps; yolov11s
46.1/45.3, 86.7 fps.

**Red-team.** This is one owner-paced run per model, not interleaved and not repeated — a single bad
or lucky 75 s draw is indistinguishable from a real model difference here. The "still" phase varied
by phone angle between runs (held free-hand, not fixtured), so yolov11m's still-window live-box rate
of 17 % against yolov11s's 92 % cannot be attributed to the model alone — it may just as well be the
angle the phone happened to be held at during that run's first 25 s. The three captures also carry
different SSE row counts (2212 / 2189 / 1912 for 11m / 8m / 11s respectively) despite the same
nominal 75 s and 30 Hz cap, which is unexplained and means the three windows are not exactly the same
number of samples. There is no ground truth (no independent frame-by-frame human label of where the
phone actually was), so "live-box rows %" measures detector-reported presence, not accuracy against
reality. All three runs used the same stretched 640×640 input; the letterbox path is untested, and
Hailo's own zoo numbers above come from Hailo's own eval protocol, not this routine, so the on-bench
percentages and the zoo mAP/fps figures are not directly comparable to each other. The one thermal
sample (`thermal_zone0` 73232 = 73.2 °C) is a single point taken after the last (yolov11s) run only —
there is no reading for the other two runs and no per-run fps log except the one `node fps 30.1` line
also taken during the yolov11s run, so neither thermal nor fps state is characterised for yolov8m or
yolov11m at all. **Verdict: yolov11s is the candidate for the follow profile; repeat with a fixed
protocol (phone in a stand, three runs per model, interleaved) before switching.**

**What's next:** the fixed-protocol repeat (phone in a stand, three interleaved runs per model), the
letterbox-vs-stretch input test, and a fresh phone LOCK routine (not all-classes A/B) on round 5+6's
`config/perception-yolov8m.json` build.

### Round 7 — clutter and re-acquire

The owner's report after the detector A/B was that the follow display is "all over the place". Round 7
tested that against a capture rather than against intuition. **Run 12**: 90 s, board build `73f85f8`,
the yolov11s **all-classes** scratch config (`tracker.hailo.classification_id -1`, `jpeg_fps 30`, from
`mk_allclasses.py` — the same recipe the A/B used), SSE shim at its 30 Hz cap, phone held and moved in
front of the owner, one click-lock on the phone early in the run. Capture committed as
`bench/evidence/2026-09-04-lock-core/run12_round7_jumpy_yolov11s.txt.gz`; the new analysis tool is
`bench/evidence/2026-09-04-lock-core/jumpiness.py` (per-row displacement of the published `lock.box`
centre, jumps split by cause, and the detector-gap structure while locked). All four rows below
reproduce verbatim from the committed `.gz`:

```
jumpy_yolov11s.txt rows=2295 states={'lost': 1582, 'confirmed': 656, 'occluded': 51, 'reacquiring': 6}
lock-box centre step (px/row): median 0.5  p90 2.2  max 46
jumps > 80 px: 0 (0.0% of locked rows) — with id change 0, first row after a detection gap 0, same id while live 0
detection gaps while locked: 20 gaps, median 1 rows, p90 12 rows, max 19 rows
lock_metrics: n=2295 90.0s | states none/confirmed/occluded/reacquiring/lost = 0%/28%/2%/0%/68% | obs_valid 28% | core_miss_live 0% (0/656) | relocks 1 (false relocks 1) | id churn 15 | class switches 0 | LOST events 1 | reacq min/mean/max 0.07/0.15/0.77s (20 eps, 0 untimed) | off-screen boxes 0 | max uncertainty_px 2063.04
phone_detect_stats: cell phone live-box rows 30.2% | live conf median 0.73 mean 0.67 max 0.91 | distinct ids 9 | rows with >=2 live boxes 0.1% ; person 100% / 0.89
```

(`jumpiness.py`, `lock_metrics.py` and `phone_detect_stats.py` respectively, each run on
`run12_round7_jumpy_yolov11s.txt.gz`. The first line's `jumpy_yolov11s.txt` is the scratch filename the
tool prints; the committed copy prints its own path and is otherwise byte-for-byte the same rows.)

**Reading.** The published lock box is *not* what is jumping: while the lock is held its centre moves a
median of 0.5 px and a p90 of 2.2 px per row, the largest single step in 90 s is 46 px, and there are
**zero** steps over 80 px — in any category, including "same id while live". Two other mechanisms
account for what the owner saw, and each gets a fix this round:

1. **Clutter — no birth floor on the SDK tracker.** The GUI draws every track the node publishes, and
   the SDK's Kalman tracker births one from *any* detection the post-process hands it: it has no
   confidence floor of its own, unlike mono's ByteTrack, which only ever births a track at
   `track.high_thr` (0.4). A live `/api/state` poll during the run carried `handbag` 0.19, `backpack`
   0.19 and `handbag` 0.17 tracks; on the all-classes config a cluttered room fills the view with
   them. **Fix (Ruling 24.1):** `HailoTrackAdapter` now emits records only for ids that have been
   *born* — seen live at least once at `conf >= tracker.hailo.birth_conf` (new key; the node defaults
   it to `track.high_thr`, so the two engines admit the same detections). The flag is sticky for that
   id's Entry (a later low-conf or coasting frame still publishes) and dies with the Entry, so an id
   dropped after `keep_lost_frames` and reused must earn its birth again. The gate runs *before*
   round 6's dedupe pass, so an unborn record can neither publish nor suppress a born one;
   `birth_conf 0` disables it.

2. **Re-acquire — a consecutive streak the phone could never reach.** The lock was `lost` for 68 % of
   rows: after the clicked lock expired, auto-acquire never took the phone back. `auto_min_streak` (5)
   required five **consecutive** gate-passing live frames, and the phone was a live box in only
   **30.2 %** of frames — five in a row essentially never happens at that hit rate. **Fix
   (Ruling 24.2):** the count is now over a sliding window — `auto_min_streak` gate-passing live frames
   within the last `auto_streak_window` (new `lock` key, 15 ≈ 0.5 s at 30 fps) frames in which that id
   appeared, for both the auto-acquire branch and the re-acquire jump. 5 of 15 still refuses run 2's
   junk-track flicker (a lone gate-passing frame ages out of the window with nothing to join it), and a
   coasting frame is no longer a *reset*, merely a frame that contributes 0.

**Configs.** `birth_conf: 0.4` added to the `tracker.hailo` block of all three hailo-engine configs
(`perception-yolov8m.json`, `perception-yolov11m.json`, `perception-yolov11s.json`);
`auto_streak_window: 15` added to the `lock` block of all five (those three plus `perception.json` and
`perception-yolov8n.json`, which run the `mono` engine and have no `tracker.hailo` block).
`config/perception-yolov11s.json` is the documented **follow profile** from this round on (owner
decision after the A/B — `docs/decisions.md` 2026-09-04); `perception-yolov8m.json` stays as the A/B
alternative.

**Verification.** Native `ctest` **14/14** (`cmake --build services/garuda-perception/build-x86 -j4 &&
ctest --test-dir services/garuda-perception/build-x86`) — five new `test_hailo_track_adapter` cases
(13–17: never-born id never emitted; born on the frame the gate is reached and emitted thereafter
through a conf drop and a coasting frame; born flag lost with the Entry; `birth_conf 0` disables;
gate-before-dedupe) and `test_lock`'s streak block rewritten for the window with the frame-by-frame
arithmetic in the comments (5 spread over 15 → acquired on the 5th; 4 of 15 → never; 5 consecutive →
unchanged; coasting no longer resets; window 0 or streak 0 disables). Cross-build to
`services/garuda-perception/build-h15l` clean, `grep -c "warning:"` = **0**. Deployed to the board with
the committed follow profile
(`env GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov11s.json
hosts/hailo15l/deploy.sh`), whose own startup lines carry both new fields:

```
selected config's hef (/opt/garuda/models/yolov11s_hailo15l_v5.3.0.hef) is present on the board (not the pinned yolo26m — no md5 check, no copy)
tracker: keep_lost_frames=75 max_lost=75
lock: auto-acquire gate conf>=0.50, edge margin 0.020*1280 = 25.6 px, streak>=5 frames within a 15-frame window
tracker.engine=hailo classification_id=1 kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=0 keep_new_frames=5 keep_lost_frames=75 min_hits=1 dedupe_containment=0.80 dedupe_iou=0.60 birth_conf=0.40
frames=301 fps=30.1
```

**The live re-measurement of round 7 is PENDING — `TBD-bench`.** Nothing above measures the two fixes:
run 12 is the *pre-fix* capture that motivated them, and the only post-fix evidence is the unit tests,
the clean builds and the board's own startup lines. What is owed is a fresh capture of the same routine
on this build, showing (a) how many junk sub-`birth_conf` tracks still reach `/api/state` (target:
none) and (b) whether auto-acquire re-locks the phone after the clicked lock expires, i.e. the `lost`
fraction falling well below run 12's 68 %.

**Red-team.** Run 12 is a single 90 s owner-paced capture on the all-classes scratch config, not the
shipped person profile, so its `id churn 15` / 9 distinct phone ids describe a configuration nobody
deploys — the committed follow profile carries `classification_id 1` and hands the tracker person
detections only. The "lock box is smooth" conclusion rests on rows where a lock was actually held
(28 % of the run); it says nothing about the other 72 %, and a display can look chaotic from the
*other* boxes alone, which is exactly the clutter hypothesis. `relocks 1 (false relocks 1)` and
`max uncertainty_px 2063` are consistent with a lock that expired and was never recovered, i.e. with
finding 2, but neither number was independently checked against video. The birth gate's default is
`track.high_thr`, chosen for engine parity, not measured: a floor of 0.4 will also drop genuine
low-confidence sightings of a real target, and the round-7 capture's own phone confidences (median
0.73, but 30 % live-box rows) do not tell us how many *true* phone frames sat below 0.4, because
`phone_detect_stats.py` only sees detections that were published. Likewise 5-of-15 is a judgement call
about how much evidence half a second should carry, not a swept parameter — a window that admits run
2's flicker would show up only as a false auto-acquire in a future capture, and nothing in this round
re-ran run 2 to confirm it still refuses.

### Round 8 — class allow-list

On the all-classes config (`tracker.hailo.classification_id -1`, needed for any demo showing more than
one class, since `classification_id` allows exactly one) a 120 s capture of real room objects
(`r7_phone_check.txt`) emitted 15274 track entries over 3063 rows — `chair` 3885, `handbag` 3137,
`toilet` 2298 (a ring light), `laptop` 1905, `suitcase` 1379, `person` 989 — every one of which passes
the round-7 birth gate at least once, cluttering the GUI whenever more than one class is tracked.
**Fix (Ruling 25):** `HailoTrackAdapter` gained a `tracker.hailo.classes` allow-list (JSON array of
label strings; empty/absent = all) applied to `seen` before any bookkeeping, so a disallowed detection
can neither be born nor take part in dedupe nor suppress an allowed record; the new
`config/perception-yolov11s-phone.json` sets `classes: ["person", "cell phone"]` with
`classification_id -1`. **Verification:** native `ctest` **14/14**, four new
`test_hailo_track_adapter` cases (18–21: basic allow/drop, explicit empty allows all, ordering before
the birth gate, ordering before dedupe); cross-build to `build-h15l` clean, `grep -c "warning:"` = 0;
deployed live (`tracker.engine=hailo classification_id=-1 ... classes=person,cell phone`,
`frames=302 fps=30.2`) and `/api/state`'s `tracks[]` carried only `person`/`cell phone` labels across
five polls with a person and phone in view, confirming the allow-list holds on the board.

### 2026-09-05 — phone lock on the round-8 phone-demo config (run r8_phone_a)

Capture: `bench/evidence/2026-09-04-lock-core/run13_round8_phone_reacquire.txt.gz` (the PC-side
timestamped SSE capture, 3071 rows / 120.0 s, `config/perception-yolov11s-phone.json`, hailo Kalman
engine, `classification_id -1` + `classes: ["person","cell phone"]`, owner holding and hiding a
phone). Every row below was produced by re-running the three tools on the committed `.gz`; nothing
is carried over from the live session.

`bench/evidence/2026-09-04-lock-core/lock_metrics.py`:

```
run13_round8_phone_reacquire.txt.gz  n=3071   120.0s | states none/confirmed/occluded/reacquiring/lost =
  0%/28%/11%/26%/33% | obs_valid  28% | core_miss_live   0% (0/884) | relocks  1 (false relocks  1) |
  id churn 43 | class switches  0 | LOST events  2 | reacq min/mean/max 0.07/0.45/4.28s (62 eps, 0 untimed) |
  off-screen boxes    0 | max uncertainty_px 2131.83
```

`phone_detect_stats.py`:

```
rows=3071 window=[0.0,120.0] s
cell phone   live-box rows  32.0% | live conf median 0.59 mean 0.57 max 0.89 | distinct ids 17 | rows with >=2 live boxes 0.0%
person       live-box rows 100.0% | live conf median 0.88
lock class rows: {'cell phone': 2045, '(none)': 1026}
```

`jumpiness.py`:

```
rows=3071 states={'confirmed': 884, 'occluded': 340, 'reacquiring': 821, 'lost': 1026}
lock-box centre step (px/row): median 0.0  p90 2.5  max 322
jumps > 80 px: 6 (0.3% of locked rows) — with id change 6, first row after a detection gap 0, same id while live 0
detection gaps while locked: 63 gaps, median 3 rows, p90 44 rows, max 258 rows
```

Reading, stated as narrowly as the capture allows. **`core_miss_live` is 0 % over 884 rows**: on
every row where the engine held a live box for the locked id, the core was CONFIRMED — the lock core
does not drop observations it is given. **`obs_valid` is 28 %** and the phone is a live box in only
**32.0 %** of rows: the target simply is not being detected most of the time, in gaps up to 258 rows
(~8.6 s). The 6 jumps over 80 px are all at an id change after a gap, i.e. the box re-appearing
somewhere else, not the filter wandering. The node log carried one `lost -> confirmed`, i.e. an
automatic re-lock after a hide, which is the single re-lock the harness counts (and, on a
single-target routine, is by definition a "false relock" in that column's own convention).

**What this capture does NOT establish:** raw detector recall (the node cannot see the pre-tracker
detection list under the hailo engine — see the `diag` note below), whether physical identity was
retained across the 17 ids, and what the owner actually saw on screen. All three remain `TBD-bench`.

### Round 9 — outside review

An outside review of the branch produced three probes, reproduced by the controller against the
round-8 build. Rulings 26–30 follow from them; the probes are now unit tests
(`tests/test_lock_core.cpp` cases 22/22b/23/23b, `tests/test_hailo_track_adapter.cpp` 22–29).

- **26 — core input is all live detections.** `HailoTrackAdapter::live_raw()` returns this frame's
  LIVE records after the class allow-list only (no birth gate, no dedupe) and `node_main.cpp` feeds
  it to `LockCore`; the published (gated + deduped) list still drives the snapshot, the resolver's
  `step()`, and both new-lock paths. A new lock still needs a visible track; maintaining one may use
  any live detection.
- **27 — dedupe protects identities.** `set_protected_id()` (the resolver's lock id each frame) plus
  a per-id age; containment/IoU may suppress a record only when it is unprotected AND younger than
  `tracker.hailo.dedupe_protect_age` (new key, default 10 frames).
- **28 — no out-of-gate new-id acceptance.** New `lock.widened_new_id` (default false): the widened
  stage accepts only a candidate carrying the core's own tracker id.
- **29 — stall expiry.** `obs_age > expire_ms` suppresses association before it happens, so a stalled
  pipeline comes back to a dead lock rather than to one that associates as if no time had passed.
- **30 — freshness.** `lock.control_valid` = `observation_valid && (obs_age_ms + age_ms) <=
  control_valid_ms`, the first consumer of `control_valid_ms`.

Probe outcomes, before (round-8 build) → after (this build):

| probe | before | after |
|---|---|---|
| `far_new_same_class` (lone new-id person 900 px away, conf 0.41, REACQUIRING) | `state=confirmed id=2 epoch=1 score=0.4025` | `state=reacquiring id=1 epoch=1 valid=0 age=640 score=0.468` |
| `frame_returns_after_11s_without_ticks` (lock at t=0, one `update()` at t=11000) | `state=confirmed id=1` | `state=lost id=1 epoch=1 valid=0 age=11000` |
| `overlapping_people` (id 1 partly behind the nearer id 2) | `surviving_ids=2,` | `surviving_ids=2,` when id 1 was **born this frame** (a duplicate birth — Ruling 27 keeps suppressing that); `surviving_ids=1,2,` once id 1 is **established** (≥ 10 emitted frames) or is the **protected** lock id |

**Measured cost of Ruling 28 on the committed captures** — attribution measured, not assumed
(re-running each replay with `expire_ms` disabled changes neither, so Ruling 29 contributes nothing
here; Ruling 28 alone accounts for both):

| capture | `widened_new_id = true` (pre-round-9 model) | shipped default |
|---|---|---|
| routine 1 (run 5, `test_lock_replay`) | — | **unchanged and passing at the shipped defaults**: CONFIRMED on 1138/1161 live conf≥0.50 rows = 0.9802, id 1316 taken 401 ms after it first goes live, 0 LOST rows. Its re-entry was never an out-of-gate new-id acceptance, so Ruling 28 does not touch it |
| routine 2 (run 7, `test_lock_replay2`) | 0 LOST rows; the 6 s hide recovers at t=14949 ms | **139 LOST rows, first at t=21079 ms, the 6 s hide never recovers** |
| phone (run 10e, `test_lock_replay_phone`) | CONFIRMED on 771/946 phone-live rows = 0.8150 | **183/946 = 0.1934** |

Ruling 22's class protections hold under both models on the phone capture (0 cross-class confirms, 0
rows on the false-lock id 163), so what Ruling 28 trades away is re-acquisition of the *real* target
across detector gaps, not class discipline. Both replay tests therefore now run each capture twice —
once at `widened_new_id = true` (keeping Rulings 20d/22.5's assertions at the params they were
derived under) and once at the shipped defaults (pinning the round-9 outcome so the trade stays
measured and cannot drift silently in either direction). **This is a real regression in occlusion
recovery, recorded rather than absorbed; the controller decides whether the trade stands.**

**Verification:** native `ctest` **14/14**; cross-build to `build-h15l` after `ninja -t clean`,
`grep -c "warning:"` = **0**; deployed live on `config/perception-yolov11s-phone.json` with the
startup lines `tracker.engine=hailo classification_id=-1 … dedupe_protect_age=10 birth_conf=0.40
classes=person,cell phone` and `lock: widened_new_id=false control_valid_ms=150 expire_ms=10000`,
`frames=277 fps=27.7` on the first report; `/api/state` carried
`"diag":{"core_candidates":0,"live_raw":0,"published":0,"raw_dets":-1,"sdk_tracks":3}` and
`"control_valid":false` on an empty-room frame — the three SDK tracks being furniture dropped by the
`classes` allow-list, which is exactly the stage-by-stage accounting `diag` exists to show.
`raw_dets` is **-1 by construction under the hailo engine**: the SDK's `TrackerStage` sits between
the post-process and our sink and rewrites the ROI, so the pre-tracker detection list is not
observable from the node at all.

### Round 10 — Ruling 32 (the round-9 trade, re-ruled)

The controller ruled that Ruling 28's blanket refusal does not stand as a plain boolean and replaced
it with **Ruling 32**: an out-of-gate candidate carrying a DIFFERENT tracker id is accepted only when
(a) it is the same class, (b) its id was **born after the last confirmed observation**, (c) it is the
only eligible out-of-gate candidate this frame, (d) `conf >= widened_new_id_min_conf` (0.5), and
(e) `obs_age_ms <= widened_new_id_max_age_ms` (5000). A SAME-id out-of-gate candidate is exempt from
(b)–(e). `widened_new_id` remains the master switch and now defaults to **true**.

(b) is the load-bearing condition and needs no appearance model: an id that was alive while the target
was still confirmed is, by construction, a different physical object, so the classic swap — the other
person who was in the room the whole time — can never be taken. It is carried by the new
`Obs::first_seen_ms` / `TrackRecord::first_seen_ms` (−1 = unknown = treated as pre-existing = refused),
stamped by the hailo adapter on the frame each id is first seen; the mono engine keeps the same
timestamps in a node-side map, because `bytetrack.{hpp,cpp}` is a line-for-line port pinned by
`tests/golden/bytetrack_ref.py` and must not gain a field for an unrelated reason.

**Replays under the shipped params** (fixtures gain `first_seen_ms` derived per id from the first
capture row that id appears in — see `tests/lock_replay_common.hpp`; the two caveats there both make
the reconstruction conservative, i.e. it can never invent a born-after-loss id):

| capture | round 9 (`widened_new_id=false`, kept as the strict reference) | round 10 shipped |
|---|---|---|
| routine 1 (run 5) | 1138/1161 = 0.9802, 0 LOST | **unchanged**, 1138/1161 = 0.9802, 0 LOST |
| routine 2 (run 7) | 139 LOST rows, first at t=21079 ms, 6 s hide never recovers | **0 LOST rows; the 6 s hide re-confirms at t=14949 ms on id 31** |
| phone (run 10e) | 183/946 = 0.1934 | 184/946 = **0.1945** |

**Routine 2 is fully recovered. The phone capture is not, and the round's ≥ 0.78 bar is not met at
the specified 5000 ms ceiling.** The cause was isolated by relaxing each condition in turn on the
fixture: (b), (c) and (d) cost nothing here, and **(e) alone** accounts for all of it —

```
shipped (32 b/c/d/e)               frac=0.1945 (184/946)
relax (d) conf floor               frac=0.1945 (184/946)
relax (b) born-after-loss          frac=0.1945 (184/946)
relax (e) age ceiling              frac=0.8150 (771/946)
relax (b)+(d)+(e)  [only (c) left] frac=0.8150 (771/946)
```

It is a **cliff, not a gradient**. Of the 26 different-id re-acquisitions this capture needs, 24 land
at `obs_age <= 3969 ms`, one at **6392 ms** and one at 8289 ms. Missing the 6392 ms one is fatal *in
this harness*: the replay drives `LockCore::update()` alone, with no `LockResolver`, so once the core
reaches LOST nothing can re-lock it and the remaining ~54 s of capture score zero. Ceiling sweep on
the same fixture:

```
ceiling   2000 ms -> phone frac 0.1945      ceiling   7000 ms -> phone frac 0.8150
ceiling   3000 ms -> phone frac 0.1945      ceiling   8000 ms -> phone frac 0.8150
ceiling   5000 ms -> phone frac 0.1945      ceiling   9500 ms -> phone frac 0.8150
ceiling   6000 ms -> phone frac 0.1945      ceiling  10000 ms -> phone frac 0.8150
```

On the real node a LOST lock with a class auto-acquire configured produces a **new epoch** and
re-locks — the round-8 board capture shows exactly that (`lost -> confirmed`, `relocks 1`) — so the
on-board cost of a 5000 ms ceiling is "an extra visible re-lock per long gap", not "the target is
never seen again". This harness cannot show that, which is itself worth stating.

**Round 10b (Ruling 33)** takes the controller's decision on that number: `widened_new_id_max_age_ms`
ships at **7000 ms**, so at the shipped default the phone capture is **771/946 = 0.8150** (against
183/946 = 0.1934 for the strict `widened_new_id = false` reference, which `test_lock_replay_phone`
still runs as its second pass), routine 2 keeps its 0 LOST rows and routine 1 is unchanged at 0.9802.
`expire_ms` stays 10000, so the different-id half of the widened window still closes 3 s before the
lock expires.

**Probe outcomes** are unchanged from round 9 by design: `far_new_same_class` →
`state=reacquiring id=1` (now refused by (d), conf 0.41 < 0.5, rather than by a blanket rule; the
same candidate at conf 0.6 IS taken, which is Ruling 32's documented accepted residual until F3);
`frame_returns_after_11s_without_ticks` → `state=lost id=1` (Ruling 29, untouched);
`overlapping_people` → `2,` for the reviewer's one-frame-old id 1, `1,2,` once established or
protected (Ruling 27, untouched).

**Verification:** native `ctest` **14/14**; cross-build after `ninja -t clean`, `grep -c "warning:"`
= **0**; deployed `config/perception-yolov11s-phone.json`, startup line
`lock: widened_new_id=true (min_conf=0.50 max_age_ms=5000, born-after-loss required)
control_valid_ms=150 expire_ms=10000`, and the node took a lock immediately
(`lock: none -> confirmed (obs_age_ms=0)`).

## 2026-09-10 — Independent Hailo-15L fresh tracker and phone model diagnosis

Branch `feat/hailo15l-fresh-tracking`, based on `9582f1d`; isolated bench deployment
`/opt/garuda-fresh`, viewer :8099. IMX678, Hailo-15L FW/HEF compiler 5.3.0, VPSP1.12.0.
Board wall clock was incorrect; dates are PC UTC and all tracking ages use board monotonic time.

New dependency-free C++17 tracker: class-aware Hungarian assignment, Kalman box state,
high/low-score association, NV12 histogram appearance, background translation estimation,
elapsed-time lifecycle and one-shot identity selection. Explicit target validity, bounded queues,
heartbeat and same-board shim deadlines. No metric depth or flight-output/arming path.

Person run: 60.023 s, 1496 HTTP samples, 20.0000 processed fps; age median 84.839 ms,
p95 124.208 ms, max 147.470 ms; 0 rejected frames, HTTP errors or validity-invariant violations.
765 selected/tracking samples following 731 unselected samples. Owner: “it tracked well.”
SIGSTOP trial: valid before; invalid at 350 ms sample (age442.9 ms); expired old identity stayed
LOST after resume. Real recording: 2202 rows / 2200 frames, five stale frames rejected, native/ARM
replay zero semantic mismatches. CPU/RSS spot: 60.9% of one CPU / 83872 KiB; temperature58.511°C.
Initial job_limit1 / scheduler_threshold4 / timeout100ms caused backlog; explicit threshold1 /
timeout10ms removed the measured backlog without relaxing freshness.

Checks: 18 native scenarios, 8 Python HTTP/replay tests, legacy CTest14 passed; ARM cross-build
and board execution. Earlier core/vision sanitizer run passed; selection and actual-layout sanitizer rerun passed (19 native scenarios).

Phone: owner reported disappearing/jumping boxes; YOLO11s letterboxing was “unchanged.”
Nested phone/person click selection and separate selection-intent age fixed independently.
Undeployed image-bridge experiment removed after owner's objection to the workaround.

Fixed-image comparison: 59 images sampled every fourth JPEG from a 233-frame/60s preview capture.
Same Pillow bilinear resizing and BT.601 limited-range NV12 input given to each HEF; tracker absent.
Phone detections at confidence≥0.15 / ≥0.5:

- YOLO11s letterbox: 1/59 / 0/59; stretch: 5/59 / 0/59.
- YOLO11m letterbox: 12/59 / 1/59; stretch: 4/59 / 0/59.
- YOLOv8m letterbox: 50/59 / 8/59; stretch: 42/59 / 16/59.

All model/geometry runs detected person at≥0.5 in59/59. Sixteen YOLOv8m letterbox overlays
spot-checked: phone boxes aligned with the visible phone. YOLOv8m letterbox is now an isolated
candidate, with unchanged tracking thresholds (birth.5/control.4/recovery.15).
Live candidate30.036s: 748 HTTP samples,19.9847 processedfps, age99.811/140.399/162.461ms
median/p95/max, zero rejections/errors/invariant violations; all samples unselected.
No claimed live phone improvement yet.

Evidence and source: `services/garuda-tracking/README.md`,
`bench/results/2026-09-10-fresh-tracking/`, `bench/fresh_model_bench.py`,
`hosts/hailo15l/model_probe.cpp`. Original JPEGs remain local; hashes and compressed model outputs retained.

Red-team: one room/person/phone; repeated and partly clipped horizontal poses, no framewise labels
or negative-scene test. Counts are detector presence, not recall/precision. JPEG-derived inputs are
not exact ISP inputs. No float-versus-quantized test yet, so the deficit cannot be attributed to
quantization. Phone confidence remains weak even with YOLOv8m. No crowd/aerial/thermal endurance
or flight validation. YOLO HEFs remain not-product-cleared under existing bench model policy.

### Correction: actual camera input geometry, same session

The owner's outside-person failure report prompted raw NV12 inspection. Both prior live
"letterbox" trials were actually STRETCH: VPSP1.12 persists scaling_mode/dimensions across
profile switches, so initialize(default stretch) then set_profile(letterbox) retained stretch.
The tracker nevertheless inverted letterbox coordinates and extracted the wrong appearance region.
This was a bug in our trial integration, not evidence against the camera or a valid letterbox trial.

Fixed by initializing the requested profile directly and checking effective stream geometry plus
actual padding pixels.20/20 new raw captures show140-row black Y padding top/bottom, neutralUV128,
640x360 image content. New19th native scenario rejects stretched pixels under letterbox config;
native19, ASAN/UBSAN, cross-build passed. Raw capture is bounded and diagnostic-only.

Corrected30.034s run:748 HTTP samples,19.9824fps, age101.090/142.056/159.709ms median/p95/max,
zero rejections/errors/invariant violations, no target selected. Owner validation is pending.
The previous live-letterbox timing files now explicitly flag invalid geometry; the offline
59-image Python-prepared model comparison remains distinct and correctly letterboxed.

ISP integration metadata was32991–33006us. No exposure/denoise/factory IQ change made.
Official YOLOv8m float ONNX (ONNX Runtime1.29 CPU) on20 captured images: phone presence>=.15
actual stretch11/20 versus corrected geometry16/20; live Hailo on matching frames10/20.
At>=.5:7/20 versus10/20, live Hailo4/20. Reference conversion uses BT.601 limited-range and
114gray corrected padding, whereas DSP uses black padding. These differences, lack of ground truth,
and unverified exact checkpoint provenance prevent attributing the residual to quantization.

Evidence: camera-input-diagnosis.json, verified-letterbox-padding.json,
camera-input-metadata.jsonl.gz, float-reference-comparison.json,
corrected-letterbox-live-summary.json in the same results directory. Image bytes remain local
in the paths recorded in the diagnosis artifact. No phone-recognition success claim made.

### Motion-filter follow-up, same session (local only)

Synthetic phone crossing confirms no person-boundary dependency. Abrupt reversal reproduced
a lost selected ID despite continuous high-confidence detections. Center acceleration std sweep
0.4/1/2/3/4/6: 0.4 failed, all >=1 passed. Selected 1.0 normalized frame units/s²; dimension
noise and existing identity/freshness/confidence gates unchanged. Added boundary/reversal and
different-phone regression coverage, bringing native scenarios to21. Python8 and ASAN/UBSAN pass.

Same6000 corrected camera detector frames, with synthetic target command: original0.4 and selected1.0
both711 valid target frames, seven confirmed phone IDs, lost atframe1676. No real phone-success
claim; inputs are unannotated and the owner's outside-body test remains pending. Higher values
>=3 increased confirmed phone ID count. Results in motion-filter-comparison.json. Not deployed.

Float reference on20 corrected raw inputs found0 phone detections>=.15, matching liveHailo0/20.
The spot-checked image has no clearly visible phone: this cannot measure recognition recall.
Retained corrected-float-reference.json; no quantization-defect conclusion.

### Owner phone acceptance and storage-stall recovery

Owner confirmed “It keeps the lock now” after the corrected outside-body test. Saved145 JPEGs
through37.637s; later HTTP capture913 none/9 acquiring samples does not independently verify
selected identity continuity. Assistant selected phone near capture end.37 identical sampled inputs:
phone>=.5:11s9,11m12,8m13; >=.15:16,23,23.8m float21/28. Presence counts only, no annotated recall.

Capture ended with HTTP/SSH timeouts. Serial SysRq showed MMC read waits and widespread file faults;
shmem455120KiB, free minusCMA32752KiB. Memory pressure plausible, storage root cause unresolved.
Sync/remount completed, then reboot; PC frames preserved, unfinished raw board capture lost.
Restored fresh phone setup; boot unchanged. Added diagnostic byte/memory guards and disabled
recording by default.32MiB JSONL,128MiB cumulative raw capture,128MiB non-CMA/space reserve.
Board profiles explicitly keep original accelerationstd.4. Native21 plus budget test,Python8,
ASAN/UBSAN,SDK build passed. Board120-frame request rejected;2-frame capture completed.
Restored30s:19.9875fps,p95age142.520ms,max172.900ms,0errors/rejects/validity violations; all745acquiring.

Artifacts: owner-phone-confirmation.json, owner-movement-*.jsonl.gz, owner-movement-live-summary.json,
storage-stall-recovery.json, post-recovery-live-summary.json, compressed serial logs.
SysRq command reference: https://docs.kernel.org/admin-guide/sysrq.html .

## 2026-09-10 — fresh learned person identity, experimental board integration

Goal remains open after owner feedback. Added a durable person identity owner separate from MOT,
immutable learned anchor plus bounded recent descriptors, explicit provenance and conservative
multi-observation reacquisition. The optional host adapter uses Hailo's OSNet_x1_0 v5.3.0 Hailo-15L
HEF (source MIT per pinned config; weight/dataset product clearance pending, **not-product-cleared**).
No model weights/upstream model code are embedded in services. A disabled recipe skeleton records
that boundary. Phone/object identity and high-resolution DSP crops are still pending.

Evidence and source/input/binary hashes:
`bench/results/2026-09-10-fresh-tracking/learned-person-identity.json` and adjacent learned-person files.
Hardware/software remain Hailo-15L SBC rev2.x / IMX678 / VPSP1.12.0 / HailoRT5.3.0; see versions.md.

- HEF parse: physical input 256high×128wide NV12 (reported half-height 128×128×3), output 512D NC.
  The first RGB assumption was rejected by the probe before inference. No RGB inference result
  is claimed.38 JPEG-derived person crops (37 frames of one person + an exact repeat), input
  SHA-2568e62c2d07e89e3c82f04bf35f05ae7368d4f90c70d7fff374b94168b699c49a7.
  `bench/fresh_person_crops.py` reproduces the original bytes exactly from saved JPEGs and manifest.
- Standalone service-mode probe: median 7.41516ms / p95 7.62776ms inference. The final shared camera/
  probe adapter in local-device mode: median 6.35764ms / p95 6.54996ms inference, median 3.86568ms CPU
  crop. Both exclude model load and detector contention. All38 outputs match exactly between probes;
  minimum cosine to first same-person crop 0.8602408; duplicate cosine 1 within floating-point error.
  These are not negative-pair or identification-accuracy measurements.
- The first concurrent launch failed with HAILO_OUT_OF_PHYSICAL_DEVICES74: HailoRT service/local
  device modes were mixed. Matching the SDK's local mode and group permits both models to run.
- First successful 60s run included an intentional2s SIGSTOP. Control invalidated in all26 sampled
  paused observations; after resume, identity epoch 1 retained while MOT id 1→2. This is an induced
  frame-feed gap with the same person still visible, not a physical occlusion/distractor trial.
  Pre-pause 45.65s had HTTP age median 138.65/ p95 211.01/ max 319.68ms, so this was not accepted as a
  clean latency result. Node publish age p95 112.85ms vs transport age p95 111.73ms prompted publication
  instrumentation and removing unused frame-JSON/descriptor-copy work.
- Follow-up 40s, binary 58201d5b3ea6d3710aba24942ef7f57c0451c218e4e947938892111c0ed2f39d:
  991 HTTP samples,0 HTTP errors,19.97735 processed frames/s; image age median 127.25252ms,
  p95 161.95732ms, max 190.68672ms;0 rejected frames,0 validity-invariant violations;3 acquisition
  samples then988 tracking samples.805 embeddings,0 failures/skips. Publication pre-send delay
  p95 13.05632ms, send interval p95 67.92136ms, prior send duration p95 0.96296ms. This is not a
  controlled latency A/B, long endurance run, or identity-accuracy evaluation.
- Earlier60s single resource snapshot: RSS85,748KiB, HWM87,648KiB,39threads;
  MemAvailable1,399,088KiB minus CmaFree1,045,980KiB. These are a snapshot, not a sustained-memory gate.
- Validation:21 previous C++ tracking scenarios +7 identity/crop scenarios;8 Python transport/replay
  tests and diagnostic-budget CTest; ASan/UBSan; exact-SDK ARM build; tracking/identity test binaries
  executed on A53. No flight/controller commands were sent.

Reproduction: `bash hosts/hailo15l/build_fresh_tracking.sh`; optional model staging/start instructions
in `services/garuda-tracking/README.md`; telemetry via `python3 bench/fresh_tracking_bench.py --seconds
40 --output /tmp/reid-live.jsonl`. Probe: copy garuda-embedding-probe, pinned HEF and reproduced NV12
to the board, pause the camera pipeline, run `garuda-embedding-probe model.hef crops.nv12 MODEL_ID`,
restore the viewer. Never run a separate probe against a live, differently grouped device.

The previous baseline binary 9dbcb7ef3506aa4266beb40a9efee93fd4b27585c4d9662ec30276b9b93517c8 and
start-phone profile were restored and verified after the tests. No boot/driver changes. Remaining
work is explicitly tracked in DELIVERY.md; no completion gate is being closed here.

### 2026-09-10 — optional camera similarity compensation

Same Hailo-15L SBC/IMX678/VPSP 1.12.0/HailoRT 5.3.0. ORB200 at 320×180, four pyramid
levels, mutual descriptor matching and RANSAC, using factory OpenCV 4.5.5 (Apache-2.0).
Default build remains dependency-free translation. No system or boot changes.

ARM generated-warp validation on fourteen recorded camera inputs: 123/126 accepted,
maximum accepted 3×3-grid error 2.1954 px at 640×360; mean estimator time 36.17 ms.
Three fits rejected. These are known artificial transforms, not physical camera poses.
The separate 60s live empty-scene run measured 20.0004 processed fps, age median 110.01 /
p95 157.54 / max 186.70 ms, zero rejected frames and HTTP errors. Sequential 30s baseline
p95 was 140.01 ms. Twelve resource samples: RSS 88,876–89,384 KiB, non-CMA minimum
289,560 KiB, CPU 101.56% of one core, temperature maximum 80.972°C, sampled clocks 1.1 GHz.

Default and optional builds, seven optional CTests with ASan/UBSan, Python regressions,
SDK cross-build and ARM estimator/core execution pass. Baseline a98d4671 was restored.
Evidence, hashes, rejected variants and reproducibility:
`bench/results/2026-09-10-fresh-tracking/camera-motion/README.md`.

Red-team: adjacent source images from one scene and generated 2D warps cannot establish
drone accuracy, identity retention, rolling-shutter/3D robustness or combined ReID cost.
Nearly half the sampled live fits had localized support. Keep experimental; the full
delivery gate remains open. Prior SDK/follow, 600-frame exact streaming and 10-minute
baseline measurements are in the neighboring `sdk-follow/` and `exact-input-stream/`
reports, also scoped to their actual synthetic or empty-scene trials.

### 2026-09-10 — exact-input target scoring and C++ replay

Added a reviewed target-identity annotation schema and scorer, with exact image hash /
sequence / capture-time / producer joins. Reports physical switches separately from
numeric MOT-ID changes, wrong-object reacquisition, visible loss, control availability,
sampled recovery and censored intervals. Unknown truth and sparse samples are unscored.
Alternative results must cover every same input and retain candidate provenance.

All 22 Python tracking tests pass (11 new). The actual native C++ tracker on a synthetic
20-frame phone trajectory with four missing detections produces the independently
specified 350 ms lost visible time (150 ms confirmation + 200 ms dropout), 200 ms dropout
recovery, 0.8 detector recall and zero physical identity switches. This is a fixture,
not measured phone recognition or hardware accuracy.

The saved 600-frame exact board recording passes completion, pixel/hash, producer and
output-pair checks and replays through the actual C++ tracker. Its 600 annotations are
unknown, so accuracy/time denominators correctly remain null. No board runtime/profile
was changed. Evidence: `bench/results/2026-09-10-fresh-tracking/target-evaluation/`.

Red-team: a green evaluator and a correct synthetic dropout cannot establish target
accuracy. Physical annotations and continuous target-active trials remain missing.
The 20-frame older corrected raw capture is sparse (500 ms), unselected, and visual
inspection shows the phone mostly outside the right edge; it is not a phone trajectory
validation set. The full delivery gate remains open.

### 2026-09-10 — paired model-input and 1280×720 source streaming

Added exact integer-ISP-timestamp pairing of the existing detector and full-FOV preview
streams, before JPEG encoding. Four owned source frames bound history; missing requested
pairs abort. Both NV12 images fit one existing ≤2 MiB packet. No new camera stream, model,
dependency, boot/driver setting or board recording files. Paired admission requires 144 MiB
non-CMA headroom; source cache and packet memory are bounded.

60-pair smoke then 600-pair run passed on the SBC. The longer run transferred 1,198,080,000
pixel bytes, sequences 845–1444 over 29.933442 s, with all 1,200 hashes, source/output
correspondence and 600 integer exposure matches verified. Zero sequence gaps or pairing
misses. The 40s enclosing camera run processed 20.0253 fps, 0 rejects/HTTP errors, p95
HTTP image age 145.30 ms; the captured-sequence subset p95 was 147.09 ms, max 183.82 ms.
Eight resource samples: RSS 90,656–93,032 KiB, non-CMA minimum 294,560 KiB, temperature
maximum 80.769°C, sampled clocks 1.1 GHz, node CPU 68.62% of one core (SSH excluded).

Seven default CTests, eight optional/sanitized CTests, 25 Python tracking and 12 follow
checks, SDK build and ARM pairing/socket execution pass. A real 60-pair template/replay/
score check preserves both hashes. Baseline a98d4671 / start-phone was restored.
Evidence: `bench/results/2026-09-10-fresh-tracking/paired-input-stream/`.

Red-team: the scene was dark and empty, no selected target. Matching timestamps and
near-identical downsampled luma establish correspondence, not recognition or ISP quality.
The higher-resolution images remain ISP-processed; no lost sensor detail is restored.
Phone/person ROI accuracy, physical occlusion/distractors and combined load remain open.

## 2026-09-12 — Hailo-15L SBC: detector A/B replay, tracker re-acquire, five-tile trial

All figures from harness runs on this bench; evidence directories named. HEF
identities: old `24a050fb…`, controlled `aec84f00…` (both 15L, DFC 5.3.0).

**Detector A/B, 433-frame paired replay of the 2026-09-11 phone-motion recording
on the physical board, five via-1080p letterbox tiles, identical bytes to both
models** (`bench/results/2026-09-12-yolo11-ab-replay/`): phone frames at the
0.15 candidate floor 191→322 of 433 (44.1 %→74.4 %; paired 133 gained / 2 lost),
longest phone hole ~2.9 s→~0.5 s; at the 0.50 track-birth floor 129→200 (29.8 %→
46.2 %, worst gap still ~3.1 s); person saturated 433/433 for both; five-tile
sequential inference wait mean 94.4→122.1 ms. Replay-A's 44.1 % matches the live
session's 44.0 % on the same recording. Detector-only presence, not IoU recall.

**Tracker re-acquire (garuda::fresh) evaluation** (`bench/results/2026-09-12-
reacquire/`): identity-safety invariant held — re-acquire ON vs OFF wrong-identity
frames equal on every MOT17 sequence tested (02: 0/0, 09: 0/0, 10: 5/5, the 5 a
pre-existing association switch). Scripted whole-scene blackouts do not
re-acquire by design (every returning track is new → ambiguous without
appearance). Offline replay of the live flicker recording (575 frames): person
split 124/575 (broken build) → 20/575 (aggregation) → 0/90 live with the corner
size filter. Live single-tile letterbox + controlled HEF: click-locked person
walk-out/return rebound reacquiring→tracking; click-locked phone rebound at
conf 0.84 after ~2.9 s out; a second return at conf 0.18–0.50 correctly did not
confirm (single-tile resolution limit).

**Five-tile trial on the fresh node** (same evidence dir, `golden-tiles-session
.jsonl` 891 rows): ~7.5 fps, per-frame five-tile inference p50 147.8 / max 172
ms, publish–capture age min 209 / p50 230 / max 287 ms (every row over the 200 ms
base freshness budget; 272/891 shim samples `source_stale`), source pairing
2196/2196 matched, multi-class detection live. Single-tile runs ~20 fps, age
~57–85 ms. Freshness raised to 500 ms for the tiles profile — its live effect on
the coasting flicker is `TBD-bench` (no person-in-frame capture landed).

**Red-team.** The A/B is one recording, one scene, decoded H264 not raw NV12,
and detector-only. The re-acquire numbers are replay (no appearance in the MOT
path; live appearance exists on the board). The five-tile latency figures come
from a recording with no person in frame, so they bound the pipeline cost but
not tracking quality. The 2026-09-11 exposure-trial directory is a FAILED run
(cap never applied) and must not be cited — see its README. No thermal or
`get_throttled`-equivalent was logged for the SBC runs; treat fps as
best-case bench numbers.

## 2026-09-12 (later) — Hailo-15L SBC: VisDrone-DET, five-tile vs single-tile recall by size

Evidence `bench/results/2026-09-12-visdrone-det/` (README, `score.json`, both raw
runs). Versions: bench/versions.md 2026-09-10 snapshot (board unchanged: VPSP
1.12.0, HailoRT 5.3.0); probe `hailo-preprocess-probe` sha `726d5e12…`.

**Setup.** VisDrone2019-DET-val, all 548 aerial images fitted onto a 1280x720
canvas (the node's tile source size), NV12 via the controlled-HEF calibration
transform, streamed through the on-board reference probe with the exact
`five_tile_layout` (4 corners 768x432 + full), 2740 inferences per HEF at post
threshold 0.05. Node filters (cut margin 0.08 as implemented, corner max area
0.05, aggregation IoU 0.3 / containment 0.7) mirrored in the scorer. Greedy
IoU ≥ 0.5 within class group; buckets by canvas-pixel height. Node stopped and
restored (`start-tiles`) around each run; live model untouched.

**Results (recall, all scored classes / person; FP per image):**

| HEF | Tiling @ floor | all | person | person 16–32 px | person 32–64 px | FP/img |
|---|---|---:|---:|---:|---:|---:|
| old 24a050fb | single @0.15 | 0.268 | 0.172 | 0.082 | 0.370 | 7.85 |
| old | five @0.15 | 0.393 | 0.310 | 0.230 | 0.577 | 12.30 |
| old | single @0.5 | 0.129 | 0.043 | 0.003 | 0.085 | 0.42 |
| old | five @0.5 | 0.223 | 0.125 | 0.041 | 0.288 | 1.09 |
| controlled aec84f00 | single @0.15 | 0.277 | 0.155 | 0.062 | 0.344 | 7.93 |
| controlled | five @0.15 | 0.408 | 0.301 | 0.210 | 0.577 | 11.39 |
| controlled | single @0.5 | 0.143 | 0.042 | 0.003 | 0.084 | 0.52 |
| controlled | five @0.5 | 0.241 | 0.126 | 0.037 | 0.294 | 1.34 |

Person <16 px: ≤ 0.025 on every row. Probe inference wait per region, median /
p95: old 21.0 / 24.3 ms, controlled 26.3 / 29.1 ms. FP near-miss share
(unmatched detection still overlapping a ground-truth box at IoU ≥ 0.3):
59–71 % at the 0.15 floor, 45–48 % at 0.5.

**Reading.** Five-tile roughly doubles 16–64 px recall on both HEFs at +3.5–4.5
FP/img (0.15 floor) or +0.7–0.8 FP/img (0.5 floor); objects under 16 px in the
720p source are unreachable by either configuration; old vs controlled HEF differ
by a few points either way (controlled better on vehicles/overall, slightly
lower on person at 0.15 single-tile) — no aerial-data regression from the
controlled build.

**Red-team.** COCO-trained model on a drone dataset it was never meant for, so
absolute recall is low and FP counts include class confusions the grouping does
not absorb (rider/motorcycle, tricycles are ignored not scored). 408 of 548
images were downscaled 0.94× and 121 upscaled 1.33× to reach the canvas, so
canvas px ≠ native px for them. IoU ≥ 0.5 is harsh on 10–20 px boxes (a 2 px
offset fails), which depresses the smallest bucket for both tilings equally.
Detector-only: no tracking, no live fps — the five-tile latency cost is the
golden-session figure above (~7.5 fps, ~230 ms age), not re-measured here. The
cut-margin filter dropped ≈11 % of raw corner detections; its recall cost is
not separated. Single val split, no confidence intervals.

## 2026-09-12 (later) — VisDrone-MOT replay: lock/outage/re-acquire on drone footage; radius growth 0.5→2.0

Evidence `bench/results/2026-09-12-visdrone-mot/`. Native replay (`garuda-track-replay`,
ctest 7/7), ground-truth boxes as detections at an assumed 30 fps, target-only
drops of 2.0–2.5 s on four sequences (dense crowd A, moving camera B, small
top-down walker C, sparse partially-occluded D); idealized appearance where
stated; MOT17-02/09 re-run as regression.

**Finding.** At the shipped `reacquire_radius_growth` 0.5 extents/s, B and C
never re-acquired even with appearance + crowd flag: C's 25-px target moved
0.094 of the frame in 1 s against a 0.062 radius; B's raw displacement
0.39–0.66 (camera + walk) against 0.18–0.26. Sweep 0.5/1/2/4 extents/s:
A and D re-acquire at every value (733 ms), C from 2.0 (733 ms), B from 2.0
(1700 ms; 1133 ms at 4.0); wrong-identity frames unchanged at every value.
Default raised to 2.0. MOT17 regression identical to the recorded numbers
(09: 224 control-valid, 0/0, 733 ms; 02: 399, 35/35, 733 + 33 ms).

**Results at the new default** (control-valid frames / wrong-id ON vs OFF /
re-acquired): A geo 74 / 0 vs 0 / no; app+crowd **352 / 0 / 733 ms**. B geo
35 / 16 vs 16 (pre-existing association switch) / no; app+crowd 78 / 0 /
1700 ms; app+crowd+camera-motion **160 / 0 / 733 ms** (and no loss at the
frame-35 camera jerk: 74 tracking frames before the drop vs 19). C geo 44 /
0 vs 0 / no; app+crowd **50 / 0 / 733 ms**. D geo 134 / 0 vs 0 / no; app
(no crowd flag needed) **510 / 0 / 733 ms**. Geometry-only never binds
(fail-closed). One coasting-frame overlap (C, frame 156, IoU 0.57, not
control-valid) is the only non-zero wrong-id cell in the appearance rows.

**Red-team.** Idealized appearance (perfectly separable identities), ground
truth as detections (no misses/jitter), 30 fps assumed, four hand-picked
cases. The ground-truth camera-motion proxy is an oracle the live estimator
will not match exactly. The growth change is validated here and on MOT17
only. DEPLOYED 2026-09-12 20:02: binary sha256 9f40f128… staged and running on the tiles
profile (frames accepted, rejected 0, age ≈ 229 ms at the first sample); OSNet HEF and the
`perception-follow.json` profile staged alongside (not yet the running profile).
`reacquire_appearance_crowd` remains off by default — every crowded aerial
case depends on it, which is the argument for the pending live check.

## 2026-09-12 (later) — VisDrone-SOT: real detector + real tracker on drone footage; histograms fail as identity evidence

Evidence `bench/results/2026-09-12-visdrone-sot/`. Controlled HEF aec84f00 through the
on-board probe (five-tile geometry, one run per sequence, node stopped/restored), detections
into `garuda-track-replay` as single-tile and five-tile streams with the board's 72-bin
`describe()` histogram recomputed from the canvas NV12; click on the annotated target once
the detector holds it ≥ 0.5 for 5 frames; 30 fps assumed; no camera-motion input.

**Detector on target (frames with a person box at IoU ≥ 0.5 / median conf / frames ≥ 0.5):**
086 single 641/697 / 0.515 / 344, five 667/697 / 0.773 / 650; 029 (top-down rider, 42 px)
single 508/568 / 0.162 / 28, five 538/568 / 0.197 / 59; 024 single 1416/1478 / 0.659 / 1202,
five 1330/1478 / 0.750 / 1284.

**Tracker after the click (on-target rate / control-valid / control-valid OFF target /
losses (recovered) / longest loss):** 086 single 0.906 / 437 / 19 / 7 (6) / 800 ms; 086 five
0.952 / 659 / 25 / 4 (4) / 667 ms. 029 lock only possible at frame 541 (single) / 516 (five)
of 568 — detector below the birth floor until then — then 0.96 / 0.98 on the remainder.
024 single 0.333 / 715 / **299** / 12 (11) / 17.5 s; 024 five re-acquire ON 0.237 / 472 /
**180** / 12 (11) / 30.2 s; 024 five re-acquire OFF 0.237 / 317 / 25. Crowd flag on = default
on every row; on 086/029 all three configs identical (coasting bridged every loss, re-acquire
never engaged).

**Finding.** On 024 five-tile, after a full occlusion at frame 603, re-acquire went
`reacquiring` at 645–672 and bound track 67 — not the target — at 677, following it for ~460
frames (180 control-valid) until it died. Measured histogram distances: target-as-last-seen
vs track 67 **0.19** (gate 0.55); the target vs its own later histograms median **0.33**
(max 0.52); target vs other persons in the same frame (885 pairs) median 0.34, **88 % under
the gate**. The impostor was closer to the memory than the target is to itself: the 72-bin
NV12 histogram does not separate drone-view pedestrians at ~80 px, and no gate value can
(anything refusing 0.19 refuses the target's 0.33). The 299 single-tile off-target frames are
ordinary association switches in the same "similar objects" scene (identical with re-acquire
OFF) — same histogram in `pair_cost`.

**Red-team.** Three sequences, one HEF, the decisive result on one sequence. Histograms from
the canvas rather than the node's AI-stream frame (same binning, different resolution). No
camera motion in replay (live has it), 30 fps assumed, harness click heuristic. The OSNet
person embedding — the board's stronger descriptor — is not exercised offline; the finding
is about histograms only.

## 2026-09-12 (evening) — Hailo-15L SBC: board switched to the follow profile (single tile + target ROI + OSNet identity)

`hosts/hailo15l/fresh/perception-follow.json` via `fresh_tracking_ctl.sh start-follow`; binary
sha256 `20dd92f0…` (radius growth 2.0, class-generic ROI assist, confidence-preserving ROI
merge), OSNet HEF `49a46e48…` staged. Verified without a person in view (three samples 10 s
apart, 20:27–20:28): frames 468 → 668 → 869, rejected 0, publish interval 40.0–40.1 ms
(~25 fps), publish–capture age 106 / 131 / 88 ms, `target_roi` mode assist reason
`not_eligible` (no lock), `person_embedding` enabled with 0 inferences, MemAvailable
1 389 360 kB after start (second detector + OSNet loaded), SoC 59.6 °C. ROI and embedding
inference cost, lock hold, re-acquire latency and wrong-bind count on this profile are
`TBD-bench` until the owner's live session (procedure in
`bench/results/2026-09-12-visdrone-sot/README.md`). Revert: `fresh_tracking_ctl.sh stop &&
start-tiles` (or `start-letterbox` for single tile without ROI).

## 2026-09-12 (evening) — Hailo-15L SBC: follow path measured offline — oracle target ROI and real OSNet identity on VisDrone-SOT

Evidence `bench/results/2026-09-12-visdrone-sot/` (per-sequence `replay-summary.json`,
`replay-summary-identity.json`, `separability-roi.json`, `embeddings*/run.json`). Same three
sequences, probe re-run with a sixth region per frame (the RoiAssist crop around the annotated
target, 640 px minimum side), OSNet descriptors for every person detection computed on the
board (`garuda-embedding-probe`: inference median 6.50 ms, p95 6.61 ms, crop 3.81 ms; 44 428 /
34 471 / ≈ 20 k crops for 086 / 024 / 029 at caps 64 / 128 / 64).

**Oracle target ROI (histogram tracker, default config).** 086: detector on target 689/697,
median conf 0.761, 651 frames ≥ 0.5 (single 641 / 0.515 / 344; five 667 / 0.773 / 650); hold
0.930 (single 0.906, five 0.952), control-valid 647, off-target 32, 2 losses. 029: 510/568,
0.187, 36 — detector-limited at every scale. 024: 1412/1478, 0.743, 1313 detected, but hold
0.108 (single 0.333, five 0.237): an association switch at a crossing (frame ~251) moves the lock
to a neighbour, that track dies, and the true target's own track — born before the loss — is
correctly refused by the born-after-loss gate; window expires. Off-target control-valid frames
70 (single 299, five 180). Before the merge-rule change (1983f75) the crop's confidence never
reached the tracker: 086 roi read 0.521 median, identical to single.

**Real OSNet identity (`learned_person_identity`, owner path).** Separability, target vs other
persons / share under the 0.25 gate: 086 median 0.412 / 5 % (histogram 0.634 / 23 % under 0.55);
024 median 0.213 / **70 %** (histogram 0.331 / 91 %). Owner on 024, single / five / roi:
on-target 0.083 / 0.073 / 0.002, off-target control-valid **26 / 21 / 0** (histogram tracker
299 / 180 / 70), the rest ambiguous (`similar_identity_candidates`,
`identity_evidence_incomplete`), occluded, reacquiring. 086 (crowd of 50–70 boxes, cap 64
leaves uncovered persons): on-target 0.10 / 0.23 / 0.29, off-target 2 / 12 / 13, mostly
`identity_evidence_incomplete`. 029 (short window): on-target 0.64 / 0.66 / 0.75, off-target 0.

**Red-team.** Oracle crop centred on the annotation, not the tracker box; 30 fps assumed;
no camera-motion input; descriptors from the canvas, not the node's frame; OSNet is a
ground-level re-id model evaluated on top-down 80 px pedestrians — its live separability at the
follow camera's viewpoint is unmeasured (`TBD-bench`, owner session). The owner's crowd refusal
is by design (any observed person without a descriptor, or two within the 0.08 margin), and the
node embeds at most 4 persons per frame live.

**2026-09-12 21:13 — follow profile redeployed with the identity-owner continuation fix and the
embedding budget** (binary sha256 `f8c08a28…`, `person_embedding_max_per_frame` 6, commit
7dbb97a). Two samples 8 s apart without a person: frames 206 → 368, rejected 0, publish interval
38.6 / 36.4 ms, age 155 / 76 ms, `target_roi` assist `not_eligible`, `person_embedding` enabled,
MemAvailable 1 391 956 kB, SoC 60.6 °C. Live lock/re-acquire numbers remain `TBD-bench` (owner
session).

**2026-09-12 21:33 — identity-owner continuation fix measured offline** (commit 7dbb97a; same
inputs and descriptors as the "follow path measured offline" entry, replayed with the fixed
owner; `bench/results/2026-09-12-visdrone-sot/<seq>/replay-summary-identity-fix.json`).
086 identity on-target single / five / roi: 0.101 / 0.227 / 0.287 → **0.164 / 0.407 / 0.674**,
control-valid 71 / 167 / 209 → 114 / 295 / 473, off-target control-valid 2 / 17 / 13. 024:
unchanged (0.083 / 0.073 / 0.002; the refusals there are similar-candidate ambiguity, not
missing descriptors). Red-team: full-coverage descriptors (cap 64–128 per frame) — live the
budget is 6 target-first crops, so the crowd numbers are an upper bound for the board.

## 2026-09-12 22:05 — Hailo-15L SBC: FIRST LIVE SESSION on the follow profile (owner in view)

Capture `bench/results/2026-09-12-visdrone-sot/live-follow-20260912-2205.jsonl.gz` (1477 shim
samples, 157 s, `golden_capture.py`); board binary `f8c08a28…`, `perception-follow.json`
(single tile + target ROI + OSNet identity, embedding budget 6). Owner click-locked himself
(lock.id 4) at ~1 m from the camera (box 600–800 px tall = 85–110 % of the 720p frame).

**Measured.** Node age p50 74–86 ms, p95 ≤ 106 ms, max 116 ms (budget 200) — never stale.
OSNet 6.9 ms inference + 4.6 ms crop per person; ROI crop **not eligible** at this range (a 2.5×
crop of a 613 px box exceeds the frame; by design, the crop is for small targets).
Re-identification after leaving the frame — absence 0.7 / 0.4 / 0.2 / **3.6 s** → back on
target in **0.37 / 0.23 / 0.17 / 0.20 s**, every time with the SAME `lock.id` 4 and a new MOT id
(90 → 91 → 92 → 94), reason `identity_verified`. States over the session: tracking 1124,
occluded 222, reacquiring 17, lost 114 rows. A **12.4 s absence** (t = 137–149 s) crossed the
owner's 10 s identity memory: `lost` (memory expired) at 145 s, the return at 149 s was not
re-bound, owner re-clicked at 157 s (new lock.id 5, and it landed on the second person, track
98, who had entered at 152 s). Brief `occluded` blips (1–3 samples) coincide with detector
misses on the over-close, partly out-of-frame body (conf dips to 0.3–0.5); the identity owner
never coasts, so control drops for ~100 ms each time.

**Two defects found.** (1) The shim relabels every unobserved-lock sample as `source_stale`
(`valid_for_ms` = freshness − observation age → 0 whenever the owner is occluded), hiding the
node's real reasons (`selected_identity_not_observed`, `candidate_not_confirmed`): 345 of 1477
samples mislabelled while the frame age never exceeded 116 ms. (2) The identity memory (10 s)
is not configurable and is short for a follow target that steps behind something.

**Red-team.** One person, one range (too close for the ROI path), no bystander crossing during
the lock (the second person only appeared after the memory had expired), no controller in the
loop; re-bind latencies are shim-sample resolution (~100 ms).

**2026-09-12 23:08 — follow profile redeployed with the identity-memory config (30 s) and the shim
label fix** (binary sha256 `8b171a33…`, commit f83573e; shim md5 55e1c79c). Verified without a
person: accepted, 208 frames, rejected 0, age 80 ms, `target_roi` assist, `person_embedding`
enabled. Note: the first restage at 22:55 shipped the previous binary (`f8c08a28…`) with the new
profile key and the node refused to start (`unknown tracking parameter: identity_memory_ms`);
the board ran `start-letterbox` for ~10 minutes until the rebuilt binary was staged.

## 2026-09-13 00:05 — Sim-in-the-loop follow-me on PX4 SITL (SIH quad, headless, PC)

Evidence `bench/results/2026-09-13-sim-followme/` (README, per-scenario JSON with 20 Hz tick
logs, PX4 console logs). Chain: scripted walking target (0.8 m/s arc) → pinhole projection →
synthetic tracker view → `follow_controller.compute` → `FollowAuthority` (coast 1.5 s, re-acquire
4 s, TTL 150 ms) → `sim_offboard_bridge` (pymavlink, GARUDA_SIM=1, UDP 14540, mixed setpoints
at 20 Hz) → PX4 `sihsim_quadx` (commit 47ce421). No camera, detector, board or ROS in the loop.

| Scenario | ACTIVE / follow ticks | framing \|err\| med / p95 | standoff med / p95 (m) | outcome |
|---|---:|---:|---:|---|
| nominal | 800 / 801 | 0.033 / 0.046 | 5.70 / 5.82 | 40 s follow, max cmd 1.39 m/s |
| target_loss 3 s | 740 / 801 | 0.033 / 0.049 | 5.71 / 7.56 | COASTING 1.3 s → HANDOFF → re-engaged, standoff recovered |
| video_stall 2 s | 800 / 801 | 0.032 / 0.048 | 5.68 / 6.78 | 39 hover ticks via intent TTL only |
| abort 5 s | 701 / 801 | 0.034 / 0.049 | 5.74 / 8.89 | sticky HANDOFF, resumed on operator resume |
| publish_failure | 303 / 304 | — | — | breaker at 15.2 s → LAND: PX4 AUTO, −3.02 → +0.10 m in 8 s |

Every run: armed, OFFBOARD, takeoff 6.9 s, first ACTIVE 0.05 s into follow. **Red-team.**
Synthetic perception from the target's true position (no detector misses except the scripted
ones, no tracker), SIH dynamics not Gazebo, one target speed, gains hand-set for a 5–6 m
standoff by the controller's proportional law (no metric range), single seed.

## 2026-09-13 00:50 — descriptor-aware association: negative result (VisDrone-SOT 024 / 086)

`bench/results/2026-09-12-visdrone-sot/<seq>/replay-summary-assoc.json` (hard 0.5 gate,
descriptor replaces histogram) and `replay-summary-assoc-blend.json` (0.85 gate, blended).
Histogram-default tracker on-target: 024 single 0.333 → 0.031 (hard); five 0.237 → 0.069 (hard)
/ 0.021 (blend); roi 0.108 → 0.070 (hard) / 0.042 (blend); 086 single 0.906 → 0.893, five
0.952 → 0.902 (off-target 25 → 62), roi 0.930 → 0.908 (off-target 32 → 48) with the hard gate.
Identity owner runs: 086 roi 0.674 → 0.647 (hard); 024 roi 0.002 → 0.197 (blend) the only gain.
Shipped as opt-in, default off (commit 59555c9).

**Identity gate/margin sweep on 086 (real OSNet, `replay-summary-gate-sweep.json`):** widening
`identity_max_distance` 0.25 → 0.35 / 0.45 lowers on-target (roi 0.641 → 0.512 / 0.527; five
0.488 → 0.353) — more candidates fall inside the gate, more `similar_identity_candidates`
refusals. Narrowing `identity_ambiguity_margin` 0.08 → 0.04 raises it: roi 0.641 → **0.754**
(off-target 13 → 15), five 0.488 → **0.611** (17 → 21). Validation with the default gate and the
shipping tracker on 086 and 024 follows below.

## 2026-09-13 01:05 — Hailo-15L SBC: follow profile with the acquisition mode (tiles while unlocked, single tile + ROI once locked)

Binary sha256 `fa2f8f40…` (opt-in association off, identity gates configurable, node
`tiles_when_unlocked`), profile `perception-follow.json` with `detection_tiles` + `tiles_when_unlocked`,
`freshness_ms` 500. Verified without a person: `detection_tiles.reason` = `tiled`, tile inferences
climbing with the frame count (81 → 117 in 6 s), publish interval 168 / 157 ms (≈ 6 fps while
searching), age 298 / 358 ms (< 500 budget), accepted, rejected 0, ROI assist and OSNet identity
enabled, MemAvailable 1 358 688 kB with all three networks loaded. The switch to the single-tile
+ ROI path on a lock (expected ~25 fps, age ~80 ms as measured on 2026-09-12) is `TBD-bench`
until a person is locked. Revert: `fresh_tracking_ctl.sh stop && start-letterbox`.

**2026-09-13 00:15 — margin 0.04 validated with the shipping tracker (association off),
`bench/results/2026-09-12-visdrone-sot/<seq>/replay-summary-margin.json`:** identity on-target
086 single / five / roi 0.164 / 0.407 / 0.674 → 0.243 / 0.512 / 0.761 (off-target 2 / 17 / 13 →
3 / 21 / 15); 024 0.083 / 0.073 / 0.002 → 0.238 / 0.407 / 0.002 (off-target 26 / 21 / 0 → 44 /
32 / 0). Adopted in the follow profile (restaged 00:15, binary unchanged `fa2f8f40…`).

## 2026-09-13 10:40 — Hailo-15L SBC: click refused on the follow profile ("fresh learned person descriptor required") — root cause and fix, lock-time switch measured

**Symptom (owner, morning):** every click on a person on the live follow profile returned
`A fresh learned person descriptor is required for identity selection.` **Board evidence
before the fix** (`/api/state`, binary `fa2f8f40…`): `diag.person_embedding.inferences` **0**,
`skipped` **97 376** over 222 149 frames, publish age 397 ms, one person track at 0.96, lock
`none / not_selected`. **Cause:** the node's embedding loop skipped every crop once the frame
was older than a fixed 150 ms (`fresh_node.cpp`), a guard sized for the single-tile path
(age ~80 ms); in the acquisition mode's searching state the five tiles deliver frames ~300 ms
old, so no person ever carried a descriptor and `TargetOwner::select` refused the click. The
lock-time switch to the single-tile path was never reached, which is why it stayed `TBD-bench`.

**Fix:** `person_embedding_max_age_ms` (node profile key, 50..5000, default = the tracker's
`freshness_ms` so every frame the tracker can still accept also gets its descriptors);
`perception-follow.json` sets 500; diag now reports `skipped_stale`, `max_age_ms`,
`budget_per_frame`. Gate: 7 ctest + 57 Python tests (new profile assertion
`person_embedding_max_age_ms ≥ freshness_ms`); ARM binary `fa2f8f40…` → **`3c99fbc9…`**, staged,
`start-follow`.

**After the fix (same scene, owner in view):** searching state — embedding inferences 94 on 95
frames, skipped 0 / stale 0, last crop 4.5 ms + inference 10.7 ms, age 251–352 ms, tiles `tiled`.
API click on the person (conf 0.94, sequence 332): reply `ok`; 1.4 s later lock
`tracking / identity_verified`, `detection_tiles.reason = locked_single_tile`, **age 64 ms**
(then 91–140 ms over the next 10 s), **20.1 fps** over the 11 s watch (frames 332 → 554),
embeddings 1 per frame, skipped 0. Subsequent owner clicks from the GUI were accepted too
(new lock ids 5 and 6, the last on the cell phone); while the lock was `reacquiring` the tiles
came back (`tiled`, age 264–372 ms) and dropped again on the next lock — the acquisition mode
behaves as designed. The ROI crop did not engage (`not_eligible`: the person filled ~80 % of the
frame height); the ROI-engaging range and the bystander crossing remain owed live checks.

## 2026-09-13 — independent audit of handoff 237ae7b (read-only board checks)

Version snapshot: `bench/versions.md`, "2026-09-13 — independent follow-handoff audit".
Full findings, source locations, limits and proposed work:
`docs/2026-09-13-independent-follow-audit.md`. No board, camera, selection,
HEF or running-process changes. No vehicle I/O or new SITL execution.

Fresh native Release build: 7/7 CTest targets passed. Python with the fresh
replay binary: follow 20 passed, bridge 5 passed, tracking 45 passed with one
adapter module skipped (staging environment unavailable). VisDrone tool tests
15 passed with `PYTHONPATH=bench/hailo_reference`; the first invocation without
that path failed collection, and the first Python runs without the replay
binary skipped dependent tests. No source fix was needed to run these suites.

Board running `/proc/20153/exe` and installed/host deployment binary hashes
agree: `3c99fbc963e4efbcfb43c7a92207d96e16aab0ee8d7415c08e0f2460653f9e02`.
Controlled YOLO11s and OSNet hashes agree with the handoff. Current stream
configuration is 640x640 letterbox + paired 1280x720, both configured at 20 fps.
20 read-only `/api/state` samples: 9.487614647 s elapsed, 57 sequences advanced
(6.007832540 updates/s), age median 364.340200 ms, maximum 438.820440 ms.
All were `tiled`, rejected-frame counter 0 -> 0, OSNet 4218 -> 4218, ROI 67 -> 67.
Phone already lost/expired; this does not measure locked/person/ROI performance.

Independent raw A/B recount: 2165 region predictions, 433 source frames per
HEF. Phone-class presence at 0.15: old 191, controlled 322; at 0.5: old 129,
controlled 200. Median summed waits 94.389000 and 122.145320 ms. This verifies
the stored numbers, not annotated target recall. Both complete 548-image DET
reports recomputed with `load_results`/`evaluate` exactly equal the committed
metric dictionaries. Controlled five-tile person recall 16–32 px 0.2102
(old 0.2302), 32–64 px 0.5770 (old 0.5773), below 16 px 63/2628 = 0.0240.
Five-tile FP/image controlled 11.394, old 12.301.

Saved SITL tick recount (not rerun): nominal 801 follow ticks, 800 ACTIVE,
settled distance median 5.699 m, absolute framing median 0.03305; target loss
26 COASTING + 34 HANDOFF, 61 hover ticks; video stall 39 hover ticks; abort
99 HANDOFF, 100 hover ticks; publish-failure trace 304 follow ticks. Source
confirms synthetic perception, not the actual tracker/camera feedback loop.

Fresh-library diagnostic probe (source/binary in scratch directory listed in
the audit): across 20 synthetic frames, ROI requests with primary evidence at
60 ms age = 10, at 101 ms = 0, without primary at 60 ms = 0. Interior tile top
edge mapped to network y=0.21875 and was not rejected at margin 0.08. A 0.9
confidence contained fragment of height 0.1 suppressed a 0.8 confidence body
of height 0.4. These are deterministic functional probes, not camera metrics.
Pure Python probes showed repeated stale commands renewing authority TTL and
preview intents producing nonzero setpoints. A fully mocked vehicle/clock
SITL probe reached `arm()` with execution=preview; no network was used.

Red-team conclusion: the measurements are real but several summaries overreach.
Oracle crops, assumed 30 fps/10 ms latency, high-resolution offline identity
crops and idealized MOT evidence cannot establish the live handover's success.
Fix those equivalence gaps and the reproduced code defects before another
model change or the board bridge. Live fast-motion/crossing gates remain
TBD-bench; no flight-readiness claim.

## 2026-09-13 — audited follow fixes, causal 15L replay and PX4 SIL

Implementation/report: `docs/2026-09-13-follow-fixes-and-sil.md`.
Raw evidence and scores: `bench/results/2026-09-13-follow-fixes/`.
Exact-SDK ARM build passed. Native CTest 7/7; tracking Python 45 pass + one
unstaged-adapter skip; follow 24 pass; bridge 7 pass; VisDrone tools 15 pass.
Commands: `hosts/hailo15l/build_fresh_tracking.sh`, Python unittest discovery,
`PYTHONPATH=bench/hailo_reference python3 -m pytest -q bench/hailo_reference/test_visdrone_tools.py`.

PX4 SIH: `GARUDA_SIM=1 python3 bench/sim/followme_sitl.py --scenario all
--duration 35 --execution live --perception tracker --tracker-binary
/media/bhanu1234/Development/hailo-export/follow-fixes-20260913/native/garuda-track-replay
--out bench/results/2026-09-13-follow-fixes/sil-final`.
All six scenarios passed `verify_follow_sitl.py`, reached armed/OFFBOARD and
finished disarmed. Native tracker and freshness adapter are real; detections
and appearance are synthetic. Nominal 695/700 ACTIVE ticks; settled framing
median/p95 .034/.046; simulated distance median/p95 5.670/5.788 m. Publisher
breaker fired at 15.2 s for failure injected at 15 s. Link-loss first run ended
observation before disarm; retained in `sil-short-observation`. Rerun with
120 s maximum observation finished PX4's configured RTL/land/disarm without
LAND injection or changing FC parameters. Its terminal altitude was -0.041 m NED.

Real HEF/DSP/OSNet causal replay: 200 prepared frames per trial, 50 ms source
period and explicit 50 ms source-age assumption; measured compute drops frames.
No ground-truth crop feedback. Car 115: initial 250 ms confirmation gap failed
selection (34 processed); gap500 enabled selection, 28/31 post-selection
on-target/control-valid outputs, but no ROI. Planner cadence fix: 42 processed,
158 skipped, 27 ROI updates, 19 global updates; 35/39 post-selection valid
on-target, one valid off-target (IoU .333143, age 314.791 ms), three coasting.
Age median/p95 200.145/309.100 ms. Skips are unscored; not live FPS or continuous
tracking recall. The off-target box exceeded the consumer's 200 ms age limit.
Person 086: original identity cadence 1/31 valid on-target, 30 ambiguous;
gap500 yielded 4/31 valid on-target, 26 ambiguous, one occluded, 2 ROI updates,
34 processed/166 skipped, median/p95 age 275.566/277.910 ms, zero valid off-target.
None met the consumer's 200 ms age limit. **Crowded-person robustness fails.**

Complete 548-image DET re-score with corrected content-edge/provenance filters:
controlled HEF five-tile @.5 grouped recall .2414 -> .2289, FP/image 1.338 ->
1.141; @.15 recall .4075 -> .3891, FP/image 11.394 -> 12.943. Both old-live and
controlled raw prediction sets scored; complete values in `det-corrected-filters.json`.
Not an overall accuracy improvement. Legacy reproduction remains selectable.

First deployed-candidate desk watch: selected the sole visible person successfully. 97 samples
over 19.827660 s, 346 processed sequence advances = 17.450370 updates/s. Age
median/p95 117.734640/236.630880 ms; 96 tracking/control-valid and one initial
unselected publication. Pass-count samples: 91 single-pass, six five-pass.
Paired 1280x720 OSNet, zero source misses/embedding failures; one expected
selection-generation discard. Large target, no ROI needed. Raw JSONL retained
gzipped. No prescribed movement/crossing or all-classes accuracy test.

Final large-target corner-scan correction: repeat watch of sole visible person,
97 samples / 19.798451 s, 394 sequence advances = 19.900546 updates/s. Age
median/p95 109.993440/148.936400 ms. 96 tracking/control-valid, one initial
unselected publication; 95 one-pass / two initial five-pass samples. Same
paired-source identity and zero pair/embedding failures. Running PID 24138
binary hash matched host and installed binary (versions). This is a desk-path
smoke check, not prescribed fast motion or controlled benchmark A/B.

Real-camera-envelope PX4 test, first candidate (`sil-board`): 417/500 ACTIVE
ticks, 82 COASTING, one IDLE; zero translation, every expired/ineligible tick
hovered, landing/disarmed at terminal -0.058 m NED. Explicit verifier passed.
The periodic COASTING gaps tracked unnecessary large-target corner scans,
prompting the correction above. Final repeat (`sil-board-final`): 499/500 ACTIVE,
one initial IDLE, no COASTING, 500 board samples, zero transport errors, zero
translation, landing/disarmed at -0.094 m NED. These use real perception but are
yaw-only transport-in-loop; camera images are not rendered from simulator pose.

Red-team: synthetic SIL cannot certify camera robustness; causal replay still
assumes source timing and differs in motion-image downscaling; skipped frames
cannot be counted as successful tracking. Edge/NMS corrections reduce aggregate
recall; crowded person fails. Updated timing gaps remain bench tuning, not
validated false-match probabilities. The desk latency watch is not a controlled
A/B against the audit's searching-state scene. No real-flight readiness claim.

## 2026-09-13 — actual Gazebo/Hailo/PX4 visual loop and local console

Scope: real rendered X500 RGBD pixels sent to the desk 15L, actual YOLO11s and
OSNet with the existing causal replay inference/tracker loop, fresh follow
authority and owned local PX4 SITL. This is no longer the desk-camera/yaw-only
transport test. No actor coordinates feed perception or control. The separate
world-view camera and drone-camera source images were inspected directly.

Reproduce with `GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh --out NEW_DIR
--auto-demo --duration 60`; verify with `bench/sim/verify_gazebo_follow.py`.
Evidence: `bench/results/2026-09-13-gazebo-visual/`, including compressed raw
ticks, full event logs, PX4 logs, per-run hashes and matched source-frame sample.

`visual-native`: 1522 ticks, 593 unique inference frames; 386/1194 non-hover
follow ticks, 302 ticks with nonzero motion. Ingress→result median/p95
132.791977/235.206678 ms; board compute 90.174/185.65144 ms. Control tick
median/p95 49.978658/51.376403 ms; RTF median .9934268179. Maximum displacement
from follow start 6.33073563 m. All 593 frames paired to exact-stamp depth;
31 evaluated dropout ticks held; recovery and final disarm verified.

`visual-aes`: 1542 ticks, 603 unique inference frames; 377/1190 non-hover follow
ticks, 272 with nonzero motion. Ingress→result median/p95 130.037609/229.925428 ms;
compute 90.43228/185.74628 ms; control interval 50.002813/51.510733 ms; RTF median
.9937878055. Maximum follow displacement 6.04413551 m. All 603 depth paired;
30 evaluated dropout ticks held, recovered, final disarm. AES-GCM was explicitly
selected after confirming board AES/PMULL support; this is not a controlled
accuracy/performance A/B and does not establish an overall cipher advantage.

`visual-final`: final staged binary repeat. 1531 ticks, 617 unique frames;
415/1194 non-hover follow ticks (34.8%), 307 nonzero-motion ticks. Ingress→result
median/p95 127.767997/227.88036 ms; compute 90.24592/185.59552 ms. Control
interval median/p95 49.999642/51.504523 ms; RTF median .9936495082. Maximum
follow displacement 6.47236046 m. All 617 frames depth paired; 31 evaluated
dropout ticks held, recovered, terminal telemetry disarmed. Independent verifier
also checks selected source/sequence, age, speed limits and depth-required
translation. **Functional demo passed; continuous robustness did not.**

PC format-conversion micro-test: seeded NumPy RNG42 1280×720×3 RGB8, 30 calls
per implementation. NumPy median/max 32.3745154892/44.4549950189 ms; native
2.9755480209/3.9747669944 ms. Exact output-byte equality asserted. Native helper
uses the same BT.601 limited-range coefficients and round-to-even 2×2 chroma
average; randomized full-resolution and small-resolution byte comparisons pass.

Regression validation: 7 native CTests passed; tracking Python 46 tests with
one skipped, follow 24 passed, bridge 7 passed, new visual-SIL tests 15 passed;
exact-SDK ARM build completed. Existing six-scenario headless SIH evidence
re-verified (not rerun or relabelled as visual tests). HTTP/Origin/Host/action
checks and JS/shell syntax passed. Browser layout/click and WebMCP execution
were not available for automated validation.

Startup/debug failures retained outside the repo in the run directory: missing
GCS heartbeat and premature arming before estimator readiness; position-before-
attitude startup; double-charged compute/old receiver timestamp; truncated event
history and missing final tick. Fixed without disabling PX4 preflight checks,
changing the 200 ms age limit or 150 ms maximum intent TTL, or supplying oracle
target data. The final desk restart returned PID 26835 with unchanged installed
binary/profile hashes and an advancing IMX678 stream; runtime target selection
was cleared. Subsequent interactive-demo state is recorded in its own run folder.

Red-team: passing contract checks does not establish correct target identity on
every frame. The scene has one rendered person, mild motion and no qualified
crossing/occlusion cases. PC ingress is not certified exposure time; simulated
depth is not physical ranging. Native board compute still has costly multi-pass
spikes, so most follow ticks hold. Previous crowded-person failures remain open.

Operator-check spot read under load (not a continuous thermal/power audit):
thermal_zone0 54414 m°C, thermal_zone1 54262 m°C; CPU0 scaling_cur_freq
1100000 kHz. Component assignments of the thermal zones were not asserted.

Additional `operator-check`: HTTP Hold remained sticky for 21.550310636 s;
all 429 ticks evaluated after a 100 ms response allowance were held and had
following disabled. Subsequent Follow produced 0/690 non-hover ticks: target
unobserved/coast budget exhausted (491), then identity memory expired (199).
Do not report this as successful long-loss reacquisition. Stop cleanup observed
armed=false with heartbeat age 2.295861 ms, then the wrapper restored the desk
app. Raw trace and scoped summary retained alongside the nominal visual runs.

## 2026-09-13 — actual ROS 2 / MAVROS on 15L, schedule ablation and SIL

Handoff and reproduction: `docs/2026-09-13-ros2-mavros-campaign.md`. Compact raw
evidence: `bench/results/2026-09-13-ros2-mavros`; full working artifacts:
`/media/bhanu1234/Development/hailo-export/ros2-follow-20260913`.

Installed separate Noble ARM64 rootfs with Jazzy/MAVROS on actual 15L; not PC
ROS, Docker, stock-OS replacement or product-cleared deployment. Native Hailo
libraries/HEFs and desk executable/current profile hashes unchanged. ROS topics,
services and post-MAVROS packets exercised against owned loopback PX4 only.

Axis tests (explicit commands, no perception claim):

| Test | Settled max 30° error | North move N/E (m) | East move N/E (m) | Forwarded motion packets | Observed offboard exit after fault |
|---|---:|---:|---:|---:|---:|
| normal | .085356039° | .755070 / -.067989 | .056408 / .824711 | 321 | none |
| requests stop | .123065514° | .754601 / -.079625 | .098638 / .786656 | 282 | 2.500154629 s |
| ROS/SSH session terminated | .120954985° | .732634 / -.061352 | .090158 / .781314 | 281 | 1.200221799 s |

All ended disarmed, correct coordinate signs, no expired forwarded motion and
no emergency direct LAND. Last fault combines ROS-session/tunnel loss; it does
not isolate those failures. Preflight readiness checks were not bypassed.
Startup failures (empty ROS parameter list, missing chroot localhost, telemetry
relay backlog) retained separately. Service `mode_sent` alone is not a mode ACK.

Exact-input parity: nine retained annotated phone crops (oracle crops, NOT full
view). Fresh source ONNX and actual board HEF compared with retained FP and
quantized-stage outputs. Three samples missed in all stages; substantial other
confidence differences persist. Exact input and model hashes recorded. No broad
detector-accuracy or quantization superiority conclusion. Fixed a separately
identified simulator limited/full-range conversion mismatch; native full-range
conversion has exact-byte reference tests. Physical ISP fault not established.

Schedule campaign: each run has 240 source frames, one fixed initial point,
declared 50 ms source period + 50 ms source age (not measured exposure/FPS).
Processed subsets differ because measured cost determines skipping.

| Sequence | Mode | Processed | Fresh valid on-target overlap | Raw target overlap hits |
|---|---|---:|---:|---:|
| person086 | fullview | 60 | 6 | 58 |
| person086 | fullview_roi | 60 | 2 | 56 |
| person086 | adaptive | 40 | 0 | 39 |
| person024 | fullview | 60 | 0 | 59 |
| person024 | fullview_roi | 60 | 0 | 59 |
| person024 | adaptive | 40 | 0 | 40 |
| car115 | fullview | 68 | 46 | 51 |
| car115 | fullview_roi | 64 | 34 | 49 |
| car115 | adaptive | 48 | 20 | 39 |

Raw hits are class-agnostic overlap, not identity certification. Person086
fullview had 43 identity-evidence-incomplete rejections; person024 never selected.
Adaptive car had one control-valid off-target overlap outside the 200 ms age
gate. Skipped/unselected frames must not be hidden. Fullview detection medians
27–28 ms versus adaptive ~125–128 ms; six-person embeddings ~63 ms; combined
CPU resize/motion ~31–34 ms. Detailed per-run exact medians in summary.json.

Rendered-camera actual board ROS/MAVROS runs (40 s requested follow):

| Run | Host non-hover / follow ticks | Ingress result median / p95 ms | Compute median / p95 ms | Forwarded / rejected motion packets | Max displacement m |
|---|---:|---:|---:|---:|---:|
| adaptive final | 244/796 | 141.223369 / 237.246394 | 92.168200 / 189.739240 | 85 / 28 | 2.144186221 |
| fullview | 576/796 | 112.018843 / 136.950228 | 66.729360 / 70.215200 | 141 / 57 | 3.914449536 |
| final-code fullview repeat | 522/797 | 111.362341 / 136.150643 | 66.576400 / 69.532520 | 201 / 42 | 6.758444121 |

All three held during injected perception dropout, recovered and disarmed;
no emergency direct LAND. Final repeat: 1135 control ticks, 604 unique inference
frames, 347 intended-motion ticks, 31 evaluated dropout ticks; control interval
median/p95 49.9988695/52.08198 ms; RTF median .9929399279. Actual wire checks
include original publication deadline, not borrowing a newer request's deadline.
Final ticks SHA256 `856981cd4fa9061980b57e8ec4d9a0ae3eb15087789679c63497e494301062ed`.
Simple single-person scene, not randomised paired accuracy or crowd validation.

Earlier `ros-visual-third`: 231/693 host non-hover ticks but **only 6** actual
forwarded motion packets, .250827165 m maximum displacement. Retained as evidence
of the relay/timing issue, not retrospectively relabelled as the final code.

Recorded car115, same fixed point (661,396), assumed 20 FPS / 1.2 rad HFOV:
adaptive 75 processed outputs, no selection, zero motion; fullview 146 outputs,
selection succeeded but **one** motion packet, requested heading span .904291166°,
actual follow span .211257751°. Both no translation, held expired pixels and
disarmed. Minimal response-verifier pass is NOT usable aerial following.

Validation: 7 native CTests, exact SDK ARM build; bridge 7 tests; fresh follow
12 tests with one skipped; perception authority 2 and follow authority 10 tests;
31 simulation/contract tests; JS syntax, shell syntax and git whitespace checks.
Browser automation returned `No browser is available`; no layout/click QA claim.

Resource spot checks, not continuous thermal/power qualification: with desk
native + ROS axis test active, 1913 MiB total, 1141 MiB available, thermal_zone0
62508 m°C, 3.5 GiB rootfs free. After final automatic desk restoration PID5190,
1197 MiB available, zone0 60838 m°C. Zone component assignment not asserted.
Temporary package proxy and package-only SSH forward stopped after install.

Red-team / remaining gates: PC envelope and safety relay remain necessary in
this SIL, so this is not standalone all-board autonomy. Remove that round trip
with local native -> ROS ingress without refreshing source deadlines. Crowded
identity/acquisition and aerial freshness still fail. Physical capture clocks,
ranging, FC hardware/firmware, faults/reconnect/operator takeover and propellers-
removed tests are absent. No real-flight, product-license or robustness sign-off.

## 2026-09-13 — installed IMX678 ISP audit and native ROS observer

Evidence: `bench/results/2026-09-13-camera-isp/`; detailed analysis:
`docs/2026-09-13-camera-isp-and-native-ros.md`. Read-only camera checks; three
observer files staged in existing ROS userspace, no vehicle publisher/services.
Desk executable/current config and producer stream unchanged after testing.

Resolved GarudaFreshLetterbox: configured zoom/AI denoise off; managed detection,
tiles and ROI on; detector source canvas 1280x720, not native 4K. IMX678/H15L
AI-denoising HEF present. Live AE enabled, exposure 33.006 ms, gain 12.8828125.
Earlier separate readback gain 14135/1024; AE changes dynamically. Not a blur A/B.

Requested 5 s API audit, 46 unselected-target samples: capture age min/median/max
210.0813599973917 / 292.0706400051713 / 434.48464000225067 ms. Uncontrolled scene,
not recall/FPS. All exceed consumer 200 ms limit; viewer budget remains 500 ms.

Actual native TCP -> on-board ROS topic -> same-board observer:

| Run | Seconds / freeze after | Status ticks | Native snapshots | ROS messages | Errors | Final age ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| initial | 10 / 5 | 200 | 249 | 124 | 0 | 5294.203519999981 |
| final code | 10 / 5 | 199 | 248 | 124 | 0 | 5286.275999993086 |

Initial live interval (<4 s from first status, after first ROS receipt), capture
age min/median/max: 210.8942800015211 / 311.0740200057626 / 411.2738800048828 ms.
After publication freeze, sequence/stream stayed fixed while age increased;
final 20 repeat statuses stale. No target selected, no eligible target, no
MAVROS launch or vehicle I/O. This is not a selected-target control-loss test.
Unit selected-envelope tests prove capture+200 ms expiry for silent/duplicate data.

Validation: camera audit 6 tests, native ROS gate/feed 6 tests, existing sim/
contract 31 tests passed; shell syntax and git whitespace passed. Final viewer
check sequence18631, stream f4758ff1-d096-4d6c-ba3a-bb7d254b4c04, lock none.
No camera restart, settings/GUI change or dependency added.

Structural review: reuse FreshFollow and current ROS rootfs; no second simulator
or frontend. Red-team: transport correctly delivering late/poor detections is
not robust following. Installed low-light HEF does not prove enabled AI ISP or
concurrent performance. Crops still use reduced pixels. Training, zoom/ISP A/B,
selected-target live faults, joined physical-camera SIL and real flight remain
open; no qualification gate ticked.

## 2026-09-13 — joined grand demo, physical person response and aerial regression

Evidence: `bench/results/2026-09-13-grand-demo/`; launch/limitations/next work:
`docs/2026-09-13-grand-demo.md`. Existing desk detector/config unchanged. New
board-local ROS camera ingestion is joined to MAVROS under an independent PC
operator lease and final guarded loopback relay. Physical camera/replay modes
are heading-only; rendered camera uses exact-paired simulated depth. No FC
hardware, native sensor zoom, AI-ISP enablement or training was performed.

Actual native Gazebo GUI launched beside the local console. Console now places
source/world views together, with actual ROS/ENU, MAVROS/NED, forwarded/rejected
wire values, PX4 response, stable target label and target-centred display zoom.
Physical JPEG/snapshot overlays are approximate, not source-frame paired.
Browser unavailable in this environment; HTTP/API and JS syntax checked, no
browser click/layout verification claim.

Physical `live-final`: owner selected person and moved in frame. Actual heading
span **27.06650971838645 degrees**; 128 moving packets forwarded, 55 rejected;
4531 total forwarded; 7176 native ROS messages, 4086 unique inference snapshots,
6314 ticks. All original-deadline checks passed, XY commands remained zero,
Hold/Land/disarm completed. Full-run source capture+HTTP age median/p95
162.3578944989915 / 385.73789999547006 ms (includes unselected/idle periods; not
a controlled person-motion latency distribution). Observed partial boxes were
rejected as outside FOV; don't clip them into falsely valid distance evidence.
Framing-reference event accepted once at 1.0x, height fraction .812500655416669;
nearer/farther relative-range accuracy not measured. MOT ID changed but selected
identity persisted in this session; no independent wrong-person ground truth.

Actual rendered-camera -> board ROS/MAVROS -> PX4 repeats:

| Run | Inference frames | Ingress median / p95 ms | Forwarded / rejected moving packets | Max XY displacement m |
| --- | ---: | ---: | ---: | ---: |
| closed-loop | 542 | 113.419455 / 138.589599 | 115 / 56 | 3.798923876388972 |
| closed-loop-final | 601 | 112.525977 / 139.94168 | 258 / 31 | 7.850030684917905 |

Final repeat: 1146 ticks, 797 follow ticks, 476 host non-hover ticks (not wire
packets), 353 intended-motion ticks, board compute median/p95
66.72192 / 69.9662 ms; control interval 50.002293 / 51.947343 ms; RTF median
.9926595705068407. Injected perception pause: 31 evaluated held ticks, recovered,
final disarmed, no expired original publication forwarded, no emergency direct
LAND. Ticks SHA256 `cc9ccf9c1988c3fac8452442cea9cd10f826b402015333948d40029d489519bf`.
Single-person scene with simulated depth, not crowd or physical monocular follow.
Final physical-only gate hardening/age-label change came after this repeat;
covered by unit tests/disarmed live check, not a new person movement test.

Recorded car115 GUI/ROS response: 148 inference frames, 27 moving packets,
1 rejected; actual follow heading span 1.103799551 degrees. EOF/stale input held
and final disarmed. Minimal protocol-response pass is **not** aerial tracking
qualification. Previous single-packet run was not a paired randomized baseline.

### Expanded actual-Hailo SOT campaign

Frozen fullview schedule, all 11 existing prepared sequences, first min(240,N)
frames each; 50 ms source period and 50 ms initial age assumptions; fixed frame-15
selection point, attempted on next processed frame if skipped. No label-driven
retries/crops. Actual DSP/YOLO11/OSNet/shared tracker; no ROS commands in this test.
**723 processed of 2567 source frames; only 3/11 selections succeeded.**

Final offline publication/expiry integration, retaining skipped frames:

| Sequence | Selected | Fresh on-target time fraction | Fresh off-target time ms |
| --- | --- | ---: | ---: |
| person086 | yes | .013425660444444435 | 0 |
| car115 | yes | .22753122844444434 | 0 |
| uav0000245_00001_s | yes | .08745783466666657 | 31.954719999999725 |
| Other eight | no | 0 | 0 |

There were **2 fresh off-target processed outputs** in sequence245. SOT annotates
one target: off-target overlap is not proven wrong-person identity. Ground-truth
boxes are piecewise constant between frame releases in the time-integrated
diagnostic. No simulated integration is presented as actual wire output. Early
release-slot-only scores are retained, final scorer additionally integrates
exact publication/expiry boundaries to avoid phase aliasing. All 11 failures and
selection errors retained. The 024 target overlapped a raw detection in 59/60
processed frames but never selected; tiny 092 targets had zero raw hits. Thus
acquisition/identity and detector scale are distinct issues.

### Paired original-pixel DET test

Same 64 evenly spaced filenames/image hashes, controlled YOLO11s HEF and actual
board probe. 49 originals at1360x765, 12 at960x540, 3 at1920x1080. Native condition
preserves original RGB pixels in padded1920x1080; eight640-square crops plus wide
view, versus current five-pass720p layout. **Not 4K capture or equal cost.**
IoU>=.5, confidence>=.15; same original-height buckets and supported class groups:

| Geometry | Person matched /1557 | Vehicle matched /1939 | FP /64 images | Median sum of region inference waits ms |
| --- | ---: | ---: | ---: | ---: |
| 720p five-pass | 442 (28.39%) | 1161 (59.88%) | 825 (12.891/image) | 128.53094 |
| Original-pixel nine-pass | 489 (31.41%) | 1186 (61.17%) | 1038 (16.219/image) | 222.39440000000002 |

At confidence .5 person recall was .1118 vs .1201, vehicle .4435 vs .4440.
Person original16–32px recall at .15: .2000 vs .2383; at .5: .0407 vs .0321.
Full original-pixel padded wide view alone performed worse; not an upscale trick.
Wait sums exclude DSP resizing, transfer, tracking and exposure. More pixels
help some cases, but all-grid processing already exceeds the200ms control-age
budget before other work. No live profile changed based on this test.

Validation: 40 simulation tests; 8 native-camera tests; 24 follow tests; 7 bridge
tests; 43 reference/scoring pytest tests plus 7 ONNX conversion/NMS unittests in
the existing DFC venv. Initial broad pytest collection failed due environment
module paths/missing ONNX Runtime in system Python; rerun with explicit paths
and existing venv, no packages installed. JS/shell syntax and whitespace checked.

Structural review: reuse one tracker, one simulator runner, existing frontend
and board ROS rootfs. Add bounded source adapter, diagnostic framing, evidence
scorers; no second perception service or dependencies. Red-team: many forwarded
packets/simple simulated scenes can conceal poor aerial acquisition and unsafe
identity changes; the expanded sweep exposes exactly that. Previously tuned
validation is not held-out generalization. No autonomous-flight gate ticked.

Final recovery check exposed a separate lifecycle bug: the native desk process
was absent although earlier launcher return codes were zero. Its log said
`insufficient headroom for second detector`; MemAvailable1414204KiB minus
CmaFree1220316KiB =193888KiB, below the unchanged192MiB reserve. The SOT runs
after245 recorded `was_running:false`; both DET runs attempted but did not prove
restoration. Inference evidence is retained, restoration fields are **not**
retrospectively declared valid. This also means final rendered SIL started with
the desk already absent; it did not demonstrate its own automatic desk restore.

Moved the exact11 campaign staging directories (107MiB) from RAM-backed `/tmp`
to `/opt/garuda-sim/replay-staging-20260913/`, recoverable, no files deleted.
MemAvailable1516756KiB minus CmaFree1220316KiB =296440KiB after move. Added
advancing-native-snapshot readiness to the lifecycle command (bounded20s;
1000ms viewer readiness age is NOT the200ms control permit), persistent-disk
causal staging and propagated DET restore failure. Two readiness unit tests
cover duplicate, changed producer, missing/stale/NaN snapshots. Actual unchanged
camera restarted, stream `cafb88da-cfe3-4b61-a8d3-d972fc460585`, sequence3,
age207.23728001117706ms at readiness. No memory guard weakening, reboot, package
change or global cache dropping. Follow-up60-frame lifecycle smoke retained.
That smoke processed15/60 frames and completed verified restoration with unchanged
profile, stream `cc55d94f-dde6-4d53-aa6c-0ebc4a2707a9`, sequence3,
age248.48015999794006ms. It validates restart, not an accuracy improvement or
control eligibility at that age. The previous camera log is not overwritten
into a success claim; the failure and correction are documented above.

## 2026-09-13 — movement geometry and ROS/MAVROS dispatch fixes

Full method, deployment, limits and commands: `docs/2026-09-13-movement-fixes.md`.
Evidence: `bench/results/2026-09-13-movement-fix/`; same-date versions entry below.
Native measured box replaces Kalman-corrected geometry on observed tracks only;
prediction remains association/coasting-only. Identity gates unchanged, candidate
distances exposed. Immediate board request evaluation resets the 50ms watchdog
without renewing leases. Relay TCP_NODELAY, bounded missing-metadata wait
(16 packets, 10ms), and final deadline recheck immediately before simulator write.

Baseline long physical interactive log, streamed with `control_path_report.py`:
3,717 follow ticks, 3,208 PC HOLD, 54 outside-image target boxes, 172 forwarded/
139 rejected motion. One allowed event was logged after its deadline before the
old write path: this exposed the final-check/logging ordering bug. First request
to publication report median37.3110925ms, p9547.647676ms (12,242 requests).
Capture-age median317.983947ms, p95436.125169ms includes long lost/absent periods;
not a controlled user-motion-only baseline. Full original log retained externally.

Two actual Hailo + board ROS/MAVROS + owned PX4/Gazebo trials, 40s follow scenarios:
first596 inference frames, 341/8 motion forwarded/rejected; final588 frames,334/4.
Both zero expired motion at dispatch check; injected perception pause held31/31
evaluated ticks, recovered, landed/disarmed. Max follow displacement8.291314397m
and8.066426473m. First trial's seven unknown-publication packets preceded matching
metadata by0.614024–3.948138ms, motivating the bounded cross-channel wait. Final
rejections were2 PC-HOLD and2 unknown/consumed bindings; no bypass of those checks.
Final first-request report median6.233834ms, p9517.616438ms (988 requests).
This is NOT exposure-to-command latency; watchdog republications are excluded
from the first-reply metric. Raw request_to_publish_ms is tick-entry evaluation
delay and excludes following ROS/wire work. Final box measured/filter coordinate
delta median3.652065715px,p9516.073440058px across404 observed boxes; zero selected
follow boxes outside image. Different scenes/load mean no causal speed/accuracy
improvement percentage is claimed.

Validation:7 native CTest targets,46 tracking Python tests including recorded
H15L person/stall fixture,24 follow,7 bridge,45 simulator,8 native-camera tests;
exact SDK ARM build, JS syntax, Python compilation and whitespace passed. Added
delayed-dispatch and metadata-late/missing/expired/HOLD/duplicate/overflow tests.
Both real SIL verifiers passed. No new physical-person movement test: final live
console disarmed/HOLD, board ROS topic advancing, no person detected/selected.

Structural review: existing tracker/authority/runner/local GUI reused; one scalar
streaming report, no dependencies or second service. Sites workflow kept GUI local.
Red-team: simple rendered motion is not real-camera/crowd/aerial accuracy; measured
boxes may jitter or be partial, identity match distances are not probabilities.
Strict200ms supervisory budget and wrong-target HOLD remain. No real-flight gate
ticked. Long-term log-size pruning remains separate; no original evidence deleted.

## 2026-09-13 — frozen aerial rerun after movement fixes; console redesign

Report: docs/2026-09-13-dataset-rerun-and-console.md.
Evidence: bench/results/2026-09-13-dataset-rerun/; matching versions entry.
Used existing follow_campaign.py (fullview, same11 clips, first240 frames or EOF),
run_visdrone_det.py (same64 reduced/original-pixel images), and recorded car
run_grand_demo.sh replay (same25s, initial point661,396). No model training,
threshold tuning, source changes or real-FC I/O.

SOT: acquisition3/11 unchanged; processed724/2567 vs723/2567. Fresh on-target
outputs99 vs98; off-target1 vs2. Time-weighted eligible on-target3703.43112ms vs
3694.66564ms over120100ms, about3.08% in both runs. Eligible off-target32.11264ms
vs31.95472ms: fewer off-target output frames do NOT establish a safety improvement.
Selected086,115,245 unchanged. One extra processed frame in0317_00000. Source,
manifest, trial and profile hashes checked against baseline. Sequence024 raw
target overlap59/60 but never acquired: source16 confirmed track startsx643.11,
fixed clickx617.62, while other raw boxes are not confirmed selectable tracks.
This is an acquisition/association diagnostic, not proof all misses are detector
failures. Initial click/assumed50ms age/source20Hz protocol stayed frozen.

All DET metric dictionaries reproduced exactly. At confidence.15, reduced five
passes: person recall28.39%, vehicle59.88%, false positives12.891/image; original
pixel nine passes:31.41%,61.17%,16.219/image. At.5 person recall11.18%/12.01%.
Summed inference waits129.49716ms/222.89582ms vs128.53094ms/222.3944ms. These
exclude resize/transfer/tracking/exposure; original canvas at most1920x1080, not4K.
HEF, probe, preparation manifests and all image hashes matched. No tracker or
ROS participates in the detector-only comparison.

Recorded-car ROS/PX4 rerun:135 inference frames,25 forwarded/3 rejected motion,
zero expired forwarded at dispatch check, zero translation commands, final
disarmed. Actual heading span0.918517009deg, requested0.645235267deg.376/420
follow ticks HOLD;289 lost. Minimal protocol verification passed; this is NOT
usable robust pursuit and recording does not react to simulated drone motion.
Rejected packets: original lease expiry1, final pre-dispatch expiry1, unknown/
consumed binding1. No safety relaxation to produce motion.

All11 SOT and both DET restorations passed; recorded scenario also restored desk
with advancing frames. Native binary, current profile, models, ISP and board
packages unchanged from69d09c9. Live console restored disarmed, Follow OFF.
Redesign uses existing local Sites workflow: dominant camera, side Gazebo/control
view, compact setup, separate identity/fresh request/sent packet, expandable
diagnostics/zoom/events. One polling stream and conservative frontend ageing of
explicit remaining request lifetime. No added control actions or hosted service.

Validation:45 simulator Python tests; JS state assertions/syntax; static HTML ID
and asset references; local HTML/JS/status HTTP checks. No browser visual QA.
Structural review: existing app/harness/controller reused; separate frontend JS
instead of inline dynamic panel construction, hashes added to run snapshots.
Red-team: frozen but previously tuned data is not held-out validation; counts
hide timing and acquisition failures; old packets are not current execution.
No robustness, aerial accuracy or physical-flight gate ticked.

## 2026-09-13 17:40 — tracker: duplicate boxes and neighbour ambiguity broke confirmation (VisDrone-SOT 024 click); fixed, regression-checked offline

**Diagnosis from retained artefacts only** (no board time; the owner's demo holds the NPU).
`bench/results/2026-09-13-dataset-rerun/sot/uav0000024_00000_s-fullview/outputs.jsonl` + the
prepared NV12 source, replayed through the current tracking library with histograms recomputed
exactly as the node does (`bench/results/2026-09-13-tracker-duplicates/probe/`): the
reproduction matches the recorded run frame for frame (same confirmed ids, same refusal).
Target detected at ≥ 0.5 on every processed frame 0–16 (conf 0.54–0.64); click at source 16
inside the truth box; **only the neighbour (track 1, 35 px to the right) was confirmed**. The
target's track 3 lost its streak at frame 4 (blocked by an unconfirmed neighbour's two
near-equal candidates), was flagged ambiguous at frames 12/20/24 (two boxes on itself,
IoU 0.5–0.7; HEF NMS is 0.70 per `hailortcli parse-hef`), and confirmed at **frame 36**.
Duplicate pairs on the target over 60 processed frames: 27, **26 with histogram distance
> 0.1** (median 0.145) — the old "different appearance" escape of the near-identical filter
would have kept every one of them. Across the eleven frozen clips only 024 fails for this
reason; 029/053/054/092×2/317×2 have no detection ≥ 0.5 on the target (detector), 086/115/245
were already accepted.

**Fix** (`services/garuda-tracking/src/tracker.cpp`): input NMS at IoU ≥ 0.5 same class,
escape only above the association gate (0.55); a row-ambiguous track no longer blocks its
candidates for other tracks. Tests added: `duplicate boxes confirm`, `neighbour ambiguity`
(both failed before the change). Gate: 7/7 ctest; Python 46 tracking (1 skipped, adapter
staging absent) + 24 follow + 17 VisDrone tools; full build script 7 ctest + 76 Python +
ARM cross build → `hailo-export/tracker-fix-20260913/h15l/garuda-fresh-tracking`
sha256 `d150568d…` (built, **not staged**).

**Regression, fixed vs HEAD (`ac5b6022…` replay = the movement-fix build):**
- MOT17-02 / MOT17-09 target-only drops, crowd flag on: lock state, track ids and boxes
  **identical on every frame** (0 differences of 600 / 525). The recorded 2026-09-12 scores
  differ from HEAD by 6 / 1 "unmatched" verdicts (correct-while-control-valid 399→394,
  223→222) — that shift belongs to the measured-box change of 69d09c9, not to this fix.
- VisDrone-MOT 14-case sweep: aggregate and every per-case number identical
  (`mot-sweep/sweep-targetdrop-fixed.json` vs `../2026-09-12-visdrone-mot/sweep-targetdrop.json`).
- Eleven-clip offline click check (`probe/eleven-clips-click.txt`): 024 confirmed at frame 8
  instead of 36 and the click reaches the identity owner (the probe has no OSNet; in the
  recorded run the target's box was rank 2 of the 6 embedded crops, so on the board it carried
  a descriptor); 086 unchanged (owner path, frame 8); 115/245 click OK at the same frame;
  the seven detector-limited clips unchanged.

**SOT replays with real OSNet descriptors, HEAD (`ac5b6022…`) vs fixed, identical configs
(`sot/{head,fixed}-*.json`; identity = `learned_person_identity`, margin04 = identity +
`identity_ambiguity_margin` 0.04 = the shipped follow profile; click accepted under identity;
rate 30; `embeddings-full`).** Identity on-target rate / control-valid frames / off-target
control-valid frames:

| Seq / flavour | Click frame HEAD → fixed | margin04 (shipped) HEAD → fixed | identity (margin 0.08) HEAD → fixed | default (histograms only) HEAD → fixed |
|---|---|---|---|---|
| 024 single | 39 → 39 | 0.238 / 387 / 44 → **0.290 / 442 / 25** | 0.081 / 145 / 28 → 0.032 / 47 / 1 | 0.331 / 715 / 300 → 0.111 / 635 / **497** |
| 024 five | 195 → **30** | 0.014 / 18 / 0 → 0.011 / 16 / 0 | 0.008 / 10 / 0 → 0.004 / 5 / 0 | 0.013 / 18 / 2 → 0.623 / 931 / 178 |
| 024 roi | 105 → **15** | 0.002 / 3 / 0 → **0.335 / 499 / 9** | 0.002 / 3 / 0 → **0.264 / 394 / 8** | 0.105 / 202 / 72 → 0.082 / 115 / 12 |
| 086 single | 15 → 15 | 0.242 / 169 / 4 → **0.265 / 185 / 4** | 0.161 / 114 / 4 → 0.176 / 124 / 4 | 0.921 / 437 / 16 → 0.909 / 452 / 12 |
| 086 five | 15 → 15 | 0.031 / 21 / 0 → 0.031 / 21 / 0 | same | 0.966 / 573 / 4 → 0.966 / 581 / 4 |
| 086 roi | 15 → 15 | 0.769 / 535 / 10 → **0.791 / 550 / 10** | 0.678 / 473 / 10 → 0.553 / 388 / 10 | 0.940 / 647 / 25 → 0.939 / 670 / 41 |

Reading (corrected after the review of commit 383b764 — the first wording "equal or better
on every row under the shipped configuration" overstated this): `margin04.json` carries only
`learned_person_identity` + the margin; freshness, max gap, identity memory and the
continuation/re-acquire gaps fall back to library defaults, so this is the identity +
margin-0.04 *library-default* configuration, not the exact shipped profile. Under it, rows that
track at all improve (024 roi 3 → 499 control-valid frames at 9 off-target, 024 single
off-target 44 → 25, 086 roi/single up), 024 five is near zero either way (0.014 → 0.011,
18 → 16 frames), and 024 roi off-target rises 0 → 9 because it now tracks. The click lands
6–7× earlier on 024 five/roi. Live selection on the board remains unverified; the exact-profile
replay follows below.
Costs, recorded: with the histogram-only default config on the look-alike scene (024 single)
the lock now stays on the wrong person longer (off-target 300 → 497: two look-alikes
overlapping at IoU ≥ 0.5 with histogram distance under the gate are merged and the histogram
tracker keeps whichever box survives); with the non-shipped margin 0.08 the crowd ROI row
loses 85 control-valid frames (086 roi 0.678 → 0.553, ambiguous 144 → 202) — in overlap
frames the target's own box can be the merged-away one. **Separately noted:** HEAD's own
024 five/margin04 is 0.014 where the 2026-09-13 00:15 run recorded 0.407 (different click
frame, 195 vs 128, and the measured-box/identity-gap changes since) — not caused by this fix,
worth its own look.

**2026-09-13 18:40 — exact shipped profile, same click frame, and the 0.41 → 0.01 question
(review of 383b764).** Config = the `tracking` section of `perception-follow.json` verbatim
(`sot-exact/exact-profile.json`: freshness 500, max gap 500, identity memory 30 s,
continuation/re-acquire gaps 500/500, margin 0.04), click accepted under that config, real
OSNet `embeddings-full`, rate 30. HEAD (`ac5b6022…`) vs fixed (`60e9d014…`); identity
on-target rate / control-valid frames / off-target control-valid frames:

| Seq / flavour | Click frame | HEAD | fixed, same click frame | fixed, its own first accepted click |
|---|---|---|---|---|
| 024 single | 39 | 0.335 / 521 / 38 | **0.379 / 580 / 35** | 0.373 / 555 / 11 (click 21) |
| 024 five | 195 | 0.020 / 42 / 16 | **0.045 / 60 / 2** | 0.050 / 76 / 4 (click 30) |
| 024 roi | 60 | 0.397 / 631 / 68 | **0.428 / 640 / 33** | 0.307 / 455 / 5 (click 15) |
| 086 single | 15 | 0.297 / 209 / 6 | 0.310 / 218 / 6 | same |
| 086 five | 15 | 0.303 / 207 / 0 | 0.303 / 207 / 0 | same |
| 086 roi | 15 | 0.877 / 609 / 10 | 0.878 / 610 / 10 | same |

With the click frame held equal, every 024 row improves on both retention and precision and
086 is unchanged (`sot-exact/`). The fixed tracker also accepts the click earlier (21 / 30 / 15
vs 39 / 195 / 60); the earlier click changes the trajectory and on the roi flavour trades
retention for precision (455 frames at 5 off-target vs 640 at 33). Rows where the click frame
differs are not like-for-like and are shown only for completeness.

**0.41 → 0.01 on 024 five/margin04 is not a tracker regression.** The 2026-09-12 23:56 native
tracker (`2d97e744…`, the binary behind the 00:15 recorded 0.407) re-run under the identical
identity/margin04 configs, descriptors and click protocol gives click frame 195 and 0.014 / 18 /
0 — the same as HEAD (`sot-old/`). The recorded 128 came from the very first conversion of that
sequence (`replay/five/conversion-summary.json`: `lock_after 128`, no embeddings, click accepted
by the histogram tracker); every later summary (identity, identity-fix, margin) reused that
conversion and its click, while a fresh run derives the first click the identity owner accepts
(195). Same tracker, click 128 → 0.407; click 195 → 0.014: the identity path on this clip is
that sensitive to where the selection lands. The midday changes and this fix are both cleared.

## 2026-09-14 — aerial detector fine-tune on the follow stack: schedule window, ROI-merge cap, phase-2 unified model

Setup: Hailo-15L SBC (HailoRT 5.3.0, `versions.md` 2026-09-02), causal replay on the board with
the real DSP / HEF / OSNet / tracker (`hosts/hailo15l/causal_replay.cpp`), the eleven frozen
VisDrone-SOT clips, deterministic every-5th-source-frame schedule (250 ms cadence, identical
frame sets for every model), 240 frames, click at frame 15 retried on any refusal within 1 s,
source-age assumption 50 ms. Fine-tuning on this PC (RTX 3060 6 GB, ultralytics 8.4.115, torch
2.9.1+cu128); HEF compile with DFC 5.3.0 under the identical recipe as the deployed controlled
HEF (`build_controlled_yolo11.py`, PTQ level 2, 1,024 aerial calibration images). Full method
and the DET / desk numbers: `bench/results/2026-09-13-aerial-detector/README.md` (§1–6); one
JSON per campaign in its `deterministic/`. "wide" = follow profile with low floor 0.25, 512
detections, 128 tracks. Columns: acquired clips / control-valid frames on the annotated target /
off it / on-target frames whose age was inside the 200 ms control budget.

### Follow schedule at the aerial cadence (adaptive mode: five tiles while searching, single tile + ROI once locked)

| HEF, profile | local gap / corner refresh (ms) | replay binary | acquired | on | off | u200 |
|---|---|---|---|---|---|---|
| controlled, `perception-follow.json` (128 cap) | 500 / 800 (defaults) | `32d2e5b0…` | 4/11 | 91 | 2 | 58 |
| controlled, same | 1500 / 2000 | `32d2e5b0…` | 4/11 | 91 | 2 | 68 |
| controlled, same | 1500 / 2000 | `570a82dc…` (merge fix) | 4/11 | 91 | 2 | 68 |
| aerial-only e7, wide | 500 / 800 | `32d2e5b0…` | 4/11 | 82 | 1 | 30 |
| aerial-only e7, wide | 1500 / 800 | `32d2e5b0…` | 4/11 | 82 | 1 | 38 |
| mixed e11, wide | 500 / 800 | `32d2e5b0…` | 6/11 | 111 | 2 | 39 |
| mixed e11, wide | 1500 / 800 | `32d2e5b0…` | 6/11 | 109 | 2 | 51 |
| mixed e11, wide | 1500 / 2000 | `32d2e5b0…` (ROI merge silently off at 512, below) | 6/11 | 115 | 1 | 69 |
| **mixed e11, wide** | **1500 / 2000** | **`570a82dc…` (merge fix)** | **6/11** | **116** | **1** | **58** |

- The handover window (`follow_local_gap_ms`) was the reason the fine-tuned model never
  reached the cheap single-tile + ROI state: on 115 the ROI verified the target on 11 of 12
  passes but two passes never fell inside 500 ms at this cadence. At 1500 the schedule hands
  over (115: 0 → 12 frames inside the budget) and the corner refresh at 2000 instead of 800
  stops re-opening the tiles every fourth frame (086: 11 → 22 inside the budget, merge off).
- The same schedule also helps the controlled HEF in this replay (58 → 68 inside the budget)
  without changing any other number; the desk profile keeps the defaults until measured live.
- **ROI merge cap.** `RoiAssist::merge` refused any detection cap above 256 while the tracker
  accepts 512, so every "wide" run above this line had the ROI path as a schedule signal only:
  on 115 none of the 22 ROI frames' local boxes reached the tracker, against 264 merged in the
  128-cap controlled run (`outputs.jsonl`, local boxes matched verbatim in the tracker input).
  Fixed in `0838a32`; with the merge working the mixed model keeps its acquisitions and
  on-target frames and gives back 11 frames of freshness (086 22 → 15, 115 14 → 10 inside
  200 ms), because the merged crops add a few milliseconds right at the budget edge. The
  controlled run on the fixed binary is identical in every number.
- Against the controlled HEF under its own defaults (the deployed configuration), the mixed
  model with the aerial schedule and the fixed binary acquires 6 clips instead of 4, holds 116
  on-target frames instead of 91, 1 off-target instead of 2, and keeps the same 58 frames
  inside the 200 ms budget.

**Strongest argument these numbers overstate the result.** The 1500/2000 window was chosen on
the same eleven clips it is reported on (in-sample), the click-retry protocol is not the frozen
one-click protocol of the 2026-09-13 morning campaigns, the six acquisitions are the controlled
model's four plus 029 and 054 (one and three on-target frames each), and the net gain of 25
on-target frames rests on one crowd clip: 086 adds 31 while 024 gives back 10 (identity
ambiguity in a walking group, decisions.md 2026-09-14 §5). What survives that argument:
the same schedule and protocol were applied to the controlled HEF (rows 2–3), the frame sets are
identical by construction, and the merge-cap fix is a correctness fix proven per frame.

### Phase 2 — unified model (mixed checkpoint re-balanced for the desk phone)

Training: 6 more epochs from the mixed e11 checkpoint in 0.878 h on 12,820 images (VisDrone-DET
train 6,471 + COCO val2017 4,952 + the 214 COCO phone images repeated five more times + 109
desk frames pseudo-labelled by the controlled HEF, repeated three times). VisDrone-val mAP50
0.383 → 0.410 (mAP50-95 0.215 → 0.237) across epochs 1–6, above the e11 checkpoint's 0.393.
HEF `fed876d8…` compiled 01:01–01:19 under the same recipe (`compile-0101/`, aerial calibration).

| Measure | controlled (deployed desk) | mixed e11 `b70e5a11…` | phase 2 `fed876d8…` |
|---|---|---|---|
| DET 548, five tiles @0.5: person / all / FP per image | 0.117 / 0.229 / 1.14 | 0.346 / 0.483 / 3.5 | **0.364 / 0.512** / 3.6 |
| DET person 16–32 px / 32–64 px @0.5 | 0.032 / 0.274 | 0.278 / 0.599 | **0.305 / 0.617** |
| DET single view @0.5: person / all | 0.042 / 0.143 | 0.215 / 0.360 | **0.226 / 0.386** |
| desk 433 frames: person @0.5 (mean conf) | 433 (0.95) | 433 (0.92) | 433 (0.945) |
| desk: phone @0.5 / @0.15 | **200 / 322** | 14 / 72 | 129 / 188 |
| eleven clips, single view: acquired / on / off / u200 | 3 / 74 / 2 / 74 | **6 / 129 / 1 / 129** | 6 / 92 / 2 / 92 |
| eleven clips, adaptive 1500/2000 (merge-fixed binary) | 4 / 91 / 2 / 58 (defaults) | **6 / 116 / 1 / 58** | 6 / 121 / **8** / 72 |

Phase 2 is the better detector on both scenes but the worse follow model on the eleven clips:
single view holds 086 for 8 frames against 35 (`identity_evidence_incomplete` on 32 of 48
frames vs 7 — ~100 people per frame, six descriptors per frame, and the extra boxes it finds
leave the target's neighbourhood undescribed more often), and adaptive mode puts control on a
bystander for 6 frames on 024 where the mixed model never does. Off-target control is the
failure the identity design exists to prevent, so it outweighs the 5 extra on-target frames.

### Deployed 01:34 — aerial profile on the board, desk profile unchanged

`stage_fresh_tracking.sh` (`GARUDA_FRESH_BUILD=…/build-merge`, `GARUDA_FRESH_AERIAL_HEF` =
mixed e11, `GARUDA_FRESH_AERIAL_HEF_SHA=b70e5a11…`): node `4666ffe8…` (ROI-merge cap fix,
schedule keys from the profile; previous `d150568d…` kept in
`/opt/garuda-fresh/backups/aerial-20260914/`), `perception-aerial.json`, aerial HEF with its
`.sha256` beside it, controlled HEF re-verified `aec84f00…`. Verification run 01:36–01:37
(`hailo-export/aerial-improve-20260913/verify-aerial.log`): `start-aerial` → camera ready,
`current.json` = aerial profile, sequence 92 → 139 over 6 s, rejected frames 0, five detector
passes per frame at 117–121 ms, ROI detector reporting the aerial HEF path; then `start-follow`
→ sequence 80 → 120, rejected 0, ROI detector on the controlled path, 120–183 person crops
described. The desk was empty at that hour (0–2 raw detections per frame with the aerial HEF,
11–14 with the controlled one, no confirmed track under either), so **no click on a person was
verified live**; that remains the owner's check, as after every node redeploy. Rollback: stop,
copy the backup over `/opt/garuda-fresh/garuda-fresh-tracking`, `start-follow`.

Board disk after staging: 401 MB free of 6.7 GB (the two earlier candidate HEFs remain under
`/opt/garuda-sim/models/`; `yolov11s_phase2_phone_…` and `…e7…` can go once the owner has
read this entry).

### 12:28 — oracle native-crop probe on the 317 pair (owner: "run the oracle crop test on 317")

Same probe and board as the DET runs; the first 240 frames of each clip at the original
1904×1070 pixels with a 640 and a 320 window centred on the annotated box, against the same
frames of the 720p preparation with its full view and oracle 640 ROI (today's paths).
`prepare_native_crop.py`, `score_native_crop.py`; eight probe passes, node stopped and restored
each time (33 s wall per pass). Best box of any tracked class at IoU ≥ 0.5, recall at the 0.5
birth floor (`bench/results/2026-09-13-aerial-detector/oracle-crop/`, README §10 for the table):

- 317a (rider, 16×31 px): mixed HEF 0.704 on today's 720p ROI vs 0.517 on the native 640 window
  and 0.146 on the 2× native window — **no gain**; at native scale the rider is labelled
  `motorcycle` on 190 of 240 frames, and 3.4–4.5 boxes overlap it per frame in every variant.
  The campaigns refused its click with "no confirmed live object" (41–45 of 45 attempts), so the
  blocker is a rider that never becomes one confirmed track, not resolution.
- 317b (van, 64 → 33 px): mixed 0.058 → 0.154 (native 640) → 0.367 (native 320, 2×); controlled
  0.242 → 0.296 (native 640). The controlled HEF beats the fine-tune on this van at 720p.
- Native pixels on this source are barely sharper than the 720p copy (target-patch Laplacian
  variance 1220 vs 1106), so the gains come from apparent size, not detail: a floor for the
  IMX678 path, where the same window holds three times the pixels.

## 2026-09-15 — native-pixel target crop on the IMX678: built, measured on the desk, not shipped

Node `124cc94f…` (branch tip), profiles `perception-follow-native{,-compare}.json`, third
frontend stream 3840×2160 (spike 2026-09-14 13:00: accepted beside 640 + 720p, ~50 MB CMA,
frames accepted). Recorder `bench/hailo_reference/native_roi_capture.py`, scorer
`score_native_roi_capture.py`; evidence and the per-band tables in
`bench/results/2026-09-15-native-crop/`. Paired, same-exposure comparison of the detector's
confidence on the locked box for the native crop and today's 720p crop (the compare profile
runs the path not chosen as well). Owner at the desk, then a phone as the small-target stand-in.

- Native stream paired on every frame of every session (0 missing); native ROI 38 ms per frame
  vs 27 ms paired; with both paths running a locked frame took 7 passes and aged 300–360 ms.
- Person (session 2, 1,339 locked frames): the owner never got under 36 % of the frame height,
  the crop engaged on 3 frames at 36 % and scored 0.43 vs 0.57 on a 1960 px window (3× shrink).
- Phone at 1:1 sensor pixels (session 5, planner context 2.5, 68 pairs): 30–40 px 0.735 vs
  0.693 (13/14 vs 14/14 at the 0.5 floor); 40–50 px 0.29 vs 0.38; 50–60 px 0.40 vs 0.64; 60–70 px
  0.46 vs 0.74. The 1:1 crop put the phone at 20–40 % of the input and the COCO detector scored
  it lower than at the ~14 % the paired 640 floor gives — scale, not pixels.
- Phone with the two rules now in the profile (session 6, context 7 → target ≈ 14 % of the crop,
  `native_max_window_px` 1280 → native only under a 2× shrink; 58 pairs): 30–40 px **0.77 vs
  0.43 (6/6 vs 3/6, native wins 5 of 6)**; 40–50 px 0.25 vs 0.39; 50–60 px 0.20 vs 0.26; 60–70 px
  0.50 vs 0.48; 80–100 px 0.86 vs 0.86 with the paired path correctly chosen. Both paths sat at
  the detector's floor at 40–60 px and the lock was lost for most of both phone sessions
  (1,506 of 1,644 rows in session 5, 558 of 1,244 in session 6).

Verdict: no measurable desk gain outside a six-frame band; the native path is never worse
where the gate lets it run; the regime it was built for (a person under ~8 % of the frame
height) is not reachable at this desk. Desk profile unchanged (paired copy); the native
profiles stay as bench profiles for an outdoor or drone-mounted session. The strongest
argument against even the six-frame gain: the phone was coasting or being re-acquired for most
of the far minute, so the "target box" both paths were scored against may itself have drifted.

## 2026-09-15 — aerial profile wired into the demo console; replay-mode transport measured

`run_grand_demo.sh replay|gazebo … --aerial` now runs the staged aerial profile (VisDrone
fine-tune `b70e5a11…`, wide caps, 1500/2000 schedule, adaptive) on the merge-fixed stream
binary `9242b4b8…` (`hosts/hailo15l/stage_sim_stream.sh`), and the console names the model,
schedule and per-frame crop state. Verified on VisDrone-SOT 086 through the console (click at
669,421, auto-demo 60 s; `bench/results/2026-09-15-demo-aerial/`, `console_capture.py`):

| Run | Profile, click | Board frames | control-valid | board age median / <200 ms | receiver age median / <200 ms |
|---|---|---|---|---|---|
| fullview (controlled), one click | 190 | 5 | 102 / 190 | 296 / 11 |
| aerial, one click | 109 | 0 (click refused: descriptor not yet computed) | 255 / 0 | 436 / 0 |
| aerial, click retried ≤ 1.5 s (`--select-retry-s`) | 121 | **59** | 248 / 50 | 399 / 0 |

The aerial profile holds the crowd-clip target in the console as it did offline (59 vs 5
control-valid frames), and the schedule hands over (50 frames at 2 passes). Neither profile
moved the simulated drone: the follow authority's 200 ms receiver-age gate never passed, because
replay mode adds 150–250 ms of PC transport per frame on top of the board's own age. That is
the "bounded heading response, not closed loop" limitation of replay mode with numbers; onboard
ingress (CLAUDE.md §7 open item) is where a follow command would become possible. Board
cleanup: 294 campaign temp directories and two unused HEFs removed, root 95 % → 47 %.

## 2026-09-17 — 1280×736 single-pass detector: recall doubled in one cheap pass, follow not improved

Same fine-tuned weights (mixed e11), same DFC recipe with `--input-size 1280 736`, HEF
`42f5eaf9…`; board detector / DET probe / scorers now take the network size from the HEF and
the preparation (`af785fa`, `99247a6`). Evidence `bench/results/2026-09-17-detector-1280/`.

- **DET 548, single view at the 0.5 floor:** person 0.378 (16–32 px 0.334, <16 px 0.087), all
  classes 0.510 — above the 640 model's five tiles (0.346 / 0.278 / 0.054 / 0.483) in one pass:
  57 ms on the board vs 131 ms for five 640 passes (medians over 514 frames); searching-state
  frame age 196 vs 267 ms.
- **Eleven clips, single view:** 3/11 acquired, 79 on-target, 1 off (640 single view 6/11, 129,
  1; 640 adaptive 6/11, 116, 1). Per clip the loss is in the tracker/identity: 024 a confident
  neighbour keeps both tracks tentative (margin off → confirms and locks the neighbour, 2
  off-target); 029 the rider flips `person`/`motorcycle` frame to frame (IoU 0 on 9 of 16
  frames); 054 the clicked person's descriptor is not there within the retry window in a
  ~100-person crowd; 086 `identity_evidence_incomplete` on 33 of 48 frames (7 at 640) with 80
  people per frame above the floor and one track-id change.
- **Tracker changes:** a contained-duplicate merge (intersection-over-min ≥ 0.7, comparable
  size) changed nothing at 1280 and cost one frame at 640 (MOT sweep identical) — reverted; an
  overlap-first descriptor priority (node and replay) left 640 single view identical, moved 640
  adaptive 116 → 117 on-target and 58 → 60 inside the budget — kept.
- Board `hailortcli benchmark` could not run (the desk node holds the device; a stray DET probe
  had to be killed once); the in-situ per-frame timing above is the measurement.

Nothing deployed. Also today: an interactive console session had filled the disk (tick log at
80 KB per tick, 128 GB) — logs removed, writer made compact (`af785fa`).

## 2026-09-18 — drone-view re-identification descriptor + evidence reach: 129 → 161 on-target, zero wrong identity

OSNet x1.0 fine-tuned on VisDrone-MOT crops (RTX 3060, 30 epochs, 33–60 s each), compiled with
the zoo's quantisation recipe (`build_osnet_reid.py`, DFC 5.3.0, 1,024 calibration crops),
measured on the Hailo-15L through the unchanged causal-replay harness. Evidence, method,
per-checkpoint and per-gate tables: `bench/results/2026-09-18-reid-visdrone/`. Rules and
deployment: decisions.md 2026-09-18. Board: HailoRT 5.3.0, replay binaries `513f1ce6`
(shipped rules, reproduces the recorded control exactly), `2441ac06` (reach only), `8e4006a9`
(reach + focus fallback + `identity_unresolved` diagnostic).

- **Holdout identities (76, one flight):** rank-1 0.960 → 0.979, false accepts inside the 0.25
  gate 8.3 % → 0.3 %, same-identity median distance 0.13 → 0.19 (epoch 30).
- **Owner-rule replay, six crowded SOT clips, 264 frames, PyTorch weights:** verified frames at
  gate 0.25 / 0.30 / 0.35: deployed 153 / 166 / 189, epoch 11 180 / 208 / 225, epoch 30
  199 / 216 / 224.
- **Eleven clips, single view (acquired / on-target / off / wrong identity):** deployed
  descriptor 6/11 / 129 / 1 / 0; epoch 30 alone at 0.30 6/11 / 141 / 2 / 0 (054 7 → 19, 086
  holds 35); epoch 30 + reach 0.5 + focus 6/11 / **161** / 2 / **0** (054 34, 086 40); epoch 11
  + reach + focus 156. Reach 2, 1 and 0.5 identical in single view.
- **Eleven clips, adaptive:** deployed 6/11 / 117 / 1 / 0; epoch 30 alone 82 (086 3: the crowd
  trap); epoch 30 + reach + focus 143 (r2, r1), 142 / 142 / 142 (r0.5, three runs); epoch 11
  + reach + focus 140 / 139 (r2, r1), 155 / 140 / 140 (r0.5, three runs: 054 flips between 15
  and 31 with the tile schedule's timing); the deployed descriptor + reach + focus 140. Every
  "wrong" frame in adaptive runs is 245's car target on the geometric lock (timing-dependent
  tile schedule), not the learned identity.
- **Mechanism (rows):** on 086 the candidate's bystander sits at 0.13–0.15 while the target is
  at 0.02–0.10; at frame 50 they come within the 0.04 margin (0.099 vs 0.132) → ambiguous →
  every later frame `identity_evidence_incomplete` with 40–58 people and 6 descriptors/frame.
  With reach + focus the same clip recovers at frame 55. `identity_unresolved` at reach 2 was
  6–27 people inside the reach against a budget of 6; at reach 0.5 it is 0–3 while tracking.
- **Reach alone on the deployed descriptor:** 129 / 117, identical to the control — the target
  itself went undescribed after a release; the focus fallback is what makes the reach usable
  (deployed descriptor + both: 134 / 140).
- **Lost to the harness, since fixed:** two clips to the control script's 2 s stop budget (now
  10 s); seven campaigns to a full eMMC (381 leftover staging copies of the binary; the replay
  now removes its directory per clip). All reruns in the evidence tables.

Red team: the descriptor was trained on VisDrone-MOT and scored on VisDrone-SOT clips of the
same benchmark (different sequences, one shared flight held out of training); the eleven-clip
protocol has been the yardstick since 2026-09-13 and its control reproduced exactly today; the
gate and the radius were chosen on the same eleven clips they are reported on (a sweep, not a
tune on a held-out set); adaptive-mode numbers vary by a few frames between identical runs
(u200 56–60 on the same control). Nothing here is a live number.

### Deployed 15:05 — aerial profile on the board with the new descriptor, desk profile unchanged

`stage_fresh_tracking.sh` with `GARUDA_FRESH_AERIAL_REID_HEF` (+ sha), node binary
`de92ee52…`; `start-aerial` smoke test: camera ready, frames 240–330 ms old in the tiled
searching state, the new descriptor ran on the desk scene (174 inferences in about a minute,
0 failures, not faulted, 9.5 ms per crop, 4.1 ms per crop cut), no errors; back on
`start-follow`. Demo stream restaged (`8e4006a9…`). Live follow numbers with this descriptor:
`TBD-bench` (no owner session yet).

### 15:40 — live desk session on the aerial profile, and the phone-preserving detector re-measured

Owner at the desk, aerial profile, 415 s logged at 10 Hz (`hailo-export/reid/live/`): lock took at
first click; identity verified on 94 % of frames with a confident detection; re-acquired after two
walk-outs within a second on new track ids; one partial self-detection inside the gate at 0.28 (owner
alone) held off by the margin. 118 lock drops: 73 descriptor past the 0.30 gate for a frame (median
anchor distance 0.17 at desk range against 0.03–0.10 for the zoo weights on the desk profile), 45
aerial-detector confidence under 0.5 on a 270–300 px person (median 0.70, p10 0.45). Owner: arm
stretch loses the lock, phone not detected (18 / 4,202 frames). Board returned to the desk profile.
Phase-2 detector (`fed876d8…`) with epoch 30 + gate 0.30 + reach 0.5: single view 140 on / 2 wrong
(245 car), adaptive 142 / 1 — equal to the deployed aerial detector in adaptive mode, 21 behind in
single view (054 16 vs 34, 024 1 vs 7). Not deployed; owner's call recorded in decisions.md.

### 15:45 — owner's phone on the desk profile, 70 s at 10 Hz (`hailo-export/reid/live/live-desk-phone-*.jsonl`)

Phone 53–86 px (controlled COCO detector, single 640 + ROI assist): detected on every frame for the
first 8 s at 0.73–0.91, lock taken on click and control-valid on 25 of ~45 tracked frames — the rest
`coasting / low_confidence` as the phone's confidence flickered 0.17–0.89 frame to frame. Then no
phone detection at all for 9 s (seconds 9–17; person detected throughout), the geometric re-acquire
window (7 s, no descriptor for a phone) expired at 15 s, the phone reappeared at 18–26 s at 0.44–0.88
and was not re-bound (window closed, no re-click), then no detection again from 27 s. Box speed while
detected: median 63 px/s, p90 153 px/s — the fast passes produced no detections, so their speed is
not in the log. Small fast object detection at the desk is the 2026-09-03 finding again, not a
regression: the aerial work did not touch the desk profile.

### 15:50 — aerial slot swapped to the phone-preserving detector (owner's call); phone on the aerial profile

`stage_fresh_tracking.sh` with `GARUDA_FRESH_AERIAL_HEF` = phase-2 `fed876d8…` (sidecar rewritten),
descriptor slot unchanged. Live, aerial profile, 175 s at 10 Hz (`live/live-aerial-phase2-phone-*`):
phone detected on 389 / 1,319 frames (29 %; continuous at 0.74–0.93 whenever held up, 73–135 px),
lock taken on every click, control-valid 168 of 268 locked frames (62 %; the rest `missing_or_stale`
during the profile's periodic five-tile pass and `low_confidence` dips), three losses each after
the phone left detection for ≥ 7 s (fast move / tilt / out of frame; 7 s geometric window). Desk
profile's own pass (70 s): detected 87 / 445 (19 %, 0.68, 71 px), control-valid 25 / 49 (51 %).
Adaptive clips equal (142), single view 140 vs 161 (`campaigns/phase2-*`). Board left on the
aerial profile at the owner's desk.

### Live review follow-up — measured geometry for phone recovery

Owner authorized a recovery fix after live testing. Telemetry is in
`/tmp/garuda-live-review-prichT/` (temporary, not archived). For the desk baseline use
`desk-comparison.jsonl` through elapsed 149.04 s; later rows include other trials.
Deduplicate by `(stream_id, sequence)`. These are sampled HTTP states, not ground truth.

At elapsed 93.98 s the phone entered `watching_for_return`. Its preceding coasting box
was 6.55 x 0.72 pixels, versus the last control-valid measurement of 29.01 x 37.83.
A fresh phone track was present at 25.67 x 53.84 pixels. Coast expiry saved the predicted
`public_track.box` into `LostMemory`, so recovery checked size against collapsed dimensions.
Another loss at 133.88 s followed an 8.24 x 1.15 pixel prediction. This identifies one
recovery mechanism, not every detection or confidence failure.

Fix: retain the last measured box per state, propagate it only through valid camera
motion, and use it for lost-target memory. Appearance, rival, size, confirmation, and
seven-second recovery gates are unchanged. Learned-person owner rules are unchanged;
other geometric classes also use the corrected reference, so aerial car totals need
re-measurement before any unchanged-benchmark claim.

The shrinking-phone regression fails with the old reference and passes with the fix;
a differently colored return remains rejected. Eight native CTest targets and Python
integration checks passed (hardware adapter test skipped). Live improvement: TBD-bench.

The owner rejected the 15 ms / gain 30 exposure trial as worse. Automatic exposure was
restored and read back at 33.006 ms. The routines were not identical paired inputs.

Deployed node SHA256 `253a2df9f9d8d076624f3e3500d76723118714d7210531588ff68220c64aaaea`.
Desk `current.json` hash remained `ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
Previous binary/config saved in `/opt/garuda-fresh/backups/pre-measured-recovery-20260918/`.
Camera-ready smoke passed, automatic exposure active; stream
`ce117063-241d-4589-a6b3-9bd46c38a683`. The causal replay binary/model slots were not deployed.
Post-fix live telemetry: `/tmp/garuda-live-review-prichT/desk-recovery-fixed.jsonl`.

Owner reports the measured-box build is much better. In the post-fix recording through
elapsed 160 s, stable phone selections automatically rebound to new MOT ids at 60.75 s
(26 to 29), 70.54 s (29 to 31), and 127.60 s (43 to 49). Three selections also reached
recovery-window expiry. These are sampled state transitions, not a paired accuracy score.
At 83-86 s, track 33 repeatedly entered verification then lost its streak on low-confidence
or absent observations: a 250 ms gap budget is shorter than two tiled-frame intervals.

Desk follow profiles now set `reacquire_gap_ms=500`; aerial profiles and the global default
remain unchanged. The 600 ms verification interval, minimum hits, confidence/appearance/
size/rival gates, freshness, and seven-second deadline remain unchanged. A new 200 ms
cadence regression fails recovery at gap 250 and succeeds at gap 500 despite one confidence
dip; wrong appearance, stale output, and gaps exceeding 500 ms remain refused. All eight
native CTest targets and seven profile tests passed. Only the desk follow JSON was deployed;
the binary is unchanged. Backup: `/opt/garuda-fresh/backups/pre-recovery-gap-20260918/`.
Restart smoke passed with stream `e39ec4db-7ceb-4885-b38a-27e303bdd06a`; auto exposure
readback 32.991 ms, gain 7.161. Post-gap live improvement remains TBD-bench.

Read-only ISP inspection: 3DNR enabled, mode 1, exposed strength 127/128; 2DNR disabled;
edge enhancement, WDR and AWB enabled; autofocus unavailable. These are control readbacks,
not proof of temporal smearing or calibrated filter strength. No ISP filter was changed.

Owner authorized a temporal-noise-reduction comparison. Baseline controls:
`isp_3dnr_enable=1`, `isp_3dnr_mode=1`, `isp_3dnr_strength=127`, `isp_3dnr_auto_level=0`,
`isp_ae_enable=1`, exposure 32991 us, gain 7333/1024. Writing strength 64 returned success
but readback remained 127; do not label this a reduced-strength measurement. Instead
disabled `isp_3dnr_enable=0`, verified by readback, leaving AE enabled. This is a temporary
3DNR on/off experiment, not a permanent profile change. Restore with
`v4l2-ctl -d /dev/video0 --set-ctrl=isp_3dnr_enable=1` and verify all baseline controls.
Telemetry: `/tmp/garuda-live-review-prichT/desk-3dnr-off.jsonl`; result TBD-bench.

3DNR-off pass completed: through elapsed 271.57 s there were two phone-selection epochs
(1 and 2), with 17 automatic changes of bound MOT id while retaining the selection epoch
(10 in epoch 1, seven in epoch 2). Both selections eventually reached recovery timeout.
These are automatic rebind events, not independently verified identity matches.
`desk-gap500.jsonl` continued recording during this same pass: its phone epochs overlap
the off file (approximately 152.45 s offset). Do not compare those files as independent
ISP-on/off trials or claim an ISP improvement from them. No matching active-phone on pass
was captured before disabling 3DNR. Owner has not yet supplied a visual-quality verdict.

Restored `isp_3dnr_enable=1` after the pass; readback mode=1, strength=100, AE=1.
Strength differs from the earlier 127 readback, so restoration means re-enabling the
existing mode, not asserting bit-identical ISP state. No fixed-strength calibration is
established. The measured-box fix and 500 ms desk recovery gap remain deployed.

Owner accepts recovery but requests faster tracking during fast phone motion. Through
271.57 s of the off recording, 288 of 716 control-valid sampled frames still used corner
tiles. Across selected-phone states, median capture-to-publication time was 227.76 ms
for tiled frames versus 122.18 ms for locked single-tile frames. This is a descriptive
schedule comparison within one recording, not proof of a tuning improvement.

Desk handover tuning: `follow_local_gap_ms=1500`, `follow_global_period_ms=2000` instead
of implicit 500/800. Full-view inference continues every frame; loss still triggers wider
search; tracker freshness and identity gates are unchanged. Native desk variants and the
desk replay source profile match in the repository; only the ordinary desk profile was
deployed. Eight native CTest targets and seven profile tests passed, including bounded
refresh and immediate searching on loss. Backup:
`/opt/garuda-fresh/backups/pre-phone-schedule-20260918/`. Live speed gain: TBD-bench.
Next telemetry: `/tmp/garuda-live-review-prichT/desk-phone-schedule.jsonl`.

Schedule experiment completed through elapsed 151.33 s (stream
`f8448fc0-3642-4e44-9a0f-8e38462f06af`): 995 unique sampled frames, with
446 in phone selection epoch 1. Five automatic rebinds occurred; the selection
eventually expired. Of 226 control-valid phone frames, 128 used tiles and 98
used the single-tile path. Median capture-to-publication time was 207.3 ms,
p95 270.6 ms, versus 142.5/269.4 ms for valid frames of the earlier 3DNR-off
pass. Motions and ISP settings differ: this is not a controlled regression
comparison and establishes no speed benefit. Rolled back the two experimental
desk schedule overrides and their dedicated tests, restoring implicit 500/800
timing. Retained the measured-box recovery fix and desk reacquire_gap_ms=500.
Board follow profile restored from pre-phone-schedule backup and restarted.

### 2026-09-18 — bounded predictive phone search (live evaluation pending)

Owner authorized the first fast-motion implementation. Desk profiles opt into
`phone_predictive_roi=true` and `phone_short_miss_ms=250`; aerial profiles and
constructor defaults retain prior scheduling. Search-only phone motion comes from
the track velocity and measured recovery box with its observation timestamp.
Projection is limited to 250 ms and 0.15 normalized displacement per axis; the
crop covers the measured position and projected direction, expanding within the
source geometry. Prediction never replaces the published measured observation,
updates its timestamp, or authorizes control. Established phone ROI history may
survive a bounded brief miss; ambiguity, age/uncertainty limits, loss, and the
independent corner-refresh deadline still force global search. Full-view
inference remains on every processed frame. Recovery and ISP settings unchanged.

Live/replay constructors share the same opt-ins. Added per-update entry age,
primary inference, corner wall time, ROI/evidence wall time, total processing,
capture-to-update time, and scheduling reason to live diagnostics. These timings
end before tracker update/publishing and are not glass-to-glass latency.

Validation: eight native CTest targets passed, including 13 search scenarios
(motion direction/reversal, bounded displacement, expired/future/nonfinite
motion, class isolation, first-miss history, deadline/ambiguity/age/uncertainty
refusals, and actual-tracker search-only measurement timestamps). Build script
Python suites passed with the existing unavailable Hailo adapter skipped; exact
SDK ARM node and causal replay builds passed. No new dependency. Patch spans
the shared search contract, host wiring, desk profiles, and regression tests;
no additional tracking engine or unbounded worker/queue was introduced.

Deployed node SHA256
`1e7ab805d47b1ee2d20c942ff2662c81a940d52c0d00fa88dfe93a5a6241f03e`.
Backup binary and desk profiles:
`/opt/garuda-fresh/backups/pre-phone-predictive-20260918/`.
Camera-ready smoke passed, stream `057d8b2d-f6b1-4415-9591-722000feae5c`;
new diagnostics present, recovery gap 500 ms, AE=1 and 3DNR=1 verified.
Only ordinary desk profile/node deployed; replay/native profile deployments
unchanged. Fast-phone accuracy and latency benefit: TBD-bench; synthetic tests
and an unselected camera smoke cannot establish either. Next live telemetry:
`/tmp/garuda-live-review-prichT/desk-phone-predictive.jsonl`.

Owner rejected the live behavior and authorized restoring the recovery-good
version. Through elapsed 156.36 s, deduplicating first HTTP sample per stream/
sequence: 288 control-valid phone frames had median capture-to-update 118.5 ms;
four automatic MOT rebinds across two selection epochs, with the final selection
expiring at 141.16 s. Brief-miss scheduling ran on 37 sampled frames, 18 ending
control-valid. These are telemetry outcomes, not verified identity accuracy or
a controlled improvement comparison. Lower latency on successful frames did
not meet the owner's continuity requirement.

Restored the pre-phone-predictive binary and ordinary desk profile from the
backup above. Removed experimental opt-ins from all four repository desk
profiles so subsequent staging does not silently re-enable them. Experimental
implementation/tests remain in source, disabled by default, for investigation;
they are not in the restored board binary. The measured-box recovery fix and
500 ms recovery gap remain active. No ISP or model changes in this rollback.

### 2026-09-18 — accepted baseline archive and qualification infrastructure

Archived and reverified 11 entries in ignored local directory
`bench/local-baselines/20260918-recovery-good/`, using the accepted node hash
above. Deployed application artifacts only; no BSP backup or exact source-build
provenance claim. Added read-only baseline archive/verify tooling and an offline
exact-source recording integrity gate. Four new qualification tests and eight
existing native camera tests passed. No new dependency or camera profile change.

Existing on-board native-camera ROS observer ran for 10 s with publication
freeze after 5 s. Evidence: `/tmp/garuda-native-observe-20260918.jsonl`.
Final counters: native_received=248, ros_received=124, errors=0. Final source
capture age 5244.977 ms, ineligible; vehicle_io=false, operator_permit=false.
Selected target was already recovery-expired before the freeze: this is NOT
valid-target dropout qualification. No MAVROS launch, mounts, camera restart,
model or ISP writes. Existing rootfs could run the observer despite /proc not
being mounted; initial readiness probe was overly strict, not a runtime blocker.
Hardware/runtime inventory remains the existing 15L/VPSP/HailoRT snapshot in
bench/versions.md; archive includes current kernel/boot and ISP readbacks.

Structural review: reuse existing capture receiver and native ROS ingress;
two additive integrity tools, tests and handoff, no second tracking/control
stack. Strongest counterargument: byte integrity and working ROS transport
do not establish perception accuracy, safe flight, or PC-independent control.
Those gates remain open in docs/2026-09-18-baseline-and-qualification.md.

### 2026-09-18 — drone-footage offline audit, no live changes

At owner's request used existing VisDrone footage rather than asking for new
phone recordings. Hash-verified all eleven prepared NV12 sources and rescored
44 saved board runs against annotations with existing causal/timeline scorers.
All six timeline tests passed. Run provenance/hashes, scoring scope and detailed
results: `bench/results/2026-09-18-reid-visdrone/offline-audit.md`.
On-target processed frames: baseline/candidate full view 129/161, adaptive
117/142. Under 200 ms: full view 129/161, adaptive 56/32. All acquired 6/11 clips;
481 evaluated processed frames per campaign. No fresh board inference or live
baseline qualification claimed. The deterministic stride produces 250 ms gaps
against a 200 ms eligibility budget; this protocol is not real-time continuity
qualification. Existing run binaries/runtime are documented in the September
18 campaign; no hardware/software deployment changed in this rescore.

### 2026-09-20 — completed measured-cadence drone baseline reviewed

All 22 fresh board replay trials launched on September 18 completed: eleven
clips, fullview/adaptive, up to 600 frames, fixed_stride=0. Exact protocol,
binary/model hashes, and per-trial evidence live in
`bench/results/2026-09-18-drone-latest-frame/` (README now marked complete).
Fullview: acquired 5/11, 120 control-valid on-target / 64 off-target, all 120
on-target under 200 ms. Adaptive: acquired 6/11, 161 on-target / 1 off-target,
82 on-target under 200 ms. Evaluated processed counts differ: 1599 and 1000.
Source-wide time-weighted eligible-on-target fractions under the declared
timing/200 ms policy: 1.48% and 0.49%; not live availability measurements.

Fullview car clip 245 contains 63 control-valid outputs with ZERO annotated
target overlap (first index 236, last 515). This is not cutoff-level box jitter;
alternate-object identity still needs visual annotation. Wrong-target geometry
must be investigated before latency-only changes. Fresh selection failures in
086/fullview and 054/adaptive also persist. No mode qualifies robust following.

All per-trial restore return codes are zero and profile_unchanged=true.
Rechecked board live-node SHA256 253a2df9...aaaea and active profile
73cb376e...91db7 against pre-campaign values: exact matches. Node running,
AE=1, 3DNR=1, no causal replay process. Six timeline tests passed. Current
review did not modify the camera or deployment. Runtime/provenance remains
the campaign's 15L kernel/model inventory and bench/versions.md snapshot.

Car245 follow-up: traced last correct ID8 at index224, ambiguous 228/232,
incorrect control-valid same-ID match at236, and incorrect ID141 recovery at272.
True-target detections exist at both wrong matches. The 600 ms observation gap
exceeds profile max_gap_ms=500; code resets the streak without clearing confirmed,
then updates recovery memory from the match. Exact association cost attribution
is unavailable without additional internal diagnostics. Added evaluator
`check_target_continuity.py` and six synthetic tests. The recorded fullview run
correctly fails the gate (exit1, 63 zero-overlap valid outputs), evidence
`/tmp/garuda-car245-regression.json`. This is an output regression gate, not a
tracker fix or an exact core-only replay. Runtime/camera unchanged.

### 2026-09-20 — car gap re-verification candidate, six board trials

Added default-off `tracking.car_gap_reverify`: selected cars with observation
gap > max_gap_ms preserve pre-association recovery memory and require existing
bounded re-verification even when the MOT ID survives. Phone/person paths and
deployment configs unchanged. Red/green gap test; 8 native CTests pass; Python
tracking 54 (1 skipped), follow 24, bridge 7 and continuity evaluator 6 pass.
Cross-build succeeded. No new dependencies or second tracking stack.

Evidence/protocol: `bench/results/2026-09-20-car-gap-reverify/README.md` and six
per-trial artifacts. Hailo-15L runtime remains bench/versions.md's VPSP 1.12.0 /
HailoRT 5.3.0, Linux 5.15.32-yocto-standard-g1de0438be5ae. Same candidate replay
binary SHA256 b98a7872bd8a91adca9fbd143f207eb0de86a13d16d74edfaa3d0ab5492feddc
in both arms; profiles differ only by the new flag. Includes previous dirty
recovery-box/disabled predictive-phone source; not the accepted live binary.

Timing-driven fullview car245 OFF/ON: 52/53 valid on-target, zero off-target;
car115: 41/41 valid on-target, zero off-target. Sampled frame sets differ and
the original wrong-box failure did not recur, so these do not prove the fix.
Added a separately labelled fixed-stride-4 diagnostic: identical 150 source
indices, 600 source frames. OFF reproduced 63 zero-overlap control-valid boxes;
ON produced zero, retaining all 53 correct control-valid boxes. At frame236
the candidate refuses the bad return rather than authorizing same-ID control.
However, it remains lost through recovery expiry: safety containment, not
successful recovery. The narrow continuity gate correctly fails fixed4-OFF
and passes the other five trials.

Time-weighted source-wide eligible-on-target fractions (200 ms expiry; declared
50 ms source age): timing-driven245 OFF/ON 6.180%/6.168%, 115 6.804%/6.698%;
fixed4 6.177%/6.168%. Low availability remains unresolved. Strongest objection:
one fixed-frame A/B is not generalization or real-time qualification; single
object annotations do not certify identity, and failing closed is not recovery.
Next gate is diagnosing true-car recovery rejection on broader car footage,
without loosening safety gates to manufacture availability.

All six replay/restore codes zero, profile_unchanged=true. Final live binary
253a2df9...aaaea and profile73cb376e...91db7 match protected hashes, live node
running, AE=1/3DNR=1, no replay process. Candidate remains bench-only/default-off;
no preferred live binary/config replacement or vehicle I/O.

### 2026-09-20 — recovery rejection diagnosis; crowd candidate rejected

Added default-off recovery diagnostics, bounded by existing max_tracks, using
the existing tracker/replay JSON rather than a second decision path. Logs first
candidate rejection, evaluated size/distance/appearance metrics, observed vs
predicted geometry, and frame confirmation/expiry status. Native logging-on/off
parity test passes; all eight CTests pass after final edits. Build Python suites:
54 tracking (1 skipped), 24 follow, 7 bridge; continuity evaluator six pass.
No new dependencies. Detailed evidence/protocol:
`bench/results/2026-09-20-recovery-diagnostics/README.md`.

Four Hailo-15L fullview trials, fixed_stride=4, same source indices in both
arms; car245 600 source frames, car115 388. Runtime unchanged from
bench/versions.md: VPSP 1.12.0/HailoRT 5.3.0, Linux
5.15.32-yocto-standard-g1de0438be5ae. Same instrumented replay binary SHA256
b51cf0b9cc5f43cf7caba22d9bf655c8e166f329300d4f4b4812e381ce8151fc.
Both profiles retain car_gap_reverify=true; candidate changes only existing
reacquire_appearance_crowd to true. No numeric thresholds were loosened.

Car245 true-overlapping ID134 passes size, distance and appearance at244
(appearance distance .06335 vs .55 gate), but the crowd rule vetoes it.
28 observed IoU>=.5 candidates hit that veto during the recovery window;
two earlier candidates are unconfirmed. Car115 has 19 such crowd rejections.
Crowd ON recovers correct ID134 at256 after 600 ms confirmation (IoU .643).
However, later same-ID boxes drift: control-valid zero-overlap at584 and592.
This is not evidence that all off-target boxes represent identity switches.

Processed valid on-target/off-target/zero-overlap: car245 OFF 53/0/0, ON
82/51/2; car115 OFF 41/0/0, ON 71/0/0. Candidate FAILS continuity gate on245
and is rejected. Time-weighted eligible-on-target with declared source age50ms
and 200ms expiry: 245 OFF/ON 6.186%/10.183%, 115 6.779%/10.924%. Fixed-frame
diagnostic results, not live availability or flight qualification.

Structural decision: retain diagnostics, do not add/enable a recovery policy
that fails the regression. Next inspect later same-ID association/localization,
not simply broaden recovery acceptance. Strongest counterargument: only two
acquired car clips and one pass per arm, with tuning informed by the failure;
held-out car footage and live phone regression are still needed.
All four trial/restore codes0 and profile_unchanged=true. Final accepted live
binary253a2df9...aaaea and profile73cb376e...91db7 unchanged, camera running,
AE1/3DNR1, no replay process, no vehicle I/O or deployment changes.

### 2026-09-20 — selected-car extent gate, full-clip regression and measured cadence

Added default-off car_extent_gate and opt-in selected-assignment diagnostics
under recovery_diagnostics. Car245 at584 accepts a ~9px box with no current
appearance evidence: floor-scaled spatial displacement .8016 versus existing
limit2, actual box-extent displacement2.3906. At592: 1.7758 versus5.9556.
The .025-frame geometry floor is32 horizontal/18 vertical pixels. Central
appearance crops below8px are already refused; true-overlap raw detections
at584 score .213/.228 below unchanged .25 input floor. Candidate adds a
selected-car extent rejection using existing distance limit, retaining all
other gates/ranking; camera-compensated measured size protects against filter
collapse. No threshold lowering, phone change, dependency or second tracker.

Red tiny-car jump test fails before implementation, passes afterward; near
continuation, phone isolation and camera-motion compensation pass. Eight CTests,
Python tracking54 (1skip), follow24, bridge7 and continuity6 pass. Provenance,
limitations and all six trial artifacts:
`bench/results/2026-09-20-car-extent-gate/README.md`.
Runtime unchanged from bench/versions.md: 15L VPSP1.12.0/HailoRT5.3.0, Linux
5.15.32-yocto-standard-g1de0438be5ae. Same replay executable SHA256
effa2dbbd77adce95b8754ebbdb5a40932b377ea8f5bec8bac4db626db7ce573 in both arms.
Both enable prior car-gap verification and experimental appearance-crowd
recovery; only new extent flag differs. No live deployment.

Full car245 extended to768 source frames (192 processed at stride4), car115
388/97. Fixed-stride OFF/ON valid on/off/zero-overlap: 245 82/59/6 ->82/57/0;
115 71/0/0 ->71/0/0. Source indices identical, correct recovery at256/268
retained. OFF zero-overlap indices584,592,632,756,760,764 disappear ON; wrong
OFF recovery at756 does not occur ON. Two additional timing-driven245 trials
(201 processed each, not guaranteed identical subsets): 74/55/2 ->75/59/0.
All three candidate trials pass the narrow non-vacuous zero-overlap gate.

Time-weighted eligible-on-target fractions (declared source age50ms, expiry200ms):
fixed245 OFF/ON7.962%/7.976%, fixed11510.867%/10.932%, timed2457.355%/7.315%.
No availability/speed gain claimed. Poorly localized but overlapping boxes
remain (candidate245 fixed57/timed59 with IoU<.5); not proven identity switches.
Strongest objection: failure-informed gate, two acquired clips, one pass per
arm; could reject genuine rapid target motion or camera-motion errors. Keep
default-off and qualify held-out footage/live behavior before deployment.
Next investigate small-target detail/box evidence, not more permissive gates.

All six trial/restore codes0, profile_unchanged=true. Verified accepted live
binary253a2df9...aaaea/profile73cb376e...91db7 unchanged, node running,
AE1/3DNR1 and no replay process. No vehicle I/O.

### 2026-09-20 — owner-authorized live deployment of car-only guards

User requested "deploy it". Backed up accepted binary/profile to board
`/opt/garuda-fresh/backups/pre-car-guards-20260920.9gfis5/`, verified original
hashes, staged/capability-checked new node, stopped camera, replaced only binary
and current.json, then start-current readiness passed. New live binary SHA256
0ad699771eb5e1c7fa4b73d373f1be0cc9f5685019ae86724d7f5142c5855124;
current.json0dafe089de090aeb2782cf781cb166046f159d995e53fb68fac548c6eff87f87.
Profile comparison proves only car_gap_reverify/car_extent_gate=true additions.
Existing detector/ISP/phone settings retained; global appearance-crowd recovery
kept OFF to avoid changing phone recovery. Not the aerial bench profile; live
car recovery accuracy is unqualified. No vehicle I/O or boot/service changes.

Verified native sequences78/80/81/83/85, valid IMX678 timestamps, JPEG stream,
AE1/3DNR1. Sampled state ages262.7/238.7/378.4/350.8/357.5ms, short readiness
sample only. Log frames58/rejected0; no target selected/control-valid output.
Runtime remains bench/versions.md's Hailo-15L VPSP1.12.0/HailoRT5.3.0 snapshot.
Rollback commands and provenance:
`bench/results/2026-09-20-car-live-deploy/README.md`. Live car routine and phone
regression still required; deployment readiness is not tracking qualification.

### 2026-09-22 — partial live phone-motion recording

Owner requested record now/done. Diagnostic budget refused120/40-frame requests;
two12-frame bursts succeeded and were SHA256-verified on PC. No live config,
binary, ISP or vehicle changes. Existing Hailo-15L VPSP1.12.0/HailoRT5.3.0 runtime
from bench/versions.md; car-only guard deployment remains the prior configuration.
Evidence/limitations: `bench/results/2026-09-22-phone-motion/README.md`;
private artifacts under ignored bench/local-baselines/20260922-phone-motion/.
First twelve updates span2000.024ms: nine valid observations, two low-confidence,
one missing observation, same phone ID2609. Later twelve span1900.014ms: phone
detected in all but lock recovery expired. Between bursts22400.280ms was NOT
recorded, so actual loss transition and fast-motion root cause remain unknown.
Not a continuous recording or FPS/identity qualification. Need host-side
continuous evidence rather than enlarging board-RAM capture budgets.

2026-09-22 cleanup/retry preparation: at owner's deletion request copied all
eight owned input-capture dirs to ignored PC archive20260922-capture-cleanup,
SHA256-verified every file, then deleted ONLY those /tmp recording dirs from
board (35373230bytes recoverable on PC). /tmp usage174M->140M; eMMC already
had3.3GB free, not the recording blocker. Models/software/backups untouched.
Enabled existing paired-source PC streaming8983 (only two config additions),
backed up prior profile in pre-pc-capture-20260922.KasIsw, restarted camera.
Live binary unchanged0ad699771e...55124, new config12578dc598...ea333,
AE1/3DNR1. Smoke12/12 paired frames,23961600pixel bytes, complete footer;
no fast-motion qualification. Tracking parameters remain unchanged. See
bench/results/2026-09-22-phone-motion/README.md for artifacts and next capture.

2026-09-22 continuous phone-motion PC recording:180/180 paired updates,
359424000pixel bytes, complete footer and offline integrity PASS. Sequences
1042..1221 contiguous processed updates,26900.377ms capture span. Observed82,
missing33, low-confidence10, watching30, verifying25. Of33 missing updates,
24 no phone/2 weak phone/7 phone>=.4 not observed on selected track. Five
returns to tracking; no recovery-expired state. Exact association cause and
box/identity accuracy remain unqualified. Initial selected/coasting history
predates capture. No settings/ISP/binary changes; existing15L runtime from
bench/versions.md. Evidence and limits:
bench/results/2026-09-22-phone-motion/fast-motion-pc-01.md. Recording now has
continuous processed evidence; this is not itself a phone-tracking improvement.

### 2026-09-22 — phone gap-association OFF-by-default candidate, offline only

Owner approved analysis/fix using continuous capture. Added observational pair
gate diagnostics and a fixed-input native replay harness, explicit selection at
sample15 after warmup. Baseline reproduces164/164 live reasons and81/81 observed
boxes for samples16..179. Confident-phone rejections at26/27,49/50,100/101,150
first hit the fixed center gate. Candidate admits only sole detected, strongly
appearance-matched, confident selected phones across bounded short gaps; all
other association/control gates and explicit recovery remain. OFF in live profiles.

Observed81->101, low10->13, missing30->27, watching22->15, verifying21->8;
all81 baseline observed boxes retained exactly. Two earlier returns44->26
(3000.041ms),55->49(1100.021ms), capture-clock differences, NOT latency/FPS.
Later outages persist:100 covariance,101 absolute displacement,150 center bound.
Default-off replay and diagnostics on/off preserve180/180 decisions. Full native
8CTest/54trackingPython(1skip)/24follow/7bridge tests and ARM cross-build PASS.
No deployment: live binary0ad699771e...55124/config12578dc598...ea333 verified
unchanged over SSH. Runtime: bench/versions.md 2026-09-22 offline PC snapshot;
capture retains prior VPSP1.12.0/HailoRT5.3.0 board setup. No dependency/ISP/FC change.

Red-team/qualification: single development recording, no held-out annotated
identity truth, candidate-dependent ROI scheduling held fixed; state improvement
does not prove correct identity or live gains. Another physical phone is visible
but not necessarily detected. Histogram guard and synthetic rivals are not full
identity validation. No project gate ticked. Structural change confined to
existing core/config/serialization/tests + PC harness; intermediate runs archived,
pre-existing dirty work retained. Controlled live A/B and distractor testing next.
Full evidence, commands, build hashes, limitations:
bench/results/2026-09-22-phone-motion/phone-gap-candidate.md.

### 2026-09-27 — drone-footage detail rejection and car compute candidate

Owner requested continued improvements using existing drone footage. Real-board
four-run fullview/fullview_roi comparison, fixedstride4, declared50ms period and
50ms initial source age, click15/retry1000ms. Car245768 source frames; car115388.
Detail candidate REJECTED: car245 correct82->53, validIoU<.5 57->55 but ZERO
overlap0->55; timely correct82->40. Car115 correct71->71, off0->0, timely71->34.
New paired evaluator catches30 lost correct frames and19 newly off-target frames
in245, rather than accepting a lower aggregate bad-output count. First bad ROI
recovery260/ID154 retained as next regression. Baseline245 all57 poorly localized
valid outputs lack a same-class/control-confidence raw box at IoU>=.5. Do not
claim this detector evidence proves identity eligibility. Full evidence:
bench/results/2026-09-27-drone-detail/README.md.

Implemented OFF-by-default defer_person_embeddings_on_car in shared scheduling
helper/live node/replay. Histograms/detections/identity/recovery/expiry retained.
Selected tracking/coasting car only; pending person click, person/phone target,
lost/reacquiring state and embedding-based association restore normal budget.
Pending person selection gets priority over the old car box. Synthetic reselection
and default/profile isolation tests added. No live profile enabled the option.

Six-run identical-binary OFF/ON fixedstride4 test on car245768,car115388,person024
1000 source frames. Only opt-in Boolean differs. Correct/bad valid counts stay
82/57,71/0,42/1 in both arms; zero-overlap0 for all. Selected target geometry/ID/
reason/state/validity match192/192,97/97,250/250 updates. Person embeddings1474
in both arms, identical per-frame counts; no person deferrals. Car total embeddings
1103->113 and582->144,169/192 and73/97 deferred updates. Median appearance time
63.165->1.117ms,63.298->1.422ms. Median processing (all-frame score median age
minus declared50ms)113.904->50.907ms and120.773->59.284ms; person96.387->96.192ms.
This is a compute saving, NOT measured live latency/FPS or localization improvement.

Time-weighted eligible correct fractions with scorer200ms expiry: car2457.180%
->20.607%,car11510.709%->34.129%. Car245 incorrect-valid duration also grows
2202.454->5703.035ms as bad boxes arrive earlier. Explicitly NOT a safe-following
promotion. Quality non-regression screens pass; strict quality-improvement screens
do not, because no additional correct frames. Single OFF-then-ON passes, no
thermal/clock series, already-used development clips, fixed scheduling and no
fresh live/held-out identity qualification are the strongest counterarguments.

8CTest/55trackingPython(1skip)/24follow/7bridge PASS; paired+continuity14 and
timeline6 evaluator tests PASS; full ARM cross-build and diff check PASS. No new
dependencies. Structural review: shared existing pipeline, one scheduling option
and regression scorer, no new tracker/FC path. No project gate ticked. Plan:
docs/2026-09-27-drone-improvement-plan.md. Runtime bench/versions.md2026-09-27,
unchanged15L VPSP1.12.0/HailoRT5.3.0. All ten trials return/restore0 and unchanged
profile. Final live node active, no replay process, protected hashes unchanged:
node0ad699771e...55124,config12578dc598...ea333. Runner cleaned only owned temporary
staging dirs; copies/artifacts retained locally. Full hashes, commands, outputs,
build log and limits: bench/results/2026-09-27-drone-budget/README.md.

### 2026-09-27 — current-evidence recovery experiment REJECTED for deployment

Owner requested the next drone-footage improvement. Traced245 ROI failure:
target-overlapping ID149 current evidence excluded as pre-existing, while wrong
ID154 confirms/rebinds260. Birth time is not proof of identity; no claim that the
old ID is a proven duplicate. Added default-off tracking.car_recovery_detection_veto
in existing shared tracker, config and diagnostics. Current same-class descriptor
competition may veto, never authorize otherwise excluded IDs. Existing score,
size/radius/appearance/control floors and ambiguity margin; reset confirmation
on contradiction, refuse stale-only candidate descriptor. Phone branch unchanged.

Eight real-board identical-binary OFF/ON fixedstride4 trials, car245768/car115388
source frames, ROI/fullview; click15/retry1000ms, assumed50ms period/initial age.
Embedding deferral OFF; experimental aerial crowd recovery ON, unlike live desk
profile. Source frames fixed; target-state feedback changes later ROI crops.
Correct/incorrect valid OFF->ON:245ROI53/55->53/0,245full82/57->79/56;
115ROI71/0->41/0,115full71/0->41/0.245ROI zero-overlap55->0 but timely correct
41->39 and no additional correct frames. Fullview245 loses256/260/268: margin
at256 resets confirmation, recovery delayed to272. Both115 modes lose30 correct
updates268..384; rival current histograms repeatedly reset confirmation until
expiry. All four conservative comparison screens FAIL. No threshold retuning
to fit clips. Experiment retained default-off, expressly rejected for promotion.

ROI245 source-wide incorrect-valid duration805.094->45.211ms, not zero despite
zero bad processed boxes: truth changes during skipped-frame publication holds.
Correct availability remains poor. Tiny-car localization/identity still unsolved.
Strongest counterargument: broadening competitors makes weak histogram/position
evidence too conservative for working recoveries. One OFF/ON pass on development
clips, no held-out/generalization/live latency/vehicle qualification claim.

Full SDK ARM build8CTest/55trackingPython(1skip)/24follow/7bridge PASS; final native
8CTest and paired/continuity14 tests PASS; diff check PASS. No dependency changes.
Native regressions reproduce unsafe old acceptance, guarded refusal, fresh600ms
reconfirmation after rivalry clears, missing current descriptor and phone isolation;
diagnostics observational with guard OFF/ON. Structural review: existing core and
harness only, no alternate engine or FC path; experimental options need pruning.
No project gate ticked. All8 trials return/restore0,liveprofileunchanged; final live
node active, no replay process. Live hashes unchanged0ad699771e...55124 and
12578dc598...ea333. Only owned temporary staging cleaned, no recordings deleted.
Full commands/hashes/counterexamples: results/2026-09-27-car-recovery-evidence/README.md.
Next: inspect temporal identity evidence/crop quality on BOTH success/failure cases,
then flight-disjoint holdout; do not enable this guard or rejected ROI scheduler.

### 2026-09-27 — track/record scope, data audit, recording failure; board recovery needed

Owner requested continued work toward drone mounting, then scoped to track/record
only, non-extreme conditions, eMMC for short tests. No vehicle commands/FC session,
new model/ISP settings, package installation or dataset download. Proposed readiness
checks/official dataset sources: docs/2026-09-27-track-record-readiness.md. They are
requirements, not passes. UAV123/UAV20L first independent aerial candidate, UAVDT
next for vehicles; exact usage permissions remain unverified. VisDrone official
policy explicitly describes2021 academic/non-commercial terms; do not assume exact
2019 archives/company use cleared. Public data cannot replace own-camera/mount tests.

New stdlib audit+4tests inventory6471 DET train,548 DET val,11 SOT clips7046frames,
7 MOT sequences. Mixed detector training directory11423 images includes4952 COCO
val2017: training, not untouched test. ReID238/5482 training IDs/crops;76/1795
validation IDs/crops, group086 shared with SOT086 and scored during model development.
No SOT training filename-group matches, but no pixel/flight independence proof.
All11 previously tuned SOT cases remain development; untouched holdout=0.

Expanded real-board baseline:11 full prepared sequences, fullview/fixedstride4,
click15/retry1000ms, declared50ms source period/initial age. Same diagnostic aerial
profile (mixed e11 detector/zoo OSNet, experimental car crowd recovery) as preceding
car comparisons, not live desk and not asserted best aerial combination. Rejected
veto and embedding deferral OFF.1765 processed,1721 evaluated,5/11 acquired,
215correct valid,59validIoU<.5. All complete manifest-index sets verified, all11
return/restore0 andprofileunchanged. Timeline correct2.2474%,incorrect2212.944ms
under declared timing/200ms expiry; not live uptime/identity certification.

Added --local to existing exact capture receiver (no SSH image transport), local
nohup orchestration with unchanged-profile checks,512MiB disk reserve/per-frame
storage checks, interval/pixel-byte stats in integrity qualification. Never overwrites
or automatically deletes recordings. Initial120-sample direct-to-eMMC test saved64
then native capture_transport_timeout, client incomplete EOF; live checks afterward
passed. A bounded2-packet reader retry saved43 then same failure. Measured pixel
write median16.377ms,max1540.025ms against native100ms send deadline; evidence does
not justify enlarging inference queues or hiding dropped frames. Failed threaded
buffer removed from source rather than retained as a switch.

Third120-sample RAM-first attempt exposed a DEFECT IN THE NEW PYTHON ADMISSION
CHECK: it used MemAvailable without subtracting CmaFree. Native diagnostic_budget
already handles this distinction on15L (large dedicated camera/NPU CMA pool).
During this trial SSH and camera API became unresponsive; ping still responds,
serial logs ISP event timeouts. Login/newline/interrupt attempts did not obtain a
usable shell. No final sample count, runtime memory or successful qualification;
do not assert a proven OOM diagnosis. New check is wrong independently of exact
stall causality. No reboot, mass-kill, sysctl or boot changes attempted. Owner asked
to power-cycle safely on bench; further capture stopped. Final live health cannot
be claimed restored. Protected binary/config were not replaced by any trial.

Corrected local checker mirrors native MemAvailable-CmaFree, rejects absent/
malformed accounting, keeps160MiB ordinary RAM reserve, defaults16/max24samples
and monitors headroom. Whole short request RAM-spooled, then validated and saved;
power/process failure can lose unsaved capture. NOT a continuous flight recorder.
Correction passes native fixture-equivalent CMA pressure/missing/reversed tests,
but cannot be board-qualified until recovery.65trackingPython tests(1skip),4data
audit and2campaign-report tests PASS; diff check PASS. No native binary rebuilt
or deployed this turn. Structural review: existing capture/replay paths, one
inventory and one bounded launcher; rejected threaded experiment pruned. No gate
ticked. Strongest counterarguments: poor independent tracking evidence, unqualified
raw recording, eMMC stalls, and newly fixed but not board-verified memory guard.

Artifacts: results/2026-09-27-track-record-readiness/; raw prefixes on board in new
owned local-record.* dirs, no existing recordings deleted. DO NOT rerun staged
old receivers. First capture path4Fkl8v; thirdFn2ASK. All per-run paths/hashes/errors
retained in run.json; first two postmortems and serial-check.txt retained. Runtime
snapshot addendum in versions.md. Resume with board recovery/log collection,
unchanged baseline verification, then corrected small monitored recording test.

### 2026-09-27 17:10 IST — recovery check after owner power-cycle confirmation

Read-only recovery probes: SSH connect timeout, camera API connection timeout,
ping 0/3 replies. PC eno1 is administratively UP but NO-CARRIER; NetworkManager
reports carrier off/unavailable and h15-link inactive. Its saved address remains
10.0.0.2/24. Without that link, the current route to 10.0.0.1 uses Wi-Fi; network
timeouts do not establish board OS health. FTDI console remains enumerated at
the recorded by-id path. Exclusive 115200 serial probe with DTR/RTS asserted,
six seconds passive read then carriage return and four seconds read produced
only an initial NUL/newline, no usable prompt. No other serial owner detected.
Board recovery, protected hashes, recording state and camera health remain
unverified. No network configuration changed; no capture/replay, deployment,
deletion, reboot or FC operation performed. Physical power/link check required.

### 2026-09-27 17:12 IST — recovered camera; bounded local capture04 integrity pass

After further owner confirmation, eno1/h15-link carrier returned. New board boot
ID eb5db10e-a888-48af-8a64-c0900cea81ba; Linux5.15.32-yocto-standard-g1de0438be5ae.
Protected node SHA0ad69977... and config12578dc5... match prior full hashes in
recovery-check.txt. No native camera running after boot; existing start-current
restored unchanged profile/binary and UI. No model/ISP/boot/network changes.
Recovered capture03:108 saved metadata sets,208M directory; error is image/frame/
output correspondence mismatch, no completion. pstore empty and /var/log volatile;
new-boot logs cannot establish old-boot OOM causality. Filesystem reports journal
recovery and two orphan inodes deleted by kernel at boot, not an agent deletion.

Corrected receiver12tests, launcher2tests, qualifier5tests PASS. Ran existing
run_local_capture_trial.py --frames16 into local-capture-04. Board destination
/opt/garuda-fresh/local-record.KQug9n. All16 paired samples completed and integrity
passed;31,948,800 pixel bytes, source span2466.709ms, interval median166.667ms,
max200.006ms, zero unrecorded tracker sequence IDs. Not a sensor-drop count.
Receiver hash f6c9b210... (full in run.json), non-CMA guard active,160MiB RAM and
512MiB storage reserves. No pixels transported over SSH. Native/profile unchanged,
no replay/MAVROS. After test free3020525568bytes; subsequent postcheck3020410880,
non-CMA headroom372700KiB, sequence232 with capture sent16/error empty/inactive.
Camera remains live, target not selected. Raw recordings retained; no deletion.
Counterarguments: only one2.47s burst, page-cache writes not durability proof,
no labelled target or sustained/thermal/mount qualification. No readiness gate
ticked; corrected receiver board-smoke-tested only. Evidence: recovery-check.txt,
local-capture-04/run.json and postcheck.json. Next: selected-target motion protocol
and durable bounded recording design before any longer autonomous recording.

### 2026-09-27 — owner-requested phone capture05

Owner requested recording; preflight API reported selected cell phone, observed,
control_valid true (self-report, not labelled accuracy). Ran bounded local capture
with16 samples. All16 paired samples saved on board in
/opt/garuda-fresh/local-record.k6ffef/capture; integrity PASS. Source span2066.679ms,
pixel bytes31,948,800, interval median100.009ms/max266.668ms, zero unrecorded tracker
sequence IDs (not sensor-drop measurement). Camera/profile hashes unchanged,
native running, no replay/MAVROS; after free2986868736bytes. Recording completed
and stopped automatically. No deletion or configuration changes. Runtime/scripts
same as capture04 (versions.md); full hashes/evidence in
results/2026-09-27-track-record-readiness/local-capture-05/run.json. No tracking
accuracy claim inferred from integrity; two-second burst is not a fast-motion
qualification or sustained recording pass.

### 2026-09-27 — phone search timing attribution and bounded-miss candidate

Owner approved staged scheduler work. Inspected current live profile, shared
FollowSchedule/RoiAssist and recorded metadata from capture05 and Sept22's180-frame
fast-motion clip. Added metadata timing analyzer (three tests) and recorded-time
native scheduling regression. Existing opt-in phone_short_miss_ms250 covers the
brief-miss mechanism; reused it, no new runtime heuristic or default change.
Candidate/baseline profile files are LOCAL ONLY, differ in that one key.

Measured baseline capture05 median processing:1pass53.880ms,2passes87.417ms,
5passes155.547ms,6passes191.187ms. Old fast-motion clip:51.055/76.010/162.612/
192.808ms respectively. Sample8 low-confidence followed by sample9 six-pass
global search183.476ms. Not counterfactual candidate speed; unchanged observations
cannot establish what would have been detected without corners. Unit regression
defers this bounded miss, retains expiry/ambiguity/class/epoch safeguards, never
sets control-valid on a missing measurement. No accuracy claim.

Native build/8CTest PASS;68Python tracking tests(1skip) PASS,14search scenarios.
No ARM build, new dependency, live profile/model/ISP write, camera restart or
recording deletion. Final protected hashes unchanged; sequence4211 on same stream,
capture inactive/error empty. All sources, script outputs, hashes, limitations and
next owner-present A/B protocol: results/2026-09-27-phone-schedule/README.md.
Strongest counterargument: corners can recover a phone that local ROI misses;
candidate may trade recovery for speed. Requires measured labelled live A/B before
promotion. Structural scope is one bench analyzer/tests plus native regression;
existing scheduling implementation reused. No project gate ticked.

### 2026-09-27 — owner-present phone bounded-miss live trial, baseline restored

Baseline16 samples saved in /opt/garuda-fresh/local-record.ozZgzs/capture; integrity
PASS,2466.694ms source span. It started already missing and reports0observed,
1missing,13watching_for_return,2verifying_returning_identity. Exact baseline backup
/opt/garuda-fresh/phone-schedule-ab.0COw9J/baseline.json hash12578dc5... verified.
Temporary candidate only adds phone_short_miss_ms250, hash05330530...; live binary
unchanged. Existing stop/start-current applied it, owner reselected and said ready.
Candidate16 samples saved /opt/garuda-fresh/local-record.g3vYFD/capture; integrity
PASS,1800.019ms,8observed/3low-confidence/5missing. bounded_phone_miss exercised
once at sample8 with2passes81.320ms and weak phone.164. Samples12..14 have no phone
under full search. Branch activation validated; tracking improvement NOT proven.
Baseline/candidate median processing156.694/113.427ms and max source gap200.010/
200.017ms, but different starting states and motion make this NOT a fair causal
comparison. No promotion. Both raw captures retained, metadata analyzed on PC.

Restored exact original profile and verified node/config hashes0ad69977.../
12578dc5...; camera advancing stream a11a4e7c-f78c-4d53-b0fa-af204a6161ed sequence67,
capture inactive/error empty, target cleared by restart. Final free2855096KiB.
No binary/model/ISP/boot changes, deletion or FC operations. Detailed timing,
hashes, limitations, rollback and next synchronized-capture protocol in
results/2026-09-27-phone-schedule/README.md and live-{baseline,candidate}-01/.
Strongest counterargument retained: baseline starts in recovery; candidate still
loses detections, no labelled pixels or controlled identical movement. Runtime
snapshot addendum in versions.md; no new code changes this trial.

### 2026-09-27 — deeper camera/YOLO input-path diagnosis

Owner challenged resize/ISP/algo assumptions after inconclusive tracking tweaks.
Read current profile chain, runtime AE/3DNR, model conversion/calibration and
region filtering. Managed detector crops paired720p, not native4K. Sensor configured
4K30, outputs20fps; runtime exposure33.006ms, gain~12x, ISP3DNR on/AI denoise off.
Ran existing DSP/HEF probes on31 regions of4 hash-verified retained exposures;
finally restored unchanged live camera.31 layout checksPASS; sample12 preview
byte-identical to DSP fullview. Recorded phone scores reproduced exactly in
sample0 corner/ROI and sample8ROI. Float source on identical pixels also weak;
oracle320 enlargement and float-only gray114 padding do not consistently help.
Found frame12 real.265 phone discarded by8% interior tile-border filter; still
below.4 control floor. No runtime fix/promoted configuration; no accuracy claim.

Added bounded diagnostic/scorer and6 regression testsPASS. Same-exposure native4K
comparison and controlled blur attribution remain open. Source/build hashes,
scope/strongest caveats, next tests and complete compact artifacts in
results/2026-09-27-image-path/README.md. Postcheck protected hashes unchanged,
camera advancing sequence1728, capture inactive, no replay/MAVROS. Added~68MB
retained probe stage on eMMC; free2851225600bytes. No deletion or FC operations.

### 2026-09-27 — recorded-video boundary/native/ISP audit

Owner requested all proposed checks using recordings.988realDSP/HEF evaluations
on184saved exposures (180fast-phone +4recent); new optional pre-region-filter
diagnostics and bench-only object-relative border candidate. Five-tile phone
presence>=.4 rises135/180→138/180; sparse matched detections15/18→16/18.
Fixed recorded schedule/core replay using frozen live config: observed81/164→90/164.
Sparse correctly localized control-valid6→8, not dense wrong-lock qualification.
18uniform hand boxes, two coarse labels corrected after full-pixel review; old
labels/results retained. Confidence/freshness/identity/ROI gates unchanged.

Equal-framing direct4K vs DSP720 on3decodedH264 exposures,21windows each: frame360
oracle960 confidence.483vs.160; other tested views mixed/tied, not a blanket4Kwin.
Initial720probe refused network alignment; restored camera, used DSPresize instead.
Final42prediction arrays repeat exactly. No original raw pairedISP720/native claim.
All184paired phone frames exposure33006us; previous15ms/3DNR logs have no matched
pixel baseline. Off/gap500 telemetry shares3022states, not independentISP trials.
No retrospective camera-setting improvement claimed; capture-dependent gap remains.

8CTest/68trackingPython(1skip)/14input-auditPythonPASS; exactSDK node/probe buildPASS.
Node built but NOTdeployed; candidate remains bench-only pending dense labels,
causal crop scheduling and aerial regressions. New source/probe hashes, run logs,
strongest limitations, final live restoration and controls in
results/2026-09-27-recorded-input/. No deletion, new recording, install or FC action.
