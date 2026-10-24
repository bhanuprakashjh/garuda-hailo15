#undef NDEBUG
#include "lock_replay_common.hpp"
#include <cassert>
#include <map>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <vector>

// Replay of a REAL on-board capture through LockCore (on-board fix round 3, Ruling 19.5).
//
// Fixture: tests/fixtures/lock_replay_routine1.json — every row of run 5 (routine 1,
// walk-out/return with the owner in view, build 83b600c, `config/perception-yolov8m.json`,
// person profile / hailo Kalman engine), 1196 rows over 120 s, extracted verbatim from the
// PC-side timestamped SSE capture committed as
// bench/evidence/2026-09-04-lock-core/run5_routine1_walk.txt.gz. Each row is
// `{t_ms, tracks:[{id, cls, conf, x, y, w, h, coasting}]}` with `t_ms` relative to the capture's
// first row; only the `tracks[]` array is kept (the board's own `lock` object is deliberately NOT
// replayed — this test drives a fresh LockCore over the same detector/tracker output and asks what
// the CURRENT core does with it).
//
// The replay is COARSER than the live pipeline and only LIVE tracks reach update() -- both are
// explained once, in lock_replay_common.hpp, which this test and test_lock_replay2.cpp share.
// Run 6 on the fixed build is what fills bench/benchlog.md's results table; this test exists to stop
// the three round-3 mechanisms (M-A/M-B/M-C, see lock_core.cpp) regressing silently.
//
// Metric (Ruling 19.5): among rows from the lock onward that carry at least one LIVE track of
// conf >= 0.5 — the room held exactly one person, and the persistent junk "person" tracks on static
// room objects all sit below 0.5 (run 2's mechanism, bench/benchlog.md) — the fraction of rows where
// the core reports CONFIRMED. Printed, then asserted.

using garuda::lock::LockCore;
using garuda::lock::Obs;
using garuda::lock::Output;
using garuda::lock::State;
using lock_replay::Row;

namespace {

const int kLockId = 1309;      // the id the board itself was locked to when the capture opens
const int kNewId = 1316;       // the NEW id the owner came back as (M-C)
const double kConfFloor = 0.5; // "a live track of conf >= 0.5" — see the metric note above

} // namespace

int main(int argc, char** argv) {
    assert(argc >= 2 && "usage: test_lock_replay <fixture.json>");
    std::vector<Row> rows = lock_replay::load(argv[1]);
    assert(rows.size() == 1196 && "fixture is run 5's 1196 rows");

    // Round 10 (Ruling 32b): the per-id birth timestamps this fixture implies -- the first row
    // each id appears in. See lock_replay_common.hpp's firstSeenMs() for the rule and its two
    // caveats (both conservative: the reconstruction can never invent a born-after-loss id).
    const std::map<int, double> firstSeen = lock_replay::firstSeenMs(rows);

    // Lock on the first row where kLockId is LIVE with conf >= kConfFloor (Ruling 19.5).
    size_t lockRow = rows.size();
    const lock_replay::Track* lockTrack = nullptr;
    for (size_t i = 0; i < rows.size() && !lockTrack; ++i)
        for (const auto& t : rows[i].tracks)
            if (t.id == kLockId && !t.coasting && t.conf >= kConfFloor) {
                lockRow = i;
                lockTrack = &t;
                break;
            }
    assert(lockTrack && "no live conf>=0.5 row for the locked id in the fixture");

    // The first row where kNewId is LIVE at all (M-C's clock origin).
    double newIdFirstLiveMs = -1.0;
    for (const auto& r : rows) {
        for (const auto& t : r.tracks)
            if (t.id == kNewId && !t.coasting) { newIdFirstLiveMs = r.t_ms; break; }
        if (newIdFirstLiveMs >= 0.0) break;
    }
    assert(newIdFirstLiveMs >= 0.0 && "fixture must contain the new id's re-entry");

    LockCore lc;
    lc.lock(lock_replay::toObs(*lockTrack, &firstSeen), rows[lockRow].t_ms);
    assert(lc.last().state == State::CONFIRMED);

    long liveRows = 0, confirmedOnLiveRows = 0, lostRows = 0;
    double newIdConfirmedMs = -1.0;
    double firstLostMs = -1.0;

    for (size_t i = lockRow; i < rows.size(); ++i) {
        const Row& r = rows[i];
        Output out = (i == lockRow) ? lc.last()                        // the lock() frame itself
                                    : lc.update(r.t_ms, lock_replay::liveObs(r, &firstSeen));

        bool hasLiveTarget = false;
        for (const auto& t : r.tracks)
            if (!t.coasting && t.conf >= kConfFloor) { hasLiveTarget = true; break; }
        if (hasLiveTarget) {
            ++liveRows;
            if (out.state == State::CONFIRMED) ++confirmedOnLiveRows;
        }
        if (out.state == State::LOST) {
            ++lostRows;
            if (firstLostMs < 0.0) firstLostMs = r.t_ms;
        }
        if (newIdConfirmedMs < 0.0 && out.state == State::CONFIRMED && out.last_id == kNewId)
            newIdConfirmedMs = r.t_ms;
    }

    double frac = liveRows ? static_cast<double>(confirmedOnLiveRows) / static_cast<double>(liveRows) : 0.0;
    std::printf("lock_replay: locked id %d at t=%.0f ms (row %zu of %zu)\n",
                kLockId, rows[lockRow].t_ms, lockRow, rows.size());
    std::printf("lock_replay: CONFIRMED on %ld of %ld rows carrying a live conf>=%.2f track = %.4f\n",
                confirmedOnLiveRows, liveRows, kConfFloor, frac);
    std::printf("lock_replay: id %d first live at t=%.0f ms, core CONFIRMED on it at t=%.0f ms (delta %.0f ms)\n",
                kNewId, newIdFirstLiveMs, newIdConfirmedMs,
                newIdConfirmedMs < 0.0 ? -1.0 : newIdConfirmedMs - newIdFirstLiveMs);
    std::printf("lock_replay: LOST rows %ld (first at t=%.0f ms)\n", lostRows, firstLostMs);
    // Flush BEFORE the asserts: abort() does not flush stdio, and these four lines are the
    // before/after evidence this test exists to produce (they must survive a failing run).
    std::fflush(stdout);

    // (1) The headline: the core must be CONFIRMED on essentially every row where the engine has a
    //     live, confident box for the one person in the room.
    assert(frac >= 0.95);
    // (2) M-C: the owner re-entered as a NEW tracker id; the core must take it promptly, not sit in
    //     REACQUIRING until expiry.
    assert(newIdConfirmedMs >= 0.0);
    assert(newIdConfirmedMs - newIdFirstLiveMs <= 1000.0);
    // (3) M-B: the lock must never decay to LOST over this capture.
    assert(lostRows == 0);

    std::cout << "lock_replay ok\n";
    return 0;
}
