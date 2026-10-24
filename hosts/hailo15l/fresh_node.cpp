// Native Hailo-15L adapter. Only this file knows the SDK; no borrowed buffers escape callbacks.
#include "garuda_tracking/json.hpp"
#include "garuda_tracking/vision.hpp"
#include "garuda_tracking/capture_stream.hpp"
#include "garuda_tracking/source_pairing.hpp"
#ifdef GARUDA_FRESH_HAVE_VISUAL_TARGET
#include "garuda_tracking/visual_target.hpp"
#endif
#ifdef GARUDA_FRESH_HAVE_OPENCV_MOTION
#include "garuda_tracking/camera_motion.hpp"
#endif
#include "diagnostic_budget.hpp"
#include "person_embedding.hpp"
#include "region_detector.hpp"
#include "garuda_tracking/tiling.hpp"
#include "garuda/yolo26_decode.hpp"
#include "garuda/feed_server.hpp"
#include "garuda/jpeg_encoder.hpp"
#include "hailo_analytics/pipeline/core/pipeline_builder.hpp"
#include "hailo_analytics/pipeline/core/pipeline.hpp"
#include "hailo_analytics/pipeline/sources/frontend_stage.hpp"
#include "hailo_analytics/pipeline/ai/ai_stage.hpp"
#include "hailo_analytics/pipeline/ai/postprocess_stage.hpp"
#include "hailo_analytics/pipeline/sinks/app_sink_stage.hpp"
#include "hailo_postprocess_tools/objects/hailo_common.hpp"
#include "media_library/media_library.hpp"
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <fstream>
#include <deque>
#include <mutex>
#include <sstream>
#include <thread>
#include <cstring>
#include <filesystem>

using namespace garuda::fresh;
using namespace hailo_analytics::pipeline;
namespace {
volatile std::sig_atomic_t stop_requested=0;
void signal_handler(int) {stop_requested=1;}
double now_ms() {return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();}
std::string read_file(const std::string& path) {std::ifstream f(path);if(!f)throw std::runtime_error("cannot read "+path);std::ostringstream s;s<<f.rdbuf();return s.str();}
bool diagnostic_space(const std::string& directory,uint64_t bytes) {
    std::ifstream memory("/proc/meminfo");std::error_code error;
    const auto disk=std::filesystem::space(directory.empty()?".":directory,error);
    return !error&&garuda::h15l::diagnostic_fits(garuda::h15l::diagnostic_headroom(memory),disk.available,bytes);
}
}

int main(int argc,char** argv) {
    if(argc==2&&std::string(argv[1])=="--capabilities") {std::puts("{\"target_roi_v1\":true}");return 0;}
    if(argc!=3||std::string(argv[1])!="--config") {std::fprintf(stderr,"usage: garuda-fresh-tracking --config PATH | --capabilities\n");return 2;}
    try {
        auto cfg=Json::parse(read_file(argv[2]));
        auto kernel_id=[](const char* path) {
            std::ifstream file(path);std::string id;file>>id;
            if(id.size()!=36)throw std::runtime_error("cannot identify producer clock/session");
            return id;
        };
        const std::string stream_id=kernel_id("/proc/sys/kernel/random/uuid");
        const std::string clock_domain="linux.monotonic:"+kernel_id("/proc/sys/kernel/random/boot_id");
        const int width=cfg.at("frame_w"),height=cfg.at("frame_h");
        const int input_w=cfg.at("input_w"),input_h=cfg.at("input_h");
        // Native-pixel crops: a third frontend stream at the sensor's own size feeds the target
        // ROI detector and the person descriptors, so a distant person is cropped from 3840x2160
        // instead of the 1280x720 copy. Search tiles, JPEG and capture stay on the paired copy.
        const std::string native_stream=cfg.value("native_stream",std::string());
        const bool native=!native_stream.empty();
        const int native_w=cfg.value("native_w",0),native_h=cfg.value("native_h",0);
        if(native&&(native_w<width||native_h<height||native_w>3840||native_h>2160||native_w%2||native_h%2||
                    native_stream==cfg.at("ai_stream")||native_stream==cfg.at("jpeg_stream")))
            throw std::invalid_argument("native source needs its own stream, even dimensions between the paired size and 3840x2160");
        // Native pixels only where they magnify: a native window wider than this is shrunk more than
        // 2x into the 640 input, i.e. the same scale as the paired copy through a cruder resampler
        // (desk A/B 2026-09-14: 0.43 vs 0.57 on a 1960 px window); such frames use the paired copy.
        const int native_max_window_px=cfg.value("native_max_window_px",1280);
        if(native&&(native_max_window_px<640||native_max_window_px>std::min(native_w,native_h)))
            throw std::invalid_argument("native_max_window_px must lie between 640 and the native height");
        // Bench A/B: with native on, also run the path that was NOT chosen on the same exposure and
        // report both target confidences; the other path's boxes are never merged into tracking.
        const bool roi_compare_paired=native&&cfg.value("target_roi_compare_paired",false);
        // Detector boxes and NV12 visual evidence use the same explicit inverse preprocessing map.
        // Stock YOLO postprocess reports input-normalized boxes; it does not undo letterboxing.
        if((cfg.at("input_geometry")!="stretch"&&cfg.at("input_geometry")!="letterbox")||width<=0||height<=0||width>8192||height>8192||
           input_w<2||input_h<2||input_w>8192||input_h>8192||input_w%2||input_h%2||width%2||height%2)
            throw std::invalid_argument("invalid NV12 frame geometry");
        const auto geometry=FrameGeometry::make(width,height,input_w,input_h,cfg.at("input_geometry")=="letterbox");
        Tracker tracker(config_from_json(cfg.value("tracking",Json::object())));
#ifdef GARUDA_FRESH_HAVE_VISUAL_TARGET
        std::unique_ptr<VisualTargetTracker> visual_target;
        if(tracker.config().visual_phone_tracking)visual_target=std::make_unique<VisualTargetTracker>();
#else
        if(tracker.config().visual_phone_tracking)throw std::invalid_argument("visual tracking requires GARUDA_TRACKING_VISUAL_TARGET build");
#endif
        const std::string roi_mode=cfg.value("target_roi",std::string("off"));
        if(roi_mode!="off"&&roi_mode!="assist"&&roi_mode!="shadow")throw std::invalid_argument("invalid target_roi mode");
        // roi_detector cuts today's paired 1280x720 copy; roi_detector_native (native profiles only)
        // cuts the sensor frame and is used only when its window magnifies (native_max_window_px).
        std::unique_ptr<garuda::h15l::RegionDetector> roi_detector,roi_detector_native;
        const std::vector<std::string> coco(garuda::yolo26::COCO,garuda::yolo26::COCO+80);
        if(roi_mode!="off") {
            if(width!=1280||height!=720||input_w!=640||input_h!=640||cfg.at("input_geometry")!="letterbox")
                throw std::invalid_argument("target ROI requires 1280x720 source and 640x640 letterbox");
            std::ifstream memory("/proc/meminfo");const auto headroom=garuda::h15l::diagnostic_headroom(memory);
            if(!headroom||*headroom<192*garuda::h15l::MiB)throw std::runtime_error("insufficient headroom for second detector");
            // All classes: the ROI follows whatever the owner locked; RoiAssist keeps only that label.
            roi_detector=std::make_unique<garuda::h15l::RegionDetector>(cfg.at("target_roi_hef").get<std::string>(),
                "garuda-fresh",coco,tracker.config().low_confidence,width,height,cfg.value("target_roi_cut_margin",0.015));
            if(native)roi_detector_native=std::make_unique<garuda::h15l::RegionDetector>(cfg.at("target_roi_hef").get<std::string>(),
                "garuda-fresh",coco,tracker.config().low_confidence,native_w,native_h,cfg.value("target_roi_cut_margin",0.015));
        }
        if(roi_compare_paired&&roi_mode!="assist")throw std::invalid_argument("ROI comparison needs target_roi assist");
        const double roi_max_age_ms=cfg.value("target_roi_max_age_ms",100.);
        RoiAssist roi_assist(roi_max_age_ms,cfg.value("target_roi_global_window_ms",400.),2.5,cfg.value("phone_predictive_roi",false));
        // Sensor-frame geometry; its context factor is the profile's (default the paired 2.5).
        RoiAssist roi_assist_native(roi_max_age_ms,cfg.value("target_roi_global_window_ms",400.),cfg.value("target_roi_native_context",2.5),cfg.value("phone_predictive_roi",false));
        FollowSchedule follow_schedule(cfg.value("follow_global_period_ms",800.),cfg.value("follow_local_gap_ms",500.),cfg.value("phone_short_miss_ms",0.));
        uint64_t roi_count=0,roi_failures=0,roi_source_misses=0,roi_added=0,roi_cut=0;
        bool roi_faulted=false;double last_shadow_ms=-1;
        Json roi_status={{"mode",roi_mode},{"inferences",0},{"faulted",false},{"reason","not_requested"}};
        // Five-tile detection: the AI stream provides the full view; a multi-class
        // RegionDetector adds the four 60% corner crops of the paired source for
        // small-object recall on the 4K camera. Aggregated before tracking.
        const bool detection_tiles=cfg.value("detection_tiles",false);
        // Acquisition mode: the four corner tiles run only while nothing is locked (or the lock
        // is lost and re-acquire is watching); once locked, the fast single tile + target ROI.
        const bool tiles_when_unlocked=cfg.value("tiles_when_unlocked",false);
        const bool managed_detection=cfg.value("managed_detection",false);
        if(managed_detection&&(!detection_tiles||roi_mode!="assist"||cfg.at("hef")!=cfg.at("target_roi_hef")))
            throw std::invalid_argument("managed detection requires tiled follow on one HEF");
        std::unique_ptr<garuda::h15l::RegionDetector> tile_detector;
        if(detection_tiles) {
            if(width!=1280||height!=720||input_w!=640||input_h!=640||cfg.at("input_geometry")!="letterbox")
                throw std::invalid_argument("tiled detection requires 1280x720 source and 640x640 letterbox");
            std::ifstream memory("/proc/meminfo");const auto headroom=garuda::h15l::diagnostic_headroom(memory);
            if(!headroom||*headroom<192*garuda::h15l::MiB)throw std::runtime_error("insufficient headroom for tiled detection");
            // Drop boxes within 8% of an interior tile border so an object in the
            // 20% tile overlap is kept only by the tile that contains it.
            tile_detector=std::make_unique<garuda::h15l::RegionDetector>(cfg.at("hef").get<std::string>(),
                "garuda-fresh",coco,tracker.config().low_confidence,width,height,cfg.value("tile_cut_margin",0.08));
        }
        uint64_t tile_count=0,tile_failures=0,tile_source_misses=0,tile_added=0;
        bool tile_faulted=false;
        Json tile_status={{"enabled",detection_tiles},{"reason","not_requested"}};
        std::unique_ptr<garuda::h15l::PersonEmbedding> person_embedding;
        const size_t embedding_budget=cfg.value("person_embedding_max_per_frame",size_t(4));
        const bool defer_car_embeddings=cfg.value("defer_person_embeddings_on_car",false);
        if(embedding_budget<1||embedding_budget>16)throw std::invalid_argument("person_embedding_max_per_frame must be 1..16");
        // Crops are skipped once the frame is older than this: a descriptor for a frame the
        // tracker will reject is wasted NPU time. Defaults to the tracker's freshness window so
        // every frame that can still be accepted also gets its descriptors (a fixed 150 ms guard
        // left every person undescribed in the tiled searching mode, ~300 ms frame age).
        const double embedding_max_age_ms=cfg.value("person_embedding_max_age_ms",tracker.config().freshness_ms);
        if(embedding_max_age_ms<50||embedding_max_age_ms>5000)throw std::invalid_argument("person_embedding_max_age_ms must be 50..5000");
        if(tracker.config().learned_person_identity) {
            person_embedding=std::make_unique<garuda::h15l::PersonEmbedding>(
                cfg.at("person_reid_hef").get<std::string>(),cfg.at("person_reid_model_id").get<std::string>(),"garuda-fresh");
        }
        std::atomic<uint64_t> embedding_count{0},embedding_failures{0},embedding_skipped{0},embedding_skipped_stale{0};
        std::atomic<uint64_t> embedding_deferred_car{0};
        std::atomic<double> embedding_inference_ms{0},embedding_crop_ms{0};
        std::atomic<bool> embedding_faulted{false};
        MotionEstimator motion;
        const std::string motion_mode=cfg.value("camera_motion",std::string("translation"));
        if(motion_mode!="translation"&&motion_mode!="similarity")throw std::invalid_argument("invalid camera_motion backend");
#ifdef GARUDA_FRESH_HAVE_OPENCV_MOTION
        std::unique_ptr<CameraMotionEstimator> similarity_motion;
        if(motion_mode=="similarity")similarity_motion=std::make_unique<CameraMotionEstimator>();
#else
        if(motion_mode=="similarity")throw std::invalid_argument("similarity motion requires GARUDA_TRACKING_OPENCV build");
#endif
        Json motion_status={{"backend",motion_mode},{"valid",false},{"reason","initial_frame"}};
        auto reset_motion=[&] {
            motion.reset();
#ifdef GARUDA_FRESH_HAVE_VISUAL_TARGET
            if(visual_target)visual_target->reset();
#endif
            roi_assist.reset();
#ifdef GARUDA_FRESH_HAVE_OPENCV_MOTION
            if(similarity_motion)similarity_motion->reset();
#endif
            motion_status={{"backend",motion_mode},{"valid",false},{"reason","reset_after_rejected_frame"}};
        };
        std::mutex tracking_mutex,jpeg_mutex,inference_mutex;
        uint64_t command_generation=0;
        std::string latest_jpeg;uint64_t jpeg_version=0;double jpeg_capture_ms=0;
        struct InputCapture {std::string stem,nv12,jpeg;Json metadata;};
        std::deque<InputCapture> capture_queue;
        size_t capture_remaining=0,capture_every=10,capture_tick=0,capture_written=0;
        uint64_t capture_bytes=0;
        std::string capture_dir,capture_error;bool capture_flushing=false;
        std::atomic<uint64_t> frame_count{0},reject_count{0};
        uint64_t sequence=0;
        const std::string record_path=cfg.value("record_path",std::string());
        const size_t record_limit=cfg.value("record_limit",size_t(3000));
        if(record_limit>100000)throw std::invalid_argument("record_limit exceeds bounded bench capture");
        std::ofstream recording;
        if(!record_path.empty()) {recording.open(record_path);if(!recording)throw std::runtime_error("cannot open record_path");}
        std::deque<std::string> record_queue;
        size_t recorded=0;uint64_t record_bytes=0;
        bool record_failed=false;
        // Called under tracking_mutex. Overflow stops recording at a valid prefix, never drops a
        // middle row (that would corrupt frame-to-frame camera-motion replay).
        auto record=[&](const Json& row) {
            if(record_path.empty()||record_failed||recorded>=record_limit)return;
            if(record_queue.size()>=16){record_failed=true;return;}
            auto serialized=row.dump();
            if(serialized.size()+1>garuda::h15l::record_byte_limit-record_bytes){record_failed=true;return;}
            record_bytes+=serialized.size()+1;record_queue.push_back(std::move(serialized));++recorded;
        };
        auto record_frame=[&](const Frame& frame) {
            if(!record_path.empty()&&!record_failed&&recorded<record_limit)record(frame_json(frame));
        };
        auto flush_recording=[&] {
            if(record_path.empty())return;
            std::deque<std::string> rows;
            {std::lock_guard<std::mutex> guard(tracking_mutex);rows.swap(record_queue);}
            uint64_t bytes=0;for(const auto& row:rows)bytes+=row.size()+1;
            if(bytes&&!diagnostic_space(std::filesystem::path(record_path).parent_path().string(),bytes)) {
                std::lock_guard<std::mutex> guard(tracking_mutex);record_failed=true;return;
            }
            for(const auto& row:rows)recording<<row<<'\n';
            if(!rows.empty()) {
                recording.flush();
                if(!recording){std::lock_guard<std::mutex> guard(tracking_mutex);record_failed=true;}
            }
        };
        // Bench-only capture: owned copies, bounded queue, file IO outside the inference mutex.
        auto flush_captures=[&] {
            std::deque<InputCapture> pending;
            {
                // Optional disk diagnostics must not delay the control publisher
                // just to discover an empty queue. A busy writer is retried next tick.
                std::unique_lock<std::mutex> guard(tracking_mutex,std::try_to_lock);
                if(!guard.owns_lock()||capture_queue.empty())return;
                pending.swap(capture_queue);capture_flushing=true;
            }
            for(const auto& item:pending) {
                const auto metadata=item.metadata.dump();
                const uint64_t bytes=item.nv12.size()+item.jpeg.size()+metadata.size()+1;
                if(bytes>garuda::h15l::capture_byte_limit-capture_bytes||!diagnostic_space(capture_dir,bytes)) {
                    std::lock_guard<std::mutex> guard(tracking_mutex);
                    capture_error="diagnostic storage or non-CMA memory budget exhausted";capture_remaining=0;break;
                }
                std::ofstream raw(item.stem+".nv12",std::ios::binary);
                raw.write(item.nv12.data(),item.nv12.size());raw.close();
                std::ofstream jpg(item.stem+".jpg",std::ios::binary);
                jpg.write(item.jpeg.data(),item.jpeg.size());jpg.close();
                std::ofstream meta(item.stem+".json");meta<<metadata<<'\n';meta.close();
                std::lock_guard<std::mutex> guard(tracking_mutex);
                if(!raw||!jpg||!meta){capture_error="capture write failed";capture_remaining=0;break;}
                ++capture_written;capture_bytes+=bytes;
            }
            {std::lock_guard<std::mutex> guard(tracking_mutex);capture_flushing=false;}
        };
        const int feed_port=cfg.value("feed_port",8981),command_port=cfg.value("command_port",8982);
        if(feed_port<1024||feed_port>65535||command_port<1024||command_port>65535||feed_port==command_port)
            throw std::invalid_argument("invalid transport ports");
        garuda::FeedServer feed(feed_port);
        std::unique_ptr<CaptureStream> capture_stream;
        const int capture_stream_port=cfg.value("capture_stream_port",0);
        const bool capture_source=cfg.value("capture_source",false);
        if(capture_source&&!capture_stream_port)throw std::invalid_argument("source capture requires capture stream port");
        if(roi_detector&&capture_stream_port&&!capture_source)throw std::invalid_argument("ROI capture requires paired source pixels");
        if(capture_source&&(width>1280||height>720||uint64_t(width*height+input_w*input_h)*3/2>2*1024*1024))
            throw std::invalid_argument("paired source capture exceeds bounded geometry");
        std::unique_ptr<SourceFrames> source_frames,native_frames;
        if(capture_source||roi_detector||detection_tiles||person_embedding||tracker.config().visual_phone_tracking)
            source_frames=std::make_unique<SourceFrames>();
        if(native&&(roi_detector||person_embedding)) {
            // Four owned 3840x2160 NV12 copies: 50 MB of ordinary memory beside the frontend's pool.
            // Headroom is non-CMA memory (MemAvailable minus CmaFree): about 300 MB on this 2 GB board
            // with its 1.28 GB CMA reserve, so the bar is the same 192 MiB the other consumers use.
            std::ifstream memory("/proc/meminfo");const auto headroom=garuda::h15l::diagnostic_headroom(memory);
            if(!headroom||*headroom<192*garuda::h15l::MiB)throw std::runtime_error("insufficient headroom for the native source");
            native_frames=std::make_unique<SourceFrames>(native_w,native_h);
        }
        if(capture_stream_port) {
            if(capture_stream_port<1024||capture_stream_port>65535||capture_stream_port==feed_port||capture_stream_port==command_port)
                throw std::invalid_argument("invalid capture stream port");
            capture_stream=std::make_unique<CaptureStream>(capture_stream_port,[capture_source] {
                std::ifstream memory("/proc/meminfo");
                const auto headroom=garuda::h15l::diagnostic_headroom(memory);
                return headroom&&*headroom>=(capture_source?144:136)*garuda::h15l::MiB;
            },capture_source);
        }
        garuda::CommandServer commands(command_port,[&](const std::string& line) {
            try {auto req=Json::parse(line);std::lock_guard<std::mutex> guard(tracking_mutex);
                if(req.value("cmd","")=="capture_input") {
                    const int count=req.value("frames",60),every=req.value("every",10);
                    if(count<1||count>120||every<1||every>40)return Json{{"ok",false},{"error","frames 1..120; every 1..40 required"}}.dump();
                    if(capture_remaining||!capture_queue.empty()||capture_flushing)return Json{{"ok",false},{"error","capture already active"}}.dump();
                    const uint64_t estimate=uint64_t(count)*(uint64_t(input_w)*input_h*3/2+garuda::h15l::MiB);
                    if(estimate>garuda::h15l::capture_byte_limit-capture_bytes||!diagnostic_space("/tmp",estimate))
                        return Json{{"ok",false},{"error","capture exceeds diagnostic storage or non-CMA memory budget; copy captures to PC first or request fewer frames"}}.dump();
                    capture_dir="/tmp/garuda-fresh-input-"+std::to_string(uint64_t(now_ms()*1000));
                    if(!std::filesystem::create_directory(capture_dir))throw std::runtime_error("capture directory exists");
                    capture_remaining=count;capture_every=every;capture_tick=0;capture_written=0;capture_error.clear();
                    return Json{{"ok",true},{"directory",capture_dir},{"frames",count},{"every",every}}.dump();
                }
                double now=now_ms();auto result=command(tracker,req,now,width,height);
                if(result.value("ok",false)){++command_generation;req["now_ms"]=now;record(req);}
                return result.dump();
            }catch(const std::exception& e){return Json{{"ok",false},{"error",e.what()}}.dump();}
        });
        auto created=MediaLibrary::create();if(!created)throw std::runtime_error("MediaLibrary::create failed");
        auto media=created.value();
        // VPSP1.12 preserves resize dimensions/mode when switching profiles. Initialize
        // directly with the requested profile; loading stretch first keeps stretch active.
        auto media_config=Json::parse(read_file(cfg.at("medialib_config").get<std::string>()));
        media_config["default_profile"]=cfg.at("profile");
        if(media->initialize(media_config.dump())!=MEDIA_LIBRARY_SUCCESS)
            throw std::runtime_error("media configuration failed");
        const auto effective=media->get_current_profile();
        if(!effective)throw std::runtime_error("cannot read effective camera profile");
        const auto& streams=effective.value().application_settings.application_input_streams;
        bool found_ai=false,found_preview=false,found_native=!native;
        for(const auto& stream:streams.resolutions) {
            if(stream.stream_id==cfg.at("ai_stream").get<std::string>()) {
                const auto wanted=cfg.at("input_geometry")=="letterbox"?DSP_SCALING_MODE_LETTERBOX_MIDDLE:DSP_SCALING_MODE_STRETCH;
                found_ai=stream.dimensions.destination_width==uint32_t(input_w)&&stream.dimensions.destination_height==uint32_t(input_h)&&
                    stream.scaling_mode==wanted&&streams.format==HAILO_FORMAT_NV12;
            }
            if(stream.stream_id==cfg.at("jpeg_stream").get<std::string>())
                found_preview=stream.dimensions.destination_width==uint32_t(width)&&stream.dimensions.destination_height==uint32_t(height)&&
                    stream.scaling_mode==DSP_SCALING_MODE_STRETCH;
            if(native&&stream.stream_id==native_stream)
                found_native=stream.dimensions.destination_width==uint32_t(native_w)&&stream.dimensions.destination_height==uint32_t(native_h)&&
                    stream.scaling_mode==DSP_SCALING_MODE_STRETCH;
        }
        if(!found_ai||!found_preview||!found_native)throw std::runtime_error("effective media geometry disagrees with tracking config");
        std::printf("effective input=%dx%d geometry=%s preview=%dx%d native=%dx%d\n",input_w,input_h,
                    cfg.at("input_geometry").get<std::string>().c_str(),width,height,native?native_w:0,native?native_h:0);
        auto frontend=sources::FrontendStageBuild::create().set_stage_name("frontend").set_leaky_opt(true).buildptr();
        if(frontend->configure(media)!=AppStatus::SUCCESS)throw std::runtime_error("frontend configuration failed");
        auto sink=sinks::AppSinkStageBuild::create().set_stage_name("tracks").set_queue_size_opt(1).set_leaky_opt(true)
            .set_process_func([&](BufferPtr buffer) {
                try {
                    std::lock_guard<std::mutex> inference_guard(inference_mutex);
                    Frame f;f.sequence=++sequence;f.now_ms=now_ms();
                    const double processing_started_ms=f.now_ms;
                    auto mlb=buffer->get_buffer();
                    f.timestamp_valid=mlb&&mlb->isp_timestamp_ns!=0;
                    f.capture_ms=f.timestamp_valid?double(mlb->isp_timestamp_ns)/1e6:0;
                    std::unique_lock<std::mutex> guard(tracking_mutex);
                    auto previous=tracker.snapshot(f.now_ms);
                    const auto generation=command_generation;
                    auto next_roi_status=roi_status,next_tile_status=tile_status,next_motion_status=motion_status;
                    if(!f.timestamp_valid||f.capture_ms<=previous.capture_ms||f.capture_ms>f.now_ms||
                       f.now_ms-f.capture_ms>tracker.config().freshness_ms) {
                        record_frame(f);tracker.update(f);reset_motion();++reject_count;return;
                    }
                    guard.unlock();
                    auto roi=buffer->get_roi();
                    if(roi) for(const auto& d:hailo_common::get_hailo_detections(roi)) {
                        if(f.detections.size()>=tracker.config().max_detections)break;
                        auto b=d->get_bbox();
                        f.detections.push_back({geometry.to_frame({b.xmin(),b.ymin(),b.width(),b.height()}),d->get_label(),d->get_confidence(),{}, {}});
                    }
                    Image image;
                    if(mlb&&mlb->buffer_data&&mlb->get_num_of_planes()>=2) {
                        if(mlb->buffer_data->width!=size_t(input_w)||mlb->buffer_data->height!=size_t(input_h)||
                           mlb->buffer_data->format!=HAILO_FORMAT_NV12)
                            throw std::runtime_error("detector buffer geometry/format does not match config");
                        image={static_cast<const uint8_t*>(mlb->get_plane_ptr(0)),static_cast<const uint8_t*>(mlb->get_plane_ptr(1)),
                               input_w,input_h,int(mlb->get_plane_stride(0)),int(mlb->get_plane_stride(1)),
                               mlb->get_plane_size(0),mlb->get_plane_size(1)};
                    }
                    const Image network_image=image;
                    if(!geometry.matches_layout(network_image)) {
                        f.timestamp_valid=false;
                        throw std::runtime_error("actual inference pixels disagree with configured geometry");
                    }
                    image=geometry.content(image);
                    auto paired=source_frames?source_frames->take(mlb->isp_timestamp_ns,managed_detection?40:0):std::optional<SourceFrame>{};
                    // Same exposure at native size; the wait only starts once the paired copy has arrived.
                    auto native_paired=native_frames?native_frames->take(mlb->isp_timestamp_ns,managed_detection?40:0):std::optional<SourceFrame>{};
                    double primary_inference_ms=0;unsigned detector_passes=1;
                    if(managed_detection) {
                        if(!paired)throw std::runtime_error("managed detector requires exact paired source");
                        auto full=five_tile_layout(f.sequence,f.capture_ms,width,height).back();
                        auto detected=tile_detector->infer(paired->image(),full);
                        f.detections=std::move(detected.detections);primary_inference_ms=detected.inference_ms;
                        for(auto& d:f.detections){d.region_id=4;d.region_full_frame=true;}
                    }
                    const auto primary_detections=(roi_detector||tile_detector)?frame_json(f).at("detections"):Json::array();
                    const bool searching=managed_detection?follow_schedule.global_required(previous.target,f.capture_ms):
                        (!previous.target.id||previous.target.state=="none"||previous.target.state=="lost");
                    bool ran_global=false,verified_local=false;
                    const double corners_started_ms=now_ms();
                    if(tile_detector&&tiles_when_unlocked&&!searching) {
                        next_tile_status={{"enabled",true},{"sequence",f.sequence},{"reason","locked_single_tile"}};
                    } else if(tile_detector) {
                        next_tile_status={{"enabled",true},{"sequence",f.sequence},{"reason","not_eligible"}};
                        if(tile_faulted) next_tile_status["reason"]="faulted";
                        else if(!paired) {++tile_source_misses;next_tile_status["reason"]="exact_source_missing";}
                        else {
                            // All five tiles come from the SAME paired source at one scale
                            // (full view + four corners); the coarse AI-stream detection is
                            // discarded to avoid cross-scale duplicates. Raw per-tile boxes
                            // are recorded before aggregation for offline validation.
                            std::vector<Detection> raw=managed_detection?f.detections:std::vector<Detection>{};
                            size_t raw_dets=raw.size(),corner_dropped=0;double dsp_ms=0,infer_ms=primary_inference_ms;
                            Json raw_json=Json::array(),pre_filter_json=Json::array();
                            size_t boundary_cut=0,pre_filter_count=0;
                            // Corner tiles exist to recover SMALL objects; a large object
                            // spanning tiles is already seen whole by the full view, so a
                            // large corner detection is a duplicate that splits the object.
                            const double corner_max_area=cfg.value("tile_corner_max_area",0.05);
                            try {
                                int tile_index=0;
                                auto regions=five_tile_layout(f.sequence,f.capture_ms,width,height);
                                if(managed_detection)regions.pop_back();
                                detector_passes+=regions.size();
                                for(const auto& local:tile_detector->infer_many(paired->image(),regions,cfg.value("tile_raw_dump",false))) {
                                    const auto& tile=local.region;
                                    boundary_cut+=local.cut_boxes;pre_filter_count+=local.audit.size();
                                    for(const auto& a:local.audit)if(pre_filter_json.size()<120)
                                        pre_filter_json.push_back({{"tile",tile_index},{"label",a.detection.label},
                                            {"conf",a.detection.confidence},{"box",box_json(a.detection.box)},
                                            {"rejection",a.fixed_cut?"interior_tile_boundary":
                                                (!tile.full_frame&&a.detection.box.w*a.detection.box.h>corner_max_area?"corner_area":"none")},
                                            {"relative_candidate_cut",a.relative_cut}});
                                    dsp_ms+=local.dsp_ms;infer_ms+=local.inference_ms;
                                    for(auto d:local.detections) {
                                        d.region_id=tile_index;d.region_full_frame=tile.full_frame;
                                        if(!tile.full_frame&&d.box.w*d.box.h>corner_max_area){++corner_dropped;continue;}
                                        raw.push_back(d);++raw_dets;
                                        if(raw_json.size()<120)raw_json.push_back({{"tile",tile_index},{"label",d.label},
                                            {"conf",d.confidence},{"box",box_json(d.box)}});
                                    }
                                    ++tile_index;
                                }
                                ++tile_count;
                                auto merged=aggregate_tile_detections(std::move(raw));
                                if(merged.size()>tracker.config().max_detections)merged.resize(tracker.config().max_detections);
                                tile_added+=merged.size();
                                f.detections=std::move(merged);   // replace the AI-stream detections
                                ran_global=true;
                                next_tile_status.update({{"reason","tiled"},{"raw_detections",raw_dets},
                                    {"corner_dropped_large",corner_dropped},{"boundary_cut_boxes",boundary_cut},
                                    {"aggregated",f.detections.size()},{"dsp_ms",dsp_ms},{"inference_ms",infer_ms}});
                                if(cfg.value("tile_raw_dump",false)) {
                                    next_tile_status["raw"]=raw_json; // historical post-filter field
                                    next_tile_status["pre_region_filter"]=pre_filter_json;
                                    next_tile_status["pre_region_filter_count"]=pre_filter_count;
                                    next_tile_status["pre_region_filter_truncated"]=pre_filter_count>pre_filter_json.size();
                                }
                            }catch(const std::exception& e) {
                                tile_faulted=true;++tile_failures;next_tile_status["reason"]="runtime_fault";
                                std::fprintf(stderr,"tiled detection faulted, restart required: %s\n",e.what());
                            }
                        }
                        next_tile_status.update({{"inferences",tile_count},{"failures",tile_failures},
                            {"faulted",tile_faulted},{"source_misses",tile_source_misses},{"added",tile_added}});
                    }
                    const double corners_elapsed_ms=now_ms()-corners_started_ms;
                    const double roi_started_ms=now_ms();
                    if(roi_detector) {
                        std::optional<SearchRegion> request;
                        next_roi_status={{"mode",roi_mode},{"sequence",f.sequence},{"reason","not_eligible"},
                            {"secondary_hef",cfg.at("target_roi_hef")},{"full_frame_inference",true}};
                        f.now_ms=now_ms();
                        if(ran_global&&previous.target.control_valid) {
                            for(const auto& d:f.detections)if(d.label==previous.target.label&&d.confidence>=.4&&
                                previous.target.box&&iou(d.box,*previous.target.box)>=.3) {
                                roi_assist.observe_global(previous.target,f.capture_ms);
                                if(roi_detector_native)roi_assist_native.observe_global(previous.target,f.capture_ms);
                            }
                        }
                        std::optional<SearchRegion> native_request;bool use_native=false;
                        if(!roi_faulted&&f.now_ms-f.capture_ms<=roi_max_age_ms) {
                            if(roi_mode=="assist") {
                                // Both planners see the same full-view evidence, before any ROI box is merged.
                                request=roi_assist.plan(f,previous.target,width,height);
                                if(roi_detector_native) {
                                    native_request=roi_assist_native.plan(f,previous.target,native_w,native_h);
                                    use_native=native_request&&native_request->w<=native_max_window_px&&native_paired.has_value();
                                }
                                next_roi_status["reason"]=use_native?roi_assist_native.reason():roi_assist.reason();
                            }
                            else if(last_shadow_ms<0||f.capture_ms-last_shadow_ms>=100) {
                                // Fixed diagnostic crop measures concurrent load even in an empty scene.
                                // Its detections are never merged into tracking or target control.
                                request=SearchRegion{f.sequence,f.capture_ms,width,height,320,40,640,640,640,640,false};
                                last_shadow_ms=f.capture_ms;
                            }
                        }
                        else next_roi_status["reason"]=roi_faulted?"faulted":"age_budget";
                        const std::string native_name="native_"+std::to_string(native_w)+"x"+std::to_string(native_h);
                        next_roi_status["source"]=use_native?native_name:"paired_1280x720";
                        next_roi_status["native_window_px"]=native_request?native_request->w:0;
                        next_roi_status["native_max_window_px"]=native?native_max_window_px:0;
                        // Best confidence the crop gave the locked target's own box (label-bound, IoU >= 0.4).
                        const auto best_on_target=[&](const std::vector<Detection>& ds) {
                            double best=0;
                            for(const auto& d:ds)if(previous.target.box&&d.label==previous.target.label&&iou(d.box,*previous.target.box)>=.4)
                                best=std::max(best,d.confidence);
                            return best;
                        };
                        const auto& active=use_native?native_request:request;
                        if(active) {
                            const int active_w=use_native?native_w:width,active_h=use_native?native_h:height;
                            next_roi_status["region"]={{"x",active->x},{"y",active->y},{"w",active->w},{"h",active->h},
                                {"source_w",active_w},{"source_h",active_h},{"capture_ms",active->capture_ms}};
                            const auto& roi_source=use_native?native_paired:paired;
                            auto& detector=use_native?*roi_detector_native:*roi_detector;
                            if(!roi_source) {++roi_source_misses;next_roi_status["reason"]="exact_source_missing";}
                            else try {
                                const auto local=detector.infer(roi_source->image(),*active);++detector_passes;++roi_count;roi_cut+=local.cut_boxes;
                                const auto added=roi_mode=="assist"?(use_native?roi_assist_native:roi_assist).merge(f,local.region,local.detections,tracker.config().max_detections):0;
                                roi_added+=added;
                                for(const auto& d:local.detections)if(previous.target.box&&d.label==previous.target.label&&
                                    d.confidence>=.4&&iou(d.box,*previous.target.box)>=.4)verified_local=true;
                                next_roi_status["reason"]=roi_mode=="shadow"?"diagnostic_only":"inferred";
                                next_roi_status["added_this_frame"]=added;next_roi_status["local_detections"]=local.detections.size();
                                next_roi_status["best_target_confidence"]=best_on_target(local.detections);
                                next_roi_status["source_copy_ms"]=local.source_copy_ms;next_roi_status["dsp_ms"]=local.dsp_ms;
                                next_roi_status["input_copy_ms"]=local.input_copy_ms;next_roi_status["inference_ms"]=local.inference_ms;
                                next_roi_status["isp_timestamp_ns"]=roi_source->timestamp_ns;
                                if(roi_compare_paired&&roi_detector_native) {
                                    // The path NOT chosen, on the same exposure: measured, never merged.
                                    const auto& other_request=use_native?request:native_request;
                                    const auto& other_source=use_native?paired:native_paired;
                                    Json compare={{"path",use_native?"paired_1280x720":native_name},{"planned",bool(other_request)}};
                                    if(other_request&&other_source) {
                                        auto& other_detector=use_native?*roi_detector:*roi_detector_native;
                                        const auto other=other_detector.infer(other_source->image(),*other_request);++detector_passes;
                                        compare["region"]={{"x",other_request->x},{"y",other_request->y},{"w",other_request->w},{"h",other_request->h},
                                            {"source_w",use_native?width:native_w},{"source_h",use_native?height:native_h}};
                                        compare["local_detections"]=other.detections.size();
                                        compare["best_target_confidence"]=best_on_target(other.detections);
                                        compare["inference_ms"]=other.inference_ms;compare["source_copy_ms"]=other.source_copy_ms;compare["dsp_ms"]=other.dsp_ms;
                                    }
                                    next_roi_status["compare_other_path"]=std::move(compare);
                                }
                            }catch(const std::exception& e) {
                                roi_faulted=true;++roi_failures;next_roi_status["reason"]="runtime_fault";
                                std::fprintf(stderr,"target ROI faulted, restart required: %s\n",e.what());
                            }
                        }
                        next_roi_status["inferences"]=roi_count;next_roi_status["failures"]=roi_failures;next_roi_status["faulted"]=roi_faulted;
                        next_roi_status["source_misses"]=roi_source_misses;next_roi_status["added"]=roi_added;next_roi_status["cut_boxes"]=roi_cut;
                    }
                    // Descriptors and histograms from the native exposure when it paired, else the copy.
                    const Image identity_image=native_paired?native_paired->image():paired?paired->image():image;
                    for(auto& d:f.detections)d.appearance=describe(identity_image,d.box);
                    if(person_embedding&&!embedding_faulted) {
                        size_t crops=0;
                        const bool deferred=defer_person_embeddings_for_car(previous.target,tracker.config(),defer_car_embeddings);
                        // Bounded per-frame work. Missing descriptors explicitly prevent identity
                        // verification of a NEW id, so spend the budget where identity is decided:
                        // the locked target's own box first, then its neighbours, then by confidence.
                        std::vector<size_t> order;
                        for(size_t k=0;k<f.detections.size();++k)if(f.detections[k].label=="person")order.push_back(k);
                        // With no target, a click refused for lack of a descriptor names the person to
                        // describe first (aerial crowds: 100 persons per frame, six crops per frame).
                        // After a release the identity is still remembered: keep the budget where it
                        // was last verified, so the re-bind evidence there is complete.
                        const auto& focus=defer_car_embeddings&&previous.target.pending_box?previous.target.pending_box:
                            previous.target.box?previous.target.box:
                            previous.target.pending_box?previous.target.pending_box:previous.target.last_verified_box;
                        // Boxes overlapping the focus come first, most overlap first; then the rest by
                        // centre distance. In a dense crowd the six nearest centres can all belong to
                        // small neighbours while the clicked person's own box, a frame later, overlaps
                        // the pending box and still went undescribed (VisDrone-SOT 054, 2026-09-17).
                        const auto priority=[&](size_t k) {
                            const auto& b=f.detections[k].box;
                            if(!focus)return -f.detections[k].confidence;
                            const auto& t=*focus;
                            const double overlap=iou(b,t);
                            if(overlap>0)return -overlap-f.detections[k].confidence*1e-3;
                            const double dx=(b.x+b.w/2)-(t.x+t.w/2),dy=(b.y+b.h/2)-(t.y+t.h/2);
                            return std::sqrt(dx*dx+dy*dy)-f.detections[k].confidence*1e-3;
                        };
                        std::stable_sort(order.begin(),order.end(),[&](size_t a,size_t b){return priority(a)<priority(b);});
                        for(size_t k:order) {
                            auto& d=f.detections[k];
                            if(deferred) {++embedding_skipped;++embedding_deferred_car;continue;}
                            if(crops>=embedding_budget) {++embedding_skipped;continue;}
                            if(!paired||!identity_image.valid()){++embedding_skipped;continue;}
                            if(now_ms()-f.capture_ms>embedding_max_age_ms) {++embedding_skipped;++embedding_skipped_stale;continue;}
                            ++crops;
                            try {
                                auto result=person_embedding->infer(identity_image,d.box);d.embedding=std::move(result.embedding);
                                embedding_inference_ms=result.inference_ms;embedding_crop_ms=result.crop_ms;++embedding_count;
                            } catch(const std::exception& e) {
                                ++embedding_failures;embedding_faulted=true;
                                std::fprintf(stderr,"person embedding faulted, restart required: %s\n",e.what());break;
                            }
                        }
                    }
#ifdef GARUDA_FRESH_HAVE_OPENCV_MOTION
                    if(similarity_motion) {
                        auto fit=similarity_motion->update(image,f.detections);f.motion=fit.motion;
                        next_motion_status={{"backend",motion_mode},{"sequence",f.sequence},{"valid",fit.motion.valid},
                            {"reason",fit.reason},{"elapsed_ms",fit.elapsed_ms},{"features",fit.features},{"matches",fit.matches},
                            {"inliers",fit.inliers},{"support_cells",fit.support_cells},{"residual_px",fit.residual_px}};
                    } else
#endif
                    {
                        f.motion=motion.update(image,f.detections);
                        next_motion_status={{"backend",motion_mode},{"sequence",f.sequence},{"valid",f.motion.valid}};
                    }
                    // Same-exposure, full-FOV pixels only. Never fall back between
                    // source/network geometries while retaining an image template.
#ifdef GARUDA_FRESH_HAVE_VISUAL_TARGET
                    VisualTargetResult visual_result;
                    const Image visual_image=paired?paired->image():Image{};
                    if(visual_target) {
                        if(visual_image.valid()&&previous.target.label=="cell phone") {
                            visual_result=visual_target->locate(visual_image,f.sequence,f.capture_ms,
                                previous.target.lock_id,previous.target.epoch);
                            f.visual_target=visual_result.measurement;
                        } else visual_target->reset();
                    }
#endif
                    f.now_ms=now_ms();
                    guard.lock();
                    if(command_generation!=generation){reset_motion();roi_assist.reset();follow_schedule.reset();++reject_count;return;}
                    next_tile_status["detector_passes_this_frame"]=detector_passes;
                    next_tile_status["schedule_reason"]=follow_schedule.reason();
                    next_tile_status["corner_wall_ms"]=corners_elapsed_ms;
                    next_tile_status["entry_age_ms"]=processing_started_ms-f.capture_ms;
                    next_tile_status["processing_wall_ms"]=f.now_ms-processing_started_ms;
                    next_tile_status["capture_to_update_ms"]=f.now_ms-f.capture_ms;
                    next_tile_status["roi_and_evidence_wall_ms"]=f.now_ms-roi_started_ms;
                    next_tile_status["primary_inference_ms"]=primary_inference_ms;
                    next_tile_status["managed_detection"]=managed_detection;
                    roi_status=std::move(next_roi_status);tile_status=std::move(next_tile_status);motion_status=std::move(next_motion_status);
                    record_frame(f);auto result=tracker.update(f);
#ifdef GARUDA_FRESH_HAVE_VISUAL_TARGET
                    if(visual_target) {
                        const auto& target=result.target;
                        const double seed_started=now_ms();
                        if(result.accepted&&paired&&target.label=="cell phone"&&target.control_valid&&
                           !target.visual_observation&&target.box)
                            visual_target->seed(visual_image,*target.box,f.sequence,f.capture_ms,target.lock_id,target.epoch);
                        motion_status["visual_target"]={{"reason",visual_result.reason},{"score",visual_result.score},
                            {"margin",visual_result.margin},{"elapsed_ms",visual_result.elapsed_ms},
                            {"seed_ms",now_ms()-seed_started},
                            {"proposed",visual_result.measurement.has_value()},{"used",target.visual_observation}};
                    }
#endif
                    if(ran_global&&result.target.control_valid) {
                        roi_assist.observe_global(result.target,f.capture_ms);
                        if(roi_detector_native)roi_assist_native.observe_global(result.target,f.capture_ms);
                    }
                    if(managed_detection)follow_schedule.observe(ran_global,verified_local,result.target,f.capture_ms);
                    if(capture_stream&&capture_stream->active()) {
                        const auto source_image=paired?paired->image():Image{};
                        capture_stream->enqueue(network_image,{{"source_id","hailo15l.imx678"},{"stream_id",stream_id},
                            {"clock_domain",clock_domain},{"frame",frame_json(f)},{"output",output_json(result,width,height)},
                            {"camera_motion",motion_status},
                            {"managed_detection",managed_detection},{"network_image_role",managed_detection?"isp_preview_not_exact_npu_input":"exact_npu_input"},
                            {"target_roi",roi_status},{"detection_tiles",tile_status},{"primary_detections",primary_detections},
                            {"geometry",cfg.at("input_geometry")},{"hef",cfg.at("hef")},
                            {"isp_timestamp_ns",mlb->isp_timestamp_ns},
                            {"isp_ae_integration_time",mlb->isp_ae_integration_time},
                            {"isp_ae_converged",mlb->isp_ae_converged},{"isp_ae_average_luma",mlb->isp_ae_average_luma}},
                            paired?&source_image:nullptr,paired?paired->timestamp_ns:0);
                    }
                    if(capture_remaining&&++capture_tick%capture_every==0) {
                        if(!network_image.valid()||capture_queue.size()>=4) {
                            capture_error="invalid image or capture queue full";capture_remaining=0;
                        } else {
                            InputCapture item;item.stem=capture_dir+"/"+std::to_string(f.sequence);
                            item.nv12.resize(size_t(input_w)*input_h*3/2);
                            char* dst=item.nv12.data();
                            for(int row=0;row<input_h;++row){std::memcpy(dst,network_image.y+size_t(row)*network_image.y_stride,input_w);dst+=input_w;}
                            for(int row=0;row<input_h/2;++row){std::memcpy(dst,network_image.uv+size_t(row)*network_image.uv_stride,input_w);dst+=input_w;}
                            item.metadata={{"frame",frame_json(f)},{"output",output_json(result,width,height)},
                                {"managed_detection",managed_detection},{"network_image_role",managed_detection?"isp_preview_not_exact_npu_input":"exact_npu_input"},
                                {"input_w",input_w},{"input_h",input_h},{"y_stride",network_image.y_stride},{"uv_stride",network_image.uv_stride},
                                {"geometry",cfg.at("input_geometry")},{"hef",cfg.at("hef")},{"preview_synchronized",false},
                                {"isp_ae_integration_time",mlb->isp_ae_integration_time},{"isp_ae_converged",mlb->isp_ae_converged},
                                {"isp_ae_average_luma",mlb->isp_ae_average_luma},{"isp_ae_fps",mlb->isp_ae_fps}};
                            {std::lock_guard<std::mutex> jpg_guard(jpeg_mutex);item.jpeg=latest_jpeg;item.metadata["preview_capture_ms"]=jpeg_capture_ms;}
                            capture_queue.push_back(std::move(item));--capture_remaining;
                        }
                    }
                    if(!result.accepted){reset_motion();++reject_count;}
                    ++frame_count;
                }catch(const std::exception& e){++reject_count;std::fprintf(stderr,"tracking frame rejected: %s\n",e.what());}
            }).buildptr();
        garuda::JpegEncoder encoder(cfg.value("jpeg_quality",75));
        const int jpeg_fps=cfg.value("jpeg_fps",10);
        if(jpeg_fps<1||jpeg_fps>30)throw std::invalid_argument("jpeg_fps must be 1..30");
        double last_jpeg_ms=0;
        auto jpeg=sinks::AppSinkStageBuild::create().set_stage_name("jpeg").set_queue_size_opt(1).set_leaky_opt(true)
            .set_process_func([&](BufferPtr buffer) {
                try {
                    double now=now_ms();if(!source_frames&&now-last_jpeg_ms<1000./jpeg_fps)return;
                    auto b=buffer->get_buffer();if(!b||!b->buffer_data||b->get_num_of_planes()<2)return;
                    if(b->buffer_data->width!=size_t(width)||b->buffer_data->height!=size_t(height)||
                       b->buffer_data->format!=HAILO_FORMAT_NV12)throw std::runtime_error("source geometry/format mismatch");
                    Image image{static_cast<const uint8_t*>(b->get_plane_ptr(0)),static_cast<const uint8_t*>(b->get_plane_ptr(1)),
                        width,height,int(b->get_plane_stride(0)),int(b->get_plane_stride(1)),b->get_plane_size(0),b->get_plane_size(1)};
                    if(!image.valid())return;
                    // Same exposure key as the inference stream. Copy before JPEG rate limiting;
                    // bounded history also warms before a recording request, avoiding a first-frame race.
                    if(source_frames)source_frames->push(b->isp_timestamp_ns,image);
                    if(now-last_jpeg_ms<1000./jpeg_fps)return;
                    last_jpeg_ms=now;
                    auto bytes=encoder.encode_nv12(image.y,image.y_stride,image.uv,image.uv_stride,width,height);
                    std::lock_guard<std::mutex> guard(jpeg_mutex);
                    latest_jpeg.assign(reinterpret_cast<const char*>(bytes.data()),bytes.size());++jpeg_version;
                    jpeg_capture_ms=double(b->isp_timestamp_ns)/1e6;
                }catch(const std::exception& e){std::fprintf(stderr,"jpeg failed: %s\n",e.what());}
            }).buildptr();
        // Native stream: copied into the bounded native cache under the same exposure key; nothing else.
        auto native_sink=sinks::AppSinkStageBuild::create().set_stage_name("native").set_queue_size_opt(1).set_leaky_opt(true)
            .set_process_func([&](BufferPtr buffer) {
                try {
                    if(!native_frames)return;
                    auto b=buffer->get_buffer();if(!b||!b->buffer_data||b->get_num_of_planes()<2)return;
                    if(b->buffer_data->width!=size_t(native_w)||b->buffer_data->height!=size_t(native_h)||
                       b->buffer_data->format!=HAILO_FORMAT_NV12)throw std::runtime_error("native geometry/format mismatch");
                    Image image{static_cast<const uint8_t*>(b->get_plane_ptr(0)),static_cast<const uint8_t*>(b->get_plane_ptr(1)),
                        native_w,native_h,int(b->get_plane_stride(0)),int(b->get_plane_stride(1)),b->get_plane_size(0),b->get_plane_size(1)};
                    if(image.valid())native_frames->push(b->isp_timestamp_ns,image);
                }catch(const std::exception& e){std::fprintf(stderr,"native source failed: %s\n",e.what());}
            }).buildptr();
        PipelineBuilder builder;
        builder.add_stage("frontend",frontend,StageType::SOURCE).add_stage("tracks",sink,StageType::SINK)
            .add_stage("jpeg",jpeg,StageType::SINK).connect_frontend("frontend",cfg.at("jpeg_stream").get<std::string>(),"jpeg");
        if(native_frames)builder.add_stage("native",native_sink,StageType::SINK).connect_frontend("frontend",native_stream,"native");
        if(managed_detection)builder.connect_frontend("frontend",cfg.at("ai_stream").get<std::string>(),"tracks");
        else {
            // Only the legacy path owns an asynchronous primary detector. The
            // managed path uses the paired-source full view exactly once.
            // Deployed 1.12 lacks ThreadedStage::set_leaky: configure at build.
            auto detect=ai::HailortAsyncStageBuild::create().set_stage_name("detect").set_hef_path(cfg.at("hef").get<std::string>())
                .set_queue_size(1).set_output_pool_size(4).set_group_id("garuda-fresh").set_batch_size(1).set_job_limit(1)
                .set_scheduler_threshold_opt(1).set_scheduler_timeout_opt(std::chrono::milliseconds(10))
                .set_nms_score_threshold(float(tracker.config().low_confidence)).buildptr();
            auto post=ai::PostprocessStageBuild::create().set_stage_name("post").set_so_path(cfg.at("postprocess_so").get<std::string>())
                .set_config_path_opt(cfg.at("postprocess_config").get<std::string>()).set_queue_size_opt(1).set_leaky_opt(true).buildptr();
            builder.add_stage("detect",detect).add_stage("post",post)
                .connect_frontend("frontend",cfg.at("ai_stream").get<std::string>(),"detect").connect("detect","post").connect("post","tracks");
        }
        auto pipeline=builder.build("garuda-fresh-tracking");
        std::signal(SIGINT,signal_handler);std::signal(SIGTERM,signal_handler);
        feed.start();commands.start();
        if(media->start_pipeline()!=MEDIA_LIBRARY_SUCCESS)throw std::runtime_error("camera start failed");
        if(pipeline->start()!=AppStatus::SUCCESS){media->stop_pipeline();throw std::runtime_error("analytics start failed");}
        std::printf("garuda-fresh-tracking: feed=%d commands=%d; target initially unselected\n",feed_port,command_port);
        uint64_t sent_jpeg=0;double last_report=now_ms(),last_send_start=0,last_send_ms=0;
        auto publish_deadline=std::chrono::steady_clock::now();
        while(!stop_requested) {
            // Diagnostic flushes may wait for tracking_mutex or storage. Finish
            // them before selecting the state that will be sent to the controller.
            flush_recording();flush_captures();
            Output output;Json message;
            {
                // Copy state and its diagnostics atomically. Taking this lock a
                // second time after snapshotting can wait through another NPU
                // call, then publish the older state with newer diagnostics.
                std::lock_guard<std::mutex> guard(tracking_mutex);
                output=tracker.snapshot(now_ms());message=output_json(output,width,height);
                message["diag"]["record_failed"]=record_failed;message["diag"]["recorded_rows"]=recorded;
                message["diag"]["record_limit_reached"]=!record_path.empty()&&recorded>=record_limit;
                message["diag"]["input_capture"]={{"remaining",capture_remaining},{"written",capture_written},
                    {"directory",capture_dir},{"error",capture_error}};
                message["diag"]["camera_motion"]=motion_status;
                if(roi_detector)message["diag"]["target_roi"]=roi_status;
                if(tile_detector)message["diag"]["detection_tiles"]=tile_status;
            }
            // Network writes never hold tracking_mutex or block inference callbacks.
            message["source_id"]="hailo15l.imx678";
            message["stream_id"]=stream_id;message["clock_domain"]=clock_domain;
            message["sample_monotonic_ms"]=output.publish_ms;
            message["diag"]["frames"]=frame_count.load();message["diag"]["rejected_frames"]=reject_count.load();
            if(capture_stream)message["diag"]["capture_stream"]=capture_stream->status();
            if(source_frames) {
                auto s=source_frames->stats();
                message["diag"]["source_pairing"]={{"buffered",s.buffered},{"pushed",s.pushed},{"matched",s.matched},
                    {"missing",s.missing},{"evicted",s.evicted},{"invalid",s.invalid}};
            }
            if(native_frames) {
                auto s=native_frames->stats();
                message["diag"]["native_pairing"]={{"stream",native_stream},{"width",native_w},{"height",native_h},{"buffered",s.buffered},
                    {"pushed",s.pushed},{"matched",s.matched},{"missing",s.missing},{"evicted",s.evicted},{"invalid",s.invalid}};
            }
            message["diag"]["person_embedding"]={{"enabled",bool(person_embedding)},{"inferences",embedding_count.load()},
                {"defer_on_car",defer_car_embeddings},{"deferred_car",embedding_deferred_car.load()},
                {"failures",embedding_failures.load()},{"skipped",embedding_skipped.load()},{"skipped_stale",embedding_skipped_stale.load()},
                {"max_age_ms",embedding_max_age_ms},{"budget_per_frame",embedding_budget},{"faulted",embedding_faulted.load()},
                {"last_inference_ms",embedding_inference_ms.load()},{"last_crop_ms",embedding_crop_ms.load()},
                {"source",native_frames?"native_"+std::to_string(native_w)+"x"+std::to_string(native_h)+"_when_paired":"paired_1280x720"}};
            message["freshness_budget_ms"]=tracker.config().freshness_ms;
            message["valid_for_ms"]=std::max(0.,tracker.config().freshness_ms-output.target.observation_age_ms);
            const double send_start=now_ms();
            message["diag"]["publisher"]={{"before_send_ms",send_start-output.publish_ms},
                {"interval_ms",last_send_start?send_start-last_send_start:0},{"previous_send_ms",last_send_ms}};
            feed.publish('S',message.dump());
            std::string jpg;
            {std::lock_guard<std::mutex> guard(jpeg_mutex);if(sent_jpeg!=jpeg_version){jpg=latest_jpeg;sent_jpeg=jpeg_version;}}
            if(!jpg.empty())feed.publish('J',jpg);
            last_send_ms=now_ms()-send_start;last_send_start=send_start;
            if(now_ms()-last_report>=10000){std::printf("frames=%lu rejected=%lu\n",frame_count.load(),reject_count.load());std::fflush(stdout);last_report=now_ms();}
            publish_deadline+=std::chrono::milliseconds(40);
            const auto finished=std::chrono::steady_clock::now();
            if(publish_deadline<finished)publish_deadline=finished; // no burst catch-up and no extra sleep after a wait
            std::this_thread::sleep_until(publish_deadline);
        }
        pipeline->stop();media->stop_pipeline();commands.stop();flush_recording();flush_captures();feed.stop();
    }catch(const std::exception& e){std::fprintf(stderr,"garuda-fresh-tracking: %s\n",e.what());return 1;}
    return 0;
}
