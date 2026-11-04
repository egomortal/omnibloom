#!/usr/bin/env python3
"""Invoke Omni's isolated upstream filter engine before loads and redirects."""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/NetworkProcess/NetworkResourceLoader.cpp'
text = path.read_text()
if '// omni upstream ublock bridge' not in text:
    anchor = 'namespace WebKit {\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''
// omni upstream ublock bridge
extern "C" bool omniUBlockShouldBlock(const char*, const char*, const char*);
static bool omniFilterRequest(const WebCore::ResourceRequest& request, const URL& documentURL, WebCore::FetchOptions::Destination destination, bool mainFrame)
{
    if (!request.url().protocolIsInHTTPFamily()) return false;
    const char* type = "other";
    using D = WebCore::FetchOptions::Destination;
    using R = WebCore::ResourceRequestRequester;
    switch (destination) {
    case D::Document: type = mainFrame ? "main_frame" : "sub_frame"; break;
    case D::Iframe: type = "sub_frame"; break;
    case D::Script: case D::Worker: case D::Sharedworker: case D::Serviceworker: type = "script"; break;
    case D::Style: type = "stylesheet"; break;
    case D::Image: type = "image"; break;
    case D::Font: type = "font"; break;
    case D::Audio: case D::Video: case D::Track: type = "media"; break;
    case D::Object: case D::Embed: type = "object"; break;
    default: break;
    }
    switch (request.requester()) {
    case R::XHR: case R::Fetch: case R::EventSource: type = "xmlhttprequest"; break;
    case R::Ping: case R::Beacon: type = "ping"; break;
    default: break;
    }
    const auto& origin = documentURL.isValid() ? documentURL : request.firstPartyForCookies();
    return omniUBlockShouldBlock(reinterpret_cast<const char*>(request.url().string().utf8().data()), reinterpret_cast<const char*>(origin.string().utf8().data()), type);
}
''')
    anchor = '    m_wasStarted = true;\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''
    if (omniFilterRequest(newRequest, m_parameters.documentURL, m_parameters.options.destination, isMainFrameLoad())) {
        didFailLoading(WebCore::ResourceError { "OmniUBlock"_s, 1, newRequest.url(), "Blocked by uBlock Origin network filter"_s });
        return;
    }
''')
    anchor = '    LOADER_RELEASE_LOG("willSendRedirectedRequest:");\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''    if (omniFilterRequest(redirectRequest, m_parameters.documentURL, m_parameters.options.destination, isMainFrameLoad())) {
        Ref protectedThis { *this };
        didFailLoading(WebCore::ResourceError { "OmniUBlock"_s, 1, redirectRequest.url(), "Redirect blocked by uBlock Origin network filter"_s });
        completionHandler({ });
        return;
    }
''')
    path.write_text(text)
text = path.read_text().replace('omniUBlockShouldBlock(request.url().string().utf8().data(), origin.string().utf8().data(), type)', 'omniUBlockShouldBlock(reinterpret_cast<const char*>(request.url().string().utf8().data()), reinterpret_cast<const char*>(origin.string().utf8().data()), type)')
path.write_text(text)
text = path.read_text()
if '// omni independent update protection' not in text:
    anchor = '    if (!request.url().protocolIsInHTTPFamily()) return false;\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''    // omni independent update protection: checked before uBlock's enabled state.
    auto updateHost = request.url().host().toString().convertToASCIILowercase();
    while (updateHost.endsWith('.')) updateHost = updateHost.left(updateHost.length() - 1);
    if (updateHost == "update.playstation.net"_s || updateHost.endsWith(".update.playstation.net"_s)
        || updateHost == "dl.playstation.net"_s || updateHost.endsWith(".dl.playstation.net"_s)) return true;
''', 1)
    path.write_text(text)
