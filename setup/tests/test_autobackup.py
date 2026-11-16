"""S06: automatic backup when the PS5 is found. Off by default; at most once per 24 h; the new zip is checked with
read_backup before older automatic backups beyond "keep last N" are pruned; manual backups are never touched; a failed
backup leaves every older one. The console is a dict; zips and settings go to a temp folder."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import autobackup, backup  # noqa: E402
from tests.test_backup import Console  # noqa: E402

O = "/data/omni/"
DAY = 24 * 60 * 60
T0 = datetime.datetime(2026, 1, 2, 3, 4, 5).timestamp()


def console():
    return Console({O + "browser-settings.txt": b"theme=dark\n", O + "bookmarks.txt": b"https://example.com/\tEx\n",
                    O + "notes.txt": b"a note\n", O + "passwords.txt": b"secret", O + "parental.txt": b"pin"})


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class AutoBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = os.path.join(self.tmp, "pc", "auto-backup.json")
        self.dir = os.path.join(self.tmp, "Backups", "Automatic")
        self.clock = Clock(T0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def enable(self, **kw):
        s = autobackup.load(self.cfg)
        s.update({"enabled": True}, **kw)
        autobackup.save(s, self.cfg)

    def run_(self, c=None, **kw):
        return autobackup.maybe_run(c or console(), settings_file=self.cfg, dest_dir=self.dir, clock=self.clock, **kw)

    # -- settings ------------------------------------------------------------------------------------------------
    def test_defaults_off_settings_and_bookmarks_keep_5(self):
        s = autobackup.load(self.cfg)
        self.assertFalse(s["enabled"])
        self.assertEqual(s["groups"], ["settings", "bookmarks"])
        self.assertEqual(s["keep"], 5)
        self.assertIsNone(self.run_())
        self.assertFalse(os.path.exists(self.dir))
        self.assertEqual(autobackup.status_line(s), "Automatic backup is off.")

    def test_settings_persist_and_are_cleaned(self):
        autobackup.save({"enabled": True, "groups": ["notes", "my-filters", "bogus"], "keep": 12}, self.cfg)
        s = autobackup.load(self.cfg)
        self.assertTrue(s["enabled"])
        self.assertEqual(s["groups"], ["settings", "notes", "my-filters"])   # settings always, unknown dropped
        self.assertEqual(s["keep"], 12)
        autobackup.save({"enabled": "yes", "keep": 99}, self.cfg)
        s = autobackup.load(self.cfg)
        self.assertFalse(s["enabled"])
        self.assertEqual(s["keep"], 20)
        autobackup.save({"keep": 0}, self.cfg)
        self.assertEqual(autobackup.load(self.cfg)["keep"], 1)
        with open(self.cfg, "w") as f:
            f.write("{not json")
        self.assertEqual(autobackup.load(self.cfg), autobackup.defaults())

    # -- running -------------------------------------------------------------------------------------------------
    def test_backup_holds_only_chosen_groups_never_private_files(self):
        self.enable()
        r = self.run_()
        self.assertTrue(r["ok"])
        self.assertTrue(autobackup.NAME_RE.match(os.path.basename(r["path"])))
        paths = {f["path"] for f in backup.read_backup(r["path"])["files"]}
        self.assertEqual(paths, {O + "browser-settings.txt", O + "bookmarks.txt"})   # notes is opt-in
        self.enable(groups=["settings", "notes"])
        self.clock.t += DAY
        paths = {f["path"] for f in backup.read_backup(self.run_()["path"])["files"]}
        self.assertEqual(paths, {O + "browser-settings.txt", O + "notes.txt"})

    def test_24h_throttle(self):
        self.enable()
        self.assertTrue(self.run_()["ok"])
        self.clock.t += DAY - 60
        self.assertIsNone(self.run_())
        self.assertEqual(len(autobackup.automatic_backups(self.dir)), 1)
        self.assertEqual(autobackup.status_line(autobackup.load(self.cfg), now=T0 + 120), "Backed up 2 min ago.")
        self.clock.t += 60
        self.assertTrue(self.run_()["ok"])
        self.assertEqual(len(autobackup.automatic_backups(self.dir)), 2)

    def test_prune_after_verify_keeps_last_n_and_manual_backups(self):
        self.enable(keep=2)
        os.makedirs(self.dir)
        manual = [os.path.join(self.dir, "omni-backup-2025-01-01.zip"), os.path.join(self.dir, "my copy.zip"),
                  os.path.join(os.path.dirname(self.dir), "omni-backup-2025-01-02.zip")]
        for p in manual:
            with open(p, "wb") as f:
                f.write(b"manual")
        order = []

        def verify(path):
            order.append(("verify", len(autobackup.automatic_backups(self.dir))))
            return backup.read_backup(path)
        made = []
        for _ in range(4):
            made.append(self.run_(verify=verify)["path"])
            self.clock.t += DAY
        self.assertEqual(autobackup.automatic_backups(self.dir), made[-2:])
        self.assertEqual(order[-1], ("verify", 3))       # the third one was still there while the new zip was checked
        for p in manual:
            self.assertTrue(os.path.exists(p), p)

    def test_unverified_backup_prunes_nothing(self):
        self.enable(keep=1)
        first = self.run_()["path"]
        self.clock.t += DAY

        def bad(path):
            raise backup.BackupError("damaged")
        r = self.run_(verify=bad)
        self.assertFalse(r["ok"])
        self.assertEqual(autobackup.automatic_backups(self.dir), [first])   # new zip removed, old one kept
        s = autobackup.load(self.cfg)
        self.assertEqual(s["last"], T0)                                     # not counted: retried next time
        self.assertIn("failed", autobackup.status_line(s, now=self.clock.t))
        self.assertTrue(self.run_()["ok"])
        self.assertIsNone(autobackup.load(self.cfg)["last_error"])

    def test_failed_backup_leaves_old_backups(self):
        self.enable(keep=1)
        first = self.run_()["path"]
        self.clock.t += DAY

        def boom(c, groups, dest):
            with open(dest, "wb") as f:
                f.write(b"half")
            raise OSError("the PS5 stopped answering")
        r = self.run_(run=boom)
        self.assertEqual(r, {"ok": False, "error": "the PS5 stopped answering"})
        self.assertEqual(autobackup.automatic_backups(self.dir), [first])

    def test_console_error_never_raises(self):
        self.enable()

        class Dead:
            def listing(self, d):
                raise OSError("gone")
        self.assertFalse(self.run_(Dead())["ok"])
        self.assertEqual(autobackup.automatic_backups(self.dir), [])

    def test_ago(self):
        self.assertEqual(autobackup.ago(5), "just now")
        self.assertEqual(autobackup.ago(125), "2 min ago")
        self.assertEqual(autobackup.ago(3 * 3600), "3 h ago")
        self.assertEqual(autobackup.ago(DAY), "1 day ago")
        self.assertEqual(autobackup.ago(3 * DAY), "3 days ago")


if __name__ == "__main__":
    unittest.main()
