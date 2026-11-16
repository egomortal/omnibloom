"""Redaction: personal details go, technical details stay. Pure: no console, no files."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup.redaction import RULES, Redactor, redact  # noqa: E402


def r(text, **kw):
    return redact(text, salt=b"test", **kw)[0]


class Urls(unittest.TestCase):
    def test_host_becomes_hash_and_path_becomes_ellipsis(self):
        out = r("open https://www.youtube.com/watch?v=LXb3EKWsInQ now")
        self.assertRegex(out, r"^open https://<host-[0-9a-f]{6}>/… now$")
        self.assertNotIn("youtube", out)
        self.assertNotIn("LXb3EKWsInQ", out)

    def test_hash_is_stable_within_a_bundle_and_salted_between_bundles(self):
        a = Redactor(salt=b"one")
        x, y = a.redact("https://news.example.org/a"), a.redact("see https://NEWS.example.org/b?c=d")
        self.assertEqual(x.split("/…")[0], y.split(" ")[1].split("/…")[0])
        b = Redactor(salt=b"two")
        self.assertNotEqual(a.host_tag("news.example.org"), b.host_tag("news.example.org"))

    def test_bare_url_without_path_has_no_ellipsis(self):
        self.assertRegex(r("https://news.example.org"), r"^https://<host-[0-9a-f]{6}>$")
        self.assertRegex(r("https://news.example.org/"), r"^https://<host-[0-9a-f]{6}>$")

    def test_credentials_in_url_are_dropped(self):
        for s in ("ftp://alice:hunter2@files.example.com:2121/pub/x.zip", "https://alice@example.com/",
                  "http://user:p%40ss@10.1.2.3:8080/admin"):
            out, counts = redact(s, salt=b"t")
            for bad in ("alice", "hunter2", "p%40ss", "files.example.com", "10.1.2.3", "2121", "8080", "user:"):
                self.assertNotIn(bad, out, s)
            self.assertEqual(counts.get("user names and passwords in web addresses"), 1, s)

    def test_query_tokens_are_dropped(self):
        for s in ("https://x.com?token=abcdef123", "https://api.example.net/v1/x?access_token=ya29.a0AfH6SM&x=1",
                  "https://example.org/cb#id_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"):
            out = r(s)
            self.assertTrue(out.endswith("/…"), out)
            for bad in ("abcdef123", "ya29", "eyJ", "example", "x.com", "api."):
                self.assertNotIn(bad, out, s)

    def test_ipv6_and_ip_hosts(self):
        self.assertEqual(r("http://[2001:db8::1]:8080/a"), "http://<ip>/…")
        self.assertEqual(r("http://10.0.0.20:9090/x"), "http://<ip>/…")

    def test_local_omnibloom_pages_keep_port_and_path_but_not_query(self):
        self.assertEqual(r("http://127.0.0.1:8765/downloads?id=5#frag"), "http://127.0.0.1:8765/downloads")
        self.assertEqual(r("http://localhost:2121/hub/"), "http://localhost:2121/hub/")

    def test_other_schemes(self):
        self.assertRegex(r("wss://live.example.tv/socket?sid=1"), r"^wss://<host-[0-9a-f]{6}>/…$")
        self.assertRegex(r("file://server.example.com/share"), r"^file://<host-[0-9a-f]{6}>/…$")

    def test_bare_site_names_use_the_same_hash(self):
        red = Redactor(salt=b"s")
        a = red.redact("https://news.example.org/x")
        b = red.redact("visited news.example.org today")
        self.assertIn(a[len("https://"):-2], b)


class Addresses(unittest.TestCase):
    def test_ipv4(self):
        self.assertEqual(r("connect 10.20.30.40:2121 ok"), "connect <ip>:2121 ok")
        self.assertEqual(r("from 192.168.0.5."), "from <ip>.")

    def test_loopback_and_versions_stay(self):
        self.assertEqual(r("127.0.0.1 Mesa 26.2.0 build 1.2.3.400"), "127.0.0.1 Mesa 26.2.0 build 1.2.3.400")

    def test_ipv6(self):
        out, counts = redact("up fe80::1%en0 and 2001:db8:0:0:1:2:3:4 and 2001:0db8:85a3::8a2e:0370:7334", salt=b"t")
        self.assertEqual(out, "up <ip> and <ip> and <ip>")
        self.assertEqual(counts.get("IP addresses"), 3)

    def test_times_and_loopback6_are_not_ipv6(self):
        self.assertEqual(r("2026-11-15 12:34:56 ::1 [0.5] 00:01:02"), "2026-11-15 12:34:56 ::1 [0.5] 00:01:02")

    def test_mac(self):
        self.assertEqual(r("pad aa:bb:cc:dd:ee:ff paired, wifi 00-1A-2B-3C-4D-5E"), "pad <mac> paired, wifi <mac>")

    def test_email(self):
        self.assertEqual(r("from someone.name+tag@mail.example.co.uk."), "from <email>.")


class Secrets(unittest.TestCase):
    def test_key_value(self):
        for s, want in (("password=hunter2", "password=<secret>"), ("cookie: SID=abc", "cookie: <secret>"),
                        ('{"token": "abc123"}', '{"token": "<secret>"}'), ("api_key=XYZ;", "api_key=<secret>;")):
            self.assertEqual(r(s), want)

    def test_bearer_and_jwt(self):
        out = r("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc")
        self.assertNotIn("eyJ", out)
        self.assertIn("<secret>", out)

    def test_long_hex_and_base64_runs(self):
        self.assertEqual(r("sha 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 end"), "sha <secret> end")
        self.assertEqual(r("blob aGVsbG8gd29ybGQgdGhpcyBpcyBhIHRva2VuIQ== end"), "blob <secret> end")
        self.assertEqual(r("id 0123456789abcdef01234567"), "id <secret>")       # exactly 24 hex

    def test_short_runs_words_and_paths_stay(self):
        for s in ("0123456789abcdef0123456",                                  # 23 hex: below the line
                  "OmniJDownloaderBridge2026Build",
                  "omnibloom-diagnostics-20261116-084512",
                  "/data/omni/native/omni-engine-child.elf",
                  "/data/omni-downloader/jdownloader/native/java25-vm-trace.log",
                  "libSceAgc.sprx app.js boot.log uv=1234567 OMNI_CRASH_V2 pid=152"):
            self.assertEqual(r(s), s)

    def test_token_inside_a_path(self):
        out = r("/data/cache/Zk9xQ2tLmN8pR4sT7vW1yA3bC6dE/file.bin")
        self.assertEqual(out, "/data/cache/<secret>/file.bin")


class HomesAndUsers(unittest.TestCase):
    def test_windows_homes(self):
        self.assertEqual(r(r"C:\Users\Jane Doe\Downloads\x.zip"), r"<home>\Downloads\x.zip")
        self.assertEqual(r("c:/users/bob/AppData/x"), "<home>/AppData/x")

    def test_unix_and_ps5_homes(self):
        self.assertEqual(r("/home/bob/x /Users/alice/y /user/home/1a2b3c4d/savedata"),
                         "<home>/x <home>/y <home>/savedata")
        self.assertEqual(r("/data/omni/home.txt"), "/data/omni/home.txt")

    def test_user_names(self):
        self.assertEqual(r("signed in as GamerTag_99 (gamertag_99)", user_names=["GamerTag_99"]),
                         "signed in as <user> (<user>)")
        self.assertEqual(r(r"C:\Users\ann lee\x", user_names=["ann lee"]), r"<home>\x")

    def test_short_or_common_names_are_not_used(self):
        self.assertEqual(r("omni boot ok ab", user_names=["omni", "ab"]), "omni boot ok ab")


class Misc(unittest.TestCase):
    def test_media_ids(self):
        self.assertEqual(r("page vid=LXb3EKWsInQ list=PLabcdef"), "page vid=<removed> list=<removed>")

    def test_file_names_and_intent_names_are_not_sites(self):
        self.assertEqual(r("download.url theme.changed boot.log hub.elf"), "download.url theme.changed boot.log hub.elf")

    def test_counts_and_rules(self):
        _, counts = redact("https://a.example.com/x 10.0.0.1 a@b.com aa:bb:cc:dd:ee:ff password=x", salt=b"t")
        for what in ("web addresses", "IP addresses", "e-mail addresses", "hardware addresses",
                     "passwords, tokens and keys"):
            self.assertEqual(counts.get(what), 1, what)
        self.assertGreaterEqual(len(RULES), 8)

    def test_idempotent(self):
        once = r("https://u:p@x.example.com/a?b=c 10.1.1.1 a@b.com C:\\Users\\bob\\x")
        self.assertEqual(r(once), once)


if __name__ == "__main__":
    unittest.main()
