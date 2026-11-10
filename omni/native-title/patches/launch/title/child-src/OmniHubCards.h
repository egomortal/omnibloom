// OMNI_HUB_CARDS_V1 (s2): Omni's view of the Omnibloom suite (SUITE-PLUGIN-STANDARD v1.1).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Reads the ID cards Setup writes to /data/hub/apps/<id>.json. A card counts only when Setup's receipt
// /data/hub/receipts/<id>.json matches it: same id and version, same port when the receipt has one, and the
// receipt's card_sha256 equals the card file's SHA-256 (required here). The same validation rules as Bloom Core
// (hub.c): id [a-z0-9-], port 1024-65535 (a title may have none), never 8760/9021/2121, paths "/..." only.
// Bloom Core does not have to be running: Omni reads the files itself, so everything works with it down.
//
// Used by: the title (Master Control origin, Apps menu, Send to Downloads via Bloom Core) and the child engine
// (the console-port block: connect() wrap, request filter, redirect hops). Header-only, libc + std only.
#pragma once
#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include <algorithm>
#include <mutex>
#include <string>
#include <vector>
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#pragma clang diagnostic ignored "-Wcast-align"
#pragma clang diagnostic ignored "-Wsign-compare"
#include "hub_json.h"
#include "hub_sha256.h"
#pragma clang diagnostic pop
#ifndef OMNI_HUB_DIR
#define OMNI_HUB_DIR "/data/hub"   // host tests build with another folder
#endif

namespace OmniHub {

constexpr int hubPort = 8760;                 // Bloom Core (it has no card)
constexpr int legacyDownloadsPort = 8765;     // the downloads worker, until it has a card
constexpr int legacyMasterControlPort = 8095; // Master Control 0.4.2, until 0.4.3's card exists

struct Card {
    std::string id, name, version, kind, mainPage;
    int port = 0;                              // 0: none (a title)
    std::vector<std::string> publicPages, pageApis, provides;
};

namespace detail {
inline bool validId(const char* s)
{
    const size_t n = strlen(s);
    if (n < 1 || n > 40 || s[0] == '-') return false;
    for (size_t i = 0; i < n; i++) if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '-')) return false;
    return true;
}
inline bool validVersion(const char* s)
{
    const size_t n = strlen(s);
    if (n < 1 || n > 32) return false;
    for (size_t i = 0; i < n; i++) {
        const char c = s[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '+' || c == '_' || c == '-')) return false;
    }
    return true;
}
inline bool validIntent(const char* s)
{
    const size_t n = strlen(s);
    if (n < 1 || n > 64 || s[0] == '.' || s[0] == '-') return false;
    for (size_t i = 0; i < n; i++) if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == '-' || s[i] == '_')) return false;
    return true;
}
inline bool validPath(const char* s)
{
    const size_t n = strlen(s);
    if (n < 1 || n > 128 || s[0] != '/' || strstr(s, "..") || strstr(s, "//")) return false;
    for (size_t i = 0; i < n; i++) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c <= 0x20 || c >= 0x7f || c == '"' || c == '\\' || c == '<' || c == '>' || c == '`' || c == '\'') return false;
    }
    return true;
}
inline bool reserved(long port) { return port == hubPort || port == 9021 || port == 2121; }
// A small regular file (no symlinks), at most `max` bytes.
inline bool readFile(const std::string& path, size_t max, std::string& out)
{
    out.clear();
    const int fd = open(path.c_str(), O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return false;
    struct stat st {};
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size < 0 || static_cast<size_t>(st.st_size) > max) { close(fd); return false; }
    out.resize(static_cast<size_t>(st.st_size));
    size_t got = 0;
    while (got < out.size()) {
        const ssize_t r = read(fd, &out[got], out.size() - got);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        got += static_cast<size_t>(r);
    }
    close(fd);
    if (got != out.size()) { out.clear(); return false; }
    return true;
}
inline std::string sha256Hex(const std::string& s)
{
    hsha h; hsha_init(&h); hsha_update(&h, s.data(), s.size());
    char out[65]; hsha_final_hex(&h, out);
    return out;
}
inline bool strList(const hj* v, std::vector<std::string>& out, bool (*valid)(const char*), int max)
{
    out.clear();
    if (!v) return true;
    if (v->t != HJ_ARR) return false;
    for (const hj* e = v->child; e; e = e->next) {
        if (e->t != HJ_STR || !valid(e->str) || int(out.size()) >= max) return false;
        out.push_back(e->str);
    }
    return true;
}
inline bool parseCard(const std::string& stem, const std::string& text, Card& c)
{
    hj_arena ar {};
    const char* err = nullptr;
    const hj* v = hj_parse(text.data(), text.size(), &ar, &err);
    bool ok = false;
    do {
        if (!v || v->t != HJ_OBJ || hj_getint(v, "hub_api", 0, 1000000) != 1) break;
        const char* id = hj_getstr(v, "id");
        const char* name = hj_getstr(v, "name");
        const char* ver = hj_getstr(v, "version");
        const char* kind = hj_getstr(v, "kind");
        if (!id || !validId(id) || stem != id || !strcmp(id, "hub")) break;
        if (!name || !*name || strlen(name) > 64 || !ver || !validVersion(ver)) break;
        if (!kind || (strcmp(kind, "title") && strcmp(kind, "payload") && strcmp(kind, "service"))) break;
        const bool title = !strcmp(kind, "title");
        long port = 0;
        const hj* pv = hj_get(v, "port");
        if (pv && pv->t != HJ_NULL) { port = hj_getint(v, "port", 1024, 65535); if (port < 0) break; }
        else if (!title) break;
        if (port && reserved(port)) break;
        c.mainPage = "/";
        if (const hj* pages = hj_get(v, "pages")) {
            if (pages->t != HJ_OBJ) break;
            bool bad = false;
            for (const hj* m = pages->child; m; m = m->next) {
                if (m->t != HJ_STR || !validPath(m->str) || !validIntent(m->key)) { bad = true; break; }
                if (!strcmp(m->key, "main")) c.mainPage = m->str;
            }
            if (bad) break;
        }
        if (!strList(hj_get(v, "public_pages"), c.publicPages, validPath, 32)) break;
        if (!strList(hj_get(v, "page_apis"), c.pageApis, validPath, 32)) break;
        if (!strList(hj_get(v, "provides"), c.provides, validIntent, 32)) break;
        c.id = id; c.name = name; c.version = ver; c.kind = kind; c.port = int(port);
        ok = true;
    } while (false);
    hj_arena_free(&ar);
    return ok;
}
// Setup's receipt: small (<= 8 KiB), same id and version, same port when present, and card_sha256 required.
inline bool receiptOk(const Card& c, const std::string& cardSha)
{
    std::string text;
    if (!readFile(std::string(OMNI_HUB_DIR "/receipts/") + c.id + ".json", 8192, text)) return false;
    hj_arena ar {};
    const hj* r = hj_parse(text.data(), text.size(), &ar, nullptr);
    bool ok = false;
    if (r && r->t == HJ_OBJ) {
        const char* id = hj_getstr(r, "id");
        const char* ver = hj_getstr(r, "version");
        const char* sha = hj_getstr(r, "card_sha256");
        const hj* port = hj_get(r, "port");
        ok = id && c.id == id && ver && c.version == ver && sha && cardSha == sha
            && (!port || port->t == HJ_NULL || hj_getint(r, "port", 0, 65535) == c.port);
    }
    hj_arena_free(&ar);
    return ok;
}
struct State { std::mutex m; time_t checkedAt = 0; std::vector<Card> cards; };
inline State& state() { static State s; return s; }
} // namespace detail

// Verified cards, sorted by id. Re-read at most every 5 seconds. Two cards on one port: the later id is dropped
// (Bloom Core marks it a conflict).
inline std::vector<Card> cards()
{
    auto& S = detail::state();
    std::lock_guard<std::mutex> g(S.m);
    const time_t now = time(nullptr);
    if (S.checkedAt && now >= S.checkedAt && now - S.checkedAt < 5) return S.cards;
    S.checkedAt = now;
    std::vector<Card> fresh;
    if (DIR* d = opendir(OMNI_HUB_DIR "/apps")) {
        while (dirent* e = readdir(d)) {
            const std::string n = e->d_name;
            if (n.size() < 6 || n.compare(n.size() - 5, 5, ".json")) continue;
            const std::string stem = n.substr(0, n.size() - 5);
            if (!detail::validId(stem.c_str())) continue;
            std::string text;
            if (!detail::readFile(std::string(OMNI_HUB_DIR "/apps/") + n, 16384, text)) continue;
            Card c;
            if (!detail::parseCard(stem, text, c) || !detail::receiptOk(c, detail::sha256Hex(text))) continue;
            fresh.push_back(std::move(c));
            if (fresh.size() >= 64) break;
        }
        closedir(d);
    }
    std::sort(fresh.begin(), fresh.end(), [](const Card& a, const Card& b) { return a.id < b.id; });
    std::vector<Card> kept;
    for (auto& c : fresh) {
        bool clash = false;
        for (const auto& k : kept) if (c.port && k.port == c.port) clash = true;
        if (!clash) kept.push_back(std::move(c));
    }
    S.cards = kept;
    return kept;
}
inline bool card(const char* id, Card& out)
{
    for (auto& c : cards()) if (c.id == id) { out = c; return true; }
    return false;
}
// Master Control's page port: its verified card's port, else Master Control 0.4.2's 8095.
inline int masterControlPort()
{
    Card c;
    return card("master-control", c) && c.port ? c.port : legacyMasterControlPort;
}
// Console ports that are never opened to web pages, whatever a card says.
inline bool neverForPages(int port) { return detail::reserved(port) || port == 8080 || port == 8084 || port == 8767 || port == 53; }
// May a web page connect to this console port? Verified cards with public pages, plus the old fixed ports while
// those apps have no card (8765 the downloads worker, 8095 Master Control 0.4.2).
inline bool pagePortAllowed(int port)
{
    bool downloads = false, mc = false;
    for (auto& c : cards()) {
        if (c.id == "downloads") downloads = true;
        if (c.id == "master-control") mc = true;
        if (c.port == port && !neverForPages(port) && !c.publicPages.empty()) return true;
    }
    return (port == legacyDownloadsPort && !downloads) || (port == legacyMasterControlPort && !mc);
}
inline bool pathMatches(const std::string& rule, const std::string& path)
{
    if (rule == "/") return path == "/" || path == "/index.html";
    if (!rule.empty() && rule.back() == '/') return !path.compare(0, rule.size(), rule);
    return path == rule;
}
// Request rule for a verified card app's port. The app's own page (same origin) and loads with no page (typed in,
// or opened by Omni) reach anything on it except /hub/ (intents come only from Bloom Core); any other page only its
// public_pages. page_apis stay reachable only from the app's own page. Not a card port: false (the port rules decide).
inline bool pathBlocked(int port, const std::string& path, bool sameOrigin, bool noDocument, std::string* app = nullptr)
{
    for (auto& c : cards()) {
        if (c.port != port || !port) continue;
        if (app) *app = c.id;
        if (!path.compare(0, 5, "/hub/")) return true;   // an app's intent endpoint (Bloom Core only): never from web content
        if (sameOrigin || noDocument) return false;
        for (auto& p : c.publicPages) if (pathMatches(p, path)) return false;
        return true;
    }
    return false;
}

// The console's own IPv4 address ("" when unknown): a UDP socket's local address after connect() (no packet is
// sent). Replaces the old hard-coded address; refreshed every 30 seconds.
inline std::string consoleIPv4()
{
    static std::mutex m;
    static time_t at = 0;
    static std::string ip;
    std::lock_guard<std::mutex> g(m);
    const time_t now = time(nullptr);
    if (at && now >= at && now - at < 30) return ip;
    at = now;
    const int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return ip;
    sockaddr_in to {};
    to.sin_family = AF_INET; to.sin_port = htons(53);
    inet_pton(AF_INET, "1.1.1.1", &to.sin_addr);
    if (!connect(s, reinterpret_cast<const sockaddr*>(&to), sizeof(to))) {
        sockaddr_in me {}; socklen_t n = sizeof(me);
        char text[INET_ADDRSTRLEN] = "";
        if (!getsockname(s, reinterpret_cast<sockaddr*>(&me), &n) && me.sin_addr.s_addr && (ntohl(me.sin_addr.s_addr) >> 24) != 127
            && inet_ntop(AF_INET, &me.sin_addr, text, sizeof(text))) ip = text;
    }
    close(s);
    return ip;
}

// One HTTP/1.0 exchange with a loopback service (blocking, with timeouts). Returns the status (0: no answer).
inline int http(int port, const char* method, const char* path, const std::string& body, std::string& reply,
    const std::string& extraHeaders = std::string(), int timeoutMs = 1500)
{
    reply.clear();
    const int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return 0;
    timeval tv { timeoutMs / 1000, (timeoutMs % 1000) * 1000 };
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    sockaddr_in a {};
    a.sin_family = AF_INET; a.sin_port = htons(static_cast<uint16_t>(port)); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(s, reinterpret_cast<const sockaddr*>(&a), sizeof(a))) { close(s); return 0; }
    char head[512];
    snprintf(head, sizeof(head), "%s %s HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nUser-Agent: Omni\r\nConnection: close\r\n%s",
        method, path, port, body.empty() ? "" : "Content-Type: application/json\r\n");
    std::string req = head;
    if (!body.empty()) req += "Content-Length: " + std::to_string(body.size()) + "\r\n";
    req += extraHeaders + "\r\n" + body;
    size_t sent = 0;
    while (sent < req.size()) {
        const ssize_t w = send(s, req.data() + sent, req.size() - sent, 0);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) { close(s); return 0; }
        sent += static_cast<size_t>(w);
    }
    std::string all;
    char buf[4096];
    for (;;) {
        const ssize_t r = recv(s, buf, sizeof(buf), 0);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        all.append(buf, static_cast<size_t>(r));
        if (all.size() > (512u << 10)) { close(s); return 0; }
    }
    close(s);
    int status = 0;
    if (all.compare(0, 5, "HTTP/") || sscanf(all.c_str(), "HTTP/%*d.%*d %d", &status) != 1) return 0;
    const size_t end = all.find("\r\n\r\n");
    if (end != std::string::npos) reply = all.substr(end + 4);
    return status;
}

// An app Bloom Core lists right now (GET /v1/apps), for the Apps menu.
struct LiveApp { std::string id, name, version, kind, mainPage; int port = 0; bool verified = false, up = false; std::vector<std::string> provides; };
// false: Bloom Core did not answer (not installed, or not running).
inline bool liveApps(std::vector<LiveApp>& out)
{
    out.clear();
    std::string body;
    if (http(hubPort, "GET", "/v1/apps", std::string(), body) != 200) return false;
    hj_arena ar {};
    const hj* v = hj_parse(body.data(), body.size(), &ar, nullptr);
    const hj* apps = v && v->t == HJ_OBJ ? hj_get(v, "apps") : nullptr;
    for (const hj* a = apps && apps->t == HJ_ARR ? apps->child : nullptr; a && out.size() < 32; a = a->next) {
        if (a->t != HJ_OBJ) continue;
        LiveApp x;
        const char* id = hj_getstr(a, "id");
        if (!id || !detail::validId(id)) continue;
        x.id = id;
        if (const char* s = hj_getstr(a, "name")) x.name = std::string(s).substr(0, 64);
        if (const char* s = hj_getstr(a, "version")) x.version = std::string(s).substr(0, 32);
        if (const char* s = hj_getstr(a, "kind")) x.kind = s;
        const long port = hj_getint(a, "port", 1024, 65535);
        x.port = port > 0 && !detail::reserved(port) ? int(port) : 0;
        const hj* pages = hj_get(a, "pages");
        if (const char* m = pages ? hj_getstr(pages, "main") : nullptr) if (detail::validPath(m)) x.mainPage = m;
        const hj* ver = hj_get(a, "verified");
        const hj* up = hj_get(a, "up");
        x.verified = ver && ver->t == HJ_TRUE;
        x.up = up && up->t == HJ_TRUE;
        detail::strList(hj_get(a, "provides"), x.provides, detail::validIntent, 32);
        out.push_back(std::move(x));
    }
    hj_arena_free(&ar);
    return apps != nullptr;
}
inline std::string jsonString(const std::string& s)
{
    std::string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20) { char u[8]; snprintf(u, sizeof(u), "\\u%04x", c); o += u; }
        else o += char(c);
    }
    return o + "\"";
}
// Sends an intent through Bloom Core with its token (read from /data/hub/token; never given to any page).
// Returns the HTTP status (200: the app took it; 404/503: nobody to take it; 0: Bloom Core not running).
inline int sendIntent(const char* intent, const std::string& argsJson)
{
    std::string token;
    if (!detail::readFile(OMNI_HUB_DIR "/token", 256, token)) return 0;
    while (!token.empty() && (token.back() == '\n' || token.back() == '\r' || token.back() == ' ')) token.pop_back();
    if (token.empty()) return 0;
    std::string reply;
    const std::string body = std::string("{\"intent\":") + jsonString(intent) + ",\"from\":\"omni\",\"args\":" + argsJson + "}";
    return http(hubPort, "POST", "/v1/intent", body, reply, "X-Hub-Token: " + token + "\r\n", 4000);
}
// Is an app that provides `intent` verified and up in Bloom Core right now?
inline bool provider(const char* intent)
{
    std::vector<LiveApp> apps;
    if (!liveApps(apps)) return false;
    for (auto& a : apps) if (a.verified && a.up) for (auto& p : a.provides) if (p == intent) return true;
    return false;
}

} // namespace OmniHub
