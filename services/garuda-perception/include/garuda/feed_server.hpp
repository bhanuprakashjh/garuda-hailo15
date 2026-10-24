#pragma once
#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace garuda {
class FeedServer {
public:
    explicit FeedServer(uint16_t port);
    ~FeedServer();
    void start();
    void stop();
    // Synchronous: sends to each client under the lock; a client that does not drain within
    // 100 ms is dropped, so a call blocks at most 100 ms per slow client. Acceptable for M0
    // (one local client, the shim).
    void publish(char type, const std::string& payload);
    size_t client_count() const;
private:
    void accept_loop();
    uint16_t m_port; int m_listen_fd = -1; std::atomic<bool> m_running{false}; std::thread m_thread;
    mutable std::mutex m_mu; std::vector<int> m_clients;
};

using CommandHandler = std::function<std::string(const std::string& request_json)>;
class CommandServer {
public:
    CommandServer(uint16_t port, CommandHandler handler);
    ~CommandServer();
    void start();
    void stop();
private:
    void accept_loop();
    void serve(int fd);
    // One per accepted connection. `done` is set once serve() has returned, so accept_loop() can
    // join and drop finished connections instead of letting m_conns grow for the process lifetime.
    struct Conn { std::thread th; std::shared_ptr<std::atomic<bool>> done; };
    uint16_t m_port; CommandHandler m_handler; int m_listen_fd = -1; std::atomic<bool> m_running{false}; std::thread m_thread;
    std::mutex m_conn_mu; std::vector<Conn> m_conns;
};
}
