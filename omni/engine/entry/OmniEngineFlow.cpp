// Omni Engine test: page flow (load -> probe JS -> paint -> PNG -> next).
// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniEngineState.h"
#include "OmniPng.h"

#include <WebKit/WKErrorRef.h>
#include <WebKit/WKPagePrivatePlayStation.h>
#include <WebKit/WKRunLoop.h>
#include <WebKit/WKURL.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <thread>
#include <unistd.h>

void omniNotify(const char*);

namespace OmniTest {

static const char* const kUrls[] = {
    "data:text/html,%3C!doctype%20html%3E%3Ctitle%3EOmni%20render%20test%3C/title%3E"
    "%3Cbody%20style='background:%23112233;color:white;font:48px%20sans-serif'%3E"
    "%3Ch1%3EOmni%20render%20test%3C/h1%3E%3Cp%3EHTML%20and%20fonts%3C/p%3E"
    "%3Cdiv%20style='width:320px;height:120px;background:%2333cc88'%3E%3C/div%3E",
    "https://example.com/",
    "https://en.wikipedia.org/wiki/PlayStation_5",
    "https://news.ycombinator.com/",
};
static constexpr int kCount = sizeof(kUrls) / sizeof(kUrls[0]);
static const char* const kTLSUrls[] = {
    "https://sha256.badssl.com/",
    "https://expired.badssl.com/",
    "https://wrong.host.badssl.com/",
    "https://self-signed.badssl.com/",
    "https://example.com/",
};
static bool tlsTest()
{
    static bool enabled = !access("/data/omni/tls-selftest.flag", F_OK);
    return enabled;
}
static int testCount() { return tlsTest() ? 5 : kCount; }
static bool expectsCertificateFailure() { return tlsTest() && state().index >= 1 && state().index <= 3; }

static const char kProbeJS[] =
    "JSON.stringify({title: document.title, links: document.links.length,"
    " images: document.images.length,"
    " text: document.body ? document.body.innerText.length : -1,"
    " height: document.documentElement.scrollHeight,"
    " font: document.body ? getComputedStyle(document.body).fontFamily : '',"
    " glyphW: (function(){var s=document.createElement('span');s.textContent='MMMMMMMMMM';"
    "document.body.appendChild(s);var w=s.getBoundingClientRect().width;s.remove();return w;})(),"
    " ua: navigator.userAgent})";

State& state()
{
    static State s;
    return s;
}

static void finish()
{
    State& S = state();
    logf("SUMMARY %d/%d %s", S.ok, testCount(), tlsTest()
        ? "HTTPS tests passed (valid pages render; invalid certificates rejected)"
        : "pages passed JS and nonuniform PNG checks");
    char msg[160];
    snprintf(msg, sizeof(msg), "Omni Engine: %d/%d checks passed. Results in %s", S.ok, testCount(),
        S.outDir.c_str());
    omniNotify(msg);
    if (S.log)
        fclose(S.log);
    _exit(0); // children exit when their IPC connection closes
}

void advance(int gen)
{
    State& S = state();
    if (gen != S.generation.load())
        return; // already moved on
    S.generation++;
    loadNext();
}

static void paintAndAdvance(void* genPtr)
{
    State& S = state();
    int gen = (int)(intptr_t)genPtr;
    if (gen != S.generation.load())
        return;
    S.pixels.assign((size_t)kW * kH * 4, 0);
    WKPagePaint(S.page, S.pixels.data(), WKSizeMake(kW, kH), WKRectMake(0, 0, kW, kH));
    size_t nonBlank = 0;
    size_t different = 0;
    for (size_t i = 0; i < S.pixels.size(); i += 4) {
        nonBlank += S.pixels[i + 3] != 0;
        different += memcmp(S.pixels.data(), S.pixels.data() + i, 4) != 0;
    }
    char path[256];
    snprintf(path, sizeof(path), "%s/shot-%d.png", S.outDir.c_str(), S.index + 1);
    bool wrote = omniWritePng(path, S.pixels.data(), kW, kH, kW * 4);
    logf("  paint: %zu/%d painted pixels, png %s -> %s", nonBlank, kW * kH,
        wrote ? "written" : "FAILED", path);
    logf("  evidence: js=%s, differing pixels=%zu", S.scriptOK ? "ok" : "failed", different);
    if (wrote && nonBlank && different && S.scriptOK)
        S.ok++;
    advance(gen);
}

static void probeResult(WKTypeRef result, WKErrorRef error, void* genPtr)
{
    if ((int)(intptr_t)genPtr != state().generation.load())
        return;
    if (error) {
        logf("  js: error %s", toStd(adoptWK(WKErrorCopyLocalizedDescription(error)).get()).c_str());
    } else if (result && WKGetTypeID(result) == WKStringGetTypeID()) {
        state().scriptOK = true;
        logf("  js: %s", toStd((WKStringRef)result).c_str());
    } else {
        logf("  js: (non-string result)");
    }
    // give the WebProcess a moment to push the painted backing store
    std::thread([genPtr] {
        usleep(1500 * 1000);
        WKRunLoopCallOnMainThread(paintAndAdvance, genPtr);
    }).detach();
}

void onFinished(int gen)
{
    State& S = state();
    if (expectsCertificateFailure()) {
        logf("SECURITY TEST FAIL: invalid certificate page loaded");
        advance(gen);
        return;
    }
    logf("  loaded in %.1f s", 35.0 - (S.deadline.load() - nowS()));
    auto js = adoptWK(WKStringCreateWithUTF8CString(kProbeJS));
    WKPageEvaluateJavaScriptInMainFrame(S.page, js.get(), (void*)(intptr_t)gen, probeResult);
}

void onFailed(int gen, WKErrorRef error)
{
    if (expectsCertificateFailure()) {
        auto domain = toStd(adoptWK(WKErrorCopyDomain(error)).get());
        int code = WKErrorGetErrorCode(error);
        if (domain == "CurlErrorDomain" && code == 60) {
            logf("CERTIFICATE REJECTION PASS: %s", toStd(adoptWK(WKErrorCopyLocalizedDescription(error)).get()).c_str());
            state().ok++;
        } else logf("SECURITY TEST FAIL: unexpected failure domain=%s code=%d", domain.c_str(), code);
        advance(gen);
        return;
    }
    logf("  FAILED: %s (code %d)",
        toStd(adoptWK(WKErrorCopyLocalizedDescription(error)).get()).c_str(),
        WKErrorGetErrorCode(error));
    advance(gen);
}

static void onTimeout(void* genPtr)
{
    if ((int)(intptr_t)genPtr != state().generation.load())
        return;
    logf("  TIMEOUT after 35 s");
    advance((int)(intptr_t)genPtr);
}

void loadNext()
{
    State& S = state();
    S.index++;
    if (S.index >= testCount())
        finish();
    int gen = S.generation.load();
    S.scriptOK = false;
    const char* address = tlsTest() ? kTLSUrls[S.index] : kUrls[S.index];
    logf("[%d] %s", S.index + 1, address);
    S.deadline = nowS() + 35.0;
    auto url = adoptWK(WKURLCreateWithUTF8CString(address));
    WKPageLoadURL(S.page, url.get());
    std::thread([gen] {
        while (state().generation.load() == gen) {
            if (nowS() > state().deadline.load()) {
                WKRunLoopCallOnMainThread(onTimeout, (void*)(intptr_t)gen);
                return;
            }
            usleep(250 * 1000);
        }
    }).detach();
}

} // namespace OmniTest
