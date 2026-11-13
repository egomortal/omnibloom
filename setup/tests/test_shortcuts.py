"""Setup's controller-shortcut list and the README's tables must say the same thing."""
import io
import os
import re
import unittest
from contextlib import redirect_stdout

from omnibloom_setup import cli, shortcuts

README = os.path.join(os.path.dirname(__file__), "..", "..", "README.md")


def _readme_rows():
    with open(README, encoding="utf-8") as f:
        text = f.read()
    section = text.split("## Controller shortcuts", 1)[1].split("\n## ", 1)[0]
    return [re.sub(r"\*\*", "", ln).strip() for ln in section.splitlines() if ln.startswith("| ")]


class ShortcutsTest(unittest.TestCase):
    def test_every_setup_row_is_in_the_readme(self):
        rows = _readme_rows()
        for _title, section in shortcuts.SECTIONS + (shortcuts.COMING,):
            for ps, xb, what in section:
                want = "| %s | %s" % (shortcuts.label(ps, xb), what)
                self.assertTrue(any(r.startswith(want) for r in rows), "README is missing: " + want)

    def test_every_readme_row_is_in_setup(self):
        known = {shortcuts.label(ps, xb) for _t, sec in shortcuts.SECTIONS + (shortcuts.COMING,) for ps, xb, _w in sec}
        for r in _readme_rows():
            button = r.split("|")[1].strip()
            if button in ("Button", "---"):
                continue
            self.assertIn(button, known, "Setup's list is missing the README row: " + r)

    def test_text_is_plain_ascii(self):   # the Windows console (cp1252) must print it
        shortcuts.text().encode("ascii")

    def test_cli_prints_them(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["shortcuts"]), 0)
        self.assertIn("LB + RB", buf.getvalue())
        self.assertIn("Media downloads", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
