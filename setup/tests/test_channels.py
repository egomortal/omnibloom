"""OMNIBLOOM_CHANNELS_V1: one package carries the stable build and the experimental Bloom Preview build.

Run: python -m unittest tests/test_channels.py   (from the setup folder)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, TOP)

from omnibloom_setup import config, release  # noqa: E402

EBOOT = config.TITLE_DIR + "eboot.bin"
PAGE = config.TITLE_DIR + "pages/start/index.html"
NEW_PAGE = config.TITLE_DIR + "pages/whatsnew/index.html"
HUB_ELF = config.PLDMGR_DIR + "payloads/BloomCore/hub.elf"
WORKER = "/data/omni-downloader/worker/worker.py"


def _write_tree(root, files):
    for dest, data in files.items():
        path = os.path.join(root, dest.lstrip("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


STABLE = {HUB_ELF: b"hub 0.5.4", EBOOT: b"stable eboot" * 1000, PAGE: b"<p>start</p>",
          config.TITLE_DIR + "sce_sys/param.json": b"{}", WORKER: b"# worker stable"}
BLOOM = {EBOOT: b"bloom eboot" * 1000, PAGE: b"<p>start</p>", NEW_PAGE: b"<p>new</p>",
         config.TITLE_DIR + "sce_sys/param.json": b"{}"}


def build(tmp, channel=True, bloom=None):
    stage, bstage, out = (os.path.join(tmp, n) for n in ("stage", "stage-bloom", "dist"))
    _write_tree(stage, STABLE)
    _write_tree(bstage, BLOOM if bloom is None else bloom)
    cmd = [sys.executable, os.path.join(TOP, "tools", "make_package.py"), "--package", "omnibloom", "--stage", stage,
           "--version", "0.5.4", "--out", out]
    if channel:
        cmd += ["--channel", "%s=%s" % (config.BLOOM_CHANNEL, bstage),
                "--channel-version", "%s=0.5.4-bloom.1" % config.BLOOM_CHANNEL,
                "--channel-label", "%s=Experimental build (Bloom Preview)" % config.BLOOM_CHANNEL,
                "--channel-notes", "%s=Expect rough edges." % config.BLOOM_CHANNEL]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r, os.path.join(out, "omnibloom-console-0.5.4.zip")


def rewrite_manifest(path, change):
    """Copy the zip with an edited manifest (for the refusal tests)."""
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    m = json.loads(items[config.RELEASE_MANIFEST])
    change(m)
    items[config.RELEASE_MANIFEST] = json.dumps(m).encode()
    bad = path.replace(".zip", "-bad.zip")
    with zipfile.ZipFile(bad, "w") as z:
        for n, data in items.items():
            z.writestr(n, data)
    return bad


class Channels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="obs-ch-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stable_by_default_and_bloom_on_request(self):
        r, path = build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        pkg = release.Package(path)
        pkg.verify_all()
        cat = release.Catalog([pkg])
        self.assertEqual(cat.channels(), {config.BLOOM_CHANNEL: {"label": "Experimental build (Bloom Preview)",
                                                                 "notes": "Expect rough edges."}})
        stable = {row["dest"]: cat.data("omni", row) for row in cat.files_for("omni")}
        self.assertEqual(stable[EBOOT], STABLE[EBOOT])
        self.assertNotIn(NEW_PAGE, stable)
        self.assertEqual(cat.apps["omni"]["version"], "0.5.4")

        self.assertEqual(cat.use_channel(config.BLOOM_CHANNEL), ["omni"])   # only the apps the channel covers
        bloom = {row["dest"]: cat.data("omni", row) for row in cat.files_for("omni")}
        self.assertEqual(bloom, BLOOM)
        self.assertEqual(cat.apps["omni"]["version"], "0.5.4-bloom.1")
        self.assertEqual(cat.apps["downloads"]["version"], "0.5.4")
        self.assertEqual({r["dest"] for r in cat.files_for("downloads")}, {WORKER})

        cat.use_channel(None)
        self.assertEqual(cat.apps["omni"]["version"], "0.5.4")
        self.assertEqual({row["dest"] for row in cat.files_for("omni")}, {d for d in STABLE if d.startswith(config.TITLE_DIR)})
        cat.close()

    def test_old_setups_see_the_stable_package_unchanged(self):
        """Setups before 0.5.4 read only schema/apps/files: those must be exactly what a package without channels has."""
        _, plain = build(os.path.join(self.tmp, "a"), channel=False)
        _, both = build(os.path.join(self.tmp, "b"))
        with zipfile.ZipFile(plain) as a, zipfile.ZipFile(both) as b:
            ma, mb = json.loads(a.read(config.RELEASE_MANIFEST)), json.loads(b.read(config.RELEASE_MANIFEST))
            self.assertEqual({k: v for k, v in mb.items() if k != "channels"}, ma)
            for row in ma["files"]:
                self.assertEqual(set(row), {"app", "src", "dest", "sha256", "bytes"})
                self.assertEqual(hashlib.sha256(b.read(row["src"])).hexdigest(), row["sha256"])
            # identical files are stored once: only the changed eboot and the new page are extra
            extra = [n for n in b.namelist() if n.startswith("channels/")]
            self.assertEqual(sorted(extra), sorted("channels/%s/files%s" % (config.BLOOM_CHANNEL, d) for d in (EBOOT, NEW_PAGE)))

    def test_unknown_channel_is_refused(self):
        _, path = build(self.tmp)
        cat = release.Catalog([release.Package(path)])
        with self.assertRaises(release.ReleaseError):
            cat.use_channel("nightly")
        self.assertIsNone(cat.channel)
        cat.close()

    def test_bad_channel_blocks_are_refused(self):
        _, path = build(self.tmp)
        ch = config.BLOOM_CHANNEL

        def outside(m):
            m["channels"][ch]["apps"]["omni"]["files"][0]["dest"] = "/data/omni-downloader/worker/x.py"

        def extra_key(m):
            m["channels"][ch]["apps"]["omni"]["files"][0]["note"] = 1

        def unknown_app(m):
            m["channels"][ch]["apps"]["ghost"] = m["channels"][ch]["apps"]["omni"]

        def bad_name(m):
            m["channels"]["Bad Name"] = m["channels"].pop(ch)

        def dup(m):
            files = m["channels"][ch]["apps"]["omni"]["files"]
            files.append(dict(files[0]))

        def empty(m):
            m["channels"][ch]["apps"]["omni"]["files"] = []

        for change in (outside, extra_key, unknown_app, bad_name, dup, empty):
            bad = rewrite_manifest(path, change)
            with self.assertRaises(release.ReleaseError, msg=change.__name__):
                release.Package(bad).close()

    def test_damaged_channel_file_is_caught(self):
        _, path = build(self.tmp)

        def wrong_sum(m):
            row = next(r for r in m["channels"][config.BLOOM_CHANNEL]["apps"]["omni"]["files"] if r["dest"] == EBOOT)
            row["sha256"] = "0" * 64
        pkg = release.Package(rewrite_manifest(path, wrong_sum))
        with self.assertRaises(release.ReleaseError):
            pkg.verify_all()
        pkg.close()

    def test_channel_app_must_ship_stable_too(self):
        r, _ = build(self.tmp, bloom={"/data/omni/native/omni-files.elf": b"broker"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("doesn't ship", r.stderr + r.stdout)

    def test_bloom_versions_order(self):
        from omnibloom_setup import installer
        self.assertFalse(installer.update_available("0.5.4-bloom.1", "0.5.4"))      # stable of the same release: not "newer"
        self.assertTrue(installer.update_available("0.5.4-bloom.1", "0.5.4-bloom.2"))
        self.assertTrue(installer.update_available("0.5.4-bloom.3", "0.5.5"))       # the next stable release is


class InstallAndSwitchBack(unittest.TestCase):
    """On the fake PS5 (needs pyftpdlib, as the other console tests): stable -> Bloom Preview -> stable."""

    def test_switch_both_ways(self):
        try:
            sys.path.insert(0, HERE)
            from test_end_to_end import connect, new_console
        except ImportError as error:
            self.skipTest(str(error))
        from omnibloom_setup import installer
        tmp = tempfile.mkdtemp(prefix="obs-ch-e2e-")
        fc = new_console(os.path.join(tmp, "ps5"))
        try:
            _, path = build(tmp)
            cat = release.Catalog([release.Package(path)])
            with connect(fc) as c:
                installer.install(c, cat, ["omni"], log=lambda m: None)
                self.assertEqual(fc.read(EBOOT), STABLE[EBOOT])
                cat.use_channel(config.BLOOM_CHANNEL)
                installer.install(c, cat, ["omni"], log=lambda m: None)
                self.assertEqual(fc.read(EBOOT), BLOOM[EBOOT])
                self.assertEqual(fc.read(NEW_PAGE), BLOOM[NEW_PAGE])
                self.assertEqual(installer.read_receipt(c, "omni")["version"], "0.5.4-bloom.1")
                cat.use_channel(None)
                installer.install(c, cat, ["omni"], log=lambda m: None)
                self.assertEqual(fc.read(EBOOT), STABLE[EBOOT])
                receipt = installer.read_receipt(c, "omni")
                self.assertEqual(receipt["version"], "0.5.4")
                # the Bloom-only page stays covered by the receipt, so uninstall still cleans it up
                self.assertIn(NEW_PAGE, {f["dest"] for f in receipt["files"]})
            cat.close()
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


class CommandLine(unittest.TestCase):
    def test_experimental_flag_switches_the_catalog(self):
        tmp = tempfile.mkdtemp(prefix="obs-ch-cli-")
        try:
            _, path = build(tmp)
            from omnibloom_setup import cli
            import argparse
            a = argparse.Namespace(package=[path], offline=True, api=None, experimental=True, command="list")
            cat = cli._catalog(a, lambda m: None)
            self.assertEqual(cat.channel, config.BLOOM_CHANNEL)
            self.assertEqual(cat.apps["omni"]["version"], "0.5.4-bloom.1")
            cat.close()
            a.experimental, a.command = True, "oneclick"   # oneclick switches it itself (and says so)
            cat = cli._catalog(a, lambda m: None)
            self.assertIsNone(cat.channel)
            cat.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
