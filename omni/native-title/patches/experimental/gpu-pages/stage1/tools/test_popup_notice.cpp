// OMNI_POPUP_NOTICE_V1: host tests of the pure part (OmniPopupNotice.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_popup_notice.cpp -o t && ./t
#include "OmniPopupNotice.h"
#include <cstdio>

namespace P = OmniPopupNotice;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // hosts
    CHECK(P::hostOf("https://www.Example.COM:8443/a?b#c") == "www.example.com");
    CHECK(P::hostOf("http://user:pw@example.org./x") == "example.org");
    CHECK(P::hostOf("HTTPS://example.net") == "example.net");
    CHECK(P::hostOf("http://[::1]:8080/") == "::1");
    CHECK(P::hostOf("about:blank").empty());
    CHECK(P::hostOf("javascript:alert(1)").empty());
    CHECK(P::hostOf("").empty());
    CHECK(P::hostKey("WWW.Example.com.") == "example.com");
    CHECK(P::hostKey("www.") == "www");
    CHECK(P::hostKey("bad host").empty());
    CHECK(P::hostKey("a..b").empty());
    CHECK(P::hostKey(std::string(300, 'a')).empty());
    CHECK(P::covers("example.com", "example.com"));
    CHECK(P::covers("example.com", "www.example.com"));
    CHECK(P::covers("example.com", "m.example.com"));
    CHECK(!P::covers("example.com", "badexample.com"));
    CHECK(!P::covers("example.com", "example.com.evil.test"));
    CHECK(!P::covers("m.example.com", "example.com"));
    CHECK(!P::covers("", "example.com"));

    // allow list
    P::AllowList l;
    CHECK(P::add(l, "www.example.com"));
    CHECK(!P::add(l, "example.com"));          // same key
    CHECK(P::add(l, "Example.ORG"));
    CHECK(!P::add(l, "not a host"));
    CHECK(l.hosts.size() == 2 && l.hosts[0] == "example.com" && l.hosts[1] == "example.org");
    CHECK(P::allowedBy(l, "sub.example.com"));
    CHECK(!P::allowedBy(l, "example.net"));
    const std::string text = P::serialize(l);
    CHECK(text == "omni-popup-allow\t1\nexample.com\nexample.org\n");
    P::AllowList back = P::parse(text);
    CHECK(back.hosts == l.hosts);
    P::AllowList crlf = P::parse("omni-popup-allow\t1\r\n# comment\r\n\r\n  www.Example.net  \r\nbad host\r\nexample.net\r\nexample.edu");
    CHECK(crlf.hosts.size() == 2 && crlf.hosts[0] == "example.net" && crlf.hosts[1] == "example.edu");
    CHECK(P::parse("").hosts.empty());
    CHECK(P::parse("example.com\n").hosts.size() == 1);   // no header: still read
    std::string big = "omni-popup-allow\t1\n";
    for (int i = 0; i < 700; ++i) big += "h" + std::to_string(i) + ".example.com\n";
    P::AllowList capped = P::parse(big);
    CHECK(capped.hosts.size() == P::kMaxHosts);
    CHECK(!P::add(capped, "one-more.example.com"));        // full
    std::string huge(P::kMaxFileBytes + 100, 'a');
    huge += "\nexample.com\n";
    CHECK(P::parse(huge).hosts.empty());                    // past the byte cap: not read
    // remove takes the covering parents too
    P::AllowList r; P::add(r, "example.com"); P::add(r, "m.example.com"); P::add(r, "example.org");
    CHECK(P::remove(r, "www.m.example.com"));
    CHECK(r.hosts.size() == 1 && r.hosts[0] == "example.org");
    CHECK(!P::remove(r, "example.net"));

    // private split
    P::AllowList saved, session;
    P::add(saved, "example.com");
    P::add(session, "example.org");
    CHECK(P::isAllowed(saved, session, "www.example.com", false));
    CHECK(P::isAllowed(saved, session, "www.example.com", true));
    CHECK(!P::isAllowed(saved, session, "example.org", false));   // a private choice never reaches a normal tab
    CHECK(P::isAllowed(saved, session, "example.org", true));
    CHECK(!P::isAllowed(saved, session, "", true));

    // recent list
    P::Recent rec;
    const uintptr_t t1 = 0x1000, t2 = 0x2000;
    CHECK(P::count(rec, t1) == 0 && P::list(rec, t1) == nullptr);
    for (int i = 0; i < 7; ++i) P::record(rec, t1, "https://example.com/p" + std::to_string(i), "example.com", P::kGesture);
    CHECK(P::count(rec, t1) == P::kPerTab);
    CHECK((*P::list(rec, t1))[0].url == "https://example.com/p6");
    CHECK((*P::list(rec, t1))[4].url == "https://example.com/p2");
    P::record(rec, t1, "https://example.com/p4", "example.com", P::kGesture);   // repeat: to the front, counted
    CHECK((*P::list(rec, t1))[0].url == "https://example.com/p4" && (*P::list(rec, t1))[0].count == 2);
    CHECK(P::count(rec, t1) == P::kPerTab);
    CHECK(P::rowValue((*P::list(rec, t1))[0]) == "No press x2");
    P::record(rec, t2, "https://ads.example.net/x", "example.org", P::kAd);
    CHECK(P::allowCandidate(rec, t2).empty());                 // an ad pop-up never offers Always allow
    P::record(rec, t2, "https://example.org/real", "www.example.org", P::kGesture);
    CHECK(P::allowCandidate(rec, t2) == "example.org");
    P::record(rec, t2, "https://example.org/blocked", "example.org", P::kSiteBlock);
    CHECK(P::allowCandidate(rec, t2) == "example.org");        // the newest no-press one
    CHECK(P::rowValue((*P::list(rec, t2))[0]) == "Site: Block");
    CHECK(P::rowValue((*P::list(rec, t2))[2]) == "Ad, uBlock");
    P::Blocked got;
    CHECK(P::take(rec, t2, 1, got) && got.url == "https://example.org/real");
    CHECK(P::allowCandidate(rec, t2).empty());
    CHECK(!P::take(rec, t2, 9, got));
    CHECK(P::take(rec, t2, 0, got) && P::take(rec, t2, 0, got) && P::count(rec, t2) == 0);
    CHECK(rec.tabs.count(t2) == 0);                            // emptied list is dropped
    P::forget(rec, t1);
    CHECK(P::count(rec, t1) == 0 && rec.order.empty());
    for (uintptr_t t = 1; t <= P::kMaxTabs + 5; ++t) P::record(rec, t, "https://example.com/", "example.com", P::kGesture);
    CHECK(rec.tabs.size() == P::kMaxTabs && rec.order.size() == P::kMaxTabs);
    CHECK(P::count(rec, 1) == 0 && P::count(rec, P::kMaxTabs + 5) == 1);
    P::record(rec, 6, "https://example.com/again", "example.com", P::kGesture);   // touched: now newest
    for (uintptr_t t = 100; t < 100 + P::kMaxTabs - 1; ++t) P::record(rec, t, "https://example.com/", "example.com", P::kGesture);
    CHECK(P::count(rec, 6) == 2);
    // reopenable
    CHECK(P::reopenable(P::Blocked { "https://example.com/", "example.com", P::kGesture, 1 }));
    CHECK(!P::reopenable(P::Blocked { "about:blank", "example.com", P::kGesture, 1 }));
    CHECK(!P::reopenable(P::Blocked { "", "example.com", P::kGesture, 1 }));
    CHECK(!P::reopenable(P::Blocked { "https://example.com/" + std::string(P::kUrlMax, 'a'), "example.com", P::kGesture, 1 }));

    // texts and the notice window
    CHECK(P::canAllow(P::kGesture) && !P::canAllow(P::kAd) && !P::canAllow(P::kSiteBlock));
    CHECK(std::string(P::openLabel(P::kAd)) == "Open anyway" && std::string(P::openLabel(P::kGesture)) == "Open it");
    CHECK(P::noticeText(P::kAd).find("uBlock") != std::string::npos && P::noticeText(P::kAd).find("Always allow") == std::string::npos);
    CHECK(P::noticeText(P::kGesture).find("Always allow") != std::string::npos);
    CHECK(P::noticeText(P::kSiteBlock).find("Always allow") == std::string::npos);
    CHECK(P::quickLabel(2) == "Blocked pop-ups (2)");
    CHECK(P::allowNotice("example.com", true) == "Pop-ups allowed on example.com (this private session)");
    CHECK(P::allowNotice("example.com", false) == "Pop-ups allowed on example.com");
    const std::string n = P::noticeText(P::kGesture);
    CHECK(P::hintUp(n, n, 9000, 1000));
    CHECK(!P::hintUp(n, n, 9000, 9000));                       // expired
    CHECK(!P::hintUp("Other notice", n, 9000, 1000));          // replaced by another notice
    CHECK(!P::hintUp(n, n, 0, 1000));
    CHECK(!P::hintUp(n, "", 9000, 1000));
    CHECK(P::hintUp(n, n, 5000, 0xFFFFF000u));                  // tick wrap
    CHECK(P::kNoticeMs == 8000);

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
