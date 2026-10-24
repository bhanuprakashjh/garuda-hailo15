# Garuda Hailo-15L Perception Node — User Guide

This guide takes someone with the hardware on their desk, and no prior project
context, from first power-on to a running follow-me tracking session and the
simulation console. Commands are written for a Linux PC cabled directly to the
board.

## Table of contents

1. [Overview](#1-overview)
2. [Hardware & first contact](#2-hardware--first-contact)
3. [PC-side toolchain](#3-pc-side-toolchain)
4. [Smoke test](#4-smoke-test)
5. [Building & deploying the fresh-tracking node](#5-building--deploying-the-fresh-tracking-node)
6. [Running follow-me](#6-running-follow-me)
7. [The follow console & simulator](#7-the-follow-console--simulator)
8. [Benchmarks & evidence](#8-benchmarks--evidence)
9. [Troubleshooting](#9-troubleshooting)
10. [Licence](#10-licence)

---

## 1. Overview

### What this is

The **Garuda Hailo-15L perception node** (internally "fresh tracking") is a
civilian follow-me / camera-tracking stack for people and vehicles, running
entirely on a Hailo-15L SBC with an IMX678 camera:

```
IMX678 (3840x2160) -> ISP -> DSP resize/letterbox
    -> YOLO HEF detector on the NPU (full view, tiles, and target-ROI crops)
    -> OSNet person re-identification embeddings (NPU)
    -> fresh tracker: confirmation, coast, identity owner, lock policy
    -> JSON snapshot + MJPEG feed -> browser viewer (port 8099)
    -> optional ROS 2 / MAVROS path to an OWNED PX4 SITL (simulation only)
```

The main pieces:

- **`hosts/hailo15l/fresh_node.cpp`** — the board executable
  (`garuda-fresh-tracking`). The only file that knows the Hailo SDK: media
  library frontend, AI stage, DSP crop/resize (`dsp_crop.cpp`,
  `region_detector.cpp`), person/image embedding stages
  (`person_embedding.hpp`, `image_embedding.cpp`).
- **`services/garuda-tracking/`** — the host-independent C++17 tracking core:
  track confirmation and coasting, the **identity owner** (learned person
  identity via OSNet descriptors), the lock/selection policy, and
  `fresh_shim.py`, the on-board HTTP viewer/shim.
- **`services/garuda-follow/`** — the follow controller and perception
  authority used by the simulation console (freshness gating, intent TTL,
  bounded commands).
- **`bench/`** — harnesses (`fresh_*.py`), the follow simulator and console
  (`bench/sim/`), replay and scoring tools (`bench/hailo_reference/`), and the
  measurement record (`benchlog.md`, `versions.md`, `evidence/`).

Two **tracking profiles** ship for the live camera: a **desk profile**
(validated at close range with the stock-domain models) and an **aerial
profile** (fine-tuned detector + drone-view re-identification descriptor,
validated offline on drone footage). See [chapter 6](#6-running-follow-me).

### Safety and scope

- **No flight hardware.** No flight controller is connected and nothing in this
  repository arms motors. All MAVLink-capable paths require `GARUDA_SIM=1` and
  talk only to PX4 SITL processes this repo itself launches on loopback.
- **Current scope is tracking and short recording.** Autonomous following on a
  real vehicle, FC integration, and flight qualification are explicitly out of
  scope and not established by anything here.
- **Claims discipline.** Every number quoted anywhere in this project comes
  from `bench/benchlog.md`, measured on this hardware, with an environment
  snapshot in `bench/versions.md`. Unmeasured = `TBD-bench`.

### Relation to the product-tier Hailo-15H

The product target of the wider Garuda SDK is a **Hailo-15H SoM**. The 15L SBC
on this bench shares the SoC family, SDK, BSP, ISP path and HailoRT 5.3.0 line,
so almost everything developed here ports directly.

> **Hard caveat — do not skip this.**
> The Hailo-15L is Hailo's lowest-throughput 15-family variant. It is a fair
> proxy for the Hailo-15H **everywhere except NPU headroom**. Never quote a
> frame rate, inference latency, or throughput figure measured on this 15L as
> a Hailo-15H number. Also note (measured 2026-09-02, `docs/decisions.md`):
> this SBC's Ethernet MAC has **software timestamping only** — it cannot be a
> hardware PTP node; re-check that capability on the 15H SoM rather than
> assuming either way.

---

## 2. Hardware & first contact

### 2.1 Identify the board

The board is a **Hailo-15L SBC rev 2.x** — a development single-board computer,
**not** an EVB and **not** a Hailo-15H. Verify what you have:

- Silkscreen: `PCB00150 Rev2.0` (kit label `REV2.21`).
- USB console FTDI descriptor: `SBC_H15L`.
- Device tree model: `Hailo - Hailo15l SBC VPU Development Board`.
- `hailortcli fw-control identify` on the board reports
  `Device Architecture: HAILO15L`.

Fixed hardware: 4× Cortex-A53 @ 1.1 GHz, 2 GB RAM (`free -m` shows ~1913 MB,
of which ~1.25 GB is CMA — budget roughly 600 MB for user space), 7.3 GB eMMC
(`mmcblk1`: 64 MB boot partition + ~7.2 GB rootfs), Sony IMX678 camera at
3840×2160, 1 GbE, on-board FTDI console, rear-side PCIe M.2 slot and microSD
slot (the SD slot is on the **rear** of the board and is not used for boot
here).

### 2.2 DIP switches

**DIP SW1: both switches ON** — this is the factory setting and means normal
eMMC boot. Both OFF produces a completely silent non-boot (no console output at
all), which is easy to mistake for a dead board.

### 2.3 Serial console

The console comes out of the on-board FTDI FT230X on the micro-USB connector
(J1). On the PC, find it by ID rather than guessing the ttyUSB index:
`/dev/serial/by-id/usb-FTDI_SBC_H15L_*` (the board-side Linux console is
ttyS1).

Settings: **115200 8N1, with DTR and RTS asserted.** With DTR/RTS dropped the
link returns garbled text. For example:

```bash
python3 -m serial.tools.miniterm /dev/serial/by-id/usb-FTDI_SBC_H15L_*-if00-port0 115200 --dtr 1 --rts 1
```

Console expectations that look like failures but are not:

- The **boot ROM never transmits** on non-secure parts — early-boot silence is
  not diagnostic of anything.
- Once booted, **getty only re-prints the login prompt on a keypress** — press
  Enter before concluding the board is dead.
- The FTDI bridge is **board-powered**: it re-enumerates on the PC after every
  power-cycle, so reopen your terminal program.
- Check that **both** power LEDs (PWR-IN and the power button's LED) are lit
  before assuming a boot failure; some "power cycles" do not actually cut the
  12 V input.

Login is `root` with the factory image's default credentials (see Hailo's SBC
quick start guide); install an SSH key immediately and treat the board as a
bench device on a private link.

### 2.4 Ethernet link

The factory image configures the board's `eth0` statically as **10.0.0.1/24**
(`/etc/network/interfaces`). Cable it directly to a wired port on the PC and
give that port a static address:

```bash
# One-time: create a NetworkManager profile for the board link
nmcli con add type ethernet ifname eno1 con-name h15-link \
  ipv4.method manual ipv4.addresses 10.0.0.2/24

# Every session (or set autoconnect): point the port at the board
nmcli con up h15-link

ping -c3 10.0.0.1
ssh root@10.0.0.1
```

Substitute your interface name for `eno1`. If the same wired port is shared
with other devices (e.g. another bench profile), the profiles are mutually
exclusive — bringing one up takes the port from the other; `nmcli con up
h15-link` re-points it at the board (see [Troubleshooting](#9-troubleshooting)).

After key-based SSH works, `ssh -o BatchMode=yes root@10.0.0.1` must succeed —
every script in this repo uses BatchMode and will not prompt for passwords.

### 2.5 Factory image — no re-flash needed

The eMMC ships with **VPSP 1.12.0** (`/etc/os-release` →
`VERSION=vpu-stability-v1.12.0`; poky 4.0.23 / kirkstone, kernel
`5.15.32-yocto-standard`). As of this snapshot that is the newest Vision
Processor SW Package, and Hailo's quick start guide says to skip programming at
1.12.0. **Do not re-flash.** Keep the VPSP's prebuilt boot chain and `.swu`
update image on the PC for recovery only (the QSG's swupdate flow: tftpd on the
PC at 10.0.0.2, `/etc/run_swupdate.sh -r <swu> -s 10.0.0.2` on the board).

Two things to know about the stock image:

- **No RTC/NTP** — the board boots believing it is 2018. Set the clock from
  the PC when date-sensitive operations matter (package signatures, log
  correlation): `ssh root@10.0.0.1 "date -s @$(date +%s)"`. Not persistent
  across reboots; that is expected.
- Some boards carry **leftover burn-in residue**: an `S99h15-record-service`
  init script that endlessly records ~55 MB H.264 clips onto the eMMC rootfs,
  and a `face_landmarks_app` demo that grabs the camera at boot and has been
  seen OOM-killing the ISP daemon. Check for and disable the recorder if
  present:

```bash
ssh root@10.0.0.1 'ls /etc/rc5.d/ | grep -i record; update-rc.d -f h15-record-service remove'
```

---

## 3. PC-side toolchain

All compilation — the ARM cross-build of the node **and** every HEF model —
happens on an x86 PC. The board never builds anything.

### 3.1 VPSP package

Download Hailo's **Vision Processor SW Package 1.12.0** for the hailo15l SBC
(`hailo_vision_processor_sw_package_1.12.0_hailo15l_sbc.tar.gz`, ~3.9 GB) and
extract it somewhere permanent, e.g. `~/hailo15/vpsp-1.12.0/`. It contains the
prebuilt boot chain, the `.swu` recovery image, the cross-SDK installer and the
`hailo15_board_tools` package.

### 3.2 Cross SDK

Install the poky cross toolchain once (~8 GB, no sudo needed):

```bash
sh vpsp-1.12.0/prebuilt/sbc/sdk/poky-glibc-x86_64-core-image-hailo-dev-armv8a-hailo15l-sbc-toolchain-4.0.23.sh \
   -y -d ~/hailo15/sdk
ls ~/hailo15/sdk/   # environment-setup-armv8a-poky-linux, sysroots/, version-...
```

Every cross build then starts with:

```bash
source ~/hailo15/sdk/environment-setup-armv8a-poky-linux
```

The repo's CMake toolchain hook (`hosts/hailo15l/cmake/hailo15l.cmake`) fails
fast if `OECORE_TARGET_SYSROOT` is unset, so a native build can never silently
masquerade as a cross build. Native x86 builds (unit tests) use plain `cmake`
with no SDK environment sourced.

The build/stage scripts find the SDK via `GARUDA_H15L_SDK` (their baked-in
default is the original bench's local path) — export it to your own install
path.

### 3.3 Board tools venv

For low-level board control (FTDI CBUS pins, UART boot recovery), create a
venv with the VPSP's `hailo15_board_tools` 1.12.0 (plus pyftdi/pyserial). This
is only needed for recovery scenarios, not day-to-day work.

### 3.4 Dataflow Compiler (DFC)

HEFs are compiled with **Hailo DFC 5.3.0** (from `hailo_ai_sw_suite_2026-04`),
targeting **`hailo15l`**:

- The DFC runs on x86 (GPU recommended for optimization levels above basic);
  **never on the board**.
- Keep the DFC, the board firmware and HailoRT on the **same 5.3.0 line** —
  version coupling across that boundary is the most common bring-up failure.
- Model fetch/build scripts and per-model cards live in `models/` (e.g.
  `fetch_yolov11s_h15l.sh`, `fetch_osnet_h15l.sh`). HEF binaries are
  git-ignored; scripts verify pinned checksums.
- The controlled YOLO11s rebuild recipe (full-range YUV conversion, NV12 input,
  1,024-image calibration, optimization level 2 — see
  `docs/2026-09-11-hailo15l-complete-summary.md`) is the reference for how this
  project builds a detector HEF from a model-zoo ONNX.

---

## 4. Smoke test

### 4.1 NPU identify

```bash
ssh root@10.0.0.1 'hailortcli fw-control identify'
```

Expected: device `[integrated]`, Control Protocol 2, **Firmware 5.3.0
(release, app), Device Architecture HAILO15L**. Anything else — wrong
architecture, version mismatch, or no response — stop and resolve before going
further (see [Troubleshooting](#9-troubleshooting)).

### 4.2 Stock camera pipeline

Before deploying anything of ours, prove the vendor camera path end to end:

```bash
ssh root@10.0.0.1
/etc/init.d/isp_media_server restart   # fresh ISP daemon (see note below)
setup_hailo_sensor.sh                  # picks imx678 + the 4K lens config
camera-viewer-server                   # vendor viewer
```

Then open **http://10.0.0.1/** (port 80) in a browser: the IMX678 should stream
at 30 fps. Two benign observations from the original bring-up: the viewer warns
that RAM < 3 GB makes its clip pipeline unsupported (true on a 2 GB 15L), and a
single `isp_mp_axi_bresp` error IRQ can appear at stream start without
repeating.

Why the `isp_media_server` restart first: on the stock image a boot race has
been observed where a boot-time demo app OOM-kills the ISP daemon ~15 s after
boot, after which every `create_pipeline` times out (−11) and
`camera-viewer-server` dies with "Device '/dev/video0' failed during
initialization". Restarting the ISP daemon clears it.

Only **one** camera/NPU pipeline can run at a time. Stop
`camera-viewer-server` before starting the Garuda node (the control scripts do
this for you).

---

## 5. Building & deploying the fresh-tracking node

### 5.1 Build

From the repository root on the PC:

```bash
bash hosts/hailo15l/build_fresh_tracking.sh
```

This script:

1. builds the tracking core natively and runs its CTest suite plus the
   `garuda-tracking`, `garuda-follow` and `garuda-bridge` Python test suites;
2. sources the cross SDK and builds the ARM targets: `garuda-fresh-tracking`
   (the node), `garuda-track-replay` (the exact-replay binary used by every
   offline harness), and the probe tools (`garuda-model-probe`,
   `garuda-embedding-probe`, `garuda-crop-probe`, `garuda-region-probe`,
   `garuda-causal-replay`).

Environment knobs:

| Variable | Default | Meaning |
|---|---|---|
| `GARUDA_H15L_SDK` | SDK install path | cross SDK location |
| `GARUDA_FRESH_BUILD` | `/tmp/garuda-fresh` | build output root (`native/`, `h15l/`) |
| `GARUDA_FRESH_OPENCV_MOTION` | `OFF` | optional OpenCV background-motion plugin |
| `GARUDA_FRESH_VISUAL_TARGET` | `OFF` | optional visual-target plugin |

### 5.2 Stage to the board

```bash
bash hosts/hailo15l/stage_fresh_tracking.sh
```

Staging copies the build, the shim/tuning UI, and all profile JSONs into
**`/opt/garuda-fresh/`** on the board, alongside the hash-verified models. It
**refuses to run while the fresh tracker is running** (stop it first) and it
never touches boot startup — the fresh node is a bench process you start
explicitly.

Every model is pinned by SHA-256; nothing is deployed by filename alone:

| Variable | Slot on the board | Notes |
|---|---|---|
| `GARUDA_FRESH_HEF` (+ `_SHA`) | `models/yolov11s_hailo15l_v5.3.0.hef` | default: the controlled COCO YOLO11s rebuild |
| (built-in) | `models/yolov8m_hailo15l_v5.3.0.hef` | phone-candidate detector |
| `GARUDA_FRESH_REID_HEF` | `models/osnet_x1_0_hailo15l_v5.3.0.hef` | zoo OSNet re-ID (desk profile) |
| `GARUDA_FRESH_ROI_HEF` | `models/yolov11m_hailo15l_v5.3.0.hef` | optional ROI-bench model |
| `GARUDA_FRESH_AERIAL_HEF` + `_SHA` | `models/yolov11s_aerial_hailo15l_v5.3.0.hef` | aerial (VisDrone fine-tuned) detector; `.sha256` sidecar written, checked at start |
| `GARUDA_FRESH_AERIAL_REID_HEF` + `_SHA` | `models/osnet_aerial_hailo15l_v5.3.0.hef` | drone-view OSNet fine-tune; sidecar-checked |

HEF files are not committed; fetch the zoo ones with the `models/fetch_*.sh`
scripts and build the fine-tuned ones on the PC (chapter 3.4).

### 5.3 Run / stop / status

`hosts/hailo15l/fresh_tracking_ctl.sh` is the explicit lifecycle tool (SSH into
the board under the hood; set `GARUDA_H15L_HOST` if not `root@10.0.0.1`):

```bash
bash hosts/hailo15l/fresh_tracking_ctl.sh start-follow   # desk follow profile
bash hosts/hailo15l/fresh_tracking_ctl.sh status
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
bash hosts/hailo15l/fresh_tracking_ctl.sh restore        # stop + restart the previous perception service
```

Start actions select a config, copy it to `/opt/garuda-fresh/current.json`, and
launch the node plus the shim. The main ones:

| Action | Config | Purpose |
|---|---|---|
| `start` | `perception.json` | YOLO11s, stretch geometry |
| `start-letterbox` | `perception-letterbox.json` | YOLO11s, letterbox comparison |
| `start-phone` | `perception-yolov8m-phone.json` | YOLOv8m phone candidate |
| `start-follow` | `perception-follow.json` | **desk follow profile** (ROI assist + OSNet identity) |
| `start-aerial` | `perception-aerial.json` | **aerial follow profile** (fine-tuned detector + drone-view re-ID; hash-checked slots) |
| `start-current` | `current.json` | restart whatever was last selected |
| `start-tiles`, `start-capture`, `start-paired-capture`, `start-person-reid`, `start-similarity`, `start-roi-assist`, `start-roi-shadow` | bench configs | measurement profiles |

Rules enforced by the script: one profile at a time (stop before switching);
model slots needed by the chosen profile must be staged and hash-verified or
the start refuses; after launch, `hosts/hailo15l/wait_fresh_camera.py` waits
for **advancing native camera snapshots** — a running PID alone is not
readiness. `stop` allows up to 10 s for the SIGTERM teardown of the media
pipeline and NPU.

### 5.4 Directory layout on the board

```
/opt/garuda-fresh/
├── garuda-fresh-tracking      # the node (ARM)
├── garuda-track-replay        # exact replay binary (used by harnesses)
├── current.json               # the active profile (copied by start-*)
├── perception*.json           # all staged profiles (from hosts/hailo15l/fresh/)
├── medialib.json, profile*.json, postprocess.json, application_settings*.json
├── fresh_shim.py              # HTTP viewer/shim (port 8099)
├── fresh_tuning.py / .html    # tuning UI
├── lib/                       # libturbojpeg from the SDK sysroot
├── models/                    # hash-pinned HEFs (+ .sha256 sidecars for candidates)
└── backups/                   # owner-made rollback copies

/tmp/garuda-fresh.log          # node log        /tmp/garuda-fresh.pid
/tmp/garuda-fresh-shim.log     # shim log        /tmp/garuda-fresh-shim.pid

/opt/garuda/                   # the EARLIER garuda-perception node (see below)
/opt/garuda-sim/               # demo-console board stream binary + sim profiles
```

Node ports: **8981** (feed), **8982** (command); the shim serves the browser
viewer and JSON API on **8099**.

### 5.5 The `garuda-perception` init script (the predecessor node)

`hosts/hailo15l/garuda-perception.init` + `hosts/hailo15l/deploy.sh` belong to
the **earlier** perception node (`services/garuda-perception`, installed under
`/opt/garuda`, boot-started as a SysV service at S99 with its own shim on port
8098). The fresh node deliberately does not install any boot service; its
`start-*` actions stop `/etc/init.d/garuda-perception` first, and
`fresh_tracking_ctl.sh restore` puts it back. Two useful properties of
`deploy.sh` if you use that older path: it is idempotent, and it sets the
board's clock from the PC on every deploy (the board has no RTC).

---

## 6. Running follow-me

### 6.1 Desk profile vs aerial profile

Both live profiles share the same pipeline shape (1280×720 working frame,
640×640 letterboxed detector input, single-view detection with periodic tiles
while searching, a DSP **target-ROI assist** crop around the locked target, and
OSNet person embeddings with a budget of 6 descriptors per frame). They differ
in models and identity rules:

| | Desk (`start-follow`) | Aerial (`start-aerial`) |
|---|---|---|
| Detector | Controlled COCO YOLO11s rebuild | YOLO11s fine-tuned on VisDrone (phone-preserving phase-2 fine-tune since 2026-09-18) |
| Re-ID descriptor | Zoo OSNet x1.0 (Market-1501 domain — the desk is its own domain) | OSNet x1.0 fine-tuned on drone-view crops (238 VisDrone-MOT identities, median 40 px tall) |
| Identity gate | 0.25 (default `identity_max_distance`) | 0.30 (`identity_max_distance`; the fine-tune separates identities but widens same-identity distances, so the gate moves with the weights) |
| Evidence rule | Unbounded (any undescribed person blocks re-binding) | **Evidence reach**: an undescribed person only blocks within `identity_evidence_radius` 0.5 extents (+ 2.0 extents/s of outage growth), plus the **focus fallback** (after a release the descriptor budget stays around the last verified box) |
| Track caps | 64 tracks / 128 detections | 128 tracks / 512 detections (crowds) |
| Follow schedule | default | `follow_local_gap_ms` 1500 / `follow_global_period_ms` 2000 (aerial cadence) |
| Validation | Live desk sessions (2026-09-12 onward) | Offline eleven-clip VisDrone replay + one live desk session; **no live aerial session yet** |

The aerial profile's detector and descriptor are **staged candidates**: the
start action verifies each HEF against the `.sha256` sidecar written at staging
time and refuses to start on a mismatch.

### 6.2 Starting a session and picking a target

```bash
bash hosts/hailo15l/fresh_tracking_ctl.sh start-follow
# open http://10.0.0.1:8099/
```

In the viewer:

- **Click a detection box** to select that object as the target, or choose a
  class (e.g. **target: person**) — class selection acquires only when exactly
  one *confirmed* object of that class is visible.
- **Clear target** unlocks. After a target expires, select again — another
  person is **never automatically substituted**.
- The selected identity is separate from the temporary track ID: the lock can
  survive track-ID churn as long as identity evidence supports it.

### 6.3 What the identity logic does

The node separates three concerns:

1. **Track confirmation** — a detection becomes a confirmed track only after
   `confirm_ms` (120 ms) of support above `birth_confidence` (0.5); weak
   detections down to `low_confidence` keep existing tracks alive but cannot
   start one.
2. **Freshness and coasting** — a published target observation is control-valid
   for `freshness_ms` (500 ms); a missed target coasts on prediction up to
   `coast_ms` (1200 ms) and is then *lost*, never silently extrapolated. A
   coasting/lost target produces **hold**, not a chase command.
3. **The identity owner** — when `learned_person_identity` is on (both live
   profiles), the lock is bound to an OSNet appearance identity, not to a track
   number:
   - Re-binding to any track (same ID included) requires a **positive
     appearance match inside the identity gate**, with an ambiguity margin of
     0.04 — if a second person's descriptor is within the margin, the frame is
     ambiguous and the lock is released rather than guessed.
   - Identity memory holds for `identity_memory_ms` (30 s): a person who walks
     out and returns inside that window is re-acquired onto the **same
     selected identity** (new track ID, same lock).
   - The rule set is **fail-closed**: an undescribed nearby person blocks
     re-binding (the aerial profile's evidence reach only scopes "nearby";
     see 6.1). Incomplete evidence produces no bind, not a wrong bind.
4. **Geometric classes** (car, phone, …) have no learned descriptor; they use a
   geometric lock with a 7 s re-acquire window and histogram/size evidence.

### 6.4 Recording

Short, bounded recording harnesses exist (`bench/fresh_stream_capture.py` with
`qualify_capture.py`; the capture profiles in 5.3). They capture exact-exposure
NV12 source pixels paired with outputs for causal replay — not compressed
flight video. Respect the bounds baked into them (small frame counts, non-CMA
RAM admission checks, eMMC reserves): sustained recording is **not** qualified
on this board, and an early unbounded attempt stalled the board's SSH and
camera API (see `docs/2026-09-27-track-record-readiness.md` before extending
them).

---

## 7. The follow console & simulator

### 7.1 Headless closed-loop check — `bench/fresh_follow_sim.py`

A fully synthetic, deterministic loop that exercises the **actual C++ tracker**
(via `garuda-track-replay`), the follow controller and simple kinematics — no
camera, board, or PX4:

```bash
python3 bench/fresh_follow_sim.py \
  --replay-bin /tmp/garuda-fresh/native/garuda-track-replay \
  --output /tmp/fresh-follow-sim.jsonl
```

It drives 500 ticks through scripted fault phases (occlusion, frozen transport,
slow transport, ambiguity, changed selection) and **asserts** that every fault
holds after its deadline and that framing converges. Use it as the quickest
sanity check after touching tracker or follow code. It makes no hardware or
accuracy claim.

### 7.2 The interactive follow console

The operator console is a local Python/HTML app (`bench/sim/`, served at
**http://127.0.0.1:8100/** on the PC) joined to the real board NPU and an owned
PX4 SITL + Gazebo instance. Everything is simulation-gated:

```bash
# Rendered-camera closed loop (Gazebo RGBD -> board inference -> PX4 -> motion):
GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh --out /tmp/garuda-visual-demo-01
```

Prerequisites: Gazebo Harmonic (gz-sim 8.x) with the cached "Mingfei actor v1"
Fuel asset (`docs/dependencies/gazebo-follow-bench.md`), a PX4 SITL build, and
the board stream binary staged to `/opt/garuda-sim/` with
`hosts/hailo15l/stage_sim_stream.sh`. Use a **new output directory for every
run** — evidence is never overwritten. The console starts **disarmed**; the
flow is Take off → select a detected person → **Follow**, with Hold / Release /
Land / a bounded perception-dropout test on the working surface.

### 7.3 The grand demo — three input modes

`hosts/hailo15l/run_grand_demo.sh` launches the same console against three
deliberately different pixel sources:

```bash
# Live desk camera (leaves the desk node running; heading response only):
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh live /tmp/garuda-live-demo-01

# Fully closed-loop rendered camera (temporarily lends the board NPU to the run):
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh gazebo /tmp/garuda-gazebo-demo-01

# Recorded aerial clip through the real board inference:
GARUDA_SIM=1 bash hosts/hailo15l/run_grand_demo.sh replay /tmp/garuda-replay-demo-01 \
  PREPARED_DATASET_DIR            # needs manifest.json + source.nv12
```

- `--aerial` on `gazebo`/`replay` runs the staged **aerial profile**
  (fine-tuned HEF, wide caps, 1500/2000 follow schedule) instead of the desk
  fullview profile.
- Live mode first needs the ROS helpers staged:
  `bash hosts/hailo15l/ros2/deploy_nodes.sh`.
- The launcher refuses a second PX4 instance; stop/land before switching modes.
  Replay/Gazebo modes pause the desk pipeline and restore it on exit.

**Recorded-clip replay with pause and double-click selection.** In replay mode
the clip (20–75 s) **loops** so the operator can work at their own pace. The
console can **pause** the recorded pixels on a still frame (the pause is taken
out of the clip position, never out of the clock — frozen evidence stays
honest), letting you study a frame and pick the right person. **Double-click**
the target on the video overlay to request follow: the console answers "Follow
will start once the target is verified" and engages only when the selection is
a verified, fresh identity — it reports `expired` if the double-clicked object
never verifies. Single clicks select; keyboard target buttons and ID-card
clicks are equivalent selection paths.

The console shows, side by side: the input video with detection/track overlays
(stale boxes labelled amber), a Gazebo world camera, the retained target
identity vs. temporary track IDs, on-board ROS message counts and frame age,
the requested setpoint vs. the MAVROS publication vs. the **actually forwarded
MAVLink** (rejections stay visible — the freshness gate is never hidden to make
a demo look smooth), PX4 altitude/heading response, a 1×/2×/4× target-centred
inspection zoom (display-only; it adds no sensor detail), and an apparent-size
reference readout that is explicitly **not** a metric distance.

Configured simulation limits (limits, not benchmarks): yaw rate ≤ 0.8 rad/s,
heading offset capped at ±30° in camera modes, forward ≤ 1 m/s / backward
≤ 0.5 m/s, default standoff 6 m, altitude 2 m. Stale, ambiguous, unselected or
expired targets always produce hold.

Automated variants and verifiers:

```bash
GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh --out /tmp/garuda-visual-trial-01 --auto-demo --duration 60
python3 bench/sim/verify_gazebo_follow.py /tmp/garuda-visual-trial-01
python3 bench/sim/console_capture.py OUT.jsonl    # record console state per board frame
```

---

## 8. Benchmarks & evidence

Everything quantitative lives in **`bench/benchlog.md`** (dated entries, with
environment snapshots in `bench/versions.md`); small committed evidence files
are under **`bench/evidence/`**. Large bench recordings, the
`bench/results/` evidence trees and frozen baseline archives are **excluded
from this snapshot** — the benchlog entries name them where they exist on the
original bench. Anything not measured is `TBD-bench`.

Selected measured results on this branch (all from `bench/benchlog.md`, quoted
with their entry dates; none of these are Hailo-15H numbers):

**2026-09-12 22:05 — first live session on the desk follow profile** (owner in
view at ~1 m, 157 s): node snapshot age p50 74–86 ms, p95 ≤ 106 ms, max 116 ms
against a 200 ms budget; OSNet 6.9 ms inference + 4.6 ms crop per person;
re-identification after absences of 0.7 / 0.4 / 0.2 / 3.6 s re-bound the same
lock identity in 0.37 / 0.23 / 0.17 / 0.20 s. A 12.4 s absence crossed the
then-10 s identity memory and was correctly not re-bound (memory is 30 s
since 2026-09-12 23:08).

**2026-09-13 — rendered-camera visual SIL (final staged repeat):** 617 unique
inference frames; 415/1194 non-hover follow ticks (34.8 % command
eligibility); ingress→result median/p95 127.8 / 227.9 ms; board compute
90.2 / 185.6 ms; max follow displacement 6.47 m; all 31 dropout ticks held,
recovered, and the run disarmed. Recorded as "functional demo passed;
continuous robustness did not."

**2026-09-13 — grand demo, physical person response:** actual PX4 heading span
27.07° following the owner's movement, 128 moving packets forwarded (55
rejected by the freshness gates and left visible); rendered-camera repeats
reached 7.85 m max XY displacement. These are measured demonstrations, not a
qualification.

**2026-09-17 — 1280×736 single-pass detector:** person recall at the 0.5 floor
0.378 in one 57 ms pass vs 0.346 for five 640 tiles at 131 ms — the better
*detector*, but on the eleven-clip follow protocol it acquired 3/11 with 79
on-target frames vs 6/11 / 129 for the 640 path, so it was not adopted; the
losses were all in the tracker/identity path.

**2026-09-18 — drone-view re-identification descriptor + evidence reach
(the re-ID lever):** OSNet fine-tuned on drone-view crops: holdout rank-1
0.960 → 0.979, false accepts inside the 0.25 gate 8.3 % → 0.3 %. On the
eleven-clip single-view replay: deployed descriptor 6/11 acquired, **129**
on-target frames, 0 wrong identity → epoch 30 + evidence reach 0.5 + focus
fallback **161** on-target, **0 wrong identity** (adaptive mode 117 → ~142,
with a few frames of run-to-run variance from tile-schedule timing). Same-day
live desk session on the aerial profile: identity verified on 94 % of frames
with a confident detection; live aerial-style numbers remain `TBD-bench`.

**2026-09-20 — completed measured-cadence drone baseline (22 replay trials):**
fullview acquired 5/11 with 120 control-valid on-target / 64 off-target
outputs; adaptive 6/11 with 161 / 1. The fullview car clip 245 contains 63
control-valid outputs with zero annotated-target overlap — a retained
wrong-target counterexample, and the reason "no mode qualifies robust
following" stands.

Read the **red-team paragraphs** attached to each benchlog entry before
re-quoting a number: they record what each result does *not* prove (training/
evaluation overlap, replay-vs-live distinctions, adaptive-mode variance,
single-scene sessions).

---

## 9. Troubleshooting

### Console shows nothing

Work through these in order — all were hit during the original bring-up and
none meant a dead board:

1. The boot ROM on non-secure parts **never transmits**; early silence proves
   nothing.
2. Press **Enter** — getty only re-prints `hailo15l login:` on a keypress.
3. Confirm your terminal asserts **DTR and RTS** at 115200 8N1; without them
   the FT230X returns garbled text (garbage at the wrong baud is a *sign of
   life*, not corruption).
4. Check DIP **SW1 is both ON** (OFF/OFF boots nothing, silently).
5. Verify **both power LEDs** (PWR-IN and the power button) are lit; a
   power-cycle that doesn't actually cut the 12 V input fixes nothing.
6. The FTDI bridge is board-powered and re-enumerates on every power-cycle —
   reopen the port.

### SSH times out / board unreachable

- The PC's wired port is probably not on the board's subnet:
  `nmcli con up h15-link` (re-points it at 10.0.0.2/24) and retry. Wired
  NetworkManager profiles are mutually exclusive — another profile on the same
  port (e.g. one sharing the port to a different bench device) silently steals
  it.
- `ping 10.0.0.1` and check link state (`nmcli dev`); the board is static
  10.0.0.1/24 with no DHCP in either direction.

### `hailortcli` identify fails or the NPU is "busy"

- Expect exactly `HAILO15L`, Firmware `5.3.0`. A different architecture string
  means you are not on the board you think you are.
- Only **one** process can own the camera/NPU pipeline: stop
  `camera-viewer-server`, the fresh node, or any replay/probe before starting
  another (`fresh_tracking_ctl.sh stop`; the staging script refuses to restage
  over a running node for the same reason). `hailortcli benchmark` cannot run
  while the node holds the device.

### Camera pipeline dead after boot

Known stock-image boot race: a demo app can OOM-kill `isp_media_server` shortly
after boot, after which every pipeline create times out (−11). Fix:

```bash
ssh root@10.0.0.1 '/etc/init.d/isp_media_server restart'
```

Also check the leftover burn-in recorder is disabled (chapter 2.5) — it both
hogs the camera and fills the eMMC.

### eMMC full

The rootfs is ~7 GB and fills fast. Historical offenders: the burn-in
recorder's video clips, and replay campaigns leaving a staged binary copy per
clip (381 copies once filled the disk; the harness now cleans per clip). Check
`df -h /` before long campaigns; keep datasets and captures on the PC. The
board has roughly 3 GB free in a healthy state.

### Board clock is in 2018

No RTC/NTP. Set it from the PC when it matters:
`ssh root@10.0.0.1 "date -s @$(date +%s)"`. It resets on every power-cycle.

### Node "started" but no tracks / no video

- Readiness means **advancing camera snapshots**, not a PID:
  `python3 hosts/hailo15l/wait_fresh_camera.py --host 10.0.0.1` (the start
  actions already run it).
- Logs: `/tmp/garuda-fresh.log` (node), `/tmp/garuda-fresh-shim.log` (shim);
  state: `curl http://10.0.0.1:8099/api/state`.
- A start that exits complaining about a missing or mismatched HEF checksum
  means the profile's model slot isn't staged — see chapter 5.2.

### Stop hangs or a restart loses a run

SIGTERM teardown of the media pipeline and NPU can take several seconds; the
control script waits up to 10 s. Don't `kill -9` unless that window has
passed.

### SSH and camera API stall together under heavy recording

Seen once (2026-09-27) during an unbounded eMMC capture: SSH and the camera API
stopped responding while ping and serial kernel messages continued (ISP event
timeouts); recovery required an owner power-cycle. The corrected capture tools
reserve non-CMA RAM and disk and cap sample counts — do not relax those bounds.
If you hit this state: serial console first, then power-cycle; verify the
protected node/config hashes afterwards.

---

## 10. Licence

### Policy

- The project's own code is **BSD 3-Clause** (`LICENSE` at the repo root).
- Product-tier (shippable `services/`) policy is **BSD / MIT / Apache /
  LGPL-dynamic only**; CI's licence scan fails hard on GPLv3.
- **GPLv3/AGPL are permitted for bench, experimental and evaluation work
  only** (running locally is not distribution). Any such component stays
  behind the plugin interfaces, is tagged **`not-product-cleared`**, and never
  gets deep-wired into shippable services. `models/` is the explicit
  evaluation zone: eval-only models never graduate; a good eval-only model is
  the signal to find or train a clean-licence equivalent.

### GPL/AGPL and otherwise restricted components on this branch

All evaluation-only and **not product-cleared**:

| Component | Licence | Where / role |
|---|---|---|
| YOLO11s / YOLOv8m / YOLOv11m / yolo26m HEFs (Ultralytics lineage, incl. the controlled rebuild and the VisDrone aerial fine-tune) | **AGPL-3.0** | the detectors (`models/*_h15l.md` cards, board model slots) |
| Ubuntu Noble ARM64 rootfs at `/opt/garuda-ros-jazzy` (board) | GPL system utilities among package-specific licences | bench ROS 2 Jazzy / MAVROS chroot (`docs/dependencies/ros2-mavros-bench.md`) |
| pymavlink | LGPL-3.0 | PC-side bench only |
| OSNet x1.0 (deep-person-reid) | source **MIT**, but model-weight and training-dataset terms not independently cleared | re-ID descriptors (zoo + drone-view fine-tune); no weight distribution from this repo |
| Hailo VPSP / board tools / DFC | Hailo proprietary | PC-side bench tooling only, never in `services/` |
| VisDrone dataset | CC BY-NC-SA 3.0 terms published for 2021; applicability to the 2019 archives and commercial use **unverified** | offline training/evaluation data, never redistributed here |

Clean components used by the bench stack: OpenCV 4.5.5 (Apache-2.0, optional
motion plugin), Gazebo gz-sim/transport/msgs (Apache-2.0), PX4 (BSD-3-Clause),
NumPy (BSD-3-Clause), Pillow (HPND), libjpeg-turbo (IJG/BSD-3-Clause), and the
Gazebo Fuel "Mingfei actor v1" walking actor (CC BY 4.0, attribution in
`docs/dependencies/gazebo-follow-bench.md`).

Authoritative records: **`models/LICENCES.md`** (model manifest and
ship-eligibility) and **`docs/dependencies/`** (per-dependency boundary notes).
Before adding any dependency, state its licence in the commit/PR description;
a failing licence scan is a hard stop, not an override.
