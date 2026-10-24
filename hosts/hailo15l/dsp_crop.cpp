#include "dsp_crop.hpp"
#include <linux/dma-heap.h>
#include <linux/dma-buf.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <stdexcept>

namespace garuda::h15l {
namespace {
int checked_ioctl(int fd,unsigned long request,void* arg) {
    int rc;do {rc=ioctl(fd,request,arg);}while(rc<0&&errno==EINTR);return rc;
}
struct Plane {
    int fd=-1;void* data=MAP_FAILED;size_t size=0;
    explicit Plane(size_t bytes):size(bytes) {
        int heap=open("/dev/dma_heap/hailo_media_buf,cma",O_RDWR|O_CLOEXEC);
        if(heap<0)throw std::runtime_error("open media DMA heap failed");
        dma_heap_allocation_data allocation{};allocation.len=bytes;allocation.fd_flags=O_RDWR|O_CLOEXEC;
        int rc=checked_ioctl(heap,DMA_HEAP_IOCTL_ALLOC,&allocation);close(heap);
        if(rc<0)throw std::runtime_error("DMA crop buffer allocation failed");
        fd=int(allocation.fd);data=mmap(nullptr,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
        if(data==MAP_FAILED){close(fd);fd=-1;throw std::runtime_error("map DMA crop buffer failed");}
    }
    ~Plane(){if(data!=MAP_FAILED)munmap(data,size);if(fd>=0)close(fd);}
    void sync(uint64_t flags) const {
        dma_buf_sync arg{};arg.flags=flags;
        if(checked_ioctl(fd,DMA_BUF_IOCTL_SYNC,&arg)<0)throw std::runtime_error("DMA crop cache synchronization failed");
    }
};
void dsp_check(dsp_status status) {
    if(status!=DSP_SUCCESS)throw std::runtime_error("DSP crop status "+std::to_string(status));
}
}
struct DmaImage::Impl {
    int width,height;
    std::unique_ptr<Plane> y,uv;
    dsp_data_plane_t planes[2]{};
    dsp_image_properties_t properties{};
    Impl(int w,int h):width(w),height(h) {
        if(w<2||h<2||w>4096||h>2160||w%2||h%2)throw std::invalid_argument("invalid DMA image dimensions");
        y=std::make_unique<Plane>(size_t(w)*h);uv=std::make_unique<Plane>(size_t(w)*h/2);
        planes[0].fd=y->fd;planes[0].bytesperline=w;planes[0].bytesused=y->size;
        planes[1].fd=uv->fd;planes[1].bytesperline=w;planes[1].bytesused=uv->size;
        properties={size_t(w),size_t(h),planes,2,DSP_IMAGE_FORMAT_NV12,DSP_MEMORY_TYPE_DMABUF};
    }
    void start(uint64_t flags) const {
        y->sync(flags|DMA_BUF_SYNC_START);
        try {uv->sync(flags|DMA_BUF_SYNC_START);}catch(...) {y->sync(flags|DMA_BUF_SYNC_END);throw;}
    }
    void end(uint64_t flags) const {y->sync(flags|DMA_BUF_SYNC_END);uv->sync(flags|DMA_BUF_SYNC_END);}
    fresh::Image image() const {
        return {static_cast<const uint8_t*>(y->data),static_cast<const uint8_t*>(uv->data),
            width,height,width,width,y->size,uv->size};
    }
};
DmaImage::DmaImage(int w,int h):impl_(std::make_unique<Impl>(w,h)) {}
DmaImage::~DmaImage()=default;
const dsp_image_properties_t& DmaImage::properties() const {return impl_->properties;}
DmaImage::ReadAccess::ReadAccess(const DmaImage& owner):owner_(owner) {owner_.impl_->start(DMA_BUF_SYNC_READ);}
DmaImage::ReadAccess::~ReadAccess() {try{owner_.impl_->end(DMA_BUF_SYNC_READ);}catch(...) {}}
fresh::Image DmaImage::ReadAccess::image() const {return owner_.impl_->image();}
void DmaImage::copy_from(const fresh::Image& image) {
    auto& p=*impl_;
    if(!image.valid()||image.width!=p.width||image.height!=p.height)throw std::invalid_argument("DMA source geometry mismatch");
    p.start(DMA_BUF_SYNC_WRITE);
    for(int row=0;row<p.height;++row)std::memcpy(static_cast<uint8_t*>(p.y->data)+size_t(row)*p.width,image.y+size_t(row)*image.y_stride,p.width);
    for(int row=0;row<p.height/2;++row)std::memcpy(static_cast<uint8_t*>(p.uv->data)+size_t(row)*p.width,image.uv+size_t(row)*image.uv_stride,p.width);
    p.end(DMA_BUF_SYNC_WRITE);
}
void DmaImage::copy_to(std::vector<uint8_t>& packed) const {
    auto& p=*impl_;packed.resize(p.y->size+p.uv->size);ReadAccess access(*this);
    std::memcpy(packed.data(),p.y->data,p.y->size);std::memcpy(packed.data()+p.y->size,p.uv->data,p.uv->size);
}
DspCrop::DspCrop(int network_w,int network_h):network_w_(network_w),network_h_(network_h),output_(network_w,network_h) {
    if(network_w<320||network_h<320||network_w>1920||network_h>1920||network_w%32||network_h%32)
        throw std::invalid_argument("network input must be multiples of 32 between 320 and 1920");
    dsp_check(dsp_create_device(&device_));
    const auto status=dsp_set_priority(device_,100);
    if(status!=DSP_SUCCESS){dsp_release_device(device_);device_=nullptr;dsp_check(status);}
}
DspCrop::~DspCrop() {if(device_)dsp_release_device(device_);}
const DmaImage& DspCrop::run(const dsp_image_properties_t& source,const fresh::SearchRegion& region) {
    if(!region.valid()||region.network_w!=network_w_||region.network_h!=network_h_||
       source.width!=size_t(region.source_w)||source.height!=size_t(region.source_h)||
       source.format!=DSP_IMAGE_FORMAT_NV12||source.planes_count!=2||!source.planes||
       source.memory!=DSP_MEMORY_TYPE_DMABUF)throw std::invalid_argument("DSP search input/region mismatch");
    for(size_t i=0;i<2;++i)if(source.planes[i].fd<0||source.planes[i].bytesperline<source.width||
        source.planes[i].bytesused<source.planes[i].bytesperline*(source.height/(i?2:1)-1)+source.width)
        throw std::invalid_argument("invalid DSP source plane");
    const dsp_roi_t roi{size_t(region.x),size_t(region.y),size_t(region.x+region.w),size_t(region.y+region.h)};
    const dsp_resize_params_t resize{&source,&output_.properties(),INTERPOLATION_TYPE_BILINEAR};
    dsp_letterbox_properties_t letterbox{};letterbox.alignment=DSP_LETTERBOX_MIDDLE;
    letterbox.color.y=0;letterbox.color.u=128;letterbox.color.v=128;
    const auto start=std::chrono::steady_clock::now();
    dsp_check(dsp_crop_and_resize_letterbox(device_,&resize,&roi,&letterbox));
    last_ms_=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    return output_;
}
}
