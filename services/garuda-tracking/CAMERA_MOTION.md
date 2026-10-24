# Experimental camera rotation and scale compensation

The optional background estimator fits a 2D similarity transform before association.
It transforms track position, velocity and uncertainty; the dependency-free core still
accepts old translation-only replay records. This helps association when the camera
rotates or changes scale. It cannot recover an object the detector fails to recognize.

The implementation extracts up to 200 ORB features from 320×180 luma, excluding detected
objects and image borders. Mutual descriptor matching feeds RANSAC. At least 16 inliers,
65% consensus, six spatial cells and substantial horizontal/vertical coverage are required.
Weak support produces an invalid motion estimate. No image buffer escapes its callback.
OpenCV runs with one thread; its thread setting is process-wide. The added fit-noise term
is a conservative proxy, not calibrated odometry covariance. Axis-aligned boxes can grow
under repeated coasting rotation. Missing observations still withhold control.

Build and stage on the existing bench (staging requires the service to be stopped):

```bash
GARUDA_FRESH_BUILD=/tmp/garuda-motion GARUDA_FRESH_OPENCV_MOTION=ON \
  bash hosts/hailo15l/build_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
# Preserve the running baseline before staging; do not overwrite an existing backup.
ssh root@10.0.0.1 'test -e /opt/garuda-fresh/backups/pre-similarity-motion/garuda-fresh-tracking || { mkdir -p /opt/garuda-fresh/backups/pre-similarity-motion && cp /opt/garuda-fresh/garuda-fresh-tracking /opt/garuda-fresh/backups/pre-similarity-motion/garuda-fresh-tracking; }'
GARUDA_FRESH_BUILD=/tmp/garuda-motion bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-similarity
```

The profile retains YOLOv8m, disables capture and learned person identity, and exposes
fit validity/rejection reason/timing under `diag.camera_motion`. Selection is manual.
A default build rejects this profile explicitly. Restore the saved baseline:

```bash
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
ssh root@10.0.0.1 'cp /opt/garuda-fresh/backups/pre-similarity-motion/garuda-fresh-tracking /opt/garuda-fresh/garuda-fresh-tracking'
bash hosts/hailo15l/fresh_tracking_ctl.sh start-phone
```

The CPU-only probe accepts bounded packed NV12 inputs, including stdin over SSH:

```bash
scp /tmp/garuda-motion/h15l/fresh-tracking/garuda-motion-probe root@10.0.0.1:/tmp/
ssh root@10.0.0.1 '/tmp/garuda-motion-probe - 640 640 letterbox 14 --warps' \
  < /tmp/garuda-motion-evaluation/validation_raw.nv12 > /tmp/motion-warps.jsonl
python3 bench/fresh_motion_report.py /tmp/motion-warps.jsonl
```

The input in this example is a local bench artifact; reconstruct its exact order using
the saved manifest. The probe verifies actual padding before removing it. `--warps`
creates known transforms of each image; omit it for unlabelled sequential estimates.
It has no detector masks and does not measure detector/identity accuracy. Do not run
offline CPU probes concurrently with a live latency benchmark.

On the 14-image validation split, 123/126 generated transforms were accepted, with
maximum accepted grid error 2.1954 pixels at 640×360. Mean ARM estimation time was
36.17 ms. In a separate 60-second empty-scene live run the pipeline processed 20.0004
frames/s, p95 image age 157.54 ms and maximum 186.70 ms. Almost half the sampled fits
were rejected for localized support. These results do not establish physical camera
motion accuracy, target-active latency, rolling-shutter handling, or combined ReID cost.

The tested baseline was restored. This mode is experimental and default OFF.
See [evidence](../../bench/results/2026-09-10-fresh-tracking/camera-motion/README.md),
[dependency licence](../../docs/dependencies/opencv-motion.md) and [open delivery requirements](DELIVERY.md).
