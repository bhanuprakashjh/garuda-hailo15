#include "garuda_tracking/json.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace garuda::fresh;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
int main() {
    try {
        Motion m{.12,-.03,true};const double angle=.15,scale=1.06;
        m.a=m.d=scale*std::cos(angle);m.b=-scale*std::sin(angle)*9/16;m.c=scale*std::sin(angle)*16/9;m.position_std=.01;
        CHECK(m.usable());Box box{.2,.25,.04,.08};auto transformed=m.transform(box);
        double cx=box.x+box.w/2-.5,cy=box.y+box.h/2-.5;
        CHECK(std::abs(transformed.x+transformed.w/2-(.5+m.dx+m.a*cx+m.b*cy))<1e-12);
        CHECK(transformed.w>box.w);
        Tracker tracker;
        for(int i=0;i<4;++i)tracker.update(Frame{uint64_t(i+1),1000.+i*60,1010.+i*60,true,{{box,"cell phone",.9,{},{}}},{}});
        CHECK(tracker.select(1,4,1190));
        Frame frame{5,1240,1250,true,{{transformed,"cell phone",.9,{},{}}},m};
        auto copy=frame_from_json(frame_json(frame));CHECK(copy.motion.b==m.b);CHECK(copy.motion.position_std==m.position_std);
        auto out=tracker.update(copy);CHECK(out.target.id==1);CHECK(out.target.control_valid);
        auto prior=out.target.position_std;
        frame={6,1300,1310,true,{},m};frame.motion.position_std=.04;
        out=tracker.update(frame);CHECK(!out.target.control_valid);CHECK(out.target.position_std>prior);
        for(auto bad:{std::numeric_limits<double>::quiet_NaN(),-1.,2.}) {
            auto invalid=m;invalid.a=bad;CHECK(!invalid.usable());CHECK(invalid.transform(box).x==box.x);
        }
        auto legacy=frame_json(frame);legacy["motion"]={{"dx",.01},{"dy",0},{"valid",true}};
        CHECK(frame_from_json(legacy).motion.a==1);CHECK(frame_from_json(legacy).motion.b==0);
        std::cout<<"motion transform: geometry, selected phone association, uncertainty, invalid transform and legacy replay passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
