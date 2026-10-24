// Offline exercise of the exact secondary detector used by the camera adapter.
#include "region_detector.hpp"
#include "dsp_crop.hpp"
#include "diagnostic_budget.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
int main(int argc,char** argv) {
    using Json=nlohmann::json;
    if(argc<4||argc>6){std::cerr<<"usage: garuda-region-probe model.hef source.nv12|- regions.json [--audit [--via720]]\n";return 2;}
    try {
        const bool audit_mode=argc>=5,via720=argc==6;
        if((audit_mode&&std::string(argv[4])!="--audit")||(via720&&std::string(argv[5])!="--via720"))
            throw std::runtime_error("unknown option");
        std::ifstream memory("/proc/meminfo");const auto headroom=garuda::h15l::diagnostic_headroom(memory);
        if(!headroom||*headroom<garuda::h15l::diagnostic_reserve+64*garuda::h15l::MiB)
            throw std::runtime_error("insufficient non-CMA headroom for streaming probe");
        std::ifstream definitions(argv[3]);Json regions;definitions>>regions;
        if(!regions.is_array()||regions.empty()||regions.size()>(audit_mode?2048:128))throw std::runtime_error("region count exceeds bound");
        const int sw=regions[0].at("source_w"),sh=regions[0].at("source_h");
        if(sw<2||sh<2||sw>3840||sh>2160||sw%2||sh%2)throw std::runtime_error("invalid source geometry");
        std::vector<std::string> labels;for(int i=0;i<80;++i)labels.push_back(std::to_string(i));
        if(via720&&(sw!=3840||sh!=2160))throw std::runtime_error("via720 requires native4K input");
        std::unique_ptr<garuda::h15l::RegionDetector> detector;
        if(audit_mode)detector=std::make_unique<garuda::h15l::RegionDetector>(argv[1],"garuda-region-probe",labels,.05,via720?1280:sw,via720?720:sh,.08);
        else detector=std::make_unique<garuda::h15l::RegionDetector>(argv[1],"garuda-region-probe","cell phone",.05,sw,sh);
        std::unique_ptr<garuda::h15l::DmaImage> native;
        std::unique_ptr<garuda::h15l::DmaImage> downscale;
        struct Device {dsp_device value=nullptr;~Device(){if(value)dsp_release_device(value);}} dsp;
        if(via720){
            native=std::make_unique<garuda::h15l::DmaImage>(sw,sh);
            downscale=std::make_unique<garuda::h15l::DmaImage>(1280,720);
            if(dsp_create_device(&dsp.value)!=DSP_SUCCESS)throw std::runtime_error("DSP create failed");
        }
        std::ifstream file;std::istream* input=&std::cin;
        if(std::string(argv[2])!="-"){file.open(argv[2],std::ios::binary);if(!file)throw std::runtime_error("input missing");input=&file;}
        const size_t Y=size_t(sw)*sh;
        std::vector<uint8_t> bytes(Y*3/2);
        garuda::fresh::Image image{bytes.data(),bytes.data()+Y,sw,sh,sw,sw,Y,Y/2};
        for(size_t i=0;i<regions.size();++i) {
            const auto& r=regions[i];
            garuda::fresh::SearchRegion region{i+1,1000.+i*50,r.at("source_w"),r.at("source_h"),r.at("x"),r.at("y"),r.at("w"),r.at("h"),640,640,r.at("full_frame")};
            if(!input->read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("partial source frame");
            if(region.source_w!=sw||region.source_h!=sh)throw std::runtime_error("mixed input geometry");
            garuda::h15l::RegionDetections result;
            if(via720) {
                if(region.x%6||region.y%6||region.w%6||region.h%6)throw std::runtime_error("non-exact720 mapping");
                native->copy_from(image);
                const dsp_resize_params_t resize{&native->properties(),&downscale->properties(),INTERPOLATION_TYPE_BILINEAR};
                if(dsp_resize(dsp.value,&resize)!=DSP_SUCCESS)throw std::runtime_error("DSP720 resize failed");
                garuda::h15l::DmaImage::ReadAccess access(*downscale);
                auto scaled=region;scaled.source_w/=3;scaled.source_h/=3;scaled.x/=3;scaled.y/=3;scaled.w/=3;scaled.h/=3;
                result=detector->infer(access.image(),scaled,true);
            } else result=detector->infer(image,region,audit_mode);
            Json ds=Json::array(),audit=Json::array();
            for(const auto& d:result.detections) {
                const auto b=result.region.to_network(d.box);
                ds.push_back({{"class_id",audit_mode?std::stoi(d.label):67},{"score",d.confidence},{"x1",b.x},{"y1",b.y},{"x2",b.x+b.w},{"y2",b.y+b.h}});
            }
            for(const auto& a:result.audit) {
                const auto b=a.network_box;
                audit.push_back({{"class_id",std::stoi(a.detection.label)},{"score",a.detection.confidence},
                    {"x1",b.x},{"y1",b.y},{"x2",b.x+b.w},{"y2",b.y+b.h},
                    {"fixed_cut",a.fixed_cut},{"relative_cut",a.relative_cut}});
            }
            std::cout<<Json{{"frame",i},{"detections",ds},{"pre_filter",audit},{"cut_boxes",result.cut_boxes},
                {"network_w",result.region.network_w},{"network_h",result.region.network_h},
                {"source_copy_ms",result.source_copy_ms},{"dsp_ms",result.dsp_ms},{"input_copy_ms",result.input_copy_ms},
                {"inference_ms",result.inference_ms}}.dump()<<'\n';
        }
        if(input->peek()!=EOF)throw std::runtime_error("extra source frames");
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
