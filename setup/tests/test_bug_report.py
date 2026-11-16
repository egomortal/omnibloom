"""Bug report: strong redaction corpus, the issue URL stays short, and nothing happens before the user confirms."""
import os
import sys
import tempfile
import unittest
import urllib.parse
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import bug_report, config  # noqa: E402
from omnibloom_setup.redaction import Redactor  # noqa: E402


def sr(text, users=("alice",)):
    return bug_report.strong_redact(text, Redactor(salt=b"t", user_names=users))


# (input, things that must be gone)
POSITIVE = [
    ("connect 192.168.0.23:2121 failed", ["192.168.0.23"]),
    ("public 8.8.4.4 and 203.0.113.9", ["8.8.4.4", "203.0.113.9"]),
    ("lan fe80::1c2b:3cff:fe4d:5e6f%eth0", ["fe80::1c2b"]),
    ("wifi aa:bb:cc:dd:ee:ff up", ["aa:bb:cc:dd:ee:ff"]),
    ("eth AA-BB-CC-11-22-33", ["AA-BB-CC-11-22-33"]),
    ("mail alice@example.com please", ["alice@example.com"]),
    ("from bob.smith+ps5@mail.example.co.uk", ["bob.smith", "mail.example"]),
    (r"open C:\Users\alice\AppData\Local\x.log", ["alice"]),
    (r"open C:\Users\Alice Smith\Documents\omni\x.log", ["Alice Smith", "Smith"]),
    (r"open D:\Users\carol jones\x", ["carol jones"]),
    ("open C:/Users/dave/Downloads/a.zip", ["dave"]),
    (r'"path": "C:\\Users\\erin\\Desktop"', ["erin"]),
    ("cd /home/frank/omni", ["frank"]),
    ("cd /mnt/c/Users/grace/Downloads", ["grace"]),
    ("cd /mnt/d/Users/heidi lee/x", ["heidi"]),
    (r"\\wsl$\Ubuntu\home\ivan\build", ["ivan"]),
    (r"\\wsl.localhost\Debian\home\judy\x", ["judy"]),
    ("/Users/mallory/Library", ["mallory"]),
    ("token=9f86d081884c7d659a2feaa0c55ad015", ["9f86d081884c7d659a2feaa0c55ad015"]),
    ("api_key=AKIAabcdEFGH1234", ["AKIAabcdEFGH1234"]),
    ("key=YWJjZGVmZ2hpams=", ["YWJjZGVmZ2hpams="]),
    ("Authorization: Bearer abc.def-ghi_jkl123", ["abc.def-ghi_jkl123"]),
    ("Authorization: token ghp_abcdefghijklmnop1234", ["ghp_abcdefghijklmnop1234"]),
    ("authorization=Basic YWxpY2U6aHVudGVyMg==", ["YWxpY2U6aHVudGVyMg"]),
    ("Cookie: SID=x1; HSID=y2", ["SID=x1", "HSID=y2"]),
    ("X-Api-Key: shortkey99", ["shortkey99"]),
    ("loose 3q2+7wAAAAAZm9vYmFyYmF6cXV4MTIzNDU2Nzg5MA==", ["Zm9vYmFyYmF6cXV4"]),
    ("onlineId=alice_ps5", ["alice_ps5"]),
    ('"onlineId": "trent99"', ["trent99"]),
    ("accountId: 1234567890123456789", ["1234567890123456789"]),
    ("psn_id=peggy-x", ["peggy-x"]),
    ("serial=MJ123456789", ["MJ123456789"]),
    ("console_id=0x00000001000000aa", ["0x00000001000000aa"]),
    ("idps=00000001008f000a1404ffff", ["00000001008f000a"]),
    ("open_psid=1a2b3c4d", ["1a2b3c4d"]),
    ("GET https://api.example.net/v1/x?access_token=ya29.zzz&user=alice", ["ya29", "api.example", "alice"]),
    ("http://127.0.0.1:8765/downloads?id=5&q=secret", ["id=5", "q=secret"]),
    ("tab 3 (private) https://shop.example.org/cart", ["shop.example", "<host-"]),
    ("incognito tab opened news.example.org", ["news.example", "<host-"]),
    ("user alice logged in", ["alice"]),
    ("https://user:pw@files.example.com/x", ["user:pw", "files.example"]),
]

# (input, text that must survive unchanged inside the output)
NEGATIVE = [
    ("Mesa 26.2.0 build 1.2.3.400", "Mesa 26.2.0 build 1.2.3.400"),
    ("loopback 127.0.0.1 ok", "127.0.0.1"),
    ("time 12:34:56 elapsed", "12:34:56"),
    ("firmware 13.60 ok", "13.60"),
    ("opened /data/omni/native/boot.log", "/data/omni/native/boot.log"),
    (r"C:\Program Files\Omnibloom\setup.exe", r"C:\Program Files\Omnibloom\setup.exe"),
    (r"D:\Games\omni\x.log", r"D:\Games\omni\x.log"),
    ("/mnt/c/Program Files/x", "/mnt/c/Program Files/x"),
    ("http://localhost:2121/hub/", "http://localhost:2121/hub/"),
    ("frames=60 dropped=0", "frames=60 dropped=0"),
    ("GL_RGBA8 texture 1920x1080", "GL_RGBA8 texture 1920x1080"),
    ("private browsing setting saved", "private browsing setting saved"),
    ("keyboard layout en-US", "keyboard layout en-US"),
    ("module libSceVideoOut.sprx loaded", "libSceVideoOut.sprx"),
    ("status=200 bytes=1048576", "status=200 bytes=1048576"),
    ("Users list empty", "Users list empty"),
]


class Corpus(unittest.TestCase):
    def test_positive(self):
        for text, gone in POSITIVE:
            out = sr(text)
            for bad in gone:
                self.assertNotIn(bad, out, "%r -> %r" % (text, out))

    def test_negative(self):
        for text, keep in NEGATIVE:
            out = sr(text)
            self.assertIn(keep, out, "%r -> %r" % (text, out))

    def test_windows_path_with_spaces_keeps_the_rest_of_the_path(self):
        self.assertEqual(sr(r"C:\Users\Alice Smith\AppData\Local\omni.log", users=()), r"<home>\AppData\Local\omni.log")

    def test_wsl_paths(self):
        self.assertEqual(sr("/mnt/c/Users/bob/omni/x.log", users=()), "<home>/omni/x.log")
        self.assertEqual(sr(r"\\wsl$\Ubuntu\home\bob\x", users=()), r"\\wsl$\Ubuntu\<home>\x")

    def test_idempotent(self):
        once = sr("Authorization: Bearer abcdefgh12345678 onlineId=bob 10.0.0.2")
        self.assertEqual(sr(once), once)


def _bundle(text="boot ok from 10.0.0.7 user alice\n"):
    return {"created": "2026-11-16T00:00:00Z", "setup_version": "0.1.0", "skipped": [], "removed": {"IP addresses": 1},
            "entries": [{"name": "omni/boot.log", "source": "/data/omni/native/boot.log", "bytes": 1, "truncated": False,
                         "text": text}],
            "versions": {"setup_version": "0.1.0", "firmware": "13.60",
                         "installed_apps": {"omni": {"name": "Omni", "version": "0.5.1"}}}}


class IssueUrl(unittest.TestCase):
    def test_short_body_is_whole_and_repo_comes_from_config(self):
        url = bug_report.new_issue_url("Crash", "it crashed")
        self.assertTrue(url.startswith("https://github.com/%s/issues/new?" % config.GITHUB_REPO))
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q["title"], ["Crash"])
        self.assertEqual(q["body"], ["it crashed"])

    def test_long_body_is_capped(self):
        for limit in (500, 2000, bug_report.MAX_URL):
            body = ("é line with spaces & symbols #%\n" * 5000)
            url = bug_report.new_issue_url("t" * 500, body, max_url=limit)
            self.assertLessEqual(len(url), limit)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            self.assertIn("cut to fit", q["body"][0])
            self.assertLessEqual(len(q["title"][0]), bug_report.TITLE_MAX)

    def test_report_url_fits_with_huge_summary(self):
        rep = bug_report.BugReport(_bundle(), summary="x y " * 10000)
        self.assertLessEqual(len(rep.issue_url()), bug_report.MAX_URL)


class Flow(unittest.TestCase):
    def test_body_has_versions_firmware_and_attach_note_and_is_redacted(self):
        rep = bug_report.BugReport(_bundle(), summary="Omni froze at 192.168.0.9 for carol@example.com",
                                   user_names=["alice"])
        for want in ("0.5.1", "13.60", "attach the diagnostics zip", "yourself"):
            self.assertIn(want, rep.body)
        text = rep.review_text()
        for bad in ("192.168.0.9", "carol@example.com", "10.0.0.7", "alice"):
            self.assertNotIn(bad, text)
            self.assertNotIn(bad, rep.title)
        self.assertIn(rep.body, text)

    def test_nothing_happens_before_confirm(self):
        opened, saved = [], []
        rep = bug_report.BugReport(_bundle())
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "report.zip")
            with self.assertRaises(bug_report.NotConfirmed):
                rep.submit(path, opener=opened.append, saver=lambda b, p: saved.append(p))
            self.assertEqual((opened, saved), ([], []))
            self.assertFalse(os.path.exists(path))
            rep.confirm()
            got_path, url = rep.submit(path, opener=opened.append)
            self.assertEqual(opened, [url])
            self.assertTrue(url.startswith("https://github.com/"))
            with zipfile.ZipFile(got_path) as z:
                boot = z.read("omni/boot.log").decode()
            self.assertNotIn("10.0.0.7", boot)
            self.assertIn(boot.rstrip("\n"), rep.review_text())   # what was shown is what was saved

    def test_module_never_imports_network_clients(self):
        src = open(bug_report.__file__, encoding="utf-8").read()
        for bad in ("urllib.request", "http.client", "requests", "socket", "ftplib"):
            self.assertNotIn("import " + bad, src)


if __name__ == "__main__":
    unittest.main()
