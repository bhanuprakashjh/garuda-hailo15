# Hailo-15L follow-me — session handoff (2026-09-11 → 2026-09-13)

> **Current agent entry point:** [Complete implementation handoff through the
> overlay and zoom fixes](2026-09-13-agent-implementation-handoff.md). It includes
> verified deployment hashes, current live-state caveats, commands, evidence and
> remaining work. This older file preserves the original session history.

> Later update: this is the historical pre-audit handoff. For the current deployed
> fixes, actual camera-to-PX4 simulation tests, and remaining failed perception
> gates, read [Follow fixes and SIL](2026-09-13-follow-fixes-and-sil.md) first.
> For the subsequent live rendered-camera demo and console, continue with
> [Gazebo visual follow](2026-09-13-gazebo-visual-follow.md).
> Latest desk deployment: [movement geometry and ROS/MAVROS fixes](2026-09-13-movement-fixes.md),
> following the [grand demo](2026-09-13-grand-demo.md). Use these for current
> binary hashes, measured checks and the remaining physical movement test.
> Subsequent [dataset rerun and console redesign](2026-09-13-dataset-rerun-and-console.md):
> acquisition remains 3/11 and detector metrics unchanged. Read this before claiming improvement.

Written 2026-09-13 morning for whoever (human or model) picks this work up.
It covers one continuous Claude Code session on branch
`feat/hailo15l-fresh-tracking`: what was asked, what was built, what was
measured, what broke and how it was fixed, what is live on the board, and
what is still open. Every number here is copied from `bench/benchlog.md`
or a `bench/results/*/README.md`; nothing is estimated (CLAUDE.md rule 1).

Read this first, then `CLAUDE.md`, then `docs/decisions.md` (entries dated
2026-09-11 to 2026-09-13), then the two plans and the spec listed in §2.

---

## 1. One-paragraph state

The Hailo-15L SBC runs the "fresh" tracking node (`garuda-fresh-tracking`)
on the follow profile `hosts/hailo15l/fresh/perception-follow.json`:
YOLO11s (controlled HEF) on a 640 letterbox of the 1280x720 source, five
detection tiles while nothing is locked, single tile + a target-ROI second
detector once locked, OSNet person embeddings feeding an identity owner
that verifies who the lock is, histogram-gated re-acquire for non-person
classes, a stable `lock.id` across re-acquire. Binary sha256 `3c99fbc9…`,
committed tip `9c1170a`, working tree clean, 203 commits ahead of
`master` (merge-base `2322c1b`). Click-to-lock works as of this morning
(it was refused overnight, §6.12). Offline, the follow path has been
measured on VisDrone DET/MOT/SOT and a PX4 SITL sim closes the loop from
the tracker's output to a simulated vehicle. Nothing on this branch is
merged to master yet.

## 2. Where everything is

| Thing | Location |
|---|---|
| Worktree (work here, never `cd` to the main checkout) | `/media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking` |
| Board | `ssh root@10.0.0.1` (PC profile `h15-link`); node + shim on `:8099` (`/api/state`, `/api/mono_click?x=&y=&sequence=`, `/api/unlock`, `/api/events`); install dir `/opt/garuda-fresh/` (`current.json` is the live profile) |
| Build (native ctest + Python unit tests + ARM cross build) | `GARUDA_FRESH_BUILD=/tmp/garuda-fresh-deploy bash /media/…/hosts/hailo15l/build_fresh_tracking.sh` — ALWAYS absolute paths (§9) |
| Stage to the board | `GARUDA_FRESH_BUILD=/tmp/garuda-fresh-deploy GARUDA_FRESH_REID_HEF=/media/bhanu1234/Development/hailo15/models/osnet_x1_0_hailo15l_v5.3.0.hef bash /media/…/hosts/hailo15l/stage_fresh_tracking.sh` (refuses while the node runs: `stop` first) |
| Control | `hosts/hailo15l/fresh_tracking_ctl.sh {start-follow|start-tiles|start-letterbox|stop|status}` |
| ARM binary after a build | `/tmp/garuda-fresh-deploy/h15l/garuda-fresh-tracking` (check `sha256sum` changed before staging) |
| Native replay binary | `/tmp/garuda-fresh-deploy/native/garuda-track-replay` |
| Reference probe (detector-only runs on the board) | built at `/tmp/garuda-reference-build/hailo-preprocess-probe` from `bench/hailo_reference/preprocess_probe.cpp` (input cap raised to 16384) |
| HEFs | controlled YOLO11s `aec84f00…` (`/media/bhanu1234/Development/hailo15/models/yolov11s_hailo15l_v5.3.0.controlled.hef`), old `24a050fb…`, OSNet `osnet_x1_0_hailo15l_v5.3.0.hef` (model id `osnet_x1_0-hailo15l-5.3.0-sha256:49a46e48…`) |
| Datasets (research use, NEVER commit) | `/media/bhanu1234/Development/hailo-export/datasets/visdrone/VisDrone2019-{DET,MOT,SOT}-val/`; MOT17Labels (CC BY-NC-SA, eval only) |
| Prepared SOT replay streams / OSNet descriptors | `hailo-export/visdrone-sot-replay-20260912-roi/<seq>`, `hailo-export/visdrone-sot-embeddings-20260912/<seq>/{embeddings,embeddings-full}.jsonl` (60–360 MB each) |
| Scratch for replay work dirs | under `hailo-export/scratch-*` — NOT `/tmp` (root fs filled once) |
| PX4 SITL | `/media/bhanu1234/Development/PX4-Autopilot` commit 47ce421; launch: `cd build/px4_sitl_default/rootfs && PX4_SIM_MODEL=sihsim_quadx HEADLESS=1 ../bin/px4 -d -s etc/init.d-posix/rcS`; MAVLink offboard `udpin:0.0.0.0:14540`; pymavlink 2.4.49 (LGPL-3, bench only). No Gazebo use, no ROS 2, no Docker on the PC |
| Spec | `docs/superpowers/specs/2026-09-12-follow-platform-and-reacquire-design.md` |
| Plans | `docs/superpowers/plans/2026-09-12-tracker-reacquire.md` (done), `…/2026-09-12-follow-path.md` (done), `…/2026-09-12-overnight-follow-hardening.md` (done) |
| Evidence dirs | `bench/results/2026-09-12-{yolo11-ab-replay,reacquire,visdrone-det,visdrone-mot,visdrone-sot}/`, `bench/results/2026-09-13-{sim-followme,overnight}/` |
| Session start state | `docs/2026-09-11-hailo15l-complete-summary.md`, `docs/2026-09-11-hailo15l-checkpoint.md` |
| Memory notes (Claude) | `~/.claude/projects/-media-bhanu1234-Development-GARUDASDK/memory/h15-kickoff-2026-09-01.md`, `harness-cwd-drift.md` |

## 3. What the owner asked for, in order

1. Analyse the running code fully; commit the untracked summary, evidence and tools.
2. Explain and run the old-vs-controlled HEF A/B on recorded video.
3. Study PixEagle, PX4-ROS2-Gazebo-YOLOv8 and the cangozpi drone repo; produce a full platform plan for this hardware; then harden the tracker's re-acquire logic, testing on recordings and any datasets available.
4. Deploy; reboot approved when the node rejected frames.
5. Owner caught that the OLD HEF had been deployed (correct — the staging script pinned the old hash).
6. Owner directive: "the single 640 is not what is needed, the 5 tile path was the right solution for the 4k camera, and the target re-acquisition gives a new id" → five tiles in the node + stable lock id.
7. Owner: tiling "is worse, marking me as 2 people, lock broken" → fix the aggregation properly, iterate from recordings, not repeated live tests.
8. "How do real systems do this, we are struggling too much" → architecture answer (single full view + target-ROI crop + ReID descriptor, tiles only for acquisition).
9. Full code review; fix the top findings; fail-closed appearance rule.
10. Use VisDrone to validate → "Go download and test".
11. Three-point summary, recommendation, "Ok do it" → the follow path (radius-growth fix, single tile + target ROI follow profile, OSNet-gated identity, validated on VisDrone-SOT and live).
12. "Ok do the fix and what next" (identity owner refusing on undescribed bystanders).
13. Root-disk cleanup help; "is this on the board?"; "I don't see any difference"; "record now" / "done" (first live session).
14. "Do all things overnight and give me the best possible results … finish all and px4 simulation by morning. Get on with it."
15. Morning: the click was refused ("A fresh learned person descriptor is required for identity selection.") → fixed (§6.12).
16. This handoff.

## 4. Timeline of what was built (with commits)

Times are the PC's local clock as in `git log`.

### 4.1 2026-09-11 evening — starting point
Fresh node with the controlled YOLO11 HEF, optional target-ROI second detector (assist/shadow), tuning panel in the shim, 4K tile replay tools, reference probe accepting arbitrary source sizes (`63224d4`…`eced1ab`). Evidence consolidated, controlled-HEF decision recorded.

### 4.2 2026-09-12 11:43 — detector A/B on a recording
`0464def`, `d65a986`, `e3d9709`: full-sequence replay of a 433-frame capture through both HEFs; controlled HEF validated on the recording; tracker shown to bind. Evidence `bench/results/2026-09-12-yolo11-ab-replay/`.

### 4.3 2026-09-12 12:00–12:16 — re-acquire in the tracker (Phase A)
Spec + plan (`8f75a36`), then `561e25e` (config surface), `bc0ec6b` (retained loss memory, states `lost/watching_for_return/reacquiring/reacquire_window_expired`), `caa86d7` (gated re-acquire with pending N-of-M confirmation: hits 3, confirm 600 ms, gap 250 ms, window 7 s), `423bbde` (refuse same-class crowds without validated appearance). MOT17-02/09 target-only outage replays (`d3d4407`), `bench/results/2026-09-12-reacquire/`.

### 4.4 2026-09-12 14:02–15:14 — five tiles in the node, stable lock id, aggregation fixes
`6a52757` stable `lock.id` across re-acquire (MOT id exposed as `lock.track_id`); `8ae86ec` staging deploys the controlled HEF (owner-caught defect); `b2b20e0`/`9cf26b3` five-tile layout (4×0.6 corners + full) and node `detection_tiles` mode; `5838f6e` regression recorded (duplicate tracks broke the lock) and reverted; `ccbf22d` aggregation rebuilt (consistent scale, border removal, containment NMS); `57f6f84` corners contribute only small objects (`tile_corner_max_area` 0.05) → person split 0/90 frames; `9ab974f`/`c7ca538` flicker root-caused to ~7.5 fps + ~150 ms latency vs the shim's freshness budget → tiles profile freshness 500 ms.

### 4.5 2026-09-12 16:51–17:36 — review fixes and the fail-closed rule
`f23ca09` lock-id contract propagated to the adapter/shim/scorer; `a50bc21` crowd gate counted bystanders wrongly + clock-domain mix; `92c8eed` evidence hygiene; `c3d03c9` a different-id re-acquire REQUIRES matching appearance (fail closed; geometry alone never binds a new id); `4119e54` target-only outage evaluation.

### 4.6 2026-09-12 18:10–18:57 — VisDrone validation
`cc6bb9e` DET recall-by-size (`bench/results/2026-09-12-visdrone-det/`); `d981ed0` MOT replay path + re-acquire radius growth 0.5 → 2.0 extents/s (`bench/results/2026-09-12-visdrone-mot/`); `d88d1dc` SOT with the real detector + real tracker: real colour histograms FAIL as identity evidence (`bench/results/2026-09-12-visdrone-sot/`).

### 4.7 2026-09-12 20:00–21:33 — the follow path (owner's "Ok do it")
`6e26ad9` target-ROI assist follows the locked class (was phone-only); `95be2bc` `perception-follow.json` (single tile + target ROI + OSNet identity) + `start-follow`; `1983f75` ROI merge keeps the more confident box; `eccfc48` SOT harness gains an oracle target-ROI flavour and real OSNet embeddings computed on the board; `8c24530` follow path measured offline; `7dbb97a` identity owner keeps a verified target despite undescribed bystanders (continuation rule); `fc12e61` measured.

### 4.8 2026-09-12 22:05–23:09 — first live session
Owner click-locked himself; 157 s capture; re-identification after 0.2–3.6 s absences in 0.17–0.37 s on the same lock id; a 12.4 s absence expired the 10 s identity memory. Two defects → `f83573e` (configurable `identity_memory_ms`, follow profile 30 s; shim keeps the node's reason for unobserved locks), `2649c04`/`4c482c7` recorded.

### 4.9 2026-09-12 23:31 → 2026-09-13 00:13 — overnight programme
- `b378a76` then `59555c9`: OSNet descriptor in ordinary association — measured regression, shipped opt-in and OFF (`association_embedding_gate = 0`).
- `9b7cc51`, `b1b56cf`: **Phase B** `FollowAuthority` (`services/garuda-follow/follow_authority.py`) + **Phase C** simulation offboard bridge (`services/garuda-bridge/sim_offboard_bridge.py`, pymavlink, `GARUDA_SIM=1` gate, UDP only) + `bench/sim/followme_sitl.py`; five scenarios measured on PX4 SITL.
- `c3ac0c8`: VisDrone-MOT multi-target sweep (`bench/hailo_reference/visdrone_mot_sweep.py`); SOT target class inferred from the detector.
- `435d049`: identity owner gate/margin/memory exposed in the tracking config; follow profile `identity_ambiguity_margin` 0.04 (measured sweep).
- `ecdafdc`: acquisition mode `tiles_when_unlocked` — five tiles only while nothing is locked, single tile + ROI once locked.
- `4e54f7d`: all eleven SOT sequences measured, morning report `bench/results/2026-09-13-overnight/README.md`.

### 4.10 2026-09-13 10:31 — morning fix
`9c1170a`: the click refusal (§6.12) — `person_embedding_max_age_ms` defaulting to the tracker's freshness window; live-verified.

## 5. Architecture as it runs now

```
IMX678 → ISP → 1280x720 NV12 source (paired by ISP timestamp)
   │
   ├─ searching (lock none/lost/reacquiring): 5 tiles (4×768x432 corners + full) → RegionDetector
   │     → aggregate (IoU 0.3 / containment 0.7, corner boxes >5 % dropped, cut margin 0.08)   ~6 fps, age ~300 ms
   └─ locked: single 640 letterbox → YOLO11s; target-ROI crop (2.5× the lock box, min side 640)
         → second YOLO11s pass → RoiAssist::merge (better box replaces)                       ~20–25 fps, age ~65–140 ms
   │
   ├─ describe(): 72-bin NV12 histogram per detection (association tie-breaker, non-person re-acquire gate)
   ├─ OSNet crop+embed for up to 6 persons/frame, target-first, only while frame age ≤ person_embedding_max_age_ms
   ├─ camera-motion estimate (translation)
   ▼
garuda::fresh::Tracker  (Hungarian association, per-axis Kalman, birth 0.5 / control 0.4 / low 0.15,
   coast 1200 ms, confirm 120 ms, max_gap 250 ms, freshness 500 ms)
   ├─ TargetOwner (learned_person_identity): binds the lock to an OSNet identity; max distance 0.25,
   │    ambiguity margin 0.04, memory 30 s; refuses ambiguous/incomplete evidence (fail closed);
   │    continuation rule: undescribed bystanders block only re-binding to a DIFFERENT id
   ├─ LostMemory + re-acquire (non-person or owner off): radius 2.0 extents growing 2.0/s, size ratio 2.5,
   │    appearance ≤ 0.55 REQUIRED for a different id, crowd refusal unless reacquire_appearance_crowd
   └─ stable lock.id; epoch; states none/tracking/occluded/coasting/reacquiring/lost
   ▼
fresh_shim.py :8099  (v2 JSON + SSE; staleness relabel only on frame staleness)
   ▼ (PC, offline / sim only for now)
services/garuda-follow/follow_authority.py  IDLE/ACTIVE/COASTING/REACQUIRING/HANDOFF, coast 1.5 s,
   reacquire 4 s, intent TTL 150 ms, abort sticky until resume  → CommandIntent
   ▼
services/garuda-bridge/sim_offboard_bridge.py  (GARUDA_SIM=1, pymavlink UDP 14540; hover unless fresh
   & eligible; prime 2 s → arm → OFFBOARD; breaker → LAND after 5 publish failures)  → PX4 SITL
```

Profile keys that matter (`perception-follow.json`): `detection_tiles` true, `tiles_when_unlocked` true, `tile_cut_margin` 0.08, `tile_corner_max_area` 0.05, `target_roi` assist, `target_roi_hef` = same HEF, `target_roi_cut_margin` 0.015, `person_reid_hef` OSNet, `person_embedding_max_per_frame` 6, `person_embedding_max_age_ms` 500, `tracking.freshness_ms` 500, `identity_memory_ms` 30000, `identity_ambiguity_margin` 0.04, `association_embedding_gate` absent (= 0, off).

## 6. Issues hit, and how each was resolved

1. **Old HEF deployed** while claiming the controlled one (staging script pinned the old hash). Owner caught it from the phone detections. Fix `8ae86ec`; the staging script now hash-verifies every model on the board.
2. **Five tiles split one person into 2–6 tracks** (coarse full view mixed with fine corners, cut margin 0.015, IoU 0.5). Reverted, aggregation rebuilt with one consistent scale, border removal, containment NMS, and corners restricted to small objects. 0/90 split frames afterwards.
3. **Tiles `source_frames` never created** (`exact_source_missing`): the paired-source buffer was only created for capture/ROI. Fixed the creation guard.
4. **Flicker at ~7.5 fps**: the shim marked 47 % of samples stale because tiled frames arrive ~150 ms late. Freshness budget 500 ms in the tiles/follow profiles.
5. **Live captures with 0 person frames** (timing) → owner asked to iterate offline; all later tuning was done on recordings and datasets.
6. **Geometry-only re-acquire nearly bound a new entrant** (MOT17-09) → different-id re-acquire requires appearance (fail closed).
7. **Re-acquire radius grew too slowly** for drone footage (0.5 extents/s): VisDrone-MOT B and C never re-acquired. Sweep → 2.0/s default; MOT17 regression unchanged.
8. **Real colour histograms are not identity evidence** (SOT 024: impostor 0.19 vs target-self 0.33 median; 88 % of other pedestrians under the 0.55 gate). Conclusion: person re-acquire needs the OSNet embedding; histograms remain a tie-breaker.
9. **Identity owner refused on undescribed bystanders** (embedding budget/coverage): only crops within the budget carry descriptors, and the owner treated any undescribed person as unresolved. Continuation rule `7dbb97a`: undescribed bystanders block only a re-bind to a different id.
10. **Shim mislabelled unobserved locks as `source_stale`** (345/1477 live samples) → relabel only on frame staleness. **Identity memory 10 s too short** (12.4 s absence) → configurable, 30 s.
11. **Stale binary staged with a new profile key** (the build script was invoked with a relative path from a drifted cwd, exited 127 unnoticed) → node refused `unknown tracking parameter: identity_memory_ms`; ~10 min on `start-letterbox`. Rule: absolute paths; verify the ARM binary hash changed before staging (memory `harness-cwd-drift.md`).
12. **Morning click refusal** "A fresh learned person descriptor is required for identity selection": the embedding loop skipped crops older than a fixed 150 ms; in the tiled searching state frames are ~300 ms old, so 0 descriptors were ever computed (97 376 skipped). Fix `9c1170a`: `person_embedding_max_age_ms` (default = freshness), diag `skipped_stale`, profile test. Verified: click accepted, lock 1.4 s, age 352 → 64 ms, 20.1 fps.
13. **Descriptor-aware association regressed** (024 on-target 0.33 → 0.03 with a hard 0.5 gate; blended 0.85 also worse) → shipped opt-in OFF; recorded as a negative result.
14. **Descriptor-based duplicate suppression** split one person across tiles → reverted.
15. **/tmp (root fs) filled** by embedding-attached replay work dirs → moved to `hailo-export/scratch-*`; 2.3 GB of Claude temp removed; sudo cleanup candidates handed to the owner (apt clean, journal vacuum, old snap revision, Chrome cache, pipx/codex, MPLAB/KiCad/arm toolchains).
16. **`pkill -f` matched the calling shell** (exit 144) twice → kill by pid or anchored pattern (`^../bin/px4`).
17. **Reference probe input cap 8192** → raised to 16384 for SOT sequences (1478 frames × 6 regions).
18. **PX4 launch**: rootfs/airframes resolve relative to the working dir → run from `build/px4_sitl_default/rootfs` with `-s etc/init.d-posix/rcS`.
19. **SOT harness**: xyxy vs xywh IoU bug; lock at frame 3 too early (→ frame 15 + confidence streak); one driver deleting another flavour's outputs (per-flavour dirs); the lock trial must run under the identity config (`--lock-config`).
20. **FollowAuthority**: hand-off was sticky (only abort is now); REACQUIRING exempt from the separation budget; session change reported once verified; COASTING↔HANDOFF flapping fixed.
21. **Nominal sim standoff** 9 m with forward gain 10 → gain 20 (5.7 m).
22. **gdown `--fuzzy`** unsupported in the venv's gdown 6.2.0; ffmpeg absent → PIL/numpy NV12 conversion; DET images of mixed resolution fitted onto a 1280x720 canvas.

## 7. Measured results (pointers; full tables in the READMEs)

- **Detector A/B on the recording** (`2026-09-12-yolo11-ab-replay`): controlled HEF validated; benchlog 2026-09-12.
- **VisDrone-DET, 548 images** (`2026-09-12-visdrone-det`): five tiles roughly double recall in the 16–64 px band on both HEFs (person 16–32 px 0.06–0.08 → 0.21–0.23; 32–64 px 0.34–0.37 → 0.58); objects under 16 px are lost either way; probe wait old 21.0 / controlled 26.3 ms median per region.
- **VisDrone-MOT** (`2026-09-12-visdrone-mot`): with growth 2.0 all four hand-picked cases re-acquire (733 ms, B 1700 ms without camera motion), 0 wrong-id frames added; sweep over 14 auto-picked targets: 8/10 locked cases re-acquired at 733 ms, 0 wrong binds, control-valid +73 %. Idealized appearance = mechanism test only.
- **VisDrone-SOT** (`2026-09-12-visdrone-sot`): histograms fail as identity (above); real OSNet gate gives 26/21/0 off-target frames instead of 299/180/70 but little on-target time on look-alikes; continuation fix raised 086 roi identity on-target 0.29 → 0.67; margin 0.04: 086 roi 0.674 → 0.761, 024 five 0.073 → 0.407; all eleven sequences: targets < ~25 px invisible (4 seqs), small persons lock only with tiles (054, 317), car 115 tiles double the hold (0.86 vs 0.44), look-alike cars (245) swap on every flavour.
- **Live session 22:05** (`live-follow-20260912-2205.jsonl.gz`): node age p50 74–86 ms; re-identification 0.17–0.37 s after 0.2–3.6 s absences, same lock id; ROI never eligible at ~1 m (body 85–110 % of frame height).
- **Acquisition mode** (benchlog 2026-09-13 01:05 and 10:40): searching ≈ 6 fps, age 250–400 ms; locked 20.1 fps, age 64–140 ms.
- **PX4 SITL** (`2026-09-13-sim-followme`): nominal 5.70 m standoff, framing error 0.033 median; target loss → coast 1.3 s → hand-off → re-engage; 2 s stall → hover by TTL; abort/resume; publish failure → LAND (−3.0 → +0.1 m in 8 s).

## 8. Open items, in recommended order

1. **Live checks still owed to the owner** (need a person): bystander crossing while locked (does the identity owner hold or refuse?); a range at which the target-ROI crop engages (target < ~40 % of frame height) and its effect on fps/age; a second look-alike person.
2. **Look-alike pedestrians** (SOT 024/245): neither histograms nor OSNet separate them from a drone view. Spec route F2 = a visual/template tracker on the ROI crop; alternatively a stronger ReID model or the owner's fail-closed refusal accepted as behaviour.
3. **Phase D — board-side bridge**: the authority + bridge run on the PC in sim only. Moving `FollowAuthority` to the board and adding a MAVLink/uXRCE path toward the CA90 is the next platform phase (keep `GARUDA_SIM=1` gating; never write FC parameters without listing them).
4. **Branch integration**: 203 commits ahead of master; `feat/hailo15l-perception` (PR #1) is merged, `feat/hailo15l-kalman-tracker` is not. Owner's call on ordering.
5. **Deferred review findings** (from the 2026-09-12 review, still open): `SearchRegion::cuts_object` ignores the letterbox offset (mirrored, not fixed, in the DET scorer); tile inferences run under `tracking_mutex`; aggregation can let a small fragment delete its containing box; `flush_captures` try_to_lock; tuning-panel bugs (fractional `exposure_ms`, preview/jpeg fps, restore guard); watchdog harness; ctl idempotency (byte-compare of the profile).
6. **Unvalidated**: `reacquire_appearance_crowd` stays OFF by default (histogram crowd binding was only validated with idealized appearance); metric range is not in the loop (standoff is the controller's proportional equilibrium, not a measured distance).
7. **Root-disk sudo cleanup** items were listed for the owner and not executed.

## 9. Gotchas for the next model

- **Shell cwd drifts between tool calls.** Always invoke scripts by absolute path and check the exit code; after a build, `sha256sum` the ARM binary and confirm it changed before staging. A profile key the binary does not know makes the node refuse to start (`unknown tracking parameter: …`) — the ctl script then leaves the board without a tracker.
- `stage_fresh_tracking.sh` refuses while the node runs: `fresh_tracking_ctl.sh stop` first, then stage, then `start-follow`. Staging needs `GARUDA_FRESH_REID_HEF` for the OSNet checksum guard on the follow profile.
- Never `pkill -f` with a pattern that can match your own shell. Kill by pid.
- Replay work dirs with embeddings are gigabytes: keep them under `hailo-export/`, never `/tmp`.
- Rule 1: every number in a doc comes from a harness run recorded in `bench/benchlog.md`; write `TBD-bench` otherwise. Rule 6: state licences (pymavlink LGPL-3 is bench-only). Anything that commands a vehicle sits behind `GARUDA_SIM=1`.
- The 15L is not the 15H: never quote 15L fps as 15H.
- `/api/state` diag fields that tell you the node's health in one read: `diag.detection_tiles.reason` (`tiled` / `locked_single_tile`), `diag.target_roi.reason`, `diag.person_embedding.{inferences,skipped,skipped_stale,max_age_ms}`, `age_ms`, `accepted`, `rejected_frames`, `lock.{state,reason,id,track_id}`.
- Revert to a plain single-tile profile without identity: `fresh_tracking_ctl.sh stop && start-letterbox`.
