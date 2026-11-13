"""autoload.txt entries are absolute paths (Payload Manager v0.6.3 did not start bare names after a reboot,
console 2026-11-13). Bare entries written by older Setups are replaced, never duplicated."""
import os
import posixpath
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import config, installer  # noqa: E402

HUB = "/data/pldmgr/payloads/BloomCore/hub.elf"
MC = "/data/pldmgr/payloads/master-control/master-control.elf"


class Console:
    """Just enough of the console for set_autoload: files in a dict."""
    def __init__(self, autoload):
        self.files = {config.AUTOLOAD_PATH: autoload.encode("utf-8")}

    def read_text(self, path, default=None):
        return self.files[path].decode("utf-8") if path in self.files else default

    def read(self, path):
        return self.files[path]

    def store(self, path, data):
        self.files[path] = data

    def listing(self, parent):
        return [posixpath.basename(p) for p in self.files if posixpath.dirname(p) == parent.rstrip("/")]

    def lines(self):
        return self.read_text(config.AUTOLOAD_PATH).split()


def nolog(*_):
    pass


class AbsoluteEntries(unittest.TestCase):
    def test_new_entry_is_absolute(self):
        c = Console("ftpsrv.elf\n")
        self.assertTrue(installer.set_autoload(c, HUB, True, nolog)["changed"])
        self.assertEqual(c.lines(), ["ftpsrv.elf", HUB])

    def test_bare_entry_from_older_setup_is_replaced(self):
        c = Console("ftpsrv.elf\nhub.elf\nmaster-control.elf\n")
        installer.set_autoload(c, HUB, True, nolog)
        installer.set_autoload(c, MC, True, nolog)
        self.assertEqual(c.lines(), ["ftpsrv.elf", HUB, MC])

    def test_already_absolute_is_unchanged(self):
        c = Console("ftpsrv.elf\n%s\n" % HUB)
        self.assertFalse(installer.set_autoload(c, HUB, True, nolog)["changed"])

    def test_remove_clears_bare_and_absolute(self):
        c = Console("ftpsrv.elf\nhub.elf\n%s\n" % HUB)
        installer.set_autoload(c, HUB, False, nolog)
        self.assertEqual(c.lines(), ["ftpsrv.elf"])

    def test_replaced_controller_payload_kept_aside(self):
        c = Console("ftpsrv.elf\nEeveeLution-PS5.elf\n")
        change = installer.set_autoload(c, MC, True, nolog, replace=config.REPLACED_CONTROLLER_PAYLOADS)
        self.assertEqual(c.lines(), ["ftpsrv.elf", MC])
        self.assertEqual(change["removed"], ["EeveeLution-PS5.elf"])


if __name__ == "__main__":
    unittest.main()
