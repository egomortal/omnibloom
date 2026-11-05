"""Audit ST-01 regression tests (GPL-3.0-or-later): an install that stops half way (FTP drop) must be
resumable with the same backups, or rolled back, and must never delete or lose the user's own files.
Fake console only.   python -m unittest tests.test_install_journal -v   (from the Setup folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_end_to_end import EBOOT, HUB_ELF, catalog_of, connect, make_packages, new_console, sha
from omnibloom_setup import config, installer

ORIGINAL = b"OLD-S0B-EBOOT"     # the user's own eboot, put there before Omnibloom


class Dropped(ConnectionError):
    pass


def drop_on_rename(console, when):
    """Make the FTP link 'drop' on the first rename for which when(src, dst) is true."""
    real = console.rename

    def rename(src, dst):
        if when(src, dst):
            raise Dropped("FTP connection lost")
        return real(src, dst)
    console.rename = rename


class InterruptedInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-journal-")
        self.fc = new_console(os.path.join(self.tmp, "console"))
        self.zips, self.files = make_packages(self.tmp)
        self.cat = catalog_of(self.zips)
        self.log = []

    def tearDown(self):
        self.fc.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def interrupt_after_parking_eboot(self):
        """First install: the user's eboot is parked, then the link drops before the new one moves in."""
        with connect(self.fc) as c:
            drop_on_rename(c, lambda src, dst: dst == EBOOT and src.endswith(".omnibloom-new"))
            with self.assertRaises(Dropped):
                installer.install(c, self.cat, ["omni"], log=self.log.append)
        self.assertFalse(self.fc.exists(EBOOT))                    # the active file is missing right now
        self.assertFalse(self.fc.exists(config.RECEIPTS_DIR + "omni.json"))

    def parked_original(self):
        folder = os.path.dirname(EBOOT)
        names = [n for n in self.fc.listdir(folder) if n.startswith("eboot.bin.before-omnibloom-")]
        self.assertEqual(len(names), 1, names)
        path = folder + "/" + names[0]
        self.assertEqual(self.fc.read(path), ORIGINAL)
        return path

    def test_resume_keeps_the_users_backup(self):
        self.interrupt_after_parking_eboot()
        parked = self.parked_original()
        with connect(self.fc) as c:
            installer.install(c, self.cat, ["omni"], log=self.log.append)
        receipt = json.loads(self.fc.read(config.RECEIPTS_DIR + "details/omni.json"))
        entry = next(f for f in receipt["files"] if f["dest"] == EBOOT)
        self.assertEqual(entry["backup"], parked, "the restore point of the user's file was lost")
        self.assertEqual(sha(self.fc.read(EBOOT)), sha(self.files[EBOOT]))
        with connect(self.fc) as c:
            self.assertEqual(installer.pending_installs(c), {})
            installer.uninstall_app(c, "omni", log=self.log.append)
        self.assertEqual(self.fc.read(EBOOT), ORIGINAL)              # uninstall puts the user's file back
        self.assertEqual(self.fc.state["deletes"], [])

    def test_interrupted_first_install_rolls_back(self):
        self.interrupt_after_parking_eboot()
        with connect(self.fc) as c:
            self.assertIn("omni", installer.pending_installs(c))
            installer.uninstall_app(c, "omni", log=self.log.append)
            self.assertEqual(installer.pending_installs(c), {})
        self.assertEqual(self.fc.read(EBOOT), ORIGINAL)
        self.assertEqual(self.fc.read("/data/omni/browser-profile/cookies.db"), b"user cookies")
        self.assertEqual(self.fc.state["deletes"], [])

    def test_nothing_starts_before_the_receipt_is_saved(self):
        with connect(self.fc) as c:
            drop_on_rename(c, lambda src, dst: dst == config.RECEIPTS_DIR + "hub.json")
            with self.assertRaises(Dropped):
                installer.install(c, self.cat, ["master-control"], log=self.log.append)
        self.assertNotIn(sha(self.files[HUB_ELF]), self.fc.state["payloads"])
        with connect(self.fc) as c:                                  # the next run finishes and then starts it
            installer.install(c, self.cat, ["master-control"], log=self.log.append)
        self.assertIn(sha(self.files[HUB_ELF]), self.fc.state["payloads"])
        self.assertEqual(self.fc.state["deletes"], [])

    def test_torn_journal_write_keeps_the_previous_state(self):
        self.interrupt_after_parking_eboot()
        with connect(self.fc) as c:
            journal = installer.read_journal(c, "omni")
            newest = installer._journal_slots("omni")[journal["seq"] % 2]
            c.store(newest, b'{"schema": "omnibloom-install')       # a write cut off half way
            older = installer.read_journal(c, "omni")
        self.assertEqual(older["seq"], journal["seq"] - 1)
        self.assertEqual(older["state"], "open")


if __name__ == "__main__":
    unittest.main()
