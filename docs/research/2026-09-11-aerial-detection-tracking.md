# Robust Detection and Visual Tracking for a Moving Camera

## Executive assessment

The present Hailo-15L phone demonstration is not an adequate baseline for evaluating robust aerial follow-me perception. It runs a real YOLO11s model, but inside an adapted surveillance-camera pipeline with different preprocessing, detector thresholds, tracking rules and reporting semantics from the successful Raspberry Pi demonstration. Successful model loading and visible boxes establish functionality, not accuracy, timing correctness or reliable identity retention.

The most defensible course is to retain the hardware and project, establish a measurable detector baseline, and correct the known integration mismatch before selecting a new model or camera. Letterboxing is a high-priority experiment, not a complete solution. The specific compiled model's preprocessing contract must determine the reference implementation.

Aerial benchmarks confirm that small image footprints, camera motion, occlusion and changing viewpoints make detection and tracking difficult. They do not establish that a black cellphone must fail, or that YOLO11 cannot support this application. Nor do they establish that a newer model will fix the current implementation. [VisDrone][1] and [UAVDT][2] provide relevant evidence, but neither is a phone-specific validation set.[^1][^2]

For civilian follow-me and camera framing, robustness should mean maintaining a correctly identified, sufficiently fresh observation within a declared operating envelope, and explicitly reporting uncertainty outside it. An indefinitely green box is not a useful acceptance criterion. Wrong-object continuation can be worse than honest loss of tracking.

The recommended sequence is: instrumentation and empty-frame semantics; matched preprocessing and quantized-model validation; raw detection evaluation; tracking and camera-motion compensation; bounded recovery; then recorded aerial evaluation. No live flight integration is part of this report.

## 1. Evidence and applicability

This assessment combines public primary research, official software/hardware documentation, and the checked-in Garuda implementations. Public sources were reviewed on September 11, 2026. Historical research is used for established mechanisms and benchmark design, not presented as a current leaderboard. Documentation on moving branches may change; implementation work should pin versions.

Three evidence levels must remain distinct. First, code establishes what an implementation is configured to do. Second, existing desk observations establish that certain output was produced, including a roughly 33 ms auto-exposure reading and adapter session changes. Third, aerial papers establish behavior on their own datasets and hardware. None independently measures this board's aerial accuracy.

There is currently no labeled, synchronized replay comparison of the Pi and Hailo-15L; no validated source-to-host clock mapping; and no raw detector-versus-tracker trace through the problematic movement. Consequently the proportion of failure due to preprocessing, detector confidence, blur, association or UI semantics remains unmeasured.

The intended targets should also be distinguished. A nearby phone is a useful regression object, but a person or vehicle viewed from above is a different appearance distribution. Distance and aircraft speed alone do not describe the difficulty. Target size in detector pixels, relative image motion, visibility and observation age are the useful variables.

## 2. What the project code establishes

### Two different Pi baselines

The older `services/garuda-track/track_service.py` defaults to YOLOv8m, a single resized RGB input and the project's custom ByteTracker. Its existing bench log reports approximately 29.6 processed capture–detect–track frames/s in one configuration. This is historical project evidence, not a new measurement or a YOLO11 result.

The newer `hosts/pi5/garuda_mono.py`, including the portal-tracking worktree, defaults to YOLO26m. It takes the latest distinct camera frame, runs detection on each processed frame, and runs depth periodically. Its camera configuration is 1280×720 at 15 fps. “Every processed frame” does not imply that the loop can never skip camera frames under load.

The newer detector uses 640×640 letterboxing, gray padding and BGR-to-RGB conversion. The detector floor is 0.15; the tracking configuration has a 0.4 high threshold, 0.12 low threshold, two confirmation hits and 25 missed updates of retention. Because the detector already rejects scores below 0.15, the effective low-score input begins at 0.15, not 0.12. [Local Pi source][L1][^18]

### Current 15L differences

| Dimension | Newer Pi path | Adapted Hailo-15L phone path | Interpretation |
|---|---|---|---|
| Default model | YOLO26m | YOLO11s | Not a model-controlled comparison |
| Input preparation | One letterboxed RGB image | Five stretched NV12 crops | Geometry and input path differ |
| Detection scheduling | Each distinct processed frame, batch 1 | Every other input frame, five crops | More work per detection opportunity |
| Host confidence floor | 0.15 | 0.38 | Weak evidence reaches one tracker but not the other |
| Track creation | High threshold 0.4, two hits | Stock header defaults: 0.5, three confirmation frames | Display can lag first raw detection |
| Miss handling | Retains predicted tracks up to 25 updates | Header default maximum missed frames 3 | Counters have different semantics; not a measured time ratio |
| Recovery | Can select a new same-class track | Manual reselection after latched loss | Visible persistence is intentionally different |
| Output | Includes retained/coasting state | Confirmed Hailo tracks, then phone-only filtering | Current boxes are not raw YOLO output |

These are source/configuration findings. The internal Hailo tracker counter timing still needs runtime verification. Comparing “25 versus 3” as exact seconds or as an eightfold lifetime increase would be unjustified. The saved phone patch and deployment record identify the compiled application and HEF. [Local 15L record][L2][^19]

### A confirmed reporting mismatch

The Hailo metadata packager returns without sending when there are no detections, landmarks or classifications. The phone filter runs before this packager. No retained phone can therefore mean no packet, even while frames continue through the camera pipeline. The adapter interprets silence as stale input after 300 ms and reconnects after its WebSocket receive timeout; reconnect creates a new source session.

This explains a concrete route from a brief absence to a stale display, changed session and latched lost selection. It does not prove the camera or inference engine has stalled. Earlier interpretations of silence as a pipeline stall were too strong. Empty-frame reporting must be corrected at the producer, or accompanied by an independent frame heartbeat; merely increasing a timeout would obscure actual outages. [Adapter][L3] and Hailo `analytic_metadata_packager_stage.cpp`, `build_metadata_proto()`/`process()`.[^20]

### The Pi tracker is not an unmodified reference ByteTrack

Its source describes a lean implementation with linear motion and greedy IoU association. It uses a second matching pass for low-score detections, but it does not implement the entire published algorithm. A local synthetic test demonstrated that a 0.20-confidence detection can continue a phone track and that the track remains stored through 25 empty updates.

The same test demonstrated an important defect: the matcher does not gate on class, so an overlapping `remote` detection can inherit a `cell phone` track ID. Also, its velocity update uses displacement since the previous measurement without dividing by missed intervals or elapsed time; after a gap that can exaggerate subsequent predictions. The newer viewer can additionally replace a coasting selection with a different live track of the same class. These mechanisms may explain apparent smoothness without demonstrating durable identity. [Local tracker][L4][^21]

Therefore the Pi is valuable as a regression reference, but should not be transplanted wholesale or described as proof that a particular tracker is flight-ready.

## 3. Letterboxing, distortion and the pixel budget

Ultralytics' documented prediction path uses aspect-preserving resizing and padding. For a fixed-shape exported backend, padding to the full target shape is distinct from dynamic minimum-rectangle inference. A fixed 640×640 HEF cannot be assumed to accept a 640×360 tensor. The Hailo Model Zoo separately documents padding, normalization and color-conversion settings; the specific model build must be checked. [Ultralytics prediction][3], [Hailo YAML reference][4].[^3][^4]

For an illustrative 1920×1080 input, direct stretch to 640×640 scales width by 1/3 and height by approximately 0.593. Letterboxing scales both axes by 1/3, produces 640×360 content and adds 140 pixels of padding above and below. Thus stretching makes the object approximately 1.78 times taller relative to its width than aspect-preserving resizing.

This is a meaningful change in appearance, particularly for a narrow rectangular phone. But letterboxing also allocates fewer tensor rows to the image. It may improve shape consistency while reducing a small object's vertical pixel extent. That tradeoff is why identical-frame detection tests, rather than visual preference, must choose the implementation.

The following are illustrative calculations, not measurements of the current AI stream. For a 3840-pixel-wide source and a 640-pixel-wide full-frame input:

| Object width in original image | Full-frame detector width | Width after using a crop spanning 60% of source width |
|---|---:|---:|
| 24 pixels | 4 pixels | 6.7 pixels |
| 60 pixels | 10 pixels | 16.7 pixels |
| 120 pixels | 20 pixels | 33.3 pixels |

Both values assume the object is fully inside the crop and the width scale governs aspect-preserving resizing. The current four regional tiles each span 60% of the input width, plus one full-frame tile. That is only about 1.67× linear magnification over a full-frame pass, not a dramatic small-object zoom. Extra scaling elsewhere in the camera pipeline must also be accounted for.

No universal minimum pixel size guarantees recognition. A few pixels may support a coarse detection in a favorable dataset while carrying insufficient appearance information to distinguish one object from another. Upscaling, sharpening and learned super-resolution cannot be treated as verified recovery of missing identity information.

SAHI is direct evidence that sliced inference and slicing-aware training can improve aerial small-object detection on VisDrone and xView. Its results are detector/dataset-specific, not guaranteed gains for YOLO11s or the 15L. Its multiple inference windows also consume processing time. The implication is to benchmark full-frame, tiled and selected-region processing jointly for recall and observation age. [SAHI paper][5].[^5]

For a selected civilian filming subject, an engineering candidate is a full-frame discovery path combined with a higher-resolution region around the selected object. The region must expand with uncertainty, and periodic global discovery must remain available. A region that follows the wrong prediction can otherwise lock the detector out of the real object's location. This is a proposed architecture, not an implemented or validated fix.

## 4. Why fast camera motion changes the problem

The relevant quantity is image displacement between usable observations. A stationary person can move rapidly across the sensor when a camera pans; a fast-moving aircraft with a stabilized camera can have relatively slow target image motion. Aerial benchmarks and tracker evaluations explicitly identify camera motion, rotation, smaller targets and distractors as challenges. [Aerial tracker evaluation][6].[^6]

Two simple analytical relationships help specify tests:

`motion smear in pixels ≈ image velocity in pixels/second × exposure time in seconds`

`uncompensated displacement in pixels ≈ image velocity × observation delay`

For an illustrative 600 pixels/second image velocity, 33 ms exposure produces about 19.8 pixels of smear; 10 ms produces 6 pixels. A 100 ms-old observation has about 60 pixels of uncompensated displacement. These are illustrative constant-velocity calculations, not measured board performance and not recommended exposure settings.

Long exposure and delayed observations are different errors. Raising reported video fps cannot remove exposure smear, and shortening exposure cannot remove queue backlog. Conversely, a low-noise image at long exposure can be less useful for a moving small target than a noisier but sharper image. Robustness studies show detection degradation under image corruptions, but do not identify the present phone's dominant failure cause. [Detection robustness benchmark][7].[^7]

Rolling shutter adds a third effect: different rows are exposed at different times. Short exposure reduces within-row motion blur but does not itself eliminate row-to-row geometric skew. Global shutter addresses that timing difference, but is not a substitute for adequate light, short enough exposure, correct software or sufficient object pixels. Basler's explanation is general sensor evidence, not an IMX678-specific timing specification. [Electronic shutter types][8].[^8]

Stabilization, camera calibration and motion estimation should therefore be considered together. Stabilization can reduce image motion but may crop the field of view. Digital warping requires correct coordinate transforms. Background-motion compensation can fail with strong parallax, little texture, rolling-shutter distortion or a scene dominated by moving objects. Any motion estimator needs a confidence signal and a fallback, rather than unconditional use.

## 5. Tracking and lock are separate estimators

ByteTrack's central result is that lower-confidence detections can recover associations that would be lost by discarding those boxes. This supports preserving an appropriate low-score candidate stream for matching existing tracks while using stricter criteria to create new ones. It does not justify lowering every threshold and showing every weak box as a valid target. [ByteTrack][9].[^9]

BoT-SORT combines motion and appearance cues with camera-motion compensation. Its published results concern multi-pedestrian tracking; direct transfer to tiny phones or distant overhead vehicles is unproven. Nevertheless it is a useful reference implementation for a moving-camera comparison, unlike a tracker that assumes image motion arises only from the target. [BoT-SORT][10].[^10]

Single-object tracking is also relevant: after an operator selects an object, a visual tracker can follow its appearance without requiring the detector to rediscover its class on every frame. HiFT and AutoTrack are public aerial-tracking examples. They support evaluating a selected-object branch, but their published speed and accuracy cannot be assumed on Hailo-15L. A learned tracker requires operator/compiler feasibility checks; a CPU tracker requires an on-board latency budget. [HiFT code][11], [AutoTrack][12].[^11][^12]

An appearance tracker can drift; a detector can rediscover a different object of the same class; a ReID model can confuse similar low-resolution instances. Agreement between these signals is useful, but no component creates identity certainty from an uninformative image. ReID compatibility and training domain must be verified separately from whether an OSNet HEF happens to exist on disk.

### Recommended state semantics

| State | Meaning | Required display/consumer behavior |
|---|---|---|
| Observed | Recent image evidence supports the selected identity | Report evidence timestamp and uncertainty |
| Predicted | A short gap is being bridged by a motion model | Clearly distinguish from measurement; do not renew measurement age |
| Ambiguous | Multiple plausible candidates or conflicting evidence | Do not silently switch selection |
| Lost | Evidence is too old, absent or unreliable | Explicit loss; bounded recovery procedure |
| Reacquired | Evidence supports a candidate after loss | Preserve provenance; report whether identity is confirmed or only hypothesized |

These are proposed interface semantics, not certified flight logic. A numeric MOT ID is scoped to a tracker session and does not itself establish physical identity. For a future vehicle integration, acceptable age and uncertainty must come from the wider system's operating envelope; the present viewer should continue exposing no valid control output.

## 6. Hardware and compiled-model correctness

The Pi/Hailo-10H and Hailo-15L are not interchangeable compute platforms. Hailo lists 40 TOPS INT4 and 20 TOPS INT8 for the 10H; the 15L brief lists 7 TOPS. Comparing 40 with 7 as if both numbers predicted the same model's speed would be misleading. TOPS also excludes important CPU, memory, scheduling and image-processing costs. [10H product specifications][13], [15L brief][14].[^13][^14]

At a hypothetical 30 input frames/s, five crops on every other frame ask for 75 crop inferences/s. That is a workload calculation, not a throughput measurement. A five-crop batch may amortize overhead, but can also add waiting and pressure to aggregation. It is not automatically worse than batch one; both latency tails and useful detection rate must be measured.

Hailo explicitly recommends evaluating full precision and optimized/quantized models because both optimization and quantization can change accuracy. The current filename, architecture match and successful runtime execution do not prove numerical parity. [Hailo optimization workflow][15].[^15]

For the exact YOLO11s HEF, record the original checkpoint, export graph, input conversion, normalization, compiler version, calibration dataset, precision policy, output decoder and embedded NMS parameters. If these build artifacts are unavailable, report that provenance gap rather than assuming the generic model-zoo settings apply.

NV12 handling deserves particular attention: color conversion must occur exactly once, with the expected range and color matrix; plane layout and stride must match the backend. Coordinate inversion must include crop offsets and padding. The latest-frame path, video path and inference path must agree on image orientation and sensor crop. These are validation targets, not currently demonstrated faults.

A second source-level issue needs investigation before changing the Hailo tracker: its stage obtains tracklets from `predict`, calls `update`, then renders the earlier returned structure. The SDK header says the structure is internal transient storage. That means neither a definitive one-frame lag nor definitive freshness can be inferred merely from call order. A deterministic sequence or documented API behavior is needed. Do not “fix” it by blindly predicting twice.

## 7. Proposed validation program

### Phase A: Restore observability without changing detection

Produce one metadata record per processed source frame, including explicit empty results. Identify detector-run versus tracker-prediction frames. Preserve source timestamps, sequence, crop geometry, detector candidate counts, tracker decisions and transport errors. Distinguish empty content from missing transport.

Record raw detections before tracking, tracked outputs after association, and selected-object state separately. Show all classes in the diagnostic view, with the selection filter applied independently. Attach detections to their actual source image rather than whichever video frame is newest. The first success criterion is a trace that can explain each lost selection, not a higher fps number.

Acceptance checks: an empty scene advances frame state without creating new source sessions; a genuine disconnect invalidates the view; cached frames do not refresh measurement age; and loss cannot turn into silent reassignment. Existing unit tests should be extended to cover actual native empty-frame behavior, not just synthetic adapter frames.

### Phase B: Freeze a replay dataset

Use identical captured frames for software comparisons. Include a static phone at several apparent sizes, movement of the phone with a stationary camera, movement of the camera with a stationary object, partial occlusion, exits/re-entries and same-class distractors. Record front/back and rotated phone views, light/dark backgrounds, and camera settings.

Include empty scenes and difficult negative objects such as remotes. Otherwise lowering thresholds can appear to improve recall while increasing false positives unnoticed. Retain original frames and timestamps. Prefer original or lightly compressed recordings; replay after video compression is a separate test because compression can change small-object evidence.

Label boxes, identities, visibility, and whether the object is actually identifiable. Split by entire recording session, not random adjacent frames, to avoid evaluation leakage. Small-object size bins such as under 8, 8–16, 16–32 and over 32 detector pixels are proposed diagnostic bins, not universal pass/fail boundaries.

### Phase C: Preprocessing and model parity

Compare stretch and letterbox on the same model and frames with identical thresholds. Save or inspect the actual tensor/crop presented to inference. Validate inverse box mapping with synthetic known rectangles and real labeled images. Compare the model's floating-point reference, quantized emulator where available, and board output under matching preprocessing.

If the float model succeeds but the compiled model fails, investigate conversion, calibration and decoding. If both fail on sharp sufficiently detailed targets, investigate model/data suitability. If the detector succeeds but the tracker fails, model replacement is not the primary repair. Capture these branches in the experiment report before changing multiple parameters.

### Phase D: Tracking ablation

Freeze detector results and replay them through the current tracker, a maintained reference implementation, and a motion-compensated candidate. This separates tracking quality from inference variability. Compare confidence floors and birth thresholds independently. Ensure low-score candidates are not already removed by embedded NMS before the tracker can use them.

Evaluate observed and predicted frames separately. Measure how long a retained box remains on the correct object rather than counting stored tracks as successes. Test class confusion, crossings, abrupt camera movement and out-of-frame return. The Pi custom matcher and its automatic same-class recovery should be explicit baselines, not the trusted answer.

### Phase E: Small-object and timing tradeoffs

Compare one full-frame pass, the existing five tiles, and a bounded selected-region plus global-discovery configuration. Measure target pixels, recall, duplicate boxes, crop-boundary failures and p95/p99 observation delay. Raising model input resolution usually requires a compatible export and new HEF, not just changing a UI dimension.

Measure sensor exposure, capture timestamp, preprocessing, submit/completion, aggregation, track update and display timestamps. Until clocks are mapped, label measurements as host-local intervals rather than end-to-end image age. Run long enough to expose thermal limits and queue growth. Metadata message rate and video refresh rate must not be reported as detector fps.

### Phase F: Public aerial footage and controlled field capture

VisDrone supplies detection, video, single-object and multi-object tasks; UAVDT adds a useful aerial detection/tracking test domain. Use their official splits and evaluation conventions, and map class labels explicitly. They complement, rather than replace, the local phone tests. [VisDrone dataset][16], [UAVDT][2].[^16][^2]

Only after replay gates pass should controlled moving-camera outdoor recordings be added, with consent where people are recorded and without autonomous target-following control. Test each declared operating envelope independently: size, lighting, motion, occlusion and distractor density. Out-of-envelope rejection is a necessary result, not a failure to hide.

## 8. Metrics and decision rules

Detection reporting should include per-class precision/recall, confidence sweeps, localization error, missed-detection burst length and performance by target size and motion. Track reporting should include identity switches, fragmentation, wrong-object retention and recovery latency. HOTA is useful because it balances detection, association and localization rather than allowing one dimension to dominate. [HOTA][17].[^17]

For the selected subject, separately report: fraction of visible identifiable time correctly observed; fraction only predicted; longest unsupported prediction; incorrect same-class reassignment; time until explicit loss; and observation-age percentiles. A headline “lock retained 99%” is meaningless if predicted and wrong-object intervals count as success.

No defensible universal lock percentage, exposure time or fps threshold can be assigned from this desk evidence. Define acceptance values before experiments using the intended filming distance, target size, allowable image error, camera motion and uncertainty limits. Zero observed identity switches in a small test is not proof of zero field risk; report sample size and failure exposure.

Advance only if an experiment improves the intended metric without unacceptable regressions. Do not trade substantial observation delay for a small still-image AP gain without accounting for image motion. Do not trade real loss reporting for cosmetic persistence. Preserve the person baseline and each reproducible experimental configuration.

## 9. Priorities and remaining uncertainties

The immediate priorities are the empty-frame/reporting repair, raw-versus-tracked instrumentation, and exact preprocessing parity. Letterboxing should be the first controlled detector experiment after those foundations, not a promise of resolution. Confidence and tracking changes follow on fixed detector output; camera-motion compensation and resolution scheduling follow once timing is observable.

The project already contains usable 15L model candidates, including YOLO11m, YOLOv8m and YOLO26m HEFs. Their presence does not establish comparable training provenance, runtime cost or accuracy. Benchmark only candidates with validated input/output contracts and a declared reason for comparison. A model-name ladder is not an engineering plan.

The key unresolved questions are the exact HEF's training/calibration preprocessing, where raw phone evidence disappears, how Hailo's tracker advances its missed-frame counters, the freshness of its returned tracklet storage, actual image-to-observation delay, and the Pi's last deployed overrides. These should be resolved before attributing the problem to camera quality, black coloration or YOLO11 itself.

The recommended architectural direction is a corrected, timestamped detector pipeline; a tested tracker with explicit camera-motion handling where beneficial; and a selection owner that separates observed, predicted, ambiguous and lost states. Retain the current bench-only separation from control. This is a stronger basis for future aerial robustness than either abandoning the project now or making the existing box persist longer.

## Sources

[^1]: Zhu et al. *Vision Meets Drones: A Challenge*. 2018. [Original paper][1]. Aerial detection/tracking challenges; not phone-specific evidence.
[^2]: Du et al. *The Unmanned Aerial Vehicle Benchmark: Object Detection and Tracking*. 2018. [Original paper][2]. UAVDT conditions and evaluation domain.
[^3]: Ultralytics. *Model Prediction with Ultralytics YOLO*. Live documentation, reviewed September 11, 2026. [Documentation][3]. Letterbox and fixed/dynamic input behavior.
[^4]: Hailo. *Model Zoo YAML Description*. Moving master branch, reviewed September 11, 2026. [Documentation][4]. Padding, normalization and conversion configuration.
[^5]: Akyon, Altinuc and Temizel. *Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection*. 2022. [Original paper][5]. Sliced inference on aerial datasets; results are not a 15L benchmark.
[^6]: Taufique, Minnehan and Savakis. *Benchmarking Deep Trackers on Aerial Videos*. Sensors 2020; arXiv version 2021. [Original paper][6]. Aerial target-size and camera-motion challenges.
[^7]: Michaelis et al. *Benchmarking Robustness in Object Detection: Autonomous Driving when Winter is Coming*. 2019. [Original paper][7]. Image-corruption robustness; predates YOLO11.
[^8]: Basler. *Electronic Shutter Types*. Live product documentation, reviewed September 11, 2026. [Documentation][8]. Generic shutter principles, not this board's sensor characterization.
[^9]: Zhang et al. *ByteTrack: Multi-Object Tracking by Associating Every Detection Box*. 2021 preprint; ECCV 2022. [Original paper][9]. Two-stage association motivation.
[^10]: Aharon, Orfaig and Bobrovsky. *BoT-SORT: Robust Associations Multi-Pedestrian Tracking*. 2022. [Original paper][10]. Motion/appearance/camera-motion association.
[^11]: Vision4Robotics. *HiFT: Hierarchical Feature Transformer for Aerial Tracking*. ICCV 2021, author-maintained [implementation][11]. Public aerial single-object tracker; no demonstrated Hailo compatibility.
[^12]: Li et al. *AutoTrack: Towards High-Performance Visual Tracking for UAV with Automatic Spatio-Temporal Regularization*. 2020. [Original paper][12]. Alternative aerial single-object tracking reference.
[^13]: Hailo. *Hailo-10H AI Accelerator*. Live specifications, reviewed September 11, 2026. [Product page][13]. INT4 versus INT8 ratings.
[^14]: Hailo. *Hailo-15L AI Vision Processor Product Brief*. Undated PDF, reviewed September 11, 2026. [Product brief][14]. 15L compute and camera-platform context.
[^15]: Hailo. *Model Optimization*. Moving master branch, reviewed September 11, 2026. [Documentation][15]. Full-precision and quantized evaluation workflow.
[^16]: AISKYEYE/VisDrone. *VisDrone-Dataset*. Author-maintained [dataset repository][16], reviewed September 11, 2026. Task definitions and official data links.
[^17]: Luiten et al. *HOTA: A Higher Order Metric for Evaluating Multi-Object Tracking*. 2020 preprint; IJCV 2021. [Original paper][17]. Detection/association/localization evaluation.
[^18]: Garuda local source: `hosts/pi5/garuda_mono.py`, `hailo_yolo26.py`, `services/garuda-track/track_service.py`; portal-tracking variant in `.claude/worktrees/feat+portal-tracking/`. [Pi entry point][L1]. Defaults are not proof of deployed environment overrides.
[^19]: Garuda local source: `hosts/hailo15l/stock-phone/phone-baseline.patch` and [deployment record][L2]. Hailo source base v1.12.0, commit `9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f`.
[^20]: Garuda [adapter][L3]; local Hailo source `/tmp/garuda-stock-yolo11-src/hailo-analytics/hailo_analytics_api/src/pipeline/codecs/analytic_metadata_packager_stage.cpp`, lines 260–327. Header `/media/bhanu1234/Development/hailo15/sdk/sysroots/armv8a-poky-linux/usr/include/hailopp/hailotracker.h`. Source-level evidence; binary behavior must be pinned in implementation tests.
[^21]: Garuda [custom tracker][L4]. Synthetic tests during the code review showed low-score continuation, 25-update storage retention and cross-class ID reuse. These are tests of local logic, not accuracy measurements on aerial footage.

[1]: https://arxiv.org/abs/1804.07437
[2]: https://arxiv.org/abs/1804.00518
[3]: https://docs.ultralytics.com/modes/predict/
[4]: https://github.com/hailo-ai/hailo_model_zoo/blob/master/docs/YAML.rst
[5]: https://arxiv.org/abs/2202.06934
[6]: https://arxiv.org/abs/2103.12924
[7]: https://arxiv.org/abs/1907.07484
[8]: https://docs.baslerweb.com/electronic-shutter-types
[9]: https://arxiv.org/abs/2110.06864
[10]: https://arxiv.org/abs/2206.14651
[11]: https://github.com/vision4robotics/HiFT
[12]: https://arxiv.org/abs/2003.12949
[13]: https://hailo.ai/products/ai-accelerators/hailo-10h-ai-accelerator/
[14]: https://hailo.ai/hailo-files/hailo-15l-product-brief-en/
[15]: https://github.com/hailo-ai/hailo_model_zoo/blob/master/docs/OPTIMIZATION.rst
[16]: https://github.com/VisDrone/VisDrone-Dataset
[17]: https://arxiv.org/abs/2009.07736
[L1]: /media/bhanu1234/Development/GARUDASDK/hosts/pi5/garuda_mono.py:149
[L2]: /media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking/hosts/hailo15l/stock-phone/README.md
[L3]: /media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking/services/garuda-tracking/hailo_adapter.py:166
[L4]: /media/bhanu1234/Development/GARUDASDK/services/garuda-track/bytetrack.py:40
