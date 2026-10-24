#pragma once
#include <vector>
namespace garuda {
class JpegEncoder {
public:
    explicit JpegEncoder(int quality = 80);
    ~JpegEncoder();
    JpegEncoder(const JpegEncoder&) = delete; JpegEncoder& operator=(const JpegEncoder&) = delete;
    // Preconditions: width,height > 0; y_stride >= width; uv_stride >= 2*ceil(width/2) (NV12 rows carry ceil(width/2) UV pairs).
    // Throws std::invalid_argument otherwise, std::runtime_error on encoder failure.
    std::vector<unsigned char> encode_nv12(const unsigned char* y, int y_stride, const unsigned char* uv, int uv_stride, int width, int height);
private:
    void* m_handle; int m_quality; std::vector<unsigned char> m_u, m_v;
};
}
