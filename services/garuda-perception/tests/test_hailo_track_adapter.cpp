#undef NDEBUG
#include "garuda/hailo_track_adapter.hpp"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <vector>

using garuda::track::HailoTrackAdapter;

int main() {
    // 1) gap and return with the same id: [A@x=100], [], [], [A@x=130], keep_lost=5 -> frames 2/3 report
    //    A coasting (tsu 1, 2) with the box frozen at x=100; frame 4 reports A live (tsu 0) at x=130.
    {
        HailoTrackAdapter ad(5, 1);
        auto r1 = ad.update({{1, "person", 0.9, 100, 0, 20, 40}});
        assert(r1.size() == 1 && r1[0].id == 1 && r1[0].time_since_update == 0 && r1[0].bbox[0] == 100);

        auto r2 = ad.update({});
        assert(r2.size() == 1 && r2[0].id == 1 && r2[0].time_since_update == 1 && r2[0].bbox[0] == 100);

        auto r3 = ad.update({});
        assert(r3.size() == 1 && r3[0].id == 1 && r3[0].time_since_update == 2 && r3[0].bbox[0] == 100);

        auto r4 = ad.update({{1, "person", 0.9, 130, 0, 20, 40}});
        assert(r4.size() == 1 && r4[0].id == 1 && r4[0].time_since_update == 0 && r4[0].bbox[0] == 130);
    }

    // 2) expiry: A seen once then absent for 6 frames, keep_lost=5 -> present (coasting, tsu growing)
    //    for frames 2..6, dropped from frame 7 on.
    {
        HailoTrackAdapter ad(5, 1);
        ad.update({{1, "person", 0.9, 0, 0, 10, 10}});
        for (int f = 2; f <= 6; ++f) {
            auto r = ad.update({});
            assert(r.size() == 1);
            assert(r[0].id == 1 && r[0].time_since_update == f - 1);
        }
        auto r7 = ad.update({});
        assert(r7.empty());
    }

    // 3) return with a new id: A appears, expires (6 absent frames > keep_lost 5), then B appears at the
    //    same place -> B is a distinct record; A is gone entirely.
    {
        HailoTrackAdapter ad(5, 1);
        ad.update({{1, "person", 0.9, 50, 50, 10, 10}});
        for (int i = 0; i < 6; ++i) ad.update({});   // tsu climbs 1..6; erased once it exceeds keep_lost
        auto r = ad.update({{2, "person", 0.9, 50, 50, 10, 10}});
        assert(r.size() == 1 && r[0].id == 2 && r[0].bbox[0] == 50);
    }

    // 4) min_hits=2: an id seen once is confirmed=false until its second sighting.
    {
        HailoTrackAdapter ad(5, 2);
        auto r1 = ad.update({{1, "person", 0.9, 0, 0, 10, 10}});
        assert(r1.size() == 1 && r1[0].confirmed == false);
        auto r2 = ad.update({{1, "person", 0.9, 1, 1, 10, 10}});
        assert(r2.size() == 1 && r2[0].confirmed == true);
    }

    // 5) class switch on the same id (the SDK tracker is class-agnostic -- one-to-one LAPJV assignment
    //    with no per-class matching -- so a different-class detection on the same track can win a
    //    single stray frame's assignment and relabel that id): cls is the MAJORITY label across the
    //    id's sightings so far, not the latest one -- a one-frame mislabel must not move it (field
    //    finding 2026-09-03: a Follow click during such a frame redirected the lock to a class with no
    //    live track).
    {
        // "cell phone","cell phone","knife","cell phone" -> majority stays "cell phone" throughout,
        // including the frame the stray "knife" sighting itself lands on.
        HailoTrackAdapter ad(5, 1);
        auto r1 = ad.update({{1, "cell phone", 0.9, 0, 0, 10, 10}});
        assert(r1.size() == 1 && r1[0].cls == "cell phone");
        auto r2 = ad.update({{1, "cell phone", 0.9, 0, 0, 10, 10}});
        assert(r2.size() == 1 && r2[0].cls == "cell phone");
        auto r3 = ad.update({{1, "knife", 0.9, 0, 0, 10, 10}});
        assert(r3.size() == 1 && r3[0].cls == "cell phone");
        auto r4 = ad.update({{1, "cell phone", 0.9, 0, 0, 10, 10}});
        assert(r4.size() == 1 && r4[0].cls == "cell phone");
    }
    {
        // "cell phone","knife","knife" -> first two sightings report "cell phone" (frame 2 is a 1-1 tie,
        // broken by earliest-first-seen label); "knife" takes the majority from the third sighting on.
        HailoTrackAdapter ad(5, 1);
        auto r1 = ad.update({{2, "cell phone", 0.9, 0, 0, 10, 10}});
        assert(r1.size() == 1 && r1[0].cls == "cell phone");
        auto r2 = ad.update({{2, "knife", 0.9, 0, 0, 10, 10}});
        assert(r2.size() == 1 && r2[0].cls == "cell phone");
        auto r3 = ad.update({{2, "knife", 0.9, 0, 0, 10, 10}});
        assert(r3.size() == 1 && r3[0].cls == "knife");
    }

    // 6) order stability: ids report in first-seen order across frames, regardless of a later frame's
    //    detection-array order (id 2 appears ahead of id 1 in frame 2's det list; id 1 was seen first).
    {
        HailoTrackAdapter ad(5, 1);
        ad.update({{1, "a", 0.9, 0, 0, 1, 1}});
        ad.update({{2, "b", 0.9, 0, 0, 1, 1}, {1, "a", 0.9, 0, 0, 1, 1}});
        auto r3 = ad.update({{1, "a", 0.9, 0, 0, 1, 1}, {2, "b", 0.9, 0, 0, 1, 1}, {3, "c", 0.9, 0, 0, 1, 1}});
        assert(r3.size() == 3);
        assert(r3[0].id == 1 && r3[1].id == 2 && r3[2].id == 3);
    }

    // --- on-board fix round 6 (Ruling 23): duplicate same-class LIVE track dedupe ---
    // Constructor is HailoTrackAdapter(keep_lost_frames, min_hits, dedupe_containment, dedupe_iou).

    // 7) full-body/torso duplicate, same origin: 819x600 wholly contains 655x600 -> only the larger
    //    (id 1) is emitted; id 2's Entry is untouched internally (it can still win a later frame).
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6);
        auto r = ad.update({{1, "person", 0.9, 0, 0, 819, 600}, {2, "person", 0.8, 0, 0, 655, 600}});
        assert(r.size() == 1 && r[0].id == 1);
    }

    // 8) same two box sizes, but shifted so only ~half of the smaller box's area is inside the larger
    //    one: containment (0.5) < 0.8 and IoU (~0.286) < 0.6 -> neither rule fires, both emitted.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6);
        auto r = ad.update({{1, "person", 0.9, 0, 0, 819, 600}, {2, "person", 0.8, 492, 0, 655, 600}});
        assert(r.size() == 2);
    }

    // 9) two same-class, same-size (equal-area) live records overlapping enough for IoU ~0.626 (>=
    //    0.6) while containment (0.77) stays below 0.8 -- the IoU rule fires and keeps the
    //    higher-confidence record (id 10, conf 0.9) over id 20 (conf 0.6).
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6);
        auto r = ad.update({{10, "person", 0.9, 0, 0, 100, 100}, {20, "person", 0.6, 23, 0, 100, 100}});
        assert(r.size() == 1 && r[0].id == 10);
    }

    // 10) different classes overlapping (a held phone fully inside the person box) -> dedupe never
    //     compares across classes, both emitted.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6);
        auto r = ad.update({{1, "person", 0.9, 0, 0, 200, 400}, {2, "cell phone", 0.8, 50, 50, 30, 60}});
        assert(r.size() == 2);
    }

    // 11) a COASTING duplicate is never a dedupe candidate, in either direction: id 1 and id 2 start
    //     far apart (no overlap, nothing to dedupe); id 1 then goes missing (coasting, box frozen at
    //     its last-seen place) while id 2's LIVE box moves to fully overlap that frozen box. Both must
    //     still be emitted -- the live box does not drop the coasting one, and the coasting box (never
    //     a comparator) cannot drop the live one either.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6);
        ad.update({{1, "person", 0.9, 0, 0, 100, 100}, {2, "person", 0.9, 500, 500, 100, 100}});
        auto r = ad.update({{2, "person", 0.9, 0, 0, 100, 100}});
        assert(r.size() == 2);
        auto it1 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 1; });
        auto it2 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 2; });
        assert(it1 != r.end() && it1->time_since_update == 1 && it1->bbox[0] == 0);
        assert(it2 != r.end() && it2->time_since_update == 0);
    }

    // 12) both dedupe thresholds 0 -> the rule is fully disabled, even for a wholly-contained pair
    //     that round 7's scenario would otherwise collapse to one record.
    {
        HailoTrackAdapter ad(5, 1, 0.0, 0.0);
        auto r = ad.update({{1, "person", 0.9, 0, 0, 819, 600}, {2, "person", 0.8, 0, 0, 655, 600}});
        assert(r.size() == 2);
    }

    // --- on-board fix round 7 (Ruling 24): the BIRTH confidence gate ---
    // Constructor is HailoTrackAdapter(keep_lost_frames, min_hits, dedupe_containment, dedupe_iou,
    // birth_conf). The SDK tracker births a track from ANY detection the post-process emits, with no
    // confidence floor of its own (mono's ByteTrack births only at track.high_thr 0.4) -- so a
    // 0.17-confidence "handbag" on a chair becomes a track and gets drawn (field finding, 2026-09-04:
    // /api/state carried handbag 0.19, backpack 0.19, handbag 0.17 tracks; the owner's "all over the
    // place"). An id must now have had ONE live detection at conf >= birth_conf before any of its
    // records are emitted.

    // 13) an id whose conf never reaches the gate is never emitted, live or coasting.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4);
        assert(ad.update({{1, "handbag", 0.19, 0, 0, 50, 50}}).empty());
        assert(ad.update({{1, "handbag", 0.31, 0, 0, 50, 50}}).empty());
        assert(ad.update({}).empty());                                    // and not while coasting either
    }

    // 14) birth on the frame the gate is first reached, and emitted from then on even when conf falls
    //     back below it or the id goes coasting: 0.2 (nothing) -> 0.45 (born, emitted) -> 0.1
    //     (still emitted) -> absent (coasting, still emitted).
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4);
        assert(ad.update({{1, "person", 0.2, 0, 0, 50, 50}}).empty());
        auto r2 = ad.update({{1, "person", 0.45, 0, 0, 50, 50}});
        assert(r2.size() == 1 && r2[0].id == 1 && r2[0].time_since_update == 0);
        auto r3 = ad.update({{1, "person", 0.1, 0, 0, 50, 50}});
        assert(r3.size() == 1 && r3[0].id == 1 && r3[0].conf == 0.1);
        auto r4 = ad.update({});
        assert(r4.size() == 1 && r4[0].id == 1 && r4[0].time_since_update == 1);
    }

    // 15) the born flag dies with the Entry: id 1 is born (conf 0.9), then absent long enough to be
    //     dropped (6 > keep_lost 5), then returns with a below-gate conf -> unborn again, not emitted
    //     until it clears the gate once more.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4);
        assert(ad.update({{1, "person", 0.9, 0, 0, 50, 50}}).size() == 1);
        for (int i = 0; i < 6; ++i) ad.update({});          // tsu climbs 1..6; erased once it exceeds 5
        assert(ad.update({{1, "person", 0.2, 0, 0, 50, 50}}).empty());
        assert(ad.update({{1, "person", 0.2, 0, 0, 50, 50}}).empty());
        assert(ad.update({{1, "person", 0.5, 0, 0, 50, 50}}).size() == 1);
    }

    // 16) birth_conf 0 disables the gate (and is the default): the 0.19 track of case 13 is emitted.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.0);
        assert(ad.update({{1, "handbag", 0.19, 0, 0, 50, 50}}).size() == 1);
        HailoTrackAdapter dflt(5, 1);
        assert(dflt.update({{1, "handbag", 0.19, 0, 0, 50, 50}}).size() == 1);
    }

    // 17) the gate runs BEFORE the dedupe pass, so an unborn record never takes part in dedupe: the
    //     full-body/torso pair of case 7, but the LARGER box (id 1) is below the gate. Without the
    //     ordering the larger unborn box would still suppress the smaller born one and the frame would
    //     publish nothing; with it, id 2 is the only record and survives.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4);
        auto r = ad.update({{1, "person", 0.2, 0, 0, 819, 600}, {2, "person", 0.8, 0, 0, 655, 600}});
        assert(r.size() == 1 && r[0].id == 2);
    }

    // --- on-board fix round 8 (Ruling 25): class allow-list ---
    // Constructor is HailoTrackAdapter(keep_lost_frames, min_hits, dedupe_containment, dedupe_iou,
    // birth_conf, classes). An empty `classes` (the default, case 16 above and every earlier case)
    // allows every class.

    // 18) allow-list ["person","cell phone"] emits those two and drops a "chair".
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.0, {"person", "cell phone"});
        auto r = ad.update({{1, "person", 0.9, 0, 0, 10, 10},
                             {2, "cell phone", 0.9, 100, 0, 10, 10},
                             {3, "chair", 0.9, 200, 0, 10, 10}});
        assert(r.size() == 2);
        auto it1 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 1; });
        auto it2 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 2; });
        auto it3 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 3; });
        assert(it1 != r.end() && it2 != r.end() && it3 == r.end());
    }

    // 19) empty list (explicit, not just the default-argument case) emits all classes.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.0, {});
        auto r = ad.update({{1, "person", 0.9, 0, 0, 10, 10},
                             {2, "cell phone", 0.9, 100, 0, 10, 10},
                             {3, "chair", 0.9, 200, 0, 10, 10}});
        assert(r.size() == 3);
    }

    // 20) the allow-list applies BEFORE the birth gate: a disallowed "chair" sighting at high conf
    //     must not count toward id 1's birth. If it did, id 1 would already read as born by the time
    //     the allowed-but-below-gate "person" sighting arrives, and that frame would wrongly emit a
    //     record. Sequence: chair@0.9 (disallowed, dropped outright) -> person@0.2 (allowed, below
    //     birth_conf 0.4, must stay unborn) -> person@0.5 (crosses the gate, now emitted).
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4, {"person"});
        assert(ad.update({{1, "chair", 0.9, 0, 0, 50, 50}}).empty());
        assert(ad.update({{1, "person", 0.2, 0, 0, 50, 50}}).empty());
        auto r = ad.update({{1, "person", 0.5, 0, 0, 50, 50}});
        assert(r.size() == 1 && r[0].id == 1 && r[0].cls == "person");
    }

    // 21) the allow-list applies BEFORE dedupe: a disallowed "chair" (id 3, high conf) never becomes a
    //     candidate or comparator, but the round-6 dedupe pass still runs normally on the two allowed
    //     "person" records (id 1's box wholly contains id 2's -> id 2 is dropped as in case 7).
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.0, {"person"});
        auto r = ad.update({{1, "person", 0.9, 0, 0, 819, 600},
                             {2, "person", 0.8, 0, 0, 655, 600},
                             {3, "chair", 0.95, 999, 999, 50, 50}});
        assert(r.size() == 1 && r[0].id == 1);
    }

    // --- on-board fix round 9 (Ruling 26): live_raw() -- the CORE's input ---
    // update() returns the PUBLISHED list (birth gate + dedupe applied); live_raw() returns this
    // frame's LIVE records after the class allow-list ONLY. node_main.cpp feeds live_raw() to
    // LockCore, so an existing lock can be maintained on a detection the display never shows, while
    // a NEW lock (resolver auto-acquire / click) still needs a published track.

    // 22) a below-birth_conf id is absent from update() and present in live_raw().
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4);
        auto pub = ad.update({{1, "cell phone", 0.3, 10, 10, 30, 60}});
        assert(pub.empty());                               // never born -> not published
        auto raw = ad.live_raw();
        assert(raw.size() == 1 && raw[0].id == 1 && raw[0].cls == "cell phone");
        assert(raw[0].time_since_update == 0 && raw[0].conf == 0.3);
    }

    // 23) a DEDUPED duplicate is absent from update() and present in live_raw(): case 7's
    //     full-body/torso pair, both born, the smaller suppressed for the display.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.4);
        auto pub = ad.update({{1, "person", 0.9, 0, 0, 819, 600}, {2, "person", 0.8, 0, 0, 655, 600}});
        assert(pub.size() == 1 && pub[0].id == 1);
        auto raw = ad.live_raw();
        assert(raw.size() == 2 && raw[0].id == 1 && raw[1].id == 2);
    }

    // 24) live_raw() honours the class allow-list (the ONLY filter it applies) and carries no
    //     COASTING record: a disallowed "chair" never appears, and an id that went missing this
    //     frame is in update()'s output (coasting) but not in live_raw().
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.0, {"person"});
        ad.update({{1, "person", 0.9, 0, 0, 50, 50}});
        auto pub = ad.update({{2, "person", 0.9, 500, 500, 50, 50}, {3, "chair", 0.95, 900, 0, 50, 50}});
        assert(pub.size() == 2);                            // id 1 coasting + id 2 live; no chair
        auto raw = ad.live_raw();
        assert(raw.size() == 1 && raw[0].id == 2);          // live + allowed only
    }

    // --- on-board fix round 9 (Ruling 27): dedupe protects established/locked identities ---
    // The reviewer's probe: two DISTINCT people, the selected id 1 partly behind the nearer id 2.
    // Containment alone cannot tell that from one person detected twice, so the age of the record
    // and the lock's own id are what break the tie: a duplicate BIRTH is still suppressed, an
    // ESTABLISHED track (>= dedupe_protect_age frames since its first emission) is not.

    // 25) id 1 established (10 emitted frames) -> BOTH survive the containment rule.
    {
        HailoTrackAdapter ad(75, 1, 0.8, 0.6, 0.4, {}, 10);
        for (int f = 0; f < 10; ++f) ad.update({{1, "person", 0.9, 100, 100, 100, 200}});
        auto r = ad.update({{1, "person", 0.9, 100, 100, 100, 200},
                             {2, "person", 0.9, 80, 80, 160, 260}});
        assert(r.size() == 2);
        auto it1 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 1; });
        auto it2 = std::find_if(r.begin(), r.end(), [](auto& rec) { return rec.id == 2; });
        assert(it1 != r.end() && it2 != r.end());
    }

    // 26) the same pair with id 1 only ONE frame old (the reviewer's own probe, verbatim) -> id 1 is
    //     still young enough to be a duplicate birth, so it is suppressed and only id 2 survives.
    {
        HailoTrackAdapter ad(75, 1, 0.8, 0.6, 0.4, {}, 10);
        ad.update({{1, "person", 0.9, 100, 100, 100, 200}});
        auto r = ad.update({{1, "person", 0.9, 100, 100, 100, 200},
                             {2, "person", 0.9, 80, 80, 160, 260}});
        assert(r.size() == 1 && r[0].id == 2);
    }

    // 27) the PROTECTED id (the lock's own) is never dropped, however young: the same one-frame-old
    //     id 1 of case 26 survives once the node marks it as the locked identity, and clearing the
    //     protection (-1) restores case 26's outcome on the next frame.
    {
        HailoTrackAdapter ad(75, 1, 0.8, 0.6, 0.4, {}, 10);
        ad.update({{1, "person", 0.9, 100, 100, 100, 200}});
        ad.set_protected_id(1);
        auto r = ad.update({{1, "person", 0.9, 100, 100, 100, 200},
                             {2, "person", 0.9, 80, 80, 160, 260}});
        assert(r.size() == 2);
        ad.set_protected_id(-1);
        auto r2 = ad.update({{1, "person", 0.9, 100, 100, 100, 200},
                              {2, "person", 0.9, 80, 80, 160, 260}});
        assert(r2.size() == 1 && r2[0].id == 2);
    }

    // 28) the IoU rule obeys the same protection: case 9's pair (IoU ~0.626, containment 0.77) would
    //     drop the lower-confidence id 20, but with id 20 protected both survive.
    {
        HailoTrackAdapter ad(5, 1, 0.8, 0.6, 0.0, {}, 10);
        ad.set_protected_id(20);
        auto r = ad.update({{10, "person", 0.9, 0, 0, 100, 100}, {20, "person", 0.6, 23, 0, 100, 100}});
        assert(r.size() == 2);
    }

    // 29) dedupe_protect_age 0 disables the age half of the rule entirely (only the protected id is
    //     ever spared), which is the pre-round-9 behaviour for every unprotected record: case 25's
    //     established id 1 is dropped again.
    {
        HailoTrackAdapter ad(75, 1, 0.8, 0.6, 0.4, {}, 0);
        for (int f = 0; f < 10; ++f) ad.update({{1, "person", 0.9, 100, 100, 100, 200}});
        auto r = ad.update({{1, "person", 0.9, 100, 100, 100, 200},
                             {2, "person", 0.9, 80, 80, 160, 260}});
        assert(r.size() == 1 && r[0].id == 2);
    }

    std::cout << "hailo_track_adapter unit cases ok\n";
    return 0;
}
