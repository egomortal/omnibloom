#!/usr/bin/env python3
"""OMNI_CLIP_HISTORY_V1 (2026-11-16): clipboard history, the last 10 things copied, memory only.

What existed
  Omni's own clipboard omniKbClipboard (OmniBrowser.cpp, OMNI_KEYBOARD_V2): one std::string in memory, never written
  to disk, gone when Omni exits (PS5 homebrew has no system clipboard). Every write to it (grep of the patched tree,
  recipe order up to apply_web_apps.py):
    OmniBrowser.cpp        omniKbCopy, webpage field: keyboard Copy / Cut (and Ctrl+C / Ctrl+X), 8 KB
                           omniKbCopy, address / dialog field: keyboard Copy / Cut
                           omniQanUse: a quick answer ("= 87") picked in the address suggestions (OMNI_QUICK_ANSWERS_V1)
                           omniL2Copied: L2 + Square (selection, link, image or page address), 8 KB (OMNI_L2_CHORDS_V1)
    OmniContextMenu.h      omniFxCopy: page menu Copy link address / Copy image address / Copy page address, and the
                           quick menu's Copy address
    OmniTextSelectShell.h  Select text > Copy, 4 KB (OMNI_TEXT_SELECT_V1)
  Readers: the keyboard's Paste key (edit-tools row, Touchpad; Ctrl+V) and L2 + Triangle. No history.

What the user sees now
  - Keyboard: the edit-tools row (Touchpad) gets a "Clips" key right after Paste (All, Cut, Home, End are 0.75 wide so
    the row stays 10 units). Cross on it opens a list over the keys: "Clipboard", the last 10 copied items newest first,
    one line each (first 40 characters, line breaks / tabs shown as spaces, "..." when longer), the one in the clipboard
    marked "In clipboard". D-pad up / down picks, Cross pastes it (it becomes the clipboard and moves to the top),
    Square removes it from the list (and empties the clipboard if it held it), Circle closes the list (not the
    keyboard). A click on a row pastes it, a click elsewhere closes the list. Empty: notice "Nothing copied yet".
  - Quick menu (Options): a top-level row "Clipboard (3)" while anything is listed. Cross: a panel with the items
    (same labels, "In clipboard" / "Private" on the right) and "Clear clipboard history" last. Cross on an item makes it
    the clipboard ("Copied: the keyboard's Paste key or L2 + Triangle pastes it"), Square removes it, Circle goes back.
    Clear clipboard history empties the list and the clipboard.
  - Items: at most 4 KB each (cut at a UTF-8 boundary; the clipboard itself keeps what it held before, up to 8 KB),
    the same text copied again moves to the top (no duplicates), the 11th pushes out the oldest.

Private tabs (the safer of the two rules, and both apply)
  An item copied while a private tab is active is listed only while the active tab is private (never in a normal tab's
  list, count or quick-menu row), and every such item is dropped when the last private tab closes (omniClhTick, every
  pass from omniF3Tick: a scan of the tab list only while a private item / private clipboard exists); if the clipboard
  itself was last filled from a private tab it is emptied too. The same text copied again in a normal tab becomes a
  normal item; picking a normal item from the list in a private tab keeps it normal (nothing in normal tabs is lost).
  Copy / paste themselves are unchanged (a private copy still pastes into a normal tab while a private tab is open).
Memory only: nothing is written anywhere; 10 x 4 KB at most; gone when Omni exits.

Pure part: engine/entry/OmniClipHistory.h (from tools/OmniClipHistory.h: the ring of 10, dedupe-move-to-front, private
rule, 4 KB cap, UTF-8-safe 40-character labels, ids). Tests: tools/test_clip_history.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_clip_history.cpp -o t && ./t).
Shell part: engine/entry/OmniClipHistoryShell.h (written by this script), namespace alias OCLH, names omniClh*.
Ids: panel kind 7560, keyboard key action 7561, quick-menu row 8495 (checked unused in every apply_*.py and the tree).

Anchors (each once; whole lines; new lines inserted before / after them or the block replaced; CRLF kept):
  OmniBrowser.cpp   the OmniTextSelect.h include line (pure include after it); 'static std::string omniKbClipboard;'
                    (declarations after); the 4 edit-tools act() lines (replaced: Clips key, narrower keys); the
                    'case omniKbPasteKey: {' line (Clips case before); the 4 clipboard writes above (omniClhNote() after
                    each; the two '= text.substr(0, 8192);' writes anchored together with their notice line);
                    the omniKbl hints line (list hints after); omniKblClick / omniKblButton call lines (list before);
                    the omniKblDraw() call line (list drawn after)
  OmniContextMenu.h 'omniKbClipboard = text;' (omniFxCopy; note after)
  OmniTextSelectShell.h 'omniKbClipboard = OTSL::clip(text);' (note after)
  OmniFeatures3.h   the OmniTextSelectShell.h include line (shell include after); the omniDlpTick line (tick after)
  OmniQuickMenu.h   the omniDlpQuickInput declaration, the omniDlpQuickRow call, the omniDlpQuickInput call line
Controls guide (OmniControlsHelp.h) is not edited here; rows to add are in the report.
Apply AFTER apply_text_select.py, apply_quick_answers.py, apply_dl_progress.py, apply_kb_layouts.py, apply_l2_chords.py.
usage: apply_clip_history.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_CLIP_HISTORY_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7560', '7561', '8495')
NAMES = ('OCLH', 'omniClh', 'OmniClipHistory')

SHELL = r'''// OMNI_CLIP_HISTORY_V1: clipboard history (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniTextSelectShell.h). Pure part: OmniClipHistory.h; reasons in tools/apply_clip_history.py.
// The last 10 things copied to omniKbClipboard, memory only (never written anywhere, gone when Omni exits). Every
// write to omniKbClipboard calls omniClhNote() right after it. Private-tab items are listed only in private tabs and
// dropped (with a private clipboard) when the last private tab closes. Main thread only.
#pragma once

namespace OCLH = OmniClipHistory;

static OCLH::History omniClh;
static bool omniClhPrivateTab() { Tab* t = active(); return t && t->omniPrivate; }
static bool omniClhAnyPrivateTab()
{
    for (auto& t : tabs) if (t && t->omniPrivate) return true;
    return false;
}
// Right after every write to omniKbClipboard (keyboard Copy / Cut, L2 + Square, the page menu's Copy ... address,
// Select text's Copy, a quick answer).
static void omniClhNote()
{
    omniClh.add(omniKbClipboard, omniClhPrivateTab());
    omniShellDirty = true;
}
// Every pass (omniF3Tick): the last private tab closed -> its items go, and a clipboard filled in a private tab.
static void omniClhTick()
{
    if (!omniClh.hasPrivate() || omniClhAnyPrivateTab()) return;
    if (omniClh.purgePrivate()) omniKbClipboard.clear();
    omniShellDirty = true;
}
static std::string omniClhLabel(const OCLH::Item& it)
{
    std::string s = OCLH::label(it.text);
    return s.empty() ? std::string("(spaces only)") : s;
}
// A listed item becomes the clipboard (and moves to the top). false: it is gone.
static bool omniClhUse(uint32_t id)
{
    std::string text;
    if (!omniClh.touch(id, &text)) return false;
    omniKbClipboard = text;
    omniShellDirty = true;
    return true;
}
static void omniClhRemove(uint32_t id)
{
    std::string text;
    if (!omniClh.remove(id, &text)) return;
    if (!omniKbClipboard.empty() && OCLH::clip(omniKbClipboard) == text) omniKbClipboard.clear();
    notice("Removed from the clipboard history");
    omniShellDirty = true;
}

// --- the keyboard's list (the "Clips" key in the edit-tools row) -----------------------------------------------------
struct OmniClhKbState { bool open = false; int session = -1; int sel = 0; };
static OmniClhKbState omniClhKb;
static bool omniClhKbShown() { return omniClhKb.open && editing && omniClhKb.session == omniKb.session; }
static void omniClhKbClose() { if (omniClhKb.open) omniShellDirty = true; omniClhKb.open = false; }
static void omniClhKbOpen()
{
    omniClhTick();
    if (!omniClh.count(omniClhPrivateTab())) { notice("Nothing copied yet: the last 10 copies are listed here until Omni closes"); return; }
    omniClhKb.open = true;
    omniClhKb.session = omniKb.session;
    omniClhKb.sel = 0;
    omniChromeWake();
    omniShellDirty = true;
}
constexpr int omniClhRowH = 34, omniClhHead = 50;
static void omniClhKbGeometry(int n, int& x, int& y, int& w, int& h)
{
    w = std::min(660, keyboardWidth);
    x = keyboardX + (keyboardWidth - w) / 2;
    h = omniClhHead + n * omniClhRowH + 10;
    y = actionY + keyHeight - h;                    // over the keys, its bottom on the action row's
}
static void omniClhKbPaste(uint32_t id)
{
    omniClhKbClose();
    if (omniClhUse(id)) omniKbAction(omniKbPasteKey);
}
static bool omniClhKbButton(int b)
{
    if (!omniClhKbShown()) { omniClhKb.open = false; return false; }
    const bool priv = omniClhPrivateTab();
    const auto items = omniClh.visible(priv);
    const int n = int(items.size());
    if (!n) { omniClhKbClose(); return false; }
    int& sel = omniClhKb.sel;
    sel = std::clamp(sel, 0, n - 1);
    omniShellDirty = true;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: sel = (sel + n - 1) % n; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: sel = (sel + 1) % n; return true;
    case SDL_CONTROLLER_BUTTON_A: omniClhKbPaste(items[size_t(sel)].id); return true;
    case SDL_CONTROLLER_BUTTON_X:
        omniClhRemove(items[size_t(sel)].id);
        if (!omniClh.count(priv)) omniClhKbClose();
        return true;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniClhKbClose(); return true;
    default: return true;                           // the other buttons wait until the list is closed
    }
}
static bool omniClhKbClick(int px, int py)
{
    if (!omniClhKbShown()) return false;
    const auto items = omniClh.visible(omniClhPrivateTab());
    int x, y, w, h;
    omniClhKbGeometry(int(items.size()), x, y, w, h);
    const int k = py >= y + omniClhHead ? (py - y - omniClhHead) / omniClhRowH : -1;
    if (px >= x && px < x + w && k >= 0 && k < int(items.size())) { omniClhKbPaste(items[size_t(k)].id); return true; }
    omniClhKbClose();                               // a click elsewhere closes the list
    return true;
}
static void omniClhKbDraw()
{
    if (!omniClhKbShown()) return;
    const bool priv = omniClhPrivateTab();
    const auto items = omniClh.visible(priv);
    const int n = int(items.size());
    if (!n) return;
    const int sel = std::clamp(omniClhKb.sel, 0, n - 1);
    const OmniTheme& T = omniTheme();
    int x, y, w, h;
    omniClhKbGeometry(n, x, y, w, h);
    omniShadow(x, y, w, h, omniRadius + 2, 14, 150, 4);
    fillRounded(x, y, w, h, omniRadius + 2, T.panel);
    const int tw = omniLabel("Clipboard", float(x + 22), float(y + 26), omniBodyBold, T.ink, 0, w / 2);
    omniLabel(priv ? "Last 10 copied (private ones until the last private tab closes)" : "Last 10 copied, kept until Omni closes",
        float(x + w - 22), float(y + 26), omniSmall, T.inkDim, 2, w - tw - 70);
    for (int i = 0; i < n; ++i) {
        const OCLH::Item& it = items[size_t(i)];
        const int ry = y + omniClhHead + i * omniClhRowH;
        const bool on = i == sel;
        if (on) fillRounded(x + 10, ry + 1, w - 20, omniClhRowH - 2, omniRadius, T.accent);
        const float cy = ry + omniClhRowH / 2.f;
        const std::string value = OCLH::rowValue(OCLH::isCurrent(omniKbClipboard, it), it.priv);
        const int vw = value.empty() ? 0 : omniLabel(value, float(x + w - 24), cy, omniSmall, on ? T.accentInk : T.inkDim, 2, 200) + 16;
        omniLabel(omniClhLabel(it), float(x + 24), cy, omniSmall, on ? T.accentInk : T.ink, 0, w - 48 - vw);
    }
}

// --- the quick menu: "Clipboard (n)" and its panel -------------------------------------------------------------------
static void omniClhPanelBuild(OmniFxPanel& p)
{
    const bool priv = omniClhPrivateTab();
    for (const auto& it : omniClh.visible(priv)) {
        OmniFxRow r; r.id = int(it.id); r.label = omniClhLabel(it); r.value = OCLH::rowValue(OCLH::isCurrent(omniKbClipboard, it), it.priv);
        p.rows.push_back(r);
    }
    if (p.rows.empty()) return;
    OmniFxRow c; c.id = OCLH::kClearRowId; c.label = "Clear clipboard history"; c.danger = true;
    p.rows.push_back(c);
}
static bool omniClhPanelInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id == OCLH::kClearRowId) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        omniClh.clear();
        omniKbClipboard.clear();
        omniFxPop();
        notice("Clipboard history cleared");
        return true;
    }
    if (r.id < 1) return false;
    if (b == SDL_CONTROLLER_BUTTON_A) {
        if (omniClhUse(uint32_t(r.id))) { omniFxCloseAll(); notice("Copied: the keyboard's Paste key or L2 + Triangle pastes it"); }
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_X) {
        omniClhRemove(uint32_t(r.id));
        if (!omniClh.count(omniClhPrivateTab())) omniFxPop();
        return true;
    }
    return false;
}
static void omniClhQuickRow(OmniFxPanel& p)
{
    const size_t n = omniClh.count(omniClhPrivateTab());
    if (!n) return;
    OmniFxRow r; r.id = OCLH::kQuickRowId; r.label = OCLH::quickLabel(n);
    p.rows.push_back(r);
}
static bool omniClhQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != OCLH::kQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    OmniFxPanel p;
    p.kind = OCLH::kPanelKind;
    p.title = "Clipboard";
    p.subtitle = "Last 10 copied, memory only (gone when Omni closes)";
    p.w = 820; p.rowH = 46; p.maxVisible = 11;
    p.build = omniClhPanelBuild; p.input = omniClhPanelInput;
    p.faces = { { 0, "Copy" }, { 2, "Remove" }, { 1, "Back" } };
    omniFxPush(std::move(p));
    return true;
}
'''

WRITE_NOTE = '    omniClhNote(); // ' + MARK + ': clipboard history\n'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTextSelect.h" // OMNI_TEXT_SELECT_V1: Select text (pure: page script, clipboard cap, actions)\n',
         '#include "OmniTextSelect.h" // OMNI_TEXT_SELECT_V1: Select text (pure: page script, clipboard cap, actions)\n'
         '#include "OmniClipHistory.h" // ' + MARK + ': clipboard history (pure: ring of 10, private rule, labels)\n'),
        ('static std::string omniKbClipboard;\n',
         'static std::string omniKbClipboard;\n'
         '// ' + MARK + ' (OmniClipHistoryShell.h): every write to omniKbClipboard calls omniClhNote() right after it.\n'
         'static void omniClhNote();\n'
         'static void omniClhTick();\n'
         'static void omniClhKbOpen();\n'
         'static bool omniClhKbShown();\n'
         'static bool omniClhKbButton(int b);\n'
         'static bool omniClhKbClick(int x, int y);\n'
         'static void omniClhKbDraw();\n'),
        # keyboard Copy / Cut in a webpage field (async: the page answers with the text)
        ('            omniKbClipboard = text.substr(0, 8192);\n'
         '            notice(context ? "Cut" : "Copied");\n',
         '            omniKbClipboard = text.substr(0, 8192);\n'
         '            omniClhNote(); // ' + MARK + '\n'
         '            notice(context ? "Cut" : "Copied");\n'),
        # keyboard Copy / Cut in the address / a dialog field
        ('    omniKbClipboard = t->substr(a, b - a);\n',
         '    omniKbClipboard = t->substr(a, b - a);\n' + WRITE_NOTE),
        # the edit-tools row: a "Clips" key after Paste; All, Cut, Home, End narrower (the row stays 10 units)
        ('        act(quick, "Select", omniKbSelectKey, 1); act(quick, "All", omniKbAllKey, 1); act(quick, "Cut", omniKbCutKey, 1);\n'
         '        act(quick, "Copy", omniKbCopyKey, 1); act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Undo", omniKbUndoKey, 1);\n'
         '        act(quick, "Home", omniKbHomeKey, 1); act(quick, "End", omniKbEndKey, 1); act(quick, "Del word", omniKbDelWordKey, 1);\n'
         '        act(quick, "Clear", omniKbClearKey, 1);\n',
         '        // ' + MARK + ': "Clips" (the clipboard history) after Paste; All, Cut, Home, End 0.75 wide, the row stays 10 units\n'
         '        act(quick, "Select", omniKbSelectKey, 1); act(quick, "All", omniKbAllKey, 0.75f); act(quick, "Cut", omniKbCutKey, 0.75f);\n'
         '        act(quick, "Copy", omniKbCopyKey, 1); act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Clips", OmniClipHistory::kKbKey, 1);\n'
         '        act(quick, "Undo", omniKbUndoKey, 1);\n'
         '        act(quick, "Home", omniKbHomeKey, 0.75f); act(quick, "End", omniKbEndKey, 0.75f); act(quick, "Del word", omniKbDelWordKey, 1);\n'
         '        act(quick, "Clear", omniKbClearKey, 1);\n'),
        ('    case omniKbPasteKey: {\n',
         '    case OmniClipHistory::kKbKey: omniKb.select = false; omniClhKbOpen(); return; // ' + MARK + ': the clipboard list\n'
         '    case omniKbPasteKey: {\n'),
        ('    if (omniKblClick(x, y)) return; // OMNI_KB_LAYOUTS_V1: the accent popup\n',
         '    if (omniClhKbClick(x, y)) return; // ' + MARK + ': the clipboard list (a row pastes, elsewhere closes it)\n'
         '    if (omniKblClick(x, y)) return; // OMNI_KB_LAYOUTS_V1: the accent popup\n'),
        ('    if (omniKbl.open) { face(0, "Insert"); face(1, "Cancel"); pill("D-pad"); label("Choose accent"); return; } // OMNI_KB_LAYOUTS_V1\n',
         '    if (omniKbl.open) { face(0, "Insert"); face(1, "Cancel"); pill("D-pad"); label("Choose accent"); return; } // OMNI_KB_LAYOUTS_V1\n'
         '    if (omniClhKbShown()) { face(0, "Paste"); face(2, "Remove"); face(1, "Close"); pill("D-pad"); label("Choose"); return; } // ' + MARK + '\n'),
        ('    omniKblDraw(); // OMNI_KB_LAYOUTS_V1: the accent popup over the keys\n',
         '    omniKblDraw(); // OMNI_KB_LAYOUTS_V1: the accent popup over the keys\n'
         '    omniClhKbDraw(); // ' + MARK + ': the clipboard list over the keys\n'),
        # a quick answer copied (OMNI_QUICK_ANSWERS_V1)
        ('    omniKbClipboard = value;\n',
         '    omniKbClipboard = value;\n' + WRITE_NOTE),
        # L2 + Square (OMNI_L2_CHORDS_V1)
        ('    omniKbClipboard = text.substr(0, 8192);\n'
         '    notice(std::string(what) + " copied. L2 + Triangle pastes it");\n',
         '    omniKbClipboard = text.substr(0, 8192);\n' + WRITE_NOTE +
         '    notice(std::string(what) + " copied. L2 + Triangle pastes it");\n'),
        ('    if (editing && omniKblButton(button)) return; // OMNI_KB_LAYOUTS_V1: the accent popup (Circle cancels it, not the keyboard)\n',
         '    if (editing && omniClhKbButton(button)) return; // ' + MARK + ': the clipboard list (Circle closes it, not the keyboard)\n'
         '    if (editing && omniKblButton(button)) return; // OMNI_KB_LAYOUTS_V1: the accent popup (Circle cancels it, not the keyboard)\n'),
    ],
    'OmniContextMenu.h': [
        ('    omniKbClipboard = text;\n',
         '    omniKbClipboard = text;\n' + WRITE_NOTE),
    ],
    'OmniTextSelectShell.h': [
        ('        omniKbClipboard = OTSL::clip(text);   // memory only: never written to disk, gone when Omni exits\n',
         '        omniKbClipboard = OTSL::clip(text);   // memory only: never written to disk, gone when Omni exits\n'
         '        omniClhNote(); // ' + MARK + ': clipboard history\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTextSelectShell.h" // OMNI_TEXT_SELECT_V1: Select text (page menu row, selecting layer, actions)\n',
         '#include "OmniTextSelectShell.h" // OMNI_TEXT_SELECT_V1: Select text (page menu row, selecting layer, actions)\n'
         '#include "OmniClipHistoryShell.h" // ' + MARK + ': clipboard history (keyboard list, quick menu row)\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniClhTick();      // ' + MARK + ': private items go when the last private tab closes\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniDlpQuickInput(const OmniFxRow& r, int b);\n',
         'static bool omniDlpQuickInput(const OmniFxRow& r, int b);\n'
         'static void omniClhQuickRow(OmniFxPanel& p); // ' + MARK + ' (OmniClipHistoryShell.h)\n'
         'static bool omniClhQuickInput(const OmniFxRow& r, int b);\n'),
        ('        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n',
         '        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n'
         '        omniClhQuickRow(p); // ' + MARK + ': Clipboard (n), while anything is listed\n'),
        ('    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n',
         '    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n'
         '    if (omniClhQuickInput(r, b)) return true; // ' + MARK + ' (before the >= 900 rows)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_TEXT_SELECT_V1', 'OMNI_QUICK_ANSWERS_V1', 'OMNI_L2_CHORDS_V1', 'OMNI_KB_LAYOUTS_V1'),
         'OmniFeatures3.h': ('OMNI_TEXT_SELECT_V1', 'OMNI_DL_PROGRESS_V1'),
         'OmniQuickMenu.h': ('OMNI_DL_PROGRESS_V1',)}


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


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniClipHistory.h', 'OmniClipHistoryShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniClipHistory.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniClipHistory.h: %s missing' % MARK)
    msgs = [write_new('OmniClipHistory.h', pure, 'OmniTextSelect.h'),
            write_new('OmniClipHistoryShell.h', SHELL, 'OmniTextSelectShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
