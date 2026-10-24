#include "garuda/lock_core.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>

// Scalar Kalman filter step functions -- the "filters" named in the class comment in lock_core.hpp.
// Kept as free functions here (not member functions, not a class) so LockCore's private state in the
// header can stay plain (pos, vel, var...) doubles: the header never has to name an
// implementation-only filter type.
namespace {

// Constant-velocity filter over a 2-state (pos, vel) with covariance (varP, varV, varPV the p/v cross
// term). State transition F = [[1, dt], [0, 1]] propagates the covariance as P' = F P F^T (the
// varP/varPV terms below); process noise uses the discrete white-noise-acceleration (WNA) model: an
// unknown constant acceleration with std `qAccStd` (px/s^2) held over the interval, giving
// Q = qAccStd^2 * [[dt^4/4, dt^3/2], [dt^3/2, dt^2]] (i.e. G G^T with G = [dt^2/2, dt]^T -- the
// impulse response of position/velocity to a constant acceleration over one interval). Fix round 1
// (2026-09-04, Ruling 1): an earlier, much smaller additive model (varP/varV += q*dt) made a fast
// mover (~500 px/s) fall out of gate within 2-3 frames of a cold lock() and unable to reacquire after
// even a short gap, because with velocity assumed exactly zero at lock() there was nowhere near
// enough first-frame position uncertainty to cover the true displacement. This WNA model, combined
// with a nonzero initial velocity uncertainty at lock() (see LockCore::lock(), p0_vel_std), gives a
// first-post-lock gate radius of ~50 px at dt=40 ms (see the Params comment in lock_core.hpp) that
// comfortably covers the brief's 20 px/frame example.
void cvPredict(double& pos, double& vel, double& varP, double& varV, double& varPV, double dt, double qAccStd) {
    pos += vel * dt;
    double newVarP = varP + 2.0 * dt * varPV + dt * dt * varV;
    double newVarPV = varPV + dt * varV;
    double dt2 = dt * dt, dt3 = dt2 * dt, dt4 = dt2 * dt2;
    double qVar = qAccStd * qAccStd;
    varP = newVarP + qVar * dt4 / 4.0;
    varPV = newVarPV + qVar * dt3 / 2.0;
    varV = varV + qVar * dt2;
}

// Scalar-measurement (position only, H = [1, 0]) correction: innovation y = z - pos; S = varP + r;
// Kalman gain K = P H^T / S = (varP/S, varPV/S); P <- (I - K H) P.
void cvCorrect(double& pos, double& vel, double& varP, double& varV, double& varPV, double z, double r) {
    double innov = z - pos;
    double s = varP + r;
    double kp = varP / s;
    double kv = varPV / s;
    pos += kp * innov;
    vel += kv * innov;
    double newVarP = varP - kp * varP;
    double newVarPV = varPV - kp * varPV;
    double newVarV = varV - kv * varPV;
    varP = newVarP;
    varPV = newVarPV;
    varV = newVarV;
}

// Random-walk (size) filter: state is just `pos`, no velocity term -- the mean has no deterministic
// drift, only its uncertainty grows with time.
void rwPredict(double& var, double dt, double q) { var += q * dt; }

inline double sq(double v) { return v * v; }

void rwCorrect(double& pos, double& var, double z, double r) {
    double innov = z - pos;
    double s = var + r;
    double k = var / s;
    pos += k * innov;
    var -= k * var;
}

} // namespace

namespace garuda {
namespace lock {

const char* state_name(State s) {
    switch (s) {
        case State::NONE: return "none";
        case State::CONFIRMED: return "confirmed";
        case State::OCCLUDED: return "occluded";
        case State::REACQUIRING: return "reacquiring";
        case State::LOST: return "lost";
    }
    return "none"; // unreachable: State has no other enumerators.
}

LockCore::LockCore(const Params& p) : m_params(p) {}

void LockCore::lock(const Obs& target, double ts_ms) {
    // Fix round 4 (M3): a degenerate box would make every later size check divide by ~0 (NaN -> nothing
    // can ever associate, and the lock silently decays to LOST). Reject it here instead, leaving the
    // core exactly as it was; warned once so a caller feeding degenerate boxes is not silent.
    if (target.w <= 1.0 || target.h <= 1.0) {
        static bool warned = false;
        if (!warned) {
            warned = true;
            std::fprintf(stderr, "lock_core: ignoring lock() on a degenerate box (w=%.3f h=%.3f)\n",
                         target.w, target.h);
        }
        return;
    }

    m_locked = true;
    m_state = State::CONFIRMED;
    ++m_epoch;   // see Output::epoch: a new lock generation, never reset
    m_last_ts_ms = ts_ms;
    m_last_confirmed_ts_ms = ts_ms;
    m_last_id = target.id;
    m_locked_cls = target.cls;   // fixed for the life of this lock -- what the class gate tests
    m_last_obs_cls = target.cls; // round 5 (Ruling 22.3): what Output.cls publishes, follows winners

    double cx = target.x + target.w / 2.0;
    double cy = target.y + target.h / 2.0;
    // Zero-MEAN initial velocity (no history yet), but NOT zero uncertainty: var_v is seeded at
    // p0_vel_std^2, not some small process-noise scale, so a fast mover already in motion when
    // lock() fires is covered by the very first post-lock gate rather than assumed stationary.
    // var_p is seeded at the measurement noise (as if the lock click were itself a single noisy
    // observation).
    double p0VelVar = m_params.p0_vel_std * m_params.p0_vel_std;
    m_cx_pos = cx; m_cx_vel = 0.0; m_cx_var_p = m_params.r_pos; m_cx_var_v = p0VelVar; m_cx_var_pv = 0.0;
    m_cy_pos = cy; m_cy_vel = 0.0; m_cy_var_p = m_params.r_pos; m_cy_var_v = p0VelVar; m_cy_var_pv = 0.0;
    m_w_pos = target.w; m_w_var = m_params.r_size;
    m_h_pos = target.h; m_h_var = m_params.r_size;

    m_last_confirmed_box = Box{target.x, target.y, target.w, target.h};

    Output out;
    out.state = State::CONFIRMED;
    out.identity_locked = true;
    out.observation_valid = true;
    out.quality = 1.0;
    out.obs_age_ms = 0.0;
    out.uncertainty_px = std::sqrt(std::max(m_cx_var_p, m_cy_var_p));
    out.box = m_last_confirmed_box;
    out.cls = m_last_obs_cls;   // Ruling 22.3: the last associated observation, not the locked class
    out.last_id = m_last_id;
    out.epoch = m_epoch;
    out.ref_w = m_w_pos;
    out.ref_h = m_h_pos;
    m_last = out;
}

void LockCore::unlock() {
    m_locked = false;
    m_state = State::NONE;
    m_last = Output{};
    m_last.epoch = m_epoch;   // the epoch of the lock just ended -- never reset (see Output::epoch)
}

Output LockCore::update(double ts_ms, const std::vector<Obs>& dets) {
    if (!m_locked) {
        m_last = Output{};
        m_last.epoch = m_epoch;
        return m_last;
    }

    // Once truly LOST the lock never auto-recovers: by the time expire_ms has elapsed the filters'
    // covariance has grown so large that almost anything would fall "in gate", so re-arming requires an
    // explicit lock() rather than letting a coincidental later detection silently reacquire.
    if (m_state == State::LOST) {
        Output out;
        out.state = State::LOST;
        out.identity_locked = false;
        out.observation_valid = false;
        out.quality = 0.0;
        out.obs_age_ms = std::max(0.0, ts_ms - m_last_confirmed_ts_ms);   // M1: never negative
        out.uncertainty_px = std::sqrt(std::max(m_cx_var_p, m_cy_var_p));
        out.cls = m_last_obs_cls;   // Ruling 22.3: the last associated observation
        out.last_id = m_last_id;
        out.epoch = m_epoch;
        out.ref_w = m_w_pos;
        out.ref_h = m_h_pos;
        m_last_ts_ms = ts_ms;
        m_last = out;
        return m_last;
    }

    // dt clamp: the first update() after lock() (or after any stalled gap) advances the filters by at
    // most 1 s per predict step, so a paused/stalled pipeline cannot explode the covariance. Only the
    // filters' own predict step is capped this way -- obs_age_ms and the OCCLUDED/REACQUIRING/LOST
    // thresholds below use the true, unclamped elapsed wall-clock time, since those must reflect how
    // long the target has actually been unseen.
    double dtS = (ts_ms - m_last_ts_ms) / 1000.0;
    dtS = std::max(0.0, std::min(1.0, dtS));
    m_last_ts_ms = ts_ms;

    // Fix round 4 (M3): the size terms divide by the size filter's own w/h. lock() now rejects a
    // degenerate box outright, but the random-walk size filter is still corrected toward whatever a
    // winning detection reports, so guard the divisors here too rather than relying on that. Read
    // BEFORE the predict step (which touches only the variances, never these means) because round 3's
    // process/measurement noise is scaled by them.
    const double wRef = std::max(m_w_pos, 1.0);
    const double hRef = std::max(m_h_pos, 1.0);

    // On-board fix round 3 (Ruling 19.2, mechanism M-B): the size random walk's variance RATE is
    // relative to the reference -- (q_size_frac * ref)^2 px^2/s -- with the absolute `q_size` kept as
    // a floor for config compatibility. Run 5's owner walked from a 169 px-wide box to 594 px in
    // 1.4 s; an absolute 50 px^2/s could never follow that, while 0.5 of the reference can.
    const double qSizeW = std::max(m_params.q_size, sq(m_params.q_size_frac * wRef));
    const double qSizeH = std::max(m_params.q_size, sq(m_params.q_size_frac * hRef));

    cvPredict(m_cx_pos, m_cx_vel, m_cx_var_p, m_cx_var_v, m_cx_var_pv, dtS, m_params.q_acc_std);
    cvPredict(m_cy_pos, m_cy_vel, m_cy_var_p, m_cy_var_v, m_cy_var_pv, dtS, m_params.q_acc_std);
    rwPredict(m_w_var, dtS, qSizeW);
    rwPredict(m_h_var, dtS, qSizeH);

    // Fix round 4 (M1): clamp at 0. A frame whose timestamp is EARLIER than the last confirmed one
    // (an out-of-order/reset ISP clock) used to give a negative age, which read as
    // quality = (1 + |age|/expire_ms) * 0.5 > 0.5 -- confidence manufactured out of a clock glitch.
    // Clamped, such a frame is simply "no time has passed since the last sighting".
    double obsAgeMs = std::max(0.0, ts_ms - m_last_confirmed_ts_ms);
    // On-board fix round 9 (Ruling 29) -- STALL EXPIRY. Expiry is elapsed wall-clock time since the
    // last confirmation, NOT a count of update() calls. Until this round the state machine advanced
    // only on the calls that actually arrived, so a pipeline that stopped calling update() (a
    // stalled camera, a blocked sink) could resume 11 s later and have the core associate the first
    // frame back as though no time had passed -- the outside review's probe, 2026-09-05: lock at
    // t=0, one update() at t=11000 with the target's own box, and the pre-round-9 core read
    // CONFIRMED on a lock that had been dead for a second.
    //
    // `expired` is evaluated BEFORE association and suppresses it entirely: no candidate is built,
    // so the no-winner branch below runs and sets LOST on exactly the same arithmetic an ordinary
    // ticked expiry uses (obsAgeMs > expire_ms), with the same Output fields, the same epoch (an
    // expiry is not a new lock generation) and therefore the same node-side transition log. The
    // filters' own predict step above still runs, so `uncertainty_px` on that frame remains an
    // honest diagnostic of how far the lock had drifted rather than a stale pre-stall value.
    //
    // The ticked path is unchanged in every band that was alive before: a frame at obs_age <=
    // expire_ms associates exactly as it did. What changes is that a frame PAST expire_ms can no
    // longer associate at all -- previously an in-gate candidate on such a frame could reset the
    // lock to CONFIRMED, which is the same "expiry only counts if someone was watching" error in
    // miniature.
    const bool expired = obsAgeMs > m_params.expire_ms;
    // The widened (out-of-gate) search runs only for the first `reacquire_ms` of the REACQUIRING band;
    // after that, only in-gate candidates are considered until expiry (obs_age_ms > expire_ms -> LOST).
    bool widened = obsAgeMs > m_params.occlusion_ms && obsAgeMs <= m_params.occlusion_ms + m_params.reacquire_ms;

    double gate2 = m_params.gate_sigma * m_params.gate_sigma;
    // Fix round 2 (Ruling 2): cap the variance used for GATING ONLY -- not the filter's own state, and
    // not uncertainty_px below (that stays the true, uncapped std). Without this, a long-uncorrected
    // coast's ~t^4-growing variance would make "in gate" cover most of the frame, defeating the point
    // of the widened-search distinction the REACQUIRING state machine depends on.
    double capVar = (m_params.gate_max_px / m_params.gate_sigma) * (m_params.gate_max_px / m_params.gate_sigma);
    double effCxVar = std::min(m_cx_var_p, capVar);
    double effCyVar = std::min(m_cy_var_p, capVar);

    // On-board fix round 3 (Ruling 19.1, mechanism M-A): the position MEASUREMENT noise scales with
    // the box. A detector's box centre on a 650 px person jitters tens of px frame to frame (run 5:
    // the width swung 640 -> 774 on arm movement, moving the centre 40-60 px) while a 60 px box's
    // centre jitters a few. Per-axis std = max(sqrt(r_pos), r_pos_frac * ref) -- r_pos stays the
    // floor, in its own px^2 unit, hence the sqrt.
    const double rPosX = sq(std::max(std::sqrt(m_params.r_pos), m_params.r_pos_frac * wRef));
    const double rPosY = sq(std::max(std::sqrt(m_params.r_pos), m_params.r_pos_frac * hRef));

    // The gate is a Mahalanobis test against the INNOVATION covariance S = min(P, cap) + R (round 3;
    // before it, R was omitted from the gate altogether -- see the gate-radius block in
    // lock_core.hpp). `gate_min_px` then floors the RADIUS: a converged filter on a big box must not
    // gate tighter than a fraction of that box, or the target's own detector jitter falls out of gate
    // and the lock flickers confirmed<->occluded (run 5's `confirmed -> occluded (33)` runs).
    const double gateMinPx = m_params.gate_min_frac * std::max(wRef, hRef);
    const double gateMinVar = sq(gateMinPx / m_params.gate_sigma);
    const double sX = std::max(effCxVar + rPosX, gateMinVar);
    const double sY = std::max(effCyVar + rPosY, gateMinVar);

    // On-board fix round 1 (Ruling 16.2): the size gate is VARIANCE-AWARE, not a fixed fraction of a
    // reference that may itself be stale or wrong. Per dimension the admitted deviation is
    //   tol = max(size_tol * ref, gate_sigma * sqrt(size_var + r_size_eff))
    // where size_var is that dimension's random-walk variance AFTER this frame's predict. So a
    // reference that has just been corrected stays tight, while a small or stale reference relaxes
    // with time instead of locking the core out for good. Run 1's failure (bench/benchlog.md,
    // "Run 1 ... edge-entry failure") is the motivating case: a 29x194 sliver reference made the fixed
    // gate +/-14.5 px in w, so the very next frame's 56 px box was already out and NOTHING could ever
    // associate again.
    // On-board fix round 3 (Ruling 19.2): both noise terms feeding this are now relative -- the
    // measurement variance is max(r_size, (r_size_frac * ref)^2) and the process rate is the
    // qSizeW/qSizeH computed above -- so the same formula now tracks a box that legitimately triples
    // in size (run 5's M-B) instead of only a small one that legitimately doubles.
    const double rSizeW = std::max(m_params.r_size, sq(m_params.r_size_frac * wRef));
    const double rSizeH = std::max(m_params.r_size, sq(m_params.r_size_frac * hRef));
    const double wTol = std::max(m_params.size_tol * wRef,
                                 m_params.gate_sigma * std::sqrt(m_w_var + rSizeW));
    const double hTol = std::max(m_params.size_tol * hRef,
                                 m_params.gate_sigma * std::sqrt(m_h_var + rSizeH));

    // On-board fix round 4 (Ruling 20a): `relaxed_only` marks a candidate that is eligible ONLY
    // because of the same-id relaxation -- it fails the strict (mult = 1) position gate or the strict
    // size tolerance. Such a candidate corrects POSITION but not SIZE (see the winner branch). A
    // candidate that never used the relaxation (any new id, including one taken by the widened
    // full-frame stage) is never `relaxed_only`, so the widened path still teaches the size filter.
    struct Candidate { double score; const Obs* det; bool relaxed_only; bool new_id; };
    std::vector<Candidate> inGateCands, outGateCands;   // fix round 4 (I3/Ruling 11): two pools
    inGateCands.reserve(dets.size());

    for (const auto& d : dets) {
        if (expired) break;   // Ruling 29: an expired lock associates nothing, in either stage
        // On-board fix round 3 (Ruling 19.3): a candidate carrying the core's OWN last id is
        // frame-to-frame continuity the multi-object tracker already established (and every candidate
        // the node passes here is LIVE, not coasting -- node_main.cpp's `live_obs`), so the core must
        // not veto it with a stale position/size reference. Its position gate radius and size
        // tolerance are both multiplied by `same_id_gate_mult`, and because the motion and size score
        // terms are computed from those same relaxed scales, its score reflects the relaxation too.
        // A radius multiplied by `mult` is a variance multiplied by `mult^2`.
        const bool sameId = (d.id == m_last_id && d.id >= 0);
        const double mult = sameId ? m_params.same_id_gate_mult : 1.0;
        const double mult2 = mult * mult;

        bool sameClass = d.cls == m_locked_cls;

        // On-board fix round 5 (Ruling 22.1) -- THE CLASS GATE. A candidate whose class differs from
        // the LOCKED class (fixed at lock(); not the published Output.cls, which follows the last
        // observation) is eligible only if it carries the core's own last id: the multi-object
        // tracker's frame-to-frame continuity is then the evidence that this is the same object the
        // detector merely re-labelled. Different class AND different id is never associated, in any
        // state, by either stage -- that combination is exactly run 10e's twelve-minute walk onto a
        // suitcase. The score's class term is unchanged for the same-id case (below).
        if (!sameClass && !sameId) continue;

        // On-board fix round 5 (Ruling 22.2) -- the hard size-ratio cap for DIFFERENT-ID candidates.
        // On top of, never instead of, the variance-aware tolerance below: that tolerance grows with
        // obs_age by design, and a few seconds of REACQUIRING was enough for it to call a 229x270
        // static box "size-consistent" with a 135x285 phone. Same-id candidates are exempt (run 5's
        // walk-toward-the-camera growth was same-id and must still be followed). A non-positive
        // `size_ratio_max` disables the cap.
        if (!sameId && m_params.size_ratio_max > 0.0) {
            const double hi = m_params.size_ratio_max, lo = 1.0 / m_params.size_ratio_max;
            const double rw = d.w / wRef, rh = d.h / hRef;
            if (rw < lo || rw > hi || rh < lo || rh > hi) continue;
        }

        double dcx = d.x + d.w / 2.0, dcy = d.y + d.h / 2.0;
        double dSq = (dcx - m_cx_pos) * (dcx - m_cx_pos) / sX
                   + (dcy - m_cy_pos) * (dcy - m_cy_pos) / sY;   // strict (mult = 1)
        double d2 = dSq / mult2;                                  // relaxed for a same-id candidate
        bool inGate = d2 <= gate2;
        double dw = std::fabs(d.w - wRef), dh = std::fabs(d.h - hRef);
        bool sizeOk = dw <= wTol * mult && dh <= hTol * mult;
        // On-board fix round 10 (Ruling 32): out of gate, a DIFFERENT-id candidate must earn its
        // way in. (a) same class is already required by `sameClass` below; (b) its id must have been
        // born strictly after the last confirmed observation -- an id that was alive while the target
        // was still confirmed was, by construction, a different object, and `first_seen_ms` of -1
        // ("the engine cannot tell us") is treated as pre-existing; (d) confidence floor;
        // (e) an age ceiling that closes the different-id half of the widened window before
        // `reacquire_ms` does. Condition (c) -- "the only eligible out-of-gate candidate this frame"
        // -- cannot be evaluated per candidate and is applied to the finished pool below.
        // A SAME-id candidate is exempt from all of it: tracker continuity IS identity evidence.
        // The in-gate half of this test is deliberately untouched.
        bool bornAfterLoss = d.first_seen_ms >= 0.0 && d.first_seen_ms > m_last_confirmed_ts_ms;
        bool newIdWidenedOk = m_params.widened_new_id
                            && bornAfterLoss
                            && d.conf >= m_params.widened_new_id_min_conf
                            && obsAgeMs <= m_params.widened_new_id_max_age_ms;
        bool widenedEligible = widened && !inGate && sameClass && sizeOk
                             && (sameId || newIdWidenedOk);
        bool eligible = (inGate && sizeOk) || widenedEligible;
        if (!eligible) continue;

        // Ruling 20a: did it need the relaxation? Only a same-id candidate can, and it needed it if
        // the strict gate or the strict tolerance would have refused it.
        bool strictOk = (dSq <= gate2) && dw <= wTol && dh <= hTol;
        bool relaxedOnly = sameId && !strictOk;

        double score = m_params.w_conf * d.conf
                     + m_params.w_motion * std::exp(-d2 / 2.0)
                     + m_params.w_size * (1.0 - std::min(1.0, dw / (wRef * mult)))
                     + m_params.w_class * (sameClass ? 1.0 : 0.0)
                     + m_params.w_id * (sameId ? 1.0 : 0.0);
        (inGate ? inGateCands : outGateCands).push_back({score, &d, relaxedOnly, !sameId});
    }

    // Ruling 32(c): a DIFFERENT-id candidate may take the widened stage only when it is the single
    // eligible out-of-gate candidate this frame. More than one, and every different-id candidate is
    // dropped -- out of gate the failure mode is "one plausible stranger", which an ambiguity ratio
    // between two strangers cannot catch, so the bar here is exclusivity rather than a margin.
    // Same-id candidates are never dropped by this (the tracker's own continuity is not guesswork),
    // and at most one can exist per frame since an id appears once.
    if (outGateCands.size() > 1) {
        outGateCands.erase(std::remove_if(outGateCands.begin(), outGateCands.end(),
                                           [](const Candidate& c) { return c.new_id; }),
                            outGateCands.end());
    }

    // One pool's own winner test: clear `floor`, and (if there is a runner-up in THIS pool) beat it by
    // `ambiguity_ratio`. `ambiguous` is reported back so the caller can distinguish "nothing here was
    // plausible at all" (fall through to the widened stage) from "two plausible candidates here"
    // (spec §8.2: report OCCLUDED/UNCERTAIN -- never widen the search on an ambiguous local frame).
    auto pick = [&](const std::vector<Candidate>& cands, double floor, bool& ambiguous)
                    -> const Candidate* {
        ambiguous = false;
        if (cands.empty()) return nullptr;
        size_t bestIdx = 0;
        for (size_t i = 1; i < cands.size(); ++i)
            if (cands[i].score > cands[bestIdx].score) bestIdx = i;
        double bestScore = cands[bestIdx].score;
        double runnerUp = -1.0;
        bool haveRunnerUp = false;
        for (size_t i = 0; i < cands.size(); ++i) {
            if (i == bestIdx) continue;
            if (!haveRunnerUp || cands[i].score > runnerUp) { runnerUp = cands[i].score; haveRunnerUp = true; }
        }
        if (bestScore < floor) return nullptr;                       // not plausible: local search failed
        if (haveRunnerUp && bestScore < m_params.ambiguity_ratio * runnerUp) {
            ambiguous = true;                                        // plausible but indistinguishable
            return nullptr;
        }
        return &cands[bestIdx];
    };

    const Obs* winner = nullptr;
    double winnerScore = 0.0;
    bool winnerRelaxedOnly = false;
    bool inGateAmbiguous = false;
    // On-board fix round 4 (Ruling 20b): while REACQUIRING, the in-gate pool is judged against
    // `min_score_widened` too. CONFIRMED/OCCLUDED keep the strict `min_score`. `widenedFloor` is the
    // same value the out-of-gate stage uses, so a config that lowers one lowers both -- which is the
    // point: the floor is a property of "how long has this been missing", not of which stage found
    // the candidate.
    const double widenedFloor = m_params.min_score_widened.value_or(m_params.min_score);
    const bool reacquiringBand = obsAgeMs > m_params.occlusion_ms && obsAgeMs <= m_params.expire_ms;
    const double inGateFloor = reacquiringBand ? widenedFloor : m_params.min_score;
    if (const Candidate* c = pick(inGateCands, inGateFloor, inGateAmbiguous)) {
        winner = c->det;
        winnerScore = c->score;
        winnerRelaxedOnly = c->relaxed_only;
    } else if (!inGateAmbiguous) {
        // Stage 2 -- the widened, full-frame search. Reached only when the local search found nothing
        // to consider (empty pool, or nothing clearing min_score); an ambiguous local frame stops here.
        // outGateCands is non-empty only while `widened` is true (see the eligibility test above).
        bool widenedAmbiguous = false;
        if (const Candidate* c = pick(outGateCands, widenedFloor, widenedAmbiguous)) {
            winner = c->det;
            winnerScore = c->score;
            winnerRelaxedOnly = c->relaxed_only;
        }
    }

    Output out;
    if (winner) {
        double wcx = winner->x + winner->w / 2.0, wcy = winner->y + winner->h / 2.0;
        // Round 3: the SAME box-scaled measurement variances the gate used (Ruling 19.1/19.2). Using
        // one R for gating and another for the update would be incoherent -- and the correction is
        // where the scaling earns most of its keep: a 650 px box's 65 px centre noise now damps the
        // filter instead of yanking it 40-60 px per frame.
        cvCorrect(m_cx_pos, m_cx_vel, m_cx_var_p, m_cx_var_v, m_cx_var_pv, wcx, rPosX);
        cvCorrect(m_cy_pos, m_cy_vel, m_cy_var_p, m_cy_var_v, m_cy_var_pv, wcy, rPosY);
        // On-board fix round 4 (Ruling 20a): POSITION always, SIZE only when the winner cleared the
        // STRICT gates. A candidate admitted solely by the same-id relaxation is, by construction, a
        // box that does not look like what the core is tracking -- in run 7 it was the owner's head
        // above a chair back (155x625 -> 276x159 -> 152x129 in half a second) -- and partial
        // occlusion and edge clipping do exactly that, transiently. Following it is right: the
        // tracker's own frame-to-frame continuity says it is the target. LEARNING it is not: the
        // core then cannot recognise the full body when it re-emerges, which is precisely how run 7's
        // 6-second hide ended in LOST with the owner standing in plain view. The size filter is left
        // untouched, so its variance keeps growing with obs_age and the tolerance widens -- the
        // reference stays the last size the core actually believed, and grows more forgiving, rather
        // than tracking a transient silhouette.
        if (!winnerRelaxedOnly) {
            rwCorrect(m_w_pos, m_w_var, winner->w, rSizeW);
            rwCorrect(m_h_pos, m_h_var, winner->h, rSizeH);
        }

        m_state = State::CONFIRMED;
        m_last_id = winner->id; // identity follows whichever candidate wins the gate/score test, not
                                 // necessarily the previous id -- see task brief: the id itself is not
                                 // sacred, position/size/class continuity is.
        // Round 5 (Ruling 22.3): the PUBLISHED class follows the winner too, so a same-id class
        // flicker (the only way a different-class winner can get here at all, post-Ruling 22.1) is
        // visible in the snapshot instead of being masked by a class field frozen at lock().
        m_last_obs_cls = winner->cls;
        m_last_confirmed_ts_ms = ts_ms;
        m_last_confirmed_box = Box{m_cx_pos - m_w_pos / 2.0, m_cy_pos - m_h_pos / 2.0, m_w_pos, m_h_pos};

        out.quality = winnerScore;
        out.obs_age_ms = 0.0;
        out.observation_valid = true;
    } else {
        // Coasting this frame. Fix round 4 (I6/Ruling 14): bound the predicted centre to the frame
        // before it is carried into the next frame's gate. `pos += vel*dt` is otherwise unbounded, so
        // a target that walks out at 300 px/s is "predicted" hundreds of px off-frame within a second
        // or two and the local gate no longer covers the edge it must re-enter through. Only the mean
        // moves; the velocity, the covariance and the published (frozen) box are untouched, so this
        // costs nothing for a target that reappears mid-frame. See the Params comment in lock_core.hpp
        // for why the clamp region is the frame itself rather than the frame plus a gate_max_px margin.
        m_cx_pos = std::min(std::max(m_cx_pos, 0.0), static_cast<double>(m_params.frame_w));
        m_cy_pos = std::min(std::max(m_cy_pos, 0.0), static_cast<double>(m_params.frame_h));

        m_state = (obsAgeMs <= m_params.occlusion_ms) ? State::OCCLUDED
                : (obsAgeMs <= m_params.expire_ms ? State::REACQUIRING : State::LOST);
        out.quality = std::max(0.0, 1.0 - obsAgeMs / m_params.expire_ms) * 0.5;
        out.obs_age_ms = obsAgeMs;
        out.observation_valid = false;
    }

    out.state = m_state;
    out.epoch = m_epoch;
    out.ref_w = m_w_pos;                 // Ruling 20a: the size reference, for tests/diagnostics
    out.ref_h = m_h_pos;
    out.identity_locked = m_state != State::LOST;
    out.uncertainty_px = std::sqrt(std::max(m_cx_var_p, m_cy_var_p));
    out.cls = m_last_obs_cls;   // Ruling 22.3: the last associated observation, not the locked class
    out.last_id = m_last_id;
    if (m_state == State::CONFIRMED)
        out.box = Box{m_cx_pos - m_w_pos / 2.0, m_cy_pos - m_h_pos / 2.0, m_w_pos, m_h_pos};
    else if (m_state == State::OCCLUDED || m_state == State::REACQUIRING)
        out.box = m_last_confirmed_box;
    else
        out.box.reset();

    m_last = out;
    return m_last;
}

} // namespace lock
} // namespace garuda
