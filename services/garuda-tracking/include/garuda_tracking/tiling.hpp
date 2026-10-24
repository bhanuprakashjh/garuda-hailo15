#pragma once
#include "search_region.hpp"
#include "tracker.hpp"
#include <vector>

namespace garuda::fresh {
// Stock five-tile layout for a high-resolution source: four 60%x60% corner
// crops (20% overlap) plus one full view, each destined for a 640x640 network
// input. Pixel offsets/sizes are even (DSP requirement); the full tile is
// flagged full_frame. Corner tiles recover small objects the downscaled full
// view loses; the overlap is resolved by aggregate_tile_detections.
std::vector<SearchRegion> five_tile_layout(uint64_t sequence, double capture_ms,
                                           int source_w, int source_h);

// Intersection over the smaller box's area — catches a small box largely
// contained in a larger same-class box, which cross-tile scale differences
// produce and plain IoU misses.
double intersection_over_min(const Box& a, const Box& b);

// Class-aware suppression across tiles: keep the highest-confidence detection
// of each cluster, dropping any lower-confidence same-label box that either
// overlaps a kept box (IoU > iou_threshold) or is largely contained in it
// (intersection-over-min > containment_threshold). Input need not be sorted.
std::vector<Detection> aggregate_tile_detections(std::vector<Detection> detections,
                                                 double iou_threshold = 0.3,
                                                 double containment_threshold = 0.7);
}
