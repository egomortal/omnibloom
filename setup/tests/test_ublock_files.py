"""Omni's network filter needs uBlock's rule files in /data/omni/. Up to v0.5.1 Setup switched the filter on but never
installed them, and Omni then blocked every page ("Filtering failed ... (error 1)"). Setup now installs the set when any
core file is missing, empty or too big, never replaces a working set, and never deletes (old files are parked)."""
import json
import os
import posixpath
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import config, installer  # noqa: E402

CORE = [config.OMNI_UBLOCK_DIR + n for n in config.OMNI_UBLOCK_CORE]
POPUP = config.OMNI_UBLOCK_DIR + config.OMNI_UBLOCK_EXTRA[0]
MANIFEST = config.OMNI_UBLOCK_DIR + config.OMNI_UBLOCK_MANIFEST


class Console:
    def __init__(self, files=None):
        self.files = dict(files or {})

    def exists(self, path):
        return path in self.files

    def size(self, path):
        return len(self.files[path]) if path in self.files else None

    def listing(self, parent):
        return {posixpath.basename(p): {} for p in self.files if posixpath.dirname(p) == parent.rstrip("/")}

    def makedirs(self, path):
        pass

    def store(self, path, data):
        self.files[path] = data

    def read(self, path):
        return self.files[path]

    def put_verified(self, path, data, readback=True):
        self.files[path + ".omnibloom-new"] = data
        return path + ".omnibloom-new"

    def rename(self, src, dst):
        self.files[dst] = self.files.pop(src)


class UBlockFiles(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.mkdtemp()
        for n in config.OMNI_UBLOCK_CORE + config.OMNI_UBLOCK_EXTRA:
            with open(os.path.join(self.src, n), "wb") as f:
                f.write(b"new " + n.encode())

    def tearDown(self):
        shutil.rmtree(self.src)

    def run_it(self, c):
        return installer.ensure_omni_ublock_files(c, lambda *_: None, source=self.src)

    def test_fresh_console_gets_the_set(self):
        c = Console()
        self.assertEqual(sorted(self.run_it(c)), sorted(CORE + [POPUP]))
        for p in CORE + [POPUP]:
            self.assertEqual(c.files[p], b"new " + posixpath.basename(p).encode())
        self.assertFalse([p for p in c.files if p.endswith(".omnibloom-new")])

    def test_working_set_is_never_replaced(self):
        old = {p: b"old" for p in CORE + [POPUP]}
        c = Console(old)
        self.assertEqual(self.run_it(c), [])
        self.assertEqual(c.files, old)

    def test_one_missing_core_file_rewrites_the_set_and_parks_the_rest(self):
        old = {CORE[0]: b"old engine", CORE[2]: b"old suffixes", POPUP: b"old popup"}
        c = Console(old)
        self.assertEqual(sorted(self.run_it(c)), sorted(CORE + [POPUP]))   # the popup rules go with the set
        for p in CORE + [POPUP]:
            self.assertTrue(c.files[p].startswith(b"new "))
        parked = sorted(v for p, v in c.files.items() if ".before-setup-" in p)
        self.assertEqual(parked, [b"old engine", b"old popup", b"old suffixes"])   # moved aside, not deleted

    def test_empty_or_too_big_counts_as_missing(self):
        for bad in (b"", b"x" * (config.OMNI_UBLOCK_MAX + 1)):
            c = Console({CORE[0]: b"e", CORE[1]: bad, CORE[2]: b"s", POPUP: b"p"})
            self.assertEqual(sorted(self.run_it(c)), sorted(CORE + [POPUP]))

    # -- versions (ublock-rules.json) --------------------------------------------------------------------------------
    def bundle(self, version, replaces=()):
        files = {n: installer._sha(b"new " + n.encode()) for n in config.OMNI_UBLOCK_CORE}
        with open(os.path.join(self.src, config.OMNI_UBLOCK_MANIFEST), "w", encoding="utf-8") as f:
            f.write(json.dumps({"version": version, "files": files, "replaces": list(replaces)}))

    def test_fresh_install_records_the_version(self):
        self.bundle("2026-11-20.1")
        c = Console()
        self.run_it(c)
        self.assertEqual(json.loads(c.files[MANIFEST])["version"], "2026-11-20.1")

    def test_an_older_setup_set_is_updated(self):
        self.bundle("2026-11-20.1")
        old = {p: b"old" for p in CORE + [POPUP]}
        old[MANIFEST] = json.dumps({"version": "2026-11-13.1"}).encode()
        c = Console(old)
        self.assertEqual(sorted(self.run_it(c)), sorted(CORE + [POPUP]))
        self.assertEqual(json.loads(c.files[MANIFEST])["version"], "2026-11-20.1")
        self.assertTrue(all(c.files[p].startswith(b"new ") for p in CORE))

    def test_the_same_or_a_newer_set_is_kept(self):
        for have in ("2026-11-20.1", "2026-12-01.1"):
            self.bundle("2026-11-20.1")
            old = {p: b"old" for p in CORE + [POPUP]}
            old[MANIFEST] = json.dumps({"version": have}).encode()
            c = Console(old)
            self.assertEqual(self.run_it(c), [])
            self.assertEqual(c.files, old)

    def test_a_hand_installed_set_is_never_replaced(self):
        # No version file and files Setup never shipped (e.g. the full uBlock lists put there by hand): kept as is.
        self.bundle("2026-11-20.1")
        old = {p: b"hand " + p.encode() for p in CORE + [POPUP]}
        c = Console(old)
        self.assertEqual(self.run_it(c), [])
        self.assertEqual(c.files, old)

    def test_a_v052_set_without_a_version_file_is_adopted_then_updated(self):
        # v0.5.2's Setup wrote the files but no version file: if they are exactly this set, only the version is recorded;
        # if they are a set a later Setup lists in "replaces", it is updated.
        self.bundle("2026-11-20.1")
        same = {config.OMNI_UBLOCK_DIR + n: b"new " + n.encode() for n in config.OMNI_UBLOCK_CORE + config.OMNI_UBLOCK_EXTRA}
        c = Console(dict(same))
        self.assertEqual(self.run_it(c), [])
        self.assertEqual(json.loads(c.files[MANIFEST])["version"], "2026-11-20.1")
        older = {n: installer._sha(b"v052 " + n.encode()) for n in config.OMNI_UBLOCK_CORE}
        self.bundle("2026-11-20.1", replaces=[older])
        c = Console({config.OMNI_UBLOCK_DIR + n: b"v052 " + n.encode() for n in config.OMNI_UBLOCK_CORE + config.OMNI_UBLOCK_EXTRA})
        self.assertEqual(sorted(self.run_it(c)), sorted(CORE + [POPUP]))

    def test_repo_manifest_matches_the_files(self):
        src = installer.ublock_source_dir()
        with open(os.path.join(src, config.OMNI_UBLOCK_MANIFEST), encoding="utf-8") as f:
            doc = json.load(f)
        for n in config.OMNI_UBLOCK_CORE + config.OMNI_UBLOCK_EXTRA:
            with open(os.path.join(src, n), "rb") as f:
                self.assertEqual(doc["files"][n], installer._sha(f.read().replace(b"\r\n", b"\n")), n)

    def test_setup_without_the_files_changes_nothing_core(self):
        c = Console()
        empty = tempfile.mkdtemp()
        try:
            self.assertEqual(installer.ensure_omni_ublock_files(c, lambda *_: None, source=empty), [])
        finally:
            shutil.rmtree(empty)
        self.assertEqual(c.files, {})

    def test_windows_line_endings_are_written_as_unix(self):
        # A Windows checkout has CRLF; Omni's engine then loads the rules but matches nothing.
        with open(os.path.join(self.src, "ublock-compiled.txt"), "wb") as f:
            f.write(b"#block\r\n[0,1,\"ads.example\"]\r\n")
        c = Console()
        self.run_it(c)
        self.assertEqual(c.files[config.OMNI_UBLOCK_DIR + "ublock-compiled.txt"], b"#block\n[0,1,\"ads.example\"]\n")

    def test_repo_carries_the_files(self):
        src = installer.ublock_source_dir()
        for n in config.OMNI_UBLOCK_CORE + config.OMNI_UBLOCK_EXTRA:
            size = os.path.getsize(os.path.join(src, n))
            self.assertTrue(0 < size <= config.OMNI_UBLOCK_MAX, n)

    def test_spec_bundles_them(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "omnibloom-setup.spec"), encoding="utf-8") as f:
            spec = f.read()
        for n in config.OMNI_UBLOCK_CORE + config.OMNI_UBLOCK_EXTRA:
            self.assertIn(n, spec)
        self.assertIn('"assets/ublock"', spec)


if __name__ == "__main__":
    unittest.main()
