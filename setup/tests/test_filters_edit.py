"""My filters editor (filters_edit.py): Omni's own rules for ublock-user-filters.txt (OmniZapper.h), byte-exact round
trips, validation, caps, grouping by site, and the .prev backup on the console (a dict) and on disk. No network."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import backup, filters_edit as fe  # noqa: E402

P = fe.FILTERS_PATH


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
        assert dst not in self.files, "rename onto an existing file"
        self.files[dst] = self.files.pop(src)


SAMPLE = ("! Omni: my filters (uBlock Origin syntax). The element zapper adds host##selector lines.\n"
          "example.com##.ad-banner\n"
          "Example.COM , news.example.org##div#promo > a\n"
          "||ads.example.net^\n"
          "##.everywhere\n"
          "example.com#@#.ad-banner\n"
          "example.com##+js(nowebrtc)\n"
          "example.com##^script:has-text(ad)\n"
          "~example.com##.x\n"
          "example.*##.x\n"
          "news.example.org##p:has-text(Sponsored)\n"
          "\n"
          "[Adblock Plus 2.0]\n")


class Rules(unittest.TestCase):
    def test_hosts(self):
        for h in ("example.com", "a-b.c0", "1.2.3.4", "xn--bcher-kva.example", "localhost"):
            self.assertTrue(fe.valid_host(h), h)
        for h in ("", ".a.com", "a.com.", "a..com", "A.com", "~a.com", "a.*", "a_b.com", "x" * 254, "bücher.de"):
            self.assertFalse(fe.valid_host(h), h)

    def test_css_safe(self):
        for s in (".ad", "#promo > a", "div[data-x=\"a b\"]", "a:nth-of-type(2)", "x" * 280, "p:not(.keep)"):
            self.assertTrue(fe.css_safe(s), s)
        for s in ("", "x" * 281, "a{color:red}", "a;b", "div[data-x=\"a;b\"]", "a<b", "a\\b", "/*x*/a", "@media", ">a", "+a", "~a", ",a",
                  " a", "a)", "a(", "a[", "a]", "a\"", "a\x01", "a\x7f", "p:has-text(x)", "p:style(x)", "p:upward(2)"):
            self.assertFalse(fe.css_safe(s), s)

    def test_selector_cap_counts_bytes(self):
        self.assertTrue(fe.css_safe("é" * 140))        # 280 bytes
        self.assertFalse(fe.css_safe("é" * 141))       # 282 bytes, as Omni counts them

    def test_parse_line_kinds(self):
        k = {l: fe.parse_line(l).kind for l in SAMPLE.split("\n")}
        self.assertEqual(k["example.com##.ad-banner"], "rule")
        self.assertEqual(fe.parse_line("Example.COM , news.example.org##div#promo > a").hosts,
                         ("example.com", "news.example.org"))
        for l in ("||ads.example.net^", "##.everywhere", "example.com#@#.ad-banner", "example.com##+js(nowebrtc)",
                  "example.com##^script:has-text(ad)", "~example.com##.x", "example.*##.x",
                  "news.example.org##p:has-text(Sponsored)", "a.com,##.x", "﻿a.com##.x"):
            self.assertEqual(fe.parse_line(l).kind, "ignored", l)
            self.assertTrue(fe.parse_line(l).reason, l)
        self.assertEqual(k["[Adblock Plus 2.0]"], "comment")
        self.assertEqual(k[""], "blank")
        self.assertEqual(fe.parse_line("  a.com##.x \t\r").selector, ".x")


class RoundTrip(unittest.TestCase):
    def test_byte_identical(self):
        for data in (SAMPLE.encode(), SAMPLE.replace("\n", "\r\n").encode(), b"a.com##.x", b"a.com##.x\n\n\n",
                     b"", b"\xef\xbb\xbfa.com##.x\r\nb.com##.y", b"a.com##.\xff\xfebad\n", b"mixed##.a\r\nb.com##.b\n",
                     "über.de##.x\n".encode(), b"a.com##.x\r"):
            self.assertEqual(fe.FilterFile(data).to_bytes(), data, data)
            self.assertEqual(fe.FilterFile(data).serialize(), data, data)

    def test_rules_match_omni(self):
        f = fe.FilterFile(SAMPLE.encode())
        self.assertEqual(f.rules(), [("example.com", ".ad-banner"), ("example.com", "div#promo > a"),
                                     ("news.example.org", "div#promo > a")])

    def test_untouched_lines_kept_on_edit(self):
        data = SAMPLE.replace("\n", "\r\n").encode()
        f = fe.FilterFile(data)
        f.add_rule("shop.example.com", ".sidebar-ad")
        out = f.serialize()
        self.assertTrue(out.startswith(data))
        self.assertEqual(out[len(data):], b"shop.example.com##.sidebar-ad\r\n")

    def test_append_after_missing_final_newline(self):
        f = fe.FilterFile(b"a.com##.x")
        f.add_rule("b.com", ".y")
        self.assertEqual(f.serialize(), b"a.com##.x\nb.com##.y\n")

    def test_empty_file_gets_header_and_loses_it(self):
        f = fe.from_bytes(None)
        self.assertFalse(f.exists)
        f.add_rule("www.example.com", ".ad")
        self.assertEqual(f.serialize(), (fe.HEADER + "\nexample.com##.ad\n").encode())
        f.remove_host(1, "example.com")
        self.assertEqual(f.serialize(), b"")


class Edits(unittest.TestCase):
    def test_add_validation(self):
        f = fe.FilterFile(b"a.com##.x\n")
        for sites, sel in (("", ".x"), ("a b.com", ".x"), ("~a.com", ".x"), ("a.com", ""), ("a.com", "a{}"),
                           ("a.com", "p:has-text(x)"), ("a.com", ".x"), ("a.com", "x" * 281)):
            with self.assertRaises(fe.EditError, msg=(sites, sel)):
                f.add_rule(sites, sel)
        self.assertEqual(f.serialize(), b"a.com##.x\n")
        f.add_rule("A.com, b.com", ".x")             # b.com is new: one line for both, as uBlock writes them
        self.assertEqual(f.lines[-1], "a.com,b.com##.x")

    def test_per_host_cap(self):
        f = fe.from_bytes(None)
        for i in range(fe.MAX_PER_HOST):
            f.add_rule("a.com", ".x%d" % i)
        with self.assertRaises(fe.EditError):
            f.add_rule("a.com", ".one-more")
        f.add_rule("b.com", ".one-more")

    def test_line_cap(self):
        f = fe.FilterFile("".join("s%d.com##.x\n" % i for i in range(fe.MAX_LINES - 2)).encode())
        f.add_rule("last.com", ".x")                 # 2999 lines
        with self.assertRaises(fe.EditError):
            f.add_rule("more.com", ".x")             # the zapper stops at lines + 2 > 3000

    def test_over_cap_file_marked_and_refused(self):
        data = "".join("s%d.com##.x\n" % i for i in range(fe.MAX_LINES + 5)).encode()
        f = fe.FilterFile(data)
        self.assertEqual(f.seen, fe.MAX_LINES)
        self.assertEqual(len(f.rules()), fe.MAX_LINES)
        past = [r for r in f.rows() if r.index >= fe.MAX_LINES]
        self.assertEqual(len(past), 5)
        self.assertTrue(all(r.kind == "ignored" and "limit" in r.reason for r in past))
        with self.assertRaises(fe.EditError):
            f.serialize()
        big = b"a.com##.x\n" + b"! " + b"z" * fe.MAX_FILE + b"\nb.com##.y\n"
        g = fe.FilterFile(big)
        self.assertEqual(g.seen, 1)                  # cut at the last whole line inside 256 KB
        self.assertEqual(g.rules(), [("a.com", ".x")])
        with self.assertRaises(fe.EditError):
            g.serialize()

    def test_edit_rule_in_place_and_shared(self):
        f = fe.FilterFile(b"! c\r\na.com##.x\r\nb.com,c.com##.y\r\n! end\r\n")
        at = f.edit_rule(1, "a.com", "a.com", ".z")
        self.assertEqual(at, 1)
        self.assertEqual(f.serialize(), b"! c\r\na.com##.z\r\nb.com,c.com##.y\r\n! end\r\n")
        at = f.edit_rule(2, "c.com", "c.com", ".w")
        self.assertEqual(f.serialize(), b"! c\r\na.com##.z\r\nb.com##.y\r\nc.com##.w\r\n! end\r\n")
        before = f.serialize()
        with self.assertRaises(fe.EditError):
            f.edit_rule(1, "a.com", "a.com", "bad{")
        self.assertEqual(f.serialize(), before)      # all or nothing

    def test_delete(self):
        f = fe.FilterFile(SAMPLE.encode())
        f.remove_host(2, "news.example.org")
        self.assertEqual(f.lines[2], "example.com##div#promo > a")
        self.assertEqual(f.delete_site("example.com"), 6)   # 2 rules + #@#, +js, ##^, ~example.com
        self.assertEqual(f.rules(), [])
        self.assertIn("||ads.example.net^", f.lines)
        self.assertIn("example.*##.x", f.lines)

    def test_set_line(self):
        f = fe.FilterFile(b"! x\n||a^\n")
        f.set_line(1, "a.com##.ad")
        self.assertEqual(f.serialize(), b"! x\na.com##.ad\n")
        with self.assertRaises(fe.EditError):
            f.set_line(1, "a\nb")

    def test_import(self):
        f = fe.FilterFile(b"a.com##.x\n")
        r = f.import_text("a.com##.x\r\n\r\n  b.com##.y  \n||ads.example^\nb.com##+js(x)\n! note\n")
        self.assertEqual(r, {"added": 4, "applied": 1, "not_applied": 3, "same": 1, "left_out": 0})
        self.assertEqual(f.serialize(), b"a.com##.x\nb.com##.y\n||ads.example^\nb.com##+js(x)\n! note\n")
        g = fe.from_bytes(None)
        g.import_text("c.com##.z")
        self.assertEqual(g.lines, [fe.HEADER, "c.com##.z"])

    def test_import_caps(self):
        f = fe.FilterFile("".join("s%d.com##.x\n" % i for i in range(fe.MAX_LINES - 1)).encode())
        r = f.import_text("n1.com##.x\nn2.com##.x\n")
        self.assertEqual((r["added"], r["left_out"]), (1, 1))
        self.assertEqual(len(f.lines), fe.MAX_LINES)
        f.serialize()


class Grouping(unittest.TestCase):
    def test_groups(self):
        g = fe.FilterFile(SAMPLE.encode()).groups()
        self.assertEqual(list(g), ["example.com", "news.example.org", fe.OTHER, fe.COMMENTS])
        ex = g["example.com"]
        self.assertEqual([r.kind for r in ex], ["rule", "rule", "ignored", "ignored", "ignored", "ignored"])
        self.assertEqual([r.kind for r in g["news.example.org"]], ["rule", "ignored"])
        self.assertEqual([r.line for r in g[fe.OTHER]], ["||ads.example.net^", "##.everywhere", "example.*##.x"])
        self.assertEqual(len(g[fe.COMMENTS]), 2)
        c = fe.FilterFile(SAMPLE.encode()).counts()
        self.assertEqual(c, {"rules": 3, "sites": 2, "not_applied": 8, "comments": 2})


class Saving(unittest.TestCase):
    def test_console_prev_backup(self):
        c = Console()
        self.assertIsNone(fe.save_console(c, b"a.com##.x\n"))
        self.assertIsNone(fe.save_console(c, b"a.com##.x\n"))            # same bytes: nothing written
        self.assertEqual(fe.save_console(c, b"b.com##.y\n"), P + ".prev")
        self.assertEqual(c.files[P + ".prev"], b"a.com##.x\n")
        self.assertEqual(fe.save_console(c, b"c.com##.z\n"), P + ".prev-2")
        self.assertEqual(c.files[P + ".prev"], b"a.com##.x\n")
        self.assertEqual(fe.load_console(c).rules(), [("c.com", ".z")])
        self.assertFalse(fe.load_console(Console()).exists)

    def test_local(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ublock-user-filters.txt")
            self.assertIsNone(fe.save_local(path, b"a.com##.x\n"))
            self.assertEqual(fe.save_local(path, b"b.com##.y\n"), path + ".prev")
            self.assertEqual(fe.load_local(path).rules(), [("b.com", ".y")])
            self.assertEqual(fe.load_local(path + ".prev").serialize(), b"a.com##.x\n")


class Backup(unittest.TestCase):
    def test_opt_in_group(self):
        rule = backup.rule_for(P)
        self.assertEqual(rule["group"], "my-filters")
        self.assertIn("my-filters", backup.PERSONAL)
        self.assertEqual(rule["max"], fe.MAX_FILE)
        self.assertIsNone(backup.rule_for("/data/omni/ublock-allowlist.txt.x"))


class Privacy(unittest.TestCase):
    def test_logs_counts_only(self):
        msgs = []
        fe.save_console(Console(), b"secret-site.example##.x\n", log=msgs.append)
        self.assertTrue(msgs)
        self.assertFalse([m for m in msgs if "secret" in m or ".x" in m.replace(".txt", "")])


if __name__ == "__main__":
    unittest.main()
