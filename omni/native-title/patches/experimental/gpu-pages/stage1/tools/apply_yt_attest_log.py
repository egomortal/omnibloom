"""OMNI_YT_ATTEST_LOG_V1 (2026-11-16, YouTube PO-token rejection experiment): LOGGING ONLY, page-invisible.

YouTube's BotGuard measures the page environment and hashes running code, so this adds NO page script, no hook and no
user-script world. It extends the UI process's existing resource-load observer (WKPageResourceLoadClient, the one
omniNetObserve / OMNI_NET_GRABBER_V1 uses) and logs, per page load:

  * BotGuard/WAA traffic: GenerateIT and Create (jnn-pa.googleapis.com/$rpc/.../Waa/<x> and www.youtube.com/api/jnn/v1/<x>),
    /youtubei/v1/att/get and /youtubei/v1/player: request time from the page's document request, response status,
    Content-Length (the body is NOT visible in the UI process: -1 = no Content-Length), MIME, completion error, durations.
  * googlevideo /videoplayback: status, Content-Length, MIME, sabr=1, and `sps` / the `pot` LENGTH only when they are in
    the URL query (non-SABR URLs). SABR's sps lives in the UMP response body (part 58) = not observable here.
  * a per-page summary line when the next page starts (and every 64 videoplayback responses as a fallback).

What the UI process can see through the WebKit C API: URL, method, status, MIME, expected content length, redirect target,
error code. NOT: request bodies (the SABR POST with the PO token), response bodies (the GenerateIT token, UMP parts), headers.

Privacy: host + path only (googlevideo hosts collapsed to *.googlevideo.com); query values are never logged except the
small integer `sps`; the PO token is reported as a length. No video ids, no cookies, no tokens. Private tabs and the
Media downloads tab are skipped.

Default OFF: /data/omni/yt-attest-log.flag (read once per process). Off = the observer is installed exactly as before
(only for Media downloads / the grabber self-test) and nothing is logged. Lines: "OMNI YTATTESTLOG: ..." on stderr
(the process log).

usage: apply_yt_attest_log.py <engine tree>   (writes engine/entry/OmniYtAttestLog.h, edits engine/entry/OmniBrowser.cpp)
Idempotent: prints 'applied' or 'already'.
"""
import sys
from pathlib import Path

MARK = 'OMNI_YT_ATTEST_LOG_V1'

HEADER = r'''// OMNI_YT_ATTEST_LOG_V1: page-invisible logging of YouTube's attestation traffic (UI-process resource-load observer).
// Pure C++ (no WebKit types) so it is unit-tested on the PC: tools/test_yt_attest_log.cpp.
// Logs host + path only; query values never, except the small integer `sps` and the LENGTH of `pot`.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <unordered_map>

namespace OmniYtAttestLog {

struct Url { std::string host, path, query; bool ok = false; };

inline Url split(const std::string& u)
{
    Url r;
    const auto s = u.find("://");
    if (s == std::string::npos) return r;
    const size_t h = s + 3;
    const size_t e = u.find_first_of("/?#", h);
    r.host = u.substr(h, e == std::string::npos ? std::string::npos : e - h);
    const auto at = r.host.rfind('@'); if (at != std::string::npos) r.host = r.host.substr(at + 1);
    const auto colon = r.host.find(':'); if (colon != std::string::npos) r.host.resize(colon);
    for (auto& c : r.host) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    if (e == std::string::npos) { r.path = "/"; r.ok = !r.host.empty(); return r; }
    const size_t q = u.find_first_of("?#", e);
    r.path = u[e] == '/' ? u.substr(e, q == std::string::npos ? std::string::npos : q - e) : std::string("/");
    if (q != std::string::npos && u[q] == '?') {
        const size_t f = u.find('#', q);
        r.query = u.substr(q + 1, f == std::string::npos ? std::string::npos : f - q - 1);
    }
    r.ok = !r.host.empty();
    return r;
}

inline bool endsWith(const std::string& s, const char* t) { const size_t n = strlen(t); return s.size() >= n && s.compare(s.size() - n, n, t) == 0; }
inline bool startsWith(const std::string& s, const char* t) { return s.rfind(t, 0) == 0; }

// The value of `key` in a query string ("" when absent); found tells absent from empty.
inline std::string param(const std::string& query, const char* key, bool& found)
{
    found = false;
    const size_t klen = strlen(key);
    size_t i = 0;
    while (i <= query.size()) {
        size_t amp = query.find('&', i); if (amp == std::string::npos) amp = query.size();
        if (amp - i >= klen && query.compare(i, klen, key) == 0 && (amp - i == klen || query[i + klen] == '=')) {
            found = true;
            return amp - i == klen ? std::string() : query.substr(i + klen + 1, amp - i - klen - 1);
        }
        i = amp + 1;
    }
    return std::string();
}

enum class Kind { None, Page, GenerateIT, Create, Waa, AttGet, Player, Videoplayback };
inline const char* kindName(Kind k)
{
    switch (k) {
    case Kind::Page: return "page"; case Kind::GenerateIT: return "GenerateIT"; case Kind::Create: return "Create";
    case Kind::Waa: return "waa"; case Kind::AttGet: return "att_get"; case Kind::Player: return "player";
    case Kind::Videoplayback: return "videoplayback"; default: return "none";
    }
}
inline bool youtubeHost(const std::string& h) { return h == "www.youtube.com" || h == "youtube.com" || h == "m.youtube.com"; }
inline bool googlevideoHost(const std::string& h) { return endsWith(h, ".googlevideo.com"); }

inline Kind classify(const Url& u)
{
    if (!u.ok) return Kind::None;
    const std::string& p = u.path;
    if (youtubeHost(u.host)) {
        if (p == "/watch" || p == "/tv" || p == "/tv/") {
            bool pbj = false; param(u.query, "pbj", pbj);
            return pbj ? Kind::None : Kind::Page;
        }
        if (startsWith(p, "/api/jnn/")) return endsWith(p, "/GenerateIT") ? Kind::GenerateIT : endsWith(p, "/Create") ? Kind::Create : Kind::Waa;
        if (p == "/youtubei/v1/att/get") return Kind::AttGet;
        if (p == "/youtubei/v1/player") return Kind::Player;
        return Kind::None;
    }
    if (u.host == "jnn-pa.googleapis.com" || (endsWith(u.host, ".googleapis.com") && p.find("/Waa/") != std::string::npos))
        return endsWith(p, "/GenerateIT") ? Kind::GenerateIT : endsWith(p, "/Create") ? Kind::Create : Kind::Waa;
    if (googlevideoHost(u.host) && p == "/videoplayback") return Kind::Videoplayback;
    return Kind::None;
}
inline std::string hostLabel(const std::string& h) { return googlevideoHost(h) ? std::string("*.googlevideo.com") : h; }
// Only small digit strings pass (sps is 1..3); anything else is reported as '?'.
inline std::string smallInt(const std::string& v) { if (v.empty() || v.size() > 3) return "?"; for (char c : v) if (c < '0' || c > '9') return "?"; return v; }
inline std::string clip(const std::string& s, size_t n) { std::string r = s.substr(0, n); for (auto& c : r) if (c < 33 || c > 126) c = '_'; return r; }

class Logger {
public:
    explicit Logger(std::function<void(const char*)> out) : m_out(std::move(out)) { }

    void onRequest(uint32_t now, const std::string& url, const std::string& method, int run)
    {
        const Url u = split(url); const Kind k = classify(u);
        if (k == Kind::None) return;
        char b[400];
        if (k == Kind::Page) {
            if (method != "GET" && !method.empty()) return;
            pageSummary("next page");
            m_page = Page(); m_page.no = ++m_pages; m_page.at = now; m_page.run = run; m_page.live = true;
            snprintf(b, sizeof b, "page n=%u run=%d host=%s path=%s", m_page.no, run, clip(u.host, 60).c_str(), clip(u.path, 40).c_str());
            emit(b); return;
        }
        if (!m_page.live) { m_page = Page(); m_page.no = ++m_pages; m_page.at = now; m_page.run = run; m_page.live = true; emit("page n=0 run=-1 (no document request seen; timings from the first attestation request)"); }
        if (m_pending.size() > 256) m_pending.clear();
        m_pending[url] = now;
        if (k == Kind::Videoplayback) {
            ++m_page.vpReq;
            if (m_page.vpLines >= vpLineCap) return;
            ++m_page.vpLines;
            bool sabr = false, hasSps = false, hasPot = false;
            const std::string sabrV = param(u.query, "sabr", sabr), sps = param(u.query, "sps", hasSps), pot = param(u.query, "pot", hasPot);
            snprintf(b, sizeof b, "vp req i=%u method=%s sabr=%s sps=%s pot_len=%s t=%u", m_page.vpReq, clip(method, 8).c_str(),
                sabr ? smallInt(sabrV).c_str() : "-", hasSps ? smallInt(sps).c_str() : "-", hasPot ? std::to_string(pot.size()).c_str() : "-", now - m_page.at);
            if (hasSps) m_page.lastSps = smallInt(sps);
            emit(b); return;
        }
        if (k == Kind::GenerateIT) { if (!m_page.gitReq) m_page.gitFirstMs = int64_t(now - m_page.at); ++m_page.gitReq; }
        snprintf(b, sizeof b, "req kind=%s host=%s path=%s method=%s t=%u first=%d", kindName(k), clip(hostLabel(u.host), 60).c_str(), clip(u.path, 90).c_str(),
            clip(method, 8).c_str(), now - m_page.at, k == Kind::GenerateIT && m_page.gitReq == 1 ? 1 : 0);
        emit(b);
    }

    void onRedirect(uint32_t now, const std::string& fromUrl, int status, const std::string& toUrl)
    {
        const Url f = split(fromUrl), t = split(toUrl);
        const Kind k = classify(f) != Kind::None ? classify(f) : classify(t);
        if (k == Kind::None || k == Kind::Page) return;
        bool hasSps = false; const std::string sps = param(t.query, "sps", hasSps);
        if (hasSps) m_page.lastSps = smallInt(sps);
        if (k == Kind::Videoplayback && m_page.vpLines >= vpLineCap) return;
        if (k == Kind::Videoplayback) ++m_page.vpLines;
        char b[300];
        snprintf(b, sizeof b, "redir kind=%s status=%d to=%s%s sps=%s t=%u", kindName(k), status, clip(hostLabel(t.host), 60).c_str(), clip(t.path, 60).c_str(),
            hasSps ? smallInt(sps).c_str() : "-", m_page.live ? now - m_page.at : 0);
        emit(b);
    }

    // len < 0: no Content-Length.
    void onResponse(uint32_t now, const std::string& url, int status, int64_t len, const std::string& mime)
    {
        const Url u = split(url); const Kind k = classify(u);
        if (k == Kind::None || k == Kind::Page || !m_page.live) return;
        const auto it = m_pending.find(url);
        const long dt = it == m_pending.end() ? -1 : long(now - it->second);
        char b[300];
        if (k == Kind::Videoplayback) {
            ++m_page.vpResp;
            if (status != 200 && status != 206) ++m_page.vpBad;
            if (len >= 0 && len < 4096) ++m_page.vpSmall;
            if (len >= 0) m_page.vpBytes += len;
            if (m_page.vpResp % 64 == 0) pageSummary("every 64 videoplayback responses");
            if (m_page.vpLines >= vpLineCap) return;
            ++m_page.vpLines;
            snprintf(b, sizeof b, "vp resp i=%u status=%d len=%lld mime=%s t=%u dt=%ld", m_page.vpResp, status, (long long)len, clip(mime, 40).c_str(), now - m_page.at, dt);
            emit(b); return;
        }
        if (k == Kind::GenerateIT) {
            ++m_page.gitResp; m_page.gitStatus = status; m_page.gitLen = len;
            if (m_page.gitRespFirstMs < 0) m_page.gitRespFirstMs = int64_t(now - m_page.at);
        }
        snprintf(b, sizeof b, "resp kind=%s status=%d len=%lld mime=%s t=%u dt=%ld", kindName(k), status, (long long)len, clip(mime, 40).c_str(), now - m_page.at, dt);
        emit(b);
    }

    void onComplete(uint32_t now, const std::string& url, int error, int64_t len)
    {
        const Url u = split(url); const Kind k = classify(u);
        if (k == Kind::None || k == Kind::Page || !m_page.live) return;
        const auto it = m_pending.find(url);
        const long dt = it == m_pending.end() ? -1 : long(now - it->second);
        if (it != m_pending.end()) m_pending.erase(it);
        if (k == Kind::Videoplayback) { if (error) ++m_page.vpErr; if (!error || m_page.vpLines >= vpLineCap) return; ++m_page.vpLines; }
        if (k == Kind::GenerateIT && error) ++m_page.gitErr;
        char b[200];
        snprintf(b, sizeof b, "done kind=%s err=%d len=%lld t=%u dt=%ld", kindName(k), error, (long long)len, now - m_page.at, dt);
        emit(b);
    }

    void pageSummary(const char* why)
    {
        if (!m_page.live) return;
        char b[500];
        snprintf(b, sizeof b, "pagesum n=%u run=%d git_req=%u git_resp=%u git_err=%u git_first_ms=%lld git_resp_ms=%lld git_status=%d git_len=%lld "
            "vp_req=%u vp_resp=%u vp_bad=%u vp_err=%u vp_small=%u vp_bytes=%lld sps=%s why=%s",
            m_page.no, m_page.run, m_page.gitReq, m_page.gitResp, m_page.gitErr, (long long)m_page.gitFirstMs, (long long)m_page.gitRespFirstMs, m_page.gitStatus,
            (long long)m_page.gitLen, m_page.vpReq, m_page.vpResp, m_page.vpBad, m_page.vpErr, m_page.vpSmall, (long long)m_page.vpBytes, m_page.lastSps.c_str(), why);
        emit(b);
    }

    static constexpr unsigned vpLineCap = 48;

private:
    struct Page {
        unsigned no = 0; uint32_t at = 0; int run = -1; bool live = false;
        unsigned gitReq = 0, gitResp = 0, gitErr = 0; int64_t gitFirstMs = -1, gitRespFirstMs = -1, gitLen = -1; int gitStatus = 0;
        unsigned vpReq = 0, vpResp = 0, vpBad = 0, vpErr = 0, vpSmall = 0, vpLines = 0; int64_t vpBytes = 0; std::string lastSps = "-";
    };
    void emit(const char* line) { if (m_out) m_out(line); }
    std::function<void(const char*)> m_out;
    Page m_page;
    unsigned m_pages = 0;
    std::unordered_map<std::string, uint32_t> m_pending;
};

} // namespace OmniYtAttestLog
'''

GLUE = r'''// OMNI_YT_ATTEST_LOG_V1: page-invisible YouTube attestation logging (UI-process resource-load observer; no page script).
// Off unless /data/omni/yt-attest-log.flag exists (read once). Lines "OMNI YTATTESTLOG: ..." (host + path only).
static bool omniYtAttestLogOn()
{
    static int on = -1;
    if (on < 0) {
        on = !access("/data/omni/yt-attest-log.flag", F_OK) ? 1 : 0;
        if (on) { fprintf(stderr, "OMNI YTATTESTLOG: on (OMNI_YT_ATTEST_LOG_V1; /data/omni/yt-attest-log.flag): resource-load observer, no page script\n"); fflush(stderr); }
    }
    return on == 1;
}
static OmniYtAttestLog::Logger& omniYtAttestLogger()
{
    static OmniYtAttestLog::Logger* logger = new OmniYtAttestLog::Logger([](const char* line) { fprintf(stderr, "OMNI YTATTESTLOG: %s\n", line); fflush(stderr); });
    return *logger;
}
static bool omniYtAttestTab(WKPageRef page)
{
    if (!omniYtAttestLogOn() || !running) return false;
    Tab* tab = omniTabForPage(page);
    return tab && !tab->omniPrivate && !tab->omniMediaSection && !tab->crashed;
}
static std::string omniYtAttestUrl(WKURLRef url)
{
    if (!url) return std::string();
    auto text = adoptWK(WKURLCopyString(url));
    return text ? OmniTest::toStd(text.get()) : std::string();
}
static int64_t omniYtAttestLen(WKURLResponseRef response)
{
    if (!response) return -1;
    const uint32_t n = WKURLResponseGetExpectedContentLength(response);
    return n == 0xffffffffu ? int64_t(-1) : int64_t(n);
}
static int omniYtAttestRun() { return ytTimeline ? int(omniYt.index) : -1; }
static void omniYtAttestSend(const void*, WKPageRef page, WKURLRequestRef request)
{
    if (!request || !omniYtAttestTab(page)) return;
    auto url = adoptWK(WKURLRequestCopyURL(request));
    auto method = adoptWK(WKURLRequestCopyHTTPMethod(request));
    omniYtAttestLogger().onRequest(SDL_GetTicks(), omniYtAttestUrl(url.get()), method ? OmniTest::toStd(method.get()) : std::string(), omniYtAttestRun());
}
static void omniYtAttestRedirect(const void*, WKPageRef page, WKURLResponseRef response, WKURLRequestRef request)
{
    if (!request || !omniYtAttestTab(page)) return;
    auto from = response ? adoptWK(WKURLResponseCopyURL(response)) : WKRetainPtr<WKURLRef>();
    auto to = adoptWK(WKURLRequestCopyURL(request));
    omniYtAttestLogger().onRedirect(SDL_GetTicks(), omniYtAttestUrl(from.get()), response ? WKURLResponseHTTPStatusCode(response) : 0, omniYtAttestUrl(to.get()));
}
static void omniYtAttestResponse(WKPageRef page, WKURLRef original, WKURLResponseRef response)
{
    if (!response || !omniYtAttestTab(page)) return;
    WKRetainPtr<WKURLRef> responseURL;
    if (!original) { responseURL = adoptWK(WKURLResponseCopyURL(response)); original = responseURL.get(); }
    auto mime = adoptWK(WKURLResponseCopyMIMEType(response));
    omniYtAttestLogger().onResponse(SDL_GetTicks(), omniYtAttestUrl(original), WKURLResponseHTTPStatusCode(response), omniYtAttestLen(response),
        mime ? OmniTest::toStd(mime.get()) : std::string());
}
static void omniYtAttestComplete(const void*, WKPageRef page, WKURLRef original, WKURLResponseRef response, WKErrorRef error)
{
    if (!omniYtAttestTab(page)) return;
    omniYtAttestLogger().onComplete(SDL_GetTicks(), omniYtAttestUrl(original), error ? (WKErrorGetErrorCode(error) ? WKErrorGetErrorCode(error) : -1) : 0, omniYtAttestLen(response));
}
'''

EDITS = [
    # the pure logger, at file scope next to the grabber's header
    ('#include "OmniNetGrabber.h" // OMNI_NET_GRABBER_V1\n',
     '#include "OmniNetGrabber.h" // OMNI_NET_GRABBER_V1\n#include "OmniYtAttestLog.h" // OMNI_YT_ATTEST_LOG_V1: page-invisible attestation logging (pure)\n'),
    # the glue, right before the grabber's install function (Tab, omniYt, omniTabForPage are all declared above it)
    ('// OMNI_C52_FIX1 (review M2): the grabber\'s resource-load client makes WebKit send will-send/response/\n',
     GLUE + '// OMNI_C52_FIX1 (review M2): the grabber\'s resource-load client makes WebKit send will-send/response/\n'),
    # the client is also installed while the log flag is on (normal, non-private, non-Media-downloads tabs)
    ('    const bool want = (grabberTest || (omniMediaDownloadsEnabled && !omniTestMode())) && !tab.omniPrivate && !tab.omniMediaSection;\n',
     '    const bool want = (grabberTest || (omniMediaDownloadsEnabled && !omniTestMode()) || omniYtAttestLogOn()) && !tab.omniPrivate && !tab.omniMediaSection; // OMNI_YT_ATTEST_LOG_V1\n'),
    ('        grabber.didReceiveResponse = [](const void*, WKPageRef page, WKURLRef original, WKURLResponseRef response) { omniNetObserve(page, original, response); };\n',
     '        grabber.didReceiveResponse = [](const void*, WKPageRef page, WKURLRef original, WKURLResponseRef response) { omniYtAttestResponse(page, original, response); omniNetObserve(page, original, response); }; // OMNI_YT_ATTEST_LOG_V1\n'
     '        if (omniYtAttestLogOn()) { grabber.didSendRequest = omniYtAttestSend; grabber.didPerformRedirect = omniYtAttestRedirect; grabber.didCompleteWithError = omniYtAttestComplete; } // OMNI_YT_ATTEST_LOG_V1\n'),
]


def main():
    if len(sys.argv) != 2: sys.exit(__doc__)
    entry = Path(sys.argv[1]) / 'engine' / 'entry'
    p = entry / 'OmniBrowser.cpp'
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    h = entry / 'OmniYtAttestLog.h'
    if MARK in s:
        if not h.exists() or h.read_bytes().decode('utf-8').replace('\r\n', '\n') != HEADER:
            h.write_bytes(HEADER.replace('\n', nl).encode('utf-8')); print('already (OmniYtAttestLog.h rewritten)')
        else: print('already')
        return 0
    for old, new in EDITS:
        old, new = old.replace('\n', nl), new.replace('\n', nl)
        if s.count(old) != 1:
            sys.exit('OmniBrowser.cpp: anchor found %d times: %r' % (s.count(old), old[:100]))
        s = s.replace(old, new, 1)
    h.write_bytes(HEADER.replace('\n', nl).encode('utf-8'))
    p.write_bytes(s.encode('utf-8'))
    print('applied')
    return 0


if __name__ == '__main__':
    sys.exit(main())
