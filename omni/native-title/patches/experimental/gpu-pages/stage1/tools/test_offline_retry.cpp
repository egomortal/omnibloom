// OMNI_OFFLINE_RETRY_V1: tests for engine/entry/OmniOfflineRetry.h (pure part).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_offline_retry.cpp -o t && ./t
#include "OmniOfflineRetry.h"
#include <cstdio>
#include <cstring>

namespace OOR = OmniOfflineRetry;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static void classification()
{
    for (int c : { 5, 6, 7, 28, 45, 55, 56 }) CHECK(OOR::networkError("CurlErrorDomain", c));
    for (int c : { 0, 1, 3, 16, 35, 51, 52, 58, 60, 77, 92, -999 }) CHECK(!OOR::networkError("CurlErrorDomain", c));
    CHECK(!OOR::networkError("OmniUBlock", 6));
    CHECK(!OOR::networkError("OmniUBlockRedirect", 7));
    CHECK(!OOR::networkError("OmniHttpsOnly", 7));        // HTTPS-only's own panel domain (any name but curl's)
    CHECK(!OOR::networkError("WebKitErrorDomain", 102));
    CHECK(!OOR::networkError("WebKitInternal", 6));
    CHECK(!OOR::networkError("", 6));
    CHECK(!OOR::networkError("curlerrordomain", 6));      // exact domain
    // offline tab: network error + panel shown + not loading / crashed / unloaded
    CHECK(OOR::offlineTab("CurlErrorDomain", 6, true, false, false, false));
    CHECK(!OOR::offlineTab("CurlErrorDomain", 6, false, false, false, false));   // page loaded since (message cleared)
    CHECK(!OOR::offlineTab("CurlErrorDomain", 6, true, true, false, false));     // reloading
    CHECK(!OOR::offlineTab("CurlErrorDomain", 6, true, false, true, false));     // crashed
    CHECK(!OOR::offlineTab("CurlErrorDomain", 6, true, false, false, true));     // unloaded
    CHECK(!OOR::offlineTab("CurlErrorDomain", 60, true, false, false, false));   // certificate
    // connect results
    CHECK(OOR::connectMeansUp(0, 0));
    CHECK(OOR::connectMeansUp(-1, ECONNREFUSED));
    CHECK(OOR::connectMeansUp(-1, EISCONN));
    CHECK(!OOR::connectMeansUp(-1, ETIMEDOUT));
    CHECK(!OOR::connectMeansUp(-1, ENETUNREACH));
    CHECK(!OOR::connectMeansUp(-1, EHOSTUNREACH));
    CHECK(!OOR::connectMeansUp(-1, EAGAIN));               // SO_SNDTIMEO expiry
    CHECK(!OOR::connectMeansUp(-1, EINPROGRESS));
    CHECK(!OOR::connectMeansUp(-1, EACCES));               // errno 13
}

static void schedule()
{
    CHECK(OOR::backoff(0) == 5000);
    CHECK(OOR::backoff(1) == 10000);
    CHECK(OOR::backoff(2) == 20000);
    CHECK(OOR::backoff(3) == 30000);
    CHECK(OOR::backoff(4) == 30000);
    CHECK(OOR::backoff(100) == 30000);
    CHECK(OOR::after(10, 10) && OOR::after(11, 10) && !OOR::after(9, 10));
    CHECK(OOR::after(5u, 0xfffffff0u));                    // tick wrap
    CHECK(!OOR::after(0xfffffff0u, 5u));
}

static void watchNoRoute()
{
    OOR::Watch w;
    CHECK(w.state() == OOR::Net::Unknown && !w.indicator());
    w.noteFailure(1000, false);                         // DNS failure, no route: down at once
    CHECK(w.state() == OOR::Net::Down && w.indicator());
    CHECK(!w.wantProbe(1000, false));                   // no route: no probe traffic at all
    CHECK(!w.wantProbe(60000, false));
    CHECK(!w.wantRouteCheck(1500));
    CHECK(w.wantRouteCheck(2000));
    w.routeChecked(2000, false);
    CHECK(!w.wantRouteCheck(2999) && w.wantRouteCheck(3000));
    w.routeChecked(3000, true);                         // cable / Wi-Fi back: probe at once (no probe ran before)
    CHECK(w.wantProbe(3000, false));
    CHECK(!w.wantProbe(3000, true));                    // busy
    w.probeStarted(3000);
    CHECK(!w.probeResult(3100, false));                 // still no internet (router up, WAN down)
    CHECK(w.state() == OOR::Net::Down);
    CHECK(!w.wantProbe(8099, false) && w.wantProbe(8100, false));   // 5 s
    w.probeStarted(8100);
    CHECK(!w.probeResult(8200, false));
    CHECK(!w.wantProbe(18199, false) && w.wantProbe(18200, false)); // 10 s
    w.probeStarted(18200);
    CHECK(w.probeResult(18300, true));                  // back: one event
    CHECK(w.upEvents() == 1 && w.state() == OOR::Net::Up && !w.indicator());
    CHECK(!w.wantProbe(99999, false));                  // up: nothing more
    CHECK(!w.wantRouteCheck(99999));
    CHECK(!w.probeResult(18400, true));                 // a second "up": no new event
    CHECK(w.upEvents() == 1);
}

static void watchRouteButNoInternet()
{
    OOR::Watch w;
    w.noteFailure(0, true);                             // route ok: unknown, probe now
    CHECK(w.state() == OOR::Net::Unknown && !w.indicator());
    CHECK(w.wantProbe(0, false));
    w.probeStarted(0);
    CHECK(!w.probeResult(3000, false));
    CHECK(w.indicator());
    // backoff 5, 10, 20, 30, 30 measured from each answer, never closer than 5 s to the last start
    uint32_t t = 3000;
    const uint32_t gaps[] = { 5000, 10000, 20000, 30000, 30000, 30000 };
    for (uint32_t g : gaps) {
        CHECK(!w.wantProbe(t + g - 1, false));
        CHECK(w.wantProbe(t + g, false));
        w.probeStarted(t + g);
        t += g;
        CHECK(!w.probeResult(t, false));
    }
    // a new network error while down keeps the backoff (no hammering)
    const uint32_t next = w.nextProbeAt();
    w.noteFailure(t + 10, true);
    CHECK(w.state() == OOR::Net::Down && w.nextProbeAt() == next);
    // the route goes away while down, then comes back: backoff reset, probe once the 5 s gap allows
    w.routeChecked(t + 1000, false);
    CHECK(!w.wantProbe(t + 40000, false));
    w.routeChecked(t + 2000, true);
    CHECK(w.wantProbe(t + 5000, false));
    CHECK(!w.wantProbe(t + 4999, false));
}

static void watchServerRefusing()
{
    // The console is online, a site refuses: Unknown -> Up is no event (no reload loop).
    OOR::Watch w;
    for (int i = 0; i < 5; ++i) {
        const uint32_t now = 100000u * uint32_t(i + 1);
        w.noteFailure(now, true);
        CHECK(!w.indicator());
        CHECK(w.wantProbe(now, false));
        w.probeStarted(now);
        CHECK(!w.probeResult(now + 50, true));
    }
    CHECK(w.upEvents() == 0);
    // min gap: two failures 1 s apart: the second probe waits for 5 s after the first
    OOR::Watch v;
    v.noteFailure(1000, true); v.probeStarted(1000); CHECK(!v.probeResult(1100, true));
    v.noteFailure(2000, true);
    CHECK(!v.wantProbe(5999, false) && v.wantProbe(6000, false));
}

static void watchIdle()
{
    OOR::Watch w;
    w.noteFailure(0, false);
    CHECK(w.indicator());
    w.idle();                                           // the user closed / left every offline tab
    CHECK(!w.indicator() && w.state() == OOR::Net::Unknown);
    // a late probe answer "up" after idle is no event (never seen down since)
    CHECK(!w.probeResult(10, true));
    CHECK(w.upEvents() == 0);
    // wrap-around ticks
    OOR::Watch x;
    x.noteFailure(0xfffff000u, true);
    x.probeStarted(0xfffff000u);
    CHECK(!x.probeResult(0xfffff100u, false));
    CHECK(!x.wantProbe(0xfffff000u + 4999u, false));
    CHECK(x.wantProbe(0xfffff100u + 5000u, false));     // wraps past 0
    CHECK(x.probeResult(0x2000u, true) && x.upEvents() == 1);
}

static void order()
{
    std::vector<OOR::Cand> t = {
        { 0, false, true, 0 }, { 1, false, false, 0 }, { 2, true, true, 0 }, { 3, false, true, 1 }, { 4, false, true, 0 },
    };
    auto o = OOR::reloadOrder(t, 1);
    CHECK(o.size() == 3 && o[0] == 2 && o[1] == 0 && o[2] == 4);   // active first; 1 not offline; 3 done for event 1
    o = OOR::reloadOrder(t, 2);
    CHECK(o.size() == 4 && o[0] == 2 && o[1] == 0 && o[2] == 3 && o[3] == 4);
    t[2].offline = false;                                           // the active tab is fine: others only
    o = OOR::reloadOrder(t, 2);
    CHECK(o.size() == 3 && o[0] == 0);
    CHECK(OOR::reloadOrder({}, 1).empty());
}

static void texts()
{
    CHECK(std::strcmp(OOR::kTitle, "You're offline") == 0);
    CHECK(OOR::panelBody(true).find("reloads by itself") != std::string::npos);
    CHECK(OOR::panelBody(false).find("press Retry") != std::string::npos);
    CHECK(OOR::backOnlineNotice(1, true) == "Back online. Reloading the page");
    CHECK(OOR::backOnlineNotice(3, true) == "Back online. Reloading 3 pages");
    CHECK(OOR::backOnlineNotice(0, true) == "Back online");
    CHECK(OOR::backOnlineNotice(2, false).find("Retry") != std::string::npos);
    CHECK(std::strcmp(OOR::settingValue(true), "On") == 0 && std::strcmp(OOR::settingValue(false), "Off") == 0);
    CHECK(OOR::settingNotice(true) != OOR::settingNotice(false));
    CHECK(std::strcmp(OOR::kOffFlag, "offline-reload-off.flag") == 0);
    // probe targets are public anycast addresses, the route address is TEST-NET-2 (no LAN address anywhere)
    CHECK(std::strcmp(OOR::kRouteIp, "198.51.100.1") == 0);
    CHECK(OOR::kConnectMs * 2 <= int(OOR::kProbeDeadlineMs));
}

static void badge()
{
    auto b = OOR::badgeLayout(1155.f, 0.f, 48.f);                   // battery shown, no sleep timer
    CHECK(b.mode == 2 && b.x == 1155.f && b.textMax == int(1276 - 1155 - 12));
    b = OOR::badgeLayout(1130.f, 0.f, 48.f);
    CHECK(b.mode == 2 && b.x == 1130.f);
    b = OOR::badgeLayout(1155.f, 62.f, 48.f);                       // + "zZ 23 min": only the dot fits
    CHECK(b.x == 1229.f && b.mode == 1);
    b = OOR::badgeLayout(1130.f, 62.f, 48.f);                       // no battery: dot + text fit
    CHECK(b.x == 1204.f && b.mode == 2);
    b = OOR::badgeLayout(1155.f, 120.f, 48.f);                      // no room at all
    CHECK(b.mode == 0);
}

static void targets()
{
    auto t = OOR::target("https://Example.COM./path?q=1#x", false, false);
    CHECK(t.ok && t.host == "example.com" && t.port == 443 && !t.ipv4 && !t.priv);
    t = OOR::target("http://example.com", false, false);
    CHECK(t.ok && t.port == 80);
    t = OOR::target("http://example.com", true, false);                  // HTTPS-only: the attempt was https
    CHECK(t.ok && t.port == 443);
    t = OOR::target("http://example.com:8080/", true, false);
    CHECK(t.ok && t.port == 443);
    t = OOR::target("http://user:pw@203.0.113.7:8080/a", false, false); // TEST-NET-3 literal, explicit port
    CHECK(t.ok && t.host == "203.0.113.7" && t.port == 8080 && t.ipv4);
    t = OOR::target("https://[2001:db8::1]:8443/", false, false);
    CHECK(t.ok && t.host == "2001:db8::1" && t.port == 8443 && !t.ipv4);
    CHECK(!OOR::target("omni://pages/start/", false, false).ok);
    CHECK(!OOR::target("about:blank", false, false).ok);
    CHECK(!OOR::target("https:///x", false, false).ok);
    CHECK(!OOR::target("https://a b/", false, false).ok);
    CHECK(!OOR::target("https://example.com:99999/", false, false).ok);
    CHECK(!OOR::target("https://example.com:0/", false, false).ok);
    CHECK(!OOR::target("https://example.com:8x/", false, false).ok);
    CHECK(OOR::isIPv4("1.2.3.4") && !OOR::isIPv4("1.2.3") && !OOR::isIPv4("1.2.3.256") && !OOR::isIPv4("a.b.c.d") && !OOR::isIPv4("1..2.3"));
    // probe kind: IPv4 literal -> TCP; a name -> route-only unless the shell can resolve
    CHECK(OOR::probeKind(OOR::target("http://203.0.113.7/", false, false), false) == OOR::Probe::Tcp);
    CHECK(OOR::probeKind(OOR::target("https://example.com/", false, false), false) == OOR::Probe::RouteOnly);
    CHECK(OOR::probeKind(OOR::target("https://example.com/", false, false), true) == OOR::Probe::Tcp);
    CHECK(OOR::probeKind(OOR::Target(), true) == OOR::Probe::RouteOnly);
    // private tabs: probed, never logged
    t = OOR::target("https://secret.example/", false, true);
    CHECK(t.ok && t.priv && OOR::logName(t) == "(private tab)" && OOR::logName(t).find("secret") == std::string::npos);
    CHECK(OOR::logName(OOR::target("https://example.com/", false, false)) == "example.com:443");
    // one host per round: the active offline tab first, else the first offline tab
    std::vector<OOR::TabTarget> v(3);
    v[0].offline = true; v[0].url = "https://a.example/";
    v[1].active = true; v[1].offline = true; v[1].url = "http://b.example/";
    v[2].offline = true; v[2].url = "https://c.example/"; v[2].priv = true;
    t = OOR::chooseTarget(v);
    CHECK(t.host == "b.example" && t.port == 80);
    v[1].offline = false;                                                // the active tab is fine
    t = OOR::chooseTarget(v);
    CHECK(t.host == "a.example" && t.port == 443);
    v[0].url = "omni://pages/start/";                                    // unusable: the next offline tab
    t = OOR::chooseTarget(v);
    CHECK(t.host == "c.example" && t.priv);
    v[1].offline = true; v[1].httpsAttempt = true;                       // HTTPS-only panel: port 443
    t = OOR::chooseTarget(v);
    CHECK(t.host == "b.example" && t.port == 443);
    for (auto& x : v) x.offline = false;
    CHECK(!OOR::chooseTarget(v).ok);
    // HTTPS-only panels caused by a network error count as offline; other HTTPS-only panels don't
    for (int c : { 5, 6, 7, 28 }) CHECK(OOR::httpsOnlyNetworkError("OmniHttpsOnly", c) && OOR::offlineTab("OmniHttpsOnly", c, true, false, false, false));
    for (int c : { 35, 60, 52, 56, -1 }) CHECK(!OOR::offlineTab("OmniHttpsOnly", c, true, false, false, false));
    CHECK(!OOR::httpsOnlyNetworkError("CurlErrorDomain", 7));
    CHECK(OOR::offlineError("CurlErrorDomain", 56) && !OOR::offlineError("OmniHttpsOnly", 56));
}

static void routeOnly()
{
    OOR::Watch w;
    w.noteFailure(0, false);                            // name host, no route: down
    w.routeChecked(1000, false);
    CHECK(!w.wantProbe(5000, false));
    w.routeChecked(2000, true);                         // link back
    CHECK(w.wantProbe(2000, false));
    CHECK(w.routeOnlyRound(2000) && w.upEvents() == 1 && w.state() == OOR::Net::Up);
    // route there all along (WAN down / DNS): route-only rounds can't tell: nothing sent, rescheduled, no event
    OOR::Watch x;
    x.noteFailure(0, true);
    CHECK(x.wantProbe(0, false));
    CHECK(!x.routeOnlyRound(0) && x.state() == OOR::Net::Unknown && !x.indicator());
    CHECK(!x.wantProbe(4999, false) && x.wantProbe(5000, false));
    CHECK(!x.routeOnlyRound(5000) && !x.wantProbe(14999, false) && x.wantProbe(15000, false));
    CHECK(x.upEvents() == 0);
    // a route that comes back, then a new no-route failure: the "came back" mark is cleared
    OOR::Watch y;
    y.noteFailure(0, false);
    y.routeChecked(1000, true);
    y.noteFailure(1500, false);
    y.routeChecked(2500, false);
    CHECK(!y.wantProbe(9000, false));
    y.routeChecked(3500, true);
    CHECK(y.routeOnlyRound(5000));
    // idle clears it too
    OOR::Watch z;
    z.noteFailure(0, false); z.routeChecked(1000, true); z.idle();
    z.noteFailure(2000, true);
    CHECK(!z.routeOnlyRound(2000) && z.upEvents() == 0);
}

int main()
{
    targets();
    routeOnly();
    classification();
    schedule();
    watchNoRoute();
    watchRouteButNoInternet();
    watchServerRefusing();
    watchIdle();
    order();
    texts();
    badge();
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
