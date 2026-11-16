"""S15 settings catalog / editor (settings_catalog.py, settings_editor.py): completeness against backup.py's settings
group, Omni's exact file formats (golden strings from the Omni patch scripts' serialize functions), validation, the
no-touch list and the .prev upload. No network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import backup, config, settings_catalog as sc, settings_editor as ed  # noqa: E402

O = "/data/omni/"


def E(name):
    return sc.BY_PATH[name if name.startswith("/") else O + name]


def ser(name, values=None, old=None):
    e = E(name)
    vals = sc.parse(e, None)
    vals.update(values or {})
    return sc.serialize(e, vals, old)


class Console:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.writes = []

    def exists(self, path):
        return path in self.files

    def listing(self, parent):
        return {p.rsplit("/", 1)[1]: {} for p in self.files if p.rsplit("/", 1)[0] == parent.rstrip("/")}

    def makedirs(self, path):
        pass

    def read(self, path):
        return self.files[path]

    def put_verified(self, path, data, readback=True):
        self.writes.append(path)
        self.files[path + ".omnibloom-new"] = data
        return path + ".omnibloom-new"

    def rename(self, src, dst):
        assert dst not in self.files, "rename onto an existing file"
        self.files[dst] = self.files.pop(src)


class Completeness(unittest.TestCase):
    def test_every_backup_settings_file_is_described(self):
        missing = [f["path"] for f in backup.FILES if f["group"] == "settings" and f["path"] not in sc.BY_PATH]
        self.assertEqual(missing, [], "backup.py's settings group has files the settings catalog doesn't describe")

    def test_catalog_only_holds_settings_files(self):
        settings = {f["path"] for f in backup.FILES if f["group"] == "settings"}
        self.assertEqual(sorted(set(sc.BY_PATH) - settings), [])

    def test_every_entry_is_complete(self):
        for e in sc.CATALOG:
            self.assertIn(e["group"], sc.GROUPS, e["path"])
            self.assertTrue(e["desc"], e["path"])
            if e["path"] in sc.EDITABLE:
                self.assertTrue(e["fields"] and e["source"], e["path"])
                for f in e["fields"]:
                    self.assertTrue(f["label"], e["path"])
                    self.assertIsNotNone(sc.accept(f, f["default"]) if not f["optional"] else "", (e["path"], f))
            else:
                self.assertFalse(e["fields"], e["path"])
                self.assertTrue(e["where"] or e["format"] == sc.INTERNAL, e["path"])

    def test_defaults_serialize_and_round_trip(self):
        for p in sc.EDITABLE:
            e = sc.BY_PATH[p]
            data = sc.serialize(e, sc.parse(e, None))
            self.assertEqual(sc.parse(e, data), sc.parse(e, None), p)


class Golden(unittest.TestCase):
    """Bytes as each file's Omni save writes them (strings from the apply_*.py serialize functions)."""

    def test_night_light(self):
        self.assertEqual(ser("night-light.txt"), b"# Omni night light (OMNI_NIGHT_LIGHT_V1)\nmode\toff\nlast\ton\n"
                                                 b"warmth\t3\nstart\t21:00\nend\t07:00\n")
        e = E("night-light.txt")
        v = sc.parse(e, "mode\tscheduled\r\nlast\toff\nwarmth\t9\nstart\t7:30\nend\t23\n")
        self.assertEqual((v["mode"], v["last"], v["warmth"], v["start"], v["end"]), ("scheduled", "on", "3", "07:30", "23:00"))

    def test_colour_filter(self):
        self.assertEqual(ser("colour-filter.txt", {"filter": "greyscale"}),
                         b"# Omni colour filter (OMNI_COLOUR_FILTER_V1)\nfilter\tgreyscale\nlast\tdeuteranopia\n")

    def test_tab_sleep(self):
        self.assertEqual(ser("tab-sleep.txt"), b"minutes\t30\npinned\t0\n")
        v = sc.parse(E("tab-sleep.txt"), "minutes\t45 \npinned\t7\n")
        self.assertEqual((v["minutes"], v["pinned"]), ("30", "1"))     # snapped (ties go to the smaller step), != 0

    def test_spatial_scroll_site_search(self):
        self.assertEqual(ser("spatial-nav.txt", {"mode": "1"}), b"mode\t1\n")
        self.assertEqual(ser("scroll-plus.txt", {"speed": "2"}), b"speed\t2\n")
        self.assertEqual(ser("scroll-plus.txt", {"smooth": "0"}), b"speed\t1\nsmooth\t0\n")
        self.assertEqual(ser("site-search.txt", {"offer": "0"}), b"offer\t0\n")

    def test_data_saver(self):
        self.assertEqual(ser("data-saver.txt", {"on": "1"}),
                         b"omni-data-saver\t1\non\t1\nvideo\t1\nautoplay\t1\nfonts\t0\nprefetch\t1\n")
        self.assertEqual(sc.parse(E("data-saver.txt"), "on\t1\n")["on"], "0")   # no header: all defaults
        self.assertTrue(E("data-saver.txt")["live"])

    def test_captions(self):
        self.assertEqual(ser("captions.txt", {"size": "150", "colour": "yellow"}),
                         b"# Omni captions v1\nsize\t150\ncolour\tyellow\nbackground\tsemi\nfont\tdefault\nedge\tnone\n"
                         b"position\tbottom\n")
        self.assertEqual(sc.parse(E("captions.txt"), "color\tcyan\n")["colour"], "cyan")

    def test_browser_more_and_bars(self):
        self.assertEqual(ser("browser-more.txt"),
                         b"suggest\t1\ndark\t0\ntablimit\t8\nkeeploaded\t6\nrefuse_mib\t160\nunload_mib\t112\n")
        self.assertEqual(sc.parse(E("browser-more.txt"), "tablimit\t99\ndark\t5\n")["tablimit"], "16")
        self.assertEqual(ser("ui-bars.txt", {"qa": "hidden"}), b"qa=hidden\nhints=shown\n")

    def test_startup_keeps_session(self):
        e = E("startup.txt")
        old = b"omni-startup\t1\nchoice\t3\nsession\tEvening\n"
        v = sc.parse(e, old)
        self.assertEqual((v["choice"], v["session"]), ("3", "Evening"))
        self.assertEqual(sc.serialize(e, dict(v, choice="1"), old), b"omni-startup\t1\nchoice\t1\nsession\tEvening\n")
        self.assertEqual(ser("startup.txt"), b"omni-startup\t1\nchoice\t0\nsession\t\n")

    def test_single_words(self):
        for name, value, data in (("ui-scale.txt", "xlarge", b"xlarge\n"), ("ui-accent.txt", "teal", b"teal\n"),
                                  ("history-keep.txt", "1w", b"1w\n"), ("kb-layout.txt", "azerty", b"azerty\n"),
                                  ("pointer-large.txt", "on", b"on\n"), ("youtube-mode.txt", "tv", b"tv\n"),
                                  ("ui-autohide.txt", "off", b"off\n"), ("controller-style.txt", "playstation",
                                                                          b"playstation\n"),
                                  ("display-mode.txt", "2160", b"2160\n"), ("dark-style.txt", "3", b"3\n"),
                                  ("ui-theme.txt", "contrast", b"contrast\n"), ("ui-lang.txt", "de", b"de\n")):
            self.assertEqual(ser(name, {"": value}), data, name)
            self.assertEqual(sc.parse(E(name), data)[""], value, name)

    def test_word_readers_follow_omni(self):
        self.assertEqual(sc.parse(E("ui-scale.txt"), "Extra-Large\n")[""], "xlarge")
        self.assertEqual(sc.parse(E("ui-accent.txt"), "  RED \r\n")[""], "red")
        self.assertEqual(sc.parse(E("ui-autohide.txt"), "offline\n")[""], "off")         # strncmp "off"
        self.assertEqual(sc.parse(E("display-mode.txt"), "1440 x\n")[""], "1080")         # fscanf needs one word
        self.assertEqual(sc.parse(E("youtube-mode.txt"), " TV\n")[""], "tv")
        self.assertEqual(sc.parse(E("ui-lang.txt"), "# c\npt_BR\n")[""], "pt")
        self.assertEqual(sc.parse(E("ui-lang.txt"), "it\n")[""], "it")                   # hand-set code kept
        self.assertEqual(sc.parse(E("kb-layout.txt"), "AZERTY\n")[""], "qwerty")         # ids are case-sensitive
        self.assertEqual(sc.parse(E("dark-style.txt"), "7\n")[""], "0")

    def test_hdr_revision(self):
        e = E(config.OMNI_HDR_PREF)
        self.assertEqual(sc.serialize(e, {"mode": "on"}, None), b"2\ton\n")
        self.assertEqual(sc.serialize(e, {"mode": "auto"}, b"7\toff\n"), b"8\tauto\n")
        self.assertEqual(sc.parse(e, b"7\ton\n")["mode"], "on")
        self.assertEqual(sc.parse(e, b"7\ton")["mode"], "off")                           # no newline: unreadable

    def test_browser_settings_patch_keeps_other_lines(self):
        e = E("browser-settings.txt")
        old = (b"search\t1\r\nzoom\t1.000\r\ntext\t1.000\r\npointer\t1\r\nsnap\t1\r\ndpad\t0\r\n"
               b"home\thttps://example.org/\r\nptrstyle\tomni\r\nsnapsize\t3\r\nptrcurve\t1\r\n")
        v = sc.parse(e, old)
        self.assertEqual((v["search"], v["snapsize"]), ("1", "3"))
        out = sc.serialize(e, dict(v, zoom="1.250", snapsize="0"), old)
        self.assertIn(b"zoom\t1.250\r\n", out)
        self.assertIn(b"snap\t0\r\n", out)
        self.assertIn(b"snapsize\t0\r\n", out)
        self.assertIn(b"home\thttps://example.org/\r\n", out)
        self.assertIn(b"ptrstyle\tomni\r\n", out)
        self.assertEqual(out.count(b"zoom\t"), 1)
        self.assertEqual(sc.parse(e, b"snap\t0\nsnapsize\t3\n")["snapsize"], "0")      # snap 0 always wins
        self.assertEqual(sc.parse(e, b"search\t42\n")["search"], "7")                   # atoi + clamp

    def test_tips_patch_keeps_seen(self):
        e = E("tips-seen.txt")
        old = b"omni-tips\t1\nenabled\t1\nseen\tzoom\n"
        self.assertEqual(sc.serialize(e, {"enabled": "0"}, old), b"omni-tips\t1\nenabled\t0\nseen\tzoom\n")
        self.assertEqual(sc.serialize(e, {"enabled": "0"}, None), b"omni-tips\t1\nenabled\t0\n")


class Validation(unittest.TestCase):
    def test_bad_values_refused(self):
        for name, vals in (("ui-scale.txt", {"": "huge"}), ("tab-sleep.txt", {"minutes": "20"}),
                           ("browser-settings.txt", {"zoom": "3.000"}), ("browser-more.txt", {"refuse_mib": "-1"}),
                           ("night-light.txt", {"start": "25:00"}), ("colour-filter.txt", {"last": "off"}),
                           ("startup.txt", {"session": "a\nb"}), ("data-saver.txt", {"on": "yes"})):
            with self.assertRaises(sc.SettingError, msg=name):
                ser(name, vals)

    def test_problems_name_the_setting(self):
        bad = sc.problems(E("tab-sleep.txt"), {"minutes": "5", "pinned": "0"})
        self.assertEqual([k for k, _ in bad], ["minutes"])


class NoTouch(unittest.TestCase):
    def test_protected_files_refused(self):
        for p in (O + "parental.txt", O + "passwords.txt", O + "passwords.key", O + "autofill.txt",
                  O + "session.txt", O + "history.txt", O + "notes.txt", config.OMNI_BOOKMARKS,
                  O + "reading-list/x.html", O + "ytguard-off.flag", O + "video-quality.txt", O + "site-zoom.txt",
                  O + "../omni/parental.txt", O + "unknown.txt"):
            with self.assertRaises(sc.SettingError, msg=p):
                sc.path_for(p)

    def test_no_editable_file_is_personal(self):
        personal = {f["path"] for f in backup.FILES if f["group"] != "settings"}
        self.assertFalse(set(sc.EDITABLE) & (personal | set(sc.NO_TOUCH)))
        self.assertIn(O + "parental.txt", sc.NO_TOUCH)

    def test_upload_refuses_before_writing(self):
        c = Console()
        with self.assertRaises(sc.SettingError):
            ed.upload(c, [(O + "ui-scale.txt", b"large\n"), (O + "parental.txt", b"x")])
        self.assertEqual(c.writes, [])


class Upload(unittest.TestCase):
    def test_plan_and_prev(self):
        c = Console({O + "ui-scale.txt": b"normal\n", O + "ui-scale.txt.prev": b"small\n"})
        raw = ed.load_console(c)
        loaded = ed.values_from(raw)
        edited = {p: dict(v) for p, v in loaded.items()}
        self.assertEqual(ed.plan(raw, loaded, edited), [])
        edited[O + "ui-scale.txt"][""] = "large"
        edited[O + "tab-sleep.txt"]["minutes"] = "60"
        changes = ed.plan(raw, loaded, edited)
        self.assertEqual([p for p, _ in changes], [O + "ui-scale.txt", O + "tab-sleep.txt"])
        done = dict(ed.upload(c, changes))
        self.assertEqual(c.files[O + "ui-scale.txt"], b"large\n")
        self.assertEqual(c.files[O + "ui-scale.txt.prev-2"], b"normal\n")
        self.assertEqual(done[O + "ui-scale.txt"], O + "ui-scale.txt.prev-2")
        self.assertIsNone(done[O + "tab-sleep.txt"])
        self.assertEqual(c.files[O + "tab-sleep.txt"], b"minutes\t60\npinned\t0\n")


if __name__ == "__main__":
    unittest.main()
