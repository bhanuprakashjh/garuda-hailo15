#pragma once
#include "tracker.hpp"
#include <cstddef>

namespace garuda::fresh {
// Borrowed NV12 planes; buffers never escape the callback. Geometry must be full-FOV (use FrameGeometry::content after letterboxing).
struct Image {
    const uint8_t* y=nullptr;
    const uint8_t* uv=nullptr;
    int width=0, height=0, y_stride=0, uv_stride=0;
    size_t y_bytes=0, uv_bytes=0;
    bool valid() const;
};
struct FrameGeometry {
    int input_w=0,input_h=0,content_x=0,content_y=0,content_w=0,content_h=0;
    static FrameGeometry make(int frame_w,int frame_h,int input_w,int input_h,bool letterbox);
    Box to_frame(const Box& detector_box) const;
    Image content(const Image& input) const;
    // Verify uniform neutral padding in an actual letterboxed NV12 buffer.
    bool matches_layout(const Image& input) const;
};
std::optional<Appearance> describe(const Image&, const Box&);
// Opt-in scheduling only: a selected car uses histograms, not person OSNet.
// Pending person selection or embedding-based MOT always restores the budget.
bool defer_person_embeddings_for_car(const Target&, const Config&, bool enabled);
// CPU bench path for learned person crops. Bilinear NV12, chroma-aligned source bounds.
// Returns the actual source region so preprocessing can be recorded exactly.
Box resize_nv12_crop(const Image&,const Box&,int output_w,int output_h,std::vector<uint8_t>& packed);
// Exact luma samples consumed by MotionEstimator after a 640x360 bilinear resize.
// Avoid producing the unused intermediate pixels/chroma. Returned NV12 is 160x90.
void motion_samples(const Image&,std::vector<uint8_t>& packed);
// Small background-only block matcher. Translation only; not VIO or a rotation estimator.
class MotionEstimator {
public:
    Motion update(const Image&, const std::vector<Detection>&);
    void reset() { previous_.clear(); previous_boxes_.clear(); }
private:
    std::vector<uint8_t> previous_;
    std::vector<Box> previous_boxes_;
};

} // namespace garuda::fresh
