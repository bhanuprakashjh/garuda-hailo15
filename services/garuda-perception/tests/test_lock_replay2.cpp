#undef NDEBUG
#include "lock_replay_common.hpp"
#include <cassert>
#include <map>
#include <cmath>
#include <cstdio>
#include <iostream>

// Replay of run 7 — routine 2, "occlusion behind a chair" — through LockCore (on-board fix round 4,
// Ruling 20d). Fixture `tests/fixtures/lock_replay_routine2.json` is the rel. 170–205 s window of
// `bench/evidence/2026-09-04-lock-core/run7_routine2_occlusion.txt.gz` (348 rows / 35 s, `t_ms`
// re-based to 0 at rel. 170 s), extracted verbatim; see lock_replay_common.hpp for the shared loader
// and for why a 10 Hz replay is a weaker gate than the live 25–30 fps pipeline.
//
// The routine, in capture time (add 170 s for the numbers in bench/benchlog.md's "Run 7" entry):
//   t≈4.1 s   the owner (id 25, 148x495 full body) ducks behind the chair — a ~3 s hide. The engine
//             coasts id 25, then drops it; she re-emerges as a NEW id 28 at conf 0.36. The widened
//             stage takes it. **This half already passed on 217fb04.**
//   t≈11.0 s  a second, ~6 s hide. The engine keeps id 28 alive on the HEAD-ONLY box above the chair
//             back (155x625 -> 276x159 -> 152x129), the core follows it, and on 217fb04 it also
//             LEARNED that as the target's size; when the owner stood up again as ids 30/31/33 the
//             size gate rejected every one of them and the lock ran down to LOST at t≈21.7 s.
//             **This half is what round 4 fixes.**
//
// The three assertions are Ruling 20d's, with the anchors computed from the fixture rather than
// hard-coded, so a re-extraction of the window cannot silently move them.

using garuda::lock::LockCore;
using garuda::lock::Output;
using garuda::lock::State;
using lock_replay::Row;

namespace {

const int kLockId = 25;              // the full-body id the routine starts on
const int kHide1ReturnId = 28;       // the id she comes back as after the 3 s hide
const double kLockConf = 0.5;        // "the first live conf >= 0.5 row" (Ruling 20d)
const double kReturnConf = 0.25;     // the detector's confidence on a person standing back up
const double kHide2AfterMs = 12000;  // after the head-box sequence ends (capture rel. 181.7 s)

} // namespace

int main(int argc, char** argv) {
    assert(argc >= 2 && "usage: test_lock_replay2 <fixture.json>");
    std::vector<Row> rows = lock_replay::load(argv[1]);
    assert(rows.size() == 348 && "fixture is run 7's rel. 170-205 s window");

    // Round 10 (Ruling 32b): the per-id birth timestamps this fixture implies -- the first row
    // each id appears in. See lock_replay_common.hpp's firstSeenMs() for the rule and its two
    // caveats (both conservative: the reconstruction can never invent a born-after-loss id).
    const std::map<int, double> firstSeen = lock_replay::firstSeenMs(rows);

    // --- anchors, read off the fixture -------------------------------------------------------
    size_t lockRow = rows.size();
    const lock_replay::Track* lockTrack = nullptr;
    for (size_t i = 0; i < rows.size() && !lockTrack; ++i)
        for (const auto& t : rows[i].tracks)
            if (t.id == kLockId && !t.coasting && t.conf >= kLockConf) {
                lockRow = i; lockTrack = &t; break;
            }
    assert(lockTrack && "no live conf>=0.5 row for the locked id");

    // End of the 3 s hide: the first row where the return id is live at all.
    double hide1ReturnMs = -1.0;
    for (const auto& r : rows) {
        for (const auto& t : r.tracks)
            if (t.id == kHide1ReturnId && !t.coasting) { hide1ReturnMs = r.t_ms; break; }
        if (hide1ReturnMs >= 0.0) break;
    }
    assert(hide1ReturnMs >= 0.0);

    // End of the 6 s hide: the first row after the head-box sequence carrying a LIVE person box of
    // conf >= 0.25. (The head boxes themselves all belong to id 28 and stop by t_ms 11730; every row
    // between then and this anchor carries only coasting entries.)
    double hide2ReturnMs = -1.0;
    for (const auto& r : rows) {
        if (r.t_ms <= kHide2AfterMs) continue;
        for (const auto& t : r.tracks)
            if (!t.coasting && t.cls == "person" && t.conf >= kReturnConf) { hide2ReturnMs = r.t_ms; break; }
        if (hide2ReturnMs >= 0.0) break;
    }
    assert(hide2ReturnMs >= 0.0);

    // --- replay -------------------------------------------------------------------------------
    // The capture is replayed TWICE, which is the honest record of what round 9's Ruling 28 cost and
    // what round 10's Ruling 32 gave back.
    //
    // The owner's re-emergence after the 6 s hide is an out-of-gate DIFFERENT-id return: she stands
    // up as ids 30/31/33, far enough from a 6-second-old prediction to be outside the gate. Round 9
    // (Ruling 28) refused every such candidate and this capture stopped recovering. Round 10
    // (Ruling 32) accepts one when it was born after the last confirmation, is alone out of gate,
    // clears the confidence floor and is inside the age ceiling -- which these rows are -- so the
    // recovery is back. Measured on this fixture, not guessed:
    //     shipped (Ruling 32)              : 0 LOST rows, 6 s hide recovers at t_ms 14949 on id 31
    //     widened_new_id = false (round 9) : 139 LOST rows, first LOST at t_ms 21079, never recovers
    // The 3 s hide (id 28) recovers identically under both -- that return is in gate.
    //
    // Pass A runs the SHIPPED params and carries Ruling 20d's three assertions (the occlusion
    // mechanisms they guard -- relaxation-only matches not teaching size, the widened floor applying
    // in-gate while REACQUIRING, the window open to expiry -- are all still under test). Pass B runs
    // the strict `widened_new_id = false` reference and pins round 9's outcome, so the difference
    // between the two policies stays measured in CI and cannot drift silently in either direction.
    struct Result {
        double hide1ConfirmedMs = -1.0, hide2ConfirmedMs = -1.0;
        int hide2ConfirmedId = -1;
        long lostRows = 0;
        double firstLostMs = -1.0;
        double refWAtHide2 = 0.0, refHAtHide2 = 0.0;
    };

    auto replay = [&](const garuda::lock::Params& p, const char* tag) {
        Result res;
        LockCore lc(p);
        lc.lock(lock_replay::toObs(*lockTrack, &firstSeen), rows[lockRow].t_ms);
        assert(lc.last().state == State::CONFIRMED);

        for (size_t i = lockRow; i < rows.size(); ++i) {
            const Row& r = rows[i];
            Output out = (i == lockRow) ? lc.last() : lc.update(r.t_ms, lock_replay::liveObs(r, &firstSeen));

            if (out.state == State::LOST) {
                ++res.lostRows;
                if (res.firstLostMs < 0.0) res.firstLostMs = r.t_ms;
            }
            if (res.hide1ConfirmedMs < 0.0 && r.t_ms >= hide1ReturnMs && out.state == State::CONFIRMED)
                res.hide1ConfirmedMs = r.t_ms;
            if (r.t_ms <= hide2ReturnMs) { res.refWAtHide2 = out.ref_w; res.refHAtHide2 = out.ref_h; }
            if (res.hide2ConfirmedMs < 0.0 && r.t_ms >= hide2ReturnMs && out.state == State::CONFIRMED) {
                res.hide2ConfirmedMs = r.t_ms;
                res.hide2ConfirmedId = out.last_id;
            }
        }

        std::printf("lock_replay2[%s]: locked id %d at t=%.0f ms (row %zu of %zu)\n",
                    tag, kLockId, rows[lockRow].t_ms, lockRow, rows.size());
        std::printf("lock_replay2[%s]: 3s hide  — id %d first live t=%.0f ms, CONFIRMED t=%.0f ms (delta %.0f ms)\n",
                    tag, kHide1ReturnId, hide1ReturnMs, res.hide1ConfirmedMs,
                    res.hide1ConfirmedMs < 0.0 ? -1.0 : res.hide1ConfirmedMs - hide1ReturnMs);
        std::printf("lock_replay2[%s]: 6s hide  — first live conf>=%.2f person t=%.0f ms, CONFIRMED t=%.0f ms "
                    "(delta %.0f ms) on id %d\n",
                    tag, kReturnConf, hide2ReturnMs, res.hide2ConfirmedMs,
                    res.hide2ConfirmedMs < 0.0 ? -1.0 : res.hide2ConfirmedMs - hide2ReturnMs,
                    res.hide2ConfirmedId);
        std::printf("lock_replay2[%s]: size reference entering the re-emergence: %.1fx%.1f\n",
                    tag, res.refWAtHide2, res.refHAtHide2);
        std::printf("lock_replay2[%s]: LOST rows %ld (first at t=%.0f ms)\n",
                    tag, res.lostRows, res.firstLostMs);
        // Flush before the asserts: abort() does not flush stdio, and these lines are the evidence.
        std::fflush(stdout);
        return res;
    };

    // --- pass A: the SHIPPED params (Ruling 32) --------------------------------------------------
    Result a = replay(garuda::lock::Params{}, "shipped");

    // (1) The 3 s hide: recovered within 3.0 s of the return id going live. This half already worked
    //     on 217fb04 and must not regress.
    assert(a.hide1ConfirmedMs >= 0.0);
    assert(a.hide1ConfirmedMs - hide1ReturnMs <= 3000.0);
    // (2) The 6 s hide: the lock must never expire during it. On 217fb04 it did, at t_ms 21680.
    assert(a.lostRows == 0);
    // (3) ...and must be back on the owner within 1.0 s of her being detectable again.
    assert(a.hide2ConfirmedMs >= 0.0);
    assert(a.hide2ConfirmedMs - hide2ReturnMs <= 1000.0);

    // --- pass B: the strict `widened_new_id = false` reference (round 9's policy) -----------------
    garuda::lock::Params strict;
    strict.widened_new_id = false;
    Result b = replay(strict, "strict_no_new_id");

    // The 3 s hide is untouched (in-gate return, no new-id widened acceptance involved) -- pinned so
    // a future change that broke it could not hide behind the 6 s hide's expected failure.
    assert(b.hide1ConfirmedMs >= 0.0);
    assert(b.hide1ConfirmedMs - hide1ReturnMs <= 3000.0);
    // Under the strict policy the 6 s hide does NOT recover and the lock expires with the owner in
    // plain view -- run 7's original failure mode. This is what Ruling 28 cost and Ruling 32 bought
    // back; pinned exactly, so the gap between the two policies is a measured number in CI rather
    // than a claim in a commit message.
    assert(b.hide2ConfirmedMs < 0.0);
    assert(b.lostRows > 0);
    assert(std::fabs(b.firstLostMs - 21079.0) < 1.0);

    std::cout << "lock_replay2 ok\n";
    return 0;
}
