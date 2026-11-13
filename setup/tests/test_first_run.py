"""Older Omni titles need /data/omni/omni-engine.elf and /data/omni/browser-mode.flag before they start the browser.
Setup creates them when missing and never replaces an existing file."""
import os
import posixpath
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import config, installer  # noqa: E402


class Console:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.dirs = set()

    def exists(self, path):
        return path in self.files

    def makedirs(self, path):
        self.dirs.add(path)

    def store(self, path, data):
        self.files[path] = data

    def read(self, path):
        return self.files[path]


class FirstRun(unittest.TestCase):
    def test_fresh_console_gets_both_files(self):
        c = Console()
        made = installer.ensure_omni_first_run(c, lambda *_: None)
        self.assertEqual(made, [p for p, _ in config.OMNI_FIRST_RUN_FILES])
        for flag in ("mse-preview", "hw-decode", "ublock-native", "media-preview"):   # 720p cap / uBlock off without these
            self.assertIn("/data/omni/%s.flag" % flag, made)
        self.assertEqual(c.files["/data/omni/browser-mode.flag"], b"1\n")
        self.assertIn(b"placeholder", c.files["/data/omni/omni-engine.elf"])

    def test_existing_files_are_never_replaced(self):
        old = {p: b"x" for p, _ in config.OMNI_FIRST_RUN_FILES}
        old["/data/omni/omni-engine.elf"] = b"\x7fELF real engine"
        c = Console(old)
        self.assertEqual(installer.ensure_omni_first_run(c, lambda *_: None), [])
        self.assertEqual(c.files, old)

    def test_only_omni_folder(self):
        for path, _ in config.OMNI_FIRST_RUN_FILES:
            self.assertEqual(posixpath.dirname(path), "/data/omni")


if __name__ == "__main__":
    unittest.main()
