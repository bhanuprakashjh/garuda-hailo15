# CLAUDE.md — Garuda SDK Bench (Pi 5 + Hailo-10H)

Project context for Claude Code. Read fully before acting. This file is the source of truth for what this machine is, what we are building, and the working rules. If anything here conflicts with an instruction in-session, ask.

---

## 1. What this project is

**Garuda SDK** — Microchip's companion-computer autonomy stack for drones/robotics. This machine is the **bench/dev tier**: Raspberry Pi 5 + Hailo-10H, developing host-agnostic services that later port to a Hailo-15H SoM (product tier). The flight controller is a **separate** device (Microchip PIC32CZ CA90 running PX4) connected over Ethernet — it is NOT part of this machine and hard real-time control NEVER runs here.

Full plan: see `docs/garuda-sdk-plan.md` and `docs/garuda-sdk.pdf` in this repo (copy them in if missing). Key architecture rules:

- Inner control loop never crosses Ethernet. We publish odometry + obstacles; FC owns attitude/rate.
- Failsafe gates on odometry covariance/validity, never on link liveness.
- One PTP clock domain for everything: camera triggers, image timestamps, IMU (from FC over DDS).
- Every sensor sits behind a plugin interface (`ICaptureBackend`, `IFrontEnd`, `IDepthSource`) — no Pi-specific calls outside `hosts/pi5/`.
- Licence policy is HARD: BSD/MIT/Apache/LGPL-dynamic only in services. **No GPLv3 code or dependencies** (no OpenVINS, VINS-Fusion, ORB-SLAM3, no GPL snippets from forums). linuxptp as external daemon is fine. If unsure about a licence, stop and flag. **[RELAXED 2026-08-02, owner directive: GPLv3/AGPL are permitted for BENCH / EXPERIMENTAL / EVALUATION work (running locally ≠ distribution). Keep any GPL component behind the plugin interfaces (ICaptureBackend/IFrontEnd/IDepthSource) and tag it `not-product-cleared`; never deep-wire GPL into shippable `services/`. Product-tier licence-clean remains the goal — revisit before Phase 8. See docs/decisions.md.]**

## 2. Hardware actually present (update this section as it changes)

| Item | State |
|---|---|
| Raspberry Pi 5, 8 GB | present, boots. **Cooling is a PASSIVE heatsink (no fan)** — OS registers no fan/cooling_device; plateaus ~84 °C and thermally throttles (`get_throttled` bit 3) under sustained one-core CV/NPU load. Keep on-device tools light (cap fps, throttle loops). Corrected 2026-08-01 (was wrongly "Active Cooler"); see decisions.md |
| AI HAT+ 2 (Hailo-10H, 40 TOPS, 8 GB on-module) | mounted via 30 mm PCIe FFC + 16 mm stacking header |
| 256 GB microSD | boot + OS |
| Power | USB-C — **verify 5 V/5 A**; run `vcgencmd get_throttled` after load tests; 0x0 = OK. If under-voltage flagged, note it in the bench log and distrust perf numbers |
| Camera Module 3 (IMX708, rolling shutter) | attached & verified 2026-07-29 on CAM/DISP 0, first light captured — inference/tracking/VLM dev only. CSI is NOT hot-pluggable: attach only with the Pi fully powered off. Cable orientation: gold contacts toward Ethernet at Pi end, toward PCB at camera end |
| 2× GS Camera (IMX296, global shutter) | sourcing — the ONLY VIO-grade cameras. XTR trigger is **1.8 V logic — 3.3 V destroys the sensor**; R11 rework required for external trigger |
| Arducam T2 ToF | planned — depth plugin, mapper/landing workstream only |
| USB H.264 camera | planned — recording path (Pi 5 has NO hardware video encoder; never software-encode during benchmarks) |
| LAN966x TSN switch EVB, CA90 FC board | not yet on bench — PTP work is point-to-point or against scope until then |
| **Hailo-15L SBC rev 2.x** (Hailo-15L SoC, 4× A53, 2 GB, 7.3 GB eMMC, IMX678 camera) | on bench since 2026-09-01 — a SEPARATE device from the Pi, not an EVB and not 15H. Boots its factory eMMC image (VPSP 1.12.0, HailoRT 5.3.0); `ssh root@10.0.0.1` (PC eno1 profile `h15-link` = 10.0.0.2/24; mutually exclusive with `pi-share`); console FTDI 115200 with DTR/RTS asserted; DIP SW1 both ON. Full snapshot: bench/versions.md 2026-09-02 |

**No flight hardware on this bench. Nothing here arms motors. If code touches MAVLink arming or offboard setpoints, it must be gated behind `GARUDA_SIM=1` or an explicit bench flag.**

## 3. This machine's software environment

- OS: Raspberry Pi OS **Trixie 64-bit** (Debian 13). Switched from Bookworm 2026-07-29: the Hailo-10H `h10-*` packages exist only in the Trixie repo — Bookworm (now oldstable) carries only the Hailo-8 line; see `docs/decisions.md`. OS major upgrades are always a **fresh flash, never in-place** (unsupported on Raspberry Pi OS). Record `uname -a` and package versions in `bench/versions.md` after every upgrade — Hailo driver/kernel coupling is the #1 bring-up failure.
- Hailo stack: install with `sudo apt install hailo-h10-all`. **Package family is `h10-*` / `h10-hailort` — NEVER mix with plain `hailort`/`hailo-all` (that's the Hailo-8 line).** If both appear installed, purge both, reinstall h10 only.
- Sanity: `hailortcli fw-control identify` must report Hailo-10H. `lspci | grep -i hailo` must show the device. Device in lspci but not hailortcli = version mismatch; absent = reseat FFC.
- Known Hailo pitfalls (apply ONLY on symptom, not pre-emptively):
  - vDMA timeout (−110): add `pcie_aspm=off` to /boot/firmware/cmdline.txt; `kernel=kernel8.img` in config.txt; `options hailo1x_pci force_desc_page_size=4096` in /etc/modprobe.d/hailo_pci.conf
  - PCIe Gen3 instability: fall back to Gen2 (`dtparam=pciex1_gen=2`) and note it — 10H holds weights in on-module DRAM so Gen2 is acceptable
- Cameras: libcamera/rpicam stack. `dtoverlay=imx296,cam0` etc. when GS cams arrive; `trigger_mode=1` via v4l2 for external trigger.
- ROS 2: **decided 2026-07-29 — Jazzy in Docker on Pi OS** (LTS to 2029; PX4 uXRCE-DDS compatible; see `docs/decisions.md`). Keep ROS thin — native on Pi OS: garuda-camera/-time, HailoRT inference, Basalt (plain C++, wrapped thinly); in the container: ROS nodes (VIO wrapper, mapper, planner), px4_msgs, rviz/rosbag2. DDS across the boundary: `--network=host --ipc=host`, one RMW pinned in both worlds (CycloneDDS). Container images build only from a committed Dockerfile in `hosts/pi5/` — never pulled-and-modified interactively (same idempotency bar as install.sh). Before Phase 4, services are plain C++/Python with the pipe/topic layer stubbed.
- Time: linuxptp (`ptp4l`, `phc2sys`); RP1 MAC has hardware timestamping (`ethtool -T eth0` to confirm).
- Python: system 3.13 under Trixie; Hailo python bindings come from the h10 packages — use venvs with `--system-site-packages` so bindings remain visible. If pyHailoRT misbehaves, verify the binding was built for the running Python (3.13) **before** debugging anything else — HailoRT/Python-version coupling is a known community pain point.
- Builds: prefer cross-compile from x86 CI for big targets; on-device builds use `-j2` (8 GB RAM) with zram/swap enabled.

## 4. Repo layout (create if missing, keep to this)

```
garuda-sdk/
├── CLAUDE.md                  # this file
├── docs/                      # plan md/pdf, bring-up guides, decisions log
├── services/                  # garuda-camera, -vio, -inference, -bridge, -time, -health, -logger, -portal, -ota
├── interfaces/                # ICaptureBackend, IFrontEnd, IDepthSource, message schemas — THE contract
├── hosts/pi5/                 # overlays, cmdline/config fragments, install scripts (idempotent)
├── models/                    # HEF fetch/build scripts + model cards (DFC runs on x86, never here)
├── calib/                     # Kalibr wrappers, targets, procedures
├── bench/                     # harnesses: sync-jitter, ptp-offset, per-stage profiler, versions.md, benchlog.md
├── datasets/                  # EuRoC/TUM-VI runners, baselines/ (committed numbers)
├── yocto/meta-garuda/         # recipes-in-waiting for the Hailo-15 product tier (see rule 6)
└── ci/                        # x86 build, unit, licence-scan (MUST fail on GPLv3)
```

## 5. Phase status & gates (tick as achieved; numbers go in bench/benchlog.md)

- [x] **P1 NPU sanity** — identify OK; model-zoo YOLO ≥30 fps on sample video; one LLM answering via hailo-ollama *(ticked 2026-07-29: identify HAILO10H FW 5.1.1; 75.95 fps end-to-end yolov8m; qwen2:1.5b answered — bench/benchlog.md)*
- [ ] **P2 capture** — CM3 streaming; later: GS pair triggered, inter-camera jitter <100 µs (LED-flash rig), 1 h no-drop at 30 fps
- [ ] **P3 time** — ptp4l stable; offset <50 µs RMS through switch (point-to-point sub-µs first); trigger generated from disciplined clock, pulse↔frame matching proven incl. dropped-frame case
- [ ] **P4 VIO** — Basalt on EuRoC headless first (record fps + per-stage ms on this Pi); live gate when GS pair arrives: ≥20 Hz front end, ≥200 Hz pose, <20 ms latency
- [ ] **P5 bridge** — MicroXRCEAgent up; odometry → EKF2 external vision on CA90; VIO-kill → covariance failsafe demonstrated
- [ ] **P6 load** — VIO + detection + VLM concurrent; no VIO frame deficit; no throttling (`vcgencmd get_throttled` = 0x0); thermals logged

## 6. Working rules for Claude Code (non-negotiable)

1. **Numbers are sacred.** Never invent, estimate, or "expect" a benchmark result into any doc, commit message, or code comment. Every performance figure must come from a harness run on this machine and be recorded in `bench/benchlog.md` with date + `versions.md` snapshot. If asked to fill a number you don't have, write `TBD-bench`.
2. **Artifacts before assumptions.** Before writing configs/drivers against hardware state, check it: `uname -a`, `lspci`, `ethtool -T eth0`, `libcamera-hello --list-cameras`, package versions. Record findings, then code.
3. **Idempotent scripts.** Everything in `hosts/pi5/` must be safe to re-run. No unguarded appends to cmdline.txt/config.txt — check-then-modify.
4. **Don't apply known-fixes pre-emptively** (ASPM off, Gen2 fallback, desc page size). Only on reproduced symptom, and log the symptom + fix in docs/decisions.md.
5. **Hardware safety:** never instruct or script anything that drives GPIO toward camera XTR without the 1.8 V level-shift path being explicit. Flag any 3.3 V-direct suggestion as an error.
6. **Licence gate:** before adding any dependency, state its licence in the commit/PR description. CI licence-scan failing is a hard stop, not an override. When a dependency lands, also drop a skeleton bitbake recipe (name/version/LICENSE/SRC_URI stub; unbuilt is fine) in `yocto/meta-garuda/` — recipes accrete one at a time so the Hailo-15 port inherits a half-built layer, not a greenfield.
7. **Small commits, tested.** Each service change lands with its unit test or harness invocation. If a test can't run without absent hardware, mark it `@requires_hw(camera_gs)` style and ensure CI skips cleanly.
8. **Structural review at midpoints:** after every ~10 files or a phase boundary, stop and summarise repo state vs this file; propose pruning before adding.
9. **Red-team on phase close:** before ticking a gate, write the strongest argument the result is wrong (thermal throttled? underpowered? wrong clock source? cherry-picked dataset?) and address it in benchlog.
10. **Sudo/system changes:** propose the command and what it modifies; for anything touching boot config, driver install, or partitions, wait for explicit go-ahead in-session.
11. **Never `apt upgrade` casually** — kernel bumps can break the hailo driver mid-sprint. Upgrades are a deliberate act: snapshot `versions.md`, upgrade, re-run P1 sanity, record.
12. **The FC is sacred:** any code that could reach PX4 (DDS/MAVLink) defaults to a simulated endpoint. Real-FC sessions are explicit, and never write parameters to the FC without listing them first.

## 7. Current immediate objective (updated 2026-08-07 — RESUME HERE)

*(P1 done 2026-07-29. Original P1 text retired; see benchlog.)*

**Bench state:** Pi (garuda@10.42.0.128, passwordless sudo) runs a FRESH 5.3.0 SD: HailoRT/fw/pcie-driver **5.3.0** (pcie driver needs the `del_timer_sync`→`timer_delete_sync` source patch on kernel ≥6.15 — decisions.md 2026-08-07; re-apply after any re-flash). Only the CM3 is connected. Service **`garuda-mono`** (systemd, GUI at `http://10.42.0.128:8098/`): YOLO26m detect every frame (letterboxed input) + ByteTrack click-to-lock (coast + 5-frame re-acquire — owner verified "lock is better" 2026-08-07) + depth→distance with 60 s chart; cal points persist (`mono_cal.json`). Depth source switch `GARUDA_MONO_DEPTH` (systemd drop-in `depth.conf`): currently **`da`** = DepthAnything relative + cal fit (INTERIM), because the smoke `yolo26n-depth` HEF (4 calib images) collapsed — reads ~2.5 m everywhere (benchlog 2026-08-07). Branch: `feat/stereo-target-range` (worktree `.worktrees/stereo-target-range`), through commit `abbb89f`+.

**2026-08-07 evening — production HEF built + deployed.** GPU restored; venv needed `nvidia-cuda-nvcc-cu12` (TF JIT); QAT OOMed the 6 GB GPU at batch 8/4/2 → owner chose **PTQ-only** (level 2, a16, 1024-img calib: 256 CM3 + 768 SUN RGB-D, `depth-calib.yaml`). `yolo26m-depth.hef` (768², 31.9 MB) deployed to the Pi, drop-in now `GARUDA_MONO_DEPTH=y26d`, cal reset, service active. **Probe gate PASS** (logit std 0.263 vs ~0.04 collapse signature; span 0.96–2.80 m). Details: decisions.md + benchlog 2026-08-07 (evening).

**NEXT, in order:**
1. **Portal tracking convergence + detection upgrades** — owner-approved spec:
   `docs/superpowers/specs/2026-08-07-portal-tracking-integration-design.md` (mono grows JSON/SSE
   API; portal follow view converges with mono tracking; yolo_world_v2s open-vocab mode; bench-gated
   960² yolo26m rebuild). Branch `feat/portal-tracking` after this branch merges.
2. **Deferred (owner, 2026-08-07): y26d physical validation** — move-test + tape-measure accuracy
   run remain TBD-bench in benchlog; metric scale is UNVALIDATED until then. If accuracy proves
   insufficient, revisit QAT (overnight batch-1 or bigger GPU) — decisions.md.

**2026-09-02 — HAILO-15L SBC BRING-UP DONE (Phase 9 pulled forward; RESUME HERE).** Note: §7 above is
STALE vs `feat/portal-tracking` (51 commits ahead in worktree `.claude/worktrees/feat+portal-tracking`,
merge pending owner) — that branch's CLAUDE.md §7 (2026-08-10) is the current Pi bench state. The
board on the bench is a **Hailo-15L SBC rev 2.x** (not the assumed 15H EVB). Bring-up spike complete
and recorded (rule 2): stock eMMC image `vpu-stability-v1.12.0` = newest VPSP, `hailortcli identify`
→ HAILO15L FW 5.3.0, IMX678 enumerates, Ethernet + SSH + console working — **no re-flash needed**.
PC-side: VPSP 1.12.0 + board-tools venv + QSG rev 1.3 under `/media/bhanu1234/Development/hailo15/`
and `Development/downloads/`; details + gotchas in decisions.md 2026-09-02 and memory
`h15-kickoff-2026-09-01.md`. DFC 5.3.0 targets `hailo15l`. **Pending owner: scope** — (a) garuda-mono
parity demo on the SBC (recommended; first step = stock `setup_hailo_sensor.sh` + `camera-viewer-server`
smoke test, then recompile an existing HEF for hailo15l), (b) full Phase 9 port, (c) characterise-only.
The 15L is a fair proxy for the 15H everywhere except NPU headroom — never quote 15L fps as 15H.

**2026-09-02 (later) — M0 done.** Perception node pipeline (frontend->yolov8->post->snapshot/JPEG
feed) built, deployed, and proven end-to-end on the SBC, on branch `feat/hailo15l-perception`
(plan: `docs/superpowers/plans/2026-09-02-hailo15l-perception-node-m0.md`); first measured numbers
in `bench/benchlog.md` 2026-09-02 "Hailo-15L SBC: M0 pipeline proven". Next: write the M1 plan.

**2026-09-03 — M1 tracking parity deployed on the SBC; coast/re-acquire behaviour validated with the
owner in view and the coast window tuned for the board (`max_lost` 25→75, `reacq` 5→15 frames, i.e.
~2.5 s / 0.5 s at 30 fps — benchlog M1 addendum "owner present"); the CPU-with-person 600 s run is
still pending.** ByteTrack + mono's lock/coast/re-acquire ported into
the node and bench-measured on the SBC (branch `feat/hailo15l-tracking`, node commit `b87caed`;
`bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: M1 tracking parity"); person-in-view validation is
an ADDENDUM PENDING owner presence (that section's numbers are all zero — the scene was empty).

**2026-09-03 (later) — M2 done.** yolo26m live on the SBC via our own post-process plugin
(`libyolo26_post.so`, replacing the stock yolov8n path), bench-measured (`bench/benchlog.md`
2026-09-03 "Hailo-15L SBC: M2 yolo26m detector"); rollback to the stock M0/M1 path is one command
(`GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8n.json
hosts/hailo15l/deploy.sh`). **Final-review fix wave (same day): a standing snapshot-age backlog
(camera 30 fps vs the detector's ~25.74 fps ceiling) was root-caused and fixed** (sink0 framerate
25/pool_max_buffers 6 + smaller detect/post queues) — measured `age_ms` max dropped from 887 ms to
194 ms (min 847→110 ms), bench/benchlog.md ADDENDUM 2026-09-03 "snapshot-age regression: mechanism
and fix".

**2026-09-03 (later still) — Kalman tracker engine A/B'd against mono's tracker on phone and
person routines** (branch `feat/hailo15l-kalman-tracker`; SDK engine + person profile now the
follow default, small-object phone tracking unsolved by either engine) — `bench/benchlog.md` and
`docs/decisions.md` 2026-09-03.

**2026-09-04 — F1 lock core implemented and bench-measured on the SBC branch.** A dedicated
time-based locked-target tracker (`garuda::lock::LockCore`) replaces the old resolver-borrowed
multi-object-tracker id as "the lock" (spec §8.2, `docs/decisions.md` 2026-09-04). Four on-board fix
rounds against real captures (auto-acquire edge/confidence/streak gating; relative position/size
gates + same-id relaxation; follow-but-don't-learn + band-dependent score floor + widened window to
expiry) took routine 1 (walk-out/return) from 4 relocks/29 % `core_miss_live` failures down to a
clean fresh-capture pass. Owner routines 1 (walk-out/return, run 6), 2 (occlusion, run 9b) and 4
(fast lateral, run 8) are measured — numbers in `bench/benchlog.md` 2026-09-04 "Hailo-15L SBC: F1
lock core" Results table; routine 3 (two-person swap) was skipped (owner: no second person
available) and routine 5 (phone, all-classes config) is pending — both stay `TBD-bench`. Branch
`feat/hailo15l-kalman-tracker` at final commit `47fb866`; integration into master is pending the
owner. **NEXT** = F4/F2 (DSP ROI for small objects / visual tracker) per the spec's §8.2 order, the
choice between them the owner's; fix rounds 5–6 (Ruling 22 phone false-lock class gate; Ruling 23
same-class duplicate-box dedupe, confirmed on a fresh close-range capture, run 11) have since landed,
alongside a same-evening yolov8m/yolov11m/yolov11s detector A/B naming yolov11s a follow-profile
candidate pending a repeat under a fixed protocol (`bench/benchlog.md` 2026-09-04 evening). **Round 7
(Ruling 24) makes `config/perception-yolov11s.json` the documented follow profile** (owner decision on
that single A/B — the fixed-protocol repeat is still owed) and adds two gates against the owner's "all
over the place": `tracker.hailo.birth_conf` (no track is published until one live detection reaches
it, the SDK tracker having no confidence floor of its own) and `lock.auto_streak_window` (auto-acquire
now needs 5 gate-passing live frames within 15, not 5 consecutive, which an intermittently-detected
target never reached) — deployed, but its live re-measurement is `TBD-bench`. F3/F5/F6,
measuring routine 3, a fresh phone LOCK routine, and that A/B repeat all still follow.

**2026-09-13 — ROS/MAVROS follow SIL continuation.** Owner requires ROS 2 and
MAVROS on the **15L**, feeding PX4. Real ARM64 Jazzy/MAVROS is installed in the
separate `/opt/garuda-ros-jazzy` bench chroot; stock Yocto/native Hailo stays intact.
Current handoff: `docs/2026-09-13-ros2-mavros-campaign.md`, then `docs/decisions.md`.
Read the failed aerial/crowd evidence before claiming robustness. PX4 is still
PC SITL only; PC-independent native ingress and real FC qualification are open.

## 8. Glossary (project-specific)

- **CA90** — PIC32CZ CA90 MCU, the PX4 flight controller (separate board)
- **Garuda** — this SDK; also the team's dsPIC33 ESC project ("Garuda ESC") — different repo, don't confuse
- **Gate** — a measured pass/fail number defined in §5; gates decide phase progression
- **HEF** — Hailo executable format (compiled model); built on x86 with the Dataflow Compiler
- **PAB** — Pixhawk Autopilot Bus (FC module standard, product-tier context)
- **T1S** — 10BASE-T1S multidrop Ethernet (product-tier ESC bus; not on this bench)
- **XTR** — IMX296 external trigger pad, 1.8 V logic
