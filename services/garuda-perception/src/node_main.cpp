// garuda-perception: front end -> yolov8 detect -> post-process -> track (mono ByteTrack, or the SDK's
// Kalman TrackerStage behind tracker.engine "hailo") -> lock resolver -> snapshot feed; sink1 -> JPEG feed.
#include "garuda/bytetrack.hpp"
#include "garuda/feed_server.hpp"
#include "garuda/hailo_track_adapter.hpp"
#include "garuda/jpeg_encoder.hpp"
#include "garuda/lock.hpp"
#include "garuda/lock_core.hpp"
#include "garuda/snapshot.hpp"
#include "garuda/track_record.hpp"
#include <nlohmann/json.hpp>

#include "hailo_analytics/pipeline/core/pipeline_builder.hpp"
#include "hailo_analytics/pipeline/core/pipeline.hpp"
#include "hailo_analytics/pipeline/sources/frontend_stage.hpp"
#include "hailo_analytics/pipeline/ai/ai_stage.hpp"
#include "hailo_analytics/pipeline/ai/postprocess_stage.hpp"
#include "hailo_analytics/pipeline/ai/tracker_stage.hpp"
#include "hailo_analytics/pipeline/sinks/app_sink_stage.hpp"
#include "hailo_postprocess_tools/objects/hailo_common.hpp"
#include "hailo_postprocess_tools/objects/hailo_objects.hpp"
#include "hailo_postprocess_tools/tracking/hailo_tracker.hpp"
#include "media_library/media_library.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <map>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

using nlohmann::json;
using namespace hailo_analytics::pipeline;
using hailo_analytics::pipeline::ai::HailortAsyncStageBuild;
using hailo_analytics::pipeline::ai::PostprocessStageBuild;
using hailo_analytics::pipeline::ai::TrackerStageBuild;
using hailo_analytics::pipeline::sinks::AppSinkStageBuild;
using hailo_analytics::pipeline::sources::FrontendStageBuild;

static std::atomic<bool> g_stop{false};
static void on_signal(int) { g_stop = true; }

struct NodeState {                      // shared between the detection callback and the command server
    std::mutex mu;
    garuda::SnapshotState snap;         // last published snapshot state (frame px)
    // Command handlers only ever record intent here; the detection-callback thread (which alone owns
    // the tracker/resolver) consumes and clears these under state.mu, then runs update/step outside it.
    std::optional<std::pair<float,float>> pending_lock_point;
    std::optional<std::string> pending_target;   // "" is a valid value (-> resolver's default class)
};

static std::string read_file(const std::string& p) { std::ifstream f(p); if (!f) throw std::runtime_error("cannot read " + p); std::stringstream ss; ss << f.rdbuf(); return ss.str(); }

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);   // line-buffered: the 10 s fps line must reach the log promptly
    std::string cfg_path = "/opt/garuda/perception.json";
    for (int i = 1; i + 1 < argc; ++i) if (std::string(argv[i]) == "--config") cfg_path = argv[i + 1];
    json cfg = json::parse(read_file(cfg_path));
    const int FW = cfg.value("frame_w", 1280), FH = cfg.value("frame_h", 720);
    const json trk = cfg.value("track", json::object());
    const double track_high_thr = trk.value("high_thr", 0.4);
    const double track_low_thr = trk.value("low_thr", 0.12);
    const double track_iou_thr = trk.value("iou_thr", 0.3);
    const int track_max_lost = trk.value("max_lost", 25);
    const int track_min_hits = trk.value("min_hits", 2);
    const int track_reacq = trk.value("reacq", 5);
    const double track_conf_floor = trk.value("conf_floor", 0.15);
    const std::string track_default_class = trk.value("default_class", std::string("person"));
    // tracker.engine selects the id-producing engine feeding LockResolver::step(): "mono" (default,
    // absent -> "mono") is the ported ByteTrack path above; "hailo" swaps in the SDK's Kalman
    // TrackerStage (tracker_stage.hpp) between "post" and "det_sink", whose ids are read off each
    // detection's HailoUniqueID (TRACKING_ID mode) and adapted to TrackRecords by HailoTrackAdapter,
    // which never re-predicts a missing box (frozen coasting) unlike ByteTrack's own predict().
    // Defaults for the "hailo" block below are the SDK's own DEFAULT_* macros (hailo_tracker.hpp)
    // except keep_lost_frames (75, matching the M1/M2 coast window at ~25-30 fps -- track.max_lost
    // above is the same number for the mono engine) and min_hits (1, this adapter's own field, no
    // SDK equivalent).
    const json trk_engine_cfg = cfg.value("tracker", json::object());
    const std::string tracker_engine = trk_engine_cfg.value("engine", std::string("mono"));
    // Refuse to start on an unrecognised tracker.engine value rather than silently falling back to
    // "mono" -- a typo'd config (e.g. "hailo " or "Hailo") would otherwise deploy the wrong engine
    // with no diagnostic anywhere in the log.
    if (tracker_engine != "mono" && tracker_engine != "hailo") {
        std::fprintf(stderr, "tracker.engine: unknown value \"%s\" (must be \"mono\" or \"hailo\") -- refusing to start\n", tracker_engine.c_str());
        return 1;
    }
    const bool use_hailo_tracker = (tracker_engine == "hailo");
    const json trk_hailo = trk_engine_cfg.value("hailo", json::object());
    const float hailo_kalman_distance = trk_hailo.value("kalman_distance", (double)DEFAULT_KALMAN_DISTANCE);
    const float hailo_iou_threshold = trk_hailo.value("iou_threshold", (double)DEFAULT_IOU_THRESHOLD);
    const float hailo_init_iou_threshold = trk_hailo.value("init_iou_threshold", (double)DEFAULT_INIT_IOU_THRESHOLD);
    const int hailo_keep_tracked_frames = trk_hailo.value("keep_tracked_frames", (int)DEFAULT_KEEP_FRAMES);
    const int hailo_keep_new_frames = trk_hailo.value("keep_new_frames", (int)DEFAULT_KEEP_FRAMES);
    const int hailo_keep_lost_frames = trk_hailo.value("keep_lost_frames", 75);
    const int hailo_min_hits = trk_hailo.value("min_hits", 1);
    // dedupe_containment / dedupe_iou (on-board fix round 6, Ruling 23): the HEF's baked NMS does not
    // suppress a box wholly (or mostly) contained inside a larger one, so a single person can produce
    // two simultaneous same-class detections (full-body + torso) that this class-agnostic tracker
    // births into two separate ids (field finding, run 8: ids 38/39 alternating on one person, boxes
    // ~819 vs ~655 px wide, `id churn 41`). HailoTrackAdapter::update() dedupes its own same-class LIVE
    // output using these two thresholds -- see hailo_track_adapter.hpp for the full mechanism. Either
    // set to 0 disables that rule.
    const double hailo_dedupe_containment = trk_hailo.value("dedupe_containment", 0.8);
    const double hailo_dedupe_iou = trk_hailo.value("dedupe_iou", 0.6);
    // birth_conf (on-board fix round 7, Ruling 24): the confidence a detection must reach once before
    // its id is published at all. The SDK's Kalman tracker births a track from ANY detection handed to
    // it -- it has no confidence floor of its own -- so the GUI drew a box for every 0.17-0.19 junk
    // detection in a cluttered room (field finding, 2026-09-04: handbag 0.19, backpack 0.19, handbag
    // 0.17 tracks in /api/state; the owner's "all over the place"). The default is track.high_thr, the
    // literal ByteTrack births at on the mono path, so the two engines admit the same detections.
    const double hailo_birth_conf = trk_hailo.value("birth_conf", track_high_thr);
    // classification_id: which class id(s) the SDK tracker's association runs on (-1 = every class, the
    // TrackerStageBuild::Builder's own default is 1, a single class -- overridden below either way).
    // Field finding, 2026-09-03, corrected 2026-09-04 (see hosts/hailo15l/README.md's classification_id
    // note, "the final-fix-wave brief's I2"): the SDK tracker is ONE class-agnostic tracker with a
    // single one-to-one LAPJV (Linear Assignment Problem, Jonker-Volgenant) assignment -- there is no
    // per-class matching mode. Tracking "every class" at once (-1) means a same-frame, overlapping
    // detection of a DIFFERENT class (a person carrying a phone, or standing near furniture) competes
    // for that SAME track slot in that one assignment problem and can win it, or split it into a new
    // id, whenever the detector's winning class flickers for one frame (chair/suitcase/scissors etc.
    // instead of person) -- a different failure from the one the majority-vote label fix (18af174)
    // addresses (that fix stops a stray frame from relabelling cls on an id that survives; it does
    // nothing if the tracker's own assignment loses the id to a competing class's box entirely).
    // classification_id does not turn on per-class association -- it restricts which class(es) are
    // ever handed to the tracker at all, so nothing else can compete for a track slot.
    // config/perception-yolov8m.json sets this to 1 (person, in the stock post-process's 1-based
    // labelmap) for that reason.
    const int hailo_classification_id = trk_hailo.value("classification_id", -1);
    // classes (on-board fix round 8, Ruling 25): classification_id allows exactly ONE class id, so a
    // demo needing more than one class (e.g. person + phone) has to run classification_id -1 (every
    // class) -- and pay for the resulting clutter (field finding: a 120 s all-classes capture on real
    // room objects emitted 15274 track entries over 3063 rows; chair 3885, handbag 3137, toilet (a
    // ring light) 2298, laptop 1905, suitcase 1379, person 989 -- bench/benchlog.md F1, "Round 8").
    // This is a HailoTrackAdapter-side allow-list, independent of classification_id: absent or an
    // empty JSON array means every class (unchanged default); otherwise a detection whose label is
    // not in the list is dropped before it can be born, tracked, or take part in dedupe (see
    // hailo_track_adapter.hpp for the ordering guarantee).
    std::vector<std::string> hailo_classes;
    for (auto& c : trk_hailo.value("classes", json::array())) hailo_classes.push_back(c.get<std::string>());
    // dedupe_protect_age (on-board fix round 9, Ruling 27): frames a track must have been PUBLISHED
    // for before the round-6 dedupe is allowed to suppress it. The dedupe cannot tell "one person
    // detected twice" from "one person standing behind another", and in the second case it silently
    // deleted the farther person -- who may be the locked target (outside review, 2026-09-05). A
    // duplicate BIRTH is young by definition and still suppressed; an established track is kept. The
    // locked identity is exempt at any age (set_protected_id, below). 0 disables the age half.
    const int hailo_dedupe_protect_age = trk_hailo.value("dedupe_protect_age", 10);
    // The two engines' coast windows (mono's track.max_lost frames, the hailo engine's
    // tracker.hailo.keep_lost_frames) are independent config knobs that are DESIGNED to match (see
    // the comment above the tracker.engine block) so switching engines doesn't silently change how
    // long a lost track survives; log both at startup and warn if they've drifted apart.
    std::printf("tracker: keep_lost_frames=%d max_lost=%d\n", hailo_keep_lost_frames, track_max_lost);
    if (hailo_keep_lost_frames != track_max_lost) {
        std::fprintf(stderr, "tracker: keep_lost_frames (%d) != max_lost (%d) -- the two engines' coast windows differ\n",
                     hailo_keep_lost_frames, track_max_lost);
    }
    // Optional raw NV12 capture of the first N sink0 (detector-input) frames, for offline replay
    // work later (file-source spike). Disabled unless both fields are set.
    const json dump_cfg = cfg.value("dump_nv12", json::object());
    const std::string dump_path = dump_cfg.value("path", std::string(""));
    const int dump_frames_cfg = dump_cfg.value("frames", 0);
    const int dump_src_w = dump_cfg.value("width", 640);
    const int dump_src_h = dump_cfg.value("height", 640);
    std::signal(SIGINT, on_signal); std::signal(SIGTERM, on_signal);

    // --- media library: create, load config, select profile ---
    auto ml = MediaLibrary::create();
    if (!ml) { std::fprintf(stderr, "MediaLibrary::create failed: %d\n", (int)ml.error()); return 1; }
    MediaLibraryInterfacePtr media = ml.value();
    if (media->initialize(read_file(cfg["medialib_config"].get<std::string>())) != MEDIA_LIBRARY_SUCCESS) { std::fprintf(stderr, "media library initialize failed\n"); return 1; }
    if (media->set_profile(cfg["profile"].get<std::string>()) != MEDIA_LIBRARY_SUCCESS) { std::fprintf(stderr, "set_profile failed\n"); return 1; }

    // publish() is called from two stage threads (det_sink, jpg_sink); FeedServer serialises it internally.
    garuda::FeedServer feed(cfg.value("feed_port", 8971));
    NodeState state;
    state.snap.lock_class = track_default_class;   // until det_sink runs its first frame, report the default class
    garuda::CommandServer cmds(cfg.value("command_port", 8972), [&](const std::string& line) -> std::string {
        json req; try { req = json::parse(line); } catch (...) { return R"({"ok":false,"error":"bad json"})"; }
        if (!req.is_object()) return R"({"ok":false,"error":"bad request"})";
        // nlohmann's value()/get() throw type_error on a mistyped field (e.g. "x":"abc"); a mistyped
        // command must be answered, never allowed to unwind out of the command-server thread.
        try {
            const std::string c = req.value("cmd", "");
            std::lock_guard<std::mutex> g(state.mu);
            if (c == "lock_point") { state.pending_lock_point = std::make_pair(req.value("x", 0.0f), req.value("y", 0.0f)); return R"({"ok":true})"; }
            if (c == "target")     { state.pending_target = req.value("class", ""); return R"({"ok":true})"; }
            if (c == "cal_reset")  { state.snap.cal_n = 0; state.snap.cal_fit.reset(); return R"({"ok":true})"; }
            if (c == "cal_add")    { return R"J({"ok":false,"error":"calibration needs depth (M2)"})J"; }
            if (c == "detector")   { return req.value("mode", "") == "primary" ? R"({"ok":true})" : R"({"ok":false,"error":"only primary in v1"})"; }
            if (c == "depth_engine"){ return req.value("engine", "") == "y26d" ? R"({"ok":true})" : R"({"ok":false,"error":"only y26d in v1"})"; }
            return R"({"ok":false,"error":"unknown cmd"})";
        } catch (const std::exception&) { return R"({"ok":false,"error":"bad request"})"; }
    });
    feed.start(); cmds.start();

    // --- stages ---
    auto frontend = FrontendStageBuild::create().set_stage_name("frontend").set_leaky_opt(true).buildptr();
    if (frontend->configure(media) != AppStatus::SUCCESS) { std::fprintf(stderr, "frontend configure failed\n"); return 1; }

    // NMS floor comes from track.conf_floor, not a literal: mono runs its detector at this same low
    // floor (hosts/pi5/garuda_mono.py CONF=0.15) precisely so ByteTrack's low-score association band
    // [low_thr, high_thr) has anything to re-associate flickers against; a higher literal here would
    // silently truncate that band before det_sink's own conf_floor guard ever sees the detections.
    // set_nms_score_threshold has no effect on the yolo26m HEF (no baked NMS; the plugin applies
    // conf_thresh from yolo26_post.json); kept for the stock HEF, where it is still the live floor.
    //
    // ADDENDUM 2026-09-03 — snapshot-age backlog, mechanism and fix (bench/benchlog.md ADDENDUM
    // 2026-09-03 under the M2 section has the measured before/after numbers). Inferred from the SDK
    // headers, not measured per stage: the camera drives sink0 at 30 fps but the yolo26m HEF's own
    // multi-context compile bounds the detect stage at ~25.74 fps (hailortcli benchmark,
    // bench/benchlog.md 2026-09-03 "yolo26m from the Hailo model zoo"). Every stage between the
    // camera and det_sink defaulted to a BLOCKING (non-leaky) queue
    // (pipeline/core/queue.hpp:58 `leaky = false` is the Queue ctor default) and only ever gets
    // popped from at the detector's slower rate, so each of those queues fills once at start-up and
    // then stays full: detect's own input queue (was set_queue_size(4) below, ai_stage.hpp's
    // HailortAsyncStage) + up to 4 in-flight jobs (set_job_limit(4)) + the post stage's input queue
    // (postprocess_stage.hpp:74's `size_t queue_size = 5` builder default — this node set neither
    // set_queue_size_opt nor set_leaky_opt on it) + det_sink's own queue (1, already leaky) — a
    // standing backlog of frames waiting in FIFO order behind one another, not a processing-latency
    // increase. Fix: shrink detect's queue from 4 to 2, and give the post stage a leaky queue of
    // depth 1 — between them these bound how many stale frames can queue up ahead of the one
    // actually being processed. The mechanism doc for A.3 also called for making detect's own queue
    // leaky via detect->set_leaky(true) — HailortAsyncStage derives from ThreadedStage (ai_stage.hpp),
    // whose set_leaky(bool) IS declared public in the SDK's pipeline/core/stage.hpp:256 and IS
    // exported by the SDK's own (cross-compile-time) libhailo_analytics.so — but this specific
    // Hailo-15L SBC's DEPLOYED /usr/lib/libhailo_analytics.so.1.12.0 does not export that symbol
    // (verified with `nm -D --defined-only` on the board: neither ThreadedStage::set_leaky(bool) nor
    // even the more basic Queue::set_leaky(bool) is present, though every other ThreadedStage method
    // is) — a header/runtime version skew on this board's image, not a naming difference. Calling it
    // linked cleanly (the SDK's own .so used at link time has the symbol) but crashed the deployed
    // binary at process start with `symbol lookup error: ... undefined symbol:
    // _ZN15hailo_analytics8pipeline13ThreadedStage9set_leakyEb` (reproduced and captured verbatim,
    // see the ADDENDUM in bench/benchlog.md) — so that one sub-change is DROPPED here as impossible
    // on this board's currently-flashed image; the queue-size and post-stage leaky changes below,
    // plus the sink0 framerate/pool_max_buffers change (medialib/make_profile.py), still apply and
    // were what was actually measured.
    auto detect = HailortAsyncStageBuild::create().set_stage_name("detect").set_hef_path(cfg["hef"].get<std::string>()).set_queue_size(2)
                      .set_output_pool_size(8).set_group_id("garuda").set_batch_size(1).set_job_limit(4)
                      .set_nms_score_threshold((float)track_conf_floor).buildptr();
    auto post = PostprocessStageBuild::create().set_stage_name("post").set_so_path(cfg["postprocess_so"].get<std::string>())
                    .set_config_path_opt(cfg["postprocess_config"].get<std::string>())
                    .set_queue_size_opt(1).set_leaky_opt(true).buildptr();

    // Detection-rate counter: one line every 10 s, read by the bench harness.
    unsigned long det_frames = 0;
    auto last_fps_report = std::chrono::steady_clock::now();

    // Owned exclusively by the det_sink callback thread — never touched from the command-server
    // thread. Pointers into either are valid only until the tracker's next update() (step() itself
    // invalidates nothing). Both engines feed the same resolver; only one of tracker/hailo_adapter is
    // ever driven per frame, selected by tracker_engine.
    garuda::track::ByteTracker tracker(track_high_thr, track_low_thr, track_iou_thr, track_max_lost, track_min_hits);
    garuda::track::HailoTrackAdapter hailo_adapter(hailo_keep_lost_frames, hailo_min_hits,
                                                    hailo_dedupe_containment, hailo_dedupe_iou,
                                                    hailo_birth_conf, hailo_classes,
                                                    hailo_dedupe_protect_age);
    // Round 10 (Ruling 32b), mono engine only: track_id -> the ts_ms of the frame that id was first
    // seen on. Same det_sink-thread-only ownership as the trackers above; see the mono branch in
    // det_sink for why the birth time is kept here rather than inside the parity-pinned ByteTracker.
    std::map<int, double> mono_first_seen_ms;

    // `resolver` is constructed below, after the `lock` block is parsed -- its auto-acquire gate
    // (Ruling 16.1) is configured from that same block.

    // LockCore (F1 lock-core, include/garuda/lock_core.hpp): a dedicated, time-based locked-target
    // tracker that owns the published `lock` once it holds an identity -- see the "Lock hand-over"
    // comment in det_sink below for how it takes over from `resolver`. Config's optional `lock` block
    // overrides any subset of the header's defaults; frame_w/h always come from this node's FW/FH, not
    // the config block (there's only one frame size in this process). Same det_sink-thread-only
    // ownership rule as tracker/hailo_adapter/resolver above -- no mutex needed.
    const json lock_cfg = cfg.value("lock", json::object());
    garuda::lock::Params lock_params;
    lock_params.frame_w = FW; lock_params.frame_h = FH;
    lock_params.occlusion_ms     = lock_cfg.value("occlusion_ms", lock_params.occlusion_ms);
    lock_params.reacquire_ms     = lock_cfg.value("reacquire_ms", lock_params.reacquire_ms);
    lock_params.expire_ms        = lock_cfg.value("expire_ms", lock_params.expire_ms);
    lock_params.control_valid_ms = lock_cfg.value("control_valid_ms", lock_params.control_valid_ms);
    lock_params.gate_sigma       = lock_cfg.value("gate_sigma", lock_params.gate_sigma);
    lock_params.min_score        = lock_cfg.value("min_score", lock_params.min_score);
    // min_score_widened (final-fix wave, I6): the widened/out-of-gate stage's own floor. The header's
    // default is an explicit 0.40 since on-board fix round 3 (Ruling 19.4); an EXPLICIT JSON `null`
    // clears it back to "the same as min_score", and a number overrides it. A key that is absent
    // simply leaves the header default in place.
    if (lock_cfg.contains("min_score_widened")) {
        if (lock_cfg["min_score_widened"].is_number())
            lock_params.min_score_widened = lock_cfg["min_score_widened"].get<double>();
        else if (lock_cfg["min_score_widened"].is_null())
            lock_params.min_score_widened.reset();
    }
    // widened_new_id (on-board fix round 9, Ruling 28): false (the shipped default) means the
    // widened/out-of-gate stage accepts ONLY a candidate carrying the core's own tracker id. See
    // lock_core.hpp for why, and for the cost -- a long disappearance now ends in LOST plus a
    // visible re-lock rather than a silent transfer onto a same-class stranger.
    // widened_new_id (round 9's Ruling 28, re-scoped by round 10's Ruling 32): now the MASTER SWITCH
    // for conditional out-of-gate acceptance of a different tracker id, defaulting to true. The two
    // knobs below are conditions (d) and (e) of that ruling; condition (b) -- the id must have been
    // born after the last confirmation -- has no knob because it is the one that is never negotiable.
    lock_params.widened_new_id   = lock_cfg.value("widened_new_id", lock_params.widened_new_id);
    lock_params.widened_new_id_min_conf =
        lock_cfg.value("widened_new_id_min_conf", lock_params.widened_new_id_min_conf);
    lock_params.widened_new_id_max_age_ms =
        lock_cfg.value("widened_new_id_max_age_ms", lock_params.widened_new_id_max_age_ms);
    lock_params.ambiguity_ratio  = lock_cfg.value("ambiguity_ratio", lock_params.ambiguity_ratio);
    lock_params.size_tol         = lock_cfg.value("size_tol", lock_params.size_tol);
    lock_params.gate_max_px      = lock_cfg.value("gate_max_px", lock_params.gate_max_px);
    lock_params.q_acc_std        = lock_cfg.value("q_acc_std", lock_params.q_acc_std);
    lock_params.p0_vel_std       = lock_cfg.value("p0_vel_std", lock_params.p0_vel_std);
    lock_params.r_pos            = lock_cfg.value("r_pos", lock_params.r_pos);
    lock_params.q_size           = lock_cfg.value("q_size", lock_params.q_size);
    lock_params.r_size           = lock_cfg.value("r_size", lock_params.r_size);
    // On-board fix round 3 (Ruling 19.1-19.3): box-relative noise + the same-id relaxation.
    lock_params.r_pos_frac        = lock_cfg.value("r_pos_frac", lock_params.r_pos_frac);
    lock_params.gate_min_frac     = lock_cfg.value("gate_min_frac", lock_params.gate_min_frac);
    lock_params.r_size_frac       = lock_cfg.value("r_size_frac", lock_params.r_size_frac);
    lock_params.q_size_frac       = lock_cfg.value("q_size_frac", lock_params.q_size_frac);
    lock_params.same_id_gate_mult = lock_cfg.value("same_id_gate_mult", lock_params.same_id_gate_mult);
    // On-board fix round 5 (Ruling 22.2): the hard size-ratio cap on different-id candidates. A
    // non-positive value disables it (back to round-4 behaviour); the class gate (22.1) has no knob
    // by design -- "different class and a different id is never the same object" is not a tuning
    // parameter.
    lock_params.size_ratio_max    = lock_cfg.value("size_ratio_max", lock_params.size_ratio_max);
    lock_params.w_conf           = lock_cfg.value("w_conf", lock_params.w_conf);
    lock_params.w_motion         = lock_cfg.value("w_motion", lock_params.w_motion);
    lock_params.w_size           = lock_cfg.value("w_size", lock_params.w_size);
    lock_params.w_class          = lock_cfg.value("w_class", lock_params.w_class);
    lock_params.w_id             = lock_cfg.value("w_id", lock_params.w_id);
    // Resolver-side auto-acquire gate (Ruling 16.1) -- parsed from the same block, consumed by
    // LockResolver below, not by LockCore.
    lock_params.auto_min_conf         = lock_cfg.value("auto_min_conf", lock_params.auto_min_conf);
    lock_params.auto_edge_margin_frac = lock_cfg.value("auto_edge_margin_frac", lock_params.auto_edge_margin_frac);
    lock_params.auto_min_streak       = lock_cfg.value("auto_min_streak", lock_params.auto_min_streak);
    lock_params.auto_streak_window    = lock_cfg.value("auto_streak_window", lock_params.auto_streak_window);
    garuda::lock::LockCore lock_core(lock_params);

    // Same det_sink-thread-only ownership as tracker/hailo_adapter/lock_core.
    garuda::track::LockResolver resolver(track_max_lost, track_reacq, track_default_class,
                                         lock_params.auto_min_conf, lock_params.auto_edge_margin_frac, FW,
                                         lock_params.auto_min_streak, lock_params.auto_streak_window);
    std::printf("lock: auto-acquire gate conf>=%.2f, edge margin %.3f*%d = %.1f px, streak>=%d frames "
                "within a %d-frame window\n",
                lock_params.auto_min_conf, lock_params.auto_edge_margin_frac, FW,
                lock_params.auto_edge_margin_frac * FW, lock_params.auto_min_streak,
                lock_params.auto_streak_window);
    // On-board fix round 3 (Ruling 19): the box-relative gate parameters, printed so a deployed build
    // can be identified from its own log without reading /opt/garuda/perception.json.
    std::printf("lock: core gates r_pos_frac=%.2f gate_min_frac=%.2f r_size_frac=%.2f q_size_frac=%.2f "
                "same_id_gate_mult=%.2f min_score=%.2f min_score_widened=%.2f size_ratio_max=%.2f\n",
                lock_params.r_pos_frac, lock_params.gate_min_frac, lock_params.r_size_frac,
                lock_params.q_size_frac, lock_params.same_id_gate_mult, lock_params.min_score,
                lock_params.min_score_widened.value_or(lock_params.min_score),
                lock_params.size_ratio_max);
    // Round 5 (Ruling 22.1): the class gate is unconditional, so say so in the same startup block --
    // a deployed build's own log is where a capture's behaviour has to be explainable from.
    std::printf("lock: class gate on (a different-class candidate is eligible only on the core's own "
                "track id); lock.class publishes the last associated observation's class\n");
    garuda::lock::State lock_logged_state = garuda::lock::State::NONE;   // for the transition log below
    // Transition logging is rate-limited PER DIRECTION (final-fix wave, M4): a detector missing every
    // other frame produces CONFIRMED<->OCCLUDED at frame rate, which at ~25 fps is 25 lines/s into the
    // board's tmpfs log. At most one line per second per (from -> to) pair; the next line that does
    // print for that pair carries how many of its own kind were suppressed in between.
    struct TransLog { std::chrono::steady_clock::time_point last{}; bool printed = false; unsigned suppressed = 0; };
    TransLog lock_trans_log[5][5];   // indexed by (int)State -- NONE..LOST, five enumerators

    // Nominal sink0 frame interval, resolved once from the media-library config chain that the node is
    // already pointed at (top config -> the named profile -> its application_settings -> the ai_stream
    // entry's `framerate`). Used ONLY by the isp_timestamp_ns == 0 fallback below (final-fix wave, M2);
    // 0 means "not resolvable here", in which case that fallback uses the last measured frame interval.
    // Best-effort by construction: any missing file/field leaves it 0 rather than failing startup.
    double nominal_interval_ms = 0.0;
    try {
        const json ml_top = json::parse(read_file(cfg["medialib_config"].get<std::string>()));
        const std::string want_profile = cfg.value("profile", std::string());
        const std::string want_stream = cfg.value("ai_stream", std::string("sink0"));
        std::string profile_path;
        for (const auto& p : ml_top.value("profiles", json::array()))
            if (p.value("name", std::string()) == want_profile) profile_path = p.value("config_file", std::string());
        if (!profile_path.empty()) {
            const json prof = json::parse(read_file(profile_path));
            const std::string app_path = prof.value("application_settings", std::string());
            if (!app_path.empty()) {
                const json app = json::parse(read_file(app_path));
                const json streams = app.value("application_input_streams", json::object());
                for (const auto& r : streams.value("resolutions", json::array())) {
                    if (r.value("stream_id", std::string()) != want_stream) continue;
                    const double fps = r.value("framerate", 0.0);
                    if (fps > 0.0) nominal_interval_ms = 1000.0 / fps;
                }
            }
        }
    } catch (const std::exception& e) {
        std::fprintf(stderr, "lock: could not read the sink0 framerate from the media-library config (%s)"
                             " -- the zero-timestamp fallback will use the last measured frame interval\n", e.what());
    }
    if (nominal_interval_ms > 0.0)
        std::printf("lock: nominal frame interval %.2f ms (from the media-library profile's %s framerate)\n",
                    nominal_interval_ms, cfg.value("ai_stream", std::string("sink0")).c_str());

    // Previous ts_ms handed to LockCore, and whether it came from a real ISP timestamp (det_sink
    // thread only, like the tracker/resolver/core above). -1 == no frame yet.
    double lock_prev_ts_ms = -1.0;
    bool lock_prev_ts_from_isp = false;
    double lock_last_dt_ms = 0.0;

    // NV12 dump state (det_sink-thread only, like the tracker/resolver above). dump_active starts
    // false when the config leaves path empty or frames <= 0, and det_sink never opens the file.
    std::ofstream dump_file;
    int dump_frames_written = 0;
    bool dump_active = !dump_path.empty() && dump_frames_cfg > 0;

    // Detections callback: HailoBBox is normalized [0..1] -> scale to the 1280x720 coordinate frame.
    auto det_sink = AppSinkStageBuild::create().set_stage_name("det_sink").set_leaky_opt(true).set_process_func([&](BufferPtr buf) {
        auto roi = buf->get_roi(); if (!roi) return;
        auto mlb = buf->get_buffer();

        // Raw sink0 NV12 dump (geometry from perception.json's dump_nv12.width/height, defaults
        // 640x640 to match the M2 letterboxed profile — independent of FW/FH above, which is the
        // full-FOV frame used only for bbox scaling). Row-by-row copy strips each plane's stride
        // padding so the file is a plain, concatenated NV12 sequence.
        if (dump_active) {
            if (!dump_file.is_open()) {
                dump_file.open(dump_path, std::ios::binary | std::ios::trunc);
                if (!dump_file.is_open()) {
                    static bool warned = false;
                    if (!warned) { warned = true; std::fprintf(stderr, "dump_nv12: failed to open %s for writing, disabling\n", dump_path.c_str()); }
                    dump_active = false;
                }
            }
            // dump_src_w/h come from perception.json's dump_nv12.width/height — the source of truth
            // for the actual value is hosts/hailo15l/medialib/make_profile.py's sink0 resolution;
            // if that profile's sink0 resolution ever changes, dump_nv12's width/height must move
            // with it.
            const int DUMP_SRC_W = dump_src_w, DUMP_SRC_H = dump_src_h;
            // mlb/buffer_data/plane-count missing is treated as a transient no-buffer frame (same as
            // jpg_sink's equivalent check below) and just skips this frame; a plane-SIZE mismatch below
            // is a persistent config problem (sink0's profile resolution no longer matches DUMP_SRC_W/H)
            // and gets its own warn-once + disable, same as the open/write failure paths above.
            if (dump_active && mlb && mlb->buffer_data && mlb->get_num_of_planes() >= 2) {
                if (mlb->get_plane_size(0) >= (size_t)mlb->get_plane_stride(0) * DUMP_SRC_H &&
                    mlb->get_plane_size(1) >= (size_t)mlb->get_plane_stride(1) * (DUMP_SRC_H / 2)) {
                    auto y = (const unsigned char*)mlb->get_plane_ptr(0);
                    auto uv = (const unsigned char*)mlb->get_plane_ptr(1);
                    if (y && uv) {
                        for (int row = 0; row < DUMP_SRC_H; ++row)
                            dump_file.write((const char*)(y + (size_t)row * mlb->get_plane_stride(0)), DUMP_SRC_W);
                        for (int row = 0; row < DUMP_SRC_H / 2; ++row)
                            dump_file.write((const char*)(uv + (size_t)row * mlb->get_plane_stride(1)), DUMP_SRC_W);
                        // dump_frames_written only advances (and the success line only prints) once the
                        // frame's bytes are confirmed good — a partial/failed write (disk full, I/O
                        // error) must never be followed by "dumped N frames" over a truncated file.
                        if (!dump_file.good()) {
                            std::fprintf(stderr, "dump_nv12: write failed after %d frames to %s, disabling\n", dump_frames_written, dump_path.c_str());
                            dump_file.close();
                            dump_active = false;
                        } else if (++dump_frames_written >= dump_frames_cfg) {
                            dump_file.close();
                            dump_active = false;
                            std::printf("dumped %d frames to %s\n", dump_frames_written, dump_path.c_str());
                            std::fflush(stdout);
                        }
                    }
                } else {
                    // Plane-size guard failed: sink0's buffer geometry doesn't match DUMP_SRC_W/H.
                    // Warn once and disable so the dump never stays silently armed against a buffer it
                    // can never safely read.
                    static bool warned_geom = false;
                    if (!warned_geom) { warned_geom = true; std::fprintf(stderr, "dump_nv12: sink0 buffer geometry does not match expected %dx%d, disabling\n", DUMP_SRC_W, DUMP_SRC_H); }
                    dump_active = false;
                }
            }
        }

        // engine == "mono" builds Det (ByteTrack's own input, no identity yet); engine == "hailo" builds
        // IdDet (the SDK's TrackerStage has already assigned the id, carried as a HailoUniqueID object
        // in TRACKING_ID mode on the detection). The conf_floor guard applies identically to both.
        std::vector<garuda::track::Det> dets;
        std::vector<garuda::track::IdDet> iddets;
        size_t missing_id = 0;
        // Round 9 `diag.raw_dets`: what the post-process handed the tracker this frame. Visible only
        // on the mono path, where "post" feeds det_sink directly. Under the hailo engine the SDK's
        // TrackerStage sits between post and this sink and rewrites the ROI, so the pre-tracker list
        // is not observable from here at all -- published as -1, never as this frame's post-tracker
        // count dressed up as a detector count (see hosts/hailo15l/README.md §9).
        int diag_raw_dets = use_hailo_tracker ? -1 : 0;
        for (auto& d : hailo_common::get_hailo_detections(roi)) {
            if (!use_hailo_tracker) ++diag_raw_dets;
            double conf = d->get_confidence();
            if (conf < track_conf_floor) continue;   // below the tracker's floor: never handed to update()
            HailoBBox b = d->get_bbox();
            // The post-process plugin already un-letterboxed and normalised to the frame. Only the
            // ASPECT RATIO of yolo26_post.json's frame_w/frame_h need match this frame_w/frame_h,
            // not their absolute values: the plugin normalises each box by dividing by its own
            // frame_w/frame_h (yolo26_post.cpp's HailoBBox construction), and every one of decode()'s
            // pixel-space geometry terms (letterbox padding, box centre/extent) scales linearly with
            // the frame dimensions passed into it — so a uniform scale factor between the plugin's
            // frame_w/h and this FW/FH cancels exactly, and only a shape (aspect-ratio) mismatch
            // would produce wrong letterbox padding and therefore wrong boxes. The stock yolov8n path
            // is a STRETCH of the same FOV — both map by simple multiplication.
            double x = b.xmin() * FW, y = b.ymin() * FH, w = b.width() * FW, h = b.height() * FH;
            // A NaN/Inf box or confidence (bad postprocess output) must never reach the tracker's sort
            // comparator -- std::sort has undefined behaviour under a non-strict-weak-ordering comparator,
            // which any NaN-bearing comparison silently violates.
            if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(w) || !std::isfinite(h) || !std::isfinite(conf)) continue;
            if (use_hailo_tracker) {
                auto ids = hailo_common::get_hailo_track_id(d);   // TRACKING_ID-mode HailoUniqueID, set by the tracker stage upstream
                if (ids.empty()) { ++missing_id; continue; }      // no id yet (e.g. stage not yet warmed up): drop, never guess one
                iddets.push_back({ids[0]->get_id(), d->get_label(), conf, x, y, w, h});
            } else {
                dets.push_back({x, y, w, h, d->get_label(), conf});
            }
        }
        // Under a single tracked class (classification_id != -1), a same-frame detection of every
        // OTHER class is expected to arrive with no tracking id -- that's the whole point of
        // classification_id (block_non_tracked_classification_id stays false so those detections
        // still reach det_sink, but they're never meant to become tracks). Warning about that every
        // run would just be noise, so the warn-once line only fires when every class is being
        // tracked (classification_id == -1), where a missing id is genuinely unexpected (e.g. the
        // stage still warming up); missing_id is still counted either way for anyone reading it off
        // a debugger/log inspection later.
        if (missing_id && hailo_classification_id == -1) {
            static bool warned_missing_id = false;
            if (!warned_missing_id) { warned_missing_id = true; std::fprintf(stderr, "hailo tracker: %zu detection(s) with no tracking id this frame, dropped\n", missing_id); }
        }

        // Per-frame order (matches tests/test_lock.cpp's replay of the golden): target -> click -> update -> step.
        bool target_changed = false;
        std::optional<int> clicked_id;
        // Operator-event logging (on-board fix round 4 addendum). A click and a `target` command are
        // the ONLY two paths in this node that call lock_core.unlock(), and both therefore show up in
        // a capture as an epoch change (or a bare NONE) with no preceding LOST row -- which, until
        // this commit, was indistinguishable from a silent internal re-lock when reading a capture
        // after the fact. The fast-lateral run had exactly one such unexplained unlock at rel.
        // 401.58 s and nothing in the log to attribute it to. These are operator events (a handful
        // per routine), not per-frame state, so they are logged unconditionally and unthrottled --
        // unlike the lock transition log above, which is rate-limited per direction.
        std::optional<std::pair<float, float>> logged_click;
        std::optional<std::string> logged_target;
        {
            std::lock_guard<std::mutex> g(state.mu);
            if (state.pending_target) {
                logged_target = *state.pending_target;
                resolver.set_target(*state.pending_target); state.pending_target.reset(); target_changed = true;
            }
            if (state.pending_lock_point) {
                auto [px, py] = *state.pending_lock_point; state.pending_lock_point.reset();
                logged_click = std::make_pair(px, py);
                if (resolver.click(px, py)) clicked_id = resolver.lock_id();   // click() sets m_lid immediately on a pick
            }
        }
        // Separate branches rather than a ternary format string: the cross-build runs with
        // -Werror=format-security, which rejects a non-literal format argument.
        if (logged_target) {
            if (logged_target->empty()) std::printf("lock: target cleared\n");
            else                        std::printf("lock: target '%s'\n", logged_target->c_str());
        }
        if (logged_click) {
            if (clicked_id) std::printf("lock: click (%.0f,%.0f) -> id %d\n",
                                        logged_click->first, logged_click->second, *clicked_id);
            else            std::printf("lock: click (%.0f,%.0f) -> no track\n",
                                        logged_click->first, logged_click->second);
        }
        // Round 10 (Ruling 32b) moved this block ABOVE the tracker update: the hailo adapter now
        // stamps each id's `first_seen_ms` with the frame's timestamp, so ts_ms has to exist before
        // update() runs. Nothing in the computation depends on this frame's tracking -- it reads
        // only the buffer's ISP timestamp and the PREVIOUS frame's lock state -- so moving it is
        // behaviour-neutral (the click/target handling above still unlocks later, unchanged).
        // ts_ms: the frame's ISP clock in milliseconds -- what every LockCore window (occlusion_ms,
        // reacquire_ms, expire_ms, ...) is measured against. isp_timestamp_ns == 0 means no valid ISP
        // clock for this frame (assumed to be the very first frames only -- whether it EVER happens
        // mid-stream on this board is an open question, listed in bench/benchlog.md's F1 deferred
        // items). Logged once, since the real clock should be available well before the
        // reacquire/expire windows (seconds) could matter.
        //
        // Final-fix wave (M2): the fallback must not change clock domain under a live lock. A single
        // steady_clock reading dropped into an ISP-clock series makes obs_age_ms either enormous
        // (instant LOST) or negative -- so while the core HOLDS an identity, a zero timestamp is
        // filled in as "the last timestamp plus one nominal frame interval" (the sink0 framerate read
        // from the media-library profile at startup, else the last measured interval, else no advance
        // at all), keeping the series in the ISP's own domain and monotonic. The steady_clock fallback
        // survives only for the case it was written for: no lock held (nothing to disturb) and no
        // earlier timestamp to extend.
        const bool ts_from_isp = (mlb && mlb->isp_timestamp_ns);
        double ts_ms;
        if (ts_from_isp) {
            ts_ms = (double)mlb->isp_timestamp_ns / 1.0e6;
        } else {
            static bool warned_ts0 = false;
            if (!warned_ts0) { warned_ts0 = true; std::fprintf(stderr, "lock: isp_timestamp_ns is 0 this frame, falling back to steady_clock ms\n"); }
            if (lock_core.last().identity_locked && lock_prev_ts_ms >= 0.0) {
                const double step = nominal_interval_ms > 0.0 ? nominal_interval_ms
                                  : (lock_last_dt_ms > 0.0 ? lock_last_dt_ms : 0.0);
                ts_ms = lock_prev_ts_ms + step;
            } else {
                ts_ms = (double)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
            }
        }
        // The measured interval is only meaningful between two consecutive REAL ISP timestamps.
        if (ts_from_isp && lock_prev_ts_from_isp && ts_ms > lock_prev_ts_ms) lock_last_dt_ms = ts_ms - lock_prev_ts_ms;
        lock_prev_ts_ms = ts_ms;
        lock_prev_ts_from_isp = ts_from_isp;

        garuda::track::LockResult lr;
        // live_obs: this frame's LIVE (time_since_update == 0) records only, in garuda::lock::Obs form
        // -- the input LockCore::update() expects (task-2-brief.md Step 2: "coasting records are NOT
        // observations"). Built alongside each engine's own step() call since both already walk the
        // same per-frame record set.
        //
        // On-board fix round 9 (Ruling 26): under the HAILO engine this is now built from
        // `hailo_adapter.live_raw()` -- the live records after the class allow-list ONLY -- not from
        // update()'s published output. The birth gate and the dedupe are DISPLAY gates: they decide
        // what is drawn and what may become a NEW lock, not what an EXISTING lock may keep tracking.
        // A locked phone dipping to conf 0.3 for a second, or a locked person momentarily swallowed
        // by a nearer person's box, is exactly when the core needs the measurement most.
        //
        // `seed_obs` is the other half of that split: the PUBLISHED live records, and the only pool
        // the two new-lock paths below (a click, and the resolver's generic hand-over) are allowed to
        // seed from. So a new lock still requires a track the operator can actually see, while
        // maintaining or recovering one may use any live detection. Under the mono engine the two
        // pools are the same list and `seed_obs` is left empty, with `seed_pool` pointing at
        // `live_obs` -- mono's behaviour is unchanged by this ruling.
        std::vector<garuda::lock::Obs> live_obs, seed_obs;
        const std::vector<garuda::lock::Obs>* seed_pool = &live_obs;
        int diag_sdk_tracks = -1, diag_live_raw = -1;
        if (use_hailo_tracker) {
            diag_sdk_tracks = (int)iddets.size();
            // The dedupe must not suppress the locked identity (Ruling 27). The resolver's pick from
            // the PREVIOUS frame is the best answer available at this point in the frame -- step()
            // has not run yet -- which is a one-frame lag on a value that changes rarely.
            hailo_adapter.set_protected_id(resolver.lock_id() ? *resolver.lock_id() : -1);
            // ts_ms (computed above) stamps each id's first_seen_ms the frame it is first seen --
            // round 10, Ruling 32b. Both Obs pools carry it through to LockCore.
            auto records = hailo_adapter.update(iddets, ts_ms);
            const auto& raw = hailo_adapter.live_raw();
            diag_live_raw = (int)raw.size();
            live_obs.reserve(raw.size());
            for (auto& r : raw)
                live_obs.push_back({r.id, r.cls, r.conf, r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3],
                                     r.first_seen_ms});
            // `r.confirmed` as well as tsu == 0, symmetrically with the mono path below (final-fix
            // wave, M6). Moot at the shipped min_hits 1, but a future min_hits > 1 must not let a
            // NEW lock be seeded from a record the resolver itself would never pick.
            seed_obs.reserve(records.size());
            for (auto& r : records)
                if (r.time_since_update == 0 && r.confirmed)
                    seed_obs.push_back({r.id, r.cls, r.conf, r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3],
                                         r.first_seen_ms});
            seed_pool = &seed_obs;
            lr = resolver.step(records);
        } else {
            tracker.update(dets);
            // Round 10 (Ruling 32b), mono side: `garuda::track::Track` has no birth timestamp, and
            // bytetrack.{hpp,cpp} is a line-for-line port pinned by tests/golden/bytetrack_ref.py --
            // adding a field or a ts parameter there would break that parity contract for a reason
            // unrelated to tracking. So the birth time is recorded HERE instead, in a map owned by
            // this callback thread: the first frame an id is seen, its ts_ms is stored; ids that have
            // disappeared from tracker.tracks() are erased, so a reused id is re-stamped exactly as
            // the hailo adapter's per-Entry field would be. Same rule, same clock, no change to the
            // parity-pinned tracker.
            for (auto it = mono_first_seen_ms.begin(); it != mono_first_seen_ms.end(); ) {
                bool still_there = false;
                for (auto& t : tracker.tracks())
                    if (t.track_id == it->first) { still_there = true; break; }
                it = still_there ? std::next(it) : mono_first_seen_ms.erase(it);
            }
            for (auto& t : tracker.tracks()) mono_first_seen_ms.emplace(t.track_id, ts_ms);
            for (auto& t : tracker.tracks())
                if (t.time_since_update == 0 && t.confirmed())
                    live_obs.push_back({t.track_id, t.cls, t.conf, t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3],
                                         mono_first_seen_ms[t.track_id]});
            diag_live_raw = (int)live_obs.size();
            lr = resolver.step(tracker);
        }


        // Lock hand-over (task-2-brief.md Step 2). `resolver` keeps making its own class/click/coast/
        // re-acquire pick every frame purely for its own bookkeeping (m_prev for the next click(), and
        // lr.lock_id/lr.coasting below feed nothing into the publish once LockCore holds an identity):
        //  - a target change always drops whatever LockCore was holding -- the user chose a new class;
        //  - ON ANY FRAME CARRYING A CLICK, the ONLY thing that may seed the core is the CLICKED id's
        //    own live observation -- never the generic lr.lock_id path (Ruling 5; extended to every
        //    path by the final-fix wave, I4/Ruling 12: fix round 1 enforced this only when the core was
        //    already holding an identity, leaving the common case -- the first click of a session, or
        //    any click after a LOST -- still going through lr.lock_id). It matters because
        //    LockResolver::step() runs its own re-acquire jump AFTER click() has set m_lid, so a click
        //    on a box that is coasting past the resolver's `reacq` threshold can leave lr.lock_id
        //    pointing at a DIFFERENT live same-class track on that same frame; locking onto that would
        //    hand the lock to an object the user did not click. If the clicked id is not live this
        //    frame, the core is left with nothing (Ruling 4: it seeds only from a live measurement) and
        //    the generic hand-over does NOT run as a fallback on this same frame -- no "pending click
        //    id" is stored. Accepted residual until F5 (click-frame sync): on the NEXT frame the
        //    generic path may lock the resolver's own (possibly drifted) pick.
        //    A click on the id the core ALREADY holds changes nothing -- it is a re-affirmation, and
        //    the core keeps tracking through update() as usual.
        //  - whenever LockCore is left with no identity (NONE or LOST) on a frame with NO click, and
        //    the resolver has a pick this frame that IS one of this frame's live observations,
        //    LockCore locks onto it (the target-change path, and the ordinary "nothing has ever been
        //    locked yet" / post-LOST path).
        // While LockCore already holds an identity and none of the above fires, the resolver's own
        // re-acquire jump is never applied to the publish -- LockCore's own update() below is the only
        // thing that can move the published lock.
        if (target_changed) lock_core.unlock();
        bool core_none_or_lost = lock_core.last().state == garuda::lock::State::NONE
                               || lock_core.last().state == garuda::lock::State::LOST;
        bool locked_this_frame = false;
        bool click_handled = false;   // true once the click branch below fires -- blocks the generic
                                      // hand-over from ALSO running this same frame, whether the click
                                      // branch itself managed to lock or not.
        // Both new-lock paths below search `*seed_pool`, the PUBLISHED live records (Ruling 26) --
        // never `live_obs`, which since round 9 also carries records the birth gate or the dedupe
        // kept off the screen. Taking a NEW lock on a box the operator cannot see would be a worse
        // failure than missing one.
        if (clicked_id && !(!core_none_or_lost && *clicked_id == lock_core.last().last_id)) {
            click_handled = true;
            lock_core.unlock();       // a click always drops what was held (a no-op when nothing was)
            for (auto& o : *seed_pool) {
                if (o.id == *clicked_id) { lock_core.lock(o, ts_ms); locked_this_frame = true; break; }
            }
            core_none_or_lost = !locked_this_frame;   // stays NONE if the clicked id wasn't live this frame
        }
        if (!click_handled && core_none_or_lost && lr.lock_id) {
            for (auto& o : *seed_pool) {
                if (o.id == *lr.lock_id) { lock_core.lock(o, ts_ms); locked_this_frame = true; break; }
            }
        }
        // A frame that just called lock() above already has this frame's Output cached in last() --
        // update() is for every OTHER frame, to advance the filters/state machine. Calling both in the
        // same frame would double-process this frame's observations against a filter already seeded by
        // them.
        garuda::lock::Output lock_out = locked_this_frame ? lock_core.last() : lock_core.update(ts_ms, live_obs);
        if (lock_out.state != lock_logged_state) {   // once per transition, never per frame
            TransLog& tl = lock_trans_log[(int)lock_logged_state][(int)lock_out.state];
            auto now = std::chrono::steady_clock::now();
            if (!tl.printed || now - tl.last >= std::chrono::seconds(1)) {
                if (tl.suppressed)
                    std::printf("lock: %s -> %s (obs_age_ms=%.0f) [+%u suppressed]\n",
                                garuda::lock::state_name(lock_logged_state), garuda::lock::state_name(lock_out.state),
                                lock_out.obs_age_ms, tl.suppressed);
                else
                    std::printf("lock: %s -> %s (obs_age_ms=%.0f)\n",
                                garuda::lock::state_name(lock_logged_state), garuda::lock::state_name(lock_out.state), lock_out.obs_age_ms);
                std::fflush(stdout);
                tl.last = now; tl.printed = true; tl.suppressed = 0;
            } else {
                ++tl.suppressed;   // reported on this direction's next printed line
            }
            lock_logged_state = lock_out.state;
        }

        garuda::SnapshotState s; s.frame_w = FW; s.frame_h = FH;
        for (auto& t : lr.alive)
            s.tracks.push_back({t.id, t.cls, t.conf,
                                 (float)t.bbox[0], (float)t.bbox[1], (float)t.bbox[2], (float)t.bbox[3],
                                 t.time_since_update > 0});
        // The published `lock` comes entirely from LockCore's Output, not from `lr` -- see the
        // hand-over comment above. Final-fix wave (M5): `id` is null (and `class` empty) whenever the
        // core holds NO identity -- NONE, and also LOST, where `last_id` still names the id the lock
        // last sat on but no track carries it any more. That keeps the pre-LockCore contract "a
        // non-null lock.id means something is locked"; `state`/`epoch` are where a consumer looks for
        // what the lock was doing.
        s.lock_id = (lock_out.identity_locked && lock_out.last_id >= 0) ? std::optional<int>(lock_out.last_id) : std::nullopt;
        s.lock_class = lock_out.identity_locked ? lock_out.cls : std::string();
        s.lock_coasting = lock_out.identity_locked && !lock_out.observation_valid;
        s.lock_state = garuda::lock::state_name(lock_out.state);
        s.lock_identity_locked = lock_out.identity_locked;
        s.lock_observation_valid = lock_out.observation_valid;
        s.lock_quality = lock_out.quality;
        s.lock_obs_age_ms = lock_out.obs_age_ms;
        s.lock_uncertainty_px = lock_out.uncertainty_px;
        // Additive (final-fix wave, I2/I5): the lock generation, and LockCore's OWN published box --
        // the filtered box while CONFIRMED, the frozen last-confirmed box while OCCLUDED/REACQUIRING,
        // null while NONE/LOST. Distinct from the same-id `tracks[]` entry, which is the tracker
        // engine's box (ByteTrack extrapolates it while coasting; the hailo adapter freezes it).
        s.lock_epoch = lock_out.epoch;
        if (lock_out.box)
            s.lock_box = garuda::LockBox{lock_out.box->x, lock_out.box->y, lock_out.box->w, lock_out.box->h};

        if (mlb && mlb->isp_timestamp_ns) {
            auto now_ns = (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
            s.age_ms = (long)((now_ns > mlb->isp_timestamp_ns ? now_ns - mlb->isp_timestamp_ns : 0) / 1000000ULL);
        }
        // On-board fix round 9 (Ruling 30): FRESHNESS, and the first consumer of `control_valid_ms`
        // (parsed since F1, used by nothing until now). Both halves of the staleness a follow
        // controller actually experiences are added: how long ago the core last saw the target
        // (obs_age_ms) and how long ago the frame it saw it in was captured (age_ms, this snapshot's
        // own capture-to-publish age). Computed AFTER age_ms above, deliberately -- it is a function
        // of it. A frame with no ISP timestamp leaves age_ms null; 0 is then the only honest
        // substitute available here (we know nothing worse), and the snapshot still carries the null
        // so a consumer can see that the transport half is unmeasured on that row.
        s.lock_control_valid = lock_out.observation_valid
                             && (lock_out.obs_age_ms + (double)s.age_ms.value_or(0))
                                    <= lock_params.control_valid_ms;
        // Round 9: per-frame stage counters. `published` is the snapshot's own tracks[] (the
        // resolver's alive list), so the five numbers read left-to-right as the frame's pipeline.
        s.diag_raw_dets = diag_raw_dets;
        s.diag_sdk_tracks = diag_sdk_tracks;
        s.diag_live_raw = diag_live_raw;
        s.diag_published = (int)s.tracks.size();
        s.diag_core_candidates = (int)live_obs.size();
        { std::lock_guard<std::mutex> g(state.mu); state.snap = s; }
        feed.publish('S', garuda::build_snapshot_json(s));
        ++det_frames;
        auto tnow = std::chrono::steady_clock::now();
        if (tnow - last_fps_report >= std::chrono::seconds(10)) {
            std::printf("frames=%lu fps=%.1f\n", det_frames, det_frames / 10.0);
            std::fflush(stdout);
            det_frames = 0; last_fps_report = tnow;
        }
    }).buildptr();

    // JPEG callback on sink1 (1280x720 NV12), capped at jpeg_fps.
    garuda::JpegEncoder jpeg(cfg.value("jpeg_quality", 80));
    const auto min_gap = std::chrono::milliseconds(1000 / std::max(1, cfg.value("jpeg_fps", 15)));
    auto last_jpeg = std::chrono::steady_clock::now() - min_gap;
    auto jpg_sink = AppSinkStageBuild::create().set_stage_name("jpg_sink").set_leaky_opt(true).set_process_func([&](BufferPtr buf) {
        auto now = std::chrono::steady_clock::now(); if (now - last_jpeg < min_gap) return; last_jpeg = now;
        auto mlb = buf->get_buffer(); if (!mlb || !mlb->buffer_data || mlb->get_num_of_planes() < 2) return;
        auto y = (const unsigned char*)mlb->get_plane_ptr(0); auto uv = (const unsigned char*)mlb->get_plane_ptr(1);
        if (!y || !uv) return;
        // Frame geometry comes from perception.json; never read past the end of a smaller buffer.
        if (mlb->get_plane_size(0) < (size_t)mlb->get_plane_stride(0) * FH ||
            mlb->get_plane_size(1) < (size_t)mlb->get_plane_stride(1) * (FH / 2)) {   // NV12: UV plane has FH/2 rows
            static bool warned = false;
            if (!warned) { warned = true; std::fprintf(stderr, "jpg_sink: sink1 buffer smaller than configured %dx%d — check perception.json vs garuda_medialib_config.json\n", FW, FH); }
            return;
        }
        auto bytes = jpeg.encode_nv12(y, (int)mlb->get_plane_stride(0), uv, (int)mlb->get_plane_stride(1), FW, FH);
        feed.publish('J', std::string((const char*)bytes.data(), bytes.size()));
    }).buildptr();

    // --- pipeline ---
    // tracker.engine "hailo" inserts the SDK's Kalman TrackerStage between "post" and "det_sink";
    // "mono" (default) wires post straight to det_sink, unchanged from before this feature.
    std::shared_ptr<hailo_analytics::pipeline::ai::TrackerStage> tracker_stage;
    if (use_hailo_tracker) {
        // classification_id (config-driven, default -1 = every class; the Builder's own default is 1,
        // a single class, overridden either way). Field finding, 2026-09-03, corrected 2026-09-04: the
        // SDK tracker is ONE class-agnostic tracker with one-to-one LAPJV assignment, not per-class
        // matching -- tracking "every class" at once (-1) means an overlapping, different-class
        // detection on the same physical object competes for that object's track slot in the SAME
        // assignment problem, and can win it (fragmenting a real object into a new id whenever the
        // detector's winning class flickers for one frame). Setting this to one class
        // (config/perception-yolov8m.json: 1 = person, stock post-process labelmap) is the demo-style
        // fix: restricting which class is ever handed to the tracker removes the competition entirely,
        // rather than enabling genuine per-class association (there is no such mode). block_non_tracked
        // stays false regardless, so a detection of a DIFFERENT class (or one Hailo declines to assign
        // an id to, e.g. the stage still warming up) still reaches det_sink rather than disappearing
        // upstream -- it carries no tracking id there, so it is dropped by the existing missing-id path
        // (the missing_id counter above), same as before; it never becomes a track or a snapshot entry.
        tracker_stage = TrackerStageBuild::create().set_stage_name("tracker").set_queue_size_opt(1)
                            .set_leaky_opt(true).set_classification_id(hailo_classification_id)
                            .set_block_non_tracked_classification_id(false).buildptr();
    }
    PipelineBuilder pb;
    pb.add_stage("frontend", frontend, StageType::SOURCE).add_stage("detect", detect).add_stage("post", post)
      .add_stage("det_sink", det_sink, StageType::SINK).add_stage("jpg_sink", jpg_sink, StageType::SINK);
    if (use_hailo_tracker) {
        pb.add_stage("tracker", tracker_stage);
        pb.connect_frontend("frontend", cfg["ai_stream"].get<std::string>(), "detect").connect("detect", "post")
          .connect("post", "tracker").connect("tracker", "det_sink")
          .connect_frontend("frontend", cfg["jpeg_stream"].get<std::string>(), "jpg_sink");
    } else {
        pb.connect_frontend("frontend", cfg["ai_stream"].get<std::string>(), "detect").connect("detect", "post")
          .connect("post", "det_sink")
          .connect_frontend("frontend", cfg["jpeg_stream"].get<std::string>(), "jpg_sink");
    }
    auto pipeline = pb.build("garuda-perception");

    // Apply the hailo tracker's Kalman/IoU/keep-frame parameters right after build(), before start().
    // HailoTracker::GetInstance()'s setters (hailo_tracker.hpp) reach the singleton's tracker map via
    // std::map<string,JDETracker>::operator[], which default-constructs a "hailo_tracker" entry using
    // JDETracker's own defaults (hailo_tracker.cpp, hailo-postprocess-tools src) if TrackerStage::init()
    // has not registered one yet -- and those defaults are the exact same DEFAULT_* constants this file
    // falls back to above, so whichever runs first (these setters, or init()'s own add_jde_tracker(),
    // which is a std::map::emplace and therefore a no-op once the key exists) the six fields below end
    // up correct either way; applying them here (rather than deferred into det_sink's first frame) also
    // means init()'s own add_jde_tracker() -- whose HailoTrackerParams argument this file cannot
    // inspect -- can never be the one to win a conflicting write. Verified empirically on the board
    // (README.md, "Tracker engines"): the log line below prints, no error/exception appears, and the
    // configured values are the ones actually applied.
    if (use_hailo_tracker) {
        auto& ht = HailoTracker::GetInstance();
        ht.set_kalman_distance("hailo_tracker", hailo_kalman_distance);
        ht.set_iou_threshold("hailo_tracker", hailo_iou_threshold);
        ht.set_init_iou_threshold("hailo_tracker", hailo_init_iou_threshold);
        ht.set_keep_tracked_frames("hailo_tracker", hailo_keep_tracked_frames);
        ht.set_keep_new_frames("hailo_tracker", hailo_keep_new_frames);
        ht.set_keep_lost_frames("hailo_tracker", hailo_keep_lost_frames);
        // classes=* means the allow-list is empty (every class); otherwise a comma-joined label list.
        std::string hailo_classes_str = "*";
        if (!hailo_classes.empty()) {
            hailo_classes_str.clear();
            for (size_t i = 0; i < hailo_classes.size(); ++i) {
                if (i) hailo_classes_str += ",";
                hailo_classes_str += hailo_classes[i];
            }
        }
        std::printf("tracker.engine=hailo classification_id=%d kalman_distance=%.2f iou_threshold=%.2f init_iou_threshold=%.2f "
                     "keep_tracked_frames=%d keep_new_frames=%d keep_lost_frames=%d min_hits=%d "
                     "dedupe_containment=%.2f dedupe_iou=%.2f dedupe_protect_age=%d birth_conf=%.2f classes=%s\n",
                     hailo_classification_id, (double)hailo_kalman_distance, (double)hailo_iou_threshold, (double)hailo_init_iou_threshold,
                     hailo_keep_tracked_frames, hailo_keep_new_frames, hailo_keep_lost_frames, hailo_min_hits,
                     hailo_dedupe_containment, hailo_dedupe_iou, hailo_dedupe_protect_age,
                     hailo_birth_conf, hailo_classes_str.c_str());
        std::fflush(stdout);
    }
    // Round 9: the three lock parameters a reader of a capture needs in order to interpret it --
    // widened_new_id (Ruling 28) decides whether an out-of-gate stranger can ever be taken,
    // control_valid_ms (Ruling 30) is the freshness budget lock.control_valid is measured against,
    // and expire_ms (Ruling 29) is now enforced on elapsed time rather than on delivered frames.
    std::printf("lock: widened_new_id=%s (min_conf=%.2f max_age_ms=%.0f, born-after-loss required) "
                 "control_valid_ms=%.0f expire_ms=%.0f\n",
                 lock_params.widened_new_id ? "true" : "false",
                 lock_params.widened_new_id_min_conf, lock_params.widened_new_id_max_age_ms,
                 lock_params.control_valid_ms, lock_params.expire_ms);
    std::fflush(stdout);

    if (media->start_pipeline() != MEDIA_LIBRARY_SUCCESS) { std::fprintf(stderr, "start_pipeline failed\n"); return 1; }
    if (pipeline->start() != AppStatus::SUCCESS) { std::fprintf(stderr, "pipeline start failed\n"); return 1; }
    std::printf("garuda-perception running (feed %d, cmd %d)\n", cfg.value("feed_port", 8971), cfg.value("command_port", 8972));
    while (!g_stop) std::this_thread::sleep_for(std::chrono::milliseconds(200));
    pipeline->stop(); media->stop_pipeline(); cmds.stop(); feed.stop();
    return 0;
}
