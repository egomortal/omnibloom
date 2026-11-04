// OMNI_AUDIO_RELAY_V1: see OmniAudioRelay.h. SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniAudioRelay.h"
#include "OmniHwPlatform.h"
#include "OmniHwProtocol.h"
#include "OmniHwService.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <fcntl.h>
#include <functional>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <poll.h>
#include <pthread.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

namespace OmniMedia::Audio {
using Hw::Wire::Message;
using Hw::Wire::Type;

bool relayFlagEnabled()
{
    if (const char* env = getenv("OMNI_AUDIO_RELAY")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/audio-relay-disabled.flag", F_OK) != 0;
#else
    return false;
#endif
}

namespace {
constexpr uint32_t relayMagic = 0x4f4d4155;   // "OMAU": the relay's channels (Hw::Wire::Message layout)
constexpr uint32_t relayVersion = 1;
constexpr uint32_t relaySlots = 6;            // players with audio at once
constexpr size_t ringFrames = 48000 * 7 / 2;  // 3.5 s, as the in-process ring
constexpr int helloTimeoutMs = 1500;
// Message use (relay channels): Hello a=pid b=channel generation c=relayVersion;
// HelloAck status (0, or -2 no audio device; text) a=shm fd (in the relay) b=shm bytes
// c=ring frames d=device frames; ShmMapped (client mapped it); Close.

std::string relayDir() { return Hw::rendezvousDir(); }

void relayNote(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void relayNote(const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "OMNI AUDIO RELAY: ");
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr); fflush(stderr);
    va_end(ap);
}

// ---- UI process ------------------------------------------------------------------------------
struct Slot {
    int index = 0;
    uint32_t generation = 0;
    int serverFd = -1, clientFd = -1, shmFd = -1;
    bool connected = false;
    uint8_t* shm = nullptr;
    size_t shmSize = 0;
    AudioRing* ring = nullptr;   // consumer view, while mixed
    unsigned pid = 0;
    double claimSince = 0;
    Message partial;
    size_t partialLen = 0;
};
Slot slots[relaySlots];
std::string dir;
std::atomic<bool> running { false }, threadDone { true };
pthread_t thread;
SDL_AudioDeviceID device = 0;          // relay thread (and start/stop)
std::atomic<bool> deviceOpen { false }; // for relayStats
SDL_AudioSpec deviceSpec {};
double lastOpenAttemptMs = 0;
bool initialisedAudio = false;
// The callback's view: rings it mixes. Changed only with the device locked (or before it opens).
AudioRing* mixed[relaySlots] = {};
std::vector<int32_t> accumulator;
std::vector<int16_t> scratch;
std::atomic<uint64_t> framesMixed { 0 }, callbacks { 0 };
std::atomic<int> mixPeak { 0 };
std::atomic<bool> hudEnabled {false};
std::atomic<int64_t> hudUnderruns {-1};
void publishHud(double now) {
    static double next=0;
    if (!hudEnabled.load(std::memory_order_relaxed) || now<next) return;
    next=now+1000;
    // Relay thread owns slots/ring lifetime; ring counters are already atomic.
    int64_t total=0; bool any=false;
    for (const auto& s:slots) if (s.ring) { any=true; total+=s.ring->underruns(); }
    hudUnderruns.store(any?total:-1,std::memory_order_relaxed);
}

std::atomic<unsigned> ringsPlaying { 0 }, ringsMixed { 0 };
// OMNI_AUDIO_CAPTURE_V1 (diagnostic, off unless /data/omni/audio-capture.flag at relay start): the
// first 30 s of mixed output while a page plays, exactly as sent to the device, written once to
// /data/omni/audio-capture.raw (48 kHz stereo s16le) by the relay thread when full or when playback
// stops. The audio thread only copies into a buffer reserved up front.
constexpr size_t captureFrameLimit = 48000 * 30;
std::vector<int16_t> captureBuffer;
std::atomic<size_t> captureFrames { 0 };
bool captureWritten = false;

void mix(void*, Uint8* stream, int len)   // SDL's audio thread
{
    int16_t* out = reinterpret_cast<int16_t*>(stream);
    size_t frames = size_t(len > 0 ? len : 0) / (AudioRing::channels * sizeof(int16_t));
    const size_t chunk = scratch.size() / AudioRing::channels;
    if (!chunk) { memset(stream, 0, size_t(len > 0 ? len : 0)); return; }
    unsigned playing = 0;
    int peak = 0;
    for (auto* ring : mixed) if (ring) { ring->consumerBeat(deviceSpec.samples); ring->applyClear(); }
    while (frames) {
        const size_t n = std::min(frames, chunk);
        std::fill(accumulator.begin(), accumulator.begin() + long(n * AudioRing::channels), 0);
        playing = 0;
        for (auto* ring : mixed) {
            if (!ring || !ring->playingSet()) continue;
            ++playing;
            const auto beforeUnderruns = ring->underruns();
            const auto beforeFill = ring->fillFrames();
            AudioRing::deviceCallback(ring, reinterpret_cast<uint8_t*>(scratch.data()), int(n * AudioRing::channels * sizeof(int16_t)));
            const auto afterUnderruns = ring->underruns();
            // Trace only: exact callback that increased the underrun counter.
            if (afterUnderruns != beforeUnderruns)
                Hw::diagnosticTrace(80, afterUnderruns - beforeUnderruns, beforeFill, n, reinterpret_cast<intptr_t>(ring));
            for (size_t i = 0; i < n * AudioRing::channels; i++) accumulator[i] += scratch[i];
        }
        for (size_t i = 0; i < n * AudioRing::channels; i++) {
            const int32_t v = std::clamp<int32_t>(accumulator[i], -32768, 32767);
            out[i] = int16_t(v);
            peak = std::max(peak, std::abs(int(v)));
        }
        if (playing && !captureBuffer.empty()) { // OMNI_AUDIO_CAPTURE_V1
            const size_t at = captureFrames.load(std::memory_order_relaxed), take = std::min(n, captureFrameLimit - at);
            if (take) { memcpy(captureBuffer.data() + at * AudioRing::channels, out, take * AudioRing::channels * sizeof(int16_t)); captureFrames.store(at + take, std::memory_order_release); }
        }
        out += n * AudioRing::channels; frames -= n;
    }
    if (len % int(AudioRing::channels * sizeof(int16_t))) memset(stream + len - len % int(AudioRing::channels * sizeof(int16_t)), 0, size_t(len % int(AudioRing::channels * sizeof(int16_t))));
    if (peak > mixPeak.load(std::memory_order_relaxed)) mixPeak.store(peak, std::memory_order_relaxed);
    framesMixed.fetch_add(size_t(len > 0 ? len : 0) / (AudioRing::channels * sizeof(int16_t)), std::memory_order_relaxed);
    callbacks.fetch_add(1, std::memory_order_relaxed);
    ringsPlaying.store(playing, std::memory_order_relaxed);
}

// The device stays open from the first success to the end (a port reopened right after it was
// closed can fail with 0x80260002 for seconds).
bool openDevice()
{
    if (device) return true;
    if (captureBuffer.empty() && !access("/data/omni/audio-capture.flag", F_OK)) captureBuffer.assign(captureFrameLimit * AudioRing::channels, 0); // OMNI_AUDIO_CAPTURE_V1 (before the callback can run)
    lastOpenAttemptMs = Hw::nowMs();
    SDL_SetMainReady();
    if (!SDL_WasInit(SDL_INIT_AUDIO)) {
        if (SDL_InitSubSystem(SDL_INIT_AUDIO)) { relayNote("audio init failed (%s); players keep their own output", SDL_GetError()); return false; }
        initialisedAudio = true;
    }
    SDL_AudioSpec wanted {}, actual {};
    wanted.freq = 48000; wanted.format = AUDIO_S16LSB; wanted.channels = 2; wanted.samples = 1024;
    wanted.callback = mix;
    deviceSpec = wanted;   // the callback's buffers follow (no changes allowed: SDL converts)
    scratch.assign(size_t(wanted.samples) * AudioRing::channels, 0);
    accumulator.assign(scratch.size(), 0);
    device = SDL_OpenAudioDevice(nullptr, 0, &wanted, &actual, 0);
    if (!device) { relayNote("device open failed (%s); players keep their own output", SDL_GetError()); return false; }
    deviceSpec = actual;
    relayNote("device open in pid %d: driver=%s device=%u obtained freq=%d format=0x%04x channels=%u samples=%u size=%u (players' rings mixed here)",
        int(getpid()), SDL_GetCurrentAudioDriver() ? SDL_GetCurrentAudioDriver() : "?", unsigned(device), actual.freq, unsigned(actual.format),
        unsigned(actual.channels), unsigned(actual.samples), unsigned(actual.size));
    SDL_PauseAudioDevice(device, 0);   // silence until a ring plays
    deviceOpen = true;
    return true;
}

void withDeviceLocked(const std::function<void()>& change)
{
    if (device) SDL_LockAudioDevice(device);
    change();
    if (device) SDL_UnlockAudioDevice(device);
}

bool sendRelay(int fd, const Message& m)
{
    const char* p = reinterpret_cast<const char*>(&m);
    size_t left = sizeof m;
    const double deadline = Hw::nowMs() + 200;
    while (left) {
        ssize_t n = send(fd, p, left, MSG_DONTWAIT);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            pollfd pfd { fd, POLLOUT, 0 };
            const int wait = int(deadline - Hw::nowMs());
            if (wait > 0 && poll(&pfd, 1, wait) >= 0) continue;
            return false;
        }
        if (n <= 0) return false;
        p += n; left -= size_t(n);
    }
    return true;
}

void writeRendezvous()
{
    std::string text = "omni-audio 1\npid " + std::to_string(getpid()) + "\n";
    for (auto& s : slots) text += "channel " + std::to_string(s.index) + " " + std::to_string(s.generation) + " " + std::to_string(s.clientFd) + "\n";
    const std::string tmp = dir + "/audio.tmp", path = dir + "/audio";
    FILE* f = fopen(tmp.c_str(), "w");
    if (!f) return;
    fputs(text.c_str(), f); fflush(f); fsync(fileno(f)); fclose(f);
    rename(tmp.c_str(), path.c_str());
}

void dropRing(Slot& s)
{
    if (s.ring) {
        AudioRing* ring = s.ring;
        withDeviceLocked([&] { for (auto*& m : mixed) if (m == ring) m = nullptr; });
        delete ring; s.ring = nullptr;
        ringsMixed.fetch_sub(1);
    }
    if (s.shm) { munmap(s.shm, s.shmSize); s.shm = nullptr; s.shmSize = 0; }
    if (s.shmFd >= 0) { close(s.shmFd); s.shmFd = -1; }
}

bool resetSlot(Slot& s)
{
    dropRing(s);
    if (s.serverFd >= 0) close(s.serverFd);
    if (s.clientFd >= 0) close(s.clientFd);
    s.serverFd = s.clientFd = -1; s.connected = false; s.pid = 0; s.partialLen = 0; s.claimSince = 0;
    int sv[2];
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sv)) { relayNote("socketpair failed errno=%d", errno); return false; }
    s.serverFd = sv[0]; s.clientFd = sv[1];
    s.generation++;
    unlink((dir + "/audio-claim-" + std::to_string(s.index)).c_str());
    return true;
}

void handle(Slot& s, const Message& in, bool& rewrite)
{
    switch (in.type) {
    case Type::Hello: {
        Message ack; ack.magic = relayMagic; ack.type = Type::HelloAck;
        if (in.b != s.generation || in.c != relayVersion) { ack.status = -1; snprintf(ack.text, sizeof ack.text, "generation/version"); sendRelay(s.serverFd, ack); break; }
        if (!device && Hw::nowMs() - lastOpenAttemptMs >= 2000) openDevice();
        if (!device) { ack.status = -2; snprintf(ack.text, sizeof ack.text, "no audio device in the UI process"); sendRelay(s.serverFd, ack); break; }
        const size_t bytes = AudioRing::sharedBytes(ringFrames);
        s.shmFd = Hw::shmCreate(bytes);
        void* p = s.shmFd >= 0 ? mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_SHARED, s.shmFd, 0) : MAP_FAILED;
        if (p == MAP_FAILED) {
            if (s.shmFd >= 0) { close(s.shmFd); s.shmFd = -1; }
            ack.status = -3; snprintf(ack.text, sizeof ack.text, "shared memory"); sendRelay(s.serverFd, ack); break;
        }
        s.shm = static_cast<uint8_t*>(p); s.shmSize = bytes;
        AudioRing::initShared(s.shm, ringFrames)->deviceFrames.store(deviceSpec.samples);
        ack.a = uint32_t(s.shmFd); ack.b = uint32_t(bytes); ack.c = uint32_t(ringFrames); ack.d = deviceSpec.samples;
        snprintf(ack.text, sizeof ack.text, "ok");
        s.connected = sendRelay(s.serverFd, ack);
        s.pid = in.a;
        // The client holds its own copy of the socket now: ours goes, so its exit is EOF here.
        if (s.connected && s.clientFd >= 0) { close(s.clientFd); s.clientFd = -1; rewrite = true; }
        break;
    }
    case Type::ShmMapped:
        if (s.shmFd >= 0) { close(s.shmFd); s.shmFd = -1; }
        if (s.shm && !s.ring) {
            auto* ring = new AudioRing(s.shm, false);
            withDeviceLocked([&] { mixed[s.index] = ring; });
            s.ring = ring;
            ringsMixed.fetch_add(1);
            relayNote("channel %d: player in pid %u mixed (%u frames of ring)", s.index, s.pid, unsigned(ringFrames));
        }
        break;
    case Type::Close:
        dropRing(s);
        break;
    default:
        break;
    }
}

void logTick(double now, double& windowMs, uint64_t& windowFrames, unsigned& lines)
{
    if (!captureBuffer.empty() && !captureWritten) { // OMNI_AUDIO_CAPTURE_V1: full, or playback stopped after some audio
        const size_t have = captureFrames.load(std::memory_order_acquire);
        if (have >= captureFrameLimit || (have >= 48000 * 5 && !ringsPlaying.load())) {
            captureWritten = true;
            if (FILE* f = fopen("/data/omni/audio-capture.raw", "wb")) { fwrite(captureBuffer.data(), sizeof(int16_t), have * AudioRing::channels, f); fclose(f); }
            relayNote("capture: wrote %zu frames (%.1f s) to /data/omni/audio-capture.raw", have, have / 48000.0);
        }
    }
    if (now - windowMs < (lines < 24 ? 5000 : 60000)) return;
    unsigned rings = 0;
    uint64_t underruns = 0;
    for (auto& s : slots) if (s.ring) { ++rings; underruns += s.ring->underruns(); }
    const uint64_t frames = framesMixed.load();
    const int peak = mixPeak.exchange(0);
    if (rings || peak) {   // quiet while no page plays (the device itself runs on, mixing silence)
        relayNote("%.1f s: rings=%u playing=%u framesPlayed=%llu (%.0f ms) peak=%d underruns=%llu device=%s",
            (now - windowMs) / 1000, rings, ringsPlaying.load(), static_cast<unsigned long long>(frames - windowFrames),
            double(frames - windowFrames) / 48.0, peak, static_cast<unsigned long long>(underruns), device ? "open" : "none");
        ++lines;
    }
    windowMs = now; windowFrames = frames;
}

void* relayMain(void*)
{
    double windowMs = Hw::nowMs();
    uint64_t windowFrames = framesMixed.load();
    unsigned lines = 0;
    while (running.load()) {
        pollfd fds[relaySlots];
        for (uint32_t i = 0; i < relaySlots; i++) fds[i] = { slots[i].serverFd, POLLIN, 0 };
        int n = poll(fds, relaySlots, 250);
        if (n < 0 && errno != EINTR) break;
        bool rewrite = false;
        for (uint32_t i = 0; i < relaySlots; i++) {
            Slot& s = slots[i];
            for (int burst = 0; burst < 16 && (fds[i].revents & (POLLIN | POLLHUP | POLLERR)); burst++) {
                char* p = reinterpret_cast<char*>(&s.partial) + s.partialLen;
                ssize_t got = recv(s.serverFd, p, sizeof(Message) - s.partialLen, burst ? MSG_DONTWAIT : 0);
                if (got < 0 && burst && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) break;
                if (got <= 0) {   // the player's process closed it or is gone: drop its ring
                    if (s.connected) relayNote("channel %d: player in pid %u left", s.index, s.pid);
                    resetSlot(s); rewrite = true;
                    break;
                }
                s.partialLen += size_t(got);
                if (s.partialLen == sizeof(Message)) {
                    s.partialLen = 0;
                    if (s.partial.magic == relayMagic) handle(s, s.partial, rewrite);
                }
            }
            if (!s.connected) {   // a claim that never says Hello (its process died mid-connect)
                const bool claimed = !access((dir + "/audio-claim-" + std::to_string(i)).c_str(), F_OK);
                if (!claimed) s.claimSince = 0;
                else if (!s.claimSince) s.claimSince = Hw::nowMs();
                else if (Hw::nowMs() - s.claimSince > 5000) { relayNote("channel %d: stale claim", s.index); resetSlot(s); rewrite = true; }
            }
        }
        if (rewrite) writeRendezvous();
        const double relayNow=Hw::nowMs(); // reuse the existing timestamp
        publishHud(relayNow);
        logTick(relayNow, windowMs, windowFrames, lines);
    }
    threadDone = true;
    return nullptr;
}
}

bool relayStart(std::string& detail)
{
    if (running.load()) { detail = "already running"; return true; }
    dir = relayDir();
    Hw::ensureDir(dir);
    unlink((dir + "/audio").c_str());
    for (uint32_t i = 0; i < relaySlots; i++) {
        slots[i].index = int(i);
        if (!resetSlot(slots[i])) { detail = "socketpair"; return false; }
    }
    openDevice();   // here, on the main thread before the shell's SDL calls; retried on demand otherwise
    writeRendezvous();
    running = true; threadDone = false;
    pthread_attr_t attr; pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 256 * 1024);
    const int e = pthread_create(&thread, &attr, relayMain, nullptr);
    pthread_attr_destroy(&attr);
    if (e) { running = false; threadDone = true; detail = "pthread_create"; return false; }
    detail = "running in pid " + std::to_string(getpid()) + (device ? ", device open" : ", no device yet");
    relayNote("%s, %u channels, rendezvous %s/audio", detail.c_str(), relaySlots, dir.c_str());
    return true;
}

void relayStop(bool fromSignal)
{
    static std::atomic<bool> stopped { false };
    if (!running.load() || stopped.exchange(true)) return;
    running = false;
    if (fromSignal) return;   // nothing that can block or lock from a signal handler
    for (int waited = 0; !threadDone.load() && waited < 1000; waited += 10) usleep(10000);
    if (threadDone.load()) pthread_join(thread, nullptr);
    unlink((dir + "/audio").c_str());
    // SDL_Quit (the shell's exit) closes the device itself; only close it while SDL audio is up.
    const bool sdlUp = SDL_WasInit(SDL_INIT_AUDIO) != 0;
    if (device && sdlUp) { SDL_CloseAudioDevice(device); relayNote("device closed"); }
    device = 0; deviceOpen = false;
    for (auto& s : slots) {
        dropRing(s);   // the device is closed: no callback runs
        if (s.serverFd >= 0) close(s.serverFd);
        if (s.clientFd >= 0) close(s.clientFd);
        s.serverFd = s.clientFd = -1;
        unlink((dir + "/audio-claim-" + std::to_string(s.index)).c_str());
    }
    if (initialisedAudio && sdlUp) SDL_QuitSubSystem(SDL_INIT_AUDIO);
    initialisedAudio = false;
}

void relayHudEnable(bool enabled) { hudEnabled.store(enabled,std::memory_order_relaxed); }
int64_t relayHudUnderruns() { return hudUnderruns.load(std::memory_order_relaxed); }

RelayStats relayStats()
{
    RelayStats st;
    st.running = running.load(); st.deviceOpen = deviceOpen.load();
    st.rings = ringsMixed.load();
    st.playing = ringsPlaying.load(); st.framesMixed = framesMixed.load(); st.callbacks = callbacks.load();
    return st;
}

// ---- WebProcess ------------------------------------------------------------------------------
namespace {
bool recvMessage(int fd, Message& out, int timeoutMs)
{
    char* p = reinterpret_cast<char*>(&out);
    size_t got = 0;
    const double deadline = Hw::nowMs() + timeoutMs;
    while (got < sizeof out) {
        pollfd pfd { fd, POLLIN, 0 };
        const int wait = int(deadline - Hw::nowMs());
        if (wait <= 0 || poll(&pfd, 1, wait) <= 0) return false;
        ssize_t n = recv(fd, p + got, sizeof out - got, MSG_DONTWAIT);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return false;
        got += size_t(n);
    }
    return out.magic == relayMagic;
}
}

std::unique_ptr<Output> Output::openRelay(std::string& why)
{
    if (!relayFlagEnabled()) { why = "disabled"; return nullptr; }
    // A channel another player just closed is free again within one relay loop (250 ms): wait for
    // it rather than fall back at once (another page's player ended as this one starts).
    for (const double end = Hw::nowMs() + 600;;) {
        bool recycling = false;
        if (auto out = tryOpenRelay(why, recycling)) return out;
        if (!recycling || why == "no audio device in the UI process" || Hw::nowMs() > end) return nullptr;
        usleep(20000);
    }
}

std::unique_ptr<Output> Output::tryOpenRelay(std::string& why, bool& recycling)
{
    const std::string d = relayDir();
    FILE* f = fopen((d + "/audio").c_str(), "r");
    if (!f) { why = "no relay (UI process)"; return nullptr; }
    char line[128]; long pid = 0;
    struct Entry { int index; unsigned gen; int fd; };
    std::vector<Entry> entries;
    while (fgets(line, sizeof line, f)) {
        int i, fd; unsigned gen;
        if (sscanf(line, "pid %ld", &pid) == 1) continue;
        if (sscanf(line, "channel %d %u %d", &i, &gen, &fd) == 3) {
            if (fd >= 0) entries.push_back({ i, gen, fd });
            else recycling = true;   // in use, or closed and not yet made new
        }
    }
    fclose(f);
    if (pid <= 0) { why = "bad rendezvous"; return nullptr; }
    why = entries.empty() ? "all relay channels in use" : "no relay channel answered";
    for (auto& e : entries) {
        const std::string claim = d + "/audio-claim-" + std::to_string(e.index);
        int c = open(claim.c_str(), O_CREAT | O_EXCL | O_WRONLY, 0644);
        if (c < 0) continue;
        close(c);
        int fd = omni_remote_dup(pid_t(pid), e.fd);
        if (fd < 0) { unlink(claim.c_str()); continue; }
        Message hello; hello.magic = relayMagic; hello.type = Type::Hello;
        hello.a = uint32_t(getpid()); hello.b = e.gen; hello.c = relayVersion;
        Message ack;
        const bool sent = send(fd, &hello, sizeof hello, MSG_DONTWAIT) == ssize_t(sizeof hello);
        if (!sent || !recvMessage(fd, ack, helloTimeoutMs) || ack.type != Type::HelloAck) { close(fd); unlink(claim.c_str()); continue; }
        if (ack.status) {   // the relay has no device: the player keeps its own output
            why = ack.text[0] ? std::string(ack.text, strnlen(ack.text, sizeof ack.text)) : "refused";
            close(fd); unlink(claim.c_str());
            return nullptr;
        }
        int shmFd = omni_remote_dup(pid_t(pid), int(ack.a));
        void* p = shmFd >= 0 ? mmap(nullptr, ack.b, PROT_READ | PROT_WRITE, MAP_SHARED, shmFd, 0) : MAP_FAILED;
        if (shmFd >= 0) close(shmFd);
        if (p == MAP_FAILED || !AudioRing::validShared(p, ack.b)) {
            if (p != MAP_FAILED) munmap(p, ack.b);
            why = "relay ring not mappable"; close(fd); return nullptr;   // the relay drops it at EOF
        }
        Message mapped; mapped.magic = relayMagic; mapped.type = Type::ShmMapped;
        if (send(fd, &mapped, sizeof mapped, MSG_DONTWAIT) != ssize_t(sizeof mapped)) { munmap(p, ack.b); close(fd); why = "relay not reading"; return nullptr; }
        std::unique_ptr<Output> out(new Output());
        out->relayFd_ = fd; out->channel_ = e.index; out->shm_ = p; out->shmSize_ = ack.b;
        out->view_ = std::make_unique<AudioRing>(p, true);
        out->deviceFrames_ = ack.d ? ack.d : 1024;
        out->view_->setPlaying(false);
        return out;
    }
    return nullptr;
}

std::unique_ptr<Output> Output::openSdl(const SDL_AudioSpec* wanted, SDL_AudioSpec* actual)
{
    SDL_AudioSpec want = *wanted;
    const SDL_AudioDeviceID id = SDL_OpenAudioDevice(nullptr, 0, &want, actual, 0);
    if (!id) return nullptr;
    std::unique_ptr<Output> out(new Output());
    out->sdl_ = id;
    out->deviceFrames_ = actual->samples ? actual->samples : 1024;
    return out;
}

Output::~Output()
{
    if (sdl_) { SDL_CloseAudioDevice(sdl_); sdl_ = 0; }
    if (relayFd_ >= 0) {
        if (view_) view_->setPlaying(false);
        Message m; m.magic = relayMagic; m.type = Type::Close;
        (void)!send(relayFd_, &m, sizeof m, MSG_DONTWAIT);   // or EOF: the relay drops the ring either way
        close(relayFd_); relayFd_ = -1;
    }
    view_.reset();
    if (shm_) { munmap(shm_, shmSize_); shm_ = nullptr; }
}

std::unique_ptr<AudioRing> Output::makeRingView() { return shm_ ? std::make_unique<AudioRing>(shm_, true) : nullptr; }
void Output::pause(bool paused) { if (sdl_) SDL_PauseAudioDevice(sdl_, paused); else if (view_) view_->setPlaying(!paused); }
bool Output::playing() const
{
    if (sdl_) return SDL_GetAudioDeviceStatus(sdl_) == SDL_AUDIO_PLAYING;
    return view_ && view_->playingSet() && view_->consumerAlive(500000);
}
const char* Output::statusName() const
{
    if (sdl_) { const auto s = SDL_GetAudioDeviceStatus(sdl_); return s == SDL_AUDIO_PLAYING ? "playing" : s == SDL_AUDIO_PAUSED ? "PAUSED" : "STOPPED"; }
    if (!view_) return "closed";
    if (!view_->playingSet()) return "PAUSED (relay)";
    return view_->consumerAlive(500000) ? "playing (relay)" : "RELAY NOT CALLING BACK";
}
void Output::lock() { if (sdl_) SDL_LockAudioDevice(sdl_); }
void Output::unlock() { if (sdl_) SDL_UnlockAudioDevice(sdl_); }
uint32_t Output::queuedBytes() const
{
    if (sdl_) return SDL_GetQueuedAudioSize(sdl_);
    return view_ ? uint32_t(view_->fillFrames() * AudioRing::channels * sizeof(int16_t)) : 0;
}
void Output::clearQueued()
{
    if (sdl_) { SDL_ClearQueuedAudio(sdl_); return; }
    if (view_) { view_->clear(); queuedMedia_ = 0; }
}
int Output::queue(const void* data, uint32_t bytes)
{
    if (sdl_) return SDL_QueueAudio(sdl_, data, bytes);
    if (!view_) return -1;
    const size_t frames = bytes / (AudioRing::channels * sizeof(int16_t));
    if (!view_->write(static_cast<const int16_t*>(data), frames, queuedMedia_)) return -1;
    queuedMedia_ += double(frames) / AudioRing::rate;
    return 0;
}
int Output::deviceFrames() const
{
    if (relayFd_ >= 0 && view_) { const uint32_t f = view_->consumerDeviceFrames(); if (f) return int(f); }
    return int(deviceFrames_);
}
unsigned Output::id() const { return sdl_ ? unsigned(sdl_) : relayFd_ >= 0 ? 1000u + unsigned(channel_) : 0u; }
std::string Output::describe() const
{
    if (sdl_) return "SDL device " + std::to_string(sdl_) + " in this process";
    return "UI-process relay channel " + std::to_string(channel_) + " (device buffer " + std::to_string(deviceFrames()) + " frames)";
}

}
