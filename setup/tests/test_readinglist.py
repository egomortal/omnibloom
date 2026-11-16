"""Export Omni's reading list to a folder on the PC (index.html + the saved pages) and an optional EPUB 3.
The console is a dict with no write methods (read-only), plus one run over real FTP against the fake console.
Index fields and saved pages are hostile here: escaping, file-name rules, the EPUB sanitiser and its structure."""
import base64
import datetime
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import readinglist as rl  # noqa: E402

D = rl.DIR + "/"
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


class ReadOnlyConsole:
    """Only listing and read exist: any write attempt fails with AttributeError."""

    def __init__(self, files):
        self.files = dict(files)
        self.calls = []

    def listing(self, parent):
        self.calls.append(("listing", parent))
        parent = parent.rstrip("/")
        return {p.rsplit("/", 1)[1]: {"dir": False, "size": len(d)} for p, d in self.files.items()
                if p.rsplit("/", 1)[0] == parent}

    def read(self, path, limit=None):
        self.calls.append(("read", path))
        data = self.files[path]
        return data[:limit] if limit else data


def tsv(*lines):
    return ("omni-reading-list\t1\n" + "".join(l + "\n" for l in lines)).encode()


EVIL_TITLE = '<script>alert(1)</script> "Tom & Jerry"\\tx'
PAGE_A = ("<!DOCTYPE html><html><head><title>A</title><meta http-equiv=\"Content-Security-Policy\" content=\"x\">"
          "<style>body{background:url(https://t.example/x.png)}</style><script>evil()</script></head><body>"
          "<div id=\"omni-saved-banner\" style=\"all:initial\">Saved copy &middot; <a href=\"https://a.example/\">Open live"
          " page</a></div><h2 onclick=\"evil()\" class=\"x\" style=\"color:red\">Hello &amp; welcome</h2>"
          "<p>Text <b>bold<i>both</b> after &nbsp; &#1;ctl</p><img src=\"https://t.example/track.gif\">"
          "<img src=\"%s\" alt=\"pic\" onerror=\"evil()\"><img src=\"data:image/png;base64,AAAA\">"
          "<img src=\"data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=\"><iframe src=\"https://f.example/\"><p>in frame</p>"
          "</iframe><form action=\"https://f.example/\"><p>in form</p><input name=q><button>Go</button>"
          "<textarea>hidden</textarea></form><a href=\"javascript:evil()\">js link</a> <a href=\"https://ok.example/?a=1&b=2\">"
          "ok link</a><object data=\"x\"><p>obj</p></object><svg><script>x()</script></svg><table><tr><td colspan=2>c"
          "<td>d</table><br><hr><p>unclosed <em>em</p></div></span></body></html>" % PNG_URI).encode()


def omni(extra=None):
    files = {
        D + "index.tsv": tsv(
            "a.example-20261110-101010.html\t1762769410\t%d\th\thttps://www.a.example/post\t%s" % (len(PAGE_A), EVIL_TITLE),
            "b.example-20261111-101010.html\t1762855810\t20\tt\tjavascript:alert(1)\tB page",
            "p\ta.example-20261110-101010.html\t400\t1762900000\t0",
            "p\tb.example-20261111-101010.html\t990\t1762900000\t0",
            "../../evil.html\t1762855810\t20\th\thttps://x.example/\tTraversal",
            "con.example-20261111-101010.html\t1762855810\t5\th\thttps://c.example/\tReserved",
            "gone.example-20261111-101010.html\t1762855810\t5\th\thttps://g.example/\tMissing file",
            "a.example-20261110-101010.html\t1\t1\th\thttps://dupe/\tDupe",
            "bad line",
            "p\tc.example-20261111-101010.html\tx\t1\t0"),
        D + "a.example-20261110-101010.html": PAGE_A,
        D + "b.example-20261111-101010.html": b"<p>just text</p>",
        D + "con.example-20261111-101010.html": b"<p>c</p>",
        D + "unlisted.example-20261111-101010.html": b"<p>not in the index</p>",
        "/data/omni/passwords.txt": b"secret",
    }
    files.update(extra or {})
    return ReadOnlyConsole(files)


class Index(unittest.TestCase):
    def test_parse_like_omni(self):
        pages = rl.parse_index(omni().files[D + "index.tsv"])
        self.assertEqual([p.id for p in pages], ["a.example-20261110-101010.html", "b.example-20261111-101010.html",
                                                 "con.example-20261111-101010.html", "gone.example-20261111-101010.html"])
        a, b = pages[0], pages[1]
        self.assertEqual(a.title, '<script>alert(1)</script> "Tom & Jerry"\tx')     # TSV-unescaped
        self.assertEqual((a.permille, a.finished_at, rl.read_label(a)), (400, 0, "40% read"))
        self.assertEqual((b.text_only, rl.read_label(b)), (True, "Finished"))      # 99 % with finished 0 -> updated
        self.assertEqual(rl.read_label(pages[2]), "")
        self.assertEqual(rl.parse_index(b"omni-reading-list\t2\nx\t1\t1\th\tu\tt\n"), [])
        self.assertEqual(rl.parse_index(b"omni-reading-list\t1\r\nab.example-1.html\t5\t1\th\thttps://a/\tT\r\n")[0].title, "T")

    def test_names(self):
        for bad in ("../x.html", "a/b.html", "A.html", "a..html", ".hidden.html", "x.htm", "a\\b.html", None, "a.html\0"):
            self.assertIsNone(rl.local_name(bad), bad)
        self.assertEqual(rl.local_name("con.example-1.html"), "_con.example-1.html")
        self.assertEqual(rl.local_name("lpt1.html"), "_lpt1.html")
        self.assertEqual(rl.local_name("news.example-20261116-101010.html"), "news.example-20261116-101010.html")
        self.assertEqual(rl.site("https://www.Example.com:8443/x"), "example.com")
        self.assertEqual(rl.site("javascript:alert(1)"), "")


class Export(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-rl-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_export(self, console, **kw):
        return rl.export(console, self.tmp, today=datetime.date(2026, 11, 16), tz=UTC, now=NOW, **kw)

    def test_folder_index_and_pages(self):
        c = omni()
        before = dict(c.files)
        r = self.run_export(c)
        self.assertEqual(c.files, before)
        self.assertEqual({k for k, _ in c.calls}, {"listing", "read"})
        self.assertNotIn(("read", "/data/omni/passwords.txt"), c.calls)
        self.assertEqual(r["path"], os.path.join(self.tmp, "Omni reading list 2026-11-16"))
        self.assertEqual((r["pages"], r["missing"], r["epub"]), (3, 1, None))
        pages = sorted(os.listdir(os.path.join(r["path"], "pages")))
        self.assertEqual(pages, ["_con.example-20261111-101010.html", "a.example-20261110-101010.html",
                                 "b.example-20261111-101010.html"])
        with open(os.path.join(r["path"], "pages", "a.example-20261110-101010.html"), "rb") as f:
            self.assertEqual(f.read(), PAGE_A)                                     # byte for byte
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.html")))
        self.assertFalse([n for n in os.listdir(self.tmp) if n.endswith(".part")])
        with open(os.path.join(r["path"], "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertNotIn("<script", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &quot;Tom &amp; Jerry&quot;", page)
        self.assertNotIn("javascript:", page)
        self.assertIn('href="pages/a.example-20261110-101010.html"', page)
        self.assertIn('href="pages/_con.example-20261111-101010.html"', page)
        self.assertIn("40% read", page)
        self.assertIn("Finished", page)
        self.assertIn("a.example", page)
        self.assertIn("2025-11-10", page)            # 1762769410 UTC
        self.assertIn("default-src 'none'", page)                       # CSP: no scripts at all
        # second export the same day goes to a new folder
        r2 = self.run_export(c)
        self.assertEqual(r2["path"], os.path.join(self.tmp, "Omni reading list 2026-11-16 2"))

    def test_empty_and_caps(self):
        with self.assertRaises(rl.ExportError):
            self.run_export(ReadOnlyConsole({}))
        big = omni()
        big.listing = lambda parent: {"index.tsv": {"size": 100}, "a.example-20261110-101010.html": {"size": 400 * rl.MiB},
                                      "b.example-20261111-101010.html": {"size": 20 * rl.MiB},
                                      "con.example-20261111-101010.html": {"size": 5}}
        p = rl.plan(big)
        self.assertEqual((len(p["pages"]), p["too_big"], p["warn"]), (2, 1, False))   # 400 MB > 32 MB page cap
        many = {"index.tsv": {"size": 100}}
        lines = []
        for i in range(30):
            pid = "s%02d.example-1.html" % i
            many[pid] = {"size": 30 * rl.MiB}
            lines.append("%s\t%d\t1\th\thttps://s/\tT" % (pid, 100 + i))
        c = ReadOnlyConsole({D + "index.tsv": tsv(*lines)})
        c.listing = lambda parent: many
        p = rl.plan(c)
        self.assertTrue(p["warn"])                                           # 600 MB > 500 MB: ask first
        self.assertEqual((len(p["pages"]), p["too_big"]), (21, 9))           # 640 MB hard cap

    def test_epub_structure_and_sanitising(self):
        r = self.run_export(omni(), epub_ids=["a.example-20261110-101010.html", "b.example-20261111-101010.html"])
        e = r["epub"]
        self.assertEqual((e["chapters"], e["images"]), (2, 1))
        with open(os.path.join(r["path"], "index.html"), encoding="utf-8") as f:
            self.assertIn('href="reading-list.epub"', f.read())
        with zipfile.ZipFile(e["path"]) as z:
            infos = z.infolist()
            self.assertEqual(infos[0].filename, "mimetype")
            self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
            self.assertEqual(infos[0].extra, b"")
            self.assertEqual(z.read("mimetype"), b"application/epub+zip")
            with open(e["path"], "rb") as f:
                self.assertEqual(f.read(58)[30:58], b"mimetypeapplication/epub+zip")
            names = set(z.namelist())
            for req in ("META-INF/container.xml", "OEBPS/package.opf", "OEBPS/text/nav.xhtml"):
                self.assertIn(req, names)
            for n in names:
                self.assertFalse(n.startswith("/") or ".." in n, n)
            cont = ET.fromstring(z.read("META-INF/container.xml"))
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            self.assertEqual(cont.find(".//c:rootfile", ns).get("full-path"), "OEBPS/package.opf")
            opf = ET.fromstring(z.read("OEBPS/package.opf"))
            O = "{http://www.idpf.org/2007/opf}"
            self.assertEqual(opf.get("version"), "3.0")
            dc = "{http://purl.org/dc/elements/1.1/}"
            md = opf.find(O + "metadata")
            for t in ("identifier", "title", "language"):
                self.assertIsNotNone(md.find(dc + t), t)
            self.assertEqual(md.find(dc + "identifier").get("id"), opf.get("unique-identifier"))
            mod = [m for m in md.findall(O + "meta") if m.get("property") == "dcterms:modified"]
            self.assertEqual(mod[0].text, "2026-11-16T12:00:00Z")
            items = {i.get("id"): i for i in opf.find(O + "manifest")}
            self.assertEqual([i.get("id") for i in items.values() if i.get("properties") == "nav"], ["nav"])
            for i in items.values():                                       # every manifest item is in the zip
                self.assertIn("OEBPS/" + i.get("href"), names)
            spine = [i.get("idref") for i in opf.find(O + "spine")]
            self.assertEqual(spine, ["ch001", "ch002"])
            X = "{http://www.w3.org/1999/xhtml}"
            for n in names:
                if n.endswith(".xhtml"):
                    root = ET.fromstring(z.read(n))                         # well-formed XHTML
                    self.assertEqual(root.tag, X + "html")
            nav = ET.fromstring(z.read("OEBPS/text/nav.xhtml"))
            toc = nav.find(".//" + X + "nav")
            self.assertEqual(toc.get("{http://www.idpf.org/2007/ops}type"), "toc")
            self.assertEqual(len(toc.findall(".//" + X + "a")), 2)
            ch = z.read("OEBPS/text/ch-001.xhtml").decode()
            root = ET.fromstring(ch)
            for bad in ("script", "style", "iframe", "form", "input", "button", "textarea", "object", "svg"):
                self.assertEqual(root.findall(".//" + X + bad), [], bad)
            self.assertEqual(len(root.findall(".//" + X + "meta")), 1)        # only our charset meta
            for el in root.iter():
                for k, v in el.attrib.items():
                    self.assertFalse(k.lower().startswith("on"), k)
                    self.assertNotEqual(k, "style")
                    if k == "class":                                        # only Setup's own wrapper classes
                        self.assertIn(v, ("title", "source", "content"))
                    self.assertNotIn("javascript:", v)
            imgs = root.findall(".//" + X + "img")
            self.assertEqual([(i.get("src"), i.get("alt")) for i in imgs], [("images/img-0001.png", "pic")])
            self.assertEqual(z.read("OEBPS/text/images/img-0001.png"), PNG)
            self.assertNotIn("t.example", ch)                               # no external resources
            self.assertNotIn("evil", ch)
            self.assertNotIn("Saved copy", ch)                              # Omni's banner dropped
            self.assertNotIn("hidden", ch)
            self.assertNotIn("in frame", ch)
            self.assertIn("in form", ch)                                    # form text kept, controls dropped
            self.assertIn("Hello &amp; welcome", ch)
            self.assertIn('href="https://ok.example/?a=1&amp;b=2"', ch)
            self.assertNotIn("\x01", ch)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", ch)      # the title, escaped
            ch2 = z.read("OEBPS/text/ch-002.xhtml").decode()
            self.assertIn("just text", ch2)
            self.assertNotIn("javascript", ch2)

    def test_sanitiser_fuzz_stays_well_formed(self):
        nasty = ["<p>a<b>b<i>c</p></b>", "</div></div><p>", "<table><td>x<tr><td>y", "<a href='https://x/'><a>z",
                 "<<>><!-- c --><![CDATA[x]]>&bogus;&#xFFFF;&#0;", "<img src=x onerror=1/>", "<br/><hr/></br>",
                 "<scr<script>ipt>x</script>", "<script>a</p></script>b", "<p title='\"&<>'>t</p>", "\x00\x0b\x7f\ud800"]
        for n in nasty:
            body, _ = rl.sanitise_page(n.encode("utf-8", "surrogatepass"), lambda k, d: None)
            ET.fromstring('<div xmlns="http://www.w3.org/1999/xhtml">%s</div>' % body)
            self.assertNotIn("<script", body)
            self.assertNotIn("onerror", body)

    def test_data_images(self):
        self.assertEqual(rl.decode_data_image(PNG_URI), ("png", PNG))
        self.assertIsNone(rl.decode_data_image("data:image/png;base64," + base64.b64encode(b"GIF89a....").decode()))
        self.assertIsNone(rl.decode_data_image("data:image/svg+xml;base64,PHN2Zz4="))
        self.assertIsNone(rl.decode_data_image("https://x/a.png"))
        self.assertIsNone(rl.decode_data_image("data:text/html;base64,PHA+"))


class OverFtp(unittest.TestCase):
    """The real ps5.Console against the fake console: the export reads only, and changes nothing there."""

    def test_read_only_over_ftp(self):
        try:
            from tests.fake_console import FakeConsole
        except ImportError:
            from fake_console import FakeConsole
        from omnibloom_setup import ps5
        tmp = tempfile.mkdtemp(prefix="omnibloom-rlftp-")
        fc = FakeConsole(os.path.join(tmp, "c"), websrv=False).start()
        try:
            src = omni()
            for path, data in src.files.items():
                fc.write(path, data)
            snap = {}
            for dp, _dn, fns in os.walk(fc.root):
                for fn in fns:
                    p = os.path.join(dp, fn)
                    st = os.stat(p)
                    snap[p] = (st.st_size, st.st_mtime_ns)
            with ps5.Console("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, timeout=10) as c:
                r = rl.export(c, os.path.join(tmp, "out"), epub_ids=["a.example-20261110-101010.html"],
                              today=datetime.date(2026, 11, 16), tz=UTC, now=NOW)
            self.assertEqual((r["pages"], r["epub"]["chapters"]), (3, 1))
            after = {}
            for dp, _dn, fns in os.walk(fc.root):
                for fn in fns:
                    p = os.path.join(dp, fn)
                    st = os.stat(p)
                    after[p] = (st.st_size, st.st_mtime_ns)
            self.assertEqual(after, snap)
            self.assertEqual(fc.state["deletes"], [])
            with open(os.path.join(r["path"], "pages", "a.example-20261110-101010.html"), "rb") as f:
                self.assertEqual(f.read(), PAGE_A)
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
