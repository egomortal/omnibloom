"""Push a user add-on (.zip or folder) to Omni, list the ones Setup put there, remove or roll one back (S12).

How Omni loads add-ons (OMNI_ADDONS_V1: engine/entry/OmniAddons.h + OmniAddonsCore.h, cap from OMNI_ADDON_CAP_40_V1):
  /app0/addons/<id>/                 bundled in the title (on the PS5's FTP: /data/homebrew/<title id>/addons/)
  /data/omni/addons/bundled/<id>/    installed by Setup: this is where pushed add-ons go
  /data/omni/addons/dev/<id>/        developer add-ons, only while /data/omni/addons-dev.flag exists
Folders are read in that order, each sorted by name; a folder name that isn't a valid id is skipped (so the
"<id>.uploading-...", "<id>.prev" and "<id>.removed-..." names used here are never loaded), the first folder
with an id wins (a title add-on can't be replaced from /data), and after 40 add-ons the rest are not loaded.
A folder holds manifest.json (parseManifest's rules, mirrored in validate_manifest) and the .js / .css files
it lists; Omni reads nothing else from it, so a package may only add licence / read-me text beside them.

Everything is checked here on the PC first with the console's own limits, then uploaded through the normal
verified FTP upload into a temporary folder name and renamed into place in one step. The earlier version is
kept as <id>.prev (for Roll back); Remove renames to <id>.removed-<time>. Nothing on the PS5 is deleted.
"""
import io
import json
import os
import posixpath
import re
import stat
import time
import zipfile
from collections import namedtuple

from . import config

# -- the loader's limits (OmniAddonsCore.h) ----------------------------------------------------------------------
MAX_ADDONS = 40                    # OMNI_ADDON_CAP_40_V1
MAX_MANIFEST = 64 * 1024
MAX_JS_FILE = 1024 * 1024
MAX_JS_TOTAL = 2 * 1024 * 1024
MAX_CSS_TOTAL = 512 * 1024
MAX_FILES = 8                      # per list (js, css)
MAX_PATTERNS = 32
MAX_HOSTS = 16
MAX_SETTINGS = 32
MAX_CHOICES = 16
MAX_TEXT_SETTING = 1024
# -- Setup's own package limits (beyond what the loader reads) ---------------------------------------------------
MAX_DOC = 256 * 1024               # one licence / read-me file
MAX_PACKAGE = 4 * 1024 * 1024      # all files together
MAX_PACKAGE_FILES = 40
MAX_DEPTH = 4
MAX_ZIP_RATIO = 200                # a member that inflates more than this is refused (zip bomb)

USER_ROOT = "/data/omni/addons/bundled/"
DEV_ROOT = "/data/omni/addons/dev/"
DEV_FLAG = "/data/omni/addons-dev.flag"
TITLE_ROOT = "/data/homebrew/" + config.TITLE_ID + "/addons/"
TITLE_ADDONS_ASSUMED = 26          # the title ships 26; used when its folder can't be listed
# Ids the title ships (fallback when its folder can't be listed). A user add-on with one of these never loads.
KNOWN_BUNDLED = frozenset((
    "audio-tools", "consent-reject", "dark-reader", "image-hold-zoom", "link-hints", "omni-auto-theme",
    "omni-clearurls", "omni-form-saver", "omni-page-outline", "omni-reader-view", "omni-recipe-mode",
    "omni-resume-videos", "omni-search-blocklist", "omni-site-redirects", "omni-sponsorblock", "omni-video-fit",
    "omni-video-speed", "omni-youtube-comfort", "subtitle-style",
))
UPLOADING = ".uploading-"
PREV = ".prev"
REMOVED = ".removed-"

DOC_EXTS = (".md", ".txt")
DOC_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "README", "AUTHORS")
IMAGE_EXTS = (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp", ".ico")
JUNK = ("__MACOSX/", ".DS_Store", "Thumbs.db", "desktop.ini")


class AddonError(Exception):
    """A package or console state Setup refuses; the message is for the user."""


Package = namedtuple("Package", "manifest files raw_manifest skipped warnings")   # files: {relpath: bytes}
Installed = namedtuple("Installed", "id name version ok why has_prev")


# -- names and patterns (validId, validFile, validHostName, localHost, normalizePattern) ----------------------
def valid_id(s):
    if not isinstance(s, str) or not s or len(s) > 40 or s[0] == "-" or s[-1] == "-":
        return False
    return all("a" <= c <= "z" or "0" <= c <= "9" or c == "-" for c in s)


_FILE_CHARS = re.compile(r"[A-Za-z0-9._/-]+\Z")


def valid_file(s, ext):
    if not isinstance(s, str) or not s or len(s) > 100 or s[0] == "/" or ".." in s or "//" in s:
        return False
    return bool(_FILE_CHARS.match(s)) and len(s) > len(ext) and s.endswith(ext)


def valid_host_name(h):
    if not h or len(h) > 253 or h[0] == "." or h[-1] == "." or ".." in h:
        return False
    return all("a" <= c <= "z" or "0" <= c <= "9" or c in "-." for c in h)


def local_host(h):
    if h == "localhost" or h.endswith(".localhost") or h.endswith(".local") or h == "0.0.0.0" or ":" in h:
        return True
    return bool(h) and all(c.isdigit() and c.isascii() or c == "." for c in h)


def _lower(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def normalize_pattern(p):
    """(normalized, None) or (None, why), exactly as OmniAddonsCore::normalizePattern."""
    if p == "<all_urls>":
        p = "*://*/*"
    sep = p.find("://")
    if sep < 0:
        return None, "no scheme in pattern"
    scheme = _lower(p[:sep])
    if scheme not in ("http", "https", "*"):
        return None, "only http, https or * patterns are allowed"
    rest = p[sep + 3:]
    slash = rest.find("/")
    if slash < 0:
        return None, "pattern has no path"
    host, path = _lower(rest[:slash]), rest[slash:]
    if not host:
        return None, "pattern has no host"
    if host != "*":
        if ":" in host:
            return None, "ports and IP addresses are not allowed in patterns"
        h = host[2:] if host.startswith("*.") else host
        if not valid_host_name(h):
            return None, "bad host in pattern"
        if local_host(h):
            return None, "local addresses are not allowed"
    if len(path.encode("utf-8")) > 200:
        return None, "pattern path too long"
    for b in path.encode("utf-8"):
        if b < 0x21 or b in (0x22, 0x5C) or b >= 0x7F:
            return None, "bad character in pattern path"
    return scheme + "://" + host + path, None


# -- manifest (parseManifest + readSetting) -----------------------------------------------------------------------
def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key %r" % k)
        d[k] = v
    return d


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(m, key, mx, required):
    if key not in m:
        if required:
            raise AddonError("manifest needs " + key)
        return None
    v = m[key]
    if not isinstance(v, str) or len(v.encode("utf-8")) > mx or any(ord(c) < 0x20 for c in v):
        raise AddonError("bad " + key)
    return v


def _str_list(m, key, mx, what):
    v = m.get(key)
    if v is None:
        return []
    if not isinstance(v, list):
        raise AddonError(what + " must be a list")
    if not all(isinstance(e, str) for e in v):
        raise AddonError(what + " must hold strings")
    if len(v) > mx:
        raise AddonError("too many " + what)
    return list(v)


def _setting(s):
    if not isinstance(s, dict):
        raise AddonError("each setting must be an object")
    key, typ, _label = _text(s, "key", 40, True), _text(s, "type", 10, True), _text(s, "label", 80, True)
    if not key:
        raise AddonError("empty setting key")
    if not all("a" <= c <= "z" or "A" <= c <= "Z" or "0" <= c <= "9" or c == "_" for c in key):
        raise AddonError("bad setting key " + key)
    d = s.get("default")
    if typ == "bool":
        if not isinstance(d, bool):
            raise AddonError("setting %s: bool default" % key)
    elif typ == "range":
        mn, mx = s.get("min"), s.get("max")
        if not (_num(d) and _num(mn) and _num(mx)) or mn >= mx:
            raise AddonError("setting %s: range needs number default, min < max" % key)
        if d < mn or d > mx:
            raise AddonError("setting %s: default outside min..max" % key)
    elif typ == "choice":
        choices = _str_list(s, "choices", MAX_CHOICES, "choices")
        labels = _str_list(s, "labels", MAX_CHOICES, "labels")
        if not choices:
            raise AddonError("setting %s: choices needed" % key)
        if labels and len(labels) != len(choices):
            raise AddonError("setting %s: labels must match choices" % key)
        if any(len(c.encode("utf-8")) > 80 for c in choices):
            raise AddonError("setting %s: choice too long" % key)
        if not isinstance(d, str) or d not in choices:
            raise AddonError("setting %s: default must be one of the choices" % key)
    elif typ == "text":
        if not isinstance(d, str) or len(d.encode("utf-8")) > MAX_TEXT_SETTING:
            raise AddonError("setting %s: text default" % key)
    else:
        raise AddonError("setting %s: unknown type %s" % (key, typ))
    return key


def validate_manifest(raw):
    """The parsed manifest (a dict with normalized matches/excludes/hosts and defaults filled in), or AddonError
    with the reason Omni would log."""
    if len(raw) > MAX_MANIFEST:
        raise AddonError("manifest.json is too big")
    try:
        m = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dupes)
    except (UnicodeDecodeError, ValueError) as e:
        raise AddonError("manifest.json: %s" % e)
    if not isinstance(m, dict):
        raise AddonError("manifest.json: not an object")
    mv = m.get("manifest_version", 1)
    if not _num(mv) or mv != 1:
        raise AddonError("manifest_version must be 1")
    out = {"id": _text(m, "id", 40, True), "name": _text(m, "name", 60, True), "version": _text(m, "version", 24, True),
           "licence": _text(m, "licence", 60, True), "source": _text(m, "source", 300, False) or "",
           "description": _text(m, "description", 300, False) or "",
           "run_at": _text(m, "run_at", 20, False) or "document_end"}
    if not valid_id(out["id"]):
        raise AddonError("bad id")
    if out["run_at"] not in ("document_start", "document_end", "document_idle"):
        raise AddonError("run_at must be document_start, document_end or document_idle")
    if out["source"] and not out["source"].startswith("https://"):
        raise AddonError("source must be an https URL")
    raw_matches = _str_list(m, "matches", MAX_PATTERNS, "matches")
    raw_excludes = _str_list(m, "excludes", MAX_PATTERNS, "excludes")
    out["js"] = _str_list(m, "js", MAX_FILES, "js files")
    out["css"] = _str_list(m, "css", MAX_FILES, "css files")
    hosts = _str_list(m, "hosts", MAX_HOSTS, "hosts")
    if not raw_matches:
        raise AddonError("matches needed")
    for key, src in (("matches", raw_matches), ("excludes", raw_excludes)):
        out[key] = []
        for p in src:
            n, why = normalize_pattern(p)
            if why:
                raise AddonError(why)
            out[key].append(n)
    if not out["js"] and not out["css"]:
        raise AddonError("an add-on needs js or css files")
    for f in out["js"]:
        if not valid_file(f, ".js"):
            raise AddonError("bad js file name " + f)
    for f in out["css"]:
        if not valid_file(f, ".css"):
            raise AddonError("bad css file name " + f)
    out["hosts"] = []
    for h in hosts:
        h = _lower(h)
        bare = h[2:] if h.startswith("*.") else h
        if not valid_host_name(bare) or local_host(bare) or "." not in bare:
            raise AddonError("bad fetch host " + h)
        out["hosts"].append(h)
    for k, default in (("all_frames", False), ("default_on", False), ("private_safe", False),
                       ("quick_switch", False), ("live_toggle", True)):
        v = m.get(k, default)
        if not isinstance(v, bool):
            raise AddonError(k + " must be true or false")
        out[k] = v
    level = _text(m, "css_level", 10, False) or "user"
    if level not in ("user", "author"):
        raise AddonError("css_level must be user or author")
    out["css_level"] = level
    keys = []
    if "settings" in m:
        if not isinstance(m["settings"], list):
            raise AddonError("settings must be a list")
        for s in m["settings"]:
            if len(keys) >= MAX_SETTINGS:
                raise AddonError("too many settings")
            k = _setting(s)
            if k in keys:
                raise AddonError("duplicate setting " + k)
            keys.append(k)
    out["settings"] = keys
    return out


# -- packages (.zip or folder) ---------------------------------------------------------------------------------------
def _junk(name):
    return name.startswith("__MACOSX/") or posixpath.basename(name) in JUNK


def _check_path(name):
    """A package member's relative path: safe on the PS5's FTP and inside the add-on folder."""
    if not name or "\\" in name or name.startswith("/") or ":" in name or "\x00" in name:
        raise AddonError("unsafe path in package: %r" % name)
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise AddonError("unsafe path in package: %r" % name)
    if len(parts) > MAX_DEPTH:
        raise AddonError("%s: folders nested too deep" % name)
    if len(name) > 100 or not _FILE_CHARS.match(name) or any(p.startswith(".") for p in parts):
        raise AddonError("%s: file names may use only letters, digits, . _ - and / (no hidden files)" % name)


def _kind(name):
    base = posixpath.basename(name)
    low = base.lower()
    if name == "manifest.json":
        return "manifest"
    if low.endswith(".js"):
        return "js"
    if low.endswith(".css"):
        return "css"
    if low.endswith(".json"):
        return "json"
    if low.endswith(DOC_EXTS) or base.split(".")[0].upper() in DOC_NAMES and "." not in base:
        return "doc"
    if low.endswith(IMAGE_EXTS):
        raise AddonError("%s: Omni add-ons can't load images from their folder (put them in the CSS as data: URLs)"
                         % name)
    raise AddonError("%s: file type not allowed (only .js, .css, .json, .md, .txt and licence files)" % name)


def _cap_for(kind):
    return {"manifest": MAX_MANIFEST, "js": MAX_JS_FILE, "css": MAX_CSS_TOTAL, "json": MAX_MANIFEST}.get(kind, MAX_DOC)


def _read_zip(path):
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        raise AddonError("not a readable .zip: %s" % e)
    raw, skipped = {}, []
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_PACKAGE_FILES * 3:
            raise AddonError("the .zip holds too many entries")
        for info in infos:
            name = info.filename
            if _junk(name):
                skipped.append(name)
                continue
            if "\\" in name or name.startswith("/") or ":" in name or ".." in name.split("/"):
                raise AddonError("unsafe path in package: %r" % name)      # zip-slip, before any folder is stripped
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise AddonError("%s: links are not allowed in a package" % name)
            if info.flag_bits & 1:
                raise AddonError("%s: encrypted .zip members are not supported" % name)
            if info.is_dir():
                _check_path(name.rstrip("/"))
                continue
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise AddonError("%s: unsupported compression" % name)
            raw[name] = info
        root = _common_root(list(raw))
        files, total = {}, 0
        for name, info in raw.items():
            rel = name[len(root):]
            _check_path(rel)
            cap = _cap_for(_kind(rel))
            if info.file_size > cap:
                raise AddonError("%s is too big (%d bytes, at most %d)" % (rel, info.file_size, cap))
            if info.compress_size and info.file_size / info.compress_size > MAX_ZIP_RATIO and info.file_size > 65536:
                raise AddonError("%s: compression ratio too high" % rel)
            with zf.open(info) as f:
                data = f.read(cap + 1)
            if len(data) > cap or len(data) != info.file_size:
                raise AddonError("%s: size doesn't match the .zip directory" % rel)
            total += len(data)
            if total > MAX_PACKAGE:
                raise AddonError("the package is larger than %d MiB" % (MAX_PACKAGE // (1024 * 1024)))
            files[rel] = data
    return files, skipped


def _common_root(names):
    """'folder/' when every file is inside one top folder and manifest.json isn't at the top, else ''."""
    if not names or "manifest.json" in names:
        return ""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        return tops.pop() + "/"
    return ""


def _read_folder(path):
    files, skipped, total = {}, [], 0
    base = os.path.realpath(path)
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        for d in list(dirnames):
            if os.path.islink(os.path.join(dirpath, d)):
                raise AddonError("%s: links are not allowed in a package" % d)
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            if _junk(rel):
                skipped.append(rel)
                continue
            if os.path.islink(full) or not os.path.isfile(full):
                raise AddonError("%s: links are not allowed in a package" % rel)
            _check_path(rel)
            cap = _cap_for(_kind(rel))
            if os.path.getsize(full) > cap:
                raise AddonError("%s is too big (at most %d bytes)" % (rel, cap))
            with open(full, "rb") as f:
                data = f.read(cap + 1)
            if len(data) > cap:
                raise AddonError("%s is too big (at most %d bytes)" % (rel, cap))
            total += len(data)
            if total > MAX_PACKAGE:
                raise AddonError("the package is larger than %d MiB" % (MAX_PACKAGE // (1024 * 1024)))
            files[rel] = data
    return files, skipped


def load_package(path):
    """Reads and fully checks a .zip or a folder with the console's rules. Returns a Package or raises AddonError."""
    if os.path.isdir(path):
        files, skipped = _read_folder(path)
    elif os.path.isfile(path):
        files, skipped = _read_zip(path)
    else:
        raise AddonError("no such file or folder")
    if len(files) > MAX_PACKAGE_FILES:
        raise AddonError("the package has more than %d files" % MAX_PACKAGE_FILES)
    lower = {}
    for n in files:
        if n.lower() in lower:
            raise AddonError("%s and %s differ only in case" % (lower[n.lower()], n))
        lower[n.lower()] = n
    if "manifest.json" not in files:
        raise AddonError("manifest.json is missing (it must be at the top of the package)")
    m = validate_manifest(files["manifest.json"])
    js_total = css_total = 0
    for f in m["js"]:
        if f not in files:
            raise AddonError(f + " missing or too big")
        js_total += len(files[f])
        if js_total > MAX_JS_TOTAL:
            raise AddonError("scripts too big")
    for f in m["css"]:
        if f not in files:
            raise AddonError(f + " missing or too big")
        css_total += len(files[f])
        if css_total > MAX_CSS_TOTAL:
            raise AddonError("styles too big")
    listed = set(m["js"]) | set(m["css"])
    warnings = ["%s is not listed in manifest.json, so Omni won't load it." % n
                for n in sorted(files) if _kind(n) in ("js", "css") and n not in listed]
    return Package(m, files, files["manifest.json"], skipped, warnings)


# -- what the add-on can do ------------------------------------------------------------------------------------
def _pattern_text(p):
    return "every website" if p == "*://*/*" else p


def access_summary(m):
    """Plain lines describing what the add-on can reach, for the confirmation."""
    lines = ["%s %s (id %s), licence %s." % (m["name"], m["version"], m["id"], m["licence"])]
    lines.append("Runs on: " + ", ".join(_pattern_text(p) for p in m["matches"]) + ".")
    if m["excludes"]:
        lines.append("Never on: " + ", ".join(m["excludes"]) + ".")
    lines.append("Private tabs: " + ("yes, it also runs there." if m["private_safe"] else "no."))
    lines.append("Can fetch from: " + (", ".join("https://" + h for h in m["hosts"]) if m["hosts"]
                                       else "nowhere (no network hosts declared).") )
    if m["all_frames"]:
        lines.append("Also runs inside embedded frames.")
    if m["css_level"] == "author" and m["css"]:
        lines.append("Its styles can override the page's own.")
    lines.append("Starts " + ("ON for every matching site." if m["default_on"] else "off (switch it on in Omni's Add-ons)."))
    lines.append("Files: %s." % ", ".join(m["js"] + m["css"]))
    lines.append("Omni never runs add-ons on its own pages or on local addresses.")
    return lines


# -- the console side ----------------------------------------------------------------------------------------------
def _dirs(console, root):
    return {n for n, e in console.listing(root).items() if e.get("dir", True)}


def console_state(console):
    """{'title': ids, 'title_listed': bool, 'user': ids, 'dev': ids, 'names': every name in USER_ROOT}"""
    title = {n for n in _dirs(console, TITLE_ROOT) if valid_id(n)}
    names = set(console.listing(USER_ROOT))
    user = {n for n in _dirs(console, USER_ROOT) if valid_id(n)}
    dev = {n for n in _dirs(console, DEV_ROOT) if valid_id(n)} if console.exists(DEV_FLAG) else set()
    return {"title": title, "title_listed": bool(title), "user": user, "dev": dev, "names": names}


def loaded_count(st):
    """How many add-ons Omni would load now (unique ids over its folders)."""
    title = st["title"] if st["title_listed"] else set(KNOWN_BUNDLED)
    extra = 0 if st["title_listed"] else max(0, TITLE_ADDONS_ASSUMED - len(title))
    return len(title | st["user"] | st["dev"]) + extra


def plan(console, pkg, update=False):
    """Checks the package against the console. Returns a dict for the confirmation; raises AddonError when the
    console would refuse it or when it would replace a user add-on without update=True."""
    st = console_state(console)
    aid = pkg.manifest["id"]
    title = st["title"] if st["title_listed"] else set(KNOWN_BUNDLED)
    if aid in title or aid in KNOWN_BUNDLED:
        raise AddonError("%s is the id of an add-on that comes with Omni; Omni would always load its own copy. "
                         "Give the add-on another id." % aid)
    exists = aid in st["user"]
    if exists and not update:
        raise AddonError("An add-on with the id %s is already on the PS5. Choose Update to replace it "
                         "(the old one is kept for Roll back)." % aid)
    count = loaded_count(st)
    if not exists and count + 1 > MAX_ADDONS:
        raise AddonError("Omni loads at most %d add-ons and %d are already there. Remove one first."
                         % (MAX_ADDONS, count))
    old_version = None
    if exists:
        try:
            old_version = validate_manifest(console.read(USER_ROOT + aid + "/manifest.json"))["version"]
        except Exception:
            old_version = "?"
    return {"id": aid, "update": exists, "old_version": old_version, "count": count + (0 if exists else 1),
            "dev_shadow": aid in st["dev"], "names": st["names"]}


def _stamp(now=None):
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(now))


def _free(names, base):
    cand, n = base, 2
    while cand in names:
        cand, n = "%s-%d" % (base, n), n + 1
    return cand


def upload(console, pkg, info, log=lambda m: None, now=None):
    """Uploads into USER_ROOT/<id>.uploading-<time>/, parks the current <id> as <id>.prev (an older .prev moves to
    <id>.prev-<time>), renames the new folder into place and reads the manifest back. Returns the final path."""
    aid = pkg.manifest["id"]
    stamp = _stamp(now)
    names = set(console.listing(USER_ROOT)) if info is None else set(info["names"])
    final = USER_ROOT + aid
    temp = USER_ROOT + _free(names, aid + UPLOADING + stamp)
    console.makedirs(temp)
    for rel in sorted(pkg.files):
        dest = temp + "/" + rel
        if "/" in rel:
            console.makedirs(posixpath.dirname(dest))
        console.rename(console.put_verified(dest, pkg.files[rel]), dest)
    got = sorted(n for n, e in console.listing(temp).items() if not e.get("dir"))
    want = sorted(n for n in pkg.files if "/" not in n)
    if got != want:
        raise IOError("The upload of %s is incomplete; it was left as %s and Omni ignores it."
                      % (aid, posixpath.basename(temp)))
    parked = None
    if aid in names:
        if aid + PREV in names:
            console.rename(final + PREV, USER_ROOT + _free(names, aid + PREV + "-" + stamp))
        parked = final + PREV
        console.rename(final, parked)
    try:
        console.rename(temp, final)
    except Exception:
        if parked:
            console.rename(parked, final)       # put the earlier version back
        raise
    if console.read(final + "/manifest.json") != pkg.raw_manifest:
        raise IOError("%s didn't read back correctly; Roll back restores the earlier version." % aid)
    log("%s %s pushed%s." % (aid, pkg.manifest["version"], " (earlier version kept as %s%s)" % (aid, PREV) if parked else ""))
    return final


def push(console, path_or_pkg, update=False, confirm=lambda summary, info: True, log=lambda m: None, now=None):
    """Load + check + confirm + upload. confirm(lines, plan) returns False to cancel (nothing written)."""
    pkg = path_or_pkg if isinstance(path_or_pkg, Package) else load_package(path_or_pkg)
    info = plan(console, pkg, update)
    if not confirm(access_summary(pkg.manifest), info):
        return None
    return upload(console, pkg, info, log, now)


def list_installed(console):
    """The add-ons Setup put on the PS5 (USER_ROOT), with their manifest checked as Omni would."""
    names = console.listing(USER_ROOT)
    out = []
    for n in sorted(names):
        if not valid_id(n) or not names[n].get("dir", True):
            continue
        try:
            m = validate_manifest(console.read(USER_ROOT + n + "/manifest.json", MAX_MANIFEST + 1))
            if m["id"] != n:
                raise AddonError("id must match the folder name")
            out.append(Installed(n, m["name"], m["version"], True, "", n + PREV in names))
        except Exception as e:
            out.append(Installed(n, n, "", False, str(e) or "manifest.json unreadable", n + PREV in names))
    return out


def remove(console, aid, now=None):
    """Renames USER_ROOT/<id> to <id>.removed-<time> (Omni no longer loads it; nothing is deleted)."""
    if not valid_id(aid):
        raise AddonError("bad id")
    names = console.listing(USER_ROOT)
    if aid not in names:
        raise AddonError("%s is not on the PS5." % aid)
    dest = USER_ROOT + _free(names, aid + REMOVED + _stamp(now))
    console.rename(USER_ROOT + aid, dest)
    return dest


def rollback(console, aid, now=None):
    """Puts <id>.prev back as <id>; the current one becomes <id>.removed-<time>."""
    if not valid_id(aid):
        raise AddonError("bad id")
    names = console.listing(USER_ROOT)
    if aid + PREV not in names:
        raise AddonError("There is no earlier version of %s to go back to." % aid)
    moved = None
    if aid in names:
        moved = USER_ROOT + _free(names, aid + REMOVED + _stamp(now))
        console.rename(USER_ROOT + aid, moved)
    console.rename(USER_ROOT + aid + PREV, USER_ROOT + aid)
    return moved


# -- Tk window -----------------------------------------------------------------------------------------------------
def open_window(root, connect=None, run_bg=None, title="Omni add-ons"):
    """connect(): a context-managed ps5.Console (None: no PS5 address, only checking a package is possible);
    run_bg(fn, done(result, err)): the app's background runner (None = run inline)."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    run = run_bg or _inline
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("760x460")
    status = tk.StringVar(value="")
    ttk.Label(win, text="Your own add-ons on the PS5 (Omni loads at most %d add-ons, its own included). "
                        "Restart Omni after a change." % MAX_ADDONS, wraplength=720).pack(anchor="w", padx=10, pady=(10, 4))
    tree = ttk.Treeview(win, columns=("id", "name", "version", "state"), show="headings", height=12, selectmode="browse")
    for col, head, width in (("id", "Id", 170), ("name", "Name", 230), ("version", "Version", 90), ("state", "State", 230)):
        tree.heading(col, text=head)
        tree.column(col, width=width, anchor="w")
    tree.pack(fill="both", expand=True, padx=10)
    ttk.Label(win, textvariable=status, wraplength=720).pack(fill="x", padx=10, pady=6)

    def selected():
        sel = tree.selection()
        return str(tree.item(sel[0], "values")[0]) if sel else None

    def refresh():
        if not connect:
            status.set("Enter the PS5's address first to see its add-ons.")
            return

        def work():
            with connect() as c:
                return list_installed(c), loaded_count(console_state(c))

        def done(r, err):
            if err:
                status.set("Couldn't read the PS5: %s" % err)
                return
            tree.delete(*tree.get_children())
            for a in r[0]:
                tree.insert("", "end", values=(a.id, a.name, a.version,
                                               ("OK" if a.ok else "Omni refuses it: " + a.why)
                                               + (" (earlier version kept)" if a.has_prev else "")))
            status.set("%d of your add-ons; Omni loads %d of %d." % (len(r[0]), r[1], MAX_ADDONS))
        status.set("Reading the PS5…")
        run(work, done)

    def push_from(path):
        if not path:
            return
        try:
            pkg = load_package(path)
        except AddonError as e:
            messagebox.showerror(title, "Omni would refuse this add-on:\n\n%s" % e, parent=win)
            return
        if not connect:
            messagebox.showinfo(title, "The add-on passes Omni's checks.\n\n" + "\n".join(access_summary(pkg.manifest)),
                                parent=win)
            return

        def check():
            with connect() as c:
                try:
                    return plan(c, pkg, update=False)
                except AddonError:
                    if pkg.manifest["id"] in console_state(c)["user"]:
                        return plan(c, pkg, update=True)
                    raise

        def checked(info, err):
            if err:
                messagebox.showerror(title, str(err), parent=win)
                status.set("Not pushed.")
                return
            head = ("Update %s from %s to %s? The current version is kept for Roll back.\n\n"
                    % (info["id"], info["old_version"], pkg.manifest["version"]) if info["update"]
                    else "Add this add-on to Omni?\n\n")
            body = "\n".join(access_summary(pkg.manifest) + pkg.warnings)
            if info["dev_shadow"]:
                body += "\n\nA developer copy with this id exists too; this one wins."
            if not messagebox.askokcancel(title, head + body, parent=win, icon="warning"):
                status.set("Cancelled; nothing was written.")
                return

            def work():
                with connect() as c:
                    return push(c, pkg, update=info["update"])

            def done(_r, err2):
                if err2:
                    status.set("Couldn't push: %s" % err2)
                else:
                    status.set("Pushed %s. Restart Omni to load it." % pkg.manifest["id"])
                    refresh()
            status.set("Uploading…")
            run(work, done)
        status.set("Checking the PS5…")
        run(check, checked)

    def act(fn, verb):
        aid = selected()
        if not aid or not connect:
            return
        if not messagebox.askokcancel(title, "%s %s? Nothing is deleted on the PS5." % (verb, aid), parent=win):
            return

        def work():
            with connect() as c:
                return fn(c, aid)

        def done(_r, err):
            status.set("Couldn't %s: %s" % (verb.lower(), err) if err else "%s: done. Restart Omni." % verb)
            if not err:
                refresh()
        run(work, done)

    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=10, pady=(0, 10))
    ps5 = "normal" if connect else "disabled"
    ttk.Button(bar, text="Push a .zip…", command=lambda: push_from(filedialog.askopenfilename(
        parent=win, filetypes=[("Add-on package", "*.zip")]))).pack(side="left")
    ttk.Button(bar, text="Push a folder…", command=lambda: push_from(filedialog.askdirectory(parent=win))
               ).pack(side="left", padx=6)
    ttk.Button(bar, text="Remove", state=ps5, command=lambda: act(remove, "Remove")).pack(side="left")
    ttk.Button(bar, text="Roll back", state=ps5, command=lambda: act(rollback, "Roll back")).pack(side="left", padx=6)
    ttk.Button(bar, text="Refresh", state=ps5, command=refresh).pack(side="left")
    ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
    refresh()
    return win


def _inline(fn, done):
    try:
        r = fn()
    except Exception as e:  # shown to the user
        done(None, e)
    else:
        done(r, None)
