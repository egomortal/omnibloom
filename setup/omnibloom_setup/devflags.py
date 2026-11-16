"""Omni's developer flags and override files (DEVELOPERS.md, "Developer flags and override files"), for the
"Advanced: Omni developer flags…" page.

The table below is the only list Setup acts on: it mirrors DEVELOPERS.md's three tables row for row (a test keeps the
names, descriptions and risks in sync). Setup reads the names in /data/omni with one listing (never file contents),
creates a flag as a one-line file ("1\\n", verified upload), and removes a flag or override file by moving it aside as
<name>.before-setup-<time> (Setup never deletes anything on the PS5; Omni only looks for the exact name, so the moved
file has no effect and can be renamed back). Override text files are never created or edited here, only moved aside.
Any name not in the table, any path, and any folder entry are refused before anything is written.
"""
import posixpath
import re

from . import installer

OMNI_DIR = "/data/omni"
FLAG_DATA = b"1\n"
PARK_SUFFIX = ".before-setup-"

KILL, OPT_IN, OVERRIDE = "kill", "opt-in", "override"
KINDS = (
    (KILL, "Kill switches", "On by default; the flag turns the feature off."),
    (OPT_IN, "Opt-in flags", "Off by default; the flag turns the feature on."),
    (OVERRIDE, "Override text files", "Present only if someone put them there. Setup can move them aside, not edit "
                                       "them (changing a user agent or tuning value from Setup is not supported)."),
)


def _row(kind, files, effect, default, audience, risk):
    return {"kind": kind, "files": tuple(files), "effect": effect, "default": default, "for": audience, "risk": risk}


_PERF_STEPS = tuple("perf-a-s%d-disabled.flag" % i for i in range(1, 9))

# Text as in DEVELOPERS.md (backticks dropped). Order as there.
ROWS = (
    _row(KILL, ["ytguard-off.flag"], "Removes the YouTube attestation guard (reloads a /watch page once, at the current "
         "position, when YouTube stops attesting the session)", "Guard installed", "Debugging YouTube playback",
         "YouTube may stop after about a minute again"),
    _row(KILL, ["nc-reset-off.flag"], "Skips the one-time move of an old-format HTTP cache aside (renamed, never deleted)",
         "Moved once per profile", "Debugging cache migration", "Old cache with missing bodies stays in use"),
    _row(KILL, ["popup-gesture-off.flag"], "Allows new windows without a user press while the blocker is on",
         "Popups need a real press/click", "Debugging sites that open windows", "Pop-up ads get through"),
    _row(KILL, ["ublock-frames-off.flag"], "uBlock site rules go back to top-frame only when "
         "ubo-content-mainframe-only.flag is set", "Per-host rules also run in subframes", "A/B of the frames change",
         "Ads inside embedded players reappear"),
    _row(KILL, ["ubo-site-rules-disabled.flag"], "Per-site uBlock content scripts off; the full ~5.4 MB content bundle is "
         "registered instead", "Per-site scripts", "Experiments, fallback",
         "Slower pages (interpreted JavaScript in every page)"),
    _row(KILL, ["ubo-content-disabled.flag"], "No uBlock cosmetic filtering or scriptlets at all", "On",
         "Debugging page breakage", "Network blocking stays; on-page ads and anti-adblock walls return"),
    _row(KILL, ["pages-off.flag"], "Built-in omni://pages off; the old native new-tab page comes back", "Built-in pages",
         "Debugging", "Start, welcome and info pages are gone"),
    _row(KILL, ["smooth-draw-disabled.flag"], "Returns 4K page drawing to the plain SDL paths (no AVX2 doubling/swap)",
         "Fast draw path", "A/B, debugging", "Higher CPU per frame"),
    _row(KILL, ("perf-a-disabled.flag",) + _PERF_STEPS, "All, or one, of the shell present optimisations: s1 paint "
         "back-off, s2 present only changed rows, s3 hashed overlay changes, s4 partial redraw, s5 draw from the "
         "half-size page, s6 transparent-row kernel, s7 deferred hand-off, s8 vblank timing", "All on",
         "A/B, debugging", "More CPU and dropped frames"),
    _row(KILL, ["page-native-4k.flag"], "On a 4K display the page is painted at full resolution instead of half size and "
         "doubled", "Half resolution", "Experiments", "Much slower page paint"),
    _row(KILL, ["playback-rate-disabled.flag"], "playbackRate always 1 (no time stretching)",
         "0.25x to 2x with pitch kept", "Debugging audio", "Speed controls on sites stop working"),
    _row(KILL, ["holepunch-v5-disabled.flag"], "Video playback falls back to V4 buffering (no deep input/decoded queues "
         "for 2-3 s stalls)", "V5", "A/B", "Stutter during main-thread stalls"),
    _row(KILL, ["holepunch-v7-disabled.flag"], "Turns off presenter re-flips that show a newer video picture when no new "
         "canvas arrives", "V7", "A/B", "More dropped video frames"),
    _row(KILL, ["c56-videofix-disabled.flag"], "Video on the plane no longer keeps the earlier page-paint/refresh cadence",
         "Fix on", "A/B", "Video regressions of candidates 55/56"),
    _row(KILL, ["c56-videofix2-disabled.flag"], "Fullscreen video no longer filters repeat mouse moves or parks the mouse "
         "after 3 s", "Fix on", "A/B", "Fullscreen control bar may never fade"),

    _row(OPT_IN, ["yt-attest-log.flag"], "Logs YouTube BotGuard/player/videoplayback request metadata (host, path, "
         "status, sizes; no ids, tokens or cookies) to the process log", "Nothing logged",
         "Debugging YouTube attestation", "Log volume only"),
    _row(OPT_IN, ["ubo-content-mainframe-only.flag"], "uBlock content scripts in the top document only; network blocking "
         "still covers every frame", "Every frame", "Performance experiments", "Less cosmetic filtering in iframes"),
    _row(OPT_IN, ["ubo-content-pageworld.flag"], "uBlock content scripts run in the page's own JavaScript world instead "
         "of an isolated one", "Isolated world", "Experiments", "Pages can see and interfere with the scripts"),
    _row(OPT_IN, ["ubo-site-debug.flag"], "One counter line per per-site script build in the log (no host names)",
         "Silent", "Debugging", "None known"),
    _row(OPT_IN, ["ubo-site-generic-top-only.flag"], "Generic per-site scripts (always-generic.js) top frame only",
         "Follows the main-frame setting", "Experiments", "Less generic filtering in iframes"),
    _row(OPT_IN, ["pages-dev.flag"], "Built-in pages load from /data/omni/pages-dev/ (needs start/index.html there) "
         "instead of the packaged ones", "Packaged pages", "Page development",
         "Broken or old pages if the folder is stale"),
    _row(OPT_IN, ["paint-hold-experimental.flag"], "Paint-hold experiment (OMNI_PAINT_HOLD_V1) on https YouTube hosts "
         "only, never in test modes or private tabs", "Off", "Experiments",
         "Experimental; effect on current builds unclear"),
    _row(OPT_IN, ["perf-a-s8-align.flag"], "Lets s8 restart the refresh timer to line up with vblank",
         "Timer runs at the display period", "Experiments", "A timer that is not re-armed stops the shell"),
    _row(OPT_IN, ["gpu-pages-zerocopy.flag", "gpu-pages-zerocopy-off.flag"], "Experimental GPU-pages builds only: page "
         "frames go to the screen without a CPU copy (needs the async-read flag); -off wins over the on flag",
         "CPU path", "Experiments", "Experimental build path; can make pages fail to show"),
    _row(OPT_IN, ["tab-media-keep-audible.flag"], "A background tab's video keeps playing if it is audible (its hardware "
         "decoder is still released)", "Paused after a short grace time", "Users who want background audio",
         "Background tabs keep using CPU and audio. Newer builds also offer this as the Background audio setting"),

    _row(OVERRIDE, ["ua-desktop.txt"], "First line (20-400 printable ASCII) replaces the desktop user agent",
         "Built-in Safari 17 string", "Site-compatibility tests", "Sites may serve broken or blocked pages"),
    _row(OVERRIDE, ["ua-youtube-tv.txt"], "First line replaces the user agent used on youtube.com/tv",
         "Built-in Cobalt-style TV string", "YouTube TV A/B", "TV app may refuse to load"),
    _row(OVERRIDE, ["jsc-env.txt"], "Up to 32 JSC_<option>=VALUE lines set JavaScriptCore options (GC tuning); cannot "
         "turn the JIT on", "JSC defaults", "Experiments", "Can make pages slow or crash"),
    _row(OVERRIDE, ["raster-env.txt"], "OMNI_RASTER_*=VALUE lines set the page process's threaded-raster settings; other "
         "keys are ignored", "Built-in raster settings", "Experiments", "Can make pages paint wrongly or slowly"),
    _row(OVERRIDE, ["video-quality.txt"], "Video frame scaling: low (bilinear, no mipmaps), none (nearest), direct "
         "(purpose unclear)", "Prescaled bilinear", "Debugging video paint", "Lower picture quality"),
    _row(OVERRIDE, ["display-hz.txt"], "Display rate used to lock video clocks (e.g. 59.94)", "60000/1001 Hz",
         "Experiments on other refresh rates", "Wrong value adds drops or audio pitch shift"),
)

# name -> row
BY_NAME = {name: row for row in ROWS for name in row["files"]}
FLAGS = tuple(n for row in ROWS if row["kind"] != OVERRIDE for n in row["files"])
OVERRIDES = tuple(n for row in ROWS if row["kind"] == OVERRIDE for n in row["files"])
_SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}\Z")


class FlagError(Exception):
    """A change Setup won't make; the message is for the user. Nothing was written."""


def path_for(name):
    """/data/omni/<name> for a name in the table; FlagError for anything else (unknown names, paths, traversal)."""
    if not isinstance(name, str) or name not in BY_NAME or not _SAFE_NAME.match(name) or ".." in name:
        raise FlagError("Setup only changes the developer flags it lists (%r isn't one)." % (name,))
    path = OMNI_DIR + "/" + name
    if posixpath.dirname(posixpath.normpath(path)) != OMNI_DIR:
        raise FlagError("Setup only changes files directly in %s." % OMNI_DIR)
    return path


def state(console):
    """{name: True/False} for every name in the table, from one listing of /data/omni (names only; a folder with a
    flag's name counts as not set and is never touched)."""
    entries = console.listing(OMNI_DIR) or {}
    return {name: bool(name in entries and not entries[name].get("dir")) for name in BY_NAME}


def plan(current, wanted_flags, remove_overrides=()):
    """The changes that turn `current` ({name: present}) into `wanted_flags` ({flag name: on}) plus moving the
    `remove_overrides` aside: [("create" | "remove", name)], flags first. Raises FlagError for any name not allowed
    for that action (unknown names, paths, overrides in wanted_flags, flags in remove_overrides)."""
    changes = []
    for name, on in sorted(wanted_flags.items()):
        path_for(name)
        if BY_NAME[name]["kind"] == OVERRIDE:
            raise FlagError("%s is an override text file; Setup doesn't create or edit those." % name)
        if bool(on) != bool(current.get(name)):
            changes.append(("create" if on else "remove", name))
    for name in sorted(set(remove_overrides)):
        path_for(name)
        if BY_NAME[name]["kind"] != OVERRIDE:
            raise FlagError("%s is a flag; tick or untick it instead." % name)
        if current.get(name):
            changes.append(("remove", name))
    return changes


def describe(changes):
    """Plain lines for the confirmation box."""
    out = []
    for action, name in changes:
        kind = BY_NAME[name]["kind"]
        if action == "create":
            out.append("Turn on %s (%s)" % (name, "turns the feature off" if kind == KILL else "turns the feature on"))
        elif kind == OVERRIDE:
            out.append("Move %s aside (back to: %s)" % (name, BY_NAME[name]["default"]))
        else:
            out.append("Turn off %s (back to the default: %s)" % (name, BY_NAME[name]["default"]))
    return out


def _free_name(names, name, suffix):
    candidate, n = name + suffix, 2
    while candidate in names:
        candidate = "%s%s-%d" % (name, suffix, n)
        n += 1
    return candidate


def apply(console, changes, log=lambda m: None, stamp=None):
    """Make `changes` (from plan). Every name is checked before anything is written. A flag is created as "1\\n"
    (verified upload, then moved into place); a removal moves the file aside as <name>.before-setup-<time>.
    The console's current listing is re-read once: a change that's already true is skipped, and a folder entry with
    that name is refused. Returns {"created": [...], "removed": [(name, parked as)], "skipped": [...]}."""
    checked = []
    for action, name in changes:
        if action not in ("create", "remove"):
            raise FlagError("Unknown change %r." % (action,))
        path_for(name)
        if action == "create" and BY_NAME[name]["kind"] == OVERRIDE:
            raise FlagError("%s is an override text file; Setup doesn't create or edit those." % name)
        checked.append((action, name))
    entries = dict(console.listing(OMNI_DIR) or {})
    for _, name in checked:
        if entries.get(name, {}).get("dir"):
            raise FlagError("%s on the PS5 is a folder, not a flag file. Nothing was changed." % name)
    suffix = PARK_SUFFIX + (stamp or installer._stamp())
    out = {"created": [], "removed": [], "skipped": []}
    for action, name in checked:
        path = path_for(name)
        present = name in entries
        if action == "create":
            if present:
                out["skipped"].append(name)
                continue
            temp = console.put_verified(path, FLAG_DATA)
            console.rename(temp, path)
            entries[name] = {"dir": False, "size": len(FLAG_DATA)}
            out["created"].append(name)
        else:
            if not present:
                out["skipped"].append(name)
                continue
            parked = _free_name(entries, name, suffix)
            console.rename(path, OMNI_DIR + "/" + parked)
            entries[parked] = entries.pop(name)
            out["removed"].append((name, parked))
    log("Developer flags: %d turned on, %d moved aside, %d already as asked." % (
        len(out["created"]), len(out["removed"]), len(out["skipped"])))
    return out
