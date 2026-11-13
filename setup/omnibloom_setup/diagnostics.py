"""Collect a diagnostics report from the PS5 for bug reports, with personal data removed.

Setup reads only technical files over FTP (Omni's start and crash logs, the Media downloads log, app versions and status,
setting flags), removes anything that could identify the user or what they browsed (web addresses, site names, IP
addresses, e-mail addresses, tokens and passwords), and saves one zip on this computer, by default in the Downloads
folder. Nothing is uploaded anywhere: the user looks at the zip and attaches it to a GitHub issue themselves.

Never read: browsing history, bookmarks, cookies, saved passwords, form data, downloads, the browser profile, or any
file the user saved.
"""
import datetime
import io
import json
import os
import posixpath
import re
import zipfile

from . import config

# Files and folders read from the PS5. Each file is capped (the newest part of a log is kept).
FILE_CAP = 512 * 1024
FILES = (
    ("omni/boot.log", "/data/omni/native/boot.log"),
    ("omni/crash.log", "/data/omni/native/crash.log"),
    ("omni/close-events.log", "/data/omni/native/close-events.log"),
    ("omni/media-downloads.log", "/data/omni/media-downloads.log"),
    ("omni/dark-style.txt", "/data/omni/dark-style.txt"),
    ("omni/quick-access.txt", "/data/omni/quick-access.txt"),
    ("omni/video-hdr-preference.txt", config.OMNI_HDR_PREF),
    ("bloom-core/status.json", "/data/hub/status.json"),
    ("payload-manager/autoload.txt", config.AUTOLOAD_PATH),
)
FOLDERS = (   # every *.json in these (small, technical)
    ("bloom-core/runtime", "/data/hub/runtime"),
    ("bloom-core/receipts", "/data/hub/receipts"),
    ("bloom-core/apps", "/data/hub/apps"),
)
NAMES_ONLY = (   # only the names of these folders' entries, never their contents
    ("omni/flags.txt", "/data/omni", lambda n: n.endswith(".flag") or n in ("omni-engine.elf",)),
    ("omni/addons.txt", "/data/homebrew/" + config.TITLE_ID + "/addons", lambda n: True),
)
NEVER = ("/data/omni/browser-profile", "/data/omni/downloads", "/data/omni/passwords", "/data/omni/vault",
         "/data/omni/history", "/data/omni/bookmarks", "/data/mastercontrol", "/data/omni-downloader/state")

# ---- redaction --------------------------------------------------------------------------------------------
_KEEP_HOSTS = {"127.0.0.1", "localhost"}
_URL = re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]{1,15})://[^\s\"'<>()\]]+")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")
_MEDIA_ID = re.compile(r"\b(vid|videoId|video_id|v|list|playlist)=([A-Za-z0-9_-]{6,})")   # what someone watched
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b")
_SECRET = re.compile(r"(?i)\b(token|key|secret|password|passwd|pass|cookie|auth|session|sid|signature|sig)(\s*[=:]\s*|\"\s*:\s*\")([^\s\",;&]+)")
# A host name: labels of letters/digits/hyphens with a known-looking top-level label. File names (boot.log, hub.elf,
# app.js) are left alone by requiring the last label not to be a common file extension.
_FILE_EXT = {"log", "txt", "json", "elf", "prx", "bin", "js", "css", "html", "htm", "png", "jpg", "webp", "svg", "ttf",
             "otf", "woff", "woff2", "flag", "cpp", "h", "inc", "py", "zip", "mp4", "webm", "conf", "pem", "so", "sprx",
             "self", "tmp", "dat", "db", "ini", "md", "xml", "plist", "cfg", "new", "off", "bak", "lock", "map", "sh"}
_HOST = re.compile(r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+([a-zA-Z]{2,24})\b")


# Real web endings: every two-letter country code, plus the common generic ones. "download.url" or "theme.changed"
# (Omnibloom intent names) and "file.before-s34" are not site names.
_TLDS = {"com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "io", "app", "dev", "tv", "gg", "me", "co", "ai",
         "xyz", "online", "site", "store", "shop", "blog", "news", "live", "video", "page", "cloud", "tech", "top", "club",
         "art", "design", "media", "social", "games", "game", "chat", "link", "world", "today", "space", "studio", "wiki",
         "fun", "pro", "mobi", "name", "asia", "travel", "jobs", "tel", "eu", "lol", "porn", "sex", "xxx", "adult", "cam"}


def _host(match):
    tld = match.group(1).lower()
    if tld in _FILE_EXT or match.group(0).lower() in _KEEP_HOSTS:
        return match.group(0)
    if not (tld in _TLDS or (len(tld) == 2 and tld.isalpha())):
        return match.group(0)
    return "<site>"


def _ip(match):
    text = match.group(0)
    parts = text.split(".")
    if text in _KEEP_HOSTS or (len(parts) == 4 and parts[0] == "127"):
        return text
    if any(int(p) > 255 for p in parts):
        return text   # a version number or similar, not an address
    return "<ip>"


def redact(text):
    """Return (clean text, counts of what was removed)."""
    counts = {}

    def sub(pattern, repl, s, what):
        out, n = pattern.subn(repl, s)
        if n:
            counts[what] = counts.get(what, 0) + n
        return out

    def url(m):
        scheme = m.group(1).lower()
        rest = m.group(0)[len(m.group(1)) + 3:]
        host = re.split(r"[/:?#]", rest, maxsplit=1)[0].lower()
        if host in _KEEP_HOSTS or host.startswith("127."):
            # local Omnibloom pages: keep host, port and path, drop the query and fragment
            return re.split(r"[?#]", m.group(0), maxsplit=1)[0]
        return "<%s-address>" % scheme

    text = sub(_SECRET, lambda m: m.group(1) + m.group(2) + "<removed>", text, "passwords, tokens and keys")
    text = sub(_URL, url, text, "web addresses")
    text = sub(_MEDIA_ID, lambda m: m.group(1) + "=<removed>", text, "video and playlist IDs")
    text = sub(_EMAIL, "<email>", text, "e-mail addresses")
    text = sub(_MAC, "<mac>", text, "hardware addresses")
    text = sub(_IPV6, "<ip6>", text, "IPv6 addresses")
    def counted(fn, what):
        def repl(m):
            r = fn(m)
            if r != m.group(0):
                counts[what] = counts.get(what, 0) + 1
            return r
        return repl

    text = _IPV4.sub(counted(_ip, "IP addresses"), text)
    text = _HOST.sub(counted(_host, "site names"), text)
    return text, counts


def _redact_json(raw):
    """Redact a JSON file: values that look personal go, structure and technical values stay."""
    try:
        data = json.loads(raw)
    except ValueError:
        return redact(raw)
    counts = {}

    def walk(v, key=""):
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                if isinstance(k, str) and "." in k and _HOST.fullmatch(k) and _host(_HOST.fullmatch(k)) == "<site>":
                    k = "<site>"; counts["site names"] = counts.get("site names", 0) + 1
                out[k] = walk(x, k)
            return out
        if isinstance(v, list):
            return [walk(x, key) for x in v]
        if isinstance(v, str):
            clean, c = redact(v)
            for what, n in c.items():
                counts[what] = counts.get(what, 0) + n
            return clean
        return v
    return json.dumps(walk(data), indent=1, ensure_ascii=False, sort_keys=True), counts


# ---- collection -------------------------------------------------------------------------------------------
def default_folder():
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    return downloads if os.path.isdir(downloads) else home


def _tail(data, cap=FILE_CAP):
    if len(data) <= cap:
        return data, False
    cut = data[-cap:]
    nl = cut.find(b"\n")
    return (cut[nl + 1:] if 0 <= nl < 4096 else cut), True


def collect(console, out_path=None, setup_version="", log=print):
    """Read the technical files, redact them, write a zip. Returns the zip's path."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_path or os.path.join(default_folder(), "omnibloom-diagnostics-%s.zip" % stamp)
    totals, notes, included = {}, [], []

    def add(z, name, text, counts, cut=False):
        z.writestr(name, text)
        included.append(name + (" (newest part only)" if cut else ""))
        for what, n in counts.items():
            totals[what] = totals.get(what, 0) + n

    def safe(path):
        return not any(path == p or path.startswith(p + "/") for p in NEVER)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path in FILES:
            if not safe(path):
                continue
            try:
                if not console.exists(path):
                    notes.append("%s: not on this PS5" % path); continue
                raw, cut = _tail(console.read(path))
            except Exception as e:   # one unreadable file never stops the report
                notes.append("%s: couldn't read (%s)" % (path, type(e).__name__)); continue
            text = raw.decode("utf-8", "replace")
            clean, counts = _redact_json(text) if name.endswith(".json") else redact(text)
            add(z, name, clean, counts, cut)
        for prefix, folder in FOLDERS:
            try:
                entries = console.listing(folder)
            except Exception:
                entries = {}
            for fname, info in sorted(entries.items()):
                if info.get("dir") or not fname.endswith(".json") or info.get("size", 0) > FILE_CAP:
                    continue
                path = folder + "/" + fname
                if not safe(path):
                    continue
                try:
                    clean, counts = _redact_json(console.read(path).decode("utf-8", "replace"))
                except Exception as e:
                    notes.append("%s: couldn't read (%s)" % (path, type(e).__name__)); continue
                add(z, prefix + "/" + fname, clean, counts)
        for name, folder, keep in NAMES_ONLY:
            try:
                entries = console.listing(folder)
            except Exception:
                entries = {}
            lines = sorted("%s%s" % (n, "/" if e.get("dir") else "") for n, e in entries.items() if keep(n))
            add(z, name, "\n".join(lines) + "\n", {})
        summary = {
            "what": "Omnibloom diagnostics report. Technical logs only, with personal data removed. Nothing was uploaded.",
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "setup_version": setup_version,
            "included": included,
            "removed": totals,
            "skipped": notes,
            "never_read": list(NEVER) + ["browsing history, bookmarks, cookies, saved passwords, form data, your downloads"],
        }
        z.writestr("README.txt", _readme(summary))
        z.writestr("summary.json", json.dumps(summary, indent=1))
    log("Diagnostics saved to %s" % out_path)
    if totals:
        log("Removed: " + ", ".join("%d %s" % (n, w) for w, n in sorted(totals.items())))
    return out_path


def _readme(s):
    lines = [
        "Omnibloom diagnostics report",
        "",
        "This zip was made by Omnibloom Setup on your computer. Nothing was sent anywhere.",
        "It holds technical logs and settings from your PS5, with personal details replaced:",
        "web addresses, site names, IP addresses, e-mail addresses, passwords and tokens.",
        "Open the files to check before you share it. To report a bug, attach this zip to an issue at",
        "https://github.com/egomortal/omnibloom/issues",
        "",
        "Created: %s   Setup: %s" % (s["created"], s["setup_version"] or "-"),
        "",
        "Included:",
    ] + ["  " + x for x in s["included"]] + ["", "Removed:"] + (
        ["  %d %s" % (n, w) for w, n in sorted(s["removed"].items())] or ["  nothing personal was found"]) + [
        "", "Not on this PS5 or unreadable:"] + (["  " + x for x in s["skipped"]] or ["  -"]) + [
        "", "Never read:"] + ["  " + x for x in s["never_read"]] + [""]
    return "\n".join(lines)
