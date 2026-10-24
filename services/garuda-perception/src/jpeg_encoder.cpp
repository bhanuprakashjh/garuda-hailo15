#include "garuda/jpeg_encoder.hpp"
#include <turbojpeg.h>
#include <stdexcept>
#include <string>
#include <cstddef>

namespace garuda {
JpegEncoder::JpegEncoder(int quality) : m_handle(tjInitCompress()), m_quality(quality) {
    if (!m_handle) throw std::runtime_error("tjInitCompress failed");
}
JpegEncoder::~JpegEncoder() { if (m_handle) tjDestroy((tjhandle)m_handle); }

std::vector<unsigned char> JpegEncoder::encode_nv12(const unsigned char* y, int y_stride, const unsigned char* uv, int uv_stride, int width, int height) {
    if (width <= 0 || height <= 0 || y_stride < width || uv_stride < 2 * ((width + 1) / 2)) {
        throw std::invalid_argument(std::string("encode_nv12 precondition violated: width=") + std::to_string(width) + " height=" + std::to_string(height) + " y_stride=" + std::to_string(y_stride) + " uv_stride=" + std::to_string(uv_stride) + " (uv_stride must be >= " + std::to_string(2 * ((width + 1) / 2)) + ")");
    }
    // TurboJPEG wants planar I420: de-interleave NV12's UV plane into U and V.
    const int cw = (width + 1) / 2, ch = (height + 1) / 2;
    m_u.resize((size_t)cw * ch); m_v.resize((size_t)cw * ch);
    for (int r = 0; r < ch; ++r) {
        const unsigned char* src = uv + (size_t)r * uv_stride; unsigned char* du = m_u.data() + (size_t)r * cw; unsigned char* dv = m_v.data() + (size_t)r * cw;
        for (int c = 0; c < cw; ++c) { du[c] = src[2 * c]; dv[c] = src[2 * c + 1]; }
    }
    const unsigned char* planes[3] = {y, m_u.data(), m_v.data()};
    int strides[3] = {y_stride, cw, cw};
    unsigned char* out = nullptr; unsigned long out_size = 0;
    int rc = tjCompressFromYUVPlanes((tjhandle)m_handle, planes, width, strides, height, TJSAMP_420, &out, &out_size, m_quality, TJFLAG_FASTDCT);
    if (rc != 0) { if (out) tjFree(out); throw std::runtime_error(std::string("tjCompressFromYUVPlanes: ") + tjGetErrorStr2((tjhandle)m_handle)); }
    std::vector<unsigned char> jpg(out, out + out_size); tjFree(out); return jpg;
}
}
