#!/usr/bin/env python3
"""OMNI_SEND_LINK_V1 (2026-11-16): send a web link from a phone or PC to Omni, instead of typing it with the controller.

While Omni runs (and the setting is on; it is off by default) it answers on the home network at http://<console IP>:8770:
  GET /       a one-page form (address + the 6-digit code shown in Omni), inline HTML/CSS/JS, nothing external
  POST /send  {url, code} as a form or JSON
A link that passes is opened in a new tab (tab limit, memory guard and private-tab rules as for "Open in new tab"),
with the notice "Opened a link sent from <client IP>". Browser settings > "Send links from your phone" shows the
address and code; D-pad left/right turns it off (closes the socket; removes /data/omni/send-link-on.flag) or on (new code),
Cross shows how to use it.
  - server thread with BLOCKING sockets + SO_RCVTIMEO/SO_SNDTIMEO (O_NONBLOCK fails with errno 13 in the title);
    poll() 250 ms on the listening socket so "off" closes it without a non-blocking socket
  - one request per connection, <= 8 KiB, 2 s for the whole request; home-network peers only
  - code: 6 random digits per start, constant-time compare, 5 wrong codes lock it for 60 s
  - links: http(s) only, <= 4096 characters, no user name/password, no control characters/spaces/backslashes
  - the server thread never touches WebKit: it queues links (mutex) and the UI tick opens them; links are never logged
  - no new dynamic imports (socket/bind/listen/accept/poll/getifaddrs/getsockname are already the title's)
New files: engine/entry/OmniSendLink.h (pure + server, no WebKit/SDL types: host-tested) and OmniSendLinkShell.h.
Edits: OmniBrowser.cpp (2 includes, 1 tick call), OmniBrowserSettings.h (declarations, the row, its input).
Anchors are lines the earlier recipe patches leave alone. Idempotent.
usage: apply_send_link.py <engine tree>"""
import sys
from pathlib import Path

MARK = 'OMNI_SEND_LINK_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

SEND_LINK_H = r'''// OMNI_SEND_LINK_V1: send a web link from a phone or PC to Omni on the console.
// A tiny HTTP server on the LAN (port 8770) while Omni runs: GET / is a one-page form (address + 6-digit code),
// POST /send takes {url, code} as a form or JSON. A link that passes the code and the checks below is queued for the
// UI thread, which opens it in a new tab (OmniSendLinkShell.h). Nothing else from a request is ever acted on.
//  - blocking sockets with SO_RCVTIMEO/SO_SNDTIMEO (O_NONBLOCK fails with errno 13 in the PS5 title); poll() with a
//    250 ms timeout lets the accept loop see "stop" without a non-blocking socket
//  - one request per connection, at most 8 KiB, 2 s for the whole request
//  - pairing: a random 6-digit code per start, compared in constant time; 5 wrong codes lock it for 60 s
//  - links: http(s) only, at most 4096 characters, no user name/password, no control characters or spaces
//  - only peers on a private network (10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, 127/8)
//  - links are never logged
// No WebKit or SDL types: the pure parts are tested on the host (OmniSendLinkTest.cpp, g++), like OmniNetGrabber.h.
#pragma once
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <arpa/inet.h>
#include <ifaddrs.h>
#include <netinet/in.h>
#include <poll.h>
#include <unistd.h>

namespace OmniSendLink {

constexpr int defaultPort = 8770;
constexpr std::size_t maxRequest = 8192, maxUrl = 4096, maxQueue = 8, codeDigits = 6;
constexpr uint64_t requestMs = 2000, lockMs = 60000;
constexpr int maxWrongCodes = 5;

// ---------------------------------------------------------------------------------------------- pure parts
inline uint64_t nowMs()
{
    timespec ts {};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return uint64_t(ts.tv_sec) * 1000u + uint64_t(ts.tv_nsec) / 1000000u;
}
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline bool startsWithNoCase(const std::string& s, const char* prefix)
{
    const std::size_t n = strlen(prefix);
    if (s.size() < n) return false;
    for (std::size_t i = 0; i < n; ++i) if (lower(s[i]) != lower(prefix[i])) return false;
    return true;
}
inline bool equalsNoCase(const std::string& a, const char* b) { return a.size() == strlen(b) && startsWithNoCase(a, b); }
inline int hexValue(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }

struct Request {
    std::string method, target, contentType, body;
    std::size_t contentLength = 0;
};
enum class Parse { Incomplete, Ok, Bad, TooLarge, NeedLength };

// One HTTP/1.x request from the first `n` bytes received. Incomplete: read more (until the 8 KiB limit or the timeout).
inline Parse parseRequest(const char* data, std::size_t n, Request& out)
{
    out = Request();
    std::size_t headEnd = std::string::npos, bodyStart = 0;
    for (std::size_t i = 0; i + 1 < n; ++i) {
        if (data[i] == '\n' && data[i + 1] == '\n') { headEnd = i; bodyStart = i + 2; break; }
        if (i + 3 < n && data[i] == '\r' && data[i + 1] == '\n' && data[i + 2] == '\r' && data[i + 3] == '\n') { headEnd = i; bodyStart = i + 4; break; }
    }
    if (headEnd == std::string::npos) return n > maxRequest ? Parse::TooLarge : Parse::Incomplete;
    if (bodyStart > maxRequest) return Parse::TooLarge;
    const std::string head(data, headEnd);
    std::size_t pos = 0;
    auto nextLine = [&](std::string& line) {
        if (pos > head.size()) return false;
        std::size_t e = head.find('\n', pos);
        if (e == std::string::npos) e = head.size();
        line = head.substr(pos, e - pos);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        pos = e + 1;
        return true;
    };
    std::string line;
    if (!nextLine(line)) return Parse::Bad;
    const std::size_t s1 = line.find(' '), s2 = s1 == std::string::npos ? s1 : line.find(' ', s1 + 1);
    if (s1 == std::string::npos || s2 == std::string::npos || line.find(' ', s2 + 1) != std::string::npos) return Parse::Bad;
    out.method = line.substr(0, s1);
    out.target = line.substr(s1 + 1, s2 - s1 - 1);
    const std::string version = line.substr(s2 + 1);
    if (out.method.empty() || out.method.size() > 16) return Parse::Bad;
    for (char c : out.method) if (c < 'A' || c > 'Z') return Parse::Bad;
    if (out.target.empty() || out.target[0] != '/') return Parse::Bad;
    for (unsigned char c : out.target) if (c <= 0x20 || c >= 0x7f) return Parse::Bad;
    if (version != "HTTP/1.1" && version != "HTTP/1.0") return Parse::Bad;
    bool haveLength = false, chunked = false;
    while (nextLine(line)) {
        if (line.empty()) continue;
        if (line[0] == ' ' || line[0] == '\t') return Parse::Bad;   // obsolete line folding
        const std::size_t colon = line.find(':');
        if (colon == std::string::npos || colon == 0) return Parse::Bad;
        const std::string name = line.substr(0, colon);
        for (char c : name) if (c <= 0x20 || c >= 0x7f || c == '(' || c == ')' || c == '"' || c == '/') return Parse::Bad;
        std::size_t vs = colon + 1, ve = line.size();
        while (vs < ve && (line[vs] == ' ' || line[vs] == '\t')) ++vs;
        while (ve > vs && (line[ve - 1] == ' ' || line[ve - 1] == '\t')) --ve;
        const std::string value = line.substr(vs, ve - vs);
        for (unsigned char c : value) if ((c < 0x20 && c != '\t') || c == 0x7f) return Parse::Bad;
        if (equalsNoCase(name, "content-length")) {
            if (value.empty() || value.size() > 6) return value.size() > 6 ? Parse::TooLarge : Parse::Bad;
            std::size_t v = 0;
            for (char c : value) { if (c < '0' || c > '9') return Parse::Bad; v = v * 10 + std::size_t(c - '0'); }
            if (haveLength && v != out.contentLength) return Parse::Bad;
            haveLength = true; out.contentLength = v;
        } else if (equalsNoCase(name, "transfer-encoding")) chunked = true;
        else if (equalsNoCase(name, "content-type")) out.contentType = value;
    }
    if (chunked) return Parse::NeedLength;   // only Content-Length bodies
    if (out.method == "POST" && !haveLength) return Parse::NeedLength;
    if (bodyStart + out.contentLength > maxRequest) return Parse::TooLarge;
    if (n < bodyStart + out.contentLength) return Parse::Incomplete;
    out.body.assign(data + bodyStart, out.contentLength);
    return Parse::Ok;
}

// Appends code point `cp` as UTF-8.
inline void appendUtf8(std::string& o, uint32_t cp)
{
    if (cp < 0x80) o += char(cp);
    else if (cp < 0x800) { o += char(0xc0 | (cp >> 6)); o += char(0x80 | (cp & 0x3f)); }
    else if (cp < 0x10000) { o += char(0xe0 | (cp >> 12)); o += char(0x80 | ((cp >> 6) & 0x3f)); o += char(0x80 | (cp & 0x3f)); }
    else { o += char(0xf0 | (cp >> 18)); o += char(0x80 | ((cp >> 12) & 0x3f)); o += char(0x80 | ((cp >> 6) & 0x3f)); o += char(0x80 | (cp & 0x3f)); }
}

// application/x-www-form-urlencoded: url=...&code=... (other fields ignored; a repeated url or code is refused).
inline bool percentDecode(const std::string& in, std::string& out)
{
    out.clear();
    for (std::size_t i = 0; i < in.size(); ++i) {
        const char c = in[i];
        if (c == '+') out += ' ';
        else if (c == '%') {
            if (i + 2 >= in.size()) return false;
            const int h = hexValue(in[i + 1]), l = hexValue(in[i + 2]);
            if (h < 0 || l < 0) return false;
            out += char(h * 16 + l); i += 2;
        } else out += c;
    }
    return true;
}
inline bool decodeForm(const std::string& body, std::string& url, std::string& code)
{
    bool haveUrl = false, haveCode = false;
    std::size_t pos = 0;
    while (pos <= body.size()) {
        std::size_t e = body.find('&', pos);
        if (e == std::string::npos) e = body.size();
        const std::string pair = body.substr(pos, e - pos);
        pos = e + 1;
        if (pair.empty()) continue;
        const std::size_t eq = pair.find('=');
        std::string k, v;
        if (!percentDecode(pair.substr(0, eq), k)) return false;
        if (!percentDecode(eq == std::string::npos ? std::string() : pair.substr(eq + 1), v)) return false;
        if (k == "url") { if (haveUrl) return false; haveUrl = true; url = v; }
        else if (k == "code") { if (haveCode) return false; haveCode = true; code = v; }
    }
    return haveUrl && haveCode;
}

// JSON: one flat object; string or number values; "url" and "code" required (a repeated one is refused).
inline bool decodeJson(const std::string& s, std::string& url, std::string& code)
{
    std::size_t i = 0;
    auto ws = [&] { while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')) ++i; };
    auto hex4 = [&](uint32_t& v) {
        if (i + 4 > s.size()) return false;
        v = 0;
        for (int k = 0; k < 4; ++k) { const int h = hexValue(s[i + k]); if (h < 0) return false; v = v * 16 + uint32_t(h); }
        i += 4; return true;
    };
    auto str = [&](std::string& o) {
        o.clear();
        if (i >= s.size() || s[i] != '"') return false;
        ++i;
        while (i < s.size()) {
            const unsigned char c = (unsigned char)s[i++];
            if (c == '"') return true;
            if (c < 0x20) return false;
            if (c != '\\') { o += char(c); continue; }
            if (i >= s.size()) return false;
            const char e = s[i++];
            switch (e) {
            case '"': o += '"'; break; case '\\': o += '\\'; break; case '/': o += '/'; break;
            case 'b': o += '\b'; break; case 'f': o += '\f'; break; case 'n': o += '\n'; break;
            case 'r': o += '\r'; break; case 't': o += '\t'; break;
            case 'u': {
                uint32_t cp = 0;
                if (!hex4(cp)) return false;
                if (cp >= 0xdc00 && cp <= 0xdfff) return false;
                if (cp >= 0xd800 && cp <= 0xdbff) {
                    uint32_t lo = 0;
                    if (i + 2 > s.size() || s[i] != '\\' || s[i + 1] != 'u') return false;
                    i += 2;
                    if (!hex4(lo) || lo < 0xdc00 || lo > 0xdfff) return false;
                    cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
                }
                appendUtf8(o, cp);
                break;
            }
            default: return false;
            }
        }
        return false;
    };
    auto number = [&](std::string& o) {
        o.clear();
        while (i < s.size() && ((s[i] >= '0' && s[i] <= '9') || s[i] == '-' || s[i] == '+' || s[i] == '.' || s[i] == 'e' || s[i] == 'E')) o += s[i++];
        return !o.empty();
    };
    bool haveUrl = false, haveCode = false;
    ws();
    if (i >= s.size() || s[i] != '{') return false;
    ++i; ws();
    if (i < s.size() && s[i] == '}') return false;
    while (true) {
        std::string k, v;
        ws();
        if (!str(k)) return false;
        ws();
        if (i >= s.size() || s[i] != ':') return false;
        ++i; ws();
        if (i < s.size() && s[i] == '"') { if (!str(v)) return false; }
        else if (!number(v)) return false;
        if (k == "url") { if (haveUrl) return false; haveUrl = true; url = v; }
        else if (k == "code") { if (haveCode) return false; haveCode = true; code = v; }
        ws();
        if (i < s.size() && s[i] == ',') { ++i; continue; }
        if (i < s.size() && s[i] == '}') { ++i; break; }
        return false;
    }
    ws();
    return i == s.size() && haveUrl && haveCode;
}

// The link check. `out` is the link with its scheme in lower case and surrounding white space trimmed.
inline bool validUrl(const std::string& in, std::string& out)
{
    std::size_t b = 0, e = in.size();
    while (b < e && (in[b] == ' ' || in[b] == '\t' || in[b] == '\r' || in[b] == '\n')) ++b;
    while (e > b && (in[e - 1] == ' ' || in[e - 1] == '\t' || in[e - 1] == '\r' || in[e - 1] == '\n')) --e;
    const std::string u = in.substr(b, e - b);
    if (u.empty() || u.size() > maxUrl) return false;
    // UTF-8, and no C0/C1 controls, DEL, space, backslash, line/paragraph separators or BOM
    for (std::size_t i = 0; i < u.size();) {
        const unsigned char c = (unsigned char)u[i];
        uint32_t cp = 0; int more = 0;
        if (c < 0x80) { cp = c; more = 0; }
        else if ((c & 0xe0) == 0xc0) { cp = c & 0x1f; more = 1; }
        else if ((c & 0xf0) == 0xe0) { cp = c & 0x0f; more = 2; }
        else if ((c & 0xf8) == 0xf0) { cp = c & 0x07; more = 3; }
        else return false;
        if (i + 1 + std::size_t(more) > u.size()) return false;
        for (int k = 1; k <= more; ++k) {
            const unsigned char d = (unsigned char)u[i + std::size_t(k)];
            if ((d & 0xc0) != 0x80) return false;
            cp = (cp << 6) | (d & 0x3f);
        }
        if ((more == 1 && cp < 0x80) || (more == 2 && cp < 0x800) || (more == 3 && (cp < 0x10000 || cp > 0x10ffff))) return false;
        if (cp >= 0xd800 && cp <= 0xdfff) return false;
        if (cp <= 0x20 || (cp >= 0x7f && cp <= 0x9f) || cp == '\\' || cp == 0x2028 || cp == 0x2029 || cp == 0xfeff) return false;
        i += 1 + std::size_t(more);
    }
    std::size_t rest;
    if (startsWithNoCase(u, "http://")) rest = 7;
    else if (startsWithNoCase(u, "https://")) rest = 8;
    else return false;
    std::size_t ae = u.find_first_of("/?#", rest);
    if (ae == std::string::npos) ae = u.size();
    const std::string auth = u.substr(rest, ae - rest);
    if (auth.empty() || auth.find('@') != std::string::npos) return false;   // no user name / password
    std::string host, port;
    if (auth[0] == '[') {   // IPv6 literal
        const std::size_t close = auth.find(']');
        if (close == std::string::npos || close < 3) return false;
        for (std::size_t k = 1; k < close; ++k) if (hexValue(auth[k]) < 0 && auth[k] != ':' && auth[k] != '.') return false;
        host = auth.substr(0, close + 1);
        if (close + 1 < auth.size()) { if (auth[close + 1] != ':') return false; port = auth.substr(close + 2); if (port.empty()) return false; }
    } else {
        const std::size_t colon = auth.find(':');
        if (colon != std::string::npos && auth.find(':', colon + 1) != std::string::npos) return false;
        host = auth.substr(0, colon);
        if (colon != std::string::npos) { port = auth.substr(colon + 1); if (port.empty()) return false; }
        if (host.empty()) return false;
        for (unsigned char c : host)
            if (!(c >= 0x80 || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '.' || c == '_')) return false;
    }
    if (!port.empty()) {
        if (port.size() > 5) return false;
        unsigned v = 0;
        for (char c : port) { if (c < '0' || c > '9') return false; v = v * 10 + unsigned(c - '0'); }
        if (v < 1 || v > 65535) return false;
    }
    out = (rest == 7 ? std::string("http://") : std::string("https://")) + u.substr(rest);
    return true;
}

// Constant-time compare of the pairing code (white space in what was typed is ignored: "123 456").
inline bool codeEquals(const std::string& expected, const std::string& typed)
{
    char given[codeDigits] = {};
    std::size_t n = 0;
    unsigned bad = 0;
    for (char c : typed) {
        if (c == ' ' || c == '\t' || c == '-') continue;
        if (n < codeDigits) given[n] = c;
        ++n;
    }
    bad |= unsigned(n != codeDigits) | unsigned(expected.size() != codeDigits);
    volatile unsigned diff = 0;
    for (std::size_t i = 0; i < codeDigits; ++i) {
        const char want = i < expected.size() ? expected[i] : 0;
        diff = diff | unsigned((unsigned char)(want ^ given[i]));
    }
    return !bad && diff == 0;
}

// Wrong-code lockout: `maxWrongCodes` wrong codes lock every attempt out for `lockMs`.
struct Gate {
    enum Result { Ok, Wrong, Locked };
    int wrong = 0;
    uint64_t lockedUntil = 0;
    Result check(const std::string& expected, const std::string& typed, uint64_t now)
    {
        if (lockedUntil && now < lockedUntil) return Locked;
        lockedUntil = 0;
        if (codeEquals(expected, typed)) { wrong = 0; return Ok; }
        if (++wrong >= maxWrongCodes) { wrong = 0; lockedUntil = now + lockMs; }
        return Wrong;
    }
    unsigned retryAfterSeconds(uint64_t now) const { return lockedUntil > now ? unsigned((lockedUntil - now + 999) / 1000) : 0; }
};

inline std::string formatIp(uint32_t hostOrder)
{
    char b[20];
    snprintf(b, sizeof b, "%u.%u.%u.%u", hostOrder >> 24, (hostOrder >> 16) & 255, (hostOrder >> 8) & 255, hostOrder & 255);
    return b;
}
// Home-network peers only (also loopback, link-local and carrier-grade NAT / VPN ranges).
inline bool isLanPeer(uint32_t h)
{
    return (h >> 24) == 10 || (h >> 24) == 127 || (h >> 20) == 0xac1 /* 172.16/12 */ || (h >> 16) == 0xc0a8 /* 192.168/16 */
        || (h >> 16) == 0xa9fe /* 169.254/16 */ || (h >> 22) == (0x6440 >> 6) /* 100.64/10 */;
}

static const char* const pageHtml =
"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Send to Omni</title>"
"<style>"
":root{color-scheme:light dark;--bg:#f4f5f7;--card:#fff;--ink:#16181d;--mute:#5b6270;--line:#d5d9e0;--acc:#2f6fed;--ok:#1d7f46;--bad:#b3261e}"
"@media(prefers-color-scheme:dark){:root{--bg:#111318;--card:#1b1e25;--ink:#eceef2;--mute:#9aa1ad;--line:#343944;--acc:#6b9bff;--ok:#5cc98a;--bad:#ff8a80}}"
"*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}"
"main{max-width:520px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}p{color:var(--mute);margin:0 0 20px}"
"form{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}"
"label{display:block;font-weight:600;margin:0 0 6px}input{width:100%;font:inherit;color:inherit;background:transparent;"
"border:1px solid var(--line);border-radius:10px;padding:12px;margin:0 0 16px}input:focus{outline:2px solid var(--acc);border-color:transparent}"
"#code{letter-spacing:.3em;font-variant-numeric:tabular-nums}"
"button{width:100%;font:inherit;font-weight:600;border:0;border-radius:10px;padding:13px;background:var(--acc);color:#fff}"
"button:disabled{opacity:.6}#msg{min-height:1.5em;margin:14px 0 0;font-weight:600}.ok{color:var(--ok)}.bad{color:var(--bad)}"
"</style></head><body><main><h1>Send to Omni</h1>"
"<p>The link opens in a new tab on your console. The code is in Omni: Browser settings, Send links from your phone.</p>"
"<form id=\"f\" method=\"post\" action=\"/send\">"
"<label for=\"url\">Web address</label>"
"<input id=\"url\" name=\"url\" type=\"url\" inputmode=\"url\" autocomplete=\"off\" autocapitalize=\"off\" spellcheck=\"false\" maxlength=\"4096\" placeholder=\"https://\" required>"
"<label for=\"code\">Code shown on the console</label>"
"<input id=\"code\" name=\"code\" inputmode=\"numeric\" autocomplete=\"one-time-code\" maxlength=\"7\" pattern=\"[0-9 ]{6,7}\" placeholder=\"000000\" required>"
"<button id=\"go\" type=\"submit\">Send</button><div id=\"msg\" role=\"status\"></div></form></main>"
"<script>(function(){var f=document.getElementById('f'),u=document.getElementById('url'),c=document.getElementById('code'),"
"g=document.getElementById('go'),m=document.getElementById('msg');"
"try{var q=new URLSearchParams(location.search).get('url');if(q)u.value=q;}catch(e){}"
"try{var k=localStorage.getItem('omniCode');if(k)c.value=k;}catch(e){}"
"function say(t,ok){m.textContent=t;m.className=ok?'ok':'bad';}"
"f.addEventListener('submit',function(ev){ev.preventDefault();var v=u.value.trim();"
"if(v&&!/^[a-z][a-z0-9+.-]*:/i.test(v))v='https://'+v;g.disabled=true;say('Sending\\u2026',true);"
"fetch('/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:v,code:c.value})})"
".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})"
".then(function(x){say(x.j.message||(x.ok?'Sent':'Not sent'),x.ok);if(x.ok){try{localStorage.setItem('omniCode',c.value);}catch(e){}u.value='';}})"
".catch(function(){say('Omni did not answer. Is it open on the console?',false);})"
".then(function(){g.disabled=false;});});})();</script></body></html>";

struct Response {
    int status = 200;
    std::string contentType = "text/plain; charset=utf-8", body, extraHeaders;
};
inline const char* reason(int status)
{
    switch (status) {
    case 200: return "OK"; case 400: return "Bad Request"; case 403: return "Forbidden"; case 404: return "Not Found";
    case 405: return "Method Not Allowed"; case 408: return "Request Timeout"; case 411: return "Length Required";
    case 413: return "Content Too Large"; case 415: return "Unsupported Media Type"; case 429: return "Too Many Requests";
    case 503: return "Service Unavailable"; default: return "Error";
    }
}
inline std::string serialize(const Response& r)
{
    char head[160];
    snprintf(head, sizeof head, "HTTP/1.1 %d %s\r\nContent-Length: %zu\r\n", r.status, reason(r.status), r.body.size());
    return std::string(head) + "Content-Type: " + r.contentType + "\r\n" + r.extraHeaders
        + "Connection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n"
          "X-Frame-Options: DENY\r\nContent-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
          "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'\r\n\r\n" + r.body;
}
// A reply in the asker's format: JSON for fetch() (JSON request), a small page for a plain form post.
inline Response reply(int status, bool json, const char* message)
{
    Response r; r.status = status;
    if (json) { r.contentType = "application/json"; r.body = std::string("{\"ok\":") + (status == 200 ? "true" : "false") + ",\"message\":\"" + message + "\"}"; }
    else {
        r.contentType = "text/html; charset=utf-8";
        r.body = std::string("<!doctype html><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Send to Omni</title><body style=\"font:16px system-ui,sans-serif;margin:24px\"><p>") + message + "</p><p><a href=\"/\">Send another link</a></p>";
    }
    return r;
}
inline Response replyFor(Parse p)
{
    switch (p) {
    case Parse::TooLarge: return reply(413, false, "That request is too large.");
    case Parse::NeedLength: return reply(411, false, "Send the link with a Content-Length.");
    case Parse::Incomplete: return reply(408, false, "The request took too long.");
    default: return reply(400, false, "Bad request.");
    }
}

// Routes one parsed request. On a link that may be opened, `accepted` is set and the reply says "Sent".
// The code and the lockout come first: without the right code a request learns nothing about the link checks.
inline Response handle(const Request& q, Gate& gate, const std::string& pairCode, uint64_t now, std::string& accepted)
{
    accepted.clear();
    const std::string path = q.target.substr(0, q.target.find('?'));
    if (path == "/") {
        if (q.method != "GET") { Response r = reply(405, false, "Use GET."); r.extraHeaders = "Allow: GET\r\n"; return r; }
        Response r; r.contentType = "text/html; charset=utf-8"; r.body = pageHtml; return r;
    }
    if (path != "/send") return reply(404, false, "Not found.");
    if (q.method != "POST") { Response r = reply(405, false, "Use POST."); r.extraHeaders = "Allow: POST\r\n"; return r; }
    const bool json = startsWithNoCase(q.contentType, "application/json");
    const bool form = startsWithNoCase(q.contentType, "application/x-www-form-urlencoded");
    if (!json && !form) return reply(415, false, "Send a form or JSON.");
    std::string url, code;
    if (!(json ? decodeJson(q.body, url, code) : decodeForm(q.body, url, code))) return reply(400, json, "Send a link and the code.");
    switch (gate.check(pairCode, code, now)) {
    case Gate::Locked: {
        Response r = reply(429, json, "Too many wrong codes. Wait a minute, then try again.");
        r.extraHeaders = "Retry-After: " + std::to_string(gate.retryAfterSeconds(now)) + "\r\n";
        return r;
    }
    case Gate::Wrong: return reply(403, json, "Wrong code. Check the code shown in Omni.");
    case Gate::Ok: break;
    }
    std::string clean;
    if (!validUrl(url, clean)) return reply(400, json, "Only http:// and https:// links up to 4096 characters, without a user name or password.");
    accepted = clean;
    return reply(200, json, "Sent. It opens in a new tab on the console.");
}

// 6 random digits: /dev/urandom, else a mix of clocks and addresses (still unique per start).
inline std::string newCode()
{
    uint64_t v = 0;
    bool got = false;
    if (FILE* f = fopen("/dev/urandom", "rb")) { got = fread(&v, 1, sizeof v, f) == sizeof v; fclose(f); }
    if (!got) {
        timespec a {}, b {};
        clock_gettime(CLOCK_REALTIME, &a); clock_gettime(CLOCK_MONOTONIC, &b);
        int stackVar = 0;
        v = uint64_t(a.tv_nsec) ^ (uint64_t(a.tv_sec) << 20) ^ (uint64_t(b.tv_nsec) << 7) ^ uint64_t(getpid()) * 0x9e3779b97f4a7c15ull
            ^ uint64_t(reinterpret_cast<uintptr_t>(&stackVar));
    }
    v += 0x9e3779b97f4a7c15ull;   // splitmix64 finaliser
    v = (v ^ (v >> 30)) * 0xbf58476d1ce4e5b9ull; v = (v ^ (v >> 27)) * 0x94d049bb133111ebull; v ^= v >> 31;
    char b[8];
    snprintf(b, sizeof b, "%06u", unsigned(v % 1000000u));
    return b;
}

// The console's address on the home network: an up, non-loopback IPv4 interface (a private one first); else the
// interface of the default route (a UDP "connect" sends nothing). Empty when there is none.
inline std::string lanAddress()
{
    constexpr unsigned up = 0x1, loopback = 0x8;   // IFF_UP, IFF_LOOPBACK (FreeBSD and Linux); <net/if.h> stays out of OmniBrowser.cpp
    std::string best, any;
    ifaddrs* list = nullptr;
    if (!getifaddrs(&list) && list) {
        for (ifaddrs* a = list; a; a = a->ifa_next) {
            if (!a->ifa_addr || a->ifa_addr->sa_family != AF_INET || !(a->ifa_flags & up) || (a->ifa_flags & loopback)) continue;
            const uint32_t h = ntohl(reinterpret_cast<const sockaddr_in*>(a->ifa_addr)->sin_addr.s_addr);
            if (!h || (h >> 24) == 127 || (h >> 16) == 0xa9fe) continue;
            if (isLanPeer(h) && best.empty()) best = formatIp(h);
            else if (any.empty()) any = formatIp(h);
        }
        freeifaddrs(list);
    }
    if (!best.empty()) return best;
    const int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd >= 0) {
        sockaddr_in to {};
        to.sin_family = AF_INET; to.sin_port = htons(9); to.sin_addr.s_addr = htonl(0xc6336401u);   // 198.51.100.1 (TEST-NET-2): only the route is looked up
        sockaddr_in me {};
        socklen_t len = sizeof me;
        if (!connect(fd, reinterpret_cast<sockaddr*>(&to), sizeof to) && !getsockname(fd, reinterpret_cast<sockaddr*>(&me), &len)) {
            const uint32_t h = ntohl(me.sin_addr.s_addr);
            if (h && (h >> 24) != 127) { close(fd); return formatIp(h); }
        }
        close(fd);
    }
    return any;
}

// ---------------------------------------------------------------------------------------------- the server
struct Item { std::string url, from; };

class Server {
public:
    enum State { Off, Starting, Listening, Failed };
    ~Server() { stop(); }
    // Starts the accept thread (no-op while running). A new code each start.
    void start(int port = defaultPort)
    {
        if (cur) return;
        cur = std::make_shared<Shared>();
        cur->code = newCode();
        cur->port = port;
        std::shared_ptr<Shared> s = cur;
        std::thread([s] { run(*s); }).detach();
    }
    // Asks the thread to close the socket (within 250 ms) and forgets queued links.
    void stop()
    {
        if (!cur) return;
        cur->stop = true;
        if (cur->pollBroken.load()) wake(cur->port);
        cur.reset();
    }
    bool started() const { return bool(cur); }
    State state() const { return cur ? State(cur->state.load()) : Off; }
    int error() const { return cur ? cur->err.load() : 0; }
    std::string code() const { return cur ? cur->code : std::string(); }
    int port() const { return cur ? cur->port : defaultPort; }
    bool pop(Item& out)
    {
        if (!cur || !cur->pending.load()) return false;
        std::lock_guard<std::mutex> g(cur->lock);
        if (cur->queue.empty()) return false;
        out = std::move(cur->queue.front());
        cur->queue.pop_front();
        cur->pending = int(cur->queue.size());
        return true;
    }

private:
    struct Shared {
        std::atomic<bool> stop { false }, pollBroken { false };
        std::atomic<int> state { Starting }, err { 0 }, pending { 0 };
        std::string code;   // set before the thread starts, never changed
        int port = defaultPort;
        std::mutex lock;
        std::deque<Item> queue;
        Gate gate;          // the server thread's only
    };
    std::shared_ptr<Shared> cur;

    static void setTimeout(int fd, int opt, uint64_t ms)
    {
        timeval tv {};
        tv.tv_sec = time_t(ms / 1000); tv.tv_usec = suseconds_t((ms % 1000) * 1000);
        setsockopt(fd, SOL_SOCKET, opt, &tv, sizeof tv);
    }
    static void sendAll(int fd, const std::string& s)
    {
#ifdef MSG_NOSIGNAL
        const int flags = MSG_NOSIGNAL;
#else
        const int flags = 0;
#endif
        const char* p = s.data();
        std::size_t n = s.size();
        while (n) {
            const ssize_t w = send(fd, p, n, flags);
            if (w < 0 && errno == EINTR) continue;
            if (w <= 0) return;
            p += w; n -= std::size_t(w);
        }
    }
    static void wake(int port)   // only when poll() is unusable: a loopback connect ends the blocking accept
    {
        const int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return;
        setTimeout(fd, SO_SNDTIMEO, 200);
        sockaddr_in a {};
        a.sin_family = AF_INET; a.sin_port = htons(uint16_t(port)); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        (void)connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a);
        close(fd);
    }
    static void serve(int fd, uint32_t peer, Shared& s)
    {
#ifdef SO_NOSIGPIPE
        int one = 1;
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
#endif
        setTimeout(fd, SO_SNDTIMEO, requestMs);
        if (!isLanPeer(peer)) { sendAll(fd, serialize(reply(403, false, "Only devices on your home network can send links."))); return; }
        const uint64_t deadline = nowMs() + requestMs;
        std::string buf;
        Request q;
        Parse p = Parse::Incomplete;
        char chunk[2048];
        while (p == Parse::Incomplete) {
            const uint64_t now = nowMs();
            if (now >= deadline || s.stop) break;
            setTimeout(fd, SO_RCVTIMEO, deadline - now);
            const ssize_t r = recv(fd, chunk, sizeof chunk, 0);
            if (r < 0 && errno == EINTR) continue;
            if (r <= 0) break;
            buf.append(chunk, std::size_t(r));
            if (buf.size() > maxRequest + 1) buf.resize(maxRequest + 1);
            p = parseRequest(buf.data(), buf.size(), q);
        }
        if (p == Parse::Incomplete && buf.empty()) return;   // nothing sent (a port check): just close
        if (p != Parse::Ok) { sendAll(fd, serialize(replyFor(p))); return; }
        std::string url;
        Response r = handle(q, s.gate, s.code, nowMs(), url);
        if (!url.empty()) {
            std::lock_guard<std::mutex> g(s.lock);
            if (s.stop || s.queue.size() >= maxQueue) r = reply(503, startsWithNoCase(q.contentType, "application/json"), "Omni is busy. Try again in a moment.");
            else { s.queue.push_back({ url, formatIp(peer) }); s.pending = int(s.queue.size()); }
        }
        sendAll(fd, serialize(r));
    }
    static void run(Shared& s)
    {
        int fd = -1;
        for (int attempt = 0; attempt < 20 && !s.stop; ++attempt) {   // a previous server may still be closing: up to 10 s
            fd = socket(AF_INET, SOCK_STREAM, 0);
            if (fd < 0) { s.err = errno; break; }
            int one = 1;
            setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
            sockaddr_in a {};
            a.sin_family = AF_INET; a.sin_port = htons(uint16_t(s.port)); a.sin_addr.s_addr = htonl(INADDR_ANY);
            if (!bind(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) && !listen(fd, 4)) break;
            s.err = errno;
            close(fd); fd = -1;
            usleep(500000);
        }
        if (fd < 0) { s.state = Failed; return; }
        s.err = 0;
        s.state = Listening;
        while (!s.stop) {
            if (!s.pollBroken) {
                pollfd pf {};
                pf.fd = fd; pf.events = POLLIN;
                const int n = poll(&pf, 1, 250);
                if (n < 0 && errno != EINTR) { s.pollBroken = true; continue; }
                if (n <= 0) continue;
            }
            sockaddr_in peer {};
            socklen_t len = sizeof peer;
            const int c = accept(fd, reinterpret_cast<sockaddr*>(&peer), &len);
            if (c < 0) { if (errno != EINTR && errno != ECONNABORTED) usleep(100000); continue; }
            if (!s.stop) serve(c, ntohl(peer.sin_addr.s_addr), s);
            close(c);
        }
        close(fd);
        s.state = Off;
    }
};

} // namespace OmniSendLink
'''

SEND_LINK_SHELL_H = r'''// OMNI_SEND_LINK_V1: the shell side of "Send links from your phone" (the server is OmniSendLink.h).
// Included in OmniBrowser.cpp's anonymous namespace after OmniFeatures3.h. Only the UI thread runs this file: the
// server thread never touches WebKit or the tabs, it only queues checked links that omniSlTick() opens here.
// Off by default (review 2026-11-16: no open port unless the user wants one); /data/omni/send-link-on.flag turns it
// on (Browser settings row); turning it off removes the flag and closes the socket.
#pragma once

static OmniSendLink::Server omniSlServer;
static const char* const omniSlOnFlag = "/data/omni/send-link-on.flag";
static int omniSlOnCache = -1;
static bool omniSlOn()
{
    if (omniSlOnCache < 0) omniSlOnCache = access(omniSlOnFlag, F_OK) == 0 ? 1 : 0;
    return omniSlOnCache == 1;
}
static std::string omniSlAddress()   // "<console IP>:8770" (e.g. 10.0.0.20:8770), or empty when the console has no address
{
    static std::string cached;
    static uint32_t at = 0;
    const uint32_t now = SDL_GetTicks();
    if (!at || now - at > 5000) { at = now ? now : 1; cached = OmniSendLink::lanAddress(); }
    return cached.empty() ? cached : cached + ":" + std::to_string(omniSlServer.port());
}
static std::string omniSlHowTo()
{
    const std::string a = omniSlAddress(), c = omniSlServer.code();
    return "On your phone or PC, open " + (a.empty() ? std::string("the console's IP address, port 8770,") : "http://" + a)
        + " and enter code " + c.substr(0, 3) + " " + c.substr(3);
}
static void omniSlTick()
{
    static uint32_t last = 0;
    const uint32_t now = SDL_GetTicks();
    if (now - last < 250) return;
    last = now;
    if (omniTestMode() || !omniSlOn()) return;
    if (!omniSlServer.started()) {
        omniSlServer.start();
        log("send-link: server starting on port 8770");
    }
    static int told = OmniSendLink::Server::Starting;
    const int st = omniSlServer.state();
    if (st != told) {
        told = st;
        if (st == OmniSendLink::Server::Failed) {
            char line[96];
            snprintf(line, sizeof line, "send-link: could not listen on port %d (errno %d)", omniSlServer.port(), omniSlServer.error());
            log(line);
        } else if (st == OmniSendLink::Server::Listening) log("send-link: listening");
    }
    if (editing) return;   // the on-screen keyboard is up: the link waits until it closes
    OmniSendLink::Item it;
    if (!omniSlServer.pop(it) || !omniWebURL(it.url)) return;
    if (omniFxOpenInNewTab(it.url, false, false)) {   // the tab limit, memory guard and private rules apply
        omniFxCloseAll(); settingsOpen = false;
        notice("Opened a link sent from " + it.from);
    } else notice("Couldn't open the link sent from " + it.from + (status.empty() || status == "Ready" ? std::string() : ": " + status));
    log("send-link: link received");   // never the link itself
}

// --- Browser settings row ---------------------------------------------------------------------------
static void omniSlSettingsRow(OmniFxPanel& p)
{
    OmniFxRow r;
    r.id = omniSlRowId; r.label = "Send links from your phone"; r.stepper = true;
    if (!omniSlOn()) r.value = "Off";
    else switch (omniSlServer.state()) {
    case OmniSendLink::Server::Listening: {
        const std::string a = omniSlAddress(), c = omniSlServer.code();
        r.value = "On";
        r.detail = (a.empty() ? std::string("console IP, port 8770") : a) + "  \xc2\xb7  code " + c.substr(0, 3) + " " + c.substr(3);
        break;
    }
    case OmniSendLink::Server::Failed: r.value = "Couldn't start"; r.detail = "port 8770 is in use"; break;
    default: r.value = "Starting"; break;
    }
    p.rows.push_back(r);
}
static bool omniSlSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (!left && !right && !a) return false;
    if (a && omniSlOn() && omniSlServer.state() == OmniSendLink::Server::Listening) { notice(omniSlHowTo()); return true; }
    if (omniSlOn()) {
        unlink(omniSlOnFlag);
        omniSlOnCache = 0;
        omniSlServer.stop();   // the socket closes within 250 ms
        notice("Send links from your phone: off");
        log("send-link: off");
    } else {
        if (FILE* f = fopen(omniSlOnFlag, "w")) { fputs("1\n", f); fclose(f); }
        omniSlOnCache = 1;
        if (!omniTestMode()) omniSlServer.start();   // a new code
        notice(omniSlHowTo());
        log("send-link: on");
    }
    return true;
}
'''


def nl_of(path):
    raw = path.read_bytes()
    return '\r\n' if b'\r\n' in raw else '\n'


def patch(name, edits):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old, new in edits:
        old, new = old.replace('\n', nl), new.replace('\n', nl)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, nl):
    p = root / name
    data = text.replace('\n', nl).encode('utf-8')
    if p.exists():
        have = p.read_bytes()
        if have == data:
            return name + ': already'
        if MARK.encode() not in have:
            sys.exit('%s exists and is not ours: stopping' % name)
    p.write_bytes(data)
    return name + ': written'


BROWSER = [
    ('#include "OmniFeatures2Includes.h" // OMNI_FEATURES_V2\n',
     '#include "OmniFeatures2Includes.h" // OMNI_FEATURES_V2\n'
     '#include "OmniSendLink.h" // OMNI_SEND_LINK_V1: LAN "send a link to Omni" server (no WebKit types)\n'),
    ('#include "OmniFeatures3.h" // OMNI_FEATURES_V3\n',
     '#include "OmniFeatures3.h" // OMNI_FEATURES_V3\n'
     '#include "OmniSendLinkShell.h" // OMNI_SEND_LINK_V1: opens sent links, Browser settings row\n'),
    ('    omniF3Tick(); // OMNI_FEATURES_V3: suggestions, screenshot, dark pages, tab memory\n',
     '    omniF3Tick(); // OMNI_FEATURES_V3: suggestions, screenshot, dark pages, tab memory\n'
     '    omniSlTick(); // OMNI_SEND_LINK_V1: start the LAN server, open links sent from a phone (UI thread only)\n'),
]

SETTINGS = [
    ('static std::string omniFxHomeEdit;\n',
     '// OMNI_SEND_LINK_V1: "Send links from your phone" (OmniSendLinkShell.h)\n'
     'constexpr int omniSlRowId = 850;\n'
     'static void omniSlSettingsRow(OmniFxPanel& p);\n'
     'static bool omniSlSettingsInput(int b);\n'
     'static std::string omniFxHomeEdit;\n'),
    ('    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions\n',
     '    omniSlSettingsRow(p); // OMNI_SEND_LINK_V1\n'
     '    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions\n'),
    ('    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n',
     '    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n'
     '    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n'),
]

nl = nl_of(root / 'OmniBrowser.cpp')
print(write_new('OmniSendLink.h', SEND_LINK_H, nl))
print(write_new('OmniSendLinkShell.h', SEND_LINK_SHELL_H, nl))
print(patch('OmniBrowserSettings.h', SETTINGS))
print(patch('OmniBrowser.cpp', BROWSER))
print('applied ' + MARK)
