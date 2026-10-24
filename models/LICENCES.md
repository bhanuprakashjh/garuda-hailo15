# models/ — evaluation zone + licence manifest

`models/` is the **model evaluation zone**: any depth/vision model may be fetched and run here to
benchmark it on the bench. **Evaluation is not distribution** — running a model privately triggers
no licence obligations — so GPL and even unlicensed models are fine *to try*. The wall this manifest
enforces:

- **SHIP-ELIGIBLE** models (BSD/MIT/Apache/LGPL-dynamic) may graduate into `services/`.
- **EVAL-ONLY** models (GPLv3, unlicensed, unclear) stay in `models/` + host viewers, **never** get
  wired into `services/`, and **never** ship. CI licence-scan polices `services/`, not this zone.
- Every model gets a card + a row here stating its licence and eligibility. HEF binaries are
  git-ignored (`models/*.hef`) — fetch via the `fetch_*.sh` scripts.

This keeps CLAUDE.md rule 6 intact (clean `services/`) while letting us evaluate the whole zoo,
exactly like the object-detection models. When a model proves out and is ship-eligible, it moves to
`services/`; when a good one is EVAL-ONLY, that's the signal to find/train a clean-licence equivalent.

## Manifest

| model | task | licence | ship-eligible | card | notes |
|---|---|---|---|---|---|
| **fast_depth** | mono depth | **MIT** | ✅ yes | `fast_depth_h10.md` | NYU-indoor; relative scale; ~221 fps |
| stereonet | stereo depth | **none (unlicensed)** | ❌ eval-only | `stereonet_h10.md` | driving-trained; range-collapses indoors |
| scdepthv3 | mono depth | **GPL-3.0** | ❌ eval-only | `scdepthv3_h10.md` | NYU-indoor; better RMSE (0.48); GPL → never ship |
| yolov5n-seg | instance seg (dynamic masking) | **GPL-3.0** (Ultralytics) | ❌ eval-only | `yolov5n_seg_h10.md` | system model-zoo HEF (`/usr/share/hailo-models/`), not fetched here; feeds `garuda-mask` behind `IFrontEnd`; ~11.5 fps sync (benchlog 2026-08-02) |
| yolov8m (h15l) | object detection | **AGPL-3.0** (Ultralytics) | ❌ eval-only | `yolov8m_h15l.md` | Hailo model-zoo HEF for Hailo-15L, `fetch_yolov8m_h15l.sh`; used by the yolov8m A/B and Kalman tracker-engine bench work (`feat/hailo15l-kalman-tracker`); `not-product-cleared` |
| yolov11m (h15l) | object detection | **AGPL-3.0** (Ultralytics) | ❌ eval-only | `yolov11m_h15l.md` | Hailo model-zoo HEF for Hailo-15L, `fetch_yolov11m_h15l.sh`; YOLO11 A/B detector, same on-chip-NMS output as yolov8m (`config/perception-yolov11m.json`, `feat/hailo15l-kalman-tracker`); `not-product-cleared` |
| yolov11s (h15l) | object detection | **AGPL-3.0** (Ultralytics) | ❌ eval-only | `yolov11s_h15l.md` | Hailo model-zoo HEF for Hailo-15L, `fetch_yolov11s_h15l.sh`; YOLO11 A/B detector, same on-chip-NMS output as yolov8m (`config/perception-yolov11s.json`, `feat/hailo15l-kalman-tracker`); `not-product-cleared` |
| yolo26m (h15l) | object detection | **AGPL-3.0** (Ultralytics) | ❌ eval-only | `yolo26m_h15l.md` | Hailo model-zoo HEF for Hailo-15L, `fetch_yolo26m_h15l.sh`; M2's detector (`libyolo26_post.so`, mono engine, `config/perception.json`, `feat/hailo15l-detector`); `not-product-cleared` |

| osnet_x1_0 (h15l) | person re-identification | source MIT per pinned Hailo config; weight/dataset clearance pending | ❌ eval-only | `osnet_h15l.md` | optional Hailo host adapter; `not-product-cleared`; no weight distribution |
| factory CLIP ViT-B/32 (h15l) | experimental object appearance | upstream source MIT; factory HEF/checkpoint/weight/data clearance pending | ❌ eval-only | `clip_h15l.md` | offline host probe only; `not-product-cleared`; no weight distribution |

> The only **ship-eligible** depth model here is `fast_depth`. For metric ranging on this rig, the
> licence-clean **CPU SGBM** stereo path (`services/garuda-camera`) remains the production choice;
> these NPU models are dense priors / evaluation candidates.
