#pragma once
#include <string>
#include <vector>

// Line-for-line port of services/garuda-track/bytetrack.py (mono's tracker), as pinned by the parity
// oracle at tests/golden/bytetrack_ref.py. Comments below cite lines in that reference.
// Note: garuda::Track (include/garuda/snapshot.hpp) is the snapshot's output type; the tracker's own
// types live in garuda::track to avoid colliding with it.
namespace garuda {
namespace track {

struct Det { double x, y, w, h; std::string label; double conf; };

struct Track {
    int track_id; double bbox[4]; std::string cls; double conf;
    double vel[2]; double last_x, last_y; int age, hits, time_since_update; int min_hits;
    bool confirmed() const { return hits >= min_hits; }         // bytetrack_ref.py Track.confirmed
    void predict();                                             // bytetrack_ref.py Track.predict
    void update(const double b[4], const std::string& c, double s); // bytetrack_ref.py Track.update
};

double iou_xywh(const double a[4], const double b[4]);          // bytetrack_ref.py _iou

class ByteTracker {
public:
    ByteTracker(double high_thr = 0.5, double low_thr = 0.1, double iou_thr = 0.3, int max_lost = 30, int min_hits = 3);
    // bytetrack_ref.py ByteTracker.update. Pointer lifetime: the returned pointers (and every pointer/reference
    // obtained from tracks()) point into this ByteTracker's internal storage and are valid only until the next
    // call to update() — that call may push_back (births) or erase (culling), which can reallocate or shift
    // m_tracks and invalidate all previously returned pointers. Do not hold them across an update() call;
    // callers must re-resolve a track by track_id each frame (this is what mono's lock logic does).
    std::vector<const Track*> update(const std::vector<Det>& dets);
    // Same pointer-lifetime rule as update(): the returned reference, and any Track* taken from it, are
    // invalidated by the next call to update().
    const std::vector<Track>& tracks() const { return m_tracks; }
private:
    double m_high, m_low, m_iou; int m_max_lost, m_min_hits; int m_next_id = 1;
    std::vector<Track> m_tracks;
};

} // namespace track
} // namespace garuda
