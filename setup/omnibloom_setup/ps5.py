"""Talking to the PS5: finding it on the network and a careful FTP client.

The console's FTP server (ftpsrv) has quirks that our own deploy scripts learned the hard way:
- LIST works; MLSD is advertised but answers 502; NLST is not supported.
- DELE answers 226 instead of 250 (Python's ftplib raises error_reply for it).
- A native title's eboot.bin is served as a decoded view, so its readback differs from the upload.
- Rename (RNFR/RNTO) works and is how we park or replace files. The setup never deletes.
"""
import concurrent.futures
import ftplib
import hashlib
import io
import ipaddress
import json
import posixpath
import socket
import urllib.request

from . import config


def port_open(host, port, timeout=1.0):
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def local_networks():
    """The /24 networks this computer is on (private addresses only)."""
    found = set()
    candidates = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.add(info[4][0])
    except OSError:
        pass
    # The address used for the default route (no packet is sent for UDP connect).
    for probe in ("10.255.255.255", "192.168.255.255", "172.31.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 9))
            candidates.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            found.add(ipaddress.ip_network(addr + "/24", strict=False))
    return sorted(found, key=str)


def scan(networks=None, ftp_port=None, loader_port=None, timeout=0.35, workers=96, progress=None):
    """Find consoles: anything answering on the FTP port, then check the loader port.
    Returns a list of dicts: {host, ftp, loader}."""
    ftp_port = ftp_port or config.FTP_PORT
    loader_port = loader_port or config.LOADER_PORT
    nets = networks if networks is not None else local_networks()
    hosts = [str(h) for n in nets for h in n.hosts()]
    hits = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(port_open, h, ftp_port, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            done += 1
            if progress and done % 16 == 0:
                progress(done, len(hosts))
            if fut.result():
                hits.append(futures[fut])
    results = []
    for h in sorted(hits, key=lambda a: ipaddress.ip_address(a)):
        results.append({"host": h, "ftp": True, "loader": port_open(h, loader_port, 1.0)})
    return results


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Console:
    """One FTP session to the PS5 plus helpers. Every write goes through `put_verified`
    or `rename`; nothing is ever deleted."""

    def __init__(self, host, ftp_port=None, loader_port=None, websrv_port=None, timeout=30, launcher_port=None):
        self.host = host
        self.ftp_port = ftp_port or config.FTP_PORT
        self.loader_port = loader_port or config.LOADER_PORT
        self.websrv_port = websrv_port or config.WEBSRV_PORT
        self.launcher_port = launcher_port or config.LAUNCHER_PORT
        self.timeout = timeout
        self.ftp = None

    # -- connection -------------------------------------------------------
    def connect(self):
        f = ftplib.FTP()
        f.connect(self.host, self.ftp_port, timeout=self.timeout)
        f.login()  # the console's FTP accepts an anonymous login
        f.set_pasv(True)
        self.ftp = f
        return self

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except ftplib.all_errors:
                try:
                    self.ftp.close()
                except Exception:
                    pass
            self.ftp = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # -- reading ----------------------------------------------------------
    def listing(self, directory):
        """Entries of a directory as {name: {"dir": bool, "size": int}}; {} if it doesn't exist."""
        lines = []
        try:
            self.ftp.retrlines("LIST " + directory.rstrip("/") + "/", lines.append)
        except ftplib.error_perm:
            return {}
        entries = {}
        for line in lines:
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            name = parts[8]
            if name in (".", ".."):
                continue
            try:
                size = int(parts[4])
            except ValueError:
                size = -1
            entries[name] = {"dir": line.startswith("d"), "size": size}
        return entries

    def exists(self, path):
        parent, name = posixpath.split(path.rstrip("/"))
        return name in self.listing(parent or "/")

    def is_dir(self, path):
        parent, name = posixpath.split(path.rstrip("/"))
        entry = self.listing(parent or "/").get(name)
        return bool(entry and entry["dir"])

    def size(self, path):
        parent, name = posixpath.split(path)
        entry = self.listing(parent or "/").get(name)
        return entry["size"] if entry else None

    def read(self, path, limit=None):
        buf = io.BytesIO()

        def sink(chunk):
            buf.write(chunk)
            if limit and buf.tell() > limit:
                raise _TooBig()

        try:
            self.ftp.retrbinary("RETR " + path, sink)
        except _TooBig:
            try:
                self.ftp.abort()
            except ftplib.all_errors:
                pass
        return buf.getvalue()

    def read_text(self, path, default=None):
        try:
            return self.read(path).decode("utf-8", "replace")
        except ftplib.error_perm:
            return default

    # -- writing (never deletes) -----------------------------------------
    def makedirs(self, directory):
        path = ""
        for part in directory.strip("/").split("/"):
            path += "/" + part
            if not self.is_dir(path):
                try:
                    self.ftp.mkd(path)
                except ftplib.error_perm:
                    if not self.is_dir(path):
                        raise

    def rename(self, src, dst):
        self.ftp.rename(src, dst)

    def store(self, path, data):
        self.ftp.storbinary("STOR " + path, io.BytesIO(data))

    def put_verified(self, path, data, readback=True):
        """Upload to `<path>.omnibloom-new`, check the readback, and return the temp name.
        The caller moves it into place (after parking any existing file)."""
        temp = path + ".omnibloom-new"
        self.store(temp, data)
        if readback:
            got = self.read(temp)
            if sha256(got) != sha256(data):
                raise IOError("upload check failed for " + path)
        else:
            size = self.size(temp)
            if size is None:
                raise IOError("upload did not arrive for " + path)
        return temp

    # -- loader -------------------------------------------------------------
    def loader_open(self):
        return port_open(self.host, self.loader_port, 2.0)

    def send_payload(self, elf_bytes):
        """Start a payload by sending its ELF to the loader (how our own scripts do it)."""
        s = socket.create_connection((self.host, self.loader_port), timeout=20)
        try:
            s.sendall(elf_bytes)
            s.shutdown(socket.SHUT_WR)
        finally:
            s.close()

    def processes(self):
        """Running process names from websrv, or None if websrv isn't there."""
        try:
            url = "http://%s:%d/processes_list" % (self.host, self.websrv_port)
            data = json.load(urllib.request.urlopen(url, timeout=4))
            return [p.get("name", "") for p in data.get("processes", [])]
        except Exception:
            return None


class _TooBig(Exception):
    pass
