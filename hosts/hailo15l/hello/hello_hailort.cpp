#include <cstdio>
#include <hailo/hailort.h>

int main() {
    hailo_version_t v{};
    hailo_status s = hailo_get_library_version(&v);
    if (s != HAILO_SUCCESS) { std::printf("hailo_get_library_version failed: %d\n", (int)s); return 1; }
    std::printf("hailort %u.%u.%u\n", v.major, v.minor, v.revision);
    return 0;
}
