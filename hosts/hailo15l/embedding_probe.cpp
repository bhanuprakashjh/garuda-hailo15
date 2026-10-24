// Bench-only NV12 embedding inference through the same adapter used by the camera node.
#include "image_embedding.hpp"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sys/resource.h>

int main(int argc,char** argv) {
    using Json=nlohmann::json;
    if(argc!=4&&argc!=5){std::cerr<<"usage: garuda-embedding-probe model.hef packed.nv12|- model_id [--clip]\n";return 2;}
    try {
        const bool clip=argc==5;
        if(clip&&std::string(argv[4])!="--clip")throw std::invalid_argument("unknown embedding probe mode");
        const int width=clip?224:128,height=clip?224:256,timeout=clip?500:100;
        const auto load_start=std::chrono::steady_clock::now();
        garuda::h15l::ImageEmbedding model(argv[1],argv[3],"garuda-embedding-probe",width,height,timeout);
        const auto load_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-load_start).count();
        std::ifstream file;std::istream* input=&std::cin;
        if(std::string(argv[2])!="-"){file.open(argv[2],std::ios::binary);if(!file)throw std::runtime_error("input file missing");input=&file;}
        const size_t Y=size_t(width)*height,UV=Y/2;
        std::vector<uint8_t> bytes(Y+UV);std::vector<double> durations,crops;
        garuda::fresh::Image image{bytes.data(),bytes.data()+Y,width,height,width,width,Y,UV};
        size_t frame=0;
        while(input->peek()!=EOF) {
            if(frame>=4096)throw std::runtime_error("probe frame limit exceeded");
            if(!input->read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("partial NV12 frame");
            const auto result=model.infer(image,{0,0,1,1});
            std::cout<<Json{{"frame",frame++},{"inference_ms",result.inference_ms},{"crop_ms",result.crop_ms},
                {"raw_norm",result.raw_norm},{"model",result.embedding.model},{"embedding",result.embedding.values},
                {"input_width",width},{"input_height",height},{"timeout_ms",timeout}}.dump()<<'\n';
            durations.push_back(result.inference_ms);crops.push_back(result.crop_ms);
        }
        if(durations.empty())throw std::runtime_error("no NV12 frames");
        std::sort(durations.begin(),durations.end());std::sort(crops.begin(),crops.end());
        rusage usage{};if(getrusage(RUSAGE_SELF,&usage))throw std::runtime_error("cannot measure probe resources");
        std::cerr<<Json{{"frames",frame},{"inference_median_ms",durations[durations.size()/2]},
            {"inference_p95_ms",durations[size_t((durations.size()-1)*.95)]},
            {"crop_median_ms",crops[crops.size()/2]},
            {"model_load_ms",load_ms},{"peak_rss_kib",usage.ru_maxrss},
            {"scope","sequential NPU calls including host wait; crop reported separately; excludes model load and detector contention"}}.dump()<<'\n';
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
