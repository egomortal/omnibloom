"""Copy screenshots and saved downloads from the PS5 to the PC (pccopy).
A dict console (listing/read/makedirs/rename only: no delete exists) for the rules, plus runs over real FTP against
the fake console (LIST times, REST resume, the trash move, never a DELE)."""
import calendar
import os
import posixpath
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import pccopy  # noqa: E402

R = pccopy.ROOT + "/"
SHOT1 = "news.example-20261110-101010.png"
SHOT2 = "www.a.example-20261115-203000.png"
T_OLD = calendar.timegm((2026, 10, 1, 9, 0, 0))


def slurp(path):
    with open(path, "rb") as f:
        return f.read()


class DictConsole:
    """Files in a dict; folders are implied. Only listing, read, makedirs and rename: nothing can be deleted."""

    def __init__(self, files, mtimes=None):
        self.files = dict(files)
        self.mtimes = dict(mtimes or {})
        self.dirs = set()
        self.reads = []
        self.renames = []

    def listing(self, parent):
        parent = parent.rstrip("/")
        out = {}
        for p, d in self.files.items():
            if p.startswith(parent + "/"):
                rest = p[len(parent) + 1:]
                if "/" in rest:
                    out[rest.split("/", 1)[0]] = {"dir": True, "size": 0}
                else:
                    out[rest] = {"dir": False, "size": len(d), "mtime": self.mtimes.get(p)}
        for d in self.dirs:
            if posixpath.dirname(d) == parent:
                out.setdefault(posixpath.basename(d), {"dir": True, "size": 0})
        return out

    def read(self, path, limit=None):
        self.reads.append(path)
        return self.files[path]

    def makedirs(self, d):
        self.dirs.add(d.rstrip("/"))

    def rename(self, src, dst):
        self.renames.append((src, dst))
        self.files[dst] = self.files.pop(src)


def console(extra=None):
    files = {
        R + "Screenshots/" + SHOT1: b"\x89PNG-one" * 100,
        R + "Screenshots/" + SHOT2: b"\x89PNG-two" * 50,
        R + "Screenshots/.hidden.png": b"h",
        R + "film.mp4": b"MP4" * 1000,
        R + "Music/song.mp3": b"ID3" * 300,
        R + "Docs/manual.pdf": b"%PDF",
        R + ".trash/old.mp4": b"gone",
        R + ".trash/Screenshots/x-20260101-000000.png": b"t",
        "/data/omni/passwords.txt": b"secret",
    }
    files.update(extra or {})
    mt = {R + "film.mp4": T_OLD, R + "Music/song.mp3": T_OLD + 86400 * 30, R + "Docs/manual.pdf": T_OLD - 86400}
    return DictConsole(files, mt)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omnibloom-pccopy-")
        self.pics = os.path.join(self.dir, "Pictures", "Omnibloom")
        self.dls = os.path.join(self.dir, "Downloads", "Omnibloom")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_copy(self, c, items=None, **kw):
        kw.setdefault("free", lambda p: 1 << 40)
        return pccopy.copy(c, items if items is not None else pccopy.scan(c)["items"], self.pics, self.dls, **kw)

    def files_under(self, base):
        out = {}
        for dp, _dn, fns in os.walk(base):
            for fn in fns:
                p = os.path.join(dp, fn)
                out[os.path.relpath(p, base).replace("\\", "/")] = slurp(p)
        return out


class Listing(unittest.TestCase):
    def test_scan(self):
        s = pccopy.scan(console())
        rels = [i.rel for i in s["items"]]
        self.assertEqual(sorted(rels), sorted(["Screenshots/" + SHOT1, "Screenshots/" + SHOT2, "film.mp4",
                                               "Music/song.mp3", "Docs/manual.pdf"]))
        self.assertFalse(any(".trash" in r or ".hidden" in r for r in rels))
        by = {i.rel: i for i in s["items"]}
        self.assertEqual(by["Screenshots/" + SHOT2].kind, "screenshot")
        self.assertEqual(by["Screenshots/" + SHOT2].group, "screenshots")
        self.assertEqual(by["Screenshots/" + SHOT2].mtime, calendar.timegm((2026, 11, 15, 20, 30, 0)))
        self.assertEqual((by["film.mp4"].kind, by["Music/song.mp3"].kind, by["Docs/manual.pdf"].kind),
                         ("video", "audio", "other"))
        self.assertEqual(rels[0], "Screenshots/" + SHOT2)            # newest first
        self.assertEqual(by["film.mp4"].size, 3000)

    def test_select(self):
        items = pccopy.scan(console())["items"]
        self.assertEqual(len(pccopy.select(items, kinds={"screenshot"})), 2)
        since = calendar.timegm((2026, 11, 12, 0, 0, 0))
        self.assertEqual([i.name for i in pccopy.select(items, since=since)], [SHOT2])
        self.assertEqual([i.name for i in pccopy.select(items, kinds={"video", "other"}, until=T_OLD + 1)],
                         ["film.mp4", "manual.pdf"])

    def test_list_time(self):
        now = calendar.timegm((2026, 11, 16, 12, 0, 0))
        self.assertEqual(pccopy.parse_list_time("Nov", "16", "11:05", now), calendar.timegm((2026, 11, 16, 11, 5, 0)))
        self.assertEqual(pccopy.parse_list_time("Dec", "30", "11:05", now), calendar.timegm((2025, 12, 30, 11, 5, 0)))
        self.assertEqual(pccopy.parse_list_time("Jan", "2", "2024", now), calendar.timegm((2024, 1, 2, 0, 0, 0)))
        self.assertIsNone(pccopy.parse_list_time("Foo", "2", "2024", now))
        self.assertIsNone(pccopy.parse_list_time("Feb", "31", "2024", now))


class Copy(Tmp):
    def test_copy_and_layout(self):
        c = console()
        seen = []
        r = self.run_copy(c, progress=lambda d, t, i, n: seen.append((d, t)))
        self.assertEqual((r["copied"], r["same"], r["trashed"], r["failed"]), (5, 0, 0, []))
        self.assertEqual(self.files_under(self.pics), {SHOT1: c.files[R + "Screenshots/" + SHOT1],
                                                       SHOT2: c.files[R + "Screenshots/" + SHOT2]})
        dl = self.files_under(self.dls)
        self.assertEqual(sorted(dl), ["Docs/manual.pdf", "Music/song.mp3", "film.mp4"])
        self.assertEqual(dl["film.mp4"], b"MP4" * 1000)
        self.assertEqual(int(os.path.getmtime(os.path.join(self.dls, "film.mp4"))), T_OLD)
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertEqual(c.renames, [])                                 # read-only by default
        self.assertNotIn("/data/omni/passwords.txt", c.reads)

    def test_second_run_skips_identical(self):
        c = console()
        self.run_copy(c)
        c.reads.clear()
        r = self.run_copy(c)
        self.assertEqual((r["copied"], r["same"]), (0, 5))
        self.assertEqual(c.reads, [])                                   # size + time matched: nothing fetched

    def test_same_size_other_time_compared_by_hash(self):
        c = console()
        os.makedirs(self.dls)
        with open(os.path.join(self.dls, "film.mp4"), "wb") as f:      # same bytes, copied some other way
            f.write(b"MP4" * 1000)
        with open(os.path.join(self.dls, "Docs"), "wb"):                # a file where a folder must go
            pass
        os.makedirs(os.path.join(self.dls, "Music"))
        with open(os.path.join(self.dls, "Music", "song.mp3"), "wb") as f:   # same size, other bytes
            f.write(b"XXX" * 300)
        items = [i for i in pccopy.scan(c)["items"] if i.group == "downloads"]
        r = self.run_copy(c, items)
        self.assertEqual((r["copied"], r["same"], r["renamed"]), (1, 1, 1))
        self.assertEqual([x[0] for x in r["failed"]], ["Docs/manual.pdf"])
        self.assertEqual(slurp(os.path.join(self.dls, "Music", "song.mp3")), b"XXX" * 300)   # kept
        self.assertEqual(slurp(os.path.join(self.dls, "Music", "song (2).mp3")), b"ID3" * 300)
        self.assertFalse([n for n in os.listdir(self.dls) if n.endswith(".part")])
        c.reads.clear()
        r = self.run_copy(c, [i for i in items if i.name == "song.mp3"])
        self.assertEqual((r["copied"], r["same"]), (0, 1))              # the earlier "(2)" counts: no "(3)"
        self.assertEqual(c.reads, [])

    def test_resume_after_stop(self):
        c = console({R + "big.mkv": bytes(range(256)) * 4096})
        items = [i for i in pccopy.scan(c)["items"] if i.name == "big.mkv"]
        stop = threading.Event()

        def progress(done, total, i, n):
            if done >= 300000:
                stop.set()
        r = self.run_copy(c, items, progress=progress, cancel=stop)
        self.assertTrue(r["cancelled"])
        part = os.path.join(self.dls, "big.mkv.part")
        self.assertTrue(os.path.isfile(part))
        self.assertFalse(os.path.exists(os.path.join(self.dls, "big.mkv")))   # no half file under the real name
        have = os.path.getsize(part)
        self.assertTrue(0 < have < len(c.files[R + "big.mkv"]))
        with open(part, "r+b") as f:
            f.truncate(have - 5)                                        # a ragged end is fine too
        r = self.run_copy(c, items)
        self.assertEqual(r["copied"], 1)
        self.assertEqual(slurp(os.path.join(self.dls, "big.mkv")), c.files[R + "big.mkv"])
        self.assertFalse(os.path.exists(part))

    def test_oversized_part_restarts(self):
        c = console()
        os.makedirs(self.dls)
        with open(os.path.join(self.dls, "film.mp4.part"), "wb") as f:
            f.write(b"Z" * 5000)
        items = [i for i in pccopy.scan(c)["items"] if i.name == "film.mp4"]
        self.assertEqual(self.run_copy(c, items)["copied"], 1)
        self.assertEqual(slurp(os.path.join(self.dls, "film.mp4")), b"MP4" * 1000)

    def test_free_space(self):
        c = console()
        with self.assertRaises(pccopy.CopyError):
            self.run_copy(c, free=lambda p: 1000)
        self.assertFalse(os.path.exists(self.pics))
        items = pccopy.scan(c)["items"]
        self.assertEqual(pccopy.needed_bytes(items, self.pics, self.dls), sum(i.size for i in items))
        self.run_copy(c)
        self.assertEqual(pccopy.needed_bytes(items, self.pics, self.dls), 0)
        self.run_copy(c, free=lambda p: 1000)                            # nothing left to fetch: no space needed

    def test_default_folders(self):
        p, d = pccopy.default_folders("C:\\Users\\x")
        self.assertEqual(p, os.path.join("C:\\Users\\x", "Pictures", "Omnibloom"))
        self.assertEqual(d, os.path.join("C:\\Users\\x", "Downloads", "Omnibloom"))


class Trash(Tmp):
    def test_off_by_default_and_move(self):
        c = console({R + ".trash/film.mp4": b"older"})
        self.run_copy(c)
        self.assertEqual(c.renames, [])
        r = self.run_copy(c, move_to_trash=True)
        self.assertEqual((r["same"], r["trashed"]), (5, 5))
        moved = dict(c.renames)
        self.assertEqual(moved[R + "film.mp4"], R + ".trash/film (2).mp4")       # name taken in the trash
        self.assertEqual(moved[R + "Music/song.mp3"], R + ".trash/Music/song.mp3")
        self.assertEqual(moved[R + "Screenshots/" + SHOT1], R + ".trash/Screenshots/" + SHOT1)
        self.assertEqual(c.files[R + ".trash/film.mp4"], b"older")
        self.assertIn(R + ".trash/Music", c.dirs)
        self.assertEqual(pccopy.scan(c)["items"], [])                   # gone from the list, restorable in the app
        self.assertFalse(hasattr(c, "delete"))

    def test_failed_copy_not_trashed(self):
        c = console()
        items = [i for i in pccopy.scan(c)["items"] if i.name == "film.mp4"]
        c.files[R + "film.mp4"] = b"short"                              # changed after the listing
        r = self.run_copy(c, items, move_to_trash=True)
        self.assertEqual((r["copied"], r["trashed"]), (0, 0))
        self.assertIn("incomplete", r["failed"][0][1])
        self.assertEqual(c.renames, [])


class Malicious(Tmp):
    def test_names(self):
        evil = {
            R + "con.mp4": b"1", R + "Screenshots/aux.png": b"2", R + 'a<b>:c|d?e*f".mkv': b"3",
            R + "trail. . ": b"4", R + "bad\r\nRETR x.mp4": b"5", R + "..": b"6", R + "sub\\..\\..\\x.mp4": b"7",
            R + "L" * 200 + ".mp4": b"8", R + "COM1.txt": b"9", R + "Docs/lpt3": b"10",
        }
        c = DictConsole(evil)
        s = pccopy.scan(c)
        names = {i.name for i in s["items"]}
        self.assertNotIn("bad\r\nRETR x.mp4", names)
        self.assertNotIn("sub\\..\\..\\x.mp4", names)
        self.assertNotIn("..", names)
        self.assertGreaterEqual(s["skipped"], 2)
        r = self.run_copy(c, s["items"])
        self.assertEqual(r["failed"], [])
        got = set(self.files_under(self.dls)) | set(self.files_under(self.pics))
        self.assertIn("_con.mp4", got)
        self.assertIn("_aux.png", got)
        self.assertIn("_COM1.txt", got)
        self.assertIn("Docs/_lpt3", got)
        self.assertIn("a_b__c_d_e_f_.mkv", got)
        self.assertIn("trail", got)
        self.assertTrue(any(n.startswith("LLL") and n.endswith(".mp4") and len(n) <= pccopy.NAME_MAX for n in got))
        for base in (self.dls, self.pics):
            for dp, _dn, fns in os.walk(self.dir):
                for fn in fns:
                    self.assertTrue(os.path.realpath(os.path.join(dp, fn)).startswith(os.path.realpath(self.dir)))

    def test_hand_made_items_refused(self):
        c = console()
        bad = pccopy.Item("../../escape.mp4", "escape.mp4", 3, None, "video", "downloads")
        bad2 = pccopy.Item("Screenshots", "Screenshots", 3, None, "screenshot", "screenshots")
        r = self.run_copy(c, [bad, bad2])
        self.assertEqual(len(r["failed"]), 2)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "escape.mp4")))

    def test_windows_name(self):
        self.assertEqual(pccopy.windows_name("..."), "_")
        self.assertEqual(pccopy.windows_name("nul .txt"), "_nul .txt")
        self.assertEqual(pccopy.windows_name(" a\tb "), "a_b")


class OverFtp(unittest.TestCase):
    def test_ftp_copy_resume_trash(self):
        try:
            from tests.fake_console import FakeConsole
        except ImportError:
            from fake_console import FakeConsole
        from omnibloom_setup import ps5
        tmp = tempfile.mkdtemp(prefix="omnibloom-pcftp-")
        fc = FakeConsole(os.path.join(tmp, "c"), websrv=False).start()
        pics, dls = os.path.join(tmp, "P"), os.path.join(tmp, "D")
        big = bytes(range(256)) * 2048
        try:
            fc.write(R + "Screenshots/" + SHOT1, b"\x89PNG" * 10)
            fc.write(R + "Videos/clip.mp4", big)
            fc.write(R + ".trash/old.mp4", b"x")
            os.makedirs(os.path.join(dls, "Videos"))
            with open(os.path.join(dls, "Videos", "clip.mp4.part"), "wb") as f:
                f.write(big[:100000])                                   # an earlier copy stopped here
            with ps5.Console("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, timeout=10) as c:
                s = pccopy.scan(c)
                self.assertEqual(sorted(i.rel for i in s["items"]), ["Screenshots/" + SHOT1, "Videos/clip.mp4"])
                clip = [i for i in s["items"] if i.name == "clip.mp4"][0]
                self.assertIsNotNone(clip.mtime)                        # from the LIST line
                self.assertLess(abs(clip.mtime - os.path.getmtime(fc.path(R + "Videos/clip.mp4"))), 61)
                seen = []
                r = pccopy.copy(c, s["items"], pics, dls, progress=lambda d, t, i, n: seen.append(d),
                                free=lambda p: 1 << 40)
                self.assertEqual((r["copied"], r["failed"]), (2, []))
                self.assertEqual(slurp(os.path.join(dls, "Videos", "clip.mp4")), big)
                self.assertGreaterEqual(min(d for d in seen if d > 0), 100000 - 1)   # resumed, not refetched
                r = pccopy.copy(c, pccopy.scan(c)["items"], pics, dls, move_to_trash=True, free=lambda p: 1 << 40)
                self.assertEqual((r["copied"], r["same"], r["trashed"]), (0, 2, 2))
            self.assertEqual(fc.state["deletes"], [])
            self.assertEqual(fc.read(R + ".trash/Videos/clip.mp4"), big)
            self.assertTrue(fc.exists(R + ".trash/Screenshots/" + SHOT1))
            self.assertFalse(fc.exists(R + "Videos/clip.mp4"))
            self.assertEqual(fc.read(R + ".trash/old.mp4"), b"x")
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
