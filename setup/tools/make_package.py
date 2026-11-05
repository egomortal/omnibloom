"""Build a console package for a release: <prefix><version>.zip + .sha256.

  python tools/make_package.py --package omnibloom --stage stage --version 0.5.0 --out dist
  python tools/make_package.py --package master-control --stage stage-mc --version 0.4.4 --out dist

`stage` mirrors the console (stage/data/homebrew/PPSA99732/eboot.bin, ...). Each file is assigned
to the app whose roots contain it; a file no app owns is refused, and so is anything outside
Omnibloom's install folders or inside the user's data (Setup would refuse those too).
App versions default to the package version; override with --app-version id=1.2.3.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import config  # noqa: E402
from omnibloom_setup.release import SCHEMA, Package, _under, check_dest  # noqa: E402

PKG_PAYLOADS = config.PLDMGR_DIR + "payloads/"
ICONS = config.ICONS_DIR

# The apps each repo ships, with their ID-card templates (Setup adds hub_api, id, version, port, icon).
APPS = {
    "hub": {
        "package": "omnibloom", "name": config.HUB_NAME, "autoload": "required",
        "roots": [PKG_PAYLOADS + "BloomCore/", ICONS + "hub/"],
        "port": {"preferred": config.HUB_PORT, "movable": False},
        "card": {"name": config.HUB_NAME, "kind": "service",
                 "launch": {"elf": PKG_PAYLOADS + "BloomCore/hub.elf", "autoload": "required"},
                 "health": "/api/health", "pages": {}, "provides": ["theme.changed"], "consumes": [],
                 "public_pages": []},
    },
    "omni": {
        "package": "omnibloom", "name": "Omni", "autoload": "never",
        "roots": [config.TITLE_DIR, "/data/omni/native/omni-engine-child.elf", "/data/omni/fonts/", ICONS + "omni/"],
        "port": None,
        "card": {"name": "Omni", "kind": "title", "title_id": config.TITLE_ID,
                 "launch": {"title_id": config.TITLE_ID, "autoload": "never"},
                 "health": None, "pages": {}, "provides": ["open.url"],
                 "consumes": ["theme", "download.url", "files.pick", "overlay.show"], "public_pages": []},
    },
    "downloads": {
        "package": "omnibloom", "name": "Omni Downloads", "autoload": "never",
        # Not /data/omni-downloader/ as a whole: jdownloader/ belongs to the JDownloader 2 engine app.
        "roots": ["/data/omni-downloader/python-worker.elf", "/data/omni-downloader/worker/", "/data/omni-downloader/runtime/",
                  "/data/omni-downloader/.deps/", ICONS + "downloads/"],
        "port": {"preferred": 8765, "movable": True},
        "card": {"name": "Omni Downloads", "kind": "service",
                 "launch": {"elf": "/data/omni-downloader/python-worker.elf", "autoload": "never"},
                 "health": "/api/health", "pages": {"main": "/"}, "provides": ["download.url"],
                 "consumes": ["theme", "files.pick"], "public_pages": ["/", "/downloads", "/assets/"],
                 "page_apis": ["/api/"]},   # s2: Omni's port block lets only the downloads page itself call /api/
    },
    "files-broker": {
        "package": "omnibloom", "name": "USB Files", "autoload": "never",
        "roots": ["/data/omni/native/omni-files.elf", ICONS + "files-broker/"],
        "port": {"preferred": 8767, "movable": True},
        "card": {"name": "USB Files", "kind": "service",
                 "launch": {"elf": "/data/omni/native/omni-files.elf", "autoload": "never"},
                 "health": None, "pages": {}, "provides": ["files.pick", "files.open"],
                 "consumes": [], "public_pages": []},
    },
    "jdownloader": {
        # Our java-worker.elf + the PS5 Java 25 runtime built from mateo-cogeanu/ps5-java25-homebrew (GPLv2+CPE parts,
        # notices shipped unchanged under notices/) + our bridge classes. JDownloader 2 itself is the user's own copy.
        "package": "omnibloom-jd-engine", "name": "JDownloader 2 engine", "autoload": "never",
        "roots": [config.JD_CONSOLE_ROOT + "java-worker.elf", config.JD_CONSOLE_ROOT + "native/",
                  config.JD_CONSOLE_ROOT + "runtime/classes/", config.JD_CONSOLE_ROOT + "notices/"],
        # Item 15: no card port. The bridge binds a loopback port per session; Bloom Core takes the live port from
        # /data/hub/runtime/jdownloader.json. health null: the bridge speaks its own session protocol, not HTTP, so
        # Bloom Core checks the runtime pid instead and never routes intents to it.
        "port": None,
        "card": {"name": "JDownloader 2 engine", "kind": "service",
                 "launch": {"elf": config.JD_CONSOLE_ROOT + "java-worker.elf", "autoload": "never", "started_by": "downloads"},
                 "health": None, "pages": {}, "provides": ["download.engine.jdownloader"], "consumes": [], "public_pages": []},
    },
    "master-control": {
        "package": "master-control", "name": "Master Control", "autoload": "optional",
        # Standard v1.1 item 7: the payload ELF and its icon live together in /data/pldmgr/payloads/<id>/.
        "roots": [PKG_PAYLOADS + "master-control/"],
        "port": {"preferred": 8766, "movable": True},
        "card": {"name": "Master Control", "kind": "payload",
                 "launch": {"elf": PKG_PAYLOADS + "master-control/master-control.elf", "autoload": "optional"},
                 "health": "/api/health", "pages": {"main": "/", "overlay": "/overlay"},
                 # Exactly what Master Control 0.4.3 answers on POST /hub/intent; it serves no
                 # /fonts/ or /assets/ (fonts are embedded); its own page calls /api/*.
                 "provides": ["overlay.show", "input.remap.profile"],
                 "consumes": ["theme"], "public_pages": ["/", "/overlay", "/icon.png", "/classic"],
                 "page_apis": ["/api/"]},
    },
}
PREFIX = {s["package"]: s["prefix"] for s in config.SOURCES}


def engine_block(rows, stage):
    """Pins the console needs to approve the engine (native-install.json is written by Setup after its check)."""
    root = config.JD_CONSOLE_ROOT
    by = {r["dest"]: r for r in rows}
    elf, image = by.get(root + "java-worker.elf"), by.get(root + "native/image-manifest.json")
    if not elf or not image:
        raise SystemExit("The engine package needs java-worker.elf and native/image-manifest.json")
    for need in ("runtime/classes/OmniJDownloaderBridge.class",
                 "runtime/classes/org/jdownloader/api/myjdownloader/MyJDownloaderController.class"):
        if root + need not in by:
            raise SystemExit("The engine package is missing " + need)
    return {"ready": True, "elf": elf["dest"], "elf_sha256": elf["sha256"], "elf_bytes": elf["bytes"],
            "image_manifest": image["dest"], "image_manifest_sha256": image["sha256"],
            "jd_tested_revision": config.JD_TESTED_REVISION,
            "java_port": {"repo": config.JAVA_PORT_REPO, "commit": config.JAVA_PORT_COMMIT, "url": config.JAVA_PORT_URL,
                          "source": config.JAVA_PORT_SOURCE_URL, "openjdk_source": config.OPENJDK_SOURCE_URL,
                          "licence": "OpenJDK parts: GPLv2 with the Classpath Exception (notices under notices/)"}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True, choices=sorted(PREFIX))
    p.add_argument("--stage", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--app-version", action="append", default=[])
    p.add_argument("--jd-engine-ready", action="store_true")
    a = p.parse_args()
    versions = dict(v.split("=", 1) for v in a.app_version)
    apps = {k: v for k, v in APPS.items() if v["package"] == a.package}
    rows = []
    for dirpath, _, names in os.walk(a.stage):
        for n in sorted(names):
            full = os.path.join(dirpath, n)
            dest = "/" + os.path.relpath(full, a.stage).replace(os.sep, "/")
            owner = [k for k, v in apps.items() if _under(dest, v["roots"])]
            if len(owner) != 1:
                raise SystemExit("No single app owns %s" % dest)
            check_dest(dest, apps[owner[0]]["roots"])
            data = open(full, "rb").read()
            rows.append({"app": owner[0], "src": "files" + dest, "dest": dest,
                         "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    rows.sort(key=lambda r: r["dest"])
    shipped = sorted({r["app"] for r in rows})
    manifest_apps = {}
    for k in shipped:
        app = copy.deepcopy(apps[k])
        app.pop("package")
        app["version"] = versions.get(k, a.version)
        manifest_apps[k] = app
    manifest = {"schema": SCHEMA, "package": a.package, "version": a.version,
                "tested_firmware": config.TESTED_FIRMWARE, "apps": manifest_apps, "files": rows}
    if a.package == "omnibloom-jd-engine":
        manifest["jdownloader_engine"] = engine_block(rows, a.stage) if a.jd_engine_ready else {"ready": False}
    os.makedirs(a.out, exist_ok=True)
    name = os.path.join(a.out, "%s%s.zip" % (PREFIX[a.package], a.version))
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(config.RELEASE_MANIFEST, json.dumps(manifest, indent=1))
        for r in rows:
            z.write(os.path.join(a.stage, r["dest"].lstrip("/")), r["src"])
    Package(name).verify_all()   # the same checks Setup runs
    digest = hashlib.sha256(open(name, "rb").read()).hexdigest()
    with open(name + ".sha256", "w") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(name)))
    print(name, digest, len(rows), "files", ",".join(shipped))


if __name__ == "__main__":
    main()
