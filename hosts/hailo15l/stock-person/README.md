# Stock masking-detector person-tracking baseline

Implemented 2026-09-11 for the desk demo board. No Garuda tracking or lock logic.
This is an adaptation of Hailo's Detection viewer, not an unchanged masking
pipeline: it reuses DPM's detector/tracker configuration but omits segmentation
and masks and retains the Detection viewer's video/WebSocket output path.

## Source and changes

Upstream: https://github.com/hailo-ai/hailo-media-library, v1.12.0,
commit `9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`.
Apply `person-baseline.patch` directly to that clean checkout; do NOT combine
with the stock-yolo11 patches. Saved patch reverse-check passed against the
compiled source; git diff --check passed. Incremental cross-build succeeded.

The patch changes DetectionPipeline only:

- Calls DPM `base_config()` and `build_dpm_config()` and uses their merged
  tiling configuration, preserving the actual detector/tracker defaults.
- Detector: stock `hailo_yolov8n_384_640.hef`, specialized 4-class model,
  input 640x384, stock specialized decoder and JSON. The shipped HEF reports
  compiler 5.4.0 although installed HailoRT CLI is 5.3.0; it successfully loads
  and produces detections. Do not infer a runtime upgrade from compiler metadata.
- Five tiles, detection every other frame, Hailo tracker predictions between
  detection frames. No segmentation inference or mask processing in Detection.
- Uses DPM's label-filter stage after aggregation to expose only people.
- Adds display-only `Track ID` classification captions after tracking because
  the shipped browser draws classifications but not numeric tracking_id fields.
  The semantic `person` label and actual tracking_id remain unchanged. No web
  asset modifications. Captions are not another classification model.
- Disables Detection's profile-triggered single-tile optimization to retain
  DPM's fixed five-tile layout. Only Daylight was smoke-tested.

## Build and deployment

Current temporary source `/tmp/garuda-stock-yolo11-src`, build directory
`/tmp/garuda-stock-yolo11-build-v1` were reused for compilation. The saved patch
is the durable reproducible change, not the temporary directory name.

```bash
source /media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux
ninja -C /tmp/garuda-stock-yolo11-build-v1 -j4 apps/webserver/camera-viewer-server
```

For a fresh build use the Meson setup options documented in
`../stock-yolo11/README.md` after applying this patch to a clean checkout.

Deployed executable: `/opt/hailo-person/camera-viewer-person-ids`.
SHA256: `6da6da01cbe9f8e3e09452d727043303c2edcae787ea6eccdd1468bfa1cbe72c`.
Working directory `/home/root/apps`; environment
`WEBSERVER_CONSOLE_LOG_LEVEL=info LD_BIND_NOW=1`.
Log `/tmp/stock-person-ids-viewer.log`; PID 1650 at verification.
Manual launch, no boot persistence. HTTP http://10.0.0.1, select Detection/Play.

Original `/usr/bin/camera-viewer-server` and all its masking resources remain
untouched. Original checksum remains
`38153430f73ed98f1a671bb61676c062d4b8bf856c5c160819f87607bfd5ccdc`.
COCO comparison executable `/opt/hailo-yolo11/camera-viewer-compare` is also
unchanged (SHA256 `2f4b612ee70c385f5484cab3e350258a93eefc88b3681ad22b655ed143f278d4`).
Rollback: stop only the verified running test process, then launch either
preserved executable from `/home/root/apps`; for COCO comparison set
`HAILO_COMPARISON_MODEL=yolov8m`. Never run two camera viewers simultaneously.

## Verification

Dynamic loader resolved stock installed libraries; immediate-binding startup
succeeded. Detection endpoint active, Daylight profile, full_performance thermal
state. No error/critical messages found in the new log. Startup identifies the
actual DPM model. No stock system binaries or camera configuration overwritten.

12-second WebSocket smoke test: 360 metadata messages spanning 11.941 seconds.
Sample: 3840x2160 frame, person confidence 0.8602, tracking_id 2, matching
classification caption `Track ID: 2`. This is approximately 30 metadata updates
per second, NOT a measurement of detector inference FPS or fast-motion accuracy.
The stock JS renderer was inspected to confirm it draws these captions; actual
browser playback and fast-motion continuity remain for user testing.

## Large inside-box ID display

User reported captions were invisible: the stock renderer put classifications
below the box, outside the canvas for bottom-clipped people. Added an isolated
webpage copy at `/opt/hailo-person/webpage`. `track-id-badge.js` draws the actual
tracking_id inside the top-left in bold 36 CSS-pixel white text on a dark badge,
clamped to the video canvas. Numeric zero is a valid ID. No tracking changes.

`patch-viewer.cjs` uses apply_patch with exact-match anchors to adapt a copy of
the shipped bundle/index; it rejects other bundle versions. Copy the badge JS
alongside the patched files. Apply `private-webpage.patch` on top of the person
source patch and rebuild to serve this isolated directory. The original web
assets and previous binaries remain unchanged. New binary:
`/opt/hailo-person/camera-viewer-person-big-id`, log `/tmp/stock-person-big-id.log`.
No boot persistence. JS syntax and mocked canvas bounds/ID-zero tests passed.
The page uses versioned script URLs to avoid stale bundle caching; refresh it.
