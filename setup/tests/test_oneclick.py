"""The one-button install against the fake console: waiting for the PS5, installing everything in order with
narration, checking each app, rolling back on a failure, waiting for Omni to close, keeping the user's HDR setting,
and "Undo last install".      python -m unittest tests.test_oneclick -v   (from setup/)
"""
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fake_console import FakeConsole  # noqa: E402
from test_end_to_end import EBOOT, HUB_ELF, MC_ELF, SUITE, WORKER, catalog_of, connect, make_packages, new_console  # noqa: E402
from omnibloom_setup import cli, config, installer, oneclick, ps5  # noqa: E402

sha = lambda b: hashlib.sha256(b).hexdigest()
FAST = dict(poll=0.2, scan_poll=0.2, remind=0.5, title_wait=20, title_poll=0.2, smp_limit=5, smp_poll=0.1, smp_settle=0.05,
            smp_settle_missing=0.05, lock_wait=5, lock_poll=0.1, status_timeout=10, reconnect=2, no_websrv_pause=0.05)
PREF = config.OMNI_HDR_PREF
USER_FILES = ("/data/omni/browser-profile/cookies.db", "/data/mastercontrol/pairings.json")


def free_ports(n):
    socks = [socket.socket() for _ in range(n)]
    for s in socks:
        s.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in socks]
    for s in socks:
        s.close()
    return ports


def snapshot(root):
    """{console path: sha} of every file on the fake PS5."""
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            full = os.path.join(d, n)
            rel = "/" + os.path.relpath(full, root).replace("\\", "/")
            with open(full, "rb") as f:
                out[rel] = sha(f.read())
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-oneclick-")
        self._env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp, "pc")     # receipts and run files on "this computer"
        self._timing = dict(oneclick.TIMING)
        oneclick.TIMING.update(FAST)
        self.events = []
        self.fc = None

    def tearDown(self):
        oneclick.TIMING.clear()
        oneclick.TIMING.update(self._timing)
        if self._env is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._env
        if self.fc:
            self.fc.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def texts(self):
        return [e.get("text", "") for e in self.events]

    def said(self, words):
        return any(words in t for t in self.texts())

    def index(self, words):
        return next(i for i, t in enumerate(self.texts()) if words in t)

    def one_click(self, zips, **kw):
        fc = self.fc
        kw.setdefault("host", "127.0.0.1")
        oc = oneclick.OneClick(ftp_port=fc.ftp_port, loader_port=fc.loader_port, websrv_port=fc.websrv_port,
                               catalog=catalog_of(zips), report=self.events.append, sleep=lambda s: time.sleep(min(s, 0.05)), **kw)
        return oc, oc.run()

    def assert_never_deleted(self):
        self.assertEqual(self.fc.state["deletes"], [], "Setup must never delete")

    def assert_lock_free(self):
        self.assertIsNone(json.loads(self.fc.read(config.SETUP_LOCK))["owner"])


class OneButton(Base):
    def test_waits_for_the_ps5_then_installs_everything_in_order(self):
        zips, files = make_packages(self.tmp)
        ftp, loader, web = free_ports(3)
        root = os.path.join(self.tmp, "console")
        fc = self.fc = FakeConsole(root)
        fc.write(config.AUTOLOAD_PATH, "shadowmountplus.elf\nkstuff-lite.elf\nftpsrv.elf\n")
        fc.write(EBOOT, b"OLD-S0B-EBOOT")
        fc.write(config.SMP_LOG, "[SCAN] start\n")
        for p in USER_FILES:
            fc.write(p, b"user data " + p.encode())
        oc = oneclick.OneClick(host="127.0.0.1", ftp_port=ftp, loader_port=loader, websrv_port=web, catalog=catalog_of(zips),
                               report=self.events.append, sleep=lambda s: time.sleep(min(s, 0.05)))
        result = {}
        t = threading.Thread(target=lambda: result.update(oc.run()))
        t.start()
        time.sleep(1.5)                          # Setup is listening; the "PS5" isn't on yet
        self.assertTrue(self.said("Waiting for your PS5"))
        self.assertFalse(self.said("Found your PS5"))
        fc.start(ftp_port=ftp, loader_port=loader, websrv_port=web)
        t.join(120)
        self.assertFalse(t.is_alive())
        self.assertTrue(result["ok"], self.texts())

        for dest, data in files.items():
            self.assertEqual(fc.read(dest), data, dest)
        self.assertEqual(fc.read(EBOOT + ".before-omnibloom-0.5.0"), b"OLD-S0B-EBOOT", "the old Omni is kept")
        # each app in order: installing → checked
        starts = [e["step"] for e in self.events if e.get("state") == "active" and e.get("step") in oneclick.ORDER]
        self.assertEqual(starts, ["hub"] + SUITE)
        oks = [e["step"] for e in self.events if e.get("state") == "ok"]
        for step in ("apps", "find", "check", "hub", "omni", "downloads", "files-broker", "master-control", "settings", "start"):
            self.assertIn(step, oks)
        for words in ("Found your PS5 at 127.0.0.1", "Installing Omni 0.5.0", "Checking Omni", "ShadowMountPlus picked up Omni",
                      "Omni 0.5.0 is installed and checked", "Set Omni's HDR to Auto", "confirmed every app", "All done"):
            self.assertTrue(self.said(words), words)
        self.assertLess(self.index("Installing Omni"), self.index("ShadowMountPlus picked up Omni"))
        self.assertLess(self.index("ShadowMountPlus picked up Omni"), self.index("Checking Omni"))
        # started only after everything was installed and checked
        self.assertIn(sha(files[HUB_ELF]), fc.state["payloads"])
        self.assertIn(sha(files[MC_ELF]), fc.state["payloads"])
        self.assertLess(self.index("Master Control 0.4.3 is installed and checked"), self.index("Starting"))
        self.assertEqual(fc.read(PREF), b"1\tauto\n")
        with connect(fc) as c:
            for a in ["hub"] + SUITE:
                self.assertEqual(installer.verify_app(c, catalog_of(zips), a), [], a)
        for p in USER_FILES:
            self.assertEqual(fc.read(p), b"user data " + p.encode())
        self.assertIn("hub.elf", fc.read(config.AUTOLOAD_PATH).decode().split())
        self.assertNotIn("master-control.elf", fc.read(config.AUTOLOAD_PATH).decode().split(), "autoload only when asked")
        self.assert_never_deleted()
        self.assert_lock_free()
        self.assertTrue(os.path.isfile(result["run_file"]))

    def test_a_failure_puts_everything_back(self):
        zips, files = make_packages(self.tmp)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        before = snapshot(fc.root)
        real_rename = ps5.Console.rename

        def broken(console, src, dst):
            if dst == MC_ELF:
                raise IOError("simulated FTP drop")
            return real_rename(console, src, dst)
        ps5.Console.rename = broken
        try:
            oc, result = self.one_click(zips)
        finally:
            ps5.Console.rename = real_rename
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"], self.texts())
        for words in ("Something went wrong", "simulated FTP drop", "Putting your PS5 back", "back the way it was"):
            self.assertTrue(self.said(words), words)
        self.assertIn({"step": "master-control", "state": "fail", "text": "Master Control didn't finish."}, self.events)
        after = snapshot(fc.root)
        for path, digest in before.items():
            if path != config.SMP_LOG:
                self.assertEqual(after.get(path), digest, "%s was not put back" % path)
        extra = [p for p in after if p not in before and oneclick.UNDONE not in p and p != config.SETUP_LOCK]
        self.assertEqual(extra, [], "anything new was set aside, not left live")
        self.assertEqual(fc.read(EBOOT), b"OLD-S0B-EBOOT")
        self.assertEqual(fc.state["payloads"], [], "nothing is started when the install doesn't finish")
        self.assertFalse(fc.exists(config.CARDS_DIR + "omni.json"))
        with connect(fc) as c:
            self.assertEqual(installer.installed_apps(c), {})
            self.assertEqual(installer.pending_installs(c), {})
        self.assert_never_deleted()
        self.assert_lock_free()

    def test_waits_for_omni_to_close_and_never_closes_it(self):
        zips, files = make_packages(self.tmp)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        fc.processes.append("eboot.bin")              # Omni (or a game) is open
        events = self.events

        class User(list):                            # closes Omni a moment after Setup asks
            def append(self, e):
                events.append(e)
                if "Please close it" in e.get("text", ""):
                    threading.Timer(0.8, lambda: fc.processes.remove("eboot.bin")).start()
        self.events = User()
        oc, result = self.one_click(zips)
        self.events = events
        self.assertTrue(result["ok"], self.texts())
        self.assertTrue(self.said("Please close it"))
        self.assertLess(self.index("Please close it"), self.index("it's closed"))
        self.assertLess(self.index("it's closed"), self.index("ShadowMountPlus picked up Omni"))
        self.assertEqual(fc.read(EBOOT), files[EBOOT])

    def test_keeps_the_users_hdr_setting_from_the_command_line(self):
        zips, _ = make_packages(self.tmp)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        fc.write(PREF, b"3\ton\n")
        argv = ["oneclick", "--ip", "127.0.0.1", "--ftp-port", str(fc.ftp_port), "--loader-port", str(fc.loader_port),
                "--websrv-port", str(fc.websrv_port), "--no-start-master-control"] + sum((["--package", z] for z in zips), [])
        self.assertEqual(cli.main(argv), 0)
        self.assertEqual(fc.read(PREF), b"3\ton\n")
        self.assertTrue(fc.state["payloads"], "Bloom Core was started")
        self.assert_lock_free()

    def test_stop_while_waiting_changes_nothing(self):
        zips, _ = make_packages(self.tmp)
        ftp, loader, web = free_ports(3)
        cancel = threading.Event()
        oc = oneclick.OneClick(host="127.0.0.1", ftp_port=ftp, loader_port=loader, websrv_port=web, catalog=catalog_of(zips),
                               report=self.events.append, cancel=cancel)
        threading.Timer(0.6, cancel.set).start()
        result = oc.run()
        self.assertFalse(result["ok"])
        self.assertTrue(self.said("You stopped Setup"))

    def test_another_setup_holds_the_ps5(self):
        zips, _ = make_packages(self.tmp)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        fc.write(config.SETUP_LOCK, json.dumps({"owner": "someone-else", "expires": time.time() + 600}))
        oneclick.TIMING["lock_wait"] = 0.5
        oc, result = self.one_click(zips)
        self.assertFalse(result["ok"])
        self.assertTrue(self.said("Another copy of Omnibloom Setup is working on this PS5"))
        self.assertFalse(fc.exists(config.CARDS_DIR + "omni.json"))


class Undo(Base):
    def test_update_then_undo_last_goes_back_to_the_old_version(self):
        old_zips, old_files = make_packages(os.path.join(self.tmp, "old"))
        new_zips, new_files = make_packages(os.path.join(self.tmp, "new"), version="0.6.0", changed=b" fixed", seed=1)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        self.assertTrue(self.one_click(old_zips)[1]["ok"], self.texts())
        installed_v5 = snapshot(fc.root)
        self.assertTrue(self.one_click(new_zips)[1]["ok"], self.texts())
        self.assertTrue(self.said("Omni 0.5.0 → 0.6.0 (update)"))
        self.assertEqual(fc.read(WORKER), new_files[WORKER])
        self.events.clear()
        ok = oneclick.undo_last("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, websrv_port=fc.websrv_port,
                                report=self.events.append, sleep=lambda s: time.sleep(min(s, 0.05)))
        self.assertTrue(ok, self.texts())
        self.assertTrue(self.said("Undone: your PS5 is back"))
        self.assertEqual(fc.read(WORKER), old_files[WORKER])
        self.assertEqual(fc.read(EBOOT), old_files[EBOOT])
        after = snapshot(fc.root)
        for path, digest in installed_v5.items():
            if path not in (config.SMP_LOG, config.HUB_DIR + "status.json", config.SETUP_LOCK):
                self.assertEqual(after.get(path), digest, path)
        with connect(fc) as c:
            self.assertEqual({a: r["version"] for a, r in installer.installed_apps(c).items()},
                             {"hub": "0.5.0", "omni": "0.5.0", "downloads": "0.5.0", "files-broker": "0.5.0", "master-control": "0.4.3"})
            for a in ["hub"] + SUITE:
                self.assertEqual(installer.verify_app(c, catalog_of(old_zips), a), [], a)
        # nothing left to undo for that run; the next undo goes to the first install
        run = oneclick.last_run("127.0.0.1")
        self.assertIn('"0.5.0"', json.dumps(run["header"]["apps"]))
        self.assert_never_deleted()

    def test_undo_leaves_files_you_changed_since(self):
        zips, _ = make_packages(self.tmp)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        self.assertTrue(self.one_click(zips)[1]["ok"], self.texts())
        fc.write(config.SETTINGS_PATH, b'{"theme": "mine"}')          # the user's own settings, created by that install
        self.events.clear()
        ok = oneclick.undo_last("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, websrv_port=fc.websrv_port,
                                report=self.events.append, sleep=lambda s: time.sleep(min(s, 0.05)))
        self.assertFalse(ok)
        self.assertTrue(self.said("was changed after the install"))
        self.assertEqual(fc.read(config.SETTINGS_PATH), b'{"theme": "mine"}')
        self.assertEqual(fc.read(EBOOT), b"OLD-S0B-EBOOT", "everything else went back")
        self.assert_never_deleted()


if __name__ == "__main__":
    unittest.main()
