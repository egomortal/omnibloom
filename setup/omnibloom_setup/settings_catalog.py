"""S15: every user-facing Omni setting file under /data/omni, described, parsed and written as Omni does.

CATALOG has one entry per file of backup.py's "settings" group (a test keeps the two in step): the console path, the
format, the Omni Options group it lives in, a one-line description, whether Omni picks a change up while running
("live"), and, for files the PC editor may change, each setting in it (key, control, allowed values, default).

The formats and rules come from the Omni patch scripts (tools/apply_*.py, each file's parse / serialize) and the
engine's own loaders; each entry names its source. What the editor writes is byte for byte what Omni's own save
writes for those values (golden strings in tests/test_settings_catalog.py).

Files Setup only describes (per-site lists, JSON stores, free text, override and internal files) are not editable
here: other Setup windows or Omni itself edit them. Nothing in NO_TOUCH (parental controls, passwords, personal data,
everything backup.py leaves out on purpose) is ever written; path_for() refuses it.
"""
import re

from . import backup, config

OMNI = backup.OMNI

TOGGLE, CHOICE, NUMBER, HIDDEN = "toggle", "choice", "number", "hidden"
WORD, KV, HDR, LIST, OVERRIDE, INTERNAL = "word", "key-value", "revision", "list", "override", "internal"
EDITABLE_FORMATS = (WORD, KV, HDR)

G_SEARCH = "Browser settings: Search"
G_POINTER = "Browser settings: Pointer and controller"
G_LOOK = "Browser settings: Look and layout"
G_ACCESS = "Browser settings: Accessibility"
G_TABS = "Browser settings: Tabs, memory and start"
G_PRIVACY = "Browser settings: Privacy and data"
G_MEDIA = "Browser settings: Video and captions"
G_DISPLAY = "Controller, theme and display"
G_SITES = "Site settings (per-site lists)"
G_OTHER = "Other Omni data"
GROUPS = (G_SEARCH, G_POINTER, G_LOOK, G_ACCESS, G_TABS, G_PRIVACY, G_MEDIA, G_DISPLAY, G_SITES, G_OTHER)

RESTART_NOTE = ("Omni reads most settings once, when it starts, and rewrites a file from memory when that setting is "
                "changed on the PS5. Close Omni before uploading, then start it again. Settings marked \"live\" are "
                "picked up while Omni runs.")


class SettingError(Exception):
    """A value Omni would not take, or a file Setup does not write; the message is for the user."""


# -- fields --------------------------------------------------------------------------------------------------------
def _field(key, label, kind, default, desc, choices=(), lo=None, hi=None, fmt="%d", step=1, optional=False):
    return {"key": key, "label": label, "kind": kind, "default": default, "desc": desc,
            "choices": tuple(choices), "lo": lo, "hi": hi, "fmt": fmt, "step": step, "optional": optional}


def _tog(key, label, default, desc, off="0", on="1"):
    return _field(key, label, TOGGLE, default, desc, ((off, "Off"), (on, "On")))


def _ch(key, label, default, desc, choices):
    return _field(key, label, CHOICE, default, desc, choices)


def _num(key, label, default, desc, lo, hi, fmt="%d", step=1):
    return _field(key, label, NUMBER, default, desc, lo=lo, hi=hi, fmt=fmt, step=step)


def _idx(names, start=0):
    return tuple((str(i + start), n) for i, n in enumerate(names))


def _entry(path, group, desc, fmt, fields=(), header=None, live=False, canonical=True, need_header=False,
           sep="\t", read=None, source="", where=""):
    return {"path": path, "group": group, "desc": desc, "format": fmt, "fields": tuple(fields), "header": header,
            "live": live, "canonical": canonical, "need_header": need_header, "sep": sep, "read": read,
            "source": source, "where": where, "name": path.rsplit("/", 1)[1]}


# -- single-word readers (each mirrors Omni's loader for that file) ------------------------------------------------
_WS = " \t\r\n"


def _first_line(text):
    return text.split("\n", 1)[0]


def _trimmed(text):
    return text.strip(_WS)


def _theme(text):              # strncmp(value, id, strlen(id)) over omniThemes, the last match wins
    v, out = _first_line(text)[:31], None
    for tok in ("dark", "midnight", "playstation", "purple", "contrast"):
        if v.startswith(tok):
            out = tok
    return out


def _autohide(text):           # strncmp(value, "off", 3) != 0 -> on
    return "off" if _first_line(text)[:15].startswith("off") else "on"


def _controller(text):         # !strncmp(value, "playstation", 11)
    return "playstation" if _first_line(text)[:31].startswith("playstation") else "xbox"


def _display(text):            # fscanf("%15s %c") == 1: exactly one word
    words = text.split()
    return words[0] if len(words) == 1 and len(words[0]) <= 15 else None


def _youtube(text):            # OmniYoutubeTv::modeIsTv: "tv", any case, surrounding space ignored
    return "tv" if _trimmed(_first_line(text) + "\n").lower() == "tv" else "normal"


def _lower_trim(text):         # OmniUiAccent::parse / OmniKbLayouts::parseId / history keep / pointer-large
    return _trimmed(text).lower()


def _accent(text):
    return _lower_trim(text)


def _exact_trim(text):
    return _trimmed(text)


def _first_nonempty(text):     # OmniHistoryKeep::parse: the first non-empty line, spaces / tabs / CR trimmed
    for line in text.split("\n"):
        t = line.strip(" \t\r")
        if t:
            return t
    return ""


_UIS_ALIASES = {"small": "small", "s": "small", "normal": "normal", "default": "normal", "m": "normal",
                "large": "large", "l": "large", "xlarge": "xlarge", "extralarge": "xlarge", "xl": "xlarge"}


def _ui_scale(text):           # OmniUiScale::parse: first non-empty line, spaces / - / _ dropped, lower case, aliases
    s = ""
    for c in text:
        if c in "\r\n":
            if s:
                break
            continue
        if c in " \t-_":
            continue
        s += c.lower() if "A" <= c <= "Z" else c
    return _UIS_ALIASES.get(s)


def _norm_code(c):             # OmniL10n::normCode: "pt_BR" -> "pt", "ES" -> "es", "auto"; else ""
    c = c.strip()
    if c.lower() == "auto":
        return "auto"
    base = re.split(r"[_-]", c, maxsplit=1)[0]
    return base.lower() if re.fullmatch(r"[A-Za-z]{2,3}", base) else ""


def _ui_lang(text):            # OmniL10n::parseChoice: first word of the first line that is not empty or a comment
    for line in text.split("\n"):
        t = line.lstrip(" \t\r")
        if not t or t[0] == "#":
            continue
        return _norm_code(re.split(r"[ \t\r#]", t, maxsplit=1)[0]) or "auto"
    return "auto"


def _dark_style(text):         # fscanf("%d") in 0..3 (OMNI_DARK_CHOICE_V1 0-2, OMNI_DARK_SCHEDULE_V1 adds 3)
    m = re.match(r"\s*([+-]?\d+)", text)
    return m.group(1).lstrip("+") if m and m.group(1).lstrip("+") in ("0", "1", "2", "3") else None


# -- the catalog -----------------------------------------------------------------------------------------------------
_ENGINES = ("Google", "DuckDuckGo", "Bing", "Startpage", "Brave", "Ecosia", "Qwant", "Custom (search-custom.txt)")
_THEMES = (("dark", "Dark"), ("midnight", "Midnight"), ("playstation", "PlayStation"), ("purple", "Purple"),
           ("contrast", "High contrast"))
_ACCENTS = (("default", "Theme default"), ("blue", "Blue"), ("teal", "Teal"), ("green", "Green"), ("amber", "Amber"),
            ("orange", "Orange"), ("red", "Red"), ("pink", "Pink"), ("violet", "Violet"))
_KB = (("qwerty", "QWERTY"), ("azerty", "AZERTY (French)"), ("qwertz", "QWERTZ (German)"),
       ("nordic", "Nordic (Swedish, Finnish)"), ("danish", "Nordic (Danish, Norwegian)"), ("spanish", "Spanish"),
       ("portuguese", "Portuguese"))
_LANGS = (("auto", "Automatic (PS5 language)"), ("en", "English"), ("es", "Español"), ("fr", "Français"),
          ("de", "Deutsch"), ("pt", "Português"))
_FILTERS = (("off", "Off"), ("protanopia", "Protanopia"), ("deuteranopia", "Deuteranopia"),
            ("tritanopia", "Tritanopia"), ("greyscale", "Greyscale"), ("invert", "Invert"))
_HOURS = tuple(("%02d:00" % h, "%02d:00" % h) for h in range(24))

CATALOG = (
    # ---- browser-settings.txt (OMNI_FEATURES_V1 omniFxLoad / omniFxSave, + OMNI_POINTER_TUNE_V1, OMNI_SEARCH_ENGINE_V1)
    _entry(OMNI + "browser-settings.txt", G_SEARCH, "Search engine, page zoom, text size, pointer and D-pad choices "
           "(the home page and pointer picture lines are kept as they are)", KV, canonical=False, source="OmniBrowserSettings.h, "
           "apply_pointer_tune.py, apply_search_engine.py", fields=(
               _ch("search", "Search engine", "0", "Where address-bar searches go (Custom uses search-custom.txt)",
                   _idx(_ENGINES)),
               _num("zoom", "Default page zoom", "1.000", "Zoom for sites without their own (0.5 to 2.5)", 0.5, 2.5,
                    "%.3f", 0.05),
               _ch("text", "Text size", "1.000", "Page text size", tuple(("%.3f" % v, "%d%%" % round(v * 100)) for v in
                                                                    (0.85, 1.0, 1.15, 1.3, 1.5, 1.75))),
               _ch("pointer", "Pointer speed", "1", "Stick pointer speed", _idx(("Slow", "Normal", "Fast", "Very fast"))),
               _ch("ptrcurve", "Pointer speed curve", "1", "How the pointer speeds up with the stick",
                   _idx(("Linear", "Smooth", "Fast"))),
               _ch("snapsize", "Pointer snaps to links", "2", "Search radius for snapping to the nearest link "
                   "(also writes snap 0/1 for older builds)", _idx(("Off", "Light (24 px)", "Normal (36 px)",
                                                                   "Strong (56 px)"))),
               _ch("dpad", "D-pad left/right", "0", "While browsing", _idx(("Back / forward", "Previous / next tab"))),
               _ch("deadzone", "Stick dead zone", "1", "How far the stick moves before the pointer does",
                   _idx(("Small", "Medium", "Large", "Extra large"))),
               _ch("ptrsize", "Pointer size", "2", "Size of the pointer picture",
                   _idx(tuple("%d%%" % p for p in (50, 75, 100, 125, 150, 175, 200, 250, 300)))),
               _num("ptrcolour", "Pointer colour", "0", "Colour index 0-11 (0 white)", 0, 11),
               _tog("ptroutline", "Pointer outline", "1", "Contrasting outline around the pointer"),
               _ch("ptropacity", "Pointer opacity", "0", "How see-through the pointer is",
                   _idx(tuple("%d%%" % p for p in (100, 90, 80, 70, 60, 50, 40)))),
           )),
    _entry(OMNI + "browser-more.txt", G_TABS, "Search suggestions, tab limit, tabs kept loaded and memory guards", KV,
           source="OmniFeatures3.h omniF3Load / omniF3Save", fields=(
               _tog("suggest", "Search suggestions", "1", "Suggestions from the search engine while typing (never in "
                    "private tabs)"),
               _field("dark", "Dark pages (old switch)", HIDDEN, "0", "Kept for older builds; Dark mode is "
                      "dark-style.txt"),
               _num("tablimit", "Tab limit", "8", "Most tabs open at once (Omni steps 4, 6, 8, 12, 16)", 4, 16),
               _num("keeploaded", "Tabs kept loaded", "6", "Older background tabs are unloaded (Omni steps 2-16)",
                    1, 16),
               _num("refuse_mib", "Refuse new tabs below (MiB)", "160", "Free memory under which new tabs are refused",
                    0, 4096, step=16),
               _num("unload_mib", "Unload tabs below (MiB)", "112", "Free memory under which background tabs unload",
                    0, 4096, step=16),
           )),
    _entry(OMNI + "search-custom.txt", G_SEARCH, "Custom search engine: one https:// address with %s", LIST,
           where="Omni: Browser settings > Search engine > Custom"),
    _entry(OMNI + "site-search.txt", G_SEARCH, "Offer to save a site's own search", KV, source="OmniSiteSearch.h "
           "parseOffer / offerText", fields=(_tog("offer", "Offer site searches", "1", "Offer to add a site's search "
                                                  "as a shortcut"),)),
    _entry(OMNI + "search-shortcuts.txt", G_SEARCH, "Search shortcut keywords (\"yt cats\")", LIST, live=True,
           where="Setup: Search shortcuts and Quick access"),

    _entry(OMNI + "ui-theme.txt", G_DISPLAY, "Theme of Omni's own screens", WORD, read=_theme, source="OmniBrowser.cpp "
           "saveUiTheme, OmniHighContrast.h", fields=(_ch("", "Theme", "dark", "Colours of bars, panels and keyboard",
                                                          _THEMES),)),
    _entry(OMNI + "ui-theme-prev.txt", G_DISPLAY, "The theme High contrast goes back to (written by Omni)", INTERNAL),
    _entry(OMNI + "ui-autohide.txt", G_DISPLAY, "Hide the bars while browsing", WORD, read=_autohide,
           source="OmniBrowser.cpp saveAutoHide", fields=(_tog("", "Auto-hide bars", "on", "Bars hide while you browse "
                                                               "and come back on any input", off="off", on="on"),)),
    _entry(OMNI + "controller-style.txt", G_DISPLAY, "Button icons shown in hints", WORD, read=_controller,
           source="OmniBrowser.cpp saveControllerStyle", fields=(_ch("", "Controller icons", "xbox", "Which button "
                                                                     "glyphs the hints show", (("xbox", "Xbox"), ("playstation", "PlayStation"))),)),
    _entry(OMNI + "display-mode.txt", G_DISPLAY, "Output resolution", WORD, read=_display, source="OmniBrowser.cpp "
           "omniDisplayModes", fields=(_ch("", "Resolution", "1080", "Takes effect when Omni starts; a failed start "
                                           "falls back to 1080p once", (("1080", "1080p"), ("1440", "1440p"), ("2160", "4K (2160p)"))),)),
    _entry(config.OMNI_HDR_PREF, G_DISPLAY, "HDR video output", HDR, source="OmniHdrPreference.h (revision<TAB>mode)",
           fields=(_ch("mode", "HDR", "off", "HDR10 output for HDR video", (("off", "Off"), ("auto", "Auto"),
                                                                           ("on", "On"))),)),
    _entry(OMNI + "video-quality.txt", G_MEDIA, "Video frame scaling override (developer file)", OVERRIDE,
           where="Setup: Advanced: Omni developer flags (move aside only)"),
    _entry(OMNI + "youtube-mode.txt", G_MEDIA, "Open YouTube in its TV layout", WORD, read=_youtube,
           source="apply_youtube_tv.py", fields=(_ch("", "YouTube", "normal", "TV mode opens YouTube home and watch "
                                                    "pages in the TV layout", (("normal", "Normal"), ("tv", "TV mode"))),)),
    _entry(OMNI + "ui-bars.txt", G_LOOK, "Show or hide the Quick access row and the bottom button bar", KV, sep="=",
           source="apply_bars_hide.py omniBarsLoad / omniBarsSave", fields=(
               _ch("qa", "Quick access row", "shown", "Hidden gives its space to the page",
                   (("shown", "Shown"), ("hidden", "Hidden"))),
               _ch("hints", "Bottom button bar", "shown", "Hidden gives its space to the page",
                   (("shown", "Shown"), ("hidden", "Hidden"))),
           )),
    _entry(OMNI + "quick-access.txt", G_LOOK, "Buttons in the Quick access row", LIST,
           where="Setup: Search shortcuts and Quick access"),
    _entry(OMNI + "ui-accent.txt", G_LOOK, "Accent colour on top of the theme", WORD, read=_accent,
           source="OmniUiAccent.h", fields=(_ch("", "Accent colour", "default", "Focus rings, selected rows, switches "
                                                "(High contrast keeps its yellow)", _ACCENTS),)),
    _entry(OMNI + "ui-scale.txt", G_LOOK, "Size of Omni's own panels and text", WORD, read=_ui_scale,
           source="OmniUiScale.h", fields=(_ch("", "Interface size", "normal", "Zooms panels, notices and the "
                                               "keyboard", (("small", "Small"), ("normal", "Normal"), ("large", "Large"),
                                                            ("xlarge", "Extra large"))),)),
    _entry(OMNI + "ui-lang.txt", G_LOOK, "Language of Omni's own screens", WORD, read=_ui_lang,
           source="apply_ui_lang.py parseChoice", fields=(_ch("", "Language", "auto", "Automatic follows the PS5 "
                                                              "system language", _LANGS),)),
    _entry(OMNI + "kb-layout.txt", G_LOOK, "Letter layout of the on-screen keyboard", WORD, read=_exact_trim,
           source="OmniKbLayouts.h parseId", fields=(_ch("", "Keyboard layout", "qwerty", "Accents: hold Cross on a "
                                                         "letter", _KB),)),
    _entry(OMNI + "tips-seen.txt", G_LOOK, "Tips: on or off, and which tips were already shown", KV, header="omni-tips\t1",
           canonical=False, source="apply_tips.py parse / serialize", fields=(
               _tog("enabled", "Show tips", "1", "One short tip at a time, when it fits what you are doing"),)),
    _entry(OMNI + "shortcuts.txt", G_LOOK, "Address-keyboard shortcut tiles (address and title per line)", LIST,
           where="Omni: address keyboard > Shortcuts"),
    _entry(OMNI + "shortcuts-map.txt", G_POINTER, "Controller button remapping (button<TAB>action lines)", LIST,
           where="Omni: Browser settings > Button mapping"),
    _entry(OMNI + "spatial-nav.txt", G_POINTER, "What the D-pad does on a page", KV, source="OmniSpatialNav.h",
           fields=(_ch("mode", "D-pad navigation", "0", "Scroll, or move the pointer between links",
                       (("0", "Scroll"), ("1", "Move between links"))),)),
    _entry(OMNI + "scroll-plus.txt", G_POINTER, "Scroll speed and smooth scrolling", KV, source="apply_scroll_plus.py",
           fields=(_ch("speed", "Scroll speed", "1", "Stick and D-pad scrolling", _idx(("Slow", "Normal", "Fast"))),
                   _field("smooth", "Smooth scrolling", CHOICE, "", "Not set leaves WebKit's own default",
                          (("", "Not set (WebKit default)"), ("0", "Off"), ("1", "On")), optional=True))),

    _entry(OMNI + "pointer-large.txt", G_ACCESS, "Double-size pointer", WORD, read=_exact_trim,
           source="OmniHighContrast.h parseLarge", fields=(_tog("", "Large pointer", "off", "Pointer drawn at twice "
                                                                "its size", off="off", on="on"),)),
    _entry(OMNI + "night-light.txt", G_ACCESS, "Warm tint over everything Omni shows, with a schedule", KV,
           header="# Omni night light (OMNI_NIGHT_LIGHT_V1)", source="apply_night_light.py OmniNightLight.h", fields=(
               _ch("mode", "Night light", "off", "Needs the title's GPU present", (("off", "Off"), ("on", "On"),
                                                                                  ("scheduled", "Scheduled"))),
               _ch("last", "Quick toggle turns on", "on", "What the Night light tile switches back to",
                   (("on", "On"), ("scheduled", "Scheduled"))),
               _ch("warmth", "Night light warmth", "3", "1 (slight) to 5 (warmest)", _idx(("1", "2", "3", "4", "5"), 1)),
               dict(_ch("start", "Night light from", "21:00", "Start of the schedule (console time, HH:MM)", _HOURS),
                    time=True),
               dict(_ch("end", "Night light until", "07:00", "End of the schedule; also the Dark mode schedule",
                        _HOURS), time=True),
           )),
    _entry(OMNI + "colour-filter.txt", G_ACCESS, "Colour filter for colour-vision deficiency", KV,
           header="# Omni colour filter (OMNI_COLOUR_FILTER_V1)", source="apply_colour_filter.py", fields=(
               _ch("filter", "Colour filter", "off", "Correction over everything Omni shows (needs the GPU present)",
                   _FILTERS),
               _ch("last", "Quick toggle turns on", "deuteranopia", "What the Colour filter tile switches back to",
                   _FILTERS[1:]),
           )),
    _entry(OMNI + "dark-style.txt", G_ACCESS, "Dark mode for web pages", WORD, read=_dark_style,
           source="apply_dark_qa.py, apply_dark_schedule.py", fields=(_ch("", "Dark mode", "0", "Natural: sites with a "
                                                                          "dark theme use it; Forced: every page dark",
                                                                          _idx(("Off", "Natural", "Forced",
                                                                                "Night light schedule"))),)),
    _entry(OMNI + "captions.txt", G_MEDIA, "Look of video captions on every site", KV, header="# Omni captions v1",
           source="apply_caption_style.py OmniCaptionStyle.h", fields=(
               _ch("size", "Caption size", "100", "Text size of the captions",
                   tuple((p, p + "%") for p in ("75", "100", "150", "200", "250"))),
               _ch("colour", "Caption colour", "white", "", (("white", "White"), ("yellow", "Yellow"), ("cyan", "Cyan"))),
               _ch("background", "Caption background", "semi", "Box behind the text",
                   (("none", "None"), ("semi", "Shaded"), ("solid", "Solid"))),
               _ch("font", "Caption font", "default", "", (("default", "Default"), ("sans", "Sans"), ("serif", "Serif"),
                                                          ("mono", "Monospace"))),
               _ch("edge", "Caption edge", "none", "Keeps text readable on bright scenes",
                   (("none", "None"), ("outline", "Outline"), ("shadow", "Shadow"))),
               _ch("position", "Caption position", "bottom", "Higher: clear of a TV's bottom edge",
                   (("bottom", "Bottom"), ("higher", "Higher"))),
           )),

    _entry(OMNI + "startup.txt", G_TABS, "What Omni opens when it starts", KV, header="omni-startup\t1",
           need_header=True, source="apply_startup_choice.py", fields=(
               _ch("choice", "On start", "0", "Continue where you left off, start page, home page or a saved session",
                   _idx(("Continue where you left off", "Start page", "Home page", "A saved session"))),
               _field("session", "Saved session name", HIDDEN, "", "Chosen on the PS5; kept as it is"),
           )),
    _entry(OMNI + "tab-sleep.txt", G_TABS, "Put idle background tabs to sleep", KV, source="OmniTabSleep.h", fields=(
        _ch("minutes", "Sleep idle tabs", "30", "After this long in the background",
            (("0", "Off"), ("10", "10 minutes"), ("30", "30 minutes"), ("60", "60 minutes"))),
        _tog("pinned", "Include pinned tabs", "0", "Pinned tabs may sleep too"),
    )),
    _entry(OMNI + "history-keep.txt", G_PRIVACY, "How long history is kept", WORD, read=_first_nonempty,
           source="apply_history_keep.py", fields=(_ch("", "Keep history", "forever", "Older entries are removed "
                                                       "hourly; Don't save stops recording",
                                                       (("forever", "Forever"), ("3m", "3 months"), ("1m", "1 month"),
                                                        ("1w", "1 week"), ("1d", "1 day"), ("off", "Don't save history"))),)),
    _entry(OMNI + "data-saver.txt", G_PRIVACY, "Data saver: lower video quality, no autoplay, fewer downloads", KV,
           header="omni-data-saver\t1", need_header=True, live=True, source="apply_data_saver.py (the web process "
           "re-reads the file every 2 s)", fields=(
               _tog("on", "Data saver", "0", "Turns the parts below on"),
               _tog("video", "Cap video at 480p", "1", "While Data saver is on"),
               _tog("autoplay", "Block autoplay", "1", "While Data saver is on"),
               _tog("fonts", "Block web fonts", "0", "While Data saver is on"),
               _tog("prefetch", "No link prefetch", "1", "While Data saver is on"),
           )),

    _entry(OMNI + "site-dark.txt", G_SITES, "Per-site Always dark / Never dark", LIST, where="Omni: Site settings"),
    _entry(OMNI + "site-zoom.txt", G_SITES, "Per-site zoom (host<TAB>percent)", LIST, where="Omni: Site settings"),
    _entry(OMNI + "site-ua.txt", G_SITES, "Sites shown as the mobile version", LIST, where="Omni: Site settings"),
    _entry(OMNI + "site-permissions.txt", G_SITES, "Per-site permissions (pop-ups, storage)", LIST,
           where="Omni: Site settings"),
    _entry(OMNI + "ublock-allowlist.txt", G_SITES, "Sites with uBlock turned off", LIST, where="Omni: Site settings"),
    _entry(OMNI + "autoplay.txt", G_SITES, "Per-site autoplay: allow, no sound or block", LIST,
           where="Omni: Site settings"),
    _entry(OMNI + "https-only.txt", G_SITES, "HTTPS-only mode and its per-site exceptions", LIST,
           where="Omni: Browser settings > HTTPS-only"),
    _entry(OMNI + "popup-allow.txt", G_SITES, "Sites allowed to open pop-ups", LIST, where="Omni: Site settings"),
    _entry(OMNI + "site-volume.txt", G_SITES, "Per-site volume (site<TAB>percent)", LIST, where="Omni: Site settings"),
    _entry(OMNI + "site-tweaks.txt", G_SITES, "Per-site page tweaks", LIST, where="Omni: Site settings > Page tweaks"),
    _entry(OMNI + "reader-sites.txt", G_SITES, "Sites that always open in reader view", LIST,
           where="Omni: Site settings"),
    _entry(OMNI + "game-sites.txt", G_SITES, "Sites that open in game mode", LIST, where="Omni: Site settings"),
    _entry(OMNI + "refresh-sites.txt", G_SITES, "Per-site auto refresh (host<TAB>seconds)", LIST,
           where="Omni: Site settings"),
    _entry(OMNI + "translate.txt", G_SITES, "Translation consent and per-site always / never", LIST,
           where="Omni: Translate"),
    _entry(OMNI + "addons/state.json", G_OTHER, "Add-ons switched on and their per-site switches", LIST,
           where="Omni: Add-ons"),
    _entry(backup.DL_STATE + "schedule.json", G_OTHER, "Downloads app schedule", LIST, where="Omni: Downloads app"),
    _entry(OMNI + "apps.json", G_OTHER, "Web apps on the start page", LIST, where="Omni: Open as app"),
    _entry(OMNI + "start-page.json", G_OTHER, "Start page layout", LIST, where="Omni: Start page > Customise"),
)

BY_PATH = {e["path"]: e for e in CATALOG}
EDITABLE = tuple(e["path"] for e in CATALOG if e["format"] in EDITABLE_FORMATS)

# Never written, never offered: parental controls, passwords, sessions, every personal group of a backup and everything
# a backup leaves out on purpose (backup.NEVER), plus the folders of backup.FOLDERS.
NO_TOUCH = tuple(sorted(set(
    (OMNI + "parental.txt", OMNI + "passwords.txt", OMNI + "passwords.key", OMNI + "autofill.txt",
     OMNI + "session.txt", OMNI + "sessions.txt", OMNI + "history.txt", config.OMNI_BOOKMARKS)
    + tuple(f["path"] for f in backup.FILES if f["group"] != "settings")
    + tuple(f["dir"] for f in backup.FOLDERS) + tuple(backup.NEVER))))
assert not set(EDITABLE) & set(NO_TOUCH)


def _touches_no_touch(path):
    for p in NO_TOUCH:
        if path == p or (p.endswith("/") and path.startswith(p)):
            return True
        if "*" in p and re.fullmatch(re.escape(p).replace(r"\*", "[^/]*"), path):
            return True
    return False


def path_for(path):
    """`path` when the editor may write it; SettingError for anything else (no-touch, lists, unknown, traversal)."""
    if not isinstance(path, str) or ".." in path or "\\" in path or _touches_no_touch(path):
        raise SettingError("Setup never changes %r from the settings editor." % (path,))
    e = BY_PATH.get(path)
    if e is None or e["format"] not in EDITABLE_FORMATS:
        raise SettingError("%s isn't a setting the PC editor changes%s." % (
            path, "" if e is None or not e["where"] else " (use %s)" % e["where"]))
    return path


def fields(entry, hidden=False):
    return [f for f in entry["fields"] if hidden or f["kind"] != HIDDEN]


def defaults(entry):
    return {f["key"]: f["default"] for f in entry["fields"]}


# -- values ----------------------------------------------------------------------------------------------------------
def _atoi(v):
    m = re.match(r"\s*([+-]?\d+)", v)
    return int(m.group(1)) if m else 0


def _atof(v):
    m = re.match(r"\s*([+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?)", v)
    return float(m.group(1)) if m else 0.0


def _bs_value(key, v):
    """browser-settings.txt as omniFxLoad reads it (atoi / atof, clamped or range-checked); None = keep the default."""
    if key in ("search", "pointer", "dpad", "deadzone", "ptrsize", "ptrcolour", "ptropacity", "ptrcurve", "snapsize"):
        hi = {"search": 7, "pointer": 3, "dpad": 1, "deadzone": 3, "ptrsize": 8, "ptrcolour": 11, "ptropacity": 6,
              "ptrcurve": 2, "snapsize": 3}[key]
        if key in ("ptrcurve", "snapsize"):       # OmniPointerTune::parseIndex: digits only, in range
            return v if re.fullmatch(r"\d{1,3}", v) and int(v) <= hi else None
        return str(min(max(_atoi(v), 0), hi))
    if key in ("zoom", "text"):
        z = _atof(v)
        lo, hi = (0.5, 2.5) if key == "zoom" else (0.85, 1.75)
        return "%.3f" % z if lo <= z <= hi else None
    if key in ("snap", "ptroutline"):
        return "0" if v == "0" else "1"
    return None


def hhmm(raw):
    """OmniNightLight::parseHhmm ("21:00", "7:30", "21"), written back as hhmm() does ("%02d:%02d"); None if bad."""
    if not isinstance(raw, str):
        return None
    m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?", raw)
    if not m or len(raw) > 5:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return "%02d:%02d" % (h, mi) if h <= 23 and mi <= 59 else None


def accept(field, raw):
    """The token Omni would take for `raw` in this field, or None (Omni keeps its default)."""
    if field["kind"] == HIDDEN:
        return raw
    if field.get("time"):
        return hhmm(raw)
    if field["kind"] == NUMBER:
        try:
            n = float(raw) if "." in field["fmt"] else int(raw)
        except (TypeError, ValueError):
            return None
        return field["fmt"] % n if field["lo"] <= n <= field["hi"] else None
    return raw if raw in [c[0] for c in field["choices"]] else None


def _lines(text):
    return text.split("\n") if text else []


def parse(entry, data):
    """{key: token} as Omni reads `data` (bytes / text; None = no file), defaults where Omni would use them.
    A word file's single setting has key ""."""
    vals = defaults(entry)
    if data is None:
        return vals
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    if text.startswith("﻿") and entry["format"] != WORD:
        text = text[1:]
    if entry["format"] == WORD:
        tok = entry["read"](text)
        f = entry["fields"][0]
        if entry["path"].endswith("ui-lang.txt") and tok and re.fullmatch(r"[a-z]{2,3}", tok):
            vals[""] = tok                          # a code set by hand stays (Omni keeps it in its cycle)
        elif tok is not None and accept(f, tok) is not None:
            vals[""] = tok
        return vals
    if entry["format"] == HDR:
        rev, mode = hdr_read(text)
        vals["mode"] = mode
        return vals
    by_key = {f["key"]: f for f in entry["fields"]}
    lines = _lines(text)
    if entry["need_header"] and (not lines or lines[0].rstrip("\r") != entry["header"]):
        return vals
    browser = entry["name"] == "browser-settings.txt"
    raw_snap, raw_size = None, None
    for line in lines:
        line = line.rstrip("\r")
        if entry["name"] in ("tab-sleep.txt", "scroll-plus.txt", "spatial-nav.txt"):
            line = line.rstrip("\r ")
        if not line or line[0] == "#":
            continue
        if entry["sep"] == "=":                     # ui-bars.txt: strncmp prefixes ("qa=hidden", "hints=hidden")
            for f in entry["fields"]:
                if line.startswith(f["key"] + "=hidden"):
                    vals[f["key"]] = "hidden"
            continue
        t = line.find(entry["sep"])
        if t < 0:
            continue
        k, v = line[:t], line[t + 1:]
        if entry["name"] == "tips-seen.txt":
            k, v = k.strip(), v.strip()
        if entry["name"] == "captions.txt" and k == "color":
            k = "colour"
        if browser:
            if k == "snap":
                raw_snap = v != "0"
            elif k == "snapsize":
                raw_size = _bs_value(k, v)
            elif k in by_key:
                got = _bs_value(k, v)
                if got is not None:
                    vals[k] = got
            continue
        if entry["name"] == "tab-sleep.txt" and k == "minutes" and re.fullmatch(r"\d{1,6}", v):
            v = str(min((0, 10, 30, 60), key=lambda s: (abs(s - int(v)), (0, 10, 30, 60).index(s))))
        if entry["name"] == "tab-sleep.txt" and k == "pinned" and re.fullmatch(r"\d{1,6}", v):
            v = "1" if int(v) else "0"
        if entry["name"] == "browser-more.txt" and k in by_key:   # omniF3Load: atoi, then != 0 or clamped
            n = _atoi(v)
            v = str(int(n != 0)) if k in ("suggest", "dark") else str(min(max(n, by_key[k]["lo"]), by_key[k]["hi"]))
        if k in by_key and k != "":
            got = accept(by_key[k], v)
            if got is not None:
                vals[k] = got
    if browser:                                     # OmniPointerTune::snapLevel(stored, snapOn)
        if raw_snap is False:
            vals["snapsize"] = "0"
        elif raw_size in ("1", "2", "3"):
            vals["snapsize"] = raw_size
        else:
            vals["snapsize"] = "2"
    return vals


def hdr_read(text):
    """OmniHdrPreference::read: (revision, mode); a missing or unreadable file is revision 1, Off."""
    if text is None:
        return 1, "off"
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    if not text or len(text.encode("utf-8")) >= 65 or not text.endswith("\n"):
        return 1, "off"
    s = text[:-1]
    if "\t" not in s:
        return 1, "off"
    r, m = s.split("\t", 1)
    if not re.fullmatch(r"\d{1,10}", r) or not 0 < int(r) <= 2147483646 or m not in ("off", "auto", "on"):
        return 1, "off"
    return int(r), m


def problems(entry, values):
    """[(key, message)] for each value Omni would not take."""
    out = []
    for f in entry["fields"]:
        v = values.get(f["key"], f["default"])
        if f["kind"] == HIDDEN:
            if not isinstance(v, str) or "\n" in v or "\r" in v or "\t" in v:
                out.append((f["key"], "%s: one line, no tabs" % f["label"]))
            continue
        if f["optional"] and v == "":
            continue
        if accept(f, v) != v:
            if f["kind"] == NUMBER:
                out.append((f["key"], "%s: a number from %s to %s" % (f["label"], f["lo"], f["hi"])))
            elif entry["path"].endswith("ui-lang.txt") and isinstance(v, str) and re.fullmatch(r"[a-z]{2,3}", v):
                continue
            else:
                out.append((f["key"], "%s: not one of Omni's choices (%r)" % (f["label"], v)))
    return out


def _line(entry, key, token):
    return key + entry["sep"] + token


def serialize(entry, values, old=None):
    """The file's bytes for `values`, as Omni's own save writes them. `old` (bytes / text / None): the file on the
    PS5, needed for files Omni keeps other lines in (browser-settings.txt, tips-seen.txt) and for the HDR revision.
    Raises SettingError for a value Omni would not take or a file the editor does not write."""
    path_for(entry["path"])
    bad = problems(entry, values)
    if bad:
        raise SettingError("%s: %s." % (entry["name"], bad[0][1]))
    vals = defaults(entry)
    vals.update({k: v for k, v in values.items() if k in vals})
    if entry["format"] == WORD:
        return (vals[""] + "\n").encode("utf-8")
    if entry["format"] == HDR:
        rev, _ = hdr_read(old)
        return ("%d\t%s\n" % (rev + 1, vals["mode"])).encode("ascii")
    if entry["canonical"]:
        out = [entry["header"]] if entry["header"] else []
        for f in entry["fields"]:
            if f["optional"] and vals[f["key"]] == "":
                continue
            out.append(_line(entry, f["key"], vals[f["key"]]))
        return ("\n".join(out) + "\n").encode("utf-8")
    return _patch(entry, vals, old)


def _derived(entry, vals):
    """The key / value lines to write: browser-settings.txt also writes snap 0/1 for its snap strength."""
    out = [(f["key"], vals[f["key"]]) for f in entry["fields"] if f["kind"] != HIDDEN]
    if entry["name"] == "browser-settings.txt":
        out.append(("snap", "0" if vals["snapsize"] == "0" else "1"))
    return out


def _patch(entry, vals, old):
    """Files Omni keeps other lines in: each written key's lines replaced in place (the first kept, repeats dropped),
    keys not there yet appended, every other line kept byte for byte (line ending of the file kept)."""
    text = old.decode("utf-8", "replace") if isinstance(old, bytes) else (old or "")
    first = text.find("\n")
    nl = "\r\n" if first > 0 and text[first - 1] == "\r" else "\n"
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    lines = [l[:-1] if l.endswith("\r") else l for l in lines]
    want = dict(_derived(entry, vals))
    done, out = set(), []
    if entry["header"] and not any(l == entry["header"] for l in lines):
        out.append(entry["header"])
    for l in lines:
        t = l.find(entry["sep"])
        k = l[:t].strip() if t >= 0 else None
        if k in want:
            if k not in done:
                out.append(_line(entry, k, want[k]))
                done.add(k)
            continue
        out.append(l)
    for k, v in _derived(entry, vals):
        if k not in done:
            out.append(_line(entry, k, v))
    return (nl.join(out) + nl).encode("utf-8")


def describe_value(field, token):
    """What the Options row shows for `token`."""
    if field["kind"] == NUMBER or field["kind"] == HIDDEN:
        return token
    for t, label in field["choices"]:
        if t == token:
            return label
    return token
