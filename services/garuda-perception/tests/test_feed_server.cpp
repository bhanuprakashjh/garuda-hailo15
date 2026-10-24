#include "garuda/feed_server.hpp"
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#undef NDEBUG          // asserts are the assertions in these tests; never compile them out
#include <cassert>
#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

static int connect_local(uint16_t port) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0); sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK); assert(::connect(fd, (sockaddr*)&a, sizeof a) == 0); return fd;
}
static void read_exact(int fd, void* p, size_t n) { size_t got = 0; while (got < n) { ssize_t r = ::read(fd, (char*)p + got, n - got); assert(r > 0); got += r; } }

int main() {
    garuda::FeedServer feed(18971); feed.start();
    int c = connect_local(18971);
    for (int i = 0; i < 50 && feed.client_count() == 0; ++i) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    assert(feed.client_count() == 1);
    feed.publish('S', "{\"v\":2}");
    char type; uint32_t len_be; read_exact(c, &type, 1); read_exact(c, &len_be, 4);
    uint32_t len = ntohl(len_be); std::string payload(len, '\0'); read_exact(c, payload.data(), len);
    assert(type == 'S' && payload == "{\"v\":2}");
    ::close(c);

    garuda::CommandServer cmd(18972, [](const std::string& req) { return req.find("\"lock_point\"") != std::string::npos ? "{\"ok\":true}" : "{\"ok\":false,\"error\":\"unknown\"}"; });
    cmd.start();
    int k = connect_local(18972);
    const char* req = "{\"cmd\":\"lock_point\",\"x\":1,\"y\":2}\n"; assert(::write(k, req, strlen(req)) > 0);
    char buf[64] = {0}; ssize_t r = ::read(k, buf, sizeof buf - 1); assert(r > 0);
    assert(std::string(buf) == "{\"ok\":true}\n");
    ::close(k);

    // stop() must not hang or leak a connection: an idle, still-connected client must be
    // dropped (closed) promptly when the server is stopped, not just when it disconnects.
    int j = connect_local(18972);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));  // let accept_loop pick it up
    auto t0 = std::chrono::steady_clock::now();
    cmd.stop();
    auto t1 = std::chrono::steady_clock::now();
    double stop_secs = std::chrono::duration<double>(t1 - t0).count();
    assert(stop_secs < 2.0);
    char drain[16];
    ssize_t r2 = ::read(j, drain, sizeof drain);
    assert(r2 <= 0);  // EOF or error: the server closed the connection
    ::close(j);

    // Destruction must not hang either, and must close out connections even mid-exchange:
    // client A is idle, client B has an unread reply sitting in its socket buffer.
    int A, B;
    std::chrono::steady_clock::time_point t2;
    {
        garuda::CommandServer cmd2(18973, [](const std::string&) { return std::string("{\"ok\":true}"); });
        cmd2.start();
        A = connect_local(18973);
        B = connect_local(18973);
        const char* reqB = "{\"cmd\":\"x\"}\n";
        assert(::write(B, reqB, strlen(reqB)) > 0);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));  // let serve() process B's line
        t2 = std::chrono::steady_clock::now();
    }  // cmd2 destructor runs here: stop() + joins
    auto t3 = std::chrono::steady_clock::now();
    double destroy_secs = std::chrono::duration<double>(t3 - t2).count();
    assert(destroy_secs < 2.0);
    char bufA[1];
    ssize_t rA = ::read(A, bufA, 1);
    assert(rA <= 0);  // idle client closed by the server
    char bufB[64] = {0};
    ssize_t rB1 = ::read(B, bufB, sizeof bufB - 1);
    assert(rB1 > 0 && std::string(bufB) == "{\"ok\":true}\n");  // drain the reply that was already sent
    ssize_t rB2 = ::read(B, bufB, sizeof bufB - 1);
    assert(rB2 <= 0);  // then the connection is closed too
    ::close(A); ::close(B);

    // A handler that throws must not take the connection thread with it: the server answers with
    // the handler-error reply and keeps serving the next line on the same connection.
    {
        garuda::CommandServer cmd3(18974, [](const std::string& req) -> std::string {
            if (req.find("\"boom\"") != std::string::npos) throw std::runtime_error("handler blew up");
            return "{\"ok\":true}";
        });
        cmd3.start();
        int t = connect_local(18974);
        const char* boom = "{\"cmd\":\"boom\"}\n";
        assert(::write(t, boom, strlen(boom)) > 0);
        char rb[128] = {0}; ssize_t rn = ::read(t, rb, sizeof rb - 1);
        assert(rn > 0);
        assert(std::string(rb) == "{\"ok\":false,\"error\":\"handler error\"}\n");
        const char* fine = "{\"cmd\":\"fine\"}\n";
        assert(::write(t, fine, strlen(fine)) > 0);            // same connection still alive
        char rb2[128] = {0}; ssize_t rn2 = ::read(t, rb2, sizeof rb2 - 1);
        assert(rn2 > 0);
        assert(std::string(rb2) == "{\"ok\":true}\n");
        ::close(t);
    }

    feed.stop();
    std::cout << "feed/command ok\n"; return 0;
}
