#pragma once
#include <optional>
#include <string>
#include <vector>

namespace garuda {
// conf is double, not float: the golden file is produced by Python's builder (doubles) and the parity test compares JSON values exactly.
struct Track { int id; std::string label; double conf; float x, y, w, h; bool coasting; };
// The locked target's own published box, in frame pixels (garuda::lock::Output.box). Deliberately
// separate from the same-id entry in `tracks[]`: that one is the multi-object tracker engine's box,
// which under the mono engine is ByteTrack's EXTRAPOLATED coasting box and under the hailo engine the
// adapter's frozen last box -- neither is what LockCore publishes (F1 lock-core, review finding I5).
struct LockBox { double x, y, w, h; };
struct SnapshotState {
    std::vector<Track> tracks;
    std::optional<int> lock_id; std::string lock_class; bool lock_coasting = false;
    // LockCore fields (F1 lock-core, see include/garuda/lock_core.hpp): additive to the Pi's v2
    // schema, emitted inside "lock" next to id/class/coasting. lock_state's string values are exactly
    // garuda::lock::state_name()'s: "none","confirmed","occluded","reacquiring","lost".
    std::string lock_state = "none";
    bool lock_identity_locked = false, lock_observation_valid = false;
    // On-board fix round 9 (Ruling 30): FRESHNESS -- the flag a follow controller must gate on.
    // `control_valid_ms` was parsed from the `lock` config block since F1 and never consumed by
    // anything; this is what consumes it. Computed by node_main.cpp as
    //   observation_valid && (obs_age_ms + age_ms) <= control_valid_ms
    // where `age_ms` is this snapshot's own capture-to-publish age (the field below), so it accounts
    // for both halves of the staleness a consumer actually experiences: how long ago the core last
    // saw the target, and how long ago the frame it saw it in was captured. `observation_valid`
    // keeps its own meaning exactly (the core associated something on its last update) -- it is the
    // core's statement, not a freshness guarantee. See hosts/hailo15l/README.md §10.
    bool lock_control_valid = false;
    double lock_quality = 0.0, lock_obs_age_ms = 0.0, lock_uncertainty_px = 0.0;
    // Lock generation (garuda::lock::Output.epoch): 0 before the first lock, +1 per lock(), never
    // reset. A change means a NEW lock; an id change within one epoch is tracker id churn the core
    // rode through (review finding I2 -- the bench harness splits its identity column on this).
    int lock_epoch = 0;
    std::optional<LockBox> lock_box;
    std::optional<double> raw_m, est_m; bool valid = false;
    std::string depth_engine = "y26d"; std::string detector_mode = "primary";
    std::vector<std::string> prompt; int cal_n = 0; std::optional<std::string> cal_fit;
    int frame_w = 1280, frame_h = 720; std::optional<long> age_ms;
    // On-board fix round 9: per-frame stage counters, published as the `diag` object so a capture
    // alone answers "where did the boxes go" without re-running anything. -1 means "this engine
    // cannot see that stage" -- notably raw_dets under the hailo engine, where the SDK's TrackerStage
    // sits between the post-process and our sink and the pre-tracker detection list never reaches
    // the node (documented in hosts/hailo15l/README.md §9).
    //   raw_dets        detections the post-process handed the tracker this frame
    //   sdk_tracks      detections arriving with an SDK tracking id
    //   live_raw        LIVE records after the class allow-list only (HailoTrackAdapter::live_raw)
    //   published       tracks in this snapshot's tracks[] (birth gate + dedupe + resolver applied)
    //   core_candidates observations actually handed to LockCore::update() this frame
    int diag_raw_dets = -1, diag_sdk_tracks = -1, diag_live_raw = -1;
    int diag_published = -1, diag_core_candidates = -1;
};
std::string build_snapshot_json(const SnapshotState& s);
}
