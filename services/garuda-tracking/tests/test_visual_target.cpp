#include "garuda_tracking/visual_target.hpp"
#include "garuda_tracking/json.hpp"
#include <opencv2/core.hpp>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace garuda::fresh;
#define CHECK(x) do {if(!(x))throw std::runtime_error(std::to_string(__LINE__)+": " #x);}while(0)
struct Pixels {
    std::vector<uint8_t> bytes=std::vector<uint8_t>(640*360*3/2,128);
    Image image(){return {bytes.data(),bytes.data()+640*360,640,360,640,640,640*360,640*360/2};}
    void object(int x,int y) {
        // Fixed, textured object, not background texture that follows the ROI.
        uint32_t state=17;
        for(int j=0;j<60;++j)for(int i=0;i<32;++i) {
            state=1664525*state+1013904223;
            bytes[(y+j)*640+x+i]=uint8_t(20+(state>>24)%160);
        }
    }
};
Box box(int x,int y){return {x/640.,y/360.,32/640.,60/360.};}
void images() {
    Pixels a,b,blank;a.object(200,120);b.object(300,150);
    VisualTargetTracker tracker;
    CHECK(!tracker.seed(blank.image(),box(200,120),1,1000,1,1));
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    auto r=tracker.locate(b.image(),2,1100,1,1);
    CHECK(r.measurement);CHECK(iou(r.measurement->box,box(300,150))>.95);
    CHECK(r.measurement->verified_ms==1000);
    CHECK(!tracker.locate(blank.image(),3,1200,1,1).measurement);
    CHECK(!tracker.locate(b.image(),4,1800,1,1).measurement);
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    Pixels twins;twins.object(120,120);twins.object(300,120);
    CHECK(!tracker.locate(twins.image(),2,1100,1,1).measurement);
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    CHECK(tracker.locate(b.image(),2,1100,1,2).reason=="selection_changed");
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    CHECK(tracker.locate(b.image(),1,1100,1,1).reason=="invalid_cadence");
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    CHECK(!tracker.locate({},2,1100,1,1).measurement);
    CHECK(!tracker.seed(a.image(),{.9,.9,.2,.2},1,1000,1,1));
    CHECK(!tracker.seed(a.image(),box(200,120),1,std::numeric_limits<double>::quiet_NaN(),1,1));
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    for(int i=2;i<=16;++i)CHECK(tracker.locate(a.image(),i,1000+100*(i-1),1,1).measurement);
    CHECK(tracker.locate(a.image(),17,2600,1,1).reason=="verification_expired");
    CHECK(tracker.seed(a.image(),box(200,120),1,1000,1,1));
    auto changed=a.image();changed.width=638;
    CHECK(tracker.locate(changed,2,1100,1,1).reason=="geometry_changed");
}
Frame frame(int seq,double time,std::vector<Detection> ds={}){return {uint64_t(seq),time,time+10,true,std::move(ds),{}};}
void core() {
    for(bool enabled:{false,true})for(const std::string label:{"cell phone","person","car"}) {
        Config cfg;cfg.visual_phone_tracking=enabled;Tracker t(cfg);
        Detection d{box(200,120),label,.9,{}};
        for(int i=1;i<=3;++i)t.update(frame(i,1000+60*i,{d}));
        CHECK(t.select(1,3,1190));auto selected=t.snapshot(1190).target;
        auto f=frame(4,1240);f.visual_target=VisualMeasurement{box(300,150),selected.lock_id,selected.epoch,4,1240,1180,.95,.3};
        auto restored=frame_from_json(frame_json(f));
        CHECK(restored.visual_target&&restored.visual_target->lock_id==selected.lock_id);
        CHECK(restored.visual_target->capture_ms==1240);
        auto out=t.update(f);const bool eligible=enabled&&label=="cell phone";
        CHECK(out.target.control_valid==eligible);
        CHECK(out.target.visual_observation==eligible);
        CHECK(out.tracks.size()==1);
        if(eligible) {
            CHECK(output_json(out)["tracks"][0]["box_source"]=="visual_measurement");
            CHECK(!t.snapshot(1500).target.control_valid);
            // A renewed-looking external anchor cannot bypass core detector-age bound.
            for(int i=5;i<=32;++i) {
                f=frame(i,1240+60*(i-4));f.visual_target=VisualMeasurement{box(300,150),selected.lock_id,selected.epoch,uint64_t(i),f.capture_ms,f.capture_ms,.95,.3};
                out=t.update(f);
            }
            CHECK(!out.target.control_valid);
        }
    }
    for(int bad=0;bad<7;++bad) {
        Config cfg;cfg.visual_phone_tracking=true;Tracker t(cfg);Detection d{box(200,120),"cell phone",.9,{}};
        for(int i=1;i<=3;++i)t.update(frame(i,1000+60*i,{d}));
        CHECK(t.select(1,3,1190));auto s=t.snapshot(1190).target;
        auto f=frame(4,1240);VisualMeasurement v{box(300,150),s.lock_id,s.epoch,4,1240,1180,.95,.3};
        if(bad==0)++v.epoch;if(bad==1)++v.lock_id;if(bad==2)--v.sequence;
        if(bad==3)--v.capture_ms;if(bad==4)v.score=std::numeric_limits<double>::quiet_NaN();
        if(bad==5)v.margin=.01;if(bad==6)v.box.w=-1;
        f.visual_target=v;CHECK(!t.update(f).target.control_valid);
    }
    // A weak detection may neither suppress independent image evidence nor
    // poison its appearance anchor. The next strong detector match still binds.
    Config cfg;cfg.visual_phone_tracking=true;Tracker tracker(cfg);
    Detection d{box(200,120),"cell phone",.9,{}};Appearance original{};original[2]=1;d.appearance=original;
    for(int i=1;i<=3;++i)tracker.update(frame(i,1000+60*i,{d}));
    CHECK(tracker.select(1,3,1190));auto s=tracker.snapshot(1190).target;
    d.box=box(250,120);d.confidence=.2;Appearance wrong{};wrong[9]=1;d.appearance=wrong;
    auto f=frame(4,1240,{d});f.visual_target=VisualMeasurement{d.box,s.lock_id,s.epoch,4,1240,1180,.95,.3};
    auto bridged=tracker.update(f);CHECK(bridged.target.visual_observation);CHECK(bridged.target.control_valid);
    CHECK(bridged.tracks.front().confidence==.9);
    d.confidence=.9;d.appearance=original;f=frame(5,1300,{d});
    f.visual_target=VisualMeasurement{d.box,s.lock_id,s.epoch,5,1300,1180,.95,.3};
    auto verified=tracker.update(f);CHECK(verified.target.control_valid);CHECK(!verified.target.visual_observation);
    CHECK(verified.target.id==s.id);
    tracker.unlock();f=frame(6,1360);f.visual_target=VisualMeasurement{d.box,s.lock_id,s.epoch,6,1360,1300,.95,.3};
    CHECK(!tracker.update(f).target.control_valid);
}
int main(){try{cv::setNumThreads(1);images();core();std::cout<<"visual target guards passed\n";}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
