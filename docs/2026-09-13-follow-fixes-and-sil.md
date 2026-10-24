# Follow fixes and PX4 SIL — 2026-09-13

> Later phase: [Gazebo visual follow demo](2026-09-13-gazebo-visual-follow.md)
> adds actual rendered pixels → Hailo → PX4 feedback and a local console.
> This report remains the desk-pipeline and headless-SIH baseline.

Status: fixes deployed to the desk Hailo-15L; native-tracker PX4 SIL passes.
**This is not a flight-ready or robust crowded-scene perception sign-off.**
Supersedes the implementation state in `2026-09-13-hailo15l-follow-handoff.md`;
the independent audit remains a historical account of the old installation.

## Implemented

- Crop-edge checks now remove letterbox padding before checking interior borders.
- Tile aggregation carries region provenance: a full-view body can replace a
  stronger contained crop fragment; separate detections from one region survive.
- Follow mode runs one paired-source full-view detector, adds four corner passes
  during acquisition/refresh, and retires them only after local handover evidence
  (or when the target is too large to need a local crop). Periodic tiled refresh
  remains for small targets; large targets still get full-view inference every
  frame and return to tiled search on loss. A handover frame may legitimately run five global passes plus one ROI;
  there is no redundant sixth full-view inference. Pass counts are published.
- Corner batches copy the source once instead of once per corner. Exact exposure
  pairing can wait at most 40 ms in the managed node; it never substitutes another
  exposure. The cache owns at most four 1280×720 frames.
- Histogram and OSNet crops use the exact paired 1280×720 source, not 640×360
  detector content. Missing pairs fail closed. HEFs/ISP image are unchanged.
- NPU work no longer holds the publisher/selection mutex. A selection-generation
  change discards in-flight results and resets motion/ROI state, avoiding old
  inference results being applied to a new selection.
- Follow profile ROI age/global-evidence budgets are 400/1600 ms; the local
  planner refresh period is half the global-evidence window. The old 200 ms
  planner period would otherwise force full-only work on every slow global update.
- Confirmation and positive-identity continuation/reacquisition gaps are 500 ms
  in this profile, bounded and explicit. This fixes timers shorter than the
  measured processing cadence. Positive descriptors, rival ambiguity, multiple
  reacquisition observations and frame-age checks are still required. These are
  observation-gap budgets, **not permission to command using old imagery**.
- The real consumer chain is `fresh envelope → FreshFollow → FollowAuthority →
  CommandIntent → simulation bridge`. It binds source/stream/selection epoch,
  charges transport time, and prevents duplicate/stale evidence renewing motion.
  The consumer's maximum observation age stays **200 ms**; intent TTL is at most
  **150 ms**, additionally bounded by the original evidence deadline.
- Preview cannot create vehicle I/O. Live simulation requires `GARUDA_SIM=1`,
  explicit IPv4 loopback UDP, an owned local PX4 child executable, and PX4 peer
  identity. Position/attitude telemetry must remain fresh; speed/yaw are bounded.
  Do not forward this endpoint to hardware. No FC parameters were changed.

## Evidence and limits

Artifacts: `bench/results/2026-09-13-follow-fixes/`.

Native CTest: **7/7**. Python tracking: **45 passed, one adapter module skipped**
(unstaged Hailo adapter). Follow: **24 passed**. Bridge: **7 passed**.
VisDrone tools: **15 passed**. Exact-SDK ARM build passed, including the new
`garuda-causal-replay` executable.

### PX4 software-in-the-loop

`sil-final/verification.json` asserts all six scenarios: nominal, target loss,
video stall, operator abort/resume, publisher failure, and complete setpoint-link
loss. Each reached OFFBOARD/armed and ended disarmed. The publisher breaker
tripped at 15.2 s after failure injection at 15 s. Complete link loss exercised
PX4's own configured RTL without a LAND command; observation was extended until
landing/disarm, without changing its parameters. The first too-short observation
is retained in `sil-short-observation/`, not presented as a completed landing.

Nominal: 695 ACTIVE ticks out of 700 follow ticks; settled absolute framing
median 0.034, p95 0.046; simulated distance median 5.670 m. These are simulation
figures using **actual native tracker code but synthetic detections/appearance**.
They do not measure YOLO, camera motion blur, metric ranging, or real flight.

### Causal recorded-pixel inference on the actual 15L

`run_causal_replay.py` sends pixels and one fixed initial selection point to the
board. The tracker chooses subsequent crops; ground truth stays in the host
scorer. Real DSP resizing, YOLO11 HEF, OSNet and native tracker/planner run with
measured processing time and source-frame skipping. Each recorded trial declares
a 50 ms frame period and a 50 ms source-age assumption. These assumptions do not
establish the original video's frame rate or live transport/ISP timing. Motion
input is CPU-downsized rather than produced by the live ISP.

| Trial (200 source frames) | Processed | Selected | ROI updates | Valid/on-target processed outputs |
|---|---:|---|---:|---:|
| Car 115, initial 250 ms confirmation gap | 34 | no | 0 | 0 |
| Car 115, confirmation gap fixed | 34 | yes | 0 | 28/31 after selection |
| Car 115, planner cadence fixed | 42 | yes | 27 | 35/39 after selection |
| Person 086, original identity cadence | 34 | yes | 0 | 1/31 after selection |
| Person 086, identity cadence fixed | 34 | yes | 2 | 4/31 after selection |

Car planner-fixed age median/p95: 200.145/309.100 ms, including the declared
50 ms source age. One control-valid car box scored IoU 0.333 against truth;
its age was 314.791 ms, beyond the PX4 consumer limit. That is a localization
failure, not proof of an identity switch. Person cadence-fixed median/p95:
275.566/277.910 ms; 26 ambiguous and one occluded output after selection.
No cadence-fixed person output met the 200 ms consumer-age limit. **That crowded
person test fails the robustness goal.** Skipped frames are unscored, not counted
as successful tracking; overlap results are not continuous-time recall.

### Detector-filter regression, including the unfavorable result

Re-scored both complete 548-image VisDrone DET raw prediction sets with corrected
filters. For the controlled HEF at confidence 0.5, five-tile grouped recall changes
0.2414 → 0.2289, while FP/image changes 1.338 → 1.141. At confidence 0.15,
recall changes 0.4075 → 0.3891 and FP/image 11.394 → 12.943. Thus the correctness
fix is **not an overall detector-accuracy improvement**. The border policy and
fragment-merging tradeoff need further held-out evaluation. Archived scoring is
reproducible with `score_visdrone_det.py --legacy-filters`; old results were not
overwritten.

### Live desk smoke test

On the first deployed candidate, selecting the sole visible person succeeded.
A 19.828 s watch sampled 97 responses and 346 processed sequence advances:
17.450 updates/s, age median 117.735 ms, p95 236.631 ms. There were 96 tracking /
control-valid samples and one initial unselected publication. Ninety-one samples
reported one detector pass, six reported five passes. OSNet used paired 1280×720
pixels; no pair misses or embedding failures. One rejected frame was the expected
in-flight selection-generation discard. The large person did not need ROI.
This was **not** a prescribed fast-motion, disappearance or two-person crossing
test. It is not directly comparable to the audit's unselected searching scene.

The final large-target scheduler correction was then deployed and its running
`/proc/24138/exe` hash verified against the installed file and host build. A second
19.798 s watch had 97 samples and 394 sequence advances: **19.901 updates/s**,
age median/p95 **109.993/148.936 ms**, 96 tracking/control-valid samples and one
initial unselected publication. Ninety-five samples were single-pass, two were
initial five-pass acquisition. This confirms the final single-person desk path;
it does not resolve the crowded-person failure above.

The first real-camera transport-in-loop PX4 run (`sil-board`) produced 417/500
ACTIVE ticks, 82 COASTING and one IDLE. Every ineligible tick hovered; translation
was zero throughout, and landing/disarm completed. Its periodic freshness pauses
prompted the final large-target corner-scan correction. The final repeat
(`sil-board-final`) produced **499/500 ACTIVE**, one initial IDLE, no COASTING,
zero board transport errors, zero translation, and completed landing/disarm.
These passes validate transport/authority behavior, not visual following of a
moving simulated person.

## Run again

From this worktree, with the existing Hailo SDK and PX4 checkout:

```bash
export GARUDA_FRESH_BUILD=/media/bhanu1234/Development/hailo-export/follow-fixes-20260913
bash hosts/hailo15l/build_fresh_tracking.sh
export GARUDA_REPLAY_BIN="$GARUDA_FRESH_BUILD/native/garuda-track-replay"
GARUDA_SIM=1 python3 bench/sim/followme_sitl.py --scenario all --duration 35 \
  --execution live --perception tracker --tracker-binary "$GARUDA_REPLAY_BIN" \
  --out /tmp/garuda-follow-sil-new-run
python3 bench/sim/verify_follow_sitl.py /tmp/garuda-follow-sil-new-run
```

Use a fresh output directory. Without `--execution live`, the runner is a pure
preview with no PX4/MAVLink I/O. The optional `--perception board` connects actual
selected camera envelopes to **yaw-only** simulation; it is transport-in-loop,
not a rendered camera feedback loop. It intentionally has no metric translation
or claimed following-distance score. A source/epoch change requires a new run.

For recorded pixels, use `python3 bench/hailo_reference/run_causal_replay.py --help`.
That bench harness briefly stops the desk camera service, stages into a unique
`/tmp/garuda-causal.*` directory, and restores the follow service in `finally`.
It requires a verified prepared source/manifest and the built ARM replay binary.

## Deployment and rollback

Live app: `/opt/garuda-fresh/garuda-fresh-tracking`, SHA256
`e9d1aabb7607167d19a4396d1c8c266b0cde03ae98332a9f96629077e8f4cf4c`.
Profile SHA256: `ca91c34a48916624a7ab7c98bb7c219f6902217e65c2d46e8d2c7c33a477061d`.
UI: `http://10.0.0.1:8099/`. No boot-image update or model replacement.

Verified pre-change backup on this PC:
`/media/bhanu1234/Development/hailo-export/follow-fixes-20260913/rollback/garuda-fresh-before.tar`.
Archive SHA256 `171d674b133bed14b61f85d7bc85dde0156cc68d19a7f3b002d978aaeb4c2132`;
45 entries; original executable hash verified inside the archive. Stop the desk
service before restoring this archive under `/opt`, then start-follow. No backup
was deleted. `versions.json` includes binary, profile, PX4 and rollback hashes.

## Next gate, not yet passed

Prioritize crowd identity coverage and latency, then hold-out small-target and
fast-motion trials. Do not lower confidence/ambiguity gates simply to increase
green-lock time. Separate detector misses, crop localization, missing descriptors,
competing identities and freshness refusals in the score. Metric depth/range,
camera-to-body calibration, real-FC integration and flight tests remain outside
this simulation implementation. No new dependency was introduced.
