"""OMNI_DARK_CHOICE_V1 + OMNI_QA_CUSTOM_V1 + OMNI_SETTINGS_CREATE_V1 (2026-11-13, owner requests).

Dark mode: one setting, Off / Natural / Forced (Browser settings > "Dark mode", stored in /data/omni/dark-style.txt).
  Natural  Omni asks every site for dark (prefers-color-scheme: dark). Sites with their own dark theme use it; the
           rest stay exactly as their designers made them.
  Forced   the same, and pages that stay light are darkened by Omni's filter (the old "Dark pages (all sites)").
  A site set to "Always dark" (the Dark mode quick button / Site settings) is forced in both modes.
  Without dark-style.txt the old setting carries over: "Dark pages (all sites)" on = Forced, off = Off.

Quick access row (the row of buttons in the top bar): you choose its buttons and their order, up to 6
(Browser settings > "Quick access buttons...", stored in /data/omni/quick-access.txt). Default: uBlock, Dark mode,
Apps, Add-ons (as before).

Create button: opens Browser settings (the full list, which links to "Controller, theme and display..."), so Dark mode,
Quick access buttons and the Quick bar are one press away. Create again closes it.

Apply AFTER apply_l2_chords.py (it anchors on that patch's Settings rows and defines omniL2Copy / omniL2Paste).
usage: apply_dark_qa.py <engine tree>
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_DARK_CHOICE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'


def patch(name, edits, regex_edits=()):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s or 'OMNI_QA_CUSTOM_V1' in s or 'OMNI_SETTINGS_CREATE_V1' in s:
        return 'already'
    for old, new in edits:
        old, new = old.replace('\n', nl), new.replace('\n', nl)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old[:90]))
        s = s.replace(old, new, 1)
    for pattern, new in regex_edits:
        new = new.replace('\n', nl)
        found = re.findall(pattern, s, flags=re.S)
        if len(found) != 1:
            sys.exit('%s: pattern found %d times: %r' % (name, len(found), pattern[:90]))
        s = re.sub(pattern, lambda _: new, s, count=1, flags=re.S)
    p.write_bytes(s.encode('utf-8'))
    return 'applied'


# ---------------------------------------------------------------- dark mode: OmniDarkPages.h
STYLE = '''static bool omniDkWant(const std::string& url)
{'''
STYLE_NEW = '''// OMNI_DARK_CHOICE_V1: 0 Off, 1 Natural (ask sites for dark only), 2 Forced (ask, and darken pages that stay light).
static int omniDarkStyleCache = -2;
static void omniF3Save();
static void omniDkChanged();
static int omniDarkStyle()
{
    if (omniDarkStyleCache == -2) {
        omniDarkStyleCache = -1;
        if (FILE* f = fopen(omniData("dark-style.txt").c_str(), "r")) {
            int v = -1;
            if (fscanf(f, "%d", &v) == 1 && v >= 0 && v <= 2) omniDarkStyleCache = v;
            fclose(f);
        }
    }
    if (omniDarkStyleCache >= 0) return omniDarkStyleCache;
    omniF3Load();
    return omniF3Set.dark ? 2 : 0;   // the old "Dark pages (all sites)" switch carries over
}
static const char* omniDarkStyleName(int s) { return s == 1 ? "Natural" : s == 2 ? "Forced" : "Off"; }
static void omniDarkStyleSet(int s)
{
    omniDarkStyleCache = std::clamp(s, 0, 2);
    omniIoQueue(omniData("dark-style.txt"), std::to_string(omniDarkStyleCache) + "\\n", false);
    omniF3Load(); omniF3Set.dark = omniDarkStyleCache == 2; omniF3Save();
    omniDkChanged();
    notice(std::string("Dark mode: ") + omniDarkStyleName(omniDarkStyleCache)
        + (omniDarkStyleCache == 1 ? " (sites with a dark theme use it)" : omniDarkStyleCache == 2 ? " (every page dark)" : ""));
}
static void omniDarkStyleStep(int dir) { omniDarkStyleSet((omniDarkStyle() + (dir < 0 ? 2 : 1)) % 3); }
// Is Omni's darkening filter allowed on this page? Forced mode, or a site set to "Always dark".
static bool omniDkForced(const std::string& url)
{
    if (omniTestMode() || !omniWebURL(url)) return false;
    const int s = omniDkSite(omniDkHost(url));
    return s == 1 || (s < 0 && omniDarkStyle() == 2);
}
static bool omniDkWant(const std::string& url)
{'''
DARK_EDITS = [
    (STYLE, STYLE_NEW),
    ('    return s < 0 ? omniF3Set.dark : s == 1;', '    return s < 0 ? omniDarkStyle() > 0 : s == 1; // OMNI_DARK_CHOICE_V1'),
    ('''    snprintf(head, sizeof(head), "(function(){var c={v:%d,g:%d,on:", ++omniDkVersion, omniF3Set.dark ? 1 : 0);''',
     '''    snprintf(head, sizeof(head), "(function(){var c={v:%d,g:%d,f:%d,on:", ++omniDkVersion, omniDarkStyle() > 0 ? 1 : 0, omniDarkStyle() == 2 ? 1 : 0); // OMNI_DARK_CHOICE_V1'''),
    ('    omniDkSetSite(host, now == omniF3Set.dark ? -1 : (now ? 1 : 0));',
     '    omniDkSetSite(host, now == (omniDarkStyle() == 2) ? -1 : (now ? 1 : 0)); // OMNI_DARK_CHOICE_V1: "on" for a site = forced there'),
    ('bool any = omniF3Set.dark;', 'bool any = omniDarkStyle() > 0; /* OMNI_DARK_CHOICE_V1 */'),
    ("function update(){",
     "function filt(){var e=D.documentElement,a=e&&e.getAttribute('data-omni-dark-force');if(a)return a==='1';var c=window.__omniDarkCfg;if(!c||c.f===undefined||c.f)return true;"
     "var h=(location.hostname||'').toLowerCase().replace(/^www\\./,'');return c.on.indexOf(h)>=0;}\nfunction update(){"),
    ("var on=w0&&!fs&&!vp&&e.getAttribute('data-omni-dark-addon')!=='on';",
     "var on=w0&&!fs&&!vp&&e.getAttribute('data-omni-dark-addon')!=='on'&&filt();"),
]


DARK_EDITS += [
    ("""        const std::string js = std::string("document.documentElement&&document.documentElement.setAttribute('data-omni-dark','") + (on ? "on" : "off") + "')";""",
     """        const std::string js = std::string("document.documentElement&&(document.documentElement.setAttribute('data-omni-dark','") + (on ? "on" : "off")
            + "'),document.documentElement.setAttribute('data-omni-dark-force','" + (omniDkForced(t->url) ? "1" : "0") + "'))"; // OMNI_DARK_CHOICE_V1"""),
    ("""    const bool now = !omniDkWant(t->url);
    omniF3Load();""",
     """    const bool now = !omniDkForced(t->url);   // OMNI_DARK_CHOICE_V1: the button means "force dark on this site"
    omniF3Load();"""),
]
# The per-site "Always dark" must stay forced in Natural mode: the default (g) now means "ask for dark", so a site
# that wants dark while the global mode is Natural is listed explicitly by omniDkToggleCurrent above.

# ---------------------------------------------------------------- dark mode: OmniFeatures3.h
F3_EDITS = [
    ('''    add(omniF3SetDark, "Dark pages (all sites)", omniF3Set.dark ? "On" : "Off", true);''',
     '''    add(omniF3SetDark, "Dark mode", omniDarkStyleName(omniDarkStyle()), true); // OMNI_DARK_CHOICE_V1: Off / Natural / Forced'''),
    ('''    case omniF3SetDark: if (!dir) return false; omniF3Set.dark = !omniF3Set.dark; omniF3Save(); omniDkChanged(); return true;''',
     '''    case omniF3SetDark: if (!dir) return false; omniDarkStyleStep(dir); return true; // OMNI_DARK_CHOICE_V1'''),
    (''': omniF3Set.dark ? "Default (dark)" : "Default (off)";''',
     ''': omniDarkStyle() == 2 ? "Default (forced)" : omniDarkStyle() == 1 ? "Default (natural)" : "Default (off)"; // OMNI_DARK_CHOICE_V1'''),
]

# ---------------------------------------------------------------- quick access row: OmniMqQuickAccess.h
QA_CATALOG = r'''// OMNI_QA_CUSTOM_V1: the row's buttons are the user's choice (up to 6, in order), /data/omni/quick-access.txt.
static void omniL2Copy();
static void omniL2Paste();
static bool omniDkForced(const std::string& url);   // OmniDarkPages.h (included later, from OmniFeatures3.h)
enum { omniQaUblock, omniQaDark, omniQaApps, omniQaAddons, omniQaMedia, omniQaCopy, omniQaPaste, omniQaQuick, omniQaBookmarks,
    omniQaTabs, omniQaHistory, omniQaTranslate, omniQaReader, omniQaFind, omniQaNewTab, omniQaReload, omniQaSettings, omniQaCount };
static const char* const omniQaKeys[omniQaCount] = { "ublock", "dark", "apps", "addons", "media", "copy", "paste", "quickbar",
    "bookmarks", "tabs", "history", "translate", "reader", "find", "newtab", "reload", "settings" };
static const char* const omniQaNames[omniQaCount] = { "uBlock", "Dark mode", "Apps", "Add-ons", "Media downloads", "Copy", "Paste",
    "Quick bar", "Bookmarks", "Tabs", "History", "Translate", "Reader view", "Find in page", "New tab", "Reload", "Settings" };
constexpr int omniQaMax = 6;
static std::vector<int> omniQaItems;
static bool omniQaLoaded = false;
static void omniQaDefaults() { omniQaItems = { omniQaUblock, omniQaDark, omniQaApps, omniQaAddons }; }
static void omniQaLoad()
{
    if (omniQaLoaded) return;
    omniQaLoaded = true;
    omniQaItems.clear();
    bool any = false;
    if (FILE* f = fopen(omniData("quick-access.txt").c_str(), "r")) {
        any = true;
        char line[64];
        while (fgets(line, sizeof(line), f) && int(omniQaItems.size()) < omniQaMax) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ')) s.pop_back();
            for (int i = 0; i < omniQaCount; ++i)
                if (s == omniQaKeys[i] && std::find(omniQaItems.begin(), omniQaItems.end(), i) == omniQaItems.end()) omniQaItems.push_back(i);
        }
        fclose(f);
    }
    if (!any) omniQaDefaults();
}
static void omniQaSave()
{
    std::string s;
    for (int i : omniQaItems) s += std::string(omniQaKeys[i]) + "\n";
    omniIoQueue(omniData("quick-access.txt"), std::move(s), false);
    omniShellDirty = true;
}
static int omniQaShown()
{
    omniQaLoad();
    const int fit = std::max(1, (width - 664) / 158);
    return std::min<int>(std::min<int>(int(omniQaItems.size()), omniQaMax), fit);
}
static int omniQaAt(int slot) { omniQaLoad(); return slot >= 0 && slot < int(omniQaItems.size()) ? omniQaItems[slot] : -1; }
static bool omniQaEnabled(int item)
{
    const bool web = active() && omniWebURL(active()->url);
    switch (item) {
    case omniQaDark: case omniQaCopy: case omniQaPaste: case omniQaTranslate: case omniQaReader: case omniQaFind: case omniQaBookmarks: return web;
    case omniQaReload: return active() != nullptr;
    default: return item >= 0;
    }
}
static std::string omniQaLabel(int item)
{
    const bool web = active() && omniWebURL(active()->url);
    if (item == omniQaUblock) return std::string("uBlock ") + (omniBlockerFailed() ? "Error" : omniBlockerEnabled() ? "On" : "Off");
    if (item == omniQaDark) return std::string("Dark ") + (!web ? "-" : omniDkForced(active()->url) ? "On" : omniDkWant(active()->url) ? "Auto" : "Off");
    if (item == omniQaMedia) return "Downloads";
    if (item == omniQaReader) return "Reader";
    if (item == omniQaFind) return "Find";
    return item >= 0 && item < omniQaCount ? omniQaNames[item] : "";
}
static void omniQaRun(int item)
{
    if (!omniQaEnabled(item)) return;
    Tab* t = active();
    omniMqFocus = -1;
    switch (item) {
    case omniQaUblock: if (omniBlockerSetEnabled(!omniBlockerEnabled()) && t) WKPageReload(t->page); break;
    case omniQaDark: omniF3QuickAction(303); break;   // the existing Dark page action (this site)
    case omniQaApps: omniHubAppsShow(); break;
    case omniQaAddons: omniAdQuickAction(381); break;
    case omniQaMedia: if (!omniGrabBegin(2)) omniMediaDownloadsOpen(false); break;
    case omniQaCopy: omniL2Copy(); break;
    case omniQaPaste: omniL2Paste(); break;
    case omniQaQuick: omniFxQuickMenuShow(); break;
    case omniQaBookmarks: omniFxBookmarksShow(0); break;
    case omniQaTabs: omniFxTabsShow(); break;
    case omniQaHistory: omniHistoryShow(); break;
    case omniQaTranslate: omniTranslateToggle(); break;
    case omniQaReader: omniReaderStart(); break;
    case omniQaFind: omniFindStart(); break;
    case omniQaNewTab: if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); } break;
    case omniQaReload: if (t) WKPageReload(t->page); break;
    case omniQaSettings: omniFxSettingsShow(); break;
    }
}
// The editor: Browser settings > Quick access buttons... (Cross adds or removes; the order is the order you add them).
static void omniQaEditorBuild(OmniFxPanel& p)
{
    omniQaLoad();
    p.subtitle = "Up to " + std::to_string(omniQaMax) + " buttons, in the order you add them";
    for (int i = 0; i < omniQaCount; ++i) {
        OmniFxRow r; r.id = 700 + i; r.label = omniQaNames[i];
        const auto at = std::find(omniQaItems.begin(), omniQaItems.end(), i);
        r.value = at == omniQaItems.end() ? std::string("Off") : "Button " + std::to_string(int(at - omniQaItems.begin()) + 1);
        p.rows.push_back(r);
    }
    OmniFxRow reset; reset.id = 799; reset.label = "Back to the default buttons"; p.rows.push_back(reset);
}
static bool omniQaEditorInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniQaLoad();
    if (r.id == 799) { omniQaDefaults(); omniQaSave(); notice("Quick access: default buttons"); return true; }
    const int item = r.id - 700;
    if (item < 0 || item >= omniQaCount) return false;
    const auto at = std::find(omniQaItems.begin(), omniQaItems.end(), item);
    if (at != omniQaItems.end()) omniQaItems.erase(at);
    else if (int(omniQaItems.size()) >= omniQaMax) { notice("Quick access is full: remove a button first"); return true; }
    else omniQaItems.push_back(item);
    omniQaSave();
    return true;
}
static void omniQaEditorShow()
{
    OmniFxPanel p;
    p.title = "Quick access buttons"; p.w = 760; p.rowH = 48; p.maxVisible = 10;
    p.build = omniQaEditorBuild; p.input = omniQaEditorInput;
    p.faces = { { 0, "Add / remove" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static int omniMqHit(int x, int y)'''

QA_EDITS = [
    ('static int omniMqHit(int x, int y)', QA_CATALOG),
    ('    return column < 4 && (x - 640) % 158 < 150 ? column : -1;',
     '    return column < omniQaShown() && (x - 640) % 158 < 150 ? column : -1; // OMNI_QA_CUSTOM_V1'),
    ('    return item != 1 || (active() && omniWebURL(active()->url));',
     '    return omniQaEnabled(omniQaAt(item)); // OMNI_QA_CUSTOM_V1'),
    ('''    if (item == 0) { if (omniBlockerSetEnabled(!omniBlockerEnabled()) && active()) WKPageReload(active()->page); }
    else if (item == 1) omniF3QuickAction(303); // existing Dark page action
    else if (item == 2) { omniMqFocus = -1; omniHubAppsShow(); }
    else if (item == 3) { omniMqFocus = -1; omniAdQuickAction(381); }''',
     '''    omniQaRun(omniQaAt(item)); // OMNI_QA_CUSTOM_V1'''),
    ('    } else if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT) omniMqFocus = (omniMqFocus + 3) % 4;',
     '    } else if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT) omniMqFocus = (omniMqFocus + omniQaShown() - 1) % omniQaShown(); // OMNI_QA_CUSTOM_V1'),
    ('    else if (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) omniMqFocus = (omniMqFocus + 1) % 4;',
     '    else if (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) omniMqFocus = (omniMqFocus + 1) % omniQaShown();'),
    ('        omniLabel(labels[i], x + 75, 138, omniSmall, enabled ? t.ink : t.inkFaint, 1, 138);',
     '        omniLabel(omniQaLabel(omniQaAt(i)), x + 75, 138, omniSmall, enabled ? t.ink : t.inkFaint, 1, 138);'),
]
QA_REGEX = [
    (r'    const bool web = active\(\) && omniWebURL\(active\(\)->url\);\n    const std::string labels\[\] = \{.*?\};\n    for \(int i = 0; i < 4; \+\+i\) \{',
     '    for (int i = 0, n = omniQaShown(); i < n; ++i) { // OMNI_QA_CUSTOM_V1'),
]

# ---------------------------------------------------------------- Browser settings rows (after the L2 patch)
SET_EDITS = [
    ('omniFxSetQuick /* OMNI_L2_CHORDS_V1 */ };', 'omniFxSetQuick /* OMNI_L2_CHORDS_V1 */, omniFxSetQa /* OMNI_QA_CUSTOM_V1 */ };\nstatic void omniQaEditorShow();'),
    ('''    add(omniFxSetQuick, "Quick bar and apps...", "L2 + Cross", false); // OMNI_L2_CHORDS_V1''',
     '''    add(omniFxSetQuick, "Quick bar and apps...", "L2 + Cross", false); // OMNI_L2_CHORDS_V1
    add(omniFxSetQa, "Quick access buttons...", "", false); // OMNI_QA_CUSTOM_V1'''),
    ('''    case omniFxSetQuick: if (!a) return false; omniFxCloseAll(); omniFxQuickMenuShow(); return true; // OMNI_L2_CHORDS_V1''',
     '''    case omniFxSetQuick: if (!a) return false; omniFxCloseAll(); omniFxQuickMenuShow(); return true; // OMNI_L2_CHORDS_V1
    case omniFxSetQa: if (!a) return false; omniQaEditorShow(); return true; // OMNI_QA_CUSTOM_V1'''),
]

# ---------------------------------------------------------------- Create opens Browser settings (OmniBrowser.cpp)
CREATE = '''    if (button == SDL_CONTROLLER_BUTTON_BACK) { settingsOpen = !settingsOpen; fieldClickDeadline = 0; omniSettingsRow = 0; return; } // OMNI_STYLE_V1: row reset'''
CREATE_NEW = '''    // OMNI_SETTINGS_CREATE_V1: Create opens Browser settings (everything, incl. "Controller, theme and display...").
    if (button == SDL_CONTROLLER_BUTTON_BACK) { if (settingsOpen) { settingsOpen = false; return; } omniFxSettingsShow(); return; }'''
CREATE_DECL = '''static void omniKbPageReset(); // OMNI_SHORTCUTS_V1'''
CREATE_DECL_NEW = '''static void omniFxSettingsShow(); // OMNI_SETTINGS_CREATE_V1
''' + CREATE_DECL

print('OmniDarkPages.h', patch('OmniDarkPages.h', DARK_EDITS))
print('OmniFeatures3.h', patch('OmniFeatures3.h', F3_EDITS))
print('OmniMqQuickAccess.h', patch('OmniMqQuickAccess.h', QA_EDITS, QA_REGEX))
print('OmniBrowserSettings.h', patch('OmniBrowserSettings.h', SET_EDITS))
print('OmniBrowser.cpp', patch('OmniBrowser.cpp', [(CREATE_DECL, CREATE_DECL_NEW), (CREATE, CREATE_NEW)]))
