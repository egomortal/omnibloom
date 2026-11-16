"""Back up Omni's data from the PS5 to one zip on this PC, and put a backup back.

What a backup may hold is a fixed list (ITEMS): Omni's settings always, and personal data only when ticked. Everything
else under /data/omni is left out on purpose: saved passwords and their key, autofill, the open-tabs session, the
browser profile (cookies, sign-ins, site storage), caches, logs, screenshots, downloads, test and tuning flags, the
engine, fonts and the ad block rules (Setup installs those; your own "My filters" list is a personal group), and the parental-controls file (it holds the PIN hash).

The zip: one entry per file, named by its console path without the leading "/", plus MANIFEST_NAME (format, versions,
created time, and every file's path, group, size and sha256).

A restore trusts nothing in the zip: every path must be one of ITEMS (exact name, or a plain file name of the right
kind in one of the known folders), sizes are capped per file, per folder and in total, every entry must match the
manifest's size and sha256, and nothing is written before the whole zip has been checked. Files on the PS5 are
replaced the way the installer does it (verified upload, the old file parked as <name>.before-setup-<time>).
Logs name groups and counts only, never a file name (reading-list pages are named after the sites).
"""
import datetime
import hashlib
import json
import os
import posixpath
import re
import zipfile
import zlib

from . import config

MANIFEST_NAME = "omni-backup.json"
FORMAT = "omnibloom-omni-backup"
FORMAT_VERSION = 1
MANIFEST_MAX = 1024 * 1024
MAX_TOTAL = 640 * 1024 * 1024          # the reading list alone may hold 500 MB
MAX_ENTRIES = 400

KiB, MiB = 1024, 1024 * 1024
OMNI = "/data/omni/"
DL_STATE = "/data/omni-downloader/state/"

# Groups, in the order the window lists them. "always": part of every backup.
GROUPS = (
    {"id": "settings", "name": "Omni settings", "detail": "browser settings, theme, controller, bars, quick access, "
     "dark mode, site zoom, volume and permissions, search shortcuts, start page, web apps, add-on choices",
     "always": True},
    {"id": "bookmarks", "name": "Bookmarks", "detail": "bookmarks.txt and the bookmarklets you let run without asking"},
    {"id": "notes", "name": "Notes", "detail": "your notes"},
    {"id": "highlights", "name": "Highlights", "detail": "text you marked on pages"},
    {"id": "tab-sessions", "name": "Saved tab sessions", "detail": "named sets of tabs you saved"},
    {"id": "history", "name": "History", "detail": "the pages you visited"},
    {"id": "reading-list", "name": "Reading list", "detail": "pages saved for later (can be large)"},
    {"id": "addon-data", "name": "Add-on data", "detail": "what each add-on saved for itself"},
    {"id": "downloads", "name": "Downloads list and saved links", "detail": "the Downloads app's history"},
    {"id": "pointers", "name": "Pointer pictures", "detail": "your own pointer images"},
    {"id": "kb-words", "name": "Learned keyboard words", "detail": "words the keyboard learned from your typing"},
    {"id": "my-filters", "name": "My filters", "detail": "your own ad-block rules and the elements you hid"},
)
GROUP_IDS = tuple(g["id"] for g in GROUPS)
PERSONAL = tuple(g["id"] for g in GROUPS if not g.get("always"))


def _f(path, group, limit):
    return {"path": path, "group": group, "max": limit}


# Single files: exact console paths.
FILES = (
    _f(OMNI + "browser-settings.txt", "settings", 256 * KiB),
    _f(OMNI + "browser-more.txt", "settings", 256 * KiB),
    _f(OMNI + "shortcuts.txt", "settings", 256 * KiB),
    _f(OMNI + "quick-access.txt", "settings", 256 * KiB),
    _f(OMNI + "ui-bars.txt", "settings", 64 * KiB),
    _f(OMNI + "ui-theme.txt", "settings", 4 * KiB),
    _f(OMNI + "ui-autohide.txt", "settings", 4 * KiB),
    _f(OMNI + "controller-style.txt", "settings", 4 * KiB),
    _f(OMNI + "dark-style.txt", "settings", 4 * KiB),
    _f(OMNI + "site-dark.txt", "settings", 1 * MiB),
    _f(OMNI + "site-zoom.txt", "settings", 1 * MiB),
    _f(OMNI + "site-ua.txt", "settings", 1 * MiB),
    _f(OMNI + "site-permissions.txt", "settings", 1 * MiB),
    _f(OMNI + "search-shortcuts.txt", "settings", 256 * KiB),
    _f(OMNI + "display-mode.txt", "settings", 4 * KiB),
    _f(OMNI + "video-quality.txt", "settings", 4 * KiB),
    _f(config.OMNI_HDR_PREF, "settings", 4 * KiB),
    _f(OMNI + "youtube-mode.txt", "settings", 4 * KiB),
    _f(OMNI + "ublock-allowlist.txt", "settings", 2 * MiB),
    _f(OMNI + "addons/state.json", "settings", 2 * MiB),
    _f(DL_STATE + "schedule.json", "settings", 256 * KiB),
    # Settings added with Omni's everyday features (each file's own read cap, or a small fixed one for one-line files).
    _f(OMNI + "apps.json", "settings", 64 * KiB),
    _f(OMNI + "start-page.json", "settings", 16 * KiB),
    _f(OMNI + "startup.txt", "settings", 4 * KiB),
    _f(OMNI + "autoplay.txt", "settings", 256 * KiB),
    _f(OMNI + "https-only.txt", "settings", 64 * KiB),
    _f(OMNI + "popup-allow.txt", "settings", 64 * KiB),
    _f(OMNI + "site-volume.txt", "settings", 64 * KiB),
    _f(OMNI + "site-tweaks.txt", "settings", 256 * KiB),
    _f(OMNI + "reader-sites.txt", "settings", 64 * KiB),
    _f(OMNI + "game-sites.txt", "settings", 64 * KiB),
    _f(OMNI + "refresh-sites.txt", "settings", 64 * KiB),
    _f(OMNI + "translate.txt", "settings", 64 * KiB),
    _f(OMNI + "search-custom.txt", "settings", 4 * KiB),
    _f(OMNI + "site-search.txt", "settings", 4 * KiB),
    _f(OMNI + "shortcuts-map.txt", "settings", 4 * KiB),
    _f(OMNI + "captions.txt", "settings", 4 * KiB),
    _f(OMNI + "ui-accent.txt", "settings", 4 * KiB),
    _f(OMNI + "ui-scale.txt", "settings", 4 * KiB),
    _f(OMNI + "ui-lang.txt", "settings", 4 * KiB),
    _f(OMNI + "ui-theme-prev.txt", "settings", 4 * KiB),
    _f(OMNI + "night-light.txt", "settings", 4 * KiB),
    _f(OMNI + "colour-filter.txt", "settings", 4 * KiB),
    _f(OMNI + "pointer-large.txt", "settings", 4 * KiB),
    _f(OMNI + "history-keep.txt", "settings", 4 * KiB),
    _f(OMNI + "tab-sleep.txt", "settings", 4 * KiB),
    _f(OMNI + "data-saver.txt", "settings", 4 * KiB),
    _f(OMNI + "kb-layout.txt", "settings", 4 * KiB),
    _f(OMNI + "scroll-plus.txt", "settings", 4 * KiB),
    _f(OMNI + "spatial-nav.txt", "settings", 4 * KiB),
    _f(OMNI + "tips-seen.txt", "settings", 4 * KiB),
    _f(config.OMNI_BOOKMARKS, "bookmarks", 2 * MiB),
    _f(OMNI + "bookmarklets.txt", "bookmarks", 128 * KiB),   # "Always" answers: SHA-256 keys of trusted bookmarklets
    _f(OMNI + "notes.txt", "notes", 4 * MiB),
    _f(OMNI + "highlights.json", "highlights", 2 * MiB),
    _f(OMNI + "sessions.txt", "tab-sessions", 2 * MiB),
    _f(OMNI + "kb-words.txt", "kb-words", 512 * KiB),
    _f(OMNI + "ublock-user-filters.txt", "my-filters", 256 * KiB),   # OmniZapper::kMaxFileBytes
    _f(OMNI + "history.txt", "history", 32 * MiB),
    _f(OMNI + "reading-list/index.tsv", "reading-list", 4 * MiB),
    _f(DL_STATE + "jobs.json", "downloads", 16 * MiB),
    _f(DL_STATE + "saved-links.json", "downloads", 8 * MiB),
    _f(OMNI + "downloads-done.txt", "downloads", 64 * KiB),
)

# Folders: plain files whose names match `name`, each up to `max` bytes, at most `count` of them, `total` bytes together.
FOLDERS = (
    {"dir": OMNI + "reading-list/", "group": "reading-list", "name": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.html\Z"),
     "max": 32 * MiB, "count": 200, "total": 500 * MiB},
    {"dir": OMNI + "addons/storage/", "group": "addon-data", "name": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.txt\Z"),
     "max": 512 * KiB, "count": 64, "total": 16 * MiB},
    {"dir": OMNI + "pointers/", "group": "pointers", "name": re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._@,()+-]{0,90}\.[Pp][Nn][Gg]\Z"),
     "max": 2 * MiB, "count": 32, "total": 32 * MiB},
)
_BY_PATH = {f["path"]: f for f in FILES}

# Never in a backup (documentation and tests; the allow-list above is what decides).
NEVER = (
    OMNI + "passwords.txt", OMNI + "passwords.key", OMNI + "autofill.txt", OMNI + "session.txt",
    OMNI + "browser-profile/", OMNI + "downloads/", OMNI + "uploads/", OMNI + "screenshots/", OMNI + "native/",
    OMNI + "fonts/", OMNI + "content-rules/", OMNI + "gpu-pages/", OMNI + "ubo-content/", OMNI + "ubo-site/",
    OMNI + "*.flag", OMNI + "*.png", OMNI + "*.log", OMNI + "*.tmp", OMNI + "ublock-*",   # except ublock-user-filters.txt ("My filters", opt-in)
    OMNI + "omni-engine.elf",
    OMNI + "display-hz.txt", OMNI + "raster-env.txt", OMNI + "jsc-env.txt", OMNI + "paint-threads.txt",
    OMNI + "ua-desktop.txt", OMNI + "ua-youtube-tv.txt", OMNI + "mse-quota-mb.txt", OMNI + "gpu-watchdog-ms.txt",
    OMNI + "yt-timeline.txt", OMNI + "addons/bundled/", OMNI + "addons/dev/", DL_STATE + "tz-offset.json",
    "/data/omni-downloader/jdownloader/", "/data/omni-downloader/downloads/",
    # parental.txt holds the parental-controls PIN hash and rules: restoring it (onto another console, or after the
    # owner reset a forgotten PIN by deleting it) could lock people out of settings and sites with a PIN nobody there
    # knows, so it is never saved. The rest are markers, test and tuning files, or installed by Setup.
    OMNI + "parental.txt", OMNI + "running.txt", OMNI + "perf-overlay.txt", OMNI + "yt-media-stop.txt",
    OMNI + "jank-mark.txt", OMNI + "crash-*.txt", OMNI + "lang/", OMNI + "sub/",
)


class BackupError(Exception):
    """A backup that can't be used; the message is for the user."""


def rule_for(path):
    """The ITEMS rule that allows `path` (a console path), or None. Only plain, normalised paths pass."""
    if not isinstance(path, str) or not path.startswith("/data/") or len(path) > 300:
        return None
    if "\\" in path or "\0" in path or "//" in path or posixpath.normpath(path) != path:
        return None
    if any(part in ("", ".", "..") for part in path[1:].split("/")):
        return None
    if path in _BY_PATH:
        return _BY_PATH[path]
    parent, name = posixpath.split(path)
    for rule in FOLDERS:
        if parent + "/" == rule["dir"] and rule["name"].match(name) and ".." not in name:
            return rule
    return None


def entry_name(path):
    return path.lstrip("/")


def default_folder(home=None):
    return os.path.join(home or os.path.expanduser("~"), "Documents", "Omnibloom Backups")


def default_path(folder, today=None):
    """<folder>/omni-backup-<date>.zip, with -2, -3... when that name is taken."""
    day = (today or datetime.date.today()).strftime("%Y-%m-%d")
    path = os.path.join(folder, "omni-backup-%s.zip" % day)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "omni-backup-%s-%d.zip" % (day, n))
        n += 1
    return path


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(console, path, limit):
    try:
        return console.read(path, limit=limit + 1)
    except TypeError:            # consoles without a read limit
        return console.read(path)


def _omni_version(console):
    from . import installer
    try:
        rec = installer.read_receipt(console, "omni")
    except Exception:
        return None
    return rec.get("version") if rec else None


# -- back up ---------------------------------------------------------------------------------------------------------------
def plan(console, groups):
    """[(path, rule)] of the files on the console for these groups (settings always), and how many were left out
    (too big or over a folder's caps). Files are found with one listing per folder."""
    groups = set(groups or ()) | {"settings"}
    listings = {}

    def listing(d):
        if d not in listings:
            listings[d] = console.listing(d) or {}
        return listings[d]

    found, left_out = [], 0
    for rule in FILES:
        if rule["group"] not in groups:
            continue
        parent, name = posixpath.split(rule["path"])
        entry = listing(parent).get(name)
        if entry is None or entry.get("dir"):
            continue
        if entry.get("size", 0) > rule["max"]:
            left_out += 1
            continue
        found.append((rule["path"], rule))
    for rule in FOLDERS:
        if rule["group"] not in groups:
            continue
        count, total = 0, 0
        for name, entry in sorted(listing(rule["dir"].rstrip("/")).items()):
            path = rule["dir"] + name
            if entry.get("dir") or rule_for(path) is not rule:
                continue
            size = entry.get("size", 0)
            if size > rule["max"] or count >= rule["count"] or total + max(size, 0) > rule["total"]:
                left_out += 1
                continue
            count += 1
            total += max(size, 0)
            found.append((path, rule))
    return found, left_out


def backup(console, groups, dest, setup_version=None, log=lambda m: None, progress=None, now=None):
    """Write the backup zip to `dest` (via dest.part, so a stopped backup leaves no half zip).
    Returns {"path", "files", "bytes", "left_out", "groups": {group: count}}."""
    files, left_out = plan(console, groups)
    created = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {"format": FORMAT, "version": FORMAT_VERSION, "created": created,
                "setup_version": setup_version or config.SETUP_VERSION, "omni_version": _omni_version(console),
                "groups": sorted(set(groups or ()) & set(GROUP_IDS) | {"settings"}), "files": []}
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    total = 0
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for i, (path, rule) in enumerate(files):
                data = _read(console, path, rule["max"])
                if len(data) > rule["max"] or total + len(data) > MAX_TOTAL:
                    left_out += 1
                    continue
                total += len(data)
                z.writestr(entry_name(path), data)
                manifest["files"].append({"path": path, "group": rule["group"], "size": len(data), "sha256": _sha(data)})
                if progress:
                    progress(i + 1, len(files))
            z.writestr(MANIFEST_NAME, json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    counts = _counts(manifest["files"])
    log("Omni backup: %d file(s), %d KB (%s)%s." % (len(manifest["files"]), (total + 1023) // 1024,
        ", ".join("%s %d" % (g, n) for g, n in counts.items()), "; %d left out (too big)" % left_out if left_out else ""))
    return {"path": dest, "files": len(manifest["files"]), "bytes": total, "left_out": left_out, "groups": counts}


def _counts(files):
    out = {}
    for f in files:
        out[f["group"]] = out.get(f["group"], 0) + 1
    return {g: out[g] for g in GROUP_IDS if g in out}


# -- check a backup ----------------------------------------------------------------------------------------------------------
def _entry_bytes(z, info, limit):
    """The entry's bytes, never more than `limit` + 1 read (a header that lies about the size is caught)."""
    out = bytearray()
    with z.open(info) as f:
        while len(out) <= limit:
            chunk = f.read(min(1024 * 1024, limit + 1 - len(out)))
            if not chunk:
                break
            out += chunk
    return bytes(out)


def read_backup(zip_path):
    """Check a backup zip completely (nothing is written anywhere). Returns its manifest with "summary":
    {group: {"files", "bytes"}}. Raises BackupError with a plain reason."""
    try:
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise BackupError("This isn't an Omni backup zip (%s)." % type(e).__name__)
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES + 1:
            raise BackupError("The backup has too many files.")
        names = [i.filename for i in infos]
        if any(i.orig_filename != i.filename for i in infos):   # zipfile rewrote a "\" or "/x" name: refuse it
            raise BackupError("The backup holds a file with an unsafe name. Nothing was changed.")
        if len(set(names)) != len(names):
            raise BackupError("The backup lists a file twice.")
        if MANIFEST_NAME not in names:
            raise BackupError("This zip has no Omni backup manifest (%s)." % MANIFEST_NAME)
        info = z.getinfo(MANIFEST_NAME)
        if info.file_size > MANIFEST_MAX:
            raise BackupError("The backup's manifest is too big.")
        try:
            manifest = json.loads(_entry_bytes(z, info, MANIFEST_MAX).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error):
            raise BackupError("The backup's manifest can't be read.")
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise BackupError("This zip isn't an Omni backup.")
        if manifest.get("version") != FORMAT_VERSION:
            raise BackupError("This backup was made by a newer Setup (format %r). Update Omnibloom Setup."
                              % (manifest.get("version"),))
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) > MAX_ENTRIES:
            raise BackupError("The backup's file list is damaged.")
        by_entry, total, per_folder = {}, 0, {}
        for f in files:
            if not isinstance(f, dict) or not isinstance(f.get("size"), int) or not isinstance(f.get("sha256"), str):
                raise BackupError("The backup's file list is damaged.")
            path = f.get("path")
            rule = rule_for(path)
            if rule is None:
                raise BackupError("The backup holds a file Setup doesn't restore. Nothing was changed.")
            if f.get("group") != rule["group"]:
                raise BackupError("The backup's file list is damaged.")
            if not 0 <= f["size"] <= rule["max"]:
                raise BackupError("A file in the backup is bigger than Omni allows. Nothing was changed.")
            name = entry_name(path)
            if name in by_entry:
                raise BackupError("The backup lists a file twice.")
            by_entry[name] = f
            total += f["size"]
            if "dir" in rule:
                c = per_folder.setdefault(rule["dir"], [0, 0])
                c[0] += 1
                c[1] += f["size"]
                if c[0] > rule["count"] or c[1] > rule["total"]:
                    raise BackupError("The backup holds more %s than Omni keeps." % rule["group"])
        if total > MAX_TOTAL:
            raise BackupError("The backup is bigger than Setup restores.")
        for info in infos:
            if info.filename == MANIFEST_NAME:
                continue
            f = by_entry.get(info.filename)
            if f is None:
                raise BackupError("The backup holds a file that isn't in its manifest. Nothing was changed.")
            mode = (info.external_attr >> 16) & 0o170000
            if info.is_dir() or info.flag_bits & 0x1 or mode not in (0, 0o100000):
                raise BackupError("The backup holds a folder, link or locked entry. Nothing was changed.")
            if info.file_size != f["size"]:
                raise BackupError("A file in the backup doesn't match its manifest. Nothing was changed.")
            try:
                data = _entry_bytes(z, info, f["size"])
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error):
                raise BackupError("A file in the backup is damaged. Nothing was changed.")
            if len(data) != f["size"] or _sha(data) != f["sha256"]:
                raise BackupError("A file in the backup doesn't match its manifest. Nothing was changed.")
        missing = set(by_entry) - set(names)
        if missing:
            raise BackupError("The backup is missing %d file(s) its manifest lists." % len(missing))
    summary = {}
    for f in files:
        s = summary.setdefault(f["group"], {"files": 0, "bytes": 0})
        s["files"] += 1
        s["bytes"] += f["size"]
    manifest["summary"] = {g: summary[g] for g in GROUP_IDS if g in summary}
    return manifest


# -- restore -------------------------------------------------------------------------------------------------------------------
def restore(console, zip_path, groups=None, log=lambda m: None, progress=None, paths=None, park_suffix=None):
    """Put the backup's files (only `groups`, default all) back on the PS5. The zip is checked in full first; each
    file then goes up verified, and a different file already there is parked as <name>.before-setup-<time>.
    `paths` (console paths) narrows it to those files: every one must be in the backup's checked manifest, or nothing
    is written. `park_suffix` replaces the parking suffix (the backup inspector uses ".prev", like shortcuts_edit).
    Omni must be closed (it keeps these files in memory and writes its own copy when it closes).
    Returns {"written", "same", "parked_suffix", "groups": {group: count}}."""
    from . import installer
    manifest = read_backup(zip_path)
    wanted = set(GROUP_IDS if groups is None else groups)
    files = [f for f in manifest["files"] if f["group"] in wanted]
    if paths is not None:
        chosen = set(paths)
        if any(rule_for(p) is None for p in chosen) or not chosen <= {f["path"] for f in files}:
            raise BackupError("That item isn't one Setup restores from this backup. Nothing was changed.")
        files = [f for f in files if f["path"] in chosen]
    # Pages before the reading-list index (an index must never point at a page that isn't there yet).
    files.sort(key=lambda f: f["path"].endswith("/reading-list/index.tsv"))
    suffix = park_suffix or ".before-setup-" + installer._stamp()
    written = same = 0
    with zipfile.ZipFile(zip_path) as z:
        for i, f in enumerate(files):
            rule = rule_for(f["path"])                       # checked again: read_backup's result could be stale
            info = z.getinfo(entry_name(f["path"]))
            data = _entry_bytes(z, info, rule["max"])
            if len(data) != f["size"] or _sha(data) != f["sha256"]:
                raise BackupError("The backup changed while it was being restored. Files written so far kept their "
                                  "earlier copies beside them (%s)." % suffix)
            if console.exists(f["path"]) and _sha(console.read(f["path"])) == f["sha256"]:
                same += 1
            else:
                installer._replace(console, f["path"], data, suffix)
                written += 1
            if progress:
                progress(i + 1, len(files))
    counts = _counts(files)
    log("Omni restore: %d file(s) written, %d already the same (%s)." % (written, same,
        ", ".join("%s %d" % (g, n) for g, n in counts.items())))
    return {"written": written, "same": same, "parked_suffix": suffix, "groups": counts}
