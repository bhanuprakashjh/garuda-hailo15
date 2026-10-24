# garuda-hailo15 — Garuda SDK perception node on the Hailo-15L SBC

A follow-me ("fresh tracking") perception node for drones and robotics, running on a
**Hailo-15L single-board computer** with an IMX678 camera. It detects people and
vehicles with YOLO HEFs on the Hailo NPU, tracks a single operator-selected target
through occlusion and re-entry using an OSNet appearance descriptor and an
identity-owner rule set, and exposes a live browser viewer, a replay/evidence
harness, and a simulation-only follow console (PX4 SITL + Gazebo).

This is a **bench project**: no flight controller is connected, nothing here arms
motors, and every code path that could emit vehicle commands is gated behind
`GARUDA_SIM=1` and owned, loopback-only PX4 SITL processes. Current owner scope is
**tracking and short recording only** — no autonomous following on a real vehicle,
and no flight authorization follows from anything in this repository.

> **Hardware caveat:** the Hailo-15L is the lowest-throughput member of the
> Hailo-15 family. It is a fair proxy for the product-tier Hailo-15H in every
> respect **except NPU headroom** — never quote 15L frame rates as 15H numbers.

## Hardware at a glance

| Item | Value |
|---|---|
| Board | Hailo-15L SBC **rev 2.x** (silkscreen `PCB00150 Rev2.0`) — a development SBC, **not** an EVB and **not** a 15H |
| SoC | Hailo-15L: 4× Cortex-A53 @ 1.1 GHz, integrated NPU, ISP, Tensilica DSP, Hantro H.264 encoder |
| Memory | 2 GB RAM (~1.25 GB reserved as CMA — roughly 600 MB for user space) |
| Storage | 7.3 GB eMMC (boot + rootfs); no SD card required |
| Camera | Sony IMX678, 3840×2160 capture through the on-board ISP |
| OS image | Factory eMMC image **VPSP 1.12.0** (`vpu-stability-v1.12.0`, poky 4.0.23 / kirkstone, kernel 5.15.32) — boots as shipped, no re-flash needed |
| Runtime | HailoRT 5.3.0; `hailortcli fw-control identify` reports **HAILO15L, Firmware 5.3.0** |
| Network | Board `eth0` static **10.0.0.1/24**, direct cable to a PC at **10.0.0.2/24** |
| Console | On-board FTDI (micro-USB J1), **115200 8N1 with DTR/RTS asserted**; DIP **SW1 both ON** for normal eMMC boot |
| PC toolchain | VPSP 1.12.0 + poky cross SDK + board-tools venv + Hailo **DFC 5.3.0 targeting `hailo15l`** (HEFs are compiled on x86, never on the board) |

## Quick start

With the board cabled directly to the PC's wired port and powered:

```bash
# PC network profile (static 10.0.0.2/24 on the wired interface)
nmcli con up h15-link

# First contact
ssh root@10.0.0.1 'hailortcli fw-control identify'   # expect HAILO15L, Firmware 5.3.0

# Build (native tests + ARM cross-build), stage to /opt/garuda-fresh, start the desk follow profile
bash hosts/hailo15l/build_fresh_tracking.sh
bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-follow
```

Then open **http://10.0.0.1:8099/** and click a detected person to lock the target.

HEF model binaries are not committed: fetch the model-zoo ones with the
`models/fetch_*.sh` scripts (checksum-pinned) and point the stage script at them —
the [user guide](docs/USER_GUIDE.md) chapter 5 covers the model slots and
environment variables (`GARUDA_H15L_SDK`, `GARUDA_FRESH_HEF`, …).

The full walk-through — board bring-up, console access, the PC toolchain, model
staging, the desk vs. aerial profiles, the follow console/simulator, benchmarks and
troubleshooting — is in **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**.

## Repository layout

| Path | What it holds |
|---|---|
| `hosts/hailo15l/` | Everything board-specific: the fresh node adapter (`fresh_node.cpp`), region detector, person/image embeddings, build/stage/control scripts (`build_fresh_tracking.sh`, `stage_fresh_tracking.sh`, `fresh_tracking_ctl.sh`), media-library profiles (`fresh/`, `medialib/`), demo launchers (`run_grand_demo.sh`, `run_visual_sim.sh`), ROS 2/MAVROS bench scripts (`ros2/`), and the earlier `garuda-perception` deploy path (`deploy.sh`, `garuda-perception.init`) |
| `services/garuda-tracking/` | The host-independent C++17 tracking core (tracker, identity owner, lock policy), the board shim/viewer (`fresh_shim.py`), tuning UI, and tests |
| `services/garuda-follow/` | Follow controller, perception authority, target adapter, simulation kinematics |
| `services/garuda-perception/` | The earlier Hailo-15L perception node (M0–F1 era) and its post-process plugins — kept as the `restore` fallback and for history |
| `services/garuda-bridge/`, other `services/` | Simulation offboard bridge and services inherited from the parent bench (largely Pi 5 era) |
| `bench/` | Harnesses and the measurement record: `benchlog.md` (every quoted number), `versions.md` (environment snapshots), `fresh_*.py` harnesses, `sim/` (follow console, Gazebo world, verifiers), `hailo_reference/` (replay/scoring tools), `evidence/` (small committed evidence) |
| `models/` | HEF fetch scripts, model cards and the licence manifest (`LICENCES.md`); HEF binaries themselves are git-ignored and fetched/built on the PC |
| `docs/` | Dated engineering reports, `decisions.md` (the decision log), dependency/licence records (`docs/dependencies/`), and the user guide |
| `hosts/pi5/`, `calib/`, `datasets/`, `interfaces/`, `yocto/`, `ci/` | Inherited from the parent monorepo (the Raspberry Pi 5 + Hailo-10H bench tier); not required for the Hailo-15L work but kept for context |

## Status and claims discipline

Every performance number in this repository was measured on the actual hardware and
is recorded in [`bench/benchlog.md`](bench/benchlog.md) with a matching environment
snapshot in [`bench/versions.md`](bench/versions.md). Unmeasured values are written
`TBD-bench`, never estimated. The tracking stack is an operator-accepted desk
baseline plus measured aerial-footage improvements — it is **not** qualified as
robust tracking, a standalone flight recorder, or anything flight-worthy.

## Licence

The project's own code is **BSD 3-Clause** (see [`LICENSE`](LICENSE)).

Product-tier policy is BSD/MIT/Apache/LGPL-dynamic only. GPLv3/AGPL components are
permitted **for bench, experimental and evaluation work only**, are tagged
`not-product-cleared`, and never graduate into shippable services. Notably, the
YOLO detector HEFs used on this branch (Ultralytics YOLO11/YOLOv8 lineage) are
**AGPL-3.0, evaluation-only**; the OSNet re-identification source is MIT with
weight/dataset clearance still pending. The full manifest is in
[`models/LICENCES.md`](models/LICENCES.md) and [`docs/dependencies/`](docs/dependencies/),
and the licence chapter of the [user guide](docs/USER_GUIDE.md#10-licence) summarises
what is and is not ship-eligible.

## Provenance

Private snapshot of the garuda-sdk-bench monorepo, branch
`feat/hailo15l-fresh-tracking`, taken 2026-10-24. Large bench recordings and frozen
baselines excluded.
