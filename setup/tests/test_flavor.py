"""Morph calls: shown during work, never twice in a row, and off with plain messages."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import flavor  # noqa: E402


class Flavor(unittest.TestCase):
    def tearDown(self):
        flavor.set_plain(False)

    def test_calls_vary_and_never_repeat_back_to_back(self):
        seen = [flavor.call() for _ in range(60)]
        self.assertTrue(all(seen))
        self.assertTrue(all(a != b for a, b in zip(seen, seen[1:])))
        self.assertGreater(len(set(seen)), 5)

    def test_plain_turns_them_off(self):
        flavor.set_plain(True)
        lines = []
        flavor.say(lines.append)
        self.assertEqual(lines, [])
        self.assertEqual(flavor.call(), "")

    def test_say_logs_one_line(self):
        lines = []
        flavor.say(lines.append)
        self.assertEqual(len(lines), 1)
        self.assertIn(lines[0][3:], flavor.CALLS)
        lines[0].encode("cp1252")   # prints on a Windows console


if __name__ == "__main__":
    unittest.main()
