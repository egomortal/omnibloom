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
from test_end_to_end import (EBOOT, HUB_ELF, JD, MC_ELF, SUITE, WORKER, catalog_of, connect, make_engine_package,  # noqa: E402
                             make_jd_install, make_packages, new_console)
from omnibloom_setup import cli, config, installer, jd, oneclick, ps5, release  # noqa: E402

sha = lambda b: hashlib.sha256(b).hexdigest()
FAST = dict(poll=0.2, scan_poll=0.2, remind=0.5, title_wait=20, title_poll=0.2, smp_limit=5, smp_poll=0.1, smp_settle=0.05,
            smp_settle_missing=0.05, lock_wait=5, lock_poll=0.1, status_timeout=10, reconnect=2, no_websrv_pause=0.05,
            jd_wait=20, jd_poll=0.2)
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
        self.jd_home = os.path.join(self.tmp, "jd2")             # the only place JDownloader 2 is looked for
        self._candidates = jd.candidate_folders
        jd.candidate_folders = lambda: [self.jd_home]
        self._jd_env = os.environ.pop("OMNIBLOOM_ENABLE_JD", None)

    def tearDown(self):
        jd.candidate_folders = self._candidates
        os.environ.pop("OMNIBLOOM_ENABLE_JD", None)
        if self._jd_env is not None:
            os.environ["OMNIBLOOM_ENABLE_JD"] = self._jd_env
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

    def one_click(self, zips, catalog=None, **kw):
        fc = self.fc
        kw.setdefault("host", "127.0.0.1")
        oc = oneclick.OneClick(ftp_port=fc.ftp_port, loader_port=fc.loader_port, websrv_port=fc.websrv_port,
                               launcher_port=getattr(fc, "launcher_port", None), catalog=catalog or catalog_of(zips),
                               report=self.events.append, sleep=lambda s: time.sleep(min(s, 0.05)), **kw)
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


class DownloadsCard(Base):
    def test_hand_installed_downloads_gets_a_matching_card_and_receipt(self):
        """The console case: downloader-7 was copied by hand, but the card and Setup's receipt still describe the
        older install. The Downloads step must rewrite card + receipt together so Bloom Core verifies it."""
        old_zips, _ = make_packages(os.path.join(self.tmp, "old"))
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        self.assertTrue(self.one_click(old_zips)[1]["ok"], self.texts())
        new_zips, new_files = make_packages(os.path.join(self.tmp, "new"), changed=b" downloader-7", seed=1)
        fc.write(WORKER, new_files[WORKER])                              # the hand install
        self.assertEqual(json.loads(fc.read(config.CARDS_DIR + "downloads.json"))["version"], "0.5.0")
        # the release names the Downloads app by its own version (make_package.py --app-version downloads=downloader-7)
        stage = os.path.join(self.tmp, "new", "stage-omnibloom-0.5.0")
        out = os.path.join(self.tmp, "dl7")
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "tools", "make_package.py"), "--package", "omnibloom",
                        "--stage", stage, "--version", "0.5.1", "--app-version", "downloads=downloader-7", "--out", out],
                       check=True, capture_output=True)
        dl7 = [os.path.join(out, "omnibloom-console-0.5.1.zip"), new_zips[1]]
        self.events.clear()
        self.assertTrue(self.one_click(dl7)[1]["ok"], self.texts())
        self.assertTrue(self.said("Downloads 0.5.0 → downloader-7 (update)"))
        card_raw = fc.read(config.CARDS_DIR + "downloads.json")
        receipt = json.loads(fc.read(config.RECEIPTS_DIR + "downloads.json"))
        self.assertEqual(json.loads(card_raw)["version"], "downloader-7")
        self.assertEqual(receipt["version"], "downloader-7")
        self.assertEqual(receipt["card_sha256"], sha(card_raw))
        self.assertEqual(fc.read(WORKER), new_files[WORKER])
        with connect(fc) as c:
            self.assertEqual(installer.verify_app(c, catalog_of(dl7), "downloads"), [])
            status = installer.read_status(c, since=int(time.time()) + 1, want=["downloads"], timeout=10)
        dl = next(a for a in status["apps"] if a["id"] == "downloads")
        self.assertTrue(dl["verified"], dl)
        self.assertEqual(dl["version"], "downloader-7")
        self.assert_never_deleted()


class JDownloader2(Base):
    def test_held_back_still_finds_it_and_says_so(self):
        zips, _ = make_packages(self.tmp)
        make_jd_install(self.jd_home)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        asked = []
        oc, result = self.one_click(zips, confirm=lambda q: asked.append(q) or True)
        self.assertTrue(result["ok"], self.texts())
        self.assertTrue(self.said("Found JDownloader 2 at %s" % self.jd_home))
        skip = [e for e in self.events if e.get("step") == "jdownloader" and e["state"] == "skip"]
        self.assertTrue(skip and "held back" in skip[0]["text"], skip)
        self.assertEqual(asked, [], "nothing to fetch")
        self.assertFalse(fc.exists(JD + "native-install.json"))

    def test_held_back_and_missing_asks_nothing(self):
        zips, _ = make_packages(self.tmp)
        self.fc = new_console(os.path.join(self.tmp, "console"))
        asked, opened = [], []
        oc, result = self.one_click(zips, confirm=lambda q: asked.append(q) or True, open_page=opened.append)
        self.assertTrue(result["ok"], self.texts())
        self.assertEqual((asked, opened), ([], []))
        self.assertTrue(self.said(config.JD_OFFICIAL_URL))

    def test_missing_then_fetched_from_the_site_and_switched_on(self):
        os.environ["OMNIBLOOM_ENABLE_JD"] = "1"
        zips, _ = make_packages(self.tmp)
        engine_zip, engine_files = make_engine_package(self.tmp)
        fc = self.fc = new_console(os.path.join(self.tmp, "console"))
        fc.start_launcher()
        cat = catalog_of(zips)
        cat.add(release.Package(engine_zip))
        opened = []

        def user_installs_it(url):                         # the user downloads, installs and opens it once
            opened.append(url)
            threading.Timer(0.6, lambda: make_jd_install(self.jd_home)).start()
        oc, result = self.one_click(zips, catalog=cat, confirm=lambda q: True, open_page=user_installs_it)
        self.assertTrue(result["ok"], self.texts())
        self.assertEqual(opened, [config.JD_OFFICIAL_URL])
        self.assertTrue(self.said("JDownloader 2 is installed. Carrying on."))
        self.assertTrue(result["jdownloader"]["ok"], result.get("jdownloader"))
        self.assertIn(("jdownloader", "ok"), [(e.get("step"), e.get("state")) for e in self.events])
        self.assertIs(json.loads(fc.read(JD + "native-install.json"))["approved"], True)
        self.assertTrue(self.said("mateo-cogeanu"), "the Java port is credited")
        self.assert_never_deleted()

    def test_no_go_ahead_means_no_page_and_no_jdownloader(self):
        os.environ["OMNIBLOOM_ENABLE_JD"] = "1"
        zips, _ = make_packages(self.tmp)
        os.makedirs(self.jd_home)
        with open(os.path.join(self.jd_home, "JDownloader.jar"), "wb") as f:
            f.write(b"bootstrap only")                     # downloaded, never opened: no Core.jar yet
        self.fc = new_console(os.path.join(self.tmp, "console"))
        opened = []
        oc, result = self.one_click(zips, confirm=lambda q: False, open_page=opened.append)
        self.assertTrue(result["ok"], self.texts())
        self.assertEqual(opened, [])
        self.assertTrue(self.said("hasn't finished setting itself up"))
        skip = [e for e in self.events if e.get("step") == "jdownloader" and e["state"] == "skip"]
        self.assertTrue(skip and "yt-dlp downloads work" in skip[0]["text"], skip)


if __name__ == "__main__":
    unittest.main()
