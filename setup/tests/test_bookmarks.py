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
        for bad in ("vbscript:alert(1)", "data:text/html,x", "javascript:", "file:///C:/x", "chrome://settings", "ftp://x", "https://", "about:blank",
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


B = bookmarks.Bookmark


class Folders(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="omnibloom-bmf-")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_chromium_keeps_one_folder_level(self):
        chromium_profile(self.home, "Default",
                         [url_node("https://top.example/", "Top"),
                          {"type": "folder", "name": "News", "children": [
                              url_node("https://n1.example/", "N1"),
                              {"type": "folder", "name": "Deeper", "children": [url_node("https://n2.example/", "N2")]}]}],
                         [{"type": "folder", "name": "x" * 60, "children": [url_node("https://o.example/", "O")]}])
        got = bookmarks.read_chromium(os.path.join(self.home, "Default", "Bookmarks"))
        self.assertEqual([(b.url, b.folder) for b in got],
                         [("https://top.example/", ""), ("https://n1.example/", "News"), ("https://n2.example/", "News"),
                          ("https://o.example/", "x" * 60)])
        src = bookmarks.Source("Chrome", "D", os.path.join(self.home, "Default", "Bookmarks"), "chromium")
        self.assertEqual(bookmarks.collect([src])[-1].folder, "x" * config.OMNI_BOOKMARK_FOLDER_MAX)

    def test_firefox_keeps_one_folder_level(self):
        prof = os.path.join(self.home, "ff")
        firefox_profile(prof, [("https://t.example/", "T"),
                               ([("https://a.example/", "A"), ([("https://b.example/", "B")], "Inner")], "Work")])
        got = bookmarks.read_firefox(os.path.join(prof, "places.sqlite"))
        self.assertEqual([(b.url, b.folder) for b in got],
                         [("https://t.example/", ""), ("https://a.example/", "Work"), ("https://b.example/", "Work")])

    def test_folder_names_cleaned_and_cut_on_a_character(self):
        self.assertEqual(bookmarks.clean_folder("a\tb\nc"), "a b c")
        f = bookmarks.clean_folder("é" * 30)
        self.assertEqual(f, "é" * 20)
        self.assertLessEqual(len(f.encode()), config.OMNI_BOOKMARK_FOLDER_MAX)


class UrlKey(unittest.TestCase):
    def test_same_page(self):
        k = bookmarks.url_key
        same = ["https://Example.COM/path", "https://example.com/path/", "https://example.com:443/path",
                "https://example.com/path?utm_source=x&utm_Medium=y", "https://example.com/path/?fbclid=1",
                b"https://EXAMPLE.com/path?gclid=2"]
        self.assertEqual({k(u) for u in same}, {"https://example.com/path"})
        self.assertEqual(k("https://example.com/"), k("https://example.com"))
        self.assertEqual(k("https://a.example/p?id=3&utm_campaign=z"), "https://a.example/p?id=3")

    def test_different_pages(self):
        k = bookmarks.url_key
        self.assertNotEqual(k("https://a.example/Path"), k("https://a.example/path"))     # paths keep their case
        self.assertNotEqual(k("https://a.example/p?id=1"), k("https://a.example/p?id=2"))
        self.assertNotEqual(k("http://a.example/"), k("https://a.example/"))
        self.assertNotEqual(k("https://a.example/#x"), k("https://a.example/#y"))
        self.assertEqual(k("not a url"), "not a url")


def sync_console(lines):
    return Console({PATH: lines}) if lines is not None else Console()


class Sync(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omnibloom-sync-")
        self.logs = []

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def out(self, name="omni.html"):
        return os.path.join(self.dir, name)

    def sync(self, console, pc, **kw):
        plan = bookmarks.plan_sync(pc, bookmarks.read_console_file(console))
        return plan, bookmarks.apply_sync(console, plan, export_path=kw.pop("export_path", self.out()),
                                          log=self.logs.append, **kw)

    def test_round_trip_with_folder_column(self):
        c = sync_console(b"https://omni.example/\tOmni page\tReading\n")
        pc = [B("https://pc.example/", "PC page", True, "News"), B("https://loose.example/", "Loose", False)]
        plan, r = self.sync(c, pc)
        self.assertEqual((r["added"], r["exported"], r["no_room"]), (2, 1, 0))
        self.assertEqual(c.files[PATH], b"https://omni.example/\tOmni page\tReading\n"
                                        b"https://pc.example/\tPC page\tNews\nhttps://loose.example/\tLoose\n")
        back = bookmarks.console_bookmarks(c.files[PATH])
        self.assertEqual([(b.url, b.title, b.folder) for b in back],
                         [("https://omni.example/", "Omni page", "Reading"), ("https://pc.example/", "PC page", "News"),
                          ("https://loose.example/", "Loose", "")])
        self.assertEqual(bookmarks.omni_entries(c.files[PATH])[1], (b"https://pc.example/", b"PC page"))
        with open(self.out(), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("<H3>Reading</H3>", page)
        self.assertIn('<A HREF="https://omni.example/">Omni page</A>', page)
        # A second sync (with the exported page now on the PC too) has nothing to do.
        again = bookmarks.plan_sync(pc + [B("https://omni.example/", "Omni page", False, "Reading")], c.files[PATH])
        self.assertEqual((again.to_console, again.to_pc, again.in_both), ([], [], 3))

    def test_old_two_column_file(self):
        old = b"https://a.example/\tA\r\nhttps://b.example/\n"
        c = sync_console(old)
        plan, r = self.sync(c, [B("https://c.example/", "C", False, "F")])
        self.assertEqual([(b.url, b.title, b.folder) for b in plan.to_pc],
                         [("https://a.example/", "A", ""), ("https://b.example/", "", "")])
        self.assertTrue(c.files[PATH].startswith(old))
        self.assertTrue(c.files[PATH].endswith(b"https://c.example/\tC\tF\n"))
        parked = [p for p in c.files if p.startswith(PATH + ".before-setup-")]
        self.assertEqual([c.files[p] for p in parked], [old])
        with open(self.out(), encoding="utf-8") as f:
            self.assertIn('<A HREF="https://b.example/">https://b.example/</A>', f.read())

    def test_malformed_lines(self):
        data = (b"\n\tno url\njavascript:alert(1)\tJS\nnot-a-url\nhttps://ok.example/\tOK\tFolder\textra\tcols\n"
                b"https://nul.example/\tN\x00ignored\nhttps://bad\xff.example/\tbad bytes\n")
        plan = bookmarks.plan_sync([], data)
        self.assertEqual(plan.not_web, 1)          # the bare word (a javascript: bookmarklet is exported now)
        self.assertEqual([(b.url, b.title, b.folder) for b in plan.to_pc][:3],
                         [("javascript:alert(1)", "JS", ""), ("https://ok.example/", "OK", "Folder"),
                          ("https://nul.example/", "N", "")])
        self.assertEqual(len(plan.to_pc), 4)
        self.assertNotIn("\x00", "".join(b.url + b.title for b in plan.to_pc))

    def test_duplicates(self):
        c = sync_console(b"https://Dup.example/a/\tOne\nhttps://dup.example/a?utm_source=x\tTwo\nhttps://only.example/\tO\n"
                         b"https://only.example\tO again\n")
        pc = [B("https://dup.example/a", "pc", True), B("https://new.example/?utm_medium=m", "N", False),
              B("https://NEW.example", "N2", False)]
        plan, r = self.sync(c, pc)
        self.assertEqual(plan.in_both, 1)
        self.assertEqual([b.url for b in plan.to_console], ["https://new.example/?utm_medium=m"])
        self.assertEqual([b.url for b in plan.to_pc], ["https://only.example/"])
        self.assertEqual(r["added"], 1)
        # The one-way import also matches by page now: nothing new to add.
        self.assertEqual(bookmarks.import_to_console(c, [B("https://new.example", "x", False)])["added"], 0)

    def test_cap_of_500(self):
        old = b"".join(b"https://old%d.example/\tOld\n" % i for i in range(495))
        c = sync_console(old)
        plan, r = self.sync(c, marks(10, bar=True))
        self.assertEqual((len(plan.to_console), plan.cap_skipped), (5, 5))
        self.assertEqual((r["added"], r["no_room"], r["total"]), (5, 5, 500))
        self.assertEqual(len(bookmarks.omni_entries(c.files[PATH])), 500)
        self.assertEqual(r["exported"], 495)                # the cap is Omni's: the PC side gets them all
        full = bookmarks.plan_sync(marks(3, 100), c.files[PATH])
        self.assertEqual((full.to_console, full.cap_skipped), ([], 3))

    def test_console_changed_after_preview(self):
        c = sync_console(b"https://a.example/\tA\n")
        plan = bookmarks.plan_sync([B("https://b.example/", "B", False)], c.files[PATH])
        c.files[PATH] += b"https://b.example/\tB saved in Omni meanwhile\nhttps://z.example/\tZ\n"
        before = c.files[PATH]
        r = bookmarks.apply_sync(c, plan, export_path=self.out())
        self.assertEqual((r["added"], r["already"]), (0, 1))
        self.assertEqual(c.files[PATH], before)               # kept as it was, no duplicate added

    def test_html_escaping(self):
        nasty = [B('https://e.example/?a=1&b="2"&c=<3>', '<script>alert("x")</script> & \'q\'', False, "F<o>&\"lder"),
                 B("https://e.example/plain", "", False)]
        page = bookmarks.export_html(nasty).decode("utf-8")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#x27;q&#x27;", page)
        self.assertIn('HREF="https://e.example/?a=1&amp;b=&quot;2&quot;&amp;c=&lt;3&gt;"', page)
        self.assertIn("<H3>F&lt;o&gt;&amp;&quot;lder</H3>", page)
        self.assertTrue(page.startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>"))
        # Read back with an HTML parser: the same addresses and titles come out.
        import html.parser

        class P(html.parser.HTMLParser):
            def __init__(self):
                super().__init__()
                self.links, self.cur = [], None

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    self.cur = [dict(attrs)["href"], ""]

            def handle_data(self, d):
                if self.cur is not None:
                    self.cur[1] += d

            def handle_endtag(self, tag):
                if tag == "a":
                    self.links.append(tuple(self.cur))
                    self.cur = None

        p = P()
        p.feed(page)
        self.assertEqual(p.links, [(nasty[0].url, nasty[0].title), (nasty[1].url, nasty[1].url)])

    def test_export_never_overwrites_or_touches_profiles(self):
        first = bookmarks.default_export_path(self.dir)
        bookmarks.write_export(first, marks(1))
        second = bookmarks.default_export_path(self.dir)
        self.assertNotEqual(first, second)
        self.assertTrue(second.endswith("-2.html"))
        with self.assertRaises(FileExistsError):
            bookmarks.write_export(first, marks(2))
        prof = os.path.join(self.dir, "Default")
        os.makedirs(prof)
        src = bookmarks.Source("Chrome", "D", os.path.join(prof, "Bookmarks"), "chromium")
        for bad in (os.path.join(prof, "Bookmarks"), os.path.join(self.dir, "places.sqlite"), os.path.join(self.dir, "x.txt")):
            with self.assertRaises(ValueError):
                bookmarks.write_export(bad, marks(1))
        with self.assertRaises(ValueError):
            bookmarks.write_export(os.path.join(prof, "export.html"), marks(1), [src])
        self.assertEqual(os.listdir(prof), [])

    def test_logs_and_plan_hold_counts_only(self):
        c = sync_console(b"https://secret-omni.example/\tPrivate title\tPrivate folder\n")
        plan, r = self.sync(c, [B("https://secret-pc.example/", "My bank", False, "Money")])
        text = " ".join(self.logs) + repr(plan)
        for word in ("secret", "Private", "bank", "Money", "example"):
            self.assertNotIn(word, text)
        self.assertEqual(len(self.logs), 1)

    def test_nothing_to_do_writes_nothing(self):
        c = sync_console(b"https://a.example/\tA\n")
        plan, r = self.sync(c, [B("https://A.example", "a", True)])
        self.assertEqual((r["added"], r["exported"]), (0, 0))
        self.assertEqual(c.files, {PATH: b"https://a.example/\tA\n"})
        self.assertEqual(os.listdir(self.dir), [])
        fresh = Console()
        plan, r = self.sync(fresh, [])
        self.assertEqual((fresh.files, r["total"]), ({}, 0))


def bookmarklet(size):
    """A javascript: address of exactly `size` bytes."""
    head = "javascript:(function(){var%20s='"
    tail = "';alert(s.length)})()"
    return head + "x" * (size - len(head) - len(tail)) + tail


class Bookmarklets(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omnibloom-bml-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_clean_url_keeps_bookmarklets(self):
        self.assertEqual(bookmarks.clean_url("javascript:alert(1)"), "javascript:alert(1)")
        self.assertEqual(bookmarks.clean_url("JavaScript:alert(1)"), "JavaScript:alert(1)")   # exact: case kept
        self.assertEqual(bookmarks.clean_url(" javascript:a();\n//x\r\n\tb() "), "javascript:a();//xb()")
        self.assertEqual(bookmarks.clean_url("javascript:a(' \x01\x7f')\x01"), "javascript:a(' %01%7F')")
        self.assertEqual(bookmarks.clean_url("javascript:a('%20')"), "javascript:a('%20')")      # escapes are code
        for bad in ("javascript:", "javascript: ", "vbscript:x", "javascript:\ud800"):
            self.assertIsNone(bookmarks.clean_url(bad), bad)

    def test_64_kb_cap(self):
        ok = bookmarklet(config.OMNI_BOOKMARKLET_URL_MAX)
        self.assertEqual(len(ok.encode()), 65536)
        self.assertEqual(bookmarks.clean_url(ok), ok)
        self.assertIsNone(bookmarks.clean_url(bookmarklet(config.OMNI_BOOKMARKLET_URL_MAX + 1)))
        wide = "javascript:'" + "é" * 32762 + "'"            # multi-byte characters count as bytes
        self.assertGreater(len(wide.encode()), 65536)
        self.assertIsNone(bookmarks.clean_url(wide))
        self.assertIsNone(bookmarks.clean_url("https://a.example/" + "x" * 2100))   # web pages keep 2048
        self.assertEqual(config.OMNI_BOOKMARKLET_LINE_BUFFER - 1, 65934)

    def test_long_bookmarklet_round_trip(self):
        code = bookmarklet(config.OMNI_BOOKMARKLET_URL_MAX)
        src = type("S", (), {"read": lambda self: [B(code, "Big\tone", True, "Tools"), B("https://a.example/", "A", True)]})
        pc = bookmarks.collect([src()])
        self.assertEqual([b.url for b in pc], [code, "https://a.example/"])
        c = sync_console(b"https://old.example/\tOld\n")
        r = bookmarks.import_to_console(c, pc)
        self.assertEqual(r["added"], 2)
        line = code.encode() + b"\tBig one\tTools\n"
        self.assertIn(line, c.files[PATH])
        # Read back whole (not as 2399-byte pieces), the web page after it intact.
        self.assertEqual(bookmarks.omni_lines(c.files[PATH]),
                         [(b"https://old.example/", b"Old", b""), (code.encode(), b"Big one", b"Tools"),
                          (b"https://a.example/", b"A", b"")])
        self.assertEqual(bookmarks.console_bookmarks(c.files[PATH])[1], B(code, "Big one", False, "Tools"))
        # Matched by the exact address: nothing to do a second time.
        again = bookmarks.plan_sync(pc, c.files[PATH])
        self.assertEqual((again.to_console, [b.url for b in again.to_pc], again.in_both),
                         ([], ["https://old.example/"], 2))
        self.assertEqual(bookmarks.merge(c.files[PATH], pc)[1:], (0, 2, 0))
        # Exact means exact: other case or an extra "utm_" tail is a different bookmarklet.
        other = code.replace("javascript:", "JavaScript:", 1)
        self.assertEqual(len(bookmarks.plan_sync([B(other, "x", False)], c.files[PATH]).to_console), 1)
        self.assertNotEqual(bookmarks.url_key("javascript:a()?utm_source=x"), bookmarks.url_key("javascript:a()"))

    def test_console_line_limits(self):
        # Exactly 65934 bytes (no newline) is one entry; one byte more spills into a second piece.
        line = bookmarklet(config.OMNI_BOOKMARKLET_URL_MAX).encode() + b"\t" + b"t" * 300 + b"\t" + b"f" * 40
        line += b"z" * (65934 - len(line))
        self.assertEqual(len(bookmarks.omni_lines(line)), 1)
        self.assertEqual(len(bookmarks.omni_lines(line + b"Q")), 2)
        # Ordinary lines keep the 2400-byte buffer; "javascript:" counts only at a line start, in any case.
        self.assertEqual(len(bookmarks.omni_lines(b"https://a.example/" + b"x" * 3000)), 2)
        self.assertEqual(len(bookmarks.omni_lines(b"JAVASCRIPT:" + b"x" * 3000 + b"\n")), 1)
        self.assertEqual(len(bookmarks.omni_lines(b" javascript:" + b"x" * 3000)), 2)

    def test_html_export_escapes(self):
        code = "javascript:(function(){var a=\"<b>&amp;</b>\";if(1<2&&3>2)alert('x')})()"
        marks = [B(code, 'Say "hi" & <go>', False, "Tools <1>"), B("javascript:void(0)", "", False)]
        page = bookmarks.export_html(marks).decode("utf-8")
        self.assertIn('<A HREF="javascript:(function(){var a=&quot;&lt;b&gt;&amp;amp;&lt;/b&gt;&quot;;'
                      'if(1&lt;2&amp;&amp;3&gt;2)alert(&#x27;x&#x27;)})()">Say &quot;hi&quot; &amp; &lt;go&gt;</A>', page)
        self.assertIn("<H3>Tools &lt;1&gt;</H3>", page)
        self.assertIn('<A HREF="javascript:void(0)">Bookmarklet</A>', page)   # never the code as a title
        self.assertNotIn("<b>", page)
        import html.parser

        class Hrefs(html.parser.HTMLParser):
            def __init__(self):
                super().__init__()
                self.found = []

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    self.found.append(dict(attrs)["href"])
        p = Hrefs()
        p.feed(page)
        self.assertEqual(p.found, [code, "javascript:void(0)"])          # what a browser reads back is exact

    def test_sync_exports_omni_bookmarklets(self):
        code = bookmarklet(5000)
        c = sync_console(code.encode() + b"\tLong JS\n" + b"https://w.example/\tW\n")
        plan = bookmarks.plan_sync([], c.files[PATH])
        self.assertEqual([(b.url, b.title) for b in plan.to_pc], [(code, "Long JS"), ("https://w.example/", "W")])
        self.assertEqual(plan.not_web, 0)
        out = os.path.join(self.dir, "o.html")
        bookmarks.apply_sync(c, plan, export_path=out)
        with open(out, encoding="utf-8") as f:
            self.assertIn(code.replace("'", "&#x27;"), f.read())


if __name__ == "__main__":
    unittest.main()
