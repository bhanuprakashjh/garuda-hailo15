#pragma once
#include <string>

// Engine-neutral per-track snapshot: whatever produces detections-with-identity (ByteTrack via the
// adapter in bytetrack.cpp/lock.cpp, or the SDK's Kalman tracker via HailoTrackAdapter, hailo_track_adapter.*)
// reports one TrackRecord per track per frame. LockResolver (lock.hpp) consumes these and no longer
// needs to know which engine produced them.
namespace garuda {
namespace track {

struct TrackRecord {
    int id;
    std::string cls;
    double conf;
    double bbox[4];              // x, y, w, h
    int time_since_update;       // 0 == seen this frame; >0 == coasting for that many frames
    bool confirmed;
    // On-board fix round 10 (Ruling 32b): the timestamp (same clock as LockCore's ts_ms, i.e. the
    // frame's ISP clock in ms) of the frame in which this id was FIRST SEEN, or -1 when the engine
    // cannot report it. LockCore uses it to refuse an out-of-gate different-id candidate that was
    // already alive while the target was still confirmed -- such an id is, by construction, a
    // different object. -1 means "unknown", which the core treats as pre-existing and therefore
    // refuses; a default member initializer keeps TrackRecord an aggregate, so the six-element brace
    // initialisations elsewhere still compile unchanged.
    double first_seen_ms = -1.0;
};

} // namespace track
} // namespace garuda
