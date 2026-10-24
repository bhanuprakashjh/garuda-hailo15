#include "garuda_tracking/tiling.hpp"
#include <algorithm>

namespace garuda::fresh {
namespace {
int even_floor(double v) { int i = int(v); return i & ~1; }
}

std::vector<SearchRegion> five_tile_layout(uint64_t sequence, double capture_ms,
                                           int source_w, int source_h) {
    std::vector<SearchRegion> out;
    if (source_w < 2 || source_h < 2) return out;
    struct Frac { double x, y, w, h; bool full; };
    // Four corners at 0.6x0.6 with 0.4 stride (20% overlap), then the full view.
    static const Frac fracs[5] = {
        {0.0, 0.0, 0.6, 0.6, false}, {0.4, 0.0, 0.6, 0.6, false},
        {0.0, 0.4, 0.6, 0.6, false}, {0.4, 0.4, 0.6, 0.6, false},
        {0.0, 0.0, 1.0, 1.0, true}};
    for (const auto& f : fracs) {
        int x = even_floor(f.x * source_w);
        int y = even_floor(f.y * source_h);
        int w = even_floor(f.w * source_w);
        int h = even_floor(f.h * source_h);
        if (x + w > source_w) w = even_floor(source_w - x);
        if (y + h > source_h) h = even_floor(source_h - y);
        if (w < 2 || h < 2) continue;
        SearchRegion r;
        r.sequence = sequence; r.capture_ms = capture_ms;
        r.source_w = source_w; r.source_h = source_h;
        r.x = x; r.y = y; r.w = w; r.h = h;
        r.network_w = 640; r.network_h = 640; r.full_frame = f.full;
        out.push_back(r);
    }
    return out;
}

double intersection_over_min(const Box& a, const Box& b) {
    const double iw = std::max(0.0, std::min(a.x + a.w, b.x + b.w) - std::max(a.x, b.x));
    const double ih = std::max(0.0, std::min(a.y + a.h, b.y + b.h) - std::max(a.y, b.y));
    const double inter = iw * ih;
    const double smaller = std::min(a.w * a.h, b.w * b.h);
    return smaller > 0 ? inter / smaller : 0.0;
}

std::vector<Detection> aggregate_tile_detections(std::vector<Detection> detections,
                                                 double iou_threshold, double containment_threshold) {
    std::stable_sort(detections.begin(), detections.end(),
                     [](const Detection& a, const Detection& b) { return a.confidence > b.confidence; });
    std::vector<Detection> kept;
    for (auto& d : detections) {
        // Containment alone is not evidence of duplication between two objects
        // seen together. A full-view body outranks a contained cross-crop fragment.
        const auto cross_fragment=[&](const Detection& large,const Detection& small) {
            return large.region_full_frame&&!small.region_full_frame&&small.region_id>=0&&
                large.label==small.label&&large.box.w*large.box.h>2*small.box.w*small.box.h&&
                intersection_over_min(large.box,small.box)>containment_threshold;
        };
        if(std::any_of(kept.begin(),kept.end(),[&](const Detection& k){return cross_fragment(k,d);}))continue;
        kept.erase(std::remove_if(kept.begin(),kept.end(),[&](const Detection& k){return cross_fragment(d,k);}),kept.end());
        const bool duplicate = std::any_of(kept.begin(), kept.end(), [&](const Detection& k) {
            // Preserve two detections from the same known region. Its own NMS
            // already ran, and they may be genuinely overlapping people.
            if(k.region_id>=0&&k.region_id==d.region_id)return false;
            return k.label == d.label && iou(k.box, d.box) > iou_threshold;
        });
        if (!duplicate) kept.push_back(std::move(d));
    }
    return kept;
}
}
