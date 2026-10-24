#include "garuda/bytetrack.hpp"
#include <algorithm>
#include <set>
#include <tuple>
#include <utility>

// Comments cite lines in tests/golden/bytetrack_ref.py (the pinned Python reference / parity oracle).
namespace garuda {
namespace track {

double iou_xywh(const double a[4], const double b[4]) {                       // _iou
    double x1 = std::max(a[0], b[0]), y1 = std::max(a[1], b[1]);
    double x2 = std::min(a[0] + a[2], b[0] + b[2]), y2 = std::min(a[1] + a[3], b[1] + b[3]);
    double inter = std::max(0.0, x2 - x1) * std::max(0.0, y2 - y1);
    double uni = a[2] * a[3] + b[2] * b[3] - inter;
    return uni > 0 ? inter / uni : 0.0;
}

void Track::predict() {                                                       // Track.predict
    bbox[0] += vel[0]; bbox[1] += vel[1];
    age += 1; time_since_update += 1;
}

void Track::update(const double b[4], const std::string& c, double s) {       // Track.update
    double nx = b[0], ny = b[1];
    vel[0] = nx - last_x; vel[1] = ny - last_y;                               // displacement since last update
    last_x = nx; last_y = ny;
    bbox[0] = nx; bbox[1] = ny; bbox[2] = b[2]; bbox[3] = b[3];
    cls = c; conf = s; hits += 1; time_since_update = 0;
}

ByteTracker::ByteTracker(double h, double l, double i, int ml, int mh)
    : m_high(h), m_low(l), m_iou(i), m_max_lost(ml), m_min_hits(mh) {}

// _greedy_match: pairs sorted by descending (iou, ti, di) tuple -- Python's `pairs.sort(reverse=True)`.
// ut/ud are built as `set(range(N))` and thereafter only ever `discard()`ed, never added to -- so
// CPython's underlying hash table is sized to hold at least N from construction and never shrinks or
// rehashes smaller as elements are removed. That keeps iteration order ascending for every N, not just
// small ints (small-int identity hashing is irrelevant here since the table never resizes downward);
// std::set<int> (ordered, ascending) matches this by construction, not by coincidence of small values.
static void greedy_match(const std::vector<Track*>& tracks, const std::vector<const Det*>& dets, double thr,
                          std::vector<std::pair<int, int>>& matches, std::set<int>& ut, std::set<int>& ud) {
    std::vector<std::tuple<double, int, int>> pairs;
    for (int ti = 0; ti < (int)tracks.size(); ++ti)
        for (int di = 0; di < (int)dets.size(); ++di) {
            double b[4] = {dets[di]->x, dets[di]->y, dets[di]->w, dets[di]->h};
            double v = iou_xywh(tracks[ti]->bbox, b);
            if (v >= thr) pairs.emplace_back(v, ti, di);
        }
    std::sort(pairs.begin(), pairs.end(), [](const auto& a, const auto& b) { return a > b; }); // pairs.sort(reverse=True)
    for (int i = 0; i < (int)tracks.size(); ++i) ut.insert(i);
    for (int i = 0; i < (int)dets.size(); ++i) ud.insert(i);
    for (auto& p : pairs) {
        int ti = std::get<1>(p), di = std::get<2>(p);
        if (ut.count(ti) && ud.count(di)) { matches.emplace_back(ti, di); ut.erase(ti); ud.erase(di); }
    }
}

std::vector<const Track*> ByteTracker::update(const std::vector<Det>& dets) {
    for (auto& t : m_tracks) t.predict();                                     // "for t in self.tracks: t.predict()"

    std::vector<const Det*> high, low;                                       // high = [d if d[2]>=high]; low = [elif low<=d[2]<high]
    for (auto& d : dets) {
        if (d.conf >= m_high) high.push_back(&d);
        else if (d.conf >= m_low) low.push_back(&d);
    }

    std::vector<Track*> all;
    for (auto& t : m_tracks) all.push_back(&t);
    std::vector<std::pair<int, int>> m1;
    std::set<int> ut, ud;
    greedy_match(all, high, m_iou, m1, ut, ud);                               // stage 1: high-score dets vs all tracks
    for (auto& pr : m1) {
        const Det* d = high[pr.second];
        double b[4] = {d->x, d->y, d->w, d->h};
        all[pr.first]->update(b, d->label, d->conf);
    }

    std::vector<Track*> rem;                                                  // rem_tracks = [self.tracks[i] for i in ut]
    for (int i : ut) rem.push_back(all[i]);
    std::vector<std::pair<int, int>> m2;
    std::set<int> ut2, ud2;                                                   // unused (Python: `_, _`)
    greedy_match(rem, low, m_iou, m2, ut2, ud2);                              // stage 2: low-score dets vs still-unmatched tracks
    for (auto& pr : m2) {
        const Det* d = low[pr.second];
        double b[4] = {d->x, d->y, d->w, d->h};
        rem[pr.first]->update(b, d->label, d->conf);
    }

    for (int di : ud) {                                                       // births: unmatched high-score dets -> new tracks
        const Det* d = high[di];
        Track t{};
        t.track_id = m_next_id++;
        t.bbox[0] = d->x; t.bbox[1] = d->y; t.bbox[2] = d->w; t.bbox[3] = d->h;
        t.cls = d->label; t.conf = d->conf;
        t.vel[0] = 0.0; t.vel[1] = 0.0;
        t.last_x = d->x; t.last_y = d->y;
        t.age = 1; t.hits = 1; t.time_since_update = 0; t.min_hits = m_min_hits;
        m_tracks.push_back(t);
    }

    // cull tracks lost too long -- self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_lost]
    m_tracks.erase(std::remove_if(m_tracks.begin(), m_tracks.end(),
                                   [&](const Track& t) { return t.time_since_update > m_max_lost; }),
                   m_tracks.end());

    std::vector<const Track*> out;                                            // [t for t in self.tracks if tsu==0 and t.confirmed]
    for (auto& t : m_tracks) if (t.time_since_update == 0 && t.confirmed()) out.push_back(&t);
    return out;
}

} // namespace track
} // namespace garuda
