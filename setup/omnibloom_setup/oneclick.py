"""The one-button install: wait for the PS5, then install everything in order, telling the user each step.

  1. Get the apps         the release packages (GitHub, or the zips next to Setup)
  2. Find your PS5        waits (listens) until the PS5 answers on FTP (2121) and the payload loader (9021);
                          with no address given it looks around the home network, remembering the last PS5
  3. Check your PS5       the read-only checks (loader, kstuff, ShadowMountPlus), then Setup's lock on the PS5
  4. Bloom Core, Omni, Downloads, USB file access, Master Control
                          each one: install (copy, check, then move into place; old files kept as backups),
                          wait for ShadowMountPlus when Omni's own files changed, then check it file by file
  JDownloader 2           found on this computer (or, with your OK, Setup opens the official download page and waits
                          for you to install it); copied to the PS5 after the apps, when this release allows it
  5. Settings             Omni's HDR setting: Auto when there's none yet; a setting you chose is kept
  6. Start and confirm    Bloom Core (and Master Control) start only now, then Bloom Core is asked to confirm

Every change on the PS5 (each upload and each rename) is recorded, on this computer too. If any step fails, Setup
puts the PS5 back exactly as it was, in reverse order, and says so. "Undo last install" does the same later.
Setup never deletes and never closes an app on the PS5: if Omni is open when its files need replacing, it waits.
"""
import base64
import datetime
import json
import os
import posixpath
import threading
import time

from . import checks, config, installer, jd, ps5, release
from .ports import PortPicker

# Timings (seconds). Tests make them short.
TIMING = {
    "poll": 5.0,             # between port checks while waiting for the PS5
    "scan_poll": 15.0,       # between network sweeps when no address was given
    "remind": 60.0,          # "still waiting" every minute
    "title_wait": 30 * 60,   # how long to wait for Omni to be closed
    "title_poll": 10.0,
    "smp_limit": 180.0,      # ShadowMountPlus remount line
    "smp_poll": 3.0,
    "smp_settle": 20.0,
    "smp_settle_missing": 60.0,
    "lock_wait": 20 * 60,
    "lock_poll": 15.0,
    "status_timeout": 25.0,  # Bloom Core rewrites its status about every 10 s
    "reconnect": 10 * 60,    # waiting for the PS5 to come back before an undo
    "no_websrv_pause": 30.0, # time to close Omni when Setup can't see the app list
    "jd_wait": 30 * 60,      # how long to wait for you to install JDownloader 2 after opening its page
    "jd_poll": 10.0,
}

SMALL = 256 * 1024           # files up to this size are saved before being overwritten (undo puts them back)
UNDONE = ".omnibloom-undone-"

# The order everything goes in. Bloom Core first; Ex-Box 360 and JDownloader 2 are not part of this release's button.
ORDER = (config.HUB_ID, "omni", "downloads", "files-broker", "master-control")
NAMES = {config.HUB_ID: config.HUB_NAME, "omni": "Omni", "downloads": "Downloads", "files-broker": "USB file access",
         "master-control": "Master Control"}
JD_STEP = "jdownloader"
STEPS = (("apps", "Get the Omnibloom apps"), ("find", "Find your PS5"), ("check", "Check your PS5")) + tuple(
    (a, NAMES[a]) for a in ORDER) + ((JD_STEP, "JDownloader 2"), ("settings", "Settings"), ("start", "Start and confirm"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Stopped(Exception):
    """The user stopped the wait, or a wait ran out. Nothing on the PS5 was changed by the step that stopped."""


# -- recording every change, so it can be undone ------------------------------------------------------------
class Recorder:
    """Attached to a Console (`console.recorder`), it is told about every STOR and rename. The list is kept in
    memory and appended to a JSON-lines file on this computer, so an install can be undone even after Setup closed."""

    def __init__(self, path=None, header=None):
        self.ops = []
        self.path = path
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._append(dict(header or {}, kind="run"))

    def _append(self, entry):
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def _add(self, op):
        op["n"] = len(self.ops)
        self.ops.append(op)
        self._append(dict(op, kind="op"))

    def before_store(self, console, path):
        parent, name = posixpath.split(path)
        entry = console.listing(parent).get(name)
        if entry is None:
            return (False, None)
        old = None
        if not path.endswith(".omnibloom-new") and not installer._decoded_on_readback(path) and 0 <= entry["size"] <= SMALL:
            old = console.read(path)
        return (True, old)

    def after_store(self, path, data, token):
        existed, old = token
        if not existed:
            self._add({"op": "created", "path": path, "sha": ps5.sha256(data)})
        elif old is not None:
            self._add({"op": "overwrote", "path": path, "sha": ps5.sha256(data), "old": base64.b64encode(old).decode("ascii")})
        else:
            self._add({"op": "overwrote-unsaved", "path": path, "sha": ps5.sha256(data)})

    def renamed(self, src, dst):
        self._add({"op": "renamed", "src": src, "dst": dst})

    def mark(self, **kw):
        self._append(dict(kw, kind="mark"))


def undo_ops(console, ops, say=lambda m: None, strict=False, on_done=None):
    """Reverse `ops` (newest first). Never deletes: files this run created are renamed aside with UNDONE in the
    name. strict=True (an undo some time later): a file someone changed since is left alone and reported.
    Returns (done, problems)."""
    saved, console.recorder = console.recorder, None
    stamp = _stamp()
    done, problems = 0, []
    try:
        for op in reversed(ops):
            if op.get("undone"):
                continue
            try:
                kind = op["op"]
                if kind == "renamed":
                    src, dst = op["src"], op["dst"]
                    if console.exists(dst) and not console.exists(src):
                        console.makedirs(posixpath.dirname(src))
                        console.rename(dst, src)
                    else:
                        raise IOError("%s isn't where Setup left it" % dst)
                elif kind in ("created", "overwrote-unsaved"):
                    path = op["path"]
                    if console.exists(path):
                        if strict and not installer._decoded_on_readback(path) and ps5.sha256(console.read(path)) != op["sha"]:
                            raise IOError("%s was changed after the install" % path)
                        console.rename(path, installer._free_name(console, path, UNDONE + stamp))
                elif kind == "overwrote":
                    path, old = op["path"], base64.b64decode(op["old"])
                    if strict and console.exists(path) and ps5.sha256(console.read(path)) != op["sha"]:
                        raise IOError("%s was changed after the install" % path)
                    console.store(path, old)
                    if console.read(path) != old:
                        raise IOError("%s didn't read back after putting it back" % path)
                op["undone"] = True
                done += 1
                if on_done:
                    on_done(op)
            except Exception as e:   # keep going: every other change is still put back
                problems.append(str(e))
                say("  Couldn't put back one change: %s" % e)
    finally:
        console.recorder = saved
    return done, problems


# -- runs saved on this computer ------------------------------------------------------------------------------
def runs_dir(host):
    return os.path.join(release.cache_dir(), "runs", host.replace(":", "_"))


def load_run(path):
    """{"header", "ops", "state"} from a run file (later marks win)."""
    header, ops, state = {}, [], "open"
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue    # a torn last line after a crash
            if e.get("kind") == "run":
                header = e
            elif e.get("kind") == "op":
                ops.append(e)
            elif e.get("kind") == "mark":
                if "state" in e:
                    state = e["state"]
                if "undone" in e and 0 <= e["undone"] < len(ops):
                    ops[e["undone"]]["undone"] = True
    return {"header": header, "ops": ops, "state": state, "path": path}


def last_run(host):
    """The newest run on this PS5 that changed something and hasn't been undone, or None."""
    d = runs_dir(host)
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d), reverse=True):
        if name.endswith(".jsonl"):
            run = load_run(os.path.join(d, name))
            if run["state"] not in ("rolled-back", "undone") and any(not o.get("undone") for o in run["ops"]):
                return run
    return None


def _remembered_host():
    try:
        with open(os.path.join(release.cache_dir(), "last-console.json"), encoding="utf-8") as f:
            return json.load(f).get("host")
    except (OSError, ValueError):
        return None


def _remember_host(host):
    try:
        with open(os.path.join(release.cache_dir(), "last-console.json"), "w", encoding="utf-8") as f:
            json.dump({"host": host}, f)
    except OSError:
        pass


# -- the run --------------------------------------------------------------------------------------------------
class OneClick:
    """One button. `report(event)` gets dicts: {"step", "state" (active|ok|fail|skip|undone), "text"} for the
    checklist, or {"text"} for a line of narration (detail lines start with two spaces)."""

    def __init__(self, host=None, ftp_port=None, loader_port=None, websrv_port=None, catalog=None, catalog_loader=None,
                 report=None, progress=None, cancel=None, wait_minutes=0, networks=None, master_control=True,
                 start_master_control=True, autoload_master_control=False, hdr="auto-if-unset", sleep=time.sleep,
                 clock=time.time, record_dir=None, jdownloader=True, jd_folder=None, confirm=None, open_page=None,
                 launcher_port=None):
        self.host = host
        self.ftp_port = ftp_port or config.FTP_PORT
        self.loader_port = loader_port or config.LOADER_PORT
        self.websrv_port = websrv_port
        self.launcher_port = launcher_port
        self.catalog = catalog
        self.catalog_loader = catalog_loader or (lambda log: release.load_catalog(log=log))
        self.report = report or (lambda e: print(e.get("text", ""), flush=True))
        self.progress = progress
        self.cancel = cancel or threading.Event()
        self.wait_seconds = None if not wait_minutes else wait_minutes * 60.0
        self.networks = networks
        self.master_control = master_control
        self.jdownloader = jdownloader
        self.jd_folder = jd_folder
        self.confirm = confirm or (lambda question: False)   # asks the user; no answer = no
        if open_page is None:
            import webbrowser
            open_page = webbrowser.open
        self.open_page = open_page
        self.start_mc = start_master_control
        self.autoload_mc = autoload_master_control
        self.hdr = hdr
        self.sleep = sleep
        self.clock = clock
        self.record_dir = record_dir
        self.result = {"installed": {}, "skipped": {}, "status": [], "rolled_back": False}
        self.lock_token = None

    # -- narration ---------------------------------------------------------------------------------------
    def say(self, text):
        self.report({"text": text})

    def detail(self, text):
        self.report({"text": "  " + text})

    def step(self, key, state, text=None):
        self.report({"step": key, "state": state, "text": text or ""})

    def _wait(self, seconds):
        """Sleep that the Stop button can cut short."""
        stopped = self.cancel.is_set()
        if not stopped:
            if self.sleep is time.sleep:
                stopped = self.cancel.wait(seconds)
            else:
                self.sleep(seconds)
        if stopped:
            raise Stopped("You stopped Setup. Nothing on your PS5 was changed by this step.")

    # -- 1. apps ---------------------------------------------------------------------------------------
    def get_apps(self):
        self.step("apps", "active", "Getting the Omnibloom apps…")
        if self.catalog is None:
            self.catalog = self.catalog_loader(self.detail)
        names = ", ".join("%s %s" % (NAMES.get(a, a), self.catalog.apps[a]["version"]) for a in ORDER if self.catalog.has(a))
        self.step("apps", "ok", "Got the apps: %s." % names)

    # -- JDownloader 2 on this computer (before the PS5, so you can install it while the PS5 starts) -------------
    def find_jdownloader(self):
        """Sets self.jd_folder to a usable JDownloader 2 install, or leaves it None (and says why)."""
        if not self.jdownloader:
            self.step(JD_STEP, "skip", "JDownloader 2: left out.")
            return None
        held = not config.jd_enabled()
        self.step(JD_STEP, "active", "Looking for JDownloader 2 on this computer…")
        folder = self._jd_pick()
        if not folder and not held:
            folder = self._jd_get_from_site()
        if folder:
            try:
                info = jd.summary(folder)
            except ValueError as e:
                self.step(JD_STEP, "fail", "JDownloader 2 at %s can't be used: %s" % (folder, e))
                self.jd_folder = None
                return None
            self.jd_folder = folder
            self.detail("Found JDownloader 2 at %s (%d files, %.0f MB%s)." % (
                folder, info["files"], info["megabytes"], (", revision %d" % info["revision"]) if info["revision"] else ""))
            if info["revision_note"]:
                self.detail(info["revision_note"])
        if held:
            self.jd_folder = None
            # Held back in this release (audit JD-03): one calm line, no questions, nothing to install.
            self.step(JD_STEP, "skip", ("Found your JDownloader 2. " if folder else "") +
                      "JDownloader 2 on the PS5 comes in a later update; yt-dlp downloads are built in and work now.")
            self.detail(config.JD_HELD_REASON)
            return None
        if not folder:
            self.step(JD_STEP, "skip", "JDownloader 2: not set up (it isn't on this computer). yt-dlp downloads work without it.")
            return None
        self.step(JD_STEP, "active", "JDownloader 2 found; it goes on the PS5 after the apps.")
        return folder

    def _jd_pick(self):
        if self.jd_folder:
            if jd.is_jd_folder(self.jd_folder):
                return self.jd_folder
            self.detail("%s doesn't have JDownloader.jar and Core.jar; looking in the usual places instead." % self.jd_folder)
            self.jd_folder = None
        found = jd.detect()
        if len(found) > 1:
            self.detail("Found JDownloader 2 in more than one place; using %s." % found[0])
        if found:
            return found[0]
        half = jd.partial_folders()
        if half:
            self.say("JDownloader 2 at %s hasn't finished setting itself up (Core.jar is missing). Open it once and "
                     "let it finish updating." % half[0])
        return None

    def _jd_get_from_site(self):
        """Not on this computer: with the user's OK, open the official download page and listen for the install."""
        question = ("JDownloader 2 isn't on this computer. Open the official download page (%s) so you can install it? "
                    "Setup waits and carries on as soon as it's installed." % config.JD_OFFICIAL_URL)
        if not self.confirm(question):
            return None
        self.say("Opening %s. JDownloader's own installers are linked there (they are hosted on mega.nz, and the page "
                 "lists a SHA-256 for each one: you can compare it before running the installer). Install JDownloader 2 "
                 "and open it once so it finishes downloading its parts. Setup is waiting for it." % config.JD_OFFICIAL_URL)
        try:
            self.open_page(config.JD_OFFICIAL_URL)
        except Exception:
            self.say("Couldn't open the browser; please open %s yourself." % config.JD_OFFICIAL_URL)
        start = self.clock()
        next_remind = start + TIMING["remind"]
        while self.clock() - start < TIMING["jd_wait"]:
            self._wait(TIMING["jd_poll"])
            folder = self._jd_pick()
            if folder:
                self.say("JDownloader 2 is installed. Carrying on.")
                return folder
            if self.clock() >= next_remind:
                self.say("Still waiting for JDownloader 2 to be installed (%d min so far)…" % ((self.clock() - start) // 60))
                next_remind = self.clock() + TIMING["remind"]
        self.say("JDownloader 2 didn't appear within %d minutes; carrying on without it. Run Setup again after "
                 "installing it." % (TIMING["jd_wait"] // 60))
        return None

    def setup_jdownloader(self, console):
        """After the apps: the engine + the user's JDownloader 2 + the check on the PS5. A failure leaves it off and
        doesn't undo anything else (yt-dlp downloads keep working)."""
        if not self.jd_folder:
            return
        if "downloads" not in self.result["installed"]:
            self.step(JD_STEP, "skip", "JDownloader 2 works through Downloads, which wasn't installed.")
            return
        self.step(JD_STEP, "active", "Setting up JDownloader 2 on the PS5 (the check on the PS5 can take a few minutes)…")
        for line in jd.credit_lines():
            self.detail(line)
        try:
            release.load_engine(self.catalog, log=self.detail)
            out = jd.setup_jdownloader(console, self.catalog, self.jd_folder, log=self.detail, progress=self.progress,
                                       sleep=self.sleep)
            self.result["jdownloader"] = {"ok": True, "install_id": out["acceptance"]["install_id"]}
            self.step(JD_STEP, "ok", "JDownloader 2 is on. Use it from Media downloads in Omni.")
        except Exception as e:
            self.result["jdownloader"] = {"ok": False, "why": str(e)}
            self.step(JD_STEP, "fail", "JDownloader 2 stays off: %s Everything else is installed; yt-dlp downloads work."
                      % (str(e).rstrip(".") + "."))

    # -- 2. find (listen for the PS5) --------------------------------------------------------------------
    def find_console(self):
        self.step("find", "active", "Waiting for your PS5…")
        self.say("Turn your PS5 on and run your jailbreak, so its FTP server (port %d) and payload loader (port %d) "
                 "are running. Setup keeps checking and carries on by itself as soon as both answer."
                 % (self.ftp_port, self.loader_port))
        start = self.clock()
        next_remind = start + TIMING["remind"]
        told_ftp_only = None
        while True:
            hosts = [self.host] if self.host else self._candidates()
            for h in hosts:
                ftp_up = ps5.port_open(h, self.ftp_port, 1.5)
                if not ftp_up:
                    continue
                if not ps5.port_open(h, self.loader_port, 1.5):
                    if told_ftp_only != h:
                        self.say("Your PS5 at %s answered on FTP (port %d). Waiting for its payload loader on port %d "
                                 "(run your jailbreak's loader)…" % (h, self.ftp_port, self.loader_port))
                        told_ftp_only = h
                    continue
                try:   # the ports are open: make sure FTP really lets us in
                    ps5.Console(h, ftp_port=self.ftp_port, timeout=15).connect().close()
                except Exception as e:
                    self.detail("%s's FTP isn't ready yet (%s)." % (h, e))
                    continue
                self.host = h
                _remember_host(h)
                waited = self.clock() - start
                self.step("find", "ok", "Found your PS5 at %s%s." % (h, (" after %d min" % (waited // 60)) if waited >= 60 else ""))
                return h
            now = self.clock()
            if self.wait_seconds is not None and now - start >= self.wait_seconds:
                raise Stopped("Your PS5 didn't answer within %d minutes. Check it's on, jailbroken and on the same "
                              "network as this computer, then press the button again." % (self.wait_seconds // 60))
            if now >= next_remind:
                self.say("Still waiting for your PS5 (%d min so far)…" % ((now - start) // 60))
                next_remind = now + TIMING["remind"]
            self._wait(TIMING["poll"] if self.host else TIMING["scan_poll"])

    def _candidates(self):
        found = []
        remembered = _remembered_host()
        if remembered and ps5.port_open(remembered, self.ftp_port, 1.5):
            return [remembered]
        for f in ps5.scan(self.networks, ftp_port=self.ftp_port, loader_port=self.loader_port):
            found.append(f["host"])
        if len(found) > 1:
            self.say("Found more than one PS5 (%s); using %s. To pick another, type its address." % (", ".join(found), found[0]))
            return found[:1]
        return found

    def connect(self):
        return ps5.Console(self.host, ftp_port=self.ftp_port, loader_port=self.loader_port, websrv_port=self.websrv_port,
                           launcher_port=self.launcher_port).connect()

    # -- 3. check + lock ----------------------------------------------------------------------------------
    def check(self, console):
        self.step("check", "active", "Checking your PS5 (about 20 seconds; nothing is changed)…")
        items, summary = checks.run_checks(console, sleep=self.sleep)
        for it in items:
            mark = {"ok": "OK", "warn": "Note", "bad": "Problem", "info": "Info"}[it["status"]]
            self.detail("%s: %s: %s" % (mark, it["label"], it["detail"]))
        if not summary["can_install"]:
            self.step("check", "fail", "Your PS5 isn't ready yet; nothing was changed.")
            raise Stopped("Fix the problem above on your PS5, then press the button again.")
        self.take_lock(console)
        self.step("check", "ok", "Your PS5 is ready.")
        return summary

    def take_lock(self, console):
        token = "%s-%s" % (_stamp(), os.urandom(4).hex())
        start = self.clock()
        told = False
        while True:
            held = self._read_lock(console)
            if not held or held.get("owner") == token or held.get("expires", 0) < time.time():
                console.makedirs(config.HUB_DIR)
                console.store(config.SETUP_LOCK, json.dumps({"owner": token, "since": _now(),
                                                            "expires": time.time() + config.SETUP_LOCK_MINUTES * 60}).encode())
                if (self._read_lock(console) or {}).get("owner") == token:
                    self.lock_token = token
                    return
            if not told:
                self.say("Another copy of Omnibloom Setup is working on this PS5. Waiting for it to finish…")
                told = True
            if self.clock() - start > TIMING["lock_wait"]:
                raise Stopped("Another copy of Setup kept this PS5 busy. Close it, then press the button again.")
            self._wait(TIMING["lock_poll"])

    def refresh_lock(self, console):
        if self.lock_token:
            saved, console.recorder = console.recorder, None
            try:
                console.store(config.SETUP_LOCK, json.dumps({"owner": self.lock_token, "since": _now(),
                                                            "expires": time.time() + config.SETUP_LOCK_MINUTES * 60}).encode())
            finally:
                console.recorder = saved

    def release_lock(self, console):
        if self.lock_token and (self._read_lock(console) or {}).get("owner") == self.lock_token:
            saved, console.recorder = console.recorder, None
            try:
                console.store(config.SETUP_LOCK, json.dumps({"owner": None, "released": _now()}).encode())
            finally:
                console.recorder = saved
        self.lock_token = None

    @staticmethod
    def _read_lock(console):
        try:
            value = json.loads(console.read_text(config.SETUP_LOCK, default="") or "null")
        except ValueError:
            return None
        return value if isinstance(value, dict) and value.get("owner") else None

    # -- 4. each app --------------------------------------------------------------------------------------
    def plan(self, console):
        installed = installer.installed_apps(console)
        order = []
        for app_id in ORDER:
            if app_id == "master-control" and not self.master_control:
                self.result["skipped"][app_id] = "you left it out"
                continue
            if not self.catalog.has(app_id):
                self.result["skipped"][app_id] = "not in this release"
                continue
            order.append(app_id)
        for app_id in sorted(installer.pending_installs(console)):   # finish an interrupted install too
            if app_id not in order and self.catalog.has(app_id):
                order.append(app_id)
        lines = []
        for app_id in order:
            have = installed.get(app_id)
            new = self.catalog.apps[app_id]["version"]
            name = NAMES.get(app_id, self.catalog.apps[app_id]["name"])
            if not have:
                lines.append("%s %s (new)" % (name, new))
            elif have["version"] != new:
                lines.append("%s %s → %s (update)" % (name, have["version"], new))
            else:
                lines.append("%s %s (check and repair)" % (name, new))
        self.say("Here's the plan, one at a time: " + "; ".join(lines) + ".")
        for app_id, why in self.result["skipped"].items():
            self.step(app_id, "skip", "%s: skipped (%s)." % (NAMES.get(app_id, app_id), why))
        return order

    def title_changes(self, console, app_id):
        """True when installing `app_id` replaces anything in Omni's title folder (which needs Omni closed)."""
        rows = [r for r in self.catalog.files_for(app_id) if r["dest"].startswith(config.TITLE_DIR)]
        if not rows:
            return False
        prev = {f["dest"]: f.get("sha256") for f in (installer.read_receipt(console, app_id) or {}).get("files", [])}
        listing = {}
        for r in rows:
            parent, name = posixpath.split(r["dest"])
            if parent not in listing:
                listing[parent] = console.listing(parent)
            if prev.get(r["dest"]) != r["sha256"] or name not in listing[parent]:
                return True
        return False

    def wait_title_closed(self, console):
        procs = console.processes()
        if procs is None:
            self.say("Setup can't see which apps are open on your PS5 (websrv isn't running), so make sure Omni is "
                     "closed now. Continuing in %d seconds…" % TIMING["no_websrv_pause"])
            self._wait(TIMING["no_websrv_pause"])
            return
        if config.TITLE_PROCESS not in procs:
            return
        self.say("An app is open on your PS5. Please close it (press the PS button, then close Omni or the game) so Setup "
                 "can replace Omni's files safely. Setup waits; it never closes apps for you.")
        start = self.clock()
        while config.TITLE_PROCESS in (console.processes() or []):
            if self.clock() - start > TIMING["title_wait"]:
                raise Stopped("The app on your PS5 stayed open, so Omni wasn't replaced.")
            self._wait(TIMING["title_poll"])
        self.say("Thanks, it's closed. Carrying on.")

    def wait_smp(self, console, offset):
        """Wait for ShadowMountPlus to log that it remounted Omni's title, then let it settle."""
        self.detail("Waiting for ShadowMountPlus to pick up Omni's files (up to %d seconds)…" % TIMING["smp_limit"])
        start = self.clock()
        while self.clock() - start < TIMING["smp_limit"]:
            self._wait(TIMING["smp_poll"])
            tail = console.read_from(config.SMP_LOG, offset).decode("utf-8", "replace")
            if any(config.TITLE_ID in ln and any(w in ln for w in config.SMP_MOUNT_WORDS) for ln in tail.splitlines()):
                self.detail("ShadowMountPlus picked up Omni. Letting it settle for %d seconds…" % TIMING["smp_settle"])
                self._wait(TIMING["smp_settle"])
                return True
        self.detail("ShadowMountPlus didn't log a remount; giving it %d more seconds to be safe." % TIMING["smp_settle_missing"])
        self._wait(TIMING["smp_settle_missing"])
        return False

    def install_one(self, console, app_id, picker):
        name = NAMES.get(app_id, self.catalog.apps[app_id]["name"])
        version = self.catalog.apps[app_id]["version"]
        self.step(app_id, "active", "Installing %s %s…" % (name, version))
        title = self.title_changes(console, app_id)
        if title:
            self.wait_title_closed(console)
        offset = console.size(config.SMP_LOG) or 0
        before = len(console.recorder.ops) if console.recorder else 0
        receipt = installer.install_app(console, self.catalog, app_id, picker,
                                        autoload_opt=(app_id == "master-control" and self.autoload_mc),
                                        start=False, log=self.detail, progress=self.progress)
        changed = console.recorder.ops[before:] if console.recorder else []
        if title and any(op["op"] == "renamed" and op["dst"].startswith(config.TITLE_DIR) for op in changed):
            self.wait_smp(console, offset)
        self.detail("Checking %s…" % name)
        problems = installer.verify_app(console, self.catalog, app_id, progress=self.progress)
        if problems:
            raise IOError("%s didn't check out: %s" % (name, "; ".join(problems[:4])))
        self.result["installed"][app_id] = receipt
        self.step(app_id, "ok", "%s %s is installed and checked." % (name, version))
        self.refresh_lock(console)
        return receipt

    # -- 5. settings ----------------------------------------------------------------------------------------
    def settings(self, console):
        self.step("settings", "active", "Settings…")
        if "omni" not in self.result["installed"] or self.hdr == "keep":
            self.step("settings", "ok" if self.hdr == "keep" else "skip", "Settings: left as they are.")
            return
        cur = console.read_text(config.OMNI_HDR_PREF, default=None)
        parts = (cur or "").split()
        mode = parts[-1] if parts else None
        if cur is not None and self.hdr != "auto":
            self.step("settings", "ok", "Kept your HDR setting (%s)." % (mode or "as it was"))
            return
        if mode == "auto":
            self.step("settings", "ok", "HDR is already set to Auto.")
            return
        rev = 1
        try:
            rev = int(parts[0]) + 1 if parts else 1
        except ValueError:
            pass
        data = ("%d\t%s\n" % (rev, "auto")).encode()
        console.makedirs(posixpath.dirname(config.OMNI_HDR_PREF))
        console.store(config.OMNI_HDR_PREF, data)
        if console.read(config.OMNI_HDR_PREF) != data:
            raise IOError("Omni's HDR setting didn't save correctly.")
        self.step("settings", "ok", "Set Omni's HDR to Auto (HDR turns on for HDR videos only). Change it any time in Omni.")

    # -- 6. start and confirm --------------------------------------------------------------------------------
    def start_and_confirm(self, console):
        self.step("start", "active", "Starting…")
        since = int(time.time()) + 1
        hub = self.result["installed"].get(config.HUB_ID)
        if hub:
            self._start(console, config.HUB_ID, "%s is running and starts with your PS5." % config.HUB_NAME)
        mc = self.result["installed"].get("master-control")
        if mc and self.start_mc:
            procs = [p.lower() for p in (console.processes() or [])]
            other = [n for n in config.REPLACED_CONTROLLER_PAYLOADS if any(n in p for p in procs)]
            if other:
                self.say("Master Control wasn't started because %s is running (two controller payloads fight over "
                         "controllers). Restart the PS5 without it, or start Master Control from Omni." % other[0])
            else:
                self._start(console, "master-control", "Master Control is running.")
        want = [a for a, r in self.result["installed"].items() if installer.writes_card(a, r.get("card"))]
        if hub and want:
            self.detail("Asking %s to confirm every app (it reports about every 10 seconds)…" % config.HUB_NAME)
            status = installer.read_status(console, since=since, want=want, timeout=TIMING["status_timeout"],
                                           sleep=self.sleep, clock=self.clock)
            issues = installer.explain_status(status, app_ids=set(want))
            self.result["status"] = issues
            for line in issues:
                self.detail(line)
            if status and not issues:
                self.step("start", "ok", "%s confirmed every app." % config.HUB_NAME)
                return
            self.step("start", "ok", "Started. %s hasn't confirmed everything yet; it keeps checking on its own." % config.HUB_NAME)
            return
        self.step("start", "ok", "Started.")

    def _start(self, console, app_id, said):
        app = self.catalog.apps[app_id]
        elf = (app["card"].get("launch") or {}).get("elf")
        row = next((r for r in self.catalog.files_for(app_id) if r["dest"] == elf), None)
        if not row:
            return
        console.send_payload(self.catalog.data(app_id, row))
        self.detail(said)

    # -- undo -------------------------------------------------------------------------------------------------
    def rollback(self, console, why):
        """Put everything this run changed back, newest first."""
        self.say("Something went wrong: %s" % why)
        self.say("Putting your PS5 back exactly as it was before Setup started…")
        try:
            console.ftp.voidcmd("NOOP")
        except Exception:
            console = self._reconnect(console)
        if console is None:
            self.say("Setup can't reach your PS5 to put things back. The list of changes is saved on this computer: "
                     "when your PS5 is back, use Undo last install.")
            return False
        rec = console.recorder
        touched_title = any(op["op"] == "renamed" and (op["dst"].startswith(config.TITLE_DIR) or op["src"].startswith(config.TITLE_DIR))
                            for op in rec.ops if not op.get("undone"))
        if touched_title:
            self.wait_title_closed(console)
        offset = console.size(config.SMP_LOG) or 0
        done, problems = undo_ops(console, rec.ops, say=self.say, on_done=lambda op: rec.mark(undone=op["n"]))
        if touched_title:
            self.wait_smp(console, offset)
        for app_id in self.result["installed"]:
            self.step(app_id, "undone", "%s: put back as it was." % NAMES.get(app_id, app_id))
        self.result["rolled_back"] = not problems
        if problems:
            rec.mark(state="rollback-incomplete")
            self.say("%d change(s) were put back, but %d couldn't be. Press Undo last install to try again, or use "
                     "Repair." % (done, len(problems)))
            return False
        rec.mark(state="rolled-back")
        self.say("Your PS5 is back the way it was (%d change%s undone). Nothing was deleted." % (done, "" if done == 1 else "s"))
        return True

    def _reconnect(self, console):
        try:
            console.close()
        except Exception:
            pass
        self.say("Lost the connection to your PS5. Waiting for it to come back (up to %d minutes)…" % (TIMING["reconnect"] // 60))
        start = self.clock()
        while self.clock() - start < TIMING["reconnect"]:
            try:
                fresh = self.connect()
                fresh.recorder = console.recorder
                return fresh
            except Exception:
                self.sleep(TIMING["poll"])
        return None

    # -- the button -------------------------------------------------------------------------------------------
    def run(self):
        """Returns the result dict. result["ok"] says whether everything was installed."""
        self.result["ok"] = False
        try:
            self.say("Omnibloom one-button install. Setup will tell you each step as it goes.")
            self.get_apps()
            self.find_jdownloader()
            self.find_console()
        except Stopped as e:
            self.say(str(e))
            return self.result
        except (release.ReleaseError, OSError) as e:
            self.step("apps", "fail", "Couldn't get the Omnibloom apps: %s" % e)
            self.say("Check this computer's internet connection, or put the console package zips next to Setup.")
            return self.result
        try:
            console = self.connect()
        except OSError as e:
            self.say("Your PS5 stopped answering (%s). Press the button again to retry; nothing was changed." % e)
            return self.result
        recorder = None
        try:
            try:
                self.check(console)
                order = self.plan(console)
            except Stopped as e:
                self.say(str(e))
                return self.result
            except Exception as e:   # nothing has been changed yet (the checks only read)
                self.step("check", "fail", "Couldn't check your PS5: %s" % e)
                self.say("Nothing was changed. Check the PS5 is still on, then press the button again.")
                return self.result
            record_dir = self.record_dir or runs_dir(self.host)
            run_path = os.path.join(record_dir, "%s.jsonl" % _stamp())
            recorder = Recorder(run_path, {"host": self.host, "started": _now(), "setup_version": config.SETUP_VERSION,
                                           "apps": {a: self.catalog.apps[a]["version"] for a in order}})
            console.recorder = recorder
            self.result["run_file"] = run_path
            picker = PortPicker(console)
            current = None
            try:
                for current in order:
                    self.install_one(console, current, picker)
                current = "settings"
                self.settings(console)
            except Exception as e:   # anything at all: put the PS5 back
                if current:
                    self.step(current, "fail", "%s didn't finish." % NAMES.get(current, current))
                console.recorder = recorder
                if self.rollback(console, str(e)):
                    self.say("Nothing was started. Fix the problem, then press the button again.")
                return self.result
            recorder.mark(state="committed")
            console.recorder = None
            self.setup_jdownloader(console)
            try:
                self.start_and_confirm(console)
            except Exception as e:   # the apps are installed and checked; starting is retried at the next boot
                self.step("start", "fail", "Couldn't start everything: %s. Everything is installed; restart the PS5 "
                                           "and run your jailbreak to start it." % e)
            self.result["ok"] = True
            self.say("All done. Open Omni from your PS5's Home screen (the tile is called Omni; it can take up to 15 "
                     "seconds to appear). Run Setup again any time to update, repair or undo.")
            return self.result
        finally:
            try:
                console.recorder = None
                self.release_lock(console)
            except Exception:
                pass
            console.close()


def undo_last(host, ftp_port=None, loader_port=None, websrv_port=None, report=None, run_path=None, sleep=time.sleep):
    """Undo the newest one-button install on `host` (or the run file given). Returns True when everything went back."""
    oc = OneClick(host=host, ftp_port=ftp_port, loader_port=loader_port, websrv_port=websrv_port, report=report, sleep=sleep)
    run = load_run(run_path) if run_path else last_run(host)
    if not run:
        oc.say("There's no install by this Setup to undo on %s." % host)
        return False
    apps = run["header"].get("apps") or {}
    names = ", ".join("%s %s" % (NAMES.get(a, a), apps[a]) for a in sorted(apps, key=lambda a: (ORDER + (a,)).index(a)))
    oc.say("Undoing the install from %s (%s)…" % (run["header"].get("started", "?"), names))
    console = oc.connect()
    try:
        oc.take_lock(console)
        rec = Recorder()
        rec.path = run["path"]
        rec.ops = run["ops"]
        touched_title = any(op["op"] == "renamed" and (op["dst"].startswith(config.TITLE_DIR) or op["src"].startswith(config.TITLE_DIR))
                            for op in rec.ops if not op.get("undone"))
        if touched_title:
            oc.wait_title_closed(console)
        offset = console.size(config.SMP_LOG) or 0
        done, problems = undo_ops(console, rec.ops, say=oc.say, strict=True, on_done=lambda op: rec.mark(undone=op["n"]))
        if touched_title:
            oc.wait_smp(console, offset)
        if problems:
            rec.mark(state="undo-incomplete")
            oc.say("%d change(s) were undone; %d were left alone because they changed since (see above). Use Repair or "
                   "Uninstall for those apps." % (done, len(problems)))
            return False
        rec.mark(state="undone")
        for a in apps:
            oc.step(a, "undone", "%s: put back as it was." % NAMES.get(a, a))
        oc.say("Undone: your PS5 is back the way it was before that install (%d changes). Apps that were started keep "
               "running until the PS5 restarts." % done)
        return True
    finally:
        try:
            oc.release_lock(console)
        except Exception:
            pass
        console.close()

