# 15L ROS 2 / MAVROS and detector campaign

Status: **board ROS/MAVROS communication demonstrated in SIL; no real-FC or
robust-perception sign-off**. This is the current continuation handoff.

Owner's deployment requirement: native Hailo perception + ROS 2 + MAVROS on
Hailo-15L; MAVROS feeds PX4. The PC provides Gazebo, operator UI and the
independently guarded simulator endpoint. A PC-only ROS demonstration is not
completion of this requirement.

## Scope and gates established before the new SIL runs

1. Exact model comparison: hash-bind source ONNX, retained FP/quantized stages,
   compiled HEF and exact DSP tensors. Retest the actual board. The nine retained
   phone samples are oracle crops, **not full-view or a held-out aerial benchmark**.
2. Compare full-view, full-view + target crop, and adaptive periodic tiles on
   the same three source sequences and one fixed initial click. Measured costs
   determine skipping, so processed subsets differ. Score overlap, raw misses,
   age and rejection reasons; do not count skipped frames as successful tracks.
3. The compiled HEF has a known full-range conversion. Gazebo RGB conversion
   must match it. Preserve the old limited-range path as a named comparison.
4. Real ARM64 ROS 2 and MAVROS processes must run on the 15L, with visible
   ROS topics, service responses and actual MAVLink received by owned PX4 SITL.
5. Test coordinate signs, stale/reordered/session-invalid requests, source loss,
   ROS loss, tunnel loss and takeover/land. Never keep an expired motion command.
6. Recorded video drives a **heading-response demonstration**, not closed-loop
   tracking. Use source bytes unchanged, declared playback FPS/FOV, and a bounded
   reference heading so a fixed recording cannot cause indefinite turning.
7. Repeat rendered-camera feedback with ROS/MAVROS in the path. Report command
   eligibility, detector misses, identity errors, timings and failure response.

Passing communication tests is distinct from detector/tracker robustness.
Actual hardware FC compatibility remains untested until an identified FC and
firmware are present. First hardware testing must be read-only, then an explicit
propellers-removed bench session, not automatic arming. Physical camera timing,
metric depth, obstacle avoidance and outdoor/crowd validation remain separate.

## Deployment boundary

The 15L retains stock VPSP 1.12.0 / glibc 2.35, 1913 MiB RAM and no Docker.
ROS was absent initially. Installed an isolated Ubuntu Noble ARM64 rootfs at `/opt/garuda-ros-jazzy` because
Jazzy binaries require a newer userspace. Native Hailo libraries and applications
are unchanged. This is a bench alternative, not a finished meta-ros Yocto port
or a security sandbox. Licenses and disabled recipe:
[dependency record](dependencies/ros2-mavros-bench.md).

The board had calendar UTC in 2018. It was corrected from PC UTC on 2026-09-13
for signed package-date validation. No RTC, boot or NTP configuration changed.
This is not PTP, exposure synchronization or a precision-clock claim.

The MAVROS endpoint is fixed `tcp://127.0.0.1:5760` on the board, through an
owned SSH tunnel to the PC loopback relay and direct-owned PX4 SITL process.
No serial hardware endpoint or configurable LAN FC URL is exposed. The relay
revalidates motion expiry and bounds *after* ROS queues. Normal arm, mode and
setpoints go through MAVROS. Direct MAVLink LAND is a separately logged emergency
cleanup fallback and must never be counted as successful MAVROS landing.

ROS topics currently use a bounded JSON envelope over `/garuda/bench_request`
to preserve the existing perception contract. The board independently runs
`PerceptionAuthority` before `/mavros/setpoint_raw/local`. The host repeats the
outer gates as the simulator safety boundary; it is still a required participant.
Deadline conversion uses an asymmetric RTT bound, not assumed equal network
delays. A drift margin is an engineering assumption, not certified synchronization.

## Current evidence

Working artifacts: `/media/bhanu1234/Development/hailo-export/ros2-follow-20260913`.
Compact text evidence is archived under `bench/results/2026-09-13-ros2-mavros`.
No acceptance gate is ticked by implementation or unit tests alone.

### What actually runs where

```text
PC Gazebo / recorded pixels -> native inference on 15L
                                      |
                         PC envelope + operator supervisor
                                      |
                       15L ROS 2 ingress -> authority -> MAVROS
                                      |
                       SSH loopback relay -> PC PX4 SITL
```

ROS 2 **really runs on ARM64 on the 15L**, not a PC stand-in. It independently
checks the perception contract and publishes `/mavros/setpoint_raw/local`.
The ingress topic is `/garuda/bench_request`; services are `/mavros/cmd/arming`
and `/mavros/set_mode`. Domain 73, CycloneDDS, loopback discovery. No serial
device is exposed to the chroot. Nothing auto-starts at board boot.

**Still not standalone on-board autonomy:** PC envelope/supervisor/relay remain
required for this simulation. The intended next architecture removes the PC
round trip between native inference and the board ROS authority. A real FC must
not require that PC relay to enforce command age. Product packaging, typed ROS
interfaces, on-board local ingress, clock qualification and a guarded physical
transport are unfinished, not silently treated as complete.

### Communication evidence

`axis-normal`, `axis-request-loss`, `axis-ros-loss` run explicit axis commands,
**not detections**. All have actual post-MAVROS motion packets, positive N/E
displacement, correct yaw sign, final disarm, and no direct emergency LAND.

| Test | Max settled 30° error | Observed offboard exit after fault |
|---|---:|---:|
| Normal + MAVROS landing | 0.085356° | Not injected |
| Requests stop, ROS stays alive | 0.123066° | 2.500155 s |
| Owned ROS/SSH session terminated | 0.120955° | 1.200222 s |

The last test is **combined ROS-session/tunnel loss**, not independent process-
versus-network fault isolation. PX4 logs show its own RTL/landing failsafe.
`SetMode.mode_sent` means sent, not mode completion; telemetry and PX4 logs are
the completion evidence. See the [PX4 offboard contract](https://docs.px4.io/main/en/flight_modes/offboard).

Fixes found during bring-up: ROS rejects an untyped empty plugin denylist;
the minimal chroot needed its own localhost entry; a one-packet-per-loop relay
starved telemetry; draining the relay only on 20 Hz control boundaries added
avoidable delay. These failures are retained, not reported as passing runs.
Afterward, relay traffic drains independently while control remains 20 Hz.

Additional final boundary: each moving MAVLink packet is bound once to an actual
ROS publication's header timestamp and its original request deadline. A newer
request cannot renew it. Selection/source epoch changes revoke pending bindings.
Unknown/duplicate/mismatched/expired packets fail closed. This timestamp binding
depends on the installed MAVROS `get_time_boot_ms` behavior; requalify on upgrade.
The 200 ms perception limit and 150 ms maximum intent TTL were not relaxed.

### Detector and scheduler evidence

Nine retained exact phone-input crops were checked against original ONNX,
retained FP/quantized stages and a fresh actual-device HEF run. Three samples
were missed by all stages; several others differed substantially in confidence.
This excludes neither model limitations nor quantization effects. These are
**oracle crops**, not full-view accuracy or a held-out flight benchmark.

Found and corrected the simulator RGB adapter: the controlled HEF expects the
known full-range conversion, while the old adapter produced limited-range
NV12. The full-range native adapter matches its NumPy reference byte-for-byte.
This diagnosis applies to simulated RGB ingress; it does **not** establish that
the physical ISP is misconfigured. Old limited-range conversion remains named
for comparisons. No HEF weights or desk sensor configuration were replaced.

Same-source schedule campaign: 240 input frames per run, one fixed initial
point, declared 50 ms frame period and 50 ms source age. Processing cost changes
which frames are skipped. These are assumptions, not recovered video FPS or
measured exposure latency. Values below are fresh on-target overlap frames /
processed frames; skipped frames are not successful tracks.

| VisDrone sequence | Full view | Full view + ROI | Adaptive tiles |
|---|---:|---:|---:|
| Person 086 | 6/60 | 2/60 | 0/40 |
| Person 024 | 0/60 | 0/60 | 0/40 |
| Car 115 | 46/68 | 34/64 | 20/48 |

For person 086, full view had raw target overlap in 58/60 processed frames but
43 `identity_evidence_incomplete` rejections. Person 024 full view had raw
overlap in 59/60 but failed initial selection entirely. Raw overlap is class-
agnostic diagnostic evidence, not identity proof. Adaptive car had one
control-valid off-target overlap result, although it exceeded the consumer age
limit. Never advertise zero wrong identities from the fresh subset alone.

Full-view detection median was roughly 27–28 ms; adaptive detection about
125–128 ms. Six-person appearance work was about 63 ms; CPU resize plus motion
about 31–34 ms. These measurements identify scheduling and identity coverage
as important bottlenecks. Retraining alone cannot fix those mechanisms.

### Rendered-camera comparison

Both rows below use actual board inference, board ROS/MAVROS, same simple
single-person world and 40 s requested follow duration. This is not a randomized
paired statistical accuracy study; the moving drone changes later input pixels.

| Run | Host non-hover follow ticks | Result median / p95 | Board compute median / p95 | Actual forwarded motion packets |
|---|---:|---:|---:|---:|
| Adaptive (`ros-visual-final`) | 244/796 | 141.223 / 237.246 ms | 92.168 / 189.739 ms | 85 |
| Full view (`ros-visual-fullview`) | 576/796 | 112.019 / 136.950 ms | 66.729 / 70.215 ms | 141 |

Maximum follow displacement was 2.144186 m and 3.914450 m respectively. Both
held on the injected two-second perception dropout, recovered, and landed /
disarmed. Host eligibility **is not executed motion**. The console now exposes
actual post-MAVROS forwarded/rejected motion counts separately. A final-code
repeat is stored as `ros-visual-qualified-repeat`; the directory name itself
does not grant qualification. Read its `mavros-verified.json`.

Final-code repeat: 522/797 host non-hover follow ticks, 201 actual forwarded
motion packets and 42 rejected. Result median/p95 111.362341/136.150643 ms;
board compute 66.576400/69.532520 ms; maximum follow displacement 6.758444 m.
It passed dropout hold/recovery, original-publication deadline checks and final
disarm without emergency direct LAND. This repeat still does not certify identity
or make the failed aerial experiment acceptable.

### Recorded aerial response

Car115 source SHA256 `0c4e7a4741851a8fd6be5b15b6320d8f14a302839a2cc11b7ba182239961851c`.
Both trials used unchanged prepared 1280×720 NV12, assumed 20 FPS / 1.2 rad HFOV,
and one fixed selection at (661,396) after playback began. No per-frame labels
went to the controller. Translation is disabled. Requested heading is relative
to a latched reference and bounded to ±30°, never cumulative yaw from a fixed
video. This clip's centered car does not provide a 30° visual excursion.

Adaptive failed selection and forwarded **zero** motion packets. Full view
selected the car but forwarded **one** motion packet; actual follow heading span
was only 0.211258°. Both held on expired pixels and ended disarmed. The second
passes only the verifier's minimal protocol-response checks—**neither is an
acceptable aerial-follow demonstration**. EOF cannot be expected to recover.

## Reproduce and operate

The rootfs is already installed. `hosts/hailo15l/ros2/install_rootfs.sh` is the
guarded reconstruction script; it needs verified assets and temporary signed-
package access. `deploy_nodes.sh` stages source and refuses an active ROS runner.
Do not install Ubuntu or ROS into the stock Yocto filesystem.

```sh
# No perception, actual board ROS/MAVROS; add --fault requests or --fault ros.
GARUDA_SIM=1 python3 bench/sim/mavros_axis_sil.py --out NEW_AXIS_DIR
python3 bench/sim/verify_mavros_axis.py NEW_AXIS_DIR

# Interactive console starts disarmed. The full-view profile is bench-only.
GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh --out NEW_VISUAL_DIR \
  --transport mavros-15l \
  --board-binary /opt/garuda-sim/garuda-causal-stream-diagnostics \
  --board-profile /opt/garuda-sim/profile-fullview.json
```

Local console: `http://127.0.0.1:8100/`. Choose a target, take off in simulation,
then Follow. Hold is operator-controlled; Stop lands/closes and restores the
previously running desk app using unchanged `current.json`, clearing selection.
For a bounded test add `--auto-demo --duration 40`; run
`bench/sim/verify_mavros_visual.py NEW_VISUAL_DIR` after completion.
For the recorded response add `--replay PREPARED_DIR --replay-fps 20
--replay-hfov 1.2 --initial-point 661 396 --auto-demo --duration 26` and use
`verify_recorded_response.py`, not the closed-loop verifier.

API/image responses and JS syntax were checked. Browser automation reported
`No browser is available`; layout/click execution was not claimed as tested.
UI changes are existing local console controls/diagnostics, not external hosting.

## Next gates, in order

1. Native inference -> ROS authority through local on-board ingress, preserving
   original capture/source identity and deadlines. Remove the simulation PC
   round trip before considering a standalone FC integration complete.
2. Split resize/motion timing; optimize measured work with exact-output regression.
   Prioritize the selected person's embedding and preserve last verified geometry
   only as a search/computation hint, never control evidence. Keep competing-
   identity checks; do not repair crowd tests by weakening ambiguity gates.
3. Repeat fixed acquisition / crowds / fast motion / occlusions with evaluator-
   only ground truth, end-to-end age, false locks and reacquisition timing.
   Fine-tune YOLO only for demonstrated model-limited cases, with held-out splits.
4. Identify actual FC hardware/firmware and transport. First read-only telemetry,
   then an explicitly authorized propellers-removed bench session. Verify mode
   transitions, coordinate frames, link loss, stale vision, operator takeover,
   FC restart, reconnect and no-auto-rearm. No current script accepts a real FC.
5. Reproducible Yocto/meta-ros packaging and licensing review; then physical
   acquisition clocks, camera calibration/range, power/thermal soak and outdoor
   validation. Simulation depth is not physical ranging or obstacle avoidance.

Strongest counterargument: a forgiving simulated single-person scene and a PC
supervisor can conceal exactly the latency, target ambiguity and recovery
failures that matter on a moving aircraft. The failed aerial/crowd runs support
that objection. Communication works; robust autonomous flight is **not proven**.
