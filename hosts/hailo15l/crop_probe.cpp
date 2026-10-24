// DSP-only, streaming probe: input and output are packed NV12. Does not open the NPU or camera.
#include "dsp_crop.hpp"
#include "diagnostic_budget.hpp"
#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>

int main(int argc,char** argv) {
    using Json=nlohmann::json;using namespace garuda;
    if(argc!=5){std::cerr<<"usage: garuda-crop-probe source.nv12 regions.json output.nv12 metadata.jsonl\n";return 2;}
    try {
        std::ifstream manifest(argv[2]);Json regions;manifest>>regions;
        if(!regions.is_array()||regions.empty()||regions.size()>128)throw std::invalid_argument("expected 1..128 regions");
        const int nw=regions[0].value("network_w",640),nh=regions[0].value("network_h",640);
        if(nw<320||nh<320||nw>1920||nh>1920||nw%32||nh%32)
            throw std::invalid_argument("invalid network dimensions");
        const uint64_t output_bytes=regions.size()*uint64_t(nw)*nh*3/2;
        std::ifstream memory("/proc/meminfo");std::error_code disk_error;
        auto parent=std::filesystem::path(argv[3]).parent_path();if(parent.empty())parent=".";
        const auto disk=std::filesystem::space(parent,disk_error);
        if(output_bytes>32*garuda::h15l::MiB||disk_error||
           !garuda::h15l::diagnostic_fits(garuda::h15l::diagnostic_headroom(memory),disk.available,output_bytes))
            throw std::runtime_error("DSP probe output exceeds storage/non-CMA memory budget");
        int sw=regions[0].at("source_w"),sh=regions[0].at("source_h");
        h15l::DmaImage source(sw,sh);h15l::DspCrop crop(nw,nh);
        std::vector<uint8_t> input(size_t(sw)*sh*3/2),output;
        std::ifstream file(argv[1],std::ios::binary);std::ofstream result(argv[3],std::ios::binary),meta(argv[4]);
        if(!file||!result||!meta)throw std::runtime_error("cannot open probe file");
        size_t index=0;
        for(const auto& r:regions) {
            fresh::SearchRegion region{index+1,double(index),r.at("source_w"),r.at("source_h"),r.at("x"),r.at("y"),r.at("w"),r.at("h"),nw,nh,r.at("full_frame")};
            if(!region.valid()||region.source_w!=sw||region.source_h!=sh||r.value("network_w",640)!=nw||r.value("network_h",640)!=nh)
                throw std::invalid_argument("invalid or mixed probe crop geometry");
            if(!file.read(reinterpret_cast<char*>(input.data()),input.size()))throw std::runtime_error("partial source NV12 frame");
            source.copy_from({input.data(),input.data()+size_t(sw)*sh,sw,sh,sw,sw,size_t(sw)*sh,size_t(sw)*sh/2});
            const auto& cropped=crop.run(source.properties(),region);
            cropped.copy_to(output);result.write(reinterpret_cast<const char*>(output.data()),output.size());
            h15l::DmaImage::ReadAccess pixels(cropped);
            if(!region.geometry().matches_layout(pixels.image()))throw std::runtime_error("DSP pixels disagree with crop geometry");
            meta<<Json{{"frame",index++},{"region",r},{"dsp_ms",crop.last_ms()},{"layout_verified",true}}.dump()<<'\n';
            if(!result||!meta)throw std::runtime_error("probe write failed");
        }
        if(file.peek()!=EOF)throw std::runtime_error("extra source frame data");
        std::cerr<<"cropped "<<index<<" frames\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
