# Hailo tracks in the Garuda project viewer

**Current mode (2026-09-11): YOLO11 r2 experiment**, adapter release5 with
`--target-label all`. See [the complete checkpoint](../../docs/2026-09-11-hailo15l-checkpoint.md)
for current configuration, recording results, limitations and rollback.

**History: YOLO11 phone**, release3 with `--target-label 'cell phone'`.
The working person binary, assets and release2 adapter remain available for rollback.
See `hosts/hailo15l/stock-phone/README.md` for model, deployment and rollback details.
The person integration history below describes earlier releases; its read-only
API and pending browser-QA statements do not describe release5. Video and card
selection were subsequently tested in Chrome and both succeeded. The dynamic
diagnostic list can move cards vertically; this usability issue remains open.

**Current update:** viewer-only click selection is now available. See the
Selection section below; the initial read-only milestone is retained as history.

First integration milestone, 2026-09-11: read-only adapter and project page at
http://10.0.0.1:8099. Standalone baseline remains http://10.0.0.1.

## What is integrated

`hailo_adapter.py` subscribes to the stock person viewer's WebSocket metadata on
loopback port 8765. It decodes Hailo's actual protobuf schema and exposes
`/api/snapshot` (`/api/mono` alias) with project-style track fields: id, label,
conf, x/y/w/h in native frame pixels. It does not run or import the old tracker,
target owner, camera driver, inference code, command transport or fresh shim.

`hailo_viewer.html/js` is a separate input mode in this project, preserving the
dark board-viewer presentation. It embeds the existing Hailo viewer so its video
and large ID overlay remain unchanged; the side panel displays the project's
imported tracks and source status. This is not yet native video ingestion into
the old MJPEG viewer, nor a replacement for Hailo's WebRTC client. Press Play in
the embedded Hailo viewer. Browser playback requires access to board port 80
and its normal WebRTC/metadata services as well as project port 8099.

No second tracker, selection, lock, ReID, controller or command integration.
All project POST commands return 405. Hailo controls inside the embedded viewer
remain normal Hailo controls; changing away from Detection will interrupt this
metadata input. Numeric IDs are not durable identity and must be scoped to
`source_session` (new UUID on reconnect or source timestamp rewind).

## Freshness and clocks

Contract: `garuda.hailo.viewer.v1`, deliberately NOT `garuda.fresh.v1`.
`source_capture_timestamp_ns` preserves the integer ISP timestamp as a decimal
string. Its clock is `hailo.isp.unmapped`; no source-to-host age is inferred.
`timestamp_valid=false`, `age_ms=null`, `lock.control_valid=false`,
`lock.observation_valid=false`, and `image_target.valid=false` always.

`arrival_age_ms` measures local time since receipt of an advancing source frame,
not camera latency or measurement age. Same-timestamp repeats do not refresh it.
After 300 ms without progress the adapter exposes no tracks. Disconnect clears
them immediately. Browser polling times out and clears the side panel on loss.
The iframe is an independent view and can continue working if the adapter stops.
No stale project state should be interpreted as an observation for control.

Hailo metadata does not distinguish fresh detector measurements from predicted
tracks. `measurement_status=not_exposed_by_source` preserves that uncertainty.
`sequence` counts accepted adapter messages, not detector inference frames.

## Reproduce and start

Run `bash hosts/hailo15l/stage_hailo_adapter.sh HAILO_SOURCE_ROOT OUTPUT_DIRECTORY`
from this worktree. It requires the installed Hailo SDK/protoc and source commit
`9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`. The descriptor is generated from
`hailo-analytics/hailo_analytics_api/src/pipeline/codecs/protos/analytics_metadata.proto`.
The adapter uses the official schema rather than interpreting protobuf manually.

Dependencies are isolated, hash-pinned pure-Python wheels in vendor/:
[websocket-client](https://pypi.org/project/websocket-client/1.9.2/) 1.9.2 and
[protobuf](https://pypi.org/project/protobuf/7.36.1/) 7.36.1. Board Python is 3.10.15.
No package was installed into board system Python or the PC's global environment.

Copy the staged directory to the board; run `python3 hailo_adapter.py --port 8099`.
The Hailo person viewer must already be running with Detection active.
Current deployment: `/opt/garuda-hailo/garuda-hailo-adapter-release1/`.
Process PID 2142 at verification; log `/tmp/garuda-hailo-adapter.log`.
No boot persistence. Local trusted bench network only; not authenticated or
internet-hardened. CLI source override is diagnostic; the iframe assumes Hailo
video is on the same board hostname at port 80.

Rollback: stop only the verified adapter process. Hailo PID 1965 and all native
detector/ISP/tracker files were left untouched. Original custom project source
and the PC preflash backup remain untouched too.

## Verification

- Seven unit/integration tests pass: exact geometry and ID zero; clock separation;
  repeated-frame expiry; disconnect clearing; reconnect/rewind session separation;
  unknown protobuf fields; malformed boxes/confidence/duplicates; HTTP read-only.
- JS syntax and stage-script shell syntax checks pass.
- Board loads the protobuf descriptor with installed Python 3.10.15.
- HTTP project page returns 200, JSON reports a live person, command fields false.
- A six-second independent WebSocket/API comparison matched 71 snapshots and
  71 person tracks by exact ISP timestamp. IDs, geometry and confidences all equal;
  one source session, 178 accepted messages advanced; max sampled arrival age
  52.54 ms. This is transport equivalence, not tracking accuracy or camera latency.
- Hailo process remained PID 1965; thermal state full_performance.
- Source inspection confirmed the Hailo page does not set frame-blocking headers.
  Browser visual testing was not performed; user should verify playback and layout.

Tests use `PYTHONPATH=STAGED/vendor HAILO_DESCRIPTOR=STAGED/analytics_metadata.desc
python3 -m unittest discover -s services/garuda-tracking/tests -p test_hailo_adapter.py -v`.

Next milestone, separately: selection/identity behavior without changing the Hailo
MOT baseline, and verified source-clock/measurement-age mapping before consumers
can treat any observation as actionable. No identity-retention claim is made.

## Selection — 2026-09-11

Release2 adds a selection owner in the adapter only; Hailo inference/tracking
are untouched. Click a person box, large ID badge, or keyboard-accessible side
card. A blue outline/card and Selected ID label identify the chosen Hailo track.
Clear selection removes it. Lost is latched: absence in Hailo output, stale
source, disconnect or session change requires explicit user reselection, even
if the same numeric ID returns. Never automatically switches to another ID.
This is a selected MOT track, not verified identity or confirmed physical visibility.

`selection` is separate from `lock`; all clock/control validity fields remain
false. `/api/select` accepts JSON id/source_session/sequence and checks recent
frame history (20 frames, maximum click age 300 ms), current presence and session.
`/api/unlock` clears viewer selection. Other command routes remain disabled.
Foreign browser origins are rejected. Trusted local bench service, not authenticated.

`person-selection.js` wraps only the private page's display callback when
embedded in the project viewer. It hit-tests recent drawn boxes/badges and sends
ID messages to the exact project origin. The parent checks iframe origin/source.
Overlapping boxes require choosing an unambiguous badge or side card. Selection
highlights expire if parent status stops. There are no calls into Hailo's tracker.
Standalone display remains unchanged; original vendor assets are not modified.
The prior private page is backed up at `/opt/hailo-person/webpage-pre-selection/`.

Deployment: `/opt/garuda-hailo/garuda-hailo-adapter-release2/`, PID 13754 at
verification; log `/tmp/garuda-hailo-selection.log`. Release1 remains intact.
Hailo native process stayed PID 1965. Only the Python adapter was restarted.
Refresh the project page to load the versioned private-page scripts.

Validation: 12 Python tests passed, including loss latch/reconnect/no silent
reacquisition, expiry and rejected stale clicks. Node mock tests cover ID zero,
click coordinates, origin checks, selected outline, and overlap rejection; JS
syntax checks passed. Live API selected person ID 32 then cleared it, preserving
control_valid=false; old-session request rejected (409), foreign origin rejected
(403). Left unselected for the user. Browser interaction testing not performed.

Rollback selection UI: stop the verified release2 adapter, run preserved release1;
restore private page assets from webpage-pre-selection if desired. No board
reflash, model change, tracking parameter change or boot service change.

### Click-layer correction

User reported selection did not work. Source inspection found Hailo's controls
overlay is a sibling of Video-Container, so the earlier listener on the canvas's
immediate parent did not cover that overlay. The listener now captures clicks
on the common `.Video-PlayerContainer`. A mock reproducing sibling-layer clicks
passes; the served page references cache-busted person-selection.js?v=2.
No detector or adapter restart. Actual browser confirmation remains pending.
