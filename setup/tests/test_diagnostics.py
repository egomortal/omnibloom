"""Diagnostics bundle: only technical files are read, personal details are redacted, caps hold, the zip is complete."""
import json
import os
import posixpath
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import diagnostics  # noqa: E402

PERSONAL = ["www.youtube.com", "LXb3EKWsInQ", "10.20.30.40", "someone@example.com", "hunter2", "news.example.org",
            "aa:bb:cc:dd:ee:ff", "secret-session-value", "my-bank.com", "PlayerOne", "9f86d081884c7d659a2feaa0c55ad015"]

NEVER_FILES = {
    "/data/omni/browser-profile/History.db": b"https://my-bank.com/account",
    "/data/omni/browser-profile/Cookies": b"my-bank.com",
    "/data/omni/downloads/video.mp4": b"\x00",
    "/data/omni/bookmarks.txt": b"https://my-bank.com\tBank\n",
    "/data/omni/bookmarks.json": b'["https://my-bank.com"]',
    "/data/omni/history.txt": b"https://my-bank.com\n",
    "/data/omni/passwords.txt": b"my-bank.com hunter2\n",
    "/data/omni/passwords.key": b"k",
    "/data/omni/cookies.txt": b"SID=secret-session-value\n",
    "/data/omni/session.txt": b"https://my-bank.com\n",
    "/data/omni/kb-words.txt": b"hunter2\n",
    "/data/omni/apps.json": b'[{"url":"https://my-bank.com"}]',
    "/data/omni/reading-list/index.tsv": b"my-bank.com\n",
    "/data/omni/reading-list/my-bank.com.html": b"<html>",
    "/data/omni/screenshots/shot1.png": b"\x89PNG",
    "/data/omni/browser-settings.txt": b"home=https://my-bank.com\n",
    "/data/omni/quick-access.txt": b"https://my-bank.com\n",
    "/data/omni/dark-style.txt": b"my-bank.com\n",
    "/data/omni/native/sec-blocked.txt": b"my-bank.com\n",
    "/data/omni-downloader/state/jobs.json": b'{"url":"https://my-bank.com"}',
    "/data/omni-downloader/state/saved-links.json": b'{"url":"https://my-bank.com"}',
}


class Console:
    def __init__(self, files, with_read_from=True):
        self.files = dict(files)
        self.reads = []
        if not with_read_from:
            self.read_from = None

    def exists(self, path):
        return path in self.files

    def read(self, path, limit=None):
        self.reads.append(path)
        return self.files[path]

    def read_from(self, path, offset):
        self.reads.append(path)
        return self.files[path][offset:]

    def read_text(self, path, default=None):
        if path not in self.files:
            return default
        self.reads.append(path)
        return self.files[path].decode("utf-8", "replace")

    def listing(self, directory):
        directory = directory.rstrip("/")
        out = {}
        for p, data in self.files.items():
            if posixpath.dirname(p) == directory:
                out[posixpath.basename(p)] = {"dir": False, "size": len(data)}
        for p in self.files:
            d = posixpath.dirname(p)
            while d and d != "/":
                if posixpath.dirname(d) == directory:
                    out[posixpath.basename(d)] = {"dir": True, "size": 0}
                d = posixpath.dirname(d)
        return out


def files():
    receipt = {"schema": "hub-receipt/v1", "id": "omni", "name": "Omni", "version": "0.5.1", "package": "omni-0.5.1.zip",
               "installed_at": "2026-11-15T10:00:00Z", "setup_version": "0.5.0", "port": None,
               "history": [{"version": "0.5.0", "installed_at": "2026-11-01T10:00:00Z"}]}
    out = {
        "/data/omni/native/boot.log": (b"[0.5] children: engine /data/omni/native/omni-engine-child.elf\n"
                                       b"browser: YTTL run 0: https://www.youtube.com/watch?v=LXb3EKWsInQ\n"
                                       b"page: OMNI_YTGUARD on /watch vid=LXb3EKWsInQ host www.youtube.com\n"
                                       b"net: connect 10.20.30.40:2121 from someone@example.com password=hunter2\n"
                                       b"pad aa:bb:cc:dd:ee:ff cookie: SID=secret-session-value\n"
                                       b"user PlayerOne signed in, save /user/home/1a2b3c4d/x\n"
                                       b"pkg sha 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08\n"),
        "/data/omni/native/starter.log": b"starter: launched title pid=88\n",
        "/data/omni/native/crash.log": b"crash diagnostics: OMNI_CRASH_V2 process pid=152 base=400000\n",
        "/data/omni/media-downloads.log": b"1794 fetch 8765/healthz -> state=0 status=200 body=48 12ms\n",
        "/data/omni-downloader/jdownloader/native/java25-vm-trace.log": b"vm: started heap=256m\n",
        "/data/hub/logs/hub.log": b"hub: listening on 127.0.0.1:8765\n",
        "/data/hub/crash/2026-11-15.json": b'{"where":"https://news.example.org/story"}',
        "/data/hub/status.json": json.dumps({"apps": [{"id": "downloads", "port": 8765, "up": True}],
                                             "last_url": "https://news.example.org/story?id=7"}).encode(),
        "/data/hub/apps/downloads.json": b'{"id":"downloads","port":8765,"health":"/api/health"}',
        "/data/hub/receipts/omni.json": json.dumps(receipt).encode(),
        "/data/pldmgr/autoload.txt": b"/data/pldmgr/payloads/BloomCore/hub.elf\n",
        "/data/omni/browser-mode.flag": b"1\n",
        "/data/omni/ytguard-off.flag": b"1\n",
        "/data/omni/ui-theme.txt": b"dark\n",
        "/data/homebrew/PPSA99732/addons/dark-reader/manifest.json": b"{}",
    }
    out.update(NEVER_FILES)
    return out


def bundle_of(console, **kw):
    return diagnostics.gather(console, setup_version="test", user_names=["PlayerOne"], salt=b"t", **kw)


class Selection(unittest.TestCase):
    def setUp(self):
        self.c = Console(files())
        self.b = bundle_of(self.c)
        self.names = [e["name"] for e in self.b["entries"]]
        self.text = "\n".join(e["text"] for e in self.b["entries"])

    def test_never_list_is_never_read(self):
        for path in self.c.reads:
            self.assertNotIn(path, NEVER_FILES, path)
            self.assertTrue(diagnostics.content_allowed(path), path)

    def test_never_list_names_are_not_listed_either(self):
        listed = "\n".join(e["text"] for e in self.b["entries"] if e["source"].endswith("(names only)"))
        for bad in ("bookmarks", "history", "passwords", "cookies", "kb-words", "session", "apps.json",
                    "reading-list", "screenshots", "browser-profile", "downloads"):
            self.assertNotIn(bad, listed, bad)
        self.assertIn("sec-blocked.txt", listed)      # a technical name: listed, never read

    def test_gate(self):
        for p in list(NEVER_FILES) + ["/data/omni/anything.txt", "/user/home/1a2b3c4d/x.log", "/data/omni/session-2.json"]:
            self.assertFalse(diagnostics.content_allowed(p), p)
        for p in ("/data/omni/native/boot.log", "/data/hub/apps/downloads.json", "/data/pldmgr/autoload.txt"):
            self.assertTrue(diagnostics.content_allowed(p), p)

    def test_txt_settings_are_names_only(self):
        settings = next(e for e in self.b["entries"] if e["name"] == "omni/settings-files.txt")["text"]
        self.assertIn("ui-theme.txt", settings)
        self.assertNotIn("/data/omni/ui-theme.txt", self.c.reads)
        self.assertNotIn("dark\n", settings)

    def test_expected_files(self):
        for n in ("omni/boot.log", "omni/starter.log", "omni/crash.log", "omni/media-downloads.log",
                  "omni-downloader/java25-vm-trace.log", "bloom-core/logs/hub.log", "bloom-core/crash/2026-11-15.json",
                  "bloom-core/status.json", "bloom-core/apps/downloads.json", "bloom-core/receipts/omni.json",
                  "payload-manager/autoload.txt", "omni/flags.txt", "omni/addons.txt", "versions.json"):
            self.assertIn(n, self.names, n)
        flags = next(e for e in self.b["entries"] if e["name"] == "omni/flags.txt")["text"]
        self.assertEqual(flags, "browser-mode.flag\nytguard-off.flag\n")

    def test_versions(self):
        v = json.loads(next(e for e in self.b["entries"] if e["name"] == "versions.json")["text"])
        self.assertEqual(v["installed_apps"]["omni"]["version"], "0.5.1")
        self.assertEqual(v["installed_apps"]["omni"]["earlier_versions"], ["0.5.0"])
        self.assertEqual(v["setup_version"], "test")
        self.assertIsNone(v["free_space_bytes"])
        self.assertIn("free space", v["free_space_note"])

    def test_free_space_and_firmware_when_the_console_knows(self):
        c = Console(files())
        c.free_space = lambda: 123456789
        c.firmware = lambda: "13.60"
        v = json.loads(next(e for e in bundle_of(c)["entries"] if e["name"] == "versions.json")["text"])
        self.assertEqual((v["free_space_bytes"], v["firmware"]), (123456789, "13.60"))

    def test_no_personal_details_survive(self):
        for p in PERSONAL:
            self.assertNotIn(p, self.text, p)
        boot = next(e for e in self.b["entries"] if e["name"] == "omni/boot.log")["text"]
        self.assertIn("/data/omni/native/omni-engine-child.elf", boot)
        self.assertIn("<user>", boot)
        self.assertIn("<home>", boot)
        self.assertRegex(boot, r"https://<host-[0-9a-f]{6}>/…")

    def test_missing_files_are_noted(self):
        b = bundle_of(Console({"/data/omni/native/boot.log": b"x\n"}))
        self.assertTrue(any("starter.log: not on this PS5" in s for s in b["skipped"]))


class Caps(unittest.TestCase):
    def big_log(self, n):
        return b"".join(b"line %07d ok\n" % i for i in range(n))

    def test_logs_keep_the_newest_2mb(self):
        for with_rf in (True, False):
            data = self.big_log(250000)          # ~3.5 MB
            c = Console({"/data/omni/native/boot.log": data}, with_read_from=with_rf)
            e = next(e for e in bundle_of(c)["entries"] if e["name"] == "omni/boot.log")
            self.assertTrue(e["truncated"])
            self.assertLessEqual(e["bytes"], diagnostics.LOG_CAP)
            self.assertTrue(e["text"].endswith("line 0249999 ok\n"))
            self.assertTrue(e["text"].startswith("line "))      # cut at a line start

    def test_small_logs_are_whole(self):
        c = Console({"/data/omni/native/boot.log": b"a\nb\n"})
        e = next(e for e in bundle_of(c)["entries"] if e["name"] == "omni/boot.log")
        self.assertFalse(e["truncated"])
        self.assertEqual(e["text"], "a\nb\n")

    def test_big_json_is_left_out(self):
        c = Console({"/data/hub/status.json": b'{"x":"' + b"a" * (diagnostics.JSON_CAP + 10) + b'"}'})
        b = bundle_of(c)
        self.assertNotIn("bloom-core/status.json", [e["name"] for e in b["entries"]])
        self.assertTrue(any("status.json: left out" in s for s in b["skipped"]))

    def test_folder_file_count_cap(self):
        fs = {"/data/hub/logs/%02d.log" % i: b"x\n" for i in range(diagnostics.FOLDER_MAX_FILES + 4)}
        b = bundle_of(Console(fs))
        logs = [e for e in b["entries"] if e["name"].startswith("bloom-core/logs/")]
        self.assertEqual(len(logs), diagnostics.FOLDER_MAX_FILES)
        self.assertIn("bloom-core/logs/19.log", [e["name"] for e in logs])      # newest names kept
        self.assertTrue(any("older files left out" in s for s in b["skipped"]))

    def test_total_cap(self):
        old = diagnostics.TOTAL_CAP
        diagnostics.TOTAL_CAP = 1000
        try:
            c = Console({"/data/omni/native/boot.log": b"z " * 450 + b"\n", "/data/omni/native/starter.log": b"y " * 450})
            b = bundle_of(c)
        finally:
            diagnostics.TOTAL_CAP = old
        self.assertNotIn("omni/starter.log", [e["name"] for e in b["entries"]])
        self.assertTrue(any("left out (the bundle is already" in s for s in b["skipped"]))


class Zip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c = Console(files())
        self.b = bundle_of(self.c)

    def test_zip_contents_and_manifest(self):
        path = diagnostics.save(self.b, os.path.join(self.tmp, "sub", "d.zip"))
        self.assertFalse(os.path.exists(path + ".part"))
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            m = json.loads(z.read("manifest.json"))
            readme = z.read("README.txt").decode()
            body = "\n".join(z.read(n).decode("utf-8", "replace") for n in names)
        self.assertEqual(set(names), {e["name"] for e in self.b["entries"]} | {"manifest.json", "README.txt"})
        self.assertEqual(m["format"], "omnibloom-diagnostics")
        self.assertEqual([f["name"] for f in m["files"]], [e["name"] for e in self.b["entries"]])
        self.assertGreaterEqual(len(m["redaction_rules"]), 8)
        self.assertIn("bookmarks", m["never_collected"])
        for what in ("web addresses", "IP addresses", "e-mail addresses", "user names", "home folders",
                     "tokens and keys", "hardware addresses"):
            self.assertGreater(m["removed"].get(what, 0), 0, what)
        self.assertIn("Nothing was sent anywhere", readme)
        for p in PERSONAL:
            self.assertNotIn(p, body, p)

    def test_failed_save_leaves_no_zip(self):
        dest = os.path.join(self.tmp, "x.zip")
        bad = dict(self.b, entries=self.b["entries"] + [{"name": "bad", "source": "", "bytes": 0, "truncated": False,
                                                          "text": object()}])
        with self.assertRaises(Exception):
            diagnostics.save(bad, dest)
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))

    def test_preview_and_file_list(self):
        prev = diagnostics.preview(self.b)
        self.assertIn("== omni/boot.log ==", prev)
        self.assertNotIn("youtube", prev)
        self.assertLessEqual(len(prev.splitlines()), 40)
        fl = diagnostics.file_list(self.b)
        self.assertTrue(any(l.startswith("omni/boot.log  (") for l in fl))
        self.assertEqual(fl[-2:], ["manifest.json", "README.txt"])

    def test_collect_still_works_for_the_cli(self):
        path = diagnostics.collect(self.c, os.path.join(self.tmp, "c.zip"), setup_version="t", log=lambda *_: None)
        with zipfile.ZipFile(path) as z:
            self.assertIn("omni/boot.log", z.namelist())

    def test_default_path(self):
        self.assertTrue(os.path.basename(diagnostics.default_path("x")).startswith("omnibloom-diagnostics-"))


if __name__ == "__main__":
    unittest.main()
