"""Suite install / single-app install / update / repair / per-app uninstall / ports / JDownloader copy,
all against the fake console.   python -m unittest tests.test_end_to_end -v   (from omnibloom-setup/)
"""
import hashlib
import http.server
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, TOP)
sys.path.insert(0, HERE)

from fake_console import HUB_STUB_MAGIC, FakeConsole  # noqa: E402
from omnibloom_setup import checks, config, installer, jd, ports, ps5, release  # noqa: E402

sha = lambda b: hashlib.sha256(b).hexdigest()
P = config.PLDMGR_DIR + "payloads/"
HUB_ELF = P + "BloomCore/hub.elf"
MC_ELF = P + "master-control/master-control.elf"      # standard v1.1 item 7: /data/pldmgr/payloads/<id>/
MC_ICON = P + "master-control/icon-256.png"
OLD_MC_ELF = P + "MasterControl/master-control.elf"   # where Setup put it before item 7
EBOOT = config.TITLE_DIR + "eboot.bin"
WORKER = "/data/omni-downloader/worker/worker.py"
BROKER = "/data/omni/native/omni-files.elf"
BRIDGE = "/data/omni-downloader/jdownloader/runtime/classes/OmniJDownloaderBridge.class"
SUITE = ["omni", "downloads", "files-broker", "master-control"]


def _write_tree(root, files):
    for dest, data in files.items():
        p = os.path.join(root, dest.lstrip("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)


def make_packages(tmp, version="0.5.0", mc_version="0.4.3", changed=b"", seed=0):
    """Build both packages (omnibloom + master-control) the way a release would."""
    rnd = lambda n: hashlib.sha256(b"%d-%s-%d" % (seed, version.encode(), n)).digest() * 10000
    omni = {
        HUB_ELF: HUB_STUB_MAGIC + b" bloom core " + version.encode(),
        config.ICONS_DIR + "hub/icon-256.png": b"\x89PNG core",
        EBOOT: rnd(1)[:300000],
        config.TITLE_DIR + "sce_sys/param.json": json.dumps({"titleId": config.TITLE_ID, "titleName": "Omni"}).encode(),
        config.TITLE_DIR + "sce_sys/icon0.png": b"\x89PNG fake icon",
        config.TITLE_DIR + "sce_module/libc.prx": rnd(2)[:4000],
        "/data/omni/native/omni-engine-child.elf": rnd(3)[:200000],
        config.ICONS_DIR + "omni/icon-256.png": b"\x89PNG omni",
        BROKER: rnd(4)[:50000],
        WORKER: b"# worker " + version.encode() + changed,
        "/data/omni-downloader/worker/probe.py": b"# probe",
        "/data/omni-downloader/python-worker.elf": rnd(5)[:90000],
        "/data/omni-downloader/.deps/yt_dlp/__init__.py": b"# yt-dlp",
    }
    mc = {MC_ELF: rnd(6)[:120000] + mc_version.encode(), MC_ICON: b"\x89PNG mc"}
    out = os.path.join(tmp, "dist")
    zips = []
    for name, files, ver in (("omnibloom", omni, version), ("master-control", mc, mc_version)):
        stage = os.path.join(tmp, "stage-%s-%s" % (name, ver))
        _write_tree(stage, files)
        subprocess.run([sys.executable, os.path.join(TOP, "tools", "make_package.py"), "--package", name,
                        "--stage", stage, "--version", ver, "--out", out], check=True, capture_output=True)
        prefix = next(s["prefix"] for s in config.SOURCES if s["repo"].endswith("/" + name))
        zips.append(os.path.join(out, "%s%s.zip" % (prefix, ver)))
    files = dict(omni)
    files.update(mc)
    return zips, files


JD = config.JD_CONSOLE_ROOT
OVERRIDE = JD + "runtime/classes/org/jdownloader/api/myjdownloader/MyJDownloaderController.class"


EGRESS_FILES = {JD + "runtime/classes/OmniEgressPolicy.class": b"\xca\xfe\xba\xbe egress",
                JD + "runtime/classes/OmniPublicAddress.class": b"\xca\xfe\xba\xbe omni-public-only-v1",
                JD + "runtime/classes/OmniPublicResolverProvider.class": b"\xca\xfe\xba\xbe resolver",
                JD + "runtime/classes/META-INF/services/java.net.spi.InetAddressResolverProvider": b"OmniPublicResolverProvider\n"}


def make_engine_package(tmp, version="0.5.0", ready=True, extra=None, egress=True):
    """The JDownloader 2 engine release asset: java-worker.elf, the Java image, our bridge classes, notices."""
    image_files = {"java25/lib/modules": b"\xda\xda\xfe\xca modules " + version.encode(), "java25/release": b'JAVA_VERSION="25.0.4"',
                   "java25/lib/server/libjvm.so": b"\x7fELF jvm", "java25/conf/security/java.security": b"# security",
                   "java25/lib/tzdb.dat": b"tzdb", "java25/lib/security/cacerts": b"certs"}
    manifest = {"schema": "omni-java-native-image/v1", "target_root": JD + "native", "console_tested": False,
                "files": [{"path": k, "bytes": len(v), "sha256": sha(v)} for k, v in sorted(image_files.items())]}
    files = {JD + "java-worker.elf": b"\x7fELF java-worker " + version.encode(),
             JD + "native/image-manifest.json": json.dumps(manifest, indent=2).encode(),
             BRIDGE: b"\xca\xfe\xba\xbe bridge " + (b"OmniEgressPolicy " if egress else b"") + version.encode(),
             JD + "runtime/classes/OmniJDownloaderBridge$Job.class": b"\xca\xfe\xba\xbe job",
             OVERRIDE: b"\xca\xfe\xba\xbe override",
             JD + "notices/openjdk/LICENSE": b"GPLv2 + CPE", JD + "notices/ps5-java25-homebrew/THIRD_PARTY_NOTICES.md": b"# notices"}
    files.update({JD + "native/" + k: v for k, v in image_files.items()})
    if egress:
        files.update(EGRESS_FILES)
    files.update(extra or {})
    stage = os.path.join(tmp, "stage-engine-%s" % version)
    _write_tree(stage, files)
    out = os.path.join(tmp, "dist")
    args = [sys.executable, os.path.join(TOP, "tools", "make_package.py"), "--package", "omnibloom-jd-engine",
            "--stage", stage, "--version", version, "--out", out] + (["--jd-engine-ready"] if ready else [])
    subprocess.run(args, check=True, capture_output=True)
    return os.path.join(out, "omnibloom-jd-engine-%s.zip" % version), files


def make_jd_install(root, revision=50639, extra=None):
    files = {"JDownloader.jar": b"jd jar", "Core.jar": b"core jar", "libs/a.jar": b"lib", "extensions/e.jar": b"ext",
             "build.json": json.dumps({"JDownloaderRevision": revision}).encode(), "cfg/settings.json": b"{}",
             "tools/Windows/ffmpeg.exe": b"MZ", "JDownloader2.exe": b"MZ", "logs/x.log": b"log"}
    files.update(extra or {})
    _write_tree(root, files)
    return root


def catalog_of(zips):
    return release.Catalog([release.Package(z) for z in zips])


def new_console(root, autoload="shadowmountplus.elf\r\nkstuff-lite.elf\r\nftpsrv.elf\r\nEeveeLution-PS5.elf\r\n"):
    fc = FakeConsole(root).start()
    fc.write(config.AUTOLOAD_PATH, autoload)
    fc.write(EBOOT, b"OLD-S0B-EBOOT")
    fc.write("/data/shadowmount/debug.log", "[SCAN] start\n")
    fc.write("/data/omni/browser-profile/cookies.db", b"user cookies")
    fc.write("/data/mastercontrol/pairings.json", b'{"xbox": "paired"}')
    return fc


def connect(fc):
    return ps5.Console("127.0.0.1", ftp_port=fc.ftp_port, loader_port=fc.loader_port, websrv_port=fc.websrv_port,
                       launcher_port=getattr(fc, "launcher_port", None)).connect()


def hub_list(fc):
    return json.load(urllib.request.urlopen("http://127.0.0.1:%d/v1/apps" % fc.hub_port, timeout=5))


def hub_apps(fc):
    return {a["id"]: a for a in hub_list(fc)["apps"]}


class Suite(unittest.TestCase):
    """One console through its whole life: suite install → no-op → update → repair → uninstall one app."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="omnibloom-suite-")
        cls.fc = new_console(os.path.join(cls.tmp, "console"))
        cls.user_data = {p: cls.fc.read(p) for p in ("/data/omni/browser-profile/cookies.db", "/data/mastercontrol/pairings.json")}
        cls.zips, cls.files = make_packages(cls.tmp)
        cls.log = []

    @classmethod
    def tearDownClass(cls):
        cls.fc.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def clean(self):
        for p, data in self.user_data.items():
            self.assertEqual(self.fc.read(p), data, p)
        self.assertEqual(self.fc.state["deletes"], [], "Setup must never delete")

    def card(self, app_id):
        return json.loads(self.fc.read(config.CARDS_DIR + app_id + ".json"))

    def receipt(self, app_id):
        return json.loads(self.fc.read(config.RECEIPTS_DIR + app_id + ".json"))

    def test_t01_scan_and_checks(self):
        found = ps5.scan([ipaddress.ip_network("127.0.0.0/30")], ftp_port=self.fc.ftp_port, loader_port=self.fc.loader_port,
                         websrv_port=self.fc.websrv_port)
        self.assertEqual([f["host"] for f in found], ["127.0.0.1"])
        with connect(self.fc) as c:
            items, summary = checks.run_checks(c)
        self.assertTrue(summary["can_install"], items)
        self.assertEqual(summary["installed"], {})

    def test_t02_full_suite_install(self):
        cat = catalog_of(self.zips)
        with connect(self.fc) as c:
            rec = installer.install(c, cat, SUITE, autoload=["master-control"], start=["master-control"], log=self.log.append)
        fc = self.fc
        self.assertEqual(list(rec)[0], "hub", "Bloom Core goes first")
        for dest, data in self.files.items():
            self.assertEqual(fc.read(dest), data, dest)
        self.assertEqual(fc.read(EBOOT + ".before-omnibloom-0.5.0"), b"OLD-S0B-EBOOT")
        ports_ = {a: self.receipt(a).get("port") for a in ["hub"] + SUITE}
        self.assertEqual(ports_["hub"], 8760)
        self.assertEqual(ports_["downloads"], 8765)
        self.assertEqual(ports_["files-broker"], 8767)
        self.assertIsNone(ports_["omni"])
        self.assertNotIn(ports_["master-control"], config.RESERVED_PORTS)
        for a in SUITE:
            card = self.card(a)
            self.assertEqual(card["hub_api"], 1)
            self.assertEqual(card["id"], a)
            raw = fc.read(config.CARDS_DIR + a + ".json")
            self.assertEqual(self.receipt(a)["card_sha256"], sha(raw), a)
            self.assertLessEqual(len(fc.read(config.RECEIPTS_DIR + a + ".json")), config.RECEIPT_MAX)
            self.assertNotIn(None, card.values(), "no null fields (Bloom Core rejects them)")
        for a in ["hub"] + SUITE:
            self.assertTrue(fc.exists(config.LOGS_DIR + a) and fc.exists(config.CRASH_DIR + a))
            self.assertTrue(fc.exists(config.DETAILS_DIR + a + ".json"))
        self.assertFalse(fc.exists(config.CARDS_DIR + "hub.json"), "Bloom Core gets a receipt, not a card")
        self.assertEqual(self.receipt("hub")["port"], 8760)
        self.assertEqual(self.card("omni")["title_id"], config.TITLE_ID)
        self.assertNotIn("port", self.card("omni"))
        self.assertEqual(self.card("master-control")["icon"], MC_ICON)
        self.assertEqual(self.card("master-control")["launch"]["elf"], MC_ELF)
        al = fc.read(config.AUTOLOAD_PATH).decode()
        self.assertEqual(al, "shadowmountplus.elf\r\nkstuff-lite.elf\r\nftpsrv.elf\r\nhub.elf\r\nmaster-control.elf\r\n")
        self.assertEqual(json.loads(fc.read(MC_ELF + ".json"))["checksum"], sha(self.files[MC_ELF]))
        self.assertEqual(json.loads(fc.read(HUB_ELF + ".json"))["filename"], "hub.elf")
        self.assertIn(sha(self.files[HUB_ELF]), fc.state["payloads"])
        self.assertIn(sha(self.files[MC_ELF]), fc.state["payloads"])
        view = hub_apps(fc)
        self.assertEqual(sorted(view), sorted(SUITE))
        self.assertTrue(all(v["verified"] for v in view.values()), view)   # v1.1: a title needs no port
        self.assertIsNone(view["omni"]["port"])
        self.assertIsNone(view["omni"]["health"])
        self.assertEqual(hub_list(fc)["invalid"], [])
        # Setup reads Bloom Core's status.json over FTP after installing.
        with connect(fc) as c:
            status = installer.read_status(c, since=int(__import__("time").time()) + 1, want=SUITE, timeout=10)
        self.assertEqual(sorted(a["id"] for a in status["apps"]), sorted(SUITE))
        self.assertEqual(installer.explain_status(status), [])
        self.assertEqual(json.loads(fc.read(config.SETTINGS_PATH))["theme"], "silver-blue")
        type(self).mc_port = ports_["master-control"]
        self.clean()

    def test_t03_reinstall_is_no_op(self):
        dirs = (config.TITLE_DIR, P + "master-control", "/data/omni-downloader/worker")
        before = {d: sorted(self.fc.listdir(d)) for d in dirs}
        with connect(self.fc) as c:
            installer.install(c, catalog_of(self.zips), SUITE, autoload=["master-control"], log=self.log.append)
        for d in dirs:
            strip = lambda names: [n for n in names if ".prev-" not in n]
            self.assertEqual(strip(sorted(self.fc.listdir(d))), strip(before[d]), d)
        self.assertEqual(self.card("master-control")["port"], self.mc_port, "a working port is kept")
        self.clean()

    def test_t04_update_one_package(self):
        tmp2 = os.path.join(self.tmp, "v2")
        zips2, files2 = make_packages(tmp2, version="0.5.1", changed=b" new")
        cat = catalog_of([zips2[0], self.zips[1]])   # new omnibloom package, same Master Control
        with connect(self.fc) as c:
            ups = installer.updates(c, cat)
            self.assertEqual(set(ups), {"hub", "omni", "downloads", "files-broker"})
            installer.install(c, cat, list(ups), log=self.log.append)
            rec = installer.read_receipt(c, "omni")
        self.assertEqual(self.fc.read(WORKER), files2[WORKER])
        self.assertTrue(self.fc.exists(WORKER + ".omnibloom-old-0.5.0"))
        eb = next(f for f in rec["files"] if f["dest"] == EBOOT)
        self.assertEqual(eb["backup"], EBOOT + ".before-omnibloom-0.5.0", "the original stays the restore point")
        self.assertEqual(rec["history"][-1]["version"], "0.5.0")
        self.assertEqual(self.receipt("master-control")["version"], "0.4.3", "Master Control untouched")
        type(self).files2 = files2
        type(self).zips2 = [zips2[0], self.zips[1]]
        self.clean()

    def test_t05_repair_one_app(self):
        self.fc.write(WORKER, b"damaged")
        self.fc.write(config.CARDS_DIR + "downloads.json", b'{"id":"downloads","port":1}')
        with connect(self.fc) as c:
            fixed = installer.repair_app(c, catalog_of(self.zips2), "downloads", log=self.log.append)
        self.assertIn(WORKER, fixed)
        self.assertIn(config.CARDS_DIR + "downloads.json", fixed)
        self.assertEqual(self.fc.read(WORKER), self.files2[WORKER])
        self.assertTrue(hub_apps(self.fc)["downloads"]["verified"])
        self.clean()

    def test_t06_bloom_core_stays_while_apps_need_it(self):
        with connect(self.fc) as c:
            with self.assertRaises(IOError):
                installer.uninstall_app(c, "hub", log=self.log.append)

    def test_t07_uninstall_one_app_others_keep_working(self):
        with connect(self.fc) as c:
            installer.uninstall_app(c, "master-control", log=self.log.append)
            left = installer.installed_apps(c)
        fc = self.fc
        self.assertEqual(sorted(left), sorted(["hub", "omni", "downloads", "files-broker"]))
        self.assertFalse(fc.exists(MC_ELF))
        self.assertFalse(fc.exists(config.CARDS_DIR + "master-control.json"))
        al = fc.read(config.AUTOLOAD_PATH).decode()
        self.assertNotIn("master-control.elf", al)
        self.assertIn("EeveeLution-PS5.elf", al, "the controller app it replaced is back")
        self.assertIn("hub.elf", al)
        self.assertEqual(fc.read(WORKER), self.files2[WORKER])
        self.assertEqual(fc.read(EBOOT), self.files2[EBOOT])
        view = hub_apps(fc)
        self.assertEqual(sorted(view), sorted(a for a in left if a != "hub"))
        self.assertTrue(all(v["verified"] for k, v in view.items() if k != "omni"))
        self.clean()

    def test_t09_uninstall_everything(self):
        with connect(self.fc) as c:
            for a in ("omni", "downloads", "files-broker", "hub"):
                installer.uninstall_app(c, a, log=self.log.append)
            self.assertEqual(installer.installed_apps(c), {})
        fc = self.fc
        self.assertEqual(fc.read(EBOOT), b"OLD-S0B-EBOOT")
        self.assertEqual(fc.read(config.AUTOLOAD_PATH).decode(),
                         "shadowmountplus.elf\r\nkstuff-lite.elf\r\nftpsrv.elf\r\nEeveeLution-PS5.elf\r\n")
        self.assertTrue(fc.exists(config.SETTINGS_PATH), "shared settings are the user's")
        self.clean()


class SingleApp(unittest.TestCase):
    def test_master_control_alone(self):
        tmp = tempfile.mkdtemp(prefix="omnibloom-single-")
        fc = new_console(os.path.join(tmp, "console"))
        try:
            zips, files = make_packages(tmp)
            with connect(fc) as c:
                rec = installer.install(c, catalog_of(zips), ["master-control"], log=lambda m: None)
                self.assertEqual(sorted(rec), ["hub", "master-control"])
            self.assertEqual(fc.read(EBOOT), b"OLD-S0B-EBOOT", "Omni not installed")
            self.assertEqual(sorted(fc.listdir(config.CARDS_DIR)), ["master-control.json"])
            self.assertTrue(fc.exists(config.RECEIPTS_DIR + "hub.json"))
            al = fc.read(config.AUTOLOAD_PATH).decode()
            self.assertIn("hub.elf", al)
            self.assertNotIn("master-control.elf", al, "autoload is opt-in")
            self.assertIn("EeveeLution-PS5.elf", al)
            self.assertEqual(fc.state["deletes"], [])
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_without_bloom_core_in_release(self):
        tmp = tempfile.mkdtemp(prefix="omnibloom-nohub-")
        fc = new_console(os.path.join(tmp, "console"))
        try:
            zips, _ = make_packages(tmp)
            log = []
            with connect(fc) as c:
                rec = installer.install(c, catalog_of([zips[1]]), ["master-control"], log=log.append)
            self.assertEqual(sorted(rec), ["master-control"])
            self.assertTrue(any("isn't in this release yet" in l for l in log))
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


class PayloadFolderMove(unittest.TestCase):
    def test_master_control_moves_to_its_id_folder(self):
        """Item 7: an install from the old /MasterControl/ layout parks the old ELF and Payload Manager entry
        (autoload lists bare names, so two copies must not both be visible), keeps one autoload line, and
        uninstall still works."""
        tmp = tempfile.mkdtemp(prefix="omnibloom-move-")
        fc = new_console(os.path.join(tmp, "console"),
                         autoload="shadowmountplus.elf\r\nkstuff-lite.elf\r\nftpsrv.elf\r\nmaster-control.elf\r\n")
        try:
            old_elf, old_meta = b"\x7fELF mc 0.4.2", b'{"filename": "master-control.elf"}'
            fc.write(OLD_MC_ELF, old_elf)
            fc.write(OLD_MC_ELF + ".json", old_meta)
            details = {"schema": installer.RECEIPT_SCHEMA + "-details", "id": "master-control",
                       "files": [{"dest": OLD_MC_ELF, "sha256": sha(old_elf), "bytes": len(old_elf), "backup": None},
                                 {"dest": OLD_MC_ELF + ".json", "sha256": sha(old_meta), "bytes": len(old_meta), "backup": None}],
                       "card": {"hub_api": 1, "id": "master-control", "version": "0.4.2", "port": 8766}}
            receipt = {"schema": installer.RECEIPT_SCHEMA, "id": "master-control", "name": "Master Control", "version": "0.4.2",
                       "installed_at": "2026-11-01T00:00:00Z", "port": 8766, "history": [],
                       "autoload": {"elf": "master-control.elf", "changed": True, "removed": [], "backup": None},
                       "details": config.DETAILS_DIR + "master-control.json"}
            fc.write(config.DETAILS_DIR + "master-control.json", json.dumps(details))
            fc.write(config.RECEIPTS_DIR + "master-control.json", json.dumps(receipt))
            zips, files = make_packages(tmp)
            log = []
            with connect(fc) as c:
                installer.install(c, catalog_of(zips), ["master-control"], autoload=["master-control"], log=log.append)
            self.assertEqual(fc.read(MC_ELF), files[MC_ELF])
            self.assertEqual(fc.read(MC_ICON), files[MC_ICON])
            self.assertFalse(fc.exists(OLD_MC_ELF), "old copy parked")
            self.assertFalse(fc.exists(OLD_MC_ELF + ".json"), "old Payload Manager entry parked")
            parked = fc.listdir(P + "MasterControl")
            self.assertIn("master-control.elf.omnibloom-moved-0.4.3", parked)
            self.assertIn("master-control.elf.json.omnibloom-moved-0.4.3", parked)
            self.assertTrue(fc.exists(MC_ELF + ".json"))
            al = fc.read(config.AUTOLOAD_PATH).decode()
            self.assertEqual(al.count("master-control.elf"), 1, al)
            card = json.loads(fc.read(config.CARDS_DIR + "master-control.json"))
            self.assertEqual((card["launch"]["elf"], card["icon"]), (MC_ELF, MC_ICON))
            self.assertTrue(hub_apps(fc)["master-control"]["verified"])
            with connect(fc) as c:
                installer.uninstall_app(c, "master-control", log=log.append)
            self.assertFalse(fc.exists(MC_ELF))
            self.assertNotIn("master-control.elf", fc.read(config.AUTOLOAD_PATH).decode())
            self.assertEqual(fc.state["deletes"], [])
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


class Ports(unittest.TestCase):
    def test_collisions(self):
        tmp = tempfile.mkdtemp(prefix="omnibloom-ports-")
        fc = new_console(os.path.join(tmp, "console"))
        busy = socket.socket()
        try:
            busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:   # something else answers on Master Control's usual port
                busy.bind(("127.0.0.1", 8766))
                busy.listen(1)
            except OSError:
                pass  # already in use on this machine: same effect for the probe
            fc.write(config.CARDS_DIR + "other.json", json.dumps({"hub_api": 1, "id": "other", "port": 8761}))
            with connect(fc) as c:
                picker = ports.PortPicker(c)
                p, note = picker.pick("master-control", {"preferred": 8766, "movable": True})
                self.assertNotIn(p, (8766, 8761) + tuple(config.RESERVED_PORTS))
                self.assertIn("8766", note)
                p2, _ = picker.pick("new-app", {"preferred": p, "movable": True})
                self.assertNotEqual(p2, p, "a port picked in this run isn't handed out twice")
                fc.write(config.CARDS_DIR + "squatter.json", json.dumps({"hub_api": 1, "id": "squatter", "port": 8765}))
                with self.assertRaises(ports.PortClash):
                    ports.PortPicker(c).pick("downloads", {"preferred": 8765, "movable": False})
                p3, _ = ports.PortPicker(c).pick("hub", {"preferred": 8760, "movable": False})
                self.assertEqual(p3, 8760, "Bloom Core owns its fixed port")
        finally:
            busy.close()
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)


class Checks(unittest.TestCase):
    def test_missing_kstuff_and_log_growth(self):
        tmp = tempfile.mkdtemp()
        fc = FakeConsole(os.path.join(tmp, "c"), websrv=False).start()
        try:
            fc.write(config.AUTOLOAD_PATH, "shadowmountplus.elf\nftpsrv.elf\n")
            fc.write("/data/shadowmount/debug.log", "x\n")

            def grow(_):
                with open(fc.path("/data/shadowmount/debug.log"), "a") as f:
                    f.write("[SKIP] scan\n")
            with connect(fc) as c:
                items, summary = checks.run_checks(c, sleep=grow)
        finally:
            fc.stop()
            shutil.rmtree(tmp, ignore_errors=True)
        status = {i["id"]: i["status"] for i in items}
        self.assertEqual(status["shadowmount"], "ok")
        self.assertEqual(status["kstuff"], "bad")
        self.assertFalse(summary["can_install"])


class PackageSafety(unittest.TestCase):
    def test_bad_destinations_refused(self):
        for dest in ("/data/omni/browser-profile/cookies.db", "/system/evil", "/data/homebrew/PPSA99732/../../pldmgr/autoload.txt",
                     "/data/mastercontrol/pairings.json", "relative/path", "/data/padbridge/x", config.SETTINGS_PATH,
                     config.CARDS_DIR + "omni.json", config.RECEIPTS_DIR + "omni.json", config.AUTOLOAD_PATH):
            with self.assertRaises(release.ReleaseError, msg=dest):
                release.check_dest(dest)
        release.check_dest(EBOOT)
        with self.assertRaises(release.ReleaseError):
            release.check_dest(MC_ELF, roots=[config.TITLE_DIR])   # an app can't write another app's folder

    def test_tampered_or_overlapping_package_refused(self):
        tmp = tempfile.mkdtemp()
        try:
            zips, _ = make_packages(tmp, version="0.9.0")
            bad = zips[0].replace(".zip", "-bad.zip")
            overlap = None
            with zipfile.ZipFile(zips[0]) as zin, zipfile.ZipFile(bad, "w") as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename.endswith("worker.py"):
                        data = b"tampered"
                    if item.filename == config.RELEASE_MANIFEST:
                        overlap = json.loads(data)
                    zout.writestr(item, data)
            with self.assertRaises(release.ReleaseError):
                release.Package(bad).verify_all()
            overlap["apps"]["files-broker"]["roots"].append(config.TITLE_DIR)
            ov = zips[0].replace(".zip", "-overlap.zip")
            with zipfile.ZipFile(ov, "w") as z:
                z.writestr(config.RELEASE_MANIFEST, json.dumps(overlap))
            with self.assertRaises(release.ReleaseError):
                release.Package(ov)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class GitHubDownload(unittest.TestCase):
    """The online path against a local stand-in for the GitHub API: both repos, then one missing."""

    def test_two_sources(self):
        tmp = tempfile.mkdtemp()
        try:
            zips, _ = make_packages(tmp, version="1.2.3", mc_version="0.4.9")
            dist = os.path.dirname(zips[0])
            state = {"mc_missing": False, "tamper": False}

            class H(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    base = "http://127.0.0.1:%d" % self.server.server_address[1]
                    body = None
                    for z in zips:
                        name = os.path.basename(z)
                        repo = "omnibloom" if name.startswith("omnibloom") else "master-control"
                        if self.path == "/repos/egomortal/%s/releases/latest" % repo:
                            if repo == "master-control" and state["mc_missing"]:
                                self.send_error(404)
                                return
                            body = json.dumps({"tag_name": "v" + name.split("-")[-1][:-4], "assets": [
                                {"name": name, "browser_download_url": base + "/dl/" + name, "size": os.path.getsize(z)},
                                {"name": name + ".sha256", "browser_download_url": base + "/dl/" + name + ".sha256"},
                                {"name": "RELEASE-MANIFEST.json", "browser_download_url": base + "/manifest/" + name}]}).encode()
                        if self.path == "/manifest/" + name:   # audit RL-01: the release manifest asset
                            raw = open(z, "rb").read()
                            body = json.dumps({"schema": "omnibloom-release-manifest/v1", "tag": "v" + name.split("-")[-1][:-4],
                                               "assets": [{"name": name, "bytes": len(raw), "sha256": sha(raw)}]}).encode()
                    if body is None and self.path.startswith("/dl/"):
                        body = open(os.path.join(dist, self.path[4:]), "rb").read()
                        if state["tamper"] and self.path.endswith(".zip"):
                            body = body[:-10] + b"0123456789"
                    if body is None:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *a):
                    pass

            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            api = "http://127.0.0.1:%d" % srv.server_address[1]
            empty = os.path.join(tmp, "empty")
            cache = os.path.join(tmp, "cache")
            os.makedirs(empty)
            os.makedirs(cache)
            old = release.cache_dir
            release.cache_dir = lambda: cache
            try:
                cat = release.load_catalog(folder=empty, api_base=api)
                self.assertEqual(cat.versions(), {"hub": "1.2.3", "omni": "1.2.3", "downloads": "1.2.3",
                                                  "files-broker": "1.2.3", "master-control": "0.4.9"})
                cat.close()
                state["mc_missing"] = True
                cat = release.load_catalog(folder=empty, api_base=api)
                self.assertFalse(cat.has("master-control"))
                self.assertTrue(cat.errors)
                cat.close()
                for f in os.listdir(cache):
                    os.remove(os.path.join(cache, f))
                state["tamper"] = True
                with self.assertRaises(release.ReleaseError):
                    release.load_catalog(folder=empty, api_base=api)
            finally:
                release.cache_dir = old
                srv.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class BloomCoreStub(unittest.TestCase):
    """The fake Bloom Core follows hub.c: titles without a port, health:null on titles, id "hub" refused, field checks,
    port conflicts (the later id loses), runtime/<id>.json and status.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-hub-")
        self.fc = FakeConsole(os.path.join(self.tmp, "c")).start()
        self.fc.start_hub_stub()

    def tearDown(self):
        self.fc.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def card(self, cid, receipt=True, **kw):
        c = {"hub_api": 1, "id": cid, "name": cid.title(), "version": "1.0", "kind": "service", "port": 8770}
        c.update(kw)
        c = {k: v for k, v in c.items() if v is not ...}
        raw = json.dumps(c).encode()
        self.fc.write(config.CARDS_DIR + cid + ".json", raw)
        if receipt:
            r = {"schema": "hub-receipt/v1", "id": cid, "version": c.get("version"), "card_sha256": sha(raw)}
            if c.get("port") is not None:
                r["port"] = c["port"]
            self.fc.write(config.RECEIPTS_DIR + cid + ".json", json.dumps(r))
        return raw

    def test_rules(self):
        self.card("omni", kind="title", port=..., health=None, title_id=config.TITLE_ID)
        self.card("hub", port=8771)
        self.card("svc-noport", port=...)
        self.card("svc-nullhealth", port=8772, health=None)
        self.card("badkind", kind="app", port=8773)
        self.card("badauto", port=8774, launch={"autoload": "sometimes"})
        self.card("badstarter", port=8775, launch={"started_by": "Downloads"})
        self.card("badpages", port=8776, public_pages=["no-slash"])
        self.card("badapis", port=8777, page_apis=["/api/../x"])
        self.card("reserved", port=9021)
        self.card("aaa", port=8780)
        self.card("bbb", port=8780)                     # same port, later id
        self.card("noreceipt", port=8781, receipt=False)
        self.card("changed", port=8782)
        # item 15: started_by apps may leave the port out; their live port comes from runtime/<id>.json
        self.card("eng", port=..., health=None, launch={"started_by": "downloads", "autoload": "never"})
        self.card("eng2", port=..., launch={"started_by": "downloads"})
        self.card("eng3", port=..., launch={"started_by": "downloads"})
        self.card("eng4", port=..., launch={"started_by": "downloads"})
        self.card("eng5", port=..., launch={"started_by": "downloads"})
        self.card("svc-nostarter", port=..., launch={"autoload": "never"})
        self.fc.write("/data/hub/runtime/eng.json", json.dumps({"id": "eng", "pid": os.getpid(), "port": 18950}))
        self.fc.write("/data/hub/runtime/eng2.json", json.dumps({"id": "eng2", "pid": os.getpid(), "port": 9021}))
        self.fc.write("/data/hub/runtime/eng3.json", json.dumps({"id": "eng3", "pid": 2 ** 22 + 12345, "port": 18951}))
        self.fc.write("/data/hub/runtime/eng4.json", json.dumps({"id": "eng4", "pid": os.getpid(), "port": 18952, "host": "192.168.1.5"}))
        self.fc.write(config.CARDS_DIR + "changed.json", json.dumps({"hub_api": 1, "id": "changed", "name": "Changed",
                                                                      "version": "1.0", "kind": "service", "port": 8782, "health": "/x"}))
        self.fc.write("/data/hub/runtime/aaa.json", json.dumps({"id": "aaa", "pid": 77, "port": 8780, "started_at": 1700000000}))
        listing = hub_list(self.fc)
        apps = {a["id"]: a for a in listing["apps"]}
        bad = {b["file"]: b["reason"] for b in listing["invalid"]}
        self.assertTrue(apps["omni"]["verified"])
        self.assertIsNone(apps["omni"]["port"])
        self.assertEqual(bad["hub.json"], "id hub is Bloom Core's own (it has no card)")
        self.assertEqual(bad["svc-noport.json"], "port missing or outside 1024-65535")
        self.assertEqual(bad["svc-nullhealth.json"], "health must be a path like /api/health")
        self.assertEqual(bad["badkind.json"], "kind must be title, payload or service")
        self.assertEqual(bad["badauto.json"], "launch.autoload must be never, optional or required")
        self.assertEqual(bad["badstarter.json"], "launch.started_by must be an app id")
        self.assertEqual(bad["badpages.json"], "public_pages must be a list of paths")
        self.assertEqual(bad["badapis.json"], "page_apis must be a list of paths")
        self.assertEqual(bad["reserved.json"], "port is reserved (8760, 9021, 2121)")
        self.assertTrue(apps["aaa"]["verified"])
        self.assertEqual((apps["bbb"]["status"], apps["bbb"]["why"]), ("conflict", "port 8780 already used by aaa"))
        self.assertEqual(apps["noreceipt"]["why"], "no receipt from Setup")
        self.assertEqual(apps["changed"]["why"], "card changed since install")
        self.assertEqual(apps["aaa"]["runtime"], {"pid": 77, "port": 8780, "started_at": 1700000000})
        self.assertEqual(bad["svc-nostarter.json"], "port missing or outside 1024-65535")
        for cid in ("eng", "eng2", "eng3", "eng4", "eng5"):
            self.assertTrue(apps[cid]["verified"], cid)
            self.assertEqual((apps[cid]["port"], apps[cid]["port_from"], apps[cid]["up"]), (None, "runtime", False), cid)
        self.assertIsNone(apps["eng"]["health"])
        self.assertEqual(apps["eng2"]["health"], "/api/health")
        self.assertNotIn("runtime_note", apps["eng"])
        self.assertEqual(apps["eng2"]["runtime_note"], "runtime port is reserved")
        self.assertEqual(apps["eng3"]["runtime_note"], "runtime pid is not running (stale)")
        self.assertEqual(apps["eng4"]["runtime_note"], "runtime host is not loopback")
        self.assertEqual(apps["eng5"]["runtime_note"], "no runtime file")
        self.fc.write_status()
        status = json.loads(self.fc.read("/data/hub/status.json"))
        self.assertEqual(status["id"], "hub")
        self.assertIn({"file": "hub.json", "reason": "id hub is Bloom Core's own (it has no card)"}, status["invalid"])
        lines = installer.explain_status(status)
        self.assertTrue(any("bbb: not verified (port 8780 already used by aaa)" in l for l in lines), lines)
        self.assertTrue(any("svc-noport.json was refused" in l for l in lines), lines)


class JDownloader(unittest.TestCase):
    """The JDownloader 2 step against the fake console, whose launcher plays java-worker.elf."""

    def setUp(self):
        os.environ["OMNIBLOOM_ENABLE_JD"] = "1"          # the step is held back by default (audit JD-03)
        self.addCleanup(os.environ.pop, "OMNIBLOOM_ENABLE_JD", None)
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-jd-")
        self.fc = new_console(os.path.join(self.tmp, "console"))
        self.fc.start_launcher()
        zips, _ = make_packages(self.tmp)
        self.engine_zip, self.engine_files = make_engine_package(self.tmp)
        self.cat = catalog_of(zips)
        self.jdroot = make_jd_install(os.path.join(self.tmp, "JDownloader 2.0"))
        self.log = []
        with connect(self.fc) as c:
            installer.install(c, self.cat, ["downloads"], log=self.log.append)

    def tearDown(self):
        self.cat.close()
        self.fc.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load_engine(self):
        release.load_engine(self.cat, folder=os.path.dirname(self.engine_zip), online=False, log=self.log.append)

    def run_setup(self):
        with connect(self.fc) as c:
            return jd.setup_jdownloader(c, self.cat, self.jdroot, log=self.log.append, sleep=lambda s: __import__("time").sleep(0.05))

    def test_held_back_by_switch(self):
        """Audit JD-03: OMNIBLOOM_ENABLE_JD=0 refuses before touching the PS5."""
        self.load_engine()
        os.environ["OMNIBLOOM_ENABLE_JD"] = "0"
        self.assertFalse(config.jd_enabled())
        with connect(self.fc) as c:
            with self.assertRaises(jd.CheckFailed) as ctx:
                jd.setup_jdownloader(c, self.cat, self.jdroot, log=self.log.append)
        self.assertIn("held back", str(ctx.exception))
        self.assertFalse(self.fc.exists(config.JD_CONSOLE_ROOT + "java-worker.elf"))

    def test_engine_without_egress_policy_is_refused(self):
        """Audit JD-03: by default an engine that doesn't declare the egress policy is refused before the PS5 changes."""
        os.environ.pop("OMNIBLOOM_ENABLE_JD", None)
        old, _ = make_engine_package(os.path.join(self.tmp, "old"), version="0.4.9", egress=False)
        self.cat.add(release.Package(old))
        self.assertTrue(jd.engine_ready(self.cat))
        self.assertNotIn("egress_policy", self.cat.jd_engine())
        self.assertFalse(config.jd_enabled(self.cat.jd_engine()))
        with connect(self.fc) as c:
            with self.assertRaises(jd.CheckFailed) as ctx:
                jd.setup_jdownloader(c, self.cat, self.jdroot, log=self.log.append)
        self.assertIn("public addresses", str(ctx.exception))
        self.assertFalse(self.fc.exists(config.JD_CONSOLE_ROOT + "java-worker.elf"))

    def test_engine_with_egress_policy_switches_on_by_default(self):
        """Audit JD-03: with an engine that declares omni-public-only-v1, no developer switch is needed."""
        os.environ.pop("OMNIBLOOM_ENABLE_JD", None)
        self.load_engine()
        self.assertEqual(self.cat.jd_engine()["egress_policy"], "omni-public-only-v1")
        self.assertTrue(config.jd_enabled())
        self.assertTrue(config.jd_enabled(self.cat.jd_engine()))
        result = self.run_setup()
        self.assertTrue(self.fc.exists(config.JD_CONSOLE_ROOT + "native-install.json"))
        self.assertIn("native_install", result)

    def test_engine_package_refuses_a_partial_egress_policy(self):
        partial = {JD + "runtime/classes/OmniEgressPolicy.class": b"\xca\xfe\xba\xbe egress"}
        with self.assertRaises(subprocess.CalledProcessError) as ctx:
            make_engine_package(os.path.join(self.tmp, "partial"), version="0.5.2", egress=False, extra=partial)
        self.assertIn(b"only part of the egress policy", ctx.exception.stderr)

    def test_detect_summary_and_revision(self):
        s = jd.summary(self.jdroot)
        self.assertEqual(s["files"], 5)                    # 2 jars + build.json + libs/a.jar + extensions/e.jar
        self.assertIsNone(s["revision_note"])
        other = make_jd_install(os.path.join(self.tmp, "jd-other"), revision=51000)
        self.assertIn("51000", jd.summary(other)["revision_note"])

    def test_engine_needs_its_package(self):
        self.assertFalse(jd.engine_ready(self.cat))
        with self.assertRaises(release.ReleaseError):
            release.load_engine(self.cat, folder=os.path.join(self.tmp, "stage-omnibloom-0.5.0"), online=False)
        self.load_engine()
        info = self.cat.jd_engine()
        self.assertEqual(info["elf_sha256"], sha(self.engine_files[JD + "java-worker.elf"]))
        self.assertEqual(info["java_port"]["repo"], "mateo-cogeanu/ps5-java25-homebrew")
        self.assertTrue(release.Catalog([release.Package(self.engine_zip)]).jd_engine_ready())
        not_ready, _ = make_engine_package(os.path.join(self.tmp, "nr"), version="0.5.1", ready=False)
        self.assertFalse(release.Catalog([release.Package(not_ready)]).jd_engine_ready())

    def test_full_flow_switches_on(self):
        self.load_engine()
        # an older JDownloader install on the console: a stale jar, a stale folder, a closed old session
        self.fc.write(JD + "runtime/libs/old-removed.jar", b"stale")
        self.fc.write(JD + "runtime/oldplugins/x.class", b"stale dir")
        self.fc.write(JD + "runtime/cfg/org.jdownloader.settings.GeneralSettings.json", b'{"user":"setting"}')
        self.fc.write(JD + "lifecycle-state.json", json.dumps({"schema": "omni-jd-lifecycle/v1", "status": "closed", "install_id": "old"}))
        self.fc.write(JD + "native-install.json", b'{"old": true}')
        result = self.run_setup()
        fc = self.fc
        spec = json.loads(fc.read(JD + "native-install.json"))
        self.assertEqual(spec["schema"], "omni-jd-native-install/v1")
        self.assertIs(spec["approved"], True)
        self.assertIs(spec["target_acceptance"]["passed"], True)
        self.assertEqual(spec["elf_sha256"], sha(self.engine_files[JD + "java-worker.elf"]))
        self.assertEqual(spec["elf_bytes"], len(self.engine_files[JD + "java-worker.elf"]))
        self.assertEqual({m["kind"] for m in spec["asset_manifests"]}, {"native-image", "jdownloader"})
        self.assertTrue(all(set(m) == {"kind", "path", "sha256"} for m in spec["asset_manifests"]))
        ev = fc.read(spec["target_acceptance"]["evidence"])
        self.assertEqual(sha(ev), spec["target_acceptance"]["evidence_sha256"])
        manifest_raw = fc.read(JD + "assets-manifest.json")
        jd_pin = next(m for m in spec["asset_manifests"] if m["kind"] == "jdownloader")
        self.assertEqual(sha(manifest_raw), jd_pin["sha256"])
        manifest = json.loads(manifest_raw)
        self.assertEqual(manifest["schema"], "omni-jd-assets-manifest/v2")
        self.assertIs(manifest["host_jre_included"], False)
        names = {r["path"] for r in manifest["files"]}
        self.assertEqual(manifest["file_count"], len(names))
        for crit in jd.CRITICAL_RUNTIME:
            self.assertIn(crit, names)
        # The console's own exact-set rule (jd_lifecycle._verify_assets): runtime/ outside JDownloader's writable
        # folders holds exactly the manifest's files, and native/java25 exactly the image manifest's.
        actual = set()
        for dirpath, dirs, files in os.walk(fc.path(JD + "runtime")):
            rel = os.path.relpath(dirpath, fc.path(JD)).replace(os.sep, "/")
            if rel.split("/")[1:2] and rel.split("/")[1] in config.JD_MUTABLE:
                continue
            actual |= {rel + "/" + f for f in files}
        self.assertEqual(actual, names)
        for row in manifest["files"]:
            self.assertEqual(sha(fc.read(JD + row["path"])), row["sha256"], row["path"])
        image = json.loads(fc.read(JD + "native/image-manifest.json"))
        on_disk = {os.path.relpath(os.path.join(d, f), fc.path(JD + "native")).replace(os.sep, "/")
                   for d, _, fs in os.walk(fc.path(JD + "native/java25")) for f in fs}
        self.assertEqual(on_disk, {r["path"] for r in image["files"]})
        # nothing deleted, user settings untouched, old things parked in setup-backup/
        self.assertEqual(fc.read(JD + "runtime/cfg/org.jdownloader.settings.GeneralSettings.json"), b'{"user":"setting"}')
        backups = [os.path.relpath(os.path.join(d, f), fc.path(config.JD_BACKUP_DIR)).replace(os.sep, "/")
                   for d, _, fs in os.walk(fc.path(config.JD_BACKUP_DIR)) for f in fs]
        self.assertTrue(any(b.endswith("runtime/libs/old-removed.jar") for b in backups), backups)
        self.assertTrue(any(b.endswith("runtime/oldplugins/x.class") for b in backups), backups)
        self.assertTrue(any(b.endswith("lifecycle-state.json") for b in backups), backups)
        self.assertTrue(any(b.endswith("native-install.json") for b in backups), backups)
        self.assertEqual(fc.state["deletes"], [])
        # two launches through /hbldr, in order, with the engine's own argument shape
        modes = [q["args"].split(" ")[2] for q in fc.state["launches"]]
        self.assertEqual(modes, ["providers", "jdownloader"])
        self.assertTrue(all(q["path"] == JD + "java-worker.elf" and q["daemon"] == "1" for q in fc.state["launches"]))
        # engine: a card without a port (item 15); Bloom Core takes its live port from runtime/jdownloader.json
        self.assertTrue(fc.exists(config.RECEIPTS_DIR + "jdownloader.json"))
        raw = fc.read(config.CARDS_DIR + "jdownloader.json")
        card = json.loads(raw)
        self.assertNotIn("port", card)
        self.assertIsNone(card["health"], "the bridge isn't HTTP: Bloom Core checks its runtime pid instead")
        self.assertEqual(card["launch"]["started_by"], "downloads")
        rec = json.loads(fc.read(config.RECEIPTS_DIR + "jdownloader.json"))
        self.assertEqual(rec["card_sha256"], sha(raw))
        self.assertNotIn("port", rec)
        apps, invalid = fc.hub_scan()
        eng = next(a for a in apps if a["id"] == "jdownloader")
        self.assertEqual((eng["verified"], eng["port"], eng["port_from"], eng["runtime_note"]), (True, None, "runtime", "no runtime file"))
        fc.write("/data/hub/runtime/jdownloader.json", json.dumps({"id": "jdownloader", "pid": os.getpid(), "port": 18950, "host": "127.0.0.1"}))
        eng = next(a for a in fc.hub_scan()[0] if a["id"] == "jdownloader")
        self.assertNotIn("runtime_note", eng)
        self.assertTrue(any("switched on" in l for l in self.log), self.log)
        self.assertEqual(result["acceptance"]["runs"]["providers"]["native_pid"], 4242)
        # Running it again is quick and keeps things on
        self.fc.state["launches"].clear()
        self.run_setup()
        self.assertEqual(len(self.fc.state["launches"]), 2)
        self.assertIs(json.loads(fc.read(JD + "native-install.json"))["approved"], True)

    def test_failed_check_leaves_it_off(self):
        self.load_engine()
        for mode, behaviour, words in (("providers", "fail", "native parts"), ("jdownloader", "no-ready", "didn't start"),
                                       ("jdownloader", "no-egress", "connection guard")):
            self.fc.jd_behaviour = {"providers": "pass", "jdownloader": "pass", "delay": 0.1}
            self.fc.jd_behaviour[mode] = behaviour
            with self.assertRaises(jd.CheckFailed) as cm:
                self.run_setup()
            self.assertIn(words, str(cm.exception))
            self.assertFalse(self.fc.exists(JD + "native-install.json"), mode)
        self.assertEqual(self.fc.state["deletes"], [])

    def test_refuses_while_running(self):
        self.load_engine()
        self.fc.write(JD + "lifecycle-state.json", json.dumps({"status": "ready"}))
        self.fc.write(JD + "native-install.json", b'{"keep": true}')
        with self.assertRaises(jd.CheckFailed):
            self.run_setup()
        self.assertEqual(self.fc.read(JD + "native-install.json"), b'{"keep": true}', "nothing switched while JD runs")
        self.assertEqual(self.fc.state.get("launches"), [])

    def test_stale_session_after_restart(self):
        # a session left "ready" by an engine that is no longer running (the PS5 restarted): Setup goes ahead
        self.load_engine()
        self.fc.write(JD + "lifecycle-state.json", json.dumps({"status": "ready", "session": "s1"}))
        self.fc.write(JD + "bridge-ready.json", json.dumps({"session": "s1", "native_pid": 183}))
        with mock.patch.object(ps5.Console, "process_ids", return_value={1, 95, 101}):
            self.run_setup()
        self.assertTrue(self.fc.exists(JD + "native-install.json"))

    def test_live_session_still_refused(self):
        self.load_engine()
        self.fc.write(JD + "lifecycle-state.json", json.dumps({"status": "ready", "session": "s1"}))
        self.fc.write(JD + "bridge-ready.json", json.dumps({"session": "s1", "native_pid": 183}))
        for pids in ({1, 183}, None):          # the engine is running / the process list can't be read
            with mock.patch.object(ps5.Console, "process_ids", return_value=pids):
                with self.assertRaises(jd.CheckFailed):
                    self.run_setup()
        self.assertEqual(self.fc.state.get("launches"), [])

    def test_no_launcher_means_off(self):
        self.load_engine()
        self.fc.launcher.shutdown()
        self.fc.launcher.server_close()
        with self.assertRaises(jd.CheckFailed) as cm:
            self.run_setup()
        self.assertIn("launcher", str(cm.exception))
        self.assertFalse(self.fc.exists(JD + "native-install.json"))

    def test_engine_update_and_uninstall(self):
        self.load_engine()
        self.run_setup()
        # a newer engine: old engine files must leave native/ (exact set), not sit beside the new ones
        engine2, files2 = make_engine_package(os.path.join(self.tmp, "e2"), version="0.5.1",
                                              extra={JD + "native/java25/lib/extra.dat": b"new"})
        with zipfile.ZipFile(engine2) as z:
            self.assertIn("files" + JD + "native/java25/lib/extra.dat", z.namelist())
        cat2 = catalog_of([engine2])
        cat2.add(self.cat.source["downloads"])
        with connect(self.fc) as c:
            jd.setup_jdownloader(c, cat2, self.jdroot, log=self.log.append, sleep=lambda s: __import__("time").sleep(0.05))
        names = set(self.fc.listdir(JD + "native/java25/lib"))
        self.assertNotIn("modules.omnibloom-old-0.5.0", names)
        self.assertEqual(self.fc.read(JD + "native/java25/lib/modules"), files2[JD + "native/java25/lib/modules"])
        cat2.close()
        with connect(self.fc) as c:
            installer.uninstall_app(c, config.JD_APP_ID, log=self.log.append)
        self.assertFalse(self.fc.exists(JD + "native-install.json"), "uninstall switches JDownloader 2 off first")
        self.assertFalse(self.fc.exists(JD + "java-worker.elf"))
        self.assertEqual(self.fc.state["deletes"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
