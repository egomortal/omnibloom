"""Read-only checks of the console before installing. Nothing here writes anything."""
import time

from . import config
from .ps5 import port_open

OK, WARN, BAD, INFO = "ok", "warn", "bad", "info"


def _item(key, label, status, detail):
    return {"id": key, "label": label, "status": status, "detail": detail}


def autoload_entries(console):
    text = console.read_text(config.AUTOLOAD_PATH, default=None)
    if text is None:
        return None
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def shadowmount_active(console, wait=18.0, sleep=time.sleep):
    """ShadowMountPlus writes to its log every 15 s while it runs. Watch it grow."""
    log = "/data/shadowmount/debug.log"
    first = console.size(log)
    if first is None:
        return None
    sleep(wait)
    second = console.size(log)
    return second is not None and second != first


def run_checks(console, quick=False, sleep=time.sleep):
    """Returns (items, summary). summary = {"can_install": bool, "installed_version": str|None,
    "autoload": [...]|None}."""
    items = []
    items.append(_item("ftp", "File transfer (FTP)", OK, "Connected to the PS5's FTP server."))

    loader = console.loader_open()
    items.append(_item("loader", "Payload loader", OK if loader else BAD,
                       "The loader is ready." if loader else
                       "Nothing is listening on port %d. Run your jailbreak again so the ELF loader starts, then press Check again." % config.LOADER_PORT))

    entries = autoload_entries(console)
    procs = console.processes()
    procs_l = [p.lower() for p in procs] if procs is not None else None
    needs_ok = True
    for key, (name, needles) in config.REQUIREMENTS.items():
        in_autoload = entries is not None and any(any(n in e.lower() for n in needles) for e in entries)
        running = procs_l is not None and any(any(n in p for n in needles) for p in procs_l)
        if key == "shadowmount" and not running and not quick:
            active = shadowmount_active(console, sleep=sleep)
            running = bool(active)
        if running:
            items.append(_item(key, name, OK, name + " is running."))
        elif in_autoload:
            items.append(_item(key, name, WARN,
                               name + " is set to start with your PS5 but doesn't look like it's running right now. "
                               "If Omni's tile won't open after setup, restart the PS5 or load " + name + " again."))
        else:
            needs_ok = False
            items.append(_item(key, name, BAD,
                               "Omnibloom needs " + name + ". Add it to your payload loader (Payload Manager autoload) "
                               "or load it now, then press Check again."))

    items.append(_item("firmware", "Firmware", INFO,
                       "Omnibloom is tested on firmware %s. Other firmware may work but isn't tested." % config.TESTED_FIRMWARE))

    from .installer import installed_apps
    installed = installed_apps(console)
    if installed:
        names = ", ".join("%s %s" % (r["name"], r["version"]) for r in installed.values())
        items.append(_item("installed", "Already installed", INFO, "On this PS5: %s." % names))

    can = loader and needs_ok
    return items, {"can_install": can, "installed": installed, "autoload": entries}
