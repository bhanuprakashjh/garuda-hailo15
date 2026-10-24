# docs/decisions.md — decisions log

Format: date, decision, evidence, alternatives rejected. Newest first.

## 2026-09-13 — measured boxes, prompt publication and deadline-bound metadata joining

Use actual current detector geometry for observed tracks; keep Kalman geometry
for association prediction and explicit diagnostics. Do not label filtered size
overshoot as an observed box. Evaluate accepted ROS setpoint requests immediately,
retain watchdog behavior and original deadlines. Join cross-channel publication
metadata with a bounded wait, never by assuming an unknown packet belongs to the
latest request. Recheck expiry after potentially blocking work, immediately before
the simulator write; log afterward. Keep identity ambiguity fail-closed and expose
candidate distances rather than silently excluding rivals or widening thresholds.

Evidence and residual limitations: `2026-09-13-movement-fixes.md` and the matching
benchlog/results. Rejected alternatives: increasing the200ms control budget,
clipping filtered boxes to hide bad geometry, equating identity retained with
motion executed, or declaring rendered-scene transport success real-flight-ready.

---

## 2026-09-03 (M2) — post-stage plugin ABI, tensor dtype, letterbox enum, pad colour: what M2 taught

Bench-measuring the M2 yolo26m detector on the Hailo-15L SBC (`bench/benchlog.md` 2026-09-03
"Hailo-15L SBC: M2 yolo26m detector"; deployed node commit `8c82367`, plugin
`services/garuda-perception/postprocess/yolo26_post.cpp`) confirmed/taught:

- **The post-stage plugin ABI is C linkage, three free functions:** `init(config_path,
  function_name) -> Params*`, `filter(HailoROIPtr roi, void* params)`, `free_resources(void*
  params)`, wrapped in `__BEGIN_DECLS`/`__END_DECLS` (i.e. `extern "C"`) so the pipeline's symbol
  lookup by name resolves them un-mangled — `services/garuda-perception/postprocess/
  yolo26_post.cpp`. A C++-mangled export here would fail to resolve at load time, not at compile
  time.
- **`HailoROI::get_tensor(name)` throws when the named tensor is absent from the ROI** —
  `yolo26_post.cpp`'s own comment above the lookup: "get_tensor() THROWS ... when the ROI carries
  no tensor of that name." The plugin guards every lookup (`b5fa3f8` "guard get_tensor()'s
  throw"); a missing box/class tensor name in `yolo26_post.json`'s `box_tensors`/`cls_tensors`
  would otherwise crash the post stage's thread, not fail cleanly.
- **The six raw output tensors are UINT16 with a zero-point/scale pair on the vstream info, not
  pre-dequantised floats** — `t->is_uint16()`, `t->qp_zp()`, `t->qp_scale()` (same file); the
  plugin dequantises itself before running the Pi-parity decode. Confirmed byte-identical against
  a real captured frame in `tests/test_yolo26_real.cpp`/`tests/golden/yolo26_real_frame.{bin,json}`
  (commit `25d7bd1`, 8/8 ctest green) — the C++ decode matches the Python reference to conf
  ±1e-5, pixels ±1e-3 on live board tensors, not just a synthetic vector.
- **The media library's letterbox enum is the bare `LETTERBOX_MIDDLE`, not a `DSP_SCALING_MODE_`-
  prefixed name** — an earlier README draft guessed the prefixed spelling; the schema pulled from
  `libmedialib.so` on the board uses the bare enumerator (`hosts/hailo15l/README.md` §4).
- **`set_profile()` does not renegotiate `sink0`'s physical geometry after `initialize()`** — a
  geometry change (640x384 stretched vs 640x640 letterboxed) needs its own top-level medialib
  config file with that geometry as its `default_profile`, not a shared config with two profiles
  hot-switched at runtime. The first rollback attempt (one shared config, calling
  `set_profile("GarudaYolov8n")` after `initialize()`) started cleanly and reported success but
  failed every inference call (`CHECK failed - Input buffer size 614400 is different than expected
  368640`) because `sink0` stayed physically 640x640 despite the call succeeding — full root-cause
  trail in `hosts/hailo15l/README.md` §8 "Rollback command". Fixed in `8c82367`: two top-level
  `garuda_medialib_config*.json` files, one per profile, selected via each `perception*.json`'s
  own `medialib_config` field.
- **The Hailo-15L DSP's `LETTERBOX_MIDDLE` pads with Y=0 (black), not the Pi's software
  letterbox's grey 114** — measured from a one-frame `dump_nv12` capture at 640x640 (padding rows
  0-139 and 500-639 all `(0,0,0.0)` min/max/mean; content rows 140-499 are not) —
  `hosts/hailo15l/README.md` §8 "Pad-colour observation". No padding-colour field exists in the
  medialib schema to change this. This is an **unmeasured accuracy difference** from the Pi's
  yolo26m deployment (whose calibration/behaviour was characterised against grey padding) —
  flagged, not fixed, here.

## 2026-09-03 (direction) — M2 = zoo HEF + our own post-process plugin; owner's roadmap (follow via the DSP, then a small VIO) recorded

**Decisions (owner, in-session 2026-09-03 late morning):**
- **M2 detector = Hailo model-zoo `yolo26m` for `hailo15l`** (`Compiled/v5.3.0/hailo15l/yolo26m.hef`,
  md5 `3aef604ab89ddaf9ecb4cefa9c6ea8af`; `models/fetch_yolo26m_h15l.sh`), not the local recompile.
  Why: the Pi's production 640 HEF is the same zoo lineage (parity of the model itself), no GPU/RAM
  job (the local export OOM-killed 3× — `models/yolo26m_h15l.md`), matched compiler/runtime 5.3.0.
  Cost: the zoo's generic COCO calibration instead of `depth-calib.yaml`; accuracy on our scenes is
  unmeasured either way.
- **Own post-process plugin instead of Hailo's `libyolo_hailortpp_post.so`.** The zoo HEF exposes six
  raw heads (`conv71/87/101` ltrb, `conv74/90/104` class logits, UINT16), no `nms_postprocess` tensor,
  and the stock `filter()` only decodes NMS-formatted tensors found by that name — it would silently
  emit nothing. The plugin ports `hosts/pi5/hailo_yolo26.py` line for line (the decode the Pi has
  validated) behind the post stage's `init`/`filter`/`free_resources` ABI. A locally recompiled HEF
  would have baked NMS and a different output format (stock post path, 81-entry labels) — two HEF
  flavours = two post paths, so the zoo flavour is the only target.
- **Letterbox 640×640 via the media library's `LETTERBOX_MIDDLE`** (schema enum confirmed from
  `libmedialib.so`; the README's guessed `DSP_SCALING_MODE_` spelling was wrong) — mono's
  preprocessing; un-map in the detection callback from config. Open: the DSP's pad colour vs the
  Pi's grey 114 — measure the effect, do not assume.
- **Left out of M2:** runtime model switching, yolo-world, custom-calibration recompile.

**Roadmap recorded (spec §8.1):** the owner's goal is tracking/follow for the drone, then a small
VIO. DSP inventory from the deployed profile: multi-resize used today; digital zoom, optical zoom +
dewarp, rotation/flip, motion detection, ISP GMV present but off. Follow (M5) = zoom-window-on-the-lock
after a measured spike, GMV prior, motion-detection gate. VIO groundwork (M6) = EuRoC replay on the
15L first; NPU front end + Basalt; GS cameras + FC-IMU time sync are prerequisites; GPL VIOs bench-only.

## 2026-09-03 (validation) — mono's coast window is a frame count; tuned for the SBC to 75/15 frames

**Decision:** the SBC's `config/perception.json` runs `track.max_lost = 75` and `track.reacq = 15`
instead of mono's 25 / 5. The tracker code and every other parameter stay identical to mono's;
only these two counts changed, in config, on the board.

**Evidence:** with the owner walking in and out of the IMX678's view (`bench/benchlog.md` M1
section, "ADDENDUM 2026-09-03 (owner present)", evidence file
`bench/evidence/2026-09-03-m1-coast-window.txt`), the locked person coasted 0.80–0.90 s and then
died on every absence of a second or more: the board detects at ~30 fps (`frames=301 fps=30.1`),
so mono's 25 frames is 0.8 s of wall-clock there. After the change the measured coasts were
2.41 s / 2.61 s (75 frames), and the re-acquire jump to a live person fired 0.5 s into a coast.
The Pi's own wall-clock window was not measured (mono's detection rate on the Pi is not recorded
in this repo), so 75/15 is a board-specific choice of "about 2.5 s / 0.5 s", not a matched value.

**Also observed, not a bug:** re-entering the frame at a different position mints a new id even
inside the window, because the matcher is IoU-only against the velocity-predicted box (mono does
the same); the lock then follows the live person via the re-acquire rule. Keeping an id across an
arbitrary re-entry would need appearance re-identification — a design change for a later
milestone, not a parameter.

**Alternatives rejected:** making `max_lost` time-based in code (breaks byte-for-byte parity with
the Python reference and the golden tests for no gain the config knob does not give); leaving 25
(the portal user sees a new id after every one-second absence, which is what prompted this).

## 2026-09-03 (later) — M1 tracking port: Python-parity gotchas ported into C++, verified against the running node

Porting ByteTrack + mono's lock/coast/re-acquire loop from `hosts/pi5/garuda_mono.py` into
`services/garuda-perception` (node commit `b87caed`, now deployed and bench-measured —
`bench/benchlog.md` 2026-09-03 "M1 tracking parity") surfaced five reusable parity gotchas,
recorded here so a future port from this codebase's Python originals doesn't re-discover them:

- **Python's `max()` keeps the FIRST element on a tie — a naive `>=` comparison in C++ keeps the
  LAST one instead, silently changing which track gets the lock on a conf/liveness tie.** The
  acquire loop in `src/lock.cpp` (`LockResolver::step`) uses a strict `>` on the
  `(is_live, conf)` pair specifically to preserve this: `if (std::make_pair(tl, t->conf) >
  std::make_pair(ll, locked->conf)) locked = t;` — inline comment: "Python max() keeps the FIRST
  max". Any future re-implementation of a Python `max()`/`min()` reduction in C++ needs the same
  check: does the language's own `max()` favour the first or last equal element, and does the C++
  comparison direction (`>` vs `>=`) match it?
- **CPython iterates a `set` of small ints in ascending order — `std::set<int>`'s sorted
  iteration matches it, but only because the port is careful to make every set in the ported code
  a `set<int>` of small (matcher-index) values, never larger/hashed ints where CPython's order
  would diverge.** `src/bytetrack.cpp` lines 36-37 (comment above `greedy_match`): "ut/ud are
  Python sets of small ints; CPython iterates those in ascending order, which std::set<int>
  (ordered, ascending) reproduces." — both the unmatched-track and unmatched-detection index
  sets, and the births-ordering loop that iterates `ud`, rely on this. Ported from the plan's own
  note (`docs/superpowers/plans/2026-09-02-hailo15l-perception-
  node-m1-tracking.md` line 377): "Python's `ut`/`ud` are sets of small ints iterated in ascending
  order — `std::set<int>` matches". This is a CPython implementation detail, not a language
  guarantee — do not assume it holds for a Python set of arbitrary (non-small-int) values.
- **A click applies to the PREVIOUS frame's published tracks, not the current in-flight frame's —
  because the click handler runs on a different thread/request than the frame loop and has no
  other track list to consult.** `LockResolver::step()` publishes `m_prev` (the current frame's
  alive tracks) at the END of each call, and `LockResolver::click()` only ever reads `m_prev` —
  see `include/garuda/lock.hpp`: "Uses the alive tracks published by the PREVIOUS step() (a click
  before any step() picks nothing)." This mirrors mono's own Python structure (`garuda_mono.py`
  POST handlers, lines 487-512) where the click handler is a separate request path from the
  frame-processing loop and reads whatever the loop last wrote. Getting this backwards (reading
  the tracker's live state mid-update instead of the last-published snapshot) would race with the
  detect thread.
- **`garuda::Track` already existed (a snapshot/JSON type in `include/garuda/snapshot.hpp`) —
  ByteTrack's own `Track` struct had to go in a nested `garuda::track` namespace, not bare
  `garuda`, to avoid a silent name clash the compiler would resolve to the wrong type rather than
  erroring on.** `include/garuda/bytetrack.hpp` and `include/garuda/lock.hpp` both open
  `namespace garuda { namespace track { ... } }`; the lock header's comment spells out why: "Lives
  in `garuda::track` (not bare `garuda`) because `garuda::Track`
  (`include/garuda/snapshot.hpp`) is a different, unrelated type." Lesson: before naming a new
  type after a domain noun already used elsewhere in the tree, `grep -rn "struct <Name>\|class
  <Name>"` the whole `include/` tree — a same-named-different-shape type in a same-named
  enclosing namespace is a correctness bug, not just a build error, if the two are structurally
  similar enough that mismatched usage still compiles.
- **The detector's NMS score threshold must equal the tracker's `conf_floor`, or ByteTrack's
  low-confidence association band is truncated before the tracker ever sees it.** Found in review
  of `cc87ae5` and fixed in `24dca06`
  (`fix(perception): NMS floor from track.conf_floor, add <vector>, correct lifetime comment`):
  `node_main.cpp`'s detect stage had `set_nms_score_threshold(0.3f)` hardcoded (M0's literal, left
  over from before the tracker existed) while `config/perception.json`'s `track.low_thr` = 0.12
  and `track.conf_floor` = 0.15 — meaning ByteTrack's second-pass association window
  `[low_thr=0.12, high_thr=0.40)` could only ever see detections in `[0.30, 0.40)`, and
  `conf_floor=0.15` (mono's own re-association floor, `hosts/pi5/garuda_mono.py`) was
  unreachable — the NMS stage silently discarded exactly the low-confidence "flicker" detections
  ByteTrack exists to re-associate against. Fixed by passing `(float)track_conf_floor` into
  `set_nms_score_threshold` instead of the literal. **General rule for this pipeline shape:
  wherever a detector and a downstream tracker both have their own confidence-floor concept, the
  detector's floor must be less-than-or-equal to the tracker's lowest floor, or the tracker is
  silently starved of exactly the detections its low-confidence band was designed to use** — a
  bug that produces no error, no crash, and no obviously-wrong output (tracks still form, just
  less often re-associate through occlusion/flicker), so it is easy to miss without deliberately
  checking the two thresholds against each other.
- **The NMS-floor fix above did not make the low-score band live.** The board's stock post-process
  config (`ssh root@10.0.0.1 'cat /home/root/apps/shared/resources/configs/yolov8.json'` →
  `detection_threshold: 0.38`) floors detections above both `track.low_thr` (0.12) and
  `track.conf_floor` (0.15) before they ever reach the NMS stage the `24dca06` fix touched — so
  ByteTrack's `[low_thr, high_thr)` re-association band stays **inert until M2** (the post-process
  port); see `bench/benchlog.md` 2026-09-03 addendum for the file pasted verbatim. Do not change
  this post-process config as part of M1 — M2 owns it.
- **Within-frame command-apply order diverges from mono, by design of the node's threading model.**
  `det_sink` (`node_main.cpp`) always consumes a pending `target` before a pending `lock_point`
  click in the same frame, regardless of which HTTP request actually arrived first, because both
  are drained from `NodeState` under one lock in a fixed order; mono's Python handlers instead run
  in true arrival order. Only observable if both commands land within roughly one frame interval
  of each other — accepted as a parity gap, not fixed.
- **`cal_reset` is a no-op waiting to be wired up correctly.** The command handler mutates
  `state.snap.cal_n`/`cal_fit` directly, but `det_sink`'s next frame replaces the whole struct
  (`state.snap = s`), so the reset has no lasting effect — harmless today because no calibration
  state exists yet, but calibration state must move out of `SnapshotState` (not be a field
  `det_sink` overwrites wholesale every frame) before M3 adds real calibration.

## 2026-09-03 — M1 Task 5: NV12 dump flag added, portal parity checked over HTTP (no person at bench)

`dump_nv12` (`{"path": "", "frames": 0}`, disabled by default) added to `services/garuda-perception`'s
`det_sink`: writes the first N `sink0` (640x384) NV12 frames to `path`, stride-stripped, and logs
`dumped N frames to <path>` once. Captured a 300-frame clip (frame count configured; the
profile's `sink0` framerate is 30 fps, the det_sink log during capture read `frames=277
fps=27.7`) on the board to
`/opt/garuda/state/clip-640x384.nv12`, copied to the PC at
`/media/bhanu1234/Development/hailo15/clips/clip-640x384.nv12` (not committed; md5 matched on both
sides: `a5f4d4100feb04107ad2b8f0721319a0`, size 110592000 = 300 × 368640 bytes). **This is an
empty-scene clip** — it was captured at night with nobody at the bench, purely to prove the dump
path end to end; a person-in-frame clip is still needed before it's useful for replay work.

Also ran the portal-parity part of Task 5's brief (Tracking tab click/coast/class-clear scenarios)
as far as possible without a person: portal page loads, the portal's server-side SSE relay
(`/api/events`) correctly reflects the board's `lock.class` after flipping it via
`POST /api/mono_target` on the board and back, and the Tracking tab's JS (`static/app.js`) was
confirmed to call `/api/mono_click` and `/api/mono_target` on the mono host, matching what those
checks exercise. The three scenarios that need an actual detection (click persists, walk-out/back
coast+reacquire, unsupported-class clears an *established* lock) remain pending owner presence —
see `hosts/hailo15l/README.md` §6/§7 for the full transcripts. Board was restored to the committed
(disabled) `dump_nv12` config via `deploy.sh` and confirmed healthy afterward; the PC-side portal
and the `ssh -L 8098` tunnel were left running, untouched.

## 2026-09-02 (latest) — M0 lessons: hailo_analytics framework surprises, boot ordering, runtime deps

Building `services/garuda-perception` (M0 pipeline: frontend -> yolov8 -> post -> snapshot/JPEG
feed, node commit `4ebd020`, plan `docs/superpowers/plans/2026-09-02-hailo15l-perception-node-m0.md`)
surfaced four reusable lessons for the Hailo-15L platform, recorded here so M1 doesn't
re-discover them. First measured numbers from this build: `bench/benchlog.md` 2026-09-02.

- **Framework naming: header lines are the only ground truth, not a plan's remembered API shape.**
  `HailortAsyncStageBuild` and `PostprocessStageBuild` expose a factory `create()` (not a bare
  `Builder()`) that returns a private-by-convention `Builder`; the stage classes live in
  `hailo_analytics::pipeline::{sources,ai,sinks}` sub-namespaces, not the top-level
  `hailo_analytics::pipeline` (where `PipelineBuilder`/`StageType`/`AppStatus`/`BufferPtr` do
  live). Every correction is tied to the exact header line that justified it — see
  `.superpowers/sdd/2026-09-02-hailo15l-perception-node-m0/task-7-report.md` §2. Lesson: grep the
  actual installed headers before writing pipeline-builder code against a remembered API shape, on
  this SDK generation at least.
- **Letterbox (M1 groundwork).** The media-library's scaling-mode field is the bare, unquoted
  `scaling_mode` key — no `"DSP_SCALING_MODE_..."` string appears anywhere in
  `media_library/*.hpp`. The real C enum (`dsp_scaling_mode_t`: `DSP_SCALING_MODE_STRETCH=0`,
  `_LETTERBOX_MIDDLE`, `_LETTERBOX_UP_LEFT`, `_SCALE_AND_CROP`, `_COUNT`) lives one directory up in
  `hailodsp.h`, outside the glob a naive search of `media_library/*.hpp` would use. The stock
  `sink0` example profile carries no `scaling_mode` key at all, meaning it defaults to
  `DSP_SCALING_MODE_STRETCH` — M0's 640x384 detect input is therefore stretched, not letterboxed,
  today. M1's YOLO input-prep work needs `DSP_SCALING_MODE_LETTERBOX_MIDDLE` set explicitly if it
  wants aspect-preserving input. That switch also invalidates `node_main.cpp`'s bbox scaling, which
  multiplies the normalized detection box straight by the 1280x720 frame size and is correct only
  while sink0 and sink1 are STRETCH-resized from the same full FOV — a letterboxed sink0 must be
  mapped back through the pad offsets and scale at that line first. Full verbatim grep output recorded in `hosts/hailo15l/README.md`
  under "Letterbox for M1"; also `task-6-report.md`.
- **TurboJPEG is a build-time-only dependency on this board image — a permanent runtime gap, not a
  one-off dev-machine miss.** The cross sysroot ships `libturbojpeg.so.0`, but the board's rootfs
  ships only `libjpeg.so.62` (the plain IJG API) — no `libturbojpeg.so.0` and no static
  `libturbojpeg.a` anywhere on-device. `garuda-perception` links the TurboJPEG C API for its
  NV12->JPEG encoder (Task 5), so every deploy needs `libturbojpeg.so.0.2.0` copied to
  `/opt/garuda/lib/` and `LD_LIBRARY_PATH=/opt/garuda/lib` set at run time (now baked into the
  init script). `task-7-report.md` §4a.
- **Boot ordering: two S99 init scripts race, and losing the race deadlocks both.** SysV
  `/etc/init.d/rc` runs `S99*` scripts strictly alphabetically; `S99garuda-perception` sorted
  before `S99hailo-thermal-service.sh`, so a `wait_ready()` that blocked on files the thermal
  service creates blocked the thermal service itself from ever starting — a structural deadlock,
  not a timeout-size problem (reproduced at a 240 s timeout in round 3 before the structural cause
  was found). Fix: don't block boot at all. `start()` now forks a detached background starter
  (`( exec nohup /bin/sh "$SELF" __start_bg >> $LOG 2>&1 < /dev/null ) &`, chosen over `setsid`
  because `setsid` forks on this board and loses pid-exactness) and returns immediately; the real
  readiness wait, the node's retry-loop launch, and the shim launch all happen in the background
  job. Lesson for any future S99 script on this board: never gate boot-time readiness on another
  S99 script's output files; either claim a priority the platform's `update-rc.d` actually orders
  past 99, or don't block boot at all.
  `.superpowers/sdd/2026-09-02-hailo15l-perception-node-m0/task-10-report.md`, rounds 3-4.
- **CPython's `socket.recv(n, MSG_WAITALL)` is not exact once a timeout is set — it can return
  short.** `garuda_mono_shim.py`'s `Feed._run` set a 5 s socket timeout (round-1 item 6) and then
  relied on `MSG_WAITALL` to fill exactly `n` bytes for the feed protocol's type byte, length
  header, and payload; with the timeout active it returned short instead (confirmed live: a
  129061-byte `J` frame came back as 65531 bytes — controller reproduction from the PC against the
  live node, 2026-09-02; raw output committed at `bench/evidence/2026-09-02-shim-short-read.txt`,
  also in the Task 11 report), so every read broke the frame parse and the
  reader reconnected roughly every 0.5 s — `/stream` never completed a frame and SSE degraded to
  sub-Hz bursts. Fixed in `f882b67` with a `recv_exact(sock, n)` loop that accumulates until it has
  exactly `n` bytes (or hits EOF), used for all three reads instead of `MSG_WAITALL`; a regression
  test forces short reads (an 8 KB-chunked, 5 ms-delayed >=200 KB frame) and asserts `/stream`
  still delivers a complete, correctly-sized JPEG part — verified failing against the old
  `MSG_WAITALL` code before the fix. Re-measured numbers: `bench/benchlog.md` 2026-09-02 addendum.

## 2026-08-02 — GPLv3 rule RELAXED for bench/experimental (owner directive)

**Directive (owner, in-session):** the CLAUDE.md §1/§6 hard "no GPLv3" rule is **relaxed for now** —
GPL-3.0 / AGPL code + models may be used for **bench, experimental, and evaluation** work. Rationale
holds legally: running software locally is not *distribution*, so no copyleft obligation triggers.
This unblocks trying **ORB-SLAM3, OpenVINS, VINS-Mono/Fusion** (all GPLv3) for the VIO/SLAM
workstream, and GPL depth models (e.g. **scdepthv3**) as real options rather than eval-only.

**Guardrails (keep it reversible — this is the whole point of "for now"):**
- GPL components stay **behind the plugin interfaces** (`ICaptureBackend`/`IFrontEnd`/`IDepthSource`)
  and are **tagged `GPL-3.0 — not product-cleared`** (as `models/LICENCES.md` does), so a product build
  can swap a clean implementation without a rewrite.
- Do **not** deep-wire GPL into shippable `services/` in a way that's costly to remove.
- **Product-tier licence-clean remains the goal** — revisit before Phase 8 (eval image) / product.
  Shipping a GPLv3-encumbered SDK is still a deliberate, unresolved decision, not a default.
- CI licence-scan: keep it reporting GPLv3 (visibility) but no longer a hard build-stop for bench work.

## 2026-08-02 — Depth in the portal: integration working; SGBM accurate, NPU depth off (checkpoint)

**Status:** the portal **Depth tab is live and working** — SGBM / StereoNet / fast_depth / scdepthv3
switchable from the browser, embedding the `garuda-depth` service (`:8097`) in an iframe. Engine
switching is **stable**: a switch writes `~/.garuda-depth-model` + `os._exit(0)`, and the unit
(`Restart=always`) brings up a fresh process — a **full process death is the only thing that
reliably resets a wedged Hailo** on this HailoRT (in-process reconfigure → HAILO_INTERNAL_FAILURE;
`os.execv` keeps the wedged device fd; ~9 s/switch). Follow GUI untouched (`portal.py` unchanged, 72
portal tests pass). `install.sh` installs/enables the unit (rule 3).

**Depth accuracy verdict (bench-confirmed on-rig):**
- **CPU SGBM = accurate / metric ("bang on")** — the production depth engine. It *measures* true
  distance (verified 12.5 in → 32 cm; consistent at range ~225 cm). Licence-clean (OpenCV).
- **NPU learned models = dense but OFF.** StereoNet (stereo) range-collapses indoors (driving-trained,
  our 47 mm baseline at 1–3 m is out-of-distribution). fast_depth / scdepthv3 (mono) are learned
  guesses — SGBM-calibrated to cm, structure-plausible, but **not measurements**, so not trustworthy
  for ranging.

**Takeaway:** SGBM is the metric depth for follow-range / obstacles. Accurate NPU depth would need a
**rig-suited, licence-clean model** (fine-tune on our short-range stereo → DFC compile); the eval
zone (`models/LICENCES.md`) is set up to chase that. NPU depth models stay bench/eval-only.

## 2026-08-02 — models/ EVALUATION ZONE + NPU depth-model bake-off

**Convention (owner-directed):** `models/` is an **evaluation zone** — ANY-licence model may be
fetched + run on the bench to benchmark it, because **evaluation is not distribution** (GPL
obligations trigger only on shipping). The wall: `models/LICENCES.md` tags each model
ship-eligible vs EVAL-ONLY; only clean-licence (BSD/MIT/Apache/LGPL-dyn) models graduate into
`services/`; CI licence-scan polices `services/`, not `models/`. Keeps CLAUDE.md rule 6 intact
(clean `services/`) while letting us try the whole zoo, like the detection models.

**Depth bake-off (all Hailo-10H, `:8093`–`:8096`):**
| model | task | licence | ship | on-bench | verdict |
|---|---|---|---|---|---|
| SGBM (CPU) | stereo | OpenCV | ✅ | ~10 fps, 66%, **metric** | the ranging engine |
| stereonet | stereo | none | ❌ | 14 fps, dense | driving-trained, range-collapses |
| fast_depth | mono | **MIT** | ✅ | 221 fps | indoor, decent structure, relative scale |
| scdepthv3 | mono | GPL-3.0 | ❌ | 135 fps | **best structure** (RMSE 0.48), eval-only |

**Takeaways:** (1) SGBM stays the *metric* depth (only one that measures). (2) Of the NPU learned
models, **scdepthv3 looks best but is GPL-3.0 (eval-only)** → signal to find/train a clean-licence
indoor mono model; **fast_depth (MIT)** is the shippable-but-weaker option. Runners:
`hosts/pi5/hailo_mono_depth.py`, `camarray_depth_mono.py` (any mono HEF via `--hef`).

## 2026-08-02 — Stereo depth on the NPU (StereoNet HEF) — bench experiment ✅ (licence-flagged)

**Result:** stereo depth now runs on the **Hailo-10H** via the **StereoNet** HEF from the Hailo
Model Zoo — dense/smooth depth at **~13.8 fps**, CPU only ~64% / 46 °C (matching offloaded to the
NPU). `http://<pi>:8094/`. Head-to-head vs CPU SGBM (`:8093`): 100% dense vs 76%, 13.8 fps vs ~2.

**How:** pre-compiled HEF (`models/fetch_stereonet.sh`, no x86 DFC needed) → HailoRT **InferModel**
API (`create_infer_model → configure → create_bindings → run`; the old VStreams `configure` path
returns HAILO_NOT_IMPLEMENTED on 5.1.1). I/O: 2× UINT8 368×1232×3 (rectified L/R) → 368×1232×1
disparity. `hosts/pi5/hailo_stereo.py` (`HailoStereoNet`) + `camarray_depth_npu.py` (viewer).
Rectify on CPU (our calibration) → StereoNet on NPU → `Z=f·B/d`. `swap=False` gave correct
near=warm on the first try (input_layer1 = left).

**⚠️ LICENCE (rule 6):** StereoNet source (nivosco/StereoNet) is **UNLICENSED** — bench-only, NOT
product-cleared; no yocto recipe added. Product must swap in a licence-clean depth model. The `.hef`
is git-ignored (fetch, don't commit). See `models/stereonet_h10.md`. Trained on driving/KITTI →
indoor accuracy rough, absolute scale provisional.

## 2026-08-02 — Dense stereo depth WORKING; outlier rejection + coverage were the unlocks ✅

**Result:** live stereo depth is now dense and coherent — **76% valid pixels**, clean
fore/background separation (person in warm/near, room in cool/far), metric center readout
(~194 cm on the wall). `http://<pi>:8093/`. The L/R swap fix + these two got there:

1. **Outlier rejection in the calibrator.** 68 raw pairs gave a *broken* stereo RMS of **23 px**
   — tilted boards trigger the checkerboard 180° flip ambiguity, scrambling L/R corner order in a
   subset. `stereo_calibrate.py` now fits → drops pairs with per-pair error > max(1px, 3×median)
   → refits, iterating (`_stereo_view_errors`). Dropped **17** → **51 inliers** → RMS **23 → 1.26 px**.
2. **Coverage buys density, not RMS.** RMS plateaued at ~1.26 px (same as the old 13-pair run) —
   the ceiling is now **image sharpness** (varLaplacian ~400–640 = soft; focus/flatness/gain-noise),
   not data quantity. But 51 well-spread pairs give **uniform rectification across the FoV**, so
   depth density jumped **31% → 76%**. Coverage helped even though it didn't move the RMS number.

**Optional push to RMS <0.5:** sharper board images — check/adjust lens focus for ~0.7 m, mount the
target dead-flat on rigid backing, lower gain + more light. 1.26 px is already usable.
**Still provisional:** absolute scale (`square=33.5 mm`) — pin with a known-distance check.

## 2026-08-01 — Depth was sparse from a LEFT/RIGHT SWAP, not calibration quality (fixed + verified)

**Finding (user was right — not just calibration):** the live depth was sparse/non-corresponding
because the stereo pair is fed to SGBM **backwards**. The calibration proves it:
`T[0] = +40.7 mm` (positive), `Q[3,2] = -1/Tx < 0`, `P2[0,3] = +46480 > 0` — all the *opposite*
sign of a standard left-reference rig. So **tile0 (left half of the combined frame) is the
physically RIGHT camera; tile1 is the LEFT.** `StereoSGBM(rect_tile0, rect_tile1)` then yields
**negative** disparity for real objects, which `disp > 0` masks away → sparse speckle.

**Fix (committed, verify on next boot):** `StereoRig.reference_is_cam2 = (P2[0,3] > 0)` and
`order_for_matching()` swaps the pair so SGBM gets (left=tile1, right=tile0) → positive
disparity; the depth view displays the reference (tile1) it's aligned to. Unit-tested
(`tests/test_stereo_rig.py`). Calibration itself is unaffected (stereoCalibrate is naming-agnostic;
RMS 1.22 is a separate quality issue). **On resume:** relaunch `camarray_depth_view.py` and
confirm the depth densifies; the RMS-1.22 noise remains until a tighter recalibration.

## 2026-08-01 — Stereo depth pipeline live end-to-end; PROVISIONAL calibration (resume point)

**State at power-down (resume here):** the whole stereo-depth chain runs on the bench —
capture → calibrate → rectify → StereoSGBM → colorized live depth view — but on a *rough*
calibration, so depth is currently sparse/noisy. Milestone (pipeline works) reached; quality
gated on a better calibration.

**What was built (all committed):**
- `hosts/pi5/camarray_capture.py` — browser calibration-capture tool (live corner overlay,
  saves raw L/R pairs to `calib/captures/`). `camarray_view.py` — plain stereo preview.
  `camarray_depth_view.py` — live rectify+SGBM depth view (port 8093).
- `calib/stereo_calibrate.py` — `findChessboardCornersSB`→`stereoCalibrate`→`stereoRectify`,
  writes `bench/camarray_stereo.yaml` + RMS; `services/garuda-camera/stereo_rig.py` loads it.
- `camarray_setup.sh` now also locks exposure/gain and (opt) caps fps via `vertical_blanking`.

**Findings (Rule 2/9):**
1. **Board is 9×6 inner corners (10×7 squares), NOT 11×8.** The hand-count of "12×9 squares"
   was wrong; `findChessboardCornersSB` on a real held-up frame only locks at (9,6). Use
   `--cols 9 --rows 6`. `square_size` is provisional **33.5 mm** (single-cell measure; it's a
   pure scale factor — pin exactly later with a known-distance check, Rule 1).
2. **Cooling is PASSIVE** (heatsink, no fan — CLAUDE.md §2 corrected). A flat-out full-res
   corner-detect loop hit **267% CPU / 84.5 °C / freeze**; fixed by throttling detect to 2 Hz,
   central single-encode MJPEG, and capping sensor fps (`GARUDA_CAM_VBLANK≈3600`, ~10 fps).
3. **Provisional calibration:** 13/17 usable pairs, **stereo RMS 1.22 px** (target <0.5),
   **baseline 40.9 mm** (physically sane → geometry locked), focal ~836 px (K1) — at
   square=33.5 mm. RMS too high → poor rectification → sparse depth.

**Next (resume):** latch the capture tool's green indicator (2 Hz detect made it flicker),
re-shoot **30–50** well-spread sharp pairs (fill frame, all corners, tilts, still), re-calibrate
to RMS <0.5, and the existing depth view densifies. Then: known-distance scale pin; optionally
move the depth matcher onto the Hailo (HEF) to offload CPU (product-tier direction).

## 2026-08-01 — CamArrayBackend implemented + verified live through the plugin path ✅

**Result:** `hosts/pi5/camarray_backend.py` is now a real `ICaptureBackend` (was a stub). It
runs `camarray_setup.sh`, then streams the combined frame raw via a `v4l2-ctl --stream-mmap
--stream-to=-` subprocess; a reader thread slices fixed-size frames and emits `FrameMeta` +
`memoryview`. Verified **on-bench through the actual backend** (not just `v4l2-ctl` by hand):
4 frames, each exactly **4,096,000 B** (5120×800×1 GREY); `plan_split(5120,800,1,4)` +
`crop_row_major` split gives **tile 0 mean 36.2 / max 255, tile 1 mean 36.2 / max 255**
(the live stereo pair — equal means = same scene), tiles 2/3 all-zero (unpopulated). Runs as
the `garuda` user with **no sudo** (user is in the `video` group; `media-ctl`/`v4l2-ctl` work).

**Bug found + fixed (Rule 4 log):** the setup script's sensor-name regex
`grep -oE "arducam-pivariety [0-9-]+"` dropped the trailing `c` of the entity name
`arducam-pivariety 10-000c` (i2c addr 0x0c → 4-hex-digit suffix `000c`). media-ctl then
rejected the truncated name on `-V`/`-e` with `Unable to setup formats: Invalid argument (22)`.
My earlier *manual* commands used the full name so never hit it; the script's extraction was
the defect. Fix: `[0-9a-z-]+` so the hex suffix is captured. `read_exact` (the frame-slicer)
is pure and unit-tested (`services/garuda-camera/tests/test_camarray_backend.py`).

## 2026-08-01 — CamArray WORKING all-Trixie via stock arducam-pivariety + raw V4L2 ✅

**Result:** the OV9281 CamArray is fully up on **this Trixie bench** — no Bookworm, no Arducam
installer, no libcamera swap, CM3/portal/follow untouched. Captured a real **5120×800 Y8**
combined frame; the two connected cameras populate **tiles 0 and 1** (mean ~111/112, live
image), tiles 2/3 empty. That's a synchronized stereo pair, raw.

**What actually cracked it (three things, in order):**
1. **Hardware, not OS** — the HAT needs its **USB power** (CSI ribbon can't power the FPGA
   bridge), and the **CSI ribbon had to be reseated** (a loose ribbon left the ArduChip's
   i2c dark). The berg SDA/SCL wiring reached only an EEPROM (`0x51`), a red herring; the
   ArduChip is at **`0x0c` on the CSI i2c (bus 10)**, reached over the ribbon.
2. **Stock driver exists** — the Trixie kernel already ships `arducam-pivariety.ko` + `.dtbo`.
   `dtoverlay=arducam-pivariety,cam0` (CSI0 + i2c_vc) binds it; it reads the ArduChip
   (firmware `0x10004`) and reports the combined sensor format.
3. **Raw V4L2, not libcamera** — stock libcamera has no pivariety CamHelper, so it won't list
   the camera; capture raw from `rp1-cfe-csi2_ch0` (`/dev/video0`) instead. The one gotcha:
   the `csi2` source pad feeds both the raw node and the ISP front-end (`pisp-fe`,
   MUST_CONNECT) — leave the ISP branch enabled and `STREAMON` fails "Broken pipe"; **disable
   `csi2:4→pisp-fe`, keep `csi2:4→csi2_ch0`**, set `Y8_1X8/5120x800`, capture GREY.

**Artifacts:** `hosts/pi5/camarray_setup.sh` (the media-ctl pipeline recipe), config in
`docs/camarray-bringup.md`. Supersedes the two entries below (stock ov9281 fails; installer
breaks Trixie; Plan-B capture-replay) — all moot now. Next: wire the recipe + raw capture into
`services/garuda-camera` `CamArrayBackend`, split 5120×800 → tiles 0/1 → stereo depth.

## 2026-08-01 (later) — CamArray ArduChip reached on-bench; bring-up via capture-and-replay (Plan B)

**Milestone:** after wiring, the CamArray bridge is alive and addressable. Root blocker was
**hardware, not OS**: the HAT needs (1) **USB power** (CSI ribbon + berg pins don't power the
FPGA bridge — LED lit but bridge under-powered), and (2) its **SDA/SCL berg holes wired to the
Pi's VideoCore i2c** — **pin 27 (ID_SD/GPIO0) / pin 28 (ID_SC/GPIO1) + GND** = `/dev/i2c-0`.
Then the ArduChip answers at **i2c `0x51` on bus 0**, chip ID `0x82 0x47 0x03`.

**It's a Pivariety-style controller (16-bit register protocol)** — register map from
`ArduCAM/Camarray_HAT` (DEVICE `0x0100` / PIXFORMAT `0x0200` / FORMAT `0x0300` / CTRL `0x0400`
/ SENSOR `0x0500` banks). So the stock `ov9281` driver (8-bit sensor protocol on the CSI bus)
can **never** drive it, and Arducam's installer is broken on Trixie 2026 (entry below).

**Decision — Plan B (capture-and-replay), CM3-safe:** capture the ArduChip init that Arducam's
working stack emits on a **Bookworm** card (kernel i2c ftrace), then **replay it on Trixie** via
`i2ctransfer` (`hosts/pi5/camarray_replay.py`) + raw-V4L2 capture into `services/garuda-camera`
— **never swapping the system libcamera**. Procedure: `docs/camarray-i2c-capture.md`.

**Alternatives rejected:** Arducam installer on this bench (breaks the CM3/libcamera stack the
whole project runs on — proven below); hand-guessing the 16-bit init blind (risky, unknown map).

## 2026-08-01 — Arducam CamArray (OV9281 ×4, B0267) NOT bring-able on Trixie yet; deferred to a Bookworm card

**Decision:** the OV9281 CamArray HAT stays on the roadmap but is **not brought up on this Trixie bench**. Do it on a separate Raspberry Pi OS **Bookworm** SD card (Arducam-supported), isolated from the working portal/follow stack.

**Evidence (reproduced on-bench, connected on CAM1 alongside CM3 on CAM0):**
- HAT answers on i2c (`ov9282 10-0060` probes), so hardware + wiring are fine; global-shutter, hardware-synced.
- **Stock `ov9281`/`ov9282` driver cannot power it:** `fail to write MIPI_CTRL00` → `failed to power-on the sensor` → `probe ... failed with error -5`. The kit's OV9281 are the *special CamArray* version (HAT bridge), not stock-driver-compatible.
- **Arducam's installer (`install_pivariety_pkgs.sh`) is built for an older OS:** it `apt remove libcamera0` + `apt purge libpisp0.0.1`, but Trixie ships **`libpisp1 1.6.0`** (name mismatch). The run **hung and was killed**, never installed the Arducam fork, and drifted the stock libs (`libcamera` → 0611-2, `libpisp` ↓ 1.5.0).
- **Recovery worked cleanly:** pre-snapshotted 50 stock camera `.debs` (`~/camera-stock-debs/` on the Pi) + `config.txt.pre-camarray`; `dpkg -i --force-downgrade` restored `libcamera 0609-1` / `libpisp 1.6.0-1`, config to auto-detect, reboot → CM3 + portal + follow all green (210/210 detections/follow).

**Cam0/cam1 mapping (Pi 5, this board):** CM3 (imx708) is on the port the overlays call **`cam1`** (i2c@80000/csi@128000); the free/CamArray port is **`cam0`** (i2c@88000/csi@110000) — the reverse of the silkscreen intuition. Record when wiring overlays.

**Alternatives rejected:** (a) run Arducam's installer on this working bench — high risk of an unrecoverable libcamera/libpisp swap breaking the CM3/portal/follow stack the whole project runs on (rule 3/10); (b) stock `ov9281` overlay — proven to fail at the driver level. See `docs/camarray-bringup.md`.

## 2026-07-30 — garuda-portal V1 security posture (bench vs product tier)

**Decision/finding:** The portal/configd privilege split (unprivileged `garuda-portal`
PUTs config and requests unit actions over a Unix socket; only root-run `garuda-configd`
whitelists and executes them) is architectural intent, **not an enforced containment
boundary on this bench**. `hosts/pi5/install.sh` grants the bench user
`ALL=(ALL) NOPASSWD: ALL` sudo (step [2/5], restoring what Trixie stopped granting by
default) so that the SAME account running the unprivileged portal can already run
anything as root directly — the socket/whitelist indirection buys nothing against that
account on this machine. It remains real, load-bearing containment at product tier,
where the deployed account must NOT hold sudo.

**Evidence:** `sudoers.d/010-${USER}-nopasswd` created unconditionally by install.sh;
`garuda-portal.service` runs `User=garuda` — the identical account install.sh just gave
passwordless root. Confirmed against the whole-branch review 2026-07-30 (this fix wave
also closed F1/F2: `probes.WATCHED_UNITS` pointed at a decommissioned unit and a non-unit
process, and `/opt/garuda/garuda-configd` was garuda-owned code executed by root — now
root:root, `go-w` stripped, see fix-wave report).

**Two HARD gates before Phase 8 or any exposure off this bench (not deferrable minors):**
1. **Authentication on the portal.** It is unauthenticated on `0.0.0.0:8080` — any host
   on the LAN can `PUT /api/config` and start/stop `garuda-*` units with no credential.
   Acceptable only because this bench sits on an isolated dev LAN with no untrusted peers.
2. **Portal run as a non-sudo account.** Product-tier deployment MUST run
   `garuda-portal` (and ideally the whole bench user) without `NOPASSWD: ALL`, or the
   configd privilege split above is decorative there too.

Both are tracked here rather than as code changes in this fix wave — they need a design
decision (auth scheme; account model) out of scope for a fix dispatch, per the
whole-branch review 2026-07-30.

## 2026-07-30 — Basalt source: mateosss/basalt fork (Monado-maintained), built from source on Trixie

**Decision:** `garuda-vio` builds on the Monado-maintained Basalt fork
(`gitlab.freedesktop.org/mateosss/basalt`, BSD-3, active releases — latest 2026-07-24 with a
Pi 5 tuned `rpi5` cmake preset), compiled from source on the bench.

**Evidence:** The canonical TUM GitLab (`gitlab.vision.in.tum.de/tum-vision/basalt`) now
refuses anonymous clones (upstream effectively gone); the GitHub mirror is frozen ~2022 and
untested against GCC 14. The fork publishes prebuilt Pi 5 debs, but they target Bookworm —
on Trixie the binary wants 13 Bookworm-era sonames (boost 1.74, OpenCV 406, fmt9); installing
that library zoo is the repo-mixing we already rejected. Source build on Trixie is ABI-native
and matches the production configuration (garuda-vio runs native, not containerised).

**Licence:** BSD-3-Clause, unchanged from upstream — passes the gate.

## 2026-07-29 — ROS 2: Jazzy in Docker on Pi OS; keep ROS thin

**Decision:** ROS 2 Jazzy (not Humble), run in Docker on the Pi OS host. Native side keeps
garuda-camera/-time, HailoRT inference, and Basalt (plain C++, thin wrapper — never ROS-ified
internally). Container side gets the ROS nodes (VIO wrapper, mapper, planner), px4_msgs, rviz,
rosbag2. Boundary plumbing: `--network=host --ipc=host`, CycloneDDS pinned as RMW in both
worlds. Container images build only from a committed Dockerfile in `hosts/pi5/`.

**Rationale:** Jazzy is current LTS (2029, matches programme life) and works with PX4
v1.15/1.16 uXRCE-DDS; Humble targeted Ubuntu 22.04 bases and was the misfit that forced the
question. MicroXRCEAgent itself is a standalone binary — ROS buys the ecosystem (typed
px4_msgs, Nav2/OMPL wrappers, rosbag2 for the §8.2 regression datasets), so the middleware
stays a thin, containerised, portable layer — exactly the packaging seam the Hailo-15 port
wants. Camera-free milestone this enables: PX4 SITL in a second container + MicroXRCEAgent =
full Phase 5 bridge (odometry→EKF2, failsafe) proven with EuRoC replay before cameras/CA90
arrive; real hardware then swaps in on a proven pipeline.

## 2026-07-29 — Host strategy: Pi OS native; ROS 2 containerised; Yocto at product tier only

**Decision:** The bench stays on Raspberry Pi OS (not Ubuntu, not Yocto). ROS 2 arrives at
Phase 4 as a container (`ros:jazzy` favoured) or a Debian-built Jazzy — decided then. Yocto
enters only at the Hailo-15 port (Phase 9), prepared for now via `yocto/meta-garuda/` and the
recipe-per-dependency rule (CLAUDE.md §6 rule 6).

**Rationale:** Put the OS where the drivers are hardest, containerise what's portable. The
NPU (`hailo-h10-*` apt flow, HAT+ EEPROM detection, kernel-coupled driver packaging) and the
camera stack (libcamera pipeline handler, dtoverlays, IMX296 `trigger_mode`, RP1 PTP) are
Pi-OS-first; Ubuntu would trade vendor-path support on the schedule-critical Phase 2/3 work
for native ROS 2 — the single most portable layer in the stack. Yocto on the bench would cost
iteration speed and require hand-integrating the h10 driver with no maintained layer.
Eval-tier deliverable (Phase 8) uses pi-gen, not Yocto. Full reasoning captured from the
2026-07-29 planning discussion.

## 2026-07-29 — Base OS: Raspberry Pi OS Trixie 64-bit (not Bookworm)

**Decision:** Bench Pi runs Raspberry Pi OS Trixie (Debian 13) 64-bit Lite. CLAUDE.md §3 updated accordingly.

**Evidence:** First boot was done on Bookworm Lite (2026-06-18 oldstable image) per the original CLAUDE.md pin. `apt` on that image cannot locate `hailo-h10-all`; `apt-cache search hailo` on Bookworm shows only the Hailo-8 family (`hailo-all`, `hailort`, `hailo-dkms`, `hailofw`) — the exact packages CLAUDE.md forbids for the Hailo-10H. Direct inspection of `archive.raspberrypi.com/debian/dists/trixie/main/binary-arm64/Packages.gz` confirms the full h10 family (`hailo-h10-all`, `h10-hailort`, `h10-hailort-pcie-driver`, `python3-h10-hailort`) exists only in the Trixie pocket. Raspberry Pi OS mainline moved to Trixie 2025-10; Bookworm is the legacy/oldstable channel and will not receive AI HAT+ 2 support.

**Alternatives rejected:**
- Bookworm + vendor .debs from hailo.ai developer zone: untested kernel/driver coupling on a combo Raspberry Pi doesn't ship, login-gated downloads, manual update path. Reintroduces the #1 bring-up failure mode CLAUDE.md warns about.
- Mixing the Trixie pocket into Bookworm sources: frankendebian, ABI risk across glibc/python — rejected outright.

**Impact:** None on architecture or phase gates. Toolchain shifts to Python 3.13/GCC 14. Hailo-10H stack becomes apt-managed and kernel-coupled by the distro, which reduces version-mismatch risk.

---

## 2026-08-02 — Build ORB-SLAM3 (bench/eval) in an aarch64 GCC-11 container, not bare-metal

**Context:** The hybrid ORB-SLAM3 + Hailo-YOLO masking spike (path A of the hybrid-SLAM plan,
`docs/superpowers/plans/2026-08-02-hybrid-orbslam3-yolo-masking.md`) needs ORB-SLAM3 stereo built on
this bench. Phase-0 recon (benchlog 2026-08-02) found the host is worst-case for it: **GCC 14.2 /
Eigen 3.4 / OpenCV 4.10**, no SLAM deps present. Public ORB-SLAM3 build success is documented only up
to GCC 11–12; GCC 14 is undocumented territory (the #1 predicted build risk).

**Decision:** Build ORB-SLAM3 in a **Docker container: `ubuntu:22.04` (GCC 11, Eigen 3.4, OpenCV 4.5.4),
built natively on the Pi's arm64 CPU** — no cross-compile, no emulation. Pangolin pinned **v0.6**
(known-good with ORB-SLAM3). Headless (`bUseViewer=false`). This matches CLAUDE.md §3's committed
"heavy compute in a container, Hailo path native, talk across the boundary" architecture: the Hailo
masker stays native (HailoRT/PCIe), ORB-SLAM3 compute is containerized, they share a bind-mounted
`MaskIPC` file. Dockerfile committed at `hosts/pi5/orbslam3/`. **GPL-3.0, not-product-cleared** (rule 6,
2026-08-02 relaxation) — behind `IFrontEnd`, skeleton yocto recipe to follow, CI licence-scan visibility.

**Alternatives rejected:**
- **Bare-metal GCC 14:** the single biggest build risk, undocumented for ORB-SLAM3. No reason to fight it.
- **x86 → aarch64 cross-compile:** needs a full aarch64 sysroot for Pangolin/OpenCV/Eigen and the whole
  point (Hailo/camera) is Pi-native; large setup for no benefit on a bench spike.

**Symptom + fix logged (rule 4):** first image build **cancelled at 48%** with no compile error and no
OOM — root cause was `docker build` self-cancelling when its **launching SSH session was torn down**
(client-pipe disconnect; `nohup` blocks SIGHUP but not this). GCC 11 was compiling the Eigen-heavy files
(`Optimizer.cc`, `G2oTypes.cc`, `ImuTypes.cc`, `CameraModels/*`) cleanly — the container pivot works.
Fix: relaunch the build under **`setsid`** (own session, immune to SSH teardown). Layer cache (apt +
Pangolin, ~1.2 GB) made the relaunch resume cheaply.

**CORRECTION — the real root cause of the repeated ~48% deaths was NOT client-disconnect or the file
itself, it was a broken parallelism `sed`.** Upstream `build.sh` uses bare `make -j` (UNLIMITED jobs)
for Thirdparty and `make -j4` for the main lib. `sed 's/make -j/make -jN/'` mangles `make -j4` →
`make -jN4` (e.g. `make -j24` at "-j2", `make -j14` at "-j1"), so the main build ran 14–24-way parallel;
many concurrent cc1plus incl. `Optimizer.cc` (~7 GB alone at -O3) drove load to 18+ and OOM-killed the
build — silently (SIGKILL), no error text, host RAM freed on death (looked like "not OOM"). Zombie
BuildKit daemon workers from repeated relaunches compounded it. **Real fix: anchored regex
`sed -E 's/make -j[0-9]*/make -j2/g'` pins EVERY make line to -j2, plus a 6 GB temp swapfile for
`Optimizer.cc`'s ~7 GB peak (CLAUDE.md §3 sanctions swap for on-device builds).** With that, one clean
`-j2` build completed: load ~2, min-avail 2.2 GB, `Optimizer.cc` cleared, image `garuda/orbslam3:bench`
(3.29 GB), never throttled during the build (peak 78 °C).

**Go/no-go verdict (bench/benchlog.md 2026-08-02): PASS.** ORB-SLAM3 stereo on EuRoC MH_01 = **~22.8 fps
tracking (43.85 ms/frame mean, 41.96 ms median), clearing the P4 ≥20 Hz front-end bar even while thermally
throttled** (peak 84.5 °C, freq-capped; passive heatsink — sustained runs throttle, no under-voltage).
Better than the research forecast. The hybrid ORB-SLAM3 + Hailo-YOLO masking is viable → proceed to the
mask seam (Task 3). Caveats (not blockers): tracking-thread rate only (no ≥200 Hz inertial pose — stereo-only,
no IMU); EuRoC-ideal (live OV9281 `TBD-bench`); ATE accuracy not yet computed (`TBD-bench`).

---

## 2026-08-03 — OV9281 CamArray is not a stereo-SLAM camera; IMX296 GS pair is the VIO path  [⚠️ RETRACTED 2026-08-04 — see below]

**Context:** Attempted live stereo SLAM (ORB-SLAM3) on the Arducam **Camarray HAT + OV9281 quad** (tiles
0+1 as the pair). Full tooling built and works (`camarray_record.py`, `orbslam3_config.py`,
`rectify_clip.py`), but ORB-SLAM3 never tracks — only ~25 stereo map points/frame.

**Root cause (exhaustively pinned — bench/benchlog.md 2026-08-03):** instrumented `Frame::
ComputeStereoMatches` — rectification is FINE (right kp on the same rows, dy≈0), but the two OV9281
images don't **correspond**: ORB descriptor match is near-random (median best-Hamming ≈100/256; descPass
≈25/1200), SGBM density only ~29%. Ruled out, one by one: scene, L/R order, config, vertical alignment,
**focus** (owner refocused both lenses sharp+matched, 118/99→~600/580 — no change), **photometry**
(CLAHE/histmatch — no help), **noise** (Gaussian/NLmeans denoise — no help). It is fundamental to the
hardware: two cheap, subtly-mismatched OV9281 optics/sensors.

**Decision:** The OV9281 CamArray is **confirmed not VIO-grade** — matches CLAUDE.md §2 ("inference/
tracking/VLM dev only"; the **IMX296 GS pair = "the ONLY VIO-grade cameras"**). All SLAM software is
proven on EuRoC (22.8 fps, ATE 4.66 cm) and is drop-in ready for the IMX296.

**IMX296 wiring — plan of record:** two IMX296 on the **Pi 5's two native CSI ports** (`dtoverlay=imx296,
cam0` / `,cam1`) + **XTR hardware trigger** (1.8 V; R11 rework) — full per-camera CSI bandwidth, mainline
`imx296` driver, no multiplexer. **Camarray-HAT alternative:** the Camarray platform *does* list IMX296
support, so the existing HAT *could* run IMX296 — BUT requires Arducam's Camarray-specific IMX296 modules
(standard modules won't work) + a **firmware reflash** (per-sensor) + the stereo (not quad) config; a
ready IMX296-stereo Camarray kit was not confirmed (OV9281/IMX477/IMX708 stereo kits exist). Native-CSI
path is cleaner and preferred. Verify against the HAT SKU before buying. (Sources: Arducam Camarray docs.)

**Silver lining:** the owner's refocus (sharp + matched) improves the OV9281 for its *actual* jobs
(depth/tracking/inference), which don't need cross-camera correspondence.

## 2026-08-04 — RETRACTION: OV9281 CAN do stereo SLAM; the failure was calibration, not the sensor

**Supersedes the 2026-08-03 decision above.** Owner challenged "IMX296 won't fix it — it's the
implementation," and a controlled re-investigation proved them right. Full write-up:
`docs/2026-08-slam-ov9281-progress.md` (Part 3); scripts in `bench/ov9281-stereo/`; numbers in
`bench/benchlog.md` (2026-08-03/04 entries).

**What was actually true:**
- The OV9281 pair is **valid stereo** — free descriptor matching gives median Hamming ~26 and **80% of
  matches fit one fundamental matrix**. The old "near-random descriptors" reading was measured *under* a
  broken rectification (the `ComputeStereoMatches` same-row search), so it compared wrong points.
- The stored stereo **calibration is broken** — it doesn't even rectify its own checkerboard captures
  (126 px corner error), and the checkerboard set's L/R correspondences are inconsistent (unrecoverable).
- **Scene self-calibration must be fit from STILL frames.** Fitting from a moving clip inflates the
  recovered inter-camera rotation by ego-motion (true ~2.4° → bogus 7.5°) and wrecks rectification.
- **Controlled still-then-move test:** with a still-fit calibration, rectification is 0.00 px static and
  ≤ 2 px under fast motion, and **ORB-SLAM3 tracks the clip with 2/207 dropped frames (~1%)** — clean.
- A **small real desync** (~10–16 ms L/R offset, `dy ≈ 0.108 × motion`) adds ≤ 2 px under motion — within
  ORB-SLAM3's tolerance. A precision refinement, not a blocker.

**Decision:**
- **OV9281 stereo SLAM is viable** with a correct calibration. It is no longer "not a stereo-SLAM camera."
- The **IMX296 GS pair remains the product path**, but for the *correct* reason — capture **simultaneity**
  (hardware trigger), worth ≤ 2 px — not "cheap/mismatched optics."
- **Action:** recalibrate the OV9281 pair on a **rigid mount** (current rig is cardboard + tape, hand-moved)
  from still frames or a fresh, well-diversified checkerboard shoot; verify |dy| ≈ 0 before trusting a run.
- The 2026-08-03 "hardware wall" reasoning (and the `dafdb70`/`4d59735`/`1326a4a` conclusions) are wrong.
  This is a rule-9 failure caught late: an assumed-correct component (rectification) was the actual bug.

## 2026-08-04 — Stereo target-range: NPU multi-tenancy spike → Option B (single-process stereo)

**Context:** S2 v1 (metric distance of the tracked object) originally designed as CM3 track + OV9281
range — two processes, both running yolov8m, needing concurrent NPU. Task-1 spike (garuda-sdk plan
`docs/superpowers/plans/2026-08-04-stereo-target-range.md`) tested that assumption on the 10H.

**Findings (measured on this Pi, HailoRT 5.1.1 / h10-hailort):**
- yolov8m HEF = `/usr/share/hailo-models/yolov8m_h10.hef` (same as garuda-inference). On-chip NMS-by-class;
  `bindings.output(name).get_buffer()` returns a **per-class list of arrays** already (easy decode). Solo
  infer **36.2 fps**.
- **Two separate processes cannot share the Hailo by default:** the 2nd gets
  `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` — a plain `VDevice` seizes the NPU exclusively.
- The HailoRT **multi-process service daemon is NOT packaged for this stack**: no systemd unit, no
  `hailort_service` binary, not in apt. Cross-process sharing would require source-building/installing it
  against the pinned 5.1.1 Hailo stack — high risk per rule 11. **Not done.**
- **Intra-process** sharing is free (one process, one yolov8m fed both streams — 30 fps CM3 + 6 fps stereo
  ≪ 76 fps capacity).

**Decision (owner: user, 2026-08-04):** Ship **Option B** — do detection + single-target lock + ranging
**entirely in garuda-depth on the OV9281 stereo pair** (one process, one yolov8m, no cross-process NPU
conflict, no system change). The CM3 is not run concurrently for this use case; the mono size-estimate
fallback is dropped (distance is stereo, or "no range"). True cross-process concurrency (CM3 colour
tracking + stereo ranging together) is deferred to **P6**, where the concurrent-NPU work — and, if needed,
building the HailoRT multi-process service — is already scoped.

**Licence note:** yolov8m (Ultralytics) is **AGPL-3.0** — the same detector already used on the bench
(P1). It is bench/eval, **not product-cleared**; the ranging code itself (`target_range`, `roi_disparity`)
is Apache/clean. Product tier needs a permissively-licensed detector (yolox/yolov6). Tag the yolov8m use
`not-product-cleared`.

## 2026-08-07 — Platform migration to HailoRT 5.3.0 + YOLO26 (fresh SD, single color camera)

**Why:** 5.1.1 constraints (grayscale-stereo flicker, yolov11m missing small objects like phones,
relative-only depth) kept blocking the single-camera perception goal. Owner directed the upgrade.

**Key facts (all verified):**
- The Pi's `h10-*` Hailo stack (Raspberry Pi apt repo) is pinned at **5.1.1**; no public 5.4.0 for ARM.
  Hailo Dev Zone has **HailoRT 5.3.0 arm64** (`hailort_5.3.0_arm64.deb`, cp313 aarch64 whl,
  `hailort-pcie-driver_5.3.0_all.deb`) — 5.3.0 is the newest ARM runtime; **firmware is bundled in the
  pcie-driver deb** (/lib/firmware/hailo/hailo10h/, auto-flashed by the driver at boot — no fw-update).
- YOLO26 + DepthAnything + yolov11m all have **v5.3.0 compiled HEFs** on the public model-zoo S3
  (`.../Compiled/v5.3.0/hailo10h/`). So 5.3.0 runtime + v5.3.0 HEFs is a matched set.
- **CRITICAL kernel patch:** the 5.3.0 pcie-driver source uses `del_timer_sync()`, REMOVED from the
  kernel (>=6.15) in favour of `timer_delete_sync()`. Against rpi kernel 6.18.34 the dkms build fails.
  Fix: `sed 's/del_timer_sync/timer_delete_sync/;s/\bdel_timer\b/timer_delete/'` on
  `linux/vdma/monitor.c` (2 occurrences), then `dkms build/install`. **A re-flash MUST re-apply this.**
- Done on a **spare SD (fresh Raspberry Pi OS Trixie 64-bit)** — the working 5.1.1 card is preserved.
- **YOLO26 HEF is NMS-free/DFL-free:** 6 raw tensors (3 box ltrb-heads H*W*4 + 3 class-logit heads
  H*W*80 @ strides 8/16/32). Decode = box*stride anchor-free + sigmoid(class) + light NMS
  (`hosts/pi5/hailo_yolo26.py`). Validated: suitcase @0.92, person @0.93, boxes exact.

**Result:** new bench = Trixie / kernel 6.18.34 / HailoRT+FW+driver **5.3.0** / Python 3.13.5.
Single-camera perception `hosts/pi5/garuda_mono.py` (systemd `garuda-mono`, :8098): CM3 (rpicam-vid)
-> YOLO26 detect + DepthAnything relative depth -> live-calibrated metric distance, self-served GUI.
Numbers: yolo26m **58 fps** (hailortcli run2), mono pipeline **25 fps**. Licence: YOLO26/yolov11m
Ultralytics AGPL (not-product-cleared); DepthAnything V2 small Apache-2.0.

## 2026-08-07 — Metric depth: DepthAnything V2 (relative) -> YOLO26-depth (metric) in garuda-mono

Why: DepthAnything V2 ViT-S outputs RELATIVE depth — needed 2+ manual cal points per scene and
still jittered (~±18 % raw on a locked static-ish target). YOLO26-depth predicts metres directly
(unbounded log-depth head, ~0.02–150 m) and measured 7.7x faster than DA-V2-S per Ultralytics.

How the HEF is built (full procedure in `models/build_yolo26_depth_hef.sh`):
Ultralytics `yolo export model=yolo26n-depth.pt format=hailo name=hailo10h` on x86 with the DFC
5.3.0 wheel extracted from the Hailo AI SW Suite 2026-04 `.run` (`--nox11 --noexec --keep`).
The HEF is cut at the depth head's final logit conv; host decode = exp(clip(logit,-4,5))**cal_a
* exp(cal_b) with cal_a/cal_b from the exporter's metadata.yaml (`hosts/pi5/hailo_yolo26_depth.py`).

Findings (x86, 14 GB RAM):
- The exporter enables DFC QAT finetune + optimization_level=2 unconditionally -> OOM-killed twice
  (~6.6 GB anon RSS; TF CPU training). Fixes applied IN THE VENV exporter: finetune policy=disabled,
  optimization_level=1. Layer Noise Analysis is invoked UNCONDITIONALLY in the DFC's
  `optimization_flow.finalize_optimization()` (no level/policy gate) — it survived at level 1 on
  this box but is the next thing to stub if a bigger model OOMs.
- garuda-mono `_est()` now treats raw depth as metres (identity); the old relative->metric cal fit
  remains as an optional scale refinement. `_sample()` made map-size-agnostic (DA=224, Y26D=192).
- DepthAnything class + HEF kept on the Pi as a fallback path.

Licence: Ultralytics YOLO26(-depth) AGPL-3.0 — bench/eval, not-product-cleared (owner relaxation
2026-08-02). Product tier still needs a licence-clean depth model before Phase 8.

## 2026-08-07 (evening) — Production y26d HEF: GPU QAT infeasible on 6 GB → PTQ-only at level 2

- GPU restored after reboot (driver 580.173.02). TF 2.19 then saw the GPU but the hailo-export venv
  had no ptxas/libdevice (torch's nvidia wheels don't include nvcc) → every GPU op failed with
  "JIT compilation failed [Op:Log]". Fix: `uv pip install nvidia-cuda-nvcc-cu12==12.8.93` into the
  venv. (Never surfaced before: the broken driver hid the GPU and everything silently ran on CPU.)
- QAT finetune (distillation: float + quantized nets co-resident at 768²) OOMs the 6 GB RTX 3060 at
  batch 8, 4 AND 2 (even with TF_FORCE_GPU_ALLOW_GROWTH=true); observed 323 s for step 1/512 → even
  a fitting batch-1 run projects to a day+. DECISION (owner): PTQ-only — finetune policy=disabled,
  optimization_level=2 kept, 1024 calib images (256 CM3 + 768 SUN RGB-D val; `depth-calib.yaml`).
  CM3 frames carry placeholder depth npys — the loader needs them to exist, calibration reads images
  only. Venv exporter patch state now: level 2 + finetune disabled (no batch_size arg).
- Layer Noise Analysis is still unconditional; at level 2 it OOMs the GPU but degrades to a WARNING
  (skips stats) and the flow completes — no stub needed.
- Survey (owner asked): NO pre-compiled metric indoor mono depth model exists for hailo10h — model
  zoo carries fast_depth/scdepthv3 (relative) + stereonet (collapses indoors); hailo-apps wraps the
  same scdepthv3 and its new YOLO26 HEFs are detect/pose only. Locally-compiled yolo26m-depth
  remains the only metric option.
- Probe gate PASS on deploy (logit std 0.263 vs ~0.04 collapse) — benchlog. Move-test + tape next.

## 2026-09-02 — Hailo-15L SBC arrives (not 15H); boots the stock 1.12.0 image, no re-flash

- The "Hailo-15H EVB" on the bench is a **Hailo-15L SBC rev 2.x** (silkscreen PCB00150 Rev2.0,
  FTDI descriptor `SBC_H15L`, identify → HAILO15L). Hailo's lowest-throughput 15 variant: same
  SoC family, SDK, BSP, ISP path, HailoRT 5.3.0 — a fair proxy for everything except NPU headroom.
  DFC 5.3.0 on the PC already targets `hailo15l`. Product-tier target stays Hailo-15H; never read
  15L fps as 15H fps (rule 1).
- The eMMC already holds `vpu-stability-v1.12.0` = the newest Vision Processor SW Package; the QSG
  (rev 1.3) says skip programming at 1.12.0. DECISION: **no re-flash**; keep the prebuilt boot
  chain + `.swu` + `hailo15_board_tools` venv on the PC for recovery only (QSG §2.5 swupdate flow:
  tftpd-hpa on the PC at 10.0.0.2, `/etc/run_swupdate.sh -r <swu> -s 10.0.0.2` on the board).
- Why the console looked dead for ~40 min: (1) the boot ROM on non-secure parts never transmits,
  so silence is not diagnostic; (2) getty only re-prints `hailo15l login:` on a keypress; (3) with
  DTR/RTS dropped the FT230X link returns garbled text; (4) the first "power-cycles" did not cut
  12 V. Two blind recovery loads read boot text at 57600 as garbage — that was the first sign of
  life. Unexplained residue: silence at the factory ON/ON setting before the first true
  power-cycle — QSG fig. 2 shows a Power Button and separate PWR-IN / PWR LEDs; if it ever happens
  again, check that BOTH LEDs are lit before assuming a boot failure.
- Pi bench card (Trixie, garuda user) was in the PC reader and was NOT overwritten; a copy of
  /home/garuda, /etc, /opt, bootfs lives at `/media/bhanu1234/Development/pi-backup-2026-09-02/`.
  The Pi is offline while the SBC uses the PC's only wired port (`h15-link` vs `pi-share`).
- Licence notes: hailo15_board_tools / VPSP are Hailo-proprietary bench tools (PC-side only, never
  in `services/`); meta-hailo-soc on GitHub is the Yocto layer set for a later product-tier port.
- **Stock demo state (2026-09-02 12:45):** at boot the image auto-runs `face_landmarks_app` on
  /dev/video0, and ~15 s in the kernel OOM-killed `isp_media_server` (the userspace ISP daemon the
  `hailo15_video` driver posts pipeline events to) — after that every `create_pipeline` times out
  (−11) and `camera-viewer-server` dies with "Device '/dev/video0' failed during initialization".
  Its watchdog did not restart it. Workaround that works: `/etc/init.d/isp_media_server restart`,
  then `setup_hailo_sensor.sh` (picks imx678 + theia_sl410m 4k config), then `camera-viewer-server`
  → http://10.0.0.1/#/ (port 80), sensor streams SDR 30 fps; one `isp_mp_axi_bresp` error IRQ at
  stream start, non-repeating. The viewer warns RAM < 3 GB → clip pipeline unsupported (2 GB 15L).
  Open: what respawns `face_landmarks_app` (not in init.d), and whether the boot OOM recurs on a
  clean reboot — if so, disable the face demo at boot (memory budget is the 15L's real limit).
- **Clean reboot 2026-09-02 12:50 (serial-captured):** U-Boot 2022.01 → kernel → login prompt in
  8 s, `isp_media_server` survived (the earlier OOM is a boot race, not deterministic). The
  camera hog is a **leftover burn-in recorder**: `/etc/rc5.d/S99h15-record-service` →
  `/home/root/H15_record_script.sh AI_ISP_Gen3_Basic,AI_ISP_Gen3_1_Basic 30 continuous` → runs
  `face_landmarks_app --disable-ai --record` in a loop, ~55 MB 4K H.264 clips every ~40 s into
  `/mnt/usb/H15_VIDEOS` **on the eMMC rootfs** (no USB mounted; ~460 MB after ~10 min of uptime,
  rootfs 6.7 G with 4.4 G free). Symlinks dated "Mar 9" (board RTC unset; dates are bogus). Not
  part of the stock image — Hailo stability-run residue. Owner decision 2026-09-02 12:57: **disabled permanently** via
  `update-rc.d -f h15-record-service remove` (init script + `H15_record_script.sh` kept for
  reference); the 12 clips (496 MB) deleted, rootfs back to 1.6 G used / 4.8 G free. PC side: `h15-link` now autoconnect=yes priority 10 so a link bounce no longer
  hands eno1 back to `pi-share`; use `nmcli con up pi-share` when the Pi returns to the cable.
- **Capability probe for the plan (2026-09-02 13:30, measured on the SBC):** `ethtool -T eth0` →
  **software timestamping only, no PTP hardware clock, no /dev/ptp** (macb/GEM on this SoC+BSP) —
  the 15L SBC cannot be a hardware-timestamped PTP node; the plan's single-clock-domain rule needs
  the switch/FC side or a GPIO/PPS scheme if a Hailo-15 SoC sits on the camera path (re-check on the
  15H SoM, do not assume). Sensor drivers in the BSP: imx662/664/675/678/334/307/715 only — **no
  IMX296** (global shutter) → driver backport needed for VIO-grade cameras. Hardware video encoder
  present (`/dev/hx280enc`, Hantro; 4K H.264 30 fps demonstrated by the recorder), Tensilica DSP via
  XRP (`/dev/dsp0`), 2× 4-lane CSI-2 RX, ISP with HDR/AI-ISP + GMV/EIS. CPU 4× A53 @ 1.1 GHz
  (performance governor), 2 GB RAM of which ~1.25 GB is CMA → ~600 MB for user space.

## 2026-09-03 — (tracker engines) a second tracker engine, SDK Kalman `TrackerStage`, added behind the mono lock rules

- **Why a second engine.** Mono's own ByteTrack (`include/garuda/bytetrack.hpp`, ported to the SBC
  at M1) is IoU-only against a velocity-predicted box; the yolov8m A/B (`bench/benchlog.md`
  2026-09-03 "yolov8m A/B for small-object (cell phone) tracking") showed the detector was not the
  small-object tracking problem — every gap in detection became a coasting box that flew off-frame
  and minted a new id on return, with either detector. The board's Hailo SDK ships its own
  Kalman-filtered `TrackerStage` (`hailo_analytics/pipeline/ai/tracker_stage.hpp`,
  `hailo_postprocess_tools/tracking/hailo_tracker.hpp`) as an alternative id/box source — plugged in
  behind the *same* `LockResolver::step()` mono already uses (`2df8435` made the resolver
  engine-neutral; `4ac8b9f` added the `"hailo"` engine choice), so click/target/coast/re-acquire
  behaviour and the `/api/state` schema stay identical regardless of which engine is picked
  (`hosts/hailo15l/README.md` §9, written the same day, has the full engineering detail — this entry
  records only the decisions and the facts that drove them).
- **SDK tracker facts, verified from source and on the board (README §9):**
  - **One class-agnostic tracker, one-to-one assignment (corrected 2026-09-04 — the bullet below
    replaces an earlier, wrong "per-class association" claim; see the final-fix-wave brief's I2,
    `.superpowers/sdd/2026-09-03-hailo15l-kalman-tracker/final-fix-brief.md`).** The JDE tracker
    (`src/tracking/jde_tracker/`) has no class anywhere in its association: every detection in a
    frame, of any label, competes in the SAME single one-to-one LAPJV (Linear Assignment Problem,
    Jonker-Volgenant) assignment against the same pool of existing tracks. (Only the separate,
    unused `HailoLightweightTracker` does genuine per-class matching — see the sentence below.) So
    with `classification_id=-1` (every class fed to the tracker), an overlapping detection of a
    DIFFERENT class on the same physical object — a `chair`/`suitcase`/`tv` box drawn on a person,
    say — competes for that object's track slot in the same assignment problem as the correct
    detection, and can win it (stealing the id onto the wrong-class box) or split it (leaving the
    real detection unmatched, minting a new id). `classification_id` does not turn on per-class
    association inside the tracker; it removes the competition by never handing the tracker any
    other class's detections at all (`block_non_tracked_classification_id=false` still lets those
    detections reach `det_sink`, just without ever entering the tracker's assignment problem).
    Measured on this bench, twice, before either fix below existed: `phone_kalman2.txt` (lock class
    flipped across `{cell phone, knife, tv}`, `lock.id` null 381/894 states) and `person_kalman.txt`
    (lock class stayed `person` throughout, but the lock id jumped 5 times in one 150 s walk with
    `lock None` never occurring) — `bench/benchlog.md` 2026-09-03 "Kalman tracker engine ... phone
    and person routines" has both tallies verbatim. Sharper evidence of the churn this causes,
    verified independently in the 2026-09-04 fix round (`python3 -c` over `person_kalman.txt`): **22
    distinct person-labelled ids appear within just the first 61 s** of that capture's 150 s span
    (all under `classification_id=-1`) — after which no new id appears for the remaining ~89 s, i.e.
    the churn is front-loaded, consistent with the tracker settling once the LAPJV assignment stops
    losing the person's detection to a competing class. `hosts/hailo15l/README.md` §9 has the
    engineering detail; the SDK also ships `LightweightTrackerStage` (genuine per-class matching,
    configurable smoothing) and `DetectionTrackerStage`, neither evaluated on this bench.
  - **Setters auto-vivify.** `HailoTracker::GetInstance().set_*()` writes through
    `std::map<std::string, JDETracker>::operator[]`, which default-constructs an entry if the key
    isn't there yet — it never throws and never no-ops. Calling the setters before
    `pipeline->start()` (this node's approach, `node_main.cpp`) is safe either way: whichever runs
    first (our setters or `TrackerStage::init()`'s own `add_jde_tracker` emplace, which is a no-op if
    the key exists), the six tuned fields end up correct, verified both from source
    (`hailo_tracker.cpp`/`jde_tracker.hpp` under the SDK's `usr/src/debug`) and empirically (the
    applied-params log line, zero errors/exceptions in the log from `starter begin` onward, plausible
    persistent-id tracks on every subsequent poll).
  - **`AREA` interpolation is unsupported on this board's DSP resize path** (not a tracker fact, but
    found the same day working this branch's medialib profile, and relevant to the DSP-dependent
    parts of the M5 roadmap below): `libmedialib`'s schema lists `AREA`/`BICUBIC`/`BILINEAR`/
    `NEAREST_NEIGHBOR`, but selecting `AREA` makes the deployed DSP resize path reject it at runtime
    — `hosts/hailo15l/medialib/make_profile.py` quotes the error verbatim:
    `[hailodsp] [error] [resize.cpp:980] [dsp_telescopic_multi_crop_and_resize_perf] Error:
    Interpolation type (2) not supported` — and the pipeline produced no frames while it was
    selected. Reverted to `BILINEAR` (what every prior profile used); full writeup
    `hosts/hailo15l/README.md` §6.
- **Label-vote decision (`18af174`).** A one-frame mislabel on a *surviving* id (the tracker keeps
  the same id, but a stray frame's winning class briefly differs) was redirecting the lock's
  reported class. Fixed by having `HailoTrackAdapter` report a track's label by majority vote over
  its recent history rather than the current frame's label alone — a different mechanism from
  `classification_id` below, because it does nothing for the case where the SDK tracker itself
  decides a stray frame is a *different* id (that case has no surviving id to vote on).
- **`classification_id` decision (`87dd48d`).** For the class-agnostic-competition fragmentation
  itself (not the label-flicker case above; corrected 2026-09-04 — see the bullet above), the fix
  adopted is the stock TAPPAS demo pattern: set `tracker.hailo.classification_id` to the one class id
  the deployment cares about (`1` = person in the stock post-process's 1-based labelmap; `0` in our
  own `libyolo26_post.so`'s 0-based COCO — the numbering is per post-process plugin, not universal,
  README §9 has the table) so the SDK tracker only ever assigns ids to detections of that one class —
  removing every other class from the competition entirely, not restricting the tracker to "its own
  class" per detection (there is no such per-class partition); every other class's detections still
  reach `det_sink` but never get a tracking id and so never appear in `tracks[]`. Verified:
  `person_kalman_cls.txt` (owner
  static) — 1 person id, 100% live-person states, 0 lock-None states, for the capture's full 150 s.
  `services/garuda-perception/config/perception-yolov8m.json` now ships with `classification_id: 1`.
- **Owner's direction for the two engines going forward** (session, same day): person follow uses
  the SDK (`"hailo"`) engine with the person profile (`classification_id: 1` + majority-vote labels)
  — this is now the checked-in default for `perception-yolov8m.json`. Small, multi-class targets
  (the phone routine) are not considered solved by either engine as measured (`bench/benchlog.md`
  same-day section) — the owner's proposed direction is the **mono** engine with a *bounded*
  prediction (something short of ByteTrack's raw per-frame velocity extrapolation, which is what
  sends a coasting box thousands of pixels off-frame) plus the DSP's zoom-window crop (spec §8.1 M5,
  item 2: a DSP crop+scale around the locked box feeding the detector a full-resolution window of
  the target) so a small object stays large enough in the network input to keep being detected.
  Neither the bounded-prediction change nor the zoom window is built yet — proposed only.

## 2026-09-04 — (tracker engines) final-fix wave: stale-frame fix, mechanism correction, minors

Whole-branch review (`.superpowers/sdd/2026-09-03-hailo15l-kalman-tracker/final-fix-brief.md`) on
`feat/hailo15l-kalman-tracker` before merge. Two Important findings and a set of minors, all fixed
in this round (report:
`.superpowers/sdd/2026-09-03-hailo15l-kalman-tracker/final-fix-report.md`):

- **Stale frames were published as fresh (I1).** SDK source (`jde_tracker_update.hpp:130-143`,
  `:302-313`; `strack.hpp:327-337`): an unmatched Tracked strack is re-added to the ACTIVATED list
  (not Lost) for up to `keep_tracked_frames` frames after a miss, and `multi_predict` never writes a
  predicted box back — so the stage re-emits the track's last matched box as if it were a fresh
  detection for up to 5 frames (the deployed default) after the object actually left, and
  `HailoTrackAdapter` reports `coasting: false` on those stale frames. Fixed by setting
  `tracker.hailo.keep_tracked_frames: 0` in `config/perception-yolov8m.json` — an unmatched strack
  now goes straight to Lost on the next miss; re-association across a real gap is unaffected because
  Lost stracks still live in `strack_pool` for `keep_lost_frames` (75, unchanged). Full mechanism
  writeup: `hosts/hailo15l/README.md` §9 "2026-09-04 fix — stale frames were published as fresh".
  Deploy + board verification: **PENDING — board unreachable** (link lost 2026-09-03 09:17:52; two
  `ping` retries at 2026-09-04 09:55 IST, 100% loss both times) — config change committed and
  cross-built clean, capture owed once the board answers.
- **"Per-class association" was the wrong mechanism (I2).** The 2026-09-03 tracker-engines entry
  above, `bench/benchlog.md`, and `hosts/hailo15l/README.md` §9 all previously claimed the SDK
  tracker associates a detection only against candidates of its own class. The JDE tracker source
  (`src/tracking/jde_tracker/`) has no class anywhere in its association — it is one class-agnostic
  tracker running a single one-to-one LAPJV assignment across every detection in a frame regardless
  of label. The corrected bullet is now inline above (2026-09-04, in the "SDK tracker facts"
  sub-list); all three docs corrected in this fix round. The observed effect is unchanged and still
  the evidence: 22 distinct person-labelled ids within the first 61 s of `person_kalman.txt`
  (`classification_id=-1`), verified independently in this round (`python3 -c` over the capture).
  `LightweightTrackerStage` (genuine per-class matching) and `DetectionTrackerStage` are both shipped
  by the SDK as alternatives — neither evaluated on this bench (README §9 note).
- **Undisclosed confounds in the 2026-09-03 A/B (I4).** (a) The mono rows in that section ran
  `track.min_hits 2` plus ByteTrack's own `high_thr 0.4` birth gate, while the hailo rows ran
  `min_hits 1` with no confidence gate on a new track's birth — so the "no-phone states" column is
  not apples-to-apples between engines; the live-conf mean gap (0.47 hailo vs 0.65 mono) is the
  fingerprint of that gate difference, not necessarily a detection-quality difference. (b) Every
  hailo-engine row in that section was captured before I1's fix, so up to 5 frames per real gap were
  silently re-emitted as live (non-coasting) rather than counted as coasting — the hailo rows'
  "coasting entries" and "no-\*-states" columns undercount real gaps relative to what I1's fix would
  now report.
- **Minors:** unknown `tracker.engine` now refuses to start (`node_main.cpp`) rather than silently
  defaulting to `"mono"`; the missing-tracking-id warn-once now fires only when
  `classification_id == -1` (expected under a single tracked class, so it counts silently instead);
  startup now logs `keep_lost_frames` vs `max_lost` and warns if they differ; the four
  previously-uncommitted 2026-09-03 captures (`phone_kalman.txt`, `phone_kalman2.txt`,
  `phone_kalman_loose.txt`, `person_kalman.txt`) are committed gzipped under
  `bench/evidence/2026-09-03-tracker-engine-captures/`, and `compare_phone_runs.py`/
  `compare_person_runs.py` now open `.gz` inputs transparently; `models/fetch_yolov8m_h15l.sh` +
  `models/yolov8m_h15l.md` + a `models/LICENCES.md` row were added for the yolov8m zoo HEF used
  throughout the A/B and tracker-engine sections (previously fetched ad hoc, undocumented as a
  model artifact). Full list and verification output: the final-fix report path above.

## 2026-09-04 — Owner direction: object detection/tracking/follow on the drone is now the main line; VIO and the rest are parked

- Stated by the owner in session, 2026-09-04 morning: **"object detection, tracking and follow on
  the drone is the main goal now; VIO and the others are parked."** This supersedes the ordering in
  `docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md` §8 (M3 depth/calibration,
  M4 packaging) and §8.1 (M6 VIO groundwork) to the extent they are not already done: whatever
  remains of M3/M4 and all of M6 wait until follow (M5) works on the drone. M5 itself (§8.1) is
  unaffected in substance — it was already "the owner's stated goal for the board" per that
  section's own heading — this decision just makes it explicitly the *only* active line rather than
  first-in-a-queue. Recorded in the spec (§8.1, one-sentence status note at the top) so it is not
  lost the way §7-vs-branch staleness has bitten this file before (rule 8: structural review at
  milestones — this is exactly the kind of owner redirection that needs to survive a branch merge).

## 2026-09-04 — F1 lock core: a dedicated time-based locked-target tracker, not a borrowed multi-object-tracker id

Implemented on `feat/hailo15l-kalman-tracker` (Task 1: `e06a78e`, `fa71db9`, `c2ee44b`, `6284b93`;
Task 2: `777e826`, `0a138c3` — HEAD at time of writing). Design: spec §8.2
(`docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md`), plan
`docs/superpowers/plans/2026-09-04-hailo15l-lock-core.md`. Full mechanism/config/snapshot writeup:
`hosts/hailo15l/README.md` §10.

**Why.** The 2026-09-03 Kalman-tracker A/B (benchlog, this file's own "final-fix wave" entry above)
measured the pre-F1 lock for what it actually was: a multi-object-tracker id the resolver happened to
be pointing at. It inherited every id split from the tracker below it, and after its own re-acquire
delay it would silently hand the published lock to "the highest-confidence live object of the same
class anywhere in the frame" — the observed failure modes were the phone lock flipping across
`{knife, cell phone, tv}` and a 150 s person walk producing 5 distinct lock ids with the lock never
going empty in between. Tuning the underlying tracker's Kalman/IoU gates could not fix this, because
the bug was architectural: identity and observation were the same variable.

**What changed.** `LockCore` (`include/garuda/lock_core.hpp`/`src/lock_core.cpp`) is a new,
engine-neutral component that owns one locked identity, separate from whichever multi-object tracker
(mono or the SDK's hailo engine) is running underneath it:

- **Time-based, not frame-based.** All windows (`occlusion_ms`, `reacquire_ms`, `expire_ms`,
  `control_valid_ms`) are milliseconds off the frame's ISP clock, not frame counts — the old
  `max_lost`/`reacq` frame-count windows drifted with detector fps (25 vs 30 fps was an open
  confound in the A/B).
- **Prediction never reaches the screen.** The published box is the Kalman-filtered box only while
  CONFIRMED; the last confirmed box, frozen bit-exact, while OCCLUDED/REACQUIRING; none while
  LOST/NONE. The internal predicted centre is used for gating/search only — a viewer never sees a
  guess presented as an observation.
- **Guarded re-acquisition, ambiguity reported not resolved.** A winning candidate must clear
  `min_score` AND beat the runner-up by `ambiguity_ratio` — two similarly-scoring candidates (the
  two-person-crossing case) produce no association that frame (state stays OCCLUDED/REACQUIRING)
  rather than a coin-flip pick. This is the direct fix for the A/B's observed failure mode.
- **Identity vs. observation are separate published facts.** `identity_locked` can be true (LockCore
  still "remembers" the target) while `observation_valid` is false (no fresh sighting this frame) —
  a follow controller (F2/F3, not built) is meant to act only on `observation_valid`, never merely on
  an id still being locked.

**The Rulings that shaped the filter tuning and hand-over logic** (full detail:
`.superpowers/sdd/2026-09-04-hailo15l-lock-core/progress.md`):

- **Ruling 1 (fix round 1):** the initial gains gave only a ~17 px gate right after `lock()`,
  unable to associate a 20 px/frame mover. Replaced the process-noise model with white-noise
  acceleration (`q_acc_std`, then 1500 px/s²) plus a nonzero initial velocity uncertainty at
  `lock()` (`p0_vel_std 400 px/s`, not the "assume stationary" default) — first-post-lock gate
  became ~50 px.
- **Ruling 2 (fix round 2):** that WNA variance grows ~t⁴ uncorrected, so within ~1 s of coasting
  the ordinary gate would already cover most of the frame — meaningless for the
  OCCLUDED-vs-REACQUIRING distinction. Added `gate_max_px` (**300 px** radius cap on the *gating*
  variance only, never on the filter's own state or on the reported `uncertainty_px`) and lowered
  `q_acc_std` to **600 px/s²** (kept `p0_vel_std` at 400). Deployed default gate config is now
  `q_acc_std 600 / p0_vel_std 400 / gate_max_px 300` — after ~2 s of coasting the effective gate
  radius is exactly 300 px, and beyond that only REACQUIRING's widened, class+size-gated search
  applies.
- **Ruling 3:** extend the 25/30 fps-equivalence test to the 20 px/frame-mover-plus-gap scenario and
  the exact boundary values — a coverage-completeness fix, not a behaviour change.
- **Ruling 4:** a resolver pick that is **not a live observation this frame does not seed the lock
  core** — the hand-over waits for a frame in which that id is actually live. `LockCore`'s filters
  must start from a real measurement; a coasting box is stale data, and spec §8.2 already says
  prediction/stale state must never masquerade as an observation. Cost if this generalises badly: the
  lock can start up to one detector interval later than a click on a coasting box would otherwise
  allow — accepted as the safer failure direction.
- **Ruling 5 (fix round 1, Task 2 review; extended by Ruling 12 below):** on an explicit click,
  **the click locks the clicked object's own live `Obs` directly**, never the resolver's generic
  `lock_id`-is-live check — the initial `777e826` implementation had a gap where a coasting click
  could be silently redirected to a different live same-class track by the resolver's own re-acquire
  jump firing on the same frame, letting the system lock onto an object the user did not click. If
  the clicked id is not live that frame, the core is left NONE (Ruling 4 applies) rather than falling
  back to a different candidate — and with the core NONE the published `lock.id` is **null**, not the
  resolver's pick. The accepted residual: on the NEXT frame the generic hand-over may lock the
  resolver's own (possibly drifted) pick, so a click on a coasting box can still land on a different
  object one frame later. That is the cost of seeding only from live measurements, and F5
  (click–frame sync) is where it gets fixed.

**Final-fix wave (2026-09-04, whole-branch review).** Six Important and ten Minor findings, ruled on
by the controller and implemented in four commits on this branch. The three that change behaviour:

- **Ruling 11 — association is two-stage, not pooled.** Spec §8.2 wins over the plan's Task 1 text:
  the in-gate pool is scored first, and the widened full-frame pool is consulted only if the local
  search found nothing plausible at all. An **ambiguous** in-gate frame reports OCCLUDED/REACQUIRING
  and does **not** widen. The pooled version let a far same-class object veto a good local match — the
  review's probe: an in-gate 2σ candidate (score 0.672) was rejected as "ambiguous" the moment a
  conf-0.95 stranger stood anywhere else in the frame (0.5375 × 1.3 = 0.699 > 0.672). That is the
  two-person room the person profile exists for.
- **Ruling 14 — a widened-path floor and a bounded coasting prediction.** New `min_score_widened`
  (default = `min_score`) so the full-frame floor can be tuned separately from the local one; and the
  coasting prediction's centre is clamped to the frame, because `pos += vel·dt` otherwise runs ~600 px
  past the edge in a 2 s walk-out and the local gate stops covering the edge the target re-enters
  through. **Deviation from the ruling as written:** it specified clamping to
  `[-gate_max_px, frame_w + gate_max_px]`, but with the shipped constants that margin *is* the whole
  capped gate radius, so an edge re-entry still lands ≥ 350 px from the clamped centre (d² ≥ 12.25 >
  gate_sigma² = 9) — outside the gate the clamp was meant to bring it into. The clamp region is the
  frame itself; recorded in `lock_core.hpp`'s `Params` comment, `hosts/hailo15l/README.md` §10 and
  `.superpowers/sdd/2026-09-04-hailo15l-lock-core/final-fix-report.md`.
- **Ruling 15 — accept the deviation above as the shipped behaviour.** Clamping to the frame itself,
  not frame ± `gate_max_px`, is what actually ships. The accepted cost: a target that re-enters well
  inside the frame is still caught by the ordinary in-gate match, while one that leaves and re-enters
  right at a far edge still falls back to the full-frame widened search, exactly as before Ruling 14.
- **Ruling 10 — publish a lock epoch** (`lock.epoch`, +1 per `lock()`, never reset) **and Ruling 13 —
  publish `lock.box`.** The epoch is what makes "the lock moved to a different object" separable from
  "the tracker underneath renumbered the same object", which the bench's single "identity switches"
  column could not distinguish — it counted the failure F1 prevents and the success F1 delivers as the
  same event. `lock.box` closes the gap where three artefacts described `LockCore`'s box as published
  when it never left the process; the harness's off-screen metric now reads it instead of the tracker
  engine's `tracks[]` box.

**On-board rounds (2026-09-04, board back up).** Four real captures, four rounds of mechanism bugs.
The first two are about how the lock is *entered*; the third and fourth, once entry was fixed and
routines could finally be measured with the owner in view, are about how it is *held* — round 3 while
the target is visible, round 4 while it is hidden:

- **Ruling 16 (run 1).** The resolver auto-acquired a 29×194 px, conf 0.17 sliver of the owner still
  entering at the right edge, and `LockCore` took it as its size reference; every later frame of that
  person (up to 293×713 within 0.8 s) failed the then-fixed ±50 % size gate, so nothing could associate
  and the lock decayed to LOST. Fixes: the resolver may auto-acquire only above a confidence floor and
  clear of the left/right frame edges; the core's size gate became variance-aware
  (`max(size_tol·ref, gate_sigma·sqrt(size_var + r_size))`); and the bench's off-screen metric now
  counts a `lock.box` whose **centre** has left the frame, not one merely overhanging an edge (109 of
  run 1's rows were a legitimately frozen box of a target that had walked out).
- **Ruling 17 (run 1, honest limit of the variance-aware size gate).** The variance-aware size fix
  above does not, by itself, re-associate run 1's own sequence — the growth needed 68 px of tolerance
  within 167 ms, and the shipped `q_size` (50 px²/s) only grants about 43 px. Accepted as-is: run 1's
  actual cause was already removed by the auto-acquire edge/confidence gate (Ruling 16), so `q_size`
  stays at 50 until a real, legitimately-stale lock demonstrates the need for more.
- **Ruling 18 (run 2).** The gate above is necessary but not sufficient: the person profile carried
  several persistent low-confidence "person" tracks on static room objects, and one of them flickered
  over the confidence floor for a **single** frame, passed the gate on it, and held the lock for the
  rest of the 120 s capture — so the owner was never locked and the run measured nothing. Auto-acquire
  now additionally requires the candidate to clear the gate on `auto_min_streak` (5) consecutive live
  frames, and the resolver's re-acquire jump is gated identically; clicks stay ungated and `LockCore`'s
  own re-acquisition is untouched.

- **Ruling 19 (run 5 — the first routine-1 run with the owner actually in view).** With entry fixed,
  the failure moved to how the lock is *held*: on 306 of the 1048 rows where the tracker engine had a
  LIVE box for the locked id (29 %), the core reported no observation, and all three mechanisms were
  the same mistake — **the core's tolerances were absolute where the evidence is relative to the
  box.** The ruling makes them relative, and adds a same-id relaxation:
  - **M-A, the position gate.** A converged filter on a ≈650×650 person had a gate of ~10 px while
    the detector's own box centre jitters 40–60 px per frame on arm movement (the box width swung
    643→774), so the target's own live box was rejected until the gate regrew — `confirmed↔occluded`
    flicker at frame rate. Fix: per-axis measurement std `max(sqrt(r_pos), r_pos_frac·ref)`
    (`r_pos_frac` 0.10), a gate that is a proper Mahalanobis test against `S = min(P, cap) + R`
    (it previously omitted R entirely), and a radius floor `gate_min_frac·max(w,h)` (0.15).
  - **M-B, the size model.** A reference frozen on a 169 px-wide partial box could not follow the same
    live id growing to 594 px in 1.4 s as the owner walked toward the camera — the absolute
    `q_size` (50 px²/s) granted ~43–79 px against a needed 60–425 px, so the lock sat unmatched for
    the full 10 s and expired. Fix: size measurement variance `max(r_size, (r_size_frac·ref)²)` and
    process rate `max(q_size, (q_size_frac·ref)²)` px²/s (`r_size_frac` 0.15, `q_size_frac` 0.5/s),
    keeping the absolute constants as floors; a person on a wide-angle lens really does triple in
    size in ~2 s, and the model now says so.
  - **M-C, the widened floor.** The owner re-entered as a NEW tracker id, alone in the room, same
    class and size-consistent, and scored ≈0.45 against `min_score_widened` 0.5 — refused for 9 s.
    Fix: `min_score_widened` default 0.5 → 0.40, the ambiguity margin unchanged so two plausible
    candidates still block.
  - **Same-id relaxation (`same_id_gate_mult` 2.0).** A candidate carrying the core's own `last_id`
    gets both its position gate radius and its size tolerance doubled, with the motion/size score
    terms computed against those relaxed scales. Every candidate the node passes in is LIVE
    (`node_main.cpp`'s `live_obs`), so an id match is frame-to-frame continuity the multi-object
    tracker has already verified — evidence the core must not override with a stale reference. It is
    a relaxation, not a bypass: class, score floor and ambiguity margin all still apply.

  Also: the bench harness gains a `core_miss_live` column (that 306/1048 as a metric), because
  `obs_valid` alone cannot tell a core association failure from a detector miss and read 62 % on a
  run whose real problem was the gates. Replaying the whole run-5 capture through the fixed core takes
  the CONFIRMED fraction on live-target rows from 0.4643 to 0.9854 with no LOST — but that is a
  replay of the very capture the fix was derived from, and coarser (10 Hz) than the live pipeline, so
  it is a regression guard, not evidence the fix works on the board. Run 6 is.

- **Ruling 20 (run 7 — routine 2, occlusion behind a chair).** The 3-second hide recovered (the
  widened stage took the new id 2.7 s after the last observation — round 3 working). The 6-second one
  did not: the engine kept the locked id alive on the owner's HEAD, visible above the chair back, and
  the core followed that box down from 155×625 to 152×129 **and learned it as the target's size**, so
  when she stood up again as new ids at 321×271/367×569 the size term was 0, the in-gate floor was the
  strict `min_score` 0.5, the widened floor applied only out of gate and only for the first 3.5 s, and
  the lock ran down to LOST with the owner in plain view. Three changes:
  - **(a) Follow, but do not learn.** A candidate admitted ONLY by the round-3 same-id relaxation —
    one that fails the strict position gate or the strict size tolerance — now corrects position but
    not size; the size filter is left untouched and its variance keeps growing. Partial occlusion and
    edge clipping shrink a box transiently, and learning that as the target's size is what makes the
    full body unrecognisable when it re-emerges.
  - **(b) The score floor is a property of the band, not of the stage.** While REACQUIRING, every
    candidate — in-gate included — is judged against `min_score_widened` (0.40); CONFIRMED and
    OCCLUDED keep `min_score` (0.5). A mediocre local match moments after a sighting is more likely
    to be the wrong object; the same match after seconds of absence is the best evidence available,
    and refusing it just runs the clock down to LOST.
  - **(c) `reacquire_ms` 3000 → 9500**, so `occlusion_ms + reacquire_ms == expire_ms` and the widened,
    full-frame search stays open for the whole reacquiring band instead of closing 6.5 s before the
    lock expires. The two stay independent parameters and the ambiguity margin is unchanged; for a
    multi-person scene the real safety is appearance (F3, not built), and until then this is a
    deliberate trade — recover the target, and rely on the margin to refuse when the scene is
    ambiguous.

  **Honest attribution, because it is not what the ruling assumed.** Replaying the capture with the
  three changes toggled shows **(c) is what prevents the LOST** and **(b) is what turns a 3.1 s
  recovery into an immediate one**; **(a) changes nothing on this capture by itself**, because run 7's
  contamination was *gradual* (the box shrank over ~1 s, and with `q_size_frac` 0.5 a 625 px reference
  tolerates ±380–470 px per frame, so every step passed the STRICT gate and was learned legitimately).
  (a) is still the right rule and is unit-tested against the capture's own head boxes at 30 fps, but
  the open question it leaves — that "strict" and "relaxed" size tolerances barely differ for a large
  reference, i.e. `q_size_frac` may be too permissive — is recorded for a future ruling rather than
  changed here. Numbers, ablation table and red team: `bench/benchlog.md`'s "Run 7 (217fb04)" entry.

  **Ruling 21 (accepted concerns on round 4).** (a) is inert on run 7 specifically because the
  contamination there was gradual and cleared the strict gate at every step; it stays as the guard
  against an abrupt, single-frame size jump. `q_size_frac` stays at 0.5 rather than being tightened,
  because lowering it would re-break run 5's M-B (the size model that has to follow a person tripling
  in size as they walk toward the camera). The widened-search-to-expiry window ((c), `reacquire_ms`
  9500) is the loosest state the core has ever been in; routine 3 (two people in frame) is the
  untested risk this creates, and appearance matching (F3, not built) is the planned answer to it.

  Also, from this round the node logs operator events (`lock: click (x,y) -> id N` / `-> no track`,
  `lock: target '<class>'` / `target cleared`). A click and a `target` command are the only two paths
  that `unlock()` the core, so both appear in a capture as an epoch change or a bare NONE with no
  preceding LOST row — indistinguishable from a silent internal re-lock when reading a capture
  afterwards. The fast-lateral run had exactly one such unexplained unlock (rel. 401.58 s) and nothing
  in the log to attribute it to; `bench/evidence/2026-09-04-lock-core/ROUTINES.md` now states the
  reading rule.

The rest were smaller correctness/hygiene fixes: obs_age clamped at 0 under a backwards timestamp,
degenerate lock boxes rejected, a zero `isp_timestamp_ns` no longer switching clock domain mid-lock,
transition logging rate-limited, `lock.id` null whenever no identity is held, and a harness anchor bug
(a LOST/NONE row now clears the last-CONFIRMED anchor) that would have written a fabricated
time-to-reacquire into the benchlog. Full list and per-finding detail:
`.superpowers/sdd/2026-09-04-hailo15l-lock-core/final-review.md` and `final-fix-report.md`.

**Verification so far:** native (`ctest`) 11/11 green including the new `lock`/`lock_core` suites and
`test_snapshot`'s updated subset-check golden; cross-build (`build-h15l`) zero `warning:` lines.
**Deploy and on-board behavioural verification are PENDING — board unreachable throughout Tasks 2 and
3** (link lost 2026-09-04 09:17:52 per the owner). The lock-focused harness
(`bench/evidence/2026-09-04-lock-core/lock_metrics.py`) and the five owner routines it is meant to run
against (`bench/evidence/2026-09-04-lock-core/ROUTINES.md`) are built and self-tested against a
synthetic fixture and real pre-F1 captures; every number in `bench/benchlog.md`'s new F1 section is
`TBD-bench` until the board is back. Full detail: that benchlog section's red-team paragraph.

**Bench outcome 2026-09-04 (closing round, board back up, four on-board fix rounds through commit
`47fb866`).** Three of five owner routines passed on fresh captures with the numbers in
`bench/benchlog.md`'s F1 "Results" table — routine 1 (walk-out/return, run 6): confirmed 89 %, 0
relocks, 0 `core_miss_live`; routine 2 (occlusion, run 9b): every hide recovered within 0.9 s, 1 LOST
event (a walk-out past the 10 s expiry, by design); routine 4 (fast lateral, run 8): confirmed 99 %,
0 `core_miss_live`, one relock attributed to an operator action rather than a tracker failure.
Routine 3 (two-person swap) was skipped (owner: "no second person today") and stays `TBD-bench`.
What remains: routine 5 (phone, all-classes config) was still capturing at closing-docs time and
stays `TBD-bench`; a genuine full multi-second occlusion was never produced (the office chair's mesh
back never fully hid the owner), so the round-4 fix's core scenario is confirmed only by replaying
run 7's own capture, not by an independent fresh full-occlusion capture; and F2–F6 (visual tracker,
appearance, DSP ROI, click-frame sync, ego-motion) remain unbuilt.

- **Ruling 22 (run 10e — routine 5, the phone routine; on-board fix round 5).** The phone left frame
  at rel. 146 s and the core, REACQUIRING with round 4's widened floor applying in-gate, walked
  across different-class in-gate candidates (`knife`, `remote`, `hair drier`) and at rel. 165.71 s
  settled on a static `chair`/`suitcase` box, holding it CONFIRMED for the remaining twelve minutes
  while publishing `lock.class = "cell phone"` throughout — a false lock that the harness's `relocks`
  column could not see (it all happened inside one epoch) and that the class field actively hid.
  Three changes: a **class gate** (a different-class candidate is eligible only if it carries the
  core's own tracker id, in any state and in either stage — accepting, until F3 appearance exists,
  that an object re-labelled under a NEW id is not re-acquired until a same-class detection appears);
  a hard **`size_ratio_max` 1.6** on different-id candidates, on top of the variance-aware tolerance,
  because that tolerance grows with `obs_age` and had come to admit a 229×270 static box against a
  135×285 phone; and **`lock.class` now publishes the last associated observation's class** rather
  than the class frozen at `lock()`, with a matching `class_switches` column in the harness whose
  false-relock alias is `relocks + class_switches`. The class gate has no config knob by design, and
  `class_switches` necessarily reads 0 on every capture taken before this round — run 10e's own
  included — because those builds could not publish a class change at all.

- **Ruling 23 (run 8, ids 38/39 — on-board fix round 6).** The yolo26m HEF's baked NMS does not
  suppress a same-class box mostly contained inside another (run 8's own capture: a 819×595 full-body
  box and a wholly-contained 655×594 torso box on one person), so the SDK's class-agnostic tracker
  births a second id for it and `id churn 41` follows; `HailoTrackAdapter::update()` now drops the
  smaller of two same-class LIVE records when it is ≥80 % covered by the larger one
  (`tracker.hailo.dedupe_containment`), else drops the lower-confidence one of a pair at IoU ≥60 %
  (`tracker.hailo.dedupe_iou`), leaving coasting records untouched either way.

## 2026-09-04 — detector A/B on the SBC: yolov11s candidate (pending repeat)

One owner-paced 75 s phone routine per model (yolov11m, yolov8m, yolov11s, all-classes configs via
the new `bench/evidence/2026-09-04-lock-core/mk_allclasses.py`) put yolov11s ahead on live `cell
phone` detection rate (71.3 % of rows vs 47.2 % and 43.7 %) and on the still-phone sub-window (91.6 %
vs 17.1 % and 40.9 %), at the cost of the most duplicate-box rows (3.3 %) and the most tracker id
churn (26 distinct ids over 75 s). This is a single unreplicated, non-interleaved run per model with
no ground truth and a phone-angle confound on the still window, so it names yolov11s a follow-profile
candidate rather than a decision. Full numbers, the comparison table and the red-team paragraph are
in `bench/benchlog.md`, "Hailo-15L SBC: detector A/B on the phone" (2026-09-04 evening).

## 2026-09-04 — follow profile switched to yolov11s (owner decision after the A/B; repeat A/B still owed)

`services/garuda-perception/config/perception-yolov11s.json` (person profile, `classification_id: 1`,
hailo/Kalman tracker engine) is the documented **follow default** from on-board fix round 7 onward —
the deploy command in `hosts/hailo15l/README.md` §4, and what §§9–10 name as the shipped config.
`perception-yolov8m.json` stays committed and supported as the A/B alternative (it is what every
capture before 2026-09-04 evening ran on), as does `perception-yolov11m.json`; the three differ only in
their `hef` field.

This is the **owner's decision on the strength of the one A/B run per model** recorded above — it is
*not* a measured result promoted to a default. The A/B's own red team stands: one non-interleaved
75 s run per model, no ground truth, a phone-angle confound on the still window, and yolov11s carrying
both the most duplicate-box rows (3.3 %) and the most tracker id churn (26 ids/75 s) of the three. **The
fixed-protocol repeat (phone in a stand, three interleaved runs per model) is still owed** and stays
`TBD-bench`; if it reverses the ordering, the follow default moves back and this entry is superseded.

- **Ruling 24 (run 12 — on-board fix round 7).** The owner's "all over the place" was tested against
  the capture (`bench/evidence/2026-09-04-lock-core/run12_round7_jumpy_yolov11s.txt.gz`, analysed by
  the new `jumpiness.py`) and is not the lock box, which steps a median 0.5 px / p90 2.2 px per row
  with **zero** jumps over 80 px in 90 s. Two other mechanisms, one fix each. (1) The SDK's Kalman
  tracker births a track from *any* detection — it has no confidence floor, unlike mono's ByteTrack at
  `track.high_thr` — so every 0.17–0.19 junk detection in a cluttered room became a drawn track;
  `HailoTrackAdapter` now publishes an id only once it has been seen live at
  `conf >= tracker.hailo.birth_conf` (defaulting to `track.high_thr`, so the two engines admit the same
  detections), the flag sticky for that id's entry and lost with it, applied *before* round 6's dedupe.
  (2) `auto_min_streak`'s five **consecutive** gate-passing live frames were unreachable for a target
  the detector sees intermittently — the phone was live in 30.2 % of frames, and after the clicked lock
  expired auto-acquire never re-locked it (`lost` 68 % of rows) — so the count is now
  `auto_min_streak` frames within the last `lock.auto_streak_window` (15) frames the id appeared in,
  for both the auto-acquire branch and the re-acquire jump. 5 of 15 still refuses run 2's lone flicker.
  Both defaults are judgement, not sweeps, and **the live re-measurement of the round is `TBD-bench`**
  (`bench/benchlog.md`, "Round 7 — clutter and re-acquire").

- **Ruling 25 (on-board fix round 8 — class allow-list).** `classification_id` allows exactly one
  class, so the phone demo's all-classes config (`-1`) cluttered `/api/state` with every class that
  cleared the round-7 birth gate (120 s, real room objects: 15274 track entries, 3063 rows — `chair`
  3885, `handbag` 3137, `toilet` 2298, `laptop` 1905, `suitcase` 1379, `person` 989); `HailoTrackAdapter`
  now takes a `tracker.hailo.classes` allow-list applied before birth/dedupe bookkeeping (empty = all,
  unchanged), and `config/perception-yolov11s-phone.json` (`classification_id -1`,
  `classes: ["person", "cell phone"]`) is the first config to use it, verified live on the board with
  only `person`/`cell phone` in `/api/state`'s `tracks[]`.

- **Rulings 26–30 (on-board fix round 9 — outside code review, 2026-09-05).** An outside review of
  `feat/hailo15l-kalman-tracker` produced three probes that the controller reproduced against the
  round-8 build; each ruling below answers one of them and carries its cost. Evidence and the full
  before/after table: `bench/benchlog.md`, "Round 9 — outside review".

- **Ruling 26 — the core's input is all live detections.** The round-7 birth gate and the round-6
  dedupe are DISPLAY gates, but until now they also decided what `LockCore` was allowed to see, so a
  locked phone dipping below `birth_conf` for a second became invisible to the very tracker whose job
  is to ride that out. `HailoTrackAdapter::live_raw()` now returns this frame's live records after the
  class allow-list only and the node feeds those to the core, while the published list still gates the
  snapshot, the resolver and both new-lock paths — so a new lock needs a visible track and maintaining
  one does not.

- **Ruling 27 — dedupe protects identities.** The containment/IoU dedupe cannot distinguish "one
  person detected twice" from "one person standing behind another", and in the second case it silently
  deleted the farther person, who may be the locked target. Suppression is now allowed only for a
  record that is neither the protected id (the resolver's current lock, passed in every frame) nor
  older than `tracker.hailo.dedupe_protect_age` frames since its first emission (default 10) — which
  still suppresses duplicate births, young by construction, while sparing established tracks.

- **Ruling 28 — no out-of-gate new-id acceptance until appearance exists.** Out of gate the motion
  term is ~0, so a widened-stage score is confidence + size + class, none of which is *identity*
  evidence, and the ambiguity margin cannot help when there is exactly one wrong candidate (the
  review's probe: a lone new-id person 900 px away at conf 0.41 took the lock outright).
  `lock.widened_new_id` (default false) restricts that stage to candidates carrying the core's own
  tracker id, at a **measured cost**: routine 2's 6-second hide no longer recovers (139 LOST rows
  against 0) and the phone replay's confirmed fraction falls 0.8150 → 0.1934, so after a long
  disappearance the lock ends in LOST plus a *visible* re-lock instead of a silent transfer — a trade
  recorded in both replay tests, which now run each capture under both models.

- **Ruling 29 — stall expiry.** Every window was advanced only by the `update()` calls that actually
  arrived, so a pipeline that stopped calling it (stalled camera, blocked sink) could resume 11 s later
  and associate the first frame back as though no time had passed. `obs_age > expire_ms` now suppresses
  association before it happens, producing exactly the ordinary ticked expiry's output, epoch and log,
  and leaving the ticked path itself unchanged.

- **Ruling 30 — freshness.** `control_valid_ms` had been parsed from the `lock` block since F1 and
  consumed by nothing, leaving a consumer with only `observation_valid`, which says the core associated
  something on its last frame and says nothing about how old that frame is by the time it is read. The
  snapshot now publishes `lock.control_valid` = `observation_valid && (obs_age_ms + age_ms) <=
  control_valid_ms`, and the future follow controller must gate on that, never on `observation_valid`
  alone.

- **Ruling 31 (same round) — the board-truth viewer, and a portal defect NOT fixed here.** The review
  also found that the PC portal on `:8080` re-tracks the board's `tracks[]` with its own ByteTrack and
  keeps its own target, so nobody has yet *seen* what the board's lock core publishes — every
  judgement of "the lock is all over the place" has been made through a second, unrelated tracker. The
  shim's `/` is therefore now a real viewer (canvas overlay, `lock.box` coloured by state,
  click-to-lock, SSE-driven, no external resources). **The portal's re-tracking is an integration
  defect to fix on the portal branch; it is not fixed here.** Until the portal consumes the board's own
  lock, `http://<board>:8098/` is the only correct place to judge it.

- **Ruling 32 (on-board fix round 10 — the round-9 trade, re-ruled).** Ruling 28's blanket refusal of
  every out-of-gate different-id candidate was reverted because it did not stand as a plain boolean:
  it correctly removed the silent identity transfer but also cost the committed occlusion capture its
  6-second-hide recovery (139 LOST rows against 0) and dropped the phone replay from 0.8150 to 0.1934,
  i.e. it traded a real failure for a different real failure. Ruling 32 keeps the protection and asks
  instead for the evidence that exists without an appearance model: a different-id candidate is
  accepted out of gate only when it is the same class, its id was **born after the last confirmed
  observation** (`Obs::first_seen_ms`; −1/unknown is treated as pre-existing and refused), it is the
  only eligible out-of-gate candidate that frame, its confidence clears `widened_new_id_min_conf`
  (0.5) and `obs_age_ms` is within `widened_new_id_max_age_ms` (5000) — with same-id candidates exempt
  from all of it, since tracker continuity is itself identity evidence. The born-after-loss test is
  the one that matters: an id alive while the target was still confirmed is by construction a
  different object, so the classic two-person swap is removed outright, and routine 2 recovers fully
  (0 LOST rows) — while the phone capture stays at 0.1945 because condition (e)'s 5000 ms ceiling
  misses a single 6392 ms re-acquisition, a cliff documented with its sweep in `bench/benchlog.md`
  ("Round 10 — Ruling 32"). **Round 10b (Ruling 33) moved that ceiling to 7000 ms**, because the
  replay showed the capture needs a lone born-after-loss re-acquisition at 6.4 s and the sweep is a
  step function around it (<= 6000 ms → 0.1945, >= 7000 ms → 0.8150); the harness overstates the cost
  — it drives `LockCore` alone, so LOST is terminal there, whereas the node's resolver re-locks with a
  new epoch — but 7000 is what the evidence asks for, and the 10-s `expire_ms` is unchanged, so the
  different-id window still closes 3 s before the lock does.

## 2026-09-11 — YOLO11 detector path root-caused; controlled HEF rebuilt and deployed live

The Hailo-15L desk demo's weak phone detection was NOT tracker logic: on one identical 960
crop the stock-derived YOLO11s HEF scored the phone 0.14 while the published Model Zoo ONNX
and DFC 5.3 float emulation both scored ~0.78 (agreeing with each other to ~0.0023 on matched
phone scores). The old HEF's source weights and build recipe are unavailable, so the exact
build fault cannot be attributed to one setting — the decision is to own the build instead. A
controlled DFC 5.3.0 rebuild (Model Zoo YOLO11s ONNX, explicit full-range YUV, NV12 format
conversion, PTQ level 2 with 1,024 SUNRGBD calibration images; QAT infeasible on the 6 GB
GPU) matches the float scores, and replayed on the physical board against identical saved
inputs lifts the selected centered-crop phone scores 0.140→0.852, no-match→0.540 and
0.658→0.894; the current five-tile approximation improves from 1/3 to 2/3 reviewed frames.
Cost: 11 contexts vs 8, sequential replay waits ~18.3→23.8 ms (one crop) and ~94–96→122–124 ms
(five inputs). The controlled HEF replaced the live model the same evening; rollback is the
preserved previous HEF beside it plus a viewer restart, and the change is not boot-persistent.
Separately, blind native-4K 640 tiling found the phone in 0/3 reviewed frames (the object was
larger than a grid tile) — retained source pixels help only with scale-aware, target-centered
crops, so tiling and tracking remain separate problems. Fast-motion recall, identity
persistence and any accuracy benchmark remain unvalidated (`TBD-bench`). Full narrative:
`docs/2026-09-11-hailo15l-complete-summary.md`; evidence:
`bench/results/2026-09-11-yolo11-{4k-tiles,float-check,controlled}/`.

## 2026-09-12 — sequence A/B replay: controlled HEF validated on the recorded video

The 2026-09-11 entry's open validation was partly discharged with a 433-frame paired replay
of the phone-motion recording on the physical board (every 2nd decodable frame — live detector
cadence — five via-1080p letterbox tiles, identical bytes to both models, live model file
untouched, viewer paused/restored per run). Phone-frame presence at the 0.15 candidate floor
rose 44.1 % → 74.4 % (paired 133 gained vs 2 lost; longest hole 2.9 s → 0.5 s); at the 0.50
track-birth floor 29.8 % → 46.2 % with a ~3.1 s worst gap remaining; person presence is
saturated for both; sequential five-tile wait 94.4 → 122.1 ms (~+29 %). Replay-A's 44.1 %
matches the live session's 44.0 % on the same recording, supporting replay fidelity. Reading:
the controlled HEF is confirmed better on this recording and the binding constraint moves to
tracker coast/re-acquire and track birth after loss — not the detector. Still open: broader
scenes/targets, live-FPS impact of the slower model, identity persistence. Evidence:
`bench/results/2026-09-12-yolo11-ab-replay/`.

## 2026-09-12 — tracker re-acquire hardening (Phase A) + reference-repo study

Studied PixEagle (Apache-2.0, the design source), PX4-ROS2-Gazebo-YOLOv8 and cangozpi's
capstone (both unlicensed / GPLv3-vendored — ideas only, no code copied); full plan A-E in
`docs/superpowers/specs/2026-09-12-follow-platform-and-reacquire-design.md`. Phase A adds a
bounded, gated re-acquire to `garuda::fresh::Tracker`: on selected-track expiry a LostMemory is
retained (label, motion-compensated box, appearance, clocks); a returning track may rebind the
lock only through born-after-loss + size + expanding-radius + appearance + uniqueness gates and an
N-of-M pending confirmation, epoch unchanged. The "expire before association" invariant is intact —
association never resurrects the lock; re-acquire is the only path, and `reacquire_window_ms=0`
restores the prior terminal-loss behavior exactly.

Key decision, forced by MOT17-10 replay: **geometry-only re-acquire refuses same-class crowds.**
The first crowd run bound to a nearby wrong person (the true target occluded, a rival the sole
in-radius candidate). Geometry cannot disambiguate rivals, so re-acquire now declines whenever >1
same-class confirmed track is present, unless the opt-in `reacquire_appearance_crowd` flag is set
AND the match is appearance-verified. That opt-in path binds through a 2.5 s crowd outage with
idealized appearance but also raised wrong-identity frames (115 vs 2), so it stays OFF pending a
live evaluation with the board's real appearance descriptors. At the default, re-acquire ON == OFF
wrong-identity on every MOT17 sequence (0/0/5, the 5 pre-existing association switches). Recorded
phone video: re-acquire correctly declines — the phone was lost edge-on (18 px) and returns face-on
(92 px), a 5x size change unverifiable without appearance (the replay path strips it; the live board
carries it). Evidence: `bench/results/2026-09-12-reacquire/`. MOT17 labels downloaded to
hailo-export/datasets (not committed). Next: Phase B continuity supervisor + follow intent, then
sim-in-the-loop; the appearance-crowd re-acquire needs its live validation before enabling.

## 2026-09-12 (later) — re-acquire: appearance is REQUIRED for a different id (fail closed)

The session's code review (15 findings) confirmed two re-acquire bugs — the crowd gate counted
continuously-tracked bystanders as rivals although the born-after-loss filter already excludes
them (why MOT17 never fired), and LostMemory mixed publish/capture clocks (state flap) — plus the
stable-lock-id change breaking three consumers (follow adapter could never resolve a target).
All fixed (f23ca09, a50bc21, c3d03c9). Diagnosing the fixed code on a new target-only outage mode
exposed the real lesson: geometry-only re-acquire on MOT17-09 pended for ~600 ms on a NEW pedestrian
who walked into the lost target's place, one frame from binding a wrong person, saved only by a
second entrant. Ruling: **a different track id binds only on matching appearance present on both
sides; missing evidence refuses** (same-id rebinding stays geometric). The board always attaches
histograms so live behaviour is unchanged; the no-appearance MOT replay now honestly shows no
geometry-only rebinding, and `--appearance` is the evaluation path. With appearance and the crowd
flag on, MOT17-09 and MOT17-02 target-only drops re-acquire the correct identity through crowds
(latency 733 ms) with ZERO wrong-identity frames added over baseline. `reacquire_appearance_crowd`
stays off by default until a live check with real (non-idealized) descriptors. Broader point
recorded for the architecture decision: re-acquisition is an appearance/ReID problem — which is
why real follow systems track a target crop with a visual tracker and re-detect only to
re-acquire, rather than tiling the full frame. Evidence: `bench/results/2026-09-12-reacquire/`.

## 2026-09-12 (later) — VisDrone adopted as the offline aerial validation set; five-tile gain quantified

Owner asked whether VisDrone (Ultralytics DET page) can validate the tracker/detector work and
said "go download and test". DET-val, MOT-val and SOT-val are now local evaluation assets under
`hailo-export/datasets/visdrone/` (research-use licence, never committed, same footing as
MOT17Labels). First use: the DET-val recall-by-size experiment
(`bench/results/2026-09-12-visdrone-det/`, benchlog 2026-09-12 later). Findings that bear on the
open five-tile-vs-single-tile+ROI architecture decision (still the owner's): (1) the node's
five-tile path roughly doubles recall for 16–64 px objects in its 720p source on both HEFs, at
+3.5–4.5 FP/img at the 0.15 floor; (2) nothing under 16 px in the 720p source is recoverable by
tiling — that band needs a higher-resolution source or a target ROI cut from one; (3) the
controlled HEF shows no regression versus the old one on aerial data. Tooling:
`prepare_visdrone_det.py` / `run_visdrone_det.py` / `score_visdrone_det.py` (+ 7 unit tests);
the scorer mirrors the node's filters *as implemented*, including the cut-margin letterbox
blind spot, so scores describe the running node — fixing that finding stays a separate item.
Next: VisDrone MOT-val through `mot_to_replay.py` (occlusion→visibility mapping, category
mapping, explicit replay rate since VisDrone ships no fps metadata) and SOT-val for the lock path.

## 2026-09-12 (later) — re-acquire radius growth 0.5 → 2.0 extents/s (VisDrone-MOT finding)

VisDrone-MOT replays (`bench/results/2026-09-12-visdrone-mot/`) exposed a gate tuned on MOT17
pedestrians that fill a third of the frame: at 0.5 extents/s the search radius never reached a
small top-down walker (C) or a target displaced by drone motion (B), so appearance-verified
re-acquire could not even be attempted. The radius is a recall gate — identity is decided by
the fail-closed appearance rule — so it was raised to 2.0 extents/s (a walk is ~1–2 body heights
per second in a forward view, more when the box is a footprint). Sweep 0.5/1/2/4 showed no
wrong-identity change at any value; MOT17-02/09 regression identical. Two replay-path additions
in the same change: `mot_to_replay.py --format visdrone --rate <fps>` (VisDrone ships no fps;
the rate is an explicit replay parameter) and `--camera-motion gt` (median shift of the other
annotated objects as the camera-motion input the live board already has; on B it both prevents
the loss at a camera jerk and cuts re-acquire latency 1700 → 733 ms). Board binary not yet
rebuilt with the new default — deploy at the next staging. The crowd flag remains off by
default; four drone cases now join MOT17 as evidence for the pending live check.

## 2026-09-12 (later) — real histograms are not identity evidence for re-acquire; embedding required for persons (recommendation)

VisDrone-SOT with the real controlled HEF and the real tracker
(`bench/results/2026-09-12-visdrone-sot/`, benchlog 2026-09-12 later) delivered the offline half
of the "live check with real descriptors" that `reacquire_appearance_crowd` was waiting on, and
it is negative for the 72-bin colour histogram: on uav0000024 the default re-acquire (crowd flag
OFF, a lone eligible new track, histogram distance 0.19 < gate 0.55) bound a different person
after a full occlusion and followed it for ~460 frames, while the target's own histogram drifts
to 0.33 over time and 88 % of other pedestrians in the same frames sit under the gate. Rulings:
(1) `reacquire_appearance_crowd` stays OFF, and the histogram gate is not to be loosened or
tightened to "fix" this — the descriptor lacks the separability, not the threshold; (2)
recommendation for the owner's architecture decision: a different-id re-acquire for a person
should require the OSNet embedding (`person_embedding`, present on the board, off in the tiles
profile) or an equally discriminative descriptor, with the histogram demoted to a tie-breaker;
the same applies to ordinary association in "similar objects" scenes (single-tile 024: 299
control-valid off-target frames with re-acquire OFF). No code change made on this evidence —
it is a design choice with a cost (embedding inference per candidate) that belongs to the owner.
Positive side of the same run: five-tile lifts detector confidence on 40–90 px drone targets
(086 median 0.52 → 0.77) and hold rate (0.906 → 0.952); a top-down rider at 42 px stays under
the birth floor for 90 % of its sequence on both tilings (detector-limited, not tracker-limited).

## 2026-09-12 (evening) — follow path: single tile + target ROI + OSNet identity; ROI merge keeps the better box

Owner approved the recommendation ("Ok do it"): single-tile full view + a target-ROI crop for the
locked object + embedding-gated person identity, five-tile retired to an on-demand acquisition
idea. Plan `docs/superpowers/plans/2026-09-12-follow-path.md`. Landed: (1) the radius-growth fix
deployed (binary 9f40f128, then 20dd92f0); (2) `RoiAssist` generalized from "cell phone" only to
the locked class, the node's ROI detector now multi-class on the tracker's `low_confidence`
(6e26ad9); (3) `perception-follow.json` + `fresh_tracking_ctl.sh start-follow`: letterbox 640 on
the controlled YOLO11s HEF, `target_roi: assist` on the SAME HEF, `learned_person_identity` with
OSNet (95be2bc); (4) **`RoiAssist::merge` ruling reversed**: a crop box overlapping a full-view box
now REPLACES it when more confident instead of being dropped (1983f75). Evidence for (4): on
VisDrone-SOT uav0000086 the oracle ROI crop sees the target at median confidence 0.761 with
650/697 frames above the birth floor, against 0.515 / 344 for the full view — the same lift the
four corner tiles give, from one extra inference — and the old "full view wins" rule discarded all
of it; with the new rule the tracker's hold rises 0.906 → 0.930 (five-tile 0.952) on that sequence.
The primary-evidence deadline is unaffected (read from the full view in `plan()` before merge).
Board switched to the follow profile 20:27 (benchlog "board switched to the follow profile"):
25 fps, age ~90–130 ms, MemAvailable 1.39 GB with both detectors and OSNet loaded; ROI and
embedding inference counts stay 0 until a lock — the owner's live session is the remaining gate.
Two limits recorded for that session: the node embeds at most 4 persons per frame, and
`TargetOwner` marks a frame ambiguous whenever any observed person lacks a descriptor, so in a
crowd the identity path refuses rather than guesses (measured offline: 086 with a 12-per-frame
embedding cap = 299 ambiguous frames, then identity memory expired).

## 2026-09-12 (evening) — measured verdict on "embedding required for person re-acquire": partial

Offline with real OSNet descriptors (benchlog "follow path measured offline"): the embedding
gate does what the histogram could not on the wrong-bind sequence (024) — off-target control-valid
frames drop from 299 / 180 / 70 to 26 / 21 / 0 across single / five / roi — but it does not buy
follow time there: 70 % of other-person pairs fall under the 0.25 identity gate (histogram 91 %),
so `TargetOwner` mostly reports ambiguous/occluded (on-target ≤ 0.08). On the 086 crowd OSNet
separates people well (5 % under gate vs 23 %) but the owner's "every observed person needs a
descriptor" rule leaves it refusing behind the 4-crops-per-frame budget. Rulings: (1) the follow
profile keeps `learned_person_identity` on — refusing beats steering at the wrong person; (2) the
open question is OSNet's separability at the follow camera's own viewpoint (ground-level, the
model's training domain), which only the owner's live session can answer; (3) if it separates
there, raise the per-frame embedding budget above 4 for the follow profile (cost 6.5 ms/crop) so
one or two bystanders never trip the incomplete-evidence refusal; if it does not, the next
candidate is a target-crop visual tracker (spec F2) rather than another descriptor. Five-tile
retired from the follow path; the oracle-ROI numbers show one crop gives its detector lift.

## 2026-09-12 (21:33) — identity owner: incomplete evidence blocks re-binding only (fix landed, measured)

`TargetOwner` refused a positively re-identified bound track whenever any other observed person
lacked a descriptor — on a crowd that is every frame, and live the per-frame crop budget
guarantees it. Ruling (7dbb97a): missing descriptors block binding a DIFFERENT id (an
undescribed person could be the true target) but not the bound track's own verified
continuation; similar-candidate ambiguity still refuses. Node budget made configurable
(`person_embedding_max_per_frame`, default 4, follow profile 6) and spent target-first. Measured
offline: 086 roi identity on-target 0.29 → 0.67 with 13 off-target frames; 024 unchanged
(descriptor separability, not evidence coverage). Board redeployed 21:13 (binary f8c08a28).

## 2026-09-12 (22:05) — first live session on the follow profile: re-identification works; two fixes

Owner click-locked himself at ~1 m (benchlog "FIRST LIVE SESSION on the follow profile"). Result:
every walk-out (0.2–3.6 s) re-bound the SAME `lock.id` 0.17–0.37 s after the return with a new
MOT id and `identity_verified` — the "gives a new id" complaint is answered on the person path.
Two things surfaced and were fixed the same evening: (1) a 12.4 s absence crossed the identity
owner's fixed 10 s memory (`identity_memory_expired`), so the return was not re-bound and the
owner re-clicked (onto the bystander who had meanwhile entered) — `tracking.identity_memory_ms`
is now configurable, follow profile 30 s (default unchanged at 10 s); (2) the shim relabelled
every unobserved-lock sample `source_stale` (node `valid_for_ms` = freshness − observation age),
burying the owner's real reasons — only frame staleness or a still-valid observation may
overwrite the reason now. Observed, not changed: the ROI crop is `not_eligible` when the person
fills > ~40 % of the frame (crop would not fit — correct), and the identity owner never coasts,
so a detector miss on an over-close body drops control for ~100 ms (a follow authority with a
coast budget — Phase B — is the place to absorb that, not the identity gate). Still owed live:
a bystander crossing while locked, and a distance where the ROI crop engages.

## 2026-09-13 (00:50) — learned descriptor in ordinary association: measured, OFF by default

Tried overnight to stop look-alike id swaps at crossings (VisDrone-SOT 024): each track keeps the
descriptor of its last confident observation and, when a detection carries one, 1 − cosine
enters the pair cost (hard 0.5 gate, then a blended 0.85 variant). Result with real OSNet crops
(`bench/results/2026-09-12-visdrone-sot/*/replay-summary-assoc*.json`): the histogram tracker
LOST the 024 target for most of the sequence — on-target 0.333 → 0.031 (single, hard gate),
0.237 → 0.021 (five, blended), 0.108 → 0.042 (roi, blended) — and 086 gained off-target frames
(five 25 → 62, roi 32 → 48 with the hard gate). Cause: the crop descriptor drifts under partial
occlusion and the extra cost pushes the target's own observation past the assignment threshold,
severing continuity; the crossing benefit never materialises because the owner's absolute
identity gate already refuses the look-alike. Ruling: `association_embedding_gate` = 0
(disabled) by default; the code path stays opt-in for descriptors that are stable frame to
frame; a companion duplicate-suppression rule (keep near-identical boxes whose descriptors
disagree) was reverted for the same reason (one person's crops from different tiles disagree).
Identity remains with `TargetOwner`; the crossing problem on look-alikes stays open for the
visual-tracker route (spec F2).

## 2026-09-13 (01:05) — acquisition mode: five tiles while nothing is locked, single tile + ROI once locked

The owner's two positions are both right for their phase: the five tiles find a small/distant
target (VisDrone-DET: ~2× recall in the 16–64 px band; SOT 054 and 317 lock only through the
tiles) but cost ~6–7.5 fps and ~300 ms age; the single tile + target-ROI path tracks at ~25 fps
with ~80 ms age and gives the same detector lift on the locked object from one crop. The node
now takes `tiles_when_unlocked`: corner tiles run only while the lock is none/lost (re-acquire
watching), the full view + ROI once locked. `perception-follow.json` adopts it with
`freshness_ms` 500 (tiled frames reach the tracker ~200–300 ms old); the shim marks samples
stale accordingly while searching, which is cosmetic without a lock. Deployed 01:05 (binary
fa2f8f40), searching state verified on the board; the lock-time switch is owed to the owner's
next session. This also serves the phone: once the phone is lost the tiles look for it again.

## 2026-09-13 (00:15) — identity owner: ambiguity margin 0.08 → 0.04 in the follow profile (measured)

Offline sweep with real OSNet descriptors (`replay-summary-gate-sweep.json`, `replay-summary-
margin.json`): widening the identity gate (0.25 → 0.35/0.45) lowers on-target time — more
candidates inside the gate, more `similar_identity_candidates` refusals — while narrowing the
ambiguity margin to 0.04 raises it everywhere the owner can bind at all: 086 roi 0.674 → 0.761
(off-target 13 → 15), five 0.407 → 0.512, single 0.164 → 0.243; 024 five 0.073 → 0.407
(off-target 21 → 32), single 0.083 → 0.238 (26 → 44), roi unchanged. Off-target frames stay an
order of magnitude below the histogram tracker's (180–299 on 024). Ruling: `tracking.
identity_ambiguity_margin` 0.04 in `perception-follow.json` (default 0.08 unchanged); the gate
stays 0.25. Restaged 00:15.

## 2026-09-13 (10:40) — embedding age guard follows the freshness window (`person_embedding_max_age_ms`)

The node skipped OSNet crops for any frame older than a fixed 150 ms, a bound chosen when the
only path was single-tile (age ~80 ms) so that a stale frame would not burn NPU time on
descriptors the tracker would reject. The acquisition mode (01:05) made the searching state
tiled (age ~300 ms), so the guard skipped *every* crop while nothing was locked, no person
ever carried a descriptor, and the click was refused with "A fresh learned person descriptor is
required for identity selection" — the owner's first morning result. Ruling: the guard is a
profile parameter, `person_embedding_max_age_ms`, defaulting to the tracker's `freshness_ms`:
a frame the tracker can still accept must also get its descriptors, and a frame it will
reject must not. The follow profile sets 500 (= its freshness budget). The profile test now
pins `person_embedding_max_age_ms ≥ tracking.freshness_ms`, and the node's diagnostics split
`skipped_stale` from the per-frame budget skips so this failure is visible in one field.
Lesson recorded: a latency guard sized for one pipeline shape silently disables a feature
when another shape changes the frame age — every such bound must be a config value tied to
the budget it protects, never a literal. Measured after the fix: click accepted, lock-time
switch to single tile 352 → 64 ms age at 20 fps (benchlog 2026-09-13 10:40).

## 2026-09-13 — audited follow timing, provenance and simulation authority

Owner requested implementation of the independent audit fixes, PX4 integration
and SIL readiness. Ruling: implement and deploy to the desk board; vehicle I/O
remains simulation-only. No new dependencies, FC parameters or OS image changes.
Details/evidence: `docs/2026-09-13-follow-fixes-and-sil.md` and matching benchlog.

Use content-coordinate crop edges, region-aware aggregation, exact paired
1280x720 identity crops, a managed full-view/corner/ROI handover, bounded source
waiting, and inference outside the publisher mutex. In-flight work crossing a
selection command is discarded. Keep periodic independent global evidence;
never let ROI self-confirm indefinitely. The follow profile explicitly uses
500 ms confirmation/identity observation gaps and 400/1600 ms ROI age/global
evidence windows because recorded measured processing violated the old timers.
These do not change the PX4 consumer's 200 ms maximum age or 150 ms intent TTL.

Use the actual FreshFollow adapter and native tracker in PX4 SIL. Preview has
zero vehicle I/O; live requires an owned local PX4 child, explicit loopback and
GARUDA_SIM=1. Source/stream/epoch changes and stale/duplicate observations fail
closed. Test total setpoint-link loss separately from the publisher-breaker LAND
path. Allow the configured PX4 RTL to finish; do not shorten tests by modifying
its parameters. Desk camera integration is yaw-only transport-in-loop, not a
rendered visual closed loop or metric-range controller.

Do not declare the perception gate passed: corrected DET filters trade recall
against fragmentation/FP, and the causal crowded-person trial remains mostly
ambiguous. Cadence alignment repairs unreachable states, not identity separability.
Further identity coverage/latency and held-out motion/crossing evaluation is
required before real FC or flight work.

Final live check also showed that periodically rescanning corners while a large
target is already resolved by the full view creates avoidable freshness pauses.
Skip those corner scans for a large, valid target; full-view inference still
runs every frame, and loss immediately restores tiled search. Small-target
periodic tiled refresh is unchanged. Both the desk watch and real-camera
yaw-only PX4 transport-in-loop repeat are recorded in the benchlog.

## 2026-09-13 — isolate the actual visual SIL demo; keep failed robustness visible

Build the Gazebo/physical-Hailo/PX4 loop as PC bench modules and a live-input
mode of the existing causal replay executable. Reuse the actual HEF/OSNet/
Tracker/FreshFollow path; do not synthesize detections from actor coordinates.
Preserve the working desk executable/profile/HEFs and stage the stream program
under `/opt/garuda-sim`. Wrapper pause/restore uses unchanged `current.json`;
restart clears target selection. No OS, driver, model or real-FC changes.

Keep the console local-only with side controls and exact-frame overlays. The
world overview is a separate rendered camera. Do not publish simulator controls
through external web hosting. Same-origin/Host gates protect local HTTP actions;
the actual MAVLink boundary remains loopback + owned PX4 PID + GARUDA_SIM=1.
Stock PX4 preflight health remains enabled. Automatic demo cannot undo Hold.

Use one latest-frame stream request at a time. Re-envelope actual PC ingress to
result completion on the PC clock, count that interval once, and charge queue
delay separately. Do not invent exposure timestamps or a board/PC clock offset.
Same-sensor RGBD depth enables simulation-only translation, not physical-camera
ranging. Keep 200 ms consumer age / 150 ms maximum intent TTL unchanged.

The native format adapter is an exact-byte performance optimization with a
NumPy reference test. Gazebo/transport (Apache-2.0), NumPy (BSD-3-Clause), Pillow
(HPND), actor (CC BY 4.0), existing PX4 (BSD-3-Clause) and pymavlink (LGPL-3.0)
remain bench/evaluation dependencies; disabled recipe/attribution supplied.
No new pretrained model or product-cleared autonomy claim.

Recorded visual runs prove nonzero closed-loop simulated motion, dropout hold/
recovery and landing, but final non-hover follow coverage is only 415/1194 ticks.
Do not label that robust continuous following. Next: identical-pixel inference
schedule ablation, certified acquisition age, evaluator-only ground truth, then
crossing/occlusion/fast-motion and vehicle trials. Previous real crowd failures
remain open. Details/evidence: `docs/2026-09-13-gazebo-visual-follow.md`.

## 2026-09-13 — 15L owns ROS 2 / MAVROS; SIL-only transport first

Owner explicitly requires ROS 2 and MAVROS on Hailo-15L feeding PX4. Installed
Jazzy/MAVROS in an isolated Noble ARM64 chroot because stock Yocto glibc is older
and no Docker runtime exists. This is a bench exception to the Pi Docker plan,
not an OS replacement, container security boundary, production port or change
to the Pi. GPL/package-specific dependencies remain `not-product-cleared` and
separate processes; dependency record and disabled recipe supplied.

Normal simulator commands now can pass through real on-board ROS/MAVROS.
Retain owned-loopback-only PX4 guard, conservative source/command deadlines,
actual-wire checks and separately logged emergency LAND. PC-independent native
ingress and physical FC transport remain unfinished. Do not add a hardware
endpoint or auto-arm path under a simulation flag.

Measured schedule ablation favors full view in the simple rendered scene;
keep it an explicitly staged simulation profile, not a desk-wide promotion.
Correct the simulator's known full-range RGB/NV12 mismatch. Retain tiled and
limited-range comparisons, and failed crowd/aerial results. Diagnose identity
coverage and latency before attributing failure solely to YOLO or retraining.

Recorded pixels support only bounded heading response. Drone movement cannot
change a recording. Actual 30° direction/axis verification is a separately
labelled simulator axis test, not a claim about successful aerial detection.
Current handoff: `docs/2026-09-13-ros2-mavros-campaign.md`.

### 2026-09-13 — audit installed ISP features; local camera ROS observer first

Follow-on checkpoint: `docs/2026-09-13-camera-isp-and-native-ros.md`.
User requests aerial people/vehicle datasets, full physical-camera SIL and
exploration of digital zoom, low-light ISP and DSP. Installed IMX678/H15L
AI-denoising profile/model exists, but current selected profile disables it.
Live AE readback is about 33 ms; current DSP ROI source is 1280x720, not 4K.
Neither proves the cause of motion failures without controlled comparison.

Add and execute read-only native camera -> same-board ROS ingestion before
joining it to MAVROS authority. Preserve original boot/source clock, age and
identity; no PC perception round trip or automatic follow permit. Initial and
final-code observer runs passed transport checks with no selected target, not
an actuation or selected-target loss test. No camera/model/GUI changes.

Explore native pre-resize ROIs with a retained wide acquisition path before
relying on global digital zoom. Geometry changes must invalidate old selection
and controller calibration. Measure short-exposure, AI-ISP and detector schedule
independently; do not use IMX715 setup scripts or 15H marketing performance for
this installed IMX678/15L. Current freshness failures remain open, not relaxed.

### 2026-09-13 — joined local grand demo; aerial failures stay qualification blockers

Implement the physical native camera -> board-local ROS -> MAVROS -> owned PX4
SITL path. PC retains operator authorization and independent final command gate.
The fixed desk camera/replay can demonstrate bounded heading response, not
visual closed-loop pursuit; disable translation in both. Actual drone-camera
Gazebo RGBD provides a separate closed loop. Launch actual Gazebo GUI alongside
the existing local console and expose actual messages rather than mock motion.

Selected identity is independent of temporary MOT ID. Display inspection zoom
is not ISP/NPU zoom. A height-ratio readout is diagnostic-only and invalidates
on clipped/stale/changed identity/geometry or major aspect change. It cannot
certify metres, collision clearance or physical follow distance.

Measured physical heading response and repeated closed-loop SIL pass the exercised
transport/freshness/Hold/Land checks. Expanded 11-sequence real-Hailo SOT sweep
acquired only3, with off-target overlap in one. Paired64-image original-pixel
tiling modestly improves low-confidence recall, increases false positives, and
nine-pass wait alone exceeds200ms. Do not promote this schedule into live control
or loosen ambiguity/freshness gates to make a more convincing demonstration.

Next: explicit acquisition diagnostics and source-coordinate native ROI with
retained wide search; measured compute budget, aerial model/decoder compatibility,
sequence-level train/calibration/test isolation, independent wrong-target audit.
Physical low-light/zoom A/B and metric-ranging safety remain separate gates.
No hardware FC authority or product/flight qualification is granted by SIL.
Full runbook/results: `docs/2026-09-13-grand-demo.md` and benchlog.

Final verification found false-success restoration: native startup failed its
non-CMA memory reserve after repeated replay binary staging in tmpfs, while the
shell launcher returned0. Keep the reserve; move this campaign's staging to
persistent storage and require advancing native snapshots for lifecycle success.
Future causal staging uses persistent disk; DET restoration errors propagate.
Do not treat earlier restore return codes as camera health evidence.

## 2026-09-13 (17:40) — tracker input NMS at IoU 0.5; a track's own indecision no longer blocks its neighbours' matches

Root cause of the "click never took" on VisDrone-SOT 024 in the frozen causal rerun
(`docs/2026-09-13-agent-implementation-handoff.md` §9, "critical clue"): the target was
detected at ≥ 0.5 on every processed frame from 0 to 16, but its track never confirmed
before the click. Two mechanisms, both reproduced frame by frame from the retained raw
detections, timing and NV12 source (`bench/results/2026-09-13-tracker-duplicates/`):
(1) the HEF's NMS stops at IoU 0.70, so a 30 px person carries a wide and a narrow box
overlapping at 0.5–0.7 on every other frame; the tracker's ambiguity rule read the pair as
two rival explanations, flagged the track ambiguous, and reset its confirmation streak
(hits back to 0 for an unconfirmed track); (2) an unconfirmed neighbour with two equally
plausible boxes blocked both, including the target's own, so the target lost that frame's
observation too. With a ~200 ms processed-frame cadence and three consecutive hits
required, confirmation slipped from frame 8 to frame 36. Only 024 among the eleven clips
fails for this reason; the seven other unacquired clips have no detection ≥ 0.5 on the
target at all (detector recall on 13–48 px targets in full-view mode).
Rulings: (a) the tracker's input duplicate filter is standard same-class NMS at IoU ≥ 0.5
(was "near-identical", IoU > 0.92, with a histogram-distance > 0.1 escape); the only escape
is an appearance distance beyond the association gate (0.55), i.e. two boxes that could
never be one object. Measured on 024, 26 of 27 one-person duplicate pairs had histogram
distance > 0.1 (median 0.15, the wide box holds more background), so the old escape
defeated the merge; a 0.5 merge with no escape broke two pinned crossings (different-colour
people, reversing phone distractor), hence the gate-based escape. The tiled searching path
already merges at IoU 0.3 across regions. (b) A row-ambiguous track is excluded from
assignment but no longer blocks its candidate detections for other tracks; a detection
wanted equally by two tracks is still blocked (column rule); an unclaimed candidate is
still not born while an unmatched track explains it (pending rule). Rejected alternatives:
lowering `min_hits`/`confirm_ms` (hides the cause, more ghosts), a "duplicate-aware"
ambiguity rule inside association (left a duplicate feeding a second ghost track at frame
12; measured), descriptor-based suppression (reverted earlier: splits one person across
tiles). Regression: MOT17-02/09 target-drop outputs identical frame for frame to HEAD;
14-case VisDrone-MOT sweep identical in every number; eleven-clip offline click check
changes only 024 (confirmed at frame 8 instead of 36, click reaches the identity owner).
SOT replays with real OSNet descriptors: see the benchlog entry (its first reading was
overstated and is corrected there; the replay config was identity + margin 0.04 on library
defaults, not the exact shipped profile). ARM binary built (`d150568d…`); it was staged and
run on the board for about a minute at 17:52 (hash verified, frames advancing, rejected 0),
then restored to `3851ef01…` from `/opt/garuda-fresh/backups/tracker-fix-20260913/` on the
review's request to validate with the exact profile before deployment. That validation is
recorded in the benchlog entry of 2026-09-13 18:40: under the verbatim shipped profile with
the click frame held equal, every 024 row improves on retention and precision and 086 is
unchanged; the 0.41 → 0.01 question is a click-protocol artefact of the archived summaries
(same tracker, click 128 vs 195), not a regression. **Deployed 18:45:** binary `d150568d…`
staged from `hailo-export/tracker-fix-20260913`, profile unchanged (`ca91c34a…`), running hash
verified, frames advancing, rejected 0. Rollback: stop, copy the backup above over
`/opt/garuda-fresh/garuda-fresh-tracking`, `start-follow`. Live click behaviour on the desk is
still the owner's to confirm.

## 2026-09-14 (01:10) — aerial follow profile: fine-tuned detector, follow schedule at the aerial cadence, ROI-merge cap fix

Context: owner request "make this work with the aerial footage" (2026-09-13, evening). The
measured story is `bench/results/2026-09-13-aerial-detector/README.md` and the benchlog entry of
2026-09-14; this entry records the rulings taken from it. VisDrone and COCO are research-use
and stay outside the repo.

1. **Detector.** A VisDrone-only fine-tune of the deployed YOLO11s (same DFC recipe, aerial
   calibration) roughly triples person recall on the 548-image probe but forgets the desk
   scene entirely (person in 0 of 433 frames). A VisDrone + COCO-val2017 mixed fine-tune keeps
   the aerial gain (person 0.346 / all classes 0.483 at the 0.5 floor vs 0.117 / 0.229 deployed)
   and the desk person (433/433, mean confidence 0.92) but dilutes the phone (14/433 at ≥ 0.5 vs
   200). Ruling: a fine-tuned model is an **aerial-profile** detector; the desk profile keeps
   the controlled COCO HEF until a unified model measures at least equal on the desk (the
   phase-2 re-balance is in the benchlog).

2. **The follow schedule is a profile parameter.** `follow_local_gap_ms` (default 500) and
   `follow_global_period_ms` (default 800) now come from the profile, in the node and the
   causal replay alike. At the deterministic aerial replay cadence (every 5th source frame,
   250 ms) two verified ROI passes never fell inside 500 ms, so the corner tiles never retired
   with the fine-tuned model and every locked frame stayed at 5–6 detector passes. Measured
   (eleven clips, click retried on any refusal ≤ 1 s, mixed model, 512-cap profile): window
   500 → 6/11 acquired, 111 on-target frames, 39 inside the 200 ms budget; 1500 → 6/11, 109,
   51; 1500 with the corner refresh at 2000 → 6/11, 115, 69. The controlled HEF under the same
   1500/2000 schedule: 4/11, 91, 68 (58 at its defaults). Ruling: `perception-aerial.json`
   carries 1500/2000; the desk profile keeps the defaults (its live cadence is ~100 ms and
   was not measured under the wider window).

3. **ROI merge silently off above 256 detections.** `RoiAssist::merge` refused any cap above
   256 while the tracker accepts `max_detections` up to 512, so the 512-cap aerial profile
   lost every ROI box without a signal: on clip 115 none of the 22 ROI frames' local boxes
   reached the tracker (the 128-cap controlled run merged 264). Fixed in `0838a32` (guard 512,
   pinned by a merge check at 512 accepted / 513 refused). Re-measured with the fixed binary:
   mixed 1500/2000 → 6/11, 116 on-target, 1 off, 58 inside 200 ms (69 with the merge off: the
   merged crops cost a few milliseconds per frame right at the budget edge — 086 22 → 15, 115
   14 → 10); the controlled run is identical in every number (4/11, 91, 2, 68). Ruling: the
   fixed binary everywhere; the freshness cost of the merge is accepted, since the merge is
   what makes the ROI path an observation source at all.

4. **Aerial profile, staged and started by hash** (`3f77b28`).
   `hosts/hailo15l/fresh/perception-aerial.json` is the desk follow profile with the fine-tuned
   HEF in both detector slots, low floor 0.25, 512 detections / 128 tracks and the 1500/2000
   schedule; nothing else differs (pinned by `test_fresh_profiles.py`).
   `stage_fresh_tracking.sh` takes the candidate only with `GARUDA_FRESH_AERIAL_HEF` plus
   `GARUDA_FRESH_AERIAL_HEF_SHA` and writes the hash beside the file on the board;
   `fresh_tracking_ctl.sh start-aerial` refuses to start unless the file still matches it.
   **Staged 01:34 with the mixed e11 HEF (`b70e5a11…`) and node `4666ffe8…`**; the previous
   node `d150568d…` is in `/opt/garuda-fresh/backups/aerial-20260914/`; the desk profile runs
   unchanged on the controlled HEF. Both profiles were started and verified streaming (benchlog
   2026-09-14, "Deployed"); the live click on a person is the owner's check.

4b. **Phase 2 (mixed checkpoint re-balanced for the desk phone) is not the follow model.** It is
   the better detector everywhere measured (DET person 0.364 vs 0.346 at the 0.5 floor, desk
   phone 129 vs 14 of 433 frames) and the worse follow model on the eleven clips (single view
   92 vs 129 on-target frames; adaptive 6 off-target frames on 024, control on a bystander,
   against none). Ruling: the aerial slot carries mixed e11; phase 2 stays a recorded candidate
   (`bench/results/2026-09-13-aerial-detector/phase2/`, HEF `fed876d8…` on the PC under
   `hailo15/models/`). The desk profile keeps the controlled HEF: no fine-tuned model reaches
   its phone presence (200 of 433 frames at ≥ 0.5).

5. **What still does not work, measured.** 092 (13 and 17 px targets) is never detected;
   053 and 317×2 are detected but refused at the click (overlapping same-class boxes, cadence);
   024 is acquired by the mixed model at the first click but lost to identity ambiguity within
   250 ms: five people walk within ~100 px at 26 × 70 px and the OSNet distances to the anchor
   run 0.204 (best) against 0.207 (runner-up) at frame 30, inside the 0.04 margin. The
   controlled model detects fewer of that group and holds 11 frames there. No identity rule was
   changed — fail closed stands (2026-09-12 embedding ruling); this is the identity-separability
   limit already named in `docs/2026-09-13-session-summary-and-aerial-gap.md`, and a small-crop
   re-identification model or a position-aware tie-break would be the next owner decision.

6. **Native-pixel crop, measured on VisDrone (12:28; corrects §5 on 317).** Oracle windows cut
   from the original 1904×1070 frames of the 317 pair against today's 720p ROI (benchlog 12:28,
   results README §10): the rider clip gains nothing (any-class recall at the 0.5 floor 0.704 on
   the 720p ROI vs 0.517 native, the rider turning into `motorcycle` at native scale, 3–4 boxes
   overlapping it every frame); the van clip gains (mixed 0.058 → 0.367 with a 2× native
   window, controlled 0.242 → 0.296). The VisDrone source is soft (native patch barely sharper
   than the 720p copy), so the gain is apparent size, not detail. Correction to §5: the 317
   clicks were refused with "no confirmed live object" (41–45 of 45 attempts), not overlapping-box
   ambiguity. Ruling: the native-crop item keeps its priority for the **camera** path, where the
   window holds three times the pixels, and is not claimable from VisDrone; the rider case
   (person + motorcycle on one spot never confirming as one track) is a tracker question, to be
   taken with the identity work.

## 2026-09-15 — native-pixel target crop on the camera: implemented and gated, desk profile unchanged

Owner: "do the crop in the imx camera" (2026-09-14). Built: a third frontend stream at the
sensor's 3840×2160 (`native_stream`/`native_w`/`native_h`), a bounded native frame cache
(`SourceFrames` now takes its bound), the target ROI detector and the OSNet crops on those
pixels, `perception-follow-native{,-compare}.json`, `start-follow-native{,-compare}`, the
recorder and scorer under `bench/hailo_reference/native_roi_*.py`. Measured with the owner and
a phone at the desk (benchlog 2026-09-15, `bench/results/2026-09-15-native-crop/`). Rulings:

1. **Scale before pixels.** At sensor scale the planner's 2.5× context put the target at 20–40 %
   of the 640 input and the COCO detector scored it lower than at the ~14 % the paired copy's
   640 floor gives (phone 50–70 px: 0.40–0.46 vs 0.64–0.74). The native planner therefore takes
   its own context factor (`target_roi_native_context`, 7 in the profiles → target ≈ 14 % of the
   crop) and native pixels are used only where the window is shrunk at most 2×
   (`native_max_window_px` 1280); wider windows go through the paired copy. With both rules the
   native crop equals the paired one wherever both show the target at the same scale
   (60–100 px: 0.50/0.48, 0.86/0.86) and wins only at 30–40 px (0.77 vs 0.43, six frames).
2. **Not shipped on the desk.** No measurable gain outside that six-frame band; the regime the
   crop was built for (a person under ~8 % of the frame height) is not reachable at this desk
   (owner's far end 36 %; the phone stands in only down to 30 px, where both paths sit at the
   detector's floor and the lock is lost). `perception-follow.json` is unchanged; node
   `124cc94f…` carries the code, the keys are absent. The native profiles stay for an outdoor or
   drone-mounted session with the same recorder and scorer.
3. **Cost recorded, not a blocker.** Native ROI 38 ms vs 27 ms per frame; the 4K stream ~50 MB
   CMA and 250 MB/s of copies into the cache; the stream paired on every frame of every session.
4. **Corrections to earlier statements.** "Three times the pixels" was true and beside the
   point: a detector crop has a preferred object scale, and the paired copy already reaches it
   for anything the desk can show. The phone re-acquire at 3–4 m (lost for most of both phone
   sessions) is the larger follow problem at that range and belongs with the identity work.

## 2026-09-15 (later) — the demo console runs the aerial profile; replay-mode transport is the gate

Owner: "did you integrate with the full GUI". It was not: the console's replay/gazebo modes ran
the desk-derived fullview profile on a Sep 13 morning stream binary. Rulings:

1. **One staged pair of stream profiles under version control** (`hosts/hailo15l/sim/`):
   `profile-fullview.json` (the desk follow profile in single-view stream mode) and
   `profile-aerial.json` (= `perception-aerial.json` in adaptive stream mode), pinned to the
   node profiles by `test_fresh_profiles.py`; `stage_sim_stream.sh` stages the fresh build's
   causal replay as the demo's stream binary and refuses the aerial profile unless the aerial
   HEF slot's recorded hash matches. `run_grand_demo.sh … --aerial` selects it; the console
   names the model hash, schedule and this frame's crop state, from the board, never guessed.
2. **Measured in the console (VisDrone 086):** the aerial profile holds the target (59
   control-valid frames vs 5 for fullview) and hands over to single view + ROI, but no profile
   moves the simulated drone, because the follow authority's 200 ms receiver-age gate never
   passes in replay mode (PC transport adds 150–250 ms to the board's 102 / 248 ms). The gate
   stays: it is the honest budget, and relaxing it for a demo would show motion the aircraft
   could not have. The fix is board-side ingress (CLAUDE.md §7 open item), not a wider budget.
3. **Click protocol.** The auto-demo's frozen one-click protocol refuses the aerial profile's
   first click (descriptor not yet computed on a searching frame); `--select-retry-s` is the
   labelled retry, off by default, mirroring the campaigns' variant.
4. Board `/opt/garuda-sim` cleaned (294 campaign temp directories, two unused HEFs): 3.1 GB →
   57 MB. Future campaigns should clean their own staging directories.

## 2026-09-17 — model lever 1 measured: a 1280×736 single pass is the better detector, not the better follow

Owner: "work more on the model so the VisDrone feed works better first". Rulings from
`bench/results/2026-09-17-detector-1280/` (benchlog 2026-09-17):

1. **Network input size is a recipe and profile parameter, not a constant.** The HEF recipe
   takes `--input-size`, the board's region detector reads its input from the HEF, the DET
   probe and scorers take it from the preparation. The 640 paths reproduce their recorded
   numbers exactly (regression on 086 and the DET rescore).
2. **The 1280×736 model is recorded as the better detector** — person recall at the 0.5 floor
   0.378 in one 57 ms pass against 0.346 for five 640 tiles at 131 ms — **and not adopted**,
   because on the eleven clips it acquires 3 against 6 and holds 79 on-target frames against
   129. Every loss is in the tracker and the identity owner (neighbour ambiguity on 024, rider
   class flips on 029, descriptor budget in the 054 crowd, incomplete identity evidence on
   086). This closes the "detector is the bottleneck" line of work: the four mechanisms named
   on 2026-09-14 §5 now stand with the detector removed as a cause.
3. **Tracker rules stay fail-closed.** The contained-duplicate merge was reverted (no gain at
   1280, one frame lost at 640; MOT sweep identical), and the ambiguity margin stays (turning
   it off locks a neighbour on 024). The overlap-first descriptor priority is kept (equal or
   slightly better everywhere measured).
4. **Next lever, by evidence:** identity for the drone viewpoint (a re-identification model
   for small top-down crops, scored first with the separability harness), then a rider rule
   (person + two-wheeler on one spot = one target). A detector at 1280 becomes worth adopting
   for the searching state once the identity path can absorb more visible people.

## 2026-09-18 — model lever 2: a drone-view re-identification descriptor, and the identity owner's crowd trap

Owner: "ok do it" on the plan "identity for the drone viewpoint, a re-identification model for
small top-down crops, scored offline first". Rulings from `bench/results/2026-09-18-reid-visdrone/`
(benchlog 2026-09-18):

1. **The descriptor is retrained, not replaced.** OSNet x1.0 (deep-person-reid, MIT) from the
   zoo's Market-1501 weights, fine-tuned on 238 VisDrone-MOT identities cut exactly as the board
   cuts them (5,482 crops, median 40 px tall; one flight held out), softmax + batch-hard triplet
   with downscale augmentation. Same architecture, same HEF interface, same NV12 crop path, so
   the node and the owner's rules are untouched by the weights. Epoch 30 goes into the profile:
   on the six crowded SOT clips it keeps the annotated target verified on 216 of 264 frames at
   gate 0.30 against 166 for the deployed weights, and on the board it holds more on-target
   frames than epoch 11 everywhere (single view 161 vs 156).
2. **The gate moves with the weights.** Fine-tuning separates identities (false accepts 8 % →
   0.3 % on the holdout) but pushes same-identity distances outwards (median 0.13 → 0.19), so
   the aerial profile's `identity_max_distance` is 0.30, not the desk's 0.25. A gate is a
   property of a descriptor; every future descriptor gets its own sweep.
3. **The crowd trap is in the rules, and it is fixed by scoping, not by loosening.** With the
   shipped rules a single ambiguous frame releases the lock, and in a 40–58-person view with six
   descriptors per frame every later frame is `identity_evidence_incomplete`: re-binding, even to
   the same track id, demanded every visible person described, and the undescribed are by
   construction the far ones (the budget is spent nearest the target). Both descriptors fall in
   (the deployed one at frame 200 of 086, the candidate at frame 50). Two opt-in changes
   (`75fa58b`): an **evidence reach** — an undescribed person only blocks inside
   `identity_evidence_radius + identity_evidence_radius_growth × s` extents of the last verified
   box (0 = the shipped rule) — and a **focus fallback** — after a release the descriptor budget
   stays around the last verified box (`Target::last_verified_box`). Fail-closed is preserved:
   a near undescribed person still blocks, the reach grows with the outage, binding still needs
   a positive appearance match inside the gate and the ambiguity margin is untouched. The
   reach rule alone changed nothing (the target itself went undescribed after a release); with
   the focus it changed everything. Radius 0.5 is deployed: identical to 1 and 2 in single
   view for every descriptor, never worse in adaptive, and the physically tightest (a walk
   covers well under half a body extent in a 250 ms frame period). One adaptive run at 0.5
   scored 155 for epoch 11; two repeats gave 140 and 140 — 054 flips between 15 and 31 with
   the tile schedule's timing, not with the radius or the weights.
4. **Aerial profile only, staged by hash (`1a37920`).** New slot
   `/opt/garuda-fresh/models/osnet_aerial_hailo15l_v5.3.0.hef` with a `.sha256` sidecar,
   staged with `GARUDA_FRESH_AERIAL_REID_HEF` + `_SHA` exactly like the aerial detector;
   `start-aerial` and the demo-stream staging check both slots. The desk profile keeps the zoo
   OSNet, gate 0.25 and the unbounded evidence rule: the desk is Market-1501's own domain and
   was validated live on 2026-09-12; nothing measured today concerns it. The focus fallback is
   in the binary for every profile (it only changes which persons are described after a
   release; with one or two people in view it changes nothing).
5. **What the numbers are and are not.** Control-valid frames on the annotated target (IoU ≥
   0.5) over eleven clips, deterministic frame set, click retried ≤ 1 s, today's replay
   binaries reproducing the recorded control exactly (single view 129, adaptive 117).
   "Off-target" (IoU < 0.5) frames were all on the right track id (box jitter on 30–40 px
   people); a separate "wrong identity" count (control-valid, no overlap) is zero in every single
   view run and one in adaptive runs on 245, whose target is a car on the geometric lock and
   whose tile schedule is timing-dependent. Adaptive-mode numbers carry that variance; single
   view is deterministic. No live session yet: the drone-view descriptor has never seen the
   IMX678, and the reach rule has never seen the owner walk out and back at 1 m.
6. **Harness rulings.** The control script's stop waits up to 10 s (SIGTERM teardown of the
   media pipeline and NPU occasionally exceeded the old 2 s, losing two clips); the causal
   replay removes its board staging directory after every clip (381 copies of the binary filled
   the 7 GB eMMC and every later campaign failed at `mktemp`). The idealized VisDrone-MOT sweep
   runs with the learned owner off and cannot see today's rules; it was not rerun.
7. **Next, by evidence:** the rider rule (029: person + two-wheeler on one spot = one target;
   the fine-tuned descriptor sees the person, not the motorcycle, and the annotated rider box
   drifts out of the gate), then a live aerial-style session at range, then the 1280 searching
   pass now that the identity path can absorb more visible people.

**Deployed 2026-09-18 15:05.** Node binary `de92ee52…` (commit `75fa58b` code) staged to
`/opt/garuda-fresh` with the aerial detector slot (`b70e5a11…`), the new aerial re-ID slot
(`0b84e321…`, sidecar written) and the desk's zoo OSNet; `start-aerial` came up with the new
descriptor (camera ready, searching-state frames 240–330 ms old, 174 descriptor inferences at
9.5 ms with 0 failures on the desk scene, no errors in the node log);
the board was returned to `start-follow` (desk profile, unchanged). The demo console's board
stream and its aerial profile were restaged from the same build (`stage_sim_stream.sh`).

**2026-09-18 15:50 — owner's call: the aerial detector slot holds the phone-preserving fine-tune.**
After the desk session the owner ruled that the aerial profile must also see the desk's small-target
proxy, a hand-held phone, including in fast motion. The phase-2 fine-tune of 2026-09-13 (mixed
VisDrone + COCO with the phone re-balanced, HEF `fed876d8…`) was re-measured under today's descriptor
and rules: equal to the mixed-e11 slot in the adaptive mode the profile runs (142 / 142 on-target),
21 frames behind in single view (054 34 → 16, 024 7 → 1), no wrong person. Options were put to the
owner (swap now / keep / retrain for both) and the swap was chosen: `start-aerial` now checks the
sidecar `fed876d8…` in the same slot; profiles unchanged. Live at the desk on the aerial profile the
phone is detected on 29 % of session frames (median 0.73, ~99 px; continuous while held up) and
control-valid on 62 % of locked frames, against 19 % / 51 % on the desk profile's own pass minutes
earlier — the fast passes and tilts lose the phone on both, which is the 2026-09-03 small-object
limit and the next lever if the phone proxy is to stand in for a fast target. The single-view crowd
frames given up (054) are the price, recorded; a retrain that keeps both is the way to buy them back.
