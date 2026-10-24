#include "garuda_tracking/camera_motion.hpp"
#include "garuda_tracking/json.hpp"
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace garuda::fresh;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
struct Pixels {
    cv::Mat y;
    std::vector<uint8_t> uv;
    Image image() {uv.resize(y.cols*y.rows/2,128);return {y.data,uv.data(),y.cols,y.rows,int(y.step),y.cols,y.step*y.rows,uv.size()};}
};
cv::Mat texture() {
    cv::Mat image(360,640,CV_8U);cv::RNG rng(63218);rng.fill(image,cv::RNG::UNIFORM,30,225);
    cv::GaussianBlur(image,image,cv::Size(5,5),.8);
    for(int y=25;y<340;y+=35)for(int x=25;x<620;x+=45)
        cv::rectangle(image,cv::Rect(x,y,14,11),cv::Scalar(rng.uniform(10,245)),-1);
    return image;
}
int main() {
    try {
        cv::setNumThreads(1);
        Pixels first{texture(),{}},second;CameraMotionEstimator estimator;
        size_t cases=0;
        for(double angle:{-8.,0.,8.})for(double scale:{.94,1.,1.06}) {
            const auto matrix=cv::getRotationMatrix2D(cv::Point2f(320,180),angle,scale);
            auto affine=matrix.clone();affine.at<double>(0,2)+=32;affine.at<double>(1,2)-=9;
            cv::warpAffine(first.y,second.y,affine,first.y.size());
            estimator.reset();CHECK(!estimator.update(first.image(),{}).motion.valid);
            auto result=estimator.update(second.image(),{});
            if(!result.motion.valid)throw std::runtime_error("synthetic fit failed: "+result.reason+" features="+std::to_string(result.features)+
                " matches="+std::to_string(result.matches)+" inliers="+std::to_string(result.inliers)+" cells="+std::to_string(result.support_cells)+
                " width="+std::to_string(result.support_width)+" height="+std::to_string(result.support_height));
            CHECK(std::abs(result.motion.dx-.05)<.004);CHECK(std::abs(result.motion.dy+.025)<.004);
            CHECK(std::abs(result.motion.a-scale*std::cos(angle*CV_PI/180))<.008);
            CHECK(std::abs(result.motion.c+scale*std::sin(angle*CV_PI/180)*640/360)<.012);
            std::cout<<Json{{"angle_degrees",angle},{"scale",scale},{"fit_ms",result.elapsed_ms},
                {"inliers",result.inliers},{"residual_px",result.residual_px}}.dump()<<'\n';++cases;
        }
        // Feed the estimated (not oracle) transform into the actual target tracker.
        // The same camera jump without compensation exceeds the small phone's association gate.
        Tracker tracker,uncompensated;estimator.reset();
        Box phone{.2,.25,.04,.08};std::vector<Detection> phone_detection={{phone,"cell phone",.9,{},{}}};
        for(int i=0;i<4;++i) {
            Frame frame{uint64_t(i+1),1000.+i*60,1010.+i*60,true,phone_detection,{}};
            frame.motion=estimator.update(first.image(),phone_detection).motion;
            tracker.update(frame);frame.motion={};uncompensated.update(frame);
        }
        CHECK(tracker.select(1,4,1190));CHECK(uncompensated.select(1,4,1190));
        Motion truth{.12,-.03,true};truth.a=truth.d=1.06*std::cos(8*CV_PI/180);
        truth.b=1.06*std::sin(8*CV_PI/180)*9/16;truth.c=-1.06*std::sin(8*CV_PI/180)*16/9;
        auto jump=cv::getRotationMatrix2D(cv::Point2f(320,180),8,1.06);jump.at<double>(0,2)+=.12*640;jump.at<double>(1,2)-=.03*360;
        cv::warpAffine(first.y,second.y,jump,first.y.size());
        phone_detection[0].box=truth.transform(phone);auto estimated=estimator.update(second.image(),phone_detection);
        CHECK(estimated.motion.valid);
        Frame moved{5,1240,1250,true,phone_detection,estimated.motion};auto tracked=tracker.update(moved);
        CHECK(tracked.target.id==1);CHECK(tracked.target.control_valid);
        moved.motion={};CHECK(!uncompensated.update(moved).target.control_valid);
        // Independently moving central foreground is masked in both images.
        auto affine=cv::getRotationMatrix2D(cv::Point2f(320,180),5,1.02);affine.at<double>(0,2)+=12;
        cv::warpAffine(first.y,second.y,affine,first.y.size());
        cv::RNG rng(91);rng.fill(second.y(cv::Rect(160,72,224,234)),cv::RNG::UNIFORM,0,255);
        std::vector<Detection> foreground={{{.25,.2,.35,.65},"person",.9,{},{}}};
        estimator.reset();estimator.update(first.image(),foreground);auto masked=estimator.update(second.image(),foreground);
        CHECK(masked.motion.valid);CHECK(std::abs(masked.motion.dx-12./640)<.004);
        // Unobservable or unsupported motion must not turn into a confident transform.
        Pixels flat{cv::Mat(360,640,CV_8U,cv::Scalar(90)),{}};
        estimator.reset();estimator.update(flat.image(),{});CHECK(!estimator.update(flat.image(),{}).motion.valid);
        estimator.reset();std::vector<Detection> cover={{{0,0,1,1},"person",.9,{},{}}};
        estimator.update(first.image(),cover);CHECK(!estimator.update(second.image(),cover).motion.valid);
        estimator.reset();estimator.update(first.image(),{});CHECK(!estimator.update(flat.image(),{}).motion.valid);
        affine=cv::getRotationMatrix2D(cv::Point2f(320,180),0,1.3);cv::warpAffine(first.y,second.y,affine,first.y.size());
        estimator.reset();estimator.update(first.image(),{});CHECK(!estimator.update(second.image(),{}).motion.valid);
        Pixels resized{cv::Mat(180,320,CV_8U,cv::Scalar(90)),{}};
        CHECK(!estimator.update(resized.image(),{}).motion.valid);
        CHECK(!estimator.update({},{}).motion.valid);
        std::cout<<"camera motion: "<<cases<<" rotation/scale combinations, foreground mask and invalid-input gates passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
