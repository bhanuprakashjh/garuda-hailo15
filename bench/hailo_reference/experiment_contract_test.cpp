#include <hailopp/hailotracker.h>
#include <hailo_analytics/pipeline/cropping/garuda_letterbox.hpp>
#include <iostream>
#include <vector>
#include <cstring>
#include <stdexcept>
void require(bool ok,const char* msg){if(!ok)throw std::runtime_error(msg);}
int main(){try {
    using namespace garuda_experiment;
    for(auto size: {std::array<int,2>{1280,720},{1920,1080},{960,540},{640,640},{720,1280}}) {
        auto c=letterbox_content(size[0],size[1],640,640);
        std::array<double,4> original{.13,.17,.63,.87};
        auto restored=undo_letterbox({c[0]+original[0]*c[2],c[1]+original[1]*c[3],
            c[0]+original[2]*c[2],c[1]+original[3]*c[3]},c);
        for(int i=0;i<4;i++)require(std::abs(original[i]-restored[i])<1e-9,"mapping mismatch");
    }
    auto c=letterbox_content(1280,720,640,640);
    auto pad=undo_letterbox({.1,0,.5,.1},c);
    require(pad[1]==0&&pad[3]==0,"padding must collapse");
    bool rejected=false;try{letterbox_content(1000,666,640,640);}catch(...){rejected=true;}
    require(rejected,"ambiguous rounding accepted");
    hailo_tracker_config_t config=HAILO_TRACKER_CONFIG_DEFAULT;
    config.add_threshold=.5f;config.class_aware_tracking=true;
    hailo_tracker tracker=nullptr;
    require(hailo_tracker_create(&config,&tracker)==HAILOPP_SUCCESS,"create failed");
    struct Release{hailo_tracker h;~Release(){hailo_tracker_release(h);}} release{tracker};
    std::vector<unsigned char> storage(sizeof(hailo_detections_t)+2*sizeof(hailo_detection_t),0);
    auto ds=reinterpret_cast<hailo_detections_t*>(storage.data());ds->count=1;
    ds->detections[0]={};auto& d=ds->detections[0];
    d.x_min=.2;d.y_min=.2;d.x_max=.4;d.y_max=.6;d.class_id=1;
    hailo_tracklets_t tracks{};
    auto step=[&](float score){
        d.score=score;
        require(hailo_tracker_predict(tracker,&tracks)==HAILOPP_SUCCESS,"predict failed");
        require(hailo_tracker_update(tracker,ds)==HAILOPP_SUCCESS,"update failed");
    };
    for(int i=0;i<6;i++)step(.2f);
    require(tracks.count==0,"weak detection created track");
    for(int i=0;i<7;i++)step(.9f);
    require(tracks.count>0,"strong detections did not create track");
    auto id=tracks.tracklets[0].id;
    for(int i=0;i<12;i++)step(.2f);
    require(tracks.count>0&&tracks.tracklets[0].id==id,"weak association changed ID");
    require(tracks.tracklets[0].state==HAILO_TRACKLET_STATE_TRACKED,"weak association lost track");
    require(tracks.tracklets[0].frames_since_update==0,"weak detection did not update track");
    std::cout<<"PASS: letterbox inverse/padding/rounding; weak birth rejected; weak association keeps ID "<<id<<"\n";
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
