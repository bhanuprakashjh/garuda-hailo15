#pragma once
#include "tracker.hpp"

namespace garuda::fresh {
struct IdentityConfig {
    double freshness_ms=200, memory_ms=10000, continuation_ms=200;
    double reacquire_ms=120, reacquire_gap_ms=150;
    // Bench starting points, not calibrated false-match probabilities.
    double max_anchor_distance=.25, max_recent_distance=.25, ambiguity_margin=.08;
    double confidence=.5, max_position_std=.12;
    unsigned reacquire_hits=3;
    // An undescribed visible person is missing evidence only while the target could have
    // reached their position: within evidence_radius extents of the last verified box, growing
    // by evidence_radius_growth extents per second of outage. 0 = every visible person counts.
    double evidence_radius=0, evidence_radius_growth=0;
};

// Selected identity, separate from detector association. No extrapolation is control-valid.
// This first learned implementation is person-only; other classes retain the ordinary tracker.
class TargetOwner {
public:
    explicit TargetOwner(IdentityConfig cfg={});
    bool select(const Track&,uint64_t epoch,double now_ms);
    void clear();
    bool active() const {return anchor_.has_value();}
    void update(uint64_t sequence,double capture_ms,double now_ms,bool timestamp_valid,
                const std::vector<Track>&);
    Target snapshot(double now_ms) const;
private:
    IdentityConfig cfg_;
    std::optional<Embedding> anchor_;
    std::deque<Embedding> recent_;
    Target target_;
    uint64_t sequence_=0;
    double capture_ms_=-1,publish_ms_=0,last_seen_ms_=0;
    std::optional<uint64_t> bound_id_,pending_id_;
    std::optional<Box> last_box_; // last verified observation, the centre of the evidence reach
    unsigned pending_hits_=0;
    double pending_start_ms_=0,pending_last_ms_=0;
    bool expired_=false,clock_valid_=true;
    void reset_pending();
    void observe(const Track&,double capture_ms);
    bool within_reach(const Box&,double capture_ms) const;
};
}
