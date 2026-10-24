#include "garuda/lock.hpp"
#include <utility>
#include <vector>

// Comments cite tests/golden/mono_lock_ref.py (step_lock/click), the pinned Python parity oracle.
namespace garuda {
namespace track {

LockResolver::LockResolver(int max_lost, int reacq, std::string default_class,
                           double auto_min_conf, double auto_edge_margin_frac, int frame_w,
                           int auto_min_streak, int auto_streak_window)
    : m_max_lost(max_lost), m_reacq(reacq), m_auto_min_conf(auto_min_conf),
      m_auto_edge_margin_frac(auto_edge_margin_frac), m_frame_w(frame_w),
      m_auto_min_streak(auto_min_streak), m_auto_streak_window(auto_streak_window),
      m_default(std::move(default_class)), m_class(m_default) {}

namespace {
// The streak test is off unless BOTH a minimum count and a window to count it over are configured
// (Ruling 24) -- a window with no minimum asks nothing, and a minimum with no window has nothing to
// count in. Off means the bookkeeping is skipped outright, not merely satisfied by arithmetic.
bool streak_test_enabled(int min_streak, int window) { return min_streak > 0 && window > 0; }
} // namespace

// Conf + edge half of the resolver's admission test (Ruling 16.1). A zero margin fraction disables the
// edge test entirely (rather than degrading to "must be strictly inside the frame"), so the pinned
// mono-parity replay is unaffected by the defaults.
bool LockResolver::gate_ok(const TrackRecord& t) const {
    if (t.conf < m_auto_min_conf) return false;
    if (m_auto_edge_margin_frac > 0.0) {
        const double margin = m_auto_edge_margin_frac * static_cast<double>(m_frame_w);
        const double x = t.bbox[0], w = t.bbox[2];
        if (x < margin || x + w > static_cast<double>(m_frame_w) - margin) return false;
    }
    return true;
}

int LockResolver::gated_frames_of(int id) const {
    for (const auto& s : m_streak) {
        if (s.id != id) continue;
        int n = 0;
        for (unsigned char f : s.hist) n += f ? 1 : 0;
        return n;
    }
    return 0;
}

// Called once per step(), BEFORE either acquiring branch, so a candidate whose Nth gate-passing frame
// within the window is this one is acquirable on that very frame (Rulings 18 + 24).
void LockResolver::update_streaks(const std::vector<TrackRecord>& records) {
    if (!streak_test_enabled(m_auto_min_streak, m_auto_streak_window)) { m_streak.clear(); return; }
    const size_t window = static_cast<size_t>(m_auto_streak_window);
    std::vector<StreakEntry> next;
    next.reserve(records.size());
    for (const auto& t : records) {
        StreakEntry e;
        e.id = t.id;
        for (const auto& s : m_streak)
            if (s.id == t.id) { e.hist = s.hist; break; }   // ids absent from this frame are not carried
        e.hist.push_back(t.time_since_update == 0 && gate_ok(t) ? 1 : 0);
        if (e.hist.size() > window)                          // drop whatever has aged out of the window
            e.hist.erase(e.hist.begin(), e.hist.end() - static_cast<long>(window));
        next.push_back(std::move(e));
    }
    m_streak.swap(next);
}

// Full admission test (Rulings 16.1 + 18 + 24): conf, edge, and enough live gate-passing frames inside
// the window. Used by the "acquire best of class" branch AND by the re-acquire jump -- an explicit
// click is the user's own choice and is never second-guessed, and LockCore's re-acquisition is its
// own, separate mechanism.
bool LockResolver::auto_acquirable(const TrackRecord& t) const {
    if (!gate_ok(t)) return false;
    if (!streak_test_enabled(m_auto_min_streak, m_auto_streak_window)) return true;
    return gated_frames_of(t.id) >= m_auto_min_streak;
}

LockResult LockResolver::step(const std::vector<TrackRecord>& records) {      // step_lock
    LockResult r;
    r.lock_class = m_class;
    update_streaks(records);   // Ruling 18 -- before either acquiring branch below
    for (auto& t : records)
        if (t.confirmed && t.time_since_update <= m_max_lost) r.alive.push_back(t);   // alive

    // Pointers into r.alive are safe from here on: r.alive is never appended to again below.
    const TrackRecord* locked = nullptr;
    if (m_lid)
        for (auto& t : r.alive)
            if (t.id == *m_lid) { locked = &t; break; }

    if (!locked && !m_class.empty()) {                                        // acquire best of class: live first, then conf
        for (auto& t : r.alive)
            if (t.cls == m_class && auto_acquirable(t)) {   // Ruling 16.1 -- gate, order otherwise unchanged
                if (!locked) { locked = &t; continue; }
                bool tl = t.time_since_update == 0, ll = locked->time_since_update == 0;
                if (std::make_pair(tl, t.conf) > std::make_pair(ll, locked->conf)) locked = &t;  // Python max() keeps the FIRST max
            }
    } else if (locked && locked->time_since_update > m_reacq && !m_class.empty()) {   // re-acquire jump
        const TrackRecord* best = nullptr;
        for (auto& t : r.alive)   // Ruling 18: the jump is gated exactly like an auto-acquire
            if (t.cls == m_class && t.time_since_update == 0 && auto_acquirable(t)
                && (!best || t.conf > best->conf)) best = &t;
        if (best) locked = best;
    }

    m_lid = locked ? std::optional<int>(locked->id) : std::nullopt;
    r.lock_id = m_lid;
    r.coasting = locked ? locked->time_since_update > 0 : false;

    m_prev.clear();
    for (auto& t : r.alive) m_prev.push_back({t.id, t.cls, {t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3]}});
    return r;
}

LockResult LockResolver::step(const ByteTracker& tracker) {
    std::vector<TrackRecord> records;
    records.reserve(tracker.tracks().size());
    for (auto& t : tracker.tracks())
        records.push_back({t.track_id, t.cls, t.conf,
                            {t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3]},
                            t.time_since_update, t.confirmed()});
    return step(records);
}

bool LockResolver::click(double cx, double cy) {                              // click
    bool picked = false;
    std::pair<int, double> best_key{};
    int best_id = 0;
    std::string best_cls;
    for (auto& t : m_prev) {
        double x = t.bbox[0], y = t.bbox[1], w = t.bbox[2], h = t.bbox[3];
        bool inside = (x <= cx && cx <= x + w) && (y <= cy && cy <= y + h);
        double dx = x + w / 2 - cx, dy = y + h / 2 - cy;
        double d2 = dx * dx + dy * dy;
        std::pair<int, double> key = inside ? std::make_pair(0, w * h) : std::make_pair(1, d2);
        if (!picked || key < best_key) { best_key = key; best_id = t.id; best_cls = t.cls; picked = true; }
    }
    if (picked) { m_lid = best_id; m_class = best_cls; }
    return picked;
}

void LockResolver::set_target(const std::string& cls) {
    m_class = cls.empty() ? m_default : cls;
    m_lid = std::nullopt;
}

} // namespace track
} // namespace garuda
