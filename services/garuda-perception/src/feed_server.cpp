#include "garuda/feed_server.hpp"
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <stdexcept>

namespace garuda {
static int listen_local(uint16_t port) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0); int one = 1;
    ::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(port); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::bind(fd, (sockaddr*)&a, sizeof a) != 0 || ::listen(fd, 8) != 0) { ::close(fd); return -1; }
    return fd;
}
static int accept_with_timeout(int listen_fd, int ms) {
    pollfd p{listen_fd, POLLIN, 0}; if (::poll(&p, 1, ms) <= 0) return -1;
    return ::accept(listen_fd, nullptr, nullptr);
}

FeedServer::FeedServer(uint16_t port) : m_port(port) {}
FeedServer::~FeedServer() { stop(); }
void FeedServer::start() {
    m_listen_fd = listen_local(m_port); if (m_listen_fd < 0) throw std::runtime_error("FeedServer: bind failed on port " + std::to_string(m_port));
    m_running = true; m_thread = std::thread([this] { accept_loop(); });
}
void FeedServer::stop() {
    if (!m_running.exchange(false)) return;
    if (m_thread.joinable()) m_thread.join();
    std::lock_guard<std::mutex> g(m_mu); for (int c : m_clients) ::close(c); m_clients.clear();
    if (m_listen_fd >= 0) { ::close(m_listen_fd); m_listen_fd = -1; }
}
void FeedServer::accept_loop() {
    while (m_running) {
        int c = accept_with_timeout(m_listen_fd, 100); if (c < 0) continue;
        int one = 1; ::setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        timeval tv{0, 100000}; ::setsockopt(c, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);   // slow client => drop
        std::lock_guard<std::mutex> g(m_mu); m_clients.push_back(c);
    }
}
void FeedServer::publish(char type, const std::string& payload) {
    uint32_t len_be = htonl((uint32_t)payload.size());
    std::string frame; frame.reserve(5 + payload.size()); frame.push_back(type); frame.append((char*)&len_be, 4); frame.append(payload);
    std::lock_guard<std::mutex> g(m_mu);
    for (auto it = m_clients.begin(); it != m_clients.end();) {
        ssize_t n = ::send(*it, frame.data(), frame.size(), MSG_NOSIGNAL);
        if (n != (ssize_t)frame.size()) { ::close(*it); it = m_clients.erase(it); } else ++it;
    }
}
size_t FeedServer::client_count() const { std::lock_guard<std::mutex> g(m_mu); return m_clients.size(); }

CommandServer::CommandServer(uint16_t port, CommandHandler h) : m_port(port), m_handler(std::move(h)) {}
CommandServer::~CommandServer() { stop(); }
void CommandServer::start() {
    m_listen_fd = listen_local(m_port); if (m_listen_fd < 0) throw std::runtime_error("CommandServer: bind failed on port " + std::to_string(m_port));
    m_running = true; m_thread = std::thread([this] { accept_loop(); });
}
void CommandServer::stop() {
    if (!m_running.exchange(false)) return;
    if (m_thread.joinable()) m_thread.join();
    {
        std::lock_guard<std::mutex> g(m_conn_mu);
        for (auto& c : m_conns) if (c.th.joinable()) c.th.join();   // each serve() loop exits within ~200ms (poll timeout + m_running check)
        m_conns.clear();
    }
    if (m_listen_fd >= 0) { ::close(m_listen_fd); m_listen_fd = -1; }
}
void CommandServer::accept_loop() {
    while (m_running) {
        int c = accept_with_timeout(m_listen_fd, 100); if (c < 0) continue;
        timeval tv{0, 100000}; ::setsockopt(c, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);   // slow reader => serve() send fails, closes fd
        std::lock_guard<std::mutex> g(m_conn_mu);
        for (auto it = m_conns.begin(); it != m_conns.end();) {      // reap connections that already finished
            if (it->done->load()) { if (it->th.joinable()) it->th.join(); it = m_conns.erase(it); } else ++it;
        }
        auto done = std::make_shared<std::atomic<bool>>(false);
        m_conns.push_back(Conn{std::thread([this, c, done] { serve(c); done->store(true); }), done});
    }
}
void CommandServer::serve(int fd) {
    std::string acc; char buf[4096];
    while (m_running) {
        pollfd p{fd, POLLIN, 0}; if (::poll(&p, 1, 200) <= 0) continue;
        ssize_t n = ::read(fd, buf, sizeof buf); if (n <= 0) break;
        acc.append(buf, n); size_t nl;
        while ((nl = acc.find('\n')) != std::string::npos) {
            std::string line = acc.substr(0, nl); acc.erase(0, nl + 1);
            std::string reply;   // a throwing handler must not take the connection thread down with it
            try { reply = m_handler(line); } catch (...) { reply = R"({"ok":false,"error":"handler error"})"; }
            reply += "\n";
            if (::send(fd, reply.data(), reply.size(), MSG_NOSIGNAL) != (ssize_t)reply.size()) { ::close(fd); return; }
        }
    }
    ::close(fd);
}
}
