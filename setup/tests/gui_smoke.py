"""Drive the Setup window through every step against the fake console and save a screenshot of each.
Needs a display (on Linux CI: xvfb-run). Usage: python tests/gui_smoke.py <shots-dir>"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import tkinter as tk  # noqa: E402

from test_end_to_end import new_console, make_packages, make_engine_package, make_jd_install, EBOOT, JD  # noqa: E402
from omnibloom_setup import config, gui, oneclick, release  # noqa: E402

shots = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "shots")
os.makedirs(shots, exist_ok=True)
tmp = tempfile.mkdtemp(prefix="omnibloom-gui-")
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "pc")      # run files and the remembered PS5 stay in the test folder
fc = new_console(os.path.join(tmp, "console"))
zips, files = make_packages(tmp)
make_engine_package(tmp)              # the JDownloader 2 engine sits next to Setup too
fc.start_launcher()
jdroot = make_jd_install(os.path.join(tmp, "JDownloader 2.0"))
os.chdir(os.path.dirname(zips[0]))   # Setup picks up the packages next to it (offline mode)
release_load = release.load_catalog
release.load_catalog = lambda **kw: release_load(online=False)

root = tk.Tk()
app = gui.SetupApp(root, test_ports={"ftp": fc.ftp_port, "loader": fc.loader_port, "websrv": fc.websrv_port,
                                     "launcher": fc.launcher_port, "host": "127.0.0.1"})


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.03)


def shot(name):
    pump(0.4)
    try:
        from PIL import ImageGrab
        x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY")).save(os.path.join(shots, name + ".png"))
    except Exception as e:  # screenshots are a bonus; the flow is the test
        print("screenshot skipped:", e)
    print("step:", name)


def wait_for(cond, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.05)
    raise SystemExit("timed out on a step (%s)" % app.steps[app.step].__name__)


root.geometry("800x680+0+0")
pump(0.5)
shot("1-welcome")
app.next()
wait_for(lambda: app.found_box.winfo_children() and app.catalog is not None)
shot("2-find")
app.next()
wait_for(lambda: str(app.next_btn["state"]) == "normal")
shot("3-check")
app.next()
shot("4-choose")
app.autoload_mc.set(True)
app.next()
app.jd_folder.set(jdroot)
app._jd_refresh()
app.jd_copy.set(True)
shot("5-jdownloader")
app.next()
wait_for(lambda: str(app.next_btn["state"]) == "normal", 180)
shot("6-install")
app.next()
shot("7-done")
assert app.result.get("_jd", {}).get("ok"), app.result.get("_jd")
assert b'"approved": true' in fc.read(JD + "native-install.json")
assert fc.read(EBOOT) == files[EBOOT]
al = fc.read(config.AUTOLOAD_PATH).decode()
assert "hub.elf" in al and "master-control.elf" in al, al
assert sorted(fc.listdir(config.CARDS_DIR)) == ["downloads.json", "files-broker.json", "jdownloader.json", "master-control.json", "omni.json"]
# Run again: Check → Installed apps → uninstall Master Control only.
app.show(2)
wait_for(lambda: str(app.next_btn["state"]) == "normal")
shot("8-check-installed")
app.page_manage()
shot("9-installed-apps")
app._start_job({"mode": "uninstall", "app": "master-control"})
wait_for(lambda: str(app.next_btn["state"]) == "normal", 120)
shot("10-uninstall-one")
assert not fc.exists(config.CARDS_DIR + "master-control.json")
assert fc.exists(config.CARDS_DIR + "omni.json")
assert fc.state["deletes"] == []
# The one button on a second, fresh PS5: Welcome → "Install the full package" → checklist → Undo this install.
oneclick.TIMING.update(poll=0.3, smp_poll=0.2, smp_settle=0.2, smp_settle_missing=0.2, status_timeout=10)
fc2 = new_console(os.path.join(tmp, "console2"))
fc2.start_launcher()
app.ports = {"ftp": fc2.ftp_port, "loader": fc2.loader_port, "websrv": fc2.websrv_port, "launcher": fc2.launcher_port,
             "host": "127.0.0.1"}
app.host.set("127.0.0.1")
app.show(0)
shot("11-one-button")
app.page_oneclick()
wait_for(lambda: not app.oc_running, 180)
shot("12-one-button-done")
assert app.oc_result.get("ok"), app.logbox.get("1.0", "end")
assert fc2.read(EBOOT) == files[EBOOT]
assert app.oc_result.get("jdownloader", {}).get("ok"), app.oc_result.get("jdownloader")   # found on "this computer"
assert fc2.read(config.OMNI_HDR_PREF) == b"1\tauto\n"
app._oc_undo(confirm=False)
wait_for(lambda: app.oc_undo_result is not None, 120)
shot("13-one-button-undo")
assert app.oc_undo_result, app.logbox.get("1.0", "end")
assert fc2.read(EBOOT) == b"OLD-S0B-EBOOT"
assert fc2.state["deletes"] == []
# Customize on a third fresh PS5: untick USB file access and Master Control, then the Install button.
fc3 = new_console(os.path.join(tmp, "console3"))
fc3.start_launcher()
app.ports = {"ftp": fc3.ftp_port, "loader": fc3.loader_port, "websrv": fc3.websrv_port, "launcher": fc3.launcher_port,
             "host": "127.0.0.1"}
app.show(0)
app.page_customize()
app.c_apps["files-broker"].set(False)
app.c_apps["master-control"].set(False)
shot("14-customize")
app.next_btn.invoke()
wait_for(lambda: not app.oc_running, 180)
shot("15-customize-done")
assert app.oc_result.get("ok"), app.logbox.get("1.0", "end")
assert sorted(app.oc_result["installed"]) == ["downloads", "hub", "omni"], sorted(app.oc_result["installed"])
assert app.oc_result.get("jdownloader", {}).get("ok"), app.oc_result.get("jdownloader")
assert not fc3.exists(config.CARDS_DIR + "master-control.json") and not fc3.exists(config.CARDS_DIR + "files-broker.json")
assert fc3.state["deletes"] == []
print("GUI SMOKE PASS")
root.destroy()
fc.stop()
fc2.stop()
fc3.stop()
