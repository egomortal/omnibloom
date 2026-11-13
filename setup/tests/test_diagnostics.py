"""Diagnostics: only technical files are read, personal details are removed, the zip lands where asked."""
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
            "aa:bb:cc:dd:ee:ff", "secret-session-value", "my-bank.com"]


class Console:
    def __init__(self, files):
        self.files = files
        self.reads = []

    def exists(self, path):
        return path in self.files

    def read(self, path, limit=None):
        self.reads.append(path)
        return self.files[path]

    def listing(self, directory):
        out = {}
        for p, data in self.files.items():
            if posixpath.dirname(p) == directory:
                out[posixpath.basename(p)] = {"dir": False, "size": len(data)}
        for p in self.files:
            parent = posixpath.dirname(posixpath.dirname(p))
            if parent == directory:
                out[posixpath.basename(posixpath.dirname(p))] = {"dir": True, "size": 0}
        return out


def console():
    return Console({
        "/data/omni/native/boot.log": (b"[0.5] children: engine /data/omni/native/omni-engine-child.elf\n"
                                       b"browser: YTTL run 0: https://www.youtube.com/watch?v=LXb3EKWsInQ\n"
                                       b"page: OMNI_YTGUARD on /watch vid=LXb3EKWsInQ host www.youtube.com\n"
                                       b"net: connect 10.20.30.40:2121 from someone@example.com password=hunter2\n"
                                       b"pad aa:bb:cc:dd:ee:ff cookie: SID=secret-session-value\n"),
        "/data/omni/native/crash.log": b"crash diagnostics: OMNI_CRASH_V2 process pid=152 base=400000\n",
        "/data/omni/media-downloads.log": b"1794 fetch 8765/healthz -> state=0 status=200 body=48 12ms {\"service\":\"omni-media-worker\"}\n",
        "/data/hub/status.json": json.dumps({"apps": [{"id": "downloads", "port": 8765, "up": True}],
                                             "last_url": "https://news.example.org/story?id=7"}).encode(),
        "/data/hub/apps/downloads.json": b'{"id":"downloads","port":8765,"health":"/api/health"}',
        "/data/pldmgr/autoload.txt": b"/data/pldmgr/payloads/BloomCore/hub.elf\n",
        "/data/omni/browser-mode.flag": b"1\n",
        "/data/omni/ytguard-off.flag": b"1\n",
        "/data/homebrew/PPSA99732/addons/dark-reader/manifest.json": b"{}",
        # must never be read:
        "/data/omni/browser-profile/History.db": b"https://my-bank.com/account",
        "/data/omni/downloads/video.mp4": b"\x00",
        "/data/omni/bookmarks.json": b'["https://my-bank.com"]',
    })


class Diagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c = console()
        self.path = diagnostics.collect(self.c, os.path.join(self.tmp, "d.zip"), setup_version="test", log=lambda *_: None)
        self.z = zipfile.ZipFile(self.path)
        self.text = "\n".join(self.z.read(n).decode("utf-8", "replace") for n in self.z.namelist())

    def test_no_personal_details_survive(self):
        for p in PERSONAL:
            self.assertNotIn(p, self.text, p)

    def test_private_places_are_never_read(self):
        for path in self.c.reads:
            self.assertFalse(path.startswith("/data/omni/browser-profile") or path.startswith("/data/omni/downloads")
                             or "bookmarks" in path, path)

    def test_technical_content_is_kept(self):
        boot = self.z.read("omni/boot.log").decode()
        self.assertIn("/data/omni/native/omni-engine-child.elf", boot)
        self.assertIn("<https-address>", boot)
        self.assertIn("127.0.0.1", diagnostics.redact("http://127.0.0.1:8765/downloads")[0])
        self.assertIn("state=0 status=200", self.z.read("omni/media-downloads.log").decode())
        self.assertIn("browser-mode.flag", self.z.read("omni/flags.txt").decode())
        self.assertIn("dark-reader/", self.z.read("omni/addons.txt").decode())
        self.assertIn("bloom-core/apps/downloads.json", self.z.namelist())

    def test_readme_explains_and_counts(self):
        readme = self.z.read("README.txt").decode()
        self.assertIn("Nothing was sent anywhere", readme)
        removed = json.loads(self.z.read("summary.json"))["removed"]
        for what in ("web addresses", "site names", "IP addresses", "e-mail addresses", "video and playlist IDs"):
            self.assertGreater(removed.get(what, 0), 0, what)

    def test_default_folder_is_downloads_when_there(self):
        self.assertTrue(diagnostics.default_folder().endswith("Downloads") or os.path.isdir(diagnostics.default_folder()))

    def test_version_like_numbers_and_file_names_stay(self):
        clean, _ = diagnostics.redact("Mesa 26.2.0 libSceAgc.sprx app.js boot.log uv=1234567")
        self.assertEqual(clean, "Mesa 26.2.0 libSceAgc.sprx app.js boot.log uv=1234567")


if __name__ == "__main__":
    unittest.main()
