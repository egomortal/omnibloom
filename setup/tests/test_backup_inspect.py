"""Backup inspector: list a backup's items with previews, and restore single items through backup.restore.
No network: the console is test_backup's in-memory fake; zips go to a temp folder."""
import hashlib
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import backup, backup_inspect  # noqa: E402
from tests.test_backup import O, Console, Tmp, evil_zip, new_console  # noqa: E402


def items_by_path(r):
    return {i["path"]: i for i in r["items"]}


class Listing(Tmp):
    def made(self):
        src = new_console()
        src.files[O + "bookmarks.txt"] = (b"https://a.example/\tFirst title\tNews\n"
                                          b"https://b.example/\tSecond\n" + b"https://c.example/\tThird\n"
                                          b"https://d.example/\tFourth\n")
        src.files[O + "history.txt"] = b"1\thttps://h.example/\tVisited page\n"
        src.files[O + "kb-words.txt"] = b"typedword\n"
        backup.backup(src, list(backup.GROUP_IDS), self.zp())
        return src

    def test_lists_every_item_with_group_size_date(self):
        src = self.made()
        r = backup_inspect.inspect(self.zp())
        items = items_by_path(r)
        with zipfile.ZipFile(self.zp()) as z:
            entries = set(z.namelist()) - {backup.MANIFEST_NAME}
        self.assertEqual({p.lstrip("/") for p in items}, entries)
        bm = items[O + "bookmarks.txt"]
        self.assertEqual((bm["group"], bm["group_name"], bm["size"]),
                         ("bookmarks", "Bookmarks", len(src.files[O + "bookmarks.txt"])))
        self.assertRegex(bm["date"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
        self.assertTrue(r["created"])
        # GROUPS order: settings first.
        self.assertEqual(r["items"][0]["group"], "settings")
        for p in items:
            self.assertNotIn("parental", p)
            self.assertNotIn("password", p)

    def test_previews(self):
        self.made()
        items = items_by_path(backup_inspect.inspect(self.zp()))
        bm = items[O + "bookmarks.txt"]
        self.assertEqual(bm["lines"], 4)
        self.assertEqual(bm["first"], ["First title", "Second", "Third"])      # titles only, 3 lines
        self.assertIn("4 lines: First title", backup_inspect.preview_text(bm))
        self.assertNotIn("https", backup_inspect.preview_text(bm))
        self.assertEqual(items[O + "ui-theme.txt"]["first"], ["xbox"])
        for p in (O + "history.txt", O + "kb-words.txt", O + "bookmarklets.txt", O + "sessions.txt",
                  O + "highlights.json", "/data/omni-downloader/state/jobs.json"):
            self.assertIsNone(items[p]["first"], p)          # count only
            self.assertIsInstance(items[p]["lines"], int, p)
        png = items[O + "pointers/hand@4,4.png"]
        self.assertIsNone(png["lines"])                      # not utf-8 -> binary
        self.assertEqual(backup_inspect.preview_text(png), "binary")

    def test_long_lines_are_cut(self):
        c = Console({O + "notes.txt": ("x" * 200 + "\n").encode()})
        backup.backup(c, ["notes"], self.zp())
        first = items_by_path(backup_inspect.inspect(self.zp()))[O + "notes.txt"]["first"]
        self.assertEqual(len(first[0]), backup_inspect.PREVIEW_WIDTH + 1)

    def test_size_text(self):
        self.assertEqual(backup_inspect.size_text(5), "5 B")
        self.assertEqual(backup_inspect.size_text(2048), "2.0 KB")


class SelectiveRestore(Tmp):
    def test_restores_only_chosen_and_keeps_prev(self):
        src = new_console()
        backup.backup(src, list(backup.GROUP_IDS), self.zp())
        target = Console({O + "bookmarks.txt": b"old\n", O + "history.txt": b"mine\n", O + "parental.txt": b"pin\n"})
        logs = []
        r = backup_inspect.restore_items(target, self.zp(), [O + "bookmarks.txt", O + "notes.txt"], log=logs.append)
        self.assertEqual((r["written"], r["same"]), (2, 0))
        self.assertEqual(target.files[O + "bookmarks.txt"], src.files[O + "bookmarks.txt"])
        self.assertEqual(target.files[O + "notes.txt"], src.files[O + "notes.txt"])
        self.assertEqual(target.files[O + "bookmarks.txt.prev"], b"old\n")
        self.assertEqual(target.files[O + "history.txt"], b"mine\n")          # not chosen: untouched
        self.assertEqual(target.files[O + "parental.txt"], b"pin\n")
        self.assertNotIn(O + "notes.txt.prev", target.files)                 # nothing there before
        self.assertFalse([p for p in target.files if "before-setup" in p or p.endswith(".omnibloom-new")])
        self.assertNotIn("bookmarks.txt", " ".join(logs))                    # counts only
        # Again with different old bytes: .prev is taken, so .prev-2.
        target.files[O + "bookmarks.txt"] = b"newer\n"
        backup_inspect.restore_items(target, self.zp(), [O + "bookmarks.txt"])
        self.assertEqual(target.files[O + "bookmarks.txt.prev-2"], b"newer\n")
        # Same bytes: not written, no .prev.
        r = backup_inspect.restore_items(target, self.zp(), [O + "bookmarks.txt"])
        self.assertEqual((r["written"], r["same"]), (0, 1))
        self.assertNotIn(O + "bookmarks.txt.prev-3", target.files)

    def refused(self, zp, paths):
        c = Console({O + "bookmarks.txt": b"mine\n", O + "parental.txt": b"pin\n"})
        before = dict(c.files)
        with self.assertRaises(backup.BackupError):
            backup_inspect.restore_items(c, zp, paths)
        self.assertEqual(c.files, before)

    def test_never_items_and_traversal_refused(self):
        backup.backup(new_console(), list(backup.GROUP_IDS), self.zp())
        for bad in (O + "parental.txt", O + "passwords.txt", O + "session.txt", O + "browser-profile/Cookies",
                    O + "../hub/receipts/omni.json", O + "reading-list/../passwords.txt", "/etc/passwd",
                    "data/omni/bookmarks.txt", O + "reading-list\\..\\x.html"):
            self.refused(self.zp(), [O + "bookmarks.txt", bad])
        self.refused(self.zp(), [])

    def test_allowed_but_not_in_backup_refused(self):
        backup.backup(new_console(), [], self.zp())                           # settings only
        self.refused(self.zp(), [O + "bookmarks.txt"])

    def test_crafted_zip_with_never_item_refused_for_listing_and_restore(self):
        d = b"pin\n"
        m = [{"path": O + "parental.txt", "group": "settings", "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}]
        zp = evil_zip(self.zp(), {}, manifest=m, extra=[("data/omni/parental.txt", d, None)])
        with self.assertRaises(backup.BackupError):
            backup_inspect.inspect(zp)
        self.refused(zp, [O + "parental.txt"])

    def test_zip_slip_entry_refused(self):
        d = b"x"
        m = [{"path": O + "../../etc/x", "group": "settings", "size": 1, "sha256": hashlib.sha256(d).hexdigest()}]
        zp = evil_zip(self.zp(), {}, manifest=m, extra=[("../../etc/x", d, None)])
        with self.assertRaises(backup.BackupError):
            backup_inspect.inspect(zp)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "..", "..", "etc", "x")))

    def test_symlink_entry_refused(self):
        d = b"x\n"
        m = [{"path": O + "ui-theme.txt", "group": "settings", "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}]

        def link(info):
            info.external_attr = (0o120777 << 16)
        zp = evil_zip(self.zp(), {}, manifest=m, extra=[("data/omni/ui-theme.txt", d, link)])
        with self.assertRaises(backup.BackupError):
            backup_inspect.inspect(zp)


class Corrupt(Tmp):
    def test_not_a_zip(self):
        with open(self.zp(), "wb") as f:
            f.write(b"PK\x03\x04 truncated junk")
        with self.assertRaises(backup.BackupError):
            backup_inspect.inspect(self.zp())

    def test_damaged_entry_bytes(self):
        backup.backup(new_console(), ["notes"], self.zp())
        with open(self.zp(), "rb") as f:
            raw = bytearray(f.read())
        # Flip bytes inside the first stored entry's data (after its local header).
        i = raw.find(b"PK\x03\x04") + 30 + len("data/omni/browser-settings.txt")
        for k in range(i, i + 4):
            raw[k] ^= 0xFF
        with open(self.zp(), "wb") as f:
            f.write(bytes(raw))
        c = Console()
        with self.assertRaises(backup.BackupError):
            backup_inspect.inspect(self.zp())
        with self.assertRaises(backup.BackupError):
            backup_inspect.restore_items(c, self.zp(), [O + "notes.txt"])
        self.assertEqual(c.files, {})

    def test_oversized_entry(self):
        zp = evil_zip(self.zp(), {O + "ui-theme.txt": b"x" * (4 * 1024 + 1)})
        with self.assertRaises(backup.BackupError):
            backup_inspect.inspect(zp)


if __name__ == "__main__":
    unittest.main()
