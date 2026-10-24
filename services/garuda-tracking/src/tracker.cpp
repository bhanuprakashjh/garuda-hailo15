#include "garuda_tracking/tracker.hpp"
#include "garuda_tracking/target_owner.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace garuda::fresh {
namespace {
constexpr double forbidden=1e6, unmatched=.95;
double square(double x) { return x*x; }
bool finite_box(const Box& b) {
    return std::isfinite(b.x) && std::isfinite(b.y) && std::isfinite(b.w) &&
           std::isfinite(b.h) && b.w>0 && b.h>0 && b.w<=2 && b.h<=2;
}
bool normalize(Detection& d) {
    if (!finite_box(d.box) || !std::isfinite(d.confidence) || d.confidence<0 ||
        d.confidence>1 || d.label.empty() || d.label.size()>128) return false;
    const double right=std::clamp(d.box.x+d.box.w,0.,1.);
    const double bottom=std::clamp(d.box.y+d.box.h,0.,1.);
    d.box.x=std::clamp(d.box.x,0.,1.); d.box.y=std::clamp(d.box.y,0.,1.);
    d.box.w=right-d.box.x; d.box.h=bottom-d.box.y;
    if (d.box.w<.001 || d.box.h<.001) return false;
    if (d.appearance) {
        double sum=0;
        for (double x:*d.appearance) { if (!std::isfinite(x) || x<0) return false; sum+=x; }
        if (!std::isfinite(sum) || sum<=0) return false;
        for (double& x:*d.appearance) x/=sum;
    }
    if(d.embedding&&!normalize_embedding(*d.embedding))return false;
    return true;
}
// Rectangular Hungarian assignment; one private dummy column per track permits unmatched rows.
std::vector<int> assign(const std::vector<std::vector<double>>& cost) {
    const int n=static_cast<int>(cost.size());
    if (!n) return {};
    const int m=static_cast<int>(cost[0].size());
    std::vector<double> u(n+1),v(m+1);
    std::vector<int> p(m+1),way(m+1);
    for (int i=1;i<=n;++i) {
        p[0]=i;
        int j0=0;
        std::vector<double> minv(m+1,forbidden*2);
        std::vector<bool> used(m+1,false);
        do {
            used[j0]=true;
            const int i0=p[j0];
            double delta=forbidden*2; int j1=0;
            for (int j=1;j<=m;++j) if (!used[j]) {
                double cur=cost[i0-1][j-1]-u[i0]-v[j];
                if (cur<minv[j]) { minv[j]=cur; way[j]=j0; }
                if (minv[j]<delta) { delta=minv[j]; j1=j; }
            }
            for (int j=0;j<=m;++j) {
                if (used[j]) { u[p[j]]+=delta; v[j]-=delta; }
                else minv[j]-=delta;
            }
            j0=j1;
        } while (p[j0]!=0);
        do { int j1=way[j0]; p[j0]=p[j1]; j0=j1; } while (j0);
    }
    std::vector<int> result(n,-1);
    for (int j=1;j<=m;++j) if(p[j]) result[p[j]-1]=j-1;
    return result;
}
}

double iou(const Box& a,const Box& b) {
    double w=std::max(0.,std::min(a.x+a.w,b.x+b.w)-std::max(a.x,b.x));
    double h=std::max(0.,std::min(a.y+a.h,b.y+b.h)-std::max(a.y,b.y));
    double denom=a.w*a.h+b.w*b.h-w*h;
    return denom>0?w*h/denom:0;
}
bool Motion::usable() const {
    for(double x:{dx,dy,a,b,c,d,position_std})if(!std::isfinite(x))return false;
    const double determinant=a*d-b*c;
    return valid&&std::abs(dx)<=.25&&std::abs(dy)<=.25&&a>=.7&&a<=1.3&&d>=.7&&d<=1.3&&
        std::abs(b)<=.5&&std::abs(c)<=.5&&determinant>=.7&&determinant<=1.4&&
        position_std>=0&&position_std<=.05;
}
Box Motion::transform(const Box& box) const {
    if(!usable())return box;
    const double x=box.x+box.w/2-.5,y=box.y+box.h/2-.5;
    const double w=std::abs(a)*box.w+std::abs(b)*box.h,h=std::abs(c)*box.w+std::abs(d)*box.h;
    return {.5+dx+a*x+b*y-w/2,.5+dy+c*x+d*y-h/2,w,h};
}
double appearance_distance(const Appearance& a,const Appearance& b) {
    double overlap=0;
    for(size_t i=0;i<a.size();++i) overlap+=std::sqrt(a[i]*b[i]);
    return std::sqrt(std::max(0.,1.-std::min(1.,overlap)));
}
void Tracker::Axis::predict(double dt,double noise) {
    p+=v*dt;
    pp+=2*dt*pv+dt*dt*vv+noise*std::pow(dt,4)/4;
    pv+=dt*vv+noise*std::pow(dt,3)/2;
    vv+=noise*dt*dt;
}
void Tracker::Axis::correct(double z,double variance) {
    double innovation=z-p, s=pp+variance, kp=pp/s, kv=pv/s;
    p+=kp*innovation; v+=kv*innovation;
    // Scalar measurement update, using the pre-update covariance in all three terms.
    double old_pp=pp,old_pv=pv;
    pp=std::max(1e-12,old_pp-kp*old_pp);
    pv=old_pv-kp*old_pv;
    vv=std::max(1e-12,vv-kv*old_pv);
}
Tracker::Tracker(Config cfg):cfg_(std::move(cfg)) {
    for (double v:{cfg_.low_confidence,cfg_.birth_confidence,cfg_.control_confidence,
                   cfg_.appearance_gate,cfg_.ambiguity_margin,cfg_.association_embedding_gate})
        if (!std::isfinite(v)||v<0||v>1) throw std::invalid_argument("invalid tracking probability");
    for(double v:{cfg_.confirm_ms,cfg_.max_gap_ms,cfg_.coast_ms,cfg_.freshness_ms,cfg_.selection_ms,
                  cfg_.max_center_distance,cfg_.max_size_ratio,cfg_.max_position_std,cfg_.position_acceleration_std,
                  cfg_.reacquire_confirm_ms,cfg_.reacquire_gap_ms,cfg_.reacquire_radius,cfg_.reacquire_radius_growth})
        if(!std::isfinite(v)||v<=0) throw std::invalid_argument("invalid tracking limit");
    if(!std::isfinite(cfg_.reacquire_window_ms)||cfg_.reacquire_window_ms<0||
       cfg_.reacquire_size_ratio<=1||!std::isfinite(cfg_.reacquire_size_ratio)||
       cfg_.reacquire_hits<1||cfg_.reacquire_hits>100)
        throw std::invalid_argument("invalid reacquire config");
    if(cfg_.low_confidence>=cfg_.birth_confidence || cfg_.control_confidence<cfg_.low_confidence ||
       cfg_.max_size_ratio<=1 || cfg_.position_acceleration_std>100 || cfg_.max_gap_ms>cfg_.coast_ms || cfg_.min_hits<2 || cfg_.min_hits>1000 ||
       cfg_.max_tracks==0||cfg_.max_tracks>256||cfg_.max_detections==0||cfg_.max_detections>512)
        throw std::invalid_argument("inconsistent tracking config");
    if(cfg_.car_gap_reverify&&cfg_.reacquire_window_ms<=0)
        throw std::invalid_argument("car gap verification requires bounded recovery");
    if(cfg_.learned_person_identity) {
        if(!std::isfinite(cfg_.identity_memory_ms)||cfg_.identity_memory_ms<=cfg_.freshness_ms||cfg_.identity_memory_ms>600000)
            throw std::invalid_argument("identity_memory_ms must exceed freshness_ms and stay within 10 minutes");
        if(!std::isfinite(cfg_.identity_max_distance)||cfg_.identity_max_distance<=0||cfg_.identity_max_distance>=1||
           !std::isfinite(cfg_.identity_ambiguity_margin)||cfg_.identity_ambiguity_margin<=0||cfg_.identity_ambiguity_margin>=1)
            throw std::invalid_argument("identity gates must lie in (0,1)");
        IdentityConfig identity;
        for(double gap:{cfg_.identity_continuation_ms,cfg_.identity_reacquire_gap_ms})
            if(!std::isfinite(gap)||gap<=0||gap>500)
                throw std::invalid_argument("identity observation gaps must be within 0..500 ms");
        identity.continuation_ms=cfg_.identity_continuation_ms;
        identity.reacquire_gap_ms=cfg_.identity_reacquire_gap_ms;
        identity.memory_ms=cfg_.identity_memory_ms;
        identity.max_anchor_distance=identity.max_recent_distance=cfg_.identity_max_distance;
        identity.ambiguity_margin=cfg_.identity_ambiguity_margin;
        for(double reach:{cfg_.identity_evidence_radius,cfg_.identity_evidence_radius_growth})
            if(!std::isfinite(reach)||reach<0||reach>100)
                throw std::invalid_argument("identity evidence reach must be within 0..100 extents");
        if(cfg_.identity_evidence_radius==0&&cfg_.identity_evidence_radius_growth>0)
            throw std::invalid_argument("identity evidence reach growth needs a radius");
        identity.evidence_radius=cfg_.identity_evidence_radius;
        identity.evidence_radius_growth=cfg_.identity_evidence_radius_growth;
        identity.freshness_ms=cfg_.freshness_ms;identity.max_position_std=cfg_.max_position_std;
        identity.confidence=std::max(cfg_.birth_confidence,cfg_.control_confidence);
        owner_=std::make_unique<TargetOwner>(identity);
    }
}
Tracker::~Tracker()=default;

Output Tracker::update(const Frame& f) {
    recovery_diagnostic_.reset();
    association_diagnostic_.reset();
    association_candidates_.clear();
    const auto reject=[&](const char* reason) {
        last_timestamp_valid_=false; // rejected input cannot leave a cached valid control result
        if(owner_)owner_->update(f.sequence,f.capture_ms,f.now_ms,false,{});
        auto out=snapshot(std::isfinite(f.now_ms)?std::max(last_publish_ms_,f.now_ms):last_publish_ms_);
        out.accepted=false; out.reason=reason;
        return out;
    };
    if(!f.timestamp_valid || !std::isfinite(f.capture_ms) || !std::isfinite(f.now_ms) ||
       f.capture_ms<0 || f.now_ms<f.capture_ms || f.now_ms<last_publish_ms_)
        return reject("invalid_clock");
    if(f.sequence<=sequence_ || f.capture_ms<=last_capture_ms_) return reject("out_of_order");
    if(f.now_ms-f.capture_ms>cfg_.freshness_ms) return reject("stale_frame");
    // Expire BEFORE association: returning after a long gap can never resurrect the selected ID.
    // Re-acquire is a separate, gated layer over the retained memory, never association.
    if(target_id_&&!target_lost_&&cfg_.reacquire_window_ms>0&&(!owner_||!owner_->active())) {
        auto it=std::find_if(states_.begin(),states_.end(),[&](const State& s){return s.public_track.id==*target_id_;});
        const bool interrupted_car=it!=states_.end()&&cfg_.car_gap_reverify&&
            it->public_track.label=="car"&&f.capture_ms-it->public_track.last_seen_ms>cfg_.max_gap_ms;
        if(it!=states_.end()&&(interrupted_car||f.now_ms-it->public_track.last_seen_ms>cfg_.coast_ms)) {
            const auto& t=it->public_track;
            // Capture-domain stamp: update() ages memory against capture_ms, so the
            // loss clock must live in the same domain (publish latency otherwise
            // makes capture_ms-lost_ms negative right after loss).
            lost_memory_=LostMemory{t.label,it->recovery_box,it->appearance,f.capture_ms,t.last_seen_ms,t.id};
            // Freeze identity memory BEFORE association. A surviving MOT ID is
            // now a candidate, not permission to resume control or relearn the
            // remembered target. Existing recovery gates and deadline apply.
            if(interrupted_car)target_lost_=true;
        }
    }
    states_.erase(std::remove_if(states_.begin(),states_.end(),[&](const State& s) {
        return f.now_ms-s.public_track.last_seen_ms>cfg_.coast_ms;
    }),states_.end());
    if(target_id_ && std::none_of(states_.begin(),states_.end(),[&](const State& s){return s.public_track.id==*target_id_;}))
        target_lost_=true;
    if(lost_memory_&&f.motion.usable())lost_memory_->box=f.motion.transform(lost_memory_->box);
    double dt=last_capture_ms_<0?0:(f.capture_ms-last_capture_ms_)/1000.;
    sequence_=f.sequence; last_capture_ms_=f.capture_ms; last_publish_ms_=f.now_ms;
    last_timestamp_valid_=true;
    for(auto& s:states_) {
        auto& t=s.public_track;
        t.observed=false; t.ambiguous=false; t.visual_observation=false;
        t.embedding.reset();
        t.filtered_box.reset();
        // Center motion can reverse quickly even when box dimensions are stable.
        // The old shared q=.16 became overconfident and gated out visible small objects.
        for(size_t k=0;k<s.axes.size();++k)
            s.axes[k].predict(dt,k<2?square(cfg_.position_acceleration_std):.16);
        if(f.motion.usable()) {
            const auto& m=f.motion;
            s.recovery_box=m.transform(s.recovery_box);
            auto mix=[](const Axis& x,const Axis& y,double a,double b,double offset,double noise) {
                Axis out;out.p=a*x.p+b*y.p+offset;out.v=a*x.v+b*y.v;
                // Cross-axis correlations are not stored by this filter. The triangle/Cauchy
                // bound dominates any such correlation; do not rotate just positions and leave
                // overconfident old diagonal covariances behind.
                const double sum=std::abs(a)+std::abs(b),ax=std::abs(a)*sum,ay=std::abs(b)*sum;
                out.pp=ax*x.pp+ay*y.pp+noise*noise;
                out.pv=ax*x.pv+ay*y.pv;out.vv=ax*x.vv+ay*y.vv;
                return out;
            };
            const auto old=s.axes;
            s.axes[0]=mix(old[0],old[1],m.a,m.b,.5+m.dx-.5*(m.a+m.b),m.position_std);
            s.axes[1]=mix(old[0],old[1],m.c,m.d,.5+m.dy-.5*(m.c+m.d),m.position_std);
            s.axes[2]=mix(old[2],old[3],std::abs(m.a),std::abs(m.b),0,m.position_std);
            s.axes[3]=mix(old[2],old[3],std::abs(m.c),std::abs(m.d),0,m.position_std);
        }
        double w=std::clamp(s.axes[2].p,.001,1.),h=std::clamp(s.axes[3].p,.001,1.);
        t.box={s.axes[0].p-w/2,s.axes[1].p-h/2,w,h};
        t.position_std=std::sqrt(std::max(s.axes[0].pp,s.axes[1].pp));
    }
    std::vector<Detection> dets;
    size_t rejected=0;
    // Bound all work, including malformed-input validation. The hardware adapter also caps input.
    // The cut keeps the most confident boxes: in an aerial crowd the input exceeds the cap and
    // detector order is arbitrary, so a plain prefix cut could drop the selected person.
    const size_t input_limit=std::min(f.detections.size(),cfg_.max_detections);
    rejected+=f.detections.size()-input_limit;
    std::vector<size_t> order(f.detections.size());
    for(size_t k=0;k<order.size();++k)order[k]=k;
    if(input_limit<order.size())
        std::partial_sort(order.begin(),order.begin()+input_limit,order.end(),
            [&](size_t a,size_t b){return f.detections[a].confidence>f.detections[b].confidence;});
    for(size_t n=0;n<input_limit;++n) {
        Detection d=f.detections[order[n]];
        if(!normalize(d)||d.confidence<cfg_.low_confidence ||
           (!cfg_.classes.empty()&&std::find(cfg_.classes.begin(),cfg_.classes.end(),d.label)==cfg_.classes.end())) {
            ++rejected; continue;
        }
        dets.push_back(std::move(d));
    }
    std::stable_sort(dets.begin(),dets.end(),[](const Detection& a,const Detection& b){return a.confidence>b.confidence;});
    // Same-class non-maximum suppression at IoU 0.5 (standard tracker input). The detector's
    // own NMS stops at 0.70 (HEF), so a 30 px person regularly carries a wide and a narrow
    // box overlapping at 0.5-0.7; fed to association those were two rival explanations
    // (ambiguity reset the confirmation streak) or two objects (a second track), and the
    // click on VisDrone-SOT 024 found no confirmed track at frame 16. Only an appearance
    // distance beyond the association gate keeps such a pair apart (two objects that could
    // never be associated as one): measured on 024, 26 of 27 one-person duplicate pairs had
    // histogram distance > 0.1 (the wide box holds more background), median 0.15, so a
    // small "different appearance" escape would defeat the merge. Descriptors deliberately
    // do not keep boxes apart here: crops of one person from different tiles disagree by
    // more than the gate and keeping both split the person (086). Containment alone (a phone
    // inside a person) is a different label and never a duplicate; a small box inside a
    // large same-class box has low IoU and is kept. The tiled path already merges at IoU 0.3
    // across regions, so this is not stricter than the searching state.
    std::vector<Detection> unique;
    for(auto& d:dets) {
        bool duplicate=std::any_of(unique.begin(),unique.end(),[&](const Detection& e){
            const bool distinct=e.appearance&&d.appearance&&appearance_distance(*e.appearance,*d.appearance)>cfg_.appearance_gate;
            return e.label==d.label&&iou(e.box,d.box)>=.5&&!distinct;
        });
        if(duplicate) ++rejected; else unique.push_back(d);
    }
    dets=std::move(unique);
    const bool sole_phone=cfg_.phone_gap_association&&
        std::count_if(dets.begin(),dets.end(),[](const Detection& d){return d.label=="cell phone";})==1&&
        std::none_of(states_.begin(),states_.end(),[&](const State& s){
            return s.public_track.label=="cell phone"&&s.public_track.confirmed&&
                (!target_id_||s.public_track.id!=*target_id_);
        });
    const auto visual_for=[&](const State& s)->const VisualMeasurement* {
        if(!cfg_.visual_phone_tracking||!f.visual_target||!target_id_||target_lost_||
           s.public_track.id!=*target_id_||s.public_track.label!="cell phone"||!s.public_track.confirmed)return nullptr;
        const auto& v=*f.visual_target;const auto& b=v.box;
        if(v.lock_id!=lock_id_||v.epoch!=epoch_||v.sequence!=f.sequence||v.capture_ms!=f.capture_ms||
           !std::isfinite(v.verified_ms)||v.verified_ms<0||v.verified_ms>f.capture_ms||
           f.capture_ms-v.verified_ms>visual_verification_horizon_ms||s.last_detector_ms<0||
           f.capture_ms-s.last_detector_ms>visual_verification_horizon_ms||
           f.capture_ms-s.public_track.last_seen_ms>500||
           !std::isfinite(v.score)||v.score<.65||v.score>1||!std::isfinite(v.margin)||v.margin<.08||v.margin>2||
           !std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.w)||!std::isfinite(b.h)||
           b.x<0||b.y<0||b.w<=0||b.h<=0||b.x+b.w>1||b.y+b.h>1)return nullptr;
        return &v;
    };
    auto pair_cost=[&](size_t i,size_t j,AssociationCandidateDiagnostic* diag=nullptr) {
        const auto& s=states_[i]; const auto& t=s.public_track; const auto& d=dets[j];
        auto reject_pair=[&](const char* reason) { if(diag)diag->gate=reason;return forbidden; };
        if(t.label!=d.label) return reject_pair("class");
        const auto* vm=visual_for(s);
        const auto& a=vm?vm->box:t.box; const auto& b=d.box;
        if(vm&&iou(a,b)<.3)return reject_pair("visual_disagreement");
        if(vm&&d.confidence<cfg_.control_confidence)return reject_pair("visual_not_detector_verified");
        const bool visual=s.appearance.has_value()&&d.appearance.has_value();
        double ad=visual?appearance_distance(*s.appearance,*d.appearance):0;
        if(diag) {
            diag->prediction=a;diag->measurement=s.recovery_box;diag->detection=b;
            diag->confidence=d.confidence;diag->gap_ms=f.capture_ms-t.last_seen_ms;
            if(visual)diag->appearance_distance=ad;
        }
        double ratio=std::max({a.w/b.w,b.w/a.w,a.h/b.h,b.h/a.h});
        if(diag)diag->size_ratio=ratio;
        if(ratio>cfg_.max_size_ratio) return reject_pair("size_ratio");
        double dx=(a.x+a.w/2)-(b.x+b.w/2),dy=(a.y+a.h/2)-(b.y+b.h/2);
        double scaled=std::sqrt(square(dx/std::max(a.w,.025))+square(dy/std::max(a.h,.025)));
        if(diag)diag->distance=scaled;
        double center_limit=cfg_.max_center_distance;
        const double gap=f.capture_ms-t.last_seen_ms;
        // Fixed two-extent gating ignores uncertainty accumulated while the
        // detector is absent. Do not relax it for crowds, weak/no appearance,
        // weak detections, ordinary frame-to-frame motion, or expired locks.
        // The experimental bridge is capped at one second / four extents and
        // still passes size, absolute-displacement, covariance and assignment
        // ambiguity gates. Appearance is tighter than ordinary association.
        if(scaled>cfg_.max_center_distance&&sole_phone&&target_id_&&t.id==*target_id_&&!target_lost_&&t.confirmed&&
           t.label=="cell phone"&&gap>cfg_.max_gap_ms&&gap<=1000&&
           d.confidence>=std::max(cfg_.birth_confidence,cfg_.control_confidence)&&
           visual&&ad<=std::min(.35,cfg_.appearance_gate))
            center_limit=std::max(center_limit,std::min(4.,center_limit+2.*gap/1000.));
        if(diag) {
            diag->center_limit=center_limit;
            diag->phone_gap_bridge=scaled>cfg_.max_center_distance&&scaled<=center_limit;
        }
        // A 0.025 frame floor spans multiple tiny aerial cars. For the selected
        // car only, retain the existing ranking/gates but also bound a jump in
        // object extents. Use camera-compensated measurement size to avoid
        // Kalman size collapse making the gate arbitrarily tight.
        if(cfg_.car_extent_gate&&target_id_&&t.id==*target_id_&&!target_lost_&&t.label=="car"&&
           std::hypot(dx/std::max({a.w,s.recovery_box.w,.001}),
                      dy/std::max({a.h,s.recovery_box.h,.001}))>cfg_.max_center_distance)
            return reject_pair("car_extent");
        // Geometry remains bounded even when covariance grows through an occlusion.
        if(scaled>center_limit || std::abs(dx)>.3 || std::abs(dy)>.3) return reject_pair("center_distance");
        double noise=std::max(.003,.08*std::max(b.w,b.h));
        double mahal=square(dx)/(s.axes[0].pp+square(noise))+square(dy)/(s.axes[1].pp+square(noise));
        if(diag)diag->mahalanobis=mahal;
        if(mahal>16) return reject_pair("mahalanobis");
        if(visual&&ad>cfg_.appearance_gate) return reject_pair("appearance");
        // A learned descriptor on both sides outranks the colour histogram: two people
        // dressed alike keep their ids through a crossing (VisDrone-SOT 024, 2026-09-12).
        const bool learned=cfg_.association_embedding_gate>0&&s.embedding&&d.embedding&&s.embedding->model==d.embedding->model;
        const double ed=learned?embedding_distance(*s.embedding,*d.embedding):0;
        if(learned&&(!std::isfinite(ed)||ed>cfg_.association_embedding_gate)) return reject_pair("embedding");
        // Blend rather than replace: a single bad crop must not break continuity of the
        // track's own observation stream (VisDrone-SOT 024 lost the target with a hard
        // 0.5 gate and a descriptor-only term).
        const double descriptor=learned&&visual?.5*ad+.5*ed:learned?ed:ad;
        const double cost=(learned||visual) ? .25*(1-iou(a,b))+.2*scaled/center_limit+.1*std::log(ratio)/std::log(cfg_.max_size_ratio+1e-9)+.45*descriptor
                                 : .60*(1-iou(a,b))+.3*scaled/center_limit+.1*std::log(ratio)/std::log(cfg_.max_size_ratio+1e-9);
        if(diag) { diag->cost=cost;diag->gate=cost<unmatched?"eligible":"cost"; }
        return cost;
    };
    // Observe selected-track candidates once, before either assignment pass. An
    // eligible pair may still be refused by ambiguity or global assignment.
    if(cfg_.recovery_diagnostics&&target_id_&&!target_lost_)
        for(size_t i=0;i<states_.size();++i) if(states_[i].public_track.id==*target_id_)
            for(size_t j=0;j<dets.size();++j) if(dets[j].label==states_[i].public_track.label) {
                association_candidates_.emplace_back();
                pair_cost(i,j,&association_candidates_.back());
            }
    std::vector<bool> used(dets.size(),false),blocked(dets.size(),false);
    std::vector<bool> matched(states_.size(),false),ambiguous(states_.size(),false);
    // High confidence first, then low-score recovery only for established tracks.
    for(int pass=0;pass<2;++pass) {
        std::vector<size_t> rows,cols;
        for(size_t i=0;i<states_.size();++i)
            if(!matched[i]&&!ambiguous[i]&&(pass==0||states_[i].public_track.confirmed)) rows.push_back(i);
        for(size_t j=0;j<dets.size();++j)
            if(!used[j]&&!blocked[j]&&((dets[j].confidence>=cfg_.birth_confidence)==(pass==0))) cols.push_back(j);
        std::vector<std::vector<double>> costs(rows.size(),std::vector<double>(cols.size()+rows.size(),unmatched));
        for(size_t i=0;i<rows.size();++i) for(size_t j=0;j<cols.size();++j) costs[i][j]=pair_cost(rows[i],cols[j]);
        // If row or column has two almost equal explanations, do not learn either identity.
        auto mark=[&](size_t i,size_t j) { ambiguous[rows[i]]=true; blocked[cols[j]]=true; };
        for(size_t i=0;i<rows.size();++i) {
            double best=unmatched,second=unmatched;
            for(size_t j=0;j<cols.size();++j) { double c=costs[i][j]; if(c<best){second=best;best=c;}else second=std::min(second,c); }
            // The undecided track learns neither identity, but its candidates stay available to
            // tracks that match them unambiguously: a bystander's indecision must not cost the
            // target its observation (VisDrone-SOT 024 frame 4, confirmation streak reset). An
            // unclaimed candidate is still not born: the unmatched track plausibly explains it
            // (pending rule below). A detection wanted equally by two tracks is handled next.
            if(best<unmatched&&second<unmatched&&second-best<cfg_.ambiguity_margin) ambiguous[rows[i]]=true;
        }
        for(size_t j=0;j<cols.size();++j) {
            double best=unmatched;size_t ib=rows.size();
            for(size_t i=0;i<rows.size();++i) if(costs[i][j]<best){best=costs[i][j];ib=i;}
            if(best>=unmatched) continue;
            // A detection wanted equally by two tracks stays blocked (fail closed). Tried and
            // reverted 2026-09-13: exempting tracks that both overlap the contested box at
            // IoU >= 0.5 ("one box, one object") fixed a torso/full-body duplicate on VisDrone
            // 024 but, in the 086 crowd, gave the target's box to a neighbour walking shoulder
            // to shoulder and the identity owner never re-bound (on-target 44 -> 4 frames).
            double second=unmatched;
            for(size_t i=0;i<rows.size();++i) if(i!=ib) second=std::min(second,costs[i][j]);
            if(second<unmatched&&second-best<cfg_.ambiguity_margin)
                for(size_t i=0;i<rows.size();++i) if(costs[i][j]<=second) mark(i,j);
        }
        for(size_t i=0;i<rows.size();++i) for(size_t j=0;j<cols.size();++j)
            if(ambiguous[rows[i]]||blocked[cols[j]]) costs[i][j]=forbidden;
        auto assignment=assign(costs);
        for(size_t i=0;i<rows.size();++i) {
            int j=assignment[i];
            if(j<0||size_t(j)>=cols.size()||costs[i][j]>=unmatched) continue;
            size_t si=rows[i],di=cols[j]; auto& s=states_[si]; auto& t=s.public_track; const auto& d=dets[di];
            used[di]=true; matched[si]=true;
            const double gap=f.capture_ms-t.last_seen_ms;
            if(cfg_.recovery_diagnostics&&target_id_&&t.id==*target_id_&&!target_lost_&&t.label=="car") {
                const auto& a=t.box;const auto& b=d.box;
                const double dx=a.x+a.w/2-b.x-b.w/2,dy=a.y+a.h/2-b.y-b.h/2;
                association_diagnostic_=AssociationDiagnostic{a,s.recovery_box,b,
                    std::hypot(dx/std::max(a.w,.025),dy/std::max(a.h,.025)),
                    std::hypot(dx/std::max({a.w,s.recovery_box.w,.001}),dy/std::max({a.h,s.recovery_box.h,.001})),gap,{}};
                if(s.appearance&&d.appearance)association_diagnostic_->appearance_distance=appearance_distance(*s.appearance,*d.appearance);
            }
            if(gap>cfg_.max_gap_ms) { s.streak_start_ms=f.capture_ms; s.hits=0; }
            ++s.hits;
            if(!t.confirmed&&s.hits>=cfg_.min_hits&&f.capture_ms-s.streak_start_ms>=cfg_.confirm_ms) t.confirmed=true;
            const double noise=std::max(.003,.08*std::max(d.box.w,d.box.h))*(pass==0?1:2);
            const std::array<double,4> z={d.box.x+d.box.w/2,d.box.y+d.box.h/2,d.box.w,d.box.h};
            for(size_t a=0;a<4;++a) s.axes[a].correct(z[a],square(noise));
            t.filtered_box=Box{s.axes[0].p-s.axes[2].p/2,s.axes[1].p-s.axes[3].p/2,s.axes[2].p,s.axes[3].p};
            // Keep the Kalman state for the NEXT association prediction, not as
            // a falsely labelled current observation. Size velocity can overshoot
            // after a person approaches, crouches or reverses direction.
            t.box=d.box;
            s.recovery_box=d.box;
            t.confidence=d.confidence; t.last_seen_ms=f.capture_ms; t.observed=true;
            if(d.confidence>=cfg_.control_confidence){s.last_detector_ms=f.capture_ms;s.last_detector_confidence=d.confidence;}
            t.embedding=d.embedding?std::make_shared<const Embedding>(*d.embedding):nullptr;
            t.position_std=std::sqrt(std::max(s.axes[0].pp,s.axes[1].pp));
            // Appearance memory changes only on confident, unambiguous observations.
            if(pass==0&&d.appearance) {
                if(!s.appearance) s.appearance=d.appearance;
                else for(size_t k=0;k<s.appearance->size();++k) (*s.appearance)[k]=.95*(*s.appearance)[k]+.05*(*d.appearance)[k];
            }
            if(pass==0&&d.embedding) s.embedding=t.embedding;
        }
    }
    // Short, selected-phone-only image measurement bridge. It learns neither
    // appearance nor embeddings and cannot confirm, birth, or recover an ID.
    for(size_t i=0;i<states_.size();++i) {
        auto& s=states_[i];auto& t=s.public_track;
        const auto* v=visual_for(s);
        if(!matched[i]&&!ambiguous[i]&&v&&s.last_detector_confidence>=cfg_.control_confidence) {
            const auto& b=v->box;
            const double noise=std::max(.006,.12*std::max(b.w,b.h));
            const std::array<double,4> z={b.x+b.w/2,b.y+b.h/2,b.w,b.h};
            for(size_t a=0;a<4;++a)s.axes[a].correct(z[a],square(noise));
            t.box=b;t.last_seen_ms=f.capture_ms;t.observed=true;t.visual_observation=true;
            t.confidence=s.last_detector_confidence; // last detector confidence, NOT visual-match score
            t.position_std=std::sqrt(std::max(s.axes[0].pp,s.axes[1].pp));
            s.recovery_box=b;matched[i]=true;
        }
    }
    for(size_t i=0;i<states_.size();++i) {
        states_[i].public_track.ambiguous=ambiguous[i];
        // A tentative track needs consecutive observations (pinned: tentative_requires_continuity).
        // Considered and rejected 2026-09-13: tolerating one miss within max_gap_ms would have
        // confirmed a 37 px aerial person one processed frame earlier (VisDrone 054) but
        // contradicts that ghost-suppression rule; the click-retry protocol covers the case.
        if(!matched[i]&&!states_[i].public_track.confirmed) { states_[i].hits=0; states_[i].streak_start_ms=f.capture_ms; }
    }
    for(size_t j=0;j<dets.size()&&states_.size()<cfg_.max_tracks;++j) {
        if(used[j]||blocked[j]||dets[j].confidence<cfg_.birth_confidence) continue;
        // A candidate plausibly explained by an unobserved track is not another new object yet.
        bool pending=false;
        for(size_t i=0;i<matched.size();++i) if(!matched[i]&&pair_cost(i,j)<unmatched) { pending=true; break; }
        if(pending) continue;
        const auto& d=dets[j]; State s;
        s.public_track={next_id_++,d.label,d.box,d.confidence,f.capture_ms,std::sqrt(.001),false,true,false,{}};
        s.recovery_box=d.box;
        s.public_track.embedding=d.embedding?std::make_shared<const Embedding>(*d.embedding):nullptr;
        s.embedding=s.public_track.embedding;
        const std::array<double,4> values={d.box.x+d.box.w/2,d.box.y+d.box.h/2,d.box.w,d.box.h};
        for(size_t i=0;i<4;++i) s.axes[i].p=values[i];
        s.born_ms=f.capture_ms; s.streak_start_ms=f.capture_ms; s.appearance=d.appearance;
        if(d.confidence>=cfg_.control_confidence){s.last_detector_ms=f.capture_ms;s.last_detector_confidence=d.confidence;}
        states_.push_back(std::move(s));
    }

    if(target_lost_&&lost_memory_&&cfg_.reacquire_window_ms>0&&(!owner_||!owner_->active())) {
        auto& m=*lost_memory_;
        if(cfg_.recovery_diagnostics) {
            recovery_diagnostic_.emplace();
            recovery_diagnostic_->reference=m.box;
            recovery_diagnostic_->elapsed_ms=f.capture_ms-m.lost_ms;
            recovery_diagnostic_->status="expired";
        }
        if(f.capture_ms-m.lost_ms>cfg_.reacquire_window_ms) {
            m.pending_id=0;m.pending_hits=0;
        } else {
            const double extent=std::max({m.box.w,m.box.h,.025});
            const double radius=std::min(2.,(cfg_.reacquire_radius+
                cfg_.reacquire_radius_growth*(f.capture_ms-m.lost_ms)/1000.)*extent);
            if(recovery_diagnostic_)recovery_diagnostic_->radius=radius;
            // Count same-class confirmed rivals among tracks that COULD be the
            // returning target (born after its last observation, or its own id).
            // A track alive while the target was still observed is by construction
            // a different object, so it is neither a candidate nor a rival: the
            // target returning as the sole NEW track beside a continuously tracked
            // bystander is unambiguous. Without appearance evidence, two or more
            // eligible new tracks are refused (a crowd forces appearance).
            size_t class_peers=0;
            for(const auto& s:states_) {
                const auto& t=s.public_track;
                if(t.label==m.label&&t.confirmed&&t.observed&&!t.ambiguous&&
                   (s.born_ms>m.last_seen_ms||t.id==m.lost_id))++class_peers;
            }
            struct Cand{const State* s;double score;bool verified;};
            if(recovery_diagnostic_)recovery_diagnostic_->class_peers=class_peers;
            std::vector<Cand> cands;
            for(const auto& s:states_) {
                const auto& t=s.public_track;
                if(t.label!=m.label)continue;
                RecoveryCandidateDiagnostic* diagnostic=nullptr;
                if(recovery_diagnostic_) {
                    recovery_diagnostic_->candidates.push_back({t.id,t.box,"",{},{},{},t.observed});
                    diagnostic=&recovery_diagnostic_->candidates.back();
                }
                const auto note=[&](const char* reason){if(diagnostic)diagnostic->reason=reason;};
                if(!t.confirmed){note("unconfirmed");continue;}
                if(t.ambiguous){note("ambiguous_track");continue;}
                if(!t.observed){note("unobserved");continue;}
                if(t.confidence<cfg_.birth_confidence){note("confidence");continue;}
                // Conservatively exclude IDs alive during the last observation.
                // Birth time is not identity proof: MOT IDs can migrate. The
                // optional current-detection guard still considers their evidence.
                if(!(s.born_ms>m.last_seen_ms||t.id==m.lost_id)){note("preexisting_id");continue;}
                const double rw=std::max(t.box.w/std::max(m.box.w,1e-6),m.box.w/std::max(t.box.w,1e-6));
                const double rh=std::max(t.box.h/std::max(m.box.h,1e-6),m.box.h/std::max(t.box.h,1e-6));
                if(diagnostic)diagnostic->size_ratio=std::max(rw,rh);
                if(rw>cfg_.reacquire_size_ratio||rh>cfg_.reacquire_size_ratio){note("size");continue;}
                const double dx=(t.box.x+t.box.w/2)-(m.box.x+m.box.w/2);
                const double dy=(t.box.y+t.box.h/2)-(m.box.y+m.box.h/2);
                const double distance=std::sqrt(dx*dx+dy*dy);
                if(diagnostic)diagnostic->distance=distance;
                if(distance>radius){note("distance");continue;}
                const bool same_id=(t.id==m.lost_id);
                const bool visual=m.appearance&&s.appearance;
                double ad=.5;
                if(visual) {
                    ad=appearance_distance(*m.appearance,*s.appearance);
                    if(diagnostic)diagnostic->appearance_distance=ad;
                    if(ad>cfg_.appearance_gate){note("appearance");continue;}
                } else if(!same_id) {
                    // Fail closed: geometry alone cannot tell the returning target from
                    // someone who walked into its place during the outage (MOT17-09 came
                    // within one frame of binding a new entrant). A different id binds
                    // only on matching appearance evidence present on BOTH sides.
                    note("missing_appearance");continue;
                }
                // Rivals cannot be disambiguated without appearance; even with
                // appearance, crowd binding stays opt-in until live-validated.
                if(class_peers>1&&!(visual&&cfg_.reacquire_appearance_crowd)){note("crowd");continue;}
                note("eligible");
                cands.push_back({&s,.6*ad+.4*distance/radius,visual});
            }
            std::sort(cands.begin(),cands.end(),[](const Cand&a,const Cand&b){return a.score<b.score;});
            bool detection_veto=false;
            if(cfg_.car_recovery_detection_veto&&m.label=="car"&&!cands.empty()) {
                const auto& chosen=cands.front().s->public_track.box;
                std::optional<double> current_score,rival_score;
                std::optional<Box> rival_box;
                // Compare CURRENT descriptors on both sides. A track's averaged
                // history must not outrank current evidence simply because the
                // other MOT ID was excluded as pre-existing or unconfirmed.
                for(const auto& d:dets) {
                    if(d.label!=m.label||d.confidence<cfg_.control_confidence||!d.appearance||!m.appearance)continue;
                    const auto& b=d.box;
                    const double ratio=std::max({b.w/std::max(m.box.w,1e-6),m.box.w/std::max(b.w,1e-6),
                        b.h/std::max(m.box.h,1e-6),m.box.h/std::max(b.h,1e-6)});
                    const double distance=std::hypot(b.x+b.w/2-m.box.x-m.box.w/2,b.y+b.h/2-m.box.y-m.box.h/2);
                    if(ratio>cfg_.reacquire_size_ratio||distance>radius)continue;
                    const double ad=appearance_distance(*m.appearance,*d.appearance);
                    if(ad>cfg_.appearance_gate)continue;
                    const double score=.6*ad+.4*distance/radius;
                    const bool assigned=std::abs(b.x-chosen.x)<1e-9&&std::abs(b.y-chosen.y)<1e-9&&
                        std::abs(b.w-chosen.w)<1e-9&&std::abs(b.h-chosen.h)<1e-9;
                    if(assigned)current_score=score;
                    else if(!rival_score||score<*rival_score){rival_score=score;rival_box=b;}
                }
                detection_veto=!current_score||(rival_score&&*rival_score-*current_score<cfg_.ambiguity_margin);
                if(recovery_diagnostic_) {
                    recovery_diagnostic_->current_candidate_score=current_score;
                    recovery_diagnostic_->competing_detection_score=rival_score;
                    recovery_diagnostic_->competing_detection=rival_box;
                }
            }
            if(cands.empty()||detection_veto||(cands.size()>1&&cands[1].score-cands[0].score<cfg_.ambiguity_margin)) {
                if(recovery_diagnostic_)recovery_diagnostic_->status=cands.empty()?"no_candidate":
                    detection_veto?"competing_or_missing_current_evidence":"ambiguous_candidates";
                // A directly contradicted confirmation cannot accumulate through
                // the existing tolerated missing-frame gap.
                if(detection_veto){m.pending_id=0;m.pending_hits=0;}
                // Refused frame: pending survives only within the gap budget.
                if(m.pending_id&&f.capture_ms-m.pending_last_ms>cfg_.reacquire_gap_ms){m.pending_id=0;m.pending_hits=0;}
            } else {
                const auto& t=cands.front().s->public_track;
                if(m.pending_id!=t.id||f.capture_ms-m.pending_last_ms>cfg_.reacquire_gap_ms) {
                    m.pending_id=t.id;m.pending_hits=0;m.pending_start_ms=f.capture_ms;
                }
                ++m.pending_hits;m.pending_last_ms=f.capture_ms;
                if(recovery_diagnostic_) {
                    recovery_diagnostic_->status="confirming";
                    recovery_diagnostic_->pending_id=m.pending_id;
                    recovery_diagnostic_->pending_hits=m.pending_hits;
                    recovery_diagnostic_->pending_ms=f.capture_ms-m.pending_start_ms;
                }
                if(m.pending_hits>=cfg_.reacquire_hits&&f.capture_ms-m.pending_start_ms>=cfg_.reacquire_confirm_ms) {
                    if(recovery_diagnostic_)recovery_diagnostic_->status="recovered";
                    target_id_=t.id;target_class_=t.label;target_lost_=false;lost_memory_.reset();
                }
            }
        }
    }
    if(!armed_class_.empty()) {
        std::vector<uint64_t> candidates;
        for(const auto& s:states_) {
            const auto& t=s.public_track;
            if(t.label==armed_class_&&t.confirmed&&t.observed&&!t.ambiguous&&t.confidence>=cfg_.birth_confidence&&
               (!owner_||t.label!="person"||bool(t.embedding)))
                candidates.push_back(t.id);
        }
        if(candidates.size()==1) {
            auto it=std::find_if(states_.begin(),states_.end(),[&](const State& s){return s.public_track.id==candidates[0];});
            if(!owner_||armed_class_!="person"||owner_->select(it->public_track,epoch_+1,f.now_ms)) {
                target_id_=candidates[0];target_class_=armed_class_;armed_class_.clear();target_lost_=false;++epoch_;
                lost_memory_.reset();lock_id_=next_lock_id_++;
            }
        }
    }
    if(owner_&&owner_->active()) {
        std::vector<Track> candidates;for(const auto& s:states_)candidates.push_back(s.public_track);
        owner_->update(f.sequence,f.capture_ms,f.now_ms,true,candidates);
    }
    last_rejected_detections_=rejected;
    auto out=snapshot(f.now_ms);
    out.accepted=true; out.reason="accepted"; out.rejected_detections=rejected;
    history_.push_back(out);
    // Selection history needs geometry/visibility, not a copy of every 512D descriptor.
    for(auto& t:history_.back().tracks)t.embedding.reset();
    if(history_.size()>32) history_.pop_front();
    return out;
}

Output Tracker::snapshot(double now) const {
    const bool clock_ok=std::isfinite(now)&&now>=last_publish_ms_;
    if(!clock_ok) now=last_publish_ms_;
    Output o; o.sequence=sequence_; o.capture_ms=std::max(0.,last_capture_ms_); o.publish_ms=now;
    o.recovery=recovery_diagnostic_;
    o.association=association_diagnostic_;
    o.association_candidates=association_candidates_;
    o.timestamp_valid=last_timestamp_valid_&&clock_ok; o.reason="heartbeat";
    o.accepted=last_timestamp_valid_; o.rejected_detections=last_rejected_detections_;
    for(const auto& s:states_) if(now-s.public_track.last_seen_ms<=cfg_.coast_ms) {
        auto t=s.public_track;
        t.observed=t.observed&&(now-t.last_seen_ms<=cfg_.freshness_ms)&&o.timestamp_valid;
        o.tracks.push_back(t);
    }
    const std::optional<Box> pending=(pending_box_&&now-pending_ms_<=cfg_.selection_ms)?pending_box_:std::nullopt;
    auto& target=o.target; target.epoch=epoch_; target.label=target_class_; target.lock_id=lock_id_; target.pending_box=pending;
    if(owner_&&owner_->active()) {
        target=owner_->snapshot(clock_ok?now:std::numeric_limits<double>::quiet_NaN());
        target.lock_id=lock_id_; target.pending_box=pending; return o;
    }
    if(!target_id_) { target.state=armed_class_.empty()?"none":"acquiring"; target.reason=armed_class_.empty()?"not_selected":"waiting_for_unique_track"; return o; }
    auto it=std::find_if(o.tracks.begin(),o.tracks.end(),[&](const Track& t){return t.id==*target_id_;});
    if(target_lost_||it==o.tracks.end()) {
        target.state="lost";
        target.reason=!lost_memory_?"reselection_required":
            now-lost_memory_->lost_ms>cfg_.reacquire_window_ms?"reacquire_window_expired":"watching_for_return";
        // The pending streak is stamped in capture time; judge its continuity
        // against the latest capture, not the publish clock, or a tiled pipeline's
        // publish latency alone flaps the state between reacquiring and lost.
        if(lost_memory_&&lost_memory_->pending_id&&
           now-lost_memory_->lost_ms<=cfg_.reacquire_window_ms&&
           last_capture_ms_-lost_memory_->pending_last_ms<=cfg_.reacquire_gap_ms) {
            target.state="reacquiring";target.reason="verifying_returning_identity";
        }
        return o;
    }
    const auto& t=*it; target.id=t.id; target.box=t.box; target.position_std=t.position_std;
    if(t.label=="cell phone"&&!t.ambiguous) {
        const auto state=std::find_if(states_.begin(),states_.end(),[&](const State& s){return s.public_track.id==t.id;});
        if(state!=states_.end()) {
            target.search_measurement=state->recovery_box;
            target.search_capture_ms=t.last_seen_ms;
            target.search_vx=state->axes[0].v;target.search_vy=state->axes[1].v;
        }
    }
    target.observation_age_ms=std::max(0.,now-t.last_seen_ms);
    target.observation_valid=t.observed&&!t.ambiguous&&o.timestamp_valid;
    target.visual_observation=t.visual_observation&&target.observation_valid;
    target.control_valid=target.observation_valid&&t.confirmed&&t.confidence>=cfg_.control_confidence&&
                         target.observation_age_ms<=cfg_.freshness_ms&&t.position_std<=cfg_.max_position_std;
    target.state=t.ambiguous?"ambiguous":target.control_valid?"tracking":"coasting";
    target.reason=!o.timestamp_valid?"invalid_clock":t.ambiguous?"ambiguous_identity":
                  !t.observed?"missing_or_stale_observation":t.confidence<cfg_.control_confidence?"low_confidence":
                  t.position_std>cfg_.max_position_std?"uncertain_position":t.visual_observation?"visual_observed":"observed";
    return o;
}
bool Tracker::select(uint64_t id,uint64_t sequence,double now) {
    selection_error_="The selected track is not freshly observed. Wait for a live box.";
    auto o=snapshot(now);
    auto displayed=std::find_if(history_.begin(),history_.end(),[&](const Output& h){return h.sequence==sequence;});
    if(displayed==history_.end()||now-displayed->capture_ms>cfg_.selection_ms) {
        selection_error_="The displayed frame is too old. Refresh the preview and select again."; return false;
    }
    if(!o.timestamp_valid) {selection_error_="Fresh camera timestamps are unavailable.";return false;}
    const bool was_visible=std::any_of(displayed->tracks.begin(),displayed->tracks.end(),[&](const Track& t){
        return t.id==id&&t.confirmed&&t.observed&&!t.ambiguous;
    });
    if(!was_visible) return false;
    for(const auto& t:o.tracks) if(t.id==id&&t.confirmed&&t.observed&&!t.ambiguous&&t.confidence>=cfg_.control_confidence) {
        if(owner_) {
            if(t.label=="person"&&!owner_->select(t,epoch_+1,now)) {
                selection_error_="A fresh learned person descriptor is required for identity selection.";
                pending_box_=t.box; pending_ms_=now;   // steer the next identity crops to this person
                return false;
            }
            if(t.label!="person")owner_->clear();
        }
        target_id_=id; target_class_=t.label; armed_class_.clear(); target_lost_=false; ++epoch_;
        lost_memory_.reset(); lock_id_=next_lock_id_++; pending_box_.reset();
        selection_error_.clear();return true;
    }
    return false;
}
bool Tracker::select_point(double x,double y,uint64_t sequence,double now) {
    selection_error_="No confirmed live object at that point. Use target: phone for a phone.";
    if(!std::isfinite(x)||!std::isfinite(y)||x<0||x>1||y<0||y>1) return false;
    auto displayed=std::find_if(history_.begin(),history_.end(),[&](const Output& h){return h.sequence==sequence;});
    if(displayed==history_.end()) {selection_error_="The displayed frame is too old. Refresh the preview.";return false;}
    std::vector<const Track*> candidates;
    for(const auto& t:displayed->tracks) if(t.confirmed&&t.observed&&!t.ambiguous&&
        (armed_class_.empty()||t.label==armed_class_)&&
        x>=t.box.x&&x<=t.box.x+t.box.w&&y>=t.box.y&&y<=t.box.y+t.box.h) candidates.push_back(&t);
    if(candidates.empty()) return false;
    std::sort(candidates.begin(),candidates.end(),[](const Track* a,const Track* b){return a->box.w*a->box.h<b->box.w*b->box.h;});
    const auto& chosen=*candidates.front();
    for(size_t i=1;i<candidates.size();++i) {
        const auto& larger=*candidates[i];const auto& a=chosen.box;const auto& b=larger.box;
        // A phone clearly inside a person is selectable. Two overlapping people are still ambiguous.
        if(chosen.label==larger.label||a.w*a.h>=.5*b.w*b.h||
           a.x<b.x||a.y<b.y||a.x+a.w>b.x+b.w||a.y+a.h>b.y+b.h) {
            selection_error_="Overlapping objects are ambiguous. Choose a target class or a separate box.";return false;
        }
    }
    return select(chosen.id,sequence,now);
}
void Tracker::arm_class(const std::string& label) {
    if(label.empty()||label.size()>128) throw std::invalid_argument("target class required");
    unlock(); armed_class_=label;
}
void Tracker::unlock() {
    if(owner_)owner_->clear();
    target_id_.reset(); target_class_.clear(); armed_class_.clear(); target_lost_=false;
    lost_memory_.reset(); lock_id_=0; pending_box_.reset();
}
} // namespace garuda::fresh
