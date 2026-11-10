// OMNI_FILES_BROKER_V1: USB drives and extended storage for the native title.
// A native title only sees /data, /mnt/disc and the fonts, so /mnt/usb0..7 and /mnt/ext0..1 come
// from the omni-files broker (outputs/omni-files-broker): a payload outside the sandbox, started here
// through the ELF loader on 9021 the first time it is needed, answering on 127.0.0.1:8767 with a
// per-start token from /data/omni/native/broker.token. It exits when the title does.
// In the big-app (no omni_native_title_active symbol) nothing here runs: every path is local as before.
// Included from OmniFeatures.h (inside OmniBrowser.cpp's anonymous namespace); the socket headers and
// the weak omni_native_title_active declaration are in OmniFeatures2Includes.h.
#pragma once

static bool omniNativeTitle()
{
    static int cached = -1;
    if (cached < 0) cached = (omni_native_title_active && omni_native_title_active()) ? 1 : 0;
    return cached == 1;
}
static bool omniOfbRemote(const std::string& path)
{
    return omniNativeTitle() && (path.rfind("/mnt/usb", 0) == 0 || path.rfind("/mnt/ext", 0) == 0);
}

struct OmniOfbEntry { std::string name; bool dir = false; long long size = 0, mtime = 0; };
struct OmniOfbPlace { std::string root; long long total = 0, avail = 0; };

static const char* const omniOfbDir = "/data/omni/native";
static std::string omniOfbHex(const std::string& s)
{
    static const char d[] = "0123456789abcdef";
    std::string o; o.reserve(s.size() * 2);
    for (unsigned char c : s) { o += d[c >> 4]; o += d[c & 15]; }
    return o;
}
static bool omniOfbUnhex(const std::string& s, std::string& out)
{
    if (s.size() % 2) return false;
    out.clear();
    for (size_t i = 0; i < s.size(); i += 2) {
        int v = 0;
        for (int k = 0; k < 2; ++k) {
            const char c = s[i + k];
            const int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
            if (d < 0) return false;
            v = v * 16 + d;
        }
        if (!v) return false;
        out += char(v);
    }
    return true;
}
static std::string omniOfbToken()
{
    char buf[40] = {};
    if (FILE* f = fopen("/data/omni/native/broker.token", "r")) { (void)!fread(buf, 1, 32, f); fclose(f); }
    return strlen(buf) == 32 ? std::string(buf) : std::string();
}
static int omniOfbConnect(int port)
{
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    timeval tv { 15, 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    sockaddr_in a {};
    a.sin_family = AF_INET; a.sin_port = htons(uint16_t(port)); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a)) { close(fd); return -1; }
    return fd;
}
static bool omniOfbSendAll(int fd, const char* p, size_t n)
{
    while (n) { const ssize_t w = send(fd, p, n, 0); if (w < 0 && errno == EINTR) continue; if (w <= 0) return false; p += w; n -= size_t(w); }
    return true;
}
// Starts the broker through the ELF loader (at most every 5 s). broker.parent tells it whose pid to
// follow and which uid owns the token file.
static std::mutex omniOfbLock;
static bool omniOfbSpawn()
{
    static uint32_t last = 0;
    const uint32_t now = SDL_GetTicks();
    if (last && now - last < 5000) return false;
    last = now;
    mkdir(omniOfbDir, 0777);
    if (FILE* f = fopen("/data/omni/native/broker.parent", "w")) { fprintf(f, "%d %d\n", int(getpid()), int(getuid())); fclose(f); }
    FILE* e = fopen("/data/omni/native/omni-files.elf", "rb");
    if (!e) { log("files broker: /data/omni/native/omni-files.elf is missing"); return false; }
    std::string elf;
    char chunk[65536];
    size_t n;
    while ((n = fread(chunk, 1, sizeof chunk, e)) > 0 && elf.size() < (16u << 20)) elf.append(chunk, n);
    fclose(e);
    const int fd = omniOfbConnect(9021);
    if (fd < 0) { log("files broker: ELF loader on 9021 not reachable"); return false; }
    const bool sent = omniOfbSendAll(fd, elf.data(), elf.size());
    shutdown(fd, SHUT_WR);
    timeval tv { 2, 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    char sink[256];
    (void)recv(fd, sink, sizeof sink, 0);
    close(fd);
    char line[96];
    snprintf(line, sizeof line, "files broker: started through the ELF loader (%zu bytes, %s)", elf.size(), sent ? "sent" : "send failed");
    log(line);
    return sent;
}
// One request. `body` is sent after the request line (write); the reply body goes to `out`.
// Returns 0 or an errno (EHOSTUNREACH when the broker can't be reached at all).
static int omniOfbCall(const std::string& verb, const std::string& path, const std::string& extra, const char* body, size_t bodyLen, std::string* out, size_t cap = 9u << 20)
{
    if (!omniNativeTitle()) return ENOTSUP;
    OmniHub::Card provider;
    if (!OmniHub::card("files-broker", provider) || provider.port < 8761 || provider.port > 8899)
        return EHOSTUNREACH;
    const int port = provider.port;
    int fd = omniOfbConnect(port);
    if (fd < 0) {
        std::lock_guard<std::mutex> g(omniOfbLock);
        fd = omniOfbConnect(port);
        if (fd < 0 && omniOfbSpawn())
            for (int i = 0; i < 40 && fd < 0; ++i) { usleep(100000); fd = omniOfbConnect(port); }
        if (fd < 0) return EHOSTUNREACH;
    }
    std::string token = omniOfbToken();
    for (int i = 0; i < 20 && token.empty(); ++i) { usleep(50000); token = omniOfbToken(); }
    std::string line = "OFB1\t" + token + "\t" + verb + "\t" + omniOfbHex(path) + (extra.empty() ? "" : "\t" + extra) + "\n";
    if (!omniOfbSendAll(fd, line.data(), line.size()) || (bodyLen && !omniOfbSendAll(fd, body, bodyLen))) { close(fd); return EPIPE; }
    std::string head;
    char c;
    while (head.size() < 64 && recv(fd, &c, 1, 0) == 1 && c != '\n') head += c;
    int err = 0;
    if (head.rfind("OK\t", 0) == 0) {
        const unsigned long long want = strtoull(head.c_str() + 3, nullptr, 10);
        if (want > cap) err = EFBIG;
        else if (out) {
            out->resize(size_t(want));
            size_t got = 0;
            while (got < want) { const ssize_t r = recv(fd, &(*out)[got], size_t(want) - got, 0); if (r < 0 && errno == EINTR) continue; if (r <= 0) break; got += size_t(r); }
            if (got < want) err = EIO;
        }
    } else if (head.rfind("ERR\t", 0) == 0) err = atoi(head.c_str() + 4);
    else err = EPROTO;
    close(fd);
    if (!err) err = 0;
    return err;
}
static std::vector<OmniOfbPlace> omniOfbPlaces()
{
    std::vector<OmniOfbPlace> out;
    std::string body;
    if (omniOfbCall("places", "", "", nullptr, 0, &body)) return out;
    size_t at = 0;
    while (at < body.size()) {
        size_t nl = body.find('\n', at); if (nl == std::string::npos) nl = body.size();
        const std::string row = body.substr(at, nl - at); at = nl + 1;
        const size_t t1 = row.find('\t'), t2 = t1 == std::string::npos ? t1 : row.find('\t', t1 + 1);
        OmniOfbPlace p;
        if (t1 == std::string::npos || !omniOfbUnhex(row.substr(0, t1), p.root)) continue;
        p.total = atoll(row.c_str() + t1 + 1);
        if (t2 != std::string::npos) p.avail = atoll(row.c_str() + t2 + 1);
        out.push_back(p);
    }
    return out;
}
static bool omniOfbParseEntry(const std::string& row, OmniOfbEntry& e)
{
    // "<d|f>\t<size>\t<mtime>\t<hex name>"
    const size_t a = row.find('\t'), b = a == std::string::npos ? a : row.find('\t', a + 1), c = b == std::string::npos ? b : row.find('\t', b + 1);
    if (c == std::string::npos || !omniOfbUnhex(row.substr(c + 1), e.name)) return false;
    e.dir = row[0] == 'd';
    e.size = atoll(row.c_str() + a + 1);
    e.mtime = atoll(row.c_str() + b + 1);
    return true;
}
static int omniOfbList(const std::string& path, std::vector<OmniOfbEntry>& out)
{
    std::string body;
    const int err = omniOfbCall("list", path, "", nullptr, 0, &body, 5u << 20);
    if (err) return err;
    size_t at = 0;
    while (at < body.size()) {
        size_t nl = body.find('\n', at); if (nl == std::string::npos) nl = body.size();
        OmniOfbEntry e;
        if (omniOfbParseEntry(body.substr(at, nl - at), e)) out.push_back(std::move(e));
        at = nl + 1;
    }
    return 0;
}
static int omniOfbStat(const std::string& path, OmniOfbEntry& e)
{
    std::string body;
    const int err = omniOfbCall("stat", path, "", nullptr, 0, &body);
    if (err) return err;
    if (!body.empty() && body.back() == '\n') body.pop_back();
    return omniOfbParseEntry(body, e) ? 0 : EPROTO;
}

// ---- background copies (one at a time): USB -> /data/omni/uploads for the file picker, and
// /data/omni/downloads -> USB for the Downloads page. The tick (omniOfbJobTick) posts the result.
struct OmniOfbJob {
    std::atomic<int> state { 0 };           // 0 idle, 1 running, 2 done, 3 failed
    std::atomic<long long> done { 0 }, total { 0 };
    int kind = 0;                           // 1 picker upload, 2 copy to USB, 3 self-test
    std::vector<std::string> results;       // local paths (1) or the destination (2)
    std::string error;
    uint32_t lastNotice = 0;
};
static OmniOfbJob omniOfbJob;
static std::thread omniOfbThread;
static bool omniOfbBusy() { return omniOfbJob.state.load() == 1; }
static void omniOfbStart(int kind, std::function<void()> work)
{
    if (omniOfbThread.joinable()) omniOfbThread.join();
    omniOfbJob.kind = kind; omniOfbJob.results.clear(); omniOfbJob.error.clear();
    omniOfbJob.done = 0; omniOfbJob.total = 0; omniOfbJob.lastNotice = 0;
    omniOfbJob.state = 1;
    omniOfbThread = std::thread([work = std::move(work)]() { work(); });
}
static std::string omniOfbBaseName(const std::string& p) { const size_t s = p.rfind('/'); return s == std::string::npos ? p : p.substr(s + 1); }
static std::string omniOfbErr(int e)
{
    if (e == EHOSTUNREACH) return "the USB helper didn't start";
    if (e == ENOSPC) return "the drive is full";
    if (e == EACCES) return "access refused";
    if (e == EEXIST) return "a file with that name exists";
    return strerror(e);
}
// Copies one remote file to `local`. Chunks of 4 MiB; up to 4 GiB.
static int omniOfbCopyIn(const std::string& remote, const std::string& local)
{
    OmniOfbEntry st;
    int err = omniOfbStat(remote, st);
    if (err) return err;
    if (st.dir) return EISDIR;
    if (st.size > (4LL << 30)) return EFBIG;
    omniOfbJob.total += st.size;
    FILE* f = fopen(local.c_str(), "wb");
    if (!f) return errno;
    long long off = 0;
    std::string chunk;
    while (off < st.size) {
        const long long want = std::min<long long>(4LL << 20, st.size - off);
        err = omniOfbCall("read", remote, std::to_string(off) + "\t" + std::to_string(want), nullptr, 0, &chunk);
        if (!err && chunk.empty()) err = EIO;
        if (err) break;
        if (fwrite(chunk.data(), 1, chunk.size(), f) != chunk.size()) { err = errno ? errno : EIO; break; }
        off += (long long)chunk.size();
        omniOfbJob.done += (long long)chunk.size();
    }
    if (fclose(f) && !err) err = errno;
    if (err) unlink(local.c_str());
    return err;
}
// Copies a local file to a new remote file (never overwrites).
static int omniOfbCopyOut(const std::string& local, const std::string& remote)
{
    FILE* f = fopen(local.c_str(), "rb");
    if (!f) return errno;
    struct stat st {};
    fstat(fileno(f), &st);
    omniOfbJob.total = st.st_size;
    std::vector<char> buf(4u << 20);
    long long off = 0;
    int err = 0;
    bool first = true;
    for (;;) {
        const size_t n = fread(buf.data(), 1, buf.size(), f);
        if (!n && !first) break;
        err = omniOfbCall("write", remote, std::to_string(off) + "\t" + std::to_string(n) + "\t" + (first ? "1" : "0"), buf.data(), n, nullptr);
        if (err) break;
        first = false;
        off += (long long)n;
        omniOfbJob.done = off;
        if (n < buf.size()) break;
    }
    fclose(f);
    return err;
}
static void omniOfbCleanUploads(int maxAgeSeconds)
{
    const std::string dir = omniData("uploads");
    const time_t now = time(nullptr);
    if (DIR* d = opendir(dir.c_str())) {
        while (dirent* e = readdir(d)) {
            if (e->d_name[0] == '.') continue;
            const std::string p = dir + "/" + e->d_name;
            struct stat st {};
            if (!stat(p.c_str(), &st) && S_ISREG(st.st_mode) && now - st.st_mtime >= maxAgeSeconds) unlink(p.c_str());
        }
        closedir(d);
    }
}
// Downloads page: copy a finished download to <first drive>/Omni/<name> (a new name if taken).
static void omniOfbCopyToUsb(const std::string& localPath)
{
    if (omniOfbBusy()) { notice("A USB copy is already running"); return; }
    notice("Copying " + omniOfbBaseName(localPath) + " to a USB drive...");
    omniOfbStart(2, [localPath]() {
        const auto places = omniOfbPlaces();
        if (places.empty()) { omniOfbJob.error = "No USB drive or extended storage found"; omniOfbJob.state = 3; return; }
        const std::string dir = places[0].root + "/Omni";
        const int mk = omniOfbCall("mkdir", dir, "", nullptr, 0, nullptr);
        if (mk && mk != EEXIST) { omniOfbJob.error = "Couldn't make " + dir + ": " + omniOfbErr(mk); omniOfbJob.state = 3; return; }
        const std::string name = omniOfbBaseName(localPath);
        const size_t dot = name.rfind('.');
        const std::string stem = dot == std::string::npos || dot == 0 ? name : name.substr(0, dot), ext = dot == std::string::npos || dot == 0 ? "" : name.substr(dot);
        std::string dest = dir + "/" + name;
        OmniOfbEntry e;
        for (int i = 2; !omniOfbStat(dest, e) && i < 1000; ++i) dest = dir + "/" + stem + " (" + std::to_string(i) + ")" + ext;
        const int err = omniOfbCopyOut(localPath, dest);
        if (err) { omniOfbJob.error = "Couldn't copy to " + dest + ": " + omniOfbErr(err); omniOfbJob.state = 3; return; }
        omniOfbJob.results = { dest };
        omniOfbJob.state = 2;
    });
}
