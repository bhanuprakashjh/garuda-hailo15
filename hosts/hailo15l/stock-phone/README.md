# YOLO11 phone mode — local desk demo

2026-09-11. Project URL: http://10.0.0.1:8099. Native viewer: http://10.0.0.1.
This is a model adaptation of the accepted person baseline, not an unchanged
vendor application. No flight controller, ReID or control output is connected.

## Reproduce

Apply `phone-baseline.patch` to a clean hailo-media-library v1.12.0 checkout,
commit `9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`. It includes both the native
pipeline and private web asset mount. Do not combine with the person or older
YOLO11 patches. Build using the SDK/Meson instructions in ../stock-yolo11/README.md.

Relative to the working person pipeline, only detector/model-dependent settings
change: YOLO11s Hailo15L HEF, 640x640 crops, COCO postprocessor/labels, and an
output allow-list of `cell phone`. Five tiles, every-other-frame detection,
Hailo tracker defaults and the existing aggregation path remain. Segmentation
is not run. Tracker metadata can include predictions, not just new detections.

Model: `/opt/hailo-yolo11/models/yolov11s_hailo15l_v5.3.0.hef`
SHA256: `24a050fb0fa4c8cba12489d2275c784b2298be3c7632a96496116b185ff31296`.
Postprocessor: `/usr/lib/hailo-post-processes/libyolo_hailortpp_post.so`, `filter`.
Config: `/opt/hailo-yolo11/coco-postprocess.json`, threshold 0.38, 81 labels
including unlabeled. These model/config files already existed on the board.

Native binary: `/opt/hailo-phone/camera-viewer-phone`
SHA256: `7327b6b1853628dc72fc79ce5f9786d69fbe64d0e25b3c373d0a77ac30c24580`.
Private assets `/opt/hailo-phone/webpage` are copied from the accepted
`/opt/hailo-person/webpage`, including large IDs and the corrected click layer.
Their class-agnostic bridge retains its historical `garuda-person-click` name.
The original vendor and person assets remain untouched.

Adapter: `/opt/garuda-hailo/garuda-hailo-adapter-release3/hailo_adapter.py`
with `--port 8099 --target-label 'cell phone'`. The default is still `person`.
Stage using hosts/hailo15l/stage_hailo_adapter.sh. Metadata filtering, title and
cards follow target_label. Click selection and latched loss are unchanged.

## Launch and rollback

Only one native camera viewer may run. Resolve and stop only the verified
current native/adapter processes before launching replacements. No boot
persistence was added; process IDs below are observations, not restart scripts.

From `/home/root/apps`, launch native with `WEBSERVER_CONSOLE_LOG_LEVEL=info
LD_BIND_NOW=1`, then adapter with the arguments above. Select Detection at
`/ai_pipeline` using PATCH JSON `{"active":"Detection"}`. Press Play in the UI.
Native PID at deployment 20140, log `/tmp/stock-phone-viewer.log`.
Adapter PID 20141, log `/tmp/garuda-hailo-phone.log`.

To restore the accepted person baseline, stop the verified phone native and
release3 adapter; launch `/opt/hailo-person/camera-viewer-person-big-id` from
`/home/root/apps` with the same environment, then run
`python3 /opt/garuda-hailo/garuda-hailo-adapter-release2/hailo_adapter.py --port 8099`.
Activate Detection and refresh the project page. Person binary/assets/release2
were preserved, not overwritten. Stock `/usr/bin/camera-viewer-server` unchanged.

## Validation and limits

Incremental cross-build, dynamic loader check, reverse patch check, JS syntax,
and 13 adapter tests passed, including mixed-class phone filtering, selection,
latched loss and unchanged person defaults. Native startup explicitly identifies
the YOLO11s model. Live metadata reported a cell phone with a numeric track ID.
An independent six-second WebSocket/API check matched 69 snapshots and 69 phone
tracks exactly by source timestamp, ID, box and confidence. Live API selection
and clearing passed; left unselected. Project HTTP returned 200. No error or
critical entries found in the startup log. Original stock executable hash verified.
Browser visual QA and fast-motion accuracy are not established by these tests.
Metadata arrival cadence is not detector inference FPS or camera latency.
