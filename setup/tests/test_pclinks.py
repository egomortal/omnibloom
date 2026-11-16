"""Send a link to Omni (pclinks.py): the link check (same rules as OmniPcLinks.h / OmniSendLink.h), the inbox file
over FTP to the fake console (verified upload, new name each time, never a delete), the send-link POST, and the page."""
import datetime
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omnibloom_setup import pclinks as pl  # noqa: E402

try:
    from tests.fake_console import FakeConsole
except ImportError:
    from fake_console import FakeConsole

NOW = datetime.datetime(2026, 11, 16, 12, 30, 5)


class ValidUrl(unittest.TestCase):
    def test_good(self):
        for u in ("https://example.com", "http://example.com/a?b=c#d", "HTTPS://Example.com/x", "https://a.b:8443/",
                  "https://[2001:db8::1]:443/p", "https://10.0.0.5/", "https://bücher.de/straße",
                  "https://example.com/" + "a" * 2000):
            self.assertIsNotNone(pl.valid_url(u), u)
        self.assertEqual(pl.valid_url("  HTTPS://Example.com/X \n"), "https://Example.com/X")

    def test_bad(self):
        for u in ("", "ftp://example.com", "javascript:alert(1)", "data:text/html,x", "file:///etc/passwd",
                  "https://user:pw@example.com/", "https://user@example.com", "https://exa mple.com",
                  "https://example.com/a b", "https://example.com/\x00", "https://ex\\ample.com", "https://",
                  "https://:80/", "https://a.com:0/", "https://a.com:65536/", "https://a.com:/", "https://a:1:2/",
                  "https://[zz::1]/", "https://a.com/ ", "https://exa$mple.com/", "https://a.com/\x85",
                  "https://example.com/" + "a" * 2030, None, 5):
            self.assertIsNone(pl.valid_url(u), repr(u))

    def test_2048_bytes_counts_utf8(self):
        base = "https://a.com/"
        self.assertIsNotNone(pl.valid_url(base + "a" * (2048 - len(base))))
        self.assertIsNone(pl.valid_url(base + "a" * (2049 - len(base))))
        self.assertIsNone(pl.valid_url(base + "é" * 1020))   # 14 + 2040 bytes


class ParseInput(unittest.TestCase):
    def test_lines_spaces_scheme_and_repeats(self):
        links, bad = pl.parse_input("example.com/page\n https://a.org  <https://b.net/x>\nnot a link\nhttps://a.org\n")
        self.assertEqual(links, ["https://example.com/page", "https://a.org", "https://b.net/x"])
        self.assertEqual(bad, 3)   # "not", "a", "link": not hosts (the repeat is dropped, not counted)
        links, bad = pl.parse_input("javascript:alert(1) mailto:x@y.z")
        self.assertEqual((links, bad), ([], 2))

    def test_shortcut_file(self):
        text = "[InternetShortcut]\r\nURL=https://example.com/a?b=1\r\nIconIndex=0\r\n"
        self.assertEqual(pl.parse_input(text), (["https://example.com/a?b=1"], 0))

    def test_too_many(self):
        many = "\n".join("https://s%d.example.com" % i for i in range(21))
        with self.assertRaises(pl.SendError):
            pl.parse_input(many)
        self.assertEqual(len(pl.parse_input("\n".join(many.split("\n")[:20]))[0]), 20)

    def test_site(self):
        self.assertEqual(pl.site("https://WWW.Example.com:8443/x?y"), "www.example.com")
        self.assertEqual(pl.site("https://[::1]:9/"), "[::1]")
        self.assertEqual(pl.site("nope"), "")


class InboxFile(unittest.TestCase):
    def test_text_and_name(self):
        self.assertEqual(pl.file_text(["https://a.com", "http://b.org/x"]), "omni-pc-links\t1\nhttps://a.com\nhttp://b.org/x\n")
        self.assertEqual(pl.file_name(NOW, "a1b2c3"), "links-20261116-123005-a1b2c3.txt")
        self.assertTrue(pl.NAME_RE.match(pl.file_name()))
        for bad in ([], ["https://u:p@a.com"], ["https://a.com/%d" % i for i in range(21)]):
            with self.assertRaises(pl.SendError):
                pl.file_text(bad)


class OverFtp(unittest.TestCase):
    def setUp(self):
        from omnibloom_setup import ps5
        self.ps5 = ps5
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-pcl-")
        self.fc = FakeConsole(os.path.join(self.tmp, "c"), websrv=False).start()

    def tearDown(self):
        self.fc.stop()

    def console(self):
        return self.ps5.Console("127.0.0.1", ftp_port=self.fc.ftp_port, loader_port=self.fc.loader_port, timeout=10)

    def test_send_creates_inbox_and_new_file_each_time(self):
        self.assertFalse(self.fc.exists(pl.INBOX))
        logs = []
        with self.console() as c:
            r1 = pl.send_inbox(c, ["https://a.com/1"], now=NOW, rand="000001", log=logs.append)
            r2 = pl.send_inbox(c, ["https://b.com/2", "https://c.com/3"], now=NOW, rand="000001")
        self.assertEqual(r1["path"], "/data/omni/inbox/links-20261116-123005-000001.txt")
        self.assertNotEqual(r2["path"], r1["path"])   # same second, same random bytes: a new name
        self.assertEqual((r2["links"], r2["waiting"]), (2, 2))
        self.assertEqual(self.fc.read(r1["path"]), b"omni-pc-links\t1\nhttps://a.com/1\n")
        self.assertEqual(self.fc.read(r2["path"]), b"omni-pc-links\t1\nhttps://b.com/2\nhttps://c.com/3\n")
        self.assertEqual(len(self.fc.listdir(pl.INBOX)), 2)   # no .omnibloom-new left behind
        self.assertEqual(self.fc.state["deletes"], [])
        self.assertEqual(logs, ["Sent 1 link to Omni's inbox."])
        self.assertNotIn("a.com", " ".join(logs))

    def test_full_inbox_refused(self):
        for i in range(pl.MAX_FILES):
            self.fc.write(pl.INBOX + "/links-20261116-120000-%06x.txt" % i, b"omni-pc-links\t1\nhttps://x.com\n")
        self.fc.write(pl.INBOX + "/other.txt", b"x")
        with self.console() as c:
            with self.assertRaises(pl.SendError) as e:
                pl.send_inbox(c, ["https://a.com"], now=NOW)
        self.assertIn("20 earlier sends", str(e.exception))
        self.assertEqual(len(self.fc.listdir(pl.INBOX)), pl.MAX_FILES + 1)

    def test_bad_link_never_uploaded(self):
        with self.console() as c:
            with self.assertRaises(pl.SendError):
                pl.send_inbox(c, ["https://u:p@a.com"])
        self.assertFalse(self.fc.exists(pl.INBOX))


class Direct(unittest.TestCase):
    """send_direct against a stub of Omni's send-link server (OmniSendLink::handle's replies)."""

    def setUp(self):
        got = self.got = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                got.append((self.path, self.headers["Content-Type"], body))
                ok = body["code"] == "123456"
                msg = "Sent. It opens in a new tab on the console." if ok else "Wrong code. Check the code shown in Omni."
                data = json.dumps({"ok": ok, "message": msg}).encode()
                self.send_response(200 if ok else 403)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()

    def test_sent(self):
        n = pl.send_direct("127.0.0.1", ["https://a.com", "https://b.com"], "123 456", port=self.port)
        self.assertEqual(n, 2)
        self.assertEqual(self.got[0], ("/send", "application/json", {"url": "https://a.com", "code": "123456"}))

    def test_wrong_code_shows_omnis_message(self):
        with self.assertRaises(pl.SendError) as e:
            pl.send_direct("127.0.0.1", ["https://a.com"], "000000", port=self.port)
        self.assertIn("Wrong code", str(e.exception))

    def test_refused_before_network(self):
        for code in ("", "12345", "abcdef"):
            with self.assertRaises(pl.SendError):
                pl.send_direct("127.0.0.1", ["https://a.com"], code, port=self.port)
        with self.assertRaises(pl.SendError):
            pl.send_direct("127.0.0.1", ["ftp://a.com"], "123456", port=self.port)
        self.assertEqual(self.got, [])

    def test_no_answer(self):
        self.srv.shutdown()
        self.srv.server_close()
        with self.assertRaises(pl.SendError) as e:
            pl.send_direct("127.0.0.1", ["https://a.com"], "123456", port=self.port, timeout=2)
        self.assertIn("didn't answer", str(e.exception))
        self.srv = None


class Page(unittest.TestCase):
    """The Setup page against the fake console: paste, preview, Send."""

    def test_page_sends_to_inbox(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as e:   # no display
            self.skipTest("no Tk display: %s" % e)
        from omnibloom_setup import gui
        tmp = tempfile.mkdtemp(prefix="omnibloom-pclgui-")
        fc = FakeConsole(os.path.join(tmp, "c"), websrv=False).start()
        try:
            root.withdraw()
            app = gui.SetupApp(root, test_ports={"ftp": fc.ftp_port, "loader": fc.loader_port, "host": "127.0.0.1"})
            root.clipboard_clear()
            root.clipboard_append("example.com/from-clipboard")
            app.page_send_link()
            root.update()
            self.assertEqual(app.pl_text.get("1.0", "end").strip(), "example.com/from-clipboard")   # offered, not sent
            self.assertFalse(fc.exists(pl.INBOX))
            app._pl_set("not a link")
            self.assertIn("isn't a web address", app.pl_preview.cget("text"))
            app._pl_send()
            self.assertIn("Paste a web address", app.pl_note.cget("text"))
            app._pl_set("https://www.example.com/a\nexample.org")
            self.assertEqual(app.pl_preview.cget("text"), "2 links: www.example.com, example.org")
            app._pl_send()
            end = time.time() + 20
            while time.time() < end and not app.pl_note.cget("text").startswith("Sent"):
                root.update()
                time.sleep(0.03)
            self.assertTrue(app.pl_note.cget("text").startswith("Sent. Omni asks about the 2 links"), app.pl_note.cget("text"))
            names = fc.listdir(pl.INBOX)
            self.assertEqual(len(names), 1)
            self.assertEqual(fc.read(pl.INBOX + "/" + names[0]),
                             b"omni-pc-links\t1\nhttps://www.example.com/a\nhttps://example.org\n")
            self.assertEqual(fc.state["deletes"], [])
        finally:
            fc.stop()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
