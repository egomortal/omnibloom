#!/usr/bin/env python3
"""uBlock link skipping / URL cleaning for top-level navigations.

Applies after patch-ublock-network.py and patch-ublock-site.py. For a
top-level GET navigation (and each server redirect of one), Omni asks the
uBlock engine for uBlock's rewrite (urlskip, removeparam, uritransform). When
there is one, the load ends with error domain "OmniUBlockRedirect" whose
description is the new URL; the browser shell then navigates there. Update
protection, trusted sites and the uBlock on/off switch are respected.
"""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/NetworkProcess/NetworkResourceLoader.cpp'
text = path.read_text()
if '// omni ublock rewrite' not in text:
    anchor = 'extern "C" bool omniUBlockSiteAllowed(const char*); // omni ublock trusted sites\n'
    assert text.count(anchor) == 1, 'run patch-ublock-site.py first'
    text = text.replace(anchor, anchor + '''extern "C" bool omniUBlockRewrite(const char*, const char*, const char*, bool, char*, size_t); // omni ublock rewrite
static String omniRewriteTopLevel(const WebCore::ResourceRequest& request, WebCore::FetchOptions::Destination destination, bool mainFrame, bool blocked)
{
    if (!mainFrame || destination != WebCore::FetchOptions::Destination::Document) return { };
    if (!request.url().protocolIsInHTTPFamily() || request.httpMethod() != "GET"_s) return { };
    auto host = request.url().host().toString().convertToASCIILowercase();
    while (host.endsWith('.')) host = host.left(host.length() - 1);
    if (host == "update.playstation.net"_s || host.endsWith(".update.playstation.net"_s)
        || host == "dl.playstation.net"_s || host.endsWith(".dl.playstation.net"_s)) return { };
    if (omniUBlockSiteAllowed(reinterpret_cast<const char*>(request.firstPartyForCookies().host().toString().utf8().data()))) return { };
    char target[8192];
    if (!omniUBlockRewrite(reinterpret_cast<const char*>(request.url().string().utf8().data()), "", "main_frame", blocked, target, sizeof(target))) return { };
    URL rewritten { String::fromUTF8(target) };
    if (!rewritten.isValid() || !rewritten.protocolIsInHTTPFamily() || rewritten.string() == request.url().string()) return { };
    return rewritten.string();
}
''', 1)

    old = '''    if (omniFilterRequest(newRequest, m_parameters.documentURL, m_parameters.options.destination, isMainFrameLoad())) {
        didFailLoading(WebCore::ResourceError { "OmniUBlock"_s, 1, newRequest.url(), "Blocked by uBlock Origin network filter"_s });
        return;
    }
'''
    assert text.count(old) == 1, 'start() block not found'
    text = text.replace(old, '''    {
        bool omniBlocked = omniFilterRequest(newRequest, m_parameters.documentURL, m_parameters.options.destination, isMainFrameLoad());
        auto omniTarget = omniRewriteTopLevel(newRequest, m_parameters.options.destination, isMainFrameLoad(), omniBlocked);
        if (!omniTarget.isEmpty()) {
            didFailLoading(WebCore::ResourceError { "OmniUBlockRedirect"_s, 3, newRequest.url(), omniTarget });
            return;
        }
        if (omniBlocked) {
            didFailLoading(WebCore::ResourceError { "OmniUBlock"_s, 1, newRequest.url(), "Blocked by uBlock Origin network filter"_s });
            return;
        }
    }
''', 1)

    old = '''    if (omniFilterRequest(redirectRequest, m_parameters.documentURL, m_parameters.options.destination, isMainFrameLoad())) {
        Ref protectedThis { *this };
        didFailLoading(WebCore::ResourceError { "OmniUBlock"_s, 1, redirectRequest.url(), "Redirect blocked by uBlock Origin network filter"_s });
        completionHandler({ });
        return;
    }
'''
    assert text.count(old) == 1, 'redirect block not found'
    text = text.replace(old, '''    {
        bool omniBlocked = omniFilterRequest(redirectRequest, m_parameters.documentURL, m_parameters.options.destination, isMainFrameLoad());
        auto omniTarget = omniRewriteTopLevel(redirectRequest, m_parameters.options.destination, isMainFrameLoad(), omniBlocked);
        if (!omniTarget.isEmpty() || omniBlocked) {
            Ref protectedThis { *this };
            if (!omniTarget.isEmpty())
                didFailLoading(WebCore::ResourceError { "OmniUBlockRedirect"_s, 3, redirectRequest.url(), omniTarget });
            else
                didFailLoading(WebCore::ResourceError { "OmniUBlock"_s, 1, redirectRequest.url(), "Redirect blocked by uBlock Origin network filter"_s });
            completionHandler({ });
            return;
        }
    }
''', 1)
    path.write_text(text)
