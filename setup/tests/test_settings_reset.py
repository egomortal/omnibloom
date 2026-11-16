"""S08 settings reset: full backup first (and nothing changes if it fails), exactly backup.py's settings group is
renamed to <name>.reset-<time>, personal data and the never-backed-up files are never touched, undo puts it back."""
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from omnibloom_setup import backup, settings_reset as sr  # noqa: E402
from test_backup import O, Console, new_console, NEW_SETTINGS, NEW_PERSONAL, NEW_NEVER  # noqa: E402

S = "20261116T101010Z"


class Recording(Console):
    def __init__(self, files=None, events=None):
        super().__init__(files)
        self.events = events if events is not None else []

    def rename(self, src, dst):
        self.events.append(("rename", src, dst))
        super().rename(src, dst)


def full_console():
    c = Recording(new_console().files)
    for f in backup.FILES:                                   # every known file present
        c.files.setdefault(f["path"], b"x\n")
    return c


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omnibloom-reset-")
        self.dest = os.path.join(self.dir, "b.zip")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class FileSet(Tmp):
    def test_exact_settings_group(self):
        want = {f["path"] for f in backup.FILES if f["group"] == "settings"}
        self.assertEqual(set(sr.SETTINGS_FILES), want)
        for n in NEW_SETTINGS:
            self.assertIn(O + n, sr.SETTINGS_FILES)
        self.assertEqual(set(sr.plan(full_console())), want)

    def test_never_touch_list(self):
        never = [O + n for n in ("bookmarks.txt", "history.txt", "passwords.txt", "passwords.key", "notes.txt",
                                 "highlights.json", "reading-list/index.tsv", "parental.txt", "session.txt",
                                 "autofill.txt", "sessions.txt", "kb-words.txt")] + [O + "browser-profile/Cookies"]
        for p in never:
            self.assertNotIn(p, sr.SETTINGS_FILES, p)
        c = full_console()
        before = dict(c.files)
        r = sr.reset(c, self.dest, stamp=S)
        for p in list(never) + [O + n for n in tuple(NEW_PERSONAL) + NEW_NEVER]:
            if p in before:
                self.assertEqual(c.files.get(p), before[p], p)
        touched = {e[1] for e in c.events}
        self.assertEqual(touched, set(sr.SETTINGS_FILES))
        self.assertEqual(set(r["renamed"]), set(sr.SETTINGS_FILES))
        for p in r["renamed"]:
            self.assertNotIn(p, c.files)
            self.assertEqual(c.files[p + ".reset-" + S], before[p])
        self.assertEqual(len(c.files), len(before))              # renamed, nothing deleted

    def test_only_confirmed_settings_paths(self):
        c = full_console()
        with self.assertRaises(sr.ResetError):
            sr.reset(c, self.dest, paths=[O + "bookmarks.txt"])
        self.assertEqual(c.events, [])
        self.assertFalse(os.path.exists(self.dest))
        r = sr.reset(c, self.dest, paths=[O + "ui-theme.txt"], stamp=S)
        self.assertEqual(r["renamed"], [O + "ui-theme.txt"])


class BackupFirst(Tmp):
    def test_backup_before_any_rename_and_full(self):
        events = []
        c = Recording(new_console().files, events)

        def fake_backup(console, groups, dest, log=None):
            events.append(("backup", tuple(groups)))
            return backup.backup(console, groups, dest)
        sr.reset(c, self.dest, backup_fn=fake_backup, stamp=S)
        self.assertEqual(events[0], ("backup", backup.GROUP_IDS))
        self.assertTrue(all(e[0] == "rename" for e in events[1:]) and len(events) > 1)
        with zipfile.ZipFile(self.dest) as z:
            names = set(z.namelist())
        for n in NEW_SETTINGS + tuple(NEW_PERSONAL):              # the zip holds what was reset, and personal data
            self.assertIn("data/omni/" + n, names)
        self.assertNotIn("data/omni/parental.txt", names)

    def test_abort_on_backup_failure(self):
        for fail in ("backup", "check"):
            c = full_console()
            before = dict(c.files)

            def bad_backup(*a, **k):
                raise OSError("disk full")

            def bad_check(path):
                raise backup.BackupError("damaged")
            with self.assertRaises(sr.ResetError) as cm:
                sr.reset(c, self.dest, backup_fn=bad_backup if fail == "backup" else None,
                         check_fn=bad_check if fail == "check" else None)
            self.assertIn("Nothing on the PS5 was changed", str(cm.exception))
            self.assertEqual(c.events, [])
            self.assertEqual(c.files, before)

    def test_rename_failure_puts_back(self):
        c = full_console()
        before = dict(c.files)
        real = Console.rename
        calls = [0]

        def flaky(src, dst):
            calls[0] += 1
            if calls[0] == 4:
                raise OSError("550")
            real(c, src, dst)
        c.rename = flaky
        with self.assertRaises(sr.ResetError):
            sr.reset(c, self.dest, stamp=S)
        self.assertEqual(c.files, before)


class Undo(Tmp):
    def test_undo_last(self):
        c = full_console()
        before = dict(c.files)
        sr.reset(c, self.dest, stamp="20261116T090000Z")
        sr.undo_last(c)                                           # first reset undone
        sr.reset(c, self.dest, stamp=S)
        c.files[O + "ui-theme.txt"] = b"default\n"                # Omni wrote a default after restarting
        self.assertEqual(sr.last_reset(c)[0], ".reset-" + S)
        r = sr.undo_last(c, stamp="20261116T120000Z")
        self.assertEqual(set(r["restored"]), set(sr.SETTINGS_FILES))
        self.assertEqual(r["parked"], [O + "ui-theme.txt"])
        for p in sr.SETTINGS_FILES:
            self.assertEqual(c.files[p], before[p])
        self.assertEqual(c.files[O + "ui-theme.txt.after-reset-20261116T120000Z"], b"default\n")
        with self.assertRaises(sr.ResetError):
            sr.undo_last(c)

    def test_same_second_and_foreign_names(self):
        c = full_console()
        r1 = sr.reset(c, self.dest, paths=[O + "ui-theme.txt"], stamp=S)
        c.files[O + "ui-theme.txt"] = b"y\n"
        r2 = sr.reset(c, self.dest, paths=[O + "ui-theme.txt"], stamp=S)
        self.assertEqual((r1["suffix"], r2["suffix"]), (".reset-" + S, ".reset-" + S + "-2"))
        c.files[O + "bookmarks.txt.reset-20991231T000000Z"] = b"not ours"   # never a settings file: ignored
        self.assertEqual(sr.last_reset(c), (".reset-" + S + "-2", [O + "ui-theme.txt"]))
        sr.undo_last(c)
        self.assertEqual(c.files[O + "ui-theme.txt"], b"y\n")


try:
    import pyftpdlib  # noqa: F401  (CI installs it; the fake PS5's FTP server needs it)
    HAVE_FTPD = True
except ImportError:
    HAVE_FTPD = False


@unittest.skipUnless(HAVE_FTPD, "pyftpdlib not installed")
class OverFtp(Tmp):
    def test_reset_and_undo_over_ftp(self):
        try:
            from tests.fake_console import FakeConsole
        except ImportError:
            from fake_console import FakeConsole
        from omnibloom_setup import ps5
        fc = FakeConsole(os.path.join(self.dir, "c"), websrv=False).start()
        try:
            for n in ("ui-theme.txt", "apps.json", "bookmarks.txt", "parental.txt", "notes.txt"):
                fc.write(O + n, b"v " + n.encode())
            with ps5.Console("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, timeout=10) as c:
                self.assertEqual(sr.plan(c), [O + "ui-theme.txt", O + "apps.json"])
                sr.reset(c, self.dest, stamp=S)
                self.assertFalse(fc.exists(O + "ui-theme.txt"))
                self.assertEqual(fc.read(O + "apps.json.reset-" + S), b"v apps.json")
                for n in ("bookmarks.txt", "parental.txt", "notes.txt"):
                    self.assertEqual(fc.read(O + n), b"v " + n.encode())
                sr.undo_last(c)
            self.assertEqual(fc.read(O + "ui-theme.txt"), b"v ui-theme.txt")
            self.assertFalse(fc.exists(O + "ui-theme.txt.reset-" + S))
        finally:
            fc.stop()


if __name__ == "__main__":
    unittest.main()
