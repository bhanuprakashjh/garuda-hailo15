#include "region_detector.hpp"
#include "dsp_crop.hpp"
#include <hailo/hailort.hpp>
#include <hailo/infer_model.hpp>
#include <sys/mman.h>
#include <unistd.h>
#include <chrono>
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace garuda::h15l {
namespace {
void check(hailo_status status) {
    if(status!=HAILO_SUCCESS)throw std::runtime_error("region detector Hailo status "+std::to_string(status));
}
template<class T>T take(hailort::Expected<T>&& result) {
    if(!result)throw std::runtime_error("region detector Hailo status "+std::to_string(result.status()));
    return result.release();
}
struct Memory {
    void* data;size_t size,allocated;
    explicit Memory(size_t bytes):size(bytes) {
        if(!bytes||bytes>4*1024*1024)throw std::invalid_argument("region detector buffer exceeds bound");
        const auto page=size_t(sysconf(_SC_PAGESIZE));allocated=(bytes+page-1)/page*page;
        data=mmap(nullptr,allocated,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        if(data==MAP_FAILED)throw std::runtime_error("region detector mmap failed");
    }
    ~Memory(){munmap(data,allocated);}
    Memory(const Memory&)=delete;Memory& operator=(const Memory&)=delete;
};
double elapsed(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
}
}
struct RegionDetector::Impl {
    std::string group,label;int class_id;
    bool multi=false;std::vector<std::string> labels;double cut_margin=0.015;
    std::unique_ptr<hailort::VDevice> device;
    std::shared_ptr<hailort::InferModel> model;
    // Network input taken from the HEF (packed NV12 tensor is height/2 x width x 3): 640x640 for the
    // deployed models, 1280x736 for a single full-scale pass over a 16:9 frame.
    int network_w=0,network_h=0;
    // Accelerator configuration/bindings are destroyed before their owned memory.
    DmaImage source;
    std::unique_ptr<DspCrop> crop;
    std::unique_ptr<Memory> y,uv,output;
    hailort::ConfiguredInferModel configured;
    hailort::ConfiguredInferModel::Bindings bindings;
    bool faulted=false;
    Impl(const std::string& hef,const std::string& group_id,const std::string& target,double threshold,int sw,int sh,
         const std::vector<std::string>* multi_labels=nullptr,double cut=0.015)
        :group(group_id),label(target),class_id(target=="person"?0:67),
         multi(multi_labels!=nullptr),labels(multi_labels?*multi_labels:std::vector<std::string>{}),cut_margin(cut),source(sw,sh) {
        const bool label_ok=multi?labels.size()==80:(label=="person"||label=="cell phone");
        // Source up to the IMX678's native 3840x2160: the DMA copy per inference is then 12.4 MB.
        if(group.empty()||!label_ok||!std::isfinite(threshold)||threshold<.05||threshold>1||sw>3840||sh>2160||
           !std::isfinite(cut_margin)||cut_margin<0||cut_margin>.25)
            throw std::invalid_argument("invalid region detector configuration");
        hailo_vdevice_params_t params{};check(hailo_init_vdevice_params(&params));
        params.group_id=group.c_str();params.multi_process_service=false;
        device=take(hailort::VDevice::create(params));model=take(device->create_infer_model(hef));
        auto in=take(model->input());auto out=take(model->output());const auto shape=in.shape();
        if(in.format().order!=HAILO_FORMAT_ORDER_NV12||shape.features!=3||shape.width%32||(shape.height*2)%32||
           shape.width<320||shape.width>1920||shape.height*2<320||shape.height*2>1920||
           out.format().order!=HAILO_FORMAT_ORDER_HAILO_NMS_BY_CLASS)
            throw std::runtime_error("region detector needs an NV12 input (320..1920, multiples of 32) and NMS-by-class output");
        network_w=int(shape.width);network_h=int(shape.height)*2;
        const auto nms=take(out.get_nms_shape());
        if(nms.number_of_classes!=80||nms.max_bboxes_per_class!=100)
            throw std::runtime_error("region detector requires known COCO NMS layout");
        crop=std::make_unique<DspCrop>(network_w,network_h);
        y=std::make_unique<Memory>(size_t(network_w)*network_h);uv=std::make_unique<Memory>(size_t(network_w)*network_h/2);
        in.set_format_type(HAILO_FORMAT_TYPE_UINT8);out.set_format_type(HAILO_FORMAT_TYPE_FLOAT32);
        out.set_nms_score_threshold(float(threshold));model->set_batch_size(1);
        if(in.get_frame_size()!=y->size+uv->size)throw std::runtime_error("region detector input size mismatch");
        output=std::make_unique<Memory>(out.get_frame_size());
        configured=take(model->configure());
        check(configured.set_scheduler_threshold(1));check(configured.set_scheduler_timeout(std::chrono::milliseconds(10)));
        bindings=take(configured.create_bindings());
        hailo_pix_buffer_t pix{};pix.number_of_planes=2;pix.memory_type=HAILO_PIX_BUFFER_MEMORY_TYPE_USERPTR;
        pix.planes[0].bytes_used=y->size;pix.planes[0].plane_size=y->size;pix.planes[0].user_ptr=y->data;
        pix.planes[1].bytes_used=uv->size;pix.planes[1].plane_size=uv->size;pix.planes[1].user_ptr=uv->data;
        check(take(bindings.input()).set_pix_buffer(pix));
        check(take(bindings.output()).set_buffer(hailort::MemoryView(output->data,output->size)));
    }
};
RegionDetector::RegionDetector(const std::string& hef,const std::string& group,const std::string& label,double threshold,int sw,int sh)
    :impl_(std::make_unique<Impl>(hef,group,label,threshold,sw,sh)) {}
RegionDetector::RegionDetector(const std::string& hef,const std::string& group,const std::vector<std::string>& class_labels,double threshold,int sw,int sh,double cut_margin)
    :impl_(std::make_unique<Impl>(hef,group,std::string("person"),threshold,sw,sh,&class_labels,cut_margin)) {}
RegionDetector::~RegionDetector()=default;
RegionDetections RegionDetector::infer(const fresh::Image& image,const fresh::SearchRegion& region,bool audit) {
    return infer_impl(image,region,true,audit);
}
std::vector<RegionDetections> RegionDetector::infer_many(const fresh::Image& image,const std::vector<fresh::SearchRegion>& regions,bool audit) {
    if(regions.empty()||regions.size()>5)throw std::invalid_argument("invalid region batch");
    for(const auto& r:regions)if(!r.valid()||r.sequence!=regions.front().sequence||r.capture_ms!=regions.front().capture_ms||
        r.source_w!=image.width||r.source_h!=image.height)throw std::invalid_argument("mixed source region batch");
    std::vector<RegionDetections> out;
    for(const auto& r:regions)out.push_back(infer_impl(image,r,out.empty(),audit));
    return out;
}
int RegionDetector::network_width() const {return impl_->network_w;}
int RegionDetector::network_height() const {return impl_->network_h;}
RegionDetections RegionDetector::infer_impl(const fresh::Image& image,const fresh::SearchRegion& request,bool copy_source,bool audit) {
    auto& p=*impl_;if(p.faulted)throw std::runtime_error("region detector faulted; restart required");
    // The network size is the detector's, not the planner's: planners describe source crops and
    // the letterbox into this model's input is decided here (640x640 or 1280x736).
    auto region=request;region.network_w=p.network_w;region.network_h=p.network_h;
    if(!region.valid()||image.width!=region.source_w||image.height!=region.source_h)
        throw std::invalid_argument("region detector image/request mismatch");
    RegionDetections result;result.region=region;
    auto start=std::chrono::steady_clock::now();if(copy_source)p.source.copy_from(image);result.source_copy_ms=copy_source?elapsed(start):0;
    const auto& resized=p.crop->run(p.source.properties(),region);result.dsp_ms=p.crop->last_ms();
    start=std::chrono::steady_clock::now();
    {
        DmaImage::ReadAccess access(resized);const auto input=access.image();
        std::memcpy(p.y->data,input.y,p.y->size);std::memcpy(p.uv->data,input.uv,p.uv->size);
    }
    result.input_copy_ms=elapsed(start);start=std::chrono::steady_clock::now();
    // The NPU scheduler is shared with the full-view stream and OSNet. With the aerial
    // fine-tuned HEFs (denser NMS output) the crowded VisDrone clip 053 exceeded a 100 ms and
    // then a 300 ms wait, and each time the fault took the whole detector down ("restart
    // required"). One second never faults on a slow job; the frame simply arrives stale and
    // the tracker's freshness budget (500 ms) rejects it. Faulting is the worse failure.
    const auto status=p.configured.run(p.bindings,std::chrono::milliseconds(1000));
    if(status!=HAILO_SUCCESS) {p.faulted=true;p.configured.shutdown();check(status);}
    result.inference_ms=elapsed(start);
    const auto* values=static_cast<const float*>(p.output->data);const size_t limit=p.output->size/sizeof(float);
    size_t pos=0;
    try {
        for(int cls=0;cls<80;++cls) {
            if(pos>=limit||!std::isfinite(values[pos])||values[pos]<0||values[pos]>100||std::floor(values[pos])!=values[pos])
                throw std::runtime_error("invalid region NMS count");
            const size_t count=size_t(values[pos++]);
            if(pos+count*5>limit)throw std::runtime_error("region NMS overflow");
            for(size_t i=0;i<count;++i,pos+=5) {
                for(size_t k=0;k<5;++k)if(!std::isfinite(values[pos+k]))throw std::runtime_error("nonfinite region NMS output");
                if(values[pos+4]<0||values[pos+4]>1)throw std::runtime_error("invalid region NMS confidence");
                if(!p.multi&&cls!=p.class_id)continue;
                fresh::Box box{values[pos+1],values[pos],values[pos+3]-values[pos+1],values[pos+2]-values[pos]};
                if(box.w<=0||box.h<=0)continue;
                const std::string& out_label=p.multi?p.labels[size_t(cls)]:p.label;
                const bool cut=region.cuts_object(box,p.cut_margin);
                if(audit)result.audit.push_back({box,{region.to_frame(box),out_label,values[pos+4],{},{}},
                                                cut,region.cuts_object_relative(box)});
                if(cut){++result.cut_boxes;continue;}
                result.detections.push_back({region.to_frame(box),out_label,values[pos+4],{}, {}});
            }
        }
    }catch(...) {p.faulted=true;throw;}
    return result;
}
}
