"""A fake PS5 for testing the setup without a console.

- FTP on a local port, rooted at a temp folder that stands in for the console's `/`, with the real
  ftpsrv quirks: MLSD → 502, NLST → 502, DELE answers 226, and a native eboot.bin is read back as a
  "decoded" view that differs from what was uploaded. Any DELE is recorded (the setup must never send one).
- A loader stub (like port 9021) that records every ELF sent to it.
- An optional websrv stub (like port 8084) with /processes_list.
- ShadowMountPlus: a rename into /data/homebrew/<title>/ appends a remount line to /data/shadowmount/debug.log
  (set `smp_remount = False` to leave it silent).
- Fixed ports can be passed to start(), so a test can start the "PS5" after Setup has begun waiting for it.

Run by itself:  python tests/fake_console.py <root>   (prints the ports)
"""
import hashlib
import http.server
import io
import json
import logging
import os
import socket
import sys
import threading

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.filesystems import AbstractedFS
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.ioloop import IOLoop
from pyftpdlib.servers import ThreadedFTPServer


logging.getLogger("pyftpdlib").setLevel(logging.WARNING)
HUB_STUB_MAGIC = b"HUBSTUB"   # a fake hub.elf starting with this makes the loader stub "run" Bloom Core


class _Decoded(io.BytesIO):
    name = "decoded-eboot"


class QuirkyFS(AbstractedFS):
    def open(self, filename, mode):
        if "r" in mode and filename.replace("\\", "/").endswith("/eboot.bin") and "/data/homebrew/" in filename.replace("\\", "/"):
            with open(filename, "rb") as f:
                raw = f.read()
            return _Decoded(b"SCE-DECODED-VIEW" + raw[::-1])
        return super().open(filename, mode)


def make_handler(state):
    class QuirkyHandler(FTPHandler):
        abstracted_fs = QuirkyFS
        banner = "fake ftpsrv ready"

        def ftp_MLSD(self, path):
            self.respond("502 Command not implemented.")

        def ftp_NLST(self, path):
            self.respond("502 Command not implemented.")

        def ftp_RNTO(self, path):
            super().ftp_RNTO(path)
            norm = path.replace("\\", "/")
            if state.get("smp_remount", True) and "/data/homebrew/" in norm:
                title = norm.split("/data/homebrew/", 1)[1].split("/", 1)[0]
                log = os.path.join(state["root"], "data", "shadowmount", "debug.log")

                def mounted():
                    os.makedirs(os.path.dirname(log), exist_ok=True)
                    with open(log, "a") as f:
                        f.write("[MOUNT] nullfs mounted /data/homebrew/%s -> /system_ex/app/%s\n" % (title, title))
                threading.Timer(0.2, mounted).start()

        def ftp_DELE(self, path):
            state["deletes"].append(path)
            try:
                os.remove(path)
            except OSError:
                pass
            self.respond("226 Deleted.")

    return QuirkyHandler


def _pid_alive(pid):
    """Is a process with this pid running? (hub.c's kill(pid, 0) check.) On Windows os.kill(pid, 0) is not a probe:
    signal 0 is CTRL_C_EVENT, which interrupts the whole console process group (it stopped the Windows CI run), so
    ask the kernel for the process instead."""
    try:
        pid = int(pid)
    except (TypeError, ValueError, OverflowError):
        return False
    if os.name == "nt":
        import ctypes
        if pid <= 0 or pid > 0xFFFFFFFF:
            return False
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.GetLastError() == 5            # access denied: it exists
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259            # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, OverflowError, ValueError):
        return False
    return True


class FakeConsole:
    def __init__(self, root, websrv=True, processes=("SceShellCore", "SceShellUI", "shadowmountplus.elf", "kstuff-lite.elf", "ftpsrv.elf", "elfldr.elf")):
        self.root = root
        self.state = {"deletes": [], "payloads": [], "root": root, "smp_remount": True}
        self.processes = list(processes)
        self.hub = None
        self.websrv_enabled = websrv
        self._threads = []

    # -- start/stop -------------------------------------------------------
    @property
    def smp_remount(self):
        return self.state["smp_remount"]

    @smp_remount.setter
    def smp_remount(self, value):
        self.state["smp_remount"] = value

    def start(self, ftp_port=0, loader_port=0, websrv_port=0, host="127.0.0.1"):
        """host: another loopback address (127.0.2.1, ...) stands in for a PS5 on a second network."""
        self.host = host
        os.makedirs(self.root, exist_ok=True)
        auth = DummyAuthorizer()
        auth.add_anonymous(self.root, perm="elradfmwMT")
        handler = make_handler(self.state)
        handler.authorizer = auth
        handler.passive_ports = None
        self.ftp = ThreadedFTPServer((host, ftp_port), handler, ioloop=IOLoop())  # own loop per fake console
        self.ftp._exit = threading.Event()  # pyftpdlib shares this Event between servers by default
        self.ftp_port = self.ftp.socket.getsockname()[1]
        self._spawn(lambda: self.ftp.serve_forever(timeout=0.2, blocking=True, handle_exit=False))

        self.loader = socket.socket()
        self.loader.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.loader.bind((host, loader_port))
        self.loader.listen(4)
        self.loader_port = self.loader.getsockname()[1]
        self._spawn(self._loader_loop)

        fake = self

        class Web(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/processes_list":
                    self.send_error(404)
                    return
                body = json.dumps({"processes": [{"name": n, "pid": i + 10} for i, n in enumerate(fake.processes)]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        if self.websrv_enabled:
            self.web = http.server.ThreadingHTTPServer((host, websrv_port), Web)
            self.websrv_port = self.web.server_address[1]
            self._spawn(self.web.serve_forever)
        else:
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            self.websrv_port = s.getsockname()[1]  # a closed port
            s.close()
            self.web = None
        return self

    def _spawn(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        self._threads.append(t)

    def _loader_loop(self):
        while True:
            try:
                conn, _ = self.loader.accept()
            except OSError:
                return
            data = b""
            conn.settimeout(5)
            try:
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            except OSError:
                pass
            conn.close()
            if data:
                self.state["payloads"].append(hashlib.sha256(data).hexdigest())
                if data.startswith(HUB_STUB_MAGIC) and not self.hub:
                    self.start_hub_stub()

    # -- Bloom Core stub ------------------------------------------------
    def start_hub_stub(self):
        """Stands in for Bloom Core (hub.elf): GET /v1/apps and /data/hub/status.json, built by `hub_scan`,
        which mirrors outputs/hub-service/src/hub.c (hub_card_check, hub_receipt_check, port conflicts,
        runtime/<id>.json, hub_write_status)."""
        fake = self

        class Hub(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/health":
                    body = {"ok": True, "version": "stub"}
                elif self.path == "/v1/apps":
                    apps, invalid = fake.hub_scan()
                    body = {"hub_api": 1, "apps": apps, "invalid": invalid}
                else:
                    self.send_error(404)
                    return
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.hub = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hub)
        self.hub_port = self.hub.server_address[1]
        self._spawn(self.hub.serve_forever)
        self._hub_seq = 0
        self._hub_stop = threading.Event()

        def writer():
            while not self._hub_stop.wait(0.2):
                try:
                    self.write_status()
                except Exception:
                    pass
        self._spawn(writer)

    def hub_view(self):
        """Valid apps plus refused cards (as {"id","invalid"}), for older tests."""
        apps, invalid = self.hub_scan()
        return apps + [{"id": b["file"][:-5], "invalid": b["reason"], "verified": False} for b in invalid]

    def hub_scan(self):
        """(apps, invalid) exactly as hub.c's hub_scan computes them."""
        cards_dir = self.path("/data/hub/apps")
        names = sorted(os.listdir(cards_dir)) if os.path.isdir(cards_dir) else []
        apps, invalid = [], []
        for nm in names:
            if nm.startswith("."):
                continue
            reason = None
            stem = nm[:-5] if nm.endswith(".json") else ""
            if len(nm) < 6 or len(nm) - 5 > 40 or not nm.endswith(".json") or not _valid_id(stem):
                reason = "file name must be <id>.json"
            app = None
            if not reason and len(apps) >= 64:
                reason = "too many apps (64 max)"
            if not reason:
                full = os.path.join(cards_dir, nm)
                if os.path.islink(full) or not os.path.isfile(full):
                    reason = "card is not a regular file"
                elif os.path.getsize(full) > 32 * 1024:
                    reason = "card larger than 32 KiB"
                else:
                    raw = open(full, "rb").read()
                    try:
                        card = json.loads(raw, object_pairs_hook=_no_dupes)
                    except ValueError as e:
                        reason = str(e) or "bad JSON"
                    else:
                        app, reason = _card_check(card, stem)
                        if app:
                            app["card_sha"] = hashlib.sha256(raw).hexdigest()
                            app["card"] = card
            if reason:
                invalid.append({"file": nm, "reason": reason})
                continue
            self._receipt_check(app)
            self._runtime(app)
            apps.append(app)
        apps.sort(key=lambda a: a["id"])
        for a in apps:
            if a["dyn"]:
                a["runtime_note"] = self._runtime_note(a, apps)
        for i, a in enumerate(apps):
            for b in apps[:i]:
                if a["port"] and b["port"] == a["port"]:
                    a.update(verified=False, status="conflict", why="port %d already used by %s" % (a["port"], b["id"]))
                    break
        return [_emit(a) for a in apps], invalid

    def _receipt_check(self, a):
        a.update(verified=False, status="unverified", why="")
        path = self.path("/data/hub/receipts/%s.json" % a["id"])
        if not os.path.lexists(path):
            a["why"] = "no receipt from Setup"
            return
        if os.path.islink(path) or not os.path.isfile(path):
            a["why"] = "receipt unreadable"
            return
        if os.path.getsize(path) > 8 * 1024:
            a["why"] = "receipt larger than 8 KiB"
            return
        try:
            r = json.loads(open(path, "rb").read(), object_pairs_hook=_no_dupes)
        except ValueError:
            r = None
        if not isinstance(r, dict):
            a["why"] = "receipt is not valid JSON"
        elif r.get("id") != a["id"]:
            a["why"] = "receipt id does not match"
        elif r.get("version") != a["version"]:
            a["why"] = "receipt version does not match"
        elif "port" in r and (0 if r["port"] is None else (r["port"] if type(r["port"]) is int and 1 <= r["port"] <= 65535 else -1)) != a["port"]:
            a["why"] = "receipt port does not match"
        elif "card_sha256" in r and r.get("card_sha256") != a["card_sha"]:
            a["why"] = "card changed since install"
        else:
            a.update(verified=True, status="ok", why="")

    def _runtime(self, a):
        path = self.path("/data/hub/runtime/%s.json" % a["id"])
        a["runtime"] = None
        a["nonlocal"] = False
        if os.path.isfile(path) and os.path.getsize(path) <= 4 * 1024:
            try:
                r = json.load(open(path))
            except ValueError:
                return
            if isinstance(r, dict) and ("id" not in r or r.get("id") == a["id"]):
                a["runtime"] = {k: r[k] for k in ("pid", "port", "started_at") if type(r.get(k)) in (int, float) and r[k] > 0}
                a["nonlocal"] = "host" in r and r["host"] not in ("127.0.0.1", "localhost")

    @staticmethod
    def _runtime_note(a, apps):
        """hub.c (item 15): why a started_by app without a card port has no usable live port, or "" if it has one.
        (This stub never probes, so its apps stay "up": false; live_port stays null like hub.c before a health pass.)"""
        rt = a.get("runtime")
        if rt is None:
            return "no runtime file"
        pid, port = rt.get("pid"), rt.get("port") or 0
        if not pid:
            return "runtime file has no pid"
        if not _pid_alive(pid):
            return "runtime pid is not running (stale)"
        if a.get("nonlocal"):
            return "runtime host is not loopback"
        if port < 1024:
            return "runtime port missing or below 1024"
        if port in (8760, 9021, 2121):
            return "runtime port is reserved"
        if any(b["port"] and b["port"] == port for b in apps):
            return "runtime port belongs to another app"
        return ""

    def write_status(self):
        """/data/hub/status.json, as hub_write_status writes it."""
        apps, invalid = self.hub_scan()
        self._hub_seq += 1
        body = {"name": "Bloom Core", "id": "hub", "version": "stub", "hub_api": 1, "pid": os.getpid(), "port": 8760,
                "written_at": int(__import__("time").time()),
                "apps": [{"id": a["id"], "version": a["version"], "port": a["port"],
                          **({"live_port": None} if a.get("port_from") else {}),
                          **({"runtime_note": a["runtime_note"]} if a.get("runtime_note") else {}),
                          "verified": a["verified"],
                          "status": a["status"], **({"why": a["why"]} if a.get("why") else {}), "up": False, "checked": False}
                         for a in apps],
                "invalid": invalid, "seq": self._hub_seq}
        p = self.path("/data/hub/status.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(body, f, separators=(",", ":"))
        os.replace(tmp, p)

    # -- launcher stub (/hbldr) that acts like java-worker.elf --------------------------------
    def start_launcher(self):
        """Like the console launcher on port 8080: /hbldr?path&args&cwd&daemon&pipe. When the path is the
        JDownloader engine, it plays the engine's part: reads the config, writes the native receipt (empty at
        start, finished JSON at the end), the provider report or the bridge's ready file. Behaviour per mode is
        set in self.jd_behaviour."""
        fake = self
        self.state.setdefault("launches", [])
        self.jd_behaviour = {"providers": "pass", "jdownloader": "pass", "delay": 0.3}

        class L(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                import urllib.parse as up
                u = up.urlparse(self.path)
                if u.path != "/hbldr":
                    self.send_error(404)
                    return
                q = dict(up.parse_qsl(u.query))
                fake.state["launches"].append(q)
                ok = fake._fake_engine(q)
                self.send_response(200 if ok else 500)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"OK" if ok else b"NO")

            def log_message(self, *a):
                pass

        self.launcher = http.server.ThreadingHTTPServer(("127.0.0.1", 0), L)
        self.launcher_port = self.launcher.server_address[1]
        self._spawn(self.launcher.serve_forever)
        return self.launcher_port

    def _fake_engine(self, q):
        root = "/data/omni-downloader/jdownloader/"
        args = q.get("args", "").split(" ")
        if q.get("path") != root + "java-worker.elf" or not self.exists(root + "java-worker.elf") or len(args) != 3:
            return False
        cfg_path, mode = args[1], args[2]
        try:
            cfg = json.loads(self.read(cfg_path))
        except (OSError, ValueError):
            return False
        receipt = cfg["native_receipt_file"]
        if self.exists(receipt):
            return False                    # O_EXCL in the real engine
        self.write(receipt, b"")
        self.write(receipt + ".log", "native pid=4242 session=%s mode=%s\n" % (cfg["session"], mode))
        behaviour = self.jd_behaviour.get(mode, "pass")

        def finish(code, phase):
            self.write(receipt, json.dumps({"schema": "omni-java-native/v1", "session": cfg["session"], "install_id": cfg["install_id"],
                                            "native_pid": 4242, "mode": mode, "finished": True, "exit_code": code, "phase": phase}) + "\n")

        def run():
            __import__("time").sleep(self.jd_behaviour.get("delay", 0.3))
            image_ok = self.exists(root + "native/java25/lib/modules")
            if mode == "providers":
                if not image_ok:
                    return finish(7, "image-preflight")
                passed = behaviour == "pass"
                steps = ["headless_configuration", "management_native", "awt_toolkit_init", "image_native_raster",
                         "font_native_init", "png_memory_roundtrip"]
                self.write(receipt + ".provider.json", json.dumps({"schema": "omni-jd-native-provider-probe/v1", "passed": passed,
                                                                    "last_step": steps[-1], "steps": steps if passed else steps[:3],
                                                                    "elapsed_ms": 1200, "error_class": "" if passed else "java.lang.UnsatisfiedLinkError"}) + "\n")
                return finish(0 if passed else 11, "Java-main-and-destroy-complete" if passed else "Java-main-exception")
            if mode == "jdownloader":
                needed = [root + "runtime/Core.jar", root + "runtime/JDownloader.jar", root + "runtime/classes/OmniJDownloaderBridge.class"]
                if behaviour == "no-ready" or not all(self.exists(n) for n in needed):
                    return finish(11, "Java-main-exception")
                self.write(cfg["ready_file"], json.dumps({"host": "127.0.0.1", "port": 43210, "token": cfg["token"], "protocol": 2,
                                                          "target_tested": False, "session": cfg["session"],
                                                          "install_id": cfg["install_id"], "native_pid": 4242,
                                                          # the bridge's own report of its egress layers (audit JD-03)
                                                          "egress_policy": None if behaviour == "no-egress" else "omni-public-only-v1",
                                                          "egress_problem": "JVM resolver is not the policy resolver" if behaviour == "no-egress" else ""}))
                __import__("time").sleep(self.jd_behaviour.get("delay", 0.3))
                return finish(0, "Java-main-and-destroy-complete")
            return finish(2, "mode")

        threading.Thread(target=run, daemon=True).start()
        return True

    def stop(self):
        try:
            self.ftp.close_all()
        except Exception:
            pass
        try:
            self.loader.close()
        except Exception:
            pass
        if self.web:
            self.web.shutdown()
        if self.hub:
            self._hub_stop.set()
            self.hub.shutdown()
        if getattr(self, "launcher", None):
            self.launcher.shutdown()

    # -- helpers for tests ----------------------------------------------
    def path(self, console_path):
        return os.path.join(self.root, console_path.lstrip("/"))

    def write(self, console_path, data):
        p = self.path(console_path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode())

    def read(self, console_path):
        with open(self.path(console_path), "rb") as f:
            return f.read()

    def exists(self, console_path):
        return os.path.exists(self.path(console_path))

    def listdir(self, console_path):
        p = self.path(console_path)
        return sorted(os.listdir(p)) if os.path.isdir(p) else []


# -- hub.c's validators (hub_valid_id/name/version/path/intent, hub_card_check), for the Bloom Core stub --------
def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key")
        d[k] = v
    return d


_LOW = set("abcdefghijklmnopqrstuvwxyz")
_DIG = set("0123456789")
_UP = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _valid_id(s):
    return isinstance(s, str) and 1 <= len(s) <= 40 and s[0] != "-" and all(c in _LOW or c in _DIG or c == "-" for c in s)


def _valid_intent(s):
    return isinstance(s, str) and 1 <= len(s) <= 64 and s[0] not in ".-" and all(c in _LOW or c in _DIG or c in ".-_" for c in s)


def _valid_version(s):
    return isinstance(s, str) and 1 <= len(s) <= 32 and all(c in _LOW or c in _UP or c in _DIG or c in ".+_-" for c in s)


def _valid_path(s, mx=128):
    if not isinstance(s, str) or not 1 <= len(s) <= mx or s[0] != "/" or ".." in s or "//" in s:
        return False
    return all(0x20 < ord(c) < 0x7f and c not in "\"\\<>`'" for c in s)


def _valid_name(s):
    return isinstance(s, str) and 1 <= len(s.encode("utf-8")) <= 64 and all(ord(c) >= 0x20 and ord(c) != 0x7f for c in s)


def _str_list(v, ok, mx=32):
    return v is None or (isinstance(v, list) and len(v) <= mx and all(isinstance(e, str) and ok(e) for e in v))


def _int_in(v, lo, hi):
    return type(v) is int and lo <= v <= hi


def _card_check(c, stem):
    """Returns (app, None) or (None, reason) with hub.c's exact reasons."""
    if not isinstance(c, dict):
        return None, "card is not a JSON object"
    api = c.get("hub_api")
    if not _int_in(api, 0, 1000000):
        return None, "hub_api missing or not an integer"
    if api != 1:
        return None, "hub_api not supported by this Bloom Core"
    cid = c.get("id")
    if not isinstance(cid, str) or not _valid_id(cid):
        return None, "id missing or invalid"
    if cid != stem:
        return None, "id does not match the file name"
    if cid == "hub":
        return None, "id hub is Bloom Core's own (it has no card)"
    if not _valid_name(c.get("name")):
        return None, "name missing or invalid"
    if not _valid_version(c.get("version")):
        return None, "version missing or invalid"
    kind = c.get("kind")
    if kind not in ("title", "payload", "service"):
        return None, "kind must be title, payload or service"
    title = kind == "title"
    lsb = c.get("launch").get("started_by") if isinstance(c.get("launch"), dict) else None
    on_demand = isinstance(lsb, str)   # item 15: checked properly below
    port = 0
    if "port" in c and c["port"] is not None:
        if not _int_in(c["port"], 1024, 65535):
            return None, "port missing or outside 1024-65535"
        port = c["port"]
    elif not title and not on_demand:
        return None, "port missing or outside 1024-65535"
    if port in (8760, 9021, 2121):
        return None, "port is reserved (8760, 9021, 2121)"
    if "health" in c:
        h = c["health"]
        if not ((title or on_demand) and h is None) and not _valid_path(h, 128):
            return None, "health must be a path like /api/health"
    health = c.get("health") if isinstance(c.get("health"), str) else ("" if title or ("health" in c and c["health"] is None) else "/api/health")
    launch = c.get("launch")
    autoload = started_by = ""
    if "launch" in c:
        if not isinstance(launch, dict):
            return None, "launch must be an object"
        if "autoload" in launch and launch["autoload"] not in ("never", "optional", "required"):
            return None, "launch.autoload must be never, optional or required"
        if "started_by" in launch and not (isinstance(launch["started_by"], str) and _valid_id(launch["started_by"])):
            return None, "launch.started_by must be an app id"
        autoload, started_by = launch.get("autoload", ""), launch.get("started_by", "")
    if "pages" in c:
        pages = c["pages"]
        if not isinstance(pages, dict):
            return None, "pages must be an object"
        if len(pages) > 16 or not all(isinstance(v, str) and _valid_path(v) for v in pages.values()):
            return None, "pages entries must be paths"
        if not all(_valid_intent(k) for k in pages):
            return None, "pages keys must be simple names"
    if not _str_list(c.get("provides"), _valid_intent):
        return None, "provides must be a list of intent names"
    if not _str_list(c.get("consumes"), _valid_intent):
        return None, "consumes must be a list of intent names"
    if not _str_list(c.get("public_pages"), _valid_path):
        return None, "public_pages must be a list of paths"
    if not _str_list(c.get("page_apis"), _valid_path):
        return None, "page_apis must be a list of paths"
    if "title_id" in c and not (_valid_version(c["title_id"]) and len(c["title_id"]) <= 15):
        return None, "title_id invalid"
    if "icon" in c and not (isinstance(c["icon"], str) and len(c["icon"]) < 256):
        return None, "icon invalid"
    return {"id": cid, "name": c["name"], "version": c["version"], "kind": kind, "title_id": c.get("title_id", ""),
            "port": port, "health": health, "autoload": autoload, "started_by": started_by,
            "dyn": not port and not title}, None


def _emit(a):
    """One app as /v1/apps lists it (hub_emit_app)."""
    out = {"id": a["id"], "name": a["name"], "version": a["version"], "kind": a["kind"]}
    if a["title_id"]:
        out["title_id"] = a["title_id"]
    out["port"] = a["port"] or None
    out["health"] = a["health"] or None
    for k in ("pages", "provides", "consumes", "public_pages", "page_apis"):
        out[k] = a["card"].get(k, {} if k == "pages" else [])
    if a["autoload"]:
        out["autoload"] = a["autoload"]
    if a["started_by"]:
        out["started_by"] = a["started_by"]
    if a.get("runtime") is not None:
        out["runtime"] = a["runtime"]
    if a["dyn"]:
        out["port_from"] = "runtime"
        out["live_port"] = None
        if a.get("runtime_note"):
            out["runtime_note"] = a["runtime_note"]
    out.update(verified=a["verified"], status=a["status"])
    if a.get("why"):
        out["why"] = a["why"]
    out.update(up=False, checked=False)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath("fake-console-root")
    os.makedirs(root, exist_ok=True)
    fc = FakeConsole(root).start()
    print(json.dumps({"ftp": fc.ftp_port, "loader": fc.loader_port, "websrv": fc.websrv_port, "root": root}), flush=True)
    threading.Event().wait()
