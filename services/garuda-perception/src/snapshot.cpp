#include "garuda/snapshot.hpp"
#include <nlohmann/json.hpp>

namespace garuda {
std::string build_snapshot_json(const SnapshotState& s) {
    using nlohmann::json;
    json tracks = json::array();
    for (const auto& t : s.tracks)
        tracks.push_back({{"id", t.id}, {"label", t.label}, {"conf", t.conf}, {"x", t.x}, {"y", t.y},
                          {"w", t.w}, {"h", t.h}, {"coasting", t.coasting}});
    json j = {
        {"v", 2},
        {"age_ms", s.age_ms ? json(*s.age_ms) : json(nullptr)},
        {"tracks", tracks},
        {"lock", {{"id", s.lock_id ? json(*s.lock_id) : json(nullptr)}, {"class", s.lock_class}, {"coasting", s.lock_coasting},
                  {"state", s.lock_state}, {"identity_locked", s.lock_identity_locked},
                  {"observation_valid", s.lock_observation_valid},
                  {"control_valid", s.lock_control_valid}, {"quality", s.lock_quality},
                  {"obs_age_ms", s.lock_obs_age_ms}, {"uncertainty_px", s.lock_uncertainty_px},
                  {"epoch", s.lock_epoch},
                  {"box", s.lock_box ? json{{"x", s.lock_box->x}, {"y", s.lock_box->y},
                                            {"w", s.lock_box->w}, {"h", s.lock_box->h}}
                                     : json(nullptr)}}},
        {"distance", {{"raw_m", s.raw_m ? json(*s.raw_m) : json(nullptr)}, {"est_m", s.est_m ? json(*s.est_m) : json(nullptr)}, {"valid", s.valid}}},
        {"depth_engine", s.depth_engine},
        {"detector", {{"mode", s.detector_mode}, {"prompt", s.prompt}}},
        {"cal", {{"n", s.cal_n}, {"fit", s.cal_fit ? json(*s.cal_fit) : json(nullptr)}}},
        {"frame", {{"width", s.frame_w}, {"height", s.frame_h}}},
        {"gesture", {{"name", nullptr}, {"track_id", nullptr}, {"held_ms", 0}}},
        // Round 9: per-frame stage counters (see SnapshotState). -1 = "this engine cannot see it".
        {"diag", {{"raw_dets", s.diag_raw_dets}, {"sdk_tracks", s.diag_sdk_tracks},
                  {"live_raw", s.diag_live_raw}, {"published", s.diag_published},
                  {"core_candidates", s.diag_core_candidates}}},
    };
    return j.dump();
}
}
