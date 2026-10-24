# Hailo stock-based YOLO11 baseline

This is a minimal adaptation of Hailo's stock camera viewer, not an unmodified
vendor-shipped YOLO11 application. No Garuda association or lock layer is used.

## Versions and recovery

- Board: Hailo-15L SBC, IMX678, stock June 18 VPSP 1.12.0 image.
- HailoRT and firmware: 5.3.0 (not 5.4).
- Source: https://github.com/hailo-ai/hailo-media-library, tag v1.12.0,
  commit `9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`.
- Model: `yolov11s_hailo15l_v5.3.0.hef`, SHA256
  `24a050fb0fa4c8cba12489d2275c784b2298be3c7632a96496116b185ff31296`.
- Model parse: HAILO15L, compiler 5.3.0, NV12 640x640, 80 classes,
  eight contexts; embedded NMS score 0.20 and IoU 0.70.
  The model's `yolov8_nms_postprocess` output name is not its model version.
- Original `/usr/bin/camera-viewer-server` is preserved. Adapted files are
  isolated under `/opt/hailo-yolo11`. Run either viewer from `/home/root/apps`,
  never both at once (shared camera, accelerator and HTTP port).
- Preflash PC backup: main workspace `.local/board-backups/20260911-stock-baseline/`.
  `board-apps-camera-config.tar.gz` SHA256
  `c141095a5031d522f61adad30b4f5b935d90a1b7bf3f029d283d6086230216a4`.
  This is an app/config backup, not a full disk image.

## Scope

`yolo11-binding.patch` changes only the detector HEF binding, 640x640 crop output,
generic Hailo NMS decoding and COCO label map, plus a model log message.
`coco-postprocess.json` preserves stock postprocessing threshold 0.38 and
max_boxes 10000, changing the class list to COCO. Embedded HEF NMS remains
model-specific. Stock tiling uses stretch resizing, not YOLO letterboxing.

Camera/ISP profiles, exposure controls, five-tile Daylight layout, every-other-frame
cropping, scheduling and Hailo tracker defaults are preserved. Metadata message
rate is not detector inference FPS; tracked or repeated detections can be sent
at camera rate. Fast-motion accuracy requires a separate controlled test.

## Rebuild

Apply the patch to a clean checkout at the exact source commit, then:

```bash
source /media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux
meson setup /tmp/garuda-stock-yolo11-build-v1 /tmp/garuda-stock-yolo11-src/hailo-analytics --buildtype=release --prefix=/usr -Dplatform=15l -Dapps_install_dir=/home/root/apps -Dbuild_case_studies=false -Dbuild_vlm_event_monitor=false -Dbuild_verification=false
ninja -C /tmp/garuda-stock-yolo11-build-v1 -j4 apps/webserver/camera-viewer-server
```

Copy the executable and COCO config into `/opt/hailo-yolo11/`, and the HEF into
`/opt/hailo-yolo11/models/`. Validate dynamic dependencies before switching.
The viewer serves port 80. Select Detection and Play in Chrome.

`check-metadata.cjs` reads 12 seconds of stock WebSocket metadata without video
recording. Pass board IP, host SDK protoc executable, and the stock protobuf
directory. It prints message count and the largest frame's decoded metadata;
this is a smoke test, not a tracking quality benchmark.

## Verified deployment — 2026-09-11

Build completed for AArch64. Board loader resolved all dependencies using stock
installed libraries; `LD_BIND_NOW=1` startup succeeded without private libraries.
Adapted binary SHA256:
`62e07101f12783e56365b29fdcad0c6a6b6776b0243234412626991db958ea48`.
Original stock executable SHA256 before and after switching:
`38153430f73ed98f1a671bb61676c062d4b8bf856c5c160819f87607bfd5ccdc`.

Active executable `/opt/hailo-yolo11/camera-viewer-server`, PID 859 at verification.
HTTP `/ai_pipeline` reports Detection; profile Daylight. Startup log explicitly
identifies the YOLO11s HEF; no startup error/critical messages found.
Log: `/tmp/stock-yolo11-viewer.log`. This is a manual launch, not boot persistence.

Read-only metadata smoke test: 315 messages spanning 11.925 seconds. Largest
sample: 3840x2160 frame, person confidence 0.8363 ID 1, chair 0.4011 ID 8,
cell phone 0.4815 ID 9. This verifies live detections and assigned tracker IDs,
not sustained phone-track quality or inference FPS. Browser playback and fast
movement remain for the user to assess. Board clock reset to March 2018 after
flashing; dates inside runtime logs do not represent the PC test date.
