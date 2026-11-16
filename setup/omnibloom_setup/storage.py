"""Storage on the PS5: how much space Omni and its parts use, and a few safe clean-ups.

The report is read-only: one FTP LIST per folder under Omni's own places (the app package, /data/omni,
/data/omni-downloader) plus the Setup-owned folders where the installer parks old copies (/data/hub, /data/pldmgr; only
parked copies are counted there). Every file is put in one category by its path; a file that matches no rule is
"not recognised" and is only counted, never changed. The browser profile is counted by size alone: its file names are
never kept or shown, and nothing in it is ever read.

Free space: Setup's FTP connection can't measure it (FTP has no free-space command; LIST and SIZE give file sizes only),
so the report asks the console object for `free_space()` the way the diagnostics bundle does and otherwise says so.

Clean-ups delete files, so each is narrow and checked twice (when the list is made and again just before each DELE):
- empty the Downloads trash (the Downloads app's Saved/.trash: files the owner already deleted once);
- remove Setup's parked copies (<name>.before-setup-<UTC time>) older than 30 days, never a copy of a settings or
  personal-data file;
- clear the icons cache;
- clear logs over 10 MB.
Settings, personal data, the browser profile, the Downloads app's lists, saved downloads and unrecognised files are
never deleted. Nothing is deleted without the caller passing the exact list the owner confirmed.
Logs name categories and counts only, never a file name.
"""
import datetime
import ftplib
import posixpath
import re

from . import backup, config

KiB, MiB, GiB = 1024, 1024 * 1024, 1024 * 1024 * 1024

OMNI = "/data/omni/"
DL = OMNI + "downloads/"
SAVED = DL + "media-worker/Saved/"         # the Downloads app's console save root (downloads/worker/save_places.py)
TRASH = SAVED + ".trash/"                   # files_library.py: "Delete" moves a file here first
SHOTS = SAVED + "Screenshots/"              # Omni's screenshot quick action saves here
OLD_SHOTS = OMNI + "screenshots/"
PROFILE = OMNI + "browser-profile/"
READING = OMNI + "reading-list/"
DLAPP = "/data/omni-downloader/"
DL_STATE = DLAPP + "state/"
JD_DOWNLOADS = DLAPP + "downloads/"
APP = config.TITLE_DIR
# Omni keeps no site-icon cache folder yet; these are the names kept for one, plus yttl/ (YouTube timeline pictures,
# made again when needed).
ICON_CACHES = (OMNI + "icons/", OMNI + "favicons/", OMNI + "icon-cache/", OMNI + "yttl/")
ENGINE_DIRS = tuple(OMNI + d for d in ("native/", "fonts/", "ubo-content/", "ubo-site/", "content-rules/", "gpu-pages/",
                                       "lang/", "sub/", "addons/bundled/", "addons/dev/", "pages-dev/"))
ENGINE_FILES = tuple(OMNI + f for f in ("omni-engine.elf", "public-suffix-list.dat", "content-blocker.json",
                                        "ytguard-extra.js")) + tuple(OMNI + f for f in config.OMNI_UBLOCK_CORE +
                                                                    config.OMNI_UBLOCK_EXTRA + (config.OMNI_UBLOCK_MANIFEST,))
OMNI_OTHER_DIRS = tuple(OMNI + d for d in ("run/", "addons/"))
PERSONAL_DIRS = tuple(OMNI + d for d in ("pointers/", "uploads/"))
OMNI_OTHER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(?:flag|txt|json|tmp|pending|off|png|bin|dat|js)\Z")
SETUP_ONLY_ROOTS = (config.HUB_DIR, config.PLDMGR_DIR)   # only parked copies are counted here
ROOTS = (APP, OMNI, DLAPP) + SETUP_ONLY_ROOTS

PARKED_SETUP = re.compile(r"\.before-setup-(\d{8}T\d{6}Z)(?:-\d+)?\Z")
OLD_COPY = re.compile(r"\.(?:before|after|prev|damaged|removed|uninstalled|omnibloom-undone)-[^/]+\Z|\.omnibloom-new\Z")
LOG_NAME = re.compile(r"\.log(?:\.[A-Za-z0-9_-]+)?\Z")

# Never deleted by any clean-up, whatever their category says.
NEVER_DELETE_ROOTS = (PROFILE, DL_STATE, READING, JD_DOWNLOADS, "/data/mastercontrol/", "/data/padbridge/")
NEVER_DELETE_NAMES = ("passwords.txt", "passwords.key", "autofill.txt", "session.txt", "parental.txt",
                      "bookmarks.txt", "history.txt", "notes.txt", "settings.json")

PARKED_MAX_AGE = datetime.timedelta(days=30)
BIG_LOG = 10 * MiB
MAX_LISTINGS = 6000      # folders listed per report at most (the report says "at least" past that)
MAX_DEPTH = 14
UNKNOWN_SHOWN = 30

TYPES = (("video", "videos"), ("audio", "music and audio"), ("image", "pictures"), ("pdf", "PDFs"),
         ("text", "text and subtitles"), ("other", "other files"))
_EXT = {}
for _k, _exts in (("video", ".mp4 .m4v .webm .mkv .mov .ts .ogv"), ("audio", ".m4a .mp3 .aac .ogg .oga .opus .flac .wav .weba"),
                  ("image", ".png .jpg .jpeg .gif .webp"), ("pdf", ".pdf"), ("text", ".txt .vtt .srt")):
    for _e in _exts.split():
        _EXT[_e] = _k

CATEGORIES = (
    {"id": "app", "name": "Omni app package", "note": "the title Setup installed"},
    {"id": "engine", "name": "Engine and native files", "note": "engine, fonts, ad-block rules (Setup installs them)"},
    {"id": "settings", "name": "Omni settings", "note": "settings, flags and small Omni files in /data/omni"},
    {"id": "personal", "name": "Your Omni data", "note": "bookmarks, history, notes, add-on data and the like"},
    {"id": "reading-list", "name": "Reading list", "note": "pages saved for later"},
    {"id": "icons", "name": "Icons cache", "note": "made again when needed", "action": "icons"},
    {"id": "screenshots", "name": "Screenshots", "note": "Downloads > Saved > Screenshots"},
    {"id": "dl-saved", "name": "Downloads: saved files", "note": "your downloads"},
    {"id": "dl-trash", "name": "Downloads trash", "note": "files you deleted in Downloads", "action": "empty-trash"},
    {"id": "dl-work", "name": "Downloads in progress", "note": "unfinished downloads"},
    {"id": "dl-app", "name": "Downloads app", "note": "the downloader and its engine"},
    {"id": "dl-lists", "name": "Downloads lists", "note": "download history, saved links, schedule"},
    {"id": "profile", "name": "Browser profile", "note": "cookies, sign-ins, site storage and cache (size only)"},
    {"id": "logs", "name": "Logs", "note": "Omni's own logs", "action": "big-logs"},
    {"id": "parked", "name": "Setup's parked copies", "note": "old files Setup moved aside (.before-setup-…)",
     "action": "old-parked"},
    {"id": "old-copies", "name": "Old build backups", "note": "can be removed: .before-*, .after-*, .prev-* copies "
     "the installer and test runs left"},
    {"id": "unknown", "name": "Not recognised", "note": "left alone: Setup never changes files it doesn't know"},
)
CATEGORY_IDS = tuple(c["id"] for c in CATEGORIES)
_CAT = {c["id"]: c for c in CATEGORIES}

ACTIONS = (
    {"id": "empty-trash", "category": "dl-trash", "name": "Empty the Downloads trash"},
    {"id": "old-parked", "category": "parked", "name": "Remove parked copies older than 30 days"},
    {"id": "icons", "category": "icons", "name": "Clear the icons cache"},
    {"id": "big-logs", "category": "logs", "name": "Clear logs over 10 MB"},
)
_ACTION = {a["id"]: a for a in ACTIONS}


class StorageError(Exception):
    """A clean-up that can't go ahead; the message is for the user."""


def size_text(n):
    if n is None:
        return "?"
    if n >= GiB:
        return "%.1f GB" % (n / float(GiB))
    if n >= MiB:
        return "%.1f MB" % (n / float(MiB))
    return "%d KB" % ((n + KiB - 1) // KiB)


def file_type(name):
    return _EXT.get(posixpath.splitext(name)[1].lower(), "other")


def _clean_path(path):
    if not isinstance(path, str) or not path.startswith("/data/") or len(path) > 1024:
        return False
    if "\\" in path or "\0" in path or "//" in path or path.endswith("/"):
        return False
    return posixpath.normpath(path) == path and all(p not in ("", ".", "..") for p in path[1:].split("/"))


def _under(path, roots):
    return any(path.startswith(r) for r in roots)


def parked_original(path):
    """The path a .before-setup-<time> copy was parked from, or None."""
    m = PARKED_SETUP.search(path)
    return path[:m.start()] if m else None


def parked_time(path):
    m = PARKED_SETUP.search(path)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def classify(path):
    """(category id, type or None) for a console file path, or None for a file that isn't Omni's (outside its
    places, or a non-parked file in Setup's own folders)."""
    if not _clean_path(path) or not _under(path, ROOTS):
        return None
    name = posixpath.basename(path)
    # Personal places first: a user's file there is theirs, whatever its name looks like.
    if path.startswith(PROFILE):
        return "profile", None
    if path.startswith(TRASH):
        return "dl-trash", None
    if path.startswith(SHOTS) or path.startswith(OLD_SHOTS):
        return "screenshots", None
    if path.startswith(SAVED) or path.startswith(JD_DOWNLOADS):
        return "dl-saved", file_type(name)
    if path.startswith(DL):
        return "dl-work", None
    if path.startswith(DL_STATE):
        return "dl-lists", None
    if path.startswith(READING):
        return "reading-list", None
    if path.startswith(config.JD_BACKUP_DIR):
        return "old-copies", None
    if PARKED_SETUP.search(name):
        return "parked", None
    if OLD_COPY.search(name):
        return "old-copies", None
    if _under(path, SETUP_ONLY_ROOTS):
        return None
    if LOG_NAME.search(name) and (path.startswith(OMNI) or path.startswith(DLAPP)):
        return "logs", None
    if _under(path, ICON_CACHES):
        return "icons", None
    if path.startswith(APP):
        return "app", None
    if _under(path, ENGINE_DIRS) or path in ENGINE_FILES:
        return "engine", None
    if path.startswith(DLAPP):
        return "dl-app", None
    rule = backup.rule_for(path)
    if rule is not None:
        return ("settings" if rule["group"] == "settings" else "personal"), None
    if path.startswith(OMNI):
        if _under(path, PERSONAL_DIRS):
            return "personal", None
        if _under(path, OMNI_OTHER_DIRS):
            return "settings", None
        if posixpath.dirname(path) + "/" == OMNI and OMNI_OTHER_NAME.match(name):
            return "settings", None
    return "unknown", None


# -- the report ---------------------------------------------------------------------------------------------------------------
def _walk(console, root, out, state):
    stack = [(root.rstrip("/"), 0)]
    while stack:
        d, depth = stack.pop()
        if state["listings"] >= MAX_LISTINGS:
            state["truncated"] = True
            return
        state["listings"] += 1
        try:
            entries = console.listing(d) or {}
        except ftplib.all_errors:
            state["unreadable"] += 1
            continue
        for name, e in sorted(entries.items()):
            if name in (".", "..") or "/" in name or not name:
                continue
            p = d + "/" + name
            if e.get("dir"):
                if depth < MAX_DEPTH:
                    stack.append((p, depth + 1))
                else:
                    state["truncated"] = True
            else:
                size = e.get("size", 0)
                out.append((p, size if isinstance(size, int) and size > 0 else 0))


def _optional(console, name):
    fn = getattr(console, name, None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception:
        return None


FREE_NOTE = ("Setup can't read the PS5's free space: its FTP connection has no free-space command (LIST and SIZE give "
             "file sizes only). See Settings > Storage on the PS5.")


def scan(console, log=lambda m: None):
    """Read-only. Returns {"rows": [{"id", "name", "note", "bytes", "files", "action"}] (largest first, empty
    categories left out), "types": {type: bytes} of saved downloads, "total", "free", "free_note", "truncated",
    "unknown": [paths, at most UNKNOWN_SHOWN], "unknown_count", "items": {category: [(path, size)]} for the
    clean-up categories only}."""
    files, state = [], {"listings": 0, "truncated": False, "unreadable": 0}
    for root in ROOTS:
        _walk(console, root, files, state)
    sums = {c: [0, 0] for c in CATEGORY_IDS}
    types = {}
    unknown = []
    items = {_ACTION[a]["category"]: [] for a in _ACTION}
    for path, size in files:
        got = classify(path)
        if got is None:
            continue
        cat, kind = got
        sums[cat][0] += size
        sums[cat][1] += 1
        if cat == "dl-saved":
            types[kind] = types.get(kind, 0) + size
        elif cat == "unknown":
            unknown.append(path)
        if cat in items:                      # never profile, personal or settings paths: they aren't kept at all
            items[cat].append((path, size))
    rows = [{"id": c["id"], "name": c["name"], "note": c["note"], "bytes": sums[c["id"]][0], "files": sums[c["id"]][1],
             "action": c.get("action")} for c in CATEGORIES if sums[c["id"]][1]]
    rows.sort(key=lambda r: (-r["bytes"], CATEGORY_IDS.index(r["id"])))
    free = _optional(console, "free_space")
    total = sum(r["bytes"] for r in rows)
    log("Storage report: %d file(s), %s in %d categor%s%s." % (len(files), size_text(total), len(rows),
        "y" if len(rows) == 1 else "ies", "; listing stopped early" if state["truncated"] else ""))
    return {"rows": rows, "types": {k: types[k] for k, _ in TYPES if k in types}, "total": total,
            "free": free if isinstance(free, int) else None, "free_note": None if isinstance(free, int) else FREE_NOTE,
            "truncated": state["truncated"] or bool(state["unreadable"]), "unknown": sorted(unknown)[:UNKNOWN_SHOWN],
            "unknown_count": len(unknown), "items": items}


def types_text(types):
    names = dict(TYPES)
    return " · ".join("%s %s" % (names[k], size_text(v)) for k, v in sorted(types.items(), key=lambda kv: -kv[1]))


def bar(n, largest, width=24):
    """A plain text bar: '#' cells for n out of the largest row."""
    if not largest or n <= 0:
        return ""
    return "#" * max(1, int(round(width * n / float(largest))))


# -- clean-up -------------------------------------------------------------------------------------------------------------------
def safe_to_delete(path, action, size=None, now=None):
    """True only when `path` is a file this clean-up may delete. Settings, personal data, the browser profile,
    Downloads lists and saved files, and anything not recognised never pass."""
    a = _ACTION.get(action)
    if a is None or not _clean_path(path):
        return False
    name = posixpath.basename(path)
    if name in NEVER_DELETE_NAMES or name.startswith("passwords") or name.startswith("autofill"):
        return False
    if path == config.SETTINGS_PATH or _under(path, NEVER_DELETE_ROOTS) or backup.rule_for(path) is not None:
        return False
    if path.startswith(DL) and not path.startswith(TRASH):
        return False
    got = classify(path)
    if got is None or got[0] != a["category"]:
        return False
    if action == "empty-trash":
        return path.startswith(TRASH)
    if action == "big-logs":
        return isinstance(size, int) and size > BIG_LOG
    if action == "icons":
        return _under(path, ICON_CACHES)
    if action == "old-parked":
        original = parked_original(path)
        when = parked_time(path)
        if not original or when is None:
            return False
        # A parked copy of a settings or personal-data file is the owner's old data: kept.
        if backup.rule_for(original) is not None or _under(original, NEVER_DELETE_ROOTS) or original == config.SETTINGS_PATH:
            return False
        if posixpath.basename(original) in NEVER_DELETE_NAMES or (original.startswith(OMNI) and classify(original) is not None
                                                                   and classify(original)[0] in ("settings", "personal")):
            return False
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return now - when > PARKED_MAX_AGE
    return False


def candidates(report, action, now=None):
    """[{"path", "size"}] this clean-up would delete, from a report (nothing is read or changed)."""
    a = _ACTION.get(action)
    if a is None:
        raise StorageError("Unknown clean-up.")
    out = [{"path": p, "size": s} for p, s in report["items"].get(a["category"], ())
           if safe_to_delete(p, action, s, now)]
    out.sort(key=lambda c: (-c["size"], c["path"]))
    return out


def confirmation(action, items):
    """The text the owner confirms: what goes and every file, one per line."""
    a = _ACTION[action]
    total = sum(i["size"] for i in items)
    head = "%s: delete %d file%s (%s) from the PS5? This can't be undone." % (
        a["name"], len(items), "" if len(items) == 1 else "s", size_text(total))
    return head, ["%s  (%s)" % (i["path"], size_text(i["size"])) for i in items]


def _delete(console, path):
    fn = getattr(console, "delete", None)
    if callable(fn):
        fn(path)
        return
    try:
        console.ftp.delete(path)
    except ftplib.error_reply as e:       # ftpsrv answers DELE with 226, which ftplib calls an odd reply
        if not str(e).startswith("226"):
            raise


def clean(console, action, items, now=None, log=lambda m: None):
    """Delete exactly the confirmed `items` (from candidates()). Each one is checked again first: still there, same size,
    and still allowed. Returns {"deleted", "bytes", "skipped"}."""
    if action not in _ACTION:
        raise StorageError("Unknown clean-up.")
    listings = {}

    def entry(path):
        parent, name = posixpath.split(path)
        if parent not in listings:
            listings[parent] = console.listing(parent) or {}
        return listings[parent].get(name)

    deleted = skipped = freed = 0
    gone = []
    for it in items:
        path, size = it.get("path"), it.get("size")
        e = entry(path) if _clean_path(path) else None
        if (e is None or e.get("dir") or e.get("size") != size or not safe_to_delete(path, action, size, now)):
            skipped += 1
            continue
        try:
            _delete(console, path)
        except ftplib.all_errors:
            skipped += 1
            continue
        gone.append((path, size))
    listings.clear()
    for path, size in gone:                # counted only when the file is really gone
        if entry(path) is None:
            deleted += 1
            freed += size
        else:
            skipped += 1
    if action == "empty-trash":
        _prune_trash_folders(console)
    log("Storage clean-up %s: %d file(s) deleted (%s), %d skipped." % (action, deleted, size_text(freed), skipped))
    return {"deleted": deleted, "bytes": freed, "skipped": skipped}


def _prune_trash_folders(console):
    """Remove folders left empty inside the trash (never .trash itself). Best effort."""
    rmd = getattr(console, "rmdir", None)
    if not callable(rmd):
        ftp = getattr(console, "ftp", None)
        rmd = getattr(ftp, "rmd", None) if ftp is not None else None
    if not callable(rmd):
        return
    folders = []
    stack = [TRASH.rstrip("/")]
    while stack and len(folders) < 2000:
        d = stack.pop()
        for name, e in (console.listing(d) or {}).items():
            if e.get("dir") and name not in (".", ".."):
                folders.append(d + "/" + name)
                stack.append(d + "/" + name)
    for d in sorted(folders, key=lambda p: -p.count("/")):
        if not d.startswith(TRASH) or console.listing(d):
            continue
        try:
            rmd(d)
        except ftplib.all_errors:
            pass
