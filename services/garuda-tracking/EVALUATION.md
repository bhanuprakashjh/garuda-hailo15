# Selected-target accuracy evaluation

`bench/fresh_target_score.py` joins reviewed physical-target annotations to the exact
detector input, its detections and its tracker response. It verifies recording completion,
producer identity, sequence, capture time, packed NV12 size and SHA-256. A nearby preview
JPEG is not accepted as the corresponding image. No additional Python dependency is used.

This implements the missing scoring path. It does not supply a physical test dataset.
The available 600-frame continuous recording is an unselected dark scene; its accuracy
fields remain null. The older corrected 20-frame recording samples every 500 ms and
has no selected target. Inspecting its actual luma shows the phone mostly beyond the
right edge. Neither is an adequate phone trajectory benchmark.

## Capture and annotation

Use [CAPTURE.md](CAPTURE.md) to start the explicit capture profile and record every
frame. Capture separate person and phone trials in sufficient light. A useful 30-second
sequence is: target alone and fully visible, sideways motion, brief occlusion and return,
another similar object/person entering after selection, then a slow camera pan while
the target remains visible. Keep the source footage; record actual actions rather than
assuming the intended timing happened. A run missing a phase does not pass that phase.

```bash
python3 bench/fresh_stream_capture.py --frames 600 --every 1 \
  --output /tmp/garuda-person-trial
python3 bench/fresh_target_score.py /tmp/garuda-person-trial \
  --init-label person --output /tmp/person-truth.json
```

Initial annotations contain `unknown` for every frame. Review the exact `.nv12` pixels,
not predictions, and fill the annotations before comparing candidates. For the current
640×640 letterbox, full-FOV content is x=[0,640), y=[140,500). Annotation boxes use
normalized **full-FOV** `[x,y,width,height]` coordinates. A content box in pixels divides
x/width by 640 and y/height by 360; do not include padding. For clipped objects, annotate
the box clipped to the visible image. Do not infer hidden box extents.

The annotation document records:

- `annotator`: reviewer/provenance; `UNREVIEWED` is rejected for labelled frames.
- `target_id`: stable physical-object identity, unrelated to a detector's numeric ID.
- `label`: target class, e.g. `person` or `cell phone`.
- `selection`: null for detector-only evaluation; otherwise `{ "epoch": 1,
  "start_sequence": 240 }` binds evaluation to the intended target selection. Use the
  first recorded frame after selection was requested, including acquisition waiting.
  A recording started after acquisition cannot measure the earlier acquisition delay.
  Split recordings for deliberate target changes; do not automatically follow epochs.
- Each frame's immutable `sequence`, `capture_ms` and `nv12_sha256` link the review to
  the actual image. Paired recordings also bind `source_nv12_sha256` to the same-exposure
  1280×720 image. Preserve these values. The source image can aid annotation; its boxes
  divide x/width by 1280 and y/height by 720 to retain the same full-FOV coordinates.
- `visibility`: `visible`, `occluded`, `out_of_view`, or `unknown`. Partially visible
  targets may be `visible` if their clipped box can be labelled reliably; use `unknown`
  when identity/location is uncertain. Non-visible targets require `box: null`.
- `box`: reviewed normalized box for visible targets; `distractors`: visible physical
  alternatives, each with stable `id` and a box. Annotate relevant distractors throughout
  the trial. Missing distractor labels cannot establish zero identity switches.

Never interpolate across an occlusion or copy a detector box into ground truth and
then call its agreement accuracy. Save raw hashes, annotations, candidate config and
result provenance; use a separate recording to validate tuning.

## Score live and alternative outputs

```bash
python3 bench/fresh_target_score.py /tmp/garuda-person-trial \
  --annotations /tmp/person-truth.json --output /tmp/person-live-score.json
```

The C++ replay comparison uses the same recorded detections, appearance descriptors,
camera motion and timestamps. It arms a class once before the first frame, then never
consults annotations or reselects a target. A configuration file contains only the
`tracking` object, not the host's full perception config.

```bash
python3 bench/fresh_target_replay.py /tmp/garuda-person-trial \
  --binary /tmp/garuda-fresh/native/garuda-track-replay --label person \
  --config /tmp/candidate-tracking.json --output /tmp/person-candidate.jsonl
python3 bench/fresh_target_score.py /tmp/garuda-person-trial \
  --annotations /tmp/person-truth.json --predictions /tmp/person-candidate.jsonl \
  --output /tmp/person-candidate-score.json
```

Replay records binary/config hashes and timing scope. It does **not** measure candidate
CPU/NPU latency, rerun detection or generate absent learned embeddings. Sparse captures
cannot recreate missing tracker updates. Alternative model inference must separately
produce predictions for every exact input, with matching source/frame/hash fields and
full-FOV geometry. Coverage mismatch, reordered frames and mixed provenance are errors.

## Definitions and limits

These are selected-target metrics, not standard MOTChallenge MOTA/IDF1:

| Output | Definition |
|---|---|
| Detector target recall | Visible labelled frames with a same-class detection at confidence ≥0.4 and clipped IoU ≥0.5, divided by visible labelled frames. Both thresholds are explicit CLI options. |
| Correct visible fraction | Intended epoch/class, valid observed lock, and a box uniquely matching the labelled target at the IoU threshold. Missing, misplaced or unverified-overlap boxes do not count as correct. |
| Correct visible control fraction | The same correct observation also claims valid control. Reported separately because a visible tracked box can still be too uncertain or stale for follow. |
| Observed-box IoU median | Target IoU on all visible selected frames claiming an observation, including zero for absent/misplaced boxes; not only successful matches. |
| Physical identity switches | Changes between uniquely matched labelled physical identities during a continuous annotated segment and unchanged epoch. An unlabelled background box is not assigned an invented identity. |
| Correct-target MOT ID changes | Numeric track-ID changes while uniquely matching the intended physical target. Reported separately from physical identity switches. |
| False reacquisition events | A claimed observation matching a labelled wrong object after a frame without a valid observation, within a continuous segment and unchanged epoch. Initial wrong selection and direct switches are covered by wrong-object frames/switches, not this event count. |
| Incorrect or unverified control | Frames claiming valid control without a correct observed target under the above rule, including unknown identity due to overlapping labelled boxes. Unknown-truth frames are unscored. This does not replace freshness/controller invariant tests. |
| Visible lost time | Left-sample-weighted time without a correct observation while the target is visible. Only adjacent sequence numbers, positive gaps ≤100 ms, known annotations and active selection at both ends contribute. No duration is invented after the last frame. |
| Visible control-unavailable time | The same eligible intervals without a correct observation that also claims valid control. This measures source-output availability, not actual controller consumption. |
| Recovery episodes | Delay from first visible miss to first correct observation; visible entry/return is distinguished from loss while visible. A visible return already correct has zero sampled delay. Gaps, unknown truth, hiding again or recording end retain censored episodes rather than discarding failures. This is sampled timing, not sub-frame ground truth. |
| Epoch mismatch | Output selection differs from the annotated intended epoch; never silently rebound. |

Missing denominators are null, not zero or 100%. Sequence/time gaps and annotation
coverage are explicit. Overlapping truth boxes can leave physical identity unverified;
they are reported separately. Identity accuracy requires sufficiently complete labels,
and a single scene cannot establish population-level accuracy.

`recorded_capture_to_output_ms` describes timestamps in the result. For live same-callback
outputs it excludes HTTP/SDK/control delivery. Replay preserves original processing
timestamps for deterministic gating; this number is **not** replay-candidate runtime.
Use the board latency/resource harnesses for runtime comparisons.

Validation: eleven metric/integrity scenarios plus existing capture/transport tests pass.
An actual C++ tracker replay of a synthetic visible phone with four missing detections
reports 0.8 detector recall, 350 ms lost visible time (150 ms initial confirmation plus
200 ms dropout), 200 ms dropout recovery and no physical switch. This validates the
scoring/integration path; no pixels or physical tracking accuracy are simulated as real.

Evidence: [evaluation harness report](../../bench/results/2026-09-10-fresh-tracking/target-evaluation/README.md).
The [full delivery requirements](DELIVERY.md) remain open.
