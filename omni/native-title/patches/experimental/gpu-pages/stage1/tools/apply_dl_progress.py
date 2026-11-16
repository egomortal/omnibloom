#!/usr/bin/env python3
"""OMNI_DL_PROGRESS_V1 (2026-11-16): Downloads progress in Omni's top bar.

What the user sees
  - While the Downloads app (the media-downloads worker) has jobs working or waiting, the top bar shows a small
    progress ring with a down arrow and "2 ↓ 45%" (jobs, overall percent; "2 ↓" while no job knows its size yet),
    right of the controller battery, the sleep timer's "zZ" and offline retry's "Offline" badge. When the bar is
    short of room the text goes and the ring stays.
  - Cross on it (the pointer over it) opens the Downloads tab (or brings it forward), as L1 + R1 does.
  - Options (top level) gets a row "Downloads (2 active)" (value "45%") while jobs run; Cross opens the Downloads tab.
  - Finished downloads: NOT new here. OMNI_SMALL_COMFORTS_V1's downloads-done notice already does it
    (/data/omni/downloads-done.txt, written by the worker per finished job, checked every 5 s: "Downloaded: <title>",
    "(and n more)", not shown while the Downloads tab is in front). Reused as it is.
  - Private tabs: nothing changes (downloads never come from private tabs; nothing here reads a tab's address).

Where the numbers come from
  The worker (omnibloom/downloads/worker/worker.py) had no route that gives job progress without its page token:
  /api/status (the full job list, often far over 4 KB) needs X-Omni-Token, which only the Downloads page has
  (/healthz has no jobs). So the worker got one minimal read-only route, OMNI_DL_PROGRESS_V1 there:
      GET /api/active  ->  {"api_version": 1, "active": N, "percent": P}
  active = jobs not finished and not paused / pausing / cancelling; percent = the mean of their known progress
  (queued = 0, still inspecting = unknown), -1 when none is known. Counts only: no titles, links or job ids. No token;
  the worker listens on 127.0.0.1 only and its Host check (127.0.0.1:<port>) keeps DNS-rebinding pages out.
  Tests: omnibloom/downloads/tests/test_active.py. An older worker answers 403 / 404: Omni stops asking.

Poll rules (all in the pure Poller below, tested)
  - Nothing at all while "Media downloads" is off, in self-tests, or with no worker port (no "downloads" card).
  - One check 5 s after start (a worker still busy from before Omni started shows up); refused = not running = stop.
  - Then only while the last answer had active jobs, or within 10 s after Omni handed something over:
      the Downloads tab opened / came forward for a link or a file (OmniMediaDownloadsHooks.inc, ready),
      a link sent with the hub's download.url intent ("Sent to Downloads"),
      the user leaving the Downloads tab (jobs are started on that page), and Cross on the indicator / row.
  - At most one request every 2 s, one at a time, on its own thread: blocking socket, SO_SNDTIMEO / SO_RCVTIMEO
    1.5 s (O_NONBLOCK fails with errno 13 in the PS5 title, so OmniMediaDownloads::get's non-blocking first try is
    not used: it would also write a diagnostic line per poll). A poll still out after 8 s is abandoned.
  - Refused (worker not running) or 0 active -> idle (indicator off). 3 failures in a row -> idle. 403 / 404 -> idle
    until the next hand-over.

Pure part: engine/entry/OmniDlProgress.h (no SDL / WebKit / sockets): reply parsing, poll schedule, label texts,
top-bar layout. Tested by tools/test_dl_progress.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_dl_progress.cpp -o t && ./t
Shell side: engine/entry/OmniDlProgressShell.h (included from OmniFeatures3.h after OmniOfflineRetryShell.h).

Anchors (exactly once each; MARK makes each file idempotent; whole lines only):
  OmniBrowser.cpp        omniOrDrawTopBar's declaration (declarations after it); the omniOrDrawTopBar call in
                         omniDrawTopBar (indicator after it); click()'s "if (x >= 1150) return;" top-bar line (hit test
                         before it); the hub send's "if (st == 200) { notice("Sent to Downloads"); ..." (hand-over
                         before it).
  OmniMediaDownloadsHooks.inc  the "tick: applying plan" diag line (hand-over after it).
  OmniQuickMenu.h        omniNpQuickRow's declaration (declarations after it); the omniPnQuickRow(p) line (row after
                         it); the omniPnQuickInput line (input before it, before the >= 900 rows).
  OmniFeatures3.h        the OmniOfflineRetryShell.h include line; the omniOrTick(now) line of omniF3Tick.
Apply AFTER apply_sleep_timer.py, apply_offline_retry.py and apply_popup_notice.py (their lines are anchors).
usage: apply_dl_progress.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_DL_PROGRESS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_DL_PROGRESS_V1: Downloads progress in the top bar, the pure part (no SDL, no WebKit, no sockets).
// The worker's GET /api/active reply, when to ask (poll schedule), the texts and the top-bar layout.
// Shell side: OmniDlProgressShell.h. The reasons are in tools/apply_dl_progress.py.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace OmniDlProgress {

constexpr uint32_t kPollGapMs = 2000;     // at most one request every 2 s
constexpr uint32_t kHandoverMs = 10000;   // keep asking this long after Omni handed something over
constexpr uint32_t kStartupMs = 5000;     // the one check after start
constexpr uint32_t kAbandonMs = 8000;     // a poll still out then is given up (its thread ends on its timeouts)
constexpr int kTimeoutMs = 1500;          // SO_SNDTIMEO / SO_RCVTIMEO (blocking socket: O_NONBLOCK fails in the title)
constexpr int kMaxFailures = 3;           // failed polls in a row -> idle
constexpr size_t kMaxReply = 2048;        // the whole HTTP reply (the body is ~45 bytes)
constexpr const char* kPath = "/api/active";
constexpr int kQuickRowId = 8480;         // Options (top level) row (popup notice 8470, controls 8200, now playing 8100)
constexpr float kTopBarRight = 1276.f;    // the top bar's right edge (layout px), as the sleep timer / offline badges
constexpr float kRingR = 6.f;             // the progress ring's radius (layout px)
constexpr float kRingW = 14.f;            // its box (ring + stroke)
constexpr float kTextGap = 5.f;           // ring -> text
constexpr float kBadgeGap = 12.f;         // previous badge -> ours (as the offline badge after the sleep timer)

inline bool after(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }   // SDL tick wrap-safe

// --- the reply ------------------------------------------------------------------------------------------------------
struct Status { bool ok = false; int active = 0; int percent = -1; };
// {"api_version": 1, "active": N, "percent": P}: a flat object; unknown keys with plain values (number, string,
// true / false / null) are skipped, so the worker may add fields; the three known ones exactly once each.
class Reader {
    const std::string& s;
    size_t at = 0;
    void ws() { while (at < s.size() && (s[at] == ' ' || s[at] == '\t' || s[at] == '\r' || s[at] == '\n')) ++at; }
    bool take(char c) { ws(); if (at < s.size() && s[at] == c) { ++at; return true; } return false; }
    bool str(std::string* out)
    {
        if (!take('"')) return false;
        while (at < s.size()) {
            const unsigned char c = static_cast<unsigned char>(s[at++]);
            if (c == '"') return true;
            if (c < 32) return false;
            if (c == '\\') {
                if (at >= s.size()) return false;
                const char e = s[at++];
                if (e == 'u') { if (at + 4 > s.size()) return false; at += 4; if (out) *out += '?'; continue; }
                if (!strchr_("\"\\/bfnrt", e)) return false;
                if (out) *out += e;
                continue;
            }
            if (out) *out += char(c);
        }
        return false;
    }
    static bool strchr_(const char* set, char c) { for (; *set; ++set) if (*set == c) return true; return false; }
    // An integer (a fraction / exponent makes it "not an integer": isInt false, still skipped correctly).
    bool number(long long& v, bool& isInt)
    {
        ws();
        const size_t start = at;
        bool neg = false;
        if (at < s.size() && s[at] == '-') { neg = true; ++at; }
        size_t digits = 0;
        v = 0;
        while (at < s.size() && s[at] >= '0' && s[at] <= '9') { if (v < 1000000000LL) v = v * 10 + (s[at] - '0'); ++at; ++digits; }
        if (!digits) { at = start; return false; }
        isInt = true;
        if (at < s.size() && s[at] == '.') { isInt = false; ++at; size_t f = 0; while (at < s.size() && s[at] >= '0' && s[at] <= '9') { ++at; ++f; } if (!f) return false; }
        if (at < s.size() && (s[at] == 'e' || s[at] == 'E')) {
            isInt = false; ++at;
            if (at < s.size() && (s[at] == '+' || s[at] == '-')) ++at;
            size_t e = 0; while (at < s.size() && s[at] >= '0' && s[at] <= '9') { ++at; ++e; }
            if (!e) return false;
        }
        if (neg) v = -v;
        return true;
    }
    bool word(const char* w)
    {
        ws();
        size_t n = 0; while (w[n]) ++n;
        if (s.compare(at, n, w) != 0) return false;
        at += n;
        return true;
    }
public:
    explicit Reader(const std::string& text) : s(text) { }
    Status read()
    {
        Status st;
        bool version = false, active = false, percent = false;
        if (!take('{')) return {};
        if (!take('}')) {
            for (;;) {
                std::string key;
                if (!str(&key) || !take(':')) return {};
                const bool known = key == "api_version" || key == "active" || key == "percent";
                long long v = 0; bool isInt = false;
                ws();
                if (known) {
                    if (!number(v, isInt) || !isInt) return {};
                    if (key == "api_version") { if (version || v != 1) return {}; version = true; }
                    else if (key == "active") { if (active || v < 0 || v > 100000) return {}; active = true; st.active = int(v); }
                    else { if (percent || v < -1 || v > 100) return {}; percent = true; st.percent = int(v); }
                } else if (at < s.size() && s[at] == '"') { if (!str(nullptr)) return {}; }
                else if (!word("true") && !word("false") && !word("null") && !number(v, isInt)) return {};
                if (take(',')) continue;
                if (take('}')) break;
                return {};
            }
        }
        ws();
        if (at != s.size() || !version || !active || !percent) return {};
        if (!st.active) st.percent = -1;
        st.ok = true;
        return st;
    }
};
inline Status parse(const std::string& body) { return Reader(body).read(); }

enum class Reply { Ok = 0, NotRunning, Missing, Failed };
// complete: the HTTP reply was read and framed correctly; status: its code; body: its body. Missing: an older worker
// without the route (403: its token check comes before "not found"; 404).
inline Reply classify(bool complete, int status, const std::string& body, Status& out)
{
    out = {};
    if (!complete) return Reply::Failed;
    if (status == 403 || status == 404) return Reply::Missing;
    if (status != 200) return Reply::Failed;
    out = parse(body);
    return out.ok ? Reply::Ok : Reply::Failed;
}
inline std::string request(unsigned port)
{
    return std::string("GET ") + kPath + " HTTP/1.0\r\nHost: 127.0.0.1:" + std::to_string(port)
        + "\r\nConnection: close\r\nAccept: application/json\r\n\r\n";
}

// --- when to ask ----------------------------------------------------------------------------------------------------
class Poller {
public:
    // May a poll start now? inFlight: one is out. Once, the first call arms the check 5 s after start.
    bool want(uint32_t now, bool inFlight)
    {
        if (!primed_) { primed_ = true; startup_ = true; startupAt_ = now + kStartupMs; }
        if (handover_ && after(now, handoverUntil_)) handover_ = false;
        if (inFlight) return false;
        if (polled_ && !after(now, nextAt_)) return false;
        if (startup_ && after(now, startupAt_)) return true;
        if (unsupported_) return false;
        return active_ > 0 || handover_;
    }
    void started(uint32_t now) { polled_ = true; startup_ = false; nextAt_ = now + kPollGapMs; }
    // A reply. True when what the top bar shows changed (redraw).
    bool finished(Reply r, const Status& s)
    {
        const int a = active_, p = percent_;
        switch (r) {
        case Reply::Ok: active_ = s.active; percent_ = s.active ? s.percent : -1; failures_ = 0; break;
        case Reply::NotRunning: active_ = 0; percent_ = -1; failures_ = 0; break;
        case Reply::Missing: active_ = 0; percent_ = -1; failures_ = 0; unsupported_ = true; handover_ = false; break;
        case Reply::Failed: if (++failures_ >= kMaxFailures) { active_ = 0; percent_ = -1; failures_ = 0; handover_ = false; } break;
        }
        return a != active_ || p != percent_;
    }
    // Omni handed a download over (or the user left the Downloads tab / asked for it): ask for the next 10 s. The 2 s
    // gap still holds. A worker that lacked the route may have been updated meanwhile: asked again.
    void handedOver(uint32_t now) { handover_ = true; handoverUntil_ = now + kHandoverMs; unsupported_ = false; }
    // "Media downloads" off: forget everything. True when the indicator was showing.
    bool reset()
    {
        const bool was = visible();
        active_ = 0; percent_ = -1; failures_ = 0; handover_ = false; unsupported_ = false; startup_ = false;
        return was;
    }
    bool visible() const { return active_ > 0; }
    int active() const { return active_; }
    int percent() const { return percent_; }
    bool handover() const { return handover_; }

private:
    bool primed_ = false, startup_ = false, polled_ = false, handover_ = false, unsupported_ = false;
    uint32_t startupAt_ = 0, nextAt_ = 0, handoverUntil_ = 0;
    int active_ = 0, percent_ = -1, failures_ = 0;
};

// --- texts ----------------------------------------------------------------------------------------------------------
inline std::string count(int active) { return active > 99 ? std::string("99+") : std::to_string(active); }
// "2 <down arrow> 45%" (U+2193), or "2 <down arrow>" while no job knows its progress. "" when nothing runs.
inline std::string label(int active, int percent)
{
    if (active <= 0) return {};
    std::string t = count(active) + " \xe2\x86\x93";
    if (percent >= 0) t += " " + std::to_string(percent > 100 ? 100 : percent) + "%";
    return t;
}
inline std::string quickLabel(int active) { return "Downloads (" + count(active) + " active)"; }
inline std::string quickValue(int percent) { return percent >= 0 ? std::to_string(percent > 100 ? 100 : percent) + "%" : std::string(); }

// --- top bar: right of the battery, the sleep timer and the offline badge ---------------------------------------------
// base: where the sleep timer starts; sleepW: its width (0: hidden); the offline badge as OmniOfflineRetry's
// badgeLayout placed it (offMode 0 hidden, 1 dot, 2 dot + text at offX + 12, at most offTextMax wide).
inline float startX(float base, float sleepW, int offMode, float offX, float offTextW, int offTextMax)
{
    float x = sleepW > 0 ? base + sleepW + kBadgeGap : base;
    if (offMode == 2) x = offX + 12.f + (offTextW < float(offTextMax) ? offTextW : float(offTextMax)) + kBadgeGap;
    else if (offMode == 1) x = offX + 7.f + kBadgeGap;
    return x;
}
struct BadgeLayout { float x = 0, w = 0; int mode = 0; int textMax = 0; };   // mode 0 hidden, 1 ring, 2 ring + text
inline BadgeLayout badgeLayout(float x, float textW)
{
    BadgeLayout b;
    b.x = x;
    const float room = kTopBarRight - x;
    if (room >= kRingW + kTextGap + textW) { b.mode = 2; b.textMax = int(room - kRingW - kTextGap); b.w = kRingW + kTextGap + textW; }
    else if (room >= kRingW) { b.mode = 1; b.w = kRingW; }
    return b;
}
// Cross with the pointer at x (layout px) inside the top bar: on the indicator (5 px of slack either side)?
inline bool hit(const BadgeLayout& b, float x) { return b.mode && x >= b.x - 5.f && x <= b.x + b.w + 5.f; }

} // namespace OmniDlProgress
'''

SHELL = r'''// OMNI_DL_PROGRESS_V1: Downloads progress in the top bar, shell side. Included from OmniFeatures3.h (after
// OmniOfflineRetryShell.h, whose badge it sits right of). The reasons are in tools/apply_dl_progress.py.
// Main thread except omniDlpRun (the poll's own thread: a blocking loopback socket with timeouts).
#pragma once
#include "OmniDlProgress.h"
#include <algorithm>
#include <arpa/inet.h>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <memory>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <thread>
#include <unistd.h>

namespace ODLP = OmniDlProgress;

struct OmniDlpPoll {
    uint16_t port = 0;
    int reply = int(ODLP::Reply::Failed);
    ODLP::Status status;
    std::atomic<bool> done { false };
};
static ODLP::Poller omniDlp;
static std::shared_ptr<OmniDlpPoll> omniDlpPoll;   // in flight (the thread holds its own reference)
static uint32_t omniDlpPollAt = 0;
static bool omniDlpOnDownloads = false;            // the Downloads tab was in front at the last tick
static ODLP::BadgeLayout omniDlpDrawn;             // where the indicator was last drawn (mode 0: not shown)

// One GET /api/active (blocking socket, SO_SNDTIMEO / SO_RCVTIMEO: O_NONBLOCK fails with errno 13 in the PS5 title).
static void omniDlpRun(std::shared_ptr<OmniDlpPoll> p)
{
    ODLP::Reply reply = ODLP::Reply::Failed;
    ODLP::Status status;
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd >= 0) {
        timeval tv {};
        tv.tv_sec = ODLP::kTimeoutMs / 1000;
        tv.tv_usec = (ODLP::kTimeoutMs % 1000) * 1000;
        (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#ifdef SO_NOSIGPIPE
        int noSignal = 1;
        (void)setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, sizeof(noSignal));
#endif
        sockaddr_in address {};
        address.sin_family = AF_INET;
        address.sin_port = htons(p->port);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
            reply = errno == ECONNREFUSED ? ODLP::Reply::NotRunning : ODLP::Reply::Failed;
        } else {
            const std::string request = ODLP::request(p->port);
            bool ok = true;
            for (size_t sent = 0; sent < request.size();) {
#ifdef MSG_NOSIGNAL
                const ssize_t n = send(fd, request.data() + sent, request.size() - sent, MSG_NOSIGNAL);
#else
                const ssize_t n = send(fd, request.data() + sent, request.size() - sent, 0);
#endif
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) { ok = false; break; }
                sent += size_t(n);
            }
            std::string raw;
            char buffer[512];
            while (ok) {
                const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
                if (n < 0 && errno == EINTR) continue;
                if (n < 0) { ok = false; break; }
                if (!n) break;
                if (raw.size() + size_t(n) > ODLP::kMaxReply) { ok = false; break; }
                raw.append(buffer, size_t(n));
            }
            if (ok) {
                const OmniMediaDownloads::HttpResult r = OmniMediaDownloads::parseHttp(raw);
                reply = ODLP::classify(r.state == OmniMediaDownloads::HttpState::Complete, r.status, r.body, status);
            }
        }
        close(fd);
    }
    p->reply = int(reply);
    p->status = status;
    p->done.store(true, std::memory_order_release);
}

// Omni handed something to the Downloads app (or the user left / asked for its tab): ask for the next 10 s.
static void omniDlpHandedOver() { omniDlp.handedOver(SDL_GetTicks()); }
static void omniDlpOpen()
{
    omniDlpHandedOver();
    omniMediaDownloadsOpen(false);   // the Downloads tab opens or comes forward (as L1 + R1)
}

static void omniDlpTick(uint32_t now)
{
    if (omniTestMode()) return;
    if (!omniMediaDownloadsEnabled) {
        if (omniDlp.reset()) omniShellDirty = true;
        omniDlpOnDownloads = false;
        return;
    }
    // 1. a reply came back (or the poll is given up)
    if (omniDlpPoll) {
        if (omniDlpPoll->done.load(std::memory_order_acquire)) {
            const auto p = std::move(omniDlpPoll);
            omniDlpPoll.reset();
            if (omniDlp.finished(ODLP::Reply(p->reply), p->status)) omniShellDirty = true;
        } else if (ODLP::after(now, omniDlpPollAt + ODLP::kAbandonMs)) {
            omniDlpPoll.reset();   // its thread ends on its own timeouts and writes only into its own struct
            if (omniDlp.finished(ODLP::Reply::Failed, {})) omniShellDirty = true;
        }
    }
    // 2. leaving the Downloads tab: jobs are started on that page
    const bool on = active() && omniMediaOwns(*active());
    if (omniDlpOnDownloads && !on) omniDlp.handedOver(now);
    omniDlpOnDownloads = on;
    // 3. the next poll (at most every 2 s, only while jobs run or just after a hand-over)
    if (!omniDlp.want(now, omniDlpPoll != nullptr)) return;
    omniDlp.started(now);
    const unsigned port = OmniMediaSection::assignedPort();   // the "downloads" card (re-read at most every 5 s)
    if (!port) { if (omniDlp.finished(ODLP::Reply::NotRunning, {})) omniShellDirty = true; return; }
    auto p = std::make_shared<OmniDlpPoll>();
    p->port = uint16_t(port);
    omniDlpPoll = p;
    omniDlpPollAt = now;
    std::thread(omniDlpRun, p).detach();
}

// --- top bar (omniDrawTopBar, right of the battery, the sleep timer and the offline badge) -----------------------------
// A ring (faint track, the overall percent as an arc from 12 o'clock) with a small down arrow inside.
static void omniDlpRing(float cx, float cy, float r, int percent, SDL_Color arc, SDL_Color ink)
{
    const OmniPix f = omniPix();
    if (!f.ok) return;
    const float s = float(displayScale), X = cx * s, Y = cy * s, R = r * s, t = 1.1f * s;
    const float sweep = percent < 0 ? 0.f : 6.2831853f * float(std::min(percent, 100)) / 100.f;
    const int x0 = std::max(0, int(X - R - t - 1)), x1 = std::min(canvas->w, int(X + R + t + 2));
    const int y0 = std::max(0, int(Y - R - t - 1)), y1 = std::min(canvas->h, int(Y + R + t + 2));
    for (int y = y0; y < y1; ++y) {
        uint32_t* row = omniRow(y);
        for (int x = x0; x < x1; ++x) {
            const float dx = x + 0.5f - X, dy = y + 0.5f - Y, ring = std::fabs(std::hypot(dx, dy) - R) - t;
            float ang = std::atan2(dx, -dy);   // 0 at 12 o'clock, clockwise
            if (ang < 0) ang += 6.2831853f;
            const float lx = (x + 0.5f) / s, ly = (y + 0.5f) / s;
            const float arrow = std::min({ omniSdSeg(lx, ly, cx, cy - 3.2f, cx, cy + 2.6f, 0.7f),
                omniSdSeg(lx, ly, cx - 2.4f, cy + 0.3f, cx, cy + 2.7f, 0.7f), omniSdSeg(lx, ly, cx + 2.4f, cy + 0.3f, cx, cy + 2.7f, 0.7f) });
            const float ringCov = std::clamp(0.5f - ring, 0.f, 1.f);
            if (ringCov > 0) omniBlendPx(row[x], f, arc, uint32_t(ringCov * (ang <= sweep ? 255 : 70)));
            const float arrowCov = std::clamp(0.5f - arrow * s, 0.f, 1.f);
            if (arrowCov > 0) omniBlendPx(row[x], f, ink, uint32_t(arrowCov * 255));
        }
    }
}
static void omniDlpDrawTopBar(float base)
{
    omniDlpDrawn = {};
    if (!omniDlp.visible()) return;
    const OmniTheme& T = omniTheme();
    const float sleepW = omniSt.on() ? float(omniTextWidthPx(omniCaption, omniSt.badge(SDL_GetTicks())) / displayScale) : 0.f;
    int offMode = 0, offTextMax = 0;
    float offX = 0, offTextW = 0;
    if (omniOrWatch.indicator()) {   // OMNI_OFFLINE_RETRY_V1's badge, placed exactly as omniOrDrawTopBar places it
        offTextW = float(omniTextWidthPx(omniCaptionBold, OOR::kBadge) / displayScale);
        const OOR::BadgeLayout o = OOR::badgeLayout(base, sleepW, offTextW);
        offMode = o.mode; offX = o.x; offTextMax = o.textMax;
    }
    const std::string text = ODLP::label(omniDlp.active(), omniDlp.percent());
    const float textW = float(omniTextWidthPx(omniCaption, text) / displayScale);
    const ODLP::BadgeLayout b = ODLP::badgeLayout(ODLP::startX(base, sleepW, offMode, offX, offTextW, offTextMax), textW);
    if (!b.mode) return;
    omniDlpDrawn = b;
    if (omniHover(int(b.x) - 5, 8, int(b.w) + 10, 44)) omniRingRect(int(b.x) - 5, 18, int(b.w + 10.5f), 24, 6, T.accent, T.hover);
    omniDlpRing(b.x + ODLP::kRingW / 2, 30, ODLP::kRingR, omniDlp.percent(), T.accent, T.inkDim);
    if (b.mode == 2) omniLabel(text, b.x + ODLP::kRingW + ODLP::kTextGap, 30, omniCaption, T.inkDim, 0, b.textMax);
}
// click(): Cross with the pointer on the indicator opens the Downloads tab.
static bool omniDlpTopBarClick(int x)
{
    if (!omniDlp.visible() || !ODLP::hit(omniDlpDrawn, float(x))) return false;
    omniDlpOpen();
    return true;
}

// --- Options (top level): "Downloads (2 active)" while jobs run ---------------------------------------------------------
static void omniDlpQuickRow(OmniFxPanel& p)
{
    if (!omniDlp.visible()) return;
    OmniFxRow r; r.id = ODLP::kQuickRowId; r.label = ODLP::quickLabel(omniDlp.active()); r.value = ODLP::quickValue(omniDlp.percent());
    p.rows.push_back(r);
}
static bool omniDlpQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != ODLP::kQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    omniFxCloseAll();
    omniDlpOpen();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('static void omniOrDrawTopBar(float x);        // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h): "Offline" in the top bar\n',
         'static void omniOrDrawTopBar(float x);        // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h): "Offline" in the top bar\n'
         'static void omniDlpDrawTopBar(float x);       // OMNI_DL_PROGRESS_V1 (OmniDlProgressShell.h): jobs + percent in the top bar\n'
         'static bool omniDlpTopBarClick(int x);        // OMNI_DL_PROGRESS_V1: Cross on it opens the Downloads tab\n'
         'static void omniDlpHandedOver();              // OMNI_DL_PROGRESS_V1: watch the Downloads app for the next 10 s\n'),
        ('    omniOrDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_OFFLINE_RETRY_V1: "Offline" while down\n',
         '    omniOrDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_OFFLINE_RETRY_V1: "Offline" while down\n'
         '    omniDlpDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_DL_PROGRESS_V1: Downloads progress while jobs run\n'),
        ('        if (x >= 1150) return; // OMNI_MQ_NATIVE_V1: no invisible old uBlock hit target\n',
         '        if (omniDlpTopBarClick(x)) return; // OMNI_DL_PROGRESS_V1: the Downloads indicator (opens the Downloads tab)\n'
         '        if (x >= 1150) return; // OMNI_MQ_NATIVE_V1: no invisible old uBlock hit target\n'),
        ('    if (st == 200) { notice("Sent to Downloads"); return true; }\n',
         '    if (st == 200) omniDlpHandedOver(); // OMNI_DL_PROGRESS_V1: show its progress in the top bar\n'
         '    if (st == 200) { notice("Sent to Downloads"); return true; }\n'),
    ],
    'OmniMediaDownloadsHooks.inc': [
        ('    OmniMediaDownloads::diag("tick: applying plan %d url %.120s", int(plan.action), plan.url.c_str());\n',
         '    OmniMediaDownloads::diag("tick: applying plan %d url %.120s", int(plan.action), plan.url.c_str());\n'
         '    omniDlpHandedOver(); // OMNI_DL_PROGRESS_V1: the Downloads tab opens: watch for jobs (top-bar progress)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static void omniNpQuickRow(OmniFxPanel& p); // OMNI_MEDIA_CONTROLS_V1 (OmniMediaControlsShell.h)\n',
         'static void omniNpQuickRow(OmniFxPanel& p); // OMNI_MEDIA_CONTROLS_V1 (OmniMediaControlsShell.h)\n'
         'static void omniDlpQuickRow(OmniFxPanel& p); // OMNI_DL_PROGRESS_V1 (OmniDlProgressShell.h)\n'
         'static bool omniDlpQuickInput(const OmniFxRow& r, int b);\n'),
        ('        omniPnQuickRow(p); // OMNI_POPUP_NOTICE_V1: Blocked pop-ups (n), while this tab has any\n',
         '        omniPnQuickRow(p); // OMNI_POPUP_NOTICE_V1: Blocked pop-ups (n), while this tab has any\n'
         '        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n'),
        ('    if (omniPnQuickInput(r, b)) return true; // OMNI_POPUP_NOTICE_V1 (before the >= 900 rows)\n',
         '    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n'
         '    if (omniPnQuickInput(r, b)) return true; // OMNI_POPUP_NOTICE_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniOfflineRetryShell.h" // OMNI_OFFLINE_RETRY_V1\n',
         '#include "OmniOfflineRetryShell.h" // OMNI_OFFLINE_RETRY_V1\n'
         '#include "OmniDlProgressShell.h" // OMNI_DL_PROGRESS_V1 (after offline retry: its badge sits right of that one)\n'),
        ('    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n',
         '    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n'
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    for need, tool in (('OMNI_SLEEP_TIMER_V1', 'apply_sleep_timer.py'), ('OMNI_OFFLINE_RETRY_V1', 'apply_offline_retry.py'),
                       ('OMNI_POPUP_NOTICE_V1', 'apply_popup_notice.py')):
        if need not in f3:
            sys.exit('OmniFeatures3.h: %s missing: %s first' % (need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniDlProgress.h', PURE, 'OmniOfflineRetry.h'),
            write_new('OmniDlProgressShell.h', SHELL, 'OmniOfflineRetryShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
