#include "garuda_tracking/json.hpp"
#include "garuda_tracking/vision.hpp"
#include "garuda_tracking/tiling.hpp"
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace garuda::fresh;
#define CHECK(expr) do {if(!(expr)) throw std::runtime_error(std::string(__func__)+":"+std::to_string(__LINE__)+": " #expr);}while(0)
Detection person(double x=.3,int color=-1,double conf=.9,std::string label="person") {
    Detection d{{x,.25,.12,.4},std::move(label),conf,{}};
    if(color>=0) {Appearance a{};a[size_t(color)]=1;d.appearance=a;}
    return d;
}
Frame frame(uint64_t n,double ts,std::vector<Detection> ds) {return {n,ts,ts+10,true,std::move(ds),{}};}
void warm(Tracker& t,std::vector<Detection> ds={person()}) {
    t.update(frame(1,1000,ds));t.update(frame(2,1060,ds));t.update(frame(3,1120,ds));
}
void observed_geometry_is_measurement() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    auto d=person(.32);d.box.h=.36;
    auto o=t.update(frame(4,1180,{d}));
    CHECK(o.tracks.size()==1);const auto& tr=o.tracks[0];
    CHECK(tr.observed);CHECK(tr.filtered_box.has_value());
    CHECK(std::abs(tr.box.x-d.box.x)<1e-12);CHECK(std::abs(tr.box.h-d.box.h)<1e-12);
    CHECK(std::abs(tr.filtered_box->h-d.box.h)>1e-6);
    CHECK(o.target.control_valid);CHECK(std::abs(o.target.box->h-d.box.h)<1e-12);
    auto j=output_json(o);CHECK(j["tracks"][0]["box_source"]=="detector_measurement");
    CHECK(!j["tracks"][0]["filtered_box"].is_null());
    o=t.update(frame(5,1240,{}));CHECK(!o.tracks[0].observed);
    CHECK(!o.tracks[0].filtered_box);CHECK(!o.target.control_valid);
    CHECK(output_json(o)["tracks"][0]["box_source"]=="prediction");
}
void car_embedding_budget_is_opt_in_and_resumes_for_person() {
    Config cfg;cfg.learned_person_identity=true;
    auto car=person(.1,2,.9,"car"),pedestrian=person(.6,3);
    Tracker tracker(cfg);warm(tracker,{car,pedestrian});CHECK(tracker.select(1,3,1130));
    auto target=tracker.snapshot(1130).target;
    CHECK(!defer_person_embeddings_for_car(target,cfg,false));
    CHECK(defer_person_embeddings_for_car(target,cfg,true));
    for(const std::string label:{"person","cell phone","dog",""}) {
        auto other=target;other.label=label;
        CHECK(!defer_person_embeddings_for_car(other,cfg,true));
    }
    for(const std::string state:{"lost","reacquiring","none"}) {
        auto other=target;other.state=state;
        CHECK(!defer_person_embeddings_for_car(other,cfg,true));
    }
    auto linked=cfg;linked.association_embedding_gate=.5;
    CHECK(!defer_person_embeddings_for_car(target,linked,true));
    auto remembered=target;remembered.identity_retained=true;
    CHECK(!defer_person_embeddings_for_car(remembered,cfg,true));
    tracker.update(frame(4,1180,{car,pedestrian}));
    CHECK(!tracker.select(2,4,1190)); // person has no fresh descriptor
    target=tracker.snapshot(1190).target;
    CHECK(target.pending_box);
    CHECK(!defer_person_embeddings_for_car(target,cfg,true));
    Embedding embedding{"test",{}};embedding.values[0]=1;pedestrian.embedding=embedding;
    tracker.update(frame(5,1240,{car,pedestrian}));
    CHECK(tracker.select(2,5,1250));
    CHECK(!defer_person_embeddings_for_car(tracker.snapshot(1250).target,cfg,true));
    tracker.unlock();CHECK(!defer_person_embeddings_for_car(tracker.snapshot(1250).target,cfg,true));
}
void car_gap_requires_reverification() {
    for(bool enabled:{false,true})for(const std::string label:{"car","cell phone"}) {
        Config cfg;cfg.max_gap_ms=500;cfg.car_gap_reverify=enabled;
        Tracker t(cfg);auto d=person(.3,2,.9,label);d.box={.3,.3,.03,.04};
        warm(t,{d});CHECK(t.select(1,3,1130));
        const auto initial=t.snapshot(1130).target;
        t.update(frame(4,1320,{}));t.update(frame(5,1520,{}));
        auto o=t.update(frame(6,1720,{d})); // 600 ms since the last observation
        const bool verify=enabled&&label=="car";
        CHECK(o.target.control_valid==!verify);
        CHECK(o.target.lock_id==initial.lock_id&&o.target.epoch==initial.epoch);
        if(verify)CHECK(o.target.reason=="verifying_returning_identity");
        o=t.update(frame(7,1920,{d}));CHECK(o.target.control_valid==!verify);
        o=t.update(frame(8,2120,{d}));CHECK(o.target.control_valid==!verify);
        o=t.update(frame(9,2320,{d}));CHECK(o.target.control_valid);
        CHECK(o.target.id==initial.id&&o.target.epoch==initial.epoch);
    }
}
void car_gap_verification_bounds() {
    Config cfg;cfg.max_gap_ms=500;cfg.car_gap_reverify=true;
    CHECK(config_from_json(Json{{"car_gap_reverify",true}}).car_gap_reverify);
    auto d=person(.3,2,.9,"car");d.box={.3,.3,.03,.04};
    Tracker boundary(cfg);warm(boundary,{d});CHECK(boundary.select(1,3,1130));
    CHECK(boundary.update(frame(4,1620,{d})).target.control_valid); // exact boundary is still continuation
    Tracker t(cfg);warm(t,{d});CHECK(t.select(1,3,1130));
    auto wrong=d;wrong.appearance=person(.3,20).appearance;
    for(int i=0;i<45;++i) {
        auto o=t.update(frame(4+i,1720+i*200,{wrong}));
        CHECK(!o.target.control_valid);
    }
    CHECK(t.snapshot(10530).target.reason=="reacquire_window_expired");
    bool refused=false;cfg.reacquire_window_ms=0;
    try{Tracker invalid(cfg);}catch(const std::invalid_argument&){refused=true;}
    CHECK(refused);
}
void car_extent_rejects_tiny_target_jump() {
    CHECK(config_from_json(Json{{"car_extent_gate",true}}).car_extent_gate);
    for(bool enabled:{false,true})for(const std::string label:{"car","cell phone"})for(double jump:{.005,.025}) {
        Config cfg;cfg.car_extent_gate=enabled;cfg.max_gap_ms=500;
        cfg.low_confidence=.25;cfg.recovery_diagnostics=true;
        Tracker t(cfg);auto d=person(.3,2,.9,label);d.box={.3,.3,.007,.014};
        warm(t,{d});CHECK(t.select(1,3,1130));
        auto weak=d;weak.confidence=.21;d.box.x+=jump;
        const auto o=t.update(frame(4,1320,{d,weak}));
        const bool refuse=enabled&&label=="car"&&jump==.025;
        CHECK(o.target.control_valid==!refuse);
        if(!enabled&&label=="car"&&jump==.025) {
            CHECK(o.association&&o.association->floor_scaled<cfg.max_center_distance);
            CHECK(o.association->extent_scaled>cfg.max_center_distance);
        }
    }
    Config cfg;cfg.car_extent_gate=true;Tracker t(cfg);
    auto d=person(.3,2,.9,"car");d.box={.3,.3,.007,.014};
    warm(t,{d});CHECK(t.select(1,3,1130));
    d.box.x+=.08;auto f=frame(4,1320,{d});f.motion={.08,0,true};
    CHECK(t.update(f).target.control_valid); // camera motion is compensated, not penalized
}
void elapsed_confirmation() {
    Tracker t;
    for(int i=1;i<=20;++i) {auto o=t.update(frame(i,1000+i,{person()}));CHECK(!o.tracks[0].confirmed);}
    auto o=t.update(frame(21,1200,{person()}));CHECK(o.tracks[0].confirmed);
}
void phone_gap_association_bounds() {
    CHECK(!Config{}.phone_gap_association);
    CHECK(config_from_json(Json{{"phone_gap_association",true}}).phone_gap_association);
    for(bool enabled:{false,true})for(const std::string label:{"cell phone","car","person"}) {
        Config cfg;cfg.max_gap_ms=500;cfg.phone_gap_association=enabled;
        cfg.recovery_diagnostics=true;
        Tracker t(cfg);auto d=person(.3,2,.9,label);d.box={.3,.3,.04,.12};
        warm(t,{d});CHECK(t.select(1,3,1130));
        const auto missing=t.update(frame(4,1420,{}));
        CHECK(!missing.target.observation_valid&&!missing.target.control_valid);
        d.box.x+=.11;
        const auto out=t.update(frame(5,1920,{d}));
        const bool expected=enabled&&label=="cell phone";
        CHECK(out.target.control_valid==expected);
        CHECK(out.association_candidates.size()==1);
        CHECK(out.association_candidates[0].phone_gap_bridge==expected);
        if(expected) {
            CHECK(out.target.id==1&&out.target.observation_valid);
            CHECK(std::abs(out.target.box->x-d.box.x)<1e-12);
        }
    }
    // Every bridge guard is fail-closed. Refusal leaves normal recovery intact.
    for(const std::string guard:{"no_appearance","wrong_appearance","weak_appearance",
                                "weak_detection","rival_detection","rival_track",
                                "late","expired","short_gap","absolute","size","distance"}) {
        Config cfg;cfg.max_gap_ms=500;cfg.phone_gap_association=true;
        Tracker t(cfg);auto d=person(.3,2,.9,"cell phone");d.box={.3,.3,.04,.12};
        if(guard=="absolute")d.box.w=.12;
        auto rival=d;rival.box.x=.75;
        warm(t,guard=="rival_track"?std::vector<Detection>{d,rival}:std::vector<Detection>{d});
        CHECK(t.select(1,3,1130));
        d.box.x+=.11;double gap=800;
        if(guard=="no_appearance")d.appearance.reset();
        if(guard=="wrong_appearance")d.appearance=person(.3,20).appearance;
        if(guard=="weak_appearance") { (*d.appearance)[2]=.5;(*d.appearance)[20]=.5; }
        if(guard=="weak_detection")d.confidence=.49;
        if(guard=="late")gap=1050;
        if(guard=="expired")gap=1250;
        if(guard=="short_gap")gap=300;
        if(guard=="absolute")d.box.x=.61;
        if(guard=="size")d.box.h=.31;
        if(guard=="distance")d.box.x=.50;
        auto out=t.update(frame(4,1120+gap,guard=="rival_detection"?
                                std::vector<Detection>{d,rival}:std::vector<Detection>{d}));
        CHECK(!out.target.control_valid&&!out.target.observation_valid);
    }
}
void phone_association_diagnostics_are_observational() {
    for(bool bridge:{false,true}) {
        Config cfg;cfg.max_gap_ms=500;cfg.phone_gap_association=bridge;
        Tracker plain(cfg);cfg.recovery_diagnostics=true;Tracker traced(cfg);
        auto d=person(.3,2,.9,"cell phone");d.box={.3,.3,.04,.12};
        warm(plain,{d});warm(traced,{d});
        CHECK(plain.select(1,3,1130)&&traced.select(1,3,1130));
        d.box.x+=.11;auto f=frame(4,1920,{d});
        auto a=plain.update(f),b=traced.update(f);
        CHECK(a.association_candidates.empty()&&b.association_candidates.size()==1);
        CHECK(b.association_candidates[0].gate==(bridge?"eligible":"center_distance"));
        auto ja=output_json(a),jb=output_json(b);
        ja.erase("association_candidates");jb.erase("association_candidates");CHECK(ja==jb);
    }
}
void recovery_diagnostics_are_observational() {
    CHECK(config_from_json(Json{{"recovery_diagnostics",true}}).recovery_diagnostics);
    for(bool evidence:{false,true})for(int color:{2,20}) {
        Config cfg;cfg.max_gap_ms=500;cfg.car_gap_reverify=true;
        cfg.car_recovery_detection_veto=evidence;
        Tracker plain(cfg);cfg.recovery_diagnostics=true;Tracker traced(cfg);
        auto d=person(.3,2,.9,"car");d.box={.3,.3,.03,.04};
        warm(plain,{d});warm(traced,{d});
        CHECK(plain.select(1,3,1130));CHECK(traced.select(1,3,1130));
        d.appearance=person(.3,color).appearance;
        bool saw_appearance=false,saw_confirm=false,saw_recovered=false,saw_expiry=false;
        for(int i=0;i<45;++i) {
            auto f=frame(4+i,1720+i*200,{d});
            auto a=plain.update(f),b=traced.update(f);
            CHECK(!a.recovery);
            auto ja=output_json(a),jb=output_json(b);
            ja.erase("recovery_diagnostic");jb.erase("recovery_diagnostic");
            ja.erase("association_diagnostic");jb.erase("association_diagnostic");
            ja.erase("association_candidates");jb.erase("association_candidates");CHECK(ja==jb);
            if(b.recovery) {
                saw_confirm|=b.recovery->status=="confirming";
                saw_recovered|=b.recovery->status=="recovered";
                saw_expiry|=b.recovery->status=="expired";
                for(const auto& c:b.recovery->candidates)if(c.reason=="appearance") {
                    CHECK(c.appearance_distance&&*c.appearance_distance>cfg.appearance_gate);
                    saw_appearance=true;
                }
            }
        }
        CHECK(color==2?(saw_confirm&&saw_recovered&&!saw_expiry):(saw_appearance&&saw_expiry&&!saw_recovered));
        CHECK(!traced.update(frame(100,100,{})).recovery); // rejected input cannot reuse stale diagnostics
    }
}
void target_and_watchdog() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    auto o=t.snapshot(1140);CHECK(o.target.control_valid);CHECK(o.target.epoch==1);
    o=t.snapshot(1400);CHECK(!o.target.control_valid);CHECK(o.target.state=="coasting");
    o=t.snapshot(2400);CHECK(o.target.state=="lost");CHECK(!o.target.id);
    t.update(frame(4,2500,{person()}));t.update(frame(5,2560,{person()}));
    // The returning object may enter gated re-acquire, but is never control-valid unverified.
    o=t.update(frame(6,2620,{person()}));CHECK(o.target.state!="tracking");CHECK(!o.target.control_valid);
    CHECK(o.tracks[0].id!=1);CHECK(t.select(o.tracks[0].id,6,2630));CHECK(t.snapshot(2630).target.epoch==2);
}
void class_isolation() {
    Tracker t;warm(t,{person(.3,-1,.9,"person"),person(.3,-1,.9,"cell phone")});
    auto o=t.update(frame(4,1180,{person(.3,-1,.9,"cell phone")}));
    CHECK(o.tracks.size()==2);CHECK(!o.tracks[0].observed);CHECK(o.tracks[0].label=="person");
    CHECK(o.tracks[1].observed);CHECK(o.tracks[1].label=="cell phone");
}
void low_score_recovery() {
    Tracker t;auto o=t.update(frame(1,1000,{person(.3,-1,.2)}));CHECK(o.tracks.empty());
    Tracker u;warm(u);CHECK(u.select(1,3,1130));
    o=u.update(frame(4,1180,{person(.305,-1,.2)}));CHECK(o.tracks.size()==1);CHECK(o.tracks[0].id==1);
    CHECK(o.tracks[0].observed);CHECK(!o.target.control_valid);CHECK(o.target.reason=="low_confidence");
    o=u.update(frame(5,1240,{person(.31)}));CHECK(o.target.control_valid);
}
void appearance_crossing() {
    Tracker t;warm(t,{person(.25,0),person(.55,1)});CHECK(t.select(1,3,1130));
    for(int i=1;i<=6;++i) {
        // Reverse detector ordering on every other frame; physical identities cross.
        auto a=person(.25+i*.03,0),b=person(.55-i*.03,1);
        auto o=t.update(frame(3+i,1120+i*60,i%2?std::vector<Detection>{b,a}:std::vector<Detection>{a,b}));
        CHECK(o.tracks.size()==2);CHECK(o.target.control_valid);CHECK(o.target.id==1);
    }
    auto o=t.snapshot(1490);CHECK(o.tracks[0].box.x>o.tracks[1].box.x);
}
Embedding synthetic_descriptor(double angle) {
    Embedding e;e.model="synthetic-test-v1";e.values[0]=std::cos(angle);e.values[1]=std::sin(angle);return e;
}
Detection described(double x,double angle) {Detection d=person(x,3);d.embedding=synthetic_descriptor(angle);return d;}
void embedding_crossing() {
    // Both people wear the SAME colour (identical histograms); only the learned
    // descriptor tells them apart when their paths cross.
    Config cfg;cfg.association_embedding_gate=.85;Tracker t(cfg);   // opt-in
    warm(t,{described(.25,0),described(.55,1.2)});CHECK(t.select(1,3,1130));
    for(int i=1;i<=6;++i) {
        auto a=described(.25+i*.03,0),b=described(.55-i*.03,1.2);
        auto o=t.update(frame(3+i,1120+i*60,i%2?std::vector<Detection>{b,a}:std::vector<Detection>{a,b}));
        CHECK(o.tracks.size()==2);CHECK(o.target.id==1);
        // At i==5 the two boxes coincide exactly and duplicate suppression keeps one
        // detection: the target coasts for that frame but its id is never swapped.
        if(i!=5)CHECK(o.target.control_valid);
    }
    auto o=t.snapshot(1490);CHECK(o.target.control_valid);CHECK(o.tracks[0].box.x>o.tracks[1].box.x);
    // A descriptor beyond the association gate cannot be the same object: the
    // old track goes unobserved and the detection is born as a new track.
    Tracker g(cfg);warm(g,{described(.3,0)});
    auto born=g.update(frame(4,1180,{described(.31,3.0)}));CHECK(born.tracks.size()==2);   // 1-cos(3.0)=1.99 > gate
    // Default (off): the same descriptor jump does not break the track's own stream.
    Tracker off;warm(off,{described(.3,0)});CHECK(off.update(frame(4,1180,{described(.31,3.0)})).tracks.size()==1);
    CHECK(std::count_if(born.tracks.begin(),born.tracks.end(),[](const Track& x){return x.observed;})==1);
}
void ambiguous_identity_holds() {
    Tracker t;warm(t,{person(.3),person(.46)});CHECK(t.select(1,3,1130));
    auto o=t.update(frame(4,1180,{person(.38)}));
    CHECK(o.target.state=="ambiguous");CHECK(!o.target.control_valid);CHECK(o.tracks.size()==2);
    CHECK(!t.select_point(.44,.4,4,1190));
}
// VisDrone-SOT 024 (2026-09-13 causal rerun): the detector's NMS runs at IoU 0.70, so one
// 30 px person regularly carries two boxes overlapping at ~0.67 (a wide and a narrow one).
// The tracker treated them as two rival explanations, flagged the track ambiguous, reset its
// confirmation streak, and the click at frame 16 found no confirmed track on the person.
void duplicate_boxes_on_one_object_still_confirm() {
    Tracker t;
    auto wide=person(.45,-1,.59);wide.box={.45,.5,.043,.1};
    auto narrow=person(.455,-1,.57);narrow.box={.455,.5,.029,.1};
    CHECK(iou(wide.box,narrow.box)>.6&&iou(wide.box,narrow.box)<.7);
    Output o;
    for(int i=1;i<=3;++i) {
        o=t.update(frame(i,1000+200*(i-1),{wide,narrow}));
        CHECK(o.tracks.size()==1);CHECK(o.tracks[0].observed);CHECK(!o.tracks[0].ambiguous);
        CHECK(o.rejected_detections==1);   // the runner-up box is a duplicate, not a second person
    }
    CHECK(o.tracks[0].confirmed);
    CHECK(t.select_point(.46,.55,3,1410));
}
// VisDrone-SOT 024 frame 4: an unconfirmed neighbour (B) had two equally plausible boxes, one
// of them the target's own box; blocking both cost the target (A) its observation and reset
// its confirmation streak although A's match was never in doubt.
void neighbour_ambiguity_does_not_block_a_clear_match() {
    Tracker t;
    auto box=[](double x,double conf=.9){auto d=person(x,-1,conf);d.box={x,.5,.03,.1};return d;};
    auto o=t.update(frame(1,1000,{box(.45),box(.42)}));CHECK(o.tracks.size()==2);
    for(int i=2;i<=3;++i) {
        // P is A's clear match and one of B's two symmetric candidates; Q is B's other one.
        o=t.update(frame(i,1000+100*(i-1),{box(.45+.002*(i-1)),box(.42-.032)}));
        CHECK(o.tracks.size()==2);
        const auto& a=o.tracks[0];const auto& b=o.tracks[1];
        CHECK(a.id==1);CHECK(a.observed);CHECK(!a.ambiguous);
        CHECK(b.id==2);CHECK(!b.observed);CHECK(b.ambiguous);
    }
    CHECK(o.tracks[0].confirmed);
}
// Aerial crowd (VisDrone 086 with the fine-tuned detector, 2026-09-13): 100 persons per frame,
// six OSNet crops per frame ordered by confidence, so the clicked person never carried a
// descriptor and every click was refused. A refused click must steer the next crops.
void refused_click_steers_identity_crops() {
    Config cfg;cfg.learned_person_identity=true;Tracker t(cfg);
    auto near=person(.6,-1,.6);near.box={.6,.5,.03,.1};   // the clicked, undescribed person
    auto loud=person(.2,-1,.95);loud.box={.2,.5,.12,.4};   // a more confident person elsewhere
    warm(t,{near,loud});
    CHECK(!t.select_point(.615,.55,3,1130));
    CHECK(t.selection_error().find("descriptor")!=std::string::npos);
    auto o=t.snapshot(1130);CHECK(o.target.pending_box.has_value());
    CHECK(std::abs(o.target.pending_box->x-near.box.x)<1e-9&&std::abs(o.target.pending_box->w-near.box.w)<1e-9);
    CHECK(!t.snapshot(1130+cfg.selection_ms+1).target.pending_box.has_value());   // a stale click steers nothing
    // The next frame carries a descriptor on that person (the node embedded it first): the retry takes.
    auto d=near;d.embedding=synthetic_descriptor(0);
    t.update(frame(4,1180,{d,loud}));
    CHECK(t.select_point(.615,.55,4,1190));
    CHECK(!t.snapshot(1190).target.pending_box.has_value());
    CHECK(t.snapshot(1190).target.state=="tracking");
}
// Aerial crowds exceed max_detections; the input cut must keep the most confident boxes.
void detection_cap_keeps_the_most_confident() {
    Config cfg;cfg.max_detections=4;Tracker t(cfg);
    std::vector<Detection> ds;
    for(int k=0;k<5;++k){auto d=person(.1+.15*k,-1,.55);ds.push_back(d);}
    auto best=person(.85,-1,.95);ds.push_back(best);   // sixth and last, the most confident
    Output o;for(int i=1;i<=3;++i)o=t.update(frame(i,1000+60*(i-1),ds));
    CHECK(o.rejected_detections==2);
    CHECK(std::any_of(o.tracks.begin(),o.tracks.end(),[&](const Track& x){return x.confirmed&&std::abs(x.box.x-.85)<1e-9;}));
}
void selection_requires_current_observation() {
    Tracker t;warm(t);CHECK(!t.select(1,2,1130));CHECK(!t.select(1,3,1400));
    CHECK(!t.select_point(-1,.5,3,1130));CHECK(t.select_point(.35,.4,3,1130));
    auto epoch=t.snapshot(1130).target.epoch;
    t.update(frame(4,1180,{}));CHECK(!t.select(1,4,1190));CHECK(t.snapshot(1190).target.epoch==epoch);
    t.unlock();CHECK(t.snapshot(1190).target.state=="none");
}
void acquisition_is_one_shot() {
    Tracker t;t.arm_class("person");warm(t,{person(.2),person(.7)});CHECK(!t.snapshot(1130).target.id);
    t.update(frame(4,2400,{person(.2)}));t.update(frame(5,2460,{person(.2)}));
    auto o=t.update(frame(6,2520,{person(.2)}));CHECK(o.target.control_valid);
    o=t.update(frame(7,5000,{person(.7)}));CHECK(o.target.state!="tracking");
    // A different same-class object can at most become a pending re-acquire
    // candidate; it never silently becomes the control target.
    t.update(frame(8,5060,{person(.7)}));o=t.update(frame(9,5120,{person(.7)}));
    CHECK(o.target.state!="tracking");CHECK(!o.target.control_valid);
}
void bad_time_never_refreshes() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    auto o=t.update(frame(3,1120,{person()}));CHECK(!o.accepted);CHECK(!o.target.control_valid);
    CHECK(!t.snapshot(1140).target.control_valid);
    auto f=frame(4,1180,{person()});f.timestamp_valid=false;o=t.update(f);CHECK(!o.accepted);
    f.timestamp_valid=true;f.now_ms=1179;o=t.update(f);CHECK(!o.accepted);
    f.now_ms=1500;o=t.update(f);CHECK(!o.accepted);CHECK(o.reason=="stale_frame");
    f.now_ms=1190;o=t.update(f);CHECK(o.accepted);CHECK(o.target.control_valid);
    CHECK(!t.snapshot(std::numeric_limits<double>::quiet_NaN()).target.control_valid);
}
void malformed_and_bounded() {
    Config cfg;cfg.max_tracks=2;cfg.max_detections=3;Tracker t(cfg);
    auto a=person();a.box.w=-1;auto b=person();b.confidence=std::numeric_limits<double>::quiet_NaN();
    auto c=person();c.appearance=Appearance{};
    auto o=t.update(frame(1,1000,{a,b,c,person()}));CHECK(o.tracks.empty());CHECK(o.rejected_detections==4);CHECK(t.snapshot(1010).accepted);CHECK(t.snapshot(1010).rejected_detections==4);
    o=t.update(frame(2,1060,{person(.1),person(.5),person(.8)}));CHECK(o.tracks.size()==2);
    bool thrown=false;try{Config bad;bad.coast_ms=-1;Tracker invalid(bad);}catch(const std::invalid_argument&){thrown=true;}CHECK(thrown);
    thrown=false;try{config_from_json({{"typo",1}});}catch(const std::invalid_argument&){thrown=true;}CHECK(thrown);
}
void tentative_requires_continuity() {
    Tracker t;t.update(frame(1,1000,{person()}));t.update(frame(2,1060,{}));
    auto o=t.update(frame(3,1120,{person()}));CHECK(!o.tracks[0].confirmed);
    o=t.update(frame(4,1180,{person()}));CHECK(!o.tracks[0].confirmed);
    o=t.update(frame(5,1240,{person()}));CHECK(o.tracks[0].confirmed);
}
void motion_compensated_pan() {
    Tracker t;warm(t,{person(.3,0)});CHECK(t.select(1,3,1130));
    auto f=frame(4,1180,{person(.5,0)});f.motion={.2,0,true};auto o=t.update(f);
    CHECK(o.target.control_valid);CHECK(o.target.id==1);CHECK(std::abs(o.tracks[0].box.x-.5)<.001);
}
void vision_stride_and_motion() {
    constexpr int W=160,H=90,S=168;
    std::vector<uint8_t> y(S*H),uv(S*H/2,128),shifted(S*H);
    uint32_t seed=7;
    for(int row=0;row<H;++row)for(int col=0;col<W;++col){seed=1664525*seed+1013904223;y[row*S+col]=uint8_t(seed>>24);}
    for(int row=0;row<H;++row)for(int col=0;col<W;++col)shifted[row*S+col]=col>=3?y[row*S+col-3]:0;
    Image image{y.data(),uv.data(),W,H,S,S,y.size(),uv.size()};CHECK(image.valid());
    auto a=describe(image,{.1,.1,.5,.7});CHECK(a);double sum=0;for(auto x:*a)sum+=x;CHECK(std::abs(sum-1)<1e-9);
    MotionEstimator estimator;CHECK(!estimator.update(image,{}).valid);
    image.y=shifted.data();auto motion=estimator.update(image,{});CHECK(motion.valid);CHECK(std::abs(motion.dx-3./W)<.001);CHECK(std::abs(motion.dy)<.001);
    image.y_bytes=10;CHECK(!image.valid());CHECK(!describe(image,{.1,.1,.5,.7}));CHECK(!estimator.update(image,{}).valid);
    image.y_bytes=y.size();std::fill(shifted.begin(),shifted.end(),128);CHECK(!estimator.update(image,{}).valid);CHECK(!estimator.update(image,{}).valid);
}
void letterbox_mapping_and_features() {
    auto g=FrameGeometry::make(1280,720,640,640,true);
    CHECK(g.content_y==140&&g.content_h==360);
    auto b=g.to_frame({.25,(140.+90)/640,.25,180./640});
    CHECK(std::abs(b.x-.25)<1e-9&&std::abs(b.y-.25)<1e-9&&std::abs(b.h-.5)<1e-9);
    std::vector<uint8_t> y(640*640,0),uv(640*320,0);
    for(int row=140;row<500;++row)for(int col=0;col<640;++col)y[row*640+col]=160;
    for(int row=70;row<250;++row)for(int col=0;col<640;++col)uv[row*640+col]=128;
    Image image{y.data(),uv.data(),640,640,640,640,y.size(),uv.size()};
    auto content=g.content(image);CHECK(content.valid());CHECK(content.height==360);
    auto a=describe(content,{0,0,1,1});CHECK(a);CHECK(std::abs((*a)[64+5]-.2)<1e-9);
    CHECK(std::abs((*a)[4*8+4]-.8)<1e-9);
    auto portrait=FrameGeometry::make(720,1280,640,640,true);
    CHECK(portrait.content(image).valid());CHECK(portrait.content_w==360);
    auto stretch=FrameGeometry::make(1280,720,640,640,false);
    CHECK(stretch.content_y==0);CHECK(stretch.to_frame({.1,.2,.3,.4}).y==.2);
}
void phone_inside_person_is_selectable() {
    auto body=person(.2,-1,.9);body.box={.2,.1,.5,.8};
    auto phone=person(.35,-1,.9,"cell phone");phone.box={.35,.35,.08,.2};
    Tracker t;warm(t,{body,phone});CHECK(t.select_point(.39,.4,3,1130));CHECK(t.snapshot(1130).target.label=="cell phone");
    phone.label="person";Tracker two;warm(two,{body,phone});CHECK(!two.select_point(.39,.4,3,1130));
    CHECK(two.selection_error().find("ambiguous")!=std::string::npos);
}
void phone_identity_crosses_person_boundary() {
    auto body=person(.3,1);body.box={.3,.15,.35,.75};
    auto phone=person(.4,0,.9,"cell phone");phone.box={.4,.4,.05,.1};
    Tracker t;warm(t,{body,phone});
    CHECK(t.select_point(.425,.45,3,1130));
    const auto id=t.snapshot(1130).target.id;
    const auto epoch=t.snapshot(1130).target.epoch;
    // Move through the person's right edge, then back through its left edge.
    // Remove the person entirely on the return leg: phone association is independent.
    for(int i=1;i<=80;++i) {
        phone.box.x=i<=30?.4+i*.015:.85-(i-30)*.015;
        std::vector<Detection> detections={phone};
        if(i<=30)detections.push_back(body);
        auto o=t.update(frame(3+i,1120+i*50,detections));
        if(!o.target.control_valid)std::cerr<<"boundary frame="<<i<<" x="<<phone.box.x<<" state="<<o.target.state<<" reason="<<o.target.reason<<" tracks="<<o.tracks.size()<<" predicted="<<(o.target.box?o.target.box->x:-1)<<"\n";
        CHECK(o.accepted);CHECK(o.target.id==id);CHECK(o.target.epoch==epoch);
        CHECK(o.target.control_valid);CHECK(o.target.label=="cell phone");
        CHECK(std::abs(o.target.box->x-phone.box.x)<.03);
    }
}
void reversing_phone_rejects_distractor() {
    auto phone=person(.4,0,.9,"cell phone");phone.box={.4,.4,.05,.1};
    auto other=phone;other.box.x=.8;(*other.appearance)[0]=0;(*other.appearance)[1]=1;
    Tracker t;warm(t,{phone,other});CHECK(t.select_point(.425,.45,3,1130));
    const auto id=t.snapshot(1130).target.id;
    for(int i=1;i<=50;++i) {
        phone.box.x=i<=20?.4+i*.01:.6-(i-20)*.01;
        other.box.x=.8-i*.01;
        auto o=t.update(frame(3+i,1120+i*50,i%2?std::vector<Detection>{phone,other}:std::vector<Detection>{other,phone}));
        CHECK(o.target.id==id);CHECK(o.target.control_valid);CHECK(o.tracks.size()==2);
        CHECK(std::abs(o.target.box->x-phone.box.x)<.03);
    }
    // A differently colored phone at the selected phone's exact location is not evidence of identity.
    other.box=phone.box;
    auto o=t.update(frame(54,3670,{other}));
    CHECK(o.target.id==id);CHECK(!o.target.control_valid);
}
void letterbox_rejects_stretched_pixels() {
    auto g=FrameGeometry::make(1280,720,640,640,true);
    std::vector<uint8_t> y(640*640,0),uv(640*320,128);
    Image img{y.data(),uv.data(),640,640,640,640,y.size(),uv.size()};
    CHECK(g.matches_layout(img));
    for(int row=140;row<500;++row)for(int col=0;col<640;++col)y[row*640+col]=uint8_t(col);
    CHECK(g.matches_layout(img)); // arbitrary picture within content
    y[8*640+8]=90;CHECK(!g.matches_layout(img)); // stretch picture in supposed padding
    CHECK(FrameGeometry::make(1280,720,640,640,false).matches_layout(img));
    y[8*640+8]=0;uv[8]=160;CHECK(!g.matches_layout(img));
}
void delayed_selection_requires_live_identity() {
    Tracker t;warm(t);
    for(int i=4;i<=10;++i)t.update(frame(i,1120+(i-3)*60,{person()}));
    CHECK(t.select(1,3,1550)); // older intent, but the selected identity is still observed now
    CHECK(t.snapshot(1550).target.control_valid);
    CHECK(!t.select(1,3,2200));CHECK(!t.snapshot(2200).target.control_valid);
}
void delayed_click_uses_displayed_box() {
    Tracker t;warm(t,{person(.3,0)});
    auto f=frame(4,1180,{person(.5,0)});f.motion={.2,0,true};t.update(f);
    CHECK(t.select_point(.35,.4,3,1190)); // click the older displayed box; current box has moved
    CHECK(t.snapshot(1190).target.id==1);
    CHECK(!t.select_point(.35,.4,3,1400));
}
void serialization_roundtrip() {
    auto f=frame(1,1000,{person(.3,2)});auto copy=frame_from_json(frame_json(f));CHECK(copy.detections[0].appearance==f.detections[0].appearance);
    Tracker t;warm(t);CHECK(command(t,{{"cmd","select"},{"id",1},{"sequence",3}},1130).at("ok")==true);
    auto o=output_json(t.snapshot(1130));CHECK(o["lock"]["control_valid"]==true);CHECK(o["distance"]["valid"]==false);
    CHECK(o["tracks"][0]["x"].get<double>()>300);CHECK(o["tracker_contract"]=="garuda.fresh.v1");
}
void reacquire_config_validation() {
    Config c;CHECK(c.reacquire_window_ms==7000);CHECK(c.reacquire_hits==3);
    c.reacquire_window_ms=0;Tracker ok(c);              // 0 disables, accepted
    c.reacquire_window_ms=-1;
    bool threw=false;try{Tracker t(c);}catch(const std::invalid_argument&){threw=true;}
    CHECK(threw);
    c=Config{};c.reacquire_size_ratio=.5;
    threw=false;try{Tracker t(c);}catch(const std::invalid_argument&){threw=true;}
    CHECK(threw);
}
void reacquire_memory_states() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    for(int i=0;i<30;++i) t.update(frame(4+i,1200+i*60,{}));   // > coast, track expires
    auto o=t.snapshot(3100);
    CHECK(o.target.state=="lost");CHECK(o.target.reason=="watching_for_return");
    o=t.snapshot(1130+9000);                                    // beyond 7 s window
    CHECK(o.target.state=="lost");CHECK(o.target.reason=="reacquire_window_expired");
}
void reacquire_disabled_matches_today() {
    Config c;c.reacquire_window_ms=0;Tracker t(c);warm(t);CHECK(t.select(1,3,1130));
    for(int i=0;i<30;++i) t.update(frame(4+i,1200+i*60,{}));
    auto o=t.snapshot(3100);
    CHECK(o.target.state=="lost");CHECK(o.target.reason=="reselection_required");
}
void lose(Tracker& t,int& seq,double& ms) {
    for(int i=0;i<30;++i){t.update(frame(seq++,ms,{}));ms+=60;}
}
void reacquire_rebinds_new_id() {
    // Appearance on both sides (the board always attaches histograms): matching
    // colour lets the lone returning person rebind.
    Tracker t;warm(t,{person(.3,2)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.32,2)}));ms+=60;}
    CHECK(o.target.state=="tracking");CHECK(o.target.id&&*o.target.id!=1);
    CHECK(o.target.epoch==1);CHECK(o.target.control_valid);
}
void phone_recovery_uses_measurement_not_coast_prediction() {
    // Shrinking before loss collapses predicted height during coasting. Recovery
    // must compare the returning phone with a measurement, not that prediction.
    for(int color:{2,20}) {
        Tracker t;
        auto phone=person(.4,2,.9,"cell phone");phone.box={.4,.4,.06,.16};
        warm(t,{phone});CHECK(t.select(1,3,1130));
        int seq=4;double ms=1180;
        for(int i=0;i<10;++i) {
            phone.box.h=.16-.008*(i+1);
            phone.box.y=.48-phone.box.h/2;
            auto o=t.update(frame(seq++,ms,{phone}));ms+=60;
            CHECK(o.target.control_valid);
        }
        lose(t,seq,ms);
        phone.appearance=person(.4,color).appearance;
        Output o;
        for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{phone}));ms+=60;}
        CHECK(o.target.control_valid==(color==2));
        if(color==2) {CHECK(o.target.id&&*o.target.id!=1);CHECK(o.target.lock_id==1);}
    }
}
void reacquire_refuses_preexisting_id() {
    Tracker t;warm(t,{person(.3),person(.7)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;
    for(int i=0;i<60;++i){t.update(frame(seq++,ms,{person(.7)}));ms+=60;}
    auto o=t.snapshot(ms);
    CHECK(o.target.state!="tracking");CHECK(!o.target.id);
}
void reacquire_gates_size() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Detection wrong=person(.31);wrong.box.w=.5;wrong.box.h=.9;wrong.box.y=.05;
    Output o;for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{wrong}));ms+=60;}
    CHECK(o.target.state!="tracking");
}
void reacquire_ambiguous_pair_refused() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.28),person(.44)}));ms+=60;}
    CHECK(o.target.state!="tracking");
}
void reacquire_gap_resets_pending() {
    Tracker t;warm(t,{person(.3,2)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    for(int i=0;i<5;++i){t.update(frame(seq++,ms,{person(.32,2)}));ms+=60;}
    ms+=400;                                          // > reacquire_gap_ms
    Output o;
    for(int i=0;i<5;++i){o=t.update(frame(seq++,ms,{person(.32,2)}));ms+=60;}
    CHECK(o.target.state=="reacquiring");             // pending restarted, span too short to bind
    for(int i=0;i<8;++i){o=t.update(frame(seq++,ms,{person(.32,2)}));ms+=60;}
    CHECK(o.target.state=="tracking");
}
void reacquire_appearance_gate() {
    Tracker t;warm(t,{person(.3,2)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.31,60)}));ms+=60;}
    CHECK(o.target.state!="tracking");
}
void phone_recovery_tolerates_bounded_confidence_gap() {
    // Tiled live frames arrive ~150-200 ms apart. A single low-confidence frame
    // must not restart the whole 600 ms verification interval on the desk profile.
    for(double gap:{250.,500.})for(int color:{2,20}) {
        Config cfg;cfg.reacquire_gap_ms=gap;
        Tracker t(cfg);
        auto phone=person(.4,2,.9,"cell phone");phone.box={.4,.4,.05,.1};
        warm(t,{phone});CHECK(t.select(1,3,1130));
        int seq=4;double ms=1180;lose(t,seq,ms);
        phone.appearance=person(.4,color).appearance;
        Output o;
        for(int i=0;i<6;++i) {
            phone.confidence=i==4?.2:.9;
            o=t.update(frame(seq++,ms,{phone}));ms+=200;
            if(i<5)CHECK(!o.target.control_valid);
        }
        CHECK(o.target.control_valid==(gap==500&&color==2));
        if(o.target.control_valid) {
            CHECK(o.target.lock_id==1);CHECK(o.target.id&&*o.target.id!=1);
            CHECK(!t.snapshot(ms+501).target.control_valid);
        }
    }
    // A longer gap still restarts pending verification; missing frames never bind.
    Config cfg;cfg.reacquire_gap_ms=500;Tracker t(cfg);
    auto phone=person(.4,2,.9,"cell phone");warm(t,{phone});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    for(int i=0;i<4;++i){CHECK(!t.update(frame(seq++,ms,{phone})).target.control_valid);ms+=200;}
    CHECK(!t.update(frame(seq++,ms+400,{})).target.control_valid);ms+=600;
    auto o=t.update(frame(seq++,ms,{phone}));CHECK(!o.target.control_valid);
    CHECK(o.target.state=="reacquiring");
}
void reacquire_binds_beside_tracked_bystander() {
    // Target A and bystander B tracked together; A leaves past the coast window
    // and returns as the only NEW confirmed person. B was alive while A was still
    // observed, so B cannot be A and must not count as a rival.
    Tracker t;warm(t,{person(.3,2),person(.7,20)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;
    for(int i=0;i<30;++i){t.update(frame(seq++,ms,{person(.7,20)}));ms+=60;}   // A gone > coast, B stays
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.32,2),person(.7,20)}));ms+=60;}
    CHECK(o.target.state=="tracking");
    CHECK(o.target.id&&*o.target.id!=1&&*o.target.id!=2);   // rebound to A-new, never to B
    CHECK(o.target.control_valid);
}
void car_recovery_checks_excluded_current_evidence() {
    CHECK(!Config{}.car_recovery_detection_veto);
    CHECK(config_from_json(Json{{"car_recovery_detection_veto",true}}).car_recovery_detection_veto);
    for(bool enabled:{false,true})for(const std::string label:{"car","cell phone"}) {
        Config cfg;cfg.car_recovery_detection_veto=enabled;cfg.recovery_diagnostics=true;
        cfg.reacquire_appearance_crowd=true;
        auto a=person(.3,2,.9,label),old=person(.36,2,.9,label),incoming=person(.42,2,.9,label);
        for(auto* d:{&a,&old,&incoming})d->box={d->box.x,.3,.02,.04};
        Tracker t(cfg);warm(t,{a,old});CHECK(t.select(1,3,1130));
        int seq=4;double ms=1180;
        for(int i=0;i<30;++i){t.update(frame(seq++,ms,{old}));ms+=60;}
        bool saw_veto=false;Output out;
        for(int i=0;i<20;++i) {
            out=t.update(frame(seq++,ms,{old,incoming}));ms+=60;
            if(out.recovery&&out.recovery->status=="competing_or_missing_current_evidence") {
                saw_veto=true;
                CHECK(out.recovery->current_candidate_score&&out.recovery->competing_detection_score);
                CHECK(*out.recovery->competing_detection_score<*out.recovery->current_candidate_score);
            }
        }
        const bool blocked=enabled&&label=="car";
        CHECK(saw_veto==blocked);CHECK(out.target.control_valid==!blocked);
        if(blocked) {
            // Remove the competing evidence. Do not inherit previous confirmation
            // hits; a complete fresh confirmation interval is still required.
            old.appearance=person(.36,20).appearance;
            for(int i=0;i<14;++i) {
                out=t.update(frame(seq++,ms,{old,incoming}));ms+=60;
                if(i<10)CHECK(!out.target.control_valid);
            }
            CHECK(out.target.control_valid&&out.target.id!=2);
        }
    }
}
void car_recovery_requires_current_candidate_appearance() {
    for(bool enabled:{false,true}) {
        Config cfg;cfg.car_gap_reverify=true;cfg.max_gap_ms=500;
        cfg.car_recovery_detection_veto=enabled;cfg.recovery_diagnostics=true;
        auto car=person(.3,2,.9,"car");Tracker t(cfg);warm(t,{car});CHECK(t.select(1,3,1130));
        car.appearance.reset();Output out;
        for(int i=0;i<5;++i) {
            out=t.update(frame(4+i,1720+i*200,{car}));
            if(enabled)CHECK(!out.target.control_valid);
        }
        CHECK(out.target.control_valid==!enabled);
        if(enabled) {
            CHECK(out.recovery&&out.recovery->status=="competing_or_missing_current_evidence");
            CHECK(!out.recovery->current_candidate_score);
        }
    }
}
void reacquire_refuses_different_id_without_appearance() {
    // No appearance on either side: a lone returning same-class object could be
    // a new entrant standing where the target was, so a different id must NOT
    // bind on geometry alone (fail closed).
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.32)}));ms+=60;}
    CHECK(o.target.state!="tracking");CHECK(!o.target.control_valid);
}
void reacquire_crowd_refused_by_default() {
    // Two same-class rivals present on return: geometry cannot disambiguate,
    // so re-acquire must refuse regardless of appearance, at the default.
    Tracker t;warm(t,{person(.3,2),person(.6,20)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.31,2),person(.62,20)}));ms+=60;}
    CHECK(o.target.state!="tracking");
}
void reacquire_crowd_binds_with_appearance_optin() {
    Config c;c.reacquire_appearance_crowd=true;Tracker t(c);
    warm(t,{person(.3,2),person(.6,20)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.31,2),person(.62,20)}));ms+=60;}
    CHECK(o.target.state=="tracking");           // rebinds to the colour-2 rival
    CHECK(o.target.box&&o.target.box->x<.45);    // near colour-2's location, not colour-20's
}
void reacquire_radius_reaches_small_walker() {
    // VisDrone-MOT case C: a 0.03-extent top-down walker returns 4 extents away
    // ~0.7 s after the coast expired. The radius is a recall gate (identity is
    // still the appearance rule), so at the default growth it must reach the
    // walker; at the old 0.5 extents/s it never did.
    auto small=[](double x){Detection d=person(x,2);d.box.w=.025;d.box.h=.03;d.box.y=.4;return d;};
    for(double growth:{2.0,0.5}) {
        Config c;c.reacquire_radius_growth=growth;Tracker t(c);
        warm(t,{small(.30)});CHECK(t.select(1,3,1130));
        int seq=4;double ms=1180;lose(t,seq,ms);
        Output o;for(int i=0;i<30;++i){o=t.update(frame(seq++,ms,{small(.42)}));ms+=60;}
        if(growth==2.0){CHECK(o.target.state=="tracking");CHECK(o.target.control_valid);}
        else CHECK(o.target.state!="tracking");
    }
}
void lock_id_stable_across_reacquire() {
    Tracker t;warm(t,{person(.3,2)});CHECK(t.select(1,3,1130));
    auto o=t.snapshot(1140);
    CHECK(o.target.lock_id!=0);
    const auto lid=o.target.lock_id;
    CHECK(o.target.id&&*o.target.id==1);                 // MOT id at selection
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output out;
    for(int i=0;i<25;++i){out=t.update(frame(seq++,ms,{person(.32,2)}));ms+=60;}
    CHECK(out.target.state=="tracking");
    CHECK(out.target.lock_id==lid);                      // STABLE across re-acquire
    CHECK(out.target.id&&*out.target.id!=1);             // MOT track id changed
    t.unlock();
    CHECK(t.snapshot(ms).target.lock_id==0);             // cleared on unlock
    CHECK(t.select(out.tracks.empty()?0:0,0,ms)==false); // no-op guard
}
void lock_id_new_selection_advances() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    const auto first=t.snapshot(1140).target.lock_id;
    CHECK(first!=0);
    t.unlock();
    // A second selection in the same tracker gets a distinct lock id.
    t.update(frame(4,1180,{person()}));t.update(frame(5,1240,{person()}));t.update(frame(6,1300,{person()}));
    auto o=t.snapshot(1310);
    CHECK(t.select(o.tracks.at(0).id,o.sequence,1310));
    CHECK(t.snapshot(1320).target.lock_id!=first);
}
void five_tile_layout_geometry() {
    auto tiles=five_tile_layout(1,1000,1280,720);
    CHECK(tiles.size()==5);
    for(size_t i=0;i<4;++i) {                                   // four corners
        CHECK(!tiles[i].full_frame);CHECK(tiles[i].valid());
        CHECK(tiles[i].w==768&&tiles[i].h==432);                // 0.6 of 1280x720
        CHECK(tiles[i].x%2==0&&tiles[i].y%2==0);
        CHECK(tiles[i].x+tiles[i].w<=1280&&tiles[i].y+tiles[i].h<=720);
    }
    CHECK(tiles[0].x==0&&tiles[0].y==0);
    CHECK(tiles[3].x==512&&tiles[3].y==288);                    // bottom-right corner start
    CHECK(tiles[4].full_frame&&tiles[4].x==0&&tiles[4].y==0&&tiles[4].w==1280&&tiles[4].h==720);
}
void tile_aggregation_class_aware_nms() {
    auto det=[](double x,double conf,std::string lab){return Detection{{x,.3,.1,.3},std::move(lab),conf,{}, {}};};
    // Same-class heavy overlap: keep the stronger one only.
    auto a=aggregate_tile_detections({det(.30,.6,"person"),det(.31,.9,"person")});
    CHECK(a.size()==1);CHECK(a[0].confidence==.9);
    // Different classes overlapping: both kept.
    auto b=aggregate_tile_detections({det(.30,.6,"person"),det(.30,.8,"cell phone")});
    CHECK(b.size()==2);
    // Same class, far apart: both kept.
    auto c=aggregate_tile_detections({det(.10,.6,"person"),det(.80,.7,"person")});
    CHECK(c.size()==2);
}
void tile_aggregation_collapses_cross_scale_duplicate() {
    // The regression: one person seen by the full tile (coarse, larger box) and
    // a corner tile (finer, smaller box, slightly offset) — low IoU but the
    // small box is largely inside the big one. Must collapse to ONE.
    Detection full{{.20,.10,.45,.80},"person",.80,{}, {}};   // coarse full-view box, area .36
    Detection corner{{.34,.25,.10,.36},"person",.95,{}, {}}; // fine corner box inside it, area .036
    full.region_id=4;full.region_full_frame=true;corner.region_id=0;
    CHECK(iou(full.box,corner.box)<.3);                      // IoU alone would keep both (~0.10)
    CHECK(intersection_over_min(full.box,corner.box)>.7);    // containment catches it (~1.0)
    auto merged=aggregate_tile_detections({full,corner});
    CHECK(merged.size()==1);CHECK(merged[0].confidence==.80);
    full.region_id=0;full.region_full_frame=false;corner.region_id=0;
    CHECK(aggregate_tile_detections({full,corner}).size()==2);
}
void tile_aggregation_overlap_zone_duplicate() {
    // Same person in two overlapping corner tiles: near-identical boxes -> one.
    Detection a{{.42,.30,.12,.40},"person",.90,{}, {}};
    Detection b{{.43,.31,.12,.40},"person",.88,{}, {}};
    CHECK(aggregate_tile_detections({a,b}).size()==1);
    // Two genuinely separate people (no overlap) survive.
    Detection p1{{.10,.30,.10,.40},"person",.9,{}, {}};
    Detection p2{{.70,.30,.10,.40},"person",.9,{}, {}};
    CHECK(aggregate_tile_detections({p1,p2}).size()==2);
}
int main() {
    const std::vector<std::pair<const char*,std::function<void()>>> cases={
        {"reacquire config",reacquire_config_validation},
        {"five tile layout",five_tile_layout_geometry},
        {"tile aggregation nms",tile_aggregation_class_aware_nms},
        {"tile cross-scale dedup",tile_aggregation_collapses_cross_scale_duplicate},
        {"tile overlap dedup",tile_aggregation_overlap_zone_duplicate},
        {"lock id stable",lock_id_stable_across_reacquire},
        {"lock id advances",lock_id_new_selection_advances},
        {"reacquire memory states",reacquire_memory_states},
        {"phone recovery measurement",phone_recovery_uses_measurement_not_coast_prediction},
        {"reacquire disabled",reacquire_disabled_matches_today},
        {"reacquire rebinds",reacquire_rebinds_new_id},
        {"reacquire preexisting id",reacquire_refuses_preexisting_id},
        {"reacquire size gate",reacquire_gates_size},
        {"reacquire ambiguity",reacquire_ambiguous_pair_refused},
        {"reacquire gap reset",reacquire_gap_resets_pending},
        {"reacquire appearance",reacquire_appearance_gate},
        {"phone recovery confidence gap",phone_recovery_tolerates_bounded_confidence_gap},
        {"reacquire beside bystander",reacquire_binds_beside_tracked_bystander},
        {"reacquire no-appearance refused",reacquire_refuses_different_id_without_appearance},
        {"reacquire crowd default",reacquire_crowd_refused_by_default},
        {"reacquire crowd optin",reacquire_crowd_binds_with_appearance_optin},
        {"reacquire radius small walker",reacquire_radius_reaches_small_walker},
        {"measured observation geometry",observed_geometry_is_measurement},
        {"car gap re-verification",car_gap_requires_reverification},
        {"car gap bounds",car_gap_verification_bounds},
        {"car extent jump",car_extent_rejects_tiny_target_jump},
        {"recovery diagnostics observational",recovery_diagnostics_are_observational},
        {"phone gap association bounds",phone_gap_association_bounds},
        {"phone diagnostics observational",phone_association_diagnostics_are_observational},
        {"car embedding budget and person reselection",car_embedding_budget_is_opt_in_and_resumes_for_person},
        {"car recovery competing current detections",car_recovery_checks_excluded_current_evidence},
        {"car recovery current descriptor required",car_recovery_requires_current_candidate_appearance},
        {"elapsed confirmation",elapsed_confirmation},{"target watchdog",target_and_watchdog},
        {"class isolation",class_isolation},{"phone boundary crossing",phone_identity_crosses_person_boundary},
        {"reversing phone distractor",reversing_phone_rejects_distractor},{"low score recovery",low_score_recovery},
        {"appearance crossing",appearance_crossing},{"embedding crossing",embedding_crossing},{"ambiguity hold",ambiguous_identity_holds},
        {"duplicate boxes confirm",duplicate_boxes_on_one_object_still_confirm},
        {"neighbour ambiguity",neighbour_ambiguity_does_not_block_a_clear_match},
        {"refused click steers crops",refused_click_steers_identity_crops},
        {"detection cap keeps best",detection_cap_keeps_the_most_confident},
        {"selection freshness",selection_requires_current_observation},{"one shot acquisition",acquisition_is_one_shot},
        {"bad clocks",bad_time_never_refreshes},{"bounded inputs",malformed_and_bounded},
        {"tentative continuity",tentative_requires_continuity},{"camera pan",motion_compensated_pan},
        {"vision buffers",vision_stride_and_motion},{"JSON contract",serialization_roundtrip},{"displayed click",delayed_click_uses_displayed_box},{"letterbox evidence",letterbox_mapping_and_features},{"actual letterbox pixels",letterbox_rejects_stretched_pixels},{"nested phone selection",phone_inside_person_is_selectable},{"selection intent age",delayed_selection_requires_live_identity}};
    int failures=0;
    for(const auto& test:cases)try{test.second();std::cout<<"PASS "<<test.first<<'\n';}catch(const std::exception& e){++failures;std::cerr<<"FAIL "<<test.first<<": "<<e.what()<<'\n';}
    return failures?1:0;
}
