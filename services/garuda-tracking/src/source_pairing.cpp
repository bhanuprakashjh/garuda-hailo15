#include "garuda_tracking/source_pairing.hpp"
#include <cstring>
#include <stdexcept>

namespace garuda::fresh {
Image SourceFrame::image() const {
    if(width<2||height<2||width>3840||height>2160||pixels.size()!=size_t(width)*height*3/2)return {};
    return {pixels.data(),pixels.data()+size_t(width)*height,width,height,width,width,
            size_t(width)*height,size_t(width)*height/2};
}
SourceFrames::SourceFrames(int max_width,int max_height):max_width_(max_width),max_height_(max_height) {
    if(max_width<2||max_height<2||max_width>3840||max_height>2160||max_width%2||max_height%2)
        throw std::invalid_argument("invalid source frame bound");
}
bool SourceFrames::push(uint64_t timestamp,const Image& image) {
    std::lock_guard<std::mutex> guard(mutex_);
    if(!timestamp||!image.valid()||image.width>max_width_||image.height>max_height_||timestamp<=last_timestamp_) {
        frames_.clear();last_timestamp_=timestamp;++stats_.invalid;return false;
    }
    last_timestamp_=timestamp;
    if(frames_.size()>=4){frames_.pop_front();++stats_.evicted;}
    SourceFrame frame;frame.timestamp_ns=timestamp;frame.width=image.width;frame.height=image.height;
    frame.pixels.resize(size_t(image.width)*image.height*3/2);auto* out=frame.pixels.data();
    for(int y=0;y<image.height;++y){std::memcpy(out,image.y+size_t(y)*image.y_stride,image.width);out+=image.width;}
    for(int y=0;y<image.height/2;++y){std::memcpy(out,image.uv+size_t(y)*image.uv_stride,image.width);out+=image.width;}
    frames_.push_back(std::move(frame));++stats_.pushed;ready_.notify_all();return true;
}
std::optional<SourceFrame> SourceFrames::take(uint64_t timestamp,unsigned wait_ms) {
    if(wait_ms>50)throw std::invalid_argument("source pairing wait exceeds bound");
    std::unique_lock<std::mutex> guard(mutex_);
    if(wait_ms)ready_.wait_for(guard,std::chrono::milliseconds(wait_ms),[&]{return last_timestamp_>=timestamp;});
    while(!frames_.empty()&&frames_.front().timestamp_ns<timestamp)frames_.pop_front();
    if(frames_.empty()||frames_.front().timestamp_ns!=timestamp){++stats_.missing;return {};}
    auto frame=std::move(frames_.front());frames_.pop_front();++stats_.matched;return frame;
}
SourceFrames::Stats SourceFrames::stats() const {
    std::lock_guard<std::mutex> guard(mutex_);auto out=stats_;out.buffered=frames_.size();return out;
}
}
