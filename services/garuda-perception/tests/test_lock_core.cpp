#undef NDEBUG
#include "garuda/lock_core.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

using garuda::lock::Box;
using garuda::lock::LockCore;
using garuda::lock::Obs;
using garuda::lock::Output;
using garuda::lock::Params;
using garuda::lock::State;
using garuda::lock::state_name;

namespace {

Obs mk(int id, const std::string& cls, double conf, double x, double y, double w, double h) {
    Obs o;
    o.id = id; o.cls = cls; o.conf = conf; o.x = x; o.y = y; o.w = w; o.h = h;
    return o;
}

// Same, plus the round-10 (Ruling 32b) birth timestamp: the ts_ms at which this tracker id was first
// seen. `mk()` leaves it -1 ("unknown"), which the core treats as pre-existing and therefore refuses
// in the widened stage -- so every case that needs an out-of-gate DIFFERENT-id candidate to be
// eligible has to say when that id was born, which is the point of the ruling.
Obs mkb(int id, const std::string& cls, double conf, double x, double y, double w, double h,
        double first_seen_ms) {
    Obs o = mk(id, cls, conf, x, y, w, h);
    o.first_seen_ms = first_seen_ms;
    return o;
}

bool boxEq(const Box& a, const Box& b) { return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h; }

} // namespace

int main() {
    // 1) lock + steady detections -> CONFIRMED every frame, box follows within 1 px after 5 frames,
    //    observation_valid true, obs_age_ms 0. Target moves at a constant velocity (5 px/frame in x at
    //    25 fps) so this also exercises the CV filter's velocity convergence, not just a stationary
    //    re-measurement. Fix round 1 (Ruling 1): with the white-noise-acceleration process model and
    //    a large initial velocity uncertainty (p0_vel_std), the tracking lag at 5 px/frame is already
    //    sub-pixel by frame 2 (verified numerically), so this is a comfortable, not a tight, margin.
    {
        LockCore lc;
        double dtMs = 40.0; // 25 fps
        double x0 = 600, y0 = 340, w = 80, h = 160;
        double vx = 5.0 / dtMs; // px/ms
        lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
        for (int f = 1; f <= 8; ++f) {
            double t = f * dtMs;
            double x = x0 + vx * t;
            Output out = lc.update(t, {mk(1, "person", 0.9, x, y0, w, h)});
            assert(out.state == State::CONFIRMED);
            assert(out.observation_valid);
            assert(out.obs_age_ms == 0.0);
            assert(out.box.has_value());
            if (f >= 5) {
                assert(std::fabs(out.box->x - x) < 1.0);
                assert(std::fabs(out.box->y - y0) < 1.0);
            }
        }
    }

    // 2) gap of 400 ms (< occlusion_ms 500) -> OCCLUDED, box frozen bit-exact equal to the last
    //    confirmed box, observation_valid false, identity_locked true; a detection returning near the
    //    prediction (same id) -> CONFIRMED with the same identity.
    {
        LockCore lc;
        double x0 = 400, y0 = 300, w = 60, h = 120;
        lc.lock(mk(7, "person", 0.9, x0, y0, w, h), 0.0);
        Output steady;
        for (int f = 1; f <= 5; ++f) steady = lc.update(f * 40.0, {mk(7, "person", 0.9, x0, y0, w, h)});
        assert(steady.state == State::CONFIRMED);
        Box lastConfirmed = *steady.box;

        double tGapStart = 5 * 40.0;
        Output gapOut = lc.update(tGapStart + 400.0, {});
        assert(gapOut.state == State::OCCLUDED);
        assert(!gapOut.observation_valid);
        assert(gapOut.identity_locked);
        assert(gapOut.box.has_value());
        assert(boxEq(*gapOut.box, lastConfirmed));

        Output back = lc.update(tGapStart + 440.0, {mk(7, "person", 0.9, x0 + 1.0, y0, w, h)});
        assert(back.state == State::CONFIRMED);
        assert(back.last_id == 7);
    }

    // 3a) gap into REACQUIRING: a same-class, size-consistent, high-conf detection far outside the
    //     gate is NOT taken while still OCCLUDED (obs_age <= occlusion_ms); once obs_age is past
    //     occlusion_ms (REACQUIRING, widened search window) the same far candidate IS taken because it
    //     is unambiguous (no runner-up).
    //     Fix round 2 (Ruling 2) note on the "far" distance: round 1 used offsets in the thousands of
    //     px because the (then-uncapped) WNA variance grew fast enough that the *ordinary* gate itself
    //     swallowed any realistic offset within ~1 s, forcing artificially huge test candidates just to
    //     stay outside it. gate_max_px now caps the gating variance, so the ordinary gate never exceeds
    //     300 px radius no matter how long the coast -- a realistic 500 px offset is outside it at
    //     every checkpoint below (verified numerically: effective-gate d2 ~= 241.5 at the OCCLUDED
    //     check (raw gate ~97 px, not yet capped), d2 ~= 25 at the widened-window check (capped at
    //     exactly 300 px), both > gate_sigma^2 = 9) while remaining reachable via the widened branch.
    //     **On-board fix round 10 (Ruling 32)**: the far candidate carries a NEW tracker id, so it
    //     now has to satisfy (b) born-after-the-last-confirmation, (d) conf >= 0.5 and (e) obs_age
    //     <= 5000 ms. It does (conf 0.9, obs_age 1000 ms), once the test says when the id was born --
    //     500 ms, after the last confirmation at 160 ms. The widened stage's own mechanics (the
    //     window, the class/size eligibility, the score floor) are what this case covers and are
    //     unchanged.
    {
        LockCore lc;
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(2, "person", 0.9, x0, y0, w, h), 0.0);
        Output steady;
        for (int f = 1; f <= 4; ++f) steady = lc.update(f * 40.0, {mk(2, "person", 0.9, x0, y0, w, h)});
        assert(steady.state == State::CONFIRMED);
        double lastConfirmedTs = 4 * 40.0;

        // still within occlusion_ms (500) -> far candidate must not be taken
        Output stillOccluded = lc.update(lastConfirmedTs + 300.0, {mk(50, "person", 0.9, x0 + 500.0, y0, w, h)});
        assert(stillOccluded.state == State::OCCLUDED);
        assert(!stillOccluded.observation_valid);

        // past occlusion_ms, still empty -> REACQUIRING
        Output reacq = lc.update(lastConfirmedTs + 600.0, {});
        assert(reacq.state == State::REACQUIRING);

        // within the widened window (occlusion_ms + reacquire_ms = 3500 by default): the lone far,
        // size-consistent, same-class candidate is unambiguous -> taken (out of the capped gate --
        // d2 ~= 25 > 9 -- but eligible via the widened branch's class+size check).
        Output taken = lc.update(lastConfirmedTs + 1000.0,
                                  {mkb(51, "person", 0.9, x0 + 500.0, y0, w, h, 500.0)});
        assert(taken.state == State::CONFIRMED);
        assert(taken.last_id == 51);
        // Fix round 4 (I6/Ruling 14): pin the score this case actually clears, so a weight/size drift
        // cannot silently flip it. Out of gate the motion term is ~0 (d^2 = 500^2/100^2 = 25 ->
        // 0.35*exp(-12.5) ~= 1.3e-6), the id is new (no w_id bonus) and the size matches exactly:
        //   0.25*0.9 + 0.15 + 0.15 = 0.525 >= min_score_widened (== min_score 0.5) -- by 0.025.
        assert(std::fabs(taken.quality - 0.525) < 1e-3);
        assert(taken.quality >= Params{}.min_score);
    }

    // 3b) REACQUIRING with two equally-good far candidates -> ambiguous, no association (state stays
    //     REACQUIRING), quality < 0.5. Same 500 px offset rationale as 3a.
    //     Round 10 (Ruling 32c) note: with two born-after-loss candidates in the widened pool this
    //     is now refused by EXCLUSIVITY before the ambiguity margin is ever consulted -- out of gate
    //     the bar is "exactly one candidate", stricter than a margin. The outcome asserted here is
    //     unchanged and case 22's (c) sub-case pins the new mechanism directly; the margin itself is
    //     still exercised by the in-gate pool (case 12b).
    {
        LockCore lc;
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(2, "person", 0.9, x0, y0, w, h), 0.0);
        for (int f = 1; f <= 4; ++f) lc.update(f * 40.0, {mk(2, "person", 0.9, x0, y0, w, h)});
        double lastConfirmedTs = 4 * 40.0;
        lc.update(lastConfirmedTs + 600.0, {}); // -> REACQUIRING

        Output ambiguous = lc.update(lastConfirmedTs + 1000.0, {
            mkb(60, "person", 0.9, x0 + 500.0, y0, w, h, 500.0),
            mkb(61, "person", 0.9, x0 + 501.0, y0, w, h, 500.0),
        });
        assert(ambiguous.state == State::REACQUIRING);
        assert(!ambiguous.observation_valid);
        assert(ambiguous.quality < 0.5);
    }

    // 3c) the widened (out-of-gate) search runs only for the first reacquire_ms of REACQUIRING
    //     (obs_age from occlusion_ms to occlusion_ms + reacquire_ms); past that, only in-gate
    //     candidates are considered until expiry -- a far, size-consistent, unambiguous candidate is
    //     NOT taken once that window has closed.
    //     **On-board fix round 4 (Ruling 20c) makes reacquire_ms 9500, so with the SHIPPED defaults
    //     occlusion_ms + reacquire_ms == expire_ms == 10000 and this boundary coincides with expiry:
    //     there is no longer a band in which the lock is still alive but the widened search has
    //     closed.** That is the intended shipped behaviour (run 7's owner re-emerged 8.5 s into a
    //     hide, inside the old dead band), but the mechanism is still a real, configurable one, so
    //     this case now pins it with an EXPLICIT reacquire_ms = 3000 -- the pre-round-4 default --
    //     rather than deleting the coverage. Case 11 pins the shipped-default boundary.
    //     With gate_max_px capping the gate's state term at 300 px regardless of how long the coast
    //     has run, the SAME realistic 500 px offset as 3a/3b stays outside the gate at obs_age
    //     3600 ms too (d^2 = 500^2/10100 = 24.75 > 9).
    {
        Params p;
        p.reacquire_ms = 3000.0;          // explicit: the shipped default no longer closes early
        // Round 10: the candidate below satisfies every Ruling 32 condition (born after the last
        // confirmation, conf 0.9, obs_age 3600 <= 5000), so the WINDOW is the only thing refusing it.
        LockCore lc(p);
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(2, "person", 0.9, x0, y0, w, h), 0.0);
        for (int f = 1; f <= 4; ++f) lc.update(f * 40.0, {mk(2, "person", 0.9, x0, y0, w, h)});
        double lastConfirmedTs = 4 * 40.0;
        lc.update(lastConfirmedTs + 600.0, {}); // -> REACQUIRING

        // obs_age = 3600 > occlusion_ms(500) + reacquire_ms(3000) = 3500 -> widened window closed.
        Output out = lc.update(lastConfirmedTs + 3600.0,
                                {mkb(52, "person", 0.9, x0 + 500.0, y0, w, h, 500.0)});
        assert(out.state == State::REACQUIRING);
        assert(!out.observation_valid);
        assert(out.last_id != 52);
    }

    // 3e) on-board fix round 4 (Ruling 20c), the shipped-default half of 3c: with reacquire_ms 9500
    //     the widened window is open for the WHOLE reacquiring band, so the same far candidate that
    //     3c refuses at obs_age 3600 ms IS taken. Score (out of gate, new id, exact size):
    //     0.25*0.9 + 0.35*exp(-24.75/2) + 0.15 + 0.15 = 0.525 >= min_score_widened 0.40.
    //     Round 10 (Ruling 32): the candidate is a new id born after the loss, conf 0.9, obs_age
    //     3600 ms -- inside (e)'s 5000 ms ceiling -- so it clears every condition and this case still
    //     pins the WINDOW length (Ruling 20c), not the new-id policy.
    {
        LockCore lc;
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(2, "person", 0.9, x0, y0, w, h), 0.0);
        for (int f = 1; f <= 4; ++f) lc.update(f * 40.0, {mk(2, "person", 0.9, x0, y0, w, h)});
        double lastConfirmedTs = 4 * 40.0;
        lc.update(lastConfirmedTs + 600.0, {}); // -> REACQUIRING

        Output out = lc.update(lastConfirmedTs + 3600.0,
                                {mkb(52, "person", 0.9, x0 + 500.0, y0, w, h, 500.0)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 52);
        assert(std::fabs(out.quality - 0.525) < 1e-3);
    }

    // 3d) fix round 2 (Ruling 2), new case: after a ~2 s gap the gate radius is capped at
    //     gate_max_px=300 px (obs_age=2000 ms is deep into REACQUIRING's widened window, since
    //     occlusion_ms+reacquire_ms=3500). A same-*class* candidate at 350 px (outside the 300 px cap)
    //     IS considered via the out-of-gate widened path and associates; a candidate at the same 350 px
    //     with a MISMATCHED class is not eligible via either path (out of gate, and the widened
    //     branch's class check fails) and is NOT associated.
    //     Round 10 (Ruling 32): both candidates are new ids born after the loss at conf 0.9 inside
    //     the age ceiling, so they clear (b)/(d)/(e) and this case still pins the gate CAP and the
    //     widened branch's CLASS check.
    {
        LockCore lc;
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(2, "person", 0.9, x0, y0, w, h), 0.0);
        for (int f = 1; f <= 4; ++f) lc.update(f * 40.0, {mk(2, "person", 0.9, x0, y0, w, h)});
        double lastConfirmedTs = 4 * 40.0;

        // class mismatch at 350 px, obs_age=2000ms (REACQUIRING, widened window still open) -> rejected
        Output mismatch = lc.update(lastConfirmedTs + 2000.0,
                                     {mkb(80, "chair", 0.9, x0 + 350.0, y0, w, h, 500.0)});
        assert(mismatch.state == State::REACQUIRING);
        assert(!mismatch.observation_valid);
        assert(mismatch.last_id != 80);

        // same class at 350 px, one update() later (still well within the widened window) -> associated
        // via the out-of-gate path.
        Output matched = lc.update(lastConfirmedTs + 2040.0,
                                    {mkb(81, "person", 0.9, x0 + 350.0, y0, w, h, 500.0)});
        assert(matched.state == State::CONFIRMED);
        assert(matched.last_id == 81);
        // Fix round 4 (I6/Ruling 14): the widened path's score here is
        // 0.25*0.9 + 0.35*exp(-12.25/2) + 0.15 + 0.15 = 0.225 + 0.00077 + 0.30 = 0.5258
        // (d^2 = 350^2/100^2 = 12.25 at the capped 100 px effective std) -- 0.026 over the floor.
        assert(std::fabs(matched.quality - 0.5258) < 1e-3);
        assert(matched.quality >= Params{}.min_score);
    }

    // 4) gap > expire_ms (10000 default) -> LOST, box none, identity_locked false; a later detection
    //    (even an exact match) does not auto-lock.
    {
        LockCore lc;
        double x0 = 300, y0 = 200, w = 50, h = 100;
        lc.lock(mk(3, "person", 0.9, x0, y0, w, h), 0.0);
        lc.update(40.0, {mk(3, "person", 0.9, x0, y0, w, h)});
        Output lost = lc.update(40.0 + 10500.0, {});
        assert(lost.state == State::LOST);
        assert(!lost.box.has_value());
        assert(!lost.identity_locked);

        Output later = lc.update(40.0 + 10540.0, {mk(3, "person", 0.9, x0, y0, w, h)});
        assert(later.state == State::LOST);
        assert(!later.box.has_value());
        assert(!later.identity_locked);
    }

    // 5) two persons crossing: locked A (id=1) and B (id=2) land on nearly the same box with A getting
    //    the w_id continuity bonus -> scores are within the ambiguity ratio -> no association for those
    //    frames (OCCLUDED); once B leaves and only A remains -> CONFIRMED with last_id A; B never
    //    becomes the lock (last_id is never 2).
    {
        LockCore lc;
        double x0 = 640, y0 = 360, w = 80, h = 160;
        lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
        Output out = lc.update(40.0, {
            mk(1, "person", 0.9, x0, y0, w, h),
            mk(2, "person", 0.9, x0, y0, w, h),
        });
        assert(out.state == State::OCCLUDED);
        assert(out.last_id != 2);

        out = lc.update(80.0, {
            mk(1, "person", 0.9, x0, y0, w, h),
            mk(2, "person", 0.9, x0, y0, w, h),
        });
        assert(out.state == State::OCCLUDED);
        assert(out.last_id != 2);

        out = lc.update(120.0, {mk(1, "person", 0.9, x0, y0, w, h)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 1);
    }

    // 6) class flicker on the SAME tracker id: the locked target's detections alternate labels
    //    person/chair at the same box -> stays CONFIRMED every frame.
    //    On-board fix round 5 (Ruling 22) changes BOTH halves of what this case asserts:
    //      - eligibility: a different-class candidate is now admitted ONLY because it carries the
    //        core's own last id (Ruling 22.1). Same id 9 throughout, so every frame is still taken --
    //        this case is precisely the "the detector re-labelled the same object" evidence the class
    //        gate is built to keep. Case 6b below is its counterpart: same flicker, NEW id, refused.
    //      - published class: `Output.cls` now follows the last associated observation (Ruling 22.3),
    //        so it reads "chair" on the chair frames instead of the frozen locked "person". Run 10e is
    //        why: the old behaviour published `cell phone` for twelve minutes of suitcase. The LOCKED
    //        class is still "person" and is what the gate tests -- proven by 6b, which is refused for
    //        being a non-"person" NEW id even though the core's last published cls was "chair".
    {
        LockCore lc;
        double x0 = 200, y0 = 200, w = 60, h = 120;
        lc.lock(mk(9, "person", 0.9, x0, y0, w, h), 0.0);
        assert(lc.last().cls == "person");   // the click's own class seeds the published one
        const char* labels[] = {"person", "chair", "person", "chair", "chair"};
        for (int f = 1; f <= 5; ++f) {
            Output out = lc.update(f * 40.0, {mk(9, labels[f - 1], 0.9, x0, y0, w, h)});
            assert(out.state == State::CONFIRMED);
            assert(out.cls == labels[f - 1]);
        }

        // 6b) Ruling 22.1, the counterpart: the very same box, same class flicker, but a NEW tracker
        //     id -- refused, in gate or not, because the class differs from the LOCKED class and the
        //     tracker offers no continuity evidence. The core coasts (OCCLUDED at 40 ms of age)
        //     rather than following it, and the published cls is unchanged (no association happened).
        //     A same-class new id at the same place is still taken on the next frame, so this is the
        //     class gate refusing, not the position/size gates.
        Output refused = lc.update(240.0, {mk(77, "chair", 0.95, x0, y0, w, h)});
        assert(refused.state == State::OCCLUDED);
        assert(!refused.observation_valid);
        assert(refused.last_id == 9);
        assert(refused.cls == "chair");      // still the last ASSOCIATED observation (frame 5)
        Output taken = lc.update(280.0, {mk(78, "person", 0.95, x0, y0, w, h)});
        assert(taken.state == State::CONFIRMED);
        assert(taken.last_id == 78);
        assert(taken.cls == "person");
    }

    // 7) fast mover: constant velocity 20 px/frame at 25 fps (500 px/s, the brief's example) ->
    //    associated from the FIRST frame after lock() and every frame thereafter (predictions stay
    //    within the gate); a 3-frame gap; the returning detection at the extrapolated position is
    //    associated, and the frozen box during the gap did NOT move.
    //    Fix round 1 (Ruling 1): the previous process-noise model (a small additive q_pos, velocity
    //    assumed exactly zero at lock()) could not gate this in at all -- the first-frame gate radius
    //    was only ~17 px against a 20 px/frame displacement. With the WNA process model plus a large
    //    initial velocity uncertainty (p0_vel_std=400 px/s), the first-frame gate radius is ~50 px
    //    (see the Params comment in lock_core.hpp), comfortably covering this case: verified
    //    numerically, d2 on frame 1 is ~1.4 (vs. gate_sigma^2=9), converging to d2 ~= 0 by frame 6 and
    //    staying there through the gap and reacquisition (d2 ~= 0.0000 on return).
    //    Fix round 2 (Ruling 2): q_acc_std lowered 1500 -> 600 (see Params comment) and gate_max_px=300
    //    introduced to cap gating on long coasts; neither changes this case's outcome -- the first-few-
    //    -frame variance here (tens to a few hundred px^2) is still far below the cap, and a lower
    //    q_acc_std makes velocity converge just as well with less injected noise (re-verified
    //    numerically: same qualitative d2 trend, still comfortably in gate throughout).
    {
        LockCore lc;
        double dtMs = 40.0;
        double x0 = 100, y0 = 300, w = 60, h = 60;
        double vx = 20.0 / dtMs; // px/ms (500 px/s)
        lc.lock(mk(4, "person", 0.9, x0, y0, w, h), 0.0);
        Output steady;
        for (int f = 1; f <= 8; ++f) {
            double t = f * dtMs;
            double x = x0 + vx * t;
            steady = lc.update(t, {mk(4, "person", 0.9, x, y0, w, h)});
            assert(steady.state == State::CONFIRMED); // true from f=1 -- see fix note above
        }
        Box frozen = *steady.box;

        // 3-frame gap: empty dets at frames 9, 10, 11
        for (int f = 9; f <= 11; ++f) {
            Output gapOut = lc.update(f * dtMs, {});
            assert(gapOut.state == State::OCCLUDED);
            assert(gapOut.box.has_value());
            assert(boxEq(*gapOut.box, frozen)); // frozen box did not move during the gap
        }

        // returning detection at the true extrapolated position (frame 12)
        double t12 = 12 * dtMs;
        double xTrue = x0 + vx * t12;
        Output back = lc.update(t12, {mk(4, "person", 0.9, xTrue, y0, w, h)});
        assert(back.state == State::CONFIRMED);
        assert(back.last_id == 4);
    }

    // 7b) negative case (Ruling 1, re-verified round 2): a candidate 300 px away on the first frame
    //     after lock() is NOT associated -- it is well outside the ~50 px first-post-lock gate radius
    //     documented on Params in lock_core.hpp (still ~50 px after round 2's q_acc_std=600, since that
    //     term contributes only ~0.2 px^2 out of ~281 px^2 at dt=40ms -- p0_vel_std dominates). Also
    //     nowhere near gate_max_px=300's cap (raw var here is a few hundred px^2, cap is 10000 px^2 --
    //     the cap only matters after long uncorrected coasts, see case 3d). Prints the OBSERVED gate
    //     radius (gate_sigma * uncertainty_px, read back from the real Output on this no-win frame,
    //     where uncertainty_px reflects the post-predict/pre-correction, uncapped variance) so it can
    //     be compared against the hand-derived ~50 px formula value in the fix report.
    {
        LockCore lc;
        double x0 = 600, y0 = 340, w = 80, h = 160;
        lc.lock(mk(6, "person", 0.9, x0, y0, w, h), 0.0);
        Output out = lc.update(40.0, {mk(70, "person", 0.9, x0 + 300.0, y0, w, h)});
        assert(out.state == State::OCCLUDED); // not associated -> no-win transition (obs_age 40 <= 500)
        assert(!out.observation_valid);
        assert(out.last_id != 70);

        double observedGateRadius = Params{}.gate_sigma * out.uncertainty_px;
        std::cout << "case 7b: observed gate radius after 1st prediction (dt=40ms) = "
                   << observedGateRadius << " px (uncertainty_px=" << out.uncertainty_px << ")\n";
        // Fix round 4 (M7): assert it, don't just print it. 3*sqrt(25 + 0.0016*160000 +
        // 360000*2.56e-6/4) = 3*sqrt(281.2304) = 50.31 px -- derived from the shipped Params
        // constants (Ruling 1's headline number), not a bench measurement. See case 15.
        assert(std::fabs(observedGateRadius - 50.31) < 1.0);
    }

    // 8) the published box never leaves the frame: lock near the edge with a rightward velocity ->
    //    the frozen box published during a long gap is exactly the last confirmed one (still inside
    //    the frame), regardless of how the internal (unpublished, never-clamped-to-the-frame)
    //    prediction moves in the meantime -- update() never derives the OCCLUDED/REACQUIRING box from
    //    the live prediction, only from the stored last-confirmed box, so this holds unconditionally.
    {
        Params p;
        LockCore lc(p);
        double dtMs = 40.0;
        double x0 = 1150, y0 = 300, w = 70, h = 100; // right edge of a 1280-wide frame
        double vx = 3.0 / dtMs;
        lc.lock(mk(5, "person", 0.9, x0, y0, w, h), 0.0);
        Output steady;
        for (int f = 1; f <= 3; ++f) {
            double t = f * dtMs;
            double x = x0 + vx * t; // stays inside the frame during these steady frames
            steady = lc.update(t, {mk(5, "person", 0.9, x, y0, w, h)});
        }
        assert(steady.state == State::CONFIRMED);
        Box lastConfirmed = *steady.box;
        assert(lastConfirmed.x + lastConfirmed.w <= static_cast<double>(p.frame_w));

        double lastConfirmedTs = 3 * dtMs;
        // Long empty gap: the published frozen box must still be exactly lastConfirmed no matter how
        // far the internal prediction has moved.
        Output gapOut = lc.update(lastConfirmedTs + 2000.0, {});
        assert(gapOut.state == State::REACQUIRING);
        assert(gapOut.box.has_value());
        assert(boxEq(*gapOut.box, lastConfirmed));
        assert(gapOut.box->x + gapOut.box->w <= static_cast<double>(p.frame_w));
    }

    // 9) state_name strings.
    {
        assert(std::string(state_name(State::NONE)) == "none");
        assert(std::string(state_name(State::CONFIRMED)) == "confirmed");
        assert(std::string(state_name(State::OCCLUDED)) == "occluded");
        assert(std::string(state_name(State::REACQUIRING)) == "reacquiring");
        assert(std::string(state_name(State::LOST)) == "lost");
    }

    // 10) frame-rate independence: the same scenario sampled at 25 fps (40 ms) and 30 fps (33.33... ms)
    //     must produce the same sequence of state transitions at the same wall-clock times (ms),
    //     agreeing within one frame interval of the slower rate (40 ms). The scenario: lock() at t=0,
    //     then no detections at all, so obs_age_ms == ts_ms exactly for both rates from the same
    //     instant -- isolating per-transition tick quantisation (< one frame interval of that rate) as
    //     the only source of divergence. (An earlier version of this test fed a few "steady" confirmed
    //     frames before the gap; that made the *last confirmed timestamp itself* land on different
    //     ticks for the two rates -- up to one 30 fps frame apart -- and that extra, compounding offset
    //     pushed the LOST transition times ~53 ms apart, over the 40 ms budget. Anchoring both runs on
    //     lock()'s t=0 removes that confound.) Runs past expire_ms(10000) so OCCLUDED -> REACQUIRING ->
    //     LOST are all exercised, driven purely by wall-clock ms, not frame counts.
    {
        auto runScenario = [](double dtMs) {
            struct Transition { State state; double ts; };
            std::vector<Transition> transitions;

            LockCore lc;
            double x0 = 640, y0 = 360, w = 80, h = 160;
            lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
            State prev = State::CONFIRMED;

            double t = 0.0;
            const double totalRun = 11000.0; // past expire_ms(10000) so LOST is reached
            while (t < totalRun) {
                t += dtMs;
                Output out = lc.update(t, {}); // no detections after lock() at all
                if (out.state != prev) {
                    transitions.push_back({out.state, t});
                    prev = out.state;
                }
            }
            return transitions;
        };

        auto t25 = runScenario(40.0);
        auto t30 = runScenario(100.0 / 3.0);

        assert(t25.size() == t30.size());
        for (size_t i = 0; i < t25.size(); ++i) {
            assert(t25[i].state == t30[i].state);
            assert(std::fabs(t25[i].ts - t30[i].ts) <= 40.0); // one frame interval of the slower (25 fps) rate
        }
        // sanity: the scenario actually exercises OCCLUDED -> REACQUIRING -> LOST
        bool sawOccluded = false, sawReacquiring = false, sawLost = false;
        for (auto& tr : t25) {
            if (tr.state == State::OCCLUDED) sawOccluded = true;
            if (tr.state == State::REACQUIRING) sawReacquiring = true;
            if (tr.state == State::LOST) sawLost = true;
        }
        assert(sawOccluded && sawReacquiring && sawLost);
    }

    // 10b) fix round 3 instruction 1 (review coverage gap): case 10 above never feeds a detection
    //      after lock(), so it only exercises timer bookkeeping -- it can't catch a bug that only shows
    //      up once real Kalman gating/scoring is in the loop every frame. Same idea, now with a moving,
    //      continuously-detected target: a 20 px/frame-at-25fps mover (500 px/s), starting at the lock
    //      box, with a 120 ms gap at t=1.0s (no detections for any tick in [1000, 1120) ms) and the
    //      detection resuming at the true extrapolated position, sampled at 25 fps and 30 fps through
    //      fresh LockCores with identical (default) Params.
    {
        struct MotionRun {
            std::vector<std::pair<State, double>> transitions; // first-occurrence transitions only
            Box boxAt2s{};
        };

        auto runMotion = [](double dtMs) {
            MotionRun r;
            LockCore lc;
            double x0 = 200.0, y0 = 300.0, w = 60.0, h = 60.0;
            double vx = 500.0; // px/s (20 px/frame at 25 fps)
            lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
            State prev = State::CONFIRMED;

            int nFrames = static_cast<int>(std::lround(2000.0 / dtMs)); // -> exactly t=2000ms on frame nFrames
            for (int f = 1; f <= nFrames; ++f) {
                double t = f * dtMs;
                bool inGap = t >= 1000.0 && t < 1120.0; // 120 ms gap starting at t=1.0s
                std::vector<Obs> dets;
                if (!inGap) {
                    double cx = x0 + w / 2.0 + vx * (t / 1000.0); // continuous motion, incl. through the gap
                    dets.push_back(mk(1, "person", 0.9, cx - w / 2.0, y0, w, h));
                }
                Output out = lc.update(t, dets);

                // (a) CONFIRMED on every frame with a detection; (b) OCCLUDED during the gap.
                assert(out.state == (inGap ? State::OCCLUDED : State::CONFIRMED));

                if (out.state != prev) { r.transitions.push_back({out.state, t}); prev = out.state; }
                if (f == nFrames) { assert(out.box.has_value()); r.boxAt2s = *out.box; }
            }
            return r;
        };

        MotionRun r25 = runMotion(40.0);
        MotionRun r30 = runMotion(100.0 / 3.0);

        // (c) transition timestamps (CONFIRMED->OCCLUDED and back) agree within one slow-frame interval.
        assert(r25.transitions.size() == 2 && r30.transitions.size() == 2); // -> OCCLUDED, then -> CONFIRMED
        assert(r25.transitions[0].first == State::OCCLUDED && r30.transitions[0].first == State::OCCLUDED);
        assert(r25.transitions[1].first == State::CONFIRMED && r30.transitions[1].first == State::CONFIRMED);
        assert(std::fabs(r25.transitions[0].second - r30.transitions[0].second) <= 40.0);
        assert(std::fabs(r25.transitions[1].second - r30.transitions[1].second) <= 40.0);

        // (d) published boxes at the same wall-clock instant (t=2.0s) agree within 5 px.
        assert(std::fabs(r25.boxAt2s.x - r30.boxAt2s.x) <= 5.0);
        assert(std::fabs(r25.boxAt2s.y - r30.boxAt2s.y) <= 5.0);
    }

    // 11) fix round 3 instruction 2: hit the state-machine's three time boundaries exactly and one ms
    //     past each, in one test. Each sub-case uses its own fresh LockCore locked at ts_ms=0 so an
    //     earlier sub-case's outcome (in particular the +3500 win, which resets obs_age to 0) can't
    //     disturb a later boundary's timing -- the four no-detection checks are still chained on a
    //     single instance (none of them ever wins, so obs_age stays anchored to the original lock()
    //     throughout that chain, exactly as it would in a real never-reacquired run).
    {
        double x0 = 500.0, y0 = 300.0, w = 100.0, h = 200.0;
        Obs target = mk(1, "person", 0.9, x0, y0, w, h);

        // +500 (still OCCLUDED, obs_age <= occlusion_ms) -> +501 (REACQUIRING) -> +10000 (still
        // REACQUIRING, identity_locked, obs_age <= expire_ms) -> +10001 (LOST). No detections at all.
        {
            LockCore lc;
            lc.lock(target, 0.0);

            Output at500 = lc.update(500.0, {});
            assert(at500.state == State::OCCLUDED);
            assert(at500.identity_locked);

            Output at501 = lc.update(501.0, {});
            assert(at501.state == State::REACQUIRING);
            assert(at501.identity_locked);

            Output at10000 = lc.update(10000.0, {});
            assert(at10000.state == State::REACQUIRING);
            assert(at10000.identity_locked);

            Output at10001 = lc.update(10001.0, {});
            assert(at10001.state == State::LOST);
            assert(!at10001.box.has_value());
            assert(!at10001.identity_locked);
        }

        // +10000 (occlusion_ms + reacquire_ms = 500 + 9500 since on-board fix round 4 / Ruling 20c,
        // and simultaneously expire_ms -- the widened window now closes exactly at expiry): a
        // class-matching, size-consistent candidate 400 px away IS associated on the last millisecond
        // the lock is alive (out of the capped gate -- d^2 = 400^2/10100 = 15.84 > 9 -- but eligible
        // via the widened branch). Under the pre-round-4 default this instant was 6.5 s past the
        // widened window and nothing could be taken; run 7's 6-second hide is exactly that failure.
        // Round 10 (Ruling 32e): id 90 is a new id at obs_age 10000 ms, which is past the SHIPPED
        // `widened_new_id_max_age_ms` (5000) -- under the shipped params it would be refused for that
        // reason, and the different-id half of the widened window therefore closes at 5 s, well
        // before `reacquire_ms` does. That is real and intended (see lock_core.hpp), but it is a
        // DIFFERENT mechanism from the one this sub-case pins, which is Ruling 20c's window length.
        // So the ceiling is raised explicitly here to keep this case measuring the window.
        {
            Params p11;
            p11.widened_new_id_max_age_ms = 10000.0;
            LockCore lc(p11);
            lc.lock(target, 0.0);
            Output at10000 = lc.update(10000.0, {mkb(90, "person", 0.9, x0 + 400.0, y0, w, h, 500.0)});
            assert(at10000.state == State::CONFIRMED);
            assert(at10000.observation_valid);
            assert(at10000.last_id == 90);
            // score = 0.25*0.9 + 0.35*exp(-15.84/2) + 0.15 + 0.15
            // = 0.225 + 0.000129 + 0.30 = 0.5251, clearing min_score_widened (0.40) by 0.125.
            assert(std::fabs(at10000.quality - 0.5251) < 1e-3);
            assert(at10000.quality >= *Params{}.min_score_widened);
        }

        // +10001 (one ms past expiry): the SAME candidate is NOT associated -- the lock is LOST and
        // LOST is terminal, so no candidate of any quality re-enters it without an explicit lock().
        // Two independent reasons say so: Ruling 29's stall check sets LOST before any association
        // is attempted, and Ruling 32(e) would refuse this out-of-gate new id at obs_age 10001 ms
        // anyway. The ceiling is raised as in the sub-case above so the FIRST of those is what this
        // case measures.
        {
            Params p11b;
            p11b.widened_new_id_max_age_ms = 20000.0;
            LockCore lc(p11b);
            lc.lock(target, 0.0);
            Output at10001 = lc.update(10001.0, {mkb(90, "person", 0.9, x0 + 400.0, y0, w, h, 500.0)});
            assert(at10001.state == State::LOST);
            assert(!at10001.observation_valid);
            assert(at10001.last_id != 90);
        }

        // On-board fix round 4 (Ruling 20b): the IN-GATE score floor is the band's floor, not a
        // fixed one -- `min_score` (0.5) while CONFIRMED/OCCLUDED, `min_score_widened` (0.40) while
        // REACQUIRING. The same candidate is refused in one band and taken in the other, and nothing
        // about it changes between the two runs except how long the target has been missing.
        //   candidate: new id 91, conf 0.1, exact size, 150 px away. In both runs the position
        //   variance is past the cap, so Sx = min(P, cap) + r_pos_frac-scaled R = 10000 + 100 and
        //   d^2 = 150^2/10100 = 2.227723 (in gate, <= 9). Score
        //   = 0.25*0.1 + 0.35*exp(-1.113861) + 0.15*1 + 0.15*1 + 0
        //   = 0.025 + 0.114901 + 0.15 + 0.15 = 0.439901 -- under min_score, over min_score_widened.
        // Run 7's 6-second hide is this shape: the owner re-emerged 110-150 px from the frozen box at
        // conf 0.27-0.35, in gate, scoring ~0.45, and was refused frame after frame until expiry.
        {
            LockCore lc;
            lc.lock(target, 0.0);
            Output occluded = lc.update(400.0, {mk(91, "person", 0.1, x0 + 150.0, y0, w, h)});
            assert(occluded.state == State::OCCLUDED);          // obs_age 400 <= occlusion_ms 500
            assert(!occluded.observation_valid);
            assert(occluded.last_id != 91);
        }
        {
            LockCore lc;
            lc.lock(target, 0.0);
            Output reacq = lc.update(1000.0, {mk(91, "person", 0.1, x0 + 150.0, y0, w, h)});
            assert(reacq.state == State::CONFIRMED);            // obs_age 1000 -> REACQUIRING band
            assert(reacq.last_id == 91);
            assert(std::fabs(reacq.quality - 0.439901) < 1e-3);
            assert(reacq.quality < Params{}.min_score);
            assert(reacq.quality >= *Params{}.min_score_widened);
        }
    }

    // 12) fix round 4 (final-fix wave, I3 / Ruling 11): TWO-STAGE association -- the in-gate pool is
    //     scored FIRST and, when it produces a winner, the out-of-gate (widened) pool is never
    //     consulted, so a far same-class object can no longer veto a good local match. This is the
    //     review's own probe, verbatim.
    //
    //     Setup: lock at t=0, then a single update() at t=1000 ms with no correction in between, so
    //     obs_age_ms = 1000 (> occlusion_ms 500, <= occlusion_ms+reacquire_ms 3500 -> REACQUIRING with
    //     the widened window OPEN -- the only band in which stage 2 runs at all). The raw position
    //     variance after that one (dt-clamped to 1 s) predict is
    //     25 + 1^2*400^2 + 600^2*1^4/4 = 25 + 160000 + 90000 = 250025 px^2, far past the gating cap
    //     (gate_max_px/gate_sigma)^2 = (300/3)^2 = 10000 px^2.
    //
    //     On-board fix round 3 (Ruling 19.1/19.3) re-derives every number in this case; the SHAPE is
    //     unchanged and that is what the case is for. With a 100x200 box the innovation covariance is
    //     now S = min(P, cap) + R with R box-scaled: r_pos_frac*w = 10 px -> Sx = 10000 + 100 = 10100
    //     (Sy = 10000 + 400 = 10400), and the gate_min_px floor (0.15*200 = 30 px -> 100 px^2) does
    //     not bind. The in-gate candidate carries the locked id, so same_id_gate_mult = 2 divides its
    //     d^2 by 4:
    //       d^2 = 200^2 / (10100*4) = 40000/40400 = 0.990099   (was 200^2/10000 = 4)
    //
    //     (a) that in-gate candidate alone (same tracker id, conf 0.9, exact size) ->
    //         score = 0.25*0.9 + 0.35*exp(-0.990099/2) + 0.15*1 + 0.15*1 + 0.10*1
    //               = 0.225 + 0.213339 + 0.15 + 0.15 + 0.10 = 0.838339 >= min_score 0.5 -> CONFIRMED.
    //     (b) the SAME frame plus a conf-0.95, same-class, size-matched stranger 700 px away (out of
    //         gate: d^2 = 700^2/10100 = 48.51 > 9, no same-id relaxation for it), whose own score is
    //         0.25*0.95 + 0.35*exp(-48.51/2) + 0.15 + 0.15 + 0 = 0.5375 -> STILL CONFIRMED on the
    //         local candidate. Under the pre-round-4 POOLED scoring the two were compared against each
    //         other and the frame read "ambiguous" -> REACQUIRING: the two-person room the person
    //         profile targets. The far candidate is now only ever looked at when the in-gate pool
    //         yields nothing at all.
    {
        double x0 = 500, y0 = 300, w = 100, h = 200;
        Obs target = mk(1, "person", 0.9, x0, y0, w, h);

        {   // (a) in-gate candidate alone
            LockCore lc;
            lc.lock(target, 0.0);
            Output out = lc.update(1000.0, {mk(1, "person", 0.9, x0 + 200.0, y0, w, h)});
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 1);
            assert(std::fabs(out.quality - 0.838339) < 1e-3);   // see the arithmetic above
        }
        {   // (b) the same in-gate candidate WITH a better-conf far stranger in the same frame
            LockCore lc;
            lc.lock(target, 0.0);
            Output out = lc.update(1000.0, {
                mk(1, "person", 0.9, x0 + 200.0, y0, w, h),     // in gate (relaxed: same id)
                mk(42, "person", 0.95, x0 + 700.0, y0, w, h),   // out of gate, higher conf
            });
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 1);
            assert(std::fabs(out.quality - 0.838339) < 1e-3);
        }
    }

    // 12b) fix round 4 (I3 / Ruling 11), the other half: an AMBIGUOUS in-gate pool stops the frame --
    //      the out-of-gate pool is NOT consulted, even though it holds a candidate that would win it
    //      outright. Same t=1000 ms REACQUIRING/widened setup as case 12.
    //      On-board fix round 3 (Ruling 19.3) re-derives the numbers and moves B from 150 px to
    //      140 px: with same_id_gate_mult = 2 relaxing A's motion term, A at 200 px and B at 150 px
    //      are no longer ambiguous (0.838339 >= 1.3*0.639901 = 0.831871 -- A wins outright, which is
    //      the ruling working as intended: tracker-verified id continuity IS a tie-breaker). Moving B
    //      6 px closer restores a genuine ambiguity and keeps this case testing what it was written
    //      to test -- that an ambiguous stage 1 does not fall through to stage 2.
    //        A: 200 px away, same id -> d^2 = 200^2/(10100*4) = 0.990099, conf 0.9
    //           = 0.225 + 0.35*exp(-0.495050) + 0.15 + 0.15 + 0.10 = 0.838339   (best)
    //        B: 140 px away, NEW id (no relaxation) -> d^2 = 140^2/10100 = 1.940594, conf 0.9
    //           = 0.225 + 0.35*exp(-0.970297) + 0.15 + 0.15 + 0 = 0.225 + 0.132640 + 0.30 = 0.657640
    //        0.838339 < 1.3 * 0.657640 = 0.854932 -> ambiguous -> no winner, stay REACQUIRING.
    //        C: 700 px away, conf 0.95, same class/size, new id -> 0.5375, alone in the out-of-gate
    //           pool and comfortably over min_score_widened (0.40 since round 3) -- if stage 2 ran
    //           after an ambiguous stage 1 it would take C and the lock would jump to a stranger on
    //           the far side of the frame. It must not run: assert the state and last_id are both
    //           unchanged.
    //      Round 10 (Ruling 32): C is given a birth timestamp after the lock (and its conf 0.95 and
    //      obs_age 1000 ms already clear (d)/(e)), so it is fully eligible out of gate and the ONLY
    //      thing keeping it out is the ambiguous stage 1 -- which is what this case measures.
    {
        double x0 = 500, y0 = 300, w = 100, h = 200;
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
        Output out = lc.update(1000.0, {
            mk(1, "person", 0.9, x0 + 200.0, y0, w, h),
            mk(77, "person", 0.9, x0 + 140.0, y0, w, h),
            mkb(99, "person", 0.95, x0 + 700.0, y0, w, h, 500.0),
        });
        assert(out.state == State::REACQUIRING);
        assert(!out.observation_valid);
        assert(out.last_id == 1);     // never 99 -- the out-of-gate pool was not consulted
    }

    // 13) fix round 4 (M1): duplicate timestamp (dt = 0) must not double-predict. Two update() calls
    //     at the SAME ts with no detections must produce bit-identical output -- the second call's
    //     predict runs with dt = 0, which adds nothing to any variance (Q terms are all dt-powers).
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        Output a = lc.update(40.0, {});
        Output b = lc.update(40.0, {});
        assert(a.state == State::OCCLUDED && b.state == State::OCCLUDED);
        assert(a.uncertainty_px == b.uncertainty_px);   // bit-exact: no second predict happened
        assert(a.obs_age_ms == b.obs_age_ms);
        assert(a.box.has_value() && b.box.has_value() && boxEq(*a.box, *b.box));
    }

    // 13b) fix round 4 (M1): a BACKWARDS timestamp (an earlier frame arriving after a later one)
    //      must not manufacture confidence. obs_age_ms is clamped at 0, so quality can never exceed
    //      the no-observation ceiling of 0.5 (= max(0, 1 - 0/expire_ms) * 0.5) and certainly never
    //      exceeds the last CONFIRMED frame's own quality; the state is OCCLUDED at most (obs_age 0
    //      is inside occlusion_ms), never something better than the evidence supports.
    //      Before the clamp, obs_age went negative and quality read (1 + |age|/expire_ms)*0.5 > 0.5.
    {
        LockCore lc;
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 5000.0);
        Output confirmed = lc.update(5040.0, {mk(1, "person", 0.9, x0, y0, w, h)});
        assert(confirmed.state == State::CONFIRMED);

        Output backwards = lc.update(2800.0, {});   // 2240 ms EARLIER than the last confirmation
        assert(backwards.state == State::OCCLUDED);
        assert(backwards.obs_age_ms == 0.0);
        assert(backwards.quality <= 0.5);
        assert(backwards.quality <= confirmed.quality);
    }

    // 14) fix round 4 (M3): a degenerate lock box (w <= 1 or h <= 1) is rejected by lock() -- the size
    //     terms divide by the size filter's own w/h, so a zero/one-pixel box would make every size
    //     check NaN and nothing could ever associate again. The core must stay NONE instead.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 0, 200), 0.0);      // w = 0
        assert(lc.last().state == State::NONE);
        assert(!lc.last().identity_locked);
        Output out = lc.update(40.0, {mk(1, "person", 0.9, 500, 300, 0, 200)});
        assert(out.state == State::NONE);

        LockCore lc2;
        lc2.lock(mk(1, "person", 0.9, 500, 300, 100, 1.0), 0.0);   // h = 1 (the boundary)
        assert(lc2.last().state == State::NONE);

        LockCore lc3;                                              // just past it -> accepted
        lc3.lock(mk(1, "person", 0.9, 500, 300, 100, 1.5), 0.0);
        assert(lc3.last().state == State::CONFIRMED);
    }

    // 15) fix round 4 (M7): pin Ruling 1's headline number. The gate radius after the first
    //     prediction from a fresh lock() at dt = 40 ms is
    //     gate_sigma * sqrt(r_pos + dt^2*p0_vel_std^2 + q_acc_std^2*dt^4/4)
    //     = 3 * sqrt(25 + 0.0016*160000 + 360000*2.56e-6/4) = 3 * sqrt(281.2304) = 50.31 px.
    //     (Derived from the shipped Params constants, not a bench measurement.) Case 7b prints this
    //     value; here it is asserted.
    {
        LockCore lc;
        lc.lock(mk(6, "person", 0.9, 600, 340, 80, 160), 0.0);
        Output out = lc.update(40.0, {});
        double observedGateRadius = Params{}.gate_sigma * out.uncertainty_px;
        assert(std::fabs(observedGateRadius - 50.31) < 1.0);
    }

    // 15b) fix round 4 (M7): a stall longer than the dt clamp (1 s). One update() 5 s after lock()
    //      advances the filters by at most 1 s, so uncertainty_px is
    //      sqrt(25 + 1*160000 + 360000/4) = sqrt(250025) = 500.02 px, NOT the ~7756 px a true 5 s
    //      predict would give (sqrt(25 + 25*160000 + 360000*625/4)). obs_age_ms, by contrast, uses
    //      the true elapsed time (5000 ms) -- the documented asymmetry between the filters' clamp and
    //      the state machine's windows.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        Output out = lc.update(5000.0, {});
        assert(out.state == State::REACQUIRING);       // 5000 ms: past occlusion_ms, inside expire_ms
        assert(out.obs_age_ms == 5000.0);
        assert(std::fabs(out.uncertainty_px - 500.02) < 1.0);
    }

    // 15c) fix round 4 (M7): LOST is terminal but re-lockable -- an explicit lock() after LOST starts
    //      FRESH filters (uncertainty_px back to sqrt(r_pos) = 5 px, not the thousands of px the
    //      expired lock had grown to) and a new identity.
    {
        LockCore lc;
        lc.lock(mk(3, "person", 0.9, 300, 200, 50, 100), 0.0);
        Output lost = lc.update(10500.0, {});
        assert(lost.state == State::LOST);
        assert(lost.uncertainty_px > 100.0);           // the expired lock's own covariance

        assert(lost.epoch == 1);                       // still the first lock's generation
        lc.lock(mk(8, "person", 0.9, 700, 400, 50, 100), 10600.0);
        assert(lc.last().state == State::CONFIRMED);
        assert(lc.last().last_id == 8);
        assert(lc.last().epoch == 2);                  // a post-LOST re-lock is a new generation
        assert(std::fabs(lc.last().uncertainty_px - std::sqrt(Params{}.r_pos)) < 1e-9);
        Output next = lc.update(10640.0, {mk(8, "person", 0.9, 700, 400, 50, 100)});
        assert(next.state == State::CONFIRMED);
    }

    // 16) fix round 4 (I6/Ruling 14): the coasting prediction is clamped to the frame, so a target
    //     that walks OUT of frame and returns through the edge it left by is re-acquired by the LOCAL
    //     (in-gate) stage, on its own geometry -- not left to the widened stage's steep conf floor or
    //     to the underlying tracker having preserved the id.
    //
    //     Scenario: lock a person whose centre is at cx=990 moving right at 300 px/s, 20 confirmed
    //     frames at 25 fps (cx = 990 + 12 px/frame -> cx=1230 at t=800 ms, box 1180..1280, i.e. exactly
    //     at the right edge of the 1280-wide frame); then 49 frames (~2 s) with no detections at all;
    //     then a re-entry at that same edge with a NEW tracker id and conf 0.6.
    //
    //     Gate radius during the coast: the raw position variance after ~2 s is far past the gating cap
    //     (25 + 2^2*400^2 + ... >> (gate_max_px/gate_sigma)^2 = 10000), so the effective gating std is
    //     exactly gate_max_px/gate_sigma = 100 px and the gate radius is exactly gate_max_px = 300 px.
    //     WITH the clamp the predicted centre sits at the frame edge (1280) plus one frame of velocity
    //     (~12 px), so the re-entry at cx=1230 is ~62 px away: d^2 ~= 0.38, well in gate, and scores
    //     0.25*0.6 + 0.35*exp(-0.38/2) + 0.15*1 + 0.15*1 + 0 ~= 0.15 + 0.289 + 0.30 = 0.739 -> CONFIRMED.
    //     WITHOUT it the centre would be at 1230 + 300*2.04 = ~1842, i.e. 612 px away (d^2 ~= 37 > 9,
    //     out of gate), and the widened stage could not take it either: an out-of-gate candidate's
    //     motion term is ~0, so a new-id, same-class, size-matched conf-0.6 candidate scores only
    //     0.25*0.6 + 0.15 + 0.15 = 0.45 < min_score 0.5. The target would simply not be re-acquired.
    {
        Params p;
        LockCore lc(p);
        double dtMs = 40.0, y0 = 300, w = 100, h = 200;
        double cx0 = 990.0, vx = 300.0;   // px/s, heading for the right edge
        lc.lock(mk(4, "person", 0.9, cx0 - w / 2.0, y0, w, h), 0.0);
        Output steady;
        for (int f = 1; f <= 20; ++f) {
            double t = f * dtMs;
            double cx = cx0 + vx * (t / 1000.0);
            steady = lc.update(t, {mk(4, "person", 0.9, cx - w / 2.0, y0, w, h)});
            assert(steady.state == State::CONFIRMED);
        }
        assert(std::fabs(steady.box->x + steady.box->w - static_cast<double>(p.frame_w)) < 2.0); // at the edge

        // ~2 s fully out of frame: no detections at all.
        for (int f = 21; f <= 70; ++f) {
            Output gapOut = lc.update(f * dtMs, {});
            assert(gapOut.state == State::OCCLUDED || gapOut.state == State::REACQUIRING);
        }

        // Re-entry at the exit edge, NEW tracker id, conf 0.6.
        Output back = lc.update(71 * dtMs, {mk(77, "person", 0.6, 1180.0, y0, w, h)});
        assert(back.state == State::CONFIRMED);
        assert(back.last_id == 77);
        assert(back.quality > 0.45);   // > the widened path's own ceiling for this candidate (0.45)
    }

    // 17) fix round 4 (I2/Ruling 10): `epoch` distinguishes a NEW lock from tracker id churn ridden
    //     through. 0 before the first lock, +1 per successful lock(), never reset -- including across
    //     unlock() (which publishes the epoch of the lock it just ended) and a rejected degenerate
    //     lock() (which is not a lock at all).
    {
        LockCore lc;
        assert(lc.last().epoch == 0);

        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        assert(lc.last().epoch == 1);
        Output out = lc.update(40.0, {mk(1, "person", 0.9, 500, 300, 100, 200)});
        assert(out.epoch == 1);

        // id churn WITHIN one epoch: the same object renumbered by the tracker underneath.
        out = lc.update(80.0, {mk(555, "person", 0.9, 502, 300, 100, 200)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 555);
        assert(out.epoch == 1);       // same lock generation -- not a re-lock

        lc.unlock();
        assert(lc.last().state == State::NONE);
        assert(lc.last().epoch == 1); // the epoch of the lock just ended, not 0

        lc.lock(mk(1, "person", 0.9, 500, 300, 0.0, 200), 120.0);   // degenerate -> rejected
        assert(lc.last().epoch == 1);

        lc.lock(mk(9, "person", 0.9, 200, 200, 60, 120), 160.0);
        assert(lc.last().epoch == 2);
        assert(lc.update(200.0, {}).epoch == 2);
    }

    // 18) fix round 4 (I6/Ruling 14): `min_score_widened` is the widened (out-of-gate) stage's own
    //     floor, tunable independently of the local one (on-board fix round 3 / Ruling 19.4 moved its
    //     DEFAULT from "unset == min_score" to an explicit 0.40; a config may still clear it back to
    //     nullopt to track min_score).
    //     Out of gate the motion term is ~0, so the far, same-class, size-matched, NEW-id, conf-0.9
    //     candidate below scores 0.25*0.9 + 0.15 + 0.15 = 0.525 (+ ~1e-6 of motion term).
    {
        double x0 = 500, y0 = 300, w = 100, h = 200;
        Obs target = mk(2, "person", 0.9, x0, y0, w, h);

        // Round 10 (Ruling 32): every candidate below carries a NEW id, so each is given a birth
        // timestamp after the lock; their conf (0.9 / 0.9 / 0.3) and obs_age (1000/1000/400 ms) are
        // otherwise fine, except the third, which is IN GATE and exempt from Ruling 32 entirely. This
        // case is about the FLOOR; case 22 is about the new-id policy.
        {   // widened floor at its default (0.40 since round 3; 0.525 cleared the previous 0.5 too)
            LockCore lc;
            lc.lock(target, 0.0);
            Output out = lc.update(1000.0, {mkb(51, "person", 0.9, x0 + 500.0, y0, w, h, 500.0)});
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 51);
            assert(std::fabs(out.quality - 0.525) < 1e-3);
        }
        {   // raised to 0.6 -> the same 0.525 candidate is NOT taken
            Params p;
            p.min_score_widened = 0.6;
            LockCore lc(p);
            lc.lock(target, 0.0);
            Output out = lc.update(1000.0, {mkb(51, "person", 0.9, x0 + 500.0, y0, w, h, 500.0)});
            assert(out.state == State::REACQUIRING);
            assert(!out.observation_valid);
            assert(out.last_id != 51);
        }
        {   // ...and OUTSIDE the reacquiring band the IN-GATE stage still uses min_score (0.5), not
            // the raised widened floor: a candidate 100 px away with conf 0.3 and a NEW id (so no
            // round-3 same-id relaxation: d^2 = 100^2/Sx = 10000/10100 = 0.990099 against the round-3
            // innovation covariance Sx = min(P, cap) + r_pos_frac-scaled R = 10000 + 100) scores
            // 0.25*0.3 + 0.35*exp(-0.495050) + 0.15 + 0.15 = 0.075 + 0.213339 + 0.30 = 0.588339 --
            // over min_score, under min_score_widened -- and is taken.
            // **On-board fix round 4 (Ruling 20b) narrows where that is true**: in the REACQUIRING
            // band the in-gate pool uses `min_score_widened` too, so this sub-case now runs at
            // obs_age 400 ms (OCCLUDED). The position variance is already past the gating cap at
            // 400 ms (25 + 0.16*160000 + 360000*0.4^4/4 = 27929 > 10000), so Sx, d^2 and the score
            // are bit-identical to the 1000 ms version this used to be -- the ONLY thing that changed
            // is which band the frame is in. Case 11's last two sub-cases pin the other side.
            Params p;
            p.min_score_widened = 0.6;
            LockCore lc(p);
            lc.lock(target, 0.0);
            Output out = lc.update(400.0, {mk(52, "person", 0.3, x0 + 100.0, y0, w, h)});
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 52);
            assert(std::fabs(out.quality - 0.588339) < 1e-3);
        }
    }

    // 19) on-board fix round 1 (Ruling 16.2): the size gate is variance-aware, so the admitted
    //     deviation per dimension is `max(size_tol*ref, gate_sigma*sqrt(size_var + R_size))` rather
    //     than a fixed fraction of a possibly-stale reference.
    //     On-board fix round 3 (Ruling 19.2) makes BOTH noise terms in that formula relative to the
    //     reference, with the old absolute constants as floors:
    //       R_size = max(r_size, (r_size_frac*ref)^2)       -- 100 px^2 vs (0.15*ref)^2
    //       rate   = max(q_size, (q_size_frac*ref)^2) px^2/s -- 50 px^2/s vs (0.5*ref)^2
    //     so the tolerance now scales with the target instead of pinning every reference to the same
    //     ~42-56 px window. All derived from config constants, not measured. Ruling 19.3 then
    //     multiplies the tolerance by `same_id_gate_mult` (2.0) for a candidate carrying the locked
    //     id; (b)/(c) below are exactly that difference.
    //
    //     (a) a SMALL reference admits a plausible growth the ORIGINAL fixed gate rejected outright:
    //         a 29 px-wide lock and a 60 px-wide candidate 200 ms later is |60-29| = 31 px, which is
    //         31/29 = 1.07 > size_tol 0.5 (rejected before round 1). Round 3's tolerance for a 29 px
    //         reference at 200 ms: rate = max(50, (0.5*29)^2 = 210.25) = 210.25 px^2/s, so
    //         w_var = 100 + 210.25*0.2 = 142.05; R_size = max(100, (0.15*29)^2 = 18.9) = 100;
    //         tol = max(0.5*29 = 14.5, 3*sqrt(142.05 + 100) = 46.67) = 46.67 px (and 93.35 px with
    //         this candidate's same-id relaxation). 31 px is comfortably inside either.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.6, 600, 300, 29, 194), 0.0);
        Output out = lc.update(200.0, {mk(1, "person", 0.9, 590, 290, 60, 230)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 1);
    }
    //     (b) an ORDINARY reference seen through a NEW tracker id (no round-3 relaxation) keeps
    //         essentially the pre-round-3 window. For a 200 px reference at dt = 40 ms:
    //         rate = max(50, (0.5*200)^2 = 10000) = 10000 px^2/s -> w_var = 100 + 10000*0.04 = 500;
    //         R_size = max(100, (0.15*200)^2 = 900) = 900;
    //         tol = max(0.5*200 = 100, 3*sqrt(500 + 900) = 112.25) = 112.25 px.
    //         So 290 px is in (|90| <= 112.25 -> CONFIRMED) and 350 px is out (|150| > 112.25 -> the
    //         candidate is not eligible in either pool -> OCCLUDED), the same two outcomes this case
    //         asserted before round 3.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 200, 400), 0.0);
        assert(lc.update(40.0, {mk(99, "person", 0.9, 500, 300, 290, 400)}).state == State::CONFIRMED);

        LockCore lc2;
        lc2.lock(mk(1, "person", 0.9, 500, 300, 200, 400), 0.0);
        assert(lc2.update(40.0, {mk(99, "person", 0.9, 500, 300, 350, 400)}).state == State::OCCLUDED);
    }
    //     (c) on-board fix round 3 (Ruling 19.3): the SAME 350 px box carrying the LOCKED id is
    //         admitted, because the tracker's own frame-to-frame continuity relaxes the tolerance to
    //         2*112.25 = 224.5 px (|150| <= 224.5). It is a relaxation, not a bypass: at 450 px the
    //         deviation is |250| > 224.5 and the same-id candidate is rejected too.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 200, 400), 0.0);
        assert(lc.update(40.0, {mk(1, "person", 0.9, 500, 300, 350, 400)}).state == State::CONFIRMED);

        LockCore lc2;
        lc2.lock(mk(1, "person", 0.9, 500, 300, 200, 400), 0.0);
        assert(lc2.update(40.0, {mk(1, "person", 0.9, 500, 300, 450, 400)}).state == State::OCCLUDED);
    }

    // 19b) on-board fix round 1: the RUN 1 EVIDENCE SEQUENCE, replayed
    //      (bench/evidence/2026-09-04-lock-core/run1_walk_prefix.txt.gz, capture rows 81.64-82.64 s;
    //      the harness row and the mechanism are in bench/benchlog.md's "Run 1 ... edge-entry
    //      failure"). The resolver auto-acquired a 29x194 px, conf 0.17 SLIVER of a person still
    //      entering at the right edge (x=1251, x+w = 1280); as they walked in, their box grew
    //      56x220 -> 79x238 -> 97x255 -> 170x431 -> 201x563 -> 285x584 -> 293x713 within 0.8 s.
    //
    //      **Under round 1's model this sequence did NOT recover, and this case pinned that.** The
    //      first row was admitted by the size gate (|56-29| = 27 <= 42.4) but scored
    //      0.25*0.17 + 0.35*exp(-1.391/2) + 0.15*(1-min(1,27/29)) + 0.15 + 0.10 = 0.477, under
    //      min_score 0.5 -- the detector's own 0.17 confidence on a half-entered person, not the size
    //      gate, was what kept it out.
    //
    //      **On-board fix round 3 (Ruling 19.1/19.3) recovers it on the very first row**, and the
    //      assertion is flipped to record that. This candidate carries the LOCKED id, so
    //      same_id_gate_mult = 2 relaxes both its gate and the normaliser of its size score term.
    //      Arithmetic at the first row (t = 33 ms, ref 29x194, candidate 56x220):
    //        gate:  P_x after the predict = 25 + 0.033^2*400^2 + 600^2*0.033^4/4 = 199.3 px^2;
    //               R_x = max(sqrt(25), 0.1*29)^2 = 25; S_x = 224.3 (the gate_min floor,
    //               (0.15*194/3)^2 = 94.1, does not bind); with mult^2 = 4, d^2 = 0.2267 -- in gate.
    //        size:  rate_w = max(50, (0.5*29)^2) = 210.25 px^2/s -> w_var = 100 + 6.9 = 106.9;
    //               R_size_w = max(100, (0.15*29)^2) = 100; tol = max(14.5, 3*sqrt(206.9)) = 43.16,
    //               x2 = 86.3 for the same id; |56-29| = 27 is inside.
    //        score: 0.25*0.17 + 0.35*exp(-0.11333) + 0.15*(1 - 27/(29*2)) + 0.15 + 0.10 = 0.6852
    //               -- over min_score 0.5, where round 1's 0.477 was not. The w_size term is the
    //               single biggest change: judged against a doubled reference the 27 px deviation
    //               costs 0.070 instead of 0.140.
    //      This does NOT make the run-1 capture a good outcome: locking onto a conf-0.17 edge sliver
    //      is still wrong, and it is still prevented upstream by Ruling 16.1's auto-acquire gate
    //      (tests/test_lock.cpp case 6b -- conf 0.17 < 0.5 AND the box is hard against the right
    //      edge). What round 3 changes is that a lock which somehow DID start on a bad reference now
    //      recovers from it instead of decaying to LOST.
    {
        struct Row { double t, x, y, w, h, conf; };
        const Row rows[] = {                       // the capture's own values
            {33,  1225, 357,  56, 220, 0.17}, {67,  1204, 339,  79, 238, 0.21},
            {167, 1185, 324,  97, 255, 0.20}, {267, 1111, 238, 170, 431, 0.16},
            {400, 1074,  14, 201, 563, 0.29}, {533, 1003,  -3, 285, 584, 0.75},
            {767,  982,   2, 293, 713, 0.80}, {867,  982,   2, 293, 713, 0.80},
            {967,  974,   3, 300, 717, 0.75},
        };
        LockCore lc;
        lc.lock(mk(1, "person", 0.17, 1251, 381, 29, 194), 0.0);
        double firstConfirmedT = -1.0, refAfterThirdRow = 0.0;
        int confirmedRows = 0;
        Output out;
        for (const auto& r : rows) {
            out = lc.update(r.t, {mk(1, "person", r.conf, r.x, r.y, r.w, r.h)});
            if (out.state == State::CONFIRMED) {
                ++confirmedRows;
                if (firstConfirmedT < 0.0) firstConfirmedT = r.t;
            }
            if (r.t == 167.0) refAfterThirdRow = out.ref_w;
        }
        assert(firstConfirmedT == 33.0);           // the FIRST row -- see the arithmetic above
        // On-board fix round 4 (Ruling 20a) changes what happens NEXT, and this is the case that
        // shows both halves of the rule on real capture rows. The first three rows clear the STRICT
        // size tolerance (|56-29| = 27, then |79-43| = 36, then |97-57| = 40, each against a strict
        // tolerance of 43-46 px that is itself growing as the reference does), so they correct BOTH
        // filters and the reference climbs 29 -> 42.95 -> 57.46 -> 79.25. The 170 px row does not
        // (|170-79.25| = 91 > the ~46 px strict tolerance) -- it is admitted only by the same-id
        // relaxation, so it corrects position and the reference STAYS at 79.25 for the rest of the
        // sequence. Rows 5-7 (201, 285, 293) fall outside even the doubled tolerance and are refused
        // outright (OCCLUDED); by rows 8-9 the size variance has grown enough that the doubled
        // tolerance covers them again and the lock re-confirms on position. Six CONFIRMED rows, and a
        // reference that never learned the growing box.
        assert(confirmedRows == 6);
        assert(std::fabs(refAfterThirdRow - 79.25) < 0.05);
        assert(std::fabs(out.ref_w - refAfterThirdRow) < 1e-9);   // frozen from the 4th row onwards
        assert(out.state == State::CONFIRMED);
        assert(out.obs_age_ms == 0.0);
        // The honest cost of Ruling 20a, recorded rather than hidden: a reference that is too SMALL
        // can no longer grow through relaxation-only matches either, so this sequence follows the
        // owner without ever learning she is 300 px wide. That is the deliberate trade -- run 7 shows
        // the opposite error (learning a transiently-shrunken box) costs a whole 6-second occlusion,
        // and this one is prevented upstream by Ruling 16.1's auto-acquire gate.
    }

    // 19c) the same first row of 19b with a healthy confidence: identical box, so the ONLY difference
    //      is the score floor. It is CONFIRMED -- which was, under round 1, the direct proof that the
    //      variance-aware size gate admitted a 27 px deviation from a 29 px reference (the original
    //      fixed gate's limit was 0.5*29 = 14.5 px, so the box could not even be scored). Since
    //      round 3, 19b itself confirms on this row at the capture's real 0.17 confidence, so this
    //      case is now the CONTROL for it: same geometry, higher conf, still CONFIRMED, proving 19b's
    //      recovery is not an artefact of one marginal score.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.17, 1251, 381, 29, 194), 0.0);
        Output out = lc.update(33.0, {mk(1, "person", 0.9, 1225, 357, 56, 220)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 1);
    }

    // 20) on-board fix round 4 (Ruling 20a): a candidate admitted ONLY by the same-id relaxation
    //     corrects POSITION but not SIZE. Run 7's geometry, at the board's real 30 fps cadence
    //     (33.33 ms; the SSE capture is sampled at 10 Hz, but the core runs per frame and the size
    //     variance between frames is what decides this test -- see (a1)'s arithmetic).
    //
    //     (a1) Lock the owner's full body, 155x625, at the place the chair-back head boxes appear
    //          (x=440, y=40). After six steady frames feed the capture's own two head boxes, same
    //          tracker id 28, 33 ms apart: 276x159 at (421, 2) and 152x129 at (495, -3).
    //          Strict tolerances at the first of them (all from the shipped constants):
    //            width  rate = max(50, (0.5*155)^2) = 6006.25 px^2/s, R = max(100, (0.15*155)^2)
    //                   = 540.56 px^2; the steady-state variance under 33 ms correction is ~244 px^2,
    //                   +200 for this frame's predict -> tol = max(0.5*155, 3*sqrt(444 + 540.56))
    //                   = 94.1 px against |276-155| = 121 px -> STRICT FAIL (relaxed: 188.2 px, pass)
    //            height rate = max(50, (0.5*625)^2) = 97656.25 px^2/s, R = max(100, (0.15*625)^2)
    //                   = 8789.06 px^2; steady ~3962 px^2, +3252 -> tol = max(312.5,
    //                   3*sqrt(7214 + 8789)) = 379.5 px against |159-625| = 466 px -> STRICT FAIL
    //          So both frames are relaxation-only: the core stays CONFIRMED and its published box
    //          keeps following in POSITION, but the size reference stays exactly 155x625 -- which is
    //          the whole point. (Because the size filter is never corrected, its variance keeps
    //          growing, so the second head box is relaxation-only too rather than sneaking in on a
    //          widened tolerance.)
    {
        const double dt = 100.0 / 3.0;   // 30 fps
        LockCore lc;
        lc.lock(mk(28, "person", 0.8, 440, 40, 155, 625), 0.0);
        double t = 0.0;
        for (int f = 1; f <= 6; ++f) {
            t = f * dt;
            Output steady = lc.update(t, {mk(28, "person", 0.8, 440, 40, 155, 625)});
            assert(steady.state == State::CONFIRMED);
        }
        struct Row { double x, y, w, h, conf; };
        const Row heads[] = {{421, 2, 276, 159, 0.54}, {495, -3, 152, 129, 0.50}};
        double prevBoxX = lc.last().box->x;
        for (const auto& r : heads) {
            t += dt;
            Output out = lc.update(t, {mk(28, "person", r.conf, r.x, r.y, r.w, r.h)});
            assert(out.state == State::CONFIRMED);            // followed
            assert(out.last_id == 28);
            assert(std::fabs(out.ref_w - 155.0) < 1e-9);      // but NOT learned
            assert(std::fabs(out.ref_h - 625.0) < 1e-9);
            assert(out.box.has_value());
            assert(std::fabs(out.box->w - 155.0) < 1e-9);     // the published box keeps the reference
            assert(std::fabs(out.box->h - 625.0) < 1e-9);     //   size...
            assert(out.box->x != prevBoxX);                   //   ...while its position moves
            prevBoxX = out.box->x;
        }
    }
    //     (a2)/(a3) why it matters, as a pair of runs differing ONLY in the size reference. Six
    //     seconds later (REACQUIRING, widened window open to expiry since Ruling 20c) the owner
    //     re-emerges as a NEW id with a full-body 155x625 box, conf 0.3, 150 px from the prediction.
    //       - against the HEALTHY 155x625 reference the size gate passes exactly, d^2 = 150^2/10240.25
    //         = 2.197 (Sx = min(P, cap) + (0.1*155)^2), and the score is
    //         0.25*0.3 + 0.35*exp(-1.0985) + 0.15 + 0.15 = 0.075 + 0.116667 + 0.30 = 0.491667 --
    //         under min_score but over min_score_widened, so Ruling 20b takes it: CONFIRMED.
    //       - against a reference CONTAMINATED down to the head box (152x129 -- what 217fb04 actually
    //         learned in run 7) the height deviation is |625-129| = 496 px against a tolerance of
    //         max(0.5*129, 3*sqrt((100 + 4160.25*6) + 374.5)) = 478.5 px: the candidate is not
    //         eligible in either pool and the lock runs down to expiry with the owner in plain view.
    //     That is run 7's 6-second hide, reproduced in nine lines.
    {
        LockCore lc;                                   // healthy full-body reference
        lc.lock(mk(28, "person", 0.8, 493.5, 37.5, 155, 625), 0.0);
        Output out = lc.update(6000.0, {mk(33, "person", 0.3, 643.5, 37.5, 155, 625)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 33);
        assert(std::fabs(out.quality - 0.491667) < 1e-3);
        assert(out.quality < Params{}.min_score);            // only Ruling 20b lets this through
        assert(out.quality >= *Params{}.min_score_widened);
    }
    {
        LockCore lc;                                   // reference contaminated to the head box
        lc.lock(mk(28, "person", 0.8, 495, 285.5, 152, 129), 0.0);
        Output out = lc.update(6000.0, {mk(33, "person", 0.3, 643.5, 37.5, 155, 625)});
        assert(out.state == State::REACQUIRING);
        assert(!out.observation_valid);
        assert(out.last_id != 33);
        // Round 5 note: this candidate is now refused EARLIER, by Ruling 22.2's ratio cap
        // (625/129 = 4.84 > size_ratio_max 1.6 on a different id), before the tolerance arithmetic
        // above is ever reached. The arithmetic is still correct and still the round-4 mechanism this
        // case was written for; it is simply no longer the first thing to say no.
    }

    // 21) on-board fix round 5 (Ruling 22.2): the hard size-ratio cap on DIFFERENT-ID candidates.
    //     Geometry, hand-derived from the shipped constants (all three sub-cases share it):
    //       lock a 100x200 box at (500,300), id 1, then two empty update()s at t = 1000 and 2000 ms
    //       so the size filter's variance grows twice (dt is clamped to 1 s per predict step, which
    //       is why two calls and not one 2 s jump). q_size_frac 0.5 gives qSizeW = (0.5*100)^2 = 2500
    //       px^2/s, so m_w_var = r_size + 2*2500 = 100 + 5000 = 5100; rSizeW = max(100, (0.15*100)^2)
    //       = 225, so wTol = max(0.5*100, 3*sqrt(5100+225)) = max(50, 218.9) = 218.9 px. Likewise
    //       qSizeH = (0.5*200)^2 = 10000, m_h_var = 100 + 20000 = 20100, rSizeH = max(100, 30^2) =
    //       900, hTol = max(100, 3*sqrt(21000)) = 434.7 px.
    //     A 300x200 candidate at the same centre therefore has dw = 200 <= 218.9 and dh = 0: the
    //     round-4 variance-aware size gate ADMITS it, in gate (d^2 = 0), scoring
    //     0.25*0.9 + 0.35*exp(0) + 0.15*(1 - min(1, 200/100)) + 0.15 + 0 = 0.225 + 0.35 + 0 + 0.15
    //     = 0.725, well over both floors. Its width ratio is 3.0 -- run 10e's mechanism in miniature:
    //     "unseen for a couple of seconds" is not a licence to accept anything roughly over there.
    {
        // (a) cap DISABLED (size_ratio_max = 0) -- the pre-round-5 model, proving the case is only
        //     ever decided by the cap: the 300x200 new id IS taken, at exactly the derived score.
        Params p;
        p.size_ratio_max = 0.0;
        LockCore lc(p);
        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        lc.update(1000.0, {});
        Output out = lc.update(2000.0, {mk(55, "person", 0.9, 400, 300, 300, 200)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 55);
        assert(std::fabs(out.quality - 0.725) < 1e-3);
    }
    {
        // (b) the shipped cap (1.6): the identical candidate is refused -- not eligible in either
        //     pool, so the core coasts on REACQUIRING and keeps its own id.
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        lc.update(1000.0, {});
        Output out = lc.update(2000.0, {mk(55, "person", 0.9, 400, 300, 300, 200)});
        assert(out.state == State::REACQUIRING);
        assert(!out.observation_valid);
        assert(out.last_id == 1);
        // ...and a 150x200 candidate (ratio 1.50, inside the cap) at the same place IS taken on the
        // next frame, so what refused (a) was the ratio and nothing else.
        Output ok = lc.update(2040.0, {mk(56, "person", 0.9, 475, 300, 150, 200)});
        assert(ok.state == State::CONFIRMED);
        assert(ok.last_id == 56);
    }
    {
        // (c) the exemption: the SAME id is not ratio-capped, because run 5's owner tripling her box
        //     size walking toward the camera was same-id and Ruling 19.2 exists to follow exactly
        //     that. Identical 300x200 box, id 1 -> taken.
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        lc.update(1000.0, {});
        Output out = lc.update(2000.0, {mk(1, "person", 0.9, 400, 300, 300, 200)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 1);
    }

    // 22) on-board fix round 10 (Ruling 32): CONDITIONAL out-of-gate acceptance of a DIFFERENT
    //     tracker id. Round 9 (Ruling 28) refused all of them and cost two committed captures their
    //     recovery; round 10 asks instead for the evidence that exists without an appearance model.
    //     Base scenario throughout: lock a 100x200 person at (100,100) as id 1, coast to 600 ms with
    //     no detections (REACQUIRING, widened window open, last confirmed ts = 0), then offer a LONE
    //     same-class, size-identical candidate with a NEW id 900 px away at t=640 ms. Out of gate
    //     the motion term is ~0, so the score is 0.25*conf + 0.15(size) + 0.15(class).
    {
        Obs original = mk(1, "person", 0.9, 100, 100, 100, 200);

        {   // (d) the confidence floor. The reviewer's own probe: conf 0.41, born after the loss,
            //     lone -- score 0.4025, over min_score_widened (0.40), but 0.41 < the 0.5 floor, so
            //     it is refused and the core keeps coasting on its own id.
            LockCore lc;
            lc.lock(original, 0.0);
            for (int t = 40; t <= 600; t += 40) lc.update(t, {});
            Output out = lc.update(640.0, {mkb(2, "person", 0.41, 1000, 100, 100, 200, 620.0)});
            assert(out.state == State::REACQUIRING);
            assert(!out.observation_valid);
            assert(out.last_id == 1);
            assert(out.epoch == 1);
        }
        {   // ...the same candidate at conf 0.6 clears every condition and IS taken. This is the
            //     ACCEPTED RESIDUAL, documented rather than buried (lock_core.hpp's Params comment):
            //     an object first seen after the loss, alone, same class, at good confidence, inside
            //     the age ceiling, is indistinguishable from the target returning until F3 exists.
            //     Score = 0.25*0.6 + 0.15 + 0.15 = 0.45 >= min_score_widened 0.40.
            LockCore lc;
            lc.lock(original, 0.0);
            for (int t = 40; t <= 600; t += 40) lc.update(t, {});
            Output out = lc.update(640.0, {mkb(2, "person", 0.6, 1000, 100, 100, 200, 620.0)});
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 2);
            assert(std::fabs(out.quality - 0.45) < 1e-3);
        }
        {   // (b) THE LOAD-BEARING CONDITION -- the two-person swap, which no confidence floor can
            //     catch. id 2 is a second person who was in the room the whole time: it is a live
            //     observation on every frame while id 1 is CONFIRMED, so its first_seen_ms (0) is
            //     NOT after the last confirmed observation. id 1 then disappears and id 2 is the
            //     only candidate left, at conf 0.9 -- everything except (b) says take it. The core
            //     must refuse it on every frame and run all the way down to LOST at expiry, with
            //     last_id never becoming 2.
            LockCore lc;
            lc.lock(original, 0.0);
            // Both people present, id 1 confirmed. id 2 sits far away, out of any gate.
            for (int t = 40; t <= 400; t += 40)
                lc.update(t, {mkb(1, "person", 0.9, 100, 100, 100, 200, 0.0),
                               mkb(2, "person", 0.9, 1000, 100, 100, 200, 0.0)});
            assert(lc.last().state == State::CONFIRMED);
            assert(lc.last().last_id == 1);
            const double lastConfirmed = 400.0;
            // id 1 gone; id 2 remains, alone, strong, for the rest of the lock's life.
            bool everTookId2 = false, sawReacquiring = false;
            Output out;
            for (double t = 440.0; t <= lastConfirmed + 12000.0; t += 40.0) {
                out = lc.update(t, {mkb(2, "person", 0.9, 1000, 100, 100, 200, 0.0)});
                if (out.last_id == 2) everTookId2 = true;
                if (out.state == State::REACQUIRING) sawReacquiring = true;
            }
            assert(!everTookId2);                       // never transferred to the other person
            assert(sawReacquiring);                     // it did spend the whole band searching
            assert(out.state == State::LOST);           // and expired instead of taking the wrong one
            assert(out.last_id == 1);
        }
        {   // ...and the same scene with id 2 BORN 1 s after the loss is taken: identical geometry,
            //     identical confidence, the only difference is when the id first existed.
            LockCore lc;
            lc.lock(original, 0.0);
            for (int t = 40; t <= 400; t += 40)
                lc.update(t, {mkb(1, "person", 0.9, 100, 100, 100, 200, 0.0)});
            assert(lc.last().last_id == 1);
            Output out = lc.update(1400.0, {mkb(2, "person", 0.9, 1000, 100, 100, 200, 1400.0)});
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 2);
        }
        {   // (c) exclusivity: TWO born-after-loss candidates, both otherwise eligible -> both are
            //     dropped from the widened pool and nothing is taken. Out of gate the danger is one
            //     plausible stranger, so the bar is "only one candidate", not an ambiguity ratio.
            LockCore lc;
            lc.lock(original, 0.0);
            for (int t = 40; t <= 600; t += 40) lc.update(t, {});
            Output out = lc.update(640.0, {mkb(2, "person", 0.9, 1000, 100, 100, 200, 620.0),
                                            mkb(3, "person", 0.9, 1000, 400, 100, 200, 620.0)});
            assert(out.state == State::REACQUIRING);
            assert(!out.observation_valid);
            assert(out.last_id == 1);
        }
        {   // (e) the age ceiling, 7000 ms since round 10b (Ruling 33): the same lone,
            //     born-after-loss, conf-0.9 candidate offered at obs_age 8000 ms is refused, while
            //     the identical candidate at 6500 ms -- past the 5000 the ruling first specified,
            //     inside the shipped 7000 -- is taken. Only tracker-id continuity recovers a lock
            //     past the ceiling, and `expire_ms` (10000) still ends the lock 3 s later.
            LockCore lc;
            lc.lock(original, 0.0);
            Output late = lc.update(8000.0, {mkb(2, "person", 0.9, 1000, 100, 100, 200, 1000.0)});
            assert(late.state == State::REACQUIRING);
            assert(late.last_id == 1);

            LockCore lc2;
            lc2.lock(original, 0.0);
            Output ok = lc2.update(6500.0, {mkb(2, "person", 0.9, 1000, 100, 100, 200, 1000.0)});
            assert(ok.state == State::CONFIRMED);
            assert(ok.last_id == 2);
        }
        {   // The SAME-id out-of-gate candidate is exempt from (b)-(e): first_seen_ms -1 (unknown),
            //     conf 0.41 (under the floor). Tracker continuity is identity evidence; the other
            //     conditions exist only to substitute for the absence of it.
            LockCore lc;
            lc.lock(original, 0.0);
            for (int t = 40; t <= 600; t += 40) lc.update(t, {});
            Output out = lc.update(640.0, {mk(1, "person", 0.41, 1000, 100, 100, 200)});
            assert(out.state == State::CONFIRMED);
            assert(out.last_id == 1);
        }
        {   // widened_new_id = false is round 9's blanket refusal, kept as the strict reference:
            //     the conf-0.6 born-after-loss candidate of the second sub-case is refused.
            Params p;
            p.widened_new_id = false;
            LockCore lc(p);
            lc.lock(original, 0.0);
            for (int t = 40; t <= 600; t += 40) lc.update(t, {});
            Output out = lc.update(640.0, {mkb(2, "person", 0.6, 1000, 100, 100, 200, 620.0)});
            assert(out.state == State::REACQUIRING);
            assert(out.last_id == 1);
        }
    }

    // 22b) Ruling 32, the IN-GATE stage is untouched: a NEW id 150 px from the prediction (in gate),
    //      with first_seen_ms unknown (-1) and conf 0.1 -- i.e. failing (b) and (d) both -- is still
    //      taken, because none of Ruling 32's conditions apply in gate. Same geometry as case 11's
    //      Ruling-20b sub-case.
    {
        LockCore lc;
        lc.lock(mk(1, "person", 0.9, 500, 300, 100, 200), 0.0);
        Output out = lc.update(1000.0, {mk(91, "person", 0.1, 650, 300, 100, 200)});
        assert(out.state == State::CONFIRMED);
        assert(out.last_id == 91);
    }

    // 23) on-board fix round 9 (Ruling 29): STALL EXPIRY. The state machine used to advance only
    //     when update() was called, so a pipeline that stopped calling it (a stalled camera, a
    //     blocked sink) could hand the core a frame 11 s later and have it associate as though no
    //     time had passed -- the reviewer's second probe: lock at t=0, then a single update() at
    //     t=11000 with the target's own box. expire_ms is 10000, so that lock is dead; it must read
    //     LOST, not CONFIRMED, and re-taking it needs an explicit lock().
    {
        Obs original = mk(1, "person", 0.9, 100, 100, 100, 200);
        LockCore lc;
        lc.lock(original, 0.0);
        Output out = lc.update(11000.0, {original});
        assert(out.state == State::LOST);
        assert(!out.identity_locked);
        assert(!out.observation_valid);
        assert(!out.box.has_value());
        assert(out.epoch == 1);                 // an expiry, not a new lock generation
        assert(out.obs_age_ms == 11000.0);

        // Terminal: the same box on the next frame changes nothing...
        Output again = lc.update(11040.0, {original});
        assert(again.state == State::LOST);
        // ...until an explicit lock(), which starts a fresh generation.
        lc.lock(original, 11080.0);
        assert(lc.last().state == State::CONFIRMED);
        assert(lc.last().epoch == 2);
    }

    // 23b) Ruling 29 must not disturb the ordinary TICKED path. Same 30 fps cadence, detections all
    //      the way through: 11 s of continuous tracking stays CONFIRMED throughout (each frame's
    //      obs_age is one frame interval, nowhere near expire_ms), and the empty-detection tick chain
    //      still crosses at exactly the same instants case 11 pins (10000 REACQUIRING, 10001 LOST).
    {
        LockCore lc;
        const double dt = 100.0 / 3.0;
        double x0 = 500, y0 = 300, w = 100, h = 200;
        lc.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
        for (int f = 1; f <= 330; ++f) {       // 330 * 33.33 ms = 11 s
            Output out = lc.update(f * dt, {mk(1, "person", 0.9, x0, y0, w, h)});
            assert(out.state == State::CONFIRMED);
            assert(out.identity_locked);
        }
        LockCore lc2;
        lc2.lock(mk(1, "person", 0.9, x0, y0, w, h), 0.0);
        assert(lc2.update(10000.0, {}).state == State::REACQUIRING);
        assert(lc2.update(10001.0, {}).state == State::LOST);
    }

    std::cout << "lock_core ok\n";
    return 0;
}
