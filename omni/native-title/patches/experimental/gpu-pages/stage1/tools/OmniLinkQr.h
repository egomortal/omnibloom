// OMNI_LINK_QR_V1: the pure part of the hold-Cross page menu's "Show link as QR code" (no SDL, no WebKit): which link
// addresses get the row, and the length cap the QR encoder (OmniQrShare.h: byte mode, level M, version 20) can hold.
// Shell side: OmniLinkQrShell.h; reasons in tools/apply_link_qr.py. Tested on the host with g++ (tools/test_link_qr.cpp).
#pragma once
#include <cstddef>
#include <string>

namespace OmniLinkQr {

constexpr int kContextId = 977;        // hold-Cross page menu row (pinned 960, QR 975, text 985, web apps 980/981)
constexpr size_t kMaxBytes = 666;      // OmniQr::maxBytes(): version 20, level M, byte mode (the test checks they agree)

enum class Check { Ok, Empty, NotWeb, TooLong };

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }

// "http://" or "https://" (any case) followed by a host. Everything else (javascript:, data:, blob:, omni:, about:,
// file:, mailto:, relative or scheme-less text) is not a link a phone can open.
inline size_t webSchemeEnd(const std::string& url)
{
    for (const char* p : { "https://", "http://" }) {
        size_t i = 0;
        for (; p[i]; ++i)
            if (i >= url.size() || lower(url[i]) != p[i]) break;
        if (!p[i]) return i;
    }
    return 0;
}

// Not shown on a TV-sized code: addresses with a user / password ("http://user:pw@host/"), control characters,
// spaces or DEL (the page script gives normalised a.href values, so these mean something odd), or no host at all.
inline Check check(const std::string& url, size_t maxBytes = kMaxBytes)
{
    if (url.empty()) return Check::Empty;
    const size_t start = webSchemeEnd(url);
    if (start == 0) return Check::NotWeb;
    for (unsigned char c : url)
        if (c <= 0x20 || c == 0x7F) return Check::NotWeb;
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    if (end == start) return Check::NotWeb;                                    // "https:///path", "http://"
    if (url.find('@', start) < end) return Check::NotWeb;                      // credentials in the authority
    if (url.size() > maxBytes) return Check::TooLong;
    return Check::Ok;
}

// The row is offered for web links; a too-long one still gets the row and a notice on Cross (as "Show QR code").
inline bool offered(const std::string& url)
{
    const Check c = check(url);
    return c == Check::Ok || c == Check::TooLong;
}

} // namespace OmniLinkQr
