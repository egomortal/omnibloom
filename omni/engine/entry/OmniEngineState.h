// Omni Engine test: shared state + helpers. SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <WebKit/WKContext.h>
#include <WebKit/WKPage.h>
#include <WebKit/WKRetainPtr.h>
#include <WebKit/WKString.h>
#include <WebKit/WKView.h>

#include <atomic>
#include <stdarg.h>
#include <stdio.h>
#include <string>
#include <time.h>
#include <vector>

namespace OmniTest {

constexpr int kW = 1280, kH = 720;

struct State {
    WKRetainPtr<WKContextRef> context;
    WKRetainPtr<WKViewRef> view;
    WKPageRef page { nullptr };
    int index { -1 };
    std::atomic<int> generation { 0 };
    std::atomic<double> deadline { 0 };
    int ok { 0 };
    bool scriptOK { false };
    FILE* log { nullptr };
    std::string outDir;
    std::vector<unsigned char> pixels;
};

State& state();

inline double nowS()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

inline void logf(const char* fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    if (state().log) {
        vfprintf(state().log, fmt, ap);
        fputc('\n', state().log);
        fflush(state().log);
    }
    va_end(ap);
}

inline std::string toStd(WKStringRef s)
{
    if (!s)
        return { };
    size_t cap = WKStringGetMaximumUTF8CStringSize(s);
    std::string out(cap, '\0');
    size_t n = WKStringGetUTF8CString(s, out.data(), cap);
    out.resize(n ? n - 1 : 0);
    return out;
}

void loadNext();
void advance(int generation);

} // namespace OmniTest
