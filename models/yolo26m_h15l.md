# yolo26m (Hailo-15L) — model card

> **STATUS (2026-09-03, later): AVAILABLE — pre-compiled by Hailo, not built here.** Hailo's public
> model zoo publishes `yolo26m` for `hailo15l` in the same release line as the Pi's production 640
> HEF (`docs/decisions.md` 2026-08: the Pi's `yolo26m.hef` came from `.../Compiled/v5.3.0/hailo10h/`).
> Fetched, parsed and benchmarked on the board — see "Zoo HEF" below and `bench/benchlog.md`
> 2026-09-03 "yolo26m from the Hailo model zoo". The local recompile described further down is now
> OPTIONAL (only needed for a custom calibration set or QAT); its OOM failure record is kept as is.

## Zoo HEF (the artifact M2 integrates)

- **Source:** `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/yolo26m.hef`
  (22388736 bytes, md5 `3aef604ab89ddaf9ecb4cefa9c6ea8af`; the `v5.4.0/hailo15l/` object has the same
  size and a `hailo15h` variant also exists). Compiler version in the HEF: 5.3.0 — a matched set with
  the board's HailoRT 5.3.0.
- **Where:** PC `/media/bhanu1234/Development/hailo15/models/yolo26m_hailo15l_v5.3.0.hef` (not in git;
  `models/*.hef` is ignored); board `/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef`.
- **Layout** (`hailortcli parse-hef` on the board, verbatim in the benchlog): input
  `yolo26m/input_layer1 UINT8, NV12(320x640x3)` (= 640×640 NV12), outputs UINT16 `conv71` 80×80×4,
  `conv87` 40×40×4, `conv101` 20×20×4 (ltrb box heads, strides 8/16/32) and `conv74` 80×80×80,
  `conv90` 40×40×80, `conv104` 20×20×80 (class logits, COCO-80); 17 contexts. Same six raw heads and
  the same layer names the Pi's decoder (`hosts/pi5/hailo_yolo26.py`, `PAIRS`) consumes, so the
  decode ports unchanged; the 16-bit output quantisation is the one difference to handle.
- **Licence:** the zoo HEF is Hailo's compiled artifact of Ultralytics YOLO26 weights — AGPL-3.0
  upstream, bench/eval only, `not-product-cleared` (same as the recipe below).

> **Original STATUS (2026-09-03, morning): NOT BUILT** — blocked by PC RAM. Layer Noise Analysis needs
> more resident memory than the PC has; the kernel OOM-killed the exporter on all three attempts.

**Licence: AGPL-3.0 — bench/eval only, `not-product-cleared`** (Ultralytics YOLO26, per CLAUDE.md
§1's relaxed policy: GPLv3/AGPL permitted for bench/experimental/evaluation work, kept behind the
plugin interfaces, never deep-wired into shippable `services/`).

- **Source weights:** `yolo26m.pt` — Ultralytics **8.4.115**, **AGPL-3.0**.
- **Compiler:** Hailo DFC **5.3.0**, via the venv `/media/bhanu1234/Development/hailo-export/venv`,
  using the sed-patched Ultralytics exporter (level-2 PTQ, QAT finetune disabled — the same patch
  state recorded in `docs/decisions.md` 2026-08-07 (evening): "Venv exporter patch state now:
  level 2 + finetune disabled"). The recipe (`hosts/hailo15l/build_yolo26m_h15l.sh`) hard-asserts
  this patch is present before exporting and refuses to run otherwise.
- **Target:** `hailo15l`, **640×640** input.
- **Quantization:** PTQ, **level 2**, finetune disabled.
- **Calibration set:** `datasets/depth-calib.yaml` — 1024 images (256 CM3 + 768 SUN RGB-D), the
  same calibration set recorded in CLAUDE.md §7 for the 10H `yolo26m-depth` production build.
- **Recipe:** `hosts/hailo15l/build_yolo26m_h15l.sh` (committed, guarded, idempotent).

## What happened

The recipe was run three times on the bench PC. Each run reached the DFC's "Layer Noise Analysis"
stage and was killed by the kernel's OOM killer before completing. No HEF was produced —
`/media/bhanu1234/Development/hailo-export/work-h15l/yolo26m_hailo_model/` is empty.

### Evidence

**Kernel OOM-kill lines** (`journalctl -k`, one line per run, all killing the exporter's `yolo`
process):

```
Sep 02 23:34:20 bhanuprakash kernel: Out of memory: Killed process 494217 (yolo) total-vm:29859748kB, anon-rss:5249632kB, file-rss:65340kB, shmem-rss:147460kB, UID:1000 pgtables:16396kB oom_score_adj:200
Sep 02 23:49:30 bhanuprakash kernel: Out of memory: Killed process 500799 (yolo) total-vm:24315300kB, anon-rss:7009532kB, file-rss:64792kB, shmem-rss:107024kB, UID:1000 pgtables:19452kB oom_score_adj:200
Sep 03 00:00:50 bhanuprakash kernel: Out of memory: Killed process 506287 (yolo) total-vm:24148432kB, anon-rss:7142564kB, file-rss:64892kB, shmem-rss:147460kB, UID:1000 pgtables:19360kB oom_score_adj:200
```

**Export log tail, third run** (`tail work-h15l/export_yolo26m_h15l.log`):

```
[info] Adaround skipped
[info] Quantization-Aware Fine-Tuning skipped
[info] Starting Layer Noise Analysis
Full Quant Analysis:   0%|          | 0/2 [00:00<?, ?iterations/s]
```

**PC memory, at the time of writing** (`free -h | sed -n '2,3p'`):

```
Mem:            14Gi       7.8Gi       1.0Gi        97Mi       6.5Gi       7.1Gi
Swap:          4.0Gi       4.0Gi        14Mi
```

**Swap configuration** (`swapon --show`):

```
NAME      TYPE SIZE USED PRIO
/swap.img file   4G   4G   -1
```

The PC has 14 GiB RAM and a 4 GiB swap file; the swap file was full (`4.0Gi USED`) during the
runs, so the kernel OOM killer intervened rather than let the exporter's allocation succeed.

## Re-run

The recipe is idempotent — re-running it reuses `work-h15l/yolo26m.pt` and only overwrites
`work-h15l/`. To re-run once headroom exists:

- **Add swap** on this PC:
  ```
  sudo fallocate -l 8G /swap2.img && sudo chmod 600 /swap2.img && sudo mkswap /swap2.img && sudo swapon /swap2.img
  ```
  so combined RAM+swap comfortably clears the anon-rss high-water mark already quoted above
  (the third run's kernel line: `anon-rss:7142564kB`), or
- Run the recipe on a machine with more RAM.

```
hosts/hailo15l/build_yolo26m_h15l.sh
```

(`GARUDA_HAILO_EXPORT` overrides the default export root of
`/media/bhanu1234/Development/hailo-export` if needed.)

## Benchmark

Zoo HEF: measured on the board 2026-09-03 with the perception service stopped —
`bench/benchlog.md` 2026-09-03 "yolo26m from the Hailo model zoo" holds the verbatim
`hailortcli benchmark` line and conditions; numbers live there, not here (CLAUDE.md rule 1).
A locally recompiled HEF, if ever built: `TBD-bench` until run the same way.

## Integration

**M2 done** (2026-09-03) — this HEF and `libyolo26_post.so` (Task 3's six-head decode plugin,
`services/garuda-perception/postprocess/yolo26_post.cpp`) are live on the board in place of the
vendor's stock `yolo_hailortpp_post`/`yolov8n` path, deployed node commit `8c82367`
(`feat/hailo15l-detector`). Bench-measured: `bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: M2
yolo26m detector". Full integration detail (config switch, rollback, letterbox, pad colour):
`hosts/hailo15l/README.md` §8.
