# Exact-input streaming capture

The optional `CaptureStream` records the actual packed NV12 detector input and the
`Frame` detections/appearance/motion from that callback. It also records the tracker
response, source process/clock identifiers, geometry, HEF path and available exposure
metadata. It does not pair the latest asynchronous preview JPEG with those detections.

Enable only for a bench capture:

```sh
bash hosts/hailo15l/build_fresh_tracking.sh
# Stop before staging, as required by the existing staging script.
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-capture
python3 bench/fresh_stream_capture.py --frames 600 --every 1 \
  --output /tmp/garuda-exact-input-recording
```

The output directory must be new. It contains numbered `.nv12` / `.json` pairs,
the request, and an end/summary record. Each metadata file contains a SHA256 of the
pixel bytes. The PC validates sequence, input/output capture correspondence, pixel
layout, producer identity, requested sample count and the final completion footer.
A disconnected or incomplete stream exits with an error and retains its saved prefix.
Do not treat a directory without successful `summary.json` as a complete recording.
The original camera/model timestamps remain in the source clock domain.

The default bench profile has a 640x640 letterboxed detector input. Its full camera
FOV is the 640x360 content region with 140 rows of padding at top and bottom. Tracker
boxes use the 1280x720 source coordinate system. Annotation/replay must use that
explicit geometry. Optional paired mode also saves the matching 1280x720 ISP-processed
image before JPEG encoding. It is not sensor Bayer RAW.

Limits are enforced at both ends:

- One loopback client on port 8983, forwarded through a temporary SSH stdio channel.
  Normal `start-phone` leaves the capture socket disabled.
- At most two queued images and one being transmitted. Each image is at most 2 MiB,
  each metadata record 128 KiB. The socket send buffer is bounded; a packet has a 100 ms
  total send deadline. Network writes run on their own thread.
- 1–1200 samples, sampling every 1–40 callbacks, and a deadline of at most 60 seconds.
  Sampling/sequence gaps are explicit; “complete” means the requested sample count,
  not proof that every sensor exposure passed through inference.
- The board checks for 128 MiB of non-CMA headroom plus 8 MiB for capture before admission.
  There are no board recording files. A queue overflow aborts capture instead of
  silently dropping middle samples or letting memory grow.
- The PC checks worst-case free storage before requesting a recording, enforces
  packet/count limits, and rejects mismatched image/observation sequences. Rejected
  tracker responses that refer to earlier state fail this strict correspondence check.

Stop the bench profile and return to ordinary operation with:

```sh
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
bash hosts/hailo15l/fresh_tracking_ctl.sh start-phone
```

This supplies synchronized evaluation inputs, not ground truth. An accuracy report
still requires visible-target/occlusion annotations, physical identity labels and
held-out person/phone/distractor/camera-motion sequences. The native stream test
checks nontrivial padded-stride packing, sampling, capture restart, memory-admission
denial and a non-draining consumer. Receiver tests check hashes, correspondence,
oversized packets and incomplete-prefix handling.

The [target evaluation guide](EVALUATION.md) now supplies the annotation schema,
exact-input integrity checks, selected-target metrics and real C++ replay comparison.
Unknown truth and sparse samples are explicitly excluded from accuracy/time claims.

## Paired higher-resolution source

`start-paired-capture` enables the same recorder plus a bounded source-frame history.
The existing sink1 stream supplies 1280×720 NV12 at its configured 20 fps; copying occurs
before the viewer's JPEG rate limit. Up to four owned packed frames are retained, including
before a request begins. No media-library/DMA buffer reference is retained. The detector
callback takes only a source frame with the **exact integer ISP nanosecond timestamp**.
An unavailable requested pair aborts capture; there is no nearest-frame substitution or
blocking wait in the detector callback. Source timestamp regression invalidates history.

Build and stage the optional profile, preserving the current binary:

```bash
GARUDA_FRESH_BUILD=/tmp/garuda-paired bash hosts/hailo15l/build_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
ssh root@10.0.0.1 'mkdir -p /opt/garuda-fresh/backups/pre-paired-capture; test -e /opt/garuda-fresh/backups/pre-paired-capture/garuda-fresh-tracking || cp /opt/garuda-fresh/garuda-fresh-tracking /opt/garuda-fresh/backups/pre-paired-capture/garuda-fresh-tracking'
GARUDA_FRESH_BUILD=/tmp/garuda-paired bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-paired-capture
python3 bench/fresh_stream_capture.py --frames 600 --every 1 \
  --output /tmp/garuda-paired-recording
```

Each sample has `.nv12` for the exact model input, `.source.nv12` for its matching source,
and `.json` containing both dimensions, offsets, lengths, hashes and equal ISP timestamps.
The optional `source_image` descriptor extends the existing GRC1 packet; paired mode
requires the current receiver. Primary-only recordings remain supported. Annotation
templates and alternative prediction records also retain `source_nv12_sha256`, preventing
a higher-resolution image from being detached from its reviewed model input.

640×640 and 1280×720 NV12 together occupy 1,996,800 bytes, within the existing 2 MiB
packet limit. Transport still holds at most two queued packets plus one in flight.
Source history adds at most four 1,382,400-byte images. Paired capture admission reserves
16 MiB above the 128 MiB non-CMA floor (144 MiB total), covering owned source/packet copies
and metadata; primary-only admission remains 136 MiB. No recording bytes are written to
the board. `diag.source_pairing` exposes matches, missing pairs, evictions and invalid input;
the cache operates only in the explicit paired profile. There are no extra camera streams,
driver changes, camera resolution switches or neural models in this feature.

The 600-pair board run transferred 1,198,080,000 pixel bytes over 29.9334 seconds of source
time, with all 1,200 hashes and 600 exact exposure pairs verified, zero sequence gaps and
zero pairing misses. During capture, HTTP image age p95 was 147.09 ms, maximum 183.82 ms.
The enclosing 40-second run processed 20.0253 frames/s with zero rejected frames or HTTP
errors. RSS was 90,656–93,032 KiB; minimum sampled non-CMA headroom 294,560 KiB. This was a
dark empty-scene transport/load test, not a target recognition result. See
[paired evidence](../../bench/results/2026-09-10-fresh-tracking/paired-input-stream/README.md).

Restore the preserved baseline after a bench trial:

```bash
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
ssh root@10.0.0.1 'cp /opt/garuda-fresh/backups/pre-paired-capture/garuda-fresh-tracking /opt/garuda-fresh/garuda-fresh-tracking'
bash hosts/hailo15l/fresh_tracking_ctl.sh start-phone
```

Pairing now makes a same-exposure high-resolution ROI comparison possible. It does not
perform that inference, decide ROI scheduling, recover detail already lost in ISP
processing, or demonstrate improved phone recognition. Those require target-active pairs
and the detector/ROI experiment described in DELIVERY.md.
