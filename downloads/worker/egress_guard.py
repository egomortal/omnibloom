# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_EGRESS_GUARD_V1: confine yt-dlp's own networking to public addresses.

Audit finding DW-01: the deep (site extractor) probe checked only the first
address, then let yt-dlp make its own connections, redirects and extractor
subrequests. This module is a small forward proxy that listens on 127.0.0.1
only. yt-dlp is given ``proxy=<guard url>``, so every HTTP request and every
HTTPS tunnel it opens comes here first. Each connection is checked with the
same resolver as the direct probe (public unicast addresses only; loopback,
private, link-local, shared, multicast and reserved are refused) and the
outgoing socket is pinned to the checked address, so DNS rebinding between
the check and the connect cannot redirect it.

One request per client connection (``Connection: close``), so a kept-alive
proxy connection can never be reused for a different, unchecked host.
"""
import socket
import threading
import urllib.parse

HEAD_LIMIT = 64 * 1024
RESOLVE_TIMEOUT = 8.0
CONNECT_TIMEOUT = 10.0
IDLE_TIMEOUT = 60.0
MAX_CONNECTIONS = 24
HOP_HEADERS = {'connection', 'keep-alive', 'proxy-connection', 'proxy-authorization',
               'proxy-authenticate', 'te', 'trailer', 'upgrade'}


class Refused(Exception):
    pass


def resolve_within(resolver, host, port, timeout=RESOLVE_TIMEOUT):
    """Run a blocking resolver with a hard deadline (audit DW-02).

    The worker thread is a daemon; a stuck OS resolver can't hold the caller
    past the deadline."""
    box = {}

    def run():
        try:
            box['value'] = resolver(host, port)
        except BaseException as error:  # noqa: BLE001 - re-raised in the caller
            box['error'] = error
    thread = threading.Thread(target=run, name='omni-resolve', daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError('address lookup timed out')
    if 'error' in box:
        raise box['error']
    return box['value']


def _split_host_port(text, default_port):
    text = text.strip()
    if text.startswith('['):
        end = text.find(']')
        if end < 0:
            raise ValueError('bad host')
        host, rest = text[1:end], text[end + 1:]
        port = int(rest[1:]) if rest.startswith(':') else default_port
    elif text.count(':') == 1:
        host, port_text = text.split(':', 1)
        port = int(port_text)
    else:
        host, port = text, default_port
    if not host or not 0 < port < 65536:
        raise ValueError('bad host or port')
    return host, port


class EgressGuard:
    def __init__(self, resolver, max_connections=MAX_CONNECTIONS, idle_timeout=IDLE_TIMEOUT,
                 resolve_timeout=RESOLVE_TIMEOUT, connect_timeout=CONNECT_TIMEOUT):
        self.resolver = resolver
        self.idle_timeout = idle_timeout
        self.resolve_timeout = resolve_timeout
        self.connect_timeout = connect_timeout
        self.slots = threading.BoundedSemaphore(max_connections)
        self.refused = 0
        self.allowed = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('127.0.0.1', 0))
        self._sock.listen(32)
        self.port = self._sock.getsockname()[1]
        self.url = 'http://127.0.0.1:%d' % self.port
        self._closed = False
        threading.Thread(target=self._accept, name='omni-egress-guard', daemon=True).start()

    def close(self):
        self._closed = True
        try:
            self._sock.close()
        except OSError:
            pass

    def _accept(self):
        while not self._closed:
            try:
                client, peer = self._sock.accept()
            except OSError:
                return
            if peer[0] != '127.0.0.1':
                client.close()
                continue
            if not self.slots.acquire(blocking=False):
                self._reply(client, 503, 'Busy')
                continue
            threading.Thread(target=self._serve, args=(client,), name='omni-egress', daemon=True).start()

    @staticmethod
    def _reply(client, code, text):
        try:
            client.sendall(('HTTP/1.1 %d %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n' % (code, text)).encode())
        except OSError:
            pass
        finally:
            client.close()

    def _read_head(self, client):
        client.settimeout(self.connect_timeout)
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = client.recv(8192)
            if not chunk:
                raise ValueError('closed')
            data += chunk
            if len(data) > HEAD_LIMIT:
                raise ValueError('head too large')
        head, rest = data.split(b'\r\n\r\n', 1)
        return head.decode('iso-8859-1'), rest

    def _open(self, host, port):
        try:
            family, address, _ = resolve_within(self.resolver, host, port, self.resolve_timeout)[:3]
        except TimeoutError:
            raise
        except Exception as error:
            # The probe's resolver raises its own Refused for local/private addresses.
            if type(error).__name__ == 'Refused':
                raise Refused(str(error)) from error
            raise
        return socket.create_connection((address, port), self.connect_timeout)

    def _serve(self, client):
        upstream = None
        try:
            try:
                head, rest = self._read_head(client)
            except (ValueError, OSError):
                client.close()
                return
            lines = head.split('\r\n')
            parts = lines[0].split(' ')
            if len(parts) != 3 or not parts[2].startswith('HTTP/1.'):
                return self._reply(client, 400, 'Bad Request')
            method, target, _ = parts
            try:
                if method.upper() == 'CONNECT':
                    host, port = _split_host_port(target, 443)
                    upstream = self._open(host, port)
                    self.allowed += 1
                    client.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                    if rest:
                        upstream.sendall(rest)
                else:
                    url = urllib.parse.urlsplit(target)
                    if url.scheme != 'http' or not url.hostname or url.username or url.password:
                        return self._reply(client, 400, 'Bad Request')
                    host, port = url.hostname, url.port or 80
                    upstream = self._open(host, port)
                    self.allowed += 1
                    path = urllib.parse.urlunsplit(('', '', url.path or '/', url.query, ''))
                    out = ['%s %s HTTP/1.1' % (method, path)]
                    seen_host = False
                    for line in lines[1:]:
                        name = line.split(':', 1)[0].strip().lower()
                        if not line or name in HOP_HEADERS:
                            continue
                        seen_host = seen_host or name == 'host'
                        out.append(line)
                    if not seen_host:
                        out.append('Host: %s' % url.netloc)
                    out.append('Connection: close')
                    upstream.sendall(('\r\n'.join(out) + '\r\n\r\n').encode('iso-8859-1') + rest)
            except Refused:
                self.refused += 1
                return self._reply(client, 403, 'Forbidden')
            except TimeoutError:
                return self._reply(client, 504, 'Gateway Timeout')
            except Exception:  # noqa: BLE001 - lookup failures, bad targets, connect errors
                return self._reply(client, 502, 'Bad Gateway')
            self._relay(client, upstream)
        finally:
            for s in (client, upstream):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
            self.slots.release()

    def _relay(self, a, b):
        import select
        a.settimeout(None)
        b.settimeout(None)
        pair = {a: b, b: a}
        while True:
            ready, _, _ = select.select([a, b], [], [], self.idle_timeout)
            if not ready:
                return
            for s in ready:
                try:
                    data = s.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                try:
                    pair[s].sendall(data)
                except OSError:
                    return


_guard = None
_guard_lock = threading.Lock()


def shared_guard(resolver):
    """One guard per worker process, started on first use."""
    global _guard
    with _guard_lock:
        if _guard is None or _guard._closed:
            _guard = EgressGuard(resolver)
        return _guard
