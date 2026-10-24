# bench/versions.md — environment snapshots

## 2026-09-28 — uuZEjY capture review

Same enabled visual-phone deployment below; read-only postcheck verifies node
76718b8887f873832d541ea2b2584e6c22d93b0890df6553db92479c44ecf378 and config
572dcddb2197e849afd9fb2de4953330c814bf56d9f668ffa9ccc33f642f76d1.
Capture source=false, port8983, native running, replay/MAVROS absent;
free eMMC2598076416bytes. No software, model, camera or config changes.
Evidence: results/2026-09-28-live-visual-recordings/uuZEjY/README.md.

## 2026-09-28 — visual-phone live trial enabled

Same board/kernel/HailoRT5.3.0/vendor OpenCV4.5.5, no installations. Exact SDK
build with GARUDA_TRACKING_VISUAL_TARGET=ON deployed as node76718b88...cf378.
Config572dcddb...f76d1 differs from the previous1024 profile only by enabling
tracking.visual_phone_tracking. Existing HEFbb9fe29b...ab43 and all media,
sensor/IQ/stabilizer/re-ID/postprocess files hash-identical. Preview service
restarted; current lock cleared. 25-state startup checks pass. Source hashes,
dependencies and prior/new binary/config hashes are retained in
results/2026-09-28-live-visual-enabled/run.json. No boot/FC/recording changes.

## 2026-09-27 — optional selected-target visual plugin

PC Linux7.0.0-31-generic x86_64, GCC13.3 native/OpenCV4.6.0 core+imgproc;
Hailo SDK GCC11.5/OpenCV4.5.5 shared libraries, board
Linux5.15.32-yocto-standard-g1de0438be5ae aarch64, existing HailoRT5.3.0.
No OS/driver/library/model/data installation. OpenCV Apache-2.0, reused
existing dependency recipe skeleton; no GPL code added to services.
Offline rendering/exploration uses existing export Python3.11/OpenCV5.0.0;
the deployed candidate implementation and all accuracy claims use C++ replay.
Native and ARM replay built with one OpenCV thread. CPU-only board probes
run nice19, no camera-service replacement. Live node SHA0ad69977...55124 and
current config SHA26d38d7c...6175 remain unchanged through all three probes;
same live stream continues advancing. Staged CPU probe binaries/configs total
about28MB eMMC; no pixel recordings added. Exact hashes and before/after state:
`results/2026-09-27-visual-target/board-round4/run.json`.

## 2026-09-27 — live 1024 full-frame trial (owner requested)

Same board/kernel/HailoRT5.3.0 and deployed node0ad69977...55124, no rebuild or
dependency/boot update. Candidate HEFbb9fe29b...ab43 now active in unique
`/opt/garuda-fresh/live-1024.8GsSQc` stage; current.json SHA256
`26d38d7c7681aaaf67303af08b9e1f636a6e3e8c8940cc14019478f253716175`.
Frontend1024x576 full view;1280x720 preview; tiles/ROI/managed detection off.
Paired diagnostic recording disabled to retain the2MiB cap, re-ID unchanged.
Sensor/IQ/stabilizer/postprocess/original profile/model/binary hashes checked
unchanged.20-frame-state startup sample passed; previous config preserved for
rollback. No recording or FC activity. Two deployment unit tests pass.
Evidence, failed attempts, health measurements and rollback:
`results/2026-09-27-live-1024-final/README.md`.

## 2026-09-27 — same-weights 1024x576 detector trial

No OS/runtime/driver/dependency installation, no live model/profile/ISP change.
Existing export venv: Python3.11, Ultralytics8.4.115 (AGPL bench-only,
not-product-cleared), PyTorch2.9.1+cu128, ONNX1.17.0, ORT1.18.0,
TensorFlow2.19.1, DFC5.3.0. Existing RTX3060Laptop6GB, Hailo15L SDK cross-build,
board HailoRT5.3.0. PC uname and source hashes retained in final-check.json.

Same frozen YOLO11s weights verified:175 exact parameter tensors, four complete
640 output comparisons bit-exact. New1024x576 candidate HEF SHA256
`bb9fe29b984e296be1cf15c8b934aca7514428ed2d1d4cc54f6bd11017efab43`.
DFC selected12 contexts; all four build stages exit0. No training. Existing1024
SUNRGBD calibration image/hash list unchanged; shape-specific PTQ rerun.

Rebuilt ARM crop/region probes, not the deployed node. New candidate/probe only
staged in `/opt/garuda-fresh/resolution-audit.8zoHlw`; recorded source pixels
streamed from PC, no new recordings/deletions. All2172 probe evaluations completed.
8CTest /70benchPython /68trackingPython(1skip) PASS. Restored live node0ad69977...,
profile12578dc5..., HEFaec84f00... unchanged; sequence376→388, no capture/replay/
MAVROS. Runtime AE33006us,3DNRenabled/mode1/strength127. eMMCfree2734161920bytes.
Full protocol, hashes, stage logs, predictions and limitations:
`results/2026-09-27-resolution-1024/README.md`. Candidate NOTpromoted.

## 2026-09-27 — recorded-pixel filter/native campaign

No board OS/runtime/model/ISP/profile upgrade. Existing exactSDK ARM build and
PC GCC13.3.0/Python3.12.3; native core and ARM region probe/node rebuilt. Only probe
staged in owned directories, node NOTdeployed. Deployed node0ad69977...,
profile12578dc5..., HEFaec84f00... unchanged after every finally restoration.
988phone crop evaluations and42matched native/via720 evaluations; native pair
repeated exactly after CLI compatibility change.8CTest/68trackingPython(1skip)/
14input-auditPythonPASS. Runtime camera controls, probe/source hashes, reproduction
and caveats: results/2026-09-27-recorded-input/README.md and final-check.json.

## 2026-09-27 — phone camera/input audit

No SDK/OS/runtime/model/ISP/profile upgrade. Existing ORT1.18.0 venv and frozen
controlled YOLO11s float source used for same-DSP-pixel scoring. Existing ARM
crop/model probes52490d52.../d77c4909... run on31 regions from4 retained exposures.
Six new diagnostic unit tests PASS. Full hashes, runtime camera audit, raw probe
outputs, score reports and final live health: results/2026-09-27-image-path/.
Node0ad69977..., profile12578dc5..., HEFaec84f00... unchanged after finally restore;
camera advancing sequence1728, no replay/MAVROS/recording. No tracking improvement
or native4K causal result claimed. Sparse hand boxes/oracle crops are diagnostic.

## 2026-09-27 — drone replay detail/budget evaluation (no live deployment)

Measured PC: Linux7.0.0-31-generic, Python3.12.3, GCC13.3.0 Ubuntu
13.3.0-6ubuntu2~24.04.1. Exact existing ARM SDK cross-build, no installs/upgrades.
Measured board: Linux5.15.32-yocto-standard-g1de0438be5ae,
/etc/os-release Hailo15l VERSION1.12.0. Existing HailoRT5.3.0 setup from prior
snapshots unchanged; no new runtime/firmware install. Detector and descriptor
SHA256 verified over SSH; full hashes, candidate/live binary/config hashes,
protocol and build results in results/2026-09-27-drone-budget/README.md.
Live node restored after every replay; active binary/profile hashes unchanged.
No thermal/clock time-series qualification; timing figures are single-run replay
compute plus declared source age, not live sensor-to-controller timing.

Same-day recovery follow-up uses the same SDK/runtime/models; no install or live
deployment. Candidate replay907dd6d5...543624 and node0c51a7b4...207aa8, archived
under ignored local-baselines/20260927-car-recovery-evidence/. Full hashes/build
log and eight OFF/ON replay records: results/2026-09-27-car-recovery-evidence/.
Default-off current-detection veto rejected for promotion because correct recovery
regresses on development footage, despite removing the retained wrong ROI lock.

Same-day track/record follow-up: no SDK/OS/native/model/profile upgrade. Reused
907dd6d5...543624 for11 full-sequence replay trials; all restored before recording.
Staged Python-only receiver/qualifier in new /opt/garuda-fresh/local-record.* dirs.
First two captures failed with transport timeouts/eMMC write stalls; post-run
protected hashes matched0ad699771e...55124 and12578dc598...ea333. Third RAM-first
trial had incorrect CMA accounting; SSH/API stalled, ping/serial still respond.
Final runtime health/hashes UNVERIFIED after third trial. No reboot performed;
owner recovery requested. Corrected non-CMA guard exists locally, not qualified on
board. Do not reuse earlier staged receiver scripts. Evidence/script hashes:
results/2026-09-27-track-record-readiness/local-capture-{01,02,03}/run.json.

17:12 IST recovery addendum supersedes unverified live state above: owner power
cycle/intervention restored network; boot ID eb5db10e-a888-48af-8a64-c0900cea81ba,
same Linux5.15.32-yocto-standard-g1de0438be5ae. Node/config full hashes unchanged.
Existing start-current restored live camera. Corrected Python receiver SHA
f6c9b210dfcbb0cfce65f39e2ccdcb1bd2fc67e0ad5583d1e40f189287b8c09c,
qualifier df3408c87d8eae9eb7fabf194731e76ee6a3f1e109cddcd965baf8bd2afd2677
staged in /opt/garuda-fresh/local-record.KQug9n;16-sample local smoke integrity
PASS. Evidence local-capture-04/run.json and postcheck.json. No native/OS/model/
profile upgrade. Sustained recording and tracking qualification remain open.

Same-day phone schedule investigation: board binary/profile remain the protected
0ad69977... /12578dc5... pair. Rebuilt PC native targets only, using existing
/tmp/garuda-drone-budget-20260927/native.8CTest and68Python tracking tests(1skip)
PASS. No new runtime algorithm; local opt-in250ms bounded phone miss candidate,
one recorded-time native regression and offline timing analyzer. Detailed hashes
and observed baseline timing: results/2026-09-27-phone-schedule/README.md. No live
deployment, ARM rebuild, OS/model/ISP/dependency or autonomous-control change.

Later owner-present A/B: existing live binary0ad69977... unchanged. Temporarily
applied candidate profile0533053071d8278ed34edf2a8f300c060e2d57bf6f61a1f3fbcfc6cde202afd6
(only phone_short_miss_ms250); native branch activation seen in one recorded frame.
Restored exact original12578dc59850faa29865335f2e17583146fc3bbf08e65d5618aa81aeea7ea333
from /opt/garuda-fresh/phone-schedule-ab.0COw9J/baseline.json; camera readiness PASS.
Binary/models/ISP/OS untouched. Both16-sample eMMC captures integrity PASS, but
different starting states/motion invalidate a causal improvement claim. Candidate
not promoted. Full results and final stream/hash evidence: phone-schedule README.

## 2026-09-22 — offline phone-association candidate (PC, no deployment)

Measured local runtime: Linux 7.0.0-31-generic, Python 3.12.3,
GCC c++ 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1).
Existing NumPy 2.3.3 / Pillow 10.2.0 used only for NV12 source-pixel inspection.
Exact-SDK build uses existing /media/bhanu1234/Development/hailo15/sdk,
environment-setup-armv8a-poky-linux; no SDK/dependency/board upgrade.
Capture runtime remains the prior Hailo-15L VPSP 1.12.0 / HailoRT 5.3.0 setup.
Evidence and binary/config hashes: results/2026-09-22-phone-motion/phone-gap-candidate.md.
Native and ARM build/test results are not board runtime or tracking qualification.

Rule: append a new dated snapshot after every upgrade or system change on the Pi.
All entries are from commands actually run on the bench Pi (or PC where noted).

---

## 2026-09-02 — Hailo-15L SBC rev 2.x bring-up (PC-side + board; SEPARATE device from the Pi)

Board reached over its on-board FTDI console and Ethernet from the PC. All values below are from
commands run on the board (or PC where noted). Guide: `hailo15l_sbc_2.x_quick_start_guide_1.3.pdf`
(rev 1.3, June 2026, aligned with VPSP 1.12.0), kept in `/media/bhanu1234/Development/downloads/`.

- **Board**: Hailo-15L SBC, silkscreen `PCB00150 Rev2.0`, RJ45 kit label `REV2.21`; device-tree model
  `Hailo - Hailo15l SBC VPU Development Board`; kit lacks its 32 GB microSD (slot is on the REAR side).
- **uname -a**: `Linux hailo15l 5.15.32-yocto-standard-01777-g4a09ed49eec6 #1 SMP PREEMPT Mon May 18 23:22:17 UTC 2026 aarch64 GNU/Linux`
- **OS**: `/etc/os-release` NAME=Hailo15l VERSION=**vpu-stability-v1.12.0**; `/etc/build-info` poky
  4.0.23 (kirkstone), MACHINE=`hailo15l-sbc` — i.e. the eMMC already carries the current 1.12.0
  image; QSG §2.4 says no re-flash needed at 1.12.0.
- **`hailortcli fw-control identify`**: device `[integrated]`, Control Protocol 2, **Firmware 5.3.0
  (release,app), Device Architecture HAILO15L** — PASS (same HailoRT 5.3.0 line as the Pi bench + PC DFC).
- **Hailo packages** (opkg): hailortcli 5.3.0, hailort-server 5.3.0, hailo-integrated-nnc 5.3.0,
  hailo15-nnc-fw 5.3.0, hailo-analytics-api 1.12.0, hailo-camera-configurations 1.12.0,
  hailo-thermal-engine 5.15.32, gstreamer1.0 1.20.7.
- **CPU/RAM**: 4× Cortex-A53 (CPU part 0xd03); `free -m` total 1913 MB. thermal_zone0 39.4 °C idle.
- **Storage**: eMMC `mmcblk1` 7.3 G — p1 64 M (boot), p2 7.2 G rootfs (`/`), p5 64.8 M; boot0/boot1 4 M.
  Rear side also carries QSPI flash and a PCIe x1 Gen3 M.2 M-key slot (QSG fig. 3).
- **Camera**: `imx678 0-001a` probed (Sony IMX678, not the QSG's IMX675); media-ctl topology
  cdns_csi2rx → hailo15_pixel_mux → hailo15_rxwrapper at 3840x2160 SRGGB12; /dev/video0..53,
  /dev/media0. Boot dmesg shows one `hailo15_video_create_pipeline` post-event timeout (−11) —
  noted, not yet investigated; demo pipeline not yet run.
- **Network**: board eth0 static **10.0.0.1/24** (`/etc/network/interfaces`), 1000 Mb/s link to PC
  eno1. PC: new NetworkManager profile `h15-link` = eno1 manual 10.0.0.2/24, autoconnect off
  (`pi-share` untouched; `nmcli con up pi-share` returns eno1 to the Pi). ping 0.17 ms.
  SSH `root@10.0.0.1` (default password `root`); PC `id_ed25519` installed → BatchMode works.
- **Console**: on-board FTDI FT230X (`SBC_H15L`, serial HLNTE2P252600005) on micro-USB J1,
  `/dev/serial/by-id/usb-FTDI_SBC_H15L_*` → ttyUSB0/1 (re-enumerates on every power-cycle: the
  bridge is board-powered). **115200 8N1 with DTR+RTS asserted** — with them dropped the text is
  garbled. Linux console = ttyS1; login root/root. Boot ROM never transmits on non-secure parts.
- **DIP SW1**: both ON = normal eMMC boot (QSG fig. 7, factory setting). OFF/OFF + power-cycle →
  no boot (silent). FTDI CBUS pins (from `hailo15_board_tools`): 0=RESET, 1=POWER_ON_OFF,
  2=BOOT_STRAP (0 = UART boot on H15L), 3=MUX_SEL (DRIVE1 = console to on-board FTDI); EEPROM
  verified factory-set (cbus_mask 0b0111).
- **PC-side tooling**: Vision Processor SW Package 1.12.0 (`hailo_vision_processor_sw_package_1.12.0_hailo15l_sbc.tar.gz`,
  3.9 GB) extracted to `/media/bhanu1234/Development/hailo15/vpsp-1.12.0/` — prebuilt boot chain +
  `hailo-update-image-hailo15l-sbc.swu` + cross SDK installer (poky 4.0.23 toolchain, 2.5 GB) +
  `hailo15_board_tools` 1.12.0. venv `hailo15/venv-boardtools` (Python 3.12.3): hailo15_board_tools
  1.12.0, pyftdi 0.56.0, pyspiflash 0.6.3, pyserial 3.5. `mkenvimage` (u-boot-tools 2025.10) present;
  `lrzsz` absent. `hailo_ai_sw_suite_2026-04.run` = DFC/HailoRT 5.3.0, identical to hailo-export — not installed.
- **eMMC untouched**: five blind `uart_boot_fw_loader` attempts (RAM-only recovery agent) all
  failed at the agent handshake — no programmer step ever ran.

## 2026-09-02 — Hailo-15L SBC: M0 perception node deployed

Sub-entry to the bring-up snapshot above (same board, same session family). Node commit
`4ebd020` (`feat/hailo15l-perception`), running under `/etc/init.d/garuda-perception` on the
board. SDK toolchain: poky **4.0.23** (cross SDK; `/etc/build-info` on the board, see the bring-up
entry above — not re-run for this sub-entry). HailoRT/firmware: **5.3.0**, Device Architecture
HAILO15L (`hailortcli fw-control identify`, see the bring-up entry above). HEF:
`hailo_yolov8n_384_640.hef` (384x640, `/home/root/apps/shared/resources/` on the board, stock
Hailo demo asset). Post-process: `libyolo_hailortpp_post.so`
(`/usr/lib/hailo-post-processes/` on the board, stock Hailo asset). Node config:
`services/garuda-perception/config/perception.json`. First measured numbers from this build:
`bench/benchlog.md` 2026-09-02 "Hailo-15L SBC: M0 pipeline proven".

## 2026-09-03 — Hailo-15L SBC: M1 tracking parity deployed

Sub-entry to the M0 sub-entry above (same board, same session family; board not power-cycled
between the two — `uptime` in `bench/benchlog.md` 2026-09-03 shows continuous uptime since a
2026-09-02 reboot). Node commit `b87caed` (`feat/hailo15l-tracking`), running under
`/etc/init.d/garuda-perception` on the board (pid 3511 at measurement time, `md5sum
/opt/garuda/bin/garuda-perception` = `ca3513114674957c26ec88399140f02a`). Adds ByteTrack + mono's
lock/coast/re-acquire rules in the node; deployed binary path `/opt/garuda/bin/garuda-perception`,
config `/opt/garuda/perception.json` (per `hosts/hailo15l/deploy.sh`, not
`/opt/garuda/config/perception.json` as an earlier draft of this task guessed). Toolchain/SDK/
HailoRT/image copied unchanged from the 2026-09-02 M0 sub-entry above (not re-derived for this
sub-entry, per instruction): SDK toolchain poky **4.0.23**; HailoRT/firmware **5.3.0**, Device
Architecture HAILO15L; HEF `hailo_yolov8n_384_640.hef` (384x640,
`/home/root/apps/shared/resources/`, stock Hailo demo asset); post-process
`libyolo_hailortpp_post.so` (`/usr/lib/hailo-post-processes/`, stock Hailo asset). One deployed
config change from M0: detector NMS score threshold now reads from `track.conf_floor` = **0.15**
(M0 had a literal `0.3f` — `git show 4ebd020:services/garuda-perception/src/node_main.cpp` line 89
`.set_nms_score_threshold(0.3f)`), per `docs/decisions.md` 2026-09-03. First measured numbers from
this build: `bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: M1 tracking parity".

## 2026-09-03 — Hailo-15L SBC: M2 yolo26m detector deployed

Sub-entry to the M1 sub-entry above (same board, same session family; board not power-cycled
between the two — `uptime` at this run's own conditions check, `bench/benchlog.md` 2026-09-03 "M2
yolo26m detector", shows continuous uptime since the same reboot). Deployed node commit `8c82367`
(`feat/hailo15l-detector`; this task's PC-side `git rev-parse HEAD` was `25d7bd1`, one commit
ahead, but `git show --stat 25d7bd1` touches only `services/garuda-perception/tests/` — the
running binary is unaffected), running under `/etc/init.d/garuda-perception` on the board (pid
8208 at measurement time, `md5sum /opt/garuda/bin/garuda-perception` =
`48a86c417d9d68a0cb90885970b03823`). Detector: Hailo model-zoo `yolo26m` HEF for hailo15l,
`/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef`, md5 `3aef604ab89ddaf9ecb4cefa9c6ea8af`
(unchanged from the 2026-09-03 zoo-HEF benchmark entry in `bench/benchlog.md`). Post-process: our
own plugin `/opt/garuda/lib/libyolo26_post.so` (md5 `46eba70477207c7eb1d9ff3fdd61fe8d`), config
`/opt/garuda/yolo26_post.json` (`conf_thresh` 0.15, `iou_thresh` 0.5, `in_w`/`in_h` 640x640,
`mode: "letterbox"`, `tensor_prefix: "yolo26m/"`) — replaces the stock
`libyolo_hailortpp_post.so`/`yolov8.json` path used by M0/M1. Media-library profile: `Garuda`
(`/opt/garuda/medialib/garuda_medialib_config.json`), `sink0` 640x640 letterboxed
(`LETTERBOX_MIDDLE`), replacing M0/M1's 640x384 stretched `GarudaYolov8n` profile (that profile is
kept, selectable via the rollback config — `hosts/hailo15l/README.md` §8 "Rollback command").
Toolchain/SDK/HailoRT/image copied unchanged from the 2026-09-02 M0 sub-entry above (not
re-derived for this sub-entry, per instruction): SDK toolchain poky **4.0.23**; HailoRT/firmware
**5.3.0**, Device Architecture HAILO15L. First measured numbers from this build:
`bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: M2 yolo26m detector".

---

## 2026-07-29 — Trixie first boot + Hailo h10 stack (CURRENT baseline)

Supersedes the Bookworm entry below (re-flash same day; see docs/decisions.md). Access unchanged: `garuda@10.42.0.128` via PC `eno1` shared network.

- **Image**: `2026-06-18-raspios-trixie-arm64-lite.img.xz` (raspios_lite_arm64 mainline), sha256 verified on PC before flash.
- **uname -a**: `Linux raspberrypi 6.18.34+rpt-rpi-2712 #1 SMP PREEMPT Debian 1:6.18.34-1+rpt1 (2026-06-09) aarch64 GNU/Linux`
- **OS**: Debian GNU/Linux 13 (trixie), 64-bit Lite
- **Python**: 3.13.5
- **Hailo packages** (all from archive.raspberrypi.com trixie/main):
  - `hailo-h10-all` 5.1.1, `h10-hailort` 5.1.1, `h10-hailort-pcie-driver` 5.1.1, `python3-h10-hailort` 5.1.1-1
  - `hailo-tappas-core` 5.1.0, `python3-hailo-tappas` 5.1.0, `hailo-models` 1.0.0-2, `rpicam-apps-hailo-postprocess` 1.12.0-1
  - kernel module `hailo1x_pci` loaded without reboot
- **hailo-gen-ai-model-zoo** 5.1.1 (deb from dev-public.hailo.ai, not apt; provides `hailo-ollama`; installed same day for P1 LLM item; Hailo's own licence — bench tool only, never linked into services)
- **linuxptp** 4.2-1+b1 (Pi; GPLv2 — external daemon only per licence policy, never linked). PC side: linuxptp 4.0-1ubuntu1.1
- **docker.io** 26.1.5+dfsg1 (Pi, Debian trixie repo, Apache-2.0; installed 2026-07-30, daemon enabled, `garuda` in docker group)
- **garuda/ros-jazzy** image (sha256:a132a6c1f783…, supersedes e24d6100) from `hosts/pi5/Dockerfile.ros-jazzy`: ros:jazzy-ros-base + rmw-cyclonedds-cpp + demo-nodes-cpp + **px4_msgs @ c0f921bce0d76f83ca6d3ccd438adbee00a09f3a** (BSD-3) + **Micro-XRCE-DDS-Agent @ 155cfaaf8b7abac2e85d4a62d3649b09ace0be55** (Apache-2.0), `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` — no GPLv3
- **PX4-Autopilot** (PC, SITL only): shallow clone @ 47ce421 ("fix(simulator_sih): restore xvert front transition (#28090)"), built `px4_sitl` with venv python deps; BSD-3. Runs SIH quad (`sihsim_quadx`), uXRCE client → 10.42.0.128:8888 via `PX4_PARAM_UXRCE_DDS_AG_IP=170524800`
- **Basalt** (Pi, source build 2026-07-30): mateosss fork @ df6e970c, GCC 14.2.0, release + cortex-a76 tuning, `-j2`; deps via fork's apt list (tbb/glew/boost/fmt/yaml-cpp/sqlite3 dev pkgs). BSD-3. Binaries in `/home/garuda/basalt/build/`
- **`hailortcli fw-control identify`**: Control Protocol 2, **Firmware 5.1.1 (release,app), Device Architecture HAILO10H** — PASS
- **vcgencmd get_throttled**: `0x0` (idle; power source not yet verified as 5 V/5 A — re-check under load)
- **ethtool -T eth0**: hardware-transmit/receive, hardware-raw-clock, provider qualifier "Precise (IEEE 1588 quality)", TX modes off/on/**onestep-sync**
- **apt state**: 59 packages upgradable at install time — deliberately NOT upgraded (CLAUDE.md rule 11)
- **sudo**: Trixie no longer grants first-user NOPASSWD; restored via `/etc/sudoers.d/010-garuda-nopasswd`
- **2026-07-30 addendum**: `python3-opencv` 4.10.0+dfsg-5 arm64 (already present via tappas/rpicam-apps-opencv-postprocess deps; now also declared explicitly in `hosts/pi5/install.sh`'s apt list) — `dpkg -l python3-opencv` on the Pi. `garuda-portal.service` + `garuda-configd.service` deployed to `/opt/garuda/` and `systemctl enable --now`'d (both `active`, `enabled`); transient bench unit `garuda-cam-portal` stopped/disabled, portal now owns `:8080`.

---

## 2026-07-29 — first boot after imaging (baseline)

Access: PC `eno1` shared network (NetworkManager profile `pi-share`), Pi at 10.42.0.128, user `garuda`.

- **Image**: `2026-06-18-raspios-bookworm-arm64-lite.img.xz` (raspios_oldstable channel — mainline moved to Trixie 2025-10; Bookworm is oldstable now), sha256 `df4c6fb0…f8f` verified on PC before flash.
- **Model**: Raspberry Pi 5 Model B Rev 1.1
- **uname -a**: `Linux raspberrypi 6.12.93+rpt-rpi-2712 #1 SMP PREEMPT Debian 1:6.12.93-1+rpt1 (2026-06-12) aarch64 GNU/Linux`
- **OS**: Debian GNU/Linux 12 (bookworm), 64-bit Lite
- **vcgencmd get_throttled**: `0x0` (idle, immediately after first boot — under-load check still TBD-bench)
- **lspci**:
  - `0001:01:00.0 Co-processor: Hailo Technologies Ltd. Device 45c4 (rev 01)` — Hailo module enumerates; identity via `hailortcli` pending driver install
  - `0002:01:00.0 Ethernet controller: Raspberry Pi Ltd RP1 PCIe 2.0 South Bridge`
- **Storage**: rootfs `/dev/mmcblk0p2` 235G, 2.0G used after first boot
- **RAM**: 7.9 Gi total
- **Hailo packages**: not yet installed
- **ethtool**: not installed yet (`ethtool -T eth0` pending — needed before PTP work)
- **Power**: source at first boot not yet the verified 5 V/5 A supply — verify before any benchmark and re-check `get_throttled` after load

## 2026-09-10 — Fresh Hailo-15L tracking bench

- Source branch feat/hailo15l-fresh-tracking, base9582f1d; new service services/garuda-tracking.
- Board HAILO15L, FW5.3.0, kernel5.15.32, stock VPSP1.12.0, IMX678.
- SDK /media/bhanu1234/Development/hailo15/sdk, GCC11.5 AArch64; host GCC13.3, CMake3.28.3, Python3.12.3.
- HEFs: cached Hailo-15L5.3.0 NV12 YOLO11s/11m/8m; hashes:
  - yolov11s: 24a050fb0fa4c8cba12489d2275c784b2298be3c7632a96496116b185ff31296.
  - yolov11m: 65d875e84dc4ad7c18789724c6cbef534c3cf712c7d578a624e2a71d2587ec20.
  - yolov8m: fe7a956375a1667e3d2fac58f546814453018ae4d9ad5fe33560f11d2117c947.
- Person profile YOLO11s stretch640; phone trial YOLOv8m letterbox640;20fps requested, independent1280x720 JPEG10fps.
- Deployment /opt/garuda-fresh, ports8981/8982/8099; boot configuration unmodified.
- See same-date benchlog and bench/results/2026-09-10-fresh-tracking/model-comparison.json for measurements and caveats.

- Same-session correction: requested-profile initialization replaces switching from the default; effective geometry and actual NV12 padding now checked. Earlier live letterbox trials retained stretch and are explicitly invalidated for geometry/behavior.
- PC reference: ONNX Runtime1.29.0, official Hailo model-zoo yolov8m ONNX; SHA256 28012ea38de2cc22fc8230e6aab3d284514af452a655a7ad3f0de2fbc7a36cb0.

### Fresh tracking phone confirmation and guarded diagnostics — 2026-09-10

Owner confirms outside-body phone retention after geometry fix. Restored guarded binary SHA256
`9dbcb7ef3506aa4266beb40a9efee93fd4b27585c4d9662ec30276b9b93517c8`, PID732 at measurement.
YOLOv8m HEF unchanged; factory IQ and boot service unchanged. Profiles explicitly preserve motion
std.4; automatic JSONL recording now off. Diagnostic storage/memory budgets enforced. Recovered
from observed MMC/file-fault stall via completed sync/remount then reboot; underlying storage
cause unresolved. See latest benchlog and bench/results/2026-09-10-fresh-tracking artifacts.

### 2026-09-10 — optional fresh person ReID bench

Same Hailo-15L SBC / IMX678 / VPSP1.12.0 image as the earlier fresh-tracking snapshot;
`hailortcli --version` again reports5.3.0. No firmware, driver, boot or IQ update.
OSNet_x1_0 model-zoo5.3.0 HEF SHA-256
`49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7` (3,244,032bytes).
Verified final40s bench executable SHA-256
`58201d5b3ea6d3710aba24942ef7f57c0451c218e4e947938892111c0ed2f39d`.
GCC SDK11.5 cross-build; native13.3 tests + ASan/UBSan. Model is bench-only, not-product-cleared;
source MIT per pinned Hailo model metadata, weight/dataset product clearance pending.
Baseline executable restored afterward: `9dbcb7ef3506aa4266beb40a9efee93fd4b27585c4d9662ec30276b9b93517c8`.

### 2026-09-10 — fresh camera-motion experiment

Same factory board/kernel/IMX678 stack; no image, driver, IQ or library installation.
Native OpenCV 4.6.0; SDK and factory runtime OpenCV 4.5.5, required modules core,
imgproc, features2d, calib3d (factory transitive flann). Upstream licence Apache-2.0.
SDK GCC 11.5 cross-build. Optional candidate binary SHA-256
`ffdbe0c5e223b6816f0013c484e4a7394ad2994278db2792689680d5efaaf87c`;
ARM probe `5f588df0796cfa69cd3965038e878b7add5c7c3c234fb0f3dcd83bb348f8282c`.
Restored normal phone binary SHA-256
`a98d4671efe5d32a93e4d246ae7cca5a725a9fad5d6fd3530fa1690146971f0f`.
Machine-readable parameters, sample clock domains and raw-source hashes live in
`bench/results/2026-09-10-fresh-tracking/camera-motion/`.

### 2026-09-10 — offline target-evaluation harness

Python standard library only; no dependency or board changes. The native C++ replay
binary used for exact-stream and synthetic integration checks has SHA-256
`16f0058169f8ab16ffba48cffbe0341a501533c0e32abe0d027661e3836477da`.
Interpreter version and source recording identifiers are saved in
`bench/results/2026-09-10-fresh-tracking/target-evaluation/verification.json`.

### 2026-09-10 — paired exact-input capture

Same Hailo-15L SBC, IMX678, factory VPSP 1.12.0 / HailoRT 5.3.0 and SDK GCC 11.5.
Existing sink0 640×640 letterbox and sink1 1280×720 full-FOV streams remain configured
at 20 fps; ISP-processed NV12 from both is retained before JPEG. Ethernet speed readback
1000 Mb/s. No library, model, camera profile file, driver or boot setting changed.
Candidate binary SHA-256
`f2d7e4d3c5135f3d9b4e7f12541fa5d1c35f510bbfb3695f6df641a65203a2e0`.
Restored phone baseline SHA-256
`a98d4671efe5d32a93e4d246ae7cca5a725a9fad5d6fd3530fa1690146971f0f`.
Source clock/process identity and both image hashes are in the paired-input-stream
evidence metadata; timestamps use the existing monotonic clock domain.

### 2026-09-13 — independent follow-handoff audit

Audited source: `237ae7bae4bd9755ad095ed041bf10ab00d9dc9c`, worktree
`.worktrees/hailo15l-fresh-tracking`, clean before audit documentation.
Host: x86_64 Linux `7.0.0-31-generic`, Python 3.12.3, CMake 3.28.3,
native GNU C++ 13.3.0. Native build: Release, GARUDA_TRACKING_OPENCV=OFF.
Build/probe directory:
`/media/bhanu1234/Development/hailo-export/scratch-independent-audit-20260913.ypRHV2`.
Fresh native replay SHA256:
`2d97e744b3bd7aa7f9be5d692a5b65960d171967c9a52597c59f300bef94d61a`.

Board readback: Hailo-15L, aarch64 Linux
`5.15.32-yocto-standard-g1de0438be5ae`, build Jun 18 2026;
existing VPSP 1.12.0 / HailoRT 5.3.0 baseline (not reinstalled).
Running PID 20153 executable, installed executable and host deployment
executable SHA256 all:
`3c99fbc963e4efbcfb43c7a92207d96e16aab0ee8d7415c08e0f2460653f9e02`.
Active profile: `/opt/garuda-fresh/current.json`, follow configuration.
Stream config: sink0 640x640 letterbox, sink1 1280x720, configured 20 fps each.
Controlled YOLO11s HEF SHA256:
`aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58`.
OSNet HEF SHA256:
`49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7`.
Observed source clock domain:
`linux.monotonic:0b4fda88-369b-493c-a6b4-da149b3c1294`;
stream ID `1642d6fb-39bc-4442-b4b5-5dedc2a28386`.
No ARM rebuild, board deployment, model inference replay or vehicle commands
were performed during this audit. See the corresponding benchlog entry.

## 2026-09-13 — follow fix deployment and SIL (after independent audit)

Worktree `feat/hailo15l-fresh-tracking`, audit commit `85612ba`, implementation
following it. Host x86_64 Ubuntu, Linux 7.0.0-31-generic; Python 3.12.3;
existing pymavlink 2.4.49 (bench dependency, no new package installed).
PX4 checkout `47ce421a88ca870eb8d55eccac5f80fc9b368948`, `px4_sitl_default`,
headless `sihsim_quadx`, owned child process, explicit loopback MAVLink only.
Board/SDK remain VPSP 1.12.0 / HailoRT 5.3.0, no OS/driver/model upgrade.
Build output `/media/bhanu1234/Development/hailo-export/follow-fixes-20260913`.

Final live binary SHA256:
`e9d1aabb7607167d19a4396d1c8c266b0cde03ae98332a9f96629077e8f4cf4c`.
The first selected-watch / board-SIL candidate was
`f2920083861458b5cf81b5a181d0d8afc04d8d54dcd682cdee2ef82abeba10fc`;
the final build suppresses unnecessary corner refresh for large valid targets.
Active follow profile SHA256:
`ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
Causal ARM replay SHA256:
`5b5caad507194b5395acbdd7d9e65281009305272a47c492abdb6022be8a01ce`.
Native replay final SHA256:
`ccef4b922f9385d24647070adf86db3338d7e474ccbc8fadb67ecc2ebd1458e4`.
Per-trial `run.json` pins the causal binary/profile used before each iteration;
`versions.json` pins final artifacts, not retroactive hashes of earlier trials.
Full SIL suite preceded the additional owned-parent/PX4-peer checks; the subsequent
board transport-in-loop run exercises those final bridge checks. Native tracker's
synthetic SIL default identity policy is unchanged by profile-specific gap tuning.

YOLO11s and OSNet retain the hashes in the audit entry. Camera still supplies
640x640 letterbox and exact-paired 1280x720 streams at configured 20 fps.
Follow uses managed paired-source inference and high-resolution identity crops.
Verified PC rollback archive:
`/media/bhanu1234/Development/hailo-export/follow-fixes-20260913/rollback/garuda-fresh-before.tar`,
SHA256 `171d674b133bed14b61f85d7bc85dde0156cc68d19a7f3b002d978aaeb4c2132`.
Original binary hash verified inside its 45-entry archive. No backup removed.

## 2026-09-13 — rendered-camera visual SIL

Worktree `feat/hailo15l-fresh-tracking`, based on `0e17b3f`; each recorded run's
`versions.json` pins actual source hashes (work was still uncommitted), board
binary/profile/HEFs, native format-adapter library, PX4 commit and Gazebo version.
Artifacts: `bench/results/2026-09-13-gazebo-visual` and full working directory
`/media/bhanu1234/Development/hailo-export/gazebo-follow-20260913`.

PC: Python 3.12.3, NumPy 2.3.3, Pillow 10.2.0, GNU C++ 13.3.0;
Gazebo Harmonic / gz-sim 8.10.0, gz-transport 13.5.0 Python bindings, msgs10;
NVIDIA RTX3060 Laptop 6 GB, driver 580.173.02. eno1 link 1000 Mb/s full duplex.
Existing PX4 `47ce421a88ca870eb8d55eccac5f80fc9b368948`, custom world with
stock X500 base, attached 1280×720 RGBD sensor at configured 20 Hz, separate
800×450 overview at configured 8 Hz. No system package/driver upgrade.

Mingfei actor v1, CC BY 4.0, external Gazebo Fuel cache; walk.dae SHA256
`49af0df3a319d1cb8ca2cebf02dbd00f625e5d5bec820bc5e109925b18b65c6e`.
Native RGB→NV12 adapter is project-owned C++ compiled on the PC, not a new
on-board runtime library. SSH final setting `aes128-gcm@openssh.com`.

Final `/opt/garuda-sim/garuda-causal-stream` SHA256
`dfc0e6208c0d1b34a1a403f7ef7e95e950689596a6f65ce97aafc4e03f7f5a74`.
Earlier reporting version: `a558ca6cea2d8de802b10a250678bd4835543290896888430f33833277efee19`.
Simulation profile equals desk follow profile SHA256
`ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
YOLO11s and OSNet hashes and HailoRT/VPSP remain unchanged from above.
Desk executable stays `e9d1aabb7607167d19a4396d1c8c266b0cde03ae98332a9f96629077e8f4cf4c`;
verified again after automatic restoration (PID 26835, advancing IMX678 stream).

New post-fix rollback archive (46 entries, embedded binary hash checked):
`/media/bhanu1234/Development/hailo-export/gazebo-follow-20260913/rollback/garuda-fresh-before-sim.tar`,
SHA256 `1571b7172fa7271fac87f38fb3ceccdb57548eb62b4335d77611b0e72ae320f6`.
Both prior rollback archives and earlier failed/debug simulation runs retained.

## 2026-09-13 — isolated 15L ROS/MAVROS campaign

Worktree `feat/hailo15l-fresh-tracking`, based on `2915825`. Per-run snapshots
hash actual source/deployed node files while development was uncommitted.
`axis-normal` and `axis-request-loss` predate the snapshot helper; do not claim
later source inventories as contemporaneous evidence for them. `axis-ros-loss`
and final rendered/replay runs have ROS snapshots. See campaign handoff/benchlog.

Board retains VPSP1.12.0, HailoRT5.3.0, Linux5.15.32 / AArch64, stock glibc2.35.
New isolated `/opt/garuda-ros-jazzy`: Ubuntu Base24.04.4 ARM64, Jazzy ROS base,
MAVROS `2.15.1-1noble.20260903.001241`, rclpy
`7.1.12-1noble.20260902.143245`, rmw_cyclonedds_cpp
`2.2.4-1noble.20260902.140937`, CycloneDDS0.10.5. Complete `dpkg-query -W`,
ROS signing-key checksum and node checksums in `ros-versions.json` (or axis
`versions.json`). Installer uses signed repository metadata but is not an
offline pinned image build. No host apt, Docker, system library or driver install.

Ubuntu archive SHA256:
`04207713ece899c3740823d33690441ad3a7f0ded1101aca744e2b0f37ac7ff2`.
GeographicLib EGM96-5 archive SHA256:
`c46224f8f723dc915d97179f4e1580a98d6c742fe2b82cd8fef0ecaaad13e614`.
The board date was corrected from 2018 using PC UTC for repository validity;
RTC/NTP/boot config unchanged. This is not precision clock synchronization.

New separate `/opt/garuda-sim/garuda-causal-stream-diagnostics`:
`9e34ea59774d9b51fdbc1c616999ab4fe4329e83d223aef02119caa938954ebe`.
Separate fullview bench profile `/opt/garuda-sim/profile-fullview.json`:
`6da201c4320bb16b5cc60ee1854dc014efe1d44a9f1bb6bc91568e4b41a4da0d`.
Desk executable remains `e9d1aabb7607167d19a4396d1c8c266b0cde03ae98332a9f96629077e8f4cf4c`;
desk/current and original simulation profile remain
`ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
No physical sensor-register readback claim after desk restarts.

YOLO11s HEF:
`aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58`.
OSNet HEF:
`49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7`.
Original ONNX for exact parity:
`0a44c5050d77a27abb971979e8399ab6084db18b0ffc7781e312171543efef8e`.
Nine exact retained DSP input crops:
`3f7220d44705792aa088accdfb6de4d551ab3f8325348d92f80c6d6bdca7b2dc`.
Fresh parity probe:
`2e0ecb2d38bb15c4ba14f5f2d6dd914dc3baa777a6b81c977d283b65fd9f4ed0`.

PC remains Python3.12 / Ubuntu24.04 / Linux7.0, Gazebo8.10.0,
PX4 `47ce421a88ca870eb8d55eccac5f80fc9b368948`. Nominal commands traverse
15L ROS/MAVROS -> owned SSH loopback relay -> owned PX4 child. Domain73,
CycloneDDS, local discovery. No physical FC endpoint or serial binding.

## 2026-09-13 — native-camera observer and ISP audit

Same VPSP1.12.0 / HailoRT5.3.0 / Linux5.15.32 aarch64 and separate ROS Jazzy
userspace. No package, driver, HEF or OS upgrade; existing rclpy/std_msgs/
CycloneDDS and Python standard library reused. Local-only domain73.
Boot ID: `0b4fda88-369b-493c-a6b4-da149b3c1294`.

Installed `/usr/lib/medialib/denoise_config/pre_isp_hdm_678_h15l.hef` SHA256:
`4a19613b4109b946a972aa1fc1f9bec5545e325fb6b594c6a4b243c5f7df36d4`.
Active/vendor configuration hashes: `bench/results/2026-09-13-camera-isp/installed-audit.json`.

Staged `/opt/garuda-ros-jazzy/opt/garuda/` files, on-board SHA256 verified:

- native_camera.py: `da0935a3a6debeb23f33170575e679e05fa55e3c40237041fc443f7ca1c4460e`
- native_camera_observe.py: `99d2c02fca718461aa1a3c02859b33b378c0558ddf2a5a13990203f0f91ac579`
- run_camera_observe.sh: `614370eb884d93c989c2d8c04b379d0cd38ec539625ecb70cc5f3b6d82a866d1`

Desk current config remains `ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`;
desk executable remains `e9d1aabb7607167d19a4396d1c8c266b0cde03ae98332a9f96629077e8f4cf4c`.
Observer ran for bounded durations and exited; not an auto-start service.

## 2026-09-13 — joined grand-demo and dataset campaign

Worktree `feat/hailo15l-fresh-tracking`, based on `e10bb403d070873c4382ff1fc96aa38f7f248f62`;
per-run `versions.json` / `ros-versions.json` hash uncommitted tested sources.
Evidence: `bench/results/2026-09-13-grand-demo/`. No new dependency, kernel,
driver, OS, HEF or native desk-camera executable/config change. Same Gazebo8.10.0,
PX4 `47ce421a88ca870eb8d55eccac5f80fc9b368948`, board VPSP1.12.0/HailoRT5.3.0,
existing isolated ROS Jazzy/MAVROS2.15.1 userspace. Simulator endpoints only.

Final deployed ROS files, readback equal to local source:

- native_camera.py: `29747ecd46f85e576f1d7e2df3ab0b19c26286db309f037d1b48f86ea2b852fc`
- mavros_node.py: `37dcc7995bd983a10d1180d1035af4cc01bd44a69e2454cc2e2efd10c8b8d374`
- run_board.sh: `cf314b6229db4c5a5c4342faa1b65ec67c5aa8f2fdeeb5978cce704bd63dd12e`

Desk native unchanged `e9d1aabb7607167d19a4396d1c8c266b0cde03ae98332a9f96629077e8f4cf4c`;
current.json unchanged `ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
Live native producer restarted only while borrowing NPU for recorded/rendered
tests; existing start-current/start-follow restoration used, selection cleared.
Sensor-register/AE equivalence after restarts is not independently certified.

SOT replay binary `9e34ea59774d9b51fdbc1c616999ab4fe4329e83d223aef02119caa938954ebe`;
DET probe `7b91c98fdafcfe1d016eb4fd7b63ae2f68173d46952e57f1af446314550ca6cf`;
both use controlled YOLO11s HEF `aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58`.
64-image720p source NV12 `3f5db9f99b85d93ef5baf8a37ae2dc88feabcf9b167b7c42dd356debd7609778`;
original-pixel padded source `9b23065fdf504d4ce19c1367301897609992eb2350a080eff89535adf82da78d`.
Preparation includes per-JPEG hashes, complete annotations and transform metadata.
Final scoring-file hashes in dataset-report.json; archival hashes in manifests.
Dataset images remain external, research-use/bench-only; no training or new data
download. Existing DFC venv ONNX Runtime1.18.0 reused for conversion unittests.

Final lifecycle correction: earlier `restore_returncode=0` did not verify a
running native child; see benchlog/evidence README. Native binary/config stayed
unchanged, but camera restoration failed after RAM-backed staging accumulated.
The exact11 campaign staging directories moved to persistent
`/opt/garuda-sim/replay-staging-20260913/` (recoverable). New local lifecycle helper
checks advancing API snapshots before success; future causal staging is on
persistent disk. These host-script changes do not replace the native executable.

## 2026-09-13 — movement-fix deployment, Hailo-15L desk board

Actual build/run snapshots: `results/2026-09-13-movement-fix/gazebo-first/` and
`gazebo-final/` (`versions.json`, `ros-versions.json`, source hashes and compressed
raw logs with archive manifests). Same stock VPSP1.12.0/HailoRT5.3.0 board and
isolated ROS Jazzy/MAVROS2.15.1 userspace; no package, model, ISP or OS changes.
PC PX4 commit47ce421a88ca870eb8d55eccac5f80fc9b368948, Gazebo8.10.0.
Build: `GARUDA_FRESH_BUILD=/media/bhanu1234/Development/hailo-export/movement-fix-20260913/build bash hosts/hailo15l/build_fresh_tracking.sh`.
Source parentf8ea55e plus committed movement-fix changes; run snapshots record
the dirty source hashes. Final relay indentation-only cleanup followed the second
run's process start; functional code was unchanged. SHA256 observed after staging:

- Native `/opt/garuda-fresh/garuda-fresh-tracking`: `3851ef019716dfa7f5ed36f219ea557cfb81cbd0820dd9e021f1431c5514a2d3`.
- Causal `/opt/garuda-sim/garuda-causal-stream-diagnostics` and `garuda-causal-movement-fix`: `ae28949f61da8498d35738a2ef3002f1b71d122709a76de84f641808f91bba9d`.
- Unchanged `current.json`: `ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
- Board `mavros_node.py`: `6b57e54db1bd9f329516483ba4d40671daf2b2ce5e9337c85f2b497ea8150cda`.
- Board `mavros_contract.py`: `5367ab6e1cfc05e13d54322784e710783a7fe13d1ff94bb9872bdfe25f9e71c4`.

Old native e9d1aabb… preserved in `/opt/garuda-fresh/backups/movement-fix-20260913/`
with profile/log. Old causal9e34ea59… preserved as
`/opt/garuda-sim/garuda-causal-stream-diagnostics.before-movement-fix-20260913`.
Both trial desk restorations passed advancing-frame readiness. Final physical
stream `d4b21b39-d459-4dab-83fb-1e5d99dccc6f`; boot clock unchanged
`linux.monotonic:0b4fda88-369b-493c-a6b4-da149b3c1294`.

## 2026-09-13 — dataset rerun and intuitive local console

Source parent69d09c9; native artifacts unchanged from movement-fix deployment.
Frozen replay uses causal SHA256
ae28949f61da8498d35738a2ef3002f1b71d122709a76de84f641808f91bba9d.
Detector probe /tmp/garuda-reference-build/hailo-preprocess-probe:
7b91c98fdafcfe1d016eb4fd7b63ae2f68173d46952e57f1af446314550ca6cf.
Controlled YOLO11s HEF:
aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58.
Fullview profile:
6da201c4320bb16b5cc60ee1854dc014efe1d44a9f1bb6bc91568e4b41a4da0d.
All original/current trials, prepared manifests and source hashes compared.

Actual board snapshot: results/2026-09-13-dataset-rerun/board-final.txt.
Linux5.15.32-yocto-standard-g1de0438be5ae, stock June18 build, aarch64.
Native3851ef019716dfa7f5ed36f219ea557cfb81cbd0820dd9e021f1431c5514a2d3;
current.json ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d.
No OS, package, firmware, ISP or model changes. Actual ROS/MAVROS/PX4/Gazebo
versions and source hashes: replay-car/ros-versions.json and versions.json in
the same evidence directory. Final UI hashes: ui-source.sha256. Compact step
labels followed the recorded scenario; final served assets were syntax/HTTP
rechecked. New frontend remains local; no added packages or external assets.

Inputs: existing visdrone-sot-replay-20260912-roi, grand-demo-20260913-det-720-input
and grand-demo-20260913-det-native-input under hailo-export. New output root:
 /media/bhanu1234/Development/hailo-export/dataset-rerun-20260913.
No dataset pixels committed. Temporary DET staging removed by its existing
harness; SOT persistent staging retained. Both avoid altering the live profile.
