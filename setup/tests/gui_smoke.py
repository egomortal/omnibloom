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
from omnibloom_setup import config, gui, release  # noqa: E402

shots = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "shots")
os.makedirs(shots, exist_ok=True)
tmp = tempfile.mkdtemp(prefix="omnibloom-gui-")
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
assert sorted(fc.listdir(config.CARDS_DIR)) == ["downloads.json", "files-broker.json", "master-control.json", "omni.json"]
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
print("GUI SMOKE PASS")
root.destroy()
fc.stop()
