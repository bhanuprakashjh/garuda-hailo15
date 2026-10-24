#pragma once
#include "garuda_tracking/search_region.hpp"
#include <memory>
#include <string>
#include <vector>

namespace garuda::h15l {
struct RegionAudit {
    fresh::Box network_box;
    fresh::Detection detection;
    bool fixed_cut=false,relative_cut=false;
};
struct RegionDetections {
    fresh::SearchRegion region;
    std::vector<fresh::Detection> detections;
    double source_copy_ms=0,dsp_ms=0,input_copy_ms=0,inference_ms=0;
    size_t cut_boxes=0;
    std::vector<RegionAudit> audit; // populated only when explicitly requested
};
// Bench-only second detector, sharing the camera's local VDevice group. Every
// result owns its exposure/region mapping; no borrowed source pixels survive infer.
class RegionDetector {
public:
    // Single-class: keep only `label` (person or cell phone) — the ROI-assist path.
    RegionDetector(const std::string& hef,const std::string& group,const std::string& label,
                   double threshold,int source_w=1280,int source_h=720);
    // Multi-class: keep every class, labelled by class_labels[class_id] (size 80,
    // 0-indexed COCO) — the tiling detection path. cut_margin drops boxes within
    // that fraction of an interior tile border (stock aggregator uses ~0.1) so an
    // object straddling the tile overlap is kept only by the tile that contains it.
    RegionDetector(const std::string& hef,const std::string& group,
                   const std::vector<std::string>& class_labels,
                   double threshold,int source_w=1280,int source_h=720,double cut_margin=0.015);
    ~RegionDetector();
    // Network input taken from the HEF; requests are letterboxed into it whatever network size
    // the planner wrote (640x640 for the deployed models, 1280x736 for a full-scale single pass).
    int network_width() const;
    int network_height() const;
    RegionDetections infer(const fresh::Image&,const fresh::SearchRegion&,bool audit=false);
    std::vector<RegionDetections> infer_many(const fresh::Image&,const std::vector<fresh::SearchRegion>&,bool audit=false);
private:
    RegionDetections infer_impl(const fresh::Image&,const fresh::SearchRegion&,bool copy_source,bool audit);
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
