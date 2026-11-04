"""Run a built Omnibloom Setup (the one-file app) in --cli mode against the fake console.
Checks results on the fake console itself (the windowed app may print to its own console).
  python tools/frozen_check.py dist/Omnibloom-Setup.exe"""
import os
import subprocess
import sys
import tempfile

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(TOP, "tests"), TOP]
from test_end_to_end import EBOOT, JD, make_engine_package, make_jd_install, make_packages, new_console  # noqa: E402
from omnibloom_setup import config  # noqa: E402

exe = os.path.abspath(sys.argv[1])
tmp = tempfile.mkdtemp(prefix="omnibloom-frozen-")
fc = new_console(os.path.join(tmp, "console"))
zips, files = make_packages(tmp)
engine, _ = make_engine_package(tmp)
jdroot = make_jd_install(os.path.join(tmp, "JDownloader 2.0"))
fc.start_launcher()
common = ["--ip", "127.0.0.1", "--ftp-port", str(fc.ftp_port), "--loader-port", str(fc.loader_port),
          "--websrv-port", str(fc.websrv_port), "--launcher-port", str(fc.launcher_port)]
pk = [x for z in zips for x in ("--package", z)]


def run(*args):
    r = subprocess.run([exe, "--cli"] + list(args) + common, timeout=300)
    print("%-10s exit %d" % (args[0], r.returncode), flush=True)
    return r.returncode


ok = True
ok &= run("check", "--quick") == 0
ok &= run("install", "--quick", "--apps", "omni,downloads,files-broker,master-control", "--autoload", "master-control", *pk) == 0
ok &= sorted(fc.listdir(config.CARDS_DIR)) == ["downloads.json", "files-broker.json", "master-control.json", "omni.json"]
ok &= fc.read(EBOOT) == files[EBOOT]
ok &= run("jd-setup", "--jd-folder", jdroot, "--offline", *pk, "--package", engine) == 0
ok &= b'"approved": true' in fc.read(JD + "native-install.json")
ok &= run("status") in (0, 1)
ok &= run("uninstall", "--app", "master-control") == 0
ok &= not fc.exists(config.CARDS_DIR + "master-control.json") and fc.exists(config.CARDS_DIR + "omni.json")
ok &= fc.state["deletes"] == []
fc.stop()
print("FROZEN CHECK", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
