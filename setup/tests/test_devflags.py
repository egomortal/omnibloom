"""Developer flags page: the table matches DEVELOPERS.md, the console is read with one listing, flags are created as
"1\\n" and removed by moving them aside, and nothing outside the table (or outside /data/omni) is ever touched."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from omnibloom_setup import devflags  # noqa: E402
from test_backup import Console  # noqa: E402   (the dict-backed fake console)

O = "/data/omni/"
DEVELOPERS_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "DEVELOPERS.md")
SECTION = "## Developer flags and override files"
TABLE_INTROS = {"Kill switches": devflags.KILL, "Opt-in": devflags.OPT_IN, "Override text files": devflags.OVERRIDE}


def _expand(cell):
    out = []
    for part in cell.replace("`", "").split(","):
        part = part.strip()
        m = re.match(r"(.*)s(\d+)\.\.s(\d+)(.*)\Z", part)
        if m:
            out += ["%ss%d%s" % (m.group(1), i, m.group(4)) for i in range(int(m.group(2)), int(m.group(3)) + 1)]
        elif part:
            out.append(part)
    return out


def doc_rows():
    """[(kind, files, effect, default, for, risk)] from DEVELOPERS.md's three tables (backticks dropped)."""
    with open(DEVELOPERS_MD, encoding="utf-8") as f:
        text = f.read()
    assert SECTION in text, "DEVELOPERS.md lost its developer flags section"
    body = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    rows, kind = [], None
    for line in body.splitlines():
        for intro, k in TABLE_INTROS.items():
            if line.startswith(intro):
                kind = k
        if not line.startswith("|") or line.startswith("| File") or line.startswith("| ---"):
            continue
        cells = [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]
        assert len(cells) == 5 and kind, line
        rows.append((kind, tuple(_expand(cells[0])), cells[1], cells[2], cells[3], cells[4]))
    return rows


class SyncWithDevelopersMd(unittest.TestCase):
    def test_same_names_in_both(self):
        doc = {(kind, n) for kind, files, *_ in doc_rows() for n in files}
        table = {(r["kind"], n) for r in devflags.ROWS for n in r["files"]}
        self.assertEqual(doc - table, set(), "in DEVELOPERS.md but not in devflags.ROWS")
        self.assertEqual(table - doc, set(), "in devflags.ROWS but not in DEVELOPERS.md")
        self.assertEqual(len(devflags.BY_NAME), sum(len(r["files"]) for r in devflags.ROWS))   # no name twice

    def test_same_words(self):
        doc = {files: rest for _, files, *rest in doc_rows()}
        for r in devflags.ROWS:
            self.assertEqual(doc.get(r["files"]), [r["effect"], r["default"], r["for"], r["risk"]], r["files"])

    def test_expands_ranges(self):
        self.assertIn("perf-a-s8-disabled.flag", devflags.FLAGS)
        self.assertEqual(len([n for n in devflags.FLAGS if n.startswith("perf-a-s") and n.endswith("-disabled.flag")]), 8)
        self.assertEqual(set(devflags.OVERRIDES), {"ua-desktop.txt", "ua-youtube-tv.txt", "jsc-env.txt", "raster-env.txt",
                                                   "video-quality.txt", "display-hz.txt"})


def console():
    return Console({
        O + "ytguard-off.flag": b"1\n",
        O + "ua-desktop.txt": b"Mozilla/5.0 test\n",
        O + "bookmarks.txt": b"keep\n",
        O + "browser-mode.flag": b"1\n",             # not a developer flag: never touched
        O + "pages-dev.flag/x": b"",                 # a folder named like a flag
    })


class State(unittest.TestCase):
    def test_one_listing_names_only(self):
        c = console()
        calls = []
        listing = c.listing
        c.listing = lambda d: (calls.append(d), listing(d))[1]
        s = devflags.state(c)
        self.assertEqual(calls, ["/data/omni"])
        self.assertEqual(c.reads, [])
        self.assertTrue(s["ytguard-off.flag"])
        self.assertTrue(s["ua-desktop.txt"])
        self.assertFalse(s["pages-dev.flag"])                    # folder, not a flag
        self.assertFalse(s["ubo-site-debug.flag"])
        self.assertEqual(set(s), set(devflags.BY_NAME))


class Apply(unittest.TestCase):
    def test_create_and_remove(self):
        c = console()
        cur = devflags.state(c)
        want = {n: cur[n] for n in devflags.FLAGS}
        want.update({"ytguard-off.flag": False, "yt-attest-log.flag": True, "perf-a-s3-disabled.flag": True})
        changes = devflags.plan(cur, want, ["ua-desktop.txt", "jsc-env.txt"])
        self.assertEqual(sorted(changes), sorted([("remove", "ytguard-off.flag"), ("create", "yt-attest-log.flag"),
                                                  ("create", "perf-a-s3-disabled.flag"), ("remove", "ua-desktop.txt")]))
        self.assertEqual(len(devflags.describe(changes)), 4)
        before_other = {p: d for p, d in c.files.items() if "bookmarks" in p or "browser-mode" in p}
        r = devflags.apply(c, changes, stamp="T")
        self.assertEqual(c.files[O + "yt-attest-log.flag"], b"1\n")
        self.assertEqual(c.files[O + "perf-a-s3-disabled.flag"], b"1\n")
        self.assertNotIn(O + "ytguard-off.flag", c.files)
        self.assertEqual(c.files[O + "ytguard-off.flag.before-setup-T"], b"1\n")       # moved aside, not deleted
        self.assertEqual(c.files[O + "ua-desktop.txt.before-setup-T"], b"Mozilla/5.0 test\n")
        self.assertEqual(sorted(r["created"]), ["perf-a-s3-disabled.flag", "yt-attest-log.flag"])
        self.assertEqual(len(r["removed"]), 2)
        for p, d in before_other.items():
            self.assertEqual(c.files[p], d)
        self.assertFalse([p for p in c.files if p.endswith(".omnibloom-new")])
        self.assertFalse([p for p in c.files if not p.startswith(O)])
        after = devflags.state(c)
        self.assertEqual(devflags.plan(after, want, ["ua-desktop.txt"]), [])

    def test_already_done_skipped_and_parked_name_free(self):
        c = console()
        c.files[O + "ytguard-off.flag.before-setup-T"] = b"old"
        r = devflags.apply(c, [("create", "ytguard-off.flag"), ("remove", "ubo-site-debug.flag")], stamp="T")
        self.assertEqual(sorted(r["skipped"]), ["ubo-site-debug.flag", "ytguard-off.flag"])
        r = devflags.apply(c, [("remove", "ytguard-off.flag")], stamp="T")
        self.assertEqual(r["removed"], [("ytguard-off.flag", "ytguard-off.flag.before-setup-T-2")])
        self.assertEqual(c.files[O + "ytguard-off.flag.before-setup-T"], b"old")

    def test_folder_with_flag_name_refused(self):
        c = console()
        before = dict(c.files)
        with self.assertRaises(devflags.FlagError):
            devflags.apply(c, [("create", "yt-attest-log.flag"), ("create", "pages-dev.flag")])
        self.assertEqual(c.files, before)


class Refusals(unittest.TestCase):
    BAD = ("browser-mode.flag", "bookmarks.txt", "../hub/x.flag", "/data/omni/ytguard-off.flag", "sub/ytguard-off.flag",
           "ytguard-off.flag/..", "..", "", None, 5, "YTGUARD-OFF.flag", "ytguard-off.flag\0", "addons-dev.flag",
           "yt-media-stop.txt", "ytguard-off.flag.before-setup-T")

    def test_unknown_names_and_paths(self):
        for bad in self.BAD:
            with self.assertRaises(devflags.FlagError, msg=repr(bad)):
                devflags.path_for(bad)
        for name in devflags.BY_NAME:
            self.assertEqual(devflags.path_for(name), O + name)

    def test_apply_writes_nothing_when_any_name_is_bad(self):
        for bad in self.BAD:
            c = console()
            before = dict(c.files)
            with self.assertRaises(devflags.FlagError, msg=repr(bad)):
                devflags.apply(c, [("create", "yt-attest-log.flag"), ("remove", bad)])
            self.assertEqual(c.files, before, repr(bad))
            with self.assertRaises(devflags.FlagError):
                devflags.plan({}, {bad: True})

    def test_overrides_never_created_and_flags_not_via_override_list(self):
        c = console()
        before = dict(c.files)
        with self.assertRaises(devflags.FlagError):
            devflags.apply(c, [("create", "jsc-env.txt")])
        with self.assertRaises(devflags.FlagError):
            devflags.plan({}, {"ua-desktop.txt": True})
        with self.assertRaises(devflags.FlagError):
            devflags.plan({}, {}, ["ytguard-off.flag"])
        with self.assertRaises(devflags.FlagError):
            devflags.apply(c, [("write", "ytguard-off.flag")])
        self.assertEqual(c.files, before)


if __name__ == "__main__":
    unittest.main()
