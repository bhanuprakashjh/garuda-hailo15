#pragma once
#include "garuda_tracking/search_region.hpp"
#include <hailo/hailodsp.h>
#include <memory>

namespace garuda::h15l {
// Small owned DMA images. No SDK C++ class-layout dependency or global pool ownership.
class DmaImage {
public:
    DmaImage(int width,int height);
    ~DmaImage();
    DmaImage(const DmaImage&)=delete;DmaImage& operator=(const DmaImage&)=delete;
    const dsp_image_properties_t& properties() const;
    void copy_from(const fresh::Image&);
    void copy_to(std::vector<uint8_t>& packed) const;
    class ReadAccess {
    public:
        explicit ReadAccess(const DmaImage&);
        ~ReadAccess();
        ReadAccess(const ReadAccess&)=delete;ReadAccess& operator=(const ReadAccess&)=delete;
        fresh::Image image() const;
    private:
        const DmaImage& owner_;
    };
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
class DspCrop {
public:
    // The letterboxed output is the detector's network input (640x640 by default; a 1280x736
    // model holds a 16:9 frame at full 720p scale). Regions must carry the same network size.
    explicit DspCrop(int network_w=640,int network_h=640);
    ~DspCrop();
    DspCrop(const DspCrop&)=delete;DspCrop& operator=(const DspCrop&)=delete;
    // Borrowed output remains valid until the next run or destruction; callers finish inference first.
    const DmaImage& run(const dsp_image_properties_t& source,const fresh::SearchRegion& region);
    double last_ms() const {return last_ms_;}
    int network_width() const {return network_w_;}
    int network_height() const {return network_h_;}
private:
    dsp_device device_=nullptr;
    int network_w_,network_h_;
    DmaImage output_;
    double last_ms_=0;
};
}
