# Track and record: staged drone-mount readiness

Owner scope (2026-09-27): **track and record for now**. No autonomous following,
FC connection, setpoints, arming, gimbal commands or flight authorization. Current
status: **not mount-qualified; camera restored, one short local recording passed**.
SSH/camera API became unresponsive during the third capture; ping and serial kernel
messages were observed during that incident. Final live health could not be verified.
After the owner's power-cycle confirmation, the 2026-09-27 17:10 IST recovery
check found PC eno1 NO-CARRIER, no SSH/ping/API response, and no usable serial
prompt during a bounded probe. Recovery remains unverified; no new capture,
deployment, deletion or agent-initiated reboot was performed.
At 17:12 IST, after further owner intervention, Ethernet/SSH recovered with new
boot ID eb5db10e-a888-48af-8a64-c0900cea81ba. Protected node/config hashes match.
Existing start-current restored the camera. Corrected capture04 saved and verified
16 paired samples (2466.709 ms source span, 31,948,800 pixel bytes) on eMMC.
Postcheck shows advancing sequence, no capture error and 372700 KiB non-CMA
headroom. This supersedes the access blocker, not the readiness failures below.
Capture03 retained 108 metadata/frame sets but failed correspondence validation;
there is no complete footer. Prior-boot crash cause is still unconfirmed.
This supersedes autonomy as the immediate milestone,
not the separate future flight-control safety requirements. Owner subsequently
specified non-extreme conditions and **eMMC only for short tests**. Use a daylight,
gentle-motion initial envelope; exact height/speed remain unqualified.

## What confidence will mean

These are proposed engineering acceptance checks, NOT measured passes or a safety
certification. Target class, flight envelope, mounting and recording medium still
need further definition (storage is now eMMC for short tests). Start with daylight,
cooperative subjects, manual piloting and
no dependency of aircraft control on this computer. Do not infer altitude from a
target pixel size without camera calibration and the actual mount/FOV.

| Stage | Required evidence | Current state |
| --- | --- | --- |
| Development regression | All retained failures included; no new incorrect bindings or lost correct observations in paired tests | Latest recovery guard fails; stays off |
| Independent footage | Freeze flight/scene-disjoint test split before tuning; audit training/calibration/model-selection overlap | Eleven local SOT clips are development data, no untouched holdout |
| Field-scale camera bench | Known intended classes/sizes; pans, blur, tilt, re-entry, similar distractors and absent-target trials; label fresh captures | Needed on the actual IMX678/mount |
| Standalone recording | No laptop required; frames/outputs paired; explicit drops/truncation/storage stop; playable video and reviewable metadata | Local bounded raw receiver implemented; camera/long-duration qualification pending |
| Sustained load | At least intended sortie duration plus margin; initially propose30min; timestamp gaps, storage rate, temperature, power and recording load logged | Not measured; no pass inferred from replay |
| Physical install | Secure mount, cooling, power headroom, cable retention, vibration/FOV checks; operator approval | Hardware-dependent, pending |
| Recording-only flight | Pilot/operator approves a bounded manual flight; no FC authority; review recordings before widening conditions | Not authorized by software tests |

Proposed perception screening targets for a declared operating envelope: acquire
within2s in at least90% of eligible trials; correct observed boxes (IoU>=.5) on at
least90% of visible processed frames after acquisition; report each scenario, not
only pooled counts. These numbers are candidate requirements, not validated
product limits. Annotate visibility/occlusion separately. Also score ALL source
frames, blackout duration, center error, ID mistakes and actual capture-to-overlay
age; processed-frame rates alone hide losses. Require no observed confident
wrong-identity bindings in the test set, while explicitly reporting exposure and
uncertainty: zero observed errors is not a zero failure probability. Do not turn
off identity checks to meet availability. Display coasting/lost distinctly; never
label a prediction as a fresh observation. The existing200ms control scorer stays
as a diagnostic, not an invented recording-only flight gate.

## Next work, in order

1. Complete11-sequence baseline finished:7046 source frames,1765 processed,1721
   post-selection evaluated updates; only5/11 acquired,215 correct valid,59 valid
   IoU<.5. All11 replay restorations passed before recording experiments. Preserve
   this baseline rather than only240-frame prefixes;
   preserve acquisition failures and wrong/low-overlap output. Fixedstride4 is a
   repeatable diagnostic, not a live-frame-rate claim.
2. Use the retained245/115 counterexamples to inspect detection crop quality,
   time-consistent identity evidence and fullview/ROI feedback. Do not ship the
   broad current-detection veto or shrink its margin to fit these clips.
3. Establish an independent dataset and explicit splits before further tuning.
   Verify exact dataset terms first; own-camera recordings remain essential.
4. Prove short standalone paired recording, then choose storage/encoder and
   qualify long-duration video with frame-linked metadata. Reuse existing camera
   and capture interfaces. Do not add another tracker or silently replace the ISP.
5. Re-run measured latest-frame scheduling and controlled live camera comparisons,
   with frozen baseline/rollback, then sustained mounted bench tests.

## Data audit and download decision

Local audit: `bench/results/2026-09-27-track-record-readiness/data-audit.json`.
There are6471 VisDrone DET training images,548 DET validation images,11 SOT
validation clips /7046 prepared frames, and7 MOT validation sequences. The mixed
detector training directory has11423 images:6471 VisDrone plus4952 COCO val2017
images. Thus those COCO validation images are training data for this experiment,
not an independent evaluation set. Training args point to this directory; the audit
does not reconstruct every checkpoint-to-HEF provenance link.

The ReID index declares238 training identities /5482 crops from6 sequence groups
and76 validation identities /1795 crops from group086. SOT086 shares that filename
group with the ReID validation data. The training script scores this split during
training, so “holdout” in its directory name means development validation, not an
untouched final test. No matching SOT group was found in declared detector/ReID
training filenames, but that is NOT proof of scene independence: authoritative
flight mapping and near-duplicate checks remain open. All11 SOT cases already
informed development and remain excluded from final holdout claims.

Additional independent data is needed for confidence, not simply more images for
training. Recommended acquisition order, pending exact terms/access:

| Data | Gap it addresses | Decision |
| --- | --- | --- |
| UAV123 + UAV20L | Independent aerial single-target trajectories and long sequences | First candidate; official full archive approximately13.7GB; keep full-rate version, split related sequences together |
| UAVDT | Small vehicles, camera motion and crowded multi-object scenes with identities | Next for vehicle target evaluation; audit task/split/flight overlap before use |
| Additional VisDrone SOT | More within-domain development failures | Lower priority than a different source; not automatically independent of existing DET/MOT training |
| Own IMX678 recordings | Actual optics, exposure/ISP, vibration, motion and mounting | Essential regardless of public datasets; consent and known test targets |

Official sources checked2026-09-27:

- [KAUST UAV123/UAV20L](https://ivul.kaust.edu.sa/benchmark-and-simulator-uav-tracking-dataset):
  aerial SOT,123 sequences, full and downsampled releases. UAV20L is a subset;
  do not count it as a separate independent dataset. Full archive size is the
  publisher's download figure, not measured local extraction space.
- [UAVDT authors](https://sites.google.com/view/daweidu/projects/uavdt):
  detection/SOT/MOT and scene attributes. Official access links exist; exact
  archive contents and license permission were not established by this audit.
- [VisDrone repository](https://github.com/VisDrone/VisDrone-Dataset):
  provides task-specific splits, including labelled SOT test-dev (11.27GB).
- [VisDrone official data policy](https://aiskyeye.com/data-protection/):
  page explicitly describes2021 academic/non-commercial CC BY-NC-SA3.0 terms.
  Verify applicability/permission for the exact2019 archives and intended company
  use; do NOT treat a toolkit's permissive code license as data clearance.

UAV123/UAVDT pages inspected do not establish a clear commercial permission grant.
**No new dataset downloaded and no training started.** Access via an official link
does not settle usage rights; do not use mirror license tags as substitutes.
Local PC free space measured about87GiB; board eMMC about3.3GiB. Keep public data
and preparations on the PC, not eMMC; account for archive plus extraction plus
NV12 expansion before downloading. No files deleted to create space.

## Bounded local capture implementation

`bench/fresh_stream_capture.py --local` reuses the exact same validated protocol
and source/output pairing as SSH capture, via127.0.0.1 only. It launches no SSH or
FC process. Corrected local mode reserves512MiB of disk and160MiB of NON-CMA RAM,
preflighting worst-case frame+metadata storage and a conservative memory allowance.
Per-frame memory and
storage checks abort before consuming their reserves. Short capture first spools
to bounded RAM; after the stream ends, the existing validator saves only verified
samples to eMMC. Partial prefixes are not complete recordings. Existing protocol
bounds (maximum60s request deadline,1200 requested frames for SSH) remain; local
default is16 and both local capture and the eMMC smoke harness cap requests at24.
Even these small captures may be refused by non-CMA RAM admission. No overwrite,
automatic deletion or boot autostart. Corrected local mode is **not board-validated**.

This follows actual eMMC failures: direct writes stopped at64/120 samples; a
two-frame asynchronous buffer stopped at43/120. The latter recorded a1540ms pixel
write against16.4ms median, and the native sender reported its100ms transport
timeout. The small-buffer experiment was removed, not left as another switch.
No timeout or native tracker/ISP setting was relaxed. The first RAM-first attempt
incorrectly used MemAvailable without subtracting CmaFree and admitted120 samples.
During it, SSH and the camera API stopped responding, while ping/serial kernel
logs still worked (ISP event timeouts). Insufficient ordinary-memory budgeting is
a concrete software defect and a likely contributor; final process/memory state
could not be read, so exact causality/completion remains unconfirmed. No reboot,
kernel setting change or deletion was performed. This failure is NOT a pass.

Correction now mirrors `hosts/hailo15l/diagnostic_budget.hpp`: subtract CmaFree,
fail closed on missing/malformed accounting, keep160MiB ordinary-memory reserve,
and cap the whole local raw capture at24 samples. Tests include the native helper's
pressure/missing/reversed fixtures. Do not run the earlier staged scripts in the
three retained local-record directories. Recover and inspect the board first,
then stage the corrected script only for a separately monitored short trial.

This is raw diagnostic NV12, not compressed flight video. It records processed
samples, not every sensor exposure. A power/process failure before saving can lose
the entire RAM capture. It is not power-loss durable or sustained-load/thermal-
qualified. Do not claim this completes the
standalone flight recorder. The capture server must already be enabled;2026-09-27
SSH inspection found capture_stream_port=8983,capture_source=true in the protected
live config. The smoke harness needs **no profile change or camera restart** after
replay restoration. Run qualification afterward; integrity passing is not tracking accuracy.

`bench/run_local_capture_trial.py --frames 16 --output NEW_PC_EVIDENCE_DIR`
performs the bounded smoke test. It refuses concurrent replay/MAVROS, checks the
live profile and storage, creates one owned eMMC directory, verifies staged script
hashes, starts the receiver with nohup, and returns from the launch SSH before
polling. No image payload crosses SSH. It retains raw data and failed prefixes,
qualifies successful recordings on-board, and checks unchanged live binary/config.
Polling retries transient SSH failures only within its observation deadline.
The launcher is not flight telemetry or a replacement camera lifecycle manager.

Example for a later controlled session ON THE BOARD, after staging the scripts and
enabling the paired source server, with a new validated destination:

```
python3 fresh_stream_capture.py --local --frames 16 --deadline-ms 60000 --output /VALIDATED_STORAGE/new-session
python3 qualify_capture.py /VALIDATED_STORAGE/new-session
```

Destination and mount are placeholders, not paths to execute without checking.
For longer sorties prefer dedicated removable storage and the existing platform
hardware encoder, subject to measured load/timestamp parity; no encoder change
or package installation is made by this turn.

Structural review: one inventory tool and tests, local transport/storage guards
in the existing recorder, existing replay campaign, no new runtime tracker/model/
dependency. Preserve rejected experiments as regressions; consolidate options
before product packaging. No mount/readiness/project gate marked complete.
