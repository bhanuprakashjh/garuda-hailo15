# Hailo-15L follow-me: what was done, and why drone footage does not work yet

Written 2026-09-13 evening for the next agent. Read this, then
`docs/2026-09-13-agent-implementation-handoff.md` (architecture, files, run and deploy
procedures), then `CLAUDE.md` and the dated entries in `docs/decisions.md`. Every number here is
copied from `bench/benchlog.md` or a `bench/results/*/README.md`; nothing is estimated.

Branch `feat/hailo15l-fresh-tracking`, worktree
`/media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking`, tip `a8cdd6e`,
tree clean, not merged to master. Board `root@10.0.0.1` runs native app `d150568d…` on
`perception-follow.json` (`ca91c34a…`), plus ROS 2 Jazzy and MAVROS in the
`/opt/garuda-ros-jazzy` chroot. The owner exited the demo; no simulator is running.

---

## 1. Work done, in order

### 1.1 Follow path and re-acquire (2026-09-11 evening → 09-13 morning, first agent)
Controlled YOLO11s HEF validated on a recording; tracker re-acquire with a stable lock id;
five detection tiles for the 720p source and their aggregation; fail-closed appearance rule
for a different-id re-acquire; VisDrone DET/MOT/SOT harnesses and first results; follow profile
with single tile + target ROI + OSNet identity; identity owner continuation rule; first live
session (re-identification in 0.17–0.37 s); overnight: FollowAuthority and a PX4 SITL bridge
with five headless scenarios, MOT multi-target sweep, identity margin 0.04, acquisition mode
(tiles while unlocked); morning fix for a refused click (embedding age guard).
Detail: `docs/2026-09-13-hailo15l-follow-handoff.md`.

### 1.2 Independent audit and corrections (09-13 midday, second agent)
The audit (`docs/2026-09-13-independent-follow-audit.md`) found real defects in 1.1: the
acquisition-to-ROI handover could strand a small target (ROI needed a frame under 100 ms and
recent full-view evidence); OSNet ran on the 640×360 letterbox content while the offline
evidence used 1280×720; six YOLO passes per searching frame under the tracking mutex; the sim
harness armed in preview mode; FollowAuthority did not check observation age or sequence;
timers shorter than the measured cadence. All were fixed and deployed
(`docs/2026-09-13-follow-fixes-and-sil.md`). The same agent then put ROS 2 Jazzy and MAVROS on
the 15L (chroot, bench-only, GPL components as separate processes), built the Gazebo visual
demo with a real rendered camera through the real Hailo inference, the local follow console on
`:8100` with three input modes (live camera, recorded aerial, Gazebo), an ISP audit, movement and
dispatch fixes, and a frozen eleven-clip aerial rerun with retained negative results
(`docs/2026-09-13-agent-implementation-handoff.md`, `…-grand-demo.md`, `…-movement-fixes.md`,
`…-dataset-rerun-and-console.md`, `…-ros2-mavros-campaign.md`, `…-camera-isp-and-native-ros.md`).

### 1.3 Tracker confirmation fix (09-13 afternoon, this agent; commits `383b764`, `affd705`, `a94a667`)
Root cause of the "click never took" on SOT clip 024 in the frozen rerun, reproduced frame for
frame from retained detections, timing and NV12 pixels: the HEF's NMS stops at IoU 0.70, so a
30 px person carries a wide and a narrow box (IoU 0.5–0.7); the tracker's ambiguity rule read
the pair as two rival identities and reset the unconfirmed track's streak; an unconfirmed
neighbour's own indecision also blocked the target's box. Confirmation came at frame 36 instead
of 8, so the click at 16 found only the neighbour. Fix: same-class NMS at IoU 0.5 at the tracker
input (escape only beyond the appearance gate 0.55; 26 of 27 measured one-person duplicate pairs
had histogram distance > 0.1, so a small escape would defeat it) and a row-ambiguous track no
longer blocks its candidates for other tracks. Two tests pin it. Regression: MOT17 target drops
identical to HEAD on every frame; 14-case MOT sweep identical; eleven-clip offline click check
changes only 024; SOT with real OSNet under the verbatim shipped profile with the click frame
held equal: 024 single 0.335 → 0.379, five 0.020 → 0.045, roi 0.397 → 0.428 on-target with
off-target 38 → 35, 16 → 2, 68 → 33; 086 unchanged. The archived 0.41 → 0.01 on 024 five was a
click-protocol artefact (click 128 reused from the first histogram conversion vs 195 derived
fresh), not a regression. Deployed 18:45 after that validation; previous binary backed up at
`/opt/garuda-fresh/backups/tracker-fix-20260913/`. Evidence
`bench/results/2026-09-13-tracker-duplicates/`.

### 1.4 Console additions (09-13 evening; `db7229c`, `a8cdd6e`)
Heading dial (top-down drone glyph at the actual yaw, ghost arrow at the requested yaw) because
the live-mode follow response is yaw only and invisible in the overview camera. ROS 2 / MAVLink
link terminal: the relay logs transitions (PC requests, board service results and setpoint
publications, packet-gate rejections with reasons, `COMMAND_LONG`/`SET_MODE` relayed,
PX4 `STATUSTEXT`, `COMMAND_ACK`, heartbeat mode/arming changes) and the console renders them.
Both frontend-served on refresh; the terminal needed a demo relaunch for the backend.

### 1.5 Live session read-back (09-13 19:1x)
A 180 s recording with the owner in view: one person track the whole time, lock verified on
every sample (descriptor distance 0.07–0.19, gate 0.25), two sub-second occlusions
re-verified immediately, heading swept 75°–110° following the person. The console alternated
FOLLOW and HOLD every 200–400 ms (439 vs 461 samples) because the observation reached the PC
older than the 200 ms budget about half the time (board publish age p50 153 ms, p95 212 ms,
plus transport). Tracking and identity were correct; the stutter is latency.

---

## 2. Why drone footage does not work

No model in this stack has been trained or fine-tuned on aerial data. The detector is the stock
COCO YOLO11s compiled for the 15L; the identity model is the stock OSNet person re-id. VisDrone
(research-use, never committed) was used only to evaluate. The failure decomposes into five
layers, largest first.

### 2.1 The detector does not see small people (dominant)
VisDrone-DET, 548 images, canvas 1280×720, five tiles (`bench/results/2026-09-12-visdrone-det/`):
person recall 0.02 under 16 px, 0.21–0.23 at 16–32 px, 0.58 at 32–64 px, 0.75 above 64 px; single
view is roughly half of that in the 16–64 band. Typical VisDrone pedestrians at the dataset's
altitudes are 13–48 px tall on this canvas. In the frozen eleven-clip rerun
(`bench/results/2026-09-13-dataset-rerun/sot/`) eight clips never had a detection at or above
the 0.5 birth floor on the target at the click frame (targets 13, 17, 21, 36, 37, 41, 48 px) — no
track exists to click on. Feeding the original pixels (up to 1080p, nine passes) raised person
recall only from 28 % to 31 % at the low floor for 70 % more inference time
(`…/dataset-rerun/det-paired/`). This is a model limit, not a tiling limit.

### 2.2 The pipeline throws away the sensor's resolution
The IMX678 produces 3840×2160; the ISP delivers 1280×720 to detection and every crop (tiles,
target ROI, OSNet) is cut from that frame. A 4K person of 100 px becomes 33 px. Native-resolution
pairing, buffer sizing, coordinate transforms and the region detector must change together to
crop before the downscale (`docs/2026-09-13-camera-isp-and-native-ros.md`); not done.

### 2.3 Identity cannot separate look-alikes from above
Colour histograms are not identity evidence on aerial pedestrians: on 024 the impostor's
distance was 0.19 against the target's own 0.33 median, and 88 % of other pedestrians sat under
the 0.55 gate (`bench/results/2026-09-12-visdrone-sot/README.md`). OSNet, trained for
ground-level full-body views, gives 0.213 median target-vs-others on 024 (gate 0.25): it removes
most wrong-person frames (299 → 26 on the single view) but refuses rather than tracks, so
on-target time stays low. Look-alike cars (245) swap on every flavour; person OSNet does not
apply to vehicles at all.

### 2.4 Acquisition and cadence
Two tracker defects blocked confirmation of correctly detected small targets (fixed in 1.3).
Under the causal rerun's declared 50 ms source period the measured processing (~175 ms per frame
in full view, more with tiles) skips three of every four source frames, so confirmation needs
three consecutive processed hits over ~600 ms; any dropout restarts it. Live, the searching
state runs ~6 fps at 250–400 ms age.

### 2.5 Control freshness
The follow consumer refuses observations older than 200 ms and intents older than 150 ms. The
board publishes at p50 153 ms in the locked state and higher while searching; with transport the
PC sees roughly half the ticks stale, producing the FOLLOW/HOLD alternation. On aerial clips
this compounds 2.4: even the acquired clips (086, 115, 245) spend only ~3 % of the timeline on
target inside the budget.

### 2.6 What the afternoon fix did and did not change
It removed one tracker-side cause of non-acquisition and improved retention and precision on
the clips that can be acquired at all. It cannot create detections: the seven detector-limited
clips are unchanged by design.

---

## 3. What would make drone footage work, in order

1. **Aerial-adapted detector.** Fine-tune on the VisDrone train split (or another aerial set) with
   sequence-separated validation, exact preprocessing parity with the HEF calibration
   transform, and quantised/HEF accuracy checked against the float model before deployment.
   Gate: person recall at 16–32 px on the frozen DET subset, then the eleven-clip rerun
   acquisition count (currently 3/11). The parser assumes 80 COCO classes; a ten-class VisDrone
   head needs decoder and class-map work.
2. **Native-pixel target ROI.** Crop the original exposure at full resolution for the ROI and the
   OSNet crop; keep the 640² detector input; one stable coordinate system; measure copy cost.
3. **Latency under 200 ms end to end.** Profile the searching state (tiles, embedding coverage,
   copies, motion) and cancel stale work; do not widen the control budget.
4. **Identity for the drone viewpoint.** Only after 1–2: a re-id model matched to top-down views,
   evaluated against crop-quality-matched baselines; vehicles need their own descriptor.
5. **Held-out evaluation discipline.** VisDrone-val has already influenced tuning; keep a
   frozen click protocol (the archived 0.41 → 0.01 confusion came from a reused click frame) and
   report retention and off-target output separately.

---

## 4. Where things are

| Item | Location |
|---|---|
| Native app, tracker, identity, ROI | `hosts/hailo15l/fresh_node.cpp`, `services/garuda-tracking/src/{tracker,target_owner,search_region,tiling}.cpp` |
| Follow profile | `hosts/hailo15l/fresh/perception-follow.json` |
| Build / stage / control | `hosts/hailo15l/{build_fresh_tracking,stage_fresh_tracking,fresh_tracking_ctl}.sh` (absolute paths; stage refuses a running node; verify the running hash) |
| Board ROS 2 / MAVROS | `hosts/hailo15l/ros2/`, chroot `/opt/garuda-ros-jazzy`, `docs/dependencies/ros2-mavros-bench.md` |
| Demo runner and console | `hosts/hailo15l/run_grand_demo.sh live|gazebo|replay NEW_DIR`, `bench/sim/{gazebo_follow,gazebo_console,remote_mavros,link_log}.py`, `bench/sim/follow_console.{html,js}` |
| Aerial evidence | `bench/results/2026-09-12-visdrone-{det,mot,sot}/`, `bench/results/2026-09-13-dataset-rerun/`, `bench/results/2026-09-13-tracker-duplicates/` |
| Datasets and prepared streams (never commit) | `/media/bhanu1234/Development/hailo-export/datasets/visdrone/`, `hailo-export/visdrone-sot-replay-20260912-roi/`, `hailo-export/visdrone-sot-embeddings-20260912/` |
| Builds | `hailo-export/tracker-fix-20260913/` (deployed `d150568d…`), `hailo-export/movement-fix-20260913/build/` (previous) |
| Session recordings | `hailo-export/live-console-20260913-{1900,1935}/` |

## 5. Gotchas

- Shell cwd drifts between tool calls: absolute paths, check exit codes, hash the ARM binary
  before staging. A profile key the binary does not know makes the node refuse to start.
- Never stop the desk node or launch a simulator while the owner's demo runs; the launcher
  refuses a second PX4 and an existing output directory.
- `run_sot_replays.py` reuses a flavour's conversion and click across summaries: hold the click
  frame equal (`--lock-after`) before calling anything a regression.
- Board `/tmp` is RAM; large replay artefacts go under `hailo-export/`, never root `/tmp`.
- Every vehicle command stays behind `GARUDA_SIM=1`, loopback and an owned PX4; there is no
  flight controller on this desk and nothing here is flight-ready.

## 6. 2026-09-14 update — the aerial detector work (read after §2)

Owner: "make this work with the aerial footage". What was done overnight, all measured
(`bench/results/2026-09-13-aerial-detector/README.md` §1–9, benchlog and decisions 2026-09-14):

- **§2.1 detector, addressed.** YOLO11s fine-tuned on VisDrone (COCO ids, same HEF recipe).
  Aerial-only forgets the desk; VisDrone + COCO-val2017 ("mixed e11") keeps it: person recall
  at the 0.5 floor 0.117 → 0.346 on the 548-image probe, desk person 433/433. Eleven-clip
  causal replay on the board (deterministic frame set, click retried ≤ 1 s): single view 3 → 6
  clips acquired and 74 → 129 on-target frames; adaptive 4 → 6 clips, 91 → 116 on-target, 2 → 1
  off-target, 58 → 58 inside the 200 ms budget. A phone re-balance ("phase 2") detects better
  still but follows worse (6 off-target frames on 024), so it was not deployed.
- **§2.4 cadence, addressed.** The handover window and corner-refresh period are profile keys
  (`follow_local_gap_ms` 1500, `follow_global_period_ms` 2000 in the aerial profile).
- **Bug found and fixed:** the ROI merge silently refused any detection cap above 256, so a
  512-cap profile never fed ROI boxes to the tracker (`0838a32`).
- **Deployed:** `hosts/hailo15l/fresh/perception-aerial.json` (`start-aerial`) with the mixed
  e11 HEF staged by hash; node `4666ffe8…`; desk profile unchanged on the controlled HEF; the
  live click on a person is still the owner's check.
- **Still failing, measured:** 13/17 px targets (092) never detected; 053 and 317×2 refused at
  the click; 024 lost within 250 ms to identity ambiguity in a walking group (OSNet 0.204 vs
  0.207 at 26 × 70 px) — §2.3 is now the dominant gap, followed by §2.2 and §2.5.

Where the new things are: profile `hosts/hailo15l/fresh/perception-aerial.json`; stage with
`GARUDA_FRESH_AERIAL_HEF` + `GARUDA_FRESH_AERIAL_HEF_SHA`; HEFs on the PC under
`hailo15/models/yolov11s_visdrone_*` and `…phase2_phone…`; training / compile / evaluation work
under `hailo-export/aerial-improve-20260913/` (never commit: datasets, weights, HEF builds);
builds `build-merge/` (deployed node and replay).

## 7. 2026-09-15 update — §2.2 native crop built and measured; not the lever the desk can show

- **Oracle crop on VisDrone 317** (only pair above 720p): no gain for the rider (720p ROI 0.70 vs
  0.52 native; rider labelled `motorcycle` at native scale, 3–4 overlapping boxes), a gain for
  the van (0.06 → 0.37 with a 2× native window). Source is soft, so gains were apparent size.
  The 317 click refusals were "no confirmed live object", not overlapping-box ambiguity.
- **Camera path built**: third frontend stream at 3840×2160, native ROI + OSNet crops, bench
  profiles `start-follow-native{,-compare}`, recorder/scorer `native_roi_*.py`; node `124cc94f…`.
  Two rules were needed and are in the profile: `target_roi_native_context` 7 (target ≈ 14 % of
  the crop; the 2.5× default put it at 40 % and the detector scored it lower) and
  `native_max_window_px` 1280 (native only under a 2× shrink).
- **Measured at the desk** (owner, then a phone down to 30 px): equal to today's crop wherever
  both show the target at the same scale; better only at 30–40 px (0.77 vs 0.43, six frames);
  both at the detector's floor at 40–60 px with the lock lost. Desk profile unchanged; the
  native profiles wait for an outdoor or drone-mounted session. §2.2 stays a real lever only for
  targets under ~8 % of the frame height, which is the aerial case and not this room.
- Board: desk profile `perception-follow.json` on node `124cc94f…` (native keys absent → the
  paired path; previous nodes in `/opt/garuda-fresh/backups/{aerial,native}-20260914/`).
- **Demo console (:8100) now runs the aerial profile on request:** `run_grand_demo.sh replay|gazebo
  … --aerial` (staged by `stage_sim_stream.sh`; the console names the model, schedule and
  crop state; `--select-retry-s` for the click). Verified on 086: 59 control-valid frames vs 5
  for the old fullview path, but no drone motion from either, because replay mode's PC
  transport puts every frame past the 200 ms receiver gate (296 / 399 ms median). Board-side
  ingress is the open item that would change that; `bench/results/2026-09-15-demo-aerial/`.

## 8. 2026-09-17 update — model lever 1 (1280×736 single pass): §2.1 is closed, §2.3 is the gap

- A 1280×736 compile of the aerial model detects small people in one 57 ms pass better than
  the five 640 tiles at 131 ms (DET person 0.378 vs 0.346; 16–32 px 0.334 vs 0.278). On the
  eleven clips it follows worse (3 vs 6 acquired, 79 vs 129 on-target), and every loss is in
  the tracker or the identity owner: neighbour ambiguity (024), rider class flips (029), the
  descriptor budget in crowds (054), incomplete identity evidence with more people visible
  (086). Not adopted; `bench/results/2026-09-17-detector-1280/`.
- Recipe, board detector, DET probe and scorers now take the network size as a parameter;
  descriptors are computed overlap-first (kept, +1 on-target / +2 fresh frames at 640).
- The order of work is therefore: identity for the drone viewpoint (§2.3), a rider rule, then
  the 1280 searching pass once the identity path can absorb more visible people.

## 9. 2026-09-18 update — model lever 2 (drone-view re-identification): §2.3 is closed for crowds, the rider is next

- OSNet x1.0 fine-tuned on VisDrone-MOT crops (epoch 30) is the aerial profile's descriptor,
  in a hash-pinned slot like the aerial detector (`1a37920`). Alone it already beats the zoo
  weights in single view (141 vs 129 on-target) and separates the 054 crowd, but it loses
  people the same way the old one did, because the losses are in the identity owner: one
  ambiguous frame releases the lock and a crowd of 40–58 people with six descriptors per
  frame can never be fully described, so re-binding is refused for the rest of the clip.
- Two opt-in owner changes (`75fa58b`) close that: an evidence reach (an undescribed person
  only blocks re-binding inside `identity_evidence_radius + growth × s` extents of the last
  verified box) and a focus fallback (the descriptor budget stays around the last verified box
  after a release). Aerial profile: gate 0.30, reach 0.5 + 2 per second. Eleven clips: single
  view 129 → 161 on-target with zero wrong-identity frames, adaptive 117 → 143. The desk profile
  keeps the zoo weights, gate 0.25 and the unbounded rule. `bench/results/2026-09-18-reid-visdrone/`.
- Harness: the control script's stop waits 10 s, the replay cleans its board staging directory
  (381 leftovers had filled the eMMC).
- Order of work now: the rider rule (029; the fine-tuned descriptor sees the person, the
  annotated box drifts to the motorcycle), a live aerial-style session at range with this
  descriptor, then the 1280 searching pass.
