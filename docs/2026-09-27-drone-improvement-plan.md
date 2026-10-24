# Drone-footage improvement loop

Use the existing VisDrone footage as regression data. Keep the accepted live
camera deployment and all vehicle interfaces unchanged. Neither phone success
nor a higher count of valid boxes establishes drone-following safety.

## Current work

Latest owner scope is **tracking and short eMMC recording only**, non-extreme
conditions. Follow `docs/2026-09-27-track-record-readiness.md`: complete11-clip
baseline/data audit done; recording tests exposed eMMC stalls and a faulty new
RAM admission check. Board SSH/API stalled in the third test; owner intervention
restored access. Existing unchanged camera restored; corrected non-CMA receiver
passed one16-sample local integrity smoke test (capture04,2466.709ms source span).
This does not qualify sustained recording or tracking accuracy. No live tracking/
model/profile promotion or flight authorization. Do not reuse old staged receivers.

1. Reproduce the small-car failure with the current compiled tracker, fixed
   source frames, identical detector/descriptor models and initial click.
2. Compare fullview versus fullview+ROI on car245 and car115. Score correct boxes,
   zero/low overlap, acquisition and measured compute plus declared source age.
3. Reject the ROI mode if it introduces bad target bindings, even if local
   detections are sharper or more confident. Preserve its failures as regressions.
4. Separately test default-off `defer_person_embeddings_on_car`: a car uses
   histogram evidence, not person OSNet. Keep histograms, person detection,
   association, recovery and expiry unchanged. Re-enable descriptors on pending
   person selection, person tracking, car loss or embedding-based association.
5. Use identical-binary OFF/ON runs of both cars and person024 as a class-isolation
   regression. A timing gain is not a localization gain; quantify both.

Results: `bench/results/2026-09-27-drone-detail/` and
`bench/results/2026-09-27-drone-budget/`. All are bench-only. The aerial comparison
profile includes experimental crowd recovery, unlike the live desk profile;
results cannot be described as current live-camera accuracy.

## Next priorities, in order

- Recovery follow-up completed: default-off `car_recovery_detection_veto` catches
  the excluded-current-evidence failure, removing55 zero-overlap outputs in245 ROI
  while retaining53 correct ones. **Rejected for deployment**: fullview245 loses
  three correct observations and car115 ROI drops71->41 correct. The guard is a
  retained bench experiment, not an enabled fix. Evidence:
  `bench/results/2026-09-27-car-recovery-evidence/README.md`. Next diagnose whether
  competing crops are duplicates/background contamination or genuine rivals and
  preserve both positive/negative recovery counterexamples before changing rules.
- Repair the new ROI recovery failure before promoting detail scheduling. Trace
  the last correct target, competing detections and recovery evidence, add a
  regression, then change one rule. Do not enlarge boxes using truth or relax
  identity gates to make overlap scores look better.
- Separate tiny-object detector coverage from refusal despite usable same-class
  detections. The new paired evaluator distinguishes wrong-class/weak detections,
  invalid tracking and incorrect valid output. A class-agnostic hit is insufficient.
- Address person acquisition and incomplete crowd descriptors on 024/054/086,
  and detection/acquisition failures on 092/317, with all failures retained in
  the campaign denominator. Protect person-selection responsiveness when saving
  non-person compute.
- Audit training/evaluation sequence provenance and reserve additional flight
  sequences before tuning again. The eleven SOT validation clips already informed
  development; they are not held-out. Nearby clips from the same flight do not
  establish independence. No new dataset download or training is started here.
- After fixed-input regressions pass, repeat measured latest-frame scheduling.
  Only then run a fresh live A/B with rollback, before any simulated follow or
  eventual separately authorized vehicle qualification.

## Evaluation discipline

`bench/hailo_reference/compare_target_replays.py` requires complete identical
fixed-stride frame sets, matching source/annotation/protocol and successful
restoration. Its conservative quality screen refuses lost correct observations,
new off-target outputs, zero-overlap outputs and reduced timely correct outputs.
It reports gains separately from mere non-regression. All boxes are scored at the
existing IoU>=0.5 threshold; low IoU is not automatically a proven identity switch.
Never-acquired/empty runs cannot pass. Unit tests cover malformed evidence and
the previously missed low-overlap regressions.

Also retain source-wide time-weighted correct AND incorrect availability with
the existing 200 ms evaluation expiry. Fixed stride and assumed 50 ms source age
are disclosed, not represented as live exposure-to-controller timing. Faster
wrong boxes remain wrong. No agreed product acceptance threshold or flight gate
is silently replaced by this regression screen.

Structural scope: reuse the existing capture/replay, native tracker, ROI planner
and model interfaces. No second tracker, new dependency or FC integration. Keep
experimental options default-off; avoid adding further heuristics until the
current experiments and counterexamples are understood.
