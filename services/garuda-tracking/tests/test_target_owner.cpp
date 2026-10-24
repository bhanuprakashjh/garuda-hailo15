#include "garuda_tracking/target_owner.hpp"
#include "garuda_tracking/json.hpp"
#include "garuda_tracking/vision.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace garuda::fresh;
#define CHECK(expr) do {if(!(expr))throw std::runtime_error(std::string(__func__)+":"+std::to_string(__LINE__)+": " #expr);}while(0)
Embedding feature(double angle=0) {
    Embedding e;e.model="synthetic-test-v1";e.values[0]=std::cos(angle);e.values[1]=std::sin(angle);return e;
}
Track observed(uint64_t id,double capture,double angle=0) {
    Track t{id,"person",{.3,.2,.2,.6},.9,capture,.01,true,true,false};t.embedding=std::make_shared<const Embedding>(feature(angle));return t;
}
void durable_identity() {
    TargetOwner owner;CHECK(owner.select(observed(10,1000),7,1010));
    owner.update(2,1060,1070,true,{observed(10,1060)});CHECK(owner.snapshot(1070).control_valid);
    owner.update(3,3000,3010,true,{});
    auto o=owner.snapshot(3010);CHECK(o.identity_retained);CHECK(!o.id);CHECK(!o.control_valid);CHECK(o.epoch==7);
    // Wrong person at the original position cannot be substituted, even with the original MOT ID.
    owner.update(4,3060,3070,true,{observed(10,3060,1.5)});CHECK(!owner.snapshot(3070).control_valid);
    for(int k=0;k<3;++k) {
        owner.update(5+k,3120+60*k,3130+60*k,true,{observed(99,3120+60*k,.2)});
        o=owner.snapshot(3130+60*k);CHECK(o.control_valid==(k==2));CHECK(o.epoch==7);
    }
    CHECK(o.id==99);CHECK(o.reason=="identity_verified");
    CHECK(!owner.snapshot(3600).control_valid);CHECK(owner.snapshot(3600).identity_retained);
    CHECK(!owner.snapshot(14000).identity_retained);CHECK(owner.snapshot(14000).state=="lost");
    owner.update(8,14000,14010,true,{observed(3,14000)});CHECK(!owner.snapshot(14010).control_valid);
    owner.clear();CHECK(!owner.active());CHECK(owner.snapshot(14010).state=="none");
}
void measured_cadence_keeps_positive_identity_not_prediction() {
    IdentityConfig cfg;cfg.freshness_ms=500;cfg.continuation_ms=cfg.reacquire_gap_ms=500;
    TargetOwner owner(cfg);CHECK(owner.select(observed(1,1000),1,1280));
    auto unknown=observed(2,1300);unknown.embedding.reset();
    owner.update(1,1300,1580,true,{observed(1,1300),unknown});CHECK(owner.snapshot(1580).control_valid);
    owner.update(2,1600,1880,true,{observed(1,1600,1.5)});CHECK(!owner.snapshot(1880).control_valid);
    owner.update(3,1900,2180,true,{observed(9,1900)});CHECK(!owner.snapshot(2180).control_valid);
    owner.update(4,2200,2480,true,{observed(9,2200)});CHECK(!owner.snapshot(2480).control_valid);
    owner.update(5,2500,2780,true,{observed(9,2500)});CHECK(owner.snapshot(2780).control_valid);
    CHECK(!owner.snapshot(3101).control_valid); // no new observation cannot renew validity
    Config mapped=config_from_json(Json{{"learned_person_identity",true},{"identity_continuation_ms",500},{"identity_reacquire_gap_ms",500}});
    CHECK(mapped.identity_continuation_ms==500&&mapped.identity_reacquire_gap_ms==500);
    mapped.identity_continuation_ms=501;bool bad=false;try{Tracker t(mapped);}catch(const std::invalid_argument&){bad=true;}CHECK(bad);
}
void ambiguity_and_incomplete_evidence() {
    TargetOwner owner;CHECK(owner.select(observed(1,1000),1,1010));
    owner.update(1,1060,1070,true,{observed(1,1060),observed(2,1060,.1)});
    auto o=owner.snapshot(1070);CHECK(o.state=="ambiguous");CHECK(!o.control_valid);
    // An undescribed bystander cannot block the bound track's own verified continuation
    // (the target itself is positively re-identified within continuation_ms) ...
    auto unknown=observed(2,1120,1.5);unknown.embedding.reset();
    owner.update(2,1120,1130,true,{observed(1,1120),unknown});CHECK(owner.snapshot(1130).control_valid);
    unknown=observed(2,1180,1.5);auto incompatible=feature(1.5);incompatible.model="different-model";
    unknown.embedding=std::make_shared<const Embedding>(incompatible);
    owner.update(3,1180,1190,true,{observed(1,1180),unknown});CHECK(owner.snapshot(1190).control_valid);
    // Descriptors distinguish a real negative; it does not block the actual target forever.
    for(int k=0;k<3;++k)owner.update(4+k,1240+60*k,1250+60*k,true,{observed(1,1240+60*k),observed(2,1240+60*k,1.5)});
    CHECK(owner.snapshot(1370).control_valid);
}
void undescribed_bystander_blocks_rebinding_only() {
    // ... but after a loss, binding to a DIFFERENT id still needs every visible
    // person described: the undescribed one could be the true target.
    TargetOwner owner;CHECK(owner.select(observed(1,1000),1,1010));
    owner.update(1,1060,1070,true,{observed(1,1060)});CHECK(owner.snapshot(1070).control_valid);
    owner.update(2,2000,2010,true,{});                         // gap > continuation_ms
    for(int k=0;k<4;++k) {
        auto unknown=observed(2,2060+60*k,1.5);unknown.embedding.reset();
        owner.update(3+k,2060+60*k,2070+60*k,true,{observed(9,2060+60*k,.1),unknown});
        auto o=owner.snapshot(2070+60*k);CHECK(!o.control_valid);CHECK(o.reason=="identity_evidence_incomplete");
    }
    for(int k=0;k<3;++k)owner.update(7+k,2400+60*k,2410+60*k,true,{observed(9,2400+60*k,.1),observed(2,2400+60*k,1.5)});
    CHECK(owner.snapshot(2530).control_valid);CHECK(owner.snapshot(2530).id==9);
}
void undescribed_bystander_beyond_reach_does_not_block_rebinding() {
    // With an evidence reach, an undescribed person is missing evidence only where the target
    // could have walked: a near one still blocks, a far one does not, and the reach grows with
    // the outage so a long absence again needs everyone described. Aerial-sized boxes.
    const Box home{.5,.5,.03,.08};                                   // extent .08
    auto person=[&](uint64_t id,double capture,Box box,double angle,bool described=true) {
        Track t{id,"person",box,.9,capture,.01,true,true,false};
        if(described)t.embedding=std::make_shared<const Embedding>(feature(angle));
        return t;
    };
    IdentityConfig cfg;cfg.evidence_radius=2;cfg.evidence_radius_growth=2;
    auto start=[&]() {
        TargetOwner owner(cfg);CHECK(owner.select(person(1,1000,home,0),1,1010));
        owner.update(1,1060,1070,true,{person(1,1060,home,0)});CHECK(owner.snapshot(1070).control_valid);
        owner.update(2,1500,1510,true,{});                          // gap > continuation_ms
        auto o=owner.snapshot(1510);CHECK(!o.box);CHECK(o.last_verified_box&&o.last_verified_box->x==home.x);
        CHECK(o.identity_unresolved==0);
        return owner;
    };
    const Box far{.9,.5,.03,.08},near{.6,.5,.03,.08};                // 5 and 1.25 extents away
    auto owner=start();                                              // .56 s out: reach 3.1 extents
    for(int k=0;k<3;++k) {
        owner.update(3+k,1560+60*k,1570+60*k,true,{person(9,1560+60*k,home,.1),person(2,1560+60*k,far,0,false)});
        auto o=owner.snapshot(1570+60*k);CHECK(o.control_valid==(k==2));
        CHECK(o.reason==(k==2?"identity_verified":"verifying_returning_identity"));
    }
    CHECK(owner.snapshot(1690).id==9);
    owner=start();
    for(int k=0;k<3;++k) {
        owner.update(3+k,1560+60*k,1570+60*k,true,{person(9,1560+60*k,home,.1),person(2,1560+60*k,near,0,false)});
        CHECK(owner.snapshot(1570+60*k).reason=="identity_evidence_incomplete");
    }
    owner=start();                                                   // 3 s out: reach 8 extents
    owner.update(3,4000,4010,true,{person(9,4000,home,.1),person(2,4000,far,0,false)});
    CHECK(owner.snapshot(4010).reason=="identity_evidence_incomplete");
    IdentityConfig shipped;TargetOwner strict(shipped);CHECK(strict.select(person(1,1000,home,0),1,1010));
    strict.update(1,1500,1510,true,{});
    strict.update(2,1560,1570,true,{person(9,1560,home,.1),person(2,1560,far,0,false)});
    CHECK(strict.snapshot(1570).reason=="identity_evidence_incomplete"); // default reach: everyone counts
    Config mapped=config_from_json(Json{{"learned_person_identity",true},{"identity_evidence_radius",2},{"identity_evidence_radius_growth",2}});
    CHECK(mapped.identity_evidence_radius==2&&mapped.identity_evidence_radius_growth==2);
    Tracker ok(mapped);
    bool bad=false;mapped.identity_evidence_radius=0;try{Tracker t(mapped);}catch(const std::invalid_argument&){bad=true;}CHECK(bad);
    bad=false;mapped.identity_evidence_radius=-1;mapped.identity_evidence_radius_growth=0;try{Tracker t(mapped);}catch(const std::invalid_argument&){bad=true;}CHECK(bad);
}
void immutable_anchor_stops_gradual_drift() {
    TargetOwner owner;CHECK(owner.select(observed(1,1000),1,1010));
    for(int k=1;k<=20;++k) {
        const double angle=.05*k;
        owner.update(k,1000+k*50,1010+k*50,true,{observed(1,1000+k*50,angle)});
        if(1-std::cos(angle)>.25)CHECK(!owner.snapshot(1010+k*50).control_valid);
    }
    CHECK(owner.snapshot(2010).identity_retained);
}
void consecutive_elapsed_verification() {
    TargetOwner owner;CHECK(owner.select(observed(1,1000),1,1010));
    for(int k=1;k<=20;++k) {
        owner.update(k,3000+k,3010+k,true,{observed(2,3000+k)});
        CHECK(!owner.snapshot(3010+k).control_valid); // 20 hits in 20ms is insufficient
    }
    owner.update(21,3060,3070,true,{}); // missing evidence resets the streak
    owner.update(22,3120,3130,true,{observed(2,3120)});
    owner.update(23,3180,3190,true,{observed(3,3180)}); // different candidate resets it too
    CHECK(!owner.snapshot(3190).control_valid);
    owner.update(24,3400,3410,true,{observed(3,3400)}); // excessive gap resets it
    owner.update(25,3460,3470,true,{observed(3,3460)});CHECK(!owner.snapshot(3470).control_valid);
    owner.update(26,3520,3530,true,{observed(3,3520)});CHECK(owner.snapshot(3530).control_valid);
}
void invalid_evidence() {
    auto e=feature();e.values[0]=std::numeric_limits<double>::quiet_NaN();CHECK(!normalize_embedding(e));
    e=feature();e.values.fill(0);CHECK(!normalize_embedding(e));
    e=feature();e.values[0]=1e308;CHECK(!normalize_embedding(e));
    auto a=feature(),b=feature();b.model="other";CHECK(!std::isfinite(embedding_distance(a,b)));
    TargetOwner owner;auto bad=observed(1,1000);bad.box.x=std::numeric_limits<double>::quiet_NaN();
    CHECK(!owner.select(bad,1,1010));CHECK(owner.select(observed(1,1000),1,1010));
    owner.update(1,1060,1400,true,{observed(1,1060)});CHECK(!owner.snapshot(1400).control_valid);
    owner.update(2,1460,1470,true,{observed(1,1460)});CHECK(!owner.snapshot(1470).control_valid);
    CHECK(!owner.snapshot(std::numeric_limits<double>::quiet_NaN()).control_valid);
    owner.update(2,1460,1470,true,{observed(1,1460)});CHECK(!owner.snapshot(1470).control_valid);
}
void integrated_tracker_reacquires_new_mot_id() {
    Config cfg;cfg.learned_person_identity=true;Tracker tracker(cfg);tracker.arm_class("person");
    auto input=[](uint64_t n,double ts,double angle=0) {
        Detection d{{.3,.2,.2,.6},"person",.9,{}};d.embedding=feature(angle);
        return Frame{n,ts,ts+10,true,{d},{}};
    };
    for(int k=1;k<=3;++k)tracker.update(input(k,1000+60*k));
    auto first=tracker.snapshot(1190);CHECK(first.target.control_valid);CHECK(first.target.identity_retained);
    tracker.update({4,3000,3010,true,{},{}});CHECK(tracker.snapshot(3010).target.state=="occluded");
    auto wrong=tracker.update(input(5,3060,1.5));CHECK(!wrong.target.control_valid);
    // Let the wrong-person MOT expire. The selected appearance remains independent of either ID.
    for(int k=0;k<5;++k)tracker.update(input(6+k,5000+60*k,.2));
    auto returned=tracker.snapshot(5250);CHECK(returned.target.control_valid);
    CHECK(returned.target.id!=first.target.id);CHECK(returned.target.epoch==first.target.epoch);
    CHECK(!tracker.snapshot(std::numeric_limits<double>::quiet_NaN()).target.control_valid);
    auto roundtrip=frame_from_json(frame_json(input(11,5300)));CHECK(roundtrip.detections[0].embedding);
    CHECK(roundtrip.detections[0].embedding->model=="synthetic-test-v1");
    tracker.unlock();CHECK(tracker.snapshot(5250).target.state=="none");
    tracker.arm_class("cell phone");auto phone=input(11,5300);phone.detections[0].label="cell phone";phone.detections[0].embedding.reset();
    for(int k=0;k<3;++k) {phone.sequence=11+k;phone.capture_ms=5300+k*60;phone.now_ms=phone.capture_ms+10;tracker.update(phone);}
    CHECK(tracker.snapshot(5430).target.control_valid);CHECK(!tracker.snapshot(5430).target.identity_retained);
}
void identity_memory_is_configurable() {
    // A follow target that steps out for longer than the default 10 s memory must
    // still be re-identified when the profile asks for a longer memory.
    Config cfg;cfg.learned_person_identity=true;cfg.identity_memory_ms=30000;Tracker tracker(cfg);tracker.arm_class("person");
    auto input=[](uint64_t n,double ts,double angle=0) {
        Detection d{{.3,.2,.2,.6},"person",.9,{}};d.embedding=feature(angle);
        return Frame{n,ts,ts+10,true,{d},{}};
    };
    for(int k=1;k<=3;++k)tracker.update(input(k,1000+60*k));
    CHECK(tracker.snapshot(1190).target.control_valid);
    tracker.update({4,1300,1310,true,{},{}});
    CHECK(tracker.snapshot(21000).target.identity_retained);        // 20 s away: still remembered
    for(int k=0;k<5;++k)tracker.update(input(5+k,21000+60*k,.05));
    auto back=tracker.snapshot(21250);CHECK(back.target.control_valid);CHECK(back.target.epoch==1);
    CHECK(!tracker.snapshot(52000).target.identity_retained);       // beyond 30 s: expired
    bool threw=false;try{Config bad;bad.learned_person_identity=true;bad.identity_memory_ms=100;Tracker t(bad);}
    catch(const std::invalid_argument&){threw=true;}CHECK(threw);   // memory must exceed freshness
    Config loose;loose.learned_person_identity=true;loose.identity_max_distance=.6;Tracker relaxed(loose);relaxed.arm_class("person");
    for(int k=1;k<=3;++k)relaxed.update(input(k,1000+60*k));
    relaxed.update(input(4,1300,.9));CHECK(relaxed.snapshot(1310).target.control_valid);   // 1-cos(.9)=.38 passes a .6 gate
    threw=false;try{Config bad;bad.learned_person_identity=true;bad.identity_max_distance=1.5;Tracker t(bad);}
    catch(const std::invalid_argument&){threw=true;}CHECK(threw);
}
void crop_preserves_planes_and_geometry() {
    std::vector<uint8_t> y(6*4,255),uv(6*2,255),out;
    for(int row=0;row<4;++row)for(int col=0;col<4;++col)y[row*6+col]=row*10+col;
    for(int row=0;row<2;++row)for(int col=0;col<4;++col)uv[row*6+col]=50+row*10+col;
    Image image{y.data(),uv.data(),4,4,6,6,y.size(),uv.size()};
    auto region=resize_nv12_crop(image,{0,0,1,1},4,4,out);CHECK(region.w==1);CHECK(out.size()==24);
    for(int row=0;row<4;++row)for(int col=0;col<4;++col)CHECK(out[row*4+col]==row*10+col);
    for(int row=0;row<2;++row)for(int col=0;col<4;++col)CHECK(out[16+row*4+col]==50+row*10+col);
    region=resize_nv12_crop(image,{.5,.5,.5,.5},2,2,out);
    CHECK(region.x==.5&&region.y==.5);CHECK(out==std::vector<uint8_t>({22,23,32,33,62,63}));
    region=resize_nv12_crop(image,{-.2,-.2,.4,.4},2,2,out);CHECK(region.x==0&&region.w==.5);
    y={0,10,20,30};uv={80,180};image={y.data(),uv.data(),2,2,2,2,y.size(),uv.size()};
    resize_nv12_crop(image,{0,0,1,1},4,4,out);CHECK(out[5]==8);CHECK(out[10]==23);
    for(size_t k=16;k<24;k+=2)CHECK(out[k]==80&&out[k+1]==180);
    bool rejected=false;try{resize_nv12_crop(image,{2,0,.1,.1},2,2,out);}catch(const std::invalid_argument&){rejected=true;}
    CHECK(rejected);image.y_bytes=1;rejected=false;
    try{resize_nv12_crop(image,{0,0,1,1},2,2,out);}catch(const std::invalid_argument&){rejected=true;}CHECK(rejected);
}
int main() {
    try {
        durable_identity();ambiguity_and_incomplete_evidence();undescribed_bystander_blocks_rebinding_only();
        undescribed_bystander_beyond_reach_does_not_block_rebinding();immutable_anchor_stops_gradual_drift();
        consecutive_elapsed_verification();invalid_evidence();integrated_tracker_reacquires_new_mot_id();
        identity_memory_is_configurable();crop_preserves_planes_and_geometry();measured_cadence_keeps_positive_identity_not_prediction();
        std::cout<<"11 learned target identity/crop scenarios passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
