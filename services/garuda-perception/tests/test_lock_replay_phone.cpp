#undef NDEBUG
#include "lock_replay_common.hpp"
#include <cassert>
#include <map>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <set>
#include <string>

// Replay of run 10e — routine 5, "the phone routine" — through LockCore (on-board fix round 5,
// Ruling 22). Fixture `tests/fixtures/lock_replay_phone.json` is the rel. 97.5–200.0 s window of
// `bench/evidence/2026-09-04-lock-core/run10e_routine5_phone.txt.gz` (2981 rows / 102.4 s, `t_ms`
// re-based to 0 at rel. 97.5 s), extracted verbatim; see lock_replay_common.hpp for the shared
// loader and for the general "a replay is a weaker gate than the live pipeline" note. **This
// capture is the exception to the 10 Hz remark there**: run 10e was taken with the shim's SSE cap
// at 30 Hz, so it samples at ~29 rows/s — essentially the board's own frame rate, which is why a
// 102 s window is 2981 rows rather than ~1000.
//
// What the capture holds (bench/benchlog.md, "Run 10e — phone: detector starvation and a silent
// false lock"), in fixture time (add 97.5 s for the capture-relative times in the benchlog):
//   t≈0.03 s   the owner's phone is live as id 109, `cell phone`, conf ≥ 0.5 — where this test locks.
//   0–48.5 s   the phone moves around the room; the detector holds it only ~37 % of rows and hands
//              out 38 distinct ids for it, so the core rides continuous id churn. This is the half
//              the fix must NOT regress.
//   t≈48.5 s   the phone leaves / is hidden. On the pre-fix model the core, REACQUIRING with the
//              widened floor 0.40 applying in-gate (Ruling 20b), then hopped across DIFFERENT-CLASS
//              in-gate candidates (`knife` 140, `remote` 146/147/149/151, `hair drier` 160/161) and
//              at t≈68.2 s settled on id 163 — a static `chair`/`suitcase` box, 229x270 at (343,447),
//              conf 0.84–0.92 — and stayed CONFIRMED on it to the end of the 900 s capture while
//              still publishing `lock.class = "cell phone"`.
//
// Ruling 22's three assertions, with every anchor computed from the fixture rather than hard-coded
// so a re-extraction of the window cannot silently move them. Note (a) deliberately reconstructs
// the winner's class from the row's own `tracks[]` (the live entry whose id is the core's `last_id`)
// instead of reading `Output.cls`: that makes the test identical before and after Ruling 22.3
// changed what `cls` publishes, so the same test measures the same thing on both models.

using garuda::lock::LockCore;
using garuda::lock::Output;
using garuda::lock::State;
using lock_replay::Row;

namespace {

const char* kPhone = "cell phone";
const double kLockConf = 0.5;        // "the first live cell phone box with conf >= 0.5" (Ruling 22.5)
const double kPhoneWindowMs = 48500; // rel. 97.5–146.0 s: the half where the phone is really there
const int kFalseLockId = 163;        // the static chair/suitcase the pre-fix core settled on

// The pre-fix "confirmed on phone-live rows" fraction over 0–48.5 s, measured by running THIS test
// against the pre-fix core (commit 097bfad) and pasted from its own printed line — see the report
// in .superpowers/sdd/2026-09-04-hailo15l-lock-core/. Ruling 22.5(c): the post-fix fraction must be
// at least this minus 0.02. The pre-fix run's other three lines, for the record:
//   cross-class CONFIRMED = 12 (first at t=5888 ms on id 116, class 'remote')
//   rows CONFIRMED on the false-lock id 163 = 958
//   final row t=102441 ms state=confirmed last_id=163 winner class 'suitcase'
const double kPreFixPhoneFrac = 0.8013;   // 758 / 946 rows, printed by the pre-fix (red) run
const double kRegressionSlack = 0.02;

// Classes the core must not be CONFIRMED on at the end of the window (Ruling 22.5(b)).
bool isForbiddenEndClass(const std::string& c) {
    return c == "chair" || c == "suitcase" || c == "tv" || c == "person" || c == "remote";
}

} // namespace

int main(int argc, char** argv) {
    assert(argc >= 2 && "usage: test_lock_replay_phone <fixture.json>");
    std::vector<Row> rows = lock_replay::load(argv[1]);
    assert(rows.size() == 2981 && "fixture is run 10e's rel. 97.5-200.0 s window");

    // Round 10 (Ruling 32b): the per-id birth timestamps this fixture implies -- the first row
    // each id appears in. See lock_replay_common.hpp's firstSeenMs() for the rule and its two
    // caveats (both conservative: the reconstruction can never invent a born-after-loss id).
    const std::map<int, double> firstSeen = lock_replay::firstSeenMs(rows);

    // --- anchor: the first live conf >= 0.5 `cell phone` box ---------------------------------
    size_t lockRow = rows.size();
    const lock_replay::Track* lockTrack = nullptr;
    for (size_t i = 0; i < rows.size() && !lockTrack; ++i)
        for (const auto& t : rows[i].tracks)
            if (t.cls == kPhone && !t.coasting && t.conf >= kLockConf) {
                lockRow = i; lockTrack = &t; break;
            }
    assert(lockTrack && "no live conf>=0.5 cell phone row in the fixture");

    const int lockedId = lockTrack->id;

    // --- replay -------------------------------------------------------------------------------
    // Replayed TWICE, and the two numbers are the whole story of rounds 9, 10 and 10b on this
    // capture. The phone half leans hard on the widened stage accepting NEW ids: the detector hands
    // out 38 distinct ids for one phone in 48 s, and after each gap the phone returns far enough
    // from the prediction to be out of gate.
    //
    //   strict  (round 9, widened_new_id = false)          : 183/946 = 0.1934
    //   shipped (round 10b, Ruling 32 + the 7000 ms ceiling): 771/946 = 0.8150
    //
    // Round 10's Ruling 32 as first specified -- same conditions, `widened_new_id_max_age_ms` 5000 --
    // recovered routine 2 completely but bought exactly ONE row here (184/946 = 0.1945). The cause
    // was condition (e) alone, measured by relaxing each condition in turn: with (b), (c) and (d) in
    // force but (e) opened, this capture reaches 0.8150; with (e) at 5000 it is 0.1945 whatever the
    // others do.
    //
    // The mechanism is a CLIFF, not a gradient. Of the 26 different-id re-acquisitions this capture
    // needs, 24 happen at obs_age <= 3969 ms, one at 6392 ms and one at 8289 ms. Missing the 6392 ms
    // one is fatal *in this harness* because the replay drives `LockCore::update()` alone: there is
    // no `LockResolver`, so once the core reaches LOST nothing can ever re-lock it and the remaining
    // ~54 s of capture score zero. The ceiling sweep is a step: 2000/3000/5000/6000 ms all give
    // 0.1945, and 7000/8000/9000/9500/10000 ms all give 0.8150. Round 10b (Ruling 33) therefore set
    // the shipped default to 7000 -- above the 6392 ms the capture actually asks for, and still 3 s
    // short of the unchanged 10 s `expire_ms`.
    //
    // On the real node a LOST lock with a class auto-acquire configured produces a NEW EPOCH and
    // re-locks -- which is what the round-8 board capture shows (`lost -> confirmed`, relocks 1) --
    // so this harness is HARSHER than the board: on the board the cost of too tight a ceiling is an
    // extra visible re-lock per long gap, not a target that is never seen again. Saying so is the
    // point; the ceiling was still moved, because 6.4 s is what the capture asks for.
    //
    // Ruling 22's OWN protections hold in both passes: 0 cross-class confirms and 0 rows on the
    // false-lock id 163 -- no ruling in this sequence trades away the class discipline round 5 added.
    struct Result {
        long phoneLiveRows = 0, confirmedOnPhoneLiveRows = 0;
        long crossClassConfirms = 0;         // (a) violations
        double firstCrossClassMs = -1.0;
        std::string firstCrossClassCls;
        int firstCrossClassId = -1;
        long confirmedOnFalseLockId = 0;     // rows CONFIRMED on id 163, any class
        Output finalOut;
        std::string finalWinnerCls;
        double frac = 0.0;
    };

    auto replay = [&](const garuda::lock::Params& p, const char* tag) {
    Result res;
    LockCore lc(p);
    lc.lock(lock_replay::toObs(*lockTrack, &firstSeen), rows[lockRow].t_ms);
    assert(lc.last().state == State::CONFIRMED);

    long& phoneLiveRows = res.phoneLiveRows;
    long& confirmedOnPhoneLiveRows = res.confirmedOnPhoneLiveRows;
    long& crossClassConfirms = res.crossClassConfirms;
    double& firstCrossClassMs = res.firstCrossClassMs;
    std::string& firstCrossClassCls = res.firstCrossClassCls;
    int& firstCrossClassId = res.firstCrossClassId;
    long& confirmedOnFalseLockId = res.confirmedOnFalseLockId;
    Output& finalOut = res.finalOut;
    std::string& finalWinnerCls = res.finalWinnerCls;
    int prevId = lockedId;               // the id of the previous associated observation

    for (size_t i = lockRow; i < rows.size(); ++i) {
        const Row& r = rows[i];
        Output out = (i == lockRow) ? lc.last() : lc.update(r.t_ms, lock_replay::liveObs(r, &firstSeen));

        // The winner's class on a CONFIRMED row: the row's own LIVE track carrying `out.last_id`.
        std::string winnerCls;
        if (out.state == State::CONFIRMED) {
            for (const auto& t : r.tracks)
                if (t.id == out.last_id && !t.coasting) { winnerCls = t.cls; break; }
        }

        // (a) a different-class winner is only ever legitimate when it carries the previous
        //     observation's id (Ruling 22.1: tracker continuity says the detector re-labelled the
        //     same object). The lock() frame itself is skipped -- it is the click, not an
        //     association.
        if (i != lockRow && out.state == State::CONFIRMED && !winnerCls.empty()
                && winnerCls != kPhone && out.last_id != prevId) {
            ++crossClassConfirms;
            if (firstCrossClassMs < 0.0) {
                firstCrossClassMs = r.t_ms;
                firstCrossClassCls = winnerCls;
                firstCrossClassId = out.last_id;
            }
        }
        if (out.state == State::CONFIRMED && out.last_id == kFalseLockId) ++confirmedOnFalseLockId;

        // (c) the phone half: rows carrying a LIVE `cell phone` box at all, and how many of them the
        //     core was CONFIRMED on.
        if (r.t_ms <= kPhoneWindowMs) {
            bool hasLivePhone = false;
            for (const auto& t : r.tracks)
                if (!t.coasting && t.cls == kPhone) { hasLivePhone = true; break; }
            if (hasLivePhone) {
                ++phoneLiveRows;
                if (out.state == State::CONFIRMED) ++confirmedOnPhoneLiveRows;
            }
        }

        if (out.state == State::CONFIRMED) prevId = out.last_id;
        finalOut = out;
        finalWinnerCls = winnerCls;
    }

    res.frac = phoneLiveRows ? static_cast<double>(confirmedOnPhoneLiveRows)
                             / static_cast<double>(phoneLiveRows)
                             : 0.0;
    std::printf("lock_replay_phone[%s]: locked id %d at t=%.0f ms (row %zu of %zu)\n",
                tag, lockedId, rows[lockRow].t_ms, lockRow, rows.size());
    std::printf("lock_replay_phone[%s]: CONFIRMED on %ld of %ld rows carrying a live '%s' box in "
                "0-%.0f ms = %.4f (pre-fix %.4f, floor %.4f)\n",
                tag, confirmedOnPhoneLiveRows, phoneLiveRows, kPhone, kPhoneWindowMs, res.frac,
                kPreFixPhoneFrac, kPreFixPhoneFrac - kRegressionSlack);
    std::printf("lock_replay_phone[%s]: cross-class CONFIRMED (different class AND different id) = %ld"
                " (first at t=%.0f ms on id %d, class '%s')\n",
                tag, crossClassConfirms, firstCrossClassMs, firstCrossClassId,
                firstCrossClassCls.empty() ? "-" : firstCrossClassCls.c_str());
    std::printf("lock_replay_phone[%s]: rows CONFIRMED on the false-lock id %d = %ld\n",
                tag, kFalseLockId, confirmedOnFalseLockId);
    std::printf("lock_replay_phone[%s]: final row t=%.0f ms state=%s last_id=%d winner class '%s'\n",
                tag, rows.back().t_ms, garuda::lock::state_name(finalOut.state), finalOut.last_id,
                finalWinnerCls.empty() ? "-" : finalWinnerCls.c_str());
    // Flush BEFORE the asserts: abort() does not flush stdio, and these lines are the evidence.
    std::fflush(stdout);
    return res;
    };

    // Ruling 22's protections must hold in EVERY pass -- they are what the round-5 rulings bought,
    // and neither Ruling 28 nor Ruling 32 trades any of them away.
    auto assertRuling22 = [](const Result& r) {
        // (a) Ruling 22.1: never CONFIRMED on a different-class candidate that does not carry the
        //     previous observation's id.
        assert(r.crossClassConfirms == 0);
        // (b) Ruling 22.5(b): at the end of the window the core is not on the static suitcase, and
        //     not CONFIRMED on any of the classes the pre-fix walk passed through.
        assert(r.finalOut.last_id != kFalseLockId);
        assert(r.confirmedOnFalseLockId == 0);
        if (r.finalOut.state == State::CONFIRMED) assert(!isForbiddenEndClass(r.finalWinnerCls));
    };

    // --- pass A: the SHIPPED params (Ruling 32 + round 10b's 7000 ms ceiling) --------------------
    // Every Ruling 32 condition is in force here exactly as deployed -- (b) born-after-loss,
    // (c) exclusivity, (d) the 0.5 confidence floor, (e) the 7000 ms ceiling.
    Result a = replay(garuda::lock::Params{}, "shipped");
    assertRuling22(a);
    assert(a.frac >= 0.78);                                  // round 10's acceptance bar
    assert(a.frac >= kPreFixPhoneFrac - kRegressionSlack);   // Ruling 22.5(c)'s original bar

    // --- pass B: the strict `widened_new_id = false` reference (round 9's policy) -----------------
    // Kept so the gap between the two policies stays a measured number in CI. Pinned as a bounded
    // range, as in round 9: neither an unnoticed further collapse nor an unremarked recovery may
    // slip past.
    garuda::lock::Params strict;
    strict.widened_new_id = false;
    Result b = replay(strict, "strict_no_new_id");
    assertRuling22(b);
    assert(b.frac > 0.15 && b.frac < 0.25);
    assert(b.frac <= a.frac);   // Ruling 32 can only ever admit MORE than the blanket refusal

    std::cout << "lock_replay_phone ok\n";
    return 0;
}
