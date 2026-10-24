# Hailo-15L tracking checkpoint and handoff — 2026-09-11

Later same-day follow-up: [controlled YOLO11 build and actual-device comparison](../bench/results/2026-09-11-yolo11-controlled/README.md)
completed float/quantized/device testing. The controlled HEF improves the
selected phone crops but is slower; later the same evening it **replaced the
live model** (the previous HEF is preserved next to it for rollback; the change
is not boot-persistent). Current live state and consolidated results:
[complete summary](2026-09-11-hailo15l-complete-summary.md). The checkpoint
below retains its original historical deployment details.

## Outcome and boundaries

An isolated, stock-derived YOLO11s experimental pipeline is running on the desk
Hailo-15L SBC. It uses letterboxing with inverse coordinate correction and a
lower candidate confidence floor, retaining strict new-track creation. The
project viewer imports Hailo tracking IDs and exposes separate detector
diagnostics, selection and latched loss. It does not run a second tracker.

**Phone continuity is still poor. This is not a completed robust tracker.**
People and vehicles are the eventual civilian follow-me/camera targets; the
phone is a diagnostic stress test. No flight controller or control output is
connected. No ReID, automatic selected-identity reacquisition or flight-safety
claim. The board remains on HailoRT 5.3.0, not 5.4.

This checkpoint commits the stock-derived viewer family, adapter, research,
diagnostic/replay/recording tools and relevant results. Older custom-node
ROI-assist/tuning changes remain uncommitted and unmodified by this checkpoint.
Do not mistake them for the deployed pipeline. Nothing is pushed remotely.

## History and implementation inventory

1. Stock June 18 VPSP 1.12.0 / IMX678 installation was the starting point for the
   isolated stock-derived builds. The PC app/config backup is at the main
   workspace `.local/board-backups/20260911-stock-baseline/`; it is not a full
   disk backup. See [stock versions/build notes](../hosts/hailo15l/stock-yolo11/README.md).
2. Preserved the successful person masking/tracking-derived baseline, with large
   IDs and private selection bridge. Added the Garuda adapter and embedded local
   viewer. See [person files](../hosts/hailo15l/stock-person/README.md) and
   [adapter history/contract](../services/garuda-tracking/HAILO_BASELINE.md).
3. Bound YOLO11s with COCO labels, 640x640 NV12 input and Hailo postprocessing;
   preserved the person variant. The phone-only release3 was an output filter,
   not a phone-only trained model. See [phone baseline](../hosts/hailo15l/stock-phone/README.md).
4. Diagnostic r1 removed the phone allow-list, emitted empty metadata frames,
   and added an optional protobuf JSON field containing pre-tracker detections,
   detector-ran marker and source timestamp. These are after confidence filtering
   and tile aggregation, not raw tensors or pre-NMS candidates. Adapter release5
   clears cached detections on reconnect and timestamp rewind. See
   [r1 details](../hosts/hailo15l/stock-phone/DIAGNOSTICS.md).
5. R2 changes crop scaling to centered gray-114 letterbox. A per-crop geometry tag
   records exact even-rounded crop/padding geometry; postprocessing reverses it
   before aggregation. Only validated even content/padding geometries are accepted.
   The private low-score config admits scores >=0.15 while track birth stays 0.50
   with class-aware association. Existing confirmation, retention, prediction,
   exposure, model, tiling and cadence remain. This is Hailo tracking, not ByteTrack.
6. Added an opt-in bounded H264 recorder at the existing encoded-output stage,
   with byte offsets and source timestamps. Added capture, exact-join verification
   and timestamp-preserving decode/review tools. See [r2 implementation and limits](../hosts/hailo15l/stock-phone/EXPERIMENT.md).

Native changes are stored as reproducible cumulative patches against
`hailo-ai/hailo-media-library` commit `9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`.
Apply exactly one chosen cumulative variant to a clean upstream checkout; do not
stack phone, diagnostic and experiment patches. The original source checkout
used for compilation is `/tmp/garuda-stock-yolo11-src`; its contents are captured
in `hosts/hailo15l/stock-phone/experiment-r2.patch`, including new helper headers.

## Current deployment

| Component | Current value |
|---|---|
| Board / sensor | Hailo-15L SBC / IMX678 |
| Platform | VPSP 1.12.0, HailoRT/firmware 5.3.0 |
| Native | `/opt/hailo-experiment/r2/camera-viewer-server` |
| Private library | `/opt/hailo-experiment/r2/lib/libhailo_analytics.so.1.12.0` |
| Postprocessor config | `/opt/hailo-experiment/r2/coco-low.json` |
| HEF | `/opt/hailo-yolo11/models/yolov11s_hailo15l_v5.3.0.hef` |
| Adapter | `/opt/garuda-hailo/garuda-hailo-adapter-release5/hailo_adapter.py --port 8099 --target-label all` |
| Project / native viewer | `http://10.0.0.1:8099` / `http://10.0.0.1` |
| Native log | `/tmp/garuda-experiment-r2.log` |
| Adapter log | `/tmp/garuda-adapter-r5.log` |
| Launch working directory | `/home/root/apps` |

Native environment: `LD_LIBRARY_PATH=/opt/hailo-experiment/r2/lib`,
`LD_BIND_NOW=1`, `WEBSERVER_CONSOLE_LOG_LEVEL=info`, `GARUDA_LETTERBOX=1`,
`GARUDA_LOW_SCORE=1`, `GARUDA_RECORD_ENABLE=1`. Activate Detection, refresh the
browser and press Play after a native restart. Native assets are reused read-only
from `/opt/hailo-diagnostics/r1/webpage`. No boot persistence was added.

Observed native PID was 30247; never act on that number without checking its
current executable. Only one native camera/NPU viewer can run at once.

### Immutable identifiers

- YOLO11s HEF: `24a050fb0fa4c8cba12489d2275c784b2298be3c7632a96496116b185ff31296`.
- R2 native: `8d24c6b09a7a0163be6816c2c65a36a9e7882fb0535186adebb9a31be96eb264`.
- R2 library: `a6ce4c9b3c87da9e3b819fbf8cd74bbbcc10e710e0c50feed6cb3502f41d6aa2`.
- Preserved r1 native: `4187374059997bd58c152fcf405dc9d3f5320019374f19194d5ffca3ee9b782f`.
- Original vendor native: `38153430f73ed98f1a671bb61676c062d4b8bf856c5c160819f87607bfd5ccdc`.

## Image path and binning discussion

Verified current path: **3840x2160 capture -> 1920x1080 AI stream -> five 640x640
inference inputs**. Four crops span 60% of each AI dimension; one is full-frame.
Cropping the already-downscaled AI stream does not restore original 4K detail.
Letterboxing preserves aspect ratio, not lost information. At the same 640-wide
input, a 16:9 full view occupies 640x360 content plus padding.

The user proposed 1280x736. No such mode was applied. Preserving the 16:9 full
view at that canvas size would mean 1280x720 content plus 8 rows above and below.
The present HEF still accepts 640x640; 1280x736 network input requires a matching
compiled model. Reducing the AI stream further does not inherently improve detail.

[Sony's color IMX678 flyer](https://www.sony-semicon.com/files/62/flyer_security/IMX678-AAQR_AAQR1_Flyer.pdf)
lists 2/2-line binning to 1920x1080. Local SDK IMX678 sensor source has a
1920x1080/30 linear mode (index 1), but its kernel register configuration was
**not verified as binning rather than cropping**. Only a 4k imaging profile
directory was observed in the installed lens configuration. No sensor registers,
sensor mode or ISP profile were changed for this investigation.

Binning may alter noise/bandwidth behavior but is not guaranteed to preserve
more detail than well-filtered resizing. Direct 4K crops before resize are a
separate small-object experiment, not implemented here.

## Evidence and conclusions

| Test | Result | What it does not prove |
|---|---|---|
| Adapter tests | 16 passed | Live tracking accuracy |
| Paired saved full-frame images, 7 fully inside | Stretch 0/7 vs letterbox 3/7 at 0.15; 0/7 vs 1/7 at 0.38, IoU >=0.5 | General recall, motion quality, false-positive rate |
| Tracker contract on board | Weak 0.20 scores cannot start tracks; maintain confirmed ID across 12 updates | Identity robustness with distractors/occlusion |
| DSP pixel checks | Expected batched padding for 1920x1080, 1152x648, 1280x720, 640x640 | Detector/model correctness |
| Browser | Video click and person ID-card click select ID 2 with blue outline | Flight/control lock or permanent identity |
| R2 motion recording | Seven phone IDs; person ID 2 in all 782 exact-matched frames; additional person ID 151 in 7 | Reliable phone continuity or fully validated person tracking |

The paired probe initially crashed with heap corruption while built against
headers copied from the earlier board software. Rebuilding against matching SDK
headers allowed both passes to finish. Failed logs are retained. A replay restore
attempt initially timed out before viewer startup completed; Detection was restored
manually, and the runner's startup allowance was increased. These failures were
test-tool/build issues, not established explanations of the original tracking fault.

R2 phone video: 900 indexed encoded units, 865 decoded frames (35–899), 782 exact
metadata matches and 118 unmatched units. Within matched units, 146/332 marked
detector updates contained a phone. This ratio is **not recall** without complete
ground truth. Reviewed frame 360 visibly contains the phone but has no phone
detection at the current floor. Frame 630 has a phone detection at 0.563 but no
confirmed phone track. Both detector-output gaps and confirmation/track gaps
therefore remain observable. See [recording report](../bench/results/2026-09-11-yolo11-experiment/r2-phone-motion/README.md).

The separate raw-box position map is explicitly not synchronized video. Native
track boxes may include predictions. Source timestamps are preserved, but no
source-to-host clock mapping exists: metadata rate is not inference FPS and
host arrival age is not camera latency. Empty native frames are implemented and
unit tested, but a genuinely empty-scene live test is still outstanding.

## Rebuild and verification commands

Use the matching installed SDK and a clean upstream checkout plus the selected
patch. Native Meson setup/build commands are in the stock build notes linked above.
Build and deploy both the webserver and matching private analytics library.
Never overwrite `/usr/bin/camera-viewer-server` or existing baseline directories.

```bash
bash hosts/hailo15l/stage_hailo_adapter.sh /tmp/garuda-stock-yolo11-src /tmp/garuda-hailo-adapter-release5
HAILO_DESCRIPTOR=/tmp/garuda-hailo-adapter-release5/analytics_metadata.desc \
PYTHONPATH=/tmp/garuda-hailo-adapter-release5/vendor \
python3 -m unittest discover -s services/garuda-tracking/tests -p test_hailo_adapter.py
node --check services/garuda-tracking/hailo_viewer.js

source /media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux
cmake -S bench/hailo_reference -B /tmp/garuda-reference-build \
  -DCMAKE_TOOLCHAIN_FILE=$OECORE_NATIVE_SYSROOT/usr/share/cmake/OEToolchainConfig.cmake \
  -DHAILO_BOARD_HEADERS=
cmake --build /tmp/garuda-reference-build --target hailo-preprocess-probe -j4
```

For the two hardware contract programs, use the SDK compiler with the patched
analytics include directory. Link `experiment_contract_test.cpp` with `-lhailopp`;
link `letterbox_pixels_test.cpp` with `-lmedialib -lhailodsp` and add SDK
`usr/include/hailo`. Copy the resulting ARM executables to a unique board test
path and run them. The helper header comes from the cumulative experiment patch.

`compare_preprocessing.py` pauses only a verified r1 diagnostic native; it is
**not an r2 launcher**. Historical `bench/hailo_reference/run.py` targets an older
custom stack and must not be used on the current deployment. Prepared original
NV12 replay input lives at `/tmp/garuda-roi-replay-20260911`; it is not in Git.
Its hashes are recorded in the paired-test run manifest.

## Recording, artifacts and recovery

`capture_experiment.py STAGED_ADAPTER NEW_OUTPUT_DIR` starts metadata capture,
requests a bounded encoded recording, downloads it and verifies exact joins.
`verify_recording.py VIDEO_DIR METADATA_JSONL` checks continuity, bounds and codec
headers. `inspect_recording.py VIDEO_DIR NEW_REVIEW_DIR` uses system Python,
GStreamer/gi and Pillow to decode with source timestamps and save review samples.

Both capture slots in the current r2 process are exhausted. Restart the verified
r2 native before another capture. Limits are 900 frames or 64 MiB per capture,
two per process and a 256 MiB free-space admission guard. Encoded recording can
begin before an IDR; keep five seconds of stationary pre-roll. Missing metadata
is never nearest-time substituted. Synchronous diagnostic writes may affect timing.

The ~120 MB of H264 camera media and review JPEGs stay local and are ignored by
Git. [Artifact manifest](../bench/results/2026-09-11-yolo11-experiment/artifacts.json)
records sizes, hashes and relative locations. Metadata and compact evidence are
committed. Board `/tmp` files can disappear at reboot; downloaded PC copies are
the retained artifacts. Do not treat Git alone as a backup of video or models.

For rollback, check the current native process executable, stop only that
process, then launch `/opt/hailo-diagnostics/r1/camera-viewer` from `/home/root/apps`
with `LD_LIBRARY_PATH=/opt/hailo-diagnostics/r1/lib`, `LD_BIND_NOW=1` and the usual
log setting, without experiment switches. Activate Detection and refresh/play.
Release5 adapter can stay running. Earlier person/phone rollback instructions
remain in their respective documents. Source-session change requires reselection.

## Open work / do not claim complete

- Inspect and retain actual five model-input NV12 crops, not just encoded video.
- Isolate preprocessing, quantized model, NMS/tile merging and tracker effects
  using identical saved inputs; run letterbox-only and threshold-only ablations.
- Test negatives, full occlusion, re-entry, small/distant people and vehicles,
  moving camera and labelled aerial footage. Annotate physical identity.
- Verify whether the available sensor FHD mode uses binning and whether suitable
  Hailo ISP calibration exists before any sensor-mode change.
- Investigate direct-4K cropping and resizing filter quality; do not assume
  downscaling or black phone color alone explains failures.
- Stabilize sidebar card positions; diagnostic rows currently shift controls.
- Validate timestamps/latency and prediction uncertainty before any control use.

The [deep research report](research/2026-09-11-aerial-detection-tracking.md) supplies
the broader technical rationale and primary-source references. Its initial
observations predate the r1/r2 measurements; this checkpoint supersedes its
statements that no detector trace or paired preprocessing experiment existed.

## Commit-time verification

Re-ran all 16 adapter tests, Python compilation, viewer JavaScript and stage-script
syntax checks, and the recorded-motion integrity verifier. Exported the staged
Git index to a clean temporary directory and cross-built `hailo-preprocess-probe`
successfully, without the older unstaged ROI changes. The cumulative r2 native
patch reverse-applies cleanly to the build source. Whitespace checks pass for
non-patch files; unified patch context includes required space-only blank lines
and is validated by patch applicability rather than stripping those prefixes.
No live camera configuration was changed during documentation/commit work.
