# Hailo-15L YOLO11 tracking work — complete summary

Date: 2026-09-11

This document consolidates the Hailo-15L desk-demo work completed so far. The
eventual use case is civilian follow-me/camera tracking for people and vehicles.
There is no flight controller connected and no flight-control output is enabled.

## Starting point

- Board: Hailo-15L SBC with IMX678 camera.
- Stock image: June 18 VPSP 1.12.0.
- Board HailoRT/firmware: 5.3.0.
- Camera capture: 3840x2160.
- Existing AI stream: 1920x1080, then five 640x640 inference inputs.
- Existing model: stock-derived YOLO11s Hailo HEF, 80 COCO classes, NV12
  640x640 input. Original live-model SHA256 before replacement:
  `24a050fb0fa4c8cba12489d2275c784b2298be3c7632a96496116b185ff31296`.
- Existing viewer: Garuda R2 experimental stock-derived viewer with letterbox
  option, low candidate floor, diagnostics, Hailo tracker and browser adapter.

The old phone problem was: detections disappeared during fast movement, phone
track IDs changed after leaving/re-entering the frame, and tracking could not be
declared robust. Person detection was substantially better than phone detection.

## Changes already made before the model rebuild

The earlier R1/R2 work added and verified:

- Full COCO labels instead of a phone-only allowlist.
- Letterbox preprocessing and inverse coordinate mapping.
- DSP crop/resize tests for 1920x1080, 1152x648, 1280x720 and 640x640.
- Detector diagnostics separated from actual tracker state.
- Postprocessed snapshots before aggregation/tracking.
- Empty-frame handling, timestamp validation, reconnect cache clearing and
  latched selection loss behavior.
- Browser selection and ID-card selection paths.
- Bounded H264 recording with exact timestamp sidecar joins.
- Existing Hailo tracker defaults were preserved; no ByteTrack or ReID was added.

The primary earlier checkpoint is [2026-09-11-hailo15l-checkpoint.md](2026-09-11-hailo15l-checkpoint.md).

## 4K tiling investigation

The question was whether shrinking 4K to 1080p loses too much detail for small
objects. A saved 3840x2160 H264 phone-motion recording was replayed on the
board using identical selected frames (90, 360 and 630).

Treatments:

1. Current approximation: DSP 4K -> 1920x1080, then the current five tiles.
2. Native 4K sliding window: 32 overlapping 640x640 source crops, stride 512.
3. Oracle-centered 4K crops: 640, 960 and 1280 square crops around the manually
   reviewed phone position, each resized to 640.

Result: blind native 640 tiling detected the phone in none of the three reviewed
frames. Centered 1280 crops detected two of three. Therefore retaining source
pixels helps only when crop scale, context and object containment are suitable;
blind tiling is not a complete solution. The phone was large enough that no
640 grid tile fully contained it.

Results: [4K tile replay](../bench/results/2026-09-11-yolo11-4k-tiles/README.md).

## Detector-path investigation

The same DSP-produced NV12 buffers were copied immediately before Hailo
inference. The published Hailo Model Zoo YOLO11s ONNX was downloaded and run
with ONNX Runtime, then compared with DFC 5.3 floating-point emulation.

Important finding: ONNX and DFC floating-point outputs agreed closely (maximum
matched phone-score difference about 0.0023). On one identical 960 crop, the old
HEF produced phone confidence 0.14 while software produced about 0.78. This
showed that the issue was not simply tracker logic.

The DFC source also documents explicit YUV conversion choices. The controlled
build used full-range YUV conversion plus NV12 format conversion with emulation
enabled. The old HEF's original source weights and build recipe were not
available, so the exact reason for the old HEF discrepancy cannot be attributed
to one setting with certainty.

Detailed report: [YOLO11 float/device input check](../bench/results/2026-09-11-yolo11-float-check/README.md).

## Controlled model build

Source model:

- Hailo Model Zoo YOLO11s ONNX from the published 2024-10-02 archive.
- ONNX SHA256:
  `0a44c5050d77a27abb971979e8399ab6084db18b0ffc7781e312171543efef8e`.

Build controls:

- DFC 5.3.0, Hailo-15L target.
- Explicit full-range YUV-to-RGB path.
- NV12 format conversion with emulator support enabled.
- 1,024 unique SUNRGBD indoor images for calibration, separate from held-out
  phone crops.
- Optimization level 2, compression level 0, batch size 1.
- QAT/finetuning disabled because of the 6 GB host GPU limit.
- NMS: score floor 0.05, IoU 0.70, 80 classes, 100 proposals/class.

Retained stages:

- `parsed.har`
- `fp.har`
- `quantized.har`
- `compiled.har`
- `controlled.hef`

The floating-point DFC model matched ONNX. Quantized emulation retained or
improved the selected phone scores, including the difficult 960 crop.

Detailed build report: [controlled YOLO11 build](../bench/results/2026-09-11-yolo11-controlled/README.md).

## Actual board result

The controlled HEF was compiled and tested on the physical Hailo-15L using the
same saved inputs. It was not installed until after the isolated replay passed.

Controlled HEF:

- SHA256: `aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58`.
- Hailo-15L, compiler 5.3.0, NV12 640x640, 80-class NMS.
- Uses 11 contexts versus 8 in the previous HEF.

Selected centered-crop results:

| Source frame/crop | Old HEF | Controlled HEF on board |
|---|---:|---:|
| 90 / 960 | 0.140 | 0.852 |
| 360 / 960 | no match | 0.540 |
| 630 / 960 | 0.658 | 0.894 |

The current five-tile approximation changed from 1/3 reviewed examples at the
0.15 candidate floor to 2/3. The difficult frame is still not reliable with
that preprocessing. These are sparse detector examples, not recall, tracking,
identity persistence or flight benchmarks.

Runtime replay waits also increased: approximately 18.3 ms to 23.8 ms for one
centered crop, and approximately 94–96 ms to 122–124 ms for five inputs. These
are sequential replay waits excluding transport and are not live FPS.

## Current live state

The controlled HEF is now live on the board at:

`/opt/hailo-yolo11/models/yolov11s_hailo15l_v5.3.0.hef`

Current live hash:

`aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58`

The previous HEF is preserved for rollback at:

`/opt/hailo-yolo11/models/yolov11s_hailo15l_v5.3.0.hef.20260911-controlled-yolo11`

Current viewer:

- `/opt/hailo-experiment/r2/camera-viewer-server`
- Current observed PID: 12079.
- Detection pipeline active.
- Camera/ISP profile unchanged.
- Adapter reports live metadata, 3840x2160 frame size, no diagnostic/source
  errors.
- Browser selection state resets after restart; manually reselect the target.

The live model replacement was a board-side change, but it is reversible using
the preserved HEF and a viewer restart. It is not boot-persistent configuration.

## Project files added in this work

Diagnostic/replay tools under `bench/hailo_reference/` include:

- `prepare_4k_tiles.py`, `run_4k_tiles.py`, `score_4k_tiles.py`
- `float_input_check.py`
- `build_controlled_yolo11.py`
- `score_controlled_yolo11.py`
- `collect_controlled_evidence.py`
- Unit tests for geometry, color conversion and controlled-model handling.

Generated evidence is under:

- `bench/results/2026-09-11-yolo11-4k-tiles/`
- `bench/results/2026-09-11-yolo11-float-check/`
- `bench/results/2026-09-11-yolo11-controlled/`

Large model, calibration and private pixel artifacts remain outside the Git
repository or are ignored. No private camera data was uploaded.

## Verification status

Completed:

- Physical Hailo-15L replay with controlled HEF.
- Float and quantized DFC emulation.
- HEF parse and hash verification.
- Exact DSP input-buffer capture and byte-equality checks.
- 11 local unit tests.
- Python syntax checks.
- `git diff --check`.

Not completed:

- Broad annotated test set for people, vehicles and phones.
- Continuous fast-motion live benchmark.
- Identity persistence through long occlusion or re-entry.
- ReID or appearance embedding.
- Production allocation/performance tuning.
- Sensor binning verification or a new 1280x736 HEF.
- Flight-controller integration.

## Recommended next step

Use the new model in a short reversible live A/B test while measuring detector
latency, missed detections and track continuity. Add scale-aware contextual ROI
crops around the selected person/vehicle, retain full-view discovery for
reacquisition, and compare against the current five-tile path. Do not claim
robust follow-me behavior until a longer annotated fast-motion test passes.

The key conclusion is: the old HEF had a real detector-path weakness on the
captured inputs, and the controlled rebuild improves it on hardware. Tiling and
tracking remain separate engineering problems.

## Follow-up 2026-09-12 — sequence A/B replay completed

The recommended A/B was run on the recorded phone-motion video: 433 frames
(every 2nd decodable frame, matching live detector cadence), five tiles each,
both HEFs on the physical board over identical bytes. Phone frames at the 0.15
floor: 44.1 % → 74.4 % (paired: 133 frames gained, 2 lost); longest detection
hole 2.9 s → 0.5 s; cost ~29 % more sequential detector wait. At the 0.50
track-birth floor a ~3.1 s worst gap remains, so tracker coast/re-acquire is
now the binding constraint. Full results and caveats:
[A/B replay](../bench/results/2026-09-12-yolo11-ab-replay/README.md).
