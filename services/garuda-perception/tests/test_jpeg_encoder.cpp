#include "garuda/jpeg_encoder.hpp"
#undef NDEBUG          // asserts are the assertions in these tests; never compile them out
#include <cassert>
#include <cstdio>
#include <vector>
#include <stdexcept>

int main() {
    const int W = 1280, H = 720;
    std::vector<unsigned char> y(W * H), uv(W * H / 2);
    for (int r = 0; r < H; ++r) for (int c = 0; c < W; ++c) y[r * W + c] = (unsigned char)((c / 5) & 0xFF);   // vertical stripes
    for (size_t i = 0; i < uv.size(); ++i) uv[i] = 128;                                                        // grey chroma
    garuda::JpegEncoder enc(80);
    auto jpg = enc.encode_nv12(y.data(), W, uv.data(), W, W, H);
    assert(jpg.size() > 2000 && jpg.size() < 400000);
    assert(jpg[0] == 0xFF && jpg[1] == 0xD8 && jpg[jpg.size() - 2] == 0xFF && jpg[jpg.size() - 1] == 0xD9);
    std::printf("jpeg ok: %zu bytes\n", jpg.size());

    // Guard case: odd width with insufficient uv_stride must throw
    const int ODD_W = 641, ODD_H = 480;
    std::vector<unsigned char> y_odd(ODD_W * ODD_H), uv_odd(ODD_W * ODD_H / 2);
    for (size_t i = 0; i < y_odd.size(); ++i) y_odd[i] = 128;
    for (size_t i = 0; i < uv_odd.size(); ++i) uv_odd[i] = 128;

    // With uv_stride=641 (insufficient for width 641), should throw std::invalid_argument
    try {
        enc.encode_nv12(y_odd.data(), ODD_W, uv_odd.data(), ODD_W, ODD_W, ODD_H);
        assert(false && "should have thrown std::invalid_argument");
    } catch (const std::invalid_argument&) {
        std::printf("guard case 1 ok: rejected odd width with insufficient uv_stride\n");
    }

    // With uv_stride=642 (sufficient for width 641), should encode successfully
    auto jpg_odd = enc.encode_nv12(y_odd.data(), ODD_W, uv_odd.data(), ODD_W + 1, ODD_W, ODD_H);
    assert(jpg_odd.size() > 2000 && jpg_odd.size() < 400000);
    assert(jpg_odd[0] == 0xFF && jpg_odd[1] == 0xD8 && jpg_odd[jpg_odd.size() - 2] == 0xFF && jpg_odd[jpg_odd.size() - 1] == 0xD9);
    std::printf("guard case 2 ok: encoded odd width with correct uv_stride: %zu bytes\n", jpg_odd.size());

    return 0;
}
