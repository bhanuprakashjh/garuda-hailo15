#pragma once
#include "vision.hpp"
#include <deque>
#include <mutex>
#include <optional>
#include <condition_variable>

namespace garuda::fresh {
struct SourceFrame {
    uint64_t timestamp_ns=0;
    int width=0,height=0;
    std::vector<uint8_t> pixels;
    Image image() const;
};
// Own at most four NV12 frames of a declared bound (the node's 1280x720 paired source by
// default; the native sensor stream, up to 3840x2160, when the profile asks for native-pixel
// crops). Never retain media-library/DMA references. Only exact ISP timestamps pair; no
// nearest-frame fallback. Optional bounded waiting lets the independent source callback catch
// up (maximum 50 ms).
class SourceFrames {
public:
    struct Stats {size_t buffered=0;uint64_t pushed=0,matched=0,missing=0,evicted=0,invalid=0;};
    explicit SourceFrames(int max_width=1280,int max_height=720);
    bool push(uint64_t timestamp_ns,const Image&);
    std::optional<SourceFrame> take(uint64_t timestamp_ns,unsigned wait_ms=0);
    Stats stats() const;
    int max_width() const {return max_width_;}
    int max_height() const {return max_height_;}
private:
    mutable std::mutex mutex_;
    std::condition_variable ready_;
    std::deque<SourceFrame> frames_;
    uint64_t last_timestamp_=0;
    int max_width_,max_height_;
    Stats stats_;
};
}
