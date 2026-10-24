#undef NDEBUG
#include "garuda/bytetrack.hpp"
#include "garuda/lock.hpp"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>
#include <optional>
#include <string>

using garuda::track::ByteTracker;
using garuda::track::Det;
using garuda::track::LockResolver;
using garuda::track::LockResult;
using garuda::track::TrackRecord;

// Golden replay: applies target/click (against the PREVIOUS step()'s alive tracks) then tracker.update()
// then step(), exactly as tests/golden/make_track_golden.py drives mono_lock_ref.py. Lock fields only —
// the tracker's own output (ids/bboxes/conf) is covered by test_bytetrack; here we cross-check just the
// alive count as a sanity signal that the same tracker state was reached.
static int replay_golden(const char* scenario_path, const char* golden_path) {
    nlohmann::json sc, gd;
    std::ifstream(scenario_path) >> sc;
    std::ifstream(golden_path) >> gd;

    ByteTracker tracker(0.4, 0.12, 0.3, 25, 2);
    LockResolver lock;

    size_t n = sc["frames"].size();
    assert(n == gd["frames"].size());
    for (size_t i = 0; i < n; ++i) {
        auto& fr = sc["frames"][i];
        if (!fr["target"].is_null()) lock.set_target(fr["target"].get<std::string>());
        if (!fr["click"].is_null()) lock.click(fr["click"][0].get<double>(), fr["click"][1].get<double>());

        std::vector<Det> dets;
        for (auto& d : fr["dets"])
            if (d[5].get<double>() >= 0.15)
                dets.push_back({d[0].get<double>(), d[1].get<double>(), d[2].get<double>(), d[3].get<double>(),
                                 d[4].get<std::string>(), d[5].get<double>()});
        tracker.update(dets);
        LockResult r = lock.step(tracker);

        auto& want = gd["frames"][i];
        bool want_has_id = !want["lock_id"].is_null();
        bool lid_ok = r.lock_id.has_value() == want_has_id && (!want_has_id || *r.lock_id == want["lock_id"].get<int>());
        bool ok = lid_ok && r.lock_class == want["lock_class"].get<std::string>() && r.coasting == want["coasting"].get<bool>()
               && r.alive.size() == want["tracks"].size();
        if (!ok) {
            std::cerr << "frame " << i << " mismatch: got lock_id=";
            if (r.lock_id) std::cerr << *r.lock_id; else std::cerr << "null";
            std::cerr << " lock_class=" << r.lock_class << " coasting=" << r.coasting << " alive=" << r.alive.size()
                      << " | want lock_id=" << want["lock_id"] << " lock_class=" << want["lock_class"]
                      << " coasting=" << want["coasting"] << " tracks=" << want["tracks"].size() << "\n";
            return 1;
        }
        // accessors must agree with the LockResult just returned
        assert(lock.lock_id() == r.lock_id);
        assert(lock.target_class() == r.lock_class);
    }
    std::cout << "lock golden ok (" << n << " frames)\n";
    return 0;
}

// Fidelity check: step(const ByteTracker&) and step(const std::vector<TrackRecord>&) built from that
// same tracker's tracks() must agree on every frame of the golden scenario. Two independent resolvers
// are driven in lockstep (same target/click/tracker.update() sequence) so each accumulates its own
// m_lid/m_prev state exactly as it would standalone; only the last step() call of each frame differs
// (tracker vs. records).
static int replay_dual(const char* scenario_path) {
    nlohmann::json sc;
    std::ifstream(scenario_path) >> sc;

    ByteTracker tracker(0.4, 0.12, 0.3, 25, 2);
    LockResolver lock_a, lock_b;

    for (auto& fr : sc["frames"]) {
        if (!fr["target"].is_null()) {
            lock_a.set_target(fr["target"].get<std::string>());
            lock_b.set_target(fr["target"].get<std::string>());
        }
        if (!fr["click"].is_null()) {
            double cx = fr["click"][0].get<double>(), cy = fr["click"][1].get<double>();
            lock_a.click(cx, cy);
            lock_b.click(cx, cy);
        }

        std::vector<Det> dets;
        for (auto& d : fr["dets"])
            if (d[5].get<double>() >= 0.15)
                dets.push_back({d[0].get<double>(), d[1].get<double>(), d[2].get<double>(), d[3].get<double>(),
                                 d[4].get<std::string>(), d[5].get<double>()});
        tracker.update(dets);

        LockResult ra = lock_a.step(tracker);

        std::vector<TrackRecord> recs;
        recs.reserve(tracker.tracks().size());
        for (auto& t : tracker.tracks())
            recs.push_back({t.track_id, t.cls, t.conf,
                             {t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3]},
                             t.time_since_update, t.confirmed()});
        LockResult rb = lock_b.step(recs);

        if (ra.lock_id != rb.lock_id || ra.lock_class != rb.lock_class || ra.coasting != rb.coasting) {
            std::cerr << "dual mismatch: tracker-based lock_id=";
            if (ra.lock_id) std::cerr << *ra.lock_id; else std::cerr << "null";
            std::cerr << " class=" << ra.lock_class << " coasting=" << ra.coasting << " | records-based lock_id=";
            if (rb.lock_id) std::cerr << *rb.lock_id; else std::cerr << "null";
            std::cerr << " class=" << rb.lock_class << " coasting=" << rb.coasting << "\n";
            return 1;
        }
    }
    std::cout << "lock dual (tracker vs records) parity ok\n";
    return 0;
}

int main(int argc, char** argv) {
    assert(argc == 3);
    if (int rc = replay_golden(argv[1], argv[2])) return rc;
    if (int rc = replay_dual(argv[1])) return rc;

    // --- Extra unit cases (not exercised by the golden) -------------------------------------------
    // All use min_hits=1 so a track confirms on birth, letting each case set up an exact tsu/conf state.

    // 0) click() on a fresh LockResolver, before any step() has ever run -> m_prev is still empty
    //    (step() is what populates it), so nothing can be picked: returns false and lock_id() stays empty.
    {
        LockResolver lock;
        bool picked = lock.click(0.0, 0.0);
        assert(!picked);
        assert(!lock.lock_id().has_value());
    }

    // 1) click nearest-centre fallback: click outside both boxes -> nearer centre wins, class follows label.
    {
        ByteTracker tr(0.4, 0.1, 0.3, 25, 1);
        LockResolver lock;
        tr.update({{0, 0, 100, 100, "a", 0.9}, {300, 0, 100, 100, "b", 0.9}});
        lock.step(tr); // publishes this frame's alive tracks for the click below
        bool picked = lock.click(500.0, 50.0); // outside both; nearer to b's centre (350,50)
        assert(picked);
        assert(lock.target_class() == "b");
        assert(lock.lock_id().has_value());
        // "b" was the second det -> id 2 (births assigned in det order on an empty tracker)
        assert(*lock.lock_id() == 2);
    }

    // 2) click inside two overlapping boxes -> the smaller-area box wins.
    {
        ByteTracker tr(0.4, 0.1, 0.3, 25, 1);
        LockResolver lock;
        tr.update({{0, 0, 200, 200, "big", 0.9}, {50, 50, 50, 50, "small", 0.9}});
        lock.step(tr);
        bool picked = lock.click(75.0, 75.0); // inside both
        assert(picked);
        assert(lock.target_class() == "small");
        assert(lock.lock_id().has_value() && *lock.lock_id() == 2);
    }

    // 3a) acquire tie-break: one coasting with higher conf vs one live with lower conf -> live wins.
    {
        ByteTracker tr(0.4, 0.1, 0.3, 25, 1);
        LockResolver lock;
        tr.update({{0, 0, 50, 50, "x", 0.5}, {200, 0, 50, 50, "x", 0.9}}); // P id1 conf.5, Q id2 conf.9, both born live
        tr.update({{0, 0, 50, 50, "x", 0.5}});                            // P stays live; Q now coasting (tsu=1), conf stays .9
        lock.set_target("x");                                            // no current lock, class "x"
        LockResult r = lock.step(tr);
        assert(r.lock_id.has_value() && *r.lock_id == 1); // live P wins over coasting Q despite lower conf
        assert(!r.coasting);
    }

    // 3b) acquire tie-break: two live, different conf -> higher conf wins.
    {
        ByteTracker tr(0.4, 0.1, 0.3, 25, 1);
        LockResolver lock;
        tr.update({{0, 0, 50, 50, "y", 0.4}, {200, 0, 50, 50, "y", 0.9}}); // id1 conf.4, id2 conf.9, both live
        lock.set_target("y");
        LockResult r = lock.step(tr);
        assert(r.lock_id.has_value() && *r.lock_id == 2);
    }

    // 3c) acquire tie-break: two live, equal conf -> first in alive order wins.
    {
        ByteTracker tr(0.4, 0.1, 0.3, 25, 1);
        LockResolver lock;
        tr.update({{0, 0, 50, 50, "z", 0.7}, {200, 0, 50, 50, "z", 0.7}}); // id1, id2, equal conf, both live
        lock.set_target("z");
        LockResult r = lock.step(tr);
        assert(r.lock_id.has_value() && *r.lock_id == 1);
    }

    // 4) set_target("") -> class becomes "person" and the lock is cleared;
    //    set_target("vehicle") with no vehicle in view -> lock_id stays null, lock_class is "vehicle".
    {
        ByteTracker tr(0.4, 0.1, 0.3, 25, 1);
        LockResolver lock; // default class "person"
        tr.update({{0, 0, 50, 50, "person", 0.9}});
        LockResult r = lock.step(tr);
        assert(r.lock_id.has_value()); // auto-acquired the only person

        lock.set_target("cat"); // move off the default so the empty-string mapping below is a real test
        assert(lock.target_class() == "cat");
        assert(!lock.lock_id().has_value());

        lock.set_target("");
        assert(lock.target_class() == "person"); // empty string maps back to the default class, not to "cat"
        assert(!lock.lock_id().has_value());

        lock.set_target("vehicle");
        assert(lock.target_class() == "vehicle");
        assert(!lock.lock_id().has_value());
        LockResult r2 = lock.step(tr); // tracker still only has the person track
        assert(!r2.lock_id.has_value());
        assert(r2.lock_class == "vehicle");
        assert(!r2.coasting);
    }

    // 5) record-based step: hand-built records, two persons, one coasting (tsu=3) -> acquires the live
    //    one over the coasting one, regardless of conf (same acquire rule as 3a, now via step(records)).
    {
        LockResolver lock; // default class "person"
        std::vector<TrackRecord> recs = {
            {1, "person", 0.9, {0, 0, 50, 50}, 3, true},     // coasting, higher conf
            {2, "person", 0.5, {200, 0, 50, 50}, 0, true},   // live, lower conf
        };
        LockResult r = lock.step(recs);
        assert(r.lock_id.has_value() && *r.lock_id == 2);
        assert(!r.coasting);
        assert(r.alive.size() == 2);
    }

    // 6) on-board fix round 1 (Ruling 16.1): the AUTO-ACQUIRE gate. A resolver configured the way the
    //    node configures it (auto_min_conf 0.5, auto_edge_margin_frac 0.02 of a 1280 px frame =
    //    25.6 px) must refuse to pick up, on its own, either a low-confidence candidate or one whose
    //    box touches the left/right edge -- the two properties of run 1's 29x194, conf 0.17 sliver at
    //    x=1251 (x+w = 1280, hard against the right edge), which seeded LockCore with a size reference
    //    no later frame of that person could match (bench/benchlog.md, "Run 1 ... edge-entry failure").
    //    Top/bottom are deliberately NOT gated: a person close to the camera legitimately spans the
    //    full frame height (run 1's healthy id-2 lock had y=-3, h=584).
    {
        const double kMinConf = 0.5, kEdgeFrac = 0.02;   // == the shipped config values
        const int kFrameW = 1280;                        // margin = 25.6 px

        {   // (a) low conf, comfortably inside the frame -> NOT auto-acquired
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW);
            std::vector<TrackRecord> recs = {{1, "person", 0.17, {600, 300, 60, 200}, 0, true}};
            LockResult r = lock.step(recs);
            assert(!r.lock_id.has_value());
            assert(r.alive.size() == 1);   // still alive/published, just not locked onto
        }
        {   // (b) run 1's actual sliver: conf 0.17 AND hard against the right edge -> NOT acquired
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW);
            std::vector<TrackRecord> recs = {{1, "person", 0.17, {1251, 381, 29, 194}, 0, true}};
            assert(!lock.step(recs).lock_id.has_value());
        }
        {   // (c) good conf but still entering at the right edge (x+w = 1280 > 1280-25.6) -> NOT acquired
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW);
            std::vector<TrackRecord> recs = {{1, "person", 0.9, {1180, 300, 100, 400}, 0, true}};
            assert(!lock.step(recs).lock_id.has_value());
        }
        {   // (d) good conf but touching the LEFT edge (x = 10 < 25.6) -> NOT acquired
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW);
            std::vector<TrackRecord> recs = {{1, "person", 0.9, {10, 300, 100, 400}, 0, true}};
            assert(!lock.step(recs).lock_id.has_value());
        }
        {   // (e) conf 0.6, fully inside left/right, spanning the FULL HEIGHT (y=-3, h=730: a close
            //     person) -> ACQUIRED. Proves conf 0.6 clears the floor and that top/bottom are not gated.
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW);
            std::vector<TrackRecord> recs = {{7, "person", 0.6, {400, -3, 300, 730}, 0, true}};
            LockResult r = lock.step(recs);
            assert(r.lock_id.has_value() && *r.lock_id == 7);
        }
        {   // (f) the gate is AUTO-acquire only: an explicit click on the very sliver of (b) still
            //     locks it -- the user's choice is never second-guessed (Ruling 16.1's own carve-out).
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW);
            std::vector<TrackRecord> recs = {{1, "person", 0.17, {1251, 381, 29, 194}, 0, true}};
            lock.step(recs);                       // publishes alive[] for the click below; acquires nothing
            assert(lock.click(1265, 478));         // inside the sliver
            assert(lock.lock_id().has_value() && *lock.lock_id() == 1);
        }
        {   // (g) the DEFAULT-constructed resolver is ungated (that is what the mono-parity golden
            //     above replays through): the same sliver is acquired.
            LockResolver lock;
            std::vector<TrackRecord> recs = {{1, "person", 0.17, {1251, 381, 29, 194}, 0, true}};
            assert(lock.step(recs).lock_id.has_value());
        }
    }

    // 7) on-board fix round 2 (Ruling 18), AMENDED by round 7 (Ruling 24): the auto-acquire STREAK
    //    gate. Run 2's capture (bench/evidence/2026-09-04-lock-core/run2_walk_junklock.txt.gz) had
    //    several persistent low-confidence "person" tracks on static room objects; one of them cleared
    //    the conf+edge gate on a SINGLE frame and took the lock for the remaining ~70 s, so the owner
    //    was never locked and the run measured nothing. Round 2 answered that with `auto_min_streak`
    //    CONSECUTIVE live gate-passing frames. Round 7 found the consecutive requirement too strict for
    //    a target the detector only sees intermittently: in the round-7 capture the phone was live in
    //    just 30.2 % of frames, so after the clicked lock expired auto-acquire never re-locked it
    //    (LOST 68 % of rows -- bench/benchlog.md F1, "Round 7"). The count is now over a SLIDING
    //    WINDOW: `auto_min_streak` (5) gate-passing LIVE frames within the last `auto_streak_window`
    //    (15) frames in which that id appeared at all.
    {
        const double kMinConf = 0.5, kEdgeFrac = 0.02;
        const int kFrameW = 1280, kStreak = 5, kWindow = 15;
        // A mid-frame, edge-clear box: only conf and liveness vary between the cases below.
        auto rec = [](double conf, int tsu) {
            return TrackRecord{1, "person", conf, {400, 200, 120, 300}, tsu, true};
        };

        {   // (a) ONE good frame and nothing else is still never enough (the run-2 flicker, exactly):
            //     the count is 1 while that frame is inside the window and 0 from frame 17 on, once it
            //     has aged out of a 15-frame window entirely. 5 is never reached.
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, kWindow);
            assert(!lock.step({rec(0.6, 0)}).lock_id.has_value());      // frame 1: count 1
            for (int i = 2; i <= 25; ++i)
                assert(!lock.step({rec(0.2, 0)}).lock_id.has_value());  // frames 2-25: count 1, then 0
        }
        {   // (b) four consecutive good frames -> still not acquired; (c) the fifth -> acquired,
            //     on that very frame (unchanged from round 2: 5 within 15 is satisfied at frame 5).
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, kWindow);
            for (int i = 1; i <= 4; ++i)
                assert(!lock.step({rec(0.6, 0)}).lock_id.has_value());
            LockResult r = lock.step({rec(0.6, 0)});
            assert(r.lock_id.has_value() && *r.lock_id == 1);
        }
        {   // (d) round 7's point: 5 gate-passing frames SPREAD across the window acquire, on the 5th
            //     of them. Frames 1, 3, 6, 9, 14 pass and the other nine fail; the running count is
            //     1,1,2,2,2,3,3,3,4,4,4,4,4,5 -> it reaches 5 on frame 14, with the oldest hit
            //     (frame 1) 13 frames old and so still inside the 15-frame window.
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, kWindow);
            const int good[] = {1, 3, 6, 9, 14};
            for (int f = 1; f <= 14; ++f) {
                const bool g = std::find(std::begin(good), std::end(good), f) != std::end(good);
                LockResult r = lock.step({rec(g ? 0.6 : 0.2, 0)});
                if (f < 14) assert(!r.lock_id.has_value());
                else        assert(r.lock_id.has_value() && *r.lock_id == 1);
            }
        }
        {   // (e) FOUR gate-passing frames in the same span (drop frame 14 from (d)) never acquire: the
            //     count peaks at 4 through frame 15, then falls back as frames 1, 3, 6, 9 age out.
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, kWindow);
            const int good[] = {1, 3, 6, 9};
            for (int f = 1; f <= 25; ++f) {
                const bool g = std::find(std::begin(good), std::end(good), f) != std::end(good);
                assert(!lock.step({rec(g ? 0.6 : 0.2, 0)}).lock_id.has_value());
            }
        }
        {   // (f) a COASTING frame no longer RESETS the count (in round 2 it did) -- it simply is not a
            //     gate-passing LIVE frame and contributes 0: 3 good + 1 coasting + good gives counts
            //     1,2,3,3,4 and reaches 5 on frame 6, the 5th live good frame.
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, kWindow);
            for (int i = 0; i < 3; ++i) assert(!lock.step({rec(0.6, 0)}).lock_id.has_value());
            assert(!lock.step({rec(0.6, 2)}).lock_id.has_value());     // coasting -> contributes 0
            assert(!lock.step({rec(0.6, 0)}).lock_id.has_value());     // frame 5: count 4
            LockResult r = lock.step({rec(0.6, 0)});                   // frame 6: count 5
            assert(r.lock_id.has_value() && *r.lock_id == 1);
        }
        {   // (g) window 0 disables the requirement even with a non-zero streak: acquired on the first
            //     gate-passing frame.
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, 0);
            assert(lock.step({rec(0.6, 0)}).lock_id.has_value());
        }
        {   // (h) streak 0 disables it as well, whatever the window...
            LockResolver lock(25, 5, "person", kMinConf, kEdgeFrac, kFrameW, 0, kWindow);
            assert(lock.step({rec(0.6, 0)}).lock_id.has_value());
        }
        {   // (i) ...and the default-constructed resolver has neither (mono parity: that is what the
            //     golden above replays through).
            LockResolver lock;
            assert(lock.step({rec(0.6, 0)}).lock_id.has_value());
        }
    }

    // 8) on-board fix round 2 (Ruling 18, part 2): the RE-ACQUIRE JUMP is gated the same way. A lock
    //    that has been coasting longer than `reacq` frames moves to the best live same-class track --
    //    which without this gate is exactly the junk flicker run 2 lost the capture to. Setup for both
    //    cases: id 1 is acquired properly (5 live conf-0.9 frames), then goes coasting while a second
    //    track is live throughout.
    {
        const double kMinConf = 0.5, kEdgeFrac = 0.02;
        const int kFrameW = 1280, kStreak = 5, kReacq = 5, kWindow = 15;
        auto one = [](double conf, int tsu) {
            return TrackRecord{1, "person", conf, {400, 200, 120, 300}, tsu, true};
        };
        auto two = [](double conf) {
            return TrackRecord{2, "person", conf, {800, 200, 120, 300}, 0, true};
        };

        for (double otherConf : {0.3, 0.6}) {
            LockResolver lock(25, kReacq, "person", kMinConf, kEdgeFrac, kFrameW, kStreak, kWindow);
            for (int i = 1; i <= 5; ++i) lock.step({one(0.9, 0), two(otherConf)});
            assert(lock.lock_id().has_value() && *lock.lock_id() == 1);   // id 1 wins on conf

            LockResult r;
            for (int tsu = 1; tsu <= kReacq + 1; ++tsu) r = lock.step({one(0.9, tsu), two(otherConf)});
            // By now id 2 has been live and (for 0.6) gate-passing for 11 straight frames -- well past
            // 5 within the last 15 either way -- so the only difference between the two cases is
            // whether it clears auto_min_conf.
            assert(r.lock_id.has_value());
            if (otherConf < kMinConf) assert(*r.lock_id == 1);   // no jump onto a conf-0.3 flicker
            else                      assert(*r.lock_id == 2);   // jump onto a proper conf-0.6 track
        }
    }

    std::cout << "lock unit cases ok\n";
    return 0;
}
