#include "garuda_tracking/target_owner.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace garuda::fresh {
namespace {
bool valid_track(const Track& t) {
    const auto& b=t.box;
    return t.id&&std::isfinite(b.x)&&std::isfinite(b.y)&&std::isfinite(b.w)&&std::isfinite(b.h)&&
        b.w>0&&b.h>0&&b.w<=2&&b.h<=2&&b.x+b.w>0&&b.y+b.h>0&&b.x<1&&b.y<1&&
        std::isfinite(t.position_std)&&t.position_std>=0&&std::isfinite(t.confidence)&&
        t.confidence>=0&&t.confidence<=1;
}
}
bool normalize_embedding(Embedding& e) {
    if(e.model.empty()||e.model.size()>256)return false;
    double norm=0;
    for(double x:e.values) {if(!std::isfinite(x))return false;norm+=x*x;}
    if(!std::isfinite(norm)||norm<1e-12)return false;
    norm=std::sqrt(norm);for(double& x:e.values)x/=norm;
    return true;
}
double embedding_distance(const Embedding& a,const Embedding& b) {
    if(a.model!=b.model)return std::numeric_limits<double>::infinity();
    double dot=0,aa=0,bb=0;
    for(size_t i=0;i<a.values.size();++i) {
        dot+=a.values[i]*b.values[i];aa+=a.values[i]*a.values[i];bb+=b.values[i]*b.values[i];
    }
    if(!std::isfinite(dot)||!std::isfinite(aa)||!std::isfinite(bb)||aa<1e-12||bb<1e-12)
        return std::numeric_limits<double>::infinity();
    return 1-std::clamp(dot/std::sqrt(aa*bb),-1.,1.);
}
TargetOwner::TargetOwner(IdentityConfig cfg):cfg_(cfg) {
    for(double x:{cfg.freshness_ms,cfg.memory_ms,cfg.continuation_ms,cfg.reacquire_ms,
        cfg.reacquire_gap_ms,cfg.max_anchor_distance,cfg.max_recent_distance,cfg.ambiguity_margin,
        cfg.confidence,cfg.max_position_std})
        if(!std::isfinite(x)||x<=0)throw std::invalid_argument("invalid identity configuration");
    for(double x:{cfg.evidence_radius,cfg.evidence_radius_growth})
        if(!std::isfinite(x)||x<0||x>100)throw std::invalid_argument("invalid identity evidence reach");
    if(cfg.memory_ms<=cfg.freshness_ms||cfg.confidence>1||cfg.max_anchor_distance>=1||
       cfg.max_recent_distance>=1||cfg.ambiguity_margin>=1||cfg.reacquire_hits<2||cfg.reacquire_hits>100||
       (cfg.evidence_radius==0&&cfg.evidence_radius_growth>0))
        throw std::invalid_argument("inconsistent identity configuration");
}
void TargetOwner::reset_pending() {pending_id_.reset();pending_hits_=0;pending_start_ms_=pending_last_ms_=0;}
void TargetOwner::clear() {
    anchor_.reset();recent_.clear();target_=Target{};bound_id_.reset();last_box_.reset();reset_pending();
    sequence_=0;capture_ms_=-1;publish_ms_=last_seen_ms_=0;expired_=false;clock_valid_=true;
}
bool TargetOwner::within_reach(const Box& b,double capture) const {
    // Unbounded reach, or no verified box to measure from: the person counts (fail closed).
    if(cfg_.evidence_radius<=0||!last_box_)return true;
    const auto& l=*last_box_;
    const double extent=std::max(l.w,l.h);
    const double seconds=std::max(0.,capture-last_seen_ms_)/1000.;
    const double reach=(cfg_.evidence_radius+cfg_.evidence_radius_growth*seconds)*extent;
    if(!std::isfinite(reach))return true;
    return std::fabs((b.x+b.w/2)-(l.x+l.w/2))<=reach&&std::fabs((b.y+b.h/2)-(l.y+l.h/2))<=reach;
}
bool TargetOwner::select(const Track& t,uint64_t epoch,double now) {
    if(!epoch||!valid_track(t)||t.label!="person"||!t.observed||!t.confirmed||t.ambiguous||!t.embedding||
       !std::isfinite(now)||!std::isfinite(t.last_seen_ms)||now<t.last_seen_ms||
       now-t.last_seen_ms>cfg_.freshness_ms||!std::isfinite(t.confidence)||t.confidence<cfg_.confidence||
       !std::isfinite(t.position_std)||t.position_std>cfg_.max_position_std)return false;
    auto e=*t.embedding;if(!normalize_embedding(e))return false;
    clear();anchor_=e;recent_.push_back(e);target_.epoch=epoch;target_.label=t.label;
    publish_ms_=now;observe(t,t.last_seen_ms);return true;
}
void TargetOwner::observe(const Track& t,double capture) {
    bound_id_=t.id;last_seen_ms_=capture;target_.id=t.id;target_.box=t.box;last_box_=t.box;
    target_.last_verified_box=t.box;
    target_.position_std=t.position_std;target_.identity_retained=true;
    target_.state="tracking";target_.reason="identity_verified";
    target_.observation_valid=target_.control_valid=true;
    auto e=*t.embedding;normalize_embedding(e);recent_.push_back(std::move(e));
    if(recent_.size()>8)recent_.pop_front();
    reset_pending();
}
void TargetOwner::update(uint64_t seq,double capture,double now,bool valid,const std::vector<Track>& tracks) {
    if(!active())return;
    target_.observation_valid=target_.control_valid=false;target_.id.reset();target_.box.reset();
    target_.identity_candidates=target_.identity_unresolved=0;
    target_.identity_best_distance.reset();target_.identity_runner_up_distance.reset();
    if(!valid||!std::isfinite(capture)||!std::isfinite(now)||capture<0||now<capture||
       now<publish_ms_||seq<=sequence_||capture<=capture_ms_||now-capture>cfg_.freshness_ms) {
        clock_valid_=false;target_.state="occluded";target_.reason="invalid_or_stale_frame";reset_pending();return;
    }
    clock_valid_=true;sequence_=seq;capture_ms_=capture;publish_ms_=now;
    if(expired_||now-last_seen_ms_>cfg_.memory_ms) {
        expired_=true;target_.identity_retained=false;target_.state="lost";
        target_.reason="identity_memory_expired";reset_pending();return;
    }
    struct Match {const Track* track;double distance;};
    std::vector<Match> matches;
    bool unresolved=false;
    if(tracks.size()>256) {target_.state="ambiguous";target_.reason="candidate_limit";reset_pending();return;}
    for(const auto& t:tracks) {
        if(t.label!="person"||!t.observed||t.last_seen_ms!=capture)continue;
        // A visible person without a compatible descriptor could be the true target — when the
        // target could have reached where they stand (the descriptor budget is spent nearest the
        // target first, so the undescribed are the far ones; VisDrone-SOT 086/054, 2026-09-18).
        if(!valid_track(t)||t.ambiguous||!t.embedding||t.embedding->model!=anchor_->model) {
            if(!valid_track(t)||within_reach(t.box,capture)) {unresolved=true;++target_.identity_unresolved;}
            continue;
        }
        auto e=*t.embedding;
        if(!normalize_embedding(e)) {unresolved=true;++target_.identity_unresolved;continue;}
        const double anchor=embedding_distance(*anchor_,e);
        double recent=2;for(const auto& r:recent_)recent=std::min(recent,embedding_distance(r,e));
        if(anchor>cfg_.max_anchor_distance||recent>cfg_.max_recent_distance)continue;
        matches.push_back({&t,.7*anchor+.3*recent});
    }
    std::sort(matches.begin(),matches.end(),[](const Match& a,const Match& b){return a.distance<b.distance;});
    target_.identity_candidates=matches.size();
    if(!matches.empty())target_.identity_best_distance=matches[0].distance;
    if(matches.size()>1)target_.identity_runner_up_distance=matches[1].distance;
    if(matches.size()>1&&matches[1].distance-matches[0].distance<cfg_.ambiguity_margin) {
        target_.state="ambiguous";target_.reason="similar_identity_candidates";reset_pending();return;
    }
    // A person without a usable descriptor could be the true target, so incomplete
    // evidence blocks binding a DIFFERENT id. It does not outrank the bound track's
    // own positive re-identification within continuation_ms: refusing there would
    // surrender control to a bystander's missing crop (VisDrone-SOT 086, 2026-09-12).
    const bool continuing=!matches.empty()&&bound_id_==matches.front().track->id&&
        capture-last_seen_ms_<=cfg_.continuation_ms&&!pending_id_;
    if(unresolved&&!continuing) {
        target_.state="ambiguous";target_.reason="identity_evidence_incomplete";reset_pending();return;
    }
    if(matches.empty()) {target_.state="occluded";target_.reason="selected_identity_not_observed";reset_pending();return;}
    const auto& t=*matches.front().track;
    if(!t.confirmed||!std::isfinite(t.confidence)||t.confidence<cfg_.confidence||
       !std::isfinite(t.position_std)||t.position_std>cfg_.max_position_std) {
        target_.state="occluded";target_.reason="candidate_not_confirmed";reset_pending();return;
    }
    if(bound_id_==t.id&&capture-last_seen_ms_<=cfg_.continuation_ms&&!pending_id_) {observe(t,capture);return;}
    if(pending_id_!=t.id||capture-pending_last_ms_>cfg_.reacquire_gap_ms) {
        reset_pending();pending_id_=t.id;pending_start_ms_=capture;
    }
    ++pending_hits_;pending_last_ms_=capture;
    target_.state="reacquiring";target_.reason="verifying_returning_identity";
    if(pending_hits_>=cfg_.reacquire_hits&&capture-pending_start_ms_>=cfg_.reacquire_ms)observe(t,capture);
}
Target TargetOwner::snapshot(double now) const {
    auto out=target_;if(!active())return out;
    const bool clock=clock_valid_&&std::isfinite(now)&&now>=publish_ms_;
    if(!clock)now=publish_ms_;
    out.observation_age_ms=std::max(0.,now-last_seen_ms_);
    if(expired_||now-last_seen_ms_>cfg_.memory_ms) {
        out.state="lost";out.reason="identity_memory_expired";out.identity_retained=false;
        out.observation_valid=out.control_valid=false;out.id.reset();out.box.reset();
    } else if(!clock||now-last_seen_ms_>cfg_.freshness_ms) {
        out.observation_valid=out.control_valid=false;out.id.reset();out.box.reset();
        if(!clock) {out.state="occluded";out.reason="invalid_clock";}
        else if(out.state=="tracking") {out.state="occluded";out.reason="missing_or_stale_observation";}
    }
    return out;
}
}
