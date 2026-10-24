#include "garuda_tracking/vision.hpp"
#include <iostream>
#include <stdexcept>
using namespace garuda::fresh;
int main() {
    try {
        for(auto size: {std::pair<int,int>{1280,720},{1920,1080},{3840,2160},{642,362}}) {
            const auto [w,h]=size;const int stride=w+16;
            std::vector<uint8_t> pixels(size_t(stride)*h*3/2),old,compact;
            uint32_t seed=19;
            for(auto& p:pixels){seed=1664525*seed+1013904223;p=uint8_t(seed>>24);}
            Image image{pixels.data(),pixels.data()+size_t(stride)*h,w,h,stride,stride,size_t(stride)*h,size_t(stride)*h/2};
            resize_nv12_crop(image,{0,0,1,1},640,360,old);motion_samples(image,compact);
            for(int y=0;y<90;++y)for(int x=0;x<160;++x)
                if(compact[y*160+x]!=old[(y*4)*640+x*4])throw std::runtime_error("motion sample mismatch");
            MotionEstimator a,b;
            Image big{old.data(),old.data()+640*360,640,360,640,640,640*360,640*180};
            Image small{compact.data(),compact.data()+160*90,160,90,160,160,160*90,160*45};
            a.update(big,{});b.update(small,{});
            auto m=a.update(big,{}),n=b.update(small,{});
            if(m.valid!=n.valid||m.dx!=n.dx||m.dy!=n.dy)throw std::runtime_error("motion estimator mismatch");
        }
        bool rejected=false;std::vector<uint8_t> out;
        try{motion_samples({},out);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid input accepted");
        std::cout<<"Motion sample parity passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
