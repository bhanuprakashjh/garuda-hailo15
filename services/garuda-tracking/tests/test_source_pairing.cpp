#include "garuda_tracking/source_pairing.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace garuda::fresh;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
int main() {
    try {
        SourceFrames cache;std::vector<uint8_t> pixels(12*12*3/2,238),expected;
        for(int y=0;y<8;++y)for(int x=0;x<8;++x){pixels[y*12+x]=uint8_t(y*8+x);expected.push_back(uint8_t(y*8+x));}
        for(int y=0;y<4;++y)for(int x=0;x<8;++x){pixels[144+y*12+x]=uint8_t(64+y*8+x);expected.push_back(uint8_t(64+y*8+x));}
        Image image{pixels.data(),pixels.data()+144,8,8,12,12,144,72};
        CHECK(cache.push(100,image));std::fill(pixels.begin(),pixels.end(),17);
        auto frame=cache.take(100);CHECK(frame);CHECK(frame->pixels==expected);CHECK(frame->image().valid());
        CHECK(!cache.take(100));
        CHECK(cache.push(200,image));CHECK(!cache.take(201)); // never substitute a nearby exposure
        CHECK(cache.push(202,image));CHECK(!cache.take(201));CHECK(cache.take(202));
        for(uint64_t stamp:{300,310,320,330,340})CHECK(cache.push(stamp,image));
        CHECK(cache.stats().buffered==4);CHECK(cache.stats().evicted==1);CHECK(!cache.take(300));CHECK(cache.take(310));
        CHECK(!cache.push(339,image));CHECK(cache.stats().buffered==0); // regression invalidates history
        CHECK(!cache.push(339,image));CHECK(cache.push(341,image));
        CHECK(!cache.push(342,{}));CHECK(cache.stats().buffered==0);
        auto invalid=image;invalid.y_stride=7;CHECK(!cache.push(343,invalid));
        CHECK(cache.stats().invalid==4);
        std::thread producer([&]{std::this_thread::sleep_for(std::chrono::milliseconds(5));cache.push(400,image);});
        auto waited=cache.take(400,40);producer.join();CHECK(waited);CHECK(waited->timestamp_ns==400);
        CHECK(!cache.take(401,5));
        bool bounded=false;try{cache.take(402,51);}catch(const std::invalid_argument&){bounded=true;}CHECK(bounded);
        // The bound is declared per cache: the default refuses a 4K frame, a native cache (the sensor
        // stream for native-pixel ROI and descriptor crops) accepts it and hands back its own pixels.
        std::vector<uint8_t> big(size_t(3840)*2160*3/2,9);
        Image native{big.data(),big.data()+size_t(3840)*2160,3840,2160,3840,3840,size_t(3840)*2160,size_t(3840)*2160/2};
        CHECK(!cache.push(500,native));
        SourceFrames wide(3840,2160);CHECK(wide.push(500,native));
        auto taken=wide.take(500);CHECK(taken&&taken->image().valid()&&taken->image().width==3840);
        bool refused=false;try{SourceFrames odd(3841,2160);}catch(const std::invalid_argument&){refused=true;}CHECK(refused);
        std::cout<<"source pairing: owned stride copy, exact exposure only, four-frame bound, regression and invalidation passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
