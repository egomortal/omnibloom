"""Collect a diagnostics bundle from the PS5 for bug reports, with personal data redacted.

Setup reads only technical files over FTP (Omni's title, starter, crash and video logs, the Media downloads log,
Bloom Core's logs, status and app receipts, the downloader engine's trace), keeps the newest 2 MB of each log, runs
everything through redaction.Redactor (web addresses, IP/MAC/e-mail addresses, tokens, home folders and user names),
and saves one zip on this computer. Nothing is uploaded: the user looks at the preview, saves the zip and attaches it
to a GitHub issue themselves.

Two steps so the window can show what will be saved first:
    bundle = gather(console)          # reads the PS5, redacts, keeps everything in memory
    preview(bundle), file_list(bundle)
    save(bundle, path)                # writes path.part, then renames it (no half zip is ever left)
collect() does both (the CLI and the older one-click job use it).

Never read (enforced by content_allowed() on every read, and tested): bookmarks, history, passwords, cookies, the
browser profile, the reading list, keyboard words, sessions, apps.json, screenshots, downloads, uploads, autofill,
the downloader's saved state, and the content of any *.txt settings file (only its name is listed).
"""
import datetime
import fnmatch
import json
import os
import posixpath
import zipfile

from . import config
from .redaction import RULES, Redactor, pc_user_names

FORMAT = "omnibloom-diagnostics"
FORMAT_VERSION = 2
LOG_CAP = 2 * 1024 * 1024           # newest 2 MB of each log
JSON_CAP = 256 * 1024               # status / receipt files are small; anything bigger is skipped
TOTAL_CAP = 32 * 1024 * 1024        # the whole bundle, before compression
FOLDER_MAX_FILES = 16
MANIFEST_NAME = "manifest.json"

NATIVE = "/data/omni/native/"
DL_NATIVE = "/data/omni-downloader/jdownloader/native/"

# Logs: (name in the zip, console path). Found by grepping the Omni sources (OmniNativeTitle.cpp, starter/main.c,
# launcher-child.cpp, OmniGpuPresent.cpp, OmniGpuVideo.cpp, apply_media_diag.py, the JDownloader adaptation patch).
LOGS = (
    ("omni/boot.log", NATIVE + "boot.log"),                 # the title process's own log
    ("omni/starter.log", NATIVE + "starter.log"),
    ("omni/crash.log", NATIVE + "crash.log"),               # crash marker + details (crash-diagnostics.flag)
    ("omni/close-events.log", NATIVE + "close-events.log"),
    ("omni/gpu-present.log", NATIVE + "gpu-present.log"),
    ("omni/gpu-video.log", NATIVE + "gpu-video.log"),
    ("omni/video-fps.log", NATIVE + "video-fps.log"),
    ("omni/media-downloads.log", "/data/omni/media-downloads.log"),
    ("omni-downloader/java25-vm-trace.log", DL_NATIVE + "java25-vm-trace.log"),
)
# Folders of logs: (zip prefix, console folder, name patterns). Newest-named first, at most FOLDER_MAX_FILES each.
LOG_FOLDERS = (
    ("bloom-core/logs", config.LOGS_DIR.rstrip("/"), ("*.log",)),
    ("bloom-core/crash", config.CRASH_DIR.rstrip("/"), ("*.log", "*.json")),
)
# Small technical JSON (status, which apps run on which port, install receipts with versions).
JSON_FILES = (("bloom-core/status.json", "/data/hub/status.json"),)
JSON_FOLDERS = (
    ("bloom-core/runtime", "/data/hub/runtime"),
    ("bloom-core/apps", "/data/hub/apps"),
    ("bloom-core/receipts", "/data/hub/receipts"),
)
# The one settings-style text file whose content is read: the payload loader's list (payload paths only).
TEXT_ALLOWED = (config.AUTOLOAD_PATH,)
TEXT_FILES = (("payload-manager/autoload.txt", config.AUTOLOAD_PATH),)
# Names only, never contents: (zip name, console folder, which names).
NAMES_ONLY = (
    ("omni/flags.txt", "/data/omni", ("*.flag",)),
    ("omni/settings-files.txt", "/data/omni", ("*.txt",)),
    ("omni/native-files.txt", "/data/omni/native", ("*",)),
    ("omni/addons.txt", "/data/homebrew/" + config.TITLE_ID + "/addons", ("*",)),
)

# Never read, never even listed by name.
NEVER_DIRS = ("browser-profile", "downloads", "screenshots", "uploads", "reading-list", "vault", "passwords",
              "history", "bookmarks", "cookies", "sessions")
NEVER_NAMES = ("bookmarks*", "history*", "passwords*", "password*", "cookies*", "cookie*", "kb-words*", "session*",
               "autofill*", "apps.json", "quick-access*", "reading-list*", "*.sqlite", "*.db", "*.png", "*.jpg",
               "*.jpeg", "*.webp", "*.mp4", "*.webm", "*.mkv")
NEVER_ROOTS = ("/data/omni-downloader/state", "/data/omni-downloader/downloads", "/data/mastercontrol",
               "/user/home", "/data/omni/browser-profile")
NEVER = ("bookmarks", "history", "passwords", "cookies", "browser-profile", "reading-list content", "kb-words",
         "sessions", "apps.json", "contents of *.txt settings files (names only)", "screenshots", "downloads",
         "uploads", "autofill", "the downloader's saved jobs and links")


def name_allowed(name):
    n = name.lower()
    return n not in NEVER_DIRS and not any(fnmatch.fnmatchcase(n, p) for p in NEVER_NAMES)


def path_allowed(path):
    """May this path's name appear in the bundle? (Not about reading its content.)"""
    p = posixpath.normpath(path).lower()
    if any(p == r or p.startswith(r + "/") for r in NEVER_ROOTS):
        return False
    return all(name_allowed(part) for part in p.strip("/").split("/") if part)


def content_allowed(path):
    """May Setup read this file's bytes? Never-list paths no; *.txt only when it's in TEXT_ALLOWED."""
    if not path_allowed(path):
        return False
    if path.lower().endswith(".txt") and path not in TEXT_ALLOWED:
        return False
    return True


class _Reader:
    """Every console read for a bundle goes through here: one listing per folder, the never-list checked first."""

    def __init__(self, console):
        self.console = console
        self.listings = {}

    def listing(self, folder):
        if folder not in self.listings:
            try:
                self.listings[folder] = self.console.listing(folder) or {}
            except Exception:
                self.listings[folder] = {}
        return self.listings[folder]

    def entry(self, path):
        parent, name = posixpath.split(path)
        return self.listing(parent).get(name)

    def read(self, path, cap, tail=True):
        """(bytes, truncated). Logs keep their newest `cap` bytes; other files over `cap` raise ValueError."""
        if not content_allowed(path):
            raise PermissionError("not collected: " + path)
        entry = self.entry(path) or {}
        size = entry.get("size")
        reader = getattr(self.console, "read_from", None)
        if tail and isinstance(size, int) and size > cap and callable(reader):
            data = reader(path, size - cap)
        elif not tail and isinstance(size, int) and size > cap:
            raise ValueError("too big")
        else:
            data = self.console.read(path)
        if len(data) <= cap:
            return data, bool(isinstance(size, int) and size > len(data) and tail and size > cap)
        if not tail:
            raise ValueError("too big")
        cut = data[-cap:]
        nl = cut.find(b"\n")
        return (cut[nl + 1:] if 0 <= nl < 4096 else cut), True


def _optional(console, name):
    fn = getattr(console, name, None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception:
        return None


def _versions(console, setup_version):
    from . import installer
    try:
        installed = installer.installed_apps(console)
    except Exception:
        installed = {}
    apps = {}
    for app_id, rec in sorted(installed.items()):
        apps[app_id] = {k: rec.get(k) for k in ("name", "version", "package", "installed_at", "setup_version", "port")
                        if rec.get(k) is not None}
        if rec.get("history"):
            apps[app_id]["earlier_versions"] = [h.get("version") for h in rec["history"] if isinstance(h, dict)]
    free = _optional(console, "free_space")
    firmware = _optional(console, "firmware")
    return {
        "setup_version": setup_version,
        "installed_apps": apps,
        "free_space_bytes": free,
        "free_space_note": None if free is not None else "Setup's FTP connection can't measure free space.",
        "firmware": firmware,
        "firmware_note": None if firmware else "Setup doesn't read the firmware version (Omnibloom is tested on %s)."
        % config.TESTED_FIRMWARE,
    }


def gather(console, setup_version=None, user_names=None, salt=None, log=lambda m: None):
    """Read and redact everything; nothing is written. Returns a bundle dict for preview() and save()."""
    setup_version = setup_version or config.SETUP_VERSION
    users = list(user_names or ()) + pc_user_names()
    red = Redactor(salt=salt, user_names=users)
    rd = _Reader(console)
    entries, skipped = [], []
    total = [0]

    def add(name, source, text, truncated=False):
        data = text.encode("utf-8")
        if total[0] + len(data) > TOTAL_CAP:
            skipped.append("%s: left out (the bundle is already %d MB)" % (source, TOTAL_CAP // (1024 * 1024)))
            return
        total[0] += len(data)
        entries.append({"name": name, "source": source, "bytes": len(data), "truncated": truncated, "text": text})

    def take(name, source, cap, tail, json_file=False):
        if not path_allowed(source) or not content_allowed(source):
            return
        entry = rd.entry(source)
        if entry is None or entry.get("dir"):
            skipped.append("%s: not on this PS5" % source)
            return
        try:
            raw, cut = rd.read(source, cap, tail=tail)
        except ValueError:
            skipped.append("%s: left out (bigger than %d KB)" % (source, cap // 1024))
            return
        except Exception as e:     # one unreadable file never stops the bundle
            skipped.append("%s: couldn't read (%s)" % (source, type(e).__name__))
            return
        text = raw.decode("utf-8", "replace")
        if json_file:
            text = _redact_json(text, red)
        else:
            text = red.redact(text)
        add(name, source, text, cut)

    for name, path in LOGS:
        take(name, path, LOG_CAP, True)
    for prefix, folder, patterns in LOG_FOLDERS:
        names = sorted((n for n, e in rd.listing(folder).items()
                        if not e.get("dir") and any(fnmatch.fnmatchcase(n.lower(), p) for p in patterns)
                        and name_allowed(n)), reverse=True)
        for n in names[:FOLDER_MAX_FILES]:
            take(prefix + "/" + n, folder + "/" + n, LOG_CAP, True, json_file=n.endswith(".json"))
        if len(names) > FOLDER_MAX_FILES:
            skipped.append("%s: %d older files left out" % (folder, len(names) - FOLDER_MAX_FILES))
    for name, path in JSON_FILES:
        take(name, path, JSON_CAP, False, json_file=True)
    for prefix, folder in JSON_FOLDERS:
        for n, e in sorted(rd.listing(folder).items()):
            if not e.get("dir") and n.endswith(".json") and name_allowed(n):
                take(prefix + "/" + n, folder + "/" + n, JSON_CAP, False, json_file=True)
    for name, path in TEXT_FILES:
        take(name, path, JSON_CAP, False)
    for name, folder, patterns in NAMES_ONLY:
        found = sorted("%s%s" % (n, "/" if e.get("dir") else "") for n, e in rd.listing(folder).items()
                       if name_allowed(n) and path_allowed(folder + "/" + n)
                       and any(fnmatch.fnmatchcase(n.lower(), p) for p in patterns))
        add(name, folder + " (names only)", red.redact("\n".join(found) + "\n" if found else "(none)\n"))
    versions = _versions(console, setup_version)
    add("versions.json", "receipts in " + config.RECEIPTS_DIR, _redact_json(json.dumps(versions), red))
    bundle = {
        "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "setup_version": setup_version,
        "entries": entries,
        "skipped": skipped,
        "removed": dict(sorted(red.counts.items())),
        "versions": versions,
    }
    log("Diagnostics: %d file(s) read, personal details removed: %s" % (
        len(entries), ", ".join("%d %s" % (n, w) for w, n in bundle["removed"].items()) or "none found"))
    return bundle


def _redact_json(raw, red):
    """Redact a JSON file: every string (keys that are site names too) goes through the redactor; numbers stay."""
    try:
        data = json.loads(raw)
    except ValueError:
        return red.redact(raw)

    def walk(v):
        if isinstance(v, dict):
            return {red.redact(k) if isinstance(k, str) else k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            return red.redact(v)
        return v
    return json.dumps(walk(data), indent=1, ensure_ascii=False, sort_keys=True) + "\n"


# ---- showing it -------------------------------------------------------------------------------------------
def _size(n):
    return "%.1f MB" % (n / 1048576.0) if n >= 1048576 else "%d KB" % ((n + 1023) // 1024)


def file_list(bundle):
    """One line per file that will be in the zip."""
    lines = ["%s  (%s%s)" % (e["name"], _size(e["bytes"]), ", newest 2 MB only" if e["truncated"] else "")
             for e in bundle["entries"]]
    return lines + [MANIFEST_NAME, "README.txt"]


def preview(bundle, lines=40, per_file=12):
    """The first lines of the redacted logs, as they will be saved."""
    out = []
    for e in bundle["entries"]:
        if not e["name"].endswith(".log") or not e["text"].strip():
            continue
        out.append("== %s ==" % e["name"])
        out.extend(e["text"].splitlines()[:per_file])
        if len(out) >= lines:
            break
    if not out:
        out = ["(no Omni logs on this PS5 yet)"]
    return "\n".join(out[:lines])


# ---- saving -----------------------------------------------------------------------------------------------
def default_folder():
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    return downloads if os.path.isdir(downloads) else home


def default_path(folder=None, now=None):
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    return os.path.join(folder or default_folder(), "omnibloom-diagnostics-%s.zip" % stamp)


def manifest(bundle):
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "created": bundle["created"],
        "setup_version": bundle["setup_version"],
        "what": "Omnibloom diagnostics: technical logs and versions from a PS5, personal data redacted. "
                "Made on the user's PC; nothing was uploaded.",
        "files": [{"name": e["name"], "source": e["source"], "bytes": e["bytes"], "newest_part_only": e["truncated"]}
                  for e in bundle["entries"]],
        "skipped": bundle["skipped"],
        "redaction_rules": list(RULES),
        "removed": bundle["removed"],
        "never_collected": list(NEVER),
        "caps": {"log_bytes": LOG_CAP, "json_bytes": JSON_CAP, "total_bytes": TOTAL_CAP},
    }


def save(bundle, dest):
    """Write the zip to dest (via dest.part, renamed when complete). Returns dest."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for e in bundle["entries"]:
                z.writestr(e["name"], e["text"])
            z.writestr(MANIFEST_NAME, json.dumps(manifest(bundle), indent=1, ensure_ascii=False) + "\n")
            z.writestr("README.txt", _readme(bundle))
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return dest


def collect(console, out_path=None, setup_version="", log=print, user_names=None):
    """gather() + save() in one go. Returns the zip's path."""
    bundle = gather(console, setup_version=setup_version, user_names=user_names, log=lambda m: None)
    path = save(bundle, out_path or default_path())
    log("Diagnostics saved to %s" % path)
    if bundle["removed"]:
        log("Removed: " + ", ".join("%d %s" % (n, w) for w, n in bundle["removed"].items()))
    return path


def _readme(b):
    lines = [
        "Omnibloom diagnostics bundle",
        "",
        "Made by Omnibloom Setup on your computer. Nothing was sent anywhere.",
        "It holds technical logs and versions from your PS5, with personal details replaced:",
        "web addresses, site names, IP, MAC and e-mail addresses, passwords, tokens, home folders and user names.",
        "Open the files to check before you share it. To report a bug, attach this zip to an issue at",
        "https://github.com/egomortal/omnibloom/issues",
        "",
        "Created: %s   Setup: %s" % (b["created"], b["setup_version"] or "-"),
        "",
        "Included:",
    ] + ["  " + x for x in file_list(b)[:-2]] + ["", "Removed:"] + (
        ["  %d %s" % (n, w) for w, n in b["removed"].items()] or ["  nothing personal was found"]) + [
        "", "Not on this PS5, left out or unreadable:"] + (["  " + x for x in b["skipped"]] or ["  -"]) + [
        "", "Redaction rules:"] + ["  - " + r for r in RULES] + [
        "", "Never collected:"] + ["  " + x for x in NEVER] + [""]
    return "\n".join(lines)
