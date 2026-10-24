#include "garuda_tracking/capture_stream.hpp"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>

using namespace garuda::fresh;
using Json=nlohmann::json;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
void wait_active(CaptureStream& stream) {
    for(int i=0;i<200&&!stream.active();++i)std::this_thread::sleep_for(std::chrono::milliseconds(1));
    CHECK(stream.active());
}
int connect_to(CaptureStream& stream,int frames=1,int every=1,bool wait=true) {
    int fd=::socket(AF_INET,SOCK_STREAM,0);CHECK(fd>=0);
    timeval timeout{2,0};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
    sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(stream.port());a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    CHECK(!::connect(fd,reinterpret_cast<sockaddr*>(&a),sizeof(a)));
    auto req=Json{{"recording_id","native-test"},{"frames",frames},{"every",every},{"deadline_ms",1000}}.dump()+"\n";
    CHECK(::send(fd,req.data(),req.size(),MSG_NOSIGNAL)==ssize_t(req.size()));if(wait)wait_active(stream);return fd;
}
std::string read_bytes(int fd,size_t n) {
    std::string out(n,'\0');size_t used=0;
    while(used<n){auto count=::recv(fd,out.data()+used,n-used,0);CHECK(count>0);used+=size_t(count);}return out;
}
std::pair<Json,std::string> packet(int fd) {
    CHECK(read_bytes(fd,4)=="GRC1");uint32_t lengths[2];auto raw=read_bytes(fd,8);std::memcpy(lengths,raw.data(),8);
    auto meta=Json::parse(read_bytes(fd,ntohl(lengths[0])));return {meta,read_bytes(fd,ntohl(lengths[1]))};
}
int main() {
    try {
        CaptureStream stream(0);
        std::vector<uint8_t> bytes(12*12*3/2,238);
        std::string expected;
        for(int y=0;y<8;++y)for(int x=0;x<8;++x){bytes[y*12+x]=uint8_t(y*8+x);expected+=char(y*8+x);}
        for(int y=0;y<4;++y)for(int x=0;x<8;++x){bytes[12*12+y*12+x]=uint8_t(64+y*8+x);expected+=char(64+y*8+x);}
        Image image{bytes.data(),bytes.data()+12*12,8,8,12,12,12*12,12*6};
        int fd=connect_to(stream,1,2);
        stream.enqueue(image,{{"sequence",1}});
        stream.enqueue(image,{{"sequence",2}});
        auto first=packet(fd);CHECK(first.first["sequence"]==2);CHECK(first.first["sample_index"]==0);
        CHECK(first.second==expected);
        auto end=packet(fd);CHECK(end.first["complete"]==true);CHECK(end.first["sent"]==1);CHECK(end.second.empty());::close(fd);
        fd=connect_to(stream);stream.enqueue(image,{{"sequence",3}});
        CHECK(packet(fd).first["sample_index"]==0);CHECK(packet(fd).first["complete"]==true);::close(fd);
        CaptureStream paired(0,{},true);
        fd=connect_to(paired,1,2);
        paired.enqueue(image,{{"isp_timestamp_ns",100}}); // unsampled input does not require a pair
        paired.enqueue(image,{{"isp_timestamp_ns",200}},&image,200);
        auto pair=packet(fd);CHECK(pair.second==expected+expected);
        CHECK(pair.first["source_image"]["byte_offset"]==expected.size());
        CHECK(pair.first["source_image"]["isp_timestamp_ns"]==200);
        CHECK(packet(fd).first["complete"]==true);::close(fd);
        fd=connect_to(paired);paired.enqueue(image,{{"isp_timestamp_ns",300}},&image,301);
        auto missing=packet(fd);CHECK(missing.first["complete"]==false);
        CHECK(missing.first["error"]=="exact_source_pair_missing");CHECK(missing.first["sent"]==0);::close(fd);
        fd=connect_to(stream,100);
        bytes.resize(1280*720*3/2,90);
        image={bytes.data(),bytes.data()+1280*720,1280,720,1280,1280,1280*720,1280*360};
        int large_fd=connect_to(paired);paired.enqueue(image,{{"isp_timestamp_ns",400}},&image,400);
        auto large=packet(large_fd);CHECK(large.first["complete"]==false);
        CHECK(large.first["error"]=="paired_pixel_limit");::close(large_fd);
        for(int i=0;i<10;++i)stream.enqueue(image,{{"sequence",i+1}});
        CHECK(stream.status()["queue_frames"].get<int>()<=2);
        for(int i=0;i<300&&stream.active();++i)std::this_thread::sleep_for(std::chrono::milliseconds(1));
        CHECK(!stream.active());CHECK(!stream.status()["error"].get<std::string>().empty());::close(fd);
        CaptureStream denied(0,[]{return false;});fd=connect_to(denied,1,1,false);
        char c;CHECK(::recv(fd,&c,1,0)==0);CHECK(!denied.active());::close(fd);
        std::cout<<"capture stream: exact stride packing, paired exposure/payload, sampling, restart, bounded slow-peer scenarios passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
