"""Read-later import (Pocket HTML / Pocket CSV / Instapaper CSV / Netscape HTML) into Omni's "Read later" folder.
Small hand-written fixtures; the console is a dict. Example addresses only (example.com / example.org)."""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import bookmarks, config, readlater_import as rl  # noqa: E402

PATH = config.OMNI_BOOKMARKS

POCKET_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Pocket Export</title></head><body>
<h1>Unread</h1>
<ul>
<li><a href="https://example.com/a" time_added="1600000000" tags="news">Article &amp; A</a></li>
<li><a href="javascript:alert(1)" time_added="1600000001" tags="">Evil</a></li>
<li><a href="https://example.com/café" time_added="1600000002" tags="">Café 日本語 \U0001F600</a></li>
<li><a href="https://example.com/a" time_added="1600000003" tags="">Same again</a></li>
<li><a time_added="1">no href</a></li>
<li><a href="ftp://example.com/file">ftp</a></li>
<li><a href="https://example.com/unclosed" time_added="1">Unclosed
</ul>
<h1>Read Archive</h1>
<ul>
<li><a href="https://example.org/old" time_added="1500000000" tags="">Old one</a></li>
</ul>
</body></html>
"""

POCKET_CSV = (
    "title,url,time_added,tags,status\n"
    "First,https://example.com/1,1700000000,,unread\n"
    "\"Quoted, with comma\",https://example.com/2,1700000001,a|b,unread\n"
    "Read one,https://example.com/3,1700000002,,archive\n"
    "Bad JS,JavaScript:void(0),1700000003,,unread\n"
    "short row only\n"
    "Ümläut файл,https://example.com/4,1700000004,,unread\n"
    "\n"
    "Dup,https://example.com/1,1700000005,,unread\n"
)

INSTAPAPER_CSV = (
    "URL,Title,Selection,Folder,Timestamp\n"
    "https://example.com/i1,Insta one,a private highlight,Unread,1700000000\n"
    "https://example.com/i2,Insta two,,Archive,1700000001\n"
    "https://example.com/i3,Starred,,Starred,1700000002\n"
    "not a url,Broken,,Unread,1\n"
    "javascript:alert(document.cookie),Evil,,Unread,1\n"
)

NETSCAPE = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE><H1>Bookmarks</H1>
<DL><p>
  <DT><H3>Read Archive</H3>
  <DL><p>
    <DT><A HREF="https://example.org/n1" ADD_DATE="1">N <b>one</b></A>
    <DT><A HREF="javascript:void(0)">Bookmarklet</A>
  </DL><p>
  <DT><A HREF="https://example.org/n2">二</A>
</DL><p>
"""


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


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-rl-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text, bom=False):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            f.write(text)
        return path


class DetectTest(Base):
    def test_formats(self):
        self.assertEqual(rl.detect_format(POCKET_HTML), "pocket_html")
        self.assertEqual(rl.detect_format(POCKET_CSV), "pocket_csv")
        self.assertEqual(rl.detect_format(INSTAPAPER_CSV), "instapaper_csv")
        self.assertEqual(rl.detect_format(NETSCAPE), "netscape")
        self.assertEqual(rl.detect_format("﻿" + INSTAPAPER_CSV), "instapaper_csv")

    def test_csv_with_html_in_title_is_still_csv(self):
        self.assertEqual(rl.detect_format("title,url,status\n<a href=x>,https://example.com/,unread\n"), "pocket_csv")

    def test_unknown(self):
        for text in ("", "hello world\n", "a,b,c\n1,2,3\n", "<html><body>no links</body></html>"):
            with self.assertRaises(rl.ReadLaterError):
                rl.detect_format(text)


class PocketHtmlTest(Base):
    def test_parse_and_plan(self):
        kind, items, bad = rl.read_file(self.write("ril_export.html", POCKET_HTML))
        self.assertEqual(kind, "pocket_html")
        self.assertEqual(bad, 0)
        plan = rl.plan_import(items, bad_rows=bad)
        urls = [b.url for b in plan.marks]
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/café", "https://example.com/unclosed"])
        self.assertEqual(plan.marks[0].title, "Article & A")
        self.assertEqual(plan.marks[1].title, "Café 日本語 \U0001F600")
        self.assertTrue(all(b.folder == rl.READ_LATER_FOLDER for b in plan.marks))
        self.assertEqual(plan.duplicates, 1)
        self.assertEqual(plan.invalid, 2)            # javascript: and ftp:
        self.assertEqual(plan.archived_left_out, 1)
        self.assertNotIn("javascript", " ".join(urls).lower())

    def test_archive_opt_in(self):
        _, items, _ = rl.read_file(self.write("ril_export.html", POCKET_HTML))
        plan = rl.plan_import(items, include_archive=True)
        last = plan.marks[-1]
        self.assertEqual((last.url, last.folder), ("https://example.org/old", rl.READ_LATER_ARCHIVE_FOLDER))
        self.assertEqual(plan.archived_left_out, 0)


class PocketCsvTest(Base):
    def test_parse(self):
        kind, items, bad = rl.read_file(self.write("part_000000.csv", POCKET_CSV, bom=True))
        self.assertEqual(kind, "pocket_csv")
        self.assertEqual(bad, 1)                      # the one-column row
        plan = rl.plan_import(items, bad_rows=bad, include_archive=True)
        self.assertEqual([b.url for b in plan.marks], ["https://example.com/1", "https://example.com/2",
                                                        "https://example.com/4", "https://example.com/3"])
        self.assertEqual(plan.marks[1].title, "Quoted, with comma")
        self.assertEqual(plan.marks[2].title, "Ümläut файл")
        self.assertEqual(plan.marks[3].folder, rl.READ_LATER_ARCHIVE_FOLDER)
        self.assertEqual((plan.duplicates, plan.invalid), (1, 2))

    def test_broken_quotes_tolerated(self):
        text = 'title,url,status\n"never closed,https://example.com/x,unread\nok,https://example.com/y,unread\n'
        _, items, bad = rl.read_file(self.write("broken.csv", text))
        plan = rl.plan_import(items, bad_rows=bad)    # no exception; whatever survives is still cleaned
        for b in plan.marks:
            self.assertIsNotNone(bookmarks.clean_url(b.url))


class InstapaperTest(Base):
    def test_selection_not_read_by_default(self):
        kind, items, bad = rl.read_file(self.write("instapaper-export.csv", INSTAPAPER_CSV))
        self.assertEqual(kind, "instapaper_csv")
        self.assertTrue(all(i.note == "" for i in items))
        plan = rl.plan_import(items, bad_rows=bad)
        self.assertEqual([b.url for b in plan.marks], ["https://example.com/i1", "https://example.com/i3"])
        self.assertEqual(plan.marks[0].title, "Insta one")
        self.assertEqual((plan.invalid, plan.archived_left_out), (2, 1))
        data, *_ = rl.merge_exact(b"", plan.marks)
        self.assertNotIn(b"highlight", data)

    def test_selection_when_ticked(self):
        _, items, bad = rl.read_file(self.write("i.csv", INSTAPAPER_CSV), include_notes=True)
        plan = rl.plan_import(items, include_notes=True)
        self.assertEqual(plan.marks[0].title, "Insta one - a private highlight")
        # read with notes but planned without: still left out
        self.assertEqual(rl.plan_import(items).marks[0].title, "Insta one")


class NetscapeTest(Base):
    def test_fallback(self):
        kind, items, _ = rl.read_file(self.write("bookmarks.html", NETSCAPE))
        self.assertEqual(kind, "netscape")
        plan = rl.plan_import(items)
        self.assertEqual([(b.url, b.title, b.folder) for b in plan.marks],
                         [("https://example.org/n1", "N one", rl.READ_LATER_FOLDER),
                          ("https://example.org/n2", "二", rl.READ_LATER_FOLDER)])
        self.assertEqual(plan.invalid, 1)


class CapsTest(Base):
    def test_title_and_url_caps(self):
        long_title = "é" * 1000
        long_url = "https://example.com/" + "x" * config.OMNI_BOOKMARK_URL_MAX
        plan = rl.plan_import([rl.Item("https://example.com/t", long_title + "\tx\n"), rl.Item(long_url, "too long")])
        self.assertEqual(len(plan.marks), 1)
        self.assertLessEqual(len(plan.marks[0].title.encode("utf-8")), config.OMNI_BOOKMARK_TITLE_MAX)
        self.assertNotIn("\t", plan.marks[0].title)
        self.assertEqual(plan.invalid, 1)

    def test_row_limit_html(self):
        many = "<h1>Unread</h1><ul>" + "".join('<li><a href="https://example.com/%d" time_added="1">t</a></li>' % i
                                               for i in range(50)) + "</ul>"
        items, over = rl.parse_html(io.StringIO(many), limit=10)
        self.assertEqual((len(items), over >= 0), (10, True))

    def test_row_limit_csv(self):
        text = "title,url\n" + "".join("t,https://example.com/%d\n" % i for i in range(30))
        items, bad = rl.parse_csv(io.StringIO(text), "pocket_csv", limit=10)
        self.assertEqual((len(items), bad), (10, 20))

    def test_byte_cap(self):
        old = rl.MAX_FILE_BYTES
        rl.MAX_FILE_BYTES = 200
        try:
            text = "title,url\n" + "".join("t,https://example.com/%d\n" % i for i in range(100))
            items, _ = rl.parse_csv(io.StringIO(text), "pocket_csv")
        finally:
            rl.MAX_FILE_BYTES = old
        self.assertLess(len(items), 100)

    def test_total_bookmark_cap_and_console_duplicates(self):
        existing = "".join("https://example.net/%d\tx\n" % i for i in range(config.OMNI_BOOKMARK_MAX - 2))
        existing += "https://example.com/1\tAlready\n"
        c = Console({PATH: existing.encode()})
        items = [rl.Item("https://example.com/%d" % i, "t%d" % i) for i in range(1, 6)]
        r = rl.import_to_console(c, rl.plan_import(items))
        self.assertEqual((r["added"], r["duplicates"], r["no_room"]), (1, 1, 3))
        self.assertEqual(r["total"], config.OMNI_BOOKMARK_MAX)
        self.assertTrue(c.files[PATH].startswith(existing.encode()))
        lines = bookmarks.omni_lines(c.files[PATH])
        self.assertEqual(lines[-1], (b"https://example.com/2", b"t2", b"Read later"))
        self.assertTrue(any(k.startswith(PATH + ".before-setup-") for k in c.files))
        self.assertEqual(rl.summary(r), "Imported 1, skipped 1 duplicate, 0 invalid, 3 left out (Omni keeps up to %d "
                                        "bookmarks)." % config.OMNI_BOOKMARK_MAX)


class ConsoleTest(Base):
    def test_empty_console_and_summary(self):
        _, items, bad = rl.read_file(self.write("ril_export.html", POCKET_HTML))
        c = Console()
        logs = []
        r = rl.import_to_console(c, rl.plan_import(items, bad_rows=bad), log=logs.append)
        self.assertEqual((r["added"], r["duplicates"], r["invalid"]), (3, 1, 2))
        self.assertEqual(logs, ["Imported 3, skipped 1 duplicate, 2 invalid, 1 read/archived not included."])
        self.assertNotIn("example", logs[0])
        self.assertIn("Café".encode("utf-8"), c.files[PATH])

    def test_nothing_new_writes_nothing(self):
        c = Console({PATH: b"https://example.com/a\tA\tRead later\n"})
        r = rl.import_to_console(c, rl.plan_import([rl.Item("https://example.com/a", "A")]))
        self.assertEqual((r["added"], r["duplicates"]), (0, 1))
        self.assertEqual(list(c.files), [PATH])

    def test_plan_repr_has_no_addresses(self):
        plan = rl.plan_import([rl.Item("https://example.com/secret", "Secret")])
        self.assertNotIn("secret", repr(plan).lower())


if __name__ == "__main__":
    unittest.main()
