#pragma once
#include "garuda/track_record.hpp"
#include <string>
#include <utility>
#include <vector>

// Adapts the SDK's Kalman tracker (which hands back per-frame detections already carrying a unique,
// persistent id — no association step of our own is needed) into the engine-neutral TrackRecord stream
// that LockResolver::step(const std::vector<TrackRecord>&) consumes. Unlike ByteTrack, this engine
// never re-predicts a missing box: a coasting record's bbox is simply the last-seen box, held frozen
// until the id is dropped.
//
// The SDK tracker is class-agnostic: every detection in a frame, of any label, competes in the SAME
// one-to-one LAPJV assignment against the same pool of tracks -- there is no per-class matching at all
// (see hosts/hailo15l/README.md's classification_id note, corrected 2026-09-04, for the full
// mechanism). One consequence: the box that wins a given id's assignment can come from a different-
// class detection on a single stray frame (e.g. a held phone flickering to "knife" or "tv"),
// relabelling that id for that frame. Reporting that frame's label verbatim let a Follow click at that
// instant redirect the lock to a class with no live track (field finding, 2026-09-03: lock showed
// nothing for 43% of a run). So cls is the MAJORITY label across the id's sightings so far, not the
// latest one — a one-frame mislabel cannot move it.
//
// On-board fix round 6 (Ruling 23): the HEF's baked NMS does not suppress a smaller box wholly (or
// mostly) contained inside a larger one, so the same physical person can produce two simultaneous
// detections -- a full-body box and a torso box -- that the SDK's one-to-one LAPJV assignment happily
// births into TWO separate tracks (field finding, run 8: ids 38/39 alternating on one person, boxes
// ~819 vs ~655 px wide, `id churn 41` -- bench/benchlog.md F1 section). update() therefore dedupes its
// own LIVE (time_since_update == 0) output, same-class only, before returning it: a smaller live box
// mostly inside a larger live box of the same class is dropped (dedupe_containment, fraction of the
// smaller box's OWN area that lies inside the larger box); failing that, two same-class live boxes
// with high IoU keep only the higher-confidence one (dedupe_iou). A dropped record is simply not
// emitted this frame -- its Entry is untouched, so it can still win next frame if the duplicate
// detection doesn't recur. COASTING records (tsu > 0) are never compared against anything and never
// dropped: a frozen last-seen box that happens to now overlap a live box of the same class is not a
// duplicate detection, just stale geometry. Either threshold set to 0 disables that rule.
//
// On-board fix round 7 (Ruling 24): the SDK tracker births a track from ANY detection the post-process
// hands it -- it has no confidence floor of its own, unlike mono's ByteTrack, which births only at
// track.high_thr (0.4). Every one of those tracks reached the snapshot and was drawn by the GUI, so a
// cluttered room filled the view with junk boxes (field finding, 2026-09-04: /api/state carried
// "handbag" 0.19, "backpack" 0.19, "handbag" 0.17 tracks; the owner's report was that the display is
// "all over the place" -- bench/benchlog.md F1 section, "Round 7"). update() therefore emits records
// only for ids that have been BORN: an id is born the first frame it is seen LIVE with
// conf >= birth_conf, and stays born for as long as its Entry lives (so a later low-conf or coasting
// frame of the same id still publishes). The flag dies with the Entry -- an id dropped after
// keep_lost_frames and then reused must earn its birth again. The gate runs BEFORE the dedupe pass
// above, so an unborn record can neither be dropped by dedupe nor suppress a born one. birth_conf 0
// disables the gate (the default, which is what the mono-parity path and the unit golden expect).
//
// On-board fix round 8 (Ruling 25): the SDK tracker has no per-class matching mode at all (see the
// class-agnostic note above) -- classification_id restricts which class(es) ever reach the tracker,
// but it allows exactly ONE class id, so a demo that must show more than one class (e.g. person +
// phone) has to run classification_id -1 (every class) and take the resulting clutter: a 120 s
// all-classes capture on real room objects emitted 15274 track entries over 3063 rows -- chair 3885,
// handbag 3137, toilet (a ring light) 2298, laptop 1905, suitcase 1379, person 989 -- every one of
// which passes the round-7 birth gate at least once (bench/benchlog.md F1 section, "Round 8"). `classes`
// is a class allow-list applied to `seen` BEFORE any bookkeeping: a detection whose label is not in the
// list is dropped before it can create or update an Entry, so it never contributes to that id's label
// majority, never sets `born`, and is never a dedupe candidate or comparator -- a disallowed sighting
// cannot contaminate or suppress an allowed one. An empty list (the default) allows every class,
// unchanged from before this round.
//
// On-board fix round 9 (Ruling 26): the two rounds above are DISPLAY gates -- they exist so the GUI
// is not filled with junk boxes and duplicate silhouettes -- and until this round they also decided
// what the lock core was allowed to see, because node_main.cpp built LockCore's `live_obs` from
// update()'s output. That conflated two different questions: "should this box be drawn and offered
// as a NEW lock candidate?" (yes, gate it) and "may the core keep tracking the object it already
// holds using this box?" (yes, always -- a locked phone dropping to conf 0.3 for a second is
// precisely when the core needs the measurement most). `live_raw()` publishes the second answer:
// this frame's LIVE records after the class allow-list ONLY -- no birth gate, no dedupe. The node
// hands live_raw() to LockCore::update() and keeps the published (gated + deduped) list for the
// snapshot, the resolver's step(), and the two paths that can create a NEW lock (a click, the
// resolver's class auto-acquire). So: maintaining or recovering an existing lock may use any live
// detection; taking a new one still needs a published track.
//
// On-board fix round 9 (Ruling 27): the round-6 dedupe cannot distinguish "one person detected
// twice" from "one person standing behind another", and in the second case it silently deletes the
// farther person -- who may be the locked target (outside review, 2026-09-05: two overlapping people,
// only the nearer id survived). Two things break that tie without appearance evidence:
//   - `set_protected_id(id)`: the node passes the resolver's current lock id every frame (or -1).
//     A record carrying it is never dropped by either rule.
//   - a per-id AGE (frames since the id's first EMISSION, i.e. since it passed the birth gate).
//     A record may be suppressed only while its age is below `dedupe_protect_age`.
// A duplicate BIRTH -- the full-body/torso pair that round 6 exists for -- appears and disappears
// within a frame or two, so it is always young and still suppressed. A track that has been emitted
// for `dedupe_protect_age` frames has earned an identity of its own and is kept even when a nearer
// box swallows it. `dedupe_protect_age` 0 restores the pre-round-9 behaviour for every record except
// the protected one.
namespace garuda {
namespace track {

// One detection for the current frame, as reported by the SDK tracker: it already knows the id.
struct IdDet {
    int id;
    std::string label;
    double conf;
    double x, y, w, h;
};

class HailoTrackAdapter {
public:
    HailoTrackAdapter(int keep_lost_frames = 5, int min_hits = 1,
                       double dedupe_containment = 0.8, double dedupe_iou = 0.6,
                       double birth_conf = 0.0,
                       std::vector<std::string> classes = {},
                       int dedupe_protect_age = 10);

    // Round 9 (Ruling 27): the identity the dedupe pass must never suppress -- the node passes the
    // resolver's current lock id each frame, or -1 for "nothing locked". Takes effect on the NEXT
    // update(); it is a plain setter, not a filter of its own.
    void set_protected_id(int id) { m_protected_id = id; }

    // One frame: the detections seen now (with ids). Returns records for every id seen now (tsu=0, its
    // box) and every id missing for 1..keep_lost_frames frames (tsu=k, the LAST SEEN box unchanged);
    // ids missing longer are dropped. cls = the majority label across all of the id's sightings so far,
    // ties broken by whichever tied label was first seen; conf = the latest sighting's conf. confirmed =
    // hits >= min_hits (hits counts frames in which the id was seen). Order: by first-seen order
    // (stable), less any record of an id not yet BORN (birth_conf gate, applied first) and any record
    // dropped by the same-class LIVE dedupe pass described above the class. Round 8: `seen` is first
    // filtered by the `classes` allow-list (see the class comment) -- a disallowed detection is dropped
    // before any of the above ever sees it.
    // `ts_ms` (on-board fix round 10, Ruling 32b) is this frame's timestamp on LockCore's own clock
    // (the ISP clock in ms). The FIRST frame an id is seen -- at any confidence, after the class
    // allow-list -- stamps that id's `first_seen_ms`, which every later record of that id carries
    // until its Entry is erased. Any confidence deliberately: the question the field answers is
    // "when did this object first exist as far as the tracker is concerned", which the birth gate's
    // confidence floor would only delay and distort. The default -1 keeps every pre-round-10 caller
    // (and the unit tests that do not care) compiling, and publishes -1, which LockCore reads as
    // "unknown, treat as pre-existing".
    std::vector<TrackRecord> update(const std::vector<IdDet>& seen, double ts_ms = -1.0);

    // Round 9 (Ruling 26): the LAST update() call's LIVE records (time_since_update == 0) after the
    // class allow-list and nothing else -- no birth gate, no dedupe, no coasting entries. This is
    // LockCore's input; update()'s return value is what the display and the resolver see. Same
    // first-seen order as update(). Empty before the first update().
    const std::vector<TrackRecord>& live_raw() const { return m_live_raw; }

private:
    struct Entry {
        int id;
        // Per-label sighting counts, in the order each distinct label was first seen for this id — that
        // order is what makes the tie-break "earliest-first-seen label" a plain linear scan (see cls()).
        std::vector<std::pair<std::string, int>> label_counts;
        double conf;            // latest sighting's conf (unlike cls, this does track the latest sighting)
        double bbox[4];
        int tsu;
        int hits;
        // Sticky for the Entry's lifetime: set the first frame this id is seen live at
        // conf >= birth_conf, and gone the moment the Entry is erased (see the round-7 note above).
        bool born;
        // Round 9 (Ruling 27): frames in which this Entry has been EMITTED so far (i.e. reached the
        // pre-dedupe output list). Read before this frame's own increment, so it is "frames since
        // first emission" -- 0 on the frame an id is born, 10 once it has been published 10 times.
        // Dies with the Entry, exactly like `born`.
        int emits;
        // Round 10 (Ruling 32b): the ts_ms of the frame this id was first seen on, or -1 if the
        // caller did not supply one. Set once at creation and never updated; dies with the Entry, so
        // an id that expires and is later reused is correctly stamped with its NEW birth time.
        double first_seen_ms;

        std::string cls() const {
            const std::pair<std::string, int>* best = nullptr;
            for (auto& lc : label_counts)
                if (!best || lc.second > best->second) best = &lc;   // strict '>': first max seen wins ties
            return best ? best->first : std::string();
        }
    };

    int m_keep_lost;
    int m_min_hits;
    double m_dedupe_containment;    // 0 disables the containment rule
    double m_dedupe_iou;            // 0 disables the IoU rule
    double m_birth_conf;            // 0 (or less) disables the birth gate
    std::vector<std::string> m_classes;   // empty = every class allowed (round 8, Ruling 25)
    int m_dedupe_protect_age;       // 0 (or less) -> only the protected id is spared (round 9)
    int m_protected_id = -1;        // the lock's own id; -1 = nothing protected (round 9)
    std::vector<Entry> m_entries;   // kept in first-seen order: only ever appended to, never reordered
    std::vector<TrackRecord> m_live_raw;   // last update()'s live, allow-listed records (round 9)
};

} // namespace track
} // namespace garuda
