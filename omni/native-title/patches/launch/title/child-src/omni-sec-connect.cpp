// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_SEC_LOCALHOST_V1 (sec-job1): the console-port block for the native title's child engine
// (/data/omni/native/omni-engine-child.elf, which runs the WebProcess and NetworkProcess payloads).
//
// Every TCP connection a web page causes (page loads, subresources, fetch/XHR, form posts, redirects,
// WebSockets) is opened by libcurl in the NetworkProcess with connect(). The child link wraps
// connect (-Wl,--wrap=connect), so this is the one place every such connection passes through, and
// the decision is made on the actual IP address after DNS. That also covers DNS answers that point a
// public name at 127.0.0.1 or at the console (DNS rebinding).
//
// Blocked: TCP to loopback (127.0.0.0/8, ::1, ::ffff:127.x), the unspecified address, and the
// console's own addresses, on every port except Omni's own UI services:
//   8765  downloads GUI / media worker            (always)
//   8095  Master Control menu and its /api         (always)
//   53    DNS                                      (always)
//   8080  websrv: only while an Omni self-test flag exists (test pages under /fs/data/omni/)
//   8099  s1c redirect test server (omni-redirect-test.elf): only while an Omni self-test flag exists
// So a page can no longer reach the ELF loader (9021), websrv (8080, incl. /hbldr), Payload Manager
// (8084), FTP (2121) or anything else listening on the console.
// Not blocked here: other devices on the home network (a router's page the user types in still
// works). Page-initiated requests to private LAN ranges need the initiator, which only the
// NetworkProcess's request filter knows: see sec-job1/webkit-patch/ for JOB 2.
//
// OMNI_SEC_PNA_CONNECT_V1 (audit OS-001, s3.1): the private-network rule is also enforced HERE, on the address
// the connection really goes to. WebKit's curl handles (CurlContext.cpp, opensocket callback) tag each socket they
// open with the request's URL and its first-party (top-level) site via omniSecConnectContext(); connect() then uses
// that tag once:
//   * initiator's address space: an IP literal or localhost/.local name by its text, any other name by what this
//     process last connected to for it (unknown = public);
//   * a public initiator may not reach a private, link-local, CGNAT, unique-local, loopback or console address,
//     except the top-level site's own host (the user's typed or followed navigation to a LAN name, e.g.
//     http://nas.lan/), and even that is refused once that host was seen on a public address (DNS rebinding);
//   * private initiators, sockets without a tag (not opened for a page), and public destinations are unchanged.
// The request-time check (OmniUBlock.cpp, OMNI_SEC_PNA_V1) stays as the first line; this closes names that only
// resolve to the home network.
//
// Switch: Browser settings "Block pages from reaching the console" (default On) writes
// /data/omni/sec-local-block.off when turned off. Each block is counted in
// /data/omni/native/sec-blocked.txt ("<count> <ip:port>"); the shell shows a notice.
#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <atomic>
#include <mutex>
#include <string>
#include "OmniHubCards.h" // OMNI_HUB_CARDS_V1 (s2): the allowed ports come from the verified ID cards

extern "C" int __real_connect(int, const struct sockaddr*, socklen_t);
extern "C" void omniSecConnectContext(int fd, const char* targetURL, const char* initiatorURL);

namespace {

std::mutex lock;
uint32_t own4[16]; int own4n = 0;                 // console's own IPv4 addresses (network order)
uint8_t own6[8][16]; int own6n = 0;               // and IPv6
bool seeded = false;

time_t testsCheckedAt = 0; bool testsOn = false;   // a *-selftest.flag exists (8080 test pages)
time_t offCheckedAt = 0; bool switchedOff = false; // the user turned the block off
time_t lastLogAt = 0; unsigned suppressed = 0;

void addOwn4(uint32_t a)
{
    if (!a || (ntohl(a) >> 24) == 127) return;
    for (int i = 0; i < own4n; ++i) if (own4[i] == a) return;
    if (own4n < 16) own4[own4n++] = a;
}
void addOwn6(const uint8_t* a)
{
    static const uint8_t zero[16] = {};
    if (!memcmp(a, zero, 16)) return;
    for (int i = 0; i < own6n; ++i) if (!memcmp(own6[i], a, 16)) return;
    if (own6n < 8) memcpy(own6[own6n++], a, 16);
}
void seed()   // under lock
{
    if (seeded) return;
    seeded = true;
    in_addr a {};
    if (inet_pton(AF_INET, "192.0.2.10", &a) == 1) addOwn4(a.s_addr);   // the console's address today
    // Plus whatever this console calls itself on its outbound connections (learned in connect() below),
    // so a changed DHCP lease is covered after the first page loads.
}
bool selfTests(time_t now)
{
    if (now - testsCheckedAt < 5) return testsOn;
    testsCheckedAt = now; testsOn = false;
    if (DIR* d = opendir("/data/omni")) {
        while (dirent* e = readdir(d)) {
            size_t n = strlen(e->d_name);
            if (n > 14 && !strcmp(e->d_name + n - 14, "-selftest.flag")) { testsOn = true; break; }
        }
        closedir(d);
    }
    return testsOn;
}
bool blockOff(time_t now)
{
    if (now - offCheckedAt < 2) return switchedOff;
    offCheckedAt = now;
    switchedOff = access("/data/omni/sec-local-block.off", F_OK) == 0;
    return switchedOff;
}
void count(const char* where)
{
    // count across processes; best effort (a lost increment only means one notice fewer)
    long long n = 0;
    if (FILE* f = fopen("/data/omni/native/sec-blocked.txt", "r")) { if (fscanf(f, "%lld", &n) != 1) n = 0; fclose(f); }
    char tmp[96]; snprintf(tmp, sizeof(tmp), "/data/omni/native/sec-blocked.%d.tmp", (int)getpid());
    if (FILE* f = fopen(tmp, "w")) { fprintf(f, "%lld %s\n", n + 1, where); fclose(f); rename(tmp, "/data/omni/native/sec-blocked.txt"); }
}

// 0 = not ours to judge (other devices, AF_UNIX, UDP...), 1 = loopback/own address
int localKind(const sockaddr* sa, socklen_t len, int* port, char* text, size_t textSize)
{
    if (!sa) return 0;
    if (sa->sa_family == AF_INET && len >= (socklen_t)sizeof(sockaddr_in)) {
        auto* in = reinterpret_cast<const sockaddr_in*>(sa);
        *port = ntohs(in->sin_port);
        uint32_t a = in->sin_addr.s_addr, h = ntohl(a);
        char ip[INET_ADDRSTRLEN] = "?"; inet_ntop(AF_INET, &in->sin_addr, ip, sizeof(ip));
        snprintf(text, textSize, "%s:%d", ip, *port);
        if ((h >> 24) == 127 || h == 0) return 1;
        for (int i = 0; i < own4n; ++i) if (own4[i] == a) return 1;
        return 0;
    }
    if (sa->sa_family == AF_INET6 && len >= (socklen_t)sizeof(sockaddr_in6)) {
        auto* in6 = reinterpret_cast<const sockaddr_in6*>(sa);
        *port = ntohs(in6->sin6_port);
        const uint8_t* b = in6->sin6_addr.s6_addr;
        char ip[INET6_ADDRSTRLEN] = "?"; inet_ntop(AF_INET6, &in6->sin6_addr, ip, sizeof(ip));
        snprintf(text, textSize, "[%s]:%d", ip, *port);
        static const uint8_t loop[16] = { 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1 }, zero[16] = {};
        if (!memcmp(b, loop, 16) || !memcmp(b, zero, 16)) return 1;
        static const uint8_t mapped[12] = { 0,0,0,0, 0,0,0,0, 0,0,0xff,0xff };
        if (!memcmp(b, mapped, 12)) {
            uint32_t a; memcpy(&a, b + 12, 4);
            if ((ntohl(a) >> 24) == 127 || !a) return 1;
            for (int i = 0; i < own4n; ++i) if (own4[i] == a) return 1;
            return 0;
        }
        for (int i = 0; i < own6n; ++i) if (!memcmp(own6[i], b, 16)) return 1;
        return 0;
    }
    return 0;
}

void learn(int fd)   // under lock: our own address on an outbound connection
{
    sockaddr_storage me {}; socklen_t n = sizeof(me);
    if (getsockname(fd, reinterpret_cast<sockaddr*>(&me), &n)) return;
    if (me.ss_family == AF_INET) addOwn4(reinterpret_cast<sockaddr_in*>(&me)->sin_addr.s_addr);
    else if (me.ss_family == AF_INET6) {
        const uint8_t* b = reinterpret_cast<sockaddr_in6*>(&me)->sin6_addr.s6_addr;
        static const uint8_t mapped[12] = { 0,0,0,0, 0,0,0,0, 0,0,0xff,0xff };
        if (!memcmp(b, mapped, 12)) { uint32_t a; memcpy(&a, b + 12, 4); addOwn4(a); }
        else if (!(b[0] == 0xfe && (b[1] & 0xc0) == 0x80)) addOwn6(b);
    }
}

// ---- OMNI_SEC_PNA_CONNECT_V1 ------------------------------------------------------------------------
enum Space { SpacePublic, SpacePrivate, SpaceLocal, SpaceUnknown };

// The host of a URL, lowercased, without brackets, port, userinfo or trailing dots ("" when there is no "://").
// Same parsing as OmniUBlock.cpp's pnaHost(), so both layers agree on what the initiator is.
std::string hostOf(const char* url)
{
    if (!url) return {};
    std::string u(url); auto s = u.find("://"); if (s == std::string::npos) return {};
    s += 3; auto e = u.find_first_of("/?#", s); std::string h = u.substr(s, e == std::string::npos ? std::string::npos : e - s);
    if (auto at = h.rfind('@'); at != std::string::npos) h = h.substr(at + 1);
    if (!h.empty() && h[0] == '[') { auto c = h.find(']'); return c == std::string::npos ? std::string() : h.substr(1, c - 1); }
    if (auto c = h.rfind(':'); c != std::string::npos) h = h.substr(0, c);
    for (auto& ch : h) if (ch >= 'A' && ch <= 'Z') ch = ch - 'A' + 'a';
    while (!h.empty() && h.back() == '.') h.pop_back();
    return h;
}
// One binary classifier for every address (IPv4, IPv6, IPv4-mapped IPv6).
Space space4(uint32_t h)   // host byte order
{
    if ((h >> 24) == 127 || (h >> 24) == 0) return SpaceLocal;
    if ((h >> 24) == 10 || (h >> 20) == 0xAC1 || (h >> 16) == 0xC0A8 || (h >> 16) == 0xA9FE || (h >> 22) == (100u << 2 | 1)) return SpacePrivate;
    return SpacePublic;
}
Space space6(const uint8_t* b)
{
    static const uint8_t loop[16] = { 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1 }, zero[16] = {}, mapped[12] = { 0,0,0,0, 0,0,0,0, 0,0,0xff,0xff };
    if (!memcmp(b, loop, 16) || !memcmp(b, zero, 16)) return SpaceLocal;
    if (!memcmp(b, mapped, 12)) { uint32_t a; memcpy(&a, b + 12, 4); return space4(ntohl(a)); }
    if ((b[0] & 0xfe) == 0xfc || (b[0] == 0xfe && (b[1] & 0xc0) == 0x80)) return SpacePrivate;   // fc00::/7, fe80::/10
    return SpacePublic;
}
Space peerSpace(const sockaddr* sa)   // the console's own addresses are Local (localKind() already said so)
{
    if (sa->sa_family == AF_INET) return space4(ntohl(reinterpret_cast<const sockaddr_in*>(sa)->sin_addr.s_addr));
    return space6(reinterpret_cast<const sockaddr_in6*>(sa)->sin6_addr.s6_addr);
}
Space literalSpace(const std::string& h)   // SpaceUnknown when h is an ordinary name
{
    if (h.empty()) return SpaceUnknown;
    if (h == "localhost" || (h.size() > 10 && !h.compare(h.size() - 10, 10, ".localhost"))) return SpaceLocal;
    if (h.size() > 6 && !h.compare(h.size() - 6, 6, ".local")) return SpacePrivate;
    in_addr a4; if (inet_pton(AF_INET, h.c_str(), &a4) == 1) return space4(ntohl(a4.s_addr));
    uint8_t a6[16]; if (inet_pton(AF_INET6, h.c_str(), a6) == 1) return space6(a6);
    return SpaceUnknown;
}

// Tags from omniSecConnectContext, keyed by socket, used once by the next connect() on that socket.
struct Tag { int fd = -1; std::string target, initiator; };
Tag tags[64]; unsigned tagNext = 0;
// Address space each name was last connected to in this process (bounded; oldest replaced).
struct Seen { std::string host; Space space = SpaceUnknown; };
Seen seen[256]; unsigned seenNext = 0;

Space seenSpace(const std::string& h)   // under lock
{
    for (auto& s : seen) if (!s.host.empty() && s.host == h) return s.space;
    return SpaceUnknown;
}
void remember(const std::string& h, Space sp)   // under lock; names only
{
    if (h.empty() || literalSpace(h) != SpaceUnknown) return;
    for (auto& s : seen) if (s.host == h) { s.space = sp; return; }
    seen[seenNext++ % 256] = Seen { h, sp };
}
bool takeTag(int fd, Tag& out)   // under lock
{
    for (auto& t : tags) if (t.fd == fd) { out = std::move(t); t = Tag(); return true; }
    return false;
}
// 0 = allowed, else the reason it is refused. Under lock.
const char* pnaVerdict(const Tag& tag, Space peer)
{
    const std::string target = hostOf(tag.target.c_str()), from = hostOf(tag.initiator.c_str());
    if (peer == SpacePublic) { remember(target, SpacePublic); return nullptr; }
    if (from.empty()) { remember(target, peer); return nullptr; }                 // not started by a page
    Space fromSpace = literalSpace(from);
    if (fromSpace == SpaceUnknown) fromSpace = seenSpace(from);
    if (fromSpace == SpacePrivate || fromSpace == SpaceLocal) { remember(target, peer); return nullptr; }   // private page -> private: allowed
    if (target == from) {                                                         // the top-level site's own host
        if (seenSpace(target) == SpacePublic) return "a public site's name now points into the home network (DNS rebinding)";
        remember(target, peer);
        return nullptr;
    }
    return "a public page may not reach the home network or the console";
}

} // namespace

// Called by WebKit's curl opensocket callback (CurlContext.cpp, OMNI_SEC_PNA_CONNECT_V1) for every socket it opens.
extern "C" void omniSecConnectContext(int fd, const char* targetURL, const char* initiatorURL)
{
    if (fd < 0) return;
    std::lock_guard<std::mutex> g(lock);
    Tag* slot = nullptr;
    for (auto& t : tags) if (t.fd == fd) { slot = &t; break; }
    if (!slot) slot = &tags[tagNext++ % 64];
    slot->fd = fd; slot->target = targetURL ? targetURL : ""; slot->initiator = initiatorURL ? initiatorURL : "";
}

extern "C" int __wrap_connect(int fd, const struct sockaddr* sa, socklen_t len)
{
    int type = 0; socklen_t tl = sizeof(type);
    const bool stream = !getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &tl) && type == SOCK_STREAM;
    if (!stream || !sa || (sa->sa_family != AF_INET && sa->sa_family != AF_INET6))
        return __real_connect(fd, sa, len);

    int port = 0; char where[80] = "";
    bool local;
    const char* pnaRefused = nullptr; std::string pnaFrom;
    {
        std::lock_guard<std::mutex> g(lock); seed(); local = localKind(sa, len, &port, where, sizeof(where)) == 1;
        Tag tag;
        if (takeTag(fd, tag) && !blockOff(time(nullptr))) {   // OMNI_SEC_PNA_CONNECT_V1: the page's rule on the real address
            pnaRefused = pnaVerdict(tag, local ? SpaceLocal : peerSpace(sa));
            if (pnaRefused) pnaFrom = hostOf(tag.initiator.c_str()) + " -> " + hostOf(tag.target.c_str());
        }
    }
    if (pnaRefused) {
        fprintf(stderr, "sec: blocked %s at %s: %s (OMNI_SEC_PNA_CONNECT_V1)\n", pnaFrom.c_str(), where, pnaRefused);
        count(where);
        errno = ECONNREFUSED;
        return -1;
    }
    if (local) {
        const time_t now = time(nullptr);
        bool allowed = port == 53 || OmniHub::pagePortAllowed(port);   // s2: card apps with public pages (8765/8095 until they have cards)
        bool off = false;
        {
            std::lock_guard<std::mutex> g(lock);
            if (!allowed && (port == 8080 || port == 8099) && selfTests(now)) allowed = true;   // s1c: 8099 = redirect test server
            if (!allowed) off = blockOff(now);
        }
        if (!allowed && !off) {
            {
                std::lock_guard<std::mutex> g(lock);
                if (now != lastLogAt) {
                    fprintf(stderr, "sec: blocked a page connection to %s (OMNI_SEC_LOCALHOST_V1)%s\n", where,
                            suppressed ? " (more suppressed)" : "");
                    lastLogAt = now; suppressed = 0;
                } else ++suppressed;
            }
            count(where);
            errno = ECONNREFUSED;
            return -1;
        }
        if (!allowed && off) {
            static std::atomic<bool> told { false };
            if (!told.exchange(true)) fprintf(stderr, "sec: console-port block switched off by the user; allowing %s\n", where);
        }
        return __real_connect(fd, sa, len);
    }
    int r = __real_connect(fd, sa, len);
    if (r == 0 || errno == EINPROGRESS) {
        int saved = errno;
        { std::lock_guard<std::mutex> g(lock); learn(fd); }
        errno = saved;
    }
    return r;
}

// Proof string for the build checks (grep in the engine).
extern "C" const char omni_sec_localhost_v1_tag[] = "OMNI_SEC_LOCALHOST_V1 connect block (sec-job1)";
extern "C" const char omni_sec_pna_connect_v1_tag[] = "OMNI_SEC_PNA_CONNECT_V1 connect-time private-network rule (s3.1)";
