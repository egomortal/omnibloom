"""Search shortcuts / Quick access editor (shortcuts_edit.py): Omni's own parse rules, round trips, validation, caps,
and the .prev backup on the console (a dict) and on disk. No network."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import shortcuts_edit as se  # noqa: E402

E = se.Engine


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


class TemplateRules(unittest.TestCase):
    def test_good(self):
        for t in ("https://example.com/search?q=%s", "HTTPS://Example.COM/s/%s", "https://a.b:8443/?q=%s&x=%20y",
                  "https://example.com/#q=%s", "https://ex-ample.org/x?a=%s&b=%s"):
            self.assertTrue(se.valid_template(t), t)

    def test_bad(self):
        for t in ("http://example.com/?q=%s",          # https only
                  "https://example.com/?q=",           # no %s
                  "https://example.com%s",             # %s not after the host
                  "https://example.com",               # no path
                  "https://localhost/?q=%s",           # no dot
                  "https://user@example.com/?q=%s",    # credentials
                  "https://-ex.com/?q=%s", "https://.ex.com/?q=%s", "https://ex.com./?q=%s",
                  "https://ex.com:/?q=%s", "https://ex.com:123456/?q=%s", "https://ex.com:8a/?q=%s",
                  "https://ex.com/?q=%s&x=%zz", "https://ex.com/?q=%s%", "https://ex.com/?q=%s %s",
                  "https://ex.com/?q=\"%s\"", "https://ex.com/{%s}", "https://ex.com/?q=%sé",
                  "https://ex.com/?q=%s" + "a" * 1024):
            self.assertFalse(se.valid_template(t), t)

    def test_length_cap_exact(self):
        base = "https://ex.com/?q=%s&p="
        self.assertTrue(se.valid_template(base + "a" * (se.MAX_TEMPLATE - len(base))))
        self.assertFalse(se.valid_template(base + "a" * (se.MAX_TEMPLATE - len(base) + 1)))

    def test_prefix(self):
        for p in ("yt", "a", "my-site_2!", "x" * 16):
            self.assertTrue(se.valid_prefix(p), p)
        for p in ("", "x" * 17, "YT", "a b", "a.b", "é"):
            self.assertFalse(se.valid_prefix(p), p)


class ParseSearch(unittest.TestCase):
    def test_omni_rules(self):
        text = ("﻿# comment\r\n\r\n"
                "YT\thttps://www.youtube.com/results?search_query=%s\tTube\r\n"
                "yt\thttps://other.example/?q=%s\r\n"                 # repeat keyword: skipped
                "w https://en.wikipedia.org/w/index.php?search=%s\r\n"  # space form (no name)
                "bad\thttp://ex.com/?q=%s\r\n"                        # http: skipped
                "lonely\r\n"                                          # no template: skipped
                "n\thttps://ex.com/?q=%s\t  a\x01b  \r\n")
        items, bad = se.parse_search(text.encode("utf-8"))
        self.assertEqual([e.prefix for e in items], ["yt", "w", "n"])
        self.assertEqual(items[0].name, "Tube")
        self.assertEqual(items[1].name, "")
        self.assertEqual(items[2].name, "a b")
        self.assertEqual(bad, 3)
        self.assertEqual(se.display_name(items[1]), "Wikipedia")   # a built-in's host
        self.assertEqual(se.display_name(E("q", "https://www.ex.com/?q=%s", "")), "ex.com")

    def test_cap_30(self):
        text = "".join("k%d\thttps://ex.com/?q=%%s\n" % i for i in range(35))
        items, bad = se.parse_search(text)
        self.assertEqual(len(items), se.MAX_ENGINES)
        self.assertEqual(bad, 5)

    def test_name_cut_40_bytes(self):
        items, _ = se.parse_search("k\thttps://ex.com/?q=%s\t" + "é" * 30 + "\n")
        self.assertLessEqual(len(items[0].name.encode("utf-8")), se.MAX_NAME)

    def test_missing_and_empty(self):
        self.assertEqual(se.from_bytes("search", None).items, list(se.BUILTINS))
        self.assertFalse(se.from_bytes("search", None).exists)
        self.assertEqual(se.from_bytes("search", b"").items, [])


class SerializeSearch(unittest.TestCase):
    def test_round_trip(self):
        items = [E("yt", "https://www.youtube.com/results?search_query=%s", "YouTube"),
                 E("w", "https://en.wikipedia.org/w/index.php?search=%s", ""),
                 E("x9", "https://ex.com:8443/a/%s?b=%2F", "Café search")]
        data = se.serialize_search(items)
        self.assertTrue(data.startswith(b"# Omni search shortcuts"))
        self.assertIn(b"w\thttps://en.wikipedia.org/w/index.php?search=%s\n", data)   # no empty name column
        self.assertEqual(se.parse_search(data), (items, 0))
        self.assertEqual(se.serialize_search(se.parse_search(data)[0]), data)

    def test_builtins_round_trip_and_crlf(self):
        data = se.serialize_search(se.BUILTINS, "\r\n")
        self.assertEqual(se.newline_of(data), "\r\n")
        loaded = se.from_bytes("search", data)
        self.assertEqual(loaded.items, list(se.BUILTINS))
        self.assertEqual(se.serialize_search(loaded.items, loaded.newline), data)

    def test_normalizes(self):
        data = se.serialize_search([E("  YT ", " https://ex.com/?q=%s ", "  two   words\t")])
        self.assertEqual(se.parse_search(data)[0], [E("yt", "https://ex.com/?q=%s", "two words")])

    def test_rejects(self):
        cases = [[E("a", "https://ex.com/?q=", "")],              # no %s
                 [E("a", "http://ex.com/?q=%s", "")],             # http
                 [E("bad key", "https://ex.com/?q=%s", "")],
                 [E("a", "https://ex.com/?q=%s", ""), E("A", "https://ex.org/?q=%s", "")],   # repeat
                 [E("k%d" % i, "https://ex.com/?q=%s", "") for i in range(31)]]
        for items in cases:
            self.assertTrue(se.search_problems(items))
            with self.assertRaises(se.EditError):
                se.serialize_search(items)

    def test_problem_rows(self):
        items = [E("a", "https://ex.com/?q=%s", ""), E("a", "https://ex.org/?q=%s", ""), E("b", "https://ex.com/", "")]
        rows = [r for r, _ in se.search_problems(items)]
        self.assertEqual(rows, [1, 2])

    def test_cap_exactly_30_ok(self):
        items = [E("k%d" % i, "https://ex.com/?q=%s", "") for i in range(30)]
        self.assertEqual(len(se.parse_search(se.serialize_search(items))[0]), 30)

    def test_clean_name(self):
        self.assertEqual(se.clean_name(" a \n b "), "a b")
        self.assertEqual(se.clean_name("x" * 50), "x" * 40)
        cut = se.clean_name("€" * 20)        # 3 bytes each: 13 fit
        self.assertEqual(cut, "€" * 13)
        self.assertEqual(se.clean_name("a\u0085b c"), "abc")


class QuickAccess(unittest.TestCase):
    def test_parse_omni_rules(self):
        keys, skipped = se.parse_quick(b"dark\r\nublock  \n DARK\nnope\ndark\n\napps\n")
        self.assertEqual(keys, ["dark", "ublock", "apps"])
        self.assertEqual(skipped, 3)                 # " DARK" (leading space kept by Omni), unknown, repeat

    def test_parse_stops_at_six(self):
        data = "".join(k + "\n" for k in se.QUICK_KEYS).encode()
        keys, _ = se.parse_quick(data)
        self.assertEqual(keys, list(se.QUICK_KEYS[:6]))

    def test_long_line_split_like_fgets(self):
        # a 70-byte line is read as 63 bytes, then the rest: "ublock" padded past the buffer is not "ublock"
        keys, skipped = se.parse_quick(b"x" * 63 + b"reload\nfind\n")
        self.assertEqual(keys, ["reload", "find"])
        self.assertEqual(skipped, 1)

    def test_missing_and_empty(self):
        self.assertEqual(se.from_bytes("quick", None).items, list(se.QUICK_DEFAULTS))
        self.assertEqual(se.from_bytes("quick", b"").items, [])
        self.assertEqual(se.serialize_quick([]), b"")

    def test_round_trip(self):
        keys = ["settings", "reader", "ublock", "find"]
        data = se.serialize_quick(keys)
        self.assertEqual(data, b"settings\nreader\nublock\nfind\n")
        self.assertEqual(se.parse_quick(data), (keys, 0))

    def test_rejects(self):
        for keys in (["ublock", "ublock"], ["nope"], list(se.QUICK_KEYS[:7])):
            self.assertTrue(se.quick_problems(keys))
            with self.assertRaises(se.EditError):
                se.serialize_quick(keys)
        self.assertEqual(se.serialize_quick(list(se.QUICK_KEYS[:6])).count(b"\n"), 6)


class Saving(unittest.TestCase):
    def test_console_new_file(self):
        c = Console()
        data = se.serialize_quick(["apps"])
        self.assertIsNone(se.save_console(c, "quick", data))
        self.assertEqual(c.files, {se.QUICK_PATH: data})
        self.assertEqual(se.load_console(c, "quick").items, ["apps"])

    def test_console_prev_backup(self):
        old = b"yt\thttps://ex.com/?q=%s\n"
        c = Console({se.SEARCH_PATH: old})
        new = se.serialize_search([E("z", "https://ex.org/?q=%s", "Z")])
        parked = se.save_console(c, "search", new)
        self.assertEqual(parked, se.SEARCH_PATH + ".prev")
        self.assertEqual(c.files[se.SEARCH_PATH + ".prev"], old)
        self.assertEqual(c.files[se.SEARCH_PATH], new)
        newer = se.serialize_search([E("q", "https://ex.net/?q=%s", "")])
        self.assertEqual(se.save_console(c, "search", newer), se.SEARCH_PATH + ".prev-2")   # never overwritten
        self.assertEqual(c.files[se.SEARCH_PATH + ".prev"], old)
        self.assertNotIn(se.SEARCH_PATH + ".omnibloom-new", c.files)

    def test_console_same_bytes_untouched(self):
        data = se.serialize_quick(["dark"])
        c = Console({se.QUICK_PATH: data})
        self.assertIsNone(se.save_console(c, "quick", data))
        self.assertEqual(c.files, {se.QUICK_PATH: data})

    def test_local_prev(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "quick-access.txt")
            self.assertIsNone(se.save_local(path, b"apps\n"))
            prev = se.save_local(path, b"dark\n")
            self.assertEqual(prev, path + ".prev")
            with open(prev, "rb") as f:
                self.assertEqual(f.read(), b"apps\n")
            self.assertEqual(se.load_local(path, "quick").items, ["dark"])
            self.assertEqual(sorted(os.listdir(d)), ["quick-access.txt", "quick-access.txt.prev"])


if __name__ == "__main__":
    unittest.main()
