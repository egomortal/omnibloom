#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""s3.1 OMNI_SEC_PNA_CONNECT_V1 (audit OS-001): WebKit side. Every curl handle WebKit opens for a page gets an opensocket
callback that tags the new socket with the request URL and its first-party (top-level) site; the child engine's connect()
wrap (child-src/omni-sec-connect.cpp) applies the private-network rule to the real peer address with that tag.
Covers CurlRequest (page loads, fetch/XHR, redirects: each hop is a new CurlRequest, downloads) and CurlStream (WebSockets).
argv[1] = the PRIVATE tree (overlay); idempotent (marker); unified diffs go to ../patches-webkit/. Source must match the
reviewed copies in ../webkit-orig/ (sha256) or nothing is written."""
import difflib, hashlib, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; N = HERE.parent
TREE = Path(sys.argv[1]); W = TREE / 'webkit/Source'; D = N / 'patches-webkit'; D.mkdir(exist_ok=True)
MARK = 'OMNI_SEC_PNA_CONNECT_V1'
C = 'WebCore/platform/network/curl/'
EDITS = {
 C + 'CurlContext.h': [
  ('#include <wtf/text/UTF8CStringView.h>\n', '#include <wtf/text/UTF8CStringView.h>\n#include <string>   // OMNI_SEC_PNA_CONNECT_V1\n'),
  ('    void enableConnectionOnly();\n', '    void enableConnectionOnly();\n\n    void setOmniInitiator(const URL& firstParty);   // OMNI_SEC_PNA_CONNECT_V1: the page that started this request\n'),
  ('    std::optional<SSL*> sslConnection() const;\n', '    std::optional<SSL*> sslConnection() const;\n    static curl_socket_t omniOpenSocket(void*, curlsocktype, struct curl_sockaddr*);   // OMNI_SEC_PNA_CONNECT_V1\n'),
  ('    mutable std::unique_ptr<CertificateInfo> m_certificateInfo;\n', '    mutable std::unique_ptr<CertificateInfo> m_certificateInfo;\n    std::string m_omniTarget;      // OMNI_SEC_PNA_CONNECT_V1: request URL and first-party site, handed to the child\'s connect()\n    std::string m_omniInitiator;\n'),
 ],
 C + 'CurlContext.cpp': [
  ('CurlHandle::CurlHandle()\n{\n', '''// OMNI_SEC_PNA_CONNECT_V1 (s3.1, audit OS-001): tag every socket curl opens with its request and first-party site, so the
// child's connect() wrap can apply the private-network rule to the address actually connected to (after DNS). Weak: only
// the child engine links omni-sec-connect.cpp; elsewhere the callback just opens the socket.
extern "C" void omniSecConnectContext(int fd, const char* targetURL, const char* initiatorURL) __attribute__((weak));
static std::string omniText(const URL& url)
{
    auto utf8 = url.string().utf8();
    const char* text = utf8.legacyCStringPointer();
    return text ? std::string(text) : std::string();
}
curl_socket_t CurlHandle::omniOpenSocket(void* data, curlsocktype purpose, struct curl_sockaddr* address)
{
    curl_socket_t fd = ::socket(address->family, address->socktype, address->protocol);
    if (fd != CURL_SOCKET_BAD && purpose == CURLSOCKTYPE_IPCXN && omniSecConnectContext) {
        auto* handle = static_cast<CurlHandle*>(data);
        omniSecConnectContext(fd, handle->m_omniTarget.c_str(), handle->m_omniInitiator.c_str());
    }
    return fd;
}

CurlHandle::CurlHandle()
{
'''),
  ('    curl_easy_setopt(m_handle, CURLOPT_COOKIEFILE, nullptr);\n', '    curl_easy_setopt(m_handle, CURLOPT_COOKIEFILE, nullptr);\n    curl_easy_setopt(m_handle, CURLOPT_OPENSOCKETFUNCTION, omniOpenSocket);   // OMNI_SEC_PNA_CONNECT_V1\n    curl_easy_setopt(m_handle, CURLOPT_OPENSOCKETDATA, this);\n'),
  ('    m_url = url.isolatedCopy();\n', '    m_url = url.isolatedCopy();\n    m_omniTarget = omniText(url);   // OMNI_SEC_PNA_CONNECT_V1\n'),
  ('void CurlHandle::enableConnectionOnly()\n{\n    curl_easy_setopt(m_handle, CURLOPT_CONNECT_ONLY, 1L);\n    curl_easy_setopt(m_handle, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);\n}\n',
   'void CurlHandle::enableConnectionOnly()\n{\n    curl_easy_setopt(m_handle, CURLOPT_CONNECT_ONLY, 1L);\n    curl_easy_setopt(m_handle, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);\n}\n\nvoid CurlHandle::setOmniInitiator(const URL& firstParty)   // OMNI_SEC_PNA_CONNECT_V1\n{\n    m_omniInitiator = omniText(firstParty);\n}\n'),
 ],
 C + 'CurlRequest.cpp': [
  ('    m_curlHandle->setURL(m_request.url(), m_localhostAlias);\n', '    m_curlHandle->setURL(m_request.url(), m_localhostAlias);\n    m_curlHandle->setOmniInitiator(m_request.firstPartyForCookies());   // OMNI_SEC_PNA_CONNECT_V1\n'),
 ],
 C + 'CurlStreamScheduler.h': [
  ('    WEBCORE_EXPORT CurlStreamID createStream(const URL&, CurlStream::Client&, CurlStream::ServerTrustEvaluation, CurlStream::LocalhostAlias);\n',
   '    WEBCORE_EXPORT CurlStreamID createStream(const URL&, CurlStream::Client&, CurlStream::ServerTrustEvaluation, CurlStream::LocalhostAlias, const URL& omniInitiator = { });   // OMNI_SEC_PNA_CONNECT_V1\n'),
 ],
 C + 'CurlStreamScheduler.cpp': [
  ('CurlStreamID CurlStreamScheduler::createStream(const URL& url, CurlStream::Client& client, CurlStream::ServerTrustEvaluation serverTrustEvaluation, CurlStream::LocalhostAlias localhostAlias)\n',
   'CurlStreamID CurlStreamScheduler::createStream(const URL& url, CurlStream::Client& client, CurlStream::ServerTrustEvaluation serverTrustEvaluation, CurlStream::LocalhostAlias localhostAlias, const URL& omniInitiator)   // OMNI_SEC_PNA_CONNECT_V1\n'),
  ('    callOnWorkerThread([this, streamID, url = url.isolatedCopy(), serverTrustEvaluation, localhostAlias]() mutable {\n        m_streamList.add(streamID, CurlStream::create(*this, streamID, WTF::move(url), serverTrustEvaluation, localhostAlias));\n',
   '    callOnWorkerThread([this, streamID, url = url.isolatedCopy(), serverTrustEvaluation, localhostAlias, omniInitiator = omniInitiator.isolatedCopy()]() mutable {\n        m_streamList.add(streamID, CurlStream::create(*this, streamID, WTF::move(url), serverTrustEvaluation, localhostAlias, WTF::move(omniInitiator)));\n'),
 ],
 C + 'CurlStream.h': [
  ('    static std::unique_ptr<CurlStream> create(CurlStreamScheduler& scheduler, CurlStreamID streamID, URL&& url, ServerTrustEvaluation serverTrustEvaluation, LocalhostAlias localhostAlias)\n    {\n        return makeUnique<CurlStream>(scheduler, streamID, WTF::move(url), serverTrustEvaluation, localhostAlias);\n    }\n\n    CurlStream(CurlStreamScheduler&, CurlStreamID, URL&&, ServerTrustEvaluation, LocalhostAlias);\n',
   '    static std::unique_ptr<CurlStream> create(CurlStreamScheduler& scheduler, CurlStreamID streamID, URL&& url, ServerTrustEvaluation serverTrustEvaluation, LocalhostAlias localhostAlias, URL&& omniInitiator = { })   // OMNI_SEC_PNA_CONNECT_V1\n    {\n        return makeUnique<CurlStream>(scheduler, streamID, WTF::move(url), serverTrustEvaluation, localhostAlias, WTF::move(omniInitiator));\n    }\n\n    CurlStream(CurlStreamScheduler&, CurlStreamID, URL&&, ServerTrustEvaluation, LocalhostAlias, URL&& omniInitiator);\n'),
 ],
 C + 'CurlStream.cpp': [
  ('CurlStream::CurlStream(CurlStreamScheduler& scheduler, CurlStreamID streamID, URL&& url, ServerTrustEvaluation serverTrustEvaluation, LocalhostAlias localhostAlias)\n',
   'CurlStream::CurlStream(CurlStreamScheduler& scheduler, CurlStreamID streamID, URL&& url, ServerTrustEvaluation serverTrustEvaluation, LocalhostAlias localhostAlias, URL&& omniInitiator)   // OMNI_SEC_PNA_CONNECT_V1\n'),
  ('    m_curlHandle->setURL(WTF::move(url), localhostAlias);\n', '    m_curlHandle->setURL(WTF::move(url), localhostAlias);\n    m_curlHandle->setOmniInitiator(omniInitiator);   // OMNI_SEC_PNA_CONNECT_V1: WebSockets get the same connect-time rule\n'),
 ],
 'WebKit/NetworkProcess/curl/WebSocketTaskCurl.cpp': [
  ('    m_streamID = m_scheduler.createStream(request.url(), *this, WebCore::CurlStream::ServerTrustEvaluation::Enable, localhostAlias);\n',
   '    m_streamID = m_scheduler.createStream(request.url(), *this, WebCore::CurlStream::ServerTrustEvaluation::Enable, localhostAlias, m_request.firstPartyForCookies());   // OMNI_SEC_PNA_CONNECT_V1\n'),
  ('            m_streamID = m_scheduler.createStream(m_request.url(), *this, WebCore::CurlStream::ServerTrustEvaluation::Disable, localhostAlias);\n',
   '            m_streamID = m_scheduler.createStream(m_request.url(), *this, WebCore::CurlStream::ServerTrustEvaluation::Disable, localhostAlias, m_request.firstPartyForCookies());   // OMNI_SEC_PNA_CONNECT_V1\n'),
 ],
}
REVIEWED = {}
for line in (N / 'webkit-orig/SHA256SUMS.txt').read_text().splitlines():
    h, p = line.split(None, 1); REVIEWED[p.strip()[2:] if p.strip().startswith('./') else p.strip()] = h
plan = []
for rel, edits in EDITS.items():
    path = W / rel
    raw = path.read_bytes(); crlf = b'\r\n' in raw; t = raw.decode('utf-8').replace('\r\n', '\n')
    if MARK in t: print('already patched:', rel); continue
    if hashlib.sha256(raw).hexdigest() != REVIEWED.get(rel): sys.exit(f'BLOCKED: {rel} differs from the reviewed copy in webkit-orig/')
    new = t
    for a, b in edits:
        if new.count(a) != 1: sys.exit(f'BLOCKED: anchor not found once in {rel}: {a[:80]!r}')
        new = new.replace(a, b)
    plan.append((rel, path, t, new, crlf))
for rel, path, t, new, crlf in plan:   # all anchors checked before anything is written
    (D / (Path(rel).name + '.pna.diff')).write_text(''.join(difflib.unified_diff(t.splitlines(True), new.splitlines(True), 'a/' + rel, 'b/' + rel)))
    path.write_bytes((new.replace('\n', '\r\n') if crlf else new).encode('utf-8')); print('patched:', rel)
print('OMNI_SEC_PNA_CONNECT_V1 webkit patch done')
