"""Import the PC's browser bookmarks into Omni (/data/omni/bookmarks.txt, `url TAB title` per line, up to 500).
Chrome / Edge / Brave / Firefox profiles are faked in a temp home; the console is a dict. Nothing already on the console
is removed, the old file is parked, and Omni's limits (count, line length, separators) are respected."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import bookmarks, config  # noqa: E402

PATH = config.OMNI_BOOKMARKS


class Console:
    def __init__(self, files=None):
        self.files = dict(files or {})

    def exists(self, path):
        return path in self.files

    def listing(self, parent):
        return {p.rsplit("/", 1)[1]: {} for p in self.files if p.rsplit("/", 1)[0] == parent.rstrip("/")}

    def makedirs(self, path):
        pass

    def read(self, path):
        return self.files[path]

    def put_verified(self, path, data, readback=True):
        self.files[path + ".omnibloom-new"] = data
        return path + ".omnibloom-new"

    def rename(self, src, dst):
        self.files[dst] = self.files.pop(src)


def url_node(url, name):
    return {"type": "url", "url": url, "name": name}


def chromium_profile(base, folder, bar, other=(), name=None):
    os.makedirs(os.path.join(base, folder), exist_ok=True)
    doc = {"roots": {"bookmark_bar": {"type": "folder", "children": list(bar)},
                     "other": {"type": "folder", "children": list(other)},
                     "synced": {"type": "folder", "children": []}}, "version": 1}
    with open(os.path.join(base, folder, "Bookmarks"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    if name:
        state = os.path.join(base, "Local State")
        cur = {}
        if os.path.exists(state):
            with open(state, encoding="utf-8") as f:
                cur = json.load(f)
        cur.setdefault("profile", {}).setdefault("info_cache", {})[folder] = {"name": name}
        with open(state, "w", encoding="utf-8") as f:
            json.dump(cur, f)


def firefox_profile(folder, toolbar, menu=(), wal=False):
    """A minimal places.sqlite. `toolbar` / `menu`: (url, title) pairs; a "folder" title makes a nested folder."""
    os.makedirs(folder, exist_ok=True)
    db = sqlite3.connect(os.path.join(folder, "places.sqlite"))
    if wal:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT)")
    db.execute("CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER, parent INTEGER, "
               "position INTEGER, title TEXT, guid TEXT)")
    db.execute("INSERT INTO moz_bookmarks VALUES (1, 2, NULL, 0, 0, '', 'root________')")
    db.execute("INSERT INTO moz_bookmarks VALUES (2, 2, NULL, 1, 0, 'menu', 'menu________')")
    db.execute("INSERT INTO moz_bookmarks VALUES (3, 2, NULL, 1, 1, 'toolbar', 'toolbar_____')")
    ids = [10]

    def add(parent, items):
        for pos, (url, title) in enumerate(items):
            ids[0] += 1
            bid = ids[0]
            if isinstance(url, list):    # a folder
                db.execute("INSERT INTO moz_bookmarks VALUES (?, 2, NULL, ?, ?, ?, ?)", (bid, parent, pos, title, "f%011d" % bid))
                add(bid, url)
                continue
            db.execute("INSERT INTO moz_places VALUES (?, ?)", (bid, url))
            db.execute("INSERT INTO moz_bookmarks VALUES (?, 1, ?, ?, ?, ?, ?)", (bid, bid, parent, pos, title, "b%011d" % bid))

    add(3, toolbar)
    add(2, menu)
    db.commit()
    if wal:
        # Keep the rows in the -wal file (as when Firefox is running): copy both files while the connection is open.
        snap = folder + "-snap"
        os.makedirs(snap, exist_ok=True)
        for n in ("places.sqlite", "places.sqlite-wal"):
            shutil.copyfile(os.path.join(folder, n), os.path.join(snap, n))
        db.close()
        for n in ("places.sqlite", "places.sqlite-wal"):
            shutil.copyfile(os.path.join(snap, n), os.path.join(folder, n))
        shm = os.path.join(folder, "places.sqlite-shm")
        if os.path.exists(shm):
            os.remove(shm)
        shutil.rmtree(snap)
    else:
        db.close()


class Cleaning(unittest.TestCase):
    def test_only_web_pages(self):
        self.assertEqual(bookmarks.clean_url("https://a.example/x"), "https://a.example/x")
        self.assertEqual(bookmarks.clean_url("HTTP://a.example/"), "http://a.example/")
        for bad in ("javascript:alert(1)", "file:///C:/x", "chrome://settings", "ftp://x", "https://", "about:blank",
                    "https://a.example/\tx", "https://a b", "https://a.example/\nx", None, 5):
            self.assertIsNone(bookmarks.clean_url(bad), bad)

    def test_long_addresses_are_left_out_not_cut(self):
        ok = "https://a.example/" + "x" * (config.OMNI_BOOKMARK_URL_MAX - 18)
        self.assertEqual(len(ok), config.OMNI_BOOKMARK_URL_MAX)
        self.assertEqual(bookmarks.clean_url(ok), ok)
        self.assertIsNone(bookmarks.clean_url(ok + "x"))

    def test_titles_one_line_and_cut_on_a_character(self):
        self.assertEqual(bookmarks.clean_title("a\tb\nc\r\nd\x00e"), "a b c d e")
        long = "é" * 400                     # 2 bytes each
        t = bookmarks.clean_title(long)
        self.assertLessEqual(len(t.encode("utf-8")), config.OMNI_BOOKMARK_TITLE_MAX)
        self.assertEqual(t, "é" * 150)
        self.assertEqual(bookmarks.clean_title(None), "")


class Finding(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="omnibloom-bm-")
        self.env = {"LOCALAPPDATA": os.path.join(self.home, "Local"), "APPDATA": os.path.join(self.home, "Roaming")}

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_windows_profiles_with_counts(self):
        chrome = os.path.join(self.env["LOCALAPPDATA"], "Google", "Chrome", "User Data")
        chromium_profile(chrome, "Default", [url_node("https://bar.example/", "Bar")],
                         [url_node("https://other.example/", "Other"), url_node("chrome://flags", "x"),
                          {"type": "folder", "children": [url_node("http://deep.example/", "Deep"),
                                                          url_node("https://bar.example/", "dupe")]}], name="Person 1")
        chromium_profile(chrome, "Profile 2", [url_node("https://two.example/", "Two")], name="Work")
        brave = os.path.join(self.env["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "User Data")
        chromium_profile(brave, "Default", [], [url_node("https://brave.example/", "B")])
        ff = os.path.join(self.env["APPDATA"], "Mozilla", "Firefox")
        firefox_profile(os.path.join(ff, "Profiles", "abcd.default-release"), [("https://fx.example/", "Fx")],
                        [("https://menu.example/", "Menu"), ("place:sort=8", "Recent")])
        with open(os.path.join(ff, "profiles.ini"), "w") as f:
            f.write("[Profile0]\nName=default-release\nIsRelative=1\nPath=Profiles/abcd.default-release\n")
        found = {s.label: s.count for s in bookmarks.find_sources("win32", self.env, self.home)}
        self.assertEqual(found, {"Chrome: Person 1": 3, "Chrome: Work": 1, "Brave: Default": 1,
                                 "Firefox: default-release": 2})

    def test_mac_and_linux_folders(self):
        chromium_profile(os.path.join(self.home, "Library", "Application Support", "Microsoft Edge"), "Default",
                         [url_node("https://edge.example/", "E")])
        self.assertEqual([s.label for s in bookmarks.find_sources("darwin", {}, self.home)], ["Edge: Default"])
        chromium_profile(os.path.join(self.home, ".config", "google-chrome"), "Default", [url_node("https://l.example/", "L")])
        firefox_profile(os.path.join(self.home, ".mozilla", "firefox", "x1.default"), [("https://f.example/", "F")])
        self.assertEqual(sorted(s.label for s in bookmarks.find_sources("linux", {}, self.home)),
                         ["Chrome: Default", "Firefox: default"])

    def test_broken_profile_is_reported_not_fatal(self):
        base = os.path.join(self.env["LOCALAPPDATA"], "Microsoft", "Edge", "User Data", "Default")
        os.makedirs(base)
        with open(os.path.join(base, "Bookmarks"), "w") as f:
            f.write("{not json")
        (s,) = bookmarks.find_sources("win32", self.env, self.home)
        self.assertEqual((s.count, s.error is not None), (0, True))

    def test_firefox_toolbar_first_nested_folders_and_wal(self):
        prof = os.path.join(self.home, "ff")
        firefox_profile(prof, [("https://t1.example/", "T1"), ([("https://t2.example/", None)], "folder")],
                        [("https://m1.example/", "M1")], wal=True)
        self.assertTrue(os.path.exists(os.path.join(prof, "places.sqlite-wal")))
        got = bookmarks.read_firefox(os.path.join(prof, "places.sqlite"))
        self.assertEqual([(b.url, b.title, b.bar) for b in got],
                         [("https://t1.example/", "T1", True), ("https://t2.example/", "", True),
                          ("https://m1.example/", "M1", False)])
        # The profile's own files are left as they were (only a temp copy is opened).
        self.assertFalse(os.path.exists(os.path.join(prof, "places.sqlite-shm")))

    def test_bar_bookmarks_win_across_profiles(self):
        a = bookmarks.Source("Chrome", "A", None, "chromium")
        b = bookmarks.Source("Firefox", "B", None, "firefox")
        a.read = lambda: [bookmarks.Bookmark("https://a-other.example/", "ao", False),
                          bookmarks.Bookmark("https://a-bar.example/", "ab", True)]
        b.read = lambda: [bookmarks.Bookmark("https://b-bar.example/", "bb", True),
                          bookmarks.Bookmark("https://a-other.example/", "dupe", False)]
        got = bookmarks.collect([a, b])
        self.assertEqual([x.url for x in got], ["https://a-bar.example/", "https://b-bar.example/", "https://a-other.example/"])
        self.assertEqual(got[2].title, "ao")


def marks(n, start=0, bar=False):
    return [bookmarks.Bookmark("https://site%d.example/" % i, "Site %d" % i, bar) for i in range(start, start + n)]


class Console_(unittest.TestCase):
    def test_fresh_console(self):
        c = Console()
        r = bookmarks.import_to_console(c, marks(3))
        self.assertEqual(r, {"added": 3, "already": 0, "no_room": 0, "total": 3})
        self.assertEqual(c.files[PATH], b"".join(b"https://site%d.example/\tSite %d\n" % (i, i) for i in range(3)))
        self.assertEqual(sorted(c.files), [PATH])          # nothing to park, no temp left

    def test_existing_kept_byte_for_byte_and_parked(self):
        old = b"https://mine.example/\tMine\r\nhttps://site1.example/\nno-tab-line"   # CRLF, no title, no final newline
        c = Console({PATH: old})
        r = bookmarks.import_to_console(c, marks(3))
        self.assertEqual((r["added"], r["already"]), (2, 1))
        new = c.files[PATH]
        self.assertTrue(new.startswith(old + b"\n"))
        self.assertEqual(new[len(old) + 1:], b"https://site0.example/\tSite 0\nhttps://site2.example/\tSite 2\n")
        parked = [p for p in c.files if p.startswith(PATH + ".before-setup-")]
        self.assertEqual(len(parked), 1)
        self.assertEqual(c.files[parked[0]], old)
        self.assertFalse([p for p in c.files if p.endswith(".omnibloom-new")])

    def test_nothing_new_writes_nothing(self):
        old = b"https://site0.example/\tSite 0\n"
        c = Console({PATH: old})
        r = bookmarks.import_to_console(c, marks(1))
        self.assertEqual((r["added"], r["already"]), (0, 1))
        self.assertEqual(c.files, {PATH: old})

    def test_limit_of_500(self):
        old = b"".join(b"https://old%d.example/\tOld\n" % i for i in range(490))
        c = Console({PATH: old})
        r = bookmarks.import_to_console(c, marks(25))
        self.assertEqual((r["added"], r["no_room"], r["total"]), (10, 15, 500))
        self.assertEqual(len(bookmarks.omni_entries(c.files[PATH])), 500)
        full = Console({PATH: c.files[PATH]})
        self.assertEqual(bookmarks.import_to_console(full, marks(5, 100))["added"], 0)

    def test_reader_matches_omni(self):
        # Empty lines don't count; a line over the 2400-byte fgets buffer counts as more than one entry.
        long = b"https://x.example/" + b"y" * 3000 + b"\tT\n"
        got = bookmarks.omni_entries(b"\n\r\nhttps://a.example/\n" + long + b"https://b.example/\tB\n")
        self.assertEqual(got[0], (b"https://a.example/", b"https://a.example/"))
        self.assertEqual(len(got), 4)
        self.assertEqual(got[-1], (b"https://b.example/", b"B"))

    def test_written_lines_fit_omni(self):
        b = bookmarks.collect([type("S", (), {"read": lambda self: [
            bookmarks.Bookmark("https://a.example/" + "x" * (config.OMNI_BOOKMARK_URL_MAX - 18), "t\tt" * 500, True)]})()])
        data, added, _, _ = bookmarks.merge(b"", b)
        self.assertEqual(added, 1)
        line = data.rstrip(b"\n")
        self.assertLess(len(data), config.OMNI_BOOKMARK_LINE_BUFFER)
        self.assertEqual(line.count(b"\t"), 1)
        self.assertEqual(bookmarks.omni_entries(data)[0][0], b.pop().url.encode())


if __name__ == "__main__":
    unittest.main()
