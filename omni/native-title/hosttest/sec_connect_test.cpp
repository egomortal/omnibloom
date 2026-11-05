// SPDX-License-Identifier: GPL-3.0-or-later
// OS-001 regression test for the child engine's connect() wrap (child-src/omni-sec-connect.cpp): the private-network
// rule is applied to the address a page's connection really goes to, after DNS. Built against the s3 file it fails
// (no connect-time rule: omniSecConnectContext is absent); against s3.1 it passes.
// Build: g++ -std=c++17 -I../child-src -DOMNI_HUB_DIR='"/tmp/no-hub"' sec_connect_test.cpp ../child-src/omni-sec-connect.cpp
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

extern "C" int __wrap_connect(int, const struct sockaddr*, socklen_t);
extern "C" void omniSecConnectContext(int fd, const char* targetURL, const char* initiatorURL) __attribute__((weak));
static int realCalls = 0;
extern "C" int __real_connect(int, const struct sockaddr*, socklen_t) { ++realCalls; return 0; }   // the network is never touched

static int fails = 0, passes = 0;
#define CHECK(c, what) do { if (c) { ++passes; printf("ok   %s\n", what); } else { ++fails; printf("FAIL %s\n", what); } } while (0)

// One page connection: curl's opensocket tags the socket, then connect() runs. true = it reached __real_connect.
static bool pageConnect(const char* target, const char* initiator, const char* ip, int port)
{
    int fd = socket(strchr(ip, ':') ? AF_INET6 : AF_INET, SOCK_STREAM, 0);
    if (omniSecConnectContext && target) omniSecConnectContext(fd, target, initiator);
    sockaddr_storage ss {}; socklen_t len;
    if (strchr(ip, ':')) { auto* a = reinterpret_cast<sockaddr_in6*>(&ss); a->sin6_family = AF_INET6; a->sin6_port = htons(port); inet_pton(AF_INET6, ip, &a->sin6_addr); len = sizeof(*a); }
    else { auto* a = reinterpret_cast<sockaddr_in*>(&ss); a->sin_family = AF_INET; a->sin_port = htons(port); inet_pton(AF_INET, ip, &a->sin_addr); len = sizeof(*a); }
    const int before = realCalls;
    errno = 0;
    const int r = __wrap_connect(fd, reinterpret_cast<sockaddr*>(&ss), len);
    const bool reached = realCalls == before + 1;
    if (!reached && !(r == -1 && errno == ECONNREFUSED)) printf("     (unexpected result %d errno %d)\n", r, errno);
    close(fd);
    return reached;
}

int main()
{
    // the core finding: a public page, a public-looking NAME, a private ADDRESS after DNS
    CHECK(!pageConnect("http://rebind.attacker.example/x", "https://attacker.example/", "192.168.1.20", 80), "public page -> name resolving to 192.168.1.20: refused at connect");
    CHECK(!pageConnect("http://lan.attacker.example/", "https://attacker.example/", "10.0.0.7", 8080), "public page -> name resolving to 10.0.0.7: refused");
    CHECK(!pageConnect("http://v6.attacker.example/", "https://attacker.example/", "fd00::5", 80), "public page -> name resolving to fd00::5 (ULA): refused");
    CHECK(!pageConnect("http://ll.attacker.example/", "https://attacker.example/", "fe80::1", 80), "public page -> name resolving to fe80::1 (link-local): refused");
    CHECK(!pageConnect("http://m.attacker.example/", "https://attacker.example/", "::ffff:192.168.1.9", 80), "public page -> IPv4-mapped private address: refused");
    CHECK(!pageConnect("http://lo.attacker.example/", "https://attacker.example/", "127.0.0.1", 8765), "public page -> name resolving to loopback on an Omni port: refused");
    CHECK(!pageConnect("http://cg.attacker.example/", "https://attacker.example/", "100.64.1.1", 80), "public page -> CGNAT address: refused");
    // unchanged behaviour
    CHECK(pageConnect("https://cdn.example/a.js", "https://news.example/", "93.184.216.34", 443), "public page -> public address: allowed");
    CHECK(pageConnect("http://nas.lan/", "http://nas.lan/", "192.168.1.30", 80), "typed LAN name (top-level site's own host): allowed");
    CHECK(pageConnect("http://192.168.1.31/api", "http://nas.lan/", "192.168.1.31", 80), "that LAN page -> another LAN device: allowed");
    CHECK(pageConnect("http://printer.lan/", "http://192.168.1.1/", "192.168.1.40", 80), "private page (IP literal) -> LAN name: allowed");
    CHECK(pageConnect("http://router.local/", "http://router.local/", "192.168.1.1", 80), ".local page: allowed");
    CHECK(pageConnect("http://192.168.1.1/", "", "192.168.1.1", 80), "no initiator (typed address / Omni's own load): allowed");
    CHECK(pageConnect(nullptr, nullptr, "192.168.1.50", 80), "socket not opened for a page (no tag): unchanged, allowed");
    // DNS rebinding of the top-level site itself
    CHECK(pageConnect("https://flip.attacker.example/", "https://flip.attacker.example/", "93.184.216.35", 443), "rebinding site first on a public address: allowed");
    CHECK(!pageConnect("http://flip.attacker.example/steal", "https://flip.attacker.example/", "192.168.1.1", 80), "same site's name now on 192.168.1.1: refused");
    // a tag is used once: the next connect on a reused fd without a new tag is the old (no-page) behaviour
    {
        int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (omniSecConnectContext) omniSecConnectContext(fd, "http://x.attacker.example/", "https://attacker.example/");
        sockaddr_in a {}; a.sin_family = AF_INET; a.sin_port = htons(80); inet_pton(AF_INET, "192.168.1.60", &a.sin_addr);
        const int c0 = realCalls; __wrap_connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a); const bool first = realCalls == c0 + 1;
        const int c1 = realCalls; __wrap_connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a); const bool second = realCalls == c1 + 1;
        CHECK(!first && second, "tag applies to one connect only");
        close(fd);
    }
    printf("SEC CONNECT TESTS: %d passed, %d failed\n", passes, fails);
    return fails ? 1 : 0;
}
