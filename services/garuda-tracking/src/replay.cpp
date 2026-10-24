#include "garuda_tracking/json.hpp"
#include <fstream>
#include <iostream>
#include <memory>

int main(int argc,char** argv) {
    using namespace garuda::fresh;
    try {
        std::cout.setf(std::ios::unitbuf); // bounded interactive SIL request/response
        Config cfg;
        if(argc>2) {std::ifstream f(argv[2]);Json j;f>>j;cfg=config_from_json(j);}
        Tracker tracker(cfg);
        std::ifstream file;
        std::istream* input=&std::cin;
        if(argc>1&&std::string(argv[1])!="-") {file.open(argv[1]);if(!file)throw std::runtime_error("cannot read replay");input=&file;}
        std::string line;size_t row=0;
        while(std::getline(*input,line)) {
            ++row;
            if(line.size()>1024*1024) throw std::runtime_error("replay row too large");
            try {
                auto j=Json::parse(line);
                if(j.contains("cmd")) std::cout<<command(tracker,j,j.at("now_ms"))<<'\n';
                else if(j.contains("heartbeat_ms")) std::cout<<output_json(tracker.snapshot(j.at("heartbeat_ms")))<<'\n';
                else std::cout<<output_json(tracker.update(frame_from_json(j)))<<'\n';
            } catch(const std::exception& e) {throw std::runtime_error("row "+std::to_string(row)+": "+e.what());}
        }
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
