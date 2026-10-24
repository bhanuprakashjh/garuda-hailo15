# Frozen dataset rerun and a clearer follow console

## Outcome

The movement-fix build was rerun on the same aerial inputs. **No meaningful
overall improvement in dataset tracking is established.** Acquisition remains
3/11 clips and detection metrics reproduce unchanged. The recorded-car ROS/PX4
path works as a limited heading-response test, not reliable closed-loop pursuit.

The redesigned local console is at http://127.0.0.1:8100/ . Refresh the page.
Handoff is live IMX678 input, simulator disarmed, Follow OFF. The camera was
restored after the dataset runs; no model, ISP, profile or board package changed.

## Frozen comparison

Baseline: bench/results/2026-09-13-grand-demo/{dataset-wide,det-paired,replay-car}.
Rerun: bench/results/2026-09-13-dataset-rerun/{sot,det-paired,replay-car}.
Archives include raw outputs, configuration, checksums and failed cases, not
dataset pixels. Full external runs: /media/bhanu1234/Development/hailo-export/dataset-rerun-20260913.

The SOT runs use the same eleven prepared sequences, input and manifest hashes,
fullview profile, initial point at source frame 15, first 240 frames (or clip end),
50 ms source period and assumed 50 ms initial source age. Only the native causal
build changed from the baseline. Measured processing determines skipped frames;
this is not live FPS or measured camera/ROS latency.

| SOT measurement | Baseline | Rerun |
|---|---:|---:|
| Clips acquiring a target | 3/11 | 3/11 |
| Source frames | 2,567 | 2,567 |
| Processed frames | 723 | 724 |
| Fresh on-target processed outputs | 98 | 99 |
| Fresh off-target processed outputs | 2 | 1 |
| Time-weighted eligible on-target duration | 3,694.666 ms | 3,703.431 ms |
| Time-weighted eligible off-target duration | 31.955 ms | 32.113 ms |
| Total evaluated source timeline | 120,100 ms | 120,100 ms |

On-target means box IoU ≥ 0.5, control-valid and within the 200 ms budget. Both
runs are about 3.08% eligible on-target time across these evaluated windows. The
off-target output count decreased, but off-target duration did not: do not
present this as an established safety improvement. The source timeline uses
piecewise-constant labels and includes skipped frames. Off-target overlap is
not a certified wrong-person identity count.

Both runs acquired sequences 086, 115 and 245. Their fresh on/off-target outputs
were 6/0, 46/0, 46/2 before and 6/0, 46/0, 47/1 after. All other clips remained
unselected. One additional processed frame occurred in sequence 0317_00000;
processing subsets therefore are not fully identical.

Acquisition failure is not synonymous with absent detector boxes. For example,
sequence 024 has raw target overlap on 59/60 processed frames, but no selection.
At source 16, the only published confirmed person track starts at x643.11 while
the fixed click is x617.62. Other raw person boxes exist nearby but are not
published confirmed tracks. The click/confirmation/association path needs its
own investigation; the frozen protocol was not changed to make this rerun pass.

## Same 64 DET images

The detector-only probe and YOLO11s HEF are unchanged. Repeated metrics exactly
match the baseline, as do the matched source images and preparation manifests.

| Condition | Person recall @.15 | Vehicle recall @.15 | False positives/image @.15 | Person recall @.5 |
|---|---:|---:|---:|---:|
| Reduced 720p, five passes | 28.39% | 59.88% | 12.891 | 11.18% |
| Original pixels, nine passes | 31.41% | 61.17% | 16.219 | 12.01% |

Summed per-image inference waits were 129.497160 ms and 222.895820 ms (baseline
128.530940 ms and 222.394400 ms). These exclude DSP resizing/cropping, transfer,
tracking and exposure. Original sources are at most 1920×1080, not 4K. This is
not an equal-compute-budget comparison. There was no new model training.

## Recorded car through ROS/MAVROS and PX4

Repeated the original 25 s scenario, clip 115, fixed initial click (661,396),
fullview profile and declared playback/FOV assumptions, using the updated native
build and relay. 135 inference frames, 25 forwarded and 3 rejected motion packets.
Zero expired motion at final dispatch check. Rejections: one original lease
expired, one lease expired immediately before dispatch, one unknown/consumed
publication. They remained rejected.

Actual follow heading span 0.918517°, requested span 0.645235°. This small response
passes the minimum protocol checker, **not** an impressive/useful follow demo.
376/420 follow ticks requested HOLD, with 289 in lost state; EOF and stale source
periods are part of this run. Expired-source HOLD and final disarm passed.
Translation commands were zero. Physical position drift is not a translation
command. Recorded pixels cannot respond to the simulated drone's movement.

## GUI changes

- One dominant camera view; actual Gazebo view and operator controls beside it.
- Compact Select → Take off → Follow setup, with a plain-language next-step
  banner. No automatic takeoff or following from a selection.
- Separate retained identity, fresh motion request and last packet sent/rejected.
  Historical packet delivery is not labelled current execution.
- Explicit remaining-request time from the backend. The frontend ages it and
  source age between polls, charging the HTTP roundtrip conservatively.
- One status poll instead of three independent pollers; camera loading no longer
  blocks status refresh. Old/failed previews cannot silently grant selection.
- Stable keyboard target buttons and image clicks retain exact displayed sequence
  references. The 500 ms display selection window is not the 200 ms control permit.
- Hold/Land controls on the working surface; zoom/framing, raw/filtered overlays,
  message details and events are expandable.
- Live physical, recorded footage and rendered camera modes are explicitly
  distinguished. Display zoom is not ISP zoom; framing is not metric depth.

Reused the existing Python/HTML local app under the Sites building/hosting
workflow. This is still the local simulator control surface, not a hosted Site.
No registration, public deployment, external assets, dependencies or new vehicle
commands. Presentation JavaScript is now a separate same-origin served asset;
version snapshots include its hash.

Validation: 45 simulator Python tests, JavaScript state assertions and syntax,
static HTML ID/asset-reference checks, and actual local HTML/JS/status HTTP
responses. Deadline expiry, disconnect, unverified identity and rejected-wire
presentation are tested. No browser screenshot, click-through or visual QA was
requested/performed. Final compact step labels were a presentation-only edit
after the recorded scenario; the served files were rechecked.

## Next engineering work

1. Diagnose why raw detections fail to become a selectable confirmed target.
   Separate a fixed initial-point replay from an operator choosing a later frame;
   do not use continuously refreshed ground-truth clicks as an oracle.
2. Address small-person aerial recall using an explicitly separated train/
   calibration/evaluation split and correct model class mapping. These validation
   clips have already informed development and are not held-out proof.
3. Evaluate selective native-pixel ROI within the existing capture-age budget;
   an all-grid loop does not meet it merely because tiling improves recall.
4. Rerun crowd, occlusion, return and temporal overlap checks. A retained ID,
   one fewer off-target frame, or a working ROS route is not flight qualification.

Structural review: existing controller/ROS authority untouched except a read-only
remaining-deadline UI field. Reused the frozen harnesses and removed duplicate
frontend polling/dynamic panel construction. No parallel perception fork.
Red-team: identical detector results do not imply robustness; tiny count changes
can conceal unchanged off-target duration; replay motion does not close the
visual feedback loop. All failures stay visible and no real-flight gate is ticked.

## Camera overlay and zoom follow-up

The image buffering fix in `eb77f9f` placed the camera layers above the detection
canvas. Live status still contained person detections, but the images hid the
boxes and intercepted selection clicks. Explicit stacking now puts the canvas
above both images and the frame notice above the canvas; images ignore pointer
events. A headless Chrome check against the running console confirmed painted
overlay pixels, loaded image buffers and the overlay as the hit-test target.

The inspection crop also cleared every time source age crossed the control
freshness limit. It now retains its last crop with a visible holding message
until fresh evidence arrives. A target change, release, identity expiry or
producer change clears the old crop. Control freshness gates are unchanged.
A live Chrome sampling check observed fresh and held crops without blanking
after initial display. Blocking status requests in that isolated test browser
preserved the crop and displayed both the holding and disconnected messages.
JavaScript syntax, existing presentation checks and diff whitespace checks pass.
