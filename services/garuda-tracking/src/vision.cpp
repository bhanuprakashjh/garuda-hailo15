#include "garuda_tracking/vision.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace garuda::fresh {
bool defer_person_embeddings_for_car(const Target& t,const Config& cfg,bool enabled) {
    return enabled&&cfg.association_embedding_gate==0&&t.id&&t.lock_id&&
        t.label=="car"&&!t.pending_box&&!t.identity_retained&&
        (t.state=="tracking"||t.state=="coasting");
}
void motion_samples(const Image& img,std::vector<uint8_t>& packed) {
    if(!img.valid())throw std::invalid_argument("invalid motion image");
    packed.resize(160*90*3/2);
    for(int y=0;y<90;++y) {
        const double sy=std::clamp((4*y+.5)*img.height/360-.5,0.,double(img.height-1));
        const int ya=int(sy),yb=std::min(ya+1,img.height-1);const double fy=sy-ya;
        for(int x=0;x<160;++x) {
            const double sx=std::clamp((4*x+.5)*img.width/640-.5,0.,double(img.width-1));
            const int xa=int(sx),xb=std::min(xa+1,img.width-1);const double fx=sx-xa;
            const double a=(1-fx)*img.y[size_t(ya)*img.y_stride+xa]+fx*img.y[size_t(ya)*img.y_stride+xb];
            const double z=(1-fx)*img.y[size_t(yb)*img.y_stride+xa]+fx*img.y[size_t(yb)*img.y_stride+xb];
            packed[size_t(y)*160+x]=uint8_t(std::lround((1-fy)*a+fy*z));
        }
    }
    std::fill(packed.begin()+160*90,packed.end(),128);
}
Box resize_nv12_crop(const Image& img,const Box& b,int ow,int oh,std::vector<uint8_t>& packed) {
    if(!img.valid()||ow<2||oh<2||ow>1024||oh>1024||ow%2||oh%2||
       !std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.w)||!std::isfinite(b.h)||b.w<=0||b.h<=0)
        throw std::invalid_argument("invalid person crop");
    const int x0=int(std::floor(std::clamp(b.x,0.,1.)*img.width/2))*2;
    const int y0=int(std::floor(std::clamp(b.y,0.,1.)*img.height/2))*2;
    const int x1=int(std::ceil(std::clamp(b.x+b.w,0.,1.)*img.width/2))*2;
    const int y1=int(std::ceil(std::clamp(b.y+b.h,0.,1.)*img.height/2))*2;
    if(x1<=x0||y1<=y0)throw std::invalid_argument("empty person crop");
    packed.resize(size_t(ow)*oh*3/2);
    auto plane=[](const uint8_t* src,int stride,int w,int h,int channels,uint8_t* dst,int dw,int dh) {
        for(int y=0;y<dh;++y) {
            const double sy=std::clamp((y+.5)*h/dh-.5,0.,double(h-1));
            const int ya=int(sy),yb=std::min(ya+1,h-1);const double fy=sy-ya;
            for(int x=0;x<dw;++x) {
                const double sx=std::clamp((x+.5)*w/dw-.5,0.,double(w-1));
                const int xa=int(sx),xb=std::min(xa+1,w-1);const double fx=sx-xa;
                for(int c=0;c<channels;++c) {
                    const double a=(1-fx)*src[size_t(ya)*stride+xa*channels+c]+fx*src[size_t(ya)*stride+xb*channels+c];
                    const double z=(1-fx)*src[size_t(yb)*stride+xa*channels+c]+fx*src[size_t(yb)*stride+xb*channels+c];
                    dst[(size_t(y)*dw+x)*channels+c]=uint8_t(std::lround((1-fy)*a+fy*z));
                }
            }
        }
    };
    plane(img.y+size_t(y0)*img.y_stride+x0,img.y_stride,x1-x0,y1-y0,1,packed.data(),ow,oh);
    plane(img.uv+size_t(y0/2)*img.uv_stride+x0,img.uv_stride,(x1-x0)/2,(y1-y0)/2,2,
          packed.data()+size_t(ow)*oh,ow/2,oh/2);
    return {double(x0)/img.width,double(y0)/img.height,double(x1-x0)/img.width,double(y1-y0)/img.height};
}
bool Image::valid() const {
    return y&&uv&&width>=2&&height>=2&&width<=8192&&height<=8192&&width%2==0&&height%2==0&&
           y_stride>=width&&uv_stride>=width&&y_bytes>=size_t(y_stride)*(height-1)+width&&
           uv_bytes>=size_t(uv_stride)*(height/2-1)+width;
}
FrameGeometry FrameGeometry::make(int fw,int fh,int iw,int ih,bool letterbox) {
    if(fw<=0||fh<=0||iw<2||ih<2||iw>8192||ih>8192||iw%2||ih%2)
        throw std::invalid_argument("invalid NV12 geometry");
    FrameGeometry g{iw,ih,0,0,iw,ih};
    if(letterbox) {
        const double scale=std::min(double(iw)/fw,double(ih)/fh);
        g.content_w=int(std::lround(fw*scale));g.content_h=int(std::lround(fh*scale));
        g.content_x=(iw-g.content_w)/2;g.content_y=(ih-g.content_h)/2;
        // Require exact chroma-aligned content/padding, not an undocumented rounding convention.
        if(g.content_w%2||g.content_h%2||g.content_x%2||g.content_y%2||g.content_w<2||g.content_h<2)
            throw std::invalid_argument("letterbox geometry is not chroma aligned");
    }
    return g;
}
Box FrameGeometry::to_frame(const Box& b) const {
    return {(b.x*input_w-content_x)/content_w,(b.y*input_h-content_y)/content_h,
            b.w*input_w/content_w,b.h*input_h/content_h};
}
Image FrameGeometry::content(const Image& input) const {
    if(!input.valid()||input.width!=input_w||input.height!=input_h)return {};
    const size_t y_offset=size_t(content_y)*input.y_stride+content_x;
    const size_t uv_offset=size_t(content_y/2)*input.uv_stride+content_x;
    return {input.y+y_offset,input.uv+uv_offset,content_w,content_h,input.y_stride,input.uv_stride,
            input.y_bytes-y_offset,input.uv_bytes-uv_offset};
}
bool FrameGeometry::matches_layout(const Image& img) const {
    if(!img.valid()||img.width!=input_w||img.height!=input_h)return false;
    int minimum=255,maximum=0;
    for(int y=0;y<input_h;y+=8)for(int x=0;x<input_w;x+=8) {
        if(x>=content_x&&x<content_x+content_w&&y>=content_y&&y<content_y+content_h)continue;
        int value=img.y[size_t(y)*img.y_stride+x];
        minimum=std::min(minimum,value);maximum=std::max(maximum,value);
        auto uv=img.uv+size_t(y/2)*img.uv_stride+(x&~1);
        if(std::abs(int(uv[0])-128)>2||std::abs(int(uv[1])-128)>2||maximum-minimum>2)return false;
    }
    return true;
}
std::optional<Appearance> describe(const Image& img,const Box& b) {
    if(!img.valid()||!std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.w)||!std::isfinite(b.h)||b.w<=0||b.h<=0)
        return std::nullopt;
    // Central body region excludes much of the background and neighboring objects.
    int x0=int(std::clamp(b.x+b.w*.2,0.,1.)*img.width),x1=int(std::clamp(b.x+b.w*.8,0.,1.)*img.width);
    int y0=int(std::clamp(b.y+b.h*.15,0.,1.)*img.height),y1=int(std::clamp(b.y+b.h*.85,0.,1.)*img.height);
    if(x1-x0<8||y1-y0<8) return std::nullopt;
    Appearance hist{};
    int count=0;
    const int step=std::max(1,std::max(x1-x0,y1-y0)/24);
    for(int y=y0;y<y1;y+=step) for(int x=x0;x<x1;x+=step) {
        const auto* uv=img.uv+size_t(y/2)*img.uv_stride+(x&~1);
        hist[(uv[0]/32)*8+uv[1]/32]+=0.8;
        hist[64+img.y[size_t(y)*img.y_stride+x]/32]+=0.2;
        ++count;
    }
    for(auto& x:hist) x/=count;
    return hist;
}
Motion MotionEstimator::update(const Image& img,const std::vector<Detection>& detections) {
    if(!img.valid()) { reset(); return {}; }
    constexpr int W=160,H=90,R=2,search=8;
    std::vector<uint8_t> current(W*H);
    for(int y=0;y<H;++y) for(int x=0;x<W;++x)
        current[y*W+x]=img.y[size_t(y*img.height/H)*img.y_stride+x*img.width/W];
    std::vector<Box> boxes;
    for(const auto& d:detections) if(std::isfinite(d.box.x)&&std::isfinite(d.box.y)&&std::isfinite(d.box.w)&&std::isfinite(d.box.h)) boxes.push_back(d.box);
    auto masked=[](int x,int y,const std::vector<Box>& bs) {
        for(const auto& b:bs) if(x/160.>=b.x-.035&&x/160.<=b.x+b.w+.035&&y/90.>=b.y-.05&&y/90.<=b.y+b.h+.05) return true;
        return false;
    };
    struct Match { int dx,dy,x,y; };
    std::vector<Match> matches;
    if(previous_.size()==current.size()) {
        for(int y=14;y<H-14;y+=12) for(int x=14;x<W-14;x+=16) {
            if(masked(x,y,previous_boxes_)) continue;
            double mean=0,var=0;
            for(int py=-R;py<=R;++py) for(int px=-R;px<=R;++px) mean+=previous_[(y+py)*W+x+px];
            mean/=25;
            for(int py=-R;py<=R;++py) for(int px=-R;px<=R;++px) var+=std::pow(previous_[(y+py)*W+x+px]-mean,2);
            if(var/25<64) continue;
            double best=1e9,second=1e9; int bx=0,by=0;
            for(int dy=-search;dy<=search;++dy) for(int dx=-search;dx<=search;++dx) {
                if(masked(x+dx,y+dy,boxes)) continue;
                double sad=0;
                for(int py=-R;py<=R;++py) for(int px=-R;px<=R;++px)
                    sad+=std::abs(int(previous_[(y+py)*W+x+px])-int(current[(y+dy+py)*W+x+dx+px]));
                if(sad<best) { second=best;best=sad;bx=dx;by=dy; } else second=std::min(second,sad);
            }
            if(best<25*25&&second>best*1.2+10&&std::abs(bx)<search&&std::abs(by)<search)
                matches.push_back({bx,by,x,y});
        }
    }
    Motion result;
    if(matches.size()>=6) {
        size_t best_count=0; int best_dx=0,best_dy=0;
        for(const auto& candidate:matches) {
            size_t count=0;
            for(const auto& m:matches) if(std::abs(m.dx-candidate.dx)<=1&&std::abs(m.dy-candidate.dy)<=1) ++count;
            if(count>best_count) { best_count=count;best_dx=candidate.dx;best_dy=candidate.dy; }
        }
        if(best_count>=6&&best_count>=matches.size()*.65) {
            double dx=0,dy=0; int xmin=W,xmax=0,ymin=H,ymax=0;
            for(const auto& m:matches) if(std::abs(m.dx-best_dx)<=1&&std::abs(m.dy-best_dy)<=1) {
                dx+=m.dx;dy+=m.dy;xmin=std::min(xmin,m.x);xmax=std::max(xmax,m.x);ymin=std::min(ymin,m.y);ymax=std::max(ymax,m.y);
            }
            if(xmax-xmin>W/3&&ymax-ymin>H/3) result={dx/best_count/W,dy/best_count/H,true};
        }
    }
    previous_=std::move(current);previous_boxes_=std::move(boxes);
    return result;
}

} // namespace garuda::fresh
