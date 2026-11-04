// Omni Engine: TLS trust store + injected-bundle loader for WebKit's PlayStation port.
// SPDX-License-Identifier: BSD-2-Clause
#include <CertificateStore/CertificateStore.h>
#include <library-bundle.h>

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace CertificateStore {

static bool readFile(const char* path, std::vector<uint8_t>& out)
{
    FILE* f = fopen(path, "rb");
    if (!f)
        return false;
    uint8_t buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
        out.insert(out.end(), buf, buf + n);
    fclose(f);
    return !out.empty();
}

void getTrustedRootCA(CertificateData& out)
{
    const char* candidates[] = {
        getenv("OMNI_CA_BUNDLE"),
        "/app0/assets/cacert.pem",
        "/data/omni/cacert.pem",
        "/etc/ssl/certs/ca-certificates.crt", // host testing
    };
    for (const char* p : candidates) {
        if (p && readFile(p, out.bytes()))
            return;
    }
    fprintf(stderr, "[omni] no CA bundle found; HTTPS will fail verification\n");
}

// Mozilla "intermediate" profile (TLS 1.2 suites; TLS 1.3 suites are OpenSSL defaults).
const char* cipherSuites()
{
    return "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
           "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
           "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
           "DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384";
}

const char* supportedGroups()
{
    return "X25519:P-256:P-384";
}

bool shouldIgnoreTLSErrors()
{
    // Browser builds never bypass certificate or hostname verification.
    return false;
}

} // namespace CertificateStore

LibraryBundle* LibraryBundle::create(const char* path)
{
    if (!path || !*path)
        return nullptr;
    void* h = dlopen(path, RTLD_NOW);
    return h ? new LibraryBundle(h) : nullptr;
}

void* LibraryBundle::resolve(const char* symbol)
{
    return dlsym(m_handle, symbol);
}
