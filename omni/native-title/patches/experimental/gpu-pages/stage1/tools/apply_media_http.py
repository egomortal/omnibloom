"""OMNI_MEDIA_HTTP_V3 (2026-11-13): Omni's /healthz request to the downloads worker failed instantly on the console.

/data/omni/media-downloads.log (OMNI_MEDIA_DIAG_V1) showed every request as `state=2 status=0 body=0 0ms` for the whole
30 s: the non-blocking loopback request (socket, fcntl/ioctl O_NONBLOCK, connect, poll) fails at once, while Bloom Core
sees the worker up and the title's own blocking connects to 127.0.0.1:9021 (the ELF loader) work.

Now any early failure of the non-blocking path logs the step and errno and retries the same request over a plain
blocking socket with SO_SNDTIMEO / SO_RCVTIMEO (the kind of connection that works from the title). A refusal is still
reported as a refusal, so the "launch only when the port refuses" rule is unchanged.

Apply AFTER apply_media_diag.py (uses OmniMediaDownloads::diag).
usage: apply_media_http.py <engine tree>   (edits engine/entry/OmniMediaDownloads.h; anchored, idempotent)
"""
import sys
from pathlib import Path

MARK = 'OMNI_MEDIA_HTTP_V3'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniMediaDownloads.h'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8').replace('\r\n', '\n')
if MARK in s:
    print('already'); sys.exit(0)
if 'OMNI_MEDIA_DIAG_V1' not in s:
    sys.exit('apply_media_diag.py must run first')

ANCHOR = '// IPv4 loopback only; no DNS, redirects, environment proxy or browser cookies.\ninline HttpResult get('
if s.count(ANCHOR) != 1:
    sys.exit('get() anchor found %d times' % s.count(ANCHOR))

BLOCKING = r'''// OMNI_MEDIA_HTTP_V3: the same request over a plain blocking socket with send/receive timeouts. Used when the
// non-blocking path fails early (it failed instantly on the console while blocking loopback connects work).
inline void diag(const char* format, ...);
inline HttpResult getBlocking(uint16_t port, const std::string& path, unsigned timeoutMs, const char* why, int err) {
    diag("http: non-blocking %s failed (errno %d); retrying with a blocking connection", why, err);
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) { diag("http: blocking socket() failed (errno %d)", errno); return {}; }
    struct Close { int fd; ~Close() { close(fd); } } owner { fd };
    timeval tv {};
    tv.tv_sec = static_cast<decltype(tv.tv_sec)>(timeoutMs / 1000);
    tv.tv_usec = static_cast<decltype(tv.tv_usec)>((timeoutMs % 1000) * 1000);
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#ifdef SO_NOSIGPIPE
    int noSignal = 1;
    (void)setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, sizeof(noSignal));
#endif
    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address))) {
        const int e = errno;
        diag("http: blocking connect failed (errno %d)", e);
        if (e == ECONNREFUSED) return { HttpState::Refused, 0, "" };
        return {};
    }
    const std::string request = "GET " + path + " HTTP/1.0\r\nHost: 127.0.0.1:" + std::to_string(port)
        + "\r\nConnection: close\r\nAccept: application/json\r\n\r\n";
    size_t sent = 0;
    while (sent < request.size()) {
#ifdef MSG_NOSIGNAL
        const ssize_t n = send(fd, request.data() + sent, request.size() - sent, MSG_NOSIGNAL);
#else
        const ssize_t n = send(fd, request.data() + sent, request.size() - sent, 0);
#endif
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { diag("http: blocking send failed (errno %d)", errno); return {}; }
        sent += static_cast<size_t>(n);
    }
    std::string raw;
    char buffer[1024];
    for (;;) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { diag("http: blocking recv failed (errno %d)", errno); return {}; }
        if (!n) break;
        if (raw.size() + static_cast<size_t>(n) > 8192) return {};
        raw.append(buffer, static_cast<size_t>(n));
    }
    return parseHttp(raw);
}
'''

s = s.replace(ANCHOR, BLOCKING + ANCHOR, 1)
start = s.index(ANCHOR)
end = s.index('    return parseHttp(raw);\n}', start)
body = s[start:end]
first_check = body.index('return {};')          # the argument check stays as it is
head, rest = body[:first_check + len('return {};')], body[first_check + len('return {};'):]

steps = [
    ('if (fd < 0) return {};', 'if (fd < 0) return getBlocking(port, path, timeoutMs, "socket()", errno); // OMNI_MEDIA_HTTP_V3'),
    ('if (!omniSocketNonBlocking(fd)) return {};', 'if (!omniSocketNonBlocking(fd)) return getBlocking(port, path, timeoutMs, "O_NONBLOCK", errno);'),
    ('if (errno != EINPROGRESS || !waitFd(fd, POLLOUT, deadline)) return {};',
     'if (errno != EINPROGRESS) return getBlocking(port, path, timeoutMs, "connect()", errno);\n'
     '        if (!waitFd(fd, POLLOUT, deadline)) return getBlocking(port, path, timeoutMs, "poll(connect)", errno);'),
    ('if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size)) return {};',
     'if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size)) return getBlocking(port, path, timeoutMs, "SO_ERROR", errno);'),
    ('if (error) return {};', 'if (error) return getBlocking(port, path, timeoutMs, "connect (SO_ERROR)", error);'),
    ('if (!waitFd(fd, POLLOUT, deadline)) return {};', 'if (!waitFd(fd, POLLOUT, deadline)) return getBlocking(port, path, timeoutMs, "poll(send)", errno);'),
    ('if (n <= 0) return {};', 'if (n <= 0) return getBlocking(port, path, timeoutMs, "send()", errno);'),
    ('if (!waitFd(fd, POLLIN, deadline)) return {};', 'if (!waitFd(fd, POLLIN, deadline)) return getBlocking(port, path, timeoutMs, "poll(recv)", errno);'),
    ('if (n < 0) return {};', 'if (n < 0) return getBlocking(port, path, timeoutMs, "recv()", errno);'),
]
for old, new in steps:
    if rest.count(old) != 1:
        sys.exit('get() step %r found %d times' % (old, rest.count(old)))
    rest = rest.replace(old, new, 1)
s = s[:start] + head + rest + s[end:]
s = s.replace('#include <sys/stat.h>', '#include <sys/stat.h>\n#include <sys/time.h> // OMNI_MEDIA_HTTP_V3', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied OMNI_MEDIA_HTTP_V3')
