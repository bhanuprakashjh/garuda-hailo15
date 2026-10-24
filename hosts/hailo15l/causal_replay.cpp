// Actual 15L DSP/HEF/OSNet and tracker on recorded pixels. Only the initial
// selection point enters this process; no per-frame truth or oracle crop input.
#include "region_detector.hpp"
#include "image_embedding.hpp"
#include "garuda_tracking/json.hpp"
#include "garuda_tracking/tiling.hpp"
#include "garuda/yolo26_decode.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>

int main(int argc,char** argv) {
    using namespace garuda::fresh;
    try {
        if(argc!=3)throw std::invalid_argument("usage: garuda-causal-replay profile.json trial.json|--stream < source");
        const bool live=std::string(argv[2])=="--stream";
        Json cfg,trial;std::ifstream(argv[1])>>cfg;
        if(!live)std::ifstream(argv[2])>>trial;
        const std::string mode=cfg.value("bench_schedule",std::string("adaptive"));
        if(mode!="adaptive"&&mode!="fullview"&&mode!="fullview_roi")
            throw std::invalid_argument("unknown bench_schedule");
        Tracker tracker(config_from_json(cfg.at("tracking")));
        const bool defer_car_embeddings=cfg.value("defer_person_embeddings_on_car",false);
        RoiAssist assist(cfg.value("target_roi_max_age_ms",400.),cfg.value("target_roi_global_window_ms",1600.),2.5,cfg.value("phone_predictive_roi",false));
        FollowSchedule schedule(cfg.value("follow_global_period_ms",800.),cfg.value("follow_local_gap_ms",500.),cfg.value("phone_short_miss_ms",0.));MotionEstimator motion;
        std::vector<std::string> labels(garuda::yolo26::COCO,garuda::yolo26::COCO+80);
        garuda::h15l::RegionDetector detector(cfg.at("hef"),"causal-replay",labels,.15,1280,720,.08);
        garuda::h15l::RegionDetector local(cfg.at("hef"),"causal-replay",labels,.15,1280,720,.015);
        std::unique_ptr<garuda::h15l::ImageEmbedding> embedding;
        if(tracker.config().learned_person_identity)
            embedding=std::make_unique<garuda::h15l::ImageEmbedding>(cfg.at("person_reid_hef"),cfg.at("person_reid_model_id"),"causal-replay");
        const size_t frames=live?1000000:trial.at("frames").get<size_t>(),select_frame=live?0:trial.at("select_frame").get<size_t>();
        const double period=live?50:trial.at("period_ms").get<double>(),source_age=live?0:trial.at("source_age_ms").get<double>();
        if(!frames||(!live&&frames>10000)||period<10||period>1000||source_age<0||source_age>400)
            throw std::invalid_argument("invalid bounded trial");
        constexpr size_t Y=1280*720;std::vector<uint8_t> pixels(Y*3/2),small;
        Image image{pixels.data(),pixels.data()+Y,1280,720,1280,1280,Y,Y/2};
        bool selected=false,attempted=false;double ready=0,first_attempt_ms=0;size_t processed=0,skipped=0,attempts=0;
        uint64_t last_sequence=0;
        for(size_t index=0;index<frames;++index) {
            Json header,ack=nullptr;
            uint64_t sequence=index+1;
            if(live) {
                // Stop-and-wait protocol: bounded JSON line, then exactly one NV12
                // image. Host retains only the latest Gazebo frame while we infer.
                // No network listener, timestamp assumption or MAVLink on the board.
                std::string line;
                char ch;
                while(std::cin.get(ch)&&ch!='\n') {
                    if(line.size()>=4096)throw std::runtime_error("oversize stream header");
                    line+=ch;
                }
                if(!std::cin&&line.empty())break;
                if(!std::cin)throw std::runtime_error("short stream header");
                header=Json::parse(line);
                if(header.at("v")!=1||header.at("bytes")!=pixels.size())throw std::runtime_error("invalid stream shape/version");
                sequence=positive_integer(header.at("sequence"));
                if(sequence<=last_sequence)throw std::runtime_error("source sequence regressed");
                last_sequence=sequence;
            }
            if(!std::cin.read(reinterpret_cast<char*>(pixels.data()),pixels.size()))throw std::runtime_error("short source stream");
            const double capture=live?std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count():1000+index*period;
            // Latest-frame scheduling: never pretend every source frame was processed. Labelled
            // A/B variant (trial "fixed_stride" N > 0): every Nth source frame regardless of timing,
            // because a few ms of noise shifts the processed set by one frame and on a crowd
            // clip that alone swung on-target frames 44 <-> 4 (VisDrone 086, 2026-09-13).
            const size_t stride=live?0:trial.value("fixed_stride",size_t(0));
            if(stride?(index%stride!=0):(capture<ready)){++skipped;continue;}
            const auto began=std::chrono::steady_clock::now();
            auto age=[&]{return source_age+std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();};
            if(live&&header.contains("command"))ack=command(tracker,header.at("command"),capture);
            Frame f;f.sequence=sequence;f.capture_ms=capture;f.now_ms=capture+source_age;f.timestamp_valid=true;
            auto previous=tracker.snapshot(f.now_ms);
            auto regions=five_tile_layout(f.sequence,capture,1280,720);
            const bool global=mode=="adaptive"&&schedule.global_required(previous.target,capture);
            const double detection_started=age();
            auto full=detector.infer(image,regions.back());f.detections=std::move(full.detections);
            for(auto& d:f.detections){d.region_id=4;d.region_full_frame=true;}
            if(global) {
                regions.pop_back();int rid=0;
                for(auto& tile:detector.infer_many(image,regions)) {
                    for(auto d:tile.detections) {
                        if(d.box.w*d.box.h>.05)continue;
                        d.region_id=rid;d.region_full_frame=false;f.detections.push_back(std::move(d));
                    }
                    ++rid;
                }
                f.detections=aggregate_tile_detections(std::move(f.detections));
                if(f.detections.size()>tracker.config().max_detections)f.detections.resize(tracker.config().max_detections);
                for(const auto& d:f.detections)if(previous.target.control_valid&&previous.target.box&&
                    d.label==previous.target.label&&d.confidence>=.4&&iou(d.box,*previous.target.box)>=.3)
                    assist.observe_global(previous.target,capture);
            }
            f.now_ms=capture+age();
            // Every full-view pass is independent global evidence, including in
            // the no-corners ablation. A local crop must never confirm itself.
            if(mode=="fullview_roi")for(const auto& d:f.detections)
                if(previous.target.control_valid&&previous.target.box&&d.label==previous.target.label&&
                    d.confidence>=.4&&iou(d.box,*previous.target.box)>=.3)
                    assist.observe_global(previous.target,capture);
            const auto request=mode=="fullview"?std::optional<SearchRegion>{}:assist.plan(f,previous.target,1280,720);
            bool verified_local=false;Json crop=nullptr,local_dets=Json::array();
            if(request) {
                auto found=local.infer(image,*request);
                crop={{"x",request->x},{"y",request->y},{"w",request->w},{"h",request->h}};
                assist.merge(f,*request,found.detections,tracker.config().max_detections);
                for(const auto& d:found.detections) {
                    const double overlap=previous.target.box?iou(d.box,*previous.target.box):0;
                    // Handover diagnostics: what the local crop saw against the target's last box.
                    local_dets.push_back({{"label",d.label},{"confidence",d.confidence},{"iou_target",overlap},
                        {"x",d.box.x},{"y",d.box.y},{"w",d.box.w},{"h",d.box.h}});
                    if(previous.target.box&&d.label==previous.target.label&&d.confidence>=.4&&overlap>=.4)verified_local=true;
                }
            }
            const double detection_ms=age()-detection_started;
            Json raw_detections=Json::array();
            for(const auto& d:f.detections)raw_detections.push_back({{"label",d.label},{"confidence",d.confidence},
                {"x",d.box.x},{"y",d.box.y},{"w",d.box.w},{"h",d.box.h},{"region_id",d.region_id}});
            const double appearance_started=age();
            for(auto& d:f.detections)d.appearance=describe(image,d.box);
            std::vector<size_t> order;
            for(size_t i=0;i<f.detections.size();++i)if(f.detections[i].label=="person")order.push_back(i);
            const auto& focus=defer_car_embeddings&&previous.target.pending_box?previous.target.pending_box:
                previous.target.box?previous.target.box:   // as the node
                previous.target.pending_box?previous.target.pending_box:previous.target.last_verified_box;
            auto priority=[&](size_t i) {   // as the node: overlap with the focus first, then centre distance
                const auto& d=f.detections[i];
                if(!focus)return -d.confidence;
                const auto& t=*focus;
                const double overlap=iou(d.box,t);
                if(overlap>0)return -overlap-d.confidence*.001;
                return std::hypot(d.box.x+d.box.w/2-t.x-t.w/2,d.box.y+d.box.h/2-t.y-t.h/2)-d.confidence*.001;
            };
            std::stable_sort(order.begin(),order.end(),[&](size_t a,size_t b){return priority(a)<priority(b);});
            size_t embedded=0;
            const bool deferred=defer_person_embeddings_for_car(previous.target,tracker.config(),defer_car_embeddings);
            if(embedding&&!deferred)for(auto i:order) {
                if(embedded>=cfg.value("person_embedding_max_per_frame",size_t(6))||age()>cfg.value("person_embedding_max_age_ms",500.))break;
                f.detections[i].embedding=embedding->infer(image,f.detections[i].box).embedding;++embedded;
            }
            const double appearance_ms=age()-appearance_started;
            const double motion_started=age();
            motion_samples(image,small);
            Image motion_image{small.data(),small.data()+160*90,160,90,160,160,160*90,160*45};
            f.motion=motion.update(motion_image,f.detections);
            const double motion_ms=age()-motion_started;
            f.now_ms=capture+age();auto out=tracker.update(f);
            if(global&&out.target.control_valid)assist.observe_global(out.target,capture);
            schedule.observe(global,verified_local,out.target,capture);
            // Frozen protocol: one click at select_frame. Optional labelled variant
            // (trial "select_retry_ms" > 0): a click refused only for a missing descriptor is
            // repeated on later processed frames within that window, as a person would click
            // again while the node describes the person they pointed at.
            const double retry_ms=live?0:trial.value("select_retry_ms",0.);
            const bool retry=attempted&&!selected&&retry_ms>0&&capture-first_attempt_ms<=retry_ms&&
                (trial.value("select_retry_any",false)||tracker.selection_error().find("descriptor")!=std::string::npos);
            if(!live&&index>=select_frame&&(!attempted||retry)) {
                if(!attempted)first_attempt_ms=capture;
                attempted=true;++attempts;
                selected=tracker.select_point(trial.at("x").get<double>()/1280,
                    trial.at("y").get<double>()/720,f.sequence,f.now_ms);
                out=tracker.snapshot(f.now_ms);
            }
            ready=f.now_ms;++processed;
            if(live)selected=out.target.lock_id!=0;
            std::cout<<Json{{"source_index",index},{"sequence",sequence},{"ack",ack},{"global",global},{"roi",crop},{"roi_reason",assist.reason()},
                {"local",local_dets},{"verified_local",verified_local},
                {"schedule",mode},{"detector_passes",1+(global?4:0)+(request?1:0)},
                {"raw_detections",raw_detections},{"stage_ms",{{"detection",detection_ms},{"appearance",appearance_ms},{"motion",motion_ms}}},
                {"age_ms",age()},{"embedded",embedded},{"person_embeddings_deferred",deferred},
                {"selected",selected},{"selection_error",tracker.selection_error()},
                {"output",output_json(out)}}.dump()<<std::endl;
        }
        std::cerr<<Json{{"processed",processed},{"skipped",skipped},{"selected",selected},{"select_attempts",attempts},
            {"select_retry_ms",live?0.:trial.value("select_retry_ms",0.)},
            {"scope",live?"live NV12 ingress; real HEF/OSNet; no exposure-age claim or actor truth":
                "causal real HEF/OSNet replay; measured processing with explicit source-age assumption; no oracle"}}<<std::endl;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
