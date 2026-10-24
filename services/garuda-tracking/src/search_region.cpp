#include "garuda_tracking/search_region.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace garuda::fresh {
bool SearchRegion::valid() const {
    return sequence&&std::isfinite(capture_ms)&&capture_ms>=0&&source_w>=2&&source_h>=2&&
        source_w<=8192&&source_h<=8192&&source_w%2==0&&source_h%2==0&&x>=0&&y>=0&&w>=2&&h>=2&&
        x%2==0&&y%2==0&&w%2==0&&h%2==0&&x<=source_w-w&&y<=source_h-h&&
        network_w>=2&&network_h>=2&&network_w<=8192&&network_h<=8192&&network_w%2==0&&network_h%2==0&&
        // Local ROIs may be rectangular: geometry() letterboxes any aspect into the
        // network square, and to_frame/cuts_object account for the padding. The ROI
        // search planner still chooses square crops; tiling uses 16:9 tiles.
        (full_frame?(x==0&&y==0&&w==source_w&&h==source_h):true);
}
FrameGeometry SearchRegion::geometry() const {
    if(!valid())throw std::invalid_argument("invalid inference search region");
    return FrameGeometry::make(w,h,network_w,network_h,true);
}
Box SearchRegion::to_frame(const Box& b) const {
    const auto local=geometry().to_frame(b);
    return {(x+local.x*w)/source_w,(y+local.y*h)/source_h,local.w*w/source_w,local.h*h/source_h};
}
Box SearchRegion::to_network(const Box& b) const {
    const auto g=geometry();
    return {((b.x*source_w-x)/w*g.content_w+g.content_x)/network_w,
            ((b.y*source_h-y)/h*g.content_h+g.content_y)/network_h,
            b.w*source_w/w*g.content_w/network_w,b.h*source_h/h*g.content_h/network_h};
}
bool SearchRegion::cuts_object(const Box& b,double margin) const {
    if(!valid()||!std::isfinite(margin)||margin<0||margin>.25)return true;
    if(full_frame)return false;
    const auto g=geometry();
    const double left=(b.x*network_w-g.content_x)/g.content_w;
    const double top=(b.y*network_h-g.content_y)/g.content_h;
    const double right=((b.x+b.w)*network_w-g.content_x)/g.content_w;
    const double bottom=((b.y+b.h)*network_h-g.content_y)/g.content_h;
    return (x>0&&left<=margin)||(y>0&&top<=margin)||
        (x+w<source_w&&right>=1-margin)||(y+h<source_h&&bottom>=1-margin);
}
bool SearchRegion::cuts_object_relative(const Box& b) const {
    if(!valid()||!std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.w)||!std::isfinite(b.h)||
       b.w<=0||b.h<=0)return true;
    if(full_frame)return false;
    const auto g=geometry();
    const double left=(b.x*network_w-g.content_x)/g.content_w;
    const double top=(b.y*network_h-g.content_y)/g.content_h;
    const double bw=b.w*network_w/g.content_w,bh=b.h*network_h/g.content_h;
    const double mx=std::clamp(.1*bw,.015,.08),my=std::clamp(.1*bh,.015,.08);
    return (x>0&&left<=mx)||(y>0&&top<=my)||
        (x+w<source_w&&left+bw>=1-mx)||(y+h<source_h&&top+bh>=1-my);
}
SearchPlanner::SearchPlanner(SearchConfig cfg):cfg_(cfg) {
    if(!std::isfinite(cfg.full_frame_period_ms)||cfg.full_frame_period_ms<=0||cfg.full_frame_period_ms>1000||
       !std::isfinite(cfg.max_target_age_ms)||cfg.max_target_age_ms<=0||cfg.max_target_age_ms>1000||
       !std::isfinite(cfg.context)||cfg.context<1.5||cfg.context>8||cfg.minimum_side<64||
       cfg.minimum_side>4096||cfg.minimum_side%2)throw std::invalid_argument("invalid search configuration");
}
SearchRegion SearchPlanner::next(uint64_t seq,double capture,int sw,int sh,const Target& t) {
    SearchRegion r{seq,capture,sw,sh,0,0,sw,sh};
    if(!r.valid())throw std::invalid_argument("invalid search frame");
    const bool reset_required=capture<=last_capture_ms_||epoch_!=t.epoch;
    last_capture_ms_=capture;epoch_=t.epoch;
    const bool searching_coast=cfg_.allow_short_coasting&&t.state=="coasting"&&
        (t.reason=="missing_or_stale_observation"||t.reason=="low_confidence")&&t.position_std<=.12;
    bool local=!reset_required&&last_full_ms_>=0&&capture-last_full_ms_<cfg_.full_frame_period_ms&&
        t.box&&t.id&&((t.observation_valid&&t.control_valid&&t.state=="tracking")||searching_coast)&&
        std::isfinite(t.observation_age_ms)&&t.observation_age_ms>=0&&t.observation_age_ms<=cfg_.max_target_age_ms;
    if(local) {
        auto b=*t.box;
        double sweep_x=0,sweep_y=0;
        if(cfg_.predict_phone&&t.label=="cell phone"&&t.search_measurement&&
           std::isfinite(t.search_capture_ms)&&t.search_capture_ms>=0&&
           capture>=t.search_capture_ms&&capture-t.search_capture_ms<=250&&
           std::isfinite(t.search_vx)&&std::isfinite(t.search_vy)) {
            b=*t.search_measurement;
            const double dt=(capture-t.search_capture_ms)/1000.;
            // Cover both the measurement and bounded projection. A reversal must
            // not move the entire crop away from the last trustworthy position.
            sweep_x=std::clamp(t.search_vx*dt,-.15,.15);
            sweep_y=std::clamp(t.search_vy*dt,-.15,.15);
            b.x+=sweep_x/2;b.y+=sweep_y/2;
            b.x=std::clamp(b.x,0.,std::max(0.,1-b.w));
            b.y=std::clamp(b.y,0.,std::max(0.,1-b.h));
        }
        local=std::isfinite(b.x)&&std::isfinite(b.y)&&std::isfinite(b.w)&&std::isfinite(b.h)&&
            b.w>0&&b.h>0&&b.w<=1&&b.h<=1&&b.x>=0&&b.y>=0&&b.x+b.w<=1&&b.y+b.h<=1&&
            std::isfinite(t.position_std)&&t.position_std>=0;
        if(local) {
            const double extent=std::max(b.w*sw,b.h*sh);
            const double needed=std::max({cfg_.context*extent,extent+4*t.position_std*std::max(sw,sh),
                std::min(double(std::min(sw,sh)),cfg_.minimum_side+std::max(std::abs(sweep_x)*sw,std::abs(sweep_y)*sh))});
            if(needed<=std::min(sw,sh)&&cfg_.minimum_side<=std::min(sw,sh)) {
                const int side=std::max(cfg_.minimum_side,int(std::ceil(needed/2))*2);
                r.x=int(std::clamp((b.x+b.w/2)*sw-side/2.,0.,double(sw-side))/2)*2;
                r.y=int(std::clamp((b.y+b.h/2)*sh-side/2.,0.,double(sh-side))/2)*2;
                r.w=r.h=side;r.full_frame=false;
            }
        }
    }
    if(r.full_frame)last_full_ms_=capture;
    return r;
}
RoiAssist::RoiAssist(double max_age,double primary_window,double context,bool predict_phone):max_age_ms_(max_age),primary_window_ms_(primary_window) {
    if(!std::isfinite(max_age)||max_age<=0||max_age>1000||!std::isfinite(primary_window)||primary_window<400||primary_window>2000||
       !std::isfinite(context)||context<1.5||context>8)
        throw std::invalid_argument("invalid ROI budgets");
    // The managed path already runs a full-view detector on every update. Its
    // local planner must not demand a refresh faster than the measured global
    // search cadence, or every slow update becomes full-only forever.
    planner_=SearchPlanner(SearchConfig{primary_window/2,std::max(200.,max_age),context,640,true,predict_phone});
}
void RoiAssist::observe_global(const Target& t,double capture) {
    if(!t.id||!t.box||!t.control_valid||!t.observation_valid||!std::isfinite(capture))return;
    if(t.epoch!=epoch_){reset();epoch_=t.epoch;}
    last_primary_ms_=capture;
}
void RoiAssist::reset() {
    planner_.reset();epoch_=sequence_=request_sequence_=0;capture_ms_=last_primary_ms_=last_request_ms_=-1;label_.clear();request_.reset();
}
std::optional<SearchRegion> RoiAssist::plan(const Frame& full,const Target& previous,int width,int height) {
    request_sequence_=0;request_.reset();
    if(!full.timestamp_valid||!full.sequence||full.sequence<=sequence_||!std::isfinite(full.capture_ms)||
       !std::isfinite(full.now_ms)||full.capture_ms<=capture_ms_||full.now_ms<full.capture_ms||full.now_ms-full.capture_ms>max_age_ms_) {
        reset();reason_="age_or_sequence_budget";return {};
    }
    if(previous.epoch!=epoch_) {reset();epoch_=previous.epoch;}
    sequence_=full.sequence;capture_ms_=full.capture_ms;
    const bool tracking=previous.observation_valid&&previous.control_valid&&previous.state=="tracking";
    const bool searching=previous.state=="coasting"&&
        (previous.reason=="missing_or_stale_observation"||previous.reason=="low_confidence")&&previous.position_std<=.12;
    // Whatever class the owner locked gets the local search; the assist merge is label-bound below.
    if(!epoch_||previous.label.empty()||!previous.id||!previous.box||(!tracking&&!searching)) {
        planner_.reset();last_primary_ms_=-1;reason_="no_usable_target";return {};
    }
    label_=previous.label;
    // Current full-frame detections only. ROI additions are supplied AFTER plan,
    // so repeatedly re-detecting the same crop cannot extend the global deadline.
    for(const auto& d:full.detections) {
        const auto& b=d.box;
        if(d.label==label_&&std::isfinite(d.confidence)&&d.confidence>=.15&&d.confidence<=1&&
           std::isfinite(b.x)&&std::isfinite(b.y)&&std::isfinite(b.w)&&std::isfinite(b.h)&&
           b.w>0&&b.h>0&&b.w<=1&&b.h<=1&&iou(b,*previous.box)>=.3)
            last_primary_ms_=full.capture_ms;
    }
    const auto region=planner_.next(full.sequence,full.capture_ms,width,height,previous);
    if(last_primary_ms_<0||full.capture_ms-last_primary_ms_>primary_window_ms_){reason_="global_evidence_expired";return {};}
    if(region.full_frame){reason_="geometry_or_periodic_full";return {};}
    if(last_request_ms_>=0&&full.capture_ms-last_request_ms_<100){reason_="roi_cadence";return {};}
    reason_="requested";
    last_request_ms_=full.capture_ms;request_sequence_=full.sequence;request_=region;return region;
}
size_t RoiAssist::merge(Frame& frame,const SearchRegion& region,const std::vector<Detection>& local,size_t limit) const {
    if(!request_||!request_sequence_||frame.sequence!=request_sequence_||region.sequence!=frame.sequence||
       frame.capture_ms!=capture_ms_||region.capture_ms!=frame.capture_ms||!frame.timestamp_valid||
       // The cap bound is the tracker's own (max_detections <= 512); a tighter guard here refused
       // every ROI box for the 512-cap aerial profile without any signal (2026-09-14).
       !region.valid()||region.full_frame||limit>512||local.size()>100)return 0;
    const auto& expected=*request_;
    if(region.x!=expected.x||region.y!=expected.y||region.w!=expected.w||region.h!=expected.h||
       region.source_w!=expected.source_w||region.source_h!=expected.source_h||
       region.network_w!=expected.network_w||region.network_h!=expected.network_h)return 0;
    size_t added=0;
    for(const auto& candidate:local) {
        if(frame.detections.size()>=limit)break;
        auto d=candidate;const auto& b=d.box;
        if(d.label!=label_||!std::isfinite(d.confidence)||d.confidence<.15||d.confidence>1||
           !std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.w)||!std::isfinite(b.h)||b.w<=0||b.h<=0||
           b.w>1||b.h>1||region.cuts_object(region.to_network(b)))continue;
        const double x1=std::clamp(b.x,0.,1.),y1=std::clamp(b.y,0.,1.);
        const double x2=std::clamp(b.x+b.w,0.,1.),y2=std::clamp(b.y+b.h,0.,1.);
        if(x2<=x1||y2<=y1)continue;
        d.box={x1,y1,x2-x1,y2-y1};
        // On overlap the better observation wins: the crop sees the target at up to
        // twice the full view's resolution, and a full-view box kept at its lower
        // confidence would hide that from the tracker's birth/control floors.
        // Primary-evidence deadlines were already taken from the full view in plan().
        Detection* overlapping=nullptr;
        for(auto& primary:frame.detections)
            if(primary.label==d.label&&iou(primary.box,d.box)>=.4){overlapping=&primary;break;}
        if(!overlapping){frame.detections.push_back(std::move(d));++added;}
        else if(d.confidence>overlapping->confidence){*overlapping=std::move(d);++added;}
    }
    return added;
}
FollowSchedule::FollowSchedule(double global_period,double local_gap,double short_miss)
    :global_period_ms_(global_period),local_gap_ms_(local_gap),short_miss_ms_(short_miss) {
    if(!std::isfinite(global_period)||global_period<=0||!std::isfinite(local_gap)||local_gap<=0||
       !std::isfinite(short_miss)||short_miss<0||short_miss>250)
        throw std::invalid_argument("invalid follow schedule budgets");
}
bool FollowSchedule::global_required(const Target& t,double capture) {
    if(t.epoch!=epoch_){reset();epoch_=t.epoch;}
    reason_="global_search";
    if(!std::isfinite(capture)||capture<last_valid_||capture<last_global_)return true;
    // Only an established phone ROI may bridge a brief miss. No ambiguity,
    // expiry, fresh identity acquisition, or independent refresh is deferred.
    if(short_miss_ms_>0&&t.label=="cell phone"&&t.id&&t.box&&t.state=="coasting"&&
       (t.reason=="missing_or_stale_observation"||t.reason=="low_confidence")&&
       std::isfinite(t.position_std)&&t.position_std<=.12&&
       std::isfinite(t.observation_age_ms)&&t.observation_age_ms>=0&&t.observation_age_ms<=250&&
       last_valid_>=0&&capture-last_valid_<=short_miss_ms_&&local_hits_>=2&&
       last_local_>=0&&capture-last_local_<=local_gap_ms_&&
       last_global_>=0&&capture-last_global_<global_period_ms_) {
        reason_="bounded_phone_miss";return false;
    }
    if(!t.id||!t.box||!t.control_valid||!t.observation_valid||t.state!="tracking")return true;
    // Large targets already resolved by the full view cannot fit the local square.
    const bool needs_crop=std::max(t.box->w*1280,t.box->h*720)*2.5<=720;
    // Full-view inference still runs EVERY frame. Corner refresh is useful only
    // for targets needing its extra scale; it must not stall a resolved large
    // target every global_period_ms. Any loss/invalidity above resumes search.
    if(!needs_crop){reason_="large_target_full_view";return false;}
    const bool global=last_global_<0||capture-last_global_>=global_period_ms_||
        (needs_crop&&(local_hits_<2||last_local_<0||capture-last_local_>local_gap_ms_));
    reason_=global?"corner_refresh_or_handover":"verified_local";return global;
}
void FollowSchedule::observe(bool global,bool local,const Target& t,double capture) {
    if(t.epoch!=epoch_){reset();epoch_=t.epoch;}
    if(!t.control_valid||!t.observation_valid){
        // Decide using the newly observed miss, not the pre-inference target.
        // Otherwise the first missing frame erases the established ROI history.
        global_required(t,capture);
        if(reason_!="bounded_phone_miss")local_hits_=0;
        return;
    }
    last_valid_=capture;
    if(global)last_global_=capture;
    if(local){if(last_local_<0||capture-last_local_>local_gap_ms_)local_hits_=0;++local_hits_;last_local_=capture;}
}
}
