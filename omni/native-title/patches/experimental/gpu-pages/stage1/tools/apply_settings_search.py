#!/usr/bin/env python3
"""OMNI_SETTINGS_SEARCH_V1 (2026-11-16): a search box at the top of Browser settings.

What the user sees
  Browser settings starts with a row "Search settings..." (value "Type a few letters"). Cross opens the on-screen
  keyboard (omniKbEdit, so the word chips work as everywhere else). After Go, only the matching rows stay, best
  first, each with its section as a dim prefix ("Privacy  HTTPS-only mode   On"); the subtitle says
  "3 of 41 settings match "dark"", the search row shows the query and "3 matches. Square clears", the highlight
  lands on the best match. Every found row works exactly as unfiltered (Cross / D-pad / Triangle go to the same
  handler, by id), and a row stays in place while it is used even if its new value no longer matches ("on" ->
  "Off"). Square clears the query whenever the row under the highlight has no Square action of its own (Home page
  keeps "Square: current page"); the highlighted setting stays highlighted in the full list. "No settings match"
  (disabled) when nothing matches. A fresh Browser settings starts without a query.

Matching (pure, OmniSettingsSearch.h; case-insensitive, punctuation = space): label starts with the query, then the
query starts a word of the label, then every query word starts a word of label or value, then inside the label
(also with spaces removed: "dpad" -> "D-pad"), then the value, then a small synonym table ("dark" -> theme / night
light, "ads" -> uBlock / content blocker, "privacy" -> HTTPS-only / GPC / learn words / clear / passwords,
"video" -> quality / HDR / autoplay / speed, "keyboard" -> layout / word suggestions, "text size" -> interface
size / site zoom, ...), then the section name. Browser settings has no section headers, so a row's section comes
from its label by a keyword table (Keyboard, Privacy, Media, Display, Controls, Tabs, Network, Browsing, else
General): rows from other patches (night light, offline retry, interface size, keyboard layouts, clear range...)
are found and sectioned without a fixed list.

How Browser settings rows are built (OmniBrowserSettings.h): omniFxSettingsBuild(p) runs on every draw and after
every button (omniFxRebuild); its add(id, label, value, stepper) lambda and the omniXxSettingsRows(p) helpers of
other patches push OmniFxRow objects into p.rows (collected, not drawn); omniFxDrawPanel draws p.rows afterwards;
omniFxSettingsInput dispatches by r.id. So the filter is a post-pass: omniSsrFilter(p) at the end of the build
rewrites p.rows (search row first; with a query only the picked rows, original objects). p.input becomes
omniSsrPanelInput (the two search rows; everything else -> omniFxSettingsInput; unused Square -> clear).
OmniFxRow gets a `prefix` string, drawn dim before the label by the shared panel (empty for every other panel).

Files: engine/entry/OmniSettingsSearch.h (pure, from tools/OmniSettingsSearch.h; tested by
tools/test_settings_search.cpp), engine/entry/OmniSettingsSearchShell.h (from tools/OmniSettingsSearchShell.h).
Ids: OSSR::kSearchRowId -780, OSSR::kNoMatchRowId -781 (negative: no Browser settings range uses them).

Anchors (exactly once each; MARK makes each file idempotent; whole lines only):
  OmniBrowser.cpp       the OmniHttpsOnly.h include line (apply_https_only.py's): + pure include.
  OmniFeaturesPanel.h   OmniFxRow's "bool enabled = true, danger = false, stepper = false;" line: + prefix;
                        the omniTgRowMark line of omniFxDrawPanel (apply_tab_groups.py's): + the dim prefix.
  OmniBrowserSettings.h "static void omniFxSettingsBuild(OmniFxPanel& p)": shell include before it;
                        "    p.rows.back().enabled = true;" (the build's last line): + omniSsrFilter(p);
                        "    p.build = omniFxSettingsBuild; p.input = omniFxSettingsInput;": + the input / reset.
Apply AFTER apply_https_only.py and apply_tab_groups.py.
usage: apply_settings_search.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_SETTINGS_SEARCH_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n',
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'
         '#include "OmniSettingsSearch.h" // OMNI_SETTINGS_SEARCH_V1: Browser settings search (pure)\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('    bool enabled = true, danger = false, stepper = false;\n',
         '    bool enabled = true, danger = false, stepper = false;\n'
         '    std::string prefix;            // OMNI_SETTINGS_SEARCH_V1: dim text before the label (a found setting\'s section)\n'),
        ('            if (omniTgRowMark(p, r, g.x, ry, p.rowH)) lx = g.x + 66; // OMNI_TAB_GROUPS_V1: group colour\n',
         '            if (omniTgRowMark(p, r, g.x, ry, p.rowH)) lx = g.x + 66; // OMNI_TAB_GROUPS_V1: group colour\n'
         '            if (!r.prefix.empty()) lx += omniLabel(r.prefix, lx, cy, omniSmall, side, 0, (g.x + g.w - 32 - lx) / 4) + 12; // OMNI_SETTINGS_SEARCH_V1: the section, dim\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static void omniFxSettingsBuild(OmniFxPanel& p)\n',
         '#include "OmniSettingsSearchShell.h" // OMNI_SETTINGS_SEARCH_V1: Search settings (omniSsrFilter, omniSsrPanelInput)\n'
         'static void omniFxSettingsBuild(OmniFxPanel& p)\n'),
        ('    p.rows.back().enabled = true;\n',
         '    p.rows.back().enabled = true;\n'
         '    omniSsrFilter(p); // OMNI_SETTINGS_SEARCH_V1: "Search settings..." first; with a query only the matching rows (keep last)\n'),
        ('    p.build = omniFxSettingsBuild; p.input = omniFxSettingsInput;\n',
         '    p.build = omniFxSettingsBuild; p.input = omniFxSettingsInput;\n'
         '    p.input = omniSsrPanelInput; omniSsrOpened(); // OMNI_SETTINGS_SEARCH_V1: search rows + Square clears, the rest to omniFxSettingsInput\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': 'OMNI_HTTPS_ONLY_V1', 'OmniFeaturesPanel.h': 'OMNI_TAB_GROUPS_V1'}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, src, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    text = (HERE / src).read_text(encoding='utf-8')
    if MARK not in text:
        sys.exit('%s: %s missing' % (src, MARK))
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    for name, need in NEEDS.items():
        if need not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply its patch first' % (name, need))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSettingsSearch.h', 'OmniSettingsSearch.h', 'OmniHttpsOnly.h'),
            write_new('OmniSettingsSearchShell.h', 'OmniSettingsSearchShell.h', 'OmniBrowserSettings.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
