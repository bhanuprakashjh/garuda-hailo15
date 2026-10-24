// Recorded pixels + detections, real tracking core. No board/network access.
#include "garuda_tracking/json.hpp"
#include "garuda_tracking/visual_target.hpp"
#include <opencv2/core.hpp>
#include <fstream>
#include <iostream>
#include <chrono>

int main(int argc,char** argv) {
    using namespace garuda::fresh;
    try {
        if(argc!=3)throw std::runtime_error("usage: garuda-visual-replay tracking.json baseline|candidate");
        const std::string mode=argv[2];if(mode!="baseline"&&mode!="candidate")throw std::runtime_error("bad mode");
        cv::setNumThreads(1);
        Json cfg;std::ifstream(argv[1])>>cfg;cfg["visual_phone_tracking"]=mode=="candidate";
        Tracker tracker(config_from_json(cfg));VisualTargetTracker visual;
        std::vector<uint8_t> pixels;Image image;Frame frame;bool have_frame=false;
        auto seed=[&](const Output& o){
            const auto& t=o.target;
            if(mode=="candidate"&&t.label=="cell phone"&&t.control_valid&&!t.visual_observation&&t.box)
                visual.seed(image,*t.box,frame.sequence,frame.capture_ms,t.lock_id,t.epoch);
        };
        std::string line;
        while(std::getline(std::cin,line)) {
            if(line.size()>1024*1024)throw std::runtime_error("oversize row");
            auto j=Json::parse(line);
            if(j.contains("cmd")) {
                auto ack=command(tracker,j,j.at("now_ms"));
                if(have_frame&&ack.value("ok",false))seed(tracker.snapshot(frame.now_ms));
                std::cout<<ack<<'\n';continue;
            }
            const int w=j.value("width",1280),h=j.value("height",720);
            if(w<16||h<16||w>4096||h>2160||w%2||h%2)throw std::runtime_error("bad geometry");
            pixels.resize(size_t(w)*h*3/2);
            const auto path=j.at("pixels").get<std::string>();
            if(path=="-") {
                if(!std::cin.read(reinterpret_cast<char*>(pixels.data()),pixels.size()))throw std::runtime_error("short streamed image");
            } else {
                std::ifstream source(path,std::ios::binary);
                const auto offset=j.value("offset",uint64_t(0));source.seekg(offset);
                if(!source.read(reinterpret_cast<char*>(pixels.data()),pixels.size()))throw std::runtime_error("short image");
            }
            image={pixels.data(),pixels.data()+w*h,w,h,w,w,size_t(w)*h,size_t(w)*h/2};
            if(j.value("letterbox",false))image=FrameGeometry::make(1280,720,w,h,true).content(image);
            frame=frame_from_json(j.at("frame"));have_frame=true;
            for(auto& d:frame.detections)if(d.label=="cell phone")d.appearance=describe(image,d.box);
            const auto before=tracker.snapshot(frame.now_ms);VisualTargetResult result;
            if(mode=="candidate") {
                result=visual.locate(image,frame.sequence,frame.capture_ms,before.target.lock_id,before.target.epoch);
                frame.visual_target=result.measurement;
            }
            auto out=tracker.update(frame);
            auto start=std::chrono::steady_clock::now();seed(out);
            const double seed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
            auto json=output_json(out,j.value("display_width",w),j.value("display_height",h));
            json["visual"]={{"reason",result.reason},{"score",result.score},{"margin",result.margin},
                {"elapsed_ms",result.elapsed_ms},{"seed_ms",seed_ms},{"proposed",result.measurement.has_value()}};
            std::cout<<json<<'\n';
        }
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
