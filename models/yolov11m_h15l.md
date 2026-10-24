# yolov11m (Hailo-15L) — model card

> **STATUS (2026-09-04): AVAILABLE — pre-compiled by Hailo, not built here.** Fetched from Hailo's
> public model zoo for a detector A/B against `yolov8m_h15l` and `yolo26m_h15l` on
> `feat/hailo15l-kalman-tracker` (`bench/benchlog.md` 2026-09-04). Added alongside `yolov11s_h15l.md`
> in the same commit, mirroring `yolov8m_h15l.md`'s shape.

## Zoo HEF (the artifact `config/perception-yolov11m.json` integrates)

- **Source:** `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/yolov11m.hef`
  (15269888 bytes, md5 `1d199595320154d0b62be010b9d374a7`). Compiler version in the HEF: 5.3.0 — a
  matched set with the board's HailoRT 5.3.0, same release line as `yolov8m_h15l.md`'s zoo HEF.
- **Fetch:** `models/fetch_yolov11m_h15l.sh` (same idempotent md5-checked shape as
  `models/fetch_yolov8m_h15l.sh`).
- **Where:** PC `/media/bhanu1234/Development/hailo15/models/yolov11m_hailo15l_v5.3.0.hef` (not in
  git; `models/*.hef` is ignored); board `/opt/garuda/models/yolov11m_hailo15l_v5.3.0.hef`
  (`config/perception-yolov11m.json`'s `hef` field). Board copy md5-verified after `scp`:
  `1d199595320154d0b62be010b9d374a7`.
- **Layout** (`hailortcli parse-hef` on the board, verbatim, 2026-09-04):

  ```
  HEF Compatible for: HAILO15L
  HEF Compiler Version: 5.3.0
  Network group name: yolov11m, Multi Context - Number of contexts: 11
      Network name: yolov11m/yolov11m
          VStream infos:
              Input  yolov11m/input_layer1 UINT8, NV12(320x640x3)
              Output yolov11m/yolov8_nms_postprocess FLOAT32, HAILO NMS BY CLASS(number of classes: 80, maximum bounding boxes per class: 100, maximum frame size: 160320)
              Operation:
                  Op YOLOV8
                  Name: YOLOV8-Post-Process
                  Score threshold: 0.200
                  IoU threshold: 0.70
                  Classes: 80
                  Max bboxes per class: 100
                  Image height: 640
                  Image width: 640
  ```

  Input `UINT8, NV12(320x640x3)` (= 640×640 NV12), output `yolov8_nms_postprocess FLOAT32, HAILO NMS
  BY CLASS` (80 classes, max 100 boxes/class, max frame size 160320) — **byte-for-byte the same
  on-chip-NMS output shape as `yolov8m_h15l`'s HEF** (the compiler's postprocess op is still named
  `YOLOV8-Post-Process`/`yolov8_nms_postprocess` regardless of the underlying architecture), so the
  stock `libyolo_hailortpp_post.so` post-process plugin + `config/yolov8m_post.json` (81 labels) +
  the existing `GarudaYolov8m` media-library profile (640×640 stretched, 30 fps) apply unchanged —
  no new plugin, config, or profile needed. 11 contexts (vs yolov8m's 13, yolov11s's 8).
- **Licence:** the zoo HEF is Hailo's compiled artifact of Ultralytics YOLO11 weights — **AGPL-3.0**
  upstream, bench/eval only, `not-product-cleared` (CLAUDE.md §1's relaxed policy: GPLv3/AGPL
  permitted for bench/experimental/evaluation work, kept behind the plugin interfaces, never
  deep-wired into shippable `services/`).

## Hailo's published numbers (quoted, not measured here)

From Hailo's model-zoo docs (`HAILO15L_object_detection.rst`, local copy under
`hailo-export/suite/sources/model_zoo/docs/`), COCO val2017, 640×640 input:

| model | mAP (float) | mAP (quantised) | FPS (batch 1) |
|---|---|---|---|
| yolov11m | 50.7 | 49.5 | 33.4 |
| yolov8m (for reference) | 49.6 | 48.8 | 39.7 |

These are Hailo's own figures, not ours — no equivalent run has been made on this bench yet.

## Benchmark

No `hailortcli benchmark` or on-bench fps/accuracy run has been made for this HEF yet — `TBD-bench`
(CLAUDE.md rule 1: never invent a number). `hailortcli parse-hef` above is read-only and does not
exercise the network.

## Integration

- **YOLO11 A/B** (`feat/hailo15l-kalman-tracker`, `config/perception-yolov11m.json`) — same
  `GarudaYolov8m` medialib profile, stock post-process, and tracker/lock parameters as
  `config/perception-yolov8m.json`, differing only in the `hef` field, to isolate the detector's
  effect against `yolov8m_h15l` and `yolo26m_h15l`. Switch with:

  ```bash
  env GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov11m.json \
      hosts/hailo15l/deploy.sh
  ```

  Rollback to the checked-in default the same way with `config/perception-yolov8m.json` (or
  `config/perception.json` for yolo26m).
