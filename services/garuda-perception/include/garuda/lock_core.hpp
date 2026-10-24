#pragma once
#include <optional>
#include <string>
#include <vector>

// LockCore: a dedicated locked-target tracker for the perception node's "lock" feature (replaces
// treating today's multi-object-tracker id as the lock — that transfers on class flicker and its
// windows were frame counts, which drift with frame rate). Time is wall-clock milliseconds from the
// frame's ISP clock, not frame counts, so occlusion/reacquire/expire windows behave identically
// regardless of the pipeline's frame rate. The design this class implements is
// docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md §8.2 ("Locked-target
// tracking"), planned in docs/superpowers/plans/2026-09-04-hailo15l-lock-core.md (Task 1); the
// published semantics are documented in hosts/hailo15l/README.md §10. Pure C++, no Hailo/OpenCV
// dependency.
namespace garuda {
namespace lock {

enum class State { NONE, CONFIRMED, OCCLUDED, REACQUIRING, LOST };
const char* state_name(State s);   // "none","confirmed","occluded","reacquiring","lost"

// A single frame's detection candidate. Frame pixels, top-left + size. id == -1 means "no track id"
// (e.g. a raw detector output not yet associated to any multi-object tracker's identity).
struct Obs {
    int id = -1;
    std::string cls;
    double conf = 0.0;
    double x = 0.0, y = 0.0, w = 0.0, h = 0.0;
    // On-board fix round 10 (Ruling 32b): the timestamp (this same ts_ms clock) of the frame in
    // which this tracker id was FIRST SEEN. -1 means the producing engine cannot report it, and the
    // core treats that as "pre-existing" -- the conservative reading, since the whole point of the
    // field is to prove an id appeared only AFTER the target was lost. See the widened-stage rules
    // in Params below.
    double first_seen_ms = -1.0;
};

// Position (cx, cy) filters use a discrete white-noise-acceleration (WNA) process model: an unknown
// constant acceleration with std `q_acc_std` (px/s^2) held over each predict interval, giving
// per-axis Q = q_acc_std^2 * [[dt^4/4, dt^3/2], [dt^3/2, dt^2]] (see lock_core.cpp's cvPredict). The
// initial velocity at lock() is unknown, modelled as N(0, p0_vel_std^2) (px/s) rather than assumed
// zero-uncertainty, so a fast mover can be gated in on the very first post-lock frame.
//
// Fix round 2 (Ruling 2): that WNA variance grows ~t^4 while left uncorrected, so within about a
// second of coasting the RAW gate would already cover most of a real frame -- "search near the
// prediction first, widen with genuine uncertainty" stops meaning anything once the ordinary gate is
// that big. `gate_max_px` caps the per-axis gate radius used for gating (both the in/out-of-gate test
// and the score's motion term): the effective std used there is
// `min(sqrt(var), gate_max_px / gate_sigma)`, i.e. the effective variance is
// `min(var, (gate_max_px/gate_sigma)^2)`. This caps ONLY the gating computation -- the Kalman
// correction gain still uses the true, uncapped variance (so a genuinely-uncertain filter still snaps
// hard onto a new in-gate measurement), and `Output.uncertainty_px` still reports the true, uncapped
// std (an honest diagnostic, not clamped to the gate).
//
// Gate radius after the first prediction (from a fresh lock(), before any correction, well under the
// cap so it is unaffected by it) is `3*sqrt(r_pos + dt^2*p0_vel_std^2 + dt^4/4*q_acc_std^2)` -- at
// dt=40 ms with the defaults below: `3*sqrt(25 + 0.0016*160000 + 6.4e-7*360000)
// = 3*sqrt(25 + 256 + 0.23) ~= 3*sqrt(281.2) ~= 50 px` -- dominated by p0_vel_std, barely moved by
// lowering q_acc_std in this round. After ~2 s of coasting the raw variance is far past the cap, so
// the state term's contribution to the gate radius is exactly `gate_max_px` = 300 px.
//
// On-board fix round 3 (Ruling 19.1): the gate is now a proper Mahalanobis test against the
// INNOVATION covariance `S = min(P, cap) + R`, not against the state variance `P` alone, and `R` is
// box-scaled (see `r_pos_frac`). Two consequences worth stating because both were surprises in the
// run-5 analysis: (a) before this round the gate omitted `R` entirely, so a converged filter with
// `uncertainty_px` 3.2 had a gate radius of only `3*3.2 = 9.6` px -- tighter even than the
// `3*sqrt(P + r_pos) ~= 17.8` px the ruling's own arithmetic assumed; (b) `gate_max_px` now caps only
// the STATE term, so a large box's measurement noise legitimately widens the gate past 300 px (a
// 650 px box: `3*sqrt(10000 + 65^2) = 358` px). Under it all sits the floor `gate_min_px =
// gate_min_frac * max(w_ref, h_ref)`, applied to the radius after `R`: a converged lock on a 655 px
// person can never gate tighter than ~98 px, which is what run 5's 40-60 px per-frame box-centre
// jitter needed. `uncertainty_px` still reports the raw, uncapped `sqrt(P)` -- it is a diagnostic of
// the filter, not a readout of the gate, and after round 3 the two are deliberately different things.
//
// Fix round 4 (final-fix wave, I3/Ruling 11): association is TWO-STAGE, matching spec §8.2 ("search
// near the prediction first, expand with uncertainty, full-frame only after local search fails … if
// two candidates are ambiguous, report OCCLUDED/UNCERTAIN") rather than the single pooled scoring the
// plan's Task 1 text described. Stage 1 scores only the IN-GATE candidates (`min_score` + the
// ambiguity margin among themselves); stage 2 — the widened, full-frame search over out-of-gate,
// same-class, size-consistent candidates, scored against `min_score_widened` with the margin applied
// within that pool only — runs ONLY when stage 1 found nothing to consider at all: an empty in-gate
// pool, or an in-gate pool whose best candidate does not even clear `min_score`. An AMBIGUOUS in-gate
// pool (a winner-quality candidate that fails the margin test against another in-gate candidate) ends
// the frame with no association and does NOT fall through to stage 2 — ambiguity near the prediction
// is a reason to report OCCLUDED/REACQUIRING, never a reason to look further afield. The practical
// effect: a far same-class object can no longer veto a good local match (it used to, because both
// pools shared one margin test).
//
// Fix round 4 (I6/Ruling 14): out of gate the motion term is ~0, so with the shipped weights a
// same-class, size-matched candidate needs `w_conf*conf + w_size + w_class (+ w_id)` >=
// `min_score_widened`, i.e. conf >= 0.8 with a new tracker id or conf >= 0.4 if the underlying tracker
// preserved the id (derived from these constants, not a bench number). `min_score_widened` exists so
// that floor can be tuned independently of the local one; it defaults to `min_score`.
//
// Fix round 4 (I6/Ruling 14): while COASTING (no winning candidate this frame) the predicted centre is
// clamped into the frame — this is what `frame_w`/`frame_h` are for. Without it, `pos += vel*dt` runs
// away off-frame (at 300 px/s the centre is ~600 px past the edge after a 2 s walk-out), so a target
// re-entering at the edge it left by is outside the local gate and re-acquisition rests entirely on
// the underlying tracker having preserved its id or the detector returning conf >= 0.8. Velocity is
// left untouched: only the mean position is bounded, so a target that reappears mid-frame is still
// gated on its true predicted motion up to the frame boundary. NOTE (deviation from Ruling 14 as
// literally written, recorded in .superpowers/sdd/2026-09-04-hailo15l-lock-core/final-fix-report.md):
// the ruling specified a `[-gate_max_px, frame_w + gate_max_px]` box, but with the shipped constants
// that margin equals the whole capped gate radius, so a re-entry at the frame edge lands >= 350 px
// from the clamped centre (d^2 >= 12.25 > gate_sigma^2 = 9) and could never gate in — the clamp
// region is therefore the frame itself, which is what makes the local gate actually cover the exit
// edge (the review's own stated intent).
// On-board fix round 3 (Ruling 19, from run 5 — the first measured routine-1 run with the owner in
// view; bench/benchlog.md's "Run 5 (83b600c)" entry). That run had the engine holding a LIVE box for
// the locked id on 306 of the 1048 rows where the core reported no observation (29 %). All three
// mechanisms were the same mistake in different clothes: **the core's tolerances were absolute where
// the evidence is relative to the box.**
//
// M-A: a 650x650 person box jitters its CENTRE by 40-60 px frame to frame (arm movement changes the
//      box width 640 -> 774), while a converged filter's gate was ~10-18 px. -> `r_pos_frac` +
//      `gate_min_frac` below.
// M-B: a size reference frozen on a 169 px-wide partial box could not follow the same id growing
//      231 -> 594 px in 1.4 s as the owner walked toward the camera (a person triples in size in ~2 s
//      on a wide-angle lens); the absolute `q_size` granted ~43-79 px against a needed 60-425 px.
//      -> `r_size_frac` + `q_size_frac` below.
// M-C: a lone, same-class, size-consistent NEW id re-entering the room scored ~0.45 against a
//      `min_score_widened` of 0.5 and was refused for 9 s. -> `min_score_widened` default 0.40.
// Plus `same_id_gate_mult`: a candidate carrying the core's OWN last id is frame-to-frame continuity
// the multi-object tracker has already verified; a stale reference must not veto it.
// On-board fix round 4 (Ruling 20, from run 7 — routine 2, occlusion behind a chair). The 3-second
// hide recovered; the 6-second one did not, and the cause was the round-3 same-id relaxation feeding
// the size filter. The engine kept the locked id alive on the HEAD-ONLY box above the chair back
// (155x625 -> 276x159 -> 152x129), the relaxation let the core follow it, and the core LEARNED that
// as the target's size — so when the owner stood up again as a new id at 321x271/367x569 the size
// gate rejected every one of them against a 152x129 reference. Three changes:
//   (a) a candidate that passes only BECAUSE of the same-id relaxation corrects POSITION but NOT
//       size — the size filter is left to keep growing its variance (see update(); no new param).
//   (b) the REACQUIRING band scores in-gate candidates against `min_score_widened`, not `min_score`.
//   (c) `reacquire_ms` 3000 -> 9500, so the widened search stays open until expiry.
// Together they say: a partially-occluded or edge-clipped target may still be FOLLOWED on the
// evidence of tracker id continuity, but it may not TEACH the core what it looks like, and the
// longer it has been missing the more willing the core is to take a mediocre local match.
//
// On-board fix round 5 (Ruling 22, from run 10e — routine 5, the phone routine, the first
// all-classes capture). The phone left frame at capture rel. 146 s; the core, REACQUIRING with the
// round-4 widened floor applying in-gate, then walked across DIFFERENT-CLASS in-gate candidates
// (`knife`, `remote`, `hair drier`) and settled at rel. 165.7 s on a static `chair`/`suitcase` box
// (229x270 at (343,447), conf 0.84-0.92), holding it CONFIRMED for the remaining ~12 minutes of the
// capture while still publishing `lock.class = "cell phone"`. Three mechanisms, each addressed:
//   (a) class was a soft 0.15 score term only, so a high-confidence box of ANY class could win on
//       conf + motion alone. -> the CLASS GATE in update(): a candidate whose class differs from the
//       locked class is eligible only if it carries the core's own `last_id`, i.e. the multi-object
//       tracker's own frame-to-frame continuity says it is the same object the detector re-labelled.
//       A different class AND a different id is never associated, in any state, in either stage.
//       The accepted cost, stated plainly: an object the detector re-labels under a NEW id (the
//       phone seen as `remote` with a fresh id) is NOT taken until a same-class detection appears
//       again. Distinguishing those two cases needs appearance (F3), which is not built.
//   (b) the relative size model (`q_size_frac` 0.5/s) legitimately tolerates a 2.3x wider box after
//       a few seconds unobserved, which is right for a person walking toward the camera and wrong
//       for "anything roughly over there". -> `size_ratio_max` below, a HARD ratio cap applied to
//       different-id candidates only.
//   (c) `Output.cls` was always the locked class, so the published `lock.class` said `cell phone`
//       for twelve minutes of suitcase. -> `Output.cls` now follows the class of the last associated
//       observation. The LOCKED class (what (a) gates on) is still fixed at lock() and never
//       changes; the published one is a readout of what the core actually last saw.
struct Params {
    // reacquire_ms (round 4, Ruling 20c): 9500 so that occlusion_ms + reacquire_ms == expire_ms —
    // the widened, full-frame search now stays open for the whole REACQUIRING band instead of
    // closing 6.5 s before the lock expires. Run 7's owner re-emerged 8.5 s into a hide, into a
    // window where only in-gate candidates were still considered and the in-gate floor was the
    // strict one; nothing could be taken and the lock expired with the target plainly in frame. The
    // two remain independent parameters (a config may still close the window early) and the
    // ambiguity margin is unchanged, so two plausible candidates still block. For a multi-person
    // scene the real safety is appearance (F3, not built): until then a long, wide-open widened
    // window is a deliberate trade — recover the target, and rely on the margin to refuse when the
    // scene is ambiguous.
    double occlusion_ms = 500, reacquire_ms = 9500, expire_ms = 10000, control_valid_ms = 150;
    double gate_sigma = 3.0, min_score = 0.5, ambiguity_ratio = 1.3, size_tol = 0.5, gate_max_px = 300.0;
    // Score floor for the widened (out-of-gate) stage, and — since on-board fix round 4 (Ruling 20b)
    // — for EVERY candidate while the lock is REACQUIRING, in-gate ones included. CONFIRMED and
    // OCCLUDED keep `min_score`. The reasoning is that the two bands are asking different questions:
    // while the target was seen moments ago, a mediocre local match is more likely to be the wrong
    // object than the right one; once it has been missing long enough to be REACQUIRING, a mediocre
    // match near the prediction is the best evidence available and refusing it just runs the clock
    // down to LOST. Run 7's 6-second hide is the case: the owner re-emerged 110-150 px from the
    // frozen box at conf 0.27-0.35, IN gate, scoring ~0.45 — over `min_score_widened` but under
    // `min_score`, and the widened floor did not apply to an in-gate candidate.
    // On-board fix round 3 (Ruling 19.4) sets
    // this to an explicit 0.40 rather than the previous "unset == the same as min_score": run 5's
    // M-C candidate (lone, same-class, size-matched, new id, conf 0.82) scored ~0.45 and was refused
    // for 9 s under a 0.5 floor. The `std::optional` is kept so a config may still reset it to
    // nullopt to get the old "track min_score" behaviour; the ambiguity margin is unchanged, so two
    // plausible candidates still block.
    std::optional<double> min_score_widened = 0.40;
    // On-board fix round 10 (Ruling 32) -- CONDITIONAL OUT-OF-GATE ACCEPTANCE OF A DIFFERENT ID.
    //
    // History, because the default moved twice. Round 9's Ruling 28 refused every different-id
    // candidate in the widened (out-of-gate, full-frame) stage, on the grounds that out of gate the
    // motion term is ~0 and the remaining score is confidence + size + class -- none of which is
    // IDENTITY evidence -- so a lone same-class object across the frame is "a person", not "THE
    // person" (the outside review's probe: a new-id person 900 px away at conf 0.41 took the lock
    // outright). That was correct about the danger and too blunt about the cure: it cost the
    // committed occlusion capture its 6-second-hide recovery (139 LOST rows vs 0) and dropped the
    // phone replay from 0.8150 to 0.1934 confirmed-on-phone-live rows (bench/benchlog.md, "Round 9").
    //
    // Round 10 keeps the protection and recovers the behaviour by asking for evidence that is
    // actually available without appearance (F3). A DIFFERENT-id candidate may win the widened stage
    // only when ALL of these hold:
    //   (a) it is the same class as the lock (unchanged from every earlier round);
    //   (b) its tracker id was BORN AFTER the last confirmed observation -- `Obs::first_seen_ms >
    //       <last confirmed ts>`, with -1 ("unknown") treated as pre-existing and therefore refused.
    //       THIS IS THE LOAD-BEARING ONE. An id that was already alive while the target was still
    //       confirmed is, by construction, a DIFFERENT physical object: the multi-object tracker was
    //       holding both at once. Only an id that appeared after the loss can be the target coming
    //       back under a new number. That single test removes the classic swap -- the other person
    //       who was in the room the whole time -- with no appearance model at all.
    //   (c) it is the ONLY eligible out-of-gate candidate this frame. The ambiguity margin still
    //       governs the in-gate pool; out of gate the bar is stricter than a margin, because the
    //       dangerous case is one wrong candidate rather than two similar ones -- if the widened
    //       pool holds more than one candidate, every different-id candidate in it is dropped
    //       (same-id continuity is unaffected; it is not identity guesswork).
    //   (d) `conf >= widened_new_id_min_conf` -- a re-acquisition across the frame on a weak
    //       detection is the shape most likely to be something else.
    //   (e) `obs_age_ms <= widened_new_id_max_age_ms` -- the longer the target has been gone, the
    //       less a position prediction constrains anything, and the more likely some unrelated
    //       same-class object has entered. Note this closes the different-id half of the widened
    //       window EARLIER than `reacquire_ms` does: beyond it only tracker-id continuity recovers a
    //       lock, and past `expire_ms` nothing does.
    //       **7000 ms since round 10b (Ruling 33), up from the 5000 the ruling first specified.**
    //       The committed phone capture needs a lone born-after-loss re-acquisition at 6392 ms, and
    //       at 5000 the replay lost the remaining ~54 s of that capture outright (0.1945 against
    //       0.8150). The replay is harsher than the board -- it drives LockCore alone, so LOST is
    //       terminal there, while the node's resolver re-locks with a NEW EPOCH -- but the number
    //       the capture actually asks for is > 6.4 s, and `expire_ms` (10000) is unchanged, so the
    //       different-id window still closes 3 s before the lock itself dies.
    // A SAME-id out-of-gate candidate is subject to none of (b)-(e): it carries the multi-object
    // tracker's own assertion that it followed the same object across the frame, which is identity
    // evidence in a way that confidence and size are not.
    //
    // `widened_new_id` remains the master switch and now defaults to TRUE (i.e. the conditions
    // above are in force). Setting it FALSE restores round 9's blanket refusal -- kept as the
    // "strict" reference the replay tests still pin, not as a recommendation.
    //
    // The accepted residual, stated rather than buried: a same-class object that genuinely appears
    // for the first time after the target is lost, alone in frame, at good confidence, within
    // `widened_new_id_max_age_ms`, IS taken. Distinguishing it from the real target needs appearance
    // (F3, not built). What (b) buys is that the object which was there all along can never be it.
    bool widened_new_id = true;
    double widened_new_id_min_conf = 0.5;         // (d)
    double widened_new_id_max_age_ms = 7000.0;    // (e)
    // Noise units, stated explicitly (on-board fix round 1, Ruling 16.2 asked for this check):
    //   q_acc_std  px/s^2   -- an acceleration STD (squared inside cvPredict's Q)
    //   p0_vel_std px/s     -- a velocity STD (squared at lock())
    //   r_pos      px^2     -- a position measurement VARIANCE ((5 px)^2). Since round 3 this is only
    //               the FLOOR of that variance -- see r_pos_frac.
    //   q_size     px^2 per SECOND -- the size random walk's variance rate (rwPredict: var += q*dt,
    //               dt in seconds). Since round 3 this is only the FLOOR of that rate -- see
    //               q_size_frac -- kept parsed and honoured for config compatibility.
    //   r_size     px^2     -- a size measurement VARIANCE ((10 px)^2), and the variance a fresh
    //               lock() seeds the size filters with. Since round 3 it is only the FLOOR of the
    //               measurement variance -- see r_size_frac -- but it is still the literal lock()
    //               seed (a freshly clicked box has no size history to be uncertain about yet).
    double q_acc_std = 600.0, p0_vel_std = 400.0, r_pos = 25.0, q_size = 50.0, r_size = 100.0;
    // Round 3 (Ruling 19.1/19.2): the four "…_frac" knobs make measurement/process noise scale with
    // the box, with the absolute values above as floors. All are per-axis: x/w use the width
    // reference, y/h the height reference.
    //   r_pos_frac    position measurement STD as a fraction of the box dimension. Per-axis std is
    //                 max(sqrt(r_pos), r_pos_frac * ref) -- note the floor is in STD units, so
    //                 r_pos's px^2 is square-rooted to compare. 0.10 of a 650 px box is 65 px,
    //                 against sqrt(25) = 5 px before.
    //   gate_min_frac gate RADIUS floor as a fraction of max(w_ref, h_ref), applied after the
    //                 measurement noise: the gate never shrinks below gate_min_frac * max(w,h) px no
    //                 matter how converged the filter is. 0.15 of a 655 px box is 98 px.
    //   r_size_frac   size measurement STD as a fraction of the size reference; per-dimension
    //                 variance is max(r_size, (r_size_frac * ref)^2).
    //   q_size_frac   size process STD per sqrt(second), as a fraction of the reference: the size
    //                 random walk grows by (q_size_frac * ref)^2 px^2 per second, floored at q_size.
    //                 0.5 means "a person's box may plausibly change by ~half its own size in a
    //                 second" -- run 5's owner tripled hers in ~2 s walking toward the camera.
    //   same_id_gate_mult  multiplier applied to BOTH the position gate radius and the size
    //                 tolerance (and hence to the motion/size score terms, which are computed against
    //                 the relaxed scales) for a candidate whose id equals the core's current
    //                 `last_id`. Every candidate the node passes in is LIVE (node_main.cpp builds
    //                 `live_obs` from records with time_since_update == 0), so an id match here is
    //                 the multi-object tracker asserting frame-to-frame continuity it verified
    //                 itself -- evidence the core must not override with a stale reference. It is a
    //                 relaxation, never a bypass: class, score floor and the ambiguity margin all
    //                 still apply.
    double r_pos_frac = 0.10, gate_min_frac = 0.15, r_size_frac = 0.15, q_size_frac = 0.5;
    double same_id_gate_mult = 2.0;
    // On-board fix round 5 (Ruling 22.2): a HARD cap on how different a DIFFERENT-ID candidate's box
    // may be from the size reference, applied on top of (never instead of) the variance-aware
    // tolerance above. A candidate whose id is not the core's own `last_id` is eligible only if both
    // `w / ref_w` and `h / ref_h` lie in [1/size_ratio_max, size_ratio_max]. Same-id candidates are
    // exempt -- run 5's walk-toward-the-camera growth (169 -> 594 px in 1.4 s) was same-id, and
    // Ruling 19.2 exists to let the core follow exactly that.
    // Why a hard cap at all: the variance-aware tolerance grows with obs_age (by design -- a target
    // unseen for seconds may legitimately have changed size), and in run 10e that growth is what let
    // a 229x270 static box look "size-consistent" with a 135x285 phone reference after a few seconds
    // of REACQUIRING. 1.6 is the ratio a fast approach/retreat needs within the ~10 s a lock lives
    // (derived from the geometry, not measured): it admits a box that has grown or shrunk by 60 %,
    // and refuses the 2.3x that run 10e's walk exploited.
    // A value <= 0 disables the cap entirely (back to round-4 behaviour); a config may do that
    // deliberately, and nothing else in the core reads this parameter.
    double size_ratio_max = 1.6;
    double w_conf = 0.25, w_motion = 0.35, w_size = 0.15, w_class = 0.15, w_id = 0.10;
    int frame_w = 1280, frame_h = 720;
    // Consumed by garuda::track::LockResolver, NOT by LockCore -- they live here because they are
    // parsed from the same `lock` config block and this struct is that block's one set of defaults
    // (on-board fix round 1, Ruling 16.1). The node passes them to the resolver's constructor: the
    // resolver may auto-acquire a target on its own only if `conf >= auto_min_conf` and the box is
    // clear of the left/right frame edges by `auto_edge_margin_frac * frame_w`. An explicit click is
    // never gated. See lock.hpp and bench/benchlog.md's "Run 1 ... edge-entry failure".
    // auto_min_streak (on-board fix round 2, Ruling 18): LIVE frames a candidate must pass that gate
    // on before the resolver may take it. A single frame of conf >= auto_min_conf is not evidence:
    // run 2 lost a whole capture to one such flicker on a static room object ("Run 2 ... junk-track
    // lock"). auto_streak_window (on-board fix round 7, Ruling 24) is the span they are counted over
    // -- 5 within the last 15 frames (~0.5 s at 30 fps), not 5 consecutive, because the phone in the
    // round-7 capture was a live box in only 30.2 % of frames and five consecutive gate-passing
    // frames essentially never happened, so auto-acquire never re-locked it ("Round 7 -- clutter and
    // re-acquire"). Either field at 0 disables the streak test. The same test also gates the
    // resolver's re-acquire jump.
    double auto_min_conf = 0.5, auto_edge_margin_frac = 0.02;
    int auto_min_streak = 5, auto_streak_window = 15;
};

struct Box { double x, y, w, h; };

struct Output {
    State state = State::NONE;
    bool identity_locked = false, observation_valid = false;
    double quality = 0.0, obs_age_ms = 0.0, uncertainty_px = 0.0;
    std::optional<Box> box;
    // The class of the LAST ASSOCIATED OBSERVATION, not the locked class (on-board fix round 5,
    // Ruling 22.3). Seeded at lock() with the clicked box's class and updated on every winning
    // association, so a same-id class flicker is visible to whoever reads the snapshot instead of
    // being hidden behind a class field that could never change. The class the core GATES on is
    // still the one fixed at lock() and is deliberately not published -- see the class gate in
    // update(). Run 10e is why: `lock.class` read `cell phone` for twelve minutes of suitcase.
    std::string cls;
    int last_id = -1;
    // The size filter's current reference — what the core believes the target's box size is (on-board
    // fix round 4, Ruling 20a). Not published in the snapshot; it exists because the round-4 failure
    // is invisible from `box`: while CONFIRMED the published box is built FROM this reference, so a
    // contaminated reference and a healthy one look identical until the moment nothing can associate
    // any more. 0 until the first successful lock().
    double ref_w = 0.0, ref_h = 0.0;
    // Lock generation: 0 before the first successful lock(), +1 on every successful lock() thereafter,
    // and NEVER reset (an unlock() keeps publishing the epoch of the lock it ended). Fix round 4
    // (I2/Ruling 10): `last_id` deliberately follows whichever candidate wins the gate (see update()),
    // so a tracker renumbering the SAME object changes `last_id` while the lock is held — indeed the
    // thing LockCore exists to ride through. `epoch` is what distinguishes that from the failure mode:
    // an epoch change means a genuinely NEW lock was taken (click, target change, post-LOST re-lock),
    // an id change WITHIN one epoch is tracker id churn the core rode through. The bench harness
    // (bench/evidence/2026-09-04-lock-core/lock_metrics.py) splits its identity column on exactly this.
    int epoch = 0;
};

class LockCore {
public:
    explicit LockCore(const Params& p = Params{});

    // Starts a lock on `target` at time `ts_ms`: the position/size filters are initialised at the
    // target's box with zero MEAN velocity but a large velocity uncertainty (p0_vel_std), state ->
    // CONFIRMED, `epoch` +1. `target.id`/`target.cls` become the locked identity/class. The LOCKED
    // class never changes after this — it is what the class gate in update() tests against — while
    // the PUBLISHED `Output.cls` follows the last associated observation (round 5, Ruling 22.3), so
    // the two differ whenever the core is riding a same-id class flicker.
    // A DEGENERATE box (w <= 1 or h <= 1) is REJECTED (fix round 4, M3): the size checks divide by the
    // size filter's own w/h, so such a lock could never associate anything again. The call is ignored
    // (state and epoch unchanged, warned once on stderr).
    void lock(const Obs& target, double ts_ms);

    // Ends the lock: state -> NONE. Safe to call when not locked.
    void unlock();

    // One frame. `dets` may be empty. Predicts the filters from the last lock()/update() timestamp,
    // gates + scores `dets`, transitions state, and returns (and caches, see last()) this frame's
    // Output. A no-op (returns a blank NONE Output) when not currently locked.
    //
    // On-board fix round 9 (Ruling 29) -- STALL EXPIRY. Before anything else, if the core still
    // holds an identity and `ts_ms - <last confirmed ts> > expire_ms`, the lock transitions to LOST
    // and this frame associates NOTHING. Until this round every window was advanced only by the
    // calls that actually arrived, so a pipeline that STOPPED calling update() -- a stalled camera,
    // a blocked sink, a thread wedged on a slow write -- could resume 11 s later and have the core
    // treat the first frame back as though no time had passed (outside review's probe, 2026-09-05:
    // lock at t=0, one update() at t=11000 with the target's own box, and the core read CONFIRMED
    // on a lock that had been dead for a second). Expiry is a property of elapsed wall-clock time,
    // not of how many frames happened to be delivered. The epoch and the log semantics are those of
    // an ordinary ticked expiry: the epoch is unchanged (an expiry is not a new lock generation) and
    // the state change is what the node's transition log prints. LOST stays terminal, so recovering
    // needs an explicit lock() -- see the LOST note in lock_core.cpp.
    Output update(double ts_ms, const std::vector<Obs>& dets);

    const Output& last() const { return m_last; }

private:
    Params m_params;
    Output m_last;

    bool m_locked = false;
    State m_state = State::NONE;
    int m_epoch = 0;                       // see Output::epoch -- never reset, only incremented
    double m_last_ts_ms = 0.0;             // timestamp of the last lock()/update() call (dt base)
    double m_last_confirmed_ts_ms = 0.0;   // timestamp of the last winning correction (obs_age base)
    int m_last_id = -1;
    std::string m_locked_cls;   // fixed at lock(); what the class GATE compares against
    std::string m_last_obs_cls; // class of the last associated observation; what Output.cls publishes
    Box m_last_confirmed_box{0.0, 0.0, 0.0, 0.0};   // frozen box published while OCCLUDED/REACQUIRING

    // Scalar Kalman filter state. cx/cy: constant-velocity, state (pos, vel) with a 2x2 covariance
    // (var_p, var_v, var_pv the p/v cross term). w/h: random-walk, state (pos) with scalar variance.
    // The actual predict/correct math lives in the anonymous namespace in lock_core.cpp; these are
    // plain scalars purely so the header never has to name an implementation-only filter type.
    double m_cx_pos = 0, m_cx_vel = 0, m_cx_var_p = 0, m_cx_var_v = 0, m_cx_var_pv = 0;
    double m_cy_pos = 0, m_cy_vel = 0, m_cy_var_p = 0, m_cy_var_v = 0, m_cy_var_pv = 0;
    double m_w_pos = 0, m_w_var = 0;
    double m_h_pos = 0, m_h_var = 0;
};

} // namespace lock
} // namespace garuda
