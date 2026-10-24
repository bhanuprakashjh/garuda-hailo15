#include "garuda_tracking/visual_target.hpp"
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>

namespace garuda::fresh {
namespace {
bool valid_box(const Box& b) {
    return std::isfinite(b.x)&&std::isfinite(b.y)&&std::isfinite(b.w)&&std::isfinite(b.h)&&
        b.x>=0&&b.y>=0&&b.w>0&&b.h>0&&b.x+b.w<=1&&b.y+b.h<=1;
}
cv::Mat luma(const Image& im) {
    if(!im.valid()||im.width>4096||im.height>2160)return {};
    cv::Mat src(im.height,im.width,CV_8U,const_cast<uint8_t*>(im.y),im.y_stride),out;
    const double scale=std::min(1.,320./im.width);
    cv::resize(src,out,{int(std::round(im.width*scale)),int(std::round(im.height*scale))},0,0,cv::INTER_AREA);
    return out;
}
cv::Rect rectangle(const Box& b,const cv::Mat& im) {
    const int x=std::lround(b.x*im.cols),y=std::lround(b.y*im.rows);
    return {x,y,int(std::lround((b.x+b.w)*im.cols))-x,int(std::lround((b.y+b.h)*im.rows))-y};
}
Box normalized(const cv::Rect& r,const cv::Mat& im) {
    return {double(r.x)/im.cols,double(r.y)/im.rows,double(r.width)/im.cols,double(r.height)/im.rows};
}
}
struct VisualTargetTracker::Impl {
    cv::Mat anchor;
    Box box;
    uint64_t sequence=0,lock_id=0,epoch=0;
    double stamp=-1,verified=-1;
    int width=0,height=0;
};
// Explicit process-wide thread cap for this opt-in CPU plugin. The deployed
// adapter and replay use the same cap; no nested pool on the four-core board.
VisualTargetTracker::VisualTargetTracker():impl_(std::make_unique<Impl>()){cv::setNumThreads(1);}
VisualTargetTracker::~VisualTargetTracker()=default;
void VisualTargetTracker::reset(){*impl_=Impl{};}
bool VisualTargetTracker::seed(const Image& image,const Box& box,uint64_t sequence,double stamp,uint64_t lock,uint64_t epoch) {
    reset();
    if(!sequence||!lock||!std::isfinite(stamp)||stamp<0||!valid_box(box))return false;
    auto gray=luma(image);if(gray.empty())return false;
    auto r=rectangle(box,gray);
    if(r.width<6||r.height<6||(r&cv::Rect(0,0,gray.cols,gray.rows))!=r)return false;
    cv::Scalar mean,stddev;cv::meanStdDev(gray(r),mean,stddev);
    if(stddev[0]<8)return false; // constant templates produce degenerate normalized correlation
    auto& s=*impl_;s.anchor=gray(r).clone();s.box=normalized(r,gray);
    s.sequence=sequence;s.stamp=s.verified=stamp;s.lock_id=lock;s.epoch=epoch;
    s.width=image.width;s.height=image.height;
    return true;
}
VisualTargetResult VisualTargetTracker::locate(const Image& image,uint64_t sequence,double stamp,uint64_t lock,uint64_t epoch) {
    const auto start=std::chrono::steady_clock::now();VisualTargetResult out;auto& s=*impl_;
    auto finish=[&](const char* reason){out.reason=reason;out.elapsed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();return out;};
    if(s.anchor.empty())return finish("uninitialized");
    if(lock!=s.lock_id||epoch!=s.epoch||!lock){reset();return finish("selection_changed");}
    if(!std::isfinite(stamp)||sequence<=s.sequence||stamp<=s.stamp||stamp-s.stamp>500) {
        reset();return finish("invalid_cadence");
    }
    if(stamp-s.verified>visual_verification_horizon_ms){reset();return finish("verification_expired");}
    if(image.width!=s.width||image.height!=s.height){reset();return finish("geometry_changed");}
    auto gray=luma(image);if(gray.empty()){reset();return finish("invalid_image");}
    s.sequence=sequence;s.stamp=stamp;
    const auto b=rectangle(s.box,gray);
    const int radius=std::min(80,2*std::max(b.width,b.height));
    auto search=cv::Rect(b.x-radius,b.y-radius,b.width+2*radius,b.height+2*radius)&cv::Rect(0,0,gray.cols,gray.rows);
    // Coarse-to-fine: search at half resolution, then refine bounded local peaks.
    // Keep the anchor/measurement at 320-wide; this changes compute, not the
    // detector input or source FOV. All scales use the same coarse search grid.
    search.width-=search.width%2;search.height-=search.height%2;
    cv::Mat coarse;cv::resize(gray(search),coarse,{search.width/2,search.height/2},0,0,cv::INTER_AREA);
    struct Candidate {double score;cv::Rect box;};std::vector<Candidate> candidates;
    for(double scale:{.8,.9,1.,1.1,1.2}) {
        const int w=2*std::lround(b.width*scale/2),h=2*std::lround(b.height*scale/2);
        if(w<6||h<6||w>search.width||h>search.height)continue;
        // Absolute scale is also bounded relative to the last verified anchor.
        if(w<s.anchor.cols*.65||w>s.anchor.cols*1.5||h<s.anchor.rows*.65||h>s.anchor.rows*1.5)continue;
        cv::Mat templ,response;cv::resize(s.anchor,templ,{w/2,h/2},0,0,cv::INTER_AREA);
        cv::Scalar mean,stddev;cv::meanStdDev(templ,mean,stddev);
        if(stddev[0]<4)continue;
        cv::matchTemplate(coarse,templ,response,cv::TM_CCOEFF_NORMED);
        for(int k=0;k<2;++k) {
            double score;cv::Point p;cv::minMaxLoc(response,nullptr,&score,nullptr,&p);
            if(std::isfinite(score))candidates.push_back({score,{search.x+2*p.x,search.y+2*p.y,w,h}});
            const auto suppress=cv::Rect(p.x-w/4,p.y-h/4,w/2+1,h/2+1)&cv::Rect(0,0,response.cols,response.rows);
            response(suppress).setTo(-1);
        }
    }
    if(candidates.empty())return finish("no_search_support");
    std::sort(candidates.begin(),candidates.end(),[](auto& a,auto& b){return a.score>b.score;});
    // A half-grid displacement can depress the coarse score on fine texture.
    // Refine all ten bounded proposals before deciding confidence/ambiguity.
    for(auto& c:candidates) {
        auto local=cv::Rect(c.box.x-3,c.box.y-3,c.box.width+6,c.box.height+6)&cv::Rect(0,0,gray.cols,gray.rows);
        cv::Mat templ,response;cv::resize(s.anchor,templ,c.box.size());
        cv::matchTemplate(gray(local),templ,response,cv::TM_CCOEFF_NORMED);
        cv::Point refined;cv::minMaxLoc(response,nullptr,&c.score,nullptr,&refined);
        if(!std::isfinite(c.score))c.score=-1;
        c.box.x=local.x+refined.x;c.box.y=local.y+refined.y;
    }
    std::sort(candidates.begin(),candidates.end(),[](auto& a,auto& b){return a.score>b.score;});
    const auto& best=candidates.front();double second=-1;
    Box found=normalized(best.box,gray);
    for(size_t k=1;k<candidates.size();++k)
        if(iou(found,normalized(candidates[k].box,gray))<.2)second=std::max(second,candidates[k].score);
    out.score=best.score;out.margin=best.score-second;
    if(out.score<.65)return finish("weak_match");
    if(out.margin<.08)return finish("ambiguous_match");
    s.box=found;
    out.measurement=VisualMeasurement{found,lock,epoch,sequence,stamp,s.verified,out.score,out.margin};
    return finish("visual_observed");
}
}
