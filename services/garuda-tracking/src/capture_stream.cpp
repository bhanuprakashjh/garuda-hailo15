#include "garuda_tracking/capture_stream.hpp"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <poll.h>
#include <unistd.h>
#include <algorithm>
#include <chrono>
#include <cstring>
#include <stdexcept>

namespace garuda::fresh {
using Json=nlohmann::json;
using Clock=std::chrono::steady_clock;
namespace {
bool send_bytes(int fd,const char* data,size_t size,Clock::time_point deadline) {
    while(size) {
        auto left=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
        if(left<=0)return false;
        pollfd p{fd,POLLOUT,0};if(::poll(&p,1,int(left))<=0)return false;
        auto n=::send(fd,data,size,MSG_NOSIGNAL|MSG_DONTWAIT);
        if(n<0&&(errno==EAGAIN||errno==EINTR))continue;
        if(n<=0)return false;
        data+=n;size-=size_t(n);
    }
    return true;
}
bool send_packet(int fd,const std::string& meta,const std::string& pixels) {
    const auto deadline=Clock::now()+std::chrono::milliseconds(100);
    uint32_t lengths[2]={htonl(uint32_t(meta.size())),htonl(uint32_t(pixels.size()))};
    return send_bytes(fd,"GRC1",4,deadline)&&send_bytes(fd,reinterpret_cast<char*>(lengths),8,deadline)&&
        send_bytes(fd,meta.data(),meta.size(),deadline)&&send_bytes(fd,pixels.data(),pixels.size(),deadline);
}
}
CaptureStream::CaptureStream(uint16_t port,std::function<bool()> can_record,bool require_source)
    :port_(port),can_record_(std::move(can_record)),require_source_(require_source) {
    listener_=::socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0);
    if(listener_<0)throw std::runtime_error("capture socket failed");
    int one=1;::setsockopt(listener_,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));
    sockaddr_in addr{};addr.sin_family=AF_INET;addr.sin_port=htons(port);addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(::bind(listener_,reinterpret_cast<sockaddr*>(&addr),sizeof(addr))||::listen(listener_,1)) {
        ::close(listener_);throw std::runtime_error("capture bind/listen failed");
    }
    socklen_t len=sizeof(addr);::getsockname(listener_,reinterpret_cast<sockaddr*>(&addr),&len);port_=ntohs(addr.sin_port);
    worker_=std::thread([this]{run();});
}
CaptureStream::~CaptureStream() {
    running_=false;active_=false;ready_.notify_all();
    if(worker_.joinable())worker_.join();
    ::close(listener_);
}
Json CaptureStream::status() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return {{"active",active_.load()},{"requested",requested_},{"enqueued",enqueued_},{"sent",sent_},
            {"queue_frames",queue_.size()},{"error",error_},{"recording_id",recording_id_},{"paired_source",require_source_}};
}
void CaptureStream::enqueue(const Image& image,Json metadata,const Image* source,uint64_t source_timestamp_ns) {
    if(!active_)return;
    std::lock_guard<std::mutex> guard(mutex_);
    if(!active_||enqueued_>=requested_||++tick_%every_)return;
    if(!image.valid()||size_t(image.width)*image.height*3/2>2*1024*1024||queue_.size()>=2) {
        error_="invalid_image_or_capture_queue_full";active_=false;ready_.notify_all();return;
    }
    const size_t primary_bytes=size_t(image.width)*image.height*3/2;
    size_t source_bytes=0;
    if(require_source_) {
        if(!source||!source->valid()||!source_timestamp_ns||!metadata.contains("isp_timestamp_ns")||
           !metadata["isp_timestamp_ns"].is_number_integer()||metadata["isp_timestamp_ns"]!=source_timestamp_ns) {
            error_="exact_source_pair_missing";active_=false;ready_.notify_all();return;
        }
        source_bytes=size_t(source->width)*source->height*3/2;
        if(source_bytes>2*1024*1024-primary_bytes) {
            error_="paired_pixel_limit";active_=false;ready_.notify_all();return;
        }
        metadata["source_image"]={{"width",source->width},{"height",source->height},{"pixel_format","NV12"},
            {"packed_stride",source->width},{"byte_offset",primary_bytes},{"byte_length",source_bytes},
            {"isp_timestamp_ns",source_timestamp_ns}};
    }
    metadata["recording_id"]=recording_id_;metadata["sample_index"]=enqueued_;
    metadata["type"]="frame";metadata["pixel_format"]="NV12";
    metadata["input_w"]=image.width;metadata["input_h"]=image.height;
    metadata["packed_stride"]=image.width;
    Packet packet;packet.metadata=metadata.dump();
    if(packet.metadata.size()>128*1024) {error_="metadata_limit";active_=false;ready_.notify_all();return;}
    packet.pixels.resize(primary_bytes+source_bytes);char* out=packet.pixels.data();
    for(int y=0;y<image.height;++y){std::memcpy(out,image.y+size_t(y)*image.y_stride,image.width);out+=image.width;}
    for(int y=0;y<image.height/2;++y){std::memcpy(out,image.uv+size_t(y)*image.uv_stride,image.width);out+=image.width;}
    if(source_bytes) {
        for(int y=0;y<source->height;++y){std::memcpy(out,source->y+size_t(y)*source->y_stride,source->width);out+=source->width;}
        for(int y=0;y<source->height/2;++y){std::memcpy(out,source->uv+size_t(y)*source->uv_stride,source->width);out+=source->width;}
    }
    queue_.push_back(std::move(packet));++enqueued_;ready_.notify_all();
}
void CaptureStream::run() {
    while(running_) {
        pollfd p{listener_,POLLIN,0};if(::poll(&p,1,50)<=0)continue;
        int fd=::accept4(listener_,nullptr,nullptr,SOCK_CLOEXEC);if(fd<0)continue;
        int send_buffer=256*1024;::setsockopt(fd,SOL_SOCKET,SO_SNDBUF,&send_buffer,sizeof(send_buffer));
        try {serve(fd);} catch(const std::exception& e) {
            std::lock_guard<std::mutex> guard(mutex_);error_=e.what();
        }
        {std::lock_guard<std::mutex> guard(mutex_);active_=false;queue_.clear();}
        ::close(fd);
    }
}
void CaptureStream::serve(int fd) {
    std::string request;bool newline=false;const auto request_deadline=Clock::now()+std::chrono::seconds(1);
    while(running_&&Clock::now()<request_deadline&&request.size()<4096) {
        pollfd p{fd,POLLIN,0};if(::poll(&p,1,50)<=0)continue;
        char c;if(::recv(fd,&c,1,MSG_DONTWAIT)!=1)throw std::runtime_error("capture request disconnected");
        if(c=='\n'){newline=true;break;}
        request+=c;
    }
    if(!newline)throw std::runtime_error("capture request incomplete or oversized");
    const auto req=Json::parse(request);
    auto bounded=[&](const char* key,int low,int high) {
        const auto& v=req.at(key);if(!v.is_number_integer())throw std::invalid_argument("integer capture bound required");
        int64_t n=v.get<int64_t>();if(n<low||n>high)throw std::invalid_argument("capture request exceeds bounds");return size_t(n);
    };
    const auto frames=bounded("frames",1,1200),every=bounded("every",1,40),duration=bounded("deadline_ms",100,60000);
    const std::string id=req.at("recording_id").get<std::string>();
    if(id.empty()||id.size()>128)throw std::invalid_argument("invalid recording ID");
    if(can_record_&&!can_record_())throw std::runtime_error("capture memory admission denied");
    {
        std::lock_guard<std::mutex> guard(mutex_);
        requested_=frames;every_=every;recording_id_=id;tick_=enqueued_=sent_=0;error_.clear();queue_.clear();active_=true;
    }
    const auto deadline=Clock::now()+std::chrono::milliseconds(duration);
    while(running_) {
        Packet packet;
        {
            std::unique_lock<std::mutex> guard(mutex_);
            ready_.wait_for(guard,std::chrono::milliseconds(20),[&]{return !queue_.empty()||!active_||!running_;});
            if(!active_||!running_||sent_>=requested_)break;
            if(Clock::now()>=deadline){error_="capture_deadline";break;}
            if(queue_.empty())continue;
            packet=std::move(queue_.front());queue_.pop_front();
        }
        if(!send_packet(fd,packet.metadata,packet.pixels)) {
            std::lock_guard<std::mutex> guard(mutex_);error_="capture_transport_timeout";break;
        }
        {std::lock_guard<std::mutex> guard(mutex_);++sent_;}
    }
    Json footer;
    {
        std::lock_guard<std::mutex> guard(mutex_);active_=false;
        if(error_.empty()&&sent_!=requested_)error_="capture_stopped";
        footer={{"type","end"},{"recording_id",recording_id_},{"sent",sent_},{"requested",requested_},
                {"complete",sent_==requested_&&error_.empty()},{"error",error_}};
    }
    send_packet(fd,footer.dump(),{});
}
}
