#!/usr/bin/env python3
"""OMNI_FILE_DOWNLOADS_V1 (2026-11-16): a regular file download on a page (PDF, ZIP, image, any
Content-Disposition: attachment or a type WebKit cannot show) is handed to the Downloads app instead of WebKit's own
download.

Where WebKit's navigation-response policy decided "download" (status < 400 and an attachment, or a main-frame
response WebKit can't display), Omni now ignores the response and opens/focuses the Downloads tab with
#url=<file address>, through the same path as the media shortcut (omniMediaDownloadsRequest: worker health check /
start, then the tick opens 127.0.0.1:<port>/downloads#url=...). Pages that display PDFs or images inline are untouched
(that branch is never reached for them). Notice: "Sent to Downloads: <file name>".
Kept on WebKit's own download (unchanged behaviour): private tabs (private links are never shared with Downloads),
non-HTTP(S) or credential-bearing addresses (blob:, data:, user@host), the Downloads tab itself, self-test modes.
With "Media downloads" off, WebKit's own download runs as before (review fix 2026-11-16).
The same address within 3 s (a page that retries the download) is dropped silently.
The Downloads GUI then checks the link (OMNI_FILE_DOWNLOADS_V1 in downloads/worker: probe plain=True) and picks
"Original file", saved by the direct file download (no file type).

Anchors: the everyday navigation client's response policy (OMNI_EVERYDAY_V1), its section comment, and the
OmniMediaDownloadsHooks.inc include (the definition goes after it, so omniMediaDownloadsRequest is declared).
Shares no anchor with apply_media_switch / apply_media_diag / apply_media_http (they edit OmniMediaDownloads.h and
OmniMediaDownloadsHooks.inc only); the notice text "Opening Media downloads..." it keys on is kept by all three.
usage: apply_file_downloads.py <engine tree>   (edits engine/entry/OmniBrowser.cpp; anchored, idempotent, keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_FILE_DOWNLOADS_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniBrowser.cpp'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8').replace('\r\n', '\n')
if MARK in s:
    print('already ' + MARK)
    sys.exit(0)
if 'static void omniMediaDownloadsRequest' not in (p.parent / 'OmniMediaDownloadsHooks.inc').read_text('utf-8', 'replace'):
    sys.exit('OmniMediaDownloadsHooks.inc: omniMediaDownloadsRequest missing')

EDITS = [
    # 1. Response policy: name the page, and hand regular downloads to the Downloads app.
    ('''    nav.decidePolicyForNavigationResponse = [](WKPageRef, WKNavigationResponseRef navigationResponse, WKFramePolicyListenerRef listener, WKTypeRef, const void*) {
        auto response = adoptWK(WKNavigationResponseCopyResponse(navigationResponse));''',
     '''    nav.decidePolicyForNavigationResponse = [](WKPageRef page, WKNavigationResponseRef navigationResponse, WKFramePolicyListenerRef listener, WKTypeRef, const void*) { // ''' + MARK + ''': page named
        auto response = adoptWK(WKNavigationResponseCopyResponse(navigationResponse));'''),
    ('''        if (status < 400 && (attachment || (mainFrame && !WKNavigationResponseCanShowMIMEType(navigationResponse)))) WKFramePolicyListenerDownload(listener);
        else WKFramePolicyListenerUse(listener);''',
     '''        if (status < 400 && (attachment || (mainFrame && !WKNavigationResponseCanShowMIMEType(navigationResponse)))) {
            // ''' + MARK + ''': a regular file goes to the Downloads app; WebKit's own download only where it is not sent.
            if (omniFileDownloadsTake(page, response.get())) WKFramePolicyListenerIgnore(listener);
            else WKFramePolicyListenerDownload(listener);
        } else WKFramePolicyListenerUse(listener);'''),
    # 2. Declaration before the navigation client (the definition needs the media hooks, included later).
    ('''// --- navigation client: user agent per site, downloads, site zoom on commit''',
     '''static bool omniFileDownloadsTake(WKPageRef page, WKURLResponseRef response); // ''' + MARK + '''
// --- navigation client: user agent per site, downloads, site zoom on commit'''),
    # 3. Definition after the media hooks.
    ('''#include "OmniMediaDownloadsHooks.inc" // OMNI_MEDIA_DOWNLOADS_V1
''',
     '''#include "OmniMediaDownloadsHooks.inc" // OMNI_MEDIA_DOWNLOADS_V1
// ''' + MARK + ''': hand a page's regular file download (WebKit chose "download") to the Downloads app, as the media
// shortcut shares a link: the Downloads tab opens or comes forward with #url=<file address>. Returns false where
// WebKit's own download should go on (private tab, not a plain HTTP(S) address, the Downloads tab itself).
static bool omniFileDownloadsTake(WKPageRef page, WKURLResponseRef response)
{
    Tab* tab = omniTabForPage(page);
    if (!tab || !response || omniTestMode() || tab->omniPrivate || tab->omniMediaSection) return false;
    auto url = adoptWK(WKURLResponseCopyURL(response));
    const std::string link = url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();
    if (!OmniMediaSection::validLink(link)) return false;   // http(s) only, no user@host, no spaces, <= 4096
    if (!omniMediaDownloadsEnabled) return false;   // Media downloads off: WebKit's own download, as before (review fix)
    std::string name;
    if (auto suggested = adoptWK(WKURLResponseCopySuggestedFilename(response))) name = OmniTest::toStd(suggested.get());
    if (name.empty()) {
        const size_t end = link.find_first_of("?#", link.find("://") + 3), slash = link.rfind('/', end == std::string::npos ? std::string::npos : end - 1);
        if (slash != std::string::npos) name = link.substr(slash + 1, (end == std::string::npos ? link.size() : end) - slash - 1);
    }
    name = omniSafeFileName(name);
    if (name.size() > 60) name = name.substr(0, 28) + "..." + name.substr(name.size() - 28);
    static std::string lastLink;
    static uint32_t lastAt = 0;
    const uint32_t now = SDL_GetTicks();
    if (link == lastLink && now - lastAt < 3000) return true;   // the page asked again: already handed over
    lastLink = link; lastAt = now;
    omniMediaDownloadsRequest(false, false, true, link);
    if (status == "Opening Media downloads...") notice("Sent to Downloads: " + name);   // accepted (else its own notice stays)
    return true;
}
'''),
]

for old, new in EDITS:
    count = s.count(old)
    if count != 1:
        sys.exit('OmniBrowser.cpp: anchor found %d times: %s' % (count, old.splitlines()[0][:90]))
    s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied ' + MARK)
