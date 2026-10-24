#include "garuda_tracking/search_region.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace garuda::fresh;
#define CHECK(expr) do {if(!(expr))throw std::runtime_error(std::string(__func__)+":"+std::to_string(__LINE__)+": " #expr);}while(0)
Target phone() {
    Target t;t.id=7;t.epoch=1;t.label="cell phone";t.box=Box{.45,.35,.05,.15};
    t.observation_valid=t.control_valid=true;t.observation_age_ms=80;t.state="tracking";return t;
}
void mapping() {
    SearchRegion full{1,1000,1280,720,0,0,1280,720};CHECK(full.valid());
    CHECK(full.geometry().content_y==140&&full.geometry().content_h==360);
    const Box b{.45,.35,.05,.15};auto n=full.to_network(b);auto restored=full.to_frame(n);
    CHECK(std::abs(restored.y-b.y)<1e-12&&std::abs(restored.h-b.h)<1e-12);
    SearchRegion local{2,1050,1280,720,448,200,320,320,640,640,false};CHECK(local.valid());
    n=local.to_network(b);restored=local.to_frame(n);
    CHECK(std::abs(restored.x-b.x)<1e-12&&std::abs(restored.w-b.w)<1e-12);
    CHECK(std::abs(n.w/b.w-4)<1e-12); // 4x linear detector size versus full-frame letterbox
    CHECK(!local.cuts_object(n));CHECK(local.cuts_object({0,.2,.1,.1}));
    local.x=0;CHECK(!local.cuts_object({0,.2,.1,.1})); // actual camera edge is not a crop truncation
    local.w=321;CHECK(!local.valid());
    // Same source field of view into a 16:9 1024 input: no vertical padding.
    full.network_w=1024;full.network_h=576;CHECK(full.valid());
    CHECK(full.geometry().content_y==0&&full.geometry().content_h==576);
    n=full.to_network(b);restored=full.to_frame(n);
    CHECK(std::abs(n.x-b.x)<1e-12&&std::abs(n.y-b.y)<1e-12);
    CHECK(std::abs(restored.w-b.w)<1e-12&&std::abs(restored.h-b.h)<1e-12);
    SearchRegion tile{3,1100,1280,720,512,288,768,432,1024,576,false};
    const Box in_tile{.6,.6,.03,.1};n=tile.to_network(in_tile);restored=tile.to_frame(n);
    CHECK(std::abs(restored.x-in_tile.x)<1e-12&&std::abs(restored.y-in_tile.y)<1e-12);
    CHECK(!tile.cuts_object(n,.08));CHECK(tile.cuts_object({.01,.5,.03,.1},.08));
}
void schedule_and_loss() {
    SearchPlanner planner;auto t=phone();
    auto a=planner.next(1,1000,1280,720,t);CHECK(a.full_frame);
    a=planner.next(2,1050,1280,720,t);CHECK(!a.full_frame);CHECK(a.w==320);
    const auto old=a;
    t.box->x=.7;a=planner.next(3,1100,1280,720,t);CHECK(!a.full_frame&&a.x!=old.x);
    CHECK(old.x==448);CHECK(old.to_frame({.5,.5,0,0}).x==608./1280); // request keeps its own geometry
    a=planner.next(4,1150,1280,720,t);CHECK(!a.full_frame);
    a=planner.next(5,1200,1280,720,t);CHECK(a.full_frame);
    t.state="ambiguous";a=planner.next(6,1250,1280,720,t);CHECK(a.full_frame);
    t=phone();t.observation_age_ms=151;a=planner.next(7,1300,1280,720,t);CHECK(a.full_frame);
    t=phone();t.control_valid=false;a=planner.next(8,1350,1280,720,t);CHECK(a.full_frame);
    t=phone();a=planner.next(9,1400,1280,720,t);CHECK(!a.full_frame);
    t.epoch=2;a=planner.next(10,1450,1280,720,t);CHECK(a.full_frame);
    a=planner.next(11,1450,1280,720,t);CHECK(a.full_frame); // duplicate clock cannot reuse a crop
    t.box=Box{.2,.1,.5,.8};a=planner.next(12,1500,1280,720,t);CHECK(a.full_frame); // big person needs full view
    t=phone();t.position_std=.1;a=planner.next(13,1550,1280,720,t);CHECK(a.w>=620);
    t.position_std=.15;a=planner.next(14,1600,1280,720,t);CHECK(a.full_frame);
}
void boundaries_and_bad_inputs() {
    for(double x:{0.,.94})for(double y:{0.,.84}) {
        SearchPlanner planner;auto t=phone();t.box=Box{x,y,.05,.15};
        planner.next(1,1000,1280,720,t);auto r=planner.next(2,1050,1280,720,t);CHECK(r.valid());CHECK(!r.full_frame);
        auto b=r.to_network(*t.box);CHECK(b.x>=0&&b.y>=0&&b.x+b.w<=1&&b.y+b.h<=1);
    }
    SearchPlanner p;auto t=phone();p.next(1,1000,1280,720,t);
    t.box->x=std::numeric_limits<double>::quiet_NaN();CHECK(p.next(2,1050,1280,720,t).full_frame);
    bool bad=false;try{p.next(3,1100,1279,720,t);}catch(const std::invalid_argument&){bad=true;}CHECK(bad);
    bad=false;try{SearchConfig cfg;cfg.minimum_side=3;SearchPlanner invalid(cfg);}catch(const std::invalid_argument&){bad=true;}CHECK(bad);
}
Frame current(uint64_t sequence,bool observed=true) {
    Frame f;f.sequence=sequence;f.capture_ms=1000+50*sequence;f.now_ms=f.capture_ms+60;f.timestamp_valid=true;
    if(observed)f.detections.push_back({*phone().box,"cell phone",.6,{}, {}});
    return f;
}
void roi_deadlines_and_primary_verification() {
    RoiAssist assist;auto t=phone();
    CHECK(!assist.plan(current(1),t,1280,720));
    auto r=assist.plan(current(2),t,1280,720);CHECK(r&&!r->full_frame&&r->w==640);
    CHECK(!assist.plan(current(3),t,1280,720)); // at most one additional inference per 100ms
    CHECK(assist.plan(current(4),t,1280,720));
    CHECK(!assist.plan(current(5),t,1280,720)); // periodic full-frame-only opportunity
    unsigned requests=0;
    for(unsigned i=6;i<=18;++i) {
        auto f=current(i,false);r=assist.plan(f,t,1280,720);
        if(i>12)CHECK(!r); // 400ms after last primary evidence, despite a still-valid prior target
        if(r)++requests;
    }
    CHECK(requests>0);CHECK(assist.plan(current(19),t,1280,720)); // fresh primary evidence restores eligibility
    auto stale=current(20);stale.now_ms=stale.capture_ms+101;CHECK(!assist.plan(stale,t,1280,720));
    CHECK(!assist.plan(current(21),t,1280,720)); // reset requires an initial full frame
    t.epoch=2;CHECK(!assist.plan(current(22),t,1280,720));
    t.control_valid=false;CHECK(!assist.plan(current(23),t,1280,720));
}
void roi_mapping_and_merge_provenance() {
    RoiAssist assist;auto t=phone();assist.plan(current(1),t,1280,720);
    auto full=current(2);const auto region=*assist.plan(full,t,1280,720);
    Detection local{*t.box,"cell phone",.9,{}, {}};
    CHECK(assist.merge(full,region,{local},128)==1);CHECK(full.detections[0].confidence==.9); // better local box replaces
    CHECK(full.detections.size()==1);
    full.detections[0].confidence=.95;local.confidence=.9;
    CHECK(assist.merge(full,region,{local},128)==0);CHECK(full.detections[0].confidence==.95); // weaker local does not
    local.confidence=.9;
    full.detections.clear();CHECK(assist.merge(full,region,{local,local},128)==1);
    full.detections.clear();auto wrong=region;wrong.x+=2;CHECK(assist.merge(full,wrong,{local},128)==0);
    wrong=region;wrong.sequence++;CHECK(assist.merge(full,wrong,{local},128)==0);
    local.label="person";CHECK(assist.merge(full,region,{local},128)==0);
    local.label="cell phone";local.box=region.to_frame({0,.4,.2,.2});CHECK(assist.merge(full,region,{local},128)==0);
    local.box=*t.box;local.confidence=.1;CHECK(assist.merge(full,region,{local},128)==0);
    local.confidence=.8;CHECK(assist.merge(full,region,{local},0)==0);
    // The merge accepts every detection cap the tracker itself accepts (up to 512). A profile
    // raised to 512 for the aerial detector silently lost every ROI box (VisDrone 115: 0 of 22
    // ROI frames reached the tracker, 2026-09-14) while the old guard stopped at 256.
    full.detections.clear();CHECK(assist.merge(full,region,{local},512)==1);
    full.detections.clear();CHECK(assist.merge(full,region,{local},513)==0);
    auto duplicate=current(2);CHECK(!assist.plan(duplicate,t,1280,720));
    CHECK(assist.merge(full,region,{local},128)==0);
}
void roi_actual_tracker_short_gap() {
    Tracker tracker;tracker.arm_class("cell phone");RoiAssist assist;unsigned assisted=0;uint64_t epoch=0;
    for(unsigned i=1;i<=24;++i) {
        auto f=current(i,i<=5);auto previous=tracker.snapshot(f.now_ms);
        auto region=assist.plan(f,previous.target,1280,720);
        if(region) {
            const auto count=assist.merge(f,*region,{{*phone().box,"cell phone",.8,{}, {}}},128);
            if(i>5)assisted+=count;
        }
        const auto output=tracker.update(f);CHECK(output.accepted);
        if(i==5){CHECK(output.target.control_valid);epoch=output.target.epoch;}
        if(i==6){CHECK(output.target.control_valid);CHECK(output.target.epoch==epoch);}
        if(i>14)CHECK(!region); // ROI detections did not renew primary evidence
        if(i>=18)CHECK(!output.target.control_valid);
    }
    CHECK(assisted>=2); // real tracker can search after a missing observation, without authorizing prediction
}
void roi_follows_selected_class() {
    // The follow target is whatever the owner locked; the ROI assist must plan
    // and merge for that class, not only for a phone.
    RoiAssist assist;auto t=phone();t.label="person";t.box=Box{.45,.30,.06,.20};
    Frame f1;f1.sequence=1;f1.capture_ms=1050;f1.now_ms=1110;f1.timestamp_valid=true;
    f1.detections.push_back({*t.box,"person",.6,{}, {}});
    CHECK(!assist.plan(f1,t,1280,720));
    Frame f2=f1;f2.sequence=2;f2.capture_ms=1100;f2.now_ms=1160;
    const auto region=assist.plan(f2,t,1280,720);CHECK(region&&!region->full_frame);
    Detection local{*t.box,"person",.9,{}, {}};
    f2.detections.clear();CHECK(assist.merge(f2,*region,{local},128)==1);
    local.label="cell phone";CHECK(assist.merge(f2,*region,{local},128)==0);
    Target none=t;none.label="";Frame f3=f2;f3.sequence=3;f3.capture_ms=1150;f3.now_ms=1210;
    CHECK(!assist.plan(f3,none,1280,720));
}
void audited_handover() {
    SearchRegion r{1,1000,1280,720,0,288,768,432,640,640,false};
    CHECK(r.cuts_object(r.to_network({.2,.4,.05,.1}),.08));
    auto t=phone();t.label="person";t.box=Box{.45,.3,.06,.2};
    RoiAssist assist(400,1600);FollowSchedule schedule;
    CHECK(schedule.global_required(t,1000));
    assist.observe_global(t,1000);schedule.observe(true,false,t,1000);
    CHECK(schedule.global_required(t,1050));
    auto f=current(1,false);f.now_ms=f.capture_ms+101;
    CHECK(!assist.plan(f,t,1280,720)); // initial planner full opportunity
    f=current(2,false);f.now_ms=f.capture_ms+101;
    CHECK(assist.plan(f,t,1280,720)); // acquisition seed suffices, coarse detector missed
    f=current(7,false);f.now_ms=f.capture_ms+280;t.observation_age_ms=350;
    CHECK(assist.plan(f,t,1280,720)); // >200ms global cadence must not starve ROI forever
    schedule.observe(false,true,t,1100);CHECK(schedule.global_required(t,1150));
    schedule.observe(false,true,t,1200);CHECK(!schedule.global_required(t,1250));
    CHECK(schedule.global_required(t,1800)); // bounded independent global refresh
    t.epoch++;CHECK(schedule.global_required(t,1850));
    t.box=Box{.2,.1,.4,.8};CHECK(!schedule.global_required(t,3000));
    t.control_valid=false;CHECK(schedule.global_required(t,3050)); // primary loss restores corner search
}
// Tiled aerial search runs ~250 ms per processed frame with a periodic full-only plan in
// between, so two verified ROI passes land ~750 ms apart; the default 500 ms window never
// retires the corners (VisDrone 115: ROI verified 11 of 12 times, handover 0 of 45 frames).
void handover_window_follows_the_cadence() {
    auto t=phone();t.label="car";t.box=Box{.45,.3,.03,.05};
    FollowSchedule fast,slow(800,1500);
    // The full view runs on every processed frame (global observed each time); the ROI verified on the last two.
    for(auto* s:{&fast,&slow}) {s->observe(true,false,t,1000);s->observe(true,true,t,1250);s->observe(true,true,t,2000);}
    CHECK(fast.global_required(t,2050));    // 750 ms apart: the default window restarts the count
    CHECK(!slow.global_required(t,2050));   // the aerial window accepts it and retires the corners
    CHECK(slow.global_required(t,2900));    // the bounded independent global refresh still happens
    slow.observe(true,true,t,2900);
    CHECK(!slow.global_required(t,2950));   // local evidence 900 ms apart stays inside 1500 ms
    slow.observe(true,true,t,4500);CHECK(slow.global_required(t,4550));   // 1600 ms local gap: recount from one hit
}
void native_context_scales_the_window() {
    // Sensor-frame planning: the phone (324 px extent at 3840x2160) gets a 2.5x window by default,
    // a 6x window when the profile asks for it, and no local crop at all once the window would
    // not fit (7x = 2268 > 2160); an out-of-range factor is refused at construction.
    auto t=phone();
    RoiAssist paired;paired.plan(current(1),t,3840,2160);auto r=paired.plan(current(2),t,3840,2160);CHECK(r&&r->w==810);
    RoiAssist wide(100,400,6);wide.plan(current(1),t,3840,2160);r=wide.plan(current(2),t,3840,2160);CHECK(r&&r->w==1944&&r->h==1944);
    RoiAssist widest(100,400,7);widest.plan(current(1),t,3840,2160);CHECK(!widest.plan(current(2),t,3840,2160));
    CHECK(widest.reason()=="geometry_or_periodic_full");
    bool refused=false;try{RoiAssist bad(100,400,9);}catch(const std::invalid_argument&){refused=true;}CHECK(refused);
}
void predictive_phone_search() {
    SearchPlanner p(SearchConfig{800,400,2.5,320,true,true});auto t=phone();
    t.search_measurement=t.box;t.search_capture_ms=1000;t.search_vx=.5;
    p.next(1,1000,1280,720,t);
    const auto r=p.next(2,1100,1280,720,t);
    CHECK(!r.full_frame&&r.w>=384);
    CHECK(r.x+r.w/2>608); // sweep toward motion, while retaining the measurement
    CHECK(r.x<=t.box->x*1280&&r.x+r.w>=(t.box->x+.05+t.box->w)*1280);
    CHECK(t.box->x==.45&&t.control_valid); // input/observation contract is unchanged
    t.search_vx=-.5;const auto reverse=p.next(3,1150,1280,720,t);
    CHECK(reverse.x+reverse.w/2<608);
    t.search_vx=100;CHECK(p.next(4,1200,1280,720,t).w<=512); // displacement capped
    const auto expired=p.next(5,1300,1280,720,t);CHECK(expired.w==320);
    t.search_capture_ms=1400;CHECK(p.next(6,1350,1280,720,t).w==320);
    t.search_capture_ms=1300;t.search_vx=std::numeric_limits<double>::quiet_NaN();
    CHECK(p.next(7,1400,1280,720,t).w==320);
    t.search_vx=.5;t.label="person";CHECK(p.next(8,1450,1280,720,t).w==320);
}
void bounded_phone_miss() {
    FollowSchedule s(800,500,250);auto t=phone();
    s.observe(true,true,t,1000);s.observe(false,true,t,1100);
    t.control_valid=t.observation_valid=false;t.state="coasting";t.reason="low_confidence";
    s.observe(false,false,t,1150); // first miss arrives after a tracking-state scheduling decision
    CHECK(!s.global_required(t,1200));CHECK(s.reason()=="bounded_phone_miss");
    s.observe(false,false,t,1200);
    CHECK(!s.global_required(t,1350));CHECK(s.global_required(t,1351));
    t.state="ambiguous";CHECK(s.global_required(t,1200));
    t.state="coasting";t.label="person";CHECK(s.global_required(t,1200));
    t.label="cell phone";t.observation_age_ms=251;CHECK(s.global_required(t,1200));
    t.observation_age_ms=80;t.position_std=.13;CHECK(s.global_required(t,1200));
    t.position_std=0;t.epoch++;CHECK(s.global_required(t,1200));
    FollowSchedule refresh(200,500,250);t=phone();
    refresh.observe(true,true,t,1000);refresh.observe(false,true,t,1100);
    t.control_valid=t.observation_valid=false;t.state="coasting";t.reason="low_confidence";
    CHECK(refresh.global_required(t,1200)); // independent refresh always wins
    bool bad=false;try{FollowSchedule invalid(800,500,251);}catch(const std::invalid_argument&){bad=true;}CHECK(bad);
}
void measured_phone_search_motion() {
    Tracker tracker;tracker.arm_class("cell phone");
    Output out;
    for(unsigned i=1;i<=12;++i) {
        auto f=current(i);f.detections[0].box.x=.35+.005*i;
        out=tracker.update(f);
    }
    CHECK(out.target.control_valid&&out.target.search_measurement);
    CHECK(out.target.search_capture_ms==1600&&out.target.search_vx>0);
    CHECK(std::abs(out.target.search_measurement->x-out.target.box->x)<1e-12);
    const auto measured=*out.target.search_measurement;
    out=tracker.update(current(13,false));
    CHECK(!out.target.control_valid&&!out.target.observation_valid);
    CHECK(out.target.search_capture_ms==1600);
    CHECK(out.target.search_measurement->x==measured.x);
    auto later=tracker.snapshot(1700);
    CHECK(!later.target.control_valid&&later.target.search_capture_ms==1600);
}
void captured_phone_miss_schedule() {
    // Capture05 samples2..9: verified local hits at 217074.613,217374.616,
    // 217641.284 and217774.624; low confidence at217874.620, broad search
    // at217941.287. This isolates scheduler decisions, NOT detector/identity
    // replay: observations stay fixed and pre-capture state is unavailable.
    FollowSchedule baseline, candidate(800,500,250);
    auto t=phone();
    for(auto* s:{&baseline,&candidate}) {
        s->observe(true,true,t,217074.613);
        s->observe(true,false,t,217274.612);
        s->observe(true,true,t,217374.616);
        CHECK(!s->global_required(t,217641.284));
        s->observe(false,true,t,217641.284);
        s->observe(false,false,t,217741.283);
        s->observe(false,true,t,217774.624);
    }
    t.control_valid=t.observation_valid=false;t.state="coasting";
    t.reason="low_confidence";t.observation_age_ms=100;
    baseline.observe(false,false,t,217874.620);
    candidate.observe(false,false,t,217874.620);
    CHECK(baseline.global_required(t,217941.287));
    CHECK(!candidate.global_required(t,217941.287));
    CHECK(candidate.reason()=="bounded_phone_miss");
    CHECK(!t.control_valid&&!t.observation_valid); // never fabricate an observation
    CHECK(candidate.global_required(t,218024.625)); // 250ms budget expires
    auto rival=t;rival.state="ambiguous";rival.reason="ambiguous_candidates";
    CHECK(candidate.global_required(rival,217941.287));
    rival=t;rival.label="car";CHECK(candidate.global_required(rival,217941.287));
    rival=t;rival.label="person";CHECK(candidate.global_required(rival,217941.287));
    rival=t;rival.id.reset();CHECK(candidate.global_required(rival,217941.287));
    rival=t;rival.epoch++;CHECK(candidate.global_required(rival,217941.287));
    FollowSchedule disabled;disabled.observe(true,true,phone(),1000);
    disabled.observe(false,true,phone(),1100);
    CHECK(disabled.global_required(t,1150)); // existing profiles remain default-off
}
void relative_boundary_candidate() {
    SearchRegion r{1,1000,1280,720,0,288,768,432,640,640,false};
    Box phone{630.6883/1280,305.6876/720,(677.6749-630.6883)/1280,(399.8839-305.6876)/720};
    const auto n=r.to_network(phone);
    CHECK(r.cuts_object(n,.08));CHECK(!r.cuts_object_relative(n));
    auto clipped=n;clipped.y=140./640;CHECK(r.cuts_object_relative(clipped));
    clipped.y=(140+360*.014)/640;CHECK(r.cuts_object_relative(clipped));
    auto invalid=n;invalid.w=std::numeric_limits<double>::quiet_NaN();CHECK(r.cuts_object_relative(invalid));
    invalid=n;invalid.h=0;CHECK(r.cuts_object_relative(invalid));
    // Camera edges are not crop cuts, but interior right and bottom edges are.
    r.x=512;r.y=0;
    CHECK(r.cuts_object_relative({0,.4,.1,.1}));
    CHECK(!r.cuts_object_relative({.8,140./640,.1,.1}));
    r.x=0;r.y=0;
    CHECK(r.cuts_object_relative({.95,.4,.05,.1}));
    CHECK(r.cuts_object_relative({.4,(140+360)/640.-.1,.1,.1}));
    r={1,1000,1280,720,0,0,1280,720};CHECK(!r.cuts_object_relative({0,0,.1,.1}));
}
int main() {try{mapping();schedule_and_loss();boundaries_and_bad_inputs();roi_deadlines_and_primary_verification();roi_mapping_and_merge_provenance();roi_actual_tracker_short_gap();roi_follows_selected_class();audited_handover();handover_window_follows_the_cadence();native_context_scales_the_window();predictive_phone_search();bounded_phone_miss();measured_phone_search_motion();captured_phone_miss_schedule();relative_boundary_candidate();std::cout<<"15 search region scenarios passed\n";}
catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
