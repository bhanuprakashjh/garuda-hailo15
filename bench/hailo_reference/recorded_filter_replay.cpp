// Fixed recorded schedule/core diagnostic, not causal end-to-end replay.
// Recompute appearance with the real core helper on hash-checked saved pixels.
#include "garuda_tracking/json.hpp"
#include "garuda_tracking/tiling.hpp"
#include <fstream>
#include <iostream>
int main(int argc,char** argv) {
    using namespace garuda::fresh;
    try {
        if(argc!=2)throw std::runtime_error("usage: recorded-filter-replay tracking.json < rows.jsonl");
        Json cfg;std::ifstream(argv[1])>>cfg;Tracker tracker(config_from_json(cfg));
        std::vector<uint8_t> pixels(1280*720*3/2);
        std::string line;
        while(std::getline(std::cin,line)) {
            if(line.size()>1024*1024)throw std::runtime_error("oversize row");
            const auto j=Json::parse(line);
            if(j.contains("cmd")){std::cout<<command(tracker,j,j.at("now_ms"))<<'\n';continue;}
            auto f=frame_from_json(j.at("frame"));
            std::ifstream image(j.at("pixels").get<std::string>(),std::ios::binary);
            if(!image.read(reinterpret_cast<char*>(pixels.data()),pixels.size())||image.peek()!=EOF)
                throw std::runtime_error("invalid720p pixels");
            Image view{pixels.data(),pixels.data()+1280*720,1280,720,1280,1280,1280*720,1280*720/2};
            f.detections=aggregate_tile_detections(std::move(f.detections));
            for(auto& d:f.detections)if(d.label=="cell phone")d.appearance=describe(view,d.box);
            std::cout<<output_json(tracker.update(f))<<'\n';
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
