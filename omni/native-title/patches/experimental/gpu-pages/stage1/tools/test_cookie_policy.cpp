// OMNI_COOKIE_POLICY_V1: host tests of the pure part (engine/entry/OmniCookiePolicy.h, written by apply_cookie_policy.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_cookie_policy.cpp -o t && ./t
#include "OmniCookiePolicy.h"
#include <cstdio>
#include <string>

namespace OCKP = OmniCookiePolicy;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main()
{
    // WebKit's WKHTTPCookieAcceptPolicy values (WKCookieManager.h); the shell static_asserts the same.
    CHECK(OCKP::kWkAlways == 0 && OCKP::kWkNever == 1 && OCKP::kWkOnlyFromMainDocumentDomain == 2 && OCKP::kWkExclusivelyFromMainDocumentDomain == 3);
    CHECK(OCKP::wkPolicy(OCKP::kAllowAll) == OCKP::kWkAlways);
    CHECK(OCKP::wkPolicy(OCKP::kBlockThirdParty) == OCKP::kWkExclusivelyFromMainDocumentDomain);
    for (int m = 0; m < OCKP::kModes; ++m) CHECK(OCKP::wkPolicy(OCKP::Mode(m)) != OCKP::kWkNever);   // Never stops deletion on Curl

    // file
    CHECK(OCKP::parse("") == OCKP::kAllowAll);
    CHECK(OCKP::parse("cookies=block-third-party") == OCKP::kBlockThirdParty);
    CHECK(OCKP::parse("cookies=block-third-party\r\n") == OCKP::kBlockThirdParty);
    CHECK(OCKP::parse("  cookies = block-third-party  \n") == OCKP::kBlockThirdParty);
    CHECK(OCKP::parse("# cookies=block-third-party\n") == OCKP::kAllowAll);
    CHECK(OCKP::parse("cookies=block-all\n") == OCKP::kAllowAll);              // unknown value: the default
    CHECK(OCKP::parse("cookie=block-third-party\n") == OCKP::kAllowAll);       // unknown key
    CHECK(OCKP::parse("cookies=block-third-party\ncookies=allow-all\n") == OCKP::kAllowAll);   // last valid line wins
    CHECK(OCKP::parse("cookies=block-third-party\ncookies=junk\n") == OCKP::kBlockThirdParty);
    CHECK(OCKP::parse(std::string("cookies=block-third-party\0x", 27)) == OCKP::kAllowAll);   // a NUL in the value: not a known value
    CHECK(OCKP::parse("garbage\n=\n==\ncookies\n") == OCKP::kAllowAll);
    for (int m = 0; m < OCKP::kModes; ++m) {
        const std::string s = OCKP::serialize(OCKP::Mode(m));
        CHECK(OCKP::parse(s) == OCKP::Mode(m));
        CHECK(!s.empty() && s.back() == '\n');
        std::string crlf;
        for (char c : s) { if (c == '\n') crlf += '\r'; crlf += c; }
        CHECK(OCKP::parse(crlf) == OCKP::Mode(m));
    }
    CHECK(long(OCKP::serialize(OCKP::kBlockThirdParty).size()) < OCKP::kMaxFileBytes);
    CHECK(OCKP::clampMode(7) == OCKP::kAllowAll && OCKP::clampMode(-1) == OCKP::kAllowAll && OCKP::clampMode(1) == OCKP::kBlockThirdParty);

    // stepping (Cross / Right next, Left previous; wraps)
    CHECK(OCKP::step(OCKP::kAllowAll, 1) == OCKP::kBlockThirdParty);
    CHECK(OCKP::step(OCKP::kBlockThirdParty, 1) == OCKP::kAllowAll);
    CHECK(OCKP::step(OCKP::kAllowAll, -1) == OCKP::kBlockThirdParty);
    CHECK(OCKP::step(OCKP::kBlockThirdParty, -1) == OCKP::kAllowAll);

    // when the shell sends the policy: fresh sessions start at Always, so Allow all sends nothing there
    CHECK(!OCKP::shouldApply(OCKP::kAllowAll, true));
    CHECK(OCKP::shouldApply(OCKP::kBlockThirdParty, true));
    CHECK(OCKP::shouldApply(OCKP::kAllowAll, false));        // a change back to Allow all must reach WebKit
    CHECK(OCKP::shouldApply(OCKP::kBlockThirdParty, false));

    // texts
    CHECK(std::string(OCKP::name(OCKP::kAllowAll)) == "Allow all");
    CHECK(std::string(OCKP::name(OCKP::kBlockThirdParty)) == "Block third-party");
    for (int m = 0; m < OCKP::kModes; ++m) {
        CHECK(has(OCKP::detail(OCKP::Mode(m)), "sign-ins"));   // the warning is in both subtitles
        CHECK(has(OCKP::detail(OCKP::Mode(m)), "may break"));
        CHECK(OCKP::detail(OCKP::Mode(m)).size() < 200);
    }
    CHECK(has(OCKP::changedNotice(OCKP::kBlockThirdParty, true), "private tabs too"));
    CHECK(!has(OCKP::changedNotice(OCKP::kBlockThirdParty, false), "private"));
    CHECK(has(OCKP::changedNotice(OCKP::kBlockThirdParty, false), "blocked"));
    CHECK(has(OCKP::changedNotice(OCKP::kAllowAll, false), "allowed"));
    for (int m = 0; m < OCKP::kModes; ++m)
        for (const std::string& s : { OCKP::detail(OCKP::Mode(m)), OCKP::changedNotice(OCKP::Mode(m), true) })
            for (unsigned char c : s) CHECK(c >= 0x20 && c < 0x7f);   // the shell font: ASCII only

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
