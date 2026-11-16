"""Back up Omni's data to a zip on the PC and restore it. The console is a dict; zips go to a temp folder.
Only known files are saved (settings always, personal data when ticked; never passwords, cookies, session, flags);
a restore checks the whole zip first (paths, sizes, sha256) and parks the files it replaces."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import backup, config  # noqa: E402

O = "/data/omni/"


class Console:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.reads = []

    def _dirs(self):
        out = set()
        for p in self.files:
            parts = p.split("/")
            for i in range(2, len(parts)):
                out.add("/".join(parts[:i]))
        return out

    def exists(self, path):
        return path in self.files or path.rstrip("/") in self._dirs()

    def listing(self, parent):
        parent = parent.rstrip("/")
        out = {}
        for p, data in self.files.items():
            head, name = p.rsplit("/", 1)
            if head == parent:
                out[name] = {"dir": False, "size": len(data)}
        for d in self._dirs():
            head, name = d.rsplit("/", 1)
            if head == parent:
                out[name] = {"dir": True, "size": 0}
        return out

    def makedirs(self, path):
        pass

    def read(self, path, limit=None):
        self.reads.append(path)
        data = self.files[path]
        return data[:limit] if limit else data

    def read_text(self, path, default=None):
        return self.files[path].decode() if path in self.files else default

    def put_verified(self, path, data, readback=True):
        self.files[path + ".omnibloom-new"] = data
        return path + ".omnibloom-new"

    def rename(self, src, dst):
        assert dst not in self.files
        self.files[dst] = self.files.pop(src)


def omni_console():
    return Console({
        O + "browser-settings.txt": b"snap=1\n",
        O + "shortcuts.txt": b"https://a.example/\tA\n",
        O + "ui-theme.txt": b"xbox\n",
        O + "site-zoom.txt": b"a.example\t125\n",
        O + "addons/state.json": b'{"x":1}',
        O + "bookmarks.txt": b"https://b.example/\tB\n",
        O + "history.txt": b"1\thttps://h.example/\tH\n",
        O + "reading-list/index.tsv": b"omni-reading-list\t1\n",
        O + "reading-list/news.example-20261116-101010.html": b"<html>page</html>",
        O + "reading-list/notes.txt": b"not a page",
        O + "addons/storage/dark-reader.txt": b"omni-addon-storage 1\n",
        O + "pointers/hand@4,4.png": b"\x89PNG..",
        "/data/omni-downloader/state/jobs.json": b"[]",
        "/data/omni-downloader/state/saved-links.json": b"[]",
        "/data/omni-downloader/state/tz-offset.json": b"{}",
        # never backed up
        O + "passwords.txt": b"secret", O + "passwords.key": b"k", O + "autofill.txt": b"me", O + "session.txt": b"tabs",
        O + "browser-profile/Cookies": b"c", O + "browser-mode.flag": b"1\n", O + "crash-diagnostics.flag": b"1\n",
        O + "native/crash.log": b"log", O + "media-downloads.log": b"log", O + "ublock-compiled.txt": b"rules",
        O + "display-hz.txt": b"60", O + "browser-preview.png": b"png",
        "/data/hub/receipts/omni.json": json.dumps({"schema": "hub-receipt/v1", "id": "omni", "version": "0.6.0"}).encode(),
    })


class Inventory(unittest.TestCase):
    def test_never_list_is_never_allowed(self):
        for p in backup.NEVER:
            self.assertIsNone(backup.rule_for(p.replace("*", "x")), p)
        for p in (O + "passwords.txt", O + "browser-profile/Cookies", O + "session.txt", O + "ublock-native.flag"):
            self.assertIsNone(backup.rule_for(p))

    def test_every_group_known(self):
        for r in backup.FILES + backup.FOLDERS:
            self.assertIn(r["group"], backup.GROUP_IDS)
        self.assertIs(backup.rule_for(config.OMNI_BOOKMARKS)["group"], "bookmarks")

    def test_paths_must_be_plain(self):
        for bad in (O + "../hub/x.json", O + "./bookmarks.txt", O + "reading-list/../passwords.txt",
                    "/data/omni//bookmarks.txt", O + "reading-list/..html", O + "reading-list/a..html",
                    O + "reading-list/sub/a.html", O + "reading-list/.hidden.html", "data/omni/bookmarks.txt",
                    O + "reading-list\\a.html", O + "bookmarks.txt\0", None, 5, O + "addons/storage/x.js"):
            self.assertIsNone(backup.rule_for(bad), bad)
        self.assertIsNotNone(backup.rule_for(O + "reading-list/a.example-20261116-101010.html"))

    def test_default_path(self):
        d = tempfile.mkdtemp()
        try:
            import datetime
            day = datetime.date(2026, 11, 16)
            p = backup.default_path(d, day)
            self.assertEqual(os.path.basename(p), "omni-backup-2026-11-16.zip")
            open(p, "w").close()
            self.assertEqual(os.path.basename(backup.default_path(d, day)), "omni-backup-2026-11-16-2.zip")
            self.assertTrue(backup.default_folder("H").endswith(os.path.join("Documents", "Omnibloom Backups")))
        finally:
            shutil.rmtree(d)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omnibloom-backup-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def zp(self, name="b.zip"):
        return os.path.join(self.dir, name)


class Backup(Tmp):
    def test_settings_only_by_default(self):
        c = omni_console()
        logs = []
        r = backup.backup(c, [], self.zp(), log=logs.append)
        with zipfile.ZipFile(self.zp()) as z:
            names = set(z.namelist())
            m = json.loads(z.read(backup.MANIFEST_NAME))
        self.assertEqual(names - {backup.MANIFEST_NAME}, {
            "data/omni/browser-settings.txt", "data/omni/shortcuts.txt", "data/omni/ui-theme.txt",
            "data/omni/site-zoom.txt", "data/omni/addons/state.json"})
        self.assertEqual((m["format"], m["version"], m["omni_version"], m["setup_version"]),
                         (backup.FORMAT, 1, "0.6.0", config.SETUP_VERSION))
        f = {x["path"]: x for x in m["files"]}[O + "ui-theme.txt"]
        self.assertEqual((f["size"], f["sha256"], f["group"]), (5, hashlib.sha256(b"xbox\n").hexdigest(), "settings"))
        self.assertEqual(r["files"], 5)
        self.assertFalse(os.path.exists(self.zp() + ".part"))
        # Logs carry counts only.
        self.assertNotIn("txt", " ".join(logs))

    def test_everything_ticked_still_skips_secrets(self):
        c = omni_console()
        backup.backup(c, list(backup.GROUP_IDS), self.zp())
        with zipfile.ZipFile(self.zp()) as z:
            names = set(z.namelist())
        for want in ("data/omni/bookmarks.txt", "data/omni/history.txt", "data/omni/reading-list/index.tsv",
                     "data/omni/reading-list/news.example-20261116-101010.html", "data/omni/addons/storage/dark-reader.txt",
                     "data/omni/pointers/hand@4,4.png", "data/omni-downloader/state/jobs.json",
                     "data/omni-downloader/state/saved-links.json"):
            self.assertIn(want, names)
        for p in names:
            for bad in ("password", "autofill", "session", "browser-profile", ".flag", ".log", "ublock", "tz-offset",
                        "notes.txt", "receipts", "display-hz", "preview"):
                self.assertNotIn(bad, p)
        self.assertFalse([p for p in c.reads if "password" in p or "Cookies" in p or "session" in p])

    def test_too_big_files_left_out(self):
        c = omni_console()
        c.files[O + "ui-theme.txt"] = b"x" * (4 * 1024 + 1)
        r = backup.backup(c, [], self.zp())
        self.assertEqual((r["files"], r["left_out"]), (4, 1))
        self.assertNotIn(O + "ui-theme.txt", c.reads)


class Restore(Tmp):
    def made(self, groups=backup.GROUP_IDS):
        backup.backup(omni_console(), list(groups), self.zp())
        return self.zp()

    def test_round_trip_parks_what_it_replaces(self):
        zp = self.made()
        src = omni_console()
        target = Console({O + "bookmarks.txt": b"old\n", O + "ui-theme.txt": b"xbox\n", O + "passwords.txt": b"keep"})
        r = backup.restore(target, zp)
        self.assertEqual(r["same"], 1)                     # ui-theme already identical: not written, not parked
        for name in ("bookmarks.txt", "history.txt", "reading-list/news.example-20261116-101010.html", "shortcuts.txt"):
            self.assertEqual(target.files[O + name], src.files[O + name])
        self.assertEqual(target.files["/data/omni-downloader/state/jobs.json"], b"[]")
        parked = [p for p in target.files if ".before-setup-" in p]
        self.assertEqual(len(parked), 1)
        self.assertTrue(parked[0].startswith(O + "bookmarks.txt.before-setup-"))
        self.assertEqual(target.files[parked[0]], b"old\n")
        self.assertEqual(target.files[O + "passwords.txt"], b"keep")
        self.assertFalse([p for p in target.files if p.endswith(".omnibloom-new")])

    def test_only_ticked_groups(self):
        zp = self.made()
        target = Console()
        r = backup.restore(target, zp, ["bookmarks"])
        self.assertEqual(sorted(target.files), [O + "bookmarks.txt"])
        self.assertEqual(r["groups"], {"bookmarks": 1})

    def test_reading_list_index_written_last(self):
        zp = self.made(["reading-list"])
        order = []
        target = Console()
        put = target.put_verified
        target.put_verified = lambda p, d, readback=True: (order.append(p), put(p, d))[1]
        backup.restore(target, zp, ["reading-list"])
        self.assertEqual(order[-1], O + "reading-list/index.tsv")

    def test_summary(self):
        m = backup.read_backup(self.made())
        self.assertEqual(m["summary"]["reading-list"], {"files": 2, "bytes": 20 + 17})
        self.assertEqual(list(m["summary"])[0], "settings")


def evil_zip(path, files, manifest=None, extra=(), version=1):
    """files: {console path: bytes} written as entries and listed in the manifest. extra: (entry name, bytes, info
    tweak) written but maybe not listed. manifest: replaces the generated file list."""
    entries = [{"path": p, "group": (backup.rule_for(p) or {"group": "settings"})["group"], "size": len(d),
                "sha256": hashlib.sha256(d).hexdigest()} for p, d in files.items()]
    doc = {"format": backup.FORMAT, "version": version, "created": "x", "files": entries if manifest is None else manifest}
    with zipfile.ZipFile(path, "w") as z:
        for p, d in files.items():
            z.writestr(p.lstrip("/"), d)
        for name, data, tweak in extra:
            info = zipfile.ZipInfo(name)
            if tweak:
                tweak(info)
            z.writestr(info, data)
        z.writestr(backup.MANIFEST_NAME, json.dumps(doc))
    return path


class Malicious(Tmp):
    def refused(self, zp):
        c = Console({O + "bookmarks.txt": b"mine\n"})
        before = dict(c.files)
        with self.assertRaises(backup.BackupError):
            backup.restore(c, zp)
        self.assertEqual(c.files, before)

    def entry(self, path, data):
        return {"path": path, "group": "settings", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def test_traversal_in_manifest_and_entry(self):
        d = b"x"
        for bad in (O + "../hub/receipts/omni.json", O + "reading-list/../../hub/x.html", "/data/omni/../../etc/passwd"):
            zp = evil_zip(self.zp(), {}, manifest=[self.entry(bad, d)],
                          extra=[(bad.lstrip("/"), d, None)])
            self.refused(zp)

    def test_absolute_and_backslash_entry_names(self):
        d = b"https://x.example/\tX\n"
        good = [{"path": config.OMNI_BOOKMARKS, "group": "bookmarks", "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}]
        for name in ("/data/omni/bookmarks.txt", "C:/data/omni/bookmarks.txt"):
            self.refused(evil_zip(self.zp(), {}, manifest=good, extra=[(name, d, None)]))
        # A real "\" in the stored name (zipfile's writer would turn it into "/"): patched into the zip's bytes.
        zp = evil_zip(self.zp(), {}, manifest=good, extra=[("data|omni|bookmarks.txt", d, None)])
        with open(zp, "rb") as f:
            raw = f.read().replace(b"data|omni|bookmarks.txt", b"data\\omni\\bookmarks.txt")
        with open(zp, "wb") as f:
            f.write(raw)
        self.refused(zp)

    def test_unknown_names(self):
        for p in (O + "passwords.txt", O + "browser-profile/Cookies", O + "session.txt", O + "native/omni-engine-child.elf",
                  O + "reading-list/evil.sh", "/data/pldmgr/autoload.txt", O + "ublock-native.flag"):
            self.refused(evil_zip(self.zp(), {p: b"x"}))

    def test_entry_not_in_manifest(self):
        self.refused(evil_zip(self.zp(), {O + "ui-theme.txt": b"x\n"}, extra=[("data/omni/shortcuts.txt", b"y", None)]))

    def test_listed_but_missing(self):
        d = b"x\n"
        self.refused(evil_zip(self.zp(), {}, manifest=[self.entry(O + "ui-theme.txt", d)]))

    def test_oversized(self):
        big = b"x" * (4 * 1024 + 1)                      # ui-theme.txt may be 4 KB
        self.refused(evil_zip(self.zp(), {O + "ui-theme.txt": big}))
        pages = {O + "reading-list/p%03d.html" % i: b"p" for i in range(201)}    # Omni keeps 200 pages
        self.refused(evil_zip(self.zp(), pages))

    def test_size_lies(self):
        d = b"dark\n"
        m = [self.entry(O + "ui-theme.txt", d)]
        m[0]["size"] = 2
        self.refused(evil_zip(self.zp(), {O + "ui-theme.txt": d}, manifest=m))

    def test_hash_mismatch(self):
        m = [self.entry(O + "ui-theme.txt", b"dark\n")]
        self.refused(evil_zip(self.zp(), {}, manifest=m, extra=[("data/omni/ui-theme.txt", b"evil\n", None)]))

    def test_wrong_group(self):
        d = b"x"
        m = [{"path": O + "history.txt", "group": "settings", "size": 1, "sha256": hashlib.sha256(d).hexdigest()}]
        self.refused(evil_zip(self.zp(), {O + "history.txt": d}, manifest=m))

    def test_duplicate_entries(self):
        zp = evil_zip(self.zp(), {O + "ui-theme.txt": b"a\n"})
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(zp, "a") as z:
                z.writestr("data/omni/ui-theme.txt", b"b\n")
        self.refused(zp)

    def test_symlink_and_folder_entries(self):
        d = b"x\n"
        m = [self.entry(O + "ui-theme.txt", d)]

        def link(info):
            info.external_attr = (0o120777 << 16)
        self.refused(evil_zip(self.zp(), {}, manifest=m, extra=[("data/omni/ui-theme.txt", d, link)]))
        self.refused(evil_zip(self.zp(), {}, manifest=[], extra=[("data/omni/reading-list/", b"", None)]))

    def test_not_a_backup(self):
        with open(self.zp(), "wb") as f:
            f.write(b"not a zip")
        self.refused(self.zp())
        with zipfile.ZipFile(self.zp(), "w") as z:
            z.writestr("data/omni/ui-theme.txt", b"x")
        self.refused(self.zp())                          # no manifest
        with zipfile.ZipFile(self.zp(), "w") as z:
            z.writestr(backup.MANIFEST_NAME, b"{not json")
        self.refused(self.zp())
        self.refused(evil_zip(self.zp(), {O + "ui-theme.txt": b"x"}, version=2))
        with zipfile.ZipFile(self.zp(), "w") as z:
            z.writestr(backup.MANIFEST_NAME, b"x" * (backup.MANIFEST_MAX + 1))
        self.refused(self.zp())

    def test_bad_manifest_rows(self):
        for rows in ([None], [{"path": O + "ui-theme.txt"}], "files", [{"path": O + "ui-theme.txt", "group": "settings",
                                                                       "size": "1", "sha256": "0"}]):
            self.refused(evil_zip(self.zp(), {}, manifest=rows))

    def test_one_bad_file_writes_nothing(self):
        good = {O + "ui-theme.txt": b"x\n", O + "shortcuts.txt": b"y\n"}
        zp = evil_zip(self.zp(), good, extra=[("data/omni/passwords.txt", b"z", None)])
        self.refused(zp)


if __name__ == "__main__":
    unittest.main()
