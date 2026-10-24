# yolov8m (Hailo-15L) — model card

> **STATUS (2026-09-03): AVAILABLE — pre-compiled by Hailo, not built here.** Fetched from Hailo's
> public model zoo for the yolov8m A/B (`bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: yolov8m A/B
> for small-object (cell phone) tracking") and reused by the Kalman tracker-engine work
> (`bench/benchlog.md` 2026-09-03 "Kalman tracker engine (SDK TrackerStage) vs mono's tracker").
> Added to `models/` retroactively in the 2026-09-04 final-fix wave (M4) — the fetch script, this
> card, and the `models/LICENCES.md` row did not exist when the HEF was first fetched ad hoc.

## Zoo HEF (the artifact `config/perception-yolov8m.json` integrates)

- **Source:** `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/yolov8m.hef`
  (18558976 bytes, md5 `8eef4ca967752c54799dd2fb5cd14dcf`). Compiler version in the HEF: 5.3.0 — a
  matched set with the board's HailoRT 5.3.0, same release line as `yolo26m_h15l.md`'s zoo HEF.
- **Fetch:** `models/fetch_yolov8m_h15l.sh` (same idempotent md5-checked shape as
  `models/fetch_yolo26m_h15l.sh`).
- **Where:** PC `/media/bhanu1234/Development/hailo15/models/yolov8m_hailo15l_v5.3.0.hef` (not in
  git; `models/*.hef` is ignored); board `/opt/garuda/models/yolov8m_hailo15l_v5.3.0.hef`
  (`config/perception-yolov8m.json`'s `hef` field).
- **Layout** (`hailortcli parse-hef` on the board, verbatim, `bench/benchlog.md` 2026-09-03): input
  `yolov8m/input_layer1 UINT8, NV12(320x640x3)` (= 640×640 NV12), output
  `yolov8m/yolov8_nms_postprocess FLOAT32, HAILO NMS BY CLASS` (80 classes, max 100 boxes/class,
  max frame size 160320) — the HEF bakes its own NMS (`YOLOV8-Post-Process`, score threshold 0.200,
  IoU threshold 0.70, 640×640), unlike `yolo26m_h15l`'s six raw decode heads; 13 contexts (vs
  yolo26m's 17). Consumed by the stock `libyolo_hailortpp_post.so` post-process plugin with
  `config/yolov8m_post.json` (81 labels: `"unlabeled"` + COCO-80, `detection_threshold` 0.15 —
  the HEF's own baked NMS score floor of 0.200 may be the effective one, unmeasured which HailoRT
  honours).
- **Deployment profile:** `GarudaYolov8m` (medialib) — sink0 640×640 **STRETCHED** (not letterboxed
  like the yolo26m profile), because the stock post-process normalises boxes to the network input
  and this node's `xmin*frame_w`-style mapping (`node_main.cpp`) is only valid for a stretch.
- **Licence:** the zoo HEF is Hailo's compiled artifact of Ultralytics YOLOv8 weights — **AGPL-3.0**
  upstream, bench/eval only, `not-product-cleared` (CLAUDE.md §1's relaxed policy: GPLv3/AGPL
  permitted for bench/experimental/evaluation work, kept behind the plugin interfaces, never
  deep-wired into shippable `services/`).

## Benchmark

`hailortcli benchmark /opt/garuda/models/yolov8m_hailo15l_v5.3.0.hef -t 15` with the perception
service stopped, verbatim (`bench/benchlog.md` 2026-09-03, thermal in milli-°C before/after):

```
== Thu Sep  3 10:20:41 UTC 2026 thermal_mC:54920 uptime:up 19:05,  0 users,  load average: 2.02, 2.30, 2.33
yolov8m: FPS: 39.67
== thermal after: 63266
```

No separate benchmark for this fix round — numbers live in `bench/benchlog.md`, not duplicated here
(CLAUDE.md rule 1).

## Integration

Used in place of `yolo26m_h15l` behind two feature branches so far, both bench-only, neither
promoted to the default `config/perception.json`:

- **yolov8m A/B** (`feat/hailo15l-yolov8-ab`, `bench/benchlog.md` 2026-09-03) — same mono-engine
  tracker parameters as the M2 (yolo26m) config, to isolate the detector's effect on small-object
  (phone) tracking. Result: the detector was not the cause of the phone-tracking problem (yolo26m
  and yolov8m showed the same failure pattern).
- **Kalman tracker engine** (`feat/hailo15l-kalman-tracker`, `bench/benchlog.md` 2026-09-03 "Kalman
  tracker engine ... phone and person routines", `hosts/hailo15l/README.md` §9) —
  `config/perception-yolov8m.json` is the config used for every `tracker.engine: "hailo"` capture on
  this branch (`classification_id: 1`, person-only, is the checked-in default;
  `docs/decisions.md` 2026-09-03 "tracker engines" has the owner's direction).
