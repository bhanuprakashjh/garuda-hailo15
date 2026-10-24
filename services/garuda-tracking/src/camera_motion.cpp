#include "garuda_tracking/camera_motion.hpp"
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/calib3d.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <set>

namespace garuda::fresh {
namespace {
constexpr int W=320,H=180;
cv::Mat background_mask(const std::vector<Detection>& detections) {
    cv::Mat mask(H,W,CV_8U,cv::Scalar(255));
    mask.rowRange(0,10)=0;mask.rowRange(H-10,H)=0;
    mask.colRange(0,10)=0;mask.colRange(W-10,W)=0;
    for(const auto& detection:detections) {
        const auto& b=detection.box;
        if(!std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.w)||!std::isfinite(b.h)||b.w<=0||b.h<=0)continue;
        int x0=int(std::clamp((b.x-.035)*W,0.,double(W))),y0=int(std::clamp((b.y-.05)*H,0.,double(H)));
        int x1=int(std::clamp((b.x+b.w+.035)*W,0.,double(W))),y1=int(std::clamp((b.y+b.h+.05)*H,0.,double(H)));
        if(x1>x0&&y1>y0)mask(cv::Rect(x0,y0,x1-x0,y1-y0))=0;
    }
    return mask;
}
bool unmasked(const cv::Mat& mask,const cv::Point2f& point) {
    return std::isfinite(point.x)&&std::isfinite(point.y)&&point.x>=0&&point.y>=0&&
        point.x<W&&point.y<H&&mask.at<uint8_t>(int(point.y),int(point.x))!=0;
}
}
struct CameraMotionEstimator::Impl {
    cv::Ptr<cv::ORB> orb=cv::ORB::create(200,1.2f,4,16,0,2,cv::ORB::HARRIS_SCORE,31,12);
    cv::BFMatcher matcher{cv::NORM_HAMMING};
    std::vector<cv::KeyPoint> previous_points;
    cv::Mat previous_descriptors;
    int source_w=0,source_h=0;
    bool initialized=false;
};
CameraMotionEstimator::CameraMotionEstimator():impl_(std::make_unique<Impl>()) {cv::setNumThreads(1);}
CameraMotionEstimator::~CameraMotionEstimator()=default;
void CameraMotionEstimator::reset() {
    impl_->previous_descriptors.release();impl_->previous_points.clear();impl_->initialized=false;
}
MotionFit CameraMotionEstimator::update(const Image& image,const std::vector<Detection>& detections) {
    const auto start=std::chrono::steady_clock::now();MotionFit fit;
    auto finish=[&](const char* reason) {
        fit.reason=reason;fit.elapsed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();return fit;
    };
    if(!image.valid()){reset();return finish("invalid_image");}
    if(image.width*9!=image.height*16){reset();return finish("unsupported_aspect_ratio");}
    if(image.width!=impl_->source_w||image.height!=impl_->source_h)reset();
    impl_->source_w=image.width;impl_->source_h=image.height;
    cv::Mat current;
    cv::resize(cv::Mat(image.height,image.width,CV_8U,const_cast<uint8_t*>(image.y),image.y_stride),
               current,cv::Size(W,H),0,0,cv::INTER_AREA);
    auto mask=background_mask(detections);
    std::vector<cv::KeyPoint> points;cv::Mat descriptors;
    const auto extraction_start=std::chrono::steady_clock::now();
    impl_->orb->detectAndCompute(current,mask,points,descriptors);
    fit.extraction_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-extraction_start).count();
    auto previous_points=std::move(impl_->previous_points);auto previous_descriptors=impl_->previous_descriptors;
    const bool initialized=impl_->initialized;impl_->initialized=true;
    // Own descriptors/keypoints; no caller DMA buffer escapes.
    impl_->previous_points=points;impl_->previous_descriptors=descriptors;
    fit.features=points.size();
    if(!initialized)return finish("initial_frame");
    if(points.size()<16||previous_points.size()<16)return finish("insufficient_background_features");
    std::vector<std::vector<cv::DMatch>> forward,backward;
    const auto matching_start=std::chrono::steady_clock::now();
    impl_->matcher.knnMatch(previous_descriptors,descriptors,forward,2);
    impl_->matcher.knnMatch(descriptors,previous_descriptors,backward,2);
    fit.matching_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-matching_start).count();
    std::vector<cv::Point2f> src,dst;
    for(const auto& matches:forward)if(matches.size()==2&&matches[0].distance<.8*matches[1].distance) {
        const auto& match=matches[0];const auto& reverse=backward.at(size_t(match.trainIdx));
        if(reverse.size()==2&&reverse[0].trainIdx==match.queryIdx&&reverse[0].distance<.8*reverse[1].distance&&
           unmasked(mask,points.at(size_t(match.trainIdx)).pt)) {
            src.push_back(previous_points.at(size_t(match.queryIdx)).pt);dst.push_back(points.at(size_t(match.trainIdx)).pt);
        }
    }
    fit.matches=src.size();if(src.size()<16)return finish("insufficient_descriptor_matches");
    cv::Mat inliers;
    const auto fit_start=std::chrono::steady_clock::now();
    auto affine=cv::estimateAffinePartial2D(src,dst,inliers,cv::RANSAC,1.5,500,.99,10);
    fit.fit_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-fit_start).count();
    if(affine.empty())return finish("fit_failed");
    const double a=affine.at<double>(0,0),b=affine.at<double>(0,1),c=affine.at<double>(1,0),d=affine.at<double>(1,1);
    const double tx=affine.at<double>(0,2),ty=affine.at<double>(1,2);
    double squared=0;float xmin=W,xmax=0,ymin=H,ymax=0;std::set<int> cells;
    for(size_t i=0;i<src.size();++i)if(inliers.at<uint8_t>(int(i))) {
        const double ex=a*src[i].x+b*src[i].y+tx-dst[i].x,ey=c*src[i].x+d*src[i].y+ty-dst[i].y;
        squared+=ex*ex+ey*ey;++fit.inliers;
        xmin=std::min(xmin,src[i].x);xmax=std::max(xmax,src[i].x);ymin=std::min(ymin,src[i].y);ymax=std::max(ymax,src[i].y);
        cells.insert(int(src[i].y/(H/3))*4+int(src[i].x/(W/4)));
    }
    if(fit.inliers<16||fit.inliers<src.size()*.65)return finish("insufficient_consensus");
    fit.residual_px=std::sqrt(squared/fit.inliers);
    fit.support_cells=cells.size();fit.support_width=(xmax-xmin)/W;fit.support_height=(ymax-ymin)/H;
    if(cells.size()<6||xmax-xmin<W*.4||ymax-ymin<H*.4)return finish("localized_support");
    if(!std::isfinite(fit.residual_px)||fit.residual_px>1.)return finish("high_residual");
    const double scale=std::hypot(a,c),rotation=std::atan2(c,a);
    if(scale<.85||scale>1.15||std::abs(rotation)>.21)return finish("excessive_rotation_or_scale");
    Motion motion;
    motion.a=a;motion.b=b*H/W;motion.c=c*W/H;motion.d=d;
    motion.dx=(a*W/2+b*H/2+tx-W/2)/W;motion.dy=(c*W/2+d*H/2+ty-H/2)/H;
    motion.position_std=std::max(.5,fit.residual_px)/std::min(W,H);motion.valid=true;
    if(!motion.usable())return finish("excessive_transform");
    fit.motion=motion;return finish("background_similarity");
}
}
