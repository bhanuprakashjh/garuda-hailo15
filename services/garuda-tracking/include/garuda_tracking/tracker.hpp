#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace garuda::fresh {
// All boxes and motion are in normalized, full-field-of-view coordinates.
struct Box { double x=0, y=0, w=0, h=0; };
using Appearance = std::array<double, 72>;
struct Embedding {
    // Identifies weights AND preprocessing; vectors from different pipelines are incomparable.
    std::string model;
    std::array<double,512> values{};
};
bool normalize_embedding(Embedding&);
double embedding_distance(const Embedding&,const Embedding&);
struct Detection {
    Box box;
    std::string label;
    double confidence=0;
    std::optional<Appearance> appearance;
    std::optional<Embedding> embedding;
    // Inference provenance for cross-crop suppression; not identity evidence.
    int region_id=-1;
    bool region_full_frame=false;
};
struct Motion {
    double dx=0, dy=0; bool valid=false;
    // Normalized full-FOV transform about image center:
    // p' = A * (p - .5) + .5 + (dx,dy). Identity A preserves old translation records.
    double a=1,b=0,c=0,d=1;
    double position_std=0; // conservative normalized fit-noise proxy, not calibrated odometry
    bool usable() const;
    Box transform(const Box&) const;
};
// Image-derived selected-target evidence. Never inserted into detections or
// allowed to create/re-identify a target. Bound to the exact selection/frame.
struct VisualMeasurement {
    Box box;
    uint64_t lock_id=0,epoch=0,sequence=0;
    double capture_ms=-1,verified_ms=-1,score=0,margin=0;
};
constexpr double visual_verification_horizon_ms=1500;
struct Frame {
    uint64_t sequence=0;
    double capture_ms=0, now_ms=0; // same local monotonic clock, never wall time
    bool timestamp_valid=false;
    std::vector<Detection> detections;
    Motion motion; // displacement from the previous ACCEPTED frame to this one
    std::optional<VisualMeasurement> visual_target;
};
struct Config {
    double low_confidence=.15, birth_confidence=.5, control_confidence=.4;
    double confirm_ms=120, max_gap_ms=250, coast_ms=1200, freshness_ms=200, selection_ms=1000;
    double max_center_distance=2.0, max_size_ratio=2.5, appearance_gate=.55;
    // OPT-IN (0 = off): use a learned embedding (1 - cosine) in ordinary association when
    // both sides carry one — pairs above the gate forbidden, below it blended with the
    // histogram term. Measured OFF by default: on VisDrone-SOT 024 real OSNet crops drift
    // under partial occlusion and the extra cost severed the target's own observation
    // stream (on-target 0.33 -> 0.03 with a 0.5 gate, 0.24 -> 0.02 blended at 0.85);
    // identity stays with the owner's absolute gate. Kept for descriptors that are
    // stable frame to frame.
    double association_embedding_gate=0;
    double ambiguity_margin=.08, max_position_std=.12;
    double position_acceleration_std=1.0; // normalized frame units / second squared
    size_t max_tracks=64, max_detections=128;
    unsigned min_hits=3;
    // Selected-target re-acquire after coast expiry (0 window disables it).
    double reacquire_window_ms=7000, reacquire_confirm_ms=600, reacquire_gap_ms=250;
    // Search radius in remembered-box extents: growth is per second of outage.
    // 0.5/s lost a walking person seen from above (VisDrone-MOT, 2026-09-12):
    // the box extent is a footprint there, and even in a forward view a walk
    // covers ~1-2 body heights per second. Identity is still gated by appearance.
    double reacquire_size_ratio=2.5, reacquire_radius=2.0, reacquire_radius_growth=2.0;
    unsigned reacquire_hits=3;
    // Bench opt-in: a selected car interrupted beyond max_gap_ms must pass
    // explicit recovery even if its MOT ID survives. Other classes unchanged.
    bool car_gap_reverify=false;
    bool recovery_diagnostics=false; // bench-only observation; never a decision input
    bool car_extent_gate=false; // bench opt-in: selected-car association uses object-sized geometry
    // Bench opt-in: excluded/unconfirmed MOT IDs may still carry competing
    // current visual evidence. They may veto car recovery, never authorize it.
    bool car_recovery_detection_veto=false;
    // Experimental fixed-input bench candidate, OFF in live profiles. During
    // a short selected-phone outage, allow bounded position uncertainty only
    // for a sole, confident, strongly appearance-matched phone. No prediction
    // is promoted to an observation; explicit lost-target recovery is unchanged.
    bool phone_gap_association=false;
    bool visual_phone_tracking=false; // experimental; no live profile enables it
    // Geometry-only re-acquire refuses when same-class rivals exist (a crowd
    // cannot be disambiguated without appearance). Enabling this permits
    // appearance-verified binding among rivals; UNVALIDATED on real board
    // descriptors — keep off until a live evaluation passes.
    bool reacquire_appearance_crowd=false;
    // Observation-cadence budgets, separate from frame age/control freshness.
    double identity_continuation_ms=200,identity_reacquire_gap_ms=150;
    std::vector<std::string> classes; // empty = all detector classes
    bool learned_person_identity=false; // experimental, requires embeddings on current observations
    // How long the learned identity is remembered without a verified observation. A follow
    // target that steps behind something for more than this must be re-selected. Must exceed
    // freshness_ms; 10 s lost the owner after a 12 s walk-out in the first live session.
    double identity_memory_ms=10000;
    // Identity owner gates (1 - cosine on the learned descriptor): candidates farther than
    // identity_max_distance from the anchor/recent memory are not the target; two candidates
    // closer than identity_ambiguity_margin to each other are refused. Exposed for offline sweeps.
    double identity_max_distance=.25, identity_ambiguity_margin=.08;
    // Reach of the incomplete-evidence rule, in extents of the last verified target box plus
    // extents per second of outage (as reacquire_radius/_growth): an undescribed person farther
    // away than the target could have walked does not block re-binding. 0 = unbounded, i.e.
    // every visible undescribed person blocks (the rule as shipped; crowds never resolve).
    double identity_evidence_radius=0, identity_evidence_radius_growth=0;
};
struct Track {
    uint64_t id=0;
    std::string label;
    Box box; // current measurement (source below); prediction ONLY while coasting
    double confidence=0, last_seen_ms=0, position_std=0;
    bool confirmed=false, observed=false, ambiguous=false;
    std::shared_ptr<const Embedding> embedding; // current observation only; shared immutable feature
    std::optional<Box> filtered_box; // diagnostic; never substitutes for current measured geometry
    bool visual_observation=false; // confidence is the last verified detector's score, not NCC
};
struct Target {
    // Search-only motion at a measured capture timestamp; never an observation.
    std::optional<Box> search_measurement;
    double search_capture_ms=-1, search_vx=0, search_vy=0;
    std::optional<uint64_t> id;   // current underlying MOT track id (may change on re-acquire)
    uint64_t lock_id=0;           // stable lock identity; persists across re-acquire, 0 when none
    uint64_t epoch=0;
    std::string state="none", reason="not_selected", label;
    std::optional<Box> box;
    bool observation_valid=false, control_valid=false;
    bool visual_observation=false;
    double observation_age_ms=0, position_std=0;
    bool identity_retained=false; // durable selected identity can outlive its current MOT ID
    // A person clicked without a fresh descriptor, kept for selection_ms: identity crops go
    // there first so the retry can take (a crowd's confident strangers otherwise use the budget).
    std::optional<Box> pending_box;
    // Where the selected identity was last verified; kept while the identity is remembered so
    // the descriptor budget stays around it after a release (a crowd's strangers otherwise
    // take the crops by confidence and the target itself goes undescribed; VisDrone-SOT 086).
    std::optional<Box> last_verified_box;
    size_t identity_candidates=0;
    // Visible people without a usable descriptor who could still be the target (inside the
    // evidence reach); diagnostic for the descriptor budget and the reach, not a decision input.
    size_t identity_unresolved=0;
    std::optional<double> identity_best_distance, identity_runner_up_distance;
};
struct RecoveryCandidateDiagnostic {
    uint64_t id=0;
    Box box;
    std::string reason;
    std::optional<double> size_ratio, distance, appearance_distance;
    bool observed=false;
};
struct RecoveryDiagnostic {
    Box reference;
    std::string status;
    double radius=0, elapsed_ms=0, pending_ms=0;
    uint64_t pending_id=0;
    unsigned pending_hits=0;
    size_t class_peers=0;
    std::vector<RecoveryCandidateDiagnostic> candidates;
    std::optional<double> current_candidate_score, competing_detection_score;
    std::optional<Box> competing_detection;
};
struct AssociationDiagnostic {
    Box prediction, measurement, detection;
    double floor_scaled=0, extent_scaled=0, gap_ms=0;
    std::optional<double> appearance_distance;
};
struct AssociationCandidateDiagnostic {
    Box prediction, measurement, detection;
    double confidence=0, gap_ms=0;
    double center_limit=0;
    bool phone_gap_bridge=false;
    std::string gate;
    std::optional<double> size_ratio, distance, mahalanobis, appearance_distance, cost;
};
struct Output {
    uint64_t sequence=0;
    double capture_ms=0, publish_ms=0;
    bool accepted=false, timestamp_valid=false;
    std::string reason;
    size_t rejected_detections=0;
    std::vector<Track> tracks;
    Target target;
    std::optional<RecoveryDiagnostic> recovery;
    std::optional<AssociationDiagnostic> association;
    std::vector<AssociationCandidateDiagnostic> association_candidates;
};

class TargetOwner;
class Tracker {
public:
    explicit Tracker(Config cfg={});
    ~Tracker();
    Output update(const Frame& frame);
    // No new frame: ages the last result, including after camera/inference failure.
    Output snapshot(double now_ms) const;
    // Commands reference the exact published sequence. Stale/unobserved IDs fail closed.
    bool select(uint64_t id, uint64_t sequence, double now_ms);
    bool select_point(double x, double y, uint64_t sequence, double now_ms);
    const std::string& selection_error() const { return selection_error_; }
    void arm_class(const std::string& label); // one acquisition, then never auto-switch
    void unlock();
    const Config& config() const { return cfg_; }
private:
    struct Axis {
        double p=0, v=0, pp=.001, pv=0, vv=.1;
        void predict(double dt, double noise);
        void correct(double z, double variance);
    };
    struct State {
        Track public_track;
        // Last measurement, propagated only by camera motion, not Kalman coasting.
        Box recovery_box;
        std::array<Axis,4> axes;
        std::optional<Appearance> appearance;
        std::shared_ptr<const Embedding> embedding; // last confident observation's descriptor
        double born_ms=0, streak_start_ms=0;
        double last_detector_ms=-1;
        double last_detector_confidence=0;
        unsigned hits=1;
    };
    // Retained selected-target memory after coast expiry; never rebound by
    // ordinary association, only by the explicit gated re-acquire step.
    struct LostMemory {
        std::string label; Box box; std::optional<Appearance> appearance;
        double lost_ms=0, last_seen_ms=0;
        uint64_t lost_id=0, pending_id=0;
        unsigned pending_hits=0;
        double pending_start_ms=0, pending_last_ms=0;
    };
    Config cfg_;
    std::vector<State> states_;
    std::optional<LostMemory> lost_memory_;
    std::optional<RecoveryDiagnostic> recovery_diagnostic_;
    std::optional<AssociationDiagnostic> association_diagnostic_;
    std::vector<AssociationCandidateDiagnostic> association_candidates_;
    uint64_t next_id_=1, sequence_=0, epoch_=0;
    uint64_t lock_id_=0, next_lock_id_=1; // stable lock identity across re-acquire
    double last_capture_ms_=-1, last_publish_ms_=0;
    bool last_timestamp_valid_=false;
    std::optional<uint64_t> target_id_;
    std::optional<Box> pending_box_; double pending_ms_=0; // click refused for lack of a descriptor
    std::string target_class_, armed_class_, selection_error_;
    bool target_lost_=false;
    size_t last_rejected_detections_=0;
    std::deque<Output> history_; // bounded click/selection history
    std::unique_ptr<TargetOwner> owner_;
};
double iou(const Box&, const Box&);
double appearance_distance(const Appearance&, const Appearance&);
} // namespace garuda::fresh
