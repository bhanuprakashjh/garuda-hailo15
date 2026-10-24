# Accepted baseline and next autonomy gate

## Frozen baseline

Owner accepted the restored recovery-good desk behavior. This is an
operator-accepted baseline, not robust-tracking or flight qualification.
Node SHA256:
`253a2df9f9d8d076624f3e3500d76723118714d7210531588ff68220c64aaaea`.
Measured-box recovery and desk `reacquire_gap_ms=500` remain active. Experimental
phone search opts are absent. AE and 3DNR remain enabled.

Ignored local archive: `bench/local-baselines/20260918-recovery-good/`.
The manifest binds deployed binary, profiles, media/postprocess configuration,
models, postprocess library, shim, JPEG library bytes and ISP/boot readbacks.
It does not archive the BSP/rootfs. Exact source-to-binary provenance is not
established: the working tree contains later disabled experiments. Do not claim
a rebuild from that tree is byte-identical. ISP values are dynamic readbacks,
not a restorable calibration.

```sh
python3 hosts/hailo15l/freeze_baseline.py verify bench/local-baselines/20260918-recovery-good
```

The board backup is `/opt/garuda-fresh/backups/pre-phone-predictive-20260918/`.
The following sequence was used and verified during the owner's rollback.
It restarts the application and clears selection, not ISP calibration; run
only when a restore is intended. It was not rerun during this archive step.

```sh
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
ssh -o BatchMode=yes root@10.0.0.1 'cp -p /opt/garuda-fresh/backups/pre-phone-predictive-20260918/garuda-fresh-tracking /opt/garuda-fresh/garuda-fresh-tracking && cp -p /opt/garuda-fresh/backups/pre-phone-predictive-20260918/perception-follow.json /opt/garuda-fresh/perception-follow.json'
bash hosts/hailo15l/fresh_tracking_ctl.sh start-follow
```

## Recording qualification

Reuse `bench/fresh_stream_capture.py`: exact-exposure NV12 source pixels and
frame/output metadata, not independently timed preview JPEGs. Managed detection
uses crops, so its preview/network image alone is not all actual NPU inputs.
Preserve paired full-FOV source pixels for causal replay.

Capture is disabled in the accepted live profile. A future session must derive
a temporary profile from frozen `current.json`, changing only
`capture_stream_port=8983` and `capture_source=true`, verify the diff, and restart
via `start-current`. Preserve and restore the original afterward. Do not use a
generic capture profile with different tracking/model settings. Recording load
must be measured. Capture has NOT been enabled in this checkpoint.

Once explicitly enabled:

```sh
python3 bench/fresh_stream_capture.py --frames 150 --deadline-ms 60000 --output /tmp/garuda-capture-NEW
python3 bench/qualify_capture.py /tmp/garuda-capture-NEW
```

The integrity gate rejects incomplete/unpaired recordings, altered pixels,
producer changes and frame/output/exposure mismatches. Passing explicitly does
not qualify accuracy. Telemetry-only recordings cannot pass this gate.

Use separate routines: steady hold; lateral motion/reversals; tilt; occlusion/
re-entry; similar-object distraction. Record target class, scene, lighting,
selection event, baseline manifest and ISP readbacks. Processed-frame captures
do not reveal what occurred in dropped camera frames; state this limitation.
Use evaluator-only labels and existing causal replay/SOT scorers, a fixed
selection protocol, and held-out sequences. Report wrong-target control,
correct recovery, longest observation gap, availability over the whole selected
interval, and latency distributions. Successful-frame median is insufficient.
Agree numeric acceptance limits before declaring a candidate better.

## Native authority workstream

Reuse `hosts/hailo15l/ros2/native_camera.py`, the observer and existing MAVROS
camera mode. The older campaign handoff predates some native-ingress work;
it is not wholly absent. Do not add a parallel authority implementation.

The existing 10-second on-board observer ran with publishing frozen after
5 seconds, current boot clock and local-only ROS domain 73. No MAVROS or
vehicle I/O. The selected target was already lost, so this confirms transport,
not a valid-to-expired transition or selected-target performance.

Still required before the board-resident follow milestone is complete:

1. Fresh selected-target native ingress and frozen-input expiry, wrong stream/
   boot/selection, reorder/duplicate and reconnect tests with on-board evidence.
2. Explicit operator permit binding and on-board authority, with no PC
   forwarding perception or refreshing its original capture deadline.
3. Owned PX4 SITL: actual forwarded/rejected MAVLink, coordinate checks,
   takeover, source/ROS/telemetry loss and no-auto-rearm behavior.
4. Closed-loop follow error and identity correctness on held-out scenes.

No real FC endpoint or flight sign-off follows from these checks. Physical
timing/calibration/VIO, range, obstacle avoidance, thermal/power qualification
and product packaging remain later gates.

```sh
python3 -m unittest discover -s services/garuda-tracking/tests -p test_qualification.py -v
python3 -m unittest discover -s hosts/hailo15l/ros2 -p test_native_camera.py -v
```

No new dependencies or runtime tracking changes. Strongest limitation: valid
archived bytes and safe transport may still carry poor detections. No perception
gate closes until labeled motion tests and closed-loop simulation pass.
