// Stored-frame harness around installed Hailo 1.12 SDK stages, not a camera app.
// Reference: hailo-media-library 9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f.
#include "dsp_crop.hpp"
#include <media_library/buffer_pool.hpp>
#include <media_library/dsp_utils.hpp>
#include <hailo_analytics/pipeline/ai/ai_stage.hpp>
#include <hailo_analytics/pipeline/ai/postprocess_stage.hpp>
#include <hailo_analytics/pipeline/sinks/app_sink_stage.hpp>
#include <hailo_analytics/pipeline/core/pipeline_builder.hpp>
#include <nlohmann/json.hpp>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <cstring>

using Json=nlohmann::json;
using namespace hailo_analytics::pipeline;
void media_check(media_library_return s) {
    if(s!=MEDIA_LIBRARY_SUCCESS)throw std::runtime_error("media buffer operation failed");
}
int main(int argc,char** argv) {
    if(argc!=6&&argc!=7){std::cerr<<"usage: hailo-reference-probe model.hef regions.json post.json output.jsonl stretch|letterbox [network-inputs.nv12] < source.nv12\n";return 2;}
    try {
        const std::string mode=argv[5];
        if(mode!="stretch" && mode!="letterbox")throw std::runtime_error("invalid mode");
        std::ifstream definitions(argv[2]);Json regions;definitions>>regions;
        if(!regions.is_array()||regions.empty()||regions.size()>16384)throw std::runtime_error("expected 1..16384 inputs");
        const int sw=regions[0].at("source_w"), sh=regions[0].at("source_h");
        if(sw<=0||sh<=0||sw>3840||sh>2160||sw%2||sh%2)throw std::runtime_error("invalid source dimensions");
        // Network input of the HEF under test: 640x640 unless the preparation says otherwise
        // (a 1280x736 model takes a 16:9 frame at full 720p scale in one pass).
        const int nw=regions[0].value("network_w",640), nh=regions[0].value("network_h",640);
        if(nw<320||nh<320||nw>1920||nh>1920||nw%32||nh%32)throw std::runtime_error("invalid network dimensions");
        std::ofstream output(argv[4]);if(!output)throw std::runtime_error("output unavailable");
        std::ofstream input_dump;
        if(argc==7){input_dump.open(argv[6],std::ios::binary);if(!input_dump)throw std::runtime_error("input dump unavailable");}
        auto source_pool=std::make_shared<MediaLibraryBufferPool>(sw,sh,HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"stored-source");
        auto half_pool=std::make_shared<MediaLibraryBufferPool>(1920,1080,HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"stored-half");
        media_check(half_pool->init());
        auto network_pool=std::make_shared<MediaLibraryBufferPool>(nw,nh,HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"stored-network");
        media_check(source_pool->init());media_check(network_pool->init());
        if(dsp_utils::acquire_device()!=DSP_SUCCESS)throw std::runtime_error("reference DSP unavailable");
        struct DspRelease {~DspRelease(){dsp_utils::release_device();}} dsp_release;
        auto detect=ai::HailortAsyncStageBuild::create().set_stage_name("detect").set_hef_path(argv[1])
            .set_queue_size(1).set_output_pool_size(4).set_group_id("stored-reference").set_batch_size(1).set_job_limit(1)
            .set_scheduler_threshold_opt(1).set_scheduler_timeout_opt(std::chrono::milliseconds(10))
            .set_nms_score_threshold(.05f).buildptr();
        auto post=ai::PostprocessStageBuild::create().set_stage_name("post")
            .set_so_path("/usr/lib/hailo-post-processes/libyolo_hailortpp_post.so")
            .set_config_path_opt(argv[3]).set_queue_size_opt(1).buildptr();
        std::mutex mutex;std::condition_variable ready;bool complete=false;Json detections;
        auto sink=sinks::AppSinkStageBuild::create().set_stage_name("result").set_queue_size_opt(1)
            .set_process_func([&](BufferPtr buffer){
                Json ds=Json::array();
                for(const auto& d:hailo_common::get_hailo_detections(buffer->get_roi())) {
                    const auto b=d->get_bbox();
                    ds.push_back({{"class_id",d->get_class_id()-1},{"label",d->get_label()},
                        {"score",d->get_confidence()},{"x1",b.xmin()},{"y1",b.ymin()},
                        {"x2",b.xmax()},{"y2",b.ymax()}});
                }
                {std::lock_guard<std::mutex> lock(mutex);detections=std::move(ds);complete=true;}ready.notify_one();
            }).buildptr();
        PipelineBuilder builder;
        builder.add_stage("detect",detect,StageType::SOURCE).add_stage("post",post)
            .add_stage("result",sink,StageType::SINK).connect("detect","post").connect("post","result");
        auto pipeline=builder.build("stored-reference");detect->add_queue("stored-input");
        if(pipeline->start()!=AppStatus::SUCCESS)throw std::runtime_error("reference pipeline start failed");
        struct Stop {PipelinePtr p;~Stop(){p->stop();}} stop{pipeline};
        dsp_device device=nullptr;
        if(dsp_create_device(&device)!=DSP_SUCCESS)throw std::runtime_error("DSP create failed");
        struct Release {dsp_device d;~Release(){dsp_release_device(d);}} release{device};
        const size_t Y=size_t(sw)*sh;std::vector<uint8_t> bytes(Y*3/2);
        // Sequence replay: a region marked reuse_source shares the previously
        // streamed frame (and its cached half-resolution buffer) instead of
        // consuming stdin, so one frame feeds all of its tiles.
        std::shared_ptr<hailo_media_library_buffer> loaded,halved;
        for(size_t i=0;i<regions.size();++i) {
            const auto& r=regions[i];
            if(r.value("network_w",640)!=nw||r.value("network_h",640)!=nh)throw std::runtime_error("mixed network dimensions");
            garuda::fresh::SearchRegion region{i+1,1000.+i*50,r.at("source_w"),r.at("source_h"),r.at("x"),r.at("y"),r.at("w"),r.at("h"),nw,nh,r.at("full_frame")};
            // Replay also accepts rectangular vendor tiles; the live search
            // planner deliberately accepts only square local ROIs.
            if(region.source_w!=sw||region.source_h!=sh||region.x<0||region.y<0||
               region.w<2||region.h<2||region.x>sw-region.w||region.y>sh-region.h||
               region.x%2||region.y%2||region.w%2||region.h%2)
                throw std::runtime_error("invalid region");
            if(r.value("via_1080p",false)&&(region.x%4||region.y%4||region.w%4||region.h%4))
                throw std::runtime_error("unaligned half-resolution region");
            if(!r.value("reuse_source",false)) {
                if(!std::cin.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("partial frame");
                auto fresh=std::make_shared<hailo_media_library_buffer>();
                media_check(source_pool->acquire_buffer(fresh));
                media_check(fresh->sync_start());
                for(int plane=0;plane<2;++plane)for(int row=0;row<(plane?sh/2:sh);++row)
                    std::memcpy(static_cast<uint8_t*>(fresh->get_plane_ptr(plane))+row*fresh->get_plane_stride(plane),bytes.data()+(plane?Y:0)+row*sw,sw);
                media_check(fresh->sync_end());
                loaded=fresh;halved=nullptr;
            } else if(!loaded)throw std::runtime_error("reuse_source before any source frame");
            auto source=loaded,network=std::make_shared<hailo_media_library_buffer>();
            media_check(network_pool->acquire_buffer(network));
            auto dst=network->buffer_data->As<hailo_dsp_buffer_data_t>();
            if(r.value("via_1080p",false)) {
                if(sw!=3840||sh!=2160)throw std::runtime_error("1080p comparison requires 4K source");
                if(!halved) {
                    auto half=std::make_shared<hailo_media_library_buffer>();
                    media_check(half_pool->acquire_buffer(half));
                    auto src=loaded->buffer_data->As<hailo_dsp_buffer_data_t>();
                    auto hd=half->buffer_data->As<hailo_dsp_buffer_data_t>();
                    const dsp_resize_params_t down{&src.properties,&hd.properties,INTERPOLATION_TYPE_BILINEAR};
                    const dsp_roi_t full{0,0,3840,2160};
                    if(dsp_crop_and_resize(device,&down,&full)!=DSP_SUCCESS)throw std::runtime_error("1080p resize failed");
                    halved=half;
                }
                source=halved;
                region.x/=2;region.y/=2;region.w/=2;region.h/=2;
            }
            const dsp_roi_t roi{size_t(region.x),size_t(region.y),size_t(region.x+region.w),size_t(region.y+region.h)};
            auto crop_src=source->buffer_data->As<hailo_dsp_buffer_data_t>();
            const dsp_resize_params_t resize{&crop_src.properties,&dst.properties,INTERPOLATION_TYPE_BILINEAR};
            dsp_letterbox_properties_t padding{};padding.alignment=DSP_LETTERBOX_MIDDLE;
            padding.color.y=114;padding.color.u=128;padding.color.v=128;
            const auto status=mode=="letterbox" ? dsp_crop_and_resize_letterbox(device,&resize,&roi,&padding)
                                               : dsp_crop_and_resize(device,&resize,&roi);
            if(status!=DSP_SUCCESS)throw std::runtime_error("resize failed");
            if(input_dump.is_open()) {
                media_check(network->sync_start());
                for(int plane=0;plane<2;++plane)for(int row=0;row<(plane?nh/2:nh);++row)
                    input_dump.write(static_cast<const char*>(network->get_plane_ptr(plane))+row*network->get_plane_stride(plane),nw);
                media_check(network->sync_end());
                if(!input_dump)throw std::runtime_error("input dump write failed");
            }
            const auto begin=std::chrono::steady_clock::now();
            {std::lock_guard<std::mutex> lock(mutex);complete=false;}
            detect->push(std::make_shared<Buffer>(network),"stored-input");
            std::unique_lock<std::mutex> lock(mutex);
            if(!ready.wait_for(lock,std::chrono::seconds(5),[&]{return complete;}))throw std::runtime_error("reference inference timed out");
            output<<Json{{"frame",i},{"detections",detections},{"preprocessing",mode},{"infer_wait_ms",std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count()}}.dump()<<'\n';
        }
        if(std::cin.peek()!=EOF)throw std::runtime_error("extra input frames");
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
