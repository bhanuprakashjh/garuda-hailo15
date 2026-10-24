// PC bench pixel-format adapter, no inference. Same BT.601 limited-range
// coefficients as the NumPy reference, including round-to-even chroma averaging.
#include <cstdint>
#include <algorithm>
#include <cmath>

extern "C" int garuda_rgb_nv12(const uint8_t* rgb, uint8_t* dst, int w, int h) {
    if(!rgb||!dst||w<=0||h<=0||w>4096||h>2160||w%2||h%2)return -1;
    auto clamp=[](int value){return std::clamp(value,0,255);};
    auto quarter_even=[](int sum){int q=sum/4, rem=sum%4;return q+(rem>2||(rem==2&&(q&1)));};
    auto* uv=dst+w*h;
    for(int y=0;y<h;y+=2)for(int x=0;x<w;x+=2) {
        int us=0,vs=0;
        for(int dy=0;dy<2;++dy)for(int dx=0;dx<2;++dx) {
            int offset=(y+dy)*w+x+dx;
            const auto* p=rgb+offset*3;
            int r=p[0],g=p[1],b=p[2];
            dst[offset]=clamp(((66*r+129*g+25*b+128)>>8)+16);
            us+=clamp(((-38*r-74*g+112*b+128)>>8)+128);
            vs+=clamp(((112*r-94*g-18*b+128)>>8)+128);
        }
        uv[y/2*w+x]=quarter_even(us);uv[y/2*w+x+1]=quarter_even(vs);
    }
    return 0;
}

// Invert the actual controlled HEF's full-range affine RGB conversion.
// Average chroma BEFORE rounding/clipping, as in its calibration preparation.
extern "C" int garuda_rgb_nv12_full(const uint8_t* rgb,uint8_t* dst,int w,int h) {
    if(!rgb||!dst||w<=0||h<=0||w>4096||h>2160||w%2||h%2)return -1;
    auto byte=[](double v){return uint8_t(std::clamp(std::nearbyint(v),0.,255.));};
    auto* uv=dst+w*h;
    for(int y=0;y<h;y+=2)for(int x=0;x<w;x+=2) {
        double us=0,vs=0;
        for(int dy=0;dy<2;++dy)for(int dx=0;dx<2;++dx) {
            const int offset=(y+dy)*w+x+dx;
            const auto* p=rgb+offset*3;
            const double yy=(double(p[1])+(.343/1.765)*p[2]+(.711/1.4)*p[0])/(1+.343/1.765+.711/1.4);
            dst[offset]=byte(yy);
            us+=(p[2]-yy)/1.765+128;
            vs+=(p[0]-yy)/1.4+128;
        }
        uv[y/2*w+x]=byte(us/4);uv[y/2*w+x+1]=byte(vs/4);
    }
    return 0;
}
