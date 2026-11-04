// Omni Engine: TLS trust store for WebKit's PlayStation port
// (WebCore/platform/network/playstation/CurlSSLHandlePlayStation.cpp).
// Loads a PEM bundle (Mozilla CA list) shipped with the Omni app.
// SPDX-License-Identifier: BSD-2-Clause
#pragma once
#include <memory>
#include <stddef.h>
#include <stdint.h>
#include <vector>

class CertificateData {
public:
    static std::unique_ptr<CertificateData> create() { return std::unique_ptr<CertificateData>(new CertificateData); }
    const uint8_t* data() const { return m_bytes.data(); }
    size_t size() const { return m_bytes.size(); }
    std::vector<uint8_t>& bytes() { return m_bytes; }

private:
    CertificateData() = default;
    std::vector<uint8_t> m_bytes;
};

namespace CertificateStore {

// Fills `out` with PEM data of trusted root CAs. Search order:
// $OMNI_CA_BUNDLE, /app0/assets/cacert.pem, /data/omni/cacert.pem.
void getTrustedRootCA(CertificateData& out);
const char* cipherSuites();      // OpenSSL cipher list (nullptr-safe: "" = library default)
const char* supportedGroups();   // OpenSSL groups/curves list
bool shouldIgnoreTLSErrors();    // Always false: certificate checks are mandatory.

} // namespace CertificateStore
