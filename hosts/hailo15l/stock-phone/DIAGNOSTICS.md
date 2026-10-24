# YOLO11 diagnostic milestone — 2026-09-11

This is a desk diagnostic build, not validated drone tracking. Local project:
http://10.0.0.1:8099. Refresh the page after the adapter update.

## Deployed

Apply `diagnostics-r1.patch` to clean hailo-media-library commit
`9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`, not on top of `phone-baseline.patch`.
Build the webserver and analytics shared library with the matching VPSP 1.12 SDK.
The patch includes the previous YOLO11 adaptation and the diagnostic changes.

- Native: `/opt/hailo-diagnostics/r1/camera-viewer`;
  SHA256 `4187374059997bd58c152fcf405dc9d3f5320019374f19194d5ffca3ee9b782f`.
- Private library: `/opt/hailo-diagnostics/r1/lib/libhailo_analytics.so.1.12.0`;
  SHA256 `095027309bf6358a11c384ca1ec76faa62d448a97e606cb73def18e37e1e6e38`.
  Launch with `LD_LIBRARY_PATH=/opt/hailo-diagnostics/r1/lib` and `LD_BIND_NOW=1`
  from `/home/root/apps`. Symlink the library as `libhailo_analytics.so.1`.
- Adapter: `/opt/garuda-hailo/garuda-hailo-adapter-release5/hailo_adapter.py`
  with `--port 8099 --target-label all`.
- Private native assets: `/opt/hailo-diagnostics/r1/webpage`.
- Activate Detection using PATCH `/ai_pipeline`, `{"active":"Detection"}`.

One native viewer at a time. Resolve exact processes before stopping them.
Original stock executable, person baseline, phone baseline and earlier adapter
releases are preserved. No boot persistence was added. Rollback uses the
baseline launch instructions in README.md, without the private library path.

## What changed

Native metadata now emits empty frames rather than treating zero detections as
missing transport. An additive protobuf string field carries pre-tracker boxes,
a detector-ran marker and the source timestamp. This is **after postprocessing,
confidence filtering and tile aggregation**, not raw network tensors. Live
threshold remains 0.38. All COCO classes pass through to the adapter.

The sidebar separates detector boxes from tracks in a position map explicitly
labelled as not synchronized video. It is not a synchronized overlay or proof
of end-to-end latency. The Sites workflow retained the existing local layout;
no cloud publication or browser visual QA was performed.

Reconnect and timestamp rewind invalidate cached detector samples. Repeated
timestamps do not refresh freshness. Lost selection remains latched; there is
no automatic identity reassignment, ReID or valid control output.

## Verification

Cross-build, loader check, reverse-patch check, JavaScript syntax and 16 adapter
tests passed. Tests cover empty-frame continuity, malformed diagnostics,
timestamp/session changes, stale data, selection and latched loss. Live direct
WebSocket evidence is under `bench/results/2026-09-11-yolo11-diagnostics`.
Empty-scene native behavior still needs an actual empty-scene test; unit tests
and source inspection alone do not establish that live scenario.

## Paired preprocessing result

`bench/hailo_reference/compare_preprocessing.py` runs the same saved NV12 frames
and same YOLO11s HEF through DSP stretch and centered gray-114 letterbox, with
the same 0.05 candidate floor. Scoring reverses each transform independently.
Output: `preprocessing-sdk/{stretch,letterbox}-score.json` in the results folder.

For seven fully-inside annotated full frames (IoU >= 0.5):

| Preprocessing | Matches at confidence 0.15 | Matches at 0.38 |
|---|---:|---:|
| Stretch | 0/7 | 0/7 |
| Letterbox | 3/7 | 1/7 |

The eighth, clipped frame had no match in either mode. Other rows use
oracle-centered square crops; they are not adaptive-tracker results. Square
crop scores agreed between modes. These sparse annotations are not a motion
benchmark, a false-positive study or an estimate of deployment accuracy.

The first two attempts crashed with heap corruption. Rebuilding with the
matching SDK headers (`-DHAILO_BOARD_HEADERS=`), instead of headers copied from
the earlier board software, allowed both 32-input passes to finish. The failed
logs are retained. Automatic viewer restoration initially timed out before
startup completed; Detection was manually reactivated and live metadata
verified. The runner now allows a longer bounded startup interval.

## Remaining gates

1. Capture original continuous motion frames with synchronized detector/tracker
   metadata, including stationary, sideways motion, rotation and empty scenes.
2. Validate live letterbox inverse mapping before any live preprocessing switch.
   The paired result supports testing it, not calling it a complete fix.
3. Compare low-score association separately from high-score track birth, on a
   frozen detection sequence with distractors and occlusion. Do not interpret
   predicted boxes as new detector measurements.
4. Evaluate bounded prediction, camera-motion compensation and reacquisition
   using labelled trajectories; never silently change selected identity.
5. Compare exposure/cadence under controlled lighting, then labelled moving-camera
   and aerial footage. No robust flight-use claim until these tests pass.

Live tracker defaults, exposure, tiling and inference cadence have not been
tuned in this milestone. Completing these gates requires additional recorded
sequences, not further conclusions from the seven still images.
