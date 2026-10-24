// Offline streaming timing/estimate probe. Does not open the camera or NPU.
#include "garuda_tracking/camera_motion.hpp"
#include "garuda_tracking/json.hpp"
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <cmath>
#include <chrono>
#include <fstream>
#include <iostream>

int main(int argc,char** argv) {
    using namespace garuda::fresh;
    if(argc!=6&&argc!=7){std::cerr<<"usage: garuda-motion-probe INPUT|- WIDTH HEIGHT letterbox|full LIMIT [--warps]\n";return 2;}
    try {
        const bool warps=argc==7;
        if(warps&&std::string(argv[6])!="--warps")throw std::invalid_argument("unknown probe option");
        const int w=std::stoi(argv[2]),h=std::stoi(argv[3]),limit=std::stoi(argv[5]);const std::string mode=argv[4];
        if(w<2||h<2||w>1280||h>720||w%2||h%2||limit<1||limit>1200||(mode!="letterbox"&&mode!="full"))
            throw std::invalid_argument("probe bounds exceeded");
        auto geometry=FrameGeometry::make(1280,720,w,h,mode=="letterbox");
        std::ifstream file;std::istream* input=&std::cin;
        if(std::string(argv[1])!="-"){file.open(argv[1],std::ios::binary);if(!file)throw std::runtime_error("cannot read probe input");input=&file;}
        cv::setNumThreads(1);CameraMotionEstimator similarity;MotionEstimator translation;
        std::vector<uint8_t> pixels(size_t(w)*h*3/2);
        for(int index=0;index<limit;++index) {
            if(!input->read(reinterpret_cast<char*>(pixels.data()),pixels.size()))throw std::runtime_error("partial probe frame");
            Image network{pixels.data(),pixels.data()+size_t(w)*h,w,h,w,w,size_t(w)*h,size_t(w)*h/2};
            if(!geometry.matches_layout(network))throw std::runtime_error("probe layout mismatch");
            const auto image=geometry.content(network);
            auto evaluate=[&](const Image& next,const cv::Mat& truth,double angle,double scale) {
                auto fit=similarity.update(next,{});
                const auto start=std::chrono::steady_clock::now();auto old=translation.update(next,{});
                const double old_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
                Frame frame;frame.motion=fit.motion;
                Json result={{"frame",index},{"similarity",frame_json(frame)["motion"]},{"reason",fit.reason},
                    {"features",fit.features},{"matches",fit.matches},{"inliers",fit.inliers},{"residual_px",fit.residual_px},
                    {"support_cells",fit.support_cells},{"similarity_ms",fit.elapsed_ms},
                    {"extraction_ms",fit.extraction_ms},{"matching_ms",fit.matching_ms},{"fit_ms",fit.fit_ms},
                    {"translation",{{"valid",old.valid},{"dx",old.dx},{"dy",old.dy},{"elapsed_ms",old_ms}}},
                    {"mask_scope","no detector masks in this input-only probe"}};
                if(!truth.empty()) {
                    auto error=[&](const Motion& motion)->Json {
                        if(!motion.usable())return nullptr;
                        double worst=0;
                        for(double y:{.1,.5,.9})for(double x:{.1,.5,.9}) {
                            auto predicted=motion.transform({x,y,0,0});
                            const double tx=truth.at<double>(0,0)*x*image.width+truth.at<double>(0,1)*y*image.height+truth.at<double>(0,2);
                            const double ty=truth.at<double>(1,0)*x*image.width+truth.at<double>(1,1)*y*image.height+truth.at<double>(1,2);
                            worst=std::max(worst,std::hypot(predicted.x*image.width-tx,predicted.y*image.height-ty));
                        }
                        return worst;
                    };
                    result["warp"]={{"angle_degrees",angle},{"scale",scale},{"center_dx",.05},{"center_dy",-.025},
                        {"similarity_grid_max_error_px",error(fit.motion)},{"translation_grid_max_error_px",error(old)}};
                }
                std::cout<<result.dump()<<'\n';
            };
            if(!warps)evaluate(image,{},0,1);
            else for(double angle:{-8.,0.,8.})for(double scale:{.94,1.,1.06}) {
                similarity.reset();translation.reset();similarity.update(image,{});translation.update(image,{});
                auto affine=cv::getRotationMatrix2D(cv::Point2f(image.width/2.f,image.height/2.f),angle,scale);
                affine.at<double>(0,2)+=image.width*.05;affine.at<double>(1,2)-=image.height*.025;
                cv::Mat warped;
                cv::warpAffine(cv::Mat(image.height,image.width,CV_8U,const_cast<uint8_t*>(image.y),image.y_stride),
                               warped,affine,cv::Size(image.width,image.height));
                std::vector<uint8_t> uv(size_t(image.width)*image.height/2,128);
                evaluate({warped.data,uv.data(),image.width,image.height,int(warped.step),image.width,
                          warped.step*warped.rows,uv.size()},affine,angle,scale);
            }
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
