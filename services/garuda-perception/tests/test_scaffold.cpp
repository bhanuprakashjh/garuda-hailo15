#include <nlohmann/json.hpp>
#undef NDEBUG          // asserts are the assertions in these tests; never compile them out
#include <cassert>
#include <cstdio>

int main() {
    nlohmann::json j = {{"v", 2}, {"tracks", nlohmann::json::array()}};
    assert(j.dump() == R"({"tracks":[],"v":2})");
    std::puts("scaffold ok");
    return 0;
}
