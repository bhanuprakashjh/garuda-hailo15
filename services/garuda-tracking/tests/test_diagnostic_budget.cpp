#include "../../../hosts/hailo15l/diagnostic_budget.hpp"
#include <cassert>
#include <sstream>
int main() {
    using namespace garuda::h15l;
    // Over a GiB appears available, but almost all belongs to CMA: reject capture.
    std::istringstream pressure("MemAvailable: 1081344 kB\nCmaFree: 1038592 kB\n");
    auto low=diagnostic_headroom(pressure);
    assert(low&&*low==42752*1024ULL);
    assert(!diagnostic_fits(low,900*MiB,MiB));
    std::istringstream normal("MemAvailable: 1400000 kB\nCmaFree: 1000000 kB\n");
    assert(diagnostic_fits(diagnostic_headroom(normal),900*MiB,64*MiB));
    assert(!diagnostic_fits(400*MiB,diagnostic_reserve+MiB,2*MiB));
    assert(!diagnostic_fits(diagnostic_reserve-1,900*MiB,0));
    std::istringstream missing("MemAvailable: 1400000 kB\n");
    assert(!diagnostic_headroom(missing));
    std::istringstream malformed("MemAvailable: huge kB\nCmaFree: 0 kB\n");
    assert(!diagnostic_headroom(malformed));
    std::istringstream reversed("MemAvailable: 1 kB\nCmaFree: 2 kB\n");
    assert(diagnostic_headroom(reversed)==0);
}
