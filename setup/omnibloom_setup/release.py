"""Getting the apps to install.

Each app repo publishes ONE console package per release: `<prefix><version>.zip` plus `<zip>.sha256`
(egomortal/omnibloom carries Bloom Core, Omni, downloads and USB files; egomortal/master-control
carries Master Control). Inside a package: `omnibloom-package.json` (the manifest) and `files/...`.

The manifest lists apps (with their ID-card template, roots, port rule and autoload rule) and files.
Every file is pinned by size and SHA-256, belongs to exactly one app, and must sit inside that app's
declared roots, which must sit inside Omnibloom's install folders. Setup combines the packages it
finds into one catalog (newest version of each app wins).

Provenance (audit RL-01): a release also carries `RELEASE-MANIFEST.json` (written by
tools/build_release.py: tag, source manifest hash, and the name, size and SHA-256 of every asset).
Setup installs a downloaded package only when the manifest, the `.sha256` file and the download all
agree, and a package next to Setup only when its `.sha256` file is beside it and matches. These are
same-channel checks: they catch damaged, swapped or partly uploaded assets, not a stolen account.
"""
import hashlib
import json
import os
import posixpath
import re
import sys
import urllib.request
import zipfile

from . import config

SCHEMA = "omnibloom-package/v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
APP_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}\Z")
KINDS = ("title", "payload", "service")
AUTOLOAD = ("never", "optional", "required")
CARD_KEYS = {"name", "kind", "launch", "health", "pages", "provides", "consumes", "public_pages"}
RELEASE_MANIFEST_ASSET = "RELEASE-MANIFEST.json"
RELEASE_MANIFEST_SCHEMA = "omnibloom-release-manifest/v1"
METADATA_LIMIT = 1 << 20     # checksum and manifest files are small; never read more than this


class ReleaseError(Exception):
    pass


def version_key(text):
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums) or (0,)


def app_dir():
    """Folder of the setup file (the exe when frozen by PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def cache_dir():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "Omnibloom", "Setup")
    os.makedirs(path, exist_ok=True)
    return path


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _checksum_line(text, name):
    """The SHA-256 from a `<hash>  <name>` line, checked to name this file."""
    parts = text.split()
    if len(parts) != 2 or not HEX64.fullmatch(parts[0].lower()) or parts[1].lstrip("*") != name:
        raise ReleaseError("The release checksum file is not valid.")
    return parts[0].lower()


def offline_package(zip_path):
    """A package next to Setup, opened only if its `.sha256` file is beside it and matches (RL-01)."""
    try:
        with open(zip_path + ".sha256", "rb") as f:
            text = f.read(METADATA_LIMIT).decode("ascii", "replace")
    except OSError:
        raise ReleaseError("%s has no checksum file next to it (.sha256), so it can't be trusted."
                           % os.path.basename(zip_path))
    return Package(zip_path, sha_expected=_checksum_line(text, os.path.basename(zip_path)))


def manifest_asset(manifest, info):
    """The release manifest's row for this package, checked against the release it came from (RL-01)."""
    if not isinstance(manifest, dict) or manifest.get("schema") != RELEASE_MANIFEST_SCHEMA \
            or manifest.get("tag") != info["tag"] or not isinstance(manifest.get("assets"), list):
        raise ReleaseError("The release manifest doesn't belong to this release.")
    rows = [a for a in manifest["assets"] if isinstance(a, dict) and a.get("name") == info["zip_name"]]
    if len(rows) != 1 or not HEX64.fullmatch(str(rows[0].get("sha256"))) or type(rows[0].get("bytes")) is not int:
        raise ReleaseError("The release manifest doesn't list %s." % info["zip_name"])
    return rows[0]


# -- finding packages -------------------------------------------------------
def find_offline_zips(folder=None, sources=None):
    """Packages next to the setup file: the newest one per source."""
    folder = folder or app_dir()
    found = []
    names = os.listdir(folder)
    for src in (sources if sources is not None else config.SOURCES):
        zips = [n for n in names if n.startswith(src["prefix"]) and n.endswith(".zip")]
        if zips:
            zips.sort(key=version_key)
            found.append(os.path.join(folder, zips[-1]))
    return found


def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": config.APP_NAME + "/" + config.SETUP_VERSION})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def latest_release_info(source, api_base=None):
    """{"tag", "zip_url", "zip_name", "sha_url", "size"} for the newest release of one source repo."""
    api_base = api_base or config.GITHUB_API
    data = _get_json("%s/repos/%s/releases/latest" % (api_base, source["repo"]))
    assets = {a["name"]: a for a in data.get("assets", [])}
    zips = [n for n in assets if n.startswith(source["prefix"]) and n.endswith(".zip")]
    if not zips:
        raise ReleaseError("%s has no console package in its newest release yet." % source["repo"])
    name = sorted(zips, key=version_key)[-1]
    sha = assets.get(name + ".sha256")
    manifest = assets.get(RELEASE_MANIFEST_ASSET)
    if not sha or not manifest:
        raise ReleaseError("%s's release is missing its checksum file, so it can't be trusted." % source["repo"])
    return {"tag": data.get("tag_name", ""), "zip_name": name, "zip_url": assets[name]["browser_download_url"],
            "sha_url": sha["browser_download_url"], "manifest_url": manifest["browser_download_url"], "size": assets[name].get("size", 0), "repo": source["repo"]}


def download_release(info, dest_dir=None, progress=None):
    dest_dir = dest_dir or cache_dir()
    target = os.path.join(dest_dir, info["zip_name"])
    ua = {"User-Agent": config.APP_NAME + "/" + config.SETUP_VERSION}
    with urllib.request.urlopen(urllib.request.Request(info["sha_url"], headers=ua), timeout=20) as r:
        expected = _checksum_line(r.read(METADATA_LIMIT).decode("ascii", "replace"), info["zip_name"])
    with urllib.request.urlopen(urllib.request.Request(info["manifest_url"], headers=ua), timeout=20) as r:
        try:
            row = manifest_asset(json.loads(r.read(METADATA_LIMIT)), info)
        except ValueError:
            raise ReleaseError("The release manifest doesn't belong to this release.")
    if row["sha256"] != expected:
        raise ReleaseError("The release manifest and checksum file disagree, so the package can't be trusted.")
    if os.path.exists(target) and file_sha256(target) == expected:
        return target
    tmp = target + ".part"
    with urllib.request.urlopen(urllib.request.Request(info["zip_url"], headers=ua), timeout=60) as r, open(tmp, "wb") as out:
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    if file_sha256(tmp) != expected or os.path.getsize(tmp) != row["bytes"]:
        os.remove(tmp)
        raise ReleaseError("The download didn't match its checksum. Please try again.")
    os.replace(tmp, target)
    return target


# -- checking ------------------------------------------------------------
def _under(path, roots):
    return any(path == r.rstrip("/") or path.startswith(r if r.endswith("/") else r + "/") for r in roots)


def check_dest(dest, roots=None):
    if not isinstance(dest, str) or not dest.startswith("/") or "\\" in dest or "\x00" in dest:
        raise ReleaseError("Bad destination in release: %r" % (dest,))
    if posixpath.normpath(dest) != dest.rstrip("/") or "/../" in dest + "/":
        raise ReleaseError("Bad destination in release: %r" % (dest,))
    if not _under(dest, config.INSTALL_ROOTS):
        raise ReleaseError("Release wants to write outside Omnibloom's folders: %s" % dest)
    if _under(dest, config.PROTECTED_ROOTS) or _under(dest, config.SETUP_OWNED):
        raise ReleaseError("Release wants to write into a protected place: %s" % dest)
    if roots is not None and not _under(dest, roots):
        raise ReleaseError("A file is outside its app's own folders: %s" % dest)


def check_app(app_id, app):
    if not APP_ID.fullmatch(app_id):
        raise ReleaseError("Bad app id: %r" % app_id)
    for key in ("name", "version", "roots", "card", "port", "autoload"):
        if key not in app:
            raise ReleaseError("App %s is missing %s." % (app_id, key))
    if app["autoload"] not in AUTOLOAD:
        raise ReleaseError("App %s has an unknown autoload rule." % app_id)
    for r in app["roots"]:   # a folder (ends with /) or one exact file
        check_dest(r)
    card = app["card"]
    missing = CARD_KEYS - set(card)
    if missing:
        raise ReleaseError("App %s's card is missing %s." % (app_id, ", ".join(sorted(missing))))
    if card["kind"] not in KINDS:
        raise ReleaseError("App %s has an unknown kind." % app_id)
    if card["kind"] == "title" and not card.get("title_id"):
        raise ReleaseError("App %s is a title without a title_id." % app_id)
    if card["kind"] in ("payload", "service") and not (card.get("launch") or {}).get("elf"):
        raise ReleaseError("App %s has no launch elf." % app_id)
    port = app["port"]
    if port is not None and (type(port) is not dict or type(port.get("preferred")) is not int or type(port.get("movable")) is not bool
                             or not 1024 <= port["preferred"] <= 65535):
        raise ReleaseError("App %s has a bad port rule." % app_id)


class Package:
    """One opened, fully checked package zip."""

    def __init__(self, zip_path, sha_expected=None):
        self.path = zip_path
        if sha_expected and file_sha256(zip_path) != sha_expected:
            raise ReleaseError("The package doesn't match its checksum.")
        self.zip = zipfile.ZipFile(zip_path)
        try:
            self.manifest = json.loads(self.zip.read(config.RELEASE_MANIFEST))
        except KeyError:
            raise ReleaseError("This zip is not an Omnibloom console package.")
        m = self.manifest
        if m.get("schema") != SCHEMA:
            raise ReleaseError("This package was made for a different Setup version.")
        self.name = str(m.get("package", ""))
        self.version = str(m.get("version", ""))
        self.apps = m.get("apps") or {}
        self.files = m.get("files") or []
        if not self.version or not self.apps or not isinstance(self.files, list):
            raise ReleaseError("The package manifest is incomplete.")
        for app_id, app in self.apps.items():
            check_app(app_id, app)
        ids = list(self.apps)
        for i, a in enumerate(ids):  # no two apps may share a folder
            for b in ids[i + 1:]:
                for ra in self.apps[a]["roots"]:
                    for rb in self.apps[b]["roots"]:
                        if _under(ra, [rb]) or _under(rb, [ra]):
                            raise ReleaseError("Apps %s and %s share a folder." % (a, b))
        seen = set()
        for row in self.files:
            if set(row) != {"app", "src", "dest", "sha256", "bytes"}:
                raise ReleaseError("Malformed file entry in the package.")
            if row["app"] not in self.apps:
                raise ReleaseError("A file belongs to an unknown app: %s" % row["app"])
            check_dest(row["dest"], self.apps[row["app"]]["roots"])
            if row["dest"] in seen:
                raise ReleaseError("Duplicate destination: %s" % row["dest"])
            seen.add(row["dest"])
            if not HEX64.fullmatch(row["sha256"]) or type(row["bytes"]) is not int:
                raise ReleaseError("Malformed checksum in the package.")

    def data(self, row):
        blob = self.zip.read(row["src"])
        if len(blob) != row["bytes"] or hashlib.sha256(blob).hexdigest() != row["sha256"]:
            raise ReleaseError("A file in the package is damaged: %s" % row["src"])
        return blob

    def verify_all(self):
        for row in self.files:
            self.data(row)

    def files_for(self, app_id):
        return [r for r in self.files if r["app"] == app_id]

    def close(self):
        self.zip.close()


class Catalog:
    """All apps Setup can install, from every package it found (newest version of each app wins)."""

    def __init__(self, packages):
        self.packages = list(packages)
        self.apps = {}      # id -> app dict
        self.source = {}    # id -> Package
        for pkg in self.packages:
            for app_id, app in pkg.apps.items():
                if app_id not in self.apps or version_key(app["version"]) > version_key(self.apps[app_id]["version"]):
                    self.apps[app_id] = app
                    self.source[app_id] = pkg

    def has(self, app_id):
        return app_id in self.apps

    def files_for(self, app_id):
        return self.source[app_id].files_for(app_id)

    def data(self, app_id, row):
        return self.source[app_id].data(row)

    def add(self, pkg):
        """Merge one more package (e.g. the JDownloader 2 engine, fetched only when the user turns it on)."""
        self.packages.append(pkg)
        for app_id, app in pkg.apps.items():
            if app_id not in self.apps or version_key(app["version"]) > version_key(self.apps[app_id]["version"]):
                self.apps[app_id] = app
                self.source[app_id] = pkg

    def jd_engine(self):
        """The engine package's `jdownloader_engine` block (pins for the Java runtime and java-worker), or None."""
        if not self.has(config.JD_APP_ID):
            return None
        info = self.source[config.JD_APP_ID].manifest.get("jdownloader_engine") or {}
        return info if info.get("ready") else None

    def jd_engine_ready(self):
        return self.jd_engine() is not None

    def versions(self):
        return {k: v["version"] for k, v in self.apps.items()}

    def close(self):
        """Release the zip files (Windows keeps open files locked)."""
        for p in self.packages:
            p.close()


def load_catalog(folder=None, online=True, api_base=None, log=lambda m: None, include_optional=False):
    """Offline packages next to the setup file win; otherwise the newest GitHub release of each source.
    Optional sources (the JDownloader 2 engine) are only fetched when asked for; one sitting next to
    Setup is always used."""
    packages, errors = [], []
    offline = find_offline_zips(folder)
    offline_prefixes = {s["prefix"] for s in config.SOURCES for z in offline if os.path.basename(z).startswith(s["prefix"])}
    for z in offline:
        log("Using the package next to Setup: %s" % os.path.basename(z))
        packages.append(offline_package(z))
    if online:
        for src in config.SOURCES:
            if src.get("optional") and not include_optional:
                continue
            if src["prefix"] in offline_prefixes:
                continue
            try:
                info = latest_release_info(src, api_base=api_base)
                log("Downloading %s %s…" % (src["repo"], info["tag"]))
                packages.append(Package(download_release(info)))
            except Exception as e:  # one missing repo shouldn't block the others
                errors.append("%s: %s" % (src["repo"], e))
    if not packages:
        raise ReleaseError("Couldn't get any Omnibloom packages. " + "; ".join(errors))
    cat = Catalog(packages)
    cat.errors = errors
    return cat


def engine_source():
    return next(s for s in config.SOURCES if s.get("package") == "omnibloom-jd-engine")


def load_engine(catalog, folder=None, online=True, api_base=None, log=lambda m: None):
    """Add the JDownloader 2 engine package to `catalog` if it isn't there yet. Order: a zip next to Setup,
    then the bundled release asset on egomortal/omnibloom. (The Java port's own GitHub releases are probe
    titles, not this engine, so there is no third source to download it from; see the recipe in the repo.)"""
    if catalog.jd_engine_ready():
        return catalog.jd_engine()
    src = engine_source()
    zips = find_offline_zips(folder, sources=[src])
    if zips:
        log("Using the JDownloader 2 engine next to Setup: %s" % os.path.basename(zips[0]))
        catalog.add(offline_package(zips[0]))
    elif online:
        info = latest_release_info(src, api_base=api_base)
        log("Downloading the JDownloader 2 engine (%s %s)…" % (src["repo"], info["tag"]))
        catalog.add(Package(download_release(info)))
    else:
        raise ReleaseError("The JDownloader 2 engine package isn't next to Setup, and downloading is off.")
    if not catalog.jd_engine_ready():
        raise ReleaseError("That package doesn't contain a ready JDownloader 2 engine.")
    return catalog.jd_engine()
