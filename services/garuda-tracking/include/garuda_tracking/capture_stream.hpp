#pragma once
#include "vision.hpp"
#include <nlohmann/json.hpp>
#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>

namespace garuda::fresh {
// Bench-only loopback stream: one client, two queued frames plus one in flight.
// No disk writes. A slow consumer terminates the capture instead of dropping
// undisclosed middle frames or blocking inference on network I/O.
class CaptureStream {
public:
    explicit CaptureStream(uint16_t port,std::function<bool()> can_record={},bool require_source=false);
    ~CaptureStream();
    uint16_t port() const {return port_;}
    bool active() const {return active_.load();}
    void enqueue(const Image& exact_model_input,nlohmann::json metadata,
                 const Image* paired_source=nullptr,uint64_t source_timestamp_ns=0);
    nlohmann::json status() const;
private:
    struct Packet {std::string metadata,pixels;};
    int listener_=-1;
    uint16_t port_=0;
    std::atomic<bool> running_{true},active_{false};
    std::thread worker_;
    mutable std::mutex mutex_;
    std::condition_variable ready_;
    std::deque<Packet> queue_;
    size_t requested_=0,every_=1,tick_=0,enqueued_=0,sent_=0;
    std::string recording_id_,error_;
    std::function<bool()> can_record_;
    bool require_source_=false;
    void run();
    void serve(int fd);
};
}
