# SPDX-License-Identifier: GPL-3.0-or-later
"""JDownloader 2 on the PS5: our engine + the user's own copy of JDownloader 2.

What goes where (all under /data/omni-downloader/jdownloader/, the layout Omni's downloads worker expects):
- The engine, from the `omnibloom-jd-engine-<ver>.zip` release asset (installed as app "jdownloader"):
  java-worker.elf (our native entry, GPL-3.0-or-later) linked with a Java 25 runtime built from
  mateo-cogeanu/ps5-java25-homebrew (OpenJDK parts GPLv2 + Classpath Exception), the runtime image under
  native/java25/, our bridge classes under runtime/classes/, and the notices under notices/.
- JDownloader 2 itself is the user's own copy (it is partly closed-source, so we never ship it): Setup
  finds it on this computer and copies the files the engine loads into runtime/.
- assets-manifest.json pins every runtime/ file; native-install.json switches the engine on. The
  downloads worker refuses to start Java unless native-install.json carries a passed console check.

Order, so the worker never starts Java against half-copied files:
  1. switch off (park native-install.json)   2. engine files   3. user's files + manifest
  4. check on the console (providers, then a short JDownloader start)   5. switch on (write native-install.json).
Nothing is ever deleted: old files go to setup-backup/<time>/, outside the folders the engine checks.
"""
import datetime
import hashlib
import json
import os
import posixpath
import secrets
import sys
import time
import urllib.parse
import urllib.request

from . import config

ASSETS_SCHEMA = "omni-jd-assets-manifest/v2"
INSTALL_SCHEMA = "omni-jd-native-install/v1"
IMAGE_SCHEMA = "omni-java-native-image/v1"
ACCEPTANCE_SCHEMA = "omnibloom-jd-acceptance/v1"
ROOT = config.JD_CONSOLE_ROOT
ASSETS_MANIFEST = "assets-manifest.json"            # relative to ROOT (same name the console already uses)
IMAGE_MANIFEST = "native/image-manifest.json"
APPROVAL = ROOT + "native-install.json"
REQUIRED = ("JDownloader.jar", "Core.jar")
# What the downloads worker insists on before it starts Java (jd_lifecycle.CRITICAL).
CRITICAL_RUNTIME = ("runtime/Core.jar", "runtime/JDownloader.jar", "runtime/classes/OmniJDownloaderBridge.class",
                    "runtime/classes/org/jdownloader/api/myjdownloader/MyJDownloaderController.class")
# Folders the console engine loads from a JDownloader 2 install.
INCLUDE_DIRS = ("libs", "extensions", "jd", "translations", "themes", "licenses")
INCLUDE_FILES = ("build.json",)
# Never copied: settings, logs, downloads, updater state, desktop launchers and native libraries.
SKIP_DIRS = {"cfg", "logs", "tmp", "update", "updates", "backup", "captchas", "downloads", "jre", "tools", "cache", "home"}
SKIP_EXT = {".exe", ".dll", ".so", ".dylib", ".jnilib", ".app", ".lnk", ".log", ".bak", ".tmp"}
MAX_FILES, MAX_TOTAL, MAX_ONE = 5000, 512 * 1024 * 1024, 128 * 1024 * 1024
STARTUP_SECONDS = 600            # the engine's own VM-startup budget (cold starts are slow)
PROVIDER_STEPS = ("headless_configuration", "management_native", "awt_toolkit_init", "image_native_raster",
                  "font_native_init", "png_memory_roundtrip")
ACTIVE_STATES = ("claimed", "launching", "uncertain", "ready", "closing")


class CheckFailed(Exception):
    """The console check didn't pass; JDownloader 2 stays off. str() is a plain-language reason."""


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode("utf-8")


# -- finding JDownloader 2 on this computer -----------------------------------------------
def candidate_folders():
    home = os.path.expanduser("~")
    c = []
    if sys.platform.startswith("win"):
        for var in ("LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)", "USERPROFILE"):
            base = os.environ.get(var)
            if base:
                c += [os.path.join(base, "JDownloader 2.0"), os.path.join(base, "JDownloader 2"), os.path.join(base, "JDownloader")]
    elif sys.platform == "darwin":
        for base in ("/Applications", os.path.join(home, "Applications")):
            c += [os.path.join(base, "JDownloader 2.0", "JDownloader2.app", "Contents", "Java"),
                  os.path.join(base, "JDownloader2.app", "Contents", "Java"),
                  os.path.join(base, "JDownloader 2.0")]
    else:
        c += [os.path.join(home, "jd2"), os.path.join(home, "JDownloader 2.0"), os.path.join(home, "JDownloader2"),
              os.path.join(home, ".jd2"), "/opt/jd2", "/opt/JDownloader", "/opt/jdownloader2"]
    return c


def is_jd_folder(path):
    return bool(path) and all(os.path.isfile(os.path.join(path, n)) for n in REQUIRED)


def detect():
    """Folders that look like a JDownloader 2 install."""
    seen, found = set(), []
    for p in candidate_folders():
        real = os.path.realpath(p)
        if real not in seen and is_jd_folder(p):
            seen.add(real)
            found.append(p)
    return found


def collect(folder):
    """[(relative_path, absolute_path, bytes)] of the files the console engine needs."""
    if not is_jd_folder(folder):
        raise ValueError("That folder doesn't have JDownloader.jar and Core.jar. Pick the folder JDownloader 2 is installed in.")
    files = [(n, os.path.join(folder, n), os.path.getsize(os.path.join(folder, n))) for n in REQUIRED]
    for n in INCLUDE_FILES:
        p = os.path.join(folder, n)
        if os.path.isfile(p) and not os.path.islink(p):
            files.append((n, p, os.path.getsize(p)))
    for top in INCLUDE_DIRS:
        root = os.path.join(folder, top)
        if not os.path.isdir(root) or os.path.islink(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d)))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or os.path.splitext(name)[1].lower() in SKIP_EXT:
                    continue
                rel = os.path.relpath(full, folder).replace(os.sep, "/")
                files.append((rel, full, os.path.getsize(full)))
    total = sum(f[2] for f in files)
    if len(files) > MAX_FILES or total > MAX_TOTAL or any(f[2] > MAX_ONE for f in files):
        raise ValueError("This JDownloader folder is larger than the PS5 engine allows (%d files, %d MB)." % (len(files), total >> 20))
    folded = {}
    for rel, _, _ in files:   # the console checks names case-insensitively
        if rel.casefold() in folded:
            raise ValueError("JDownloader has two files whose names differ only in capitals: %s, %s" % (folded[rel.casefold()], rel))
        folded[rel.casefold()] = rel
    return files


def revision(folder):
    """JDownloaderRevision from the user's build.json, or None."""
    try:
        with open(os.path.join(folder, "build.json"), encoding="utf-8") as f:
            value = json.load(f).get("JDownloaderRevision")
        return int(value) if value is not None else None
    except (OSError, ValueError, TypeError):
        return None


def summary(folder):
    files = collect(folder)
    rev = revision(folder)
    return {"folder": folder, "files": len(files), "megabytes": round(sum(f[2] for f in files) / 1048576, 1),
            "revision": rev, "tested_revision": config.JD_TESTED_REVISION,
            "revision_note": None if rev in (None, config.JD_TESTED_REVISION) else
            ("Your JDownloader 2 is revision %d; Omnibloom was tested with %d. The check on the PS5 will tell "
             "whether this one works." % (rev, config.JD_TESTED_REVISION))}


def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(files, extra_rows=()):
    """The pinned file list the console engine checks before it starts Java (jd_lifecycle._verify_assets)."""
    rows = [{"path": "runtime/" + rel, "bytes": size, "sha256": _hash(full)} for rel, full, size in files]
    rows += [dict(r) for r in extra_rows]
    rows.sort(key=lambda r: r["path"])
    names = [r["path"] for r in rows]
    if len(set(n.casefold() for n in names)) != len(names):
        raise ValueError("Two runtime files would share a name.")
    missing = [c for c in CRITICAL_RUNTIME if c not in names]
    if missing:
        raise ValueError("The JDownloader 2 file list would be missing %s." % ", ".join(missing))
    return {"schema": ASSETS_SCHEMA, "host_jre_included": False, "files": rows,
            "file_count": len(rows), "asset_bytes": sum(r["bytes"] for r in rows)}


def engine_ready(catalog):
    """True only when Setup has the engine package (bundled release asset, or a zip next to Setup)."""
    return bool(catalog) and catalog.jd_engine_ready()


# -- console helpers ----------------------------------------------------------------------
def _park(console, path, stamp, log=None):
    """Move one file or folder under ROOT into setup-backup/<stamp>/ (same relative path). Never deletes."""
    rel = path[len(ROOT):] if path.startswith(ROOT) else path.lstrip("/")
    target = config.JD_BACKUP_DIR + stamp + "/" + rel
    console.makedirs(posixpath.dirname(target))
    n = 2
    base = target
    while console.exists(target):
        target = "%s-%d" % (base, n)
        n += 1
    console.rename(path, target)
    if log:
        log("Moved %s aside to %s" % (path, target))
    return target


def _read_json(console, path, limit=64 * 1024):
    if not console.exists(path):
        return None
    try:
        return json.loads(console.read(path, limit=limit).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


def session_state(console):
    """The downloads worker's JDownloader session state, or None."""
    return _read_json(console, ROOT + "lifecycle-state.json")


def _stale_session(console, st):
    """True when the session state says JDownloader is active but its engine process provably isn't running: the
    console lists its processes and none has the pid the bridge recorded (e.g. the PS5 restarted since). Anything
    uncertain (no process list, no recorded pid) counts as running."""
    pid = st.get("native_pid")
    if pid is None:
        ready = _read_json(console, ROOT + "bridge-ready.json") or {}
        if ready.get("session") == st.get("session"):
            pid = ready.get("native_pid")
    lister = getattr(console, "process_ids", None)
    pids = lister() if lister else None
    try:
        return pid is not None and pids is not None and int(pid) not in pids
    except (TypeError, ValueError):
        return False


def ensure_idle(console, log=None):
    st = session_state(console)
    if st and st.get("status") in ACTIVE_STATES and _stale_session(console, st):
        if log:
            log("An earlier JDownloader 2 session on the PS5 didn't close (its process is gone, e.g. after a restart); "
                "treating it as closed.")
        return dict(st, status="stale")
    if st and st.get("status") in ACTIVE_STATES:
        raise CheckFailed("JDownloader 2 is running on the PS5 right now (or its last start didn't finish). "
                          "Close Media downloads in Omni, wait a minute, then try again.")
    return st


def switch_off(console, stamp, log=print):
    """Park native-install.json (and a closed session's state) so the worker can't start Java mid-change.
    A closed state from an older install would otherwise stop the new one from starting."""
    st = ensure_idle(console, log)
    parked = []
    for name in ("native-install.json", "lifecycle-state.json", "bridge-ready.json"):
        p = ROOT + name
        if console.exists(p):
            parked.append(_park(console, p, stamp))
    if parked:
        log("JDownloader 2 is switched off on the PS5 while it's being set up.")
    return {"parked": parked, "previous_state": (st or {}).get("status")}


def _walk(console, directory):
    """[(path, is_dir)] of everything under directory (FTP LIST, depth-first)."""
    out = []
    for name, entry in sorted(console.listing(directory).items()):
        p = directory.rstrip("/") + "/" + name
        out.append((p, entry["dir"]))
        if entry["dir"]:
            out.extend(_walk(console, p))
    return out


def tidy_runtime(console, keep, stamp, log=print):
    """runtime/ must hold exactly the manifest's files (outside JDownloader's own writable folders).
    Move every other file, and every folder no kept file lives in, to setup-backup/. Returns what moved."""
    root = ROOT + "runtime"
    keep = set(keep)                                  # paths relative to ROOT, e.g. runtime/libs/a.jar
    dirs = {posixpath.dirname(k) for k in keep}
    for d in list(dirs):
        while d and d != ".":
            dirs.add(d)
            d = posixpath.dirname(d)
    moved = []
    for name, entry in sorted(console.listing(root).items()):
        if entry["dir"] and name in config.JD_MUTABLE:
            continue
        stack = [(root + "/" + name, entry["dir"])]
        while stack:
            path, is_dir = stack.pop()
            rel = path[len(ROOT):]
            if is_dir:
                if rel not in dirs:
                    moved.append(_park(console, path, stamp))
                    continue
                stack.extend((path + "/" + n, e["dir"]) for n, e in console.listing(path).items())
            elif rel not in keep and not path.endswith(".omnibloom-new"):
                moved.append(_park(console, path, stamp))
    if moved:
        log("Moved %d old JDownloader file%s aside (kept in setup-backup/%s)." % (len(moved), "" if len(moved) == 1 else "s", stamp))
    return moved


# -- 2/3. engine + the user's files -------------------------------------------------------
def install_engine(console, catalog, log=print, progress=None):
    """Install or update the engine app (receipt-tracked like any other app)."""
    from . import installer
    from .ports import PortPicker
    return installer.install_app(console, catalog, config.JD_APP_ID, PortPicker(console, probe=False), log=log, progress=progress)


def engine_rows(catalog):
    """Manifest rows for the engine's own runtime/ files (our bridge classes)."""
    rows = []
    for row in catalog.files_for(config.JD_APP_ID):
        if row["dest"].startswith(ROOT + "runtime/"):
            rows.append({"path": row["dest"][len(ROOT):], "bytes": row["bytes"], "sha256": row["sha256"]})
    return rows


def copy_to_console(console, folder, catalog, stamp=None, log=print, progress=None):
    """Copy the user's JDownloader 2 files into runtime/, tidy runtime/ to the exact list, write the manifest.
    JDownloader's own settings (runtime/cfg) and other writable folders are left alone."""
    if not engine_ready(catalog):
        raise ValueError("The JDownloader 2 engine package isn't loaded.")
    stamp = stamp or _stamp()
    files = collect(folder)
    manifest = build_manifest(files, engine_rows(catalog))
    keep = [r["path"] for r in manifest["files"]]
    want = {r["path"]: r for r in manifest["files"]}
    root = ROOT + "runtime/"
    copied = skipped = 0
    for i, (rel, full, size) in enumerate(files, 1):
        dest = root + rel
        row = want["runtime/" + rel]
        console.makedirs(posixpath.dirname(dest))
        if console.exists(dest) and console.size(dest) == size and _sha(console.read(dest)) == row["sha256"]:
            skipped += 1
        else:
            with open(full, "rb") as fh:
                data = fh.read()
            if _sha(data) != row["sha256"]:
                raise IOError("%s changed while it was being copied. Close JDownloader 2 on this computer and try again." % rel)
            temp = console.put_verified(dest, data)
            if console.exists(dest):
                _park(console, dest, stamp)
            console.rename(temp, dest)
            copied += 1
        if progress:
            progress(i, len(files))
    tidy_runtime(console, keep, stamp, log=log)
    data = _json_bytes(manifest)
    path = ROOT + ASSETS_MANIFEST
    temp = console.put_verified(path, data)
    if console.exists(path):
        _park(console, path, stamp)
    console.rename(temp, path)
    log("JDownloader 2 from this computer: %d file%s copied, %d already there." % (copied, "" if copied == 1 else "s", skipped))
    return {"files": len(files), "copied": copied, "manifest_sha256": _sha(data), "manifest": path}


# -- 4. the console check ------------------------------------------------------------------
def _launcher_url(console, path, args):
    port = getattr(console, "launcher_port", None) or config.LAUNCHER_PORT
    query = urllib.parse.urlencode({"path": path, "args": args, "cwd": ROOT.rstrip("/"), "daemon": "1", "pipe": "0"})
    return "http://%s:%d/hbldr?%s" % (console.host, port, query)


def launch(console, config_path, mode):
    """Start java-worker.elf through the console's own launcher (/hbldr, the same way the downloads worker does).
    Returns True when the launcher acknowledged; the run itself is judged only by its receipt file."""
    url = _launcher_url(console, ROOT + "java-worker.elf", "omni-jd-worker %s %s" % (config_path, mode))
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            r.read(4096)
            return 200 <= r.status < 300
    except Exception:
        return False


def _wait_finished(console, receipt, session, mode, timeout, sleep, clock, log, also=None):
    """Poll the engine's receipt until it holds a finished JSON (it's created empty at start, filled at the end).
    `also(console)` may return a value early (e.g. the bridge's ready file) but we still wait for the finish,
    so no Java process is left running. Never kills anything."""
    end = clock() + timeout
    early = None
    last_note = clock()
    while clock() < end:
        if also and early is None:
            early = also(console)
        value = _read_json(console, receipt)
        if value and value.get("finished") is True:
            if value.get("session") != session or value.get("mode") != mode:
                raise CheckFailed("The PS5 answered for a different check run; nothing was switched on.")
            return value, early
        if clock() - last_note >= 30:
            log("  still waiting for the PS5 (%s check)…" % mode)
            last_note = clock()
        sleep(3.0)
    raise CheckFailed("The %s check didn't finish within %d minutes. JDownloader 2 stays off. If the PS5 is slow right "
                      "after starting, run Setup's JDownloader 2 step again in a few minutes." % (mode, timeout // 60))


def _run_mode(console, mode, install_id, check_dir, extra, timeout, sleep, clock, log, also=None):
    session = secrets.token_hex(16)
    work = check_dir + mode + "/"
    for sub in ("home", "tmp", "downloads"):
        console.makedirs(work + sub)
    receipt = work + "native-receipt.json"
    cfg = {"session": session, "install_id": install_id, "native_receipt_file": receipt,
           "runtime": ROOT + "runtime", "home": work + "home", "tmp": work + "tmp",
           "java_home": ROOT + "native/java25", "startup_seconds": STARTUP_SECONDS}
    cfg.update(extra(work, session) if extra else {})
    path = work + "config.json"
    data = (json.dumps(cfg, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > 8192:
        raise CheckFailed("Check settings too long for the engine.")
    temp = console.put_verified(path, data)
    console.rename(temp, path)
    log("Checking JDownloader 2 on the PS5 (%s)… this can take a few minutes the first time." % mode)
    if not launch(console, path, mode):
        raise CheckFailed("The PS5's launcher didn't accept the check (port %d). Make sure your jailbreak's web launcher "
                          "(websrv) is running, then try again." % (getattr(console, "launcher_port", None) or config.LAUNCHER_PORT))
    done, early = _wait_finished(console, receipt, session, mode, timeout, sleep, clock, log, also=also)
    raw = console.read(receipt)
    return session, done, early, raw, work


def self_check(console, catalog, jd_manifest_sha, sleep=time.sleep, clock=time.monotonic, log=print, jd_start=True):
    """Two short runs of the engine on the PS5, judged only by the files they write:
    1. providers: the Java runtime boots and its native parts work (no JDownloader code involved);
    2. jdownloader: the user's JDownloader 2 loads with our bridge, which writes its ready file and stops
       by itself after a short lifetime.
    Returns the acceptance record; raises CheckFailed with a plain reason otherwise."""
    ensure_idle(console)
    info = catalog.jd_engine()
    install_id = "omnibloom-%s-%s" % (catalog.apps[config.JD_APP_ID]["version"].replace("+", "_"), secrets.token_hex(4))
    check_dir = config.JD_CHECKS_DIR + _stamp() + "-" + secrets.token_hex(3) + "/"
    console.makedirs(check_dir)

    session, done, _, raw, work = _run_mode(console, "providers", install_id, check_dir, lambda w, s: {"max_seconds": 120},
                                            STARTUP_SECONDS + 240, sleep, clock, log)
    report_path = work + "native-receipt.json.provider.json"
    report = _read_json(console, report_path) or {}
    steps = report.get("steps")
    step_names = [s.get("name") if isinstance(s, dict) else s for s in steps] if isinstance(steps, list) else []
    if report and report.get("passed") is not True:
        raise CheckFailed("The Java runtime started, but its native parts didn't all pass (%s, stopped after %s). "
                          "JDownloader 2 stays off." % (report.get("error_class") or "no detail", report.get("last_step") or "?"))
    if done.get("exit_code") != 0 or done.get("phase") != "Java-main-and-destroy-complete":
        raise CheckFailed("The Java runtime didn't start correctly on the PS5 (exit %s, %s). JDownloader 2 stays off."
                          % (done.get("exit_code"), done.get("phase")))
    if report.get("schema") != "omni-jd-native-provider-probe/v1" or tuple(step_names) != PROVIDER_STEPS:
        raise CheckFailed("The Java runtime started, but its native-parts report was incomplete. JDownloader 2 stays off.")
    provider_raw = console.read(report_path)
    log("  Java runtime: OK.")

    evidence = {"providers": {"session": session, "receipt_sha256": _sha(raw), "provider_report_sha256": _sha(provider_raw),
                              "native_pid": done.get("native_pid")}}
    if jd_start:
        ready_name = "bridge-ready.json"

        def extra(w, s):
            return {"token": secrets.token_hex(32), "port": 0, "downloads": w + "downloads", "ready_file": w + ready_name,
                    "max_seconds": 150, "idle_seconds": 60}

        def ready(c):
            v = _read_json(c, check_dir + "jdownloader/" + ready_name)
            return v if v else None

        session2, done2, ready_value, raw2, work2 = _run_mode(console, "jdownloader", install_id, check_dir, extra,
                                                              STARTUP_SECONDS + 150 + 240, sleep, clock, log, also=ready)
        if ready_value is None:
            ready_value = _read_json(console, work2 + ready_name)
        if not ready_value or ready_value.get("session") != session2 or ready_value.get("install_id") != install_id \
                or ready_value.get("protocol") != 2:
            raise CheckFailed("JDownloader 2 from this computer didn't start on the PS5 (exit %s, %s). If it's much newer or "
                              "older than revision %d, update it and try again. JDownloader 2 stays off."
                              % (done2.get("exit_code"), done2.get("phase"), config.JD_TESTED_REVISION))
        if config.jd_policy_declared(catalog.jd_engine()) and ready_value.get("egress_policy") != config.JD_EGRESS_POLICY:
            raise CheckFailed("JDownloader 2 started on the PS5, but its connection guard (%s) wasn't fully in place (%s). "
                              "JDownloader 2 stays off." % (config.JD_EGRESS_POLICY, ready_value.get("egress_problem") or "no detail"))
        if done2.get("exit_code") not in (0,):
            raise CheckFailed("JDownloader 2 started on the PS5 but didn't stop cleanly (exit %s, %s). JDownloader 2 stays off."
                              % (done2.get("exit_code"), done2.get("phase")))
        evidence["jdownloader"] = {"session": session2, "receipt_sha256": _sha(raw2),
                                   "ready_sha256": _sha(console.read(work2 + ready_name)), "native_pid": done2.get("native_pid")}
        log("  JDownloader 2 from this computer: OK.")

    acceptance = {"schema": ACCEPTANCE_SCHEMA, "passed": True, "install_id": install_id, "checked_utc": _now(),
                  "setup_version": config.SETUP_VERSION, "engine_version": catalog.apps[config.JD_APP_ID]["version"],
                  "elf_sha256": info["elf_sha256"], "image_manifest_sha256": info["image_manifest_sha256"],
                  "jd_manifest_sha256": jd_manifest_sha, "runs": evidence}
    data = _json_bytes(acceptance)
    path = check_dir + "acceptance.json"
    temp = console.put_verified(path, data)
    console.rename(temp, path)
    acceptance["evidence_sha256"] = _sha(data)
    acceptance["evidence_path"] = path
    return acceptance


# -- 5. switch on --------------------------------------------------------------------------
def switch_on(console, catalog, jd_manifest_sha, acceptance, stamp, log=print):
    info = catalog.jd_engine()
    spec = {"schema": INSTALL_SCHEMA, "approved": True, "install_id": acceptance["install_id"],
            "elf_sha256": info["elf_sha256"], "elf_bytes": info["elf_bytes"], "startup_seconds": STARTUP_SECONDS,
            "asset_manifests": [{"kind": "native-image", "path": IMAGE_MANIFEST, "sha256": info["image_manifest_sha256"]},
                                {"kind": "jdownloader", "path": ASSETS_MANIFEST, "sha256": jd_manifest_sha}],
            "target_acceptance": {"passed": True, "evidence_sha256": acceptance["evidence_sha256"],
                                  "evidence": acceptance["evidence_path"], "by": "omnibloom-setup",
                                  "checked_utc": acceptance["checked_utc"]}}
    data = _json_bytes(spec)
    if len(data) > 8192:
        raise IOError("native-install.json would be too large for the downloads worker.")
    temp = console.put_verified(APPROVAL, data)
    if console.exists(APPROVAL):
        _park(console, APPROVAL, stamp)
    console.rename(temp, APPROVAL)
    log("JDownloader 2 is switched on. Open Media downloads in Omni to use it.")
    return spec


def setup_jdownloader(console, catalog, folder, log=print, progress=None, sleep=time.sleep, clock=time.monotonic):
    """The whole JDownloader 2 step. On any failure JDownloader 2 is left switched off (yt-dlp keeps working)."""
    if not config.jd_enabled():          # audit JD-03: held back by the user/developer switch
        raise CheckFailed(config.JD_HELD_REASON)
    if not engine_ready(catalog):
        raise ValueError("The JDownloader 2 engine package isn't loaded.")
    if not config.jd_enabled(catalog.jd_engine()):   # audit JD-03: the engine must declare the egress policy
        raise CheckFailed(config.JD_ENGINE_POLICY_REASON)
    collect(folder)                      # fail early on a bad folder, before touching the PS5
    stamp = _stamp()
    ensure_idle(console)
    switch_off(console, stamp, log=log)
    install_engine(console, catalog, log=log, progress=progress)
    copy = copy_to_console(console, folder, catalog, stamp=stamp, log=log, progress=progress)
    acceptance = self_check(console, catalog, copy["manifest_sha256"], sleep=sleep, clock=clock, log=log)
    spec = switch_on(console, catalog, copy["manifest_sha256"], acceptance, stamp, log=log)
    return {"copy": copy, "acceptance": acceptance, "native_install": spec}


def credit_lines():
    info = config
    return [info.JAVA_PORT_CREDIT,
            "JDownloader 2 is by AppWork GmbH (" + info.JD_OFFICIAL_URL + "); Omnibloom uses your own copy and never ships it."]
