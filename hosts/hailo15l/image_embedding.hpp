#pragma once
#include "garuda_tracking/vision.hpp"
#include <cstdint>
#include <memory>

namespace garuda::h15l {
struct ImageEmbeddingResult {
    fresh::Embedding embedding;
    fresh::Box crop;
    double crop_ms=0,inference_ms=0,raw_norm=0;
};
// Bounded NV12 -> 512D Hailo adapter. Model shape must match the explicit physical
// image dimensions. Defaults preserve the OSNet camera path and its 100ms timeout.
class ImageEmbedding {
public:
    ImageEmbedding(const std::string& hef,const std::string& model_id,const std::string& group,
                   int width=128,int height=256,uint32_t timeout_ms=100);
    ~ImageEmbedding();
    ImageEmbeddingResult infer(const fresh::Image&,const fresh::Box&);
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
