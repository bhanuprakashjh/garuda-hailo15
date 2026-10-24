# Movement fixes: measured boxes and the ROS/MAVROS path

Implemented and deployed on the desk Hailo-15L. Local console:
http://127.0.0.1:8100/ . Final handoff is physical IMX678 input, simulator
disarmed, Follow OFF. No physical flight controller is connected or authorized.

## Findings and changes

1. **Measured geometry was being replaced by filtered geometry.** Matched tracks
   carried a Kalman-corrected position and size while marked `observed=true`.
   The filter's size velocity can overshoot after a size/direction change.
   Observed tracks now expose the current, normalized detector box; the Kalman
   state is retained for next-frame association. `filtered_box` and `box_source`
   expose the distinction. Predictions remain ineligible for control. Existing
   detector clipping, confidence, uncertainty and person-size limits remain.
   A measured box is not ground truth, and may jitter or represent a partial body.
2. **Independent timer phase delayed accepted commands.** Board ROS now evaluates
   and publishes immediately after accepting a setpoint request, then resets its
   normal 50ms watchdog timer. It does not renew the original lease. Expiry and
   total-runner-loss behavior remain HOLD and PX4 offboard-loss failsafe.
   TCP_NODELAY is enabled on the PC tunnel socket. Repeated full PX4-log reads
   stop once takeoff priming completes.
3. **A cross-channel ordering race was measured.** In the first updated rendered
   trial, seven rejected MAVLink motion packets preceded their matching JSON
   publication record by 0.614–3.948ms. The final relay can retain at most 16
   unmatched packets while metadata is missing, for up to 10ms from original
   receipt. It never forwards without one-shot publication binding; original
   deadlines, latest PC intent, numeric bounds and identity checks still apply.
   HOLD or a source/identity change clears pending packets. Missing, expired,
   duplicate or contradictory records cannot borrow a new lease.
4. **Final dispatch needed another freshness check.** The old interactive log
   contains one allowed motion event stamped after its deadline; logging and
   process-ownership checks preceded the actual write. Those potentially blocking
   operations no longer sit between the final deadline check and the PX4 write.
   Wire evidence is logged afterward with the pre-write check timestamp. This is
   a software dispatch bound, not a measurement of physical actuator latency.
5. **Identity ambiguity stays fail-closed.** No similarity threshold or candidate
   exclusion was relaxed. Candidate count and best/runner-up identity distances
   are now exposed. These are match distances, not calibrated probabilities.
   Diagnosing duplicate detections versus genuinely similar people still needs
   labelled/source-paired examples; this change does not claim that problem solved.
6. **Console truthfulness.** Identity retention, operator Follow, freshness of the
   PC motion request, and last wire disposition are separate. An expired PC
   request no longer remains labelled FOLLOW until the next control tick.
   Rejection reasons and measured/filtered box provenance are visible. A bare
   physical-mode `/frame.jpg` no longer silently falls back to the Gazebo camera.
   Physical JPEG/overlay pairing is still approximate. The Sites workflow reused
   the existing local dashboard; no hosted website, account or dependency was added.

## Actual validation

Evidence: `bench/results/2026-09-13-movement-fix/`. Both rendered trials use real
Hailo inference, board ROS 2/MAVROS and the owned PC PX4/Gazebo instance.

| Check | First updated trial | Final trial with metadata wait |
|---|---:|---:|
| Unique inference frames | 596 | 588 |
| Motion packets forwarded / rejected | 341 / 8 | 334 / 4 |
| Expired motion at final dispatch check | 0 | 0 |
| Follow displacement | 8.291314m | 8.066426m |
| Perception-pause evaluated ticks held | 31/31 | 31/31 |
| Recovered after pause; landed/disarmed | Yes | Yes |

Final first-request-to-publication-report latency was median **6.233834ms**,
p95 **17.616438ms**, 988 requests. This measures the PC request through the board
evaluation to its returned report, **not** camera exposure to executed command.
The raw `request_to_publish_ms` field is sampled at tick entry; the report and GUI
correctly describe it as request-to-evaluation and exclude subsequent ROS/wire work.
Periodic watchdog republications are reported separately from first replies.

Final motion rejections: two `pc_hold`, two `unknown_or_consumed_publication`.
They were not hidden or turned into accepted commands. Final measured-versus-filtered
maximum-coordinate difference was median3.652066px, p9516.073440px across404
observed boxes. No selected follow box was outside the image in these rendered
trials, but that is not proof of an improvement on the user's different movements.

The baseline report streams the original long interactive log rather than loading
its repeated snapshots into RAM. Its 3,717 follow ticks include long lost/absent
periods: 3,208 HOLD ticks, 54 outside-image target boxes and 172/139 forwarded/rejected
motion packets. First-report latency median37.311093ms, p9547.647676ms. These are
**unpaired runs with different scenes/workloads**, not a causal before/after accuracy
or speed benchmark. Original full baseline remains outside git at
`/media/bhanu1234/Development/hailo-export/grand-demo-20260913-interactive`.

Local validation: 7/7 native CTest targets, 46 tracking Python tests (including
recorded H15L person/process-stall replay), 24 follow tests, 7 bridge tests,
45 simulator tests, 8 native-camera tests; exact VPSP SDK ARM build completed.
New tests cover measured-versus-filtered geometry, stale GUI requests, correct
physical preview, gate reasons, delayed final dispatch, late/missing metadata,
expired leases, HOLD, duplicate packets and bounded pending-queue overflow.
JavaScript syntax, Python compilation and whitespace checked. No browser visual
QA or new physical-person movement trial is claimed.

## Deployment and rollback

Model HEFs, `current.json`, ISP settings, OS, drivers and ROS rootfs packages are
unchanged. Native binary SHA256:
`3851ef019716dfa7f5ed36f219ea557cfb81cbd0820dd9e021f1431c5514a2d3`.
The validated causal executable is staged under both
`/opt/garuda-sim/garuda-causal-movement-fix` and the grand-demo launcher's normal
`/opt/garuda-sim/garuda-causal-stream-diagnostics` path, SHA256
`ae28949f61da8498d35738a2ef3002f1b71d122709a76de84f641808f91bba9d`.
Board ROS scripts were staged with `hosts/hailo15l/ros2/deploy_nodes.sh` while
the simulator was stopped. Exact versions/hashes are in archived run snapshots.

Recoverable prior native binary, profile and camera log:
`/opt/garuda-fresh/backups/movement-fix-20260913/`.
Prior causal binary:
`/opt/garuda-sim/garuda-causal-stream-diagnostics.before-movement-fix-20260913`.
Rollback only with the simulator landed/stopped: stop the desk pipeline, copy the
backup binary into its original location, then `fresh_tracking_ctl.sh start-current`.
Restore ROS source from parent commit f8ea55e into a separate checkout and deploy
only with the owned ROS simulator stopped. Do not reset this worktree or boot image.

## Remaining acceptance work

Repeat the user's physical-camera movement with a selected person: slow lateral
motion, quick reversal, approaching/crouching, partial exit and return. Compare
measured/filtered boxes, source capture age, identity candidate gap, PC request,
actual forwarded yaw and PX4 heading. A full-view unlocked scan still can exceed
the200ms control budget; camera acquisition/ISP/inference latency was not removed
by this transport patch. At handoff the physical feed and board ROS input were
advancing, but no person was detected/selected, so movement validation remains open.

Red-team: a simple rendered person and many forwarded packets can conceal real
camera recall, crowd swaps, jitter and stale exposure timestamps. Fresh measured
geometry can still be wrong; uncertain identity must keep HOLD. Original aerial
dataset failures are not retrospectively passed. No outdoor tracking, safe metric
distance, real-flight or crowd-identity gate is certified by these desk tests.

Structural review: reuse the existing native tracker, ROS authority, simulator
runner and local UI. Added one streaming scalar report; no second detector,
controller, service, dependencies or training fork. Prune redundant repeated
snapshot logging in a separate bounded logging change, not by deleting evidence.
