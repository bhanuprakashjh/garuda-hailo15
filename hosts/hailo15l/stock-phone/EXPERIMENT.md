# Isolated YOLO11 letterbox / low-score experiment (r2)

2026-09-11. Running locally at http://10.0.0.1:8099 with adapter release5.
This is a civilian desk-camera experiment, not validated flight tracking.

## Changes

The native process is `/opt/hailo-experiment/r2/camera-viewer-server`, launched
from `/home/root/apps` with:

```
LD_LIBRARY_PATH=/opt/hailo-experiment/r2/lib
LD_BIND_NOW=1
WEBSERVER_CONSOLE_LOG_LEVEL=info
GARUDA_LETTERBOX=1
GARUDA_LOW_SCORE=1
GARUDA_RECORD_ENABLE=1
```

Private analytics library symlink `.so.1` targets `.so.1.12.0`. The original
stock executable, r1 diagnostic binary/library, prior phone/person builds,
camera configuration and adapter release5 remain unchanged. Native web assets
are reused read-only from `/opt/hailo-diagnostics/r1/webpage`. No boot persistence.

- Letterbox: centered NV12 padding Y=114/U=128/V=128. Each crop carries its exact
  padding geometry. Postprocessing removes padding and maps boxes back to the
  actual even-rounded source crop **before** aggregation and tracking.
- Only exact even content/padding geometries are accepted. Unvalidated rounding
  cases fail rather than silently producing incorrectly mapped boxes. Current
  1920x1080, 1152x648 tiles and 640x640 model inputs satisfy this constraint.
- Low-score mode: NPU candidate floor and postprocessor threshold 0.15; new-track
  threshold 0.50; class-aware matching enabled. Tracker confirmation, retention,
  prediction, model, five-tile layout, every-other-frame cadence and exposure
  unchanged. This uses Hailo association, not a replacement ByteTrack algorithm.
- Both environment switches can be omitted independently for controlled ablations.
  Postprocessor config is private: `/opt/hailo-experiment/r2/coco-low.json`.

Current image path is 3840x2160 camera -> 1920x1080 AI stream -> five 640x640
inference inputs. Four tiles cover 60% of each AI dimension; one covers the full
AI frame. These are not full-detail 4K crops. Letterboxing preserves shape, not
lost detail. Direct-4K cropping is a separate future small-target experiment.

## Reproduce and rollback

Apply `experiment-r2.patch` to clean hailo-media-library commit
`9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`; it is cumulative, not an incremental
patch over r1. Build webserver plus analytics with the matching VPSP 1.12 SDK.
The patch includes the two new helper headers. Reverse-apply check passed.
Do not use header copies from the previous board image.

Native SHA256: `8d24c6b09a7a0163be6816c2c65a36a9e7882fb0535186adebb9a31be96eb264`.
Library SHA256: `a6ce4c9b3c87da9e3b819fbf8cd74bbbcc10e710e0c50feed6cb3502f41d6aa2`.
Deployment PID observed: 30247, log `/tmp/garuda-experiment-r2.log`.
Never reuse an observed PID without checking its `/proc/PID/exe` first.

For rollback, stop only the verified r2 native and launch the preserved r1
native using its own private library path, as documented in DIAGNOSTICS.md.
Activate Detection and refresh/play the browser. Adapter need not be replaced.
Selection is invalidated across source sessions; select explicitly again.

## Tests and observations

- Cross-build and private-library loader resolution passed; no error/critical
  entries in the deployment log. Stock and r1 native hashes verified unchanged.
- `bench/hailo_reference/experiment_contract_test.cpp` passed on the board:
  inverse mapping for landscape/portrait/square inputs, padding-only box
  rejection, rejection of unvalidated rounding, weak scores cannot start tracks,
  and 12 weak updates maintain an existing confirmed track with the same ID.
- `letterbox_pixels_test.cpp` passed on the actual batched DSP resize path for
  1920x1080, 1152x648, 1280x720 and 640x640. All output Y-plane pixels matched
  expected content and padding regions. This does not establish model accuracy.
- Browser refreshed and playback resumed. Person/phone boxes appeared aligned.
  This is a visual smoke test, not a quantitative localization evaluation.
- Forty-second metadata smoke: 1069 messages, 469 marked detector frames,
  zero timestamp-alignment mismatches, repeats or timeouts; max host arrival
  gap 89.75 ms. Phone detections appeared on 160 detector frames. Uncontrolled
  motion means these counts cannot be compared as accuracy against earlier runs.

## Source-timestamped recording

Opt-in recorder copies encoded H264 access units at the existing `sink0_udp`
stage. A sidecar records byte offsets, lengths and encoder-buffer source
timestamps. Trigger: `/tmp/garuda-r2-record.request`. It creates a unique
`/tmp/garuda-r2-record.XXXXXX` directory, never overwrites captures, and consumes
the request marker. Limits: 900 frames or 64 MiB per capture, two per native
process, 256 MiB free-space admission check. Recording is not continuous by
default. Temporary captures survive until removal or reboot; downloaded copies
are under the project results directory.

Smoke video: 900 indexed access units, 59,926,141 bytes; GStreamer H264 decode
completed successfully. 818 units matched metadata by **exact source timestamp**;
82 had no metadata match and must remain unlabelled/missing, not interpolated.
First SPS/IDR occurred at frame 34, so preceding units may not decode. Allow a
five-second stationary pre-roll. This is encoded 4K video, not original NV12,
and does not permit an exact pre-ISP or pre-compression model comparison.
Synchronous diagnostic writes can affect timing; report cadence during capture.

Evidence: `bench/results/2026-09-11-yolo11-experiment/r2-smoke/`.
Both per-process capture slots are now used (smoke plus phone movement test).
Restart the verified r2 process before requesting another recording.
`bench/hailo_reference/capture_experiment.py STAGED_ADAPTER NEW_OUTPUT_DIR`
captures metadata, requests video, downloads it and validates timestamp joins.
Start only after the user is ready. Verification requires a completed 900-frame
capture; truncated or byte-limited recordings are deliberately rejected.

## Still required

Controlled stationary/sideways/rotation repeat with video; manual annotations
and distractor/empty-scene evaluation; separate letterbox-only and low-score-only
ablations; person/vehicle distance, occlusion and moving-camera trials. No claim
of improved robustness or safe flight performance has been established yet.
