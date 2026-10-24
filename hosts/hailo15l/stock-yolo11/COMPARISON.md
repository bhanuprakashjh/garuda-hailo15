# Desk-board model comparison — 2026-09-11

User clarified this is a desktop demo board with no flight controller.
Approved order: YOLOv8m, then YOLO11m. Leave each available for user testing;
do not claim a motion-quality comparison from unmatched metadata samples.

`model-comparison.patch` supersedes `yolo11-binding.patch` for a clean upstream
checkout; do not apply both. It keeps the camera profiles, tiling, scheduling,
COCO postprocessing and tracker code unchanged and adds an allowlisted startup
selector `HAILO_COMPARISON_MODEL`: yolov8m, yolov11m, yolov11s (default).
Build command is the same as README. Deployed as separate executable
`/opt/hailo-yolo11/camera-viewer-compare`; original stock and initial YOLO11s
executables remain intact. No boot persistence added.

Both newly staged HEFs parse as HAILO15L/compiler 5.3.0, NV12 640x640,
80 COCO classes, NMS threshold 0.20/IoU 0.70. YOLOv8m: 13 contexts;
YOLO11m: 11 contexts. Both use the existing generic NMS decoder.

Current launch: YOLOv8m, PID 1238 at verification, working directory
`/home/root/apps`, log `/tmp/stock-yolov8m-viewer.log`. Environment:
`HAILO_COMPARISON_MODEL=yolov8m WEBSERVER_CONSOLE_LOG_LEVEL=info LD_BIND_NOW=1`.
HTTP `/ai_pipeline`: Detection; `/profile`: Daylight. Startup log explicitly
names yolov8m HEF. Loader verification and startup succeeded.

Comparison binary SHA256:
`2f4b612ee70c385f5484cab3e350258a93eefc88b3681ad22b655ed143f278d4`.
Unchanged COCO JSON SHA256:
`f8a5761fc83e8542dbd604533dbed03b417242c70f2fd873e2767b0170fddd1a`.
Original vendor executable checksum remains as recorded in README.

12-second metadata smoke test: 197 messages over 11.820 seconds (not inference
FPS). Largest sample: person 0.9422 ID 1; cell phone 0.4786 ID 3; remote 0.6452
ID 4. Phone and remote boxes nearly coincide, suggesting class ambiguity in this
sample, not confirmation of two physical objects. Motion reliability untested.
YOLO11m is staged but has not been run in the stock-based comparison viewer yet.
