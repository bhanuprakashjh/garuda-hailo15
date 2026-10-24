#pragma once
#include "vision.hpp"
#include <memory>

namespace garuda::fresh {
struct VisualTargetResult {
    std::optional<VisualMeasurement> measurement;
    std::string reason="uninitialized";
    double score=0, margin=0, elapsed_ms=0;
};
// Selected-object localizer, independent of YOLO. OpenCV core/imgproc only.
// Templates are learned ONLY from explicit detector verification, never from
// a visual-only update. Bounded horizon; no re-identification or track births.
class VisualTargetTracker {
public:
    VisualTargetTracker();
    ~VisualTargetTracker();
    VisualTargetTracker(const VisualTargetTracker&)=delete;
    VisualTargetTracker& operator=(const VisualTargetTracker&)=delete;
    bool seed(const Image&, const Box&, uint64_t sequence, double capture_ms,
              uint64_t lock_id, uint64_t epoch);
    VisualTargetResult locate(const Image&, uint64_t sequence, double capture_ms,
                              uint64_t lock_id, uint64_t epoch);
    void reset();
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
