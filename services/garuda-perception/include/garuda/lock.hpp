#pragma once
#include "garuda/bytetrack.hpp"
#include "garuda/track_record.hpp"
#include <optional>
#include <string>
#include <utility>
#include <vector>

// Port of mono's lock/coast/re-acquire loop and click/target handlers (hosts/pi5/garuda_mono.py, loop
// body lines 229-249 and POST handlers 487-512), pinned by the parity oracle at
// tests/golden/mono_lock_ref.py (functions step_lock/click) and driven exactly as
// tests/golden/make_track_golden.py drives it. Lives in garuda::track (not bare garuda) because
// garuda::Track (include/garuda/snapshot.hpp) is a different, unrelated type.
namespace garuda {
namespace track {

struct LockResult {
    std::optional<int> lock_id;
    std::string lock_class;
    bool coasting = false;
    // Copies (not pointers): every track engine's records survive independently of that engine's own
    // storage, so alive has no pointer-lifetime rule to document.
    std::vector<TrackRecord> alive;
};

class LockResolver {
public:
    // auto_min_conf / auto_edge_margin_frac gate the AUTO-ACQUIRE branch of step() only (on-board fix
    // round 1, Ruling 16.1): a candidate the resolver picks up on its own must have
    // `conf >= auto_min_conf` and its box must be clear of the LEFT and RIGHT frame edges by
    // `auto_edge_margin_frac * frame_w`. Top/bottom are deliberately NOT gated — a person close to the
    // camera legitimately spans the full frame height. Run 1 (bench/benchlog.md 2026-09-04, "Run 1 ...
    // edge-entry failure") is why: the resolver auto-acquired a 29x194 px, conf 0.17 sliver of a person
    // still entering at the right edge (x+w == 1280), which then seeded LockCore with a size reference
    // no later frame of that person could match.
    // auto_min_streak (on-board fix round 2, Ruling 18) additionally requires the candidate to have
    // passed that conf+edge test on this many frames as a LIVE record (time_since_update == 0)
    // before it may be picked up. Run 2 (bench/benchlog.md 2026-09-04, "Run 2 ... junk-track lock")
    // is why: the person profile carried several persistent low-confidence "person" tracks on static
    // room objects, and one of them (id 25, conf mostly 0.15-0.37) flickered over 0.5 for a single
    // frame, passed the conf+edge gate on that frame, and held the lock for the rest of the 120 s
    // capture. A single frame is not evidence; five are.
    //
    // auto_streak_window (on-board fix round 7, Ruling 24) is the span those frames are counted over:
    // auto_min_streak gate-passing live frames within the LAST auto_streak_window frames in which
    // that id appeared, not auto_min_streak CONSECUTIVE ones as round 2 had it. Round 2's rule was
    // unreachable for an intermittently-detected target: in the round-7 capture the phone was a live
    // box in only 30.2 % of frames, so five consecutive gate-passing frames essentially never
    // happened and, once the clicked lock expired, auto-acquire never re-locked it (LOST for 68 % of
    // rows -- bench/benchlog.md F1, "Round 7"). A window of 15 at ~30 fps is half a second, and 5 of
    // 15 still refuses run 2's lone flicker (a single frame's credit ages out with nothing to join
    // it). Either auto_min_streak or auto_streak_window set to 0 disables the streak test entirely.
    // A coasting frame is not a reset any more, merely a frame that contributes nothing; the test is
    // still live-only, since only live frames are ever counted.
    //
    // The SAME conf+edge+streak test gates the re-acquire jump (a coasting lock moving to the best
    // live same-class track after `reacq` frames) -- that path could otherwise hand the lock to
    // exactly the junk flicker this gate exists to refuse. LockCore's own re-acquisition is separate
    // and unaffected.
    //
    // All three DEFAULT TO OFF here (conf 0 admits everything; a zero margin skips the edge test; a
    // zero streak requires nothing), because a default-constructed LockResolver is what
    // tests/test_lock.cpp replays the pinned mono parity golden through (tests/golden/mono_lock_ref.py
    // has no such gate). The node always passes the live config's values from the `lock` block — see
    // garuda::lock::Params.
    LockResolver(int max_lost = 25, int reacq = 5, std::string default_class = "person",
                 double auto_min_conf = 0.0, double auto_edge_margin_frac = 0.0, int frame_w = 1280,
                 int auto_min_streak = 0, int auto_streak_window = 0);

    // Engine-neutral. Call once per frame with that frame's records (in the producing engine's stable
    // per-frame order). Resolves/holds/coasts/re-acquires the lock exactly as before and publishes this
    // frame's alive-record list for the next click(). alive = records with confirmed && tsu <= max_lost.
    LockResult step(const std::vector<TrackRecord>& records);

    // ByteTrack convenience: builds records from tracker.tracks() (same order) and calls step(records)
    // above. Behaviour is identical to the pre-refactor step(const ByteTracker&).
    LockResult step(const ByteTracker& tracker);

    // Uses the alive tracks published by the PREVIOUS step() (a click before any step() picks nothing).
    // Prefers the smallest box containing the point, else the nearest box centre; on a pick, sets the
    // lock to that track's id and the target class to that track's label. Returns whether something was picked.
    bool click(double cx, double cy);

    // Sets the target class (empty string -> the default class) and clears the current lock.
    void set_target(const std::string& cls);

    std::optional<int> lock_id() const { return m_lid; }
    const std::string& target_class() const { return m_class; }

private:
    struct PrevTrack { int id; std::string cls; double bbox[4]; };

    // Conf + edge half of the gate (see the constructor comment) -- no streak involved.
    bool gate_ok(const TrackRecord& t) const;
    // Full test: conf + edge + streak. Used by BOTH the auto-acquire branch and the re-acquire jump.
    bool auto_acquirable(const TrackRecord& t) const;
    // How many of the frames in this id's window were live AND gate_ok (0 if the id has no window).
    int gated_frames_of(int id) const;
    // Rebuilds m_streak from this frame's records: appends 1 for an id that is live and passes
    // gate_ok and 0 for one that is coasting or fails it, trims each history to auto_streak_window,
    // and carries nothing at all for an id that is not in `records` (so an id that has gone away
    // takes its window with it rather than leaving a stale one behind -- this is what bounds the
    // bookkeeping to the ids currently in flight).
    void update_streaks(const std::vector<TrackRecord>& records);

    int m_max_lost;
    int m_reacq;
    double m_auto_min_conf;
    double m_auto_edge_margin_frac;
    int m_frame_w;
    int m_auto_min_streak;
    int m_auto_streak_window;
    // Per-id sliding window of the last auto_streak_window frames' gate results (1 = live and
    // gate_ok), oldest first. A plain vector of plain vectors, rebuilt each frame: a frame carries a
    // handful of tracks and a window is ~15 bytes, so linear scans beat any node-based map and keep
    // this header free of another include.
    struct StreakEntry { int id; std::vector<unsigned char> hist; };
    std::vector<StreakEntry> m_streak;
    std::string m_default;
    std::string m_class;
    std::optional<int> m_lid;
    std::vector<PrevTrack> m_prev;
};

} // namespace track
} // namespace garuda
