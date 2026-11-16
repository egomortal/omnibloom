"""Storage on the PS5: the report (sizes per category, recognised vs not recognised files) and the clean-ups (only
trash, old parked copies, icons cache and big logs; never settings, personal data, the profile or unknown files).
The console is a dict with a delete; one run goes over real FTP against the fake console (DELE answers 226)."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import config, storage  # noqa: E402

O = "/data/omni/"
S = storage.SAVED
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)
OLD = "20261001T101010Z"      # 46 days before NOW
NEW = "20261110T101010Z"      # 6 days before NOW
MB = 1024 * 1024


class Console:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.deleted = []

    def _dirs(self):
        out = set()
        for p in self.files:
            parts = p.split("/")
            for i in range(2, len(parts)):
                out.add("/".join(parts[:i]))
        return out

    def listing(self, parent):
        parent = parent.rstrip("/")
        out = {}
        for p, size in self.files.items():
            head, name = p.rsplit("/", 1)
            if head == parent:
                out[name] = {"dir": False, "size": size}
        for d in self._dirs():
            head, name = d.rsplit("/", 1)
            if head == parent:
                out[name] = {"dir": True, "size": 0}
        return out

    def delete(self, path):
        self.deleted.append(path)
        del self.files[path]


def omni():
    return Console({
        config.TITLE_DIR + "eboot.bin": 30 * MB,
        config.TITLE_DIR + "sce_sys/param.json": 2000,
        O + "native/omni-engine-child.elf": 80 * MB,
        O + "native/omni-engine-child.elf.before-setup-" + OLD: 79 * MB,
        O + "native/omni-engine-child.elf.before-setup-" + NEW: 79 * MB,
        O + "native/boot.log": 12 * MB,
        O + "native/boot.log.1": 3 * MB,
        O + "media-downloads.log": 11 * MB,
        O + "fonts/DejaVuSans.ttf": 700000,
        O + "browser-settings.txt": 300,
        O + "browser-settings.txt.before-setup-" + OLD: 290,
        O + "bookmarks.txt": 5000,
        O + "bookmarks.txt.before-setup-" + OLD: 4000,
        O + "history.txt": 90000,
        O + "passwords.txt": 800,
        O + "browser-mode.flag": 2,
        O + "reading-list/index.tsv": 100,
        O + "reading-list/a.example-20261110-101010.html": 50000,
        O + "reading-list/a.example-20261110-101010.html.before-setup-" + OLD: 40000,
        O + "browser-profile/Cookies": 100000,
        O + "browser-profile/cache/secret-site.example.bin": 9 * MB,
        O + "browser-profile/cache/old.before-setup-" + OLD: 1000,
        O + "icons/a.example.png": 3000,
        O + "yttl/r1-01-00001.png": 7000,
        S + "Screenshots/news.example-20261110-101010.png": 900000,
        S + "film.mp4": 700 * MB,
        S + "song.mp3": 5 * MB,
        S + "Music/tune.flac": 30 * MB,
        S + "doc.pdf": 200000,
        S + "keep.before-setup-" + OLD: 1234,
        S + ".trash/old-film.mkv": 400 * MB,
        S + ".trash/Music/gone.mp3": 4 * MB,
        storage.DL + "media-worker/work/part.tmp": 20 * MB,
        "/data/omni-downloader/worker/worker.py": 90000,
        "/data/omni-downloader/state/jobs.json": 40000,
        "/data/omni-downloader/state/schedule.json.before-setup-" + OLD: 300,
        "/data/omni-downloader/jdownloader/setup-backup/20261001T101010Z/a.jar": 2 * MB,
        "/data/hub/receipts/omni.json": 900,
        "/data/hub/receipts/omni.json.prev-20261001T101010Z": 880,
        "/data/hub/apps/omni.json": 500,
        "/data/pldmgr/autoload.txt": 100,
        "/data/pldmgr/autoload.txt.before-omnibloom-20261001T101010Z": 90,
        O + "mystery/blob.dat": 6 * MB,
        O + "weird name.xyz": 10,
        "/data/someone-else/big.bin": 999 * MB,
    })


def rows(rep):
    return {r["id"]: r for r in rep["rows"]}


class Report(unittest.TestCase):
    def test_sizes_per_category_sorted(self):
        c = omni()
        rep = storage.scan(c)
        r = rows(rep)
        self.assertEqual(r["dl-saved"]["bytes"], 700 * MB + 5 * MB + 30 * MB + 200000 + 1234)
        self.assertEqual(r["dl-trash"]["bytes"], 404 * MB)
        self.assertEqual(r["dl-trash"]["files"], 2)
        self.assertEqual(r["engine"]["bytes"], 80 * MB + 700000)
        self.assertEqual(r["parked"]["bytes"], 158 * MB + 290 + 4000)
        self.assertEqual(r["logs"]["bytes"], 26 * MB)
        self.assertEqual(r["app"]["bytes"], 30 * MB + 2000)
        self.assertEqual(r["reading-list"]["bytes"], 90100)
        self.assertEqual(r["profile"]["bytes"], 100000 + 9 * MB + 1000)
        self.assertEqual(r["icons"]["bytes"], 10000)
        self.assertEqual(r["old-copies"]["bytes"], 2 * MB + 880 + 90)
        self.assertEqual(r["dl-lists"]["files"], 2)
        self.assertEqual(r["dl-work"]["bytes"], 20 * MB)
        self.assertEqual(rep["types"], {"video": 700 * MB, "audio": 35 * MB, "pdf": 200000, "other": 1234})
        sizes = [x["bytes"] for x in rep["rows"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(rep["total"], sum(sizes))
        self.assertNotIn(999 * MB, sizes)                        # not Omni's: not counted
        self.assertEqual(c.deleted, [])                          # the report changes nothing

    def test_recognised_and_unknown(self):
        rep = storage.scan(omni())
        self.assertEqual(rep["unknown"], [O + "mystery/blob.dat", O + "weird name.xyz"])
        self.assertEqual(rows(rep)["unknown"]["bytes"], 6 * MB + 10)
        self.assertEqual(storage.classify(O + "bookmarks.txt"), ("personal", None))
        self.assertEqual(storage.classify(O + "browser-settings.txt"), ("settings", None))
        self.assertEqual(storage.classify(O + "browser-mode.flag"), ("settings", None))
        self.assertEqual(storage.classify(O + "passwords.txt"), ("settings", None))
        self.assertEqual(storage.classify(S + "keep.before-setup-" + OLD), ("dl-saved", "other"))
        self.assertIsNone(storage.classify("/data/hub/apps/omni.json"))
        self.assertIsNone(storage.classify("/data/omni/../etc/x"))
        self.assertEqual(storage.classify("/data/pldmgr/autoload.txt.before-omnibloom-x"), ("old-copies", None))

    def test_profile_names_never_kept(self):
        rep = storage.scan(omni())
        text = repr(rep)
        self.assertNotIn("Cookies", text)
        self.assertNotIn("secret-site", text)

    def test_free_space(self):
        rep = storage.scan(omni())
        self.assertIsNone(rep["free"])
        self.assertIn("free-space", rep["free_note"])
        c = omni()
        c.free_space = lambda: 50 * 1024 * MB
        self.assertEqual(storage.scan(c)["free"], 50 * 1024 * MB)

    def test_text_helpers(self):
        self.assertEqual(storage.size_text(2 * 1024 * MB), "2.0 GB")
        self.assertEqual(storage.size_text(1500), "2 KB")
        self.assertEqual(storage.bar(5, 10, 10), "#####")
        self.assertEqual(storage.bar(0, 10), "")
        self.assertIn("videos 700.0 MB", storage.types_text({"video": 700 * MB}))


class CleanUp(unittest.TestCase):
    def setUp(self):
        self.c = omni()
        self.rep = storage.scan(self.c)

    def paths(self, action):
        return [i["path"] for i in storage.candidates(self.rep, action, now=NOW)]

    def test_selection(self):
        self.assertEqual(sorted(self.paths("empty-trash")), [S + ".trash/Music/gone.mp3", S + ".trash/old-film.mkv"])
        self.assertEqual(self.paths("old-parked"), [O + "native/omni-engine-child.elf.before-setup-" + OLD])
        self.assertEqual(sorted(self.paths("icons")), [O + "icons/a.example.png", O + "yttl/r1-01-00001.png"])
        self.assertEqual(sorted(self.paths("big-logs")), [O + "media-downloads.log", O + "native/boot.log"])

    def test_never_settings_or_personal(self):
        everything = set()
        for a in storage.ACTIONS:
            everything |= set(self.paths(a["id"]))
        for p in self.c.files:
            got = storage.classify(p)
            if got and got[0] in ("settings", "personal", "profile", "reading-list", "dl-saved", "dl-lists",
                                  "screenshots", "unknown", "app", "engine", "dl-work", "old-copies"):
                self.assertNotIn(p, everything, p)
        for p in (O + "bookmarks.txt.before-setup-" + OLD, O + "browser-settings.txt.before-setup-" + OLD,
                  O + "reading-list/a.example-20261110-101010.html.before-setup-" + OLD,
                  O + "browser-profile/cache/old.before-setup-" + OLD, S + "keep.before-setup-" + OLD,
                  "/data/omni-downloader/state/schedule.json.before-setup-" + OLD):
            self.assertNotIn(p, everything, p)
            for a in storage.ACTIONS:
                self.assertFalse(storage.safe_to_delete(p, a["id"], 1, NOW))
        for p in (O + "passwords.txt", O + "bookmarks.txt", config.SETTINGS_PATH, O + "native/boot.log/../x.log",
                  S + "film.mp4", O + "mystery/blob.dat"):
            for a in storage.ACTIONS:
                self.assertFalse(storage.safe_to_delete(p, a["id"], 50 * MB, NOW), (p, a["id"]))

    def test_confirmation_lists_every_file(self):
        items = storage.candidates(self.rep, "empty-trash", now=NOW)
        head, lines = storage.confirmation("empty-trash", items)
        self.assertIn("2 files", head)
        self.assertIn("404.0 MB", head)
        self.assertEqual(len(lines), 2)
        for i in items:
            self.assertTrue(any(l.startswith(i["path"] + "  (") for l in lines))

    def test_clean_deletes_exactly_the_confirmed_list(self):
        items = storage.candidates(self.rep, "big-logs", now=NOW)[:1]
        r = storage.clean(self.c, "big-logs", items, now=NOW)
        self.assertEqual(r, {"deleted": 1, "bytes": 12 * MB, "skipped": 0})
        self.assertEqual(self.c.deleted, [O + "native/boot.log"])
        self.assertIn(O + "media-downloads.log", self.c.files)

    def test_clean_rechecks(self):
        items = storage.candidates(self.rep, "empty-trash", now=NOW)
        self.c.files[S + ".trash/old-film.mkv"] = 1                   # changed since the list was made
        forged = items + [{"path": O + "bookmarks.txt", "size": 5000}, {"path": S + "film.mp4", "size": 700 * MB}]
        r = storage.clean(self.c, "empty-trash", forged, now=NOW)
        self.assertEqual((r["deleted"], r["skipped"]), (1, 3))
        self.assertEqual(self.c.deleted, [S + ".trash/Music/gone.mp3"])
        with self.assertRaises(storage.StorageError):
            storage.clean(self.c, "everything", items)

    def test_parked_age(self):
        p = O + "native/x.elf.before-setup-" + NEW
        self.assertFalse(storage.safe_to_delete(p, "old-parked", 1, NOW))
        self.assertTrue(storage.safe_to_delete(p, "old-parked", 1, NOW + datetime.timedelta(days=31)))
        self.assertFalse(storage.safe_to_delete(O + "native/x.elf.before-setup-garbage", "old-parked", 1, NOW))


class OverFtp(unittest.TestCase):
    def test_report_and_trash_over_ftp(self):
        try:
            from tests.fake_console import FakeConsole
        except ImportError:
            from fake_console import FakeConsole
        from omnibloom_setup import ps5
        tmp = tempfile.mkdtemp(prefix="omnibloom-storage-")
        fc = FakeConsole(os.path.join(tmp, "c"), websrv=False).start()
        try:
            fc.write(S + ".trash/Music/gone.mp3", b"x" * 300)
            fc.write(S + "film.mp4", b"y" * 500)
            fc.write(O + "bookmarks.txt", b"https://a.example/\tA\n")
            fc.write(O + "browser-profile/Cookies", b"c" * 40)
            with ps5.Console("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, timeout=10) as c:
                rep = storage.scan(c)
                r = rows(rep)
                self.assertEqual((r["dl-trash"]["bytes"], r["dl-saved"]["bytes"], r["profile"]["bytes"]), (300, 500, 40))
                items = storage.candidates(rep, "empty-trash")
                res = storage.clean(c, "empty-trash", items)
            self.assertEqual(res["deleted"], 1)
            self.assertFalse(fc.exists(S + ".trash/Music/gone.mp3"))
            self.assertFalse(fc.exists(S + ".trash/Music"))           # emptied folder pruned
            self.assertTrue(fc.exists(S + ".trash"))
            self.assertTrue(fc.exists(S + "film.mp4") and fc.exists(O + "bookmarks.txt"))
            self.assertTrue(fc.exists(O + "browser-profile/Cookies"))
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
