// omni-gpu-pages stage 1: the GPU STALL WATCHDOG (OMNI_GPU_WATCHDOG_V1). Timer, decision and flag-file logic only:
// no GPU, EGL, GL, Vulkan or WebKit type, so the host test (stage1/tools/test_gpu_watchdog.cpp) compiles this text.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Why: with layers on, the console was seen to hard-hang 15-45 s after launch (power cycle needed), and the driver's
// own stall line ("radv/ps5: the GPU has not reached submission N in 10 s") never reached the log: whatever kills the
// console does it inside RADV_PS5_STALL_NS. This turns a GPU wait that has been pending for longer than the limit
// (default 1500 ms, /data/omni/gpu-watchdog-ms.txt; 0 or "off" disables) into "layers off for this session":
//
//   - users: the engine child's compositor threads bracket every place they can wait on the GPU (GpuScope: begin/end
//     on a slot, lock-free), and a whole composited frame (kFrame, a looser limit: frameLimitMs);
//   - a watchdog thread (never the UI or main thread) calls Watch::check() every pollMs(); the first overdue slot trips
//     the watch exactly once;
//   - recordTrip() then writes, fsync'd (the console may die seconds later):
//       /data/omni/gpu-pages-stage1-session-off.flag   stage 1 off until the title starts again (sessionStart())
//       /data/omni/gpu-pages/watchdog-trips.txt         today's trips, one line each, other days dropped
//       /data/omni/gpu-pages-stage1-off.flag            ONLY on a second trip the same UTC day, from an EARLIER session: the
//                                                       existing kill switch, so layers stay off across restarts
//       /data/omni/gpu-pages/watchdog-notice.txt        the text the shell shows (taken once by the crash handler)
//     and returns the one clear log line.
// A trip in a session that is already off (several page processes tripping on the same stall) adds no history line:
// one stall never counts as two.
#pragma once
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

namespace OmniGpuWatchdog {

static constexpr int kDefaultMs = 1500, kMinMs = 250, kMaxMs = 10000;
static constexpr int kExitCode = 75;   // the page process's exit status after a trip (EX_TEMPFAIL)

// The text of gpu-watchdog-ms.txt. nullptr (no file), empty or unreadable: the default. "0"/"off": 0 (disabled).
// Anything else is clamped into [kMinMs, kMaxMs].
inline int parseLimitMs(const char* text)
{
    if (!text) return kDefaultMs;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') ++text;
    if (!strncmp(text, "off", 3)) return 0;
    char* end = nullptr;
    errno = 0;
    long v = strtol(text, &end, 10);
    if (end == text || errno) return kDefaultMs;
    if (v == 0) return 0;
    if (v < kMinMs) return kMinMs;
    if (v > kMaxMs) return kMaxMs;
    return static_cast<int>(v);
}
// A whole frame (draw + readback) may legitimately take longer than one GPU wait: a cold Mesa shader cache cost
// ~1.3 s of CPU on the first page frame. Twice the limit, at least 3 s.
inline int frameLimitMs(int limitMs) { return limitMs <= 0 ? 0 : (limitMs * 2 > 3000 ? limitMs * 2 : 3000); }
// How often the watchdog thread looks: a quarter of the limit, 50..250 ms (a trip lands by limit + pollMs).
inline int pollMs(int limitMs) { int p = limitMs / 4; return p < 50 ? 50 : (p > 250 ? 250 : p); }

enum Kind : uint32_t { kWait = 0, kFrame = 1 };
// What a slot waits on (for the log line).
enum What : uint32_t { kWhatReadback = 1, kWhatTileDiff, kWhatAsyncFence, kWhatFrame, kWhatPresent, kWhatOther };
inline const char* whatName(uint32_t what)
{
    switch (what) {
    case kWhatReadback: return "readback (glReadPixels)";
    case kWhatTileDiff: return "tile-diff readback";
    case kWhatAsyncFence: return "async readback fence (glClientWaitSync)";
    case kWhatFrame: return "composited frame (draw + readback)";
    case kWhatPresent: return "title present fence";
    default: return "GPU wait";
    }
}

// Lock-free slots: begin() claims a free one (CAS), end() frees it. Any number of compositor threads write, one
// watchdog thread reads. A full table (more than kSlots waits at once) simply leaves the extra wait unwatched.
struct Watch {
    static constexpr int kSlots = 16;
    std::atomic<uint32_t> busy[kSlots] {};
    std::atomic<double> since[kSlots] {};   // 0: being claimed or freed
    std::atomic<uint32_t> kind[kSlots] {}, what[kSlots] {};
    std::atomic<int> tripped { 0 };

    int begin(Kind k, uint32_t w, double nowMs)
    {
        for (int i = 0; i < kSlots; ++i) {
            uint32_t expect = 0;
            if (busy[i].load(std::memory_order_relaxed) || !busy[i].compare_exchange_strong(expect, 1, std::memory_order_acquire)) continue;
            kind[i].store(k, std::memory_order_relaxed);
            what[i].store(w, std::memory_order_relaxed);
            since[i].store(nowMs > 0 ? nowMs : 1e-3, std::memory_order_release);
            return i;
        }
        return -1;
    }
    void end(int slot)
    {
        if (slot < 0 || slot >= kSlots) return;
        since[slot].store(0, std::memory_order_release);
        busy[slot].store(0, std::memory_order_release);
    }
    // The first slot pending beyond its limit trips the watch (once per process): true, with what it was and for how
    // long. Afterwards always false. limitMs <= 0: never.
    bool check(double nowMs, int limitMs, uint32_t* whatOut, double* pendingOut)
    {
        if (limitMs <= 0 || tripped.load(std::memory_order_relaxed)) return false;
        for (int i = 0; i < kSlots; ++i) {
            if (!busy[i].load(std::memory_order_acquire)) continue;
            const double t = since[i].load(std::memory_order_acquire);
            if (t <= 0) continue;
            const int limit = kind[i].load(std::memory_order_relaxed) == kFrame ? frameLimitMs(limitMs) : limitMs;
            if (nowMs - t <= limit) continue;
            int expect = 0;
            if (!tripped.compare_exchange_strong(expect, 1)) return false;
            if (whatOut) *whatOut = what[i].load(std::memory_order_relaxed);
            if (pendingOut) *pendingOut = nowMs - t;
            return true;
        }
        return false;
    }
};

// ---------------------------------------------------------------------------------------------- the trip decision
// watchdog-trips.txt holds one line per counted trip: "<yyyymmdd> <epoch> <who> <pid>".
// The UTC calendar day of t as yyyymmdd (pure arithmetic, H. Hinnant's civil_from_days: no localtime/tz code is
// pulled into the child, whose symbol gate and the title's import gate both stay small).
inline long dayOf(long long t)
{
    long long z = (t >= 0 ? t : t - 86399) / 86400 + 719468;
    const long long era = (z >= 0 ? z : z - 146096) / 146097;
    const long long doe = z - era * 146097;
    const long long yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const long long doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const long long mp = (5 * doy + 2) / 153;
    const long long d = doy - (153 * mp + 2) / 5 + 1, m = mp < 10 ? mp + 3 : mp - 9, y = yoe + era * 400 + (m <= 2);
    return static_cast<long>(y * 10000 + m * 100 + d);
}
inline int tripsOn(const char* history, long day)
{
    int n = 0;
    for (const char* p = history; p && *p;) {
        char* end = nullptr;
        long d = strtol(p, &end, 10);
        if (end != p && d == day) ++n;
        const char* nl = strchr(p, '\n');
        if (!nl) break;
        p = nl + 1;
    }
    return n;
}
struct Decision {
    bool sameSession { false };   // the session was already off: another page process tripped on the same stall
    bool persist { false };       // second stall today (from an earlier session): the persistent kill switch
    int earlierToday { 0 };
};
inline Decision decide(const char* history, long today, bool sessionAlreadyOff)
{
    Decision d;
    d.sameSession = sessionAlreadyOff;
    d.earlierToday = tripsOn(history, today);
    d.persist = !sessionAlreadyOff && d.earlierToday >= 1;
    return d;
}
// History rewritten with today's lines only (older days dropped), plus the new trip's line when it counts.
inline size_t keepToday(const char* history, long today, char* out, size_t size)
{
    size_t n = 0;
    if (size) out[0] = 0;
    for (const char* p = history; p && *p;) {
        const char* nl = strchr(p, '\n');
        size_t len = nl ? static_cast<size_t>(nl - p) : strlen(p);
        char* end = nullptr;
        long d = strtol(p, &end, 10);
        if (end != p && d == today && n + len + 2 <= size) { memcpy(out + n, p, len); n += len; out[n++] = '\n'; out[n] = 0; }
        if (!nl) break;
        p = nl + 1;
    }
    return n;
}
inline const char* noticeText(const Decision& d)
{
    return d.persist ? "Layers are off: the GPU stalled twice today. Pages draw on the CPU until layers are turned back on."
                     : "Layers are off for this session: the GPU stopped answering. Pages draw on the CPU.";
}
inline int formatLine(char* out, size_t size, const Decision& d, const char* who, int pid, uint32_t what, double pendingMs,
    int limitMs, const char* action)
{
    return snprintf(out, size, "OMNI GPU WATCHDOG: %s pid=%d: %s pending %.0f ms (limit %d ms): layers OFF %s; %s", who, pid,
        whatName(what), pendingMs, what == kWhatFrame ? frameLimitMs(limitMs) : limitMs,
        d.sameSession ? "(this session was already off: same stall, not counted again)"
            : d.persist ? "until /data/omni/gpu-pages-stage1-off.flag is removed (second stall today)"
                        : "for this session (gpu-pages-stage1-session-off.flag; a second stall today makes it permanent)",
        action);
}

// ---------------------------------------------------------------------------------------------- the flag files
// base is "/data/omni" on the console (a temp dir in the host test).
struct Files {
    char session[200], killSwitch[200], history[200], notice[200], dir[200], limit[200];
    explicit Files(const char* base)
    {
        snprintf(session, sizeof session, "%s/gpu-pages-stage1-session-off.flag", base);
        snprintf(killSwitch, sizeof killSwitch, "%s/gpu-pages-stage1-off.flag", base);
        snprintf(dir, sizeof dir, "%s/gpu-pages", base);
        snprintf(history, sizeof history, "%s/gpu-pages/watchdog-trips.txt", base);
        snprintf(notice, sizeof notice, "%s/gpu-pages/watchdog-notice.txt", base);
        snprintf(limit, sizeof limit, "%s/gpu-watchdog-ms.txt", base);
    }
};
inline bool writeDurable(const char* path, const char* text)   // tmp + fsync + rename: whole or absent, even on power loss
{
    char tmp[220];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) return false;
    size_t len = strlen(text), done = 0;
    while (done < len) {
        ssize_t w = write(fd, text + done, len - done);
        if (w <= 0) break;
        done += static_cast<size_t>(w);
    }
    bool ok = done == len && !fsync(fd);
    close(fd);
    ok = ok && !rename(tmp, path);
    if (!ok) unlink(tmp);
    return ok;
}
inline size_t readSmall(const char* path, char* out, size_t size)
{
    if (!size) return 0;
    out[0] = 0;
    int fd = open(path, O_RDONLY);
    if (fd < 0) return 0;
    ssize_t n = read(fd, out, size - 1);
    close(fd);
    if (n < 0) n = 0;
    out[n] = 0;
    return static_cast<size_t>(n);
}
// The limit for this process, read once by the caller (0: watchdog off).
inline int readLimitMs(const char* base)
{
    Files f(base);
    char text[32];
    if (access(f.limit, F_OK)) return kDefaultMs;
    readSmall(f.limit, text, sizeof text);
    return parseLimitMs(text);
}
inline bool sessionOff(const char* base) { Files f(base); return !access(f.session, F_OK); }
// The title's start: "layers off" from a stall lasts one title session. (Today's history stays: it decides the 2nd.)
inline void sessionStart(const char* base)
{
    Files f(base);
    unlink(f.session);
    unlink(f.notice);
}
// Takes the notice once (the shell's crash handler). false: there is none.
inline bool takeNotice(const char* base, char* out, size_t size)
{
    Files f(base);
    if (access(f.notice, F_OK)) return false;
    readSmall(f.notice, out, size);
    unlink(f.notice);
    size_t n = strlen(out);
    while (n && (out[n - 1] == '\n' || out[n - 1] == '\r')) out[--n] = 0;
    return n > 0;
}
// The trip: decide, write the files (fsync'd), and format the one log line into line. Never blocks on the GPU.
inline Decision recordTrip(const char* base, long today, long long epoch, const char* who, int pid, uint32_t what, double pendingMs,
    int limitMs, const char* action, char* line, size_t lineSize)
{
    Files f(base);
    mkdir(base, 0777);
    mkdir(f.dir, 0777);
    char history[4096], kept[4096];
    readSmall(f.history, history, sizeof history);
    Decision d = decide(history, today, !access(f.session, F_OK));
    if (!d.sameSession) {
        size_t n = keepToday(history, today, kept, sizeof kept);
        snprintf(kept + n, sizeof kept - n, "%ld %lld %s %d\n", today, epoch, who, pid);
        writeDurable(f.history, kept);
        writeDurable(f.session, "OMNI_GPU_WATCHDOG_V1: a GPU stall turned layers off until the title starts again\n");
        if (d.persist) {
            char text[200];
            snprintf(text, sizeof text, "OMNI_GPU_WATCHDOG_V1: written on %ld after a second GPU stall that day; remove to turn layers back on\n", today);
            writeDurable(f.killSwitch, text);
        }
        char notice[300];
        snprintf(notice, sizeof notice, "%s\n", noticeText(d));
        writeDurable(f.notice, notice);
    }
    formatLine(line, lineSize, d, who, pid, what, pendingMs, limitMs, action);
    return d;
}

} // namespace OmniGpuWatchdog
