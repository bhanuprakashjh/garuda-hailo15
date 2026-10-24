#include "image_embedding.hpp"
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
using namespace hailort;
void check(hailo_status status) {
    if(status!=HAILO_SUCCESS)throw std::runtime_error("embedding Hailo status "+std::to_string(status));
}
template<class T>T take(Expected<T>&& result) {
    if(!result)throw std::runtime_error("embedding Hailo status "+std::to_string(result.status()));
    return result.release();
}
size_t checked_pixels(int width,int height) {
    if(width<2||height<2||width>512||height>512||width%2||height%2)
        throw std::invalid_argument("embedding NV12 dimensions must be even and within 2..512");
    return size_t(width)*height;
}
struct Memory {
    void* data;size_t size,allocated;
    explicit Memory(size_t bytes):size(bytes) {
        const auto page=size_t(sysconf(_SC_PAGESIZE));allocated=(bytes+page-1)/page*page;
        data=mmap(nullptr,allocated,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        if(data==MAP_FAILED)throw std::runtime_error("embedding mmap failed");
    }
    ~Memory(){munmap(data,allocated);}
    Memory(const Memory&)=delete;Memory& operator=(const Memory&)=delete;
};
double ms_since(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
}
}
struct ImageEmbedding::Impl {
    std::string model_id,group;
    std::unique_ptr<hailort::VDevice> device;
    std::shared_ptr<hailort::InferModel> model;
    // Buffers precede bindings/configuration so they outlive all accelerator references.
    int width,height;
    uint32_t timeout_ms;
    Memory y,uv,out;
    hailort::ConfiguredInferModel configured;
    hailort::ConfiguredInferModel::Bindings bindings;
    std::vector<uint8_t> crop;
    bool failed=false;
    Impl(const std::string& hef,const std::string& id,const std::string& group_id,int w,int h,uint32_t timeout)
        :model_id(id),group(group_id),width(w),height(h),timeout_ms(timeout),
         y(checked_pixels(w,h)),uv(checked_pixels(w,h)/2),out(512*sizeof(float)) {
        if(timeout_ms<1||timeout_ms>1000)throw std::invalid_argument("embedding timeout must be 1..1000 ms");
        if(id.empty()||id.size()>200||group.empty())throw std::invalid_argument("embedding provenance/group required");
        hailo_vdevice_params_t params{};check(hailo_init_vdevice_params(&params));
        // Analytics 1.12 opens a local VDevice by default. Both models must use the
        // same local group; mixing a service device and a local device cannot share the NPU.
        params.group_id=group.c_str();params.multi_process_service=false;
        device=take(hailort::VDevice::create(params));model=take(device->create_infer_model(hef));
        auto input=take(model->input());auto output=take(model->output());
        const auto shape=input.shape(),oshape=output.shape();
        // NV12 stream dimensions encode half the physical image height.
        if(input.format().order!=HAILO_FORMAT_ORDER_NV12||shape.height!=uint32_t(height/2)||shape.width!=uint32_t(width)||shape.features!=3||
           size_t(oshape.height)*oshape.width*oshape.features!=512)
            throw std::runtime_error("unexpected NV12 embedding dimensions or non-512D output");
        input.set_format_type(HAILO_FORMAT_TYPE_UINT8);output.set_format_type(HAILO_FORMAT_TYPE_FLOAT32);
        if(input.get_frame_size()!=y.size+uv.size||output.get_frame_size()!=out.size)
            throw std::runtime_error("unexpected embedding buffer size");
        model->set_batch_size(1);configured=take(model->configure());
        check(configured.set_scheduler_threshold(1));check(configured.set_scheduler_timeout(std::chrono::milliseconds(10)));
        bindings=take(configured.create_bindings());
        hailo_pix_buffer_t pix{};pix.number_of_planes=2;pix.memory_type=HAILO_PIX_BUFFER_MEMORY_TYPE_USERPTR;
        pix.planes[0].bytes_used=y.size;pix.planes[0].plane_size=y.size;pix.planes[0].user_ptr=y.data;
        pix.planes[1].bytes_used=uv.size;pix.planes[1].plane_size=uv.size;pix.planes[1].user_ptr=uv.data;
        check(take(bindings.input()).set_pix_buffer(pix));
        check(take(bindings.output()).set_buffer(hailort::MemoryView(out.data,out.size)));
    }
};
ImageEmbedding::ImageEmbedding(const std::string& hef,const std::string& id,const std::string& group,
                               int width,int height,uint32_t timeout_ms)
    :impl_(std::make_unique<Impl>(hef,id,group,width,height,timeout_ms)) {}
ImageEmbedding::~ImageEmbedding()=default;
ImageEmbeddingResult ImageEmbedding::infer(const fresh::Image& image,const fresh::Box& box) {
    auto& p=*impl_;ImageEmbeddingResult result;
    if(p.failed)throw std::runtime_error("embedding runtime faulted; restart required");
    auto start=std::chrono::steady_clock::now();
    result.crop=fresh::resize_nv12_crop(image,box,p.width,p.height,p.crop);
    std::memcpy(p.y.data,p.crop.data(),p.y.size);std::memcpy(p.uv.data,p.crop.data()+p.y.size,p.uv.size);
    result.crop_ms=ms_since(start);start=std::chrono::steady_clock::now();
    const auto status=p.configured.run(p.bindings,std::chrono::milliseconds(p.timeout_ms));
    if(status!=HAILO_SUCCESS) {
        p.failed=true;p.configured.shutdown();check(status); // never reuse a possibly in-flight buffer
    }
    result.inference_ms=ms_since(start);
    result.embedding.model=p.model_id+"/nv12-bilinear-chroma-align-v1";
    const auto* values=static_cast<const float*>(p.out.data);
    double norm=0;for(size_t i=0;i<512;++i) {result.embedding.values[i]=values[i];norm+=double(values[i])*values[i];}
    result.raw_norm=std::sqrt(norm);
    if(!fresh::normalize_embedding(result.embedding))throw std::runtime_error("invalid learned embedding");
    return result;
}
}
