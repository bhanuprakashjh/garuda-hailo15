# Garuda visual follow demo — 2026-09-13

## What exists now

A **real rendered-camera visual loop**, not the earlier desk-camera/yaw-only
transport test:

```
Gazebo X500-mounted RGBD camera (1280×720, configured 20 Hz)
  → latest-frame PC RGB→NV12 conversion
  → bounded SSH stream to the physical Hailo-15L
  → actual YOLO11s HEF + DSP full-view/tiles/ROI + OSNet + fresh Tracker
  → exact-frame result, identity/freshness gates, aligned simulated depth
  → loopback MAVLink to owned PX4 SITL
  → simulated drone motion changes subsequent camera pixels
```

The local Follow Console shows the actual drone image and its matching boxes,
a separate rendered world-camera view, selected identity, ingress age,
inference time, real-time factor, range, flight state, and event timeline.
Controls are beside the main video. Select, Take off, Follow, Hold, Release,
Land, a two-second perception dropout, and Stop demo use the real backend.
No cloud hosting or external vehicle-control endpoint was created.

**This is a functional visual SIL demo, not robust continuous following or
flight qualification.** It still spends substantial time holding because
perception cannot consistently meet the unchanged freshness budget.
The previously failed crowded-person real-pixel gate remains failed.

## Run it on this PC

Working tree:
`/media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking`.
The world needs the installed PX4/Gazebo stack and the cached Mingfei actor v1.
See [dependency/asset attribution](dependencies/gazebo-follow-bench.md).

Interactive console, initially **disarmed**:

```bash
GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh --out /tmp/garuda-visual-demo-01
```

Use a new output directory on every run. Open **http://127.0.0.1:8100/** on this
PC, not the board address. Wait for camera/PX4 startup, press Take off, then
select a detected person and press Follow. Takeoff waits for the owned PX4
instance's health-ready message and verifies armed/OFFBOARD altitude telemetry.
The actor initially stays in place, then walks and turns along the path.

Reproducible automatic trial:

```bash
GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh \
  --out /tmp/garuda-visual-trial-01 --auto-demo --duration 60
python3 bench/sim/verify_gazebo_follow.py /tmp/garuda-visual-trial-01
```

Automatic mode selects only a sole detected, unambiguous person, never an actor
coordinate. It injects a two-second perception pause after takeoff, then lands.
Operator Hold is sticky even during the automatic trial; Follow is explicit.
An automatic trial does not become a repeat-flight loop after landing.

Stop demo (or Ctrl-C) requests simulator landing, closes the board stream and
terminates only the owned simulation processes. The wrapper restores the desk
app **if it was running when the demo started**. Its selection is cleared by
restart. The wrapper's restoration path has been exercised by completed trials.
After restoration, the desk page is http://10.0.0.1:8099/ .

Direct `bench/sim/gazebo_follow.py` is lower-level: it does not pause/restore the
desk app. Use the wrapper for ordinary operation. Do not run both inference
programs against the board NPU simultaneously. No other PX4 process may already
be using the simulator's default MAVLink ports.

## Board deployment and rollback

The existing `/opt/garuda-fresh/garuda-fresh-tracking`, `current.json`, HEFs and
ISP configuration files were not replaced. No OS, driver, sensor mode, boot
configuration, or HailoRT update was installed.

The new experimental executable is staged separately:

- `/opt/garuda-sim/garuda-causal-stream`
- `/opt/garuda-sim/profile.json` — copied from the verified desk follow profile
- previous experimental executable retained as `garuda-causal-stream.a558ca6c`

The stream program shares the actual inference/identity/tracker loop with
`hosts/hailo15l/causal_replay.cpp`; `--stream` adds bounded live input and
frame-referenced selection commands. Recorded replay mode is retained.
This is **not** the live IMX678/ISP capture path. Its motion image uses the
existing replay resize path, and host transfer adds latency.

Final staged stream SHA256:
`dfc0e6208c0d1b34a1a403f7ef7e95e950689596a6f65ce97aafc4e03f7f5a74`.
Earlier trials used `a558ca6cea2d8de802b10a250678bd4835543290896888430f33833277efee19`;
the final change corrects stream selection/status reporting, not inference.

Pre-simulation full desk-directory backup:
`/media/bhanu1234/Development/hailo-export/gazebo-follow-20260913/rollback/garuda-fresh-before-sim.tar`.
SHA256 `1571b7172fa7271fac87f38fb3ceccdb57548eb62b4335d77611b0e72ae320f6`.
Its 46-entry listing and embedded desk executable hash were verified.
This backup contains the **post-fix** desk binary, unlike the older pre-fix
archive documented in the previous handoff. Neither backup was deleted.

Desk restart preserves configuration files but clears runtime target selection.
Exact live sensor-register/exposure state was not independently compared across
restart; do not interpret file preservation as a camera-register audit.

## Timing and control contract

- One in-flight board request; the host retains the latest camera frame, not an
  unbounded FIFO. Input is one bounded JSON header and exactly one NV12 image.
  Non-increasing IDs, bad image sizes, oversized headers/results and timeouts
  fail closed. Each result is checked against the submitted frame ID.
- The UI retrieves JPEGs by that result's sequence. Expired JPEGs return 410;
  they are not replaced by a newer, mismatched image. Overview is a separate
  live camera and is **not** claimed to be synchronized with the detection view.
- Board ingress timing is preserved for diagnostics. The control envelope is
  re-expressed on the PC monotonic clock, from actual PC image ingress to result
  receipt. This includes conversion, transfer and inference exactly once.
  Queue/JPEG time before the controller consumes the result is also charged.
- PC ingress is **not exposure time**. A separate advancing Gazebo-clock gate
  rejects old simulation stamps and paused/reset clocks; this is not a certified
  simulation-exposure-to-wall-time mapping. No board/PC clock-offset estimate is
  fabricated. A validated acquisition-age contract remains work to do.
- `PerceptionAuthority` / `FreshFollow` remain responsible for identity binding,
  uncertainty, freshness and intent TTL. Consumer freshness stays **200 ms**;
  intent TTL remains at most **150 ms**, bounded by remaining observation life.
- Publisher is configured for **20 Hz**, independent of SSH inference. Stale,
  ambiguous, unselected or expired targets produce hold, never extrapolated
  chase commands. No actor trajectory/pose is subscribed to by the controller.
- Translation requires exact-timestamp depth from the **same RGBD sensor and
  projection**. Central torso samples must be finite and sufficiently consistent.
  Without accepted depth, a valid target can command yaw only.
- Default simulated standoff is **6 m**; forward speed is bounded to **1 m/s**,
  backward to **0.5 m/s**, yaw to **0.8 rad/s**, altitude held at **2 m**.
  Large horizontal target error suppresses translation while turning.
  Those are configuration limits, not achieved performance claims.
- All MAVLink runs require `GARUDA_SIM=1`, loopback UDP, the configured PX4
  executable, and a direct owned child PID. No physical flight controller is
  connected or commanded. Fresh isolated simulator rootfs/parameters and a
  unique Gazebo transport partition are used per run.

## What testing established

Evidence: `bench/results/2026-09-13-gazebo-visual/`; full working artifacts and
earlier unsuccessful iterations remain under
`/media/bhanu1234/Development/hailo-export/gazebo-follow-20260913/`.
Per-run versions files pin source hashes even when the git tree was uncommitted.

Two pre-final complete trials (`visual-native`, `visual-aes`) independently
passed the log verifier: real motion, selected-source/sequence binding, no
over-age or over-limit motion, paired-depth translation, dropout hold/recovery,
and final observed disarm. The final staged-binary repeat also passed: 617 unique
inference frames, 415/1194 non-hover follow ticks, maximum follow displacement
6.472 m, ingress-to-result median/p95 127.768/227.880 ms, processing
90.246/185.596 ms, real-time-factor median 0.99365. All 31 evaluated dropout
ticks held, command recovery occurred, and final telemetry confirmed disarm.
This is **34.8% command eligibility**, not continuous robust following.

| Measured result | Native pixels / default SSH | Native pixels / AES-GCM |
|---|---:|---:|
| Ingress → result median / p95, ms | 132.792 / 235.207 | 130.038 / 229.925 |
| Board processing median / p95, ms | 90.174 / 185.651 | 90.432 / 185.746 |
| Non-hover follow ticks / total | 386 / 1194 | 377 / 1190 |
| Maximum displacement from follow start, m | 6.331 | 6.044 |
| Sim real-time factor, median | 0.99343 | 0.99379 |
| Dropout-window ticks, all held | 31 | 30 |
| Landed/disarmed and recovery | yes | yes |

These are individual trials, **not a controlled detector-accuracy A/B**.
AES-GCM is now explicitly configured; hardware AES is available on the board.
The small timing difference does not establish an overall performance gain.
Substantial command ineligibility remains, mostly associated with age and
periodic multi-pass detection. Calling these results “robust tracking passed”
would be incorrect.

PC conversion micro-test: 30 calls on the same seeded 1280×720 RGB8 array,
NumPy median **32.3745 ms**, native median **2.97555 ms**. The output matches
the original BT.601 limited-range NumPy conversion **byte for byte**, including
chroma averaging. Native conversion also matches reference bytes in unit tests
at small and full resolutions. This optimizes host format conversion, not YOLO.

Validation: seven native tracker CTests; 46 tracking Python tests (one skipped),
24 follow tests, seven bridge tests; 15 new visual-SIL tests. ARM stream build
completed against the installed SDK. Existing six-scenario SIH evidence was
re-verified, not re-labelled as rendered-camera testing. Shell syntax and
console JavaScript parsing passed. HTTP source/Host/Origin/action routes were
tested; camera images were inspected directly. No automated browser click/
layout QA was available. Optional WebMCP tools are feature-detected but their
browser registration/execution was **not** verified.
Thermal/power state was not continuously logged; a later under-load spot read
is in the benchlog, not evidence that every trial was unthrottled.

An additional HTTP operator check verified sticky Hold during auto mode and
Stop → observed disarm → desk restoration. After a long Hold, the selected
person was no longer observed and identity memory expired. A subsequent Follow
request produced **no eligible motion**; this is safe refusal, not successful
reacquisition. That trace is retained as `operator-check`, not hidden as a pass
of long-loss tracking. The final GUI also labels over-age boxes amber/stale.

## Failures encountered and fixed (not hidden)

1. First render run: missing ground-station heartbeat blocked stock PX4 arming.
   Added the console heartbeat; did not disable preflight checks.
2. First visual run: position appeared before attitude telemetry; the bridge
   correctly rejected stale telemetry. Wait for both before priming.
3. Another startup armed before heading health settled and was denied. Wait for
   this owned PX4 instance's health-ready report; no forced arm/parameter bypass.
4. Initial timing double-counted board processing. Re-envelop measured elapsed
   time once, then separately charge the controller's consumption delay.
5. Background result timestamps could precede a prior controller tick. Charge
   queue delay at ingestion instead of presenting an old receiver timestamp.
6. NumPy format conversion was a measured host bottleneck. Native exact-byte
   conversion removes most of it without changing pixels or the model.
7. Early evidence dropped the final disarmed tick and truncated old events from
   a UI-sized deque. Persist a complete event JSONL and the terminal tick.
8. Auto-demo originally could undo operator Hold. Automatic follow is now a
   one-time initial action; Hold remains sticky and urgent commands supersede
   queued follow/selection requests.

## Next work, in order

1. **Latency/scheduling ablation on identical source pixels.** Compare full-view
   only, full-view + local ROI, and periodic tiled refresh. Quantify detection
   recall, wrong-target risk and eligible command coverage together before
   changing shared scheduling. Do not enlarge the age limit to mask latency.
2. **Acquisition-time provenance.** Validate simulation frame generation to PC
   monotonic time and report capture-to-command age, not just ingress age.
3. **Independent ground truth.** Add an evaluator-only path for identity/box and
   distance error; it must never enter the perception/controller input. Current
   verifier checks contracts, not whether every box belongs to the right person.
4. **Crossings, physical occluders, rotations, smaller targets, fast camera
   motion and vehicles.** These visual scenarios are not yet qualified. The
   existing headless SIH six-scenario suite is not a substitute.
5. **Outdoor/physical integration only after those gates.** Simulated RGBD is
   not physical-camera metric depth or obstacle avoidance. Real flight needs
   calibrated sensing, vehicle-state quality, independent failsafes, and a
   separately authorized hardware bridge.

Structural review: no ROS stack, alternate detector, external web deployment,
new service dependency or model weight was introduced. The world, host format
adapter, console and evaluator remain bench modules; the desk tracker/bridge
algorithms were not forked to manufacture a successful simulation result.

## 2026-09-15 addendum — aerial profile and model readout

- `run_grand_demo.sh replay|gazebo OUT [PREPARED] --aerial` runs the staged aerial profile
  (`hosts/hailo15l/sim/profile-aerial.json`: VisDrone fine-tuned HEF, wide caps, 1500/2000
  follow schedule, adaptive tiles + ROI) instead of `profile-fullview.json`. Both profiles and
  the stream binary are staged by `hosts/hailo15l/stage_sim_stream.sh` from the fresh build.
- The console's camera panel names what the board runs (model hash, schedule, this frame's
  crop state); `versions.json` records the staged profile and its HEF hash.
- `--select-retry-s S` repeats the auto-demo's initial click for S seconds until a lock exists
  (the campaigns' labelled retry). Default 0 keeps the frozen one-click protocol.
- `bench/sim/console_capture.py OUT.jsonl` records the console state per board frame.
- Measured on VisDrone-SOT 086 (`bench/results/2026-09-15-demo-aerial/`): the aerial profile
  holds the target (59 control-valid frames vs 5), but in replay mode no profile passes the
  200 ms receiver gate — PC transport adds 150–250 ms to the board's own age — so the demo
  remains a bounded heading response, not motion.
