// Offline detector comparison on identical packed 640x640 NV12 frames.
// No camera, tracker, or flight interfaces. HailoRT 5.3.0 / Hailo-15L.
#include <hailo/hailort.hpp>
#include <hailo/infer_model.hpp>
#include <nlohmann/json.hpp>
#include "garuda/yolo26_decode.hpp"
#include <sys/mman.h>
#include <unistd.h>
#include <fstream>
#include <iostream>
#include <cmath>
#include <cstring>
#include <array>
#include <chrono>
using namespace hailort;
using Json=nlohmann::json;
void check(hailo_status s){if(s!=HAILO_SUCCESS)throw std::runtime_error("Hailo status "+std::to_string(s));}
template<class T>T take(Expected<T>&& x){if(!x)throw std::runtime_error("Hailo status "+std::to_string(x.status()));return x.release();}
struct Memory {
    void* p;size_t size,allocated;
    explicit Memory(size_t n):size(n){
        size_t page=size_t(sysconf(_SC_PAGESIZE));allocated=(n+page-1)/page*page;
        p=mmap(nullptr,allocated,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        if(p==MAP_FAILED)throw std::runtime_error("mmap failed");
    }
    ~Memory(){munmap(p,allocated);}
    Memory(const Memory&)=delete;Memory& operator=(const Memory&)=delete;
};
// Reuse the existing Pi-parity YOLO26 decoder; do not invent a second raw-head interpretation.
int probe_yolo26(const std::shared_ptr<InferModel>& model,const char* path,float threshold) {
    auto input=take(model->input());const auto shape=input.shape();
    if(input.format().order!=HAILO_FORMAT_ORDER_NV12||shape.height!=320||shape.width!=640||shape.features!=3)
        throw std::runtime_error("raw-head probe requires 640x640 NV12 input");
    input.set_format_type(HAILO_FORMAT_TYPE_UINT8);
    std::array<std::string,6> names{};std::array<std::unique_ptr<Memory>,6> memory;
    for(auto output:model->outputs()) {
        const auto s=output.shape();
        const int scale=s.height==80?0:s.height==40?1:s.height==20?2:-1;
        if(scale<0||s.width!=s.height||(s.features!=4&&s.features!=80)||output.format().order!=HAILO_FORMAT_ORDER_NHWC)
            throw std::runtime_error("unexpected YOLO26 raw-head layout");
        const size_t slot=scale+(s.features==80?3:0);
        if(!names[slot].empty())throw std::runtime_error("duplicate raw-head shape");
        names[slot]=output.name();output.set_format_type(HAILO_FORMAT_TYPE_FLOAT32);
        output.set_format_order(HAILO_FORMAT_ORDER_NHWC);
        if(output.get_frame_size()!=size_t(s.width)*s.height*s.features*sizeof(float))
            throw std::runtime_error("raw-head buffer size mismatch");
        memory[slot]=std::make_unique<Memory>(output.get_frame_size());
    }
    model->set_batch_size(1);auto configured=take(model->configure());
    check(configured.set_scheduler_threshold(1));check(configured.set_scheduler_timeout(std::chrono::milliseconds(10)));
    auto bindings=take(configured.create_bindings());
    constexpr size_t Y=640*640,UV=Y/2;
    if(input.get_frame_size()!=Y+UV)throw std::runtime_error("invalid raw-head input size");
    Memory y(Y),uv(UV);
    hailo_pix_buffer_t pix{};pix.number_of_planes=2;pix.memory_type=HAILO_PIX_BUFFER_MEMORY_TYPE_USERPTR;
    pix.planes[0].bytes_used=Y;pix.planes[0].plane_size=Y;pix.planes[0].user_ptr=y.p;
    pix.planes[1].bytes_used=UV;pix.planes[1].plane_size=UV;pix.planes[1].user_ptr=uv.p;
    check(take(bindings.input()).set_pix_buffer(pix));
    for(size_t i=0;i<6;++i) {
        if(!memory[i])throw std::runtime_error("missing raw-head tensor");
        check(take(bindings.output(names[i])).set_buffer(MemoryView(memory[i]->p,memory[i]->size)));
    }
    std::ifstream file(path,std::ios::binary);if(!file)throw std::runtime_error("input missing");
    size_t frame=0;
    while(file.peek()!=EOF) {
        if(frame>=512)throw std::runtime_error("raw-head probe frame limit exceeded");
        if(!file.read(static_cast<char*>(y.p),Y)||!file.read(static_cast<char*>(uv.p),UV))throw std::runtime_error("partial NV12 frame");
        const auto start=std::chrono::steady_clock::now();
        check(configured.run(bindings,std::chrono::milliseconds(5000)));
        const auto inference_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        garuda::yolo26::TensorView boxes[3],classes[3];
        for(int i=0;i<6;++i) {
            const auto* p=static_cast<const float*>(memory[i]->p);
            for(size_t j=0;j<memory[i]->size/sizeof(float);++j)if(!std::isfinite(p[j]))throw std::runtime_error("nonfinite raw-head output");
            const int size=80>>(i%3);
            auto view=garuda::yolo26::TensorView{p,size,size,i<3?4:80,false,0,1};
            if(i<3)boxes[i]=view;else classes[i-3]=view;
        }
        garuda::yolo26::Params params;params.conf_thresh=threshold;
        const auto detections=garuda::yolo26::decode(boxes,classes,params,640,640,{1,1,0,0});
        Json ds=Json::array();for(const auto& d:detections)ds.push_back({{"class_id",d.class_id},{"score",d.conf},
            {"x1",d.x1/640},{"y1",d.y1/640},{"x2",d.x2/640},{"y2",d.y2/640}});
        std::cout<<Json{{"frame",frame++},{"detections",ds},{"inference_ms",inference_ms},{"decoder","garuda.yolo26.pi-parity"}}.dump()<<'\n';
    }
    std::cerr<<"inferred "<<frame<<" raw-head frames\n";return 0;
}
int main(int argc,char** argv){
    if(argc!=4){std::cerr<<"usage: garuda-model-probe model.hef input.nv12 score_threshold\n";return 2;}
    try {
        float threshold=std::stof(argv[3]);if(!std::isfinite(threshold)||threshold<.001||threshold>1)throw std::runtime_error("invalid threshold");
        hailo_vdevice_params_t params{};check(hailo_init_vdevice_params(&params));
        params.group_id="garuda-model-probe";params.multi_process_service=true;
        auto device=take(VDevice::create(params));auto model=take(device->create_infer_model(argv[1]));
        if(model->outputs().size()==6)return probe_yolo26(model,argv[2],threshold);
        auto input=take(model->input());auto output=take(model->output());
        if(input.format().order!=HAILO_FORMAT_ORDER_NV12||output.format().order!=HAILO_FORMAT_ORDER_HAILO_NMS_BY_CLASS)
            throw std::runtime_error("probe requires NV12 input and NMS-by-class output");
        auto shape=input.shape();auto nms=take(output.get_nms_shape());
        if(shape.height!=320||shape.width!=640||shape.features!=3||nms.number_of_classes!=80||nms.max_bboxes_per_class!=100)
            throw std::runtime_error("unexpected model shape or class layout");
        input.set_format_type(HAILO_FORMAT_TYPE_UINT8);output.set_format_type(HAILO_FORMAT_TYPE_FLOAT32);
        output.set_nms_score_threshold(threshold);model->set_batch_size(1);
        auto configured=take(model->configure());check(configured.set_scheduler_threshold(1));
        check(configured.set_scheduler_timeout(std::chrono::milliseconds(10)));
        auto bindings=take(configured.create_bindings());
        constexpr size_t Y=640*640,UV=Y/2;
        if(input.get_frame_size()!=Y+UV)throw std::runtime_error("input is not 640x640 NV12");
        Memory y(Y),uv(UV),out(output.get_frame_size());
        hailo_pix_buffer_t pix{};pix.number_of_planes=2;pix.memory_type=HAILO_PIX_BUFFER_MEMORY_TYPE_USERPTR;
        pix.planes[0].bytes_used=Y;pix.planes[0].plane_size=Y;pix.planes[0].user_ptr=y.p;
        pix.planes[1].bytes_used=UV;pix.planes[1].plane_size=UV;pix.planes[1].user_ptr=uv.p;
        check(take(bindings.input()).set_pix_buffer(pix));check(take(bindings.output()).set_buffer(MemoryView(out.p,out.size)));
        std::ifstream file(argv[2],std::ios::binary);if(!file)throw std::runtime_error("input missing");
        size_t frame=0;
        while(file.peek()!=EOF){
            if(!file.read(static_cast<char*>(y.p),Y)||!file.read(static_cast<char*>(uv.p),UV))throw std::runtime_error("partial NV12 frame");
            check(configured.run(bindings,std::chrono::milliseconds(5000)));
            const float* data=static_cast<const float*>(out.p);size_t pos=0,limit=out.size/sizeof(float);
            Json ds=Json::array();
            for(int cls=0;cls<80;++cls){
                if(pos>=limit||!std::isfinite(data[pos])||data[pos]<0||data[pos]>100||std::floor(data[pos])!=data[pos])throw std::runtime_error("invalid NMS count");
                int n=int(data[pos++]);if(pos+size_t(n)*5>limit)throw std::runtime_error("NMS overflow");
                for(int i=0;i<n;++i,pos+=5){
                    for(int k=0;k<5;++k)if(!std::isfinite(data[pos+k]))throw std::runtime_error("invalid NMS value");
                    ds.push_back({{"class_id",cls},{"y1",data[pos]},{"x1",data[pos+1]},{"y2",data[pos+2]},{"x2",data[pos+3]},{"score",data[pos+4]}});
                }
            }
            std::cout<<Json{{"frame",frame++},{"detections",ds}}.dump()<<'\n';
        }
        std::cerr<<"inferred "<<frame<<" frames\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
