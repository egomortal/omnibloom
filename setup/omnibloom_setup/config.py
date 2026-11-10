"""Fixed settings for Omnibloom Setup. Nothing here is personal: no addresses, no user paths."""

APP_NAME = "Omnibloom Setup"
SETUP_VERSION = "0.1.0"
TAGLINE = "potential birth from possibility"

# Where the apps come from. Setup downloads the newest release of each repo at run time,
# so the setup file itself stays small. Each release carries one console package:
# <prefix><version>.zip + <zip>.sha256, with RELEASE_MANIFEST inside.
GITHUB_API = "https://api.github.com"
SOURCES = (
    {"repo": "egomortal/omnibloom", "prefix": "omnibloom-console-", "package": "omnibloom"},        # Bloom Core, Omni, downloads, USB files
    {"repo": "egomortal/master-control", "prefix": "master-control-console-", "package": "master-control"},
    # The JDownloader 2 engine (our java-worker + the PS5 Java 25 runtime built from mateo-cogeanu's port).
    # A separate release asset, fetched only when the user turns JDownloader 2 on.
    {"repo": "egomortal/omnibloom", "prefix": "omnibloom-jd-engine-", "package": "omnibloom-jd-engine", "optional": True},
)
GITHUB_REPO = SOURCES[0]["repo"]
RELEASE_MANIFEST = "omnibloom-package.json"     # inside each package zip

# Console services (all provided by the user's own jailbreak setup).
FTP_PORT = 2121           # FTP server payload (ftpsrv); accepts any login
LOADER_PORT = 9021        # ELF loader (elfldr): send an ELF here to start it
WEBSRV_PORT = 8084        # optional: websrv's /processes_list (used only if present)
LAUNCHER_PORT = 8080      # the homebrew launcher's /hbldr (starts an ELF with arguments); used only by the JDownloader 2 check

# ---- Suite plug-in standard (Hub API v1, SUITE-PLUGIN-STANDARD.md) ---------------------------
HUB_API = 1
HUB_DIR = "/data/hub/"
CARDS_DIR = HUB_DIR + "apps/"          # /data/hub/apps/<id>.json   (ID cards, written by Setup)
RECEIPTS_DIR = HUB_DIR + "receipts/"   # /data/hub/receipts/<id>.json (one small receipt per app; Bloom Core reads it)
DETAILS_DIR = RECEIPTS_DIR + "details/"  # /data/hub/receipts/details/<id>.json (file list, backups, full card)
RECEIPT_MAX = 8 * 1024                 # Bloom Core refuses receipts larger than 8 KiB
CARD_MAX = 32 * 1024                   # ... and cards larger than 32 KiB
ICONS_DIR = HUB_DIR + "icons/"
LOGS_DIR = HUB_DIR + "logs/"
CRASH_DIR = HUB_DIR + "crash/"
SETTINGS_PATH = HUB_DIR + "settings.json"
DEFAULT_SETTINGS = {"theme": "silver-blue", "language": "en", "motion": "full", "sound": True}
HUB_PORT = 8760                        # the only fixed port in the suite
HUB_ID = "hub"

# Ports Setup must never hand to an app (owner shown to the user if there's a clash).
RESERVED_PORTS = {
    2121: "FTP server", 9021: "payload loader", 8080: "websrv", 8084: "websrv",
    HUB_PORT: "Bloom Core", 8765: "Omni downloads", 8767: "Omni USB files", 7090: "Ex-Box 360 companion",
    8095: "older Master Control / PadBridge / OmniPad-PS5",
}
# Where Setup looks for a free port for an app that can move.
PORT_RANGES = ((8761, 8799), (8800, 8899))

TITLE_ID = "PPSA99732"
TITLE_DIR = "/data/homebrew/" + TITLE_ID + "/"

# Payload Manager (pldmgr) layout, proven on the console: one folder per payload,
# `<file>.elf` + `<file>.elf.json`, and autoload.txt lists bare file names only.
PLDMGR_DIR = "/data/pldmgr/"
AUTOLOAD_PATH = PLDMGR_DIR + "autoload.txt"

# The only places a release may put app files (each app also declares its own roots inside these).
INSTALL_ROOTS = (
    TITLE_DIR,
    "/data/omni/native/",
    "/data/omni/fonts/",
    "/data/omni-downloader/",
    PLDMGR_DIR + "payloads/",
    ICONS_DIR,
)
# Written only by Setup itself (never by release files).
SETUP_OWNED = (CARDS_DIR, RECEIPTS_DIR)

# Never written, renamed or removed: the user's own data.
PROTECTED_ROOTS = (
    "/data/omni/browser-profile",
    "/data/omni/downloads",
    "/data/omni-downloader/state",
    "/data/omni-downloader/jdownloader/runtime/cfg",
    "/data/omni-downloader/downloads",
    "/data/mastercontrol",
    "/data/padbridge",
    SETTINGS_PATH,
)

# Files whose FTP readback is not the uploaded bytes: ftpsrv serves a decoded view of a
# native title's eboot.bin, so its hash can only be checked locally before upload.
# The console's rule is "eboot/prx readback is decrypted": the same goes for the title's .prx/.sprx modules.
DECODED_ON_READBACK = ("eboot.bin",)
DECODED_SUFFIXES = (".prx", ".sprx")

# ShadowMountPlus logs a line when it (re)mounts a title; after Omni's files change, Setup waits for it.
SMP_LOG = "/data/shadowmount/debug.log"
SMP_MOUNT_WORDS = ("nullfs mounted", "mount.lnk created")
# A running title shows as this process name in websrv's list. Setup waits for it to close; it never closes it.
TITLE_PROCESS = "eboot.bin"

# One Setup at a time per PS5 (the one-button install takes it; {"owner": null} when free).
SETUP_LOCK = HUB_DIR + "setup-lock.json"
SETUP_LOCK_MINUTES = 30

# Omni's HDR setting (`<revision>TAB<off|auto|on>` and a newline; Omni treats a missing file as Off). The one-button install
# sets Auto when there's no setting yet and keeps the user's choice otherwise.
OMNI_HDR_PREF = "/data/omni/video-hdr-preference.txt"

# Required console software, with how the setup recognises each one in autoload.txt.
REQUIREMENTS = {
    "shadowmount": ("ShadowMountPlus", ("shadowmount",)),
    "kstuff": ("kstuff", ("kstuff",)),
}
TESTED_FIRMWARE = "13.60"

# What the user picks in the window. Each group installs one or more apps (IDs as in the cards).
HUB_NAME = "Bloom Core"
GROUPS = (
    {"id": "omni", "name": "Omni", "apps": ("omni", "downloads", "files-broker"),
     "description": "The web browser, with downloads and USB file access."},
    {"id": "master-control", "name": "Master Control", "apps": ("master-control",),
     "description": "Use Xbox, Switch and other controllers on your PS5."},
    {"id": "exbox", "name": "Ex-Box 360", "apps": ("exbox",),
     "description": "An Xbox 360-style dashboard for your PS5."},
)
# Shown when a group's apps aren't in the release yet.
COMING_SOON = {
    "exbox": "Coming soon. Ex-Box 360 is moving to a new install layout, and its Xbox 360 artwork "
             "has to come from your own console backups, so Setup can't install it yet.",
}
# Older controller payloads that Master Control replaces in autoload (only if the user ticks the box).
REPLACED_CONTROLLER_PAYLOADS = ("padbridge", "eeveelution")

# JDownloader 2 (never shipped by us; the user's own copy is used).
JD_CONSOLE_ROOT = "/data/omni-downloader/jdownloader/"
JD_OFFICIAL_URL = "https://jdownloader.org/jdownloader2"
JD_APP_ID = "jdownloader"                    # the engine app (our java-worker + bundled Java runtime)
JD_TESTED_REVISION = 50639                   # JDownloaderRevision in build.json the bridge was built and tested with

# Audit JD-03: JDownloader 2 opens its own connections (plugins, redirects, update checks) with no reviewed
# destination policy yet, so Setup keeps the step held back. Developers can still test it with OMNIBLOOM_ENABLE_JD=1.
JD_HELD_REASON = ("JDownloader 2 is held back in this release: its own connections (file-host plugins and their "
                  "redirects) don't yet go through Omnibloom's private-address check. yt-dlp downloads are not affected.")


def jd_enabled():
    import os
    return os.environ.get("OMNIBLOOM_ENABLE_JD") == "1"


JD_CHECKS_DIR = JD_CONSOLE_ROOT + "setup-checks/"
JD_BACKUP_DIR = JD_CONSOLE_ROOT + "setup-backup/"   # outside runtime/, so old files never break the engine's exact file list
# Folders under runtime/ that JDownloader itself writes; never touched, never part of the pinned file list.
JD_MUTABLE = ("cfg", "cache", "logs", "home", "tmp", "downloads", "update", "updates", "backup", "captchas")
# The console Java runtime is built from this open-source port (OpenJDK 25 for PS5 homebrew).
JAVA_PORT_REPO = "mateo-cogeanu/ps5-java25-homebrew"
JAVA_PORT_URL = "https://github.com/" + JAVA_PORT_REPO
JAVA_PORT_COMMIT = "db3ac845fa090c64e2a737d6c4222dd37867d7fe"
JAVA_PORT_SOURCE_URL = "https://codeload.github.com/%s/tar.gz/%s" % (JAVA_PORT_REPO, JAVA_PORT_COMMIT)
OPENJDK_SOURCE_URL = "https://github.com/freebsd/openjdk/tree/b219cdec88ca2e165711f63b8158ab78303facc8"
JAVA_PORT_CREDIT = ("JDownloader 2 runs on the PS5 thanks to the PS5 Java 25 port by mateo-cogeanu (" + JAVA_PORT_URL + "). "
                    "Its OpenJDK parts are GPLv2 with the Classpath Exception; the source is at the port's repo and at "
                    + OPENJDK_SOURCE_URL + ".")

# Look (from CODEX-GRAPHICS-USER.md). Astra may restyle the window later.
COLORS = {
    "ground": "#070C12",
    "panel": "#0E1821",
    "text": "#E6EDF3",
    "muted": "#9FB1C2",
    "accent": "#6CCBFF",
    "accent_light": "#A6E2FF",
    "accent_dark": "#4FB6F0",
    "ink_on_accent": "#06202F",
    "chrome": "#F4F8FB",
    "ok": "#7BE0A6",
    "warn": "#FFD27A",
    "bad": "#FF8A8A",
}
