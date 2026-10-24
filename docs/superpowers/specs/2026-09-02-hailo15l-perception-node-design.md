# Hailo-15L perception node with garuda-mono parity — design

**Changelog:**
- 2026-09-03: M2 implemented on branch `feat/hailo15l-detector` (plan
  `docs/superpowers/plans/2026-09-03-hailo15l-perception-node-m2-detector.md`) — numbers in
  `bench/benchlog.md` "2026-09-03 — Hailo-15L SBC: M2 yolo26m detector".
- 2026-09-02: transport changed from ZeroMQ to framed TCP (shim is stdlib-only; pyzmq absent on the board).
- 2026-09-02 (M0 as built): the node runs the board's `hailo_yolov8n_384_640.hef`, not the
  `hailo_yolov8s_384_640.hef` this spec named for stage zero (§1, §5, §8). Both HEFs ship on the
  board (`/home/root/apps/shared/resources/`); yolov8n drove the M0 pipeline proof and
  `bench/benchlog.md` carries `hailortcli benchmark` numbers for both. §5 corrected below; the §1
  and §8 mentions are left as written and are superseded by this line.
- 2026-09-02 (M0 as built): the node does **not** log to syslog. The SysV init script redirects the
  node's and shim's stdout/stderr to `/var/log/garuda-perception.log` (a tmpfs, so it clears on
  every boot); syslog integration is deferred past M0. §6 corrected below.
- 2026-09-04: §8.2 "Locked-target tracker (follow core)" added — the owner's direction (follow is the main goal) and the design review of the lock (identity vs observation, time-based windows, guarded re-acquisition, visual tracker, appearance templates, DSP ROI, click–frame sync, ego-motion, lock-focused benchmark); plans F1–F6.
- 2026-09-03 (later): M2 design approved by the owner and written into §8 item 3 (model-zoo
  `yolo26m` for `hailo15l` + our own post-process plugin porting the Pi's decoder, letterbox
  640×640, parity tests incl. a real-tensor golden, deploy models step + rollback config; runtime
  switching / yolo-world / recompile out of scope); §8 item 4 (M3) rewritten as monocular depth on
  the single IMX678 with the zoo route first; new §8.1 records the owner's roadmap after M4 (follow
  via the DSP's zoom/GMV/motion-detection features, then a small VIO with its prerequisites).
- 2026-09-03: Milestones re-sequenced after M0 (owner decision 2026-09-02): M1 = tracking and lock
  parity; M2 = our yolo26m detector + post-process; M3 = depth, calibration, distance; M4 =
  packaging and the Pi-vs-15L delta table.

Date: 2026-09-02. Status: owner-approved design (sections reviewed in session), spec reviewed and amended.
Scope decision: owner chose "perception node, portal consumes it" over a full mono clone and over a
two-box-only demo. Implementation approach: native C++ node on Hailo's analytics framework plus a
thin Python-stdlib shim (approach A).

## 1. Context (measured 2026-09-02, see bench/versions.md and docs/decisions.md)

- Board: **Hailo-15L SBC rev 2.x** (not the 15H EVB the plan assumed). 4× Cortex-A53 @ 1.1 GHz,
  2 GB RAM of which ~1.25 GB is CMA for video buffers (~600 MB usable), 7.3 GB eMMC, 2× 4-lane
  CSI-2, ISP with HDR/AI-ISP, hardware H.264/H.265 encoder, Tensilica DSP, integrated Hailo-15L
  NPU. Stock image `vpu-stability-v1.12.0` (kernel 5.15, poky kirkstone), HailoRT 5.3.0 —
  the same HailoRT line as the Pi bench and the PC's DFC. No PTP hardware clock. Camera: IMX678.
- The board's native pipeline framework is `hailo_analytics` (C++): front-end source from the media
  library, `HailortAsyncStage` inference, post-process plugins, tracker stages, sinks for ZeroMQ,
  RTP/UDP, WebSocket, file, and an in-process app sink. GStreamer carries the media-library
  elements only (no TAPPAS `hailonet`). Python 3.10 on the board has the standard library and
  PyGObject but **no NumPy, OpenCV, or HailoRT bindings**, and Hailo packages no pyHailoRT for
  this SoC. The SDK sysroot ships NumPy/OpenCV headers and libs for cross-builds only.
- The Pi's `garuda-mono` (`hosts/pi5/garuda_mono.py` + `hailo_yolo26*.py`, `mono_state.py`,
  `services/garuda-track`) is Python on NumPy/OpenCV/pyHailoRT with frames from `rpicam-vid`.
  The portal (`services/garuda-portal/mono_client.py`) consumes exactly the v2 snapshot schema from
  `mono_state.build_snapshot` over `GET /api/events` (SSE), pulls MJPEG through its own client
  loop, and POSTs `/api/mono_click`, `/api/mono_target`, `/api/mono_calibrate[_reset]`,
  `/api/detector`, `/api/depth_engine`. `GARUDA_MONO_URL` selects the mono host.
- Model artifacts on the PC: `hailo-export/work/{yolo26m,yolo26m-depth,yolo26n-depth}_hailo_model/`
  (Hailo-10H HEFs, metadata, calibration set `datasets/depth-calib.yaml`); DFC 5.3.0 accepts
  `--hw-arch hailo15l`. The board carries `hailo_yolov8s_384_640.hef` with on-chip NMS and
  `libyolo_hailortpp_post.so`.

## 2. Goals and non-goals

Goals
1. The SBC runs the whole perception core — capture, ISP, detect, track/lock, depth, distance —
   and the unchanged `garuda-portal` shows it by pointing `GARUDA_MONO_URL` at the board.
2. Behavioural parity with mono where it matters: same snapshot schema, same lock/coast/re-acquire
   behaviour (owner-verified on the Pi), same distance-from-depth and calibration maths.
3. Measured Hailo-15L numbers next to the Pi's in one delta table (rule 1: harness-run only).
4. First product-tier packaging: recipe stubs in `yocto/meta-garuda/`, board code behind the
   plugin interfaces so Pi mono and the SBC node are two implementations of one contract.

Non-goals (version one)
- Open-vocabulary (`world`) and `pose` detector modes; DepthAnything depth engine on the 15L.
- The global-shutter IMX296 pair (no driver in this BSP; separate port).
- A custom Yocto image build; PTP/time-sync work on the SBC (no hardware clock).
- Any change to the portal.

## 3. Architecture and components

Three processes; two new on the board, one existing.

- **`garuda-perception`** (C++, SBC, `services/garuda-perception/`). One `hailo_analytics`
  pipeline: media-library front end → HailoRT detect stage → our post-process → ported ByteTrack +
  lock FSM → HailoRT depth stage (only while locked) → distance → outputs. Outputs: v2 JSON snapshot
  per processed frame on a framed TCP feed (127.0.0.1:8971, `S` frames for snapshots), JPEG frames
  on the same feed (`J` frames, capped at 15 fps), hardware H.264 over RTP to a configurable host:port
  (off by default). Commands arrive on a JSON-lines TCP command socket (127.0.0.1:8972) as small JSON objects.
- **`garuda-mono-shim`** (Python standard library only, SBC, `services/garuda-perception/shim/`).
  Consumes the framed TCP feed (8971), serves mono's HTTP contract on port 8098 (`GET /api/events` SSE
  throttled to ≤10 Hz, `GET /api/state`, `GET /stream` MJPEG, the POST commands), forwards commands
  over the TCP command socket (8972). No NumPy/OpenCV.
- **`garuda-portal`** (unchanged, PC or Pi).

Board-specific pieces live in `hosts/hailo15l/`: the front-end binding (the `ICaptureBackend`
implementation for the media library), the SysV init script, the deploy script, and the config
template. Pipeline logic, post-process, tracker port, distance, and the shim are host-agnostic and
live in `services/garuda-perception/`. `IDepthSource` is implemented by the depth stage wrapper.

## 4. Data flow and contracts

Per frame:
1. **Front end.** IMX678 at 4K 30 fps through the ISP; the DSP multi-resize emits three copies:
   full resolution → H.264 encoder; **1280×720** → JPEG and the coordinate frame; the detector
   input. Letterbox to the detector's square input if the resize stage supports padding, else the
   squash resize (`lb=None` legacy path) that mono's post-process already handles. Decided in M0
   and recorded.
2. **Detect.** `HailortAsyncStage` with the yolo26m HEF for `hailo15l`; post-process = sigmoid on
   class scores, ltrb × stride, light NMS — a C++ port of `hailo_yolo26.py`.
3. **Track/lock.** `services/garuda-track/bytetrack.py` and `lock_fsm.py` ported line for line
   (coast + 5-frame re-acquire, `select_by_point` for click-to-lock).
4. **Depth/distance.** yolo26m-depth HEF at 768² input while a lock exists; depth =
   `exp(clip(logit, −4, 5)) ** cal_a * exp(cal_b)`; distance = median depth inside the locked box.
   Calibration points persist in `/opt/garuda/state/mono_cal.json`.
5. **Outputs.** Snapshot keys exactly `mono_state.build_snapshot` v2: `v, age_ms, tracks[{id,label,
   conf,x,y,w,h,coasting}], lock{id,class,coasting}, distance{raw_m,est_m,valid}, depth_engine,
   detector{mode,prompt}, cal{n,fit}, frame{width,height}, gesture{name,track_id,held_ms}`. Boxes in
   1280×720 pixels; `frame` reports 1280×720; `gesture` is always the empty object; `age_ms` is
   measured from the front end's buffer timestamp (CLOCK_MONOTONIC).

Commands (JSON-lines TCP): `{"cmd":"lock_point","x":..,"y":..}`, `{"cmd":"target","class":..}`,
`{"cmd":"cal_add","true_m":..}`, `{"cmd":"cal_reset"}`, `{"cmd":"detector","mode":..}`,
`{"cmd":"depth_engine","engine":..}`. Reply `{"ok":true}` or `{"ok":false,"error":"..."}`.
Shim mapping: `/api/mono_click?x&y` → `lock_point`; `/api/mono_target` → `target`;
`/api/mono_calibrate` → `cal_add`; `/api/mono_calibrate_reset` → `cal_reset`;
`/api/detector?mode=` → `detector`; `/api/depth_engine?engine=` → `depth_engine`.

Parity gaps, reported not hidden: `detector` accepts only `primary` (others → HTTP 501 with an
explanatory body); `depth_engine` accepts only `y26d` (others → 501). The snapshot always reports
`detector.mode="primary"`, `depth_engine="y26d"`.

## 5. Models and the bench gate

- **Stage zero:** a stock board HEF + `libyolo_hailortpp_post.so` drive M0 so every downstream
  stage is built against real detections before our HEFs exist for this chip. **M0 as built uses
  `hailo_yolov8n_384_640.hef`**; `hailo_yolov8s_384_640.hef` is on the board too and both are
  benchmarked in `bench/benchlog.md`.
- **yolo26m detect (15L):** DFC 5.3.0 on the PC, same model script and calibration set as the
  10H build, `--hw-arch hailo15l`. Model card `models/yolo26m_h15l.md`.
- **yolo26m-depth (15L):** same PTQ recipe as the production 10H build (optimisation level 2,
  1024-image calibration, `depth-calib.yaml`). Probe gate unchanged: logit std must clear the
  ~0.04 collapse signature before deploy. Model card `models/yolo26m-depth_h15l.md`.
- Licence: yolo26 family is AGPL-3.0 — bench/evaluation only, `not-product-cleared` (owner
  relaxation 2026-08-02); never wired into a shippable service.

Measurement (all into `bench/benchlog.md` with a `versions.md` snapshot; no unmeasured figure
anywhere): `hailortcli benchmark` (hw-only, streaming, latency) per HEF on the board; node
end-to-end snapshot rate, CPU load, RAM headroom, die temperature over a 10-minute run; the Pi's
existing numbers beside them in one delta table.

Gate (a target, not a measurement): **≥15 snapshots/s with a lock active** (detect + depth every
frame) and no thermal throttling. If yolo26m misses it, the fallback is explicit and recorded:
smaller yolo26 variant, or depth on alternate frames — whichever the numbers justify. 15L results
are a floor for the 15H, never an estimate of it.

## 6. Build, deploy, packaging, operation

- **Build:** cross-compile with the SDK installer from the Vision Processor package (target
  sysroot = the board's exact libs: HailoRT 5.3.0, `hailo_analytics`, media library, nlohmann/json).
  CMake + one toolchain file; unit tests build natively on x86 for CI. Shim needs no build.
- **Deploy:** `hosts/hailo15l/deploy.sh` copies binaries, shim, HEFs, config to `/opt/garuda/` over
  SSH, installs the init script, restarts services. Idempotent; the stock image is otherwise
  untouched (the burn-in recorder removal of 2026-09-02 is already done and recorded).
- **Run:** SysV init script `garuda-perception` ordered after `isp_media_server`; the node checks
  the ISP server at start and retries with back-off (the boot-time OOM race is real), logging the
  event. Config = one JSON file (camera profile, HEF paths, TCP feed/command ports, RTP destination,
  state path). The init script redirects the node's and shim's stdout/stderr to
  `/var/log/garuda-perception.log`; syslog integration is deferred past M0.
- **Network:** PC profile `h15-link` (10.0.0.2/24, autoconnect priority 10) ↔ board 10.0.0.1;
  portal via `GARUDA_MONO_URL=http://10.0.0.1:8098`. `pi-share` returns the wired port to the Pi.
- **Packaging:** skeleton recipes `yocto/meta-garuda/recipes-garuda/garuda-perception/` and
  `garuda-mono-shim/` (licence, SRC_URI stub, DEPENDS on Hailo's public layers); unbuilt.
- **Licences:** `hailo_analytics` and the media library are Hailo proprietary SDK components used
  under the developer licence (record in decisions.md); nlohmann/json MIT; our code
  under the project licence. CI licence scan remains a hard stop.

## 7. Testing

- **Unit (x86 CI):** post-process, tracker, lock FSM, distance maths — each compared against
  recorded outputs of the Pi's Python on identical inputs (parity as a test). Shim SSE/MJPEG
  framing against a fake publisher.
- **Integration (board):** a recorded raw video replayed through the framework's file source so
  the node runs deterministically without the camera.
- **Goldens (M2):** `tests/golden/yolo26_golden.json` (synthetic sparse cases decoded by the
  byte-identical Pi decoder, `test_yolo26_decode`) and `tests/golden/yolo26_real_frame.{bin,json}`
  (one real frame's six raw UINT16 tensors dumped on the board, `test_yolo26_real`).
- **Bench:** section 5 harness plus a live portal session: click-to-lock, coast, re-acquire,
  distance readout. Hardware-dependent tests carry `@requires_hw(hailo15l)` so CI skips cleanly.

## 8. Milestones (each ends runnable, with a benchlog entry)

1. **M0 — pipeline proven.** Node on stock yolov8s; snapshots + JPEG over framed TCP; shim serving
   them; portal shows live detections from the board. First benchmark numbers.
2. **M1 — tracking and lock parity.** Tracker/lock ported.
3. **M2 — our yolo26m detector + post-process** (design approved by the owner 2026-09-03). The
   detector is Hailo's model-zoo `yolo26m` compiled for `hailo15l` (release line v5.3.0, the same
   lineage as the Pi's production HEF; fetched + benchmarked 2026-09-03, `models/yolo26m_h15l.md`),
   not a local recompile. It exposes six raw heads (no baked NMS), so the node gets its own
   post-process plugin `libyolo26_post.so` (the `init`/`filter`/`free_resources` ABI the post
   stage loads by name): dequantise the UINT16 tensors with the vstream zero-point/scale, decode
   exactly as `hosts/pi5/hailo_yolo26.py` does (ltrb×stride, sigmoid, per-class greedy NMS at
   IoU 0.5), score floor = `track.conf_floor` (0.15) so ByteTrack's low band becomes live, COCO-80
   names as the portal expects. Detector input becomes 640×640 with the media library's
   `LETTERBOX_MIDDLE` scaling mode (mono's preprocessing); the detection callback un-maps boxes
   through the pad/scale computed from config. Parity: byte-identical copy of the Pi decoder + its
   unit cases ported to C++, plus a real-tensor golden (six raw tensors dumped on the board, decoded
   by the Python on the PC, asserted equal to the plugin's output). Deploy gains a models step
   (HEF, plugin, post config under `/opt/garuda`), the stock yolov8n configuration stays as a
   second config for one-flag rollback. Bench: end-to-end rate + CPU vs M1, the NPU-only
   `hailortcli` number as the ceiling. Out of scope: runtime model switching (the `detector`
   command stays a stub), yolo-world, custom-calibration recompile (would carry baked NMS and a
   different post path — a separate task if ever wanted). Status: implemented 2026-09-03 —
   numbers in bench/benchlog.md '2026-09-03 — Hailo-15L SBC: M2 yolo26m detector'; the
   snapshot-age regression noted there is being addressed in the branch's final fix wave.
4. **M3 — depth, calibration, distance.** Monocular depth on the board's single IMX678 (the Pi's
   single-camera depth path, not the OV9281 stereo rig): a depth model for `hailo15l` — try the
   model zoo first, the same fetch/parse/benchmark route as M2, recompile only if the zoo has
   nothing suitable — probe-gated; relative depth + calibration fit to metres; distance to the
   locked track; the colour-coded depth map served to the portal's mono depth tab; section 5 gate
   measured with the detector sharing the NPU (rates will drop — measure, do not promise) and the
   fallback decided.
5. **M4 — packaging and the Pi-vs-15L delta table.** Init + deploy scripts, recipe stubs,
   10-minute thermal run, Pi-vs-15L table, CLAUDE.md §2/§7 updated.

### 8.1 Roadmap after M4 (owner direction, discussion of 2026-09-03 — recorded so it is not lost)

**Status (2026-09-04):** the owner set object detection/tracking/follow on the drone as the main
line; M6 (VIO) and whatever remains of M3/M4 are parked until follow works on the drone
(`docs/decisions.md` 2026-09-04).

The owner's stated goal for the board: object tracking/follow for the drone, then a small VIO.
Not scheduled yet; each becomes its own spec/plan when its turn comes.

- **M5 — follow, using the DSP.** Today the DSP path is used for one thing only: the multi-resize
  front end (640×384 detector stream + 1280×720 JPEG stream, bilinear NV12); M2 adds the letterbox
  scaling mode. The deployed profile (`hosts/hailo15l/medialib/profile/application_settings.json`)
  carries, switched off: digital zoom (magnification mode), optical zoom with dewarping (up to 3×),
  rotation/flip, motion detection (sensitivity + threshold), and ISP global motion vectors (GMV).
  Plan of record: (1) a spike that enables digital zoom and measures latency and frame-rate cost on
  this board (rule 1 — nothing about DSP cost is measured yet); (2) "zoom window on the lock": a
  DSP crop+scale around the locked box feeds the detector a full-resolution window of the target
  (range for small/far targets at unchanged NPU load), the tracker stays in full-frame coordinates;
  (3) GMV as an ego-motion prior for the tracker's prediction during coasting; (4) motion detection
  as a loiter-mode wake-up gate (detector at reduced rate until something moves). Dewarp/stabilisation
  are held until the GS cameras and VIO. The tracker half of follow landed early, ahead of the DSP
  work above: the SDK's Kalman `TrackerStage` engine behind the same lock rules, with a person-only
  profile (`classification_id`, majority-vote labels) the owner has set as the follow default —
  bench-measured in `bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: Kalman tracker engine (SDK
  TrackerStage) vs mono's tracker — phone and person routines".
- **M6 — VIO groundwork on the 15L.** Constraints stated up front: the IMX678 is rolling shutter —
  fine for a slow-motion demo VIO and for pipeline development, but the project's VIO-grade cameras
  are the IMX296 GS pair (1.8 V trigger rework required; CLAUDE.md §2); the IMU arrives from the FC
  over DDS and the SBC has no hardware PTP clock, so camera-IMU timestamping (Phase 3 work) must
  exist before any drone-rate VIO number means anything; 4× A53 @1.1 GHz / 2 GB will not run a
  heavy CPU VIO — the intended shape is a learned front end on the NPU (SuperPoint-class features,
  published for the Hailo-15 line) feeding a licence-clean C++ back end (Basalt; the hybrid-SLAM
  workstream's "path B"). First task, per the P4 gate: EuRoC replay on the board, recording fps and
  per-stage ms, before any live attempt. Licence line unchanged: ORB-SLAM3 / OpenVINS / VINS-Fusion
  are GPL and bench-only; anything that ships is Basalt or equally clean.

### 8.2 Locked-target tracker (follow core) — design adopted 2026-09-04 (owner direction; reviewed in session)

> **STATUS (2026-09-04): F1 implemented and bench-measured 2026-09-04 (benchlog "Hailo-15L SBC: F1
> lock core"); F2–F6 pending.** `LockCore` (time-based states, prediction never published, guarded
> re-acquisition, identity-vs-observation separation, all per this section) is in the core library and
> wired into the node, branch `feat/hailo15l-kalman-tracker` (final commit `47fb866`, four on-board fix
> rounds after the board came back) — see `docs/decisions.md` 2026-09-04 "F1 lock core" for the
> mechanism and the Rulings that tuned it, `hosts/hailo15l/README.md` §10 for the published snapshot
> fields, and `bench/benchlog.md` 2026-09-04 "F1 lock core" for the lock-focused harness
> (`bench/evidence/2026-09-04-lock-core/lock_metrics.py`) and owner routines (`ROUTINES.md`). Three of
> five owner routines are measured on fresh captures (walk-out/return, occlusion, fast lateral — numbers
> in the benchlog "Results" table); the two-person swap routine was skipped (no second person
> available) and the phone/all-classes routine is pending — both stay `TBD-bench`. Integration of this
> branch is pending the owner. F2–F6 below remain unbuilt.

**Why.** Measured on 2026-09-03 (benchlog "Kalman tracker engine … phone and person routines"): the
lock is a detector-generated multi-object-tracker id, so it inherits every id split; after the
re-acquire delay the resolver takes the highest-confidence live object of the same class anywhere
in the frame, which transferred the lock silently (the "knife"/"tv" lock, the 22-id person run);
frozen coasting hides but does not fix this; `max_lost`/`reacq` are frame counts whose meaning
changes with the detector rate (25 vs 30 fps). Tuning Kalman/IoU gates does not address any of it.

**Architecture.** Full-frame detector + multi-object tracker (either engine) → the user (or the
default class) locks an object → a dedicated locked-target tracker owns it → the detector verifies
and corrects it, periodically full-frame. Identity and observation are separate: the system may
remember which object is locked while admitting it cannot currently see it.

- **States:** `CONFIRMED → VISUAL_TRACK → OCCLUDED → REACQUIRING → LOST` (plus `NONE`).
  `VISUAL_TRACK` = held by the visual tracker between detections (F2); before F2 the core moves
  CONFIRMED → OCCLUDED directly.
- **Time, not frames:** all windows in milliseconds from the frame's ISP timestamp: the
  control-valid observation age, the short occlusion window, the re-acquisition window, the final
  expiry.
- **Prediction never reaches the screen:** motion is predicted internally (Kalman: centre, size,
  velocity) for gating and search; the published box is the smoothed box only when CONFIRMED (or
  VISUAL_TRACK), the last confirmed box frozen while OCCLUDED/REACQUIRING, none when LOST.
- **Guarded re-acquisition:** a candidate must match the predicted position (gate widening with
  uncertainty), the expected size/aspect, the motion history and — from F3 — the stored
  appearance; class is a soft hint. Search near the prediction first, expand with uncertainty,
  full-frame only after local search fails and only with appearance confirmation. If two
  candidates are ambiguous, report OCCLUDED/UNCERTAIN; never choose. No tracker claims it found
  the same object after a long disappearance without strong identity evidence.
- **Appearance (F3):** two templates — immutable from the original lock, and a slowly updated
  recent one — updated only when detector, tracker and motion agree; frozen during overlap with
  another track, low confidence or rapid class change. Colour signature first; no re-ID network on
  this NPU for now.
- **Visual tracker (F2):** sparse optical flow (or a correlation filter) on the detector-input
  patch every frame between detections, on the CPU (OpenCV 4.5.5 is on the image; if the `video`
  module is absent, ship it under `/opt/garuda/lib` or implement LK); the detector verifies.
- **Locked-object ROI (F4):** crop a larger region around the prediction from the high-resolution
  image (the DSP's crop+scale, zero NPU cost) and feed it to the tracker/detector; periodic
  full-frame detection for recovery. This is the lever for small phones, distant people and drone
  targets; full-frame 640×640 detection throws away most of their pixels.
- **Published fields:** `lock.state`, `identity_locked`, `observation_valid`, `quality`,
  `obs_age_ms`, `uncertainty_px` next to the existing `id/class/coasting`. Flight-follow commands
  are valid only with `observation_valid` (a fresh visual observation), never because an id is
  still locked.
- **Ego-motion (F6):** subtract global image motion before predicting target motion — the ISP's
  global motion vectors first (already exposed by the DSP profile), gyro/FC attitude later.
- **Click–frame sync (F5):** the click carries the displayed frame's sequence/timestamp and is
  resolved against that frame's boxes; boxes are drawn on-board into the video so what is shown is
  one frame.
- **Lock-focused benchmark:** identity switches, re-acquisition accuracy and time, false re-locks,
  off-screen predictions, lock retention under fast motion and occlusion — from the owner's
  routines, per build.

**Plans:** F1 lock core `docs/superpowers/plans/2026-09-04-hailo15l-lock-core.md`; F2–F6 follow.


## 9. Risks

- **Framework knowledge** — documented by headers and the developer guide; M0 absorbs surprises.
- **Memory** — ~600 MB usable; measured at every milestone; JPEG path throttled first.
- **NPU throughput** — unknown until measured; fallback ladder in section 5.
- **Depth quality** — the Pi's metric scale is still unvalidated (tape-measure run TBD-bench);
  the 15L build inherits the caveat.

## 10. Open items carried forward (not blockers)

- Two-box topology test (SBC perception + Pi VIO/bridge) once the Pi is back on the cable.
- Custom Yocto image build from `meta-hailo-soc` + `meta-garuda`.
- IMX296 driver port for the global-shutter pair; camera-trigger timestamping without a PTP clock.
