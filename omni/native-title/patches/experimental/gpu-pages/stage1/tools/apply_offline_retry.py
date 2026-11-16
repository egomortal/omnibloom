#!/usr/bin/env python3
"""OMNI_OFFLINE_RETRY_V1 (2026-11-16): network-aware error pages.

What the user sees
  - A page fails because the console is offline or the network dropped (DNS failure, connection refused / timed out,
    no route, send / receive failure): Omni's error panel says "You're offline" (instead of "This page couldn't
    load") with "The console isn't connected to the internet. This page reloads by itself when the connection is
    back." Retry / Close work as before.
  - The top bar shows a small amber dot + "Offline" (right of the controller battery and the sleep timer) while the
    network is down; it goes away when the network is back or no tab shows a network error any more.
  - When the network comes back, every tab whose last load failed with a network error reloads once (active tab
    first, the others 1.2 s apart) and "Back online. Reloading 2 pages" shows.
  - Browser settings > "Reload pages when back online": On (default) / Off (/data/omni/offline-reload-off.flag).
    Off: the panel says "... Check the network connection, then press Retry." and "Back online. Press Retry ..."
  - Never reloaded: HTTP error pages (4xx / 5xx are documents, not load failures), HTTPS-only's "no secure
    connection" panel unless its https attempt failed for a network reason (below), uBlock blocks / redirects, certificate / TLS errors, crashed tabs,
    unloaded tabs, a tab the user navigated or retried meanwhile. At most once per "back online" event.

How the network state is known
  The PS5 system API (sceNetCtlGetState / sceNetCtlGetInfo) is NOT usable: nothing in the tree declares it and the
  title's import gate (build-omni-gpupages-rc6-title.sh) allows only the launch title's imports, which have no
  sceNetCtl* (they do have socket / connect / setsockopt / getsockopt / shutdown / close / pthread_create).
  So, only while some tab shows a network error:
    1. route check (main thread, no packet sent): a UDP socket connect()ed to TEST-NET-2 198.51.100.1:9 and
       getsockname(): no route / no address -> "down" at once. Every 1 s while a tab is offline.
    2. TCP probe (worker thread, blocking socket with SO_SNDTIMEO / SO_RCVTIMEO 3 s; O_NONBLOCK fails with errno
       13 in the title) to the failed tab's OWN host (the contact the user just made; never a third party): the
       active tab's if it is offline, else the first offline tab's, one host per round; its port, else 443 for
       https (and HTTPS-only's https attempt) / 80 for http; connected or refused = up. Nothing is sent.
       Host names: the title cannot resolve (getaddrinfo / any resolver is not among the launch title's imports,
       so the import gate would refuse it), so only IPv4-literal hosts get a TCP probe; for a name the round is
       route-only: the route returning while down counts as "back online" (link back), nothing is sent.
       OMNI_OFFLINE_RETRY_RESOLVE=1 compiles a getaddrinfo path on the probe thread (needs the gate widened).
       Private tabs' hosts are probed like any other but never logged ("(private tab)").
       Probes start at most every 5 s, backing off 5, 10, 20, 30, 30 s while down; none while there is no route
       (the route coming back triggers one at once, the 5 s gap kept). A probe still in connect() after 7 s
       counts as down; the main thread shut()s its socket down (fd guarded by a mutex, never a closed fd); at most
       2 such stuck probes before no new one starts.
    3. No tab offline -> nothing runs, state forgotten (badge off).
  "Back online" = a probe says up after the network was seen down (Down -> Up). Unknown -> Up (a server refusing
  while the console is online) is no event, so a dead server is never reloaded in a loop.

Error classification (this port: WebKit's curl network process, ResourceErrorCurl.cpp, domain "CurlErrorDomain"):
  network = CURLcode 5, 6, 7, 28, 45, 55, 56. The panel says "You're offline" only when the watch says Down.
  HTTPS-only: its panel stays as it is (its early return at the top of failed() untouched), but when the https
  attempt failed with curl 5 / 6 / 7 / 28 the tab counts as offline: it is watched and reloaded when back online
  (its http URL, so HTTPS-only makes a fresh https attempt). Other HTTPS-only panels are never reloaded.

Pure part: engine/entry/OmniOfflineRetry.h (no SDL / WebKit / sockets): classification, the watch (route check /
probe schedule / backoff / events), reload order, texts, top-bar badge layout.
Tested by tools/test_offline_retry.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_offline_retry.cpp -o t && ./t
Shell side: engine/entry/OmniOfflineRetryShell.h (included from OmniFeatures3.h after OmniMediaControlsShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniErrorPage.h        "int failCode = 0;" in OmniFxTabState (orEvent field after it); the OmniFxErrorLayout struct
                         line (declarations before it); the "Too many redirects" title line (title becomes
                         "You're offline"); the "(error N)" body line (offline body after it). HTTPS-only's lines
                         (omniHo* handover at the top of omniFxErrorDraw / Button / Click) are untouched, and its
                         panel draws first, so it is never replaced.
  OmniBrowser.cpp        the omniStDrawTopBar declaration (declarations after it); omniFxRecordFailure(...) in failed()
                         (omniOrFailed after it: below HTTPS-only's early return, uBlock redirects and quiet cancels);
                         the omniStDrawTopBar call in omniDrawTopBar (badge after it).
  OmniBrowserSettings.h  omniHoSettingsInput's declaration (row id 895 + declarations after it); the omniHoSettingsRows
                         call (row after it); the omniHoRowId input line (handler before it, before the >= 300 rows).
  OmniFeatures3.h        the OmniMediaControlsShell.h include line (the last include); the omniStTick(now) line of
                         omniF3Tick (omniOrTick after it).
Apply AFTER apply_https_only.py, apply_media_controls.py and apply_sleep_timer.py (their lines are anchors).
usage: apply_offline_retry.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_OFFLINE_RETRY_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_OFFLINE_RETRY_V1: network-aware error pages, the pure part (no SDL, no WebKit, no sockets).
// Which load errors are network errors, the network watch (route check / probe schedule with backoff, "back online"
// events), which tabs reload when the network is back (and in what order), the texts and the top-bar badge layout.
// Shell side: OmniOfflineRetryShell.h. The reasons are in tools/apply_offline_retry.py.
#pragma once
#include <cerrno>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniOfflineRetry {

constexpr uint32_t kMinGapMs = 5000;        // probes start at most every 5 s ...
constexpr uint32_t kMaxGapMs = 30000;       // ... backing off to every 30 s while the network stays down
constexpr uint32_t kRouteCheckMs = 1000;    // the route check (no packet sent) while a tab is offline
constexpr int kConnectMs = 3000;            // per probe target (SO_SNDTIMEO / SO_RCVTIMEO; blocking socket)
constexpr uint32_t kProbeDeadlineMs = 7000; // a probe still in connect() then counts as "down" (and is shut down)
constexpr uint32_t kFirstReloadMs = 500;    // network back: the first reload (the active tab) after this
constexpr uint32_t kStaggerMs = 1200;       // then one more tab every 1.2 s
constexpr size_t kMaxStuckProbes = 2;       // abandoned probes still blocked in connect(): no new probe beyond this
constexpr float kTopBarRight = 1276.f;      // the top bar's right edge (layout px), as the sleep timer badge uses

// Route check: a UDP socket "connected" to TEST-NET-2 only looks the route up (no packet is sent).
constexpr const char* kRouteIp = "198.51.100.1";
constexpr int kRoutePort = 9;
constexpr const char* kOffFlag = "offline-reload-off.flag";   // in /data/omni/: "Reload pages when back online" Off

constexpr const char* kTitle = "You're offline";
constexpr const char* kBadge = "Offline";
constexpr const char* kSettingLabel = "Reload pages when back online";

inline bool after(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }   // SDL tick wrap-safe

// Curl codes this port's network process reports (CurlErrorDomain, ResourceErrorCurl.cpp) that mean "no network":
//   5 couldn't resolve proxy, 6 couldn't resolve host (DNS), 7 couldn't connect (refused / no route),
//   28 timed out, 45 interface failed, 55 send failure, 56 receive failure (the network dropped mid-load).
// Not: TLS / certificate errors (35, 51, 60, ...), empty reply (52: the server), HTTP status pages (4xx / 5xx are
// documents, not failures), uBlock ("OmniUBlock*"), HTTPS-only's own panel (its own domain), cancels.
inline bool networkError(const std::string& domain, int code)
{
    if (domain != "CurlErrorDomain") return false;
    switch (code) {
    case 5: case 6: case 7: case 28: case 45: case 55: case 56: return true;
    default: return false;
    }
}
// HTTPS-only's panel ("doesn't support a secure connection", failDomain "OmniHttpsOnly", failCode = the curl code of
// the https attempt) when that attempt failed for a network reason: offline, not insecure. Reloading its http URL
// goes through HTTPS-only again (a fresh https attempt).
constexpr const char* kHttpsOnlyDomain = "OmniHttpsOnly";   // OmniHttpsOnly::kErrorDomain
inline bool httpsOnlyNetworkError(const std::string& domain, int code)
{
    return domain == kHttpsOnlyDomain && (code == 5 || code == 6 || code == 7 || code == 28);
}
inline bool offlineError(const std::string& domain, int code) { return networkError(domain, code) || httpsOnlyNetworkError(domain, code); }
// A tab shows the error panel for a network error (its last load failed that way and nothing replaced it).
inline bool offlineTab(const std::string& failDomain, int failCode, bool messageShown, bool loading, bool crashed, bool unloaded)
{
    return offlineError(failDomain, failCode) && messageShown && !loading && !crashed && !unloaded;
}

// --- what the probe contacts: the failed tab's OWN host (the contact the user just made), nothing else ------------
struct Target {
    bool ok = false;
    std::string host;      // lower case, no brackets / port / user info
    int port = 0;          // explicit port, else 443 (https / HTTPS-only attempt) or 80 (http)
    bool ipv4 = false;     // dotted IPv4 literal: connect without resolving
    bool priv = false;     // a private tab's host: probed, never logged
};
inline bool isIPv4(const std::string& h)
{
    int parts = 0, digits = 0, value = 0;
    for (size_t i = 0; i <= h.size(); ++i) {
        if (i == h.size() || h[i] == '.') {
            if (!digits || value > 255) return false;
            ++parts; digits = 0; value = 0;
            continue;
        }
        if (h[i] < '0' || h[i] > '9' || ++digits > 3) return false;
        value = value * 10 + (h[i] - '0');
    }
    return parts == 4;
}
// url: the failed load's URL (http / https only). httpsAttempt: HTTPS-only's panel (its URL is the http one, the
// failed attempt was https).
inline Target target(const std::string& url, bool httpsAttempt, bool priv)
{
    Target t;
    int defaultPort = 0;
    size_t start = 0;
    if (url.compare(0, 8, "https://") == 0) { defaultPort = 443; start = 8; }
    else if (url.compare(0, 7, "http://") == 0) { defaultPort = httpsAttempt ? 443 : 80; start = 7; }
    else return t;
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    if (size_t at = auth.rfind('@'); at != std::string::npos) auth = auth.substr(at + 1);
    std::string host, port;
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos) return t;
        host = auth.substr(1, close - 1);
        if (close + 1 < auth.size()) { if (auth[close + 1] != ':') return t; port = auth.substr(close + 2); }
    } else {
        const size_t colon = auth.find(':');
        host = auth.substr(0, colon);
        if (colon != std::string::npos) port = auth.substr(colon + 1);
    }
    for (char& c : host) if (c >= 'A' && c <= 'Z') c = char(c + 32);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > 253) return t;
    for (char c : host) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '.' || c == ':')) return t;
    t.port = defaultPort;
    if (!port.empty()) {
        if (port.size() > 5) return t;
        int v = 0;
        for (char c : port) { if (c < '0' || c > '9') return t; v = v * 10 + (c - '0'); }
        if (v < 1 || v > 65535) return t;
        if (!httpsAttempt) t.port = v;
    }
    t.host = host;
    t.ipv4 = isIPv4(host);
    t.priv = priv;
    t.ok = true;
    return t;
}
// What the logs may say about a target: never a private tab's host.
inline std::string logName(const Target& t) { return t.priv ? std::string("(private tab)") : t.host + ":" + std::to_string(t.port); }

// One host per probe round: the active tab's if it is offline, else the first offline tab's (tab order).
struct TabTarget { bool active = false, offline = false, priv = false, httpsAttempt = false; std::string url; };
inline Target chooseTarget(const std::vector<TabTarget>& tabs)
{
    for (const TabTarget& t : tabs)
        if (t.active && t.offline) { Target g = target(t.url, t.httpsAttempt, t.priv); if (g.ok) return g; }
    for (const TabTarget& t : tabs)
        if (!t.active && t.offline) { Target g = target(t.url, t.httpsAttempt, t.priv); if (g.ok) return g; }
    return Target();
}
// How the round can tell "up": a TCP connect needs an address. The title can't resolve names (no getaddrinfo /
// resolver import passes the title's import gate), so a host name falls back to the route check alone, unless the
// shell is built with a resolver (canResolve).
enum class Probe { Tcp, RouteOnly };
inline Probe probeKind(const Target& t, bool canResolve)
{
    if (!t.ok) return Probe::RouteOnly;
    return t.ipv4 || canResolve ? Probe::Tcp : Probe::RouteOnly;
}
// A blocking connect()'s result: connected, or refused by the far end (it answered): the network works.
inline bool connectMeansUp(int rc, int err) { return rc == 0 || err == ECONNREFUSED || err == EISCONN; }

// 5, 10, 20, 30, 30, ... seconds
inline uint32_t backoff(int step)
{
    uint32_t d = kMinGapMs;
    for (int i = 0; i < step && d < kMaxGapMs; ++i) d *= 2;
    return d > kMaxGapMs ? kMaxGapMs : d;
}

enum class Net { Unknown, Up, Down };
inline const char* name(Net n) { return n == Net::Up ? "up" : n == Net::Down ? "down" : "unknown"; }

// The network as Omni knows it. Only watched while some tab shows a network error ("offline tab"):
//   a network error -> route check at once: no route -> Down; else Unknown and a probe soon (Down stays Down)
//   probe = a TCP connect to the failed tab's own host (IPv4 literal, or a name when the shell can resolve);
//   a host name without a resolver: route-only rounds (routeOnlyRound): the route returning while down = up
//   Down + no route  -> no probe, a route check every second; the route comes back -> a probe at once (5 s gap kept)
//   probe "down"     -> Down, next probe after 5, 10, 20, 30, 30 ... s
//   probe "up"       -> Up; Down -> Up is a "back online" event (upEvents() + 1): the offline tabs reload once
//   Unknown -> Up is no event (the network never looked down: a server refusing, not the console offline)
//   no offline tab   -> idle(): nothing probed, state Unknown (the top-bar badge goes away)
class Watch {
public:
    Net state() const { return st_; }
    uint32_t upEvents() const { return events_; }
    bool indicator() const { return st_ == Net::Down; }
    uint32_t nextProbeAt() const { return nextAt_; }

    void noteFailure(uint32_t now, bool routeOk)
    {
        route_ = routeOk;
        routeAt_ = now + kRouteCheckMs;
        if (!routeOk) { st_ = Net::Down; routeBack_ = false; return; }
        if (st_ == Net::Down) return;   // still down as far as we know: keep the backoff
        st_ = Net::Unknown;
        step_ = 0;
        nextAt_ = earliest(now);
    }
    bool wantRouteCheck(uint32_t now) const { return st_ != Net::Up && after(now, routeAt_); }
    void routeChecked(uint32_t now, bool ok)
    {
        routeAt_ = now + kRouteCheckMs;
        if (!ok) st_ = Net::Down;
        else if (!route_ && st_ == Net::Down) { step_ = 0; nextAt_ = earliest(now); routeBack_ = true; }
        route_ = ok;
    }
    bool wantProbe(uint32_t now, bool busy) const { return st_ != Net::Up && !busy && route_ && after(now, nextAt_); }
    void probeStarted(uint32_t now) { lastStart_ = now; started_ = true; }
    // true: the network is back (Down -> Up)
    bool probeResult(uint32_t now, bool up)
    {
        if (up) {
            const bool back = st_ == Net::Down;
            st_ = Net::Up;
            step_ = 0;
            if (back) ++events_;
            return back;
        }
        st_ = Net::Down;
        const uint32_t from = started_ ? lastStart_ : now;
        uint32_t at = now + backoff(step_);
        if (!after(at, from + kMinGapMs)) at = from + kMinGapMs;
        nextAt_ = at;
        if (step_ < 8) ++step_;
        return false;
    }
    // A round without a TCP probe (the target is a host name the title can't resolve): the route coming back while
    // down counts as "up" (the link returned); otherwise nothing is sent and the round is just rescheduled.
    bool routeOnlyRound(uint32_t now)
    {
        if (routeBack_ && st_ == Net::Down) { routeBack_ = false; return probeResult(now, true); }
        nextAt_ = now + backoff(step_);
        if (step_ < 8) ++step_;
        return false;
    }
    void idle()
    {
        routeBack_ = false;
        st_ = Net::Unknown;
        step_ = 0;
        route_ = true;
        nextAt_ = 0;
    }

private:
    uint32_t earliest(uint32_t now) const
    {
        return started_ && !after(now, lastStart_ + kMinGapMs) ? lastStart_ + kMinGapMs : now;
    }
    Net st_ = Net::Unknown;
    uint32_t events_ = 0, nextAt_ = 0, lastStart_ = 0, routeAt_ = 0;
    int step_ = 0;
    bool route_ = true, started_ = false, routeBack_ = false;
};

// Which tabs reload for "back online" event `event`, in order: the active tab first, then by tab order. Only tabs
// showing a network error that were not already reloaded for this event (at most once per event).
struct Cand { int index = 0; bool active = false, offline = false; uint32_t doneEvent = 0; };
inline std::vector<int> reloadOrder(const std::vector<Cand>& tabs, uint32_t event)
{
    std::vector<int> out;
    for (const Cand& c : tabs) if (c.active && c.offline && c.doneEvent != event) out.push_back(c.index);
    for (const Cand& c : tabs) if (!c.active && c.offline && c.doneEvent != event) out.push_back(c.index);
    return out;
}

// --- texts ---------------------------------------------------------------------------------------------------------
inline std::string panelBody(bool autoReload)
{
    return autoReload ? "The console isn't connected to the internet. This page reloads by itself when the connection is back."
                      : "The console isn't connected to the internet. Check the network connection, then press Retry.";
}
inline std::string backOnlineNotice(size_t reloading, bool autoReload)
{
    if (!autoReload) return "Back online. Press Retry to reload the page";
    if (reloading == 0) return "Back online";
    if (reloading == 1) return "Back online. Reloading the page";
    return "Back online. Reloading " + std::to_string(reloading) + " pages";
}
inline std::string settingNotice(bool on)
{
    return on ? "Pages that failed offline reload when the connection is back" : "Pages that failed offline stay as they are";
}
inline const char* settingValue(bool on) { return on ? "On" : "Off"; }

// --- top-bar badge: right of the controller battery and the sleep timer ------------------------------------------
// base: where the sleep timer badge starts; sleepW: its width (0: not shown); textW: the width of kBadge.
struct BadgeLayout { float x = 0; int mode = 0; int textMax = 0; };   // mode 0 hidden, 1 dot only, 2 dot + "Offline"
inline BadgeLayout badgeLayout(float base, float sleepW, float textW)
{
    BadgeLayout b;
    b.x = sleepW > 0 ? base + sleepW + 12.f : base;
    const float room = kTopBarRight - b.x;
    if (room >= 12.f + textW) { b.mode = 2; b.textMax = int(room - 12.f); }
    else if (room >= 8.f) b.mode = 1;
    return b;
}

} // namespace OmniOfflineRetry
'''

SHELL = r'''// OMNI_OFFLINE_RETRY_V1: network-aware error pages, shell side. Included from OmniFeatures3.h (after
// OmniMediaControlsShell.h). The reasons are in tools/apply_offline_retry.py. Main thread except omniOrProbeRun.
#pragma once
#include "OmniOfflineRetry.h"
#include <algorithm>
#include <arpa/inet.h>
#include <atomic>
#include <deque>
#include <memory>
#include <mutex>
#include <netinet/in.h>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>

namespace OOR = OmniOfflineRetry;

// One TCP probe on its own thread (blocking sockets with timeouts: O_NONBLOCK fails with errno 13 in the PS5 title).
// fd is published under m so the main thread can shut down a connect() that outlives the deadline without ever
// touching a closed (possibly reused) descriptor.
struct OmniOrProbe {
    std::mutex m;
    int fd = -1;
    bool abandoned = false;
    OOR::Target target;   // the failed tab's own host (read by the worker only; set before it starts)
    std::atomic<bool> done { false }, up { false };
};
// OMNI_OFFLINE_RETRY_RESOLVE: 1 resolves host names on the probe thread (getaddrinfo). Off by default: getaddrinfo is
// not among the launch title's imports, so the title's import gate would refuse it; names then use route-only rounds.
#ifndef OMNI_OFFLINE_RETRY_RESOLVE
#define OMNI_OFFLINE_RETRY_RESOLVE 0
#endif
#if OMNI_OFFLINE_RETRY_RESOLVE
#include <netdb.h>
#endif
static OOR::Watch omniOrWatch;
static std::shared_ptr<OmniOrProbe> omniOrProbe;                 // in flight
static std::vector<std::shared_ptr<OmniOrProbe>> omniOrStuck;    // past the deadline, thread not back yet
static uint32_t omniOrProbeAt = 0;
struct OmniOrQueued { const Tab* tab; uint32_t event; };
static std::deque<OmniOrQueued> omniOrQueue;                     // staggered reloads (active tab first)
static uint32_t omniOrNextReload = 0;
static int omniOrSetting = -1;   // -1 not read yet, 0 off, 1 on (/data/omni/offline-reload-off.flag)

static bool omniOrOn()
{
    if (omniOrSetting < 0) omniOrSetting = access(omniData(OOR::kOffFlag).c_str(), F_OK) != 0 ? 1 : 0;
    return omniOrSetting == 1;
}
static bool omniOrTabOffline(const Tab& t)
{
    const OmniFxTabState& s = omniFxState(&t);
    return OOR::offlineTab(s.failDomain, s.failCode, !t.message.empty(), t.loading, t.crashed, omniTmIsUnloaded(t));
}
// The error panel (OmniErrorPage.h): "You're offline" instead of "This page couldn't load".
static bool omniOrOfflineShown(const Tab* t) { return t && omniOrWatch.indicator() && omniOrTabOffline(*t); }
static std::string omniOrPanelBody() { return OOR::panelBody(omniOrOn()); }

// Has the console a route to the internet? A UDP socket "connected" to TEST-NET-2 only looks the route up (no
// packet is sent); no route (link down, no address) fails at once. Cheap enough for the main thread.
static bool omniOrRouteUp()
{
    const int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return true;   // can't tell: let the probe decide
    sockaddr_in to {};
    to.sin_family = AF_INET;
    to.sin_port = htons(OOR::kRoutePort);
    inet_pton(AF_INET, OOR::kRouteIp, &to.sin_addr);
    bool ok = false;
    if (!connect(fd, reinterpret_cast<const sockaddr*>(&to), sizeof to)) {
        sockaddr_in me {};
        socklen_t len = sizeof me;
        if (!getsockname(fd, reinterpret_cast<sockaddr*>(&me), &len)) {
            const uint32_t h = ntohl(me.sin_addr.s_addr);
            ok = h && (h >> 24) != 127;
        }
    }
    close(fd);
    return ok;
}

// connect() on fd to address a (blocking, SO_SNDTIMEO / SO_RCVTIMEO kConnectMs). False: abandoned meanwhile.
static bool omniOrConnect(OmniOrProbe& p, int family, const sockaddr* a, socklen_t len, bool& up)
{
    const int fd = socket(family, SOCK_STREAM, 0);
    if (fd < 0) return true;
    timeval tv { OOR::kConnectMs / 1000, (OOR::kConnectMs % 1000) * 1000 };
    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    {
        std::lock_guard<std::mutex> g(p.m);
        if (p.abandoned) { close(fd); return false; }
        p.fd = fd;
    }
    const int rc = connect(fd, a, len);
    const int err = rc ? errno : 0;
    bool abandoned;
    {
        std::lock_guard<std::mutex> g(p.m);
        p.fd = -1;
        close(fd);
        abandoned = p.abandoned;
    }
    if (abandoned) return false;   // shut down by the main thread: whatever connect() said is not an answer
    up = OOR::connectMeansUp(rc, err);
    return true;
}
// The probe thread: a TCP connect to the failed tab's own host and port (nothing is sent). Connected or refused = up.
static void omniOrProbeRun(std::shared_ptr<OmniOrProbe> p)
{
    bool up = false;
    const OOR::Target& t = p->target;
    if (t.ipv4) {
        sockaddr_in a {};
        a.sin_family = AF_INET;
        a.sin_port = htons(static_cast<uint16_t>(t.port));
        if (inet_pton(AF_INET, t.host.c_str(), &a.sin_addr) == 1)
            omniOrConnect(*p, AF_INET, reinterpret_cast<const sockaddr*>(&a), sizeof a, up);
    }
#if OMNI_OFFLINE_RETRY_RESOLVE
    else {
        addrinfo hints {};
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;
        addrinfo* list = nullptr;
        const std::string port = std::to_string(t.port);
        if (!getaddrinfo(t.host.c_str(), port.c_str(), &hints, &list)) {
            int tries = 0;
            for (addrinfo* a = list; a && !up && tries < 2; a = a->ai_next, ++tries)
                if (!omniOrConnect(*p, a->ai_family, a->ai_addr, a->ai_addrlen, up)) break;
            freeaddrinfo(list);
        }
    }
#endif
    p->up = up;
    p->done = true;
}
// This round's target: the active tab's host if it is offline, else the first offline tab's.
static OOR::Target omniOrTarget()
{
    std::vector<OOR::TabTarget> v;
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Tab& t = *tabs[i];
        const OmniFxTabState& s = omniFxState(&t);
        OOR::TabTarget x;
        x.active = i == size_t(selected);
        x.offline = omniOrTabOffline(t);
        x.priv = t.omniPrivate;
        x.httpsAttempt = OOR::httpsOnlyNetworkError(s.failDomain, s.failCode);
        x.url = s.failURL.empty() ? t.url : s.failURL;
        v.push_back(std::move(x));
    }
    return OOR::chooseTarget(v);
}

static void omniOrReload(Tab& t)
{
    OmniFxTabState& s = omniFxState(&t);
    const std::string url = s.failURL.empty() ? t.url : s.failURL;
    const OOR::Target g = OOR::target(url, false, t.omniPrivate);
    fprintf(stderr, "OMNI OFFLINE: back online, reloading %s\n", g.ok ? OOR::logName(g).c_str() : "a tab"); fflush(stderr);
    t.message.clear();
    omniShellDirty = true;
    if (!omniWebURL(url)) { WKPageReload(t.page); return; }
    omniSavedDocumentChanged(t);
    t.url = url;
    t.loading = true;
    omniApplyUserAgent(&t, url);
    auto u = adoptWK(WKURLCreateWithUTF8CString(url.c_str()));
    WKPageLoadURL(t.page, u.get());
}
// Down -> Up: the offline tabs reload once for this event (active first, staggered), if the setting is on.
static void omniOrBackOnline(uint32_t now)
{
    const uint32_t event = omniOrWatch.upEvents();
    std::vector<OOR::Cand> c;
    for (size_t i = 0; i < tabs.size(); ++i)
        c.push_back({ int(i), i == size_t(selected), omniOrTabOffline(*tabs[i]), omniFxState(tabs[i].get()).orEvent });
    const std::vector<int> order = OOR::reloadOrder(c, event);
    if (order.empty()) return;
    const bool on = omniOrOn();
    if (on) {
        for (int i : order) {
            omniFxState(tabs[size_t(i)].get()).orEvent = event;
            omniOrQueue.push_back({ tabs[size_t(i)].get(), event });
        }
        omniOrNextReload = now + OOR::kFirstReloadMs;
    }
    notice(OOR::backOnlineNotice(order.size(), on));
}
static void omniOrAnswer(uint32_t now, bool up)
{
    const OOR::Net before = omniOrWatch.state();
    const bool back = omniOrWatch.probeResult(now, up);
    if (omniOrWatch.state() != before) {
        omniShellDirty = true;
        fprintf(stderr, "OMNI OFFLINE: network %s -> %s\n", OOR::name(before), OOR::name(omniOrWatch.state())); fflush(stderr);
    }
    if (back) omniOrBackOnline(now);
}

// failed() (OmniBrowser.cpp), after the error panel recorded the failure.
static void omniOrFailed(Tab&, const std::string& domain, int code)
{
    if (omniTestMode() || !OOR::networkError(domain, code)) return;
    const bool route = omniOrRouteUp();
    omniOrWatch.noteFailure(SDL_GetTicks(), route);
    omniShellDirty = true;
    fprintf(stderr, "OMNI OFFLINE: network error %d; route %s; network %s\n", code, route ? "yes" : "no", OOR::name(omniOrWatch.state()));
    fflush(stderr);
}

// --- per pass (omniF3Tick) -------------------------------------------------------------------------------------------
static void omniOrTick(uint32_t now)
{
    if (omniTestMode()) return;
    // 1. the probe's answer (or its deadline)
    if (omniOrProbe && omniOrProbe->done) {
        const bool up = omniOrProbe->up;
        omniOrProbe.reset();
        omniOrAnswer(now, up);
    } else if (omniOrProbe && OOR::after(now, omniOrProbeAt + OOR::kProbeDeadlineMs)) {
        {
            std::lock_guard<std::mutex> g(omniOrProbe->m);
            omniOrProbe->abandoned = true;
            if (omniOrProbe->fd >= 0) shutdown(omniOrProbe->fd, SHUT_RDWR);
        }
        omniOrStuck.push_back(std::move(omniOrProbe));
        omniOrProbe.reset();
        omniOrAnswer(now, false);
    }
    if (!omniOrStuck.empty())
        omniOrStuck.erase(std::remove_if(omniOrStuck.begin(), omniOrStuck.end(), [](const std::shared_ptr<OmniOrProbe>& p) { return p->done.load(); }), omniOrStuck.end());
    // 2. watch the network only while a tab shows a network error
    bool any = false;
    for (auto& t : tabs) if (omniOrTabOffline(*t)) { any = true; break; }
    if (!any) {
        if (omniOrWatch.indicator()) omniShellDirty = true;
        omniOrWatch.idle();
    } else {
        if (omniOrWatch.wantRouteCheck(now)) {
            const bool was = omniOrWatch.indicator();
            omniOrWatch.routeChecked(now, omniOrRouteUp());
            if (was != omniOrWatch.indicator()) omniShellDirty = true;
        }
        if (omniOrWatch.wantProbe(now, omniOrProbe != nullptr || omniOrStuck.size() >= OOR::kMaxStuckProbes)) {
            const OOR::Target g = omniOrTarget();
            if (OOR::probeKind(g, OMNI_OFFLINE_RETRY_RESOLVE != 0) == OOR::Probe::RouteOnly) {
                const OOR::Net before = omniOrWatch.state();
                if (omniOrWatch.routeOnlyRound(now)) omniOrBackOnline(now);
                if (omniOrWatch.state() != before) omniShellDirty = true;
            } else {
                auto p = std::make_shared<OmniOrProbe>();
                p->target = g;
                omniOrProbe = p;
                omniOrProbeAt = now;
                omniOrWatch.probeStarted(now);
                fprintf(stderr, "OMNI OFFLINE: probing %s\n", OOR::logName(g).c_str()); fflush(stderr);
                std::thread(omniOrProbeRun, p).detach();
            }
        }
    }
    // 3. staggered reloads (each tab checked again: still open, still offline, not reloaded by the user meanwhile)
    while (!omniOrQueue.empty() && OOR::after(now, omniOrNextReload)) {
        const OmniOrQueued q = omniOrQueue.front();
        omniOrQueue.pop_front();
        Tab* t = nullptr;
        for (auto& x : tabs) if (x.get() == q.tab) { t = x.get(); break; }
        if (!t || !omniOrTabOffline(*t) || omniFxState(t).orEvent != q.event) continue;
        omniOrReload(*t);
        omniOrNextReload = now + OOR::kStaggerMs;
        break;
    }
}

// --- top bar (omniDrawTopBar, right of the controller battery and the sleep timer) -----------------------------------
static void omniOrDrawTopBar(float base)
{
    if (!omniOrWatch.indicator()) return;
    const OmniTheme& T = omniTheme();
    const float sleepW = omniSt.on() ? float(omniTextWidthPx(omniCaption, omniSt.badge(SDL_GetTicks())) / displayScale) : 0.f;
    const float textW = float(omniTextWidthPx(omniCaptionBold, OOR::kBadge) / displayScale);
    const OOR::BadgeLayout b = OOR::badgeLayout(base, sleepW, textW);
    if (!b.mode) return;
    omniDisc(b.x + 3.5f, 30, 3.5f, omniWarn);
    if (b.mode == 2) omniLabel(OOR::kBadge, b.x + 12, 30, omniCaptionBold, T.inkDim, 0, b.textMax);
}

// --- Browser settings: "Reload pages when back online" On / Off ------------------------------------------------------
static bool omniOrSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData(OOR::kOffFlag);
    if (omniOrOn()) { if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); } }
    else unlink(flag.c_str());
    omniOrSetting = -1;
    if (!omniOrOn()) omniOrQueue.clear();
    notice(OOR::settingNotice(omniOrOn()));
    return true;
}
'''

EDITS = {
    'OmniErrorPage.h': [
        ('    int failCode = 0;\n',
         '    int failCode = 0;\n'
         '    uint32_t orEvent = 0;   // OMNI_OFFLINE_RETRY_V1: the "back online" event this tab was last reloaded for\n'),
        ('struct OmniFxErrorLayout { int x, y, w, h, chipY; int chipX[3], chipW[3]; int chips; };\n',
         'static bool omniOrOfflineShown(const Tab* t); // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h): "You\'re offline"\n'
         'static std::string omniOrPanelBody();\n'
         'struct OmniFxErrorLayout { int x, y, w, h, chipY; int chipX[3], chipW[3]; int chips; };\n'),
        ('        : t->message.find("redirected") != std::string::npos ? "Too many redirects" : "This page couldn\'t load";\n',
         '        : t->message.find("redirected") != std::string::npos ? "Too many redirects"\n'
         '        : omniOrOfflineShown(t) ? "You\'re offline" : "This page couldn\'t load"; // OMNI_OFFLINE_RETRY_V1\n'),
        ('    if (!crashed && !cert && !blocked && s.failCode) body += " (error " + std::to_string(s.failCode) + ")";\n',
         '    if (!crashed && !cert && !blocked && s.failCode) body += " (error " + std::to_string(s.failCode) + ")";\n'
         '    if (!crashed && omniOrOfflineShown(t)) body = omniOrPanelBody(); // OMNI_OFFLINE_RETRY_V1: reloads when back online\n'),
    ],
    'OmniBrowser.cpp': [
        ('static void omniStDrawTopBar(float x);        // OMNI_SLEEP_TIMER_V1: "zZ 23 min" in the top bar\n',
         'static void omniStDrawTopBar(float x);        // OMNI_SLEEP_TIMER_V1: "zZ 23 min" in the top bar\n'
         'static void omniOrDrawTopBar(float x);        // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h): "Offline" in the top bar\n'
         'static void omniOrFailed(Tab& tab, const std::string& domain, int code); // OMNI_OFFLINE_RETRY_V1: network errors\n'),
        ('    omniFxRecordFailure(tab, error); // OMNI_FEATURES_V1: error panel (Retry / Back)\n',
         '    omniFxRecordFailure(tab, error); // OMNI_FEATURES_V1: error panel (Retry / Back)\n'
         '    omniOrFailed(tab, domain, code); // OMNI_OFFLINE_RETRY_V1: a network error: is the console offline? (reload when back)\n'),
        ('    omniStDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_SLEEP_TIMER_V1: "zZ 23 min" while active\n',
         '    omniStDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_SLEEP_TIMER_V1: "zZ 23 min" while active\n'
         '    omniOrDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_OFFLINE_RETRY_V1: "Offline" while down\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniHoSettingsInput(int id, int b);\n',
         'static bool omniHoSettingsInput(int id, int b);\n'
         'constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n'
         'static bool omniOrOn();\n'
         'static bool omniOrSettingsInput(int b);\n'),
        ('    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n',
         '    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n'
         '    add(omniOrRowId, "Reload pages when back online", omniOrOn() ? "On" : "Off", true); // OMNI_OFFLINE_RETRY_V1\n'),
        ('    if (r.id == omniHoRowId || r.id == omniHoGpcRowId) return omniHoSettingsInput(r.id, b); // OMNI_HTTPS_ONLY_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniOrRowId) return omniOrSettingsInput(b); // OMNI_OFFLINE_RETRY_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniHoRowId || r.id == omniHoGpcRowId) return omniHoSettingsInput(r.id, b); // OMNI_HTTPS_ONLY_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n',
         '#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n'
         '#include "OmniOfflineRetryShell.h" // OMNI_OFFLINE_RETRY_V1\n'),
        ('    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n',
         '    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n'
         '    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n'),
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
    for need, tool in (('OMNI_HTTPS_ONLY_V1', 'apply_https_only.py'), ('OMNI_MEDIA_CONTROLS_V1', 'apply_media_controls.py'),
                       ('OMNI_SLEEP_TIMER_V1', 'apply_sleep_timer.py')):
        if need not in f3:
            sys.exit('OmniFeatures3.h: %s missing: %s first' % (need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniOfflineRetry.h', PURE, 'OmniHttpsOnly.h'),
            write_new('OmniOfflineRetryShell.h', SHELL, 'OmniHttpsOnlyShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
