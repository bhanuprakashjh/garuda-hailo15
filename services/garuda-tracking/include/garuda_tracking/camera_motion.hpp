#pragma once
#include "vision.hpp"
#include <memory>

namespace garuda::fresh {
struct MotionFit {
    Motion motion;
    size_t features=0,matches=0,inliers=0,support_cells=0;
    double support_width=0,support_height=0;
    double residual_px=0,elapsed_ms=0;
    double extraction_ms=0,matching_ms=0,fit_ms=0;
    std::string reason="initial_frame";
};
// Optional OpenCV plugin. Background ORB descriptors with mutual ratio matching
// and robust similarity fit on a 16:9 full-FOV image.
// No identity, range, VIO or camera-pose output.
class CameraMotionEstimator {
public:
    // Construct at process startup: caps OpenCV's process-wide thread pool to one.
    CameraMotionEstimator();
    ~CameraMotionEstimator();
    MotionFit update(const Image&,const std::vector<Detection>&);
    void reset();
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
