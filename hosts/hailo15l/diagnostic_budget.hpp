#pragma once
#include <cstdint>
#include <istream>
#include <limits>
#include <optional>
#include <sstream>
#include <string>

namespace garuda::h15l {
constexpr uint64_t MiB=1024*1024;
constexpr uint64_t diagnostic_reserve=128*MiB;
constexpr uint64_t capture_byte_limit=128*MiB;
constexpr uint64_t record_byte_limit=32*MiB;

// MemAvailable includes CMA pages, which are not a general-purpose memory budget.
inline std::optional<uint64_t> diagnostic_headroom(std::istream& input) {
    std::optional<uint64_t> available,cma;
    std::string line;
    while(std::getline(input,line)) {
        std::istringstream row(line);std::string key,unit;uint64_t value;
        if(!(row>>key))continue;
        if(key!="MemAvailable:"&&key!="CmaFree:")continue;
        if(!(row>>value>>unit)||unit!="kB"||value>std::numeric_limits<uint64_t>::max()/1024)return {};
        (key=="MemAvailable:"?available:cma)=value*1024;
    }
    if(!available||!cma)return {};
    return *available>*cma?*available-*cma:0;
}
inline bool diagnostic_fits(std::optional<uint64_t> headroom,uint64_t disk_free,uint64_t bytes) {
    return headroom&&*headroom>=diagnostic_reserve&&disk_free>=diagnostic_reserve&&
        bytes<=*headroom-diagnostic_reserve&&bytes<=disk_free-diagnostic_reserve;
}
} // namespace garuda::h15l
