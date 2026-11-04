#!/usr/bin/env python3
"""App-local public browsing DNS; keep PlayStation and local hosts on system DNS."""
import pathlib
import sys
def patch_source(s):
    old_policy = '    bool widgetHost = url.protocolIs("https"_s) && url.host() == "www.gstatic.com"_s;'
    v2_policy = '''    // [omni-widget-dns-v2] These five names resolved to 0.0.0.0 on the console.
    bool widgetHost = url.protocolIs("https"_s) && (
        url.host() == "www.gstatic.com"_s
        || url.host() == "youtube.com"_s
        || url.host() == "www.youtube.com"_s
        || url.host() == "m.youtube.com"_s
        || url.host() == "i.ytimg.com"_s);'''
    new_policy = '''    // [omni-browser-dns-v3] Browser-only resolver; no system networking changes.
    auto dnsHost = url.host().toString().convertToASCIILowercase();
    while (dnsHost.endsWith('.')) dnsHost = dnsHost.left(dnsHost.length() - 1);
    auto within = [&](const String& domain) { return dnsHost == domain || dnsHost.endsWith(makeString('.' , domain)); };
    bool systemHost = !dnsHost.contains('.') || within("localhost"_s)
        || within("local"_s) || within("lan"_s)
        || within("playstation.net"_s) || within("playstation.com"_s)
        || within("sony.com"_s) || within("sonyentertainmentnetwork.com"_s);
    bool widgetHost = url.protocolIsInHTTPFamily() && !systemHost;'''
    if '[omni-widget-dns]' in s:
        if '[omni-browser-dns-v3]' in s:
            assert s.count(new_policy) == 1, 'Unexpected existing v2 resolver policy'
        elif '[omni-widget-dns-v2]' in s:
            assert s.count(v2_policy) == 1
            s = s.replace(v2_policy, new_policy, 1)
        else:
            assert s.count(old_policy) == 1, 'Unexpected legacy resolver policy'
            s = s.replace(old_policy, new_policy, 1)
        assert 'CURLOPT_DOH_SSL_VERIFYPEER, 1L' in s
        assert 'CURLOPT_DOH_SSL_VERIFYHOST, 2L' in s
        assert 'if (handle != self->m_handle)' in s, 'Missing DoH TLS callback isolation'
        return s
    anchor = '    if (url.protocolIs("https"_s))\n        enableSSL();'
    assert s.count(anchor) == 1, 'Unexpected curl SSL initialization'
    s = s.replace(anchor, anchor + '''

#if PLATFORM(PLAYSTATION)
    // [omni-widget-dns] App-local, exact-host exception; never change system DNS.
    // Redirects are separate CurlRequests and re-evaluate this condition.
    bool widgetHost = url.protocolIs("https"_s) && url.host() == "www.gstatic.com"_s;
    curl_easy_setopt(m_handle, CURLOPT_DOH_URL, widgetHost ? "https://cloudflare-dns.com/dns-query" : nullptr);
    curl_easy_setopt(m_handle, CURLOPT_DOH_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(m_handle, CURLOPT_DOH_SSL_VERIFYHOST, 2L);
#endif
''', 1)
    anchor = '''CURLcode CurlHandle::willSetupSslCtxCallback(CURL*, void* sslCtx, void* userData)
{
    return static_cast<CurlHandle*>(userData)->willSetupSslCtx(sslCtx);
}'''
    assert s.count(anchor) == 1, 'Unexpected curl SSL callback'
    s = s.replace(anchor, '''CURLcode CurlHandle::willSetupSslCtxCallback(CURL* handle, void* sslCtx, void* userData)
{
    auto* self = static_cast<CurlHandle*>(userData);
    // DoH child transfers inherit this callback. Let libcurl verify their
    // certificates normally without mixing their chains into the page request.
    if (handle != self->m_handle)
        return CURLE_OK;
    return self->willSetupSslCtx(sslCtx);
}''', 1)
    assert s.count(old_policy) == 1
    return s.replace(old_policy, new_policy, 1)

if __name__ == '__main__':
    p = pathlib.Path(sys.argv[1]) / 'Source/WebCore/platform/network/curl/CurlContext.cpp'
    original = p.read_text()
    updated = patch_source(original)
    if updated != original:
        p.write_text(updated)
