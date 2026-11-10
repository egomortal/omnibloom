# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end PC test of the bridge with the real JDownloader 2 core and egress policy omni-public-only-v1.

    python jdownloader/java/tests/bridge_e2e.py --jd "<your JDownloader 2 folder>" --classes <compiled classes> --out <scratch>

Copies JDownloader 2's program files (jars, libs, plugins; never cfg/, logs or accounts) into <out>/runtime, starts
OmniJDownloaderBridge the way java-worker.elf does (same class path order, headless, private ROOT/home/tmp), then
speaks the bridge protocol (4-byte length + JSON, session token):
  * health must report egress_policy == "omni-public-only-v1" once JDownloader is ready;
  * private targets (loopback by name, literal, numeric forms, a public DNS name answering 127.0.0.1, a public page
    redirecting to loopback) are refused and a local "secret" server is never contacted;
  * a public file downloads completely through the guard.
Writes <out>/bridge-e2e-receipt.json.
"""
import argparse
import hashlib
import http.server
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

SKIP = {"cfg", "logs", "tmp", "update", "jre", "java", "backup", "captchas", "downloads"}


class Secret(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        Secret.hits.append(self.path)
        body = b"secret" * 100
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


def copy_jd(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        full = os.path.join(src, name)
        if name in SKIP or name.lower().endswith((".exe", ".log", ".vmoptions")):
            continue
        if os.path.isdir(full):
            shutil.copytree(full, os.path.join(dst, name), dirs_exist_ok=True)
        else:
            shutil.copy2(full, os.path.join(dst, name))


def classpath(runtime, classes):
    parts = [classes, os.path.join(runtime, "Core.jar"), os.path.join(runtime, "JDownloader.jar")]
    for sub in ("libs", "extensions"):
        d = os.path.join(runtime, sub)
        if os.path.isdir(d):
            parts += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".jar")]
    return os.pathsep.join(parts + [runtime])


class Bridge:
    def __init__(self, ready):
        info = json.load(open(ready, encoding="utf-8"))
        self.port, self.token, self.session = info["port"], info["token"], info["session"]

    def call(self, action, **fields):
        req = dict(fields, action=action, token=self.token, session=self.session)
        data = json.dumps(req).encode()
        with socket.create_connection(("127.0.0.1", self.port), timeout=30) as s:
            s.sendall(struct.pack(">i", len(data)) + data)
            head = b""
            while len(head) < 4:
                chunk = s.recv(4 - len(head))
                if not chunk:
                    raise IOError("closed")
                head += chunk
            n = struct.unpack(">i", head)[0]
            body = b""
            while len(body) < n:
                chunk = s.recv(n - len(body))
                if not chunk:
                    raise IOError("closed")
                body += chunk
        return json.loads(body)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jd", required=True)
    p.add_argument("--classes", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--jdk")
    p.add_argument("--public-url", default="http://www.rfc-editor.org/rfc/rfc2606.txt")
    p.add_argument("--public-text", default="Reserved Top Level DNS Names")
    a = p.parse_args()
    out = os.path.abspath(a.out)
    shutil.rmtree(out, ignore_errors=True)
    runtime, home, tmp, downloads, state = (os.path.join(out, d) for d in ("runtime", "home", "tmp", "downloads", "state"))
    for d in (home, tmp, downloads, state):
        os.makedirs(d)
    copy_jd(a.jd, runtime)
    classes = os.path.join(runtime, "classes")
    shutil.copytree(a.classes, classes)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Secret)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    sp = server.server_address[1]

    ready = os.path.join(state, "ready.json")
    config = os.path.join(state, "config.json")
    json.dump({"token": secrets.token_hex(32), "session": secrets.token_hex(16), "install_id": "pc-e2e",
               "downloads": downloads, "max_seconds": 3600, "idle_seconds": 900, "port": 0, "ready_file": ready},
              open(config, "w", encoding="utf-8"))
    java = os.path.join(a.jdk, "bin", "java") if a.jdk else "java"
    cmd = [java, "-Xms16m", "-Xmx256m", "-XX:+UseSerialGC", "-XX:ActiveProcessorCount=2", "-Djava.awt.headless=true",
           "-Duser.timezone=UTC", "-cp", classpath(runtime, classes), "-DROOT=" + runtime, "-Duser.home=" + home,
           "-Djava.io.tmpdir=" + tmp, "OmniJDownloaderBridge", config]
    log = open(os.path.join(out, "bridge-stdout.log"), "w", encoding="utf-8", errors="replace")
    started = time.time()
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=runtime)
    results, checks = {}, []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else " :: " + str(detail)[:300]), flush=True)

    try:
        while not os.path.exists(ready):
            if proc.poll() is not None:
                raise SystemExit("bridge exited early: %s" % proc.returncode)
            time.sleep(0.2)
        b = Bridge(ready)
        results["bridge_listening_seconds"] = round(time.time() - started, 1)
        health = b.call("health")
        check("health before ready withholds the policy", health.get("egress_policy") in (None, "") and health["egress"]["guard"], health)
        deadline = time.time() + 900
        while time.time() < deadline:
            health = b.call("health")
            if health.get("ready") or health.get("startup_error"):
                break
            time.sleep(1)
        results["jd_ready_seconds"] = round(time.time() - started, 1)
        results["health"] = health
        check("JDownloader core ready", health.get("ready") is True, health.get("startup_error"))
        check("health reports egress_policy omni-public-only-v1", health.get("egress_policy") == "omni-public-only-v1", health.get("egress"))
        eg = health.get("egress") or {}
        check("every layer reported healthy", all(eg.get(k) is True for k in ("guard", "resolver", "proxy_selector", "socket_factory", "jd_proxy")), eg)

        def run_job(url, expect_complete, wait=75):
            jid = secrets.token_hex(8)
            r = b.call("submit", id=jid, url=url)
            if not r.get("ok"):
                return {"submitted": False, "error": r.get("error")}
            end = time.time() + wait
            st = {}
            while time.time() < end:
                st = b.call("status", id=jid)
                if st.get("state") in ("completed", "failed", "cancelled"):
                    break
                time.sleep(1)
            final = dict(st)
            if final.get("state") not in ("completed", "failed", "cancelled"):
                b.call("cancel", id=jid)
            for _ in range(120):
                r = b.call("release", id=jid)
                if r.get("ok"):
                    break
                time.sleep(1)
            final["released"] = bool(r.get("ok"))
            final["submitted"] = True
            return final

        private = {
            "loopback literal": "http://127.0.0.1:%d/file.bin" % sp,
            "loopback numeric": "http://2130706433:%d/file.bin" % sp,
            "loopback ipv6": "http://[::1]:%d/file.bin" % sp,
            "localhost name": "http://localhost:%d/file.bin" % sp,
            "LAN literal": "http://192.168.1.1/file.bin",
            "metadata address": "http://169.254.169.254/latest/meta-data/",
            "public name, loopback answer (localtest.me)": "http://localtest.me:%d/file.bin" % sp,
            "public name, loopback answer (127.0.0.1.nip.io)": "http://127.0.0.1.nip.io:%d/file.bin" % sp,
            "public page redirecting to loopback (httpbin)": "https://httpbin.org/redirect-to?url=http%%3A%%2F%%2F127.0.0.1%%3A%d%%2Fsecret.bin" % sp,
        }
        results["private"] = {}
        for label, url in private.items():
            before = len(Secret.hits)
            outcome = run_job(url, False)
            results["private"][label] = outcome
            reached = len(Secret.hits) - before
            check("private target refused: " + label, reached == 0 and outcome.get("state") != "completed",
                  dict(outcome, secret_hits=reached))
        health = b.call("health")
        results["refused_after_private"] = health.get("egress")
        check("guard counted refusals", (health.get("egress") or {}).get("refused", 0) + (health.get("egress") or {}).get("refused_direct", 0) > 0, health.get("egress"))
        check("policy still active after refusals", health.get("egress_policy") == "omni-public-only-v1", health.get("egress"))

        t0 = time.time()
        pub = run_job(a.public_url, True, wait=240)
        results["public"] = dict(pub, seconds=round(time.time() - t0, 1))
        path = pub.get("filepath") or ""
        content_ok = False
        if path and os.path.isfile(path):
            data = open(path, "rb").read()
            results["public"]["bytes"] = len(data)
            results["public"]["sha256"] = hashlib.sha256(data).hexdigest()
            content_ok = a.public_text.encode() in data
        check("public file downloaded through the guard", pub.get("state") == "completed" and content_ok, pub)
        check("secret server never contacted", len(Secret.hits) == 0, Secret.hits)
        health = b.call("health")
        results["final_health"] = health
        check("guard allowed public connections", (health.get("egress") or {}).get("allowed", 0) > 0, health.get("egress"))
        r = b.call("shutdown")
        results["shutdown"] = r
    finally:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        server.shutdown()
    version = subprocess.run([java, "-version"], capture_output=True, text=True).stderr.splitlines()[0]
    receipt = {"schema": "omni-jd-bridge-e2e/v1", "policy": "omni-public-only-v1",
               "passed": all(c["ok"] for c in checks), "checks": checks, "results": results, "java": version,
               "jd_build": json.load(open(os.path.join(runtime, "build.json"), encoding="utf-8")) if os.path.exists(os.path.join(runtime, "build.json")) else None,
               "bridge_exit_code": proc.returncode, "console_contacted": False, "target_tested": False}
    with open(os.path.join(out, "bridge-e2e-receipt.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(receipt, f, indent=1, sort_keys=True, default=str)
        f.write("\n")
    print("RECEIPT", os.path.join(out, "bridge-e2e-receipt.json"), "passed" if receipt["passed"] else "FAILED")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
