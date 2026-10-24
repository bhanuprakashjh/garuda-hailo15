#pragma once
#include "vision.hpp"

namespace garuda::fresh {
// Value object owned by one inference request. Never remap an old result with a new crop.
struct SearchRegion {
    uint64_t sequence=0;
    double capture_ms=0;
    int source_w=0,source_h=0,x=0,y=0,w=0,h=0,network_w=640,network_h=640;
    bool full_frame=true;
    bool valid() const;
    FrameGeometry geometry() const;
    Box to_frame(const Box& network_box) const;
    Box to_network(const Box& frame_box) const;
    bool cuts_object(const Box& network_box,double margin=.015) const;
    // Bench candidate only: margin scales with object extent, bounded by the
    // existing ROI floor and tile ceiling. Not proof an object is untruncated.
    bool cuts_object_relative(const Box& network_box) const;
};
struct SearchConfig {
    double full_frame_period_ms=200,max_target_age_ms=150,context=2.5;
    int minimum_side=320;
    bool allow_short_coasting=false; // search hypothesis only; never changes target/control validity
    bool predict_phone=false;
};
class SearchPlanner {
public:
    explicit SearchPlanner(SearchConfig cfg={});
    SearchRegion next(uint64_t sequence,double capture_ms,int source_w,int source_h,const Target& previous);
    void reset() {last_full_ms_=-1;last_capture_ms_=-1;epoch_=0;}
private:
    SearchConfig cfg_;
    double last_full_ms_=-1,last_capture_ms_=-1;
    uint64_t epoch_=0;
};

// Additional ROI inference only: the host still runs a full-frame detector on
// every exposure. Short ROI-only continuation cannot renew full-frame evidence.
class RoiAssist {
public:
    // context: crop side as a multiple of the target's extent (the planner's 640 px floor still
    // applies). 2.5 is the paired-copy default; a native-pixel planner wants more, because at
    // sensor scale 2.5x makes the target 40 % of the crop, where the COCO detector scores it lower
    // than at the ~14 % the paired copy shows (desk phone A/B 2026-09-15).
    explicit RoiAssist(double max_age_ms=100,double primary_window_ms=400,double context=2.5,bool predict_phone=false);
    void observe_global(const Target&,double capture_ms);
    const std::string& reason() const {return reason_;}
    std::optional<SearchRegion> plan(const Frame& full,const Target& previous,int width,int height);
    // Only the request's same-frame, selected-class boxes are accepted: new ones are
    // added, and a local box replaces an overlapping full-frame box when it is more
    // confident. Returns the number of boxes added or upgraded; no tracker state changes.
    size_t merge(Frame&,const SearchRegion&,const std::vector<Detection>& local,size_t limit) const;
    void reset();
private:
    double max_age_ms_=100,primary_window_ms_=400;
    std::string reason_="not_requested";
    SearchPlanner planner_{SearchConfig{200,200,2.5,640,true}};
    uint64_t epoch_=0,sequence_=0,request_sequence_=0;
    double capture_ms_=-1,last_primary_ms_=-1,last_request_ms_=-1;
    std::string label_;
    std::optional<SearchRegion> request_;
};
// Causal acquisition/ROI handover, shared by live code and replay. Search
// scheduling never changes tracker validity or permits predicted motion.
class FollowSchedule {
public:
    // global_period_ms: bounded independent corner refresh while a small target is locked.
    // local_gap_ms: the two verified local (ROI) passes that retire the corners must fall
    // within this window. 500 ms suits the desk's 20 fps single-pass cadence; a tiled aerial
    // search at ~250 ms per processed frame with a periodic full-only plan in between never
    // gets two ROI passes inside 500 ms, so the corners never retire and the age stays high
    // (VisDrone 115, 2026-09-14: ROI verified 11 of 12 times, handover 0 of 45 frames).
    explicit FollowSchedule(double global_period_ms=800,double local_gap_ms=500,double short_miss_ms=0);
    const std::string& reason() const {return reason_;}
    bool global_required(const Target&,double capture_ms);
    void observe(bool global,bool local,const Target&,double capture_ms);
    void reset(){epoch_=0;last_global_=last_local_=last_valid_=-1;local_hits_=0;reason_="reset";}
private:
    double global_period_ms_,local_gap_ms_;
    double short_miss_ms_=0,last_valid_=-1;
    std::string reason_="initial";
    uint64_t epoch_=0;
    double last_global_=-1,last_local_=-1;
    unsigned local_hits_=0;
};
}
