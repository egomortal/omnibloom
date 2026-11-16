// OMNI_LINK_QR_V1 tests: the pure part of "Show link as QR code" (tools/OmniLinkQr.h).
//   g++ -std=c++20 -Wall -Wextra -I tools [-I <tree>/engine/entry] tools/test_link_qr.cpp -o t && ./t
// With the engine tree on the include path it also checks the cap against the encoder (OmniQr::maxBytes()).
#include "OmniLinkQr.h"
#include <cstdio>
#include <string>
#if __has_include("OmniQrShare.h")
#include "OmniQrShare.h"
#define HAVE_QR 1
#endif

static int fails = 0, runs = 0;
#define CHECK(c) do { ++runs; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniLinkQr;

int main()
{
    // scheme filter: http / https (any case) with a host only
    CHECK(check("https://example.com/a?b=1#c") == Check::Ok);
    CHECK(check("http://example.com") == Check::Ok);
    CHECK(check("HTTPS://Example.com/") == Check::Ok);
    CHECK(check("HtTp://x.y:8080/p") == Check::Ok);
    CHECK(check("https://example.com/user@place") == Check::Ok);        // '@' in the path is not a credential
    CHECK(check("https://example.com/?mail=a@b.c") == Check::Ok);
    CHECK(check("https://[::1]:8080/") == Check::Ok);
    CHECK(check("") == Check::Empty);
    CHECK(check("javascript:alert(1)") == Check::NotWeb);
    CHECK(check("JavaScript:void(0)") == Check::NotWeb);
    CHECK(check("data:text/html,<b>x</b>") == Check::NotWeb);
    CHECK(check("data:image/png;base64,AAAA") == Check::NotWeb);
    CHECK(check("omni://settings") == Check::NotWeb);
    CHECK(check("omni:newtab") == Check::NotWeb);
    CHECK(check("blob:https://example.com/1234") == Check::NotWeb);
    CHECK(check("about:blank") == Check::NotWeb);
    CHECK(check("file:///data/x.html") == Check::NotWeb);
    CHECK(check("mailto:a@b.c") == Check::NotWeb);
    CHECK(check("ftp://example.com/") == Check::NotWeb);
    CHECK(check("httpx://example.com/") == Check::NotWeb);
    CHECK(check("https:example.com") == Check::NotWeb);
    CHECK(check("//example.com/") == Check::NotWeb);
    CHECK(check("/relative/path") == Check::NotWeb);
    CHECK(check(" https://example.com/") == Check::NotWeb);           // leading space: not a normalised href
    CHECK(check("https://exa mple.com/") == Check::NotWeb);
    CHECK(check("https://example.com/\n") == Check::NotWeb);
    CHECK(check(std::string("https://example.com/\x7f")) == Check::NotWeb);
    CHECK(check("http://") == Check::NotWeb);                          // no host
    CHECK(check("https:///path") == Check::NotWeb);
    CHECK(check("https://?q") == Check::NotWeb);
    CHECK(check("https://user:pw@example.com/") == Check::NotWeb);     // credentials never go on the TV
    CHECK(check("https://user@example.com") == Check::NotWeb);
    CHECK(check("https://javascript:alert(1)@x") == Check::NotWeb);
    // UTF-8 (bytes >= 0x80) is allowed: only controls, space and DEL are refused
    CHECK(check("https://example.com/caf\xc3\xa9") == Check::Ok);

    // length cap: exactly kMaxBytes fits, one more does not
    const std::string head = "https://example.com/";
    const std::string at = head + std::string(kMaxBytes - head.size(), 'a');
    CHECK(at.size() == kMaxBytes);
    CHECK(check(at) == Check::Ok);
    CHECK(check(at + "b") == Check::TooLong);
    CHECK(check(head + std::string(5000, 'x')) == Check::TooLong);
    CHECK(check("https://example.com/abc", 20) == Check::TooLong);
    CHECK(check("https://example.com/ab", 22) == Check::Ok);
    CHECK(check("javascript:" + std::string(5000, 'x')) == Check::NotWeb);   // the scheme is refused before the length

    // offered: the row shows for web links, also too-long ones (a notice explains on Cross)
    CHECK(offered("https://example.com/"));
    CHECK(offered(at + "b"));
    CHECK(!offered(""));
    CHECK(!offered("javascript:void(0)"));
    CHECK(!offered("data:,x"));
    CHECK(!offered("omni://home"));
    CHECK(!offered("https://u:p@example.com/"));

    CHECK(kContextId == 977);
#ifdef HAVE_QR
    CHECK(size_t(OmniQr::maxBytes()) == kMaxBytes);                    // the cap is what the encoder holds
    OmniQr::Code code;
    CHECK(OmniQr::encode(at, code) && code.version == OmniQr::kMaxVersion);
    CHECK(!OmniQr::encode(at + "b", code));
    std::printf("checked against OmniQrShare.h\n");
#endif
    std::printf("%d/%d passed\n", runs - fails, runs);
    return fails ? 1 : 0;
}
