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
    if(argc!=5){std::cerr<<"usage: hailo-reference-probe model.hef regions.json post.json output.jsonl < source.nv12\n";return 2;}
    try {
        std::ifstream definitions(argv[2]);Json regions;definitions>>regions;
        if(!regions.is_array()||regions.empty()||regions.size()>128)throw std::runtime_error("expected 1..128 inputs");
        std::ofstream output(argv[4]);if(!output)throw std::runtime_error("output unavailable");
        auto source_pool=std::make_shared<MediaLibraryBufferPool>(1280,720,HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"stored-source");
        auto network_pool=std::make_shared<MediaLibraryBufferPool>(640,640,HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"stored-network");
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
        garuda::h15l::DmaImage ours_source(1280,720);garuda::h15l::DspCrop ours_crop;
        constexpr size_t Y=1280*720;std::vector<uint8_t> bytes(Y*3/2),ours;
        for(size_t i=0;i<regions.size();++i) {
            const auto& r=regions[i];
            garuda::fresh::SearchRegion region{i+1,1000.+i*50,r.at("source_w"),r.at("source_h"),r.at("x"),r.at("y"),r.at("w"),r.at("h"),640,640,r.at("full_frame")};
            if(!region.valid()||region.source_w!=1280||region.source_h!=720)throw std::runtime_error("invalid region");
            if(!std::cin.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("partial frame");
            auto source=std::make_shared<hailo_media_library_buffer>(),network=std::make_shared<hailo_media_library_buffer>();
            media_check(source_pool->acquire_buffer(source));media_check(network_pool->acquire_buffer(network));
            media_check(source->sync_start());
            for(int plane=0;plane<2;++plane)for(int row=0;row<(plane?360:720);++row)
                std::memcpy(static_cast<uint8_t*>(source->get_plane_ptr(plane))+row*source->get_plane_stride(plane),bytes.data()+(plane?Y:0)+row*1280,1280);
            media_check(source->sync_end());
            dsp_utils::crop_resize_dims_t dims{1,size_t(region.x),size_t(region.x+region.w),size_t(region.y),size_t(region.y+region.h),640,640};
            dsp_letterbox_properties_t letterbox{};letterbox.alignment=DSP_LETTERBOX_MIDDLE;
            letterbox.color.y=0;letterbox.color.u=128;letterbox.color.v=128;
            if(dsp_utils::perform_crop_and_resize(source->buffer_data.get(),network->buffer_data.get(),dims,
                INTERPOLATION_TYPE_BILINEAR,letterbox)!=DSP_SUCCESS)throw std::runtime_error("reference resize failed");
            garuda::fresh::Image image{bytes.data(),bytes.data()+Y,1280,720,1280,1280,Y,Y/2};
            ours_source.copy_from(image);ours_crop.run(ours_source.properties(),region).copy_to(ours);
            size_t differing=0;int max_difference=0;
            media_check(network->sync_start());
            for(int plane=0;plane<2;++plane)for(int row=0;row<(plane?320:640);++row)for(int col=0;col<640;++col) {
                const auto actual=static_cast<uint8_t*>(network->get_plane_ptr(plane))[row*network->get_plane_stride(plane)+col];
                const int difference=std::abs(int(actual)-int(ours[(plane?640*640:0)+row*640+col]));
                differing+=difference!=0;max_difference=std::max(max_difference,difference);
            }
            media_check(network->sync_end());
            {std::lock_guard<std::mutex> lock(mutex);complete=false;}
            detect->push(std::make_shared<Buffer>(network),"stored-input");
            std::unique_lock<std::mutex> lock(mutex);
            if(!ready.wait_for(lock,std::chrono::seconds(5),[&]{return complete;}))throw std::runtime_error("reference inference timed out");
            output<<Json{{"frame",i},{"detections",detections},{"pixel_differences",differing},{"max_pixel_difference",max_difference}}.dump()<<'\n';
        }
        if(std::cin.peek()!=EOF)throw std::runtime_error("extra input frames");
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
