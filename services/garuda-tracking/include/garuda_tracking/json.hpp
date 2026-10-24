#pragma once
#include "tracker.hpp"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <stdexcept>

namespace garuda::fresh {
using Json=nlohmann::json;
inline Json box_json(const Box& b,double w=1,double h=1) {
    return {{"x",b.x*w},{"y",b.y*h},{"w",b.w*w},{"h",b.h*h}};
}
inline uint64_t positive_integer(const Json& value) {
    if(!value.is_number_integer() || (value.is_number_unsigned()?value.get<uint64_t>()==0:value.get<int64_t>()<=0))
        throw std::invalid_argument("positive integer required");
    return value.get<uint64_t>();
}
inline Config config_from_json(const Json& j) {
    Config c;
    if(!j.is_object()) throw std::invalid_argument("tracking config must be an object");
    for(auto it=j.begin();it!=j.end();++it) {
        const auto& k=it.key();
#define GARUDA_PARAM(name) if(k==#name) { c.name=it.value().get<decltype(c.name)>(); continue; }
        GARUDA_PARAM(low_confidence) GARUDA_PARAM(birth_confidence) GARUDA_PARAM(control_confidence)
        GARUDA_PARAM(selection_ms) GARUDA_PARAM(confirm_ms) GARUDA_PARAM(max_gap_ms) GARUDA_PARAM(coast_ms) GARUDA_PARAM(freshness_ms)
        GARUDA_PARAM(max_center_distance) GARUDA_PARAM(max_size_ratio) GARUDA_PARAM(appearance_gate)
        GARUDA_PARAM(ambiguity_margin) GARUDA_PARAM(max_position_std) GARUDA_PARAM(max_tracks)
        GARUDA_PARAM(position_acceleration_std)
        GARUDA_PARAM(reacquire_window_ms) GARUDA_PARAM(reacquire_confirm_ms) GARUDA_PARAM(reacquire_gap_ms)
        GARUDA_PARAM(reacquire_size_ratio) GARUDA_PARAM(reacquire_radius) GARUDA_PARAM(reacquire_radius_growth)
        GARUDA_PARAM(reacquire_hits) GARUDA_PARAM(reacquire_appearance_crowd)
        GARUDA_PARAM(car_gap_reverify)
        GARUDA_PARAM(recovery_diagnostics)
        GARUDA_PARAM(car_extent_gate)
        GARUDA_PARAM(car_recovery_detection_veto)
        GARUDA_PARAM(phone_gap_association)
        GARUDA_PARAM(visual_phone_tracking)
        GARUDA_PARAM(learned_person_identity) GARUDA_PARAM(identity_memory_ms) GARUDA_PARAM(association_embedding_gate) GARUDA_PARAM(identity_max_distance) GARUDA_PARAM(identity_ambiguity_margin)
        GARUDA_PARAM(identity_continuation_ms) GARUDA_PARAM(identity_reacquire_gap_ms)
        GARUDA_PARAM(identity_evidence_radius) GARUDA_PARAM(identity_evidence_radius_growth)
        GARUDA_PARAM(max_detections) GARUDA_PARAM(min_hits) GARUDA_PARAM(classes)
#undef GARUDA_PARAM
        throw std::invalid_argument("unknown tracking parameter: "+k);
    }
    return c;
}
inline Frame frame_from_json(const Json& j) {
    Frame f; f.sequence=positive_integer(j.at("sequence")); f.capture_ms=j.at("capture_ms").get<double>();
    f.now_ms=j.at("now_ms").get<double>(); f.timestamp_valid=j.at("timestamp_valid").get<bool>();
    if(j.contains("visual_target")&&!j["visual_target"].is_null()) {
        const auto& v=j.at("visual_target");const auto& b=v.at("box");
        f.visual_target=VisualMeasurement{{b.at("x"),b.at("y"),b.at("w"),b.at("h")},
            positive_integer(v.at("lock_id")),v.at("epoch").get<uint64_t>(),positive_integer(v.at("sequence")),
            v.at("capture_ms"),v.at("verified_ms"),v.at("score"),v.at("margin")};
    }
    if(j.contains("motion")) {
        const auto& m=j.at("motion"); f.motion={m.at("dx"),m.at("dy"),m.at("valid")};
        if(m.contains("linear")) {
            auto a=m.at("linear").get<std::array<double,4>>();
            f.motion.a=a[0];f.motion.b=a[1];f.motion.c=a[2];f.motion.d=a[3];
        }
        f.motion.position_std=m.value("position_std",0.);
    }
    for(const auto& d:j.at("detections")) {
        Detection det; auto b=d.at("box"); det.box={b.at("x"),b.at("y"),b.at("w"),b.at("h")};
        det.label=d.at("label");det.confidence=d.at("confidence");
        det.region_id=d.value("region_id",-1);det.region_full_frame=d.value("region_full_frame",false);
        if(d.contains("appearance")&&!d["appearance"].is_null()) det.appearance=d["appearance"].get<Appearance>();
        if(d.contains("embedding")&&!d["embedding"].is_null()) {
            const auto& e=d.at("embedding");
            if(!e.at("values").is_array()||e.at("values").size()!=512)
                throw std::invalid_argument("embedding must have exactly 512 values");
            det.embedding=Embedding{e.at("model").get<std::string>(),e.at("values").get<std::array<double,512>>()};
        }
        f.detections.push_back(std::move(det));
        if(f.detections.size()>512) throw std::invalid_argument("too many detections");
    }
    return f;
}
inline Json frame_json(const Frame& f) {
    Json ds=Json::array();
    for(const auto& d:f.detections) {
        Json item={{"box",box_json(d.box)},{"label",d.label},{"confidence",d.confidence},
                   {"appearance",d.appearance?Json(*d.appearance):Json(nullptr)}};
        if(d.embedding)item["embedding"]={{"model",d.embedding->model},{"values",d.embedding->values}};
        item["region_id"]=d.region_id;item["region_full_frame"]=d.region_full_frame;
        ds.push_back(std::move(item));
    }
    Json out={{"sequence",f.sequence},{"capture_ms",f.capture_ms},{"now_ms",f.now_ms},{"timestamp_valid",f.timestamp_valid},
            {"motion",{{"dx",f.motion.dx},{"dy",f.motion.dy},{"valid",f.motion.valid},
                       {"linear",{f.motion.a,f.motion.b,f.motion.c,f.motion.d}},
                       {"position_std",f.motion.position_std}}},{"detections",ds}};
    if(f.visual_target) {
        const auto& v=*f.visual_target;
        out["visual_target"]={{"box",box_json(v.box)},{"lock_id",v.lock_id},{"epoch",v.epoch},
            {"sequence",v.sequence},{"capture_ms",v.capture_ms},{"verified_ms",v.verified_ms},{"score",v.score},{"margin",v.margin}};
    }
    return out;
}
inline Json output_json(const Output& o,int width=1280,int height=720) {
    Json association_candidates=Json::array();
    for(const auto& c:o.association_candidates) association_candidates.push_back({
        {"prediction",box_json(c.prediction,width,height)},
        {"measurement",box_json(c.measurement,width,height)},
        {"detection",box_json(c.detection,width,height)},
        {"confidence",c.confidence},{"gap_ms",c.gap_ms},{"gate",c.gate},
        {"center_limit",c.center_limit},{"phone_gap_bridge",c.phone_gap_bridge},
        {"size_ratio",c.size_ratio?Json(*c.size_ratio):Json(nullptr)},
        {"distance",c.distance?Json(*c.distance):Json(nullptr)},
        {"mahalanobis",c.mahalanobis?Json(*c.mahalanobis):Json(nullptr)},
        {"appearance_distance",c.appearance_distance?Json(*c.appearance_distance):Json(nullptr)},
        {"cost",c.cost?Json(*c.cost):Json(nullptr)}});
    Json association=nullptr;
    if(o.association) {
        const auto& a=*o.association;
        association={{"prediction",box_json(a.prediction,width,height)},
            {"measurement",box_json(a.measurement,width,height)},
            {"detection",box_json(a.detection,width,height)},
            {"floor_scaled",a.floor_scaled},{"extent_scaled",a.extent_scaled},{"gap_ms",a.gap_ms},
            {"appearance_distance",a.appearance_distance?Json(*a.appearance_distance):Json(nullptr)}};
    }
    Json recovery=nullptr;
    if(o.recovery) {
        const auto& r=*o.recovery;
        Json candidates=Json::array();
        for(const auto& c:r.candidates) candidates.push_back({{"id",c.id},
            {"box",box_json(c.box,width,height)},{"reason",c.reason},{"observed",c.observed},
            {"size_ratio",c.size_ratio?Json(*c.size_ratio):Json(nullptr)},
            {"distance",c.distance?Json(*c.distance):Json(nullptr)},
            {"appearance_distance",c.appearance_distance?Json(*c.appearance_distance):Json(nullptr)}});
        recovery={{"reference",box_json(r.reference,width,height)},{"status",r.status},
            {"radius",r.radius},{"elapsed_ms",r.elapsed_ms},{"pending_id",r.pending_id},
            {"pending_hits",r.pending_hits},{"pending_ms",r.pending_ms},
            {"class_peers",r.class_peers},{"candidates",candidates},
            {"current_candidate_score",r.current_candidate_score?Json(*r.current_candidate_score):Json(nullptr)},
            {"competing_detection_score",r.competing_detection_score?Json(*r.competing_detection_score):Json(nullptr)},
            {"competing_detection",r.competing_detection?box_json(*r.competing_detection,width,height):Json(nullptr)}};
    }
    Json tracks=Json::array();
    for(const auto& t:o.tracks) {
        if(!t.confirmed) continue;
        auto j=box_json(t.box,width,height);
        j.update({{"id",t.id},{"label",t.label},{"conf",t.confidence},{"coasting",!t.observed},
                  {"ambiguous",t.ambiguous},{"observation_age_ms",std::max(0.,o.publish_ms-t.last_seen_ms)}});
        j["box_source"]=t.observed?(t.visual_observation?"visual_measurement":"detector_measurement"):"prediction";
        j["filtered_box"]=t.filtered_box?box_json(*t.filtered_box,width,height):Json(nullptr);
        tracks.push_back(j);
    }
    const auto& t=o.target;
    // v2 display-compatible envelope, with an explicit new tracker contract and monotonic timestamps.
    return {{"v",2},{"tracker_contract","garuda.fresh.v1"},{"sequence",o.sequence},
            {"capture_monotonic_ms",o.capture_ms},{"publish_monotonic_ms",o.publish_ms},
            {"timestamp_valid",o.timestamp_valid},{"accepted",o.accepted},{"reason",o.reason},
            {"age_ms",o.timestamp_valid?Json(std::max(0.,o.publish_ms-o.capture_ms)):Json(nullptr)},
            {"tracks",tracks},{"recovery_diagnostic",recovery},{"association_diagnostic",association},
            {"association_candidates",association_candidates},{"frame",{{"width",width},{"height",height}}},
            {"lock",{{"id",t.lock_id?Json(t.lock_id):Json(nullptr)},
                     {"track_id",t.id?Json(*t.id):Json(nullptr)},{"epoch",t.epoch},{"class",t.label},
                     {"state",t.state},{"reason",t.reason},{"identity_locked",t.id.has_value()||t.identity_retained},
                     {"identity_retained",t.identity_retained},
                     {"identity_candidates",t.identity_candidates},{"identity_unresolved",t.identity_unresolved},
                     {"identity_best_distance",t.identity_best_distance?Json(*t.identity_best_distance):Json(nullptr)},
                     {"identity_runner_up_distance",t.identity_runner_up_distance?Json(*t.identity_runner_up_distance):Json(nullptr)},
                     {"coasting",t.id.has_value()&&!t.control_valid},{"observation_valid",t.observation_valid},
                     {"control_valid",t.control_valid},{"obs_age_ms",t.observation_age_ms},
                     {"box_source",t.observation_valid?(t.visual_observation?"visual_measurement":"detector_measurement"):"prediction"},
                     {"uncertainty_px",t.position_std*std::max(width,height)},
                     {"box",t.box?box_json(*t.box,width,height):Json(nullptr)},
                     {"pending_box",t.pending_box?box_json(*t.pending_box,width,height):Json(nullptr)},
                     {"last_verified_box",t.last_verified_box?box_json(*t.last_verified_box,width,height):Json(nullptr)}}},
            {"image_target",{{"valid",t.control_valid},
                {"u",t.box?Json(t.box->x+t.box->w/2):Json(nullptr)},
                {"v",t.box?Json(t.box->y+t.box->h/2):Json(nullptr)},
                {"width_fraction",t.box?Json(t.box->w):Json(nullptr)},
                {"height_fraction",t.box?Json(t.box->h):Json(nullptr)}}},
            {"distance",{{"raw_m",nullptr},{"est_m",nullptr},{"valid",false}}},
            {"depth_engine","none"},{"detector",{{"mode","primary"},{"prompt",Json::array()}}},
            {"cal",{{"n",0},{"fit",nullptr}}},{"gesture",{{"name",nullptr},{"track_id",nullptr},{"held_ms",0}}},
            {"diag",{{"rejected_detections",o.rejected_detections}}}};
}
inline Json command(Tracker& tracker,const Json& j,double now,int width=1280,int height=720) {
    const std::string cmd=j.at("cmd");
    if(cmd=="unlock") {tracker.unlock();return {{"ok",true}};}
    if(cmd=="target") {tracker.arm_class(j.at("class").get<std::string>());return {{"ok",true}};}
    bool ok=false;
    if(cmd=="select") ok=tracker.select(positive_integer(j.at("id")),positive_integer(j.at("sequence")),now);
    else if(cmd=="lock_point") ok=tracker.select_point(j.at("x").get<double>()/width,j.at("y").get<double>()/height,positive_integer(j.at("sequence")),now);
    else return {{"ok",false},{"error","unsupported command"}};
    return ok?Json{{"ok",true}}:Json{{"ok",false},{"error",tracker.selection_error()}};
}
} // namespace garuda::fresh
