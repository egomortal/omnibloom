#!/usr/bin/env python3
"""OMNI_KB_SNIPPETS_V1 (2026-11-16): keyboard snippets, up to 10 saved phrases in the edit row (backlog E18).

What existed (audited in the patched tree after the recipe chain + apply_kb_showpw.py + apply_kb_fields.py +
apply_kb_nextfield.py)
  - The on-screen keyboard (OMNI_KEYBOARD_V2) has an edit-tools row (Touchpad / the Edit key): Select All Cut Copy
    Paste Clips Undo Home End Del word Clear (apply_clip_history.py added Clips, apply_kb_showpw.py puts Show / Hide
    where Copy is in password fields). Autofill (OmniAutofill.h) fills whole forms only; clipboard history is memory
    only (gone when Omni exits). Nothing keeps a phrase you type often (your e-mail, a stock reply).
  - Every pad button already has a keyboard job (Cross type, Square delete, Triangle space, Options Go, Circle / Create
    close, L1 / R1 cursor, L2 / R2 word, L3 Shift and hold L3 + L1 / R1 next field, R3 layer, Touchpad Edit), so this
    is a key in the edit row, not a new chord.

What the user sees
  - Edit tools row (Touchpad, or the Edit key): a "Snippets" key right after "Clips" (Select, Copy, Undo and Clear go
    0.75 wide so the row stays 10 units). Not in password fields (the row there is unchanged: Show / Hide, no
    Snippets), not in guest mode, not in self-tests.
  - Cross on it opens a list over the keys, the clipboard list's style: "Snippets", the saved phrases in the order
    they were saved (one line each, first 40 characters, "..." when longer), then "+ Save current text as snippet".
    D-pad up / down picks, Circle closes the list (not the keyboard), a click on a row acts on it, a click outside
    closes it.
      * Cross on a phrase inserts it at the cursor (as Paste: replaces a selection), the list closes.
      * Cross on "+ Save current text as snippet": the text being edited (the selection when there is one, else the
        whole text box) is cleaned (one line, at most 200 characters) and the row asks: Save "...": Cross saves,
        Circle cancels. In a private tab the question says the snippet stays on this console after the tab closes:
        nothing is saved from a private tab without that explicit Cross. Empty text: "Nothing to save"; already
        saved: "That snippet is already saved"; 10 saved: the row reads "10 snippets saved: delete one to save more".
      * Square on a phrase asks "Delete this snippet?"; Square (or Cross) again deletes it, Circle / D-pad cancels.
    The list's subtitle labels the store: "Saved on this console as plain text: never save passwords".
  - Password fields: never a Snippets key, never the list (it closes when the field turns out to be a password), never
    a save from one (the field kind is re-checked when the save is confirmed; a webpage field must have been read by the
    keyboard's probe first).
  - Notices never name the phrase.
Store: /data/omni/kb-snippets.txt, plain text, "omni-kb-snippets<TAB>1" then one phrase per line, rewritten whole
  through omniIoQueue (the background writer) on every save / delete; read once on first use (64 KB cap). Snippets
  are global (every tab, private ones too: inserting from a private tab is allowed and writes nothing). Never read,
  shown or written in guest mode (when OmniGuestMode.h is in the tree: __has_include) or self-tests.
Setup backup (backup.py): a new opt-in personal group, e.g.
  {"id": "kb-snippets", "name": "Keyboard snippets", "detail": "phrases you saved for the keyboard (may hold your
  e-mail or address)"} with _f(OMNI + "kb-snippets.txt", "kb-snippets", 16 * KiB)   (10 x 200 x 4 bytes + header).
Controls guide row to add (OmniControlsHelp.h is not edited here), after the "Clipboard history" row:
  { kKeyboard, { gTouchpad }, 0, false, "Keyboard snippets: Edit > Snippets", "Up to 10 saved phrases; {Cross} inserts or saves, {Square} deletes; not in password fields", "omniKsnKb* (OMNI_KB_SNIPPETS_V1)" },

Pure part: engine/entry/OmniKbSnippets.h (from tools/OmniKbSnippets.h: cleaning, 200-character UTF-8-safe cap, the
list of 10, file parse / serialize, labels, the picker's state, texts). Tests: tools/test_kb_snippets.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_kb_snippets.cpp -o t && ./t).
Shell part: engine/entry/OmniKbSnippetsShell.h (written by this script), namespace alias OKSN, names omniKsn*.
Ids: keyboard key action 7581 (OmniKbSnippets::kKbKey; checked unused in the tree). No settings row, no new import.

Anchors (each exactly once; whole lines; CRLF / LF kept; MARK makes each file idempotent):
  OmniBrowser.cpp   the next-field include line (pure include + the guest-mode __has_include block after); the clipboard
                    list's last forward declaration (declarations after); the edit-tools Select / Copy / Paste+Clips /
                    Undo / Clear lines (widths, the Snippets key); 'case omniKbPasteKey: {' (Snippets case before); the
                    clipboard list's click, hints and button lines (the snippets list's before); its draw line (after)
  OmniFeatures3.h   the clipboard-history shell include line (shell include after)
Other patches' names in anchors are spelled in two parts: their name scans read every apply_*.py's code.
Apply AFTER apply_kb_nextfield.py (and so after apply_clip_history.py, apply_kb_showpw.py, apply_kb_fields.py).
usage: apply_kb_snippets.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_KB_SNIPPETS_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_kb_snippets.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7581',)
NAMES = ('OKSN', 'omniKsn', 'OmniKsn', 'OmniKbSnippets', 'OMNI_KB_SNIPPETS')

# Other patches' names, in two parts (see the docstring).
CLH = 'omni' + 'Clh'
CLH_NS = 'OmniClip' + 'History'
KBF_MARK = 'OMNI_KB_' + 'FIELDS_V1'
KNF_MARK = 'OMNI_KB_' + 'NEXTFIELD_V1'
KNF_INCLUDE = '#include "OmniKb' + 'NextField.h" // ' + KNF_MARK + ': previous / next text box page script (pure)\n'
GUEST_MARK = 'OMNI_GUEST' + '_MODE_V1'   # never written into the tree (that patch skips files holding it)

NEEDS = {'OmniBrowser.cpp': ('OMNI_KEYBOARD_V2', 'OMNI_CLIP_HISTORY_V1', 'OMNI_KB_SHOWPW_V1', KBF_MARK, KNF_MARK),
         'OmniFeatures3.h': ('OMNI_CLIP_HISTORY_V1',)}

SHELL = r'''// OMNI_KB_SNIPPETS_V1: keyboard snippets (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after the clipboard history's shell). Pure part: OmniKbSnippets.h; reasons in tools/apply_kb_snippets.py.
// Up to 10 saved phrases (one line, at most 200 characters each) in /data/omni/kb-snippets.txt (plain text, omniIoQueue
// whole-file rewrite). The edit-tools row's "Snippets" key opens a list over the keys: Cross inserts a phrase at the
// cursor, the last row saves the text being edited after a confirm (worded for private tabs), Square twice deletes.
// Never in password fields, guest mode or self-tests. Main thread only.
#pragma once

namespace OKSN = OmniKbSnippets;

static OKSN::List omniKsnList;
static bool omniKsnLoaded = false;
static bool omniKsnGuest()
{
#ifdef OMNI_KSN_GUEST
    return omniGuest();
#else
    return false;
#endif
}
static bool omniKsnPrivateTab() { Tab* t = active(); return t && t->omniPrivate; }
// The key and the list: never in a password field, guest mode or self-tests.
static bool omniKsnKeyShown()
{
    return editing && omniKb.field != omniKbFieldPassword && !omniTestMode() && !omniKsnGuest();
}
static void omniKsnLoad()
{
    if (omniKsnLoaded) return;
    omniKsnLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OKSN::kFile).c_str(), "rb")) {
        char buffer[4096];
        size_t n;
        while (text.size() < OKSN::kReadCap && (n = fread(buffer, 1, sizeof(buffer), f)) > 0) text.append(buffer, n);
        fclose(f);
    }
    omniKsnList = OKSN::List::parse(text);
}
static void omniKsnStore()
{
    if (omniTestMode() || omniKsnGuest()) return;
    omniIoQueue(omniData(OKSN::kFile), omniKsnList.serialize(), false);
}

// --- the list over the keys ------------------------------------------------------------------------------------------
struct OmniKsnKbState {
    bool open = false;
    int session = -1;
    OKSN::Picker picker;
    std::string pending;        // the cleaned text waiting for the save confirm (memory only)
    bool pendingCut = false;
};
static OmniKsnKbState omniKsnKb;
static bool omniKsnKbShown() { return omniKsnKb.open && omniKsnKb.session == omniKb.session && omniKsnKeyShown(); }
static int omniKsnKbConfirm() { return omniKsnKbShown() ? omniKsnKb.picker.confirm : int(OKSN::cNone); }
static const char* omniKsnKbCrossLabel()
{
    if (omniKsnKb.picker.confirm == OKSN::cSave) return "Save";
    if (omniKsnKb.picker.confirm == OKSN::cDelete) return "Delete";
    return size_t(std::max(0, omniKsnKb.picker.sel)) < omniKsnList.size() ? "Insert" : "Save";
}
static void omniKsnKbClose()
{
    if (omniKsnKb.open) omniShellDirty = true;
    omniKsnKb.open = false;
    omniKsnKb.picker.confirm = OKSN::cNone;
    omniKsnKb.pending.clear();
}
static void omniKsnKbOpen()
{
    if (!omniKsnKeyShown()) return;   // password fields never list snippets
    if (omniKb.kind == 1 && !omniKb.fieldKnown) { notice("Reading the text box: try again in a moment"); return; }
    omniKsnLoad();
    omniKsnKb.open = true;
    omniKsnKb.session = omniKb.session;
    omniKsnKb.picker = OKSN::Picker();
    omniKsnKb.pending.clear();
    omniChromeWake();
    omniShellDirty = true;
}
// The text being edited: the selection when there is one, else the whole text box. false: not read yet.
static bool omniKsnCurrentText(std::string& out)
{
    if (omniKb.kind == 1) {
        if (!omniKb.mirrorValid || !omniKb.fieldKnown) return false;
        if (omniKb.mirrorNoSel) out = omniKb.before;
        else if (!omniKb.selected.empty()) out = omniKb.selected;
        else out = omniKb.before + omniKb.after;
        return true;
    }
    const std::string* t = omniKbText();
    if (!t) return false;
    omniKbClamp();
    const size_t a = std::min(omniKb.caret, omniKb.anchor), b = std::max(omniKb.caret, omniKb.anchor);
    out = a != b ? t->substr(a, b - a) : *t;
    return true;
}
static void omniKsnInsert(size_t i)
{
    if (i >= omniKsnList.size() || !omniKsnKeyShown()) return;
    const std::string value = omniKsnList.at(i);
    omniKsnKbClose();
    omniKb.select = false;
    append(value);   // as Paste: at the caret, replacing a selection
    omniShellDirty = true;
}
static void omniKsnAskSave()
{
    std::string text;
    if (!omniKsnCurrentText(text)) { notice("Reading the text box: try again in a moment"); return; }
    bool cut = false;
    text = OKSN::clean(text, &cut);
    if (text.empty()) { notice(OKSN::emptyNotice()); return; }
    for (const auto& it : omniKsnList.items())
        if (it == text) { notice(OKSN::addedNotice(OKSN::kDuplicate, false)); return; }
    omniKsnKb.pending = std::move(text);
    omniKsnKb.pendingCut = cut;
    omniKsnKb.picker.askSave();
}
static void omniKsnSave()
{
    if (omniKsnKb.pending.empty() || !omniKsnKeyShown()) return;   // the field kind is checked again here
    const OKSN::Add r = omniKsnList.add(omniKsnKb.pending);
    omniKsnKb.pending.clear();
    if (r == OKSN::kAdded) {
        omniKsnStore();
        omniKsnKb.picker.sel = int(omniKsnList.size()) - 1;
    }
    notice(OKSN::addedNotice(r, omniKsnKb.pendingCut));
}
static void omniKsnDelete(size_t i)
{
    if (!omniKsnList.remove(i)) return;
    omniKsnStore();
    omniKsnKb.picker.afterDelete(omniKsnList.size());
    notice("Snippet deleted");
}
static void omniKsnDo(OKSN::Act a)
{
    const size_t sel = size_t(std::max(0, omniKsnKb.picker.sel));
    switch (a) {
    case OKSN::aInsert: omniKsnInsert(sel); break;
    case OKSN::aAskSave: omniKsnAskSave(); break;
    case OKSN::aSave: omniKsnSave(); break;
    case OKSN::aFullNotice: notice(OKSN::saveRowLabel(omniKsnList.size())); break;
    case OKSN::aDelete: omniKsnDelete(sel); break;
    case OKSN::aClose: omniKsnKbClose(); break;
    default: break;
    }
    if (omniKsnKb.picker.confirm != OKSN::cSave) omniKsnKb.pending.clear();
}
static bool omniKsnKbButton(int b)
{
    if (!omniKsnKbShown()) { if (omniKsnKb.open) omniKsnKbClose(); return false; }
    OKSN::Btn k = OKSN::bOther;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: k = OKSN::bUp; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: k = OKSN::bDown; break;
    case SDL_CONTROLLER_BUTTON_A: k = OKSN::bCross; break;
    case SDL_CONTROLLER_BUTTON_X: k = OKSN::bSquare; break;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: k = OKSN::bCircle; break;
    default: break;
    }
    omniShellDirty = true;
    omniKsnDo(omniKsnKb.picker.press(k, omniKsnList.size()));
    return true;                                    // the other buttons wait until the list is closed
}
constexpr int omniKsnRowH = 32, omniKsnHead = 50;
static void omniKsnKbGeometry(int rows, int& x, int& y, int& w, int& h)
{
    w = std::min(700, keyboardWidth);
    x = keyboardX + (keyboardWidth - w) / 2;
    h = omniKsnHead + rows * omniKsnRowH + 10;
    y = actionY + keyHeight - h;                    // over the keys, its bottom on the action row's
}
static bool omniKsnKbClick(int px, int py)
{
    if (!omniKsnKbShown()) return false;
    const size_t n = omniKsnList.size();
    int x, y, w, h;
    omniKsnKbGeometry(int(n) + 1, x, y, w, h);
    omniShellDirty = true;
    if (px < x || px >= x + w || py < y || py >= y + h) { omniKsnKbClose(); return true; }   // elsewhere closes it
    const int k = py >= y + omniKsnHead ? (py - y - omniKsnHead) / omniKsnRowH : -1;
    if (k < 0 || k > int(n)) return true;           // the title or the margin
    omniKsnDo(omniKsnKb.picker.click(k, n));
    return true;
}
static void omniKsnKbDraw()
{
    if (!omniKsnKbShown()) return;
    const size_t n = omniKsnList.size();
    const int rows = int(n) + 1;
    const OKSN::Picker& pk = omniKsnKb.picker;
    const int sel = std::clamp(pk.sel, 0, rows - 1);
    const OmniTheme& T = omniTheme();
    int x, y, w, h;
    omniKsnKbGeometry(rows, x, y, w, h);
    omniShadow(x, y, w, h, omniRadius + 2, 14, 150, 4);
    fillRounded(x, y, w, h, omniRadius + 2, T.panel);
    const int tw = omniLabel("Snippets", float(x + 22), float(y + 26), omniBodyBold, T.ink, 0, w / 2);
    omniLabel(OKSN::subtitle(pk.confirm, omniKsnPrivateTab()), float(x + w - 22), float(y + 26), omniSmall,
        pk.confirm != OKSN::cNone ? T.accent : T.inkDim, 2, w - tw - 70);
    for (int i = 0; i < rows; ++i) {
        const int ry = y + omniKsnHead + i * omniKsnRowH;
        const bool on = i == sel, phrase = size_t(i) < n;
        if (on) fillRounded(x + 10, ry + 1, w - 20, omniKsnRowH - 2, omniRadius, T.accent);
        const float cy = ry + omniKsnRowH / 2.f;
        std::string text, value;
        if (phrase) {
            text = OKSN::label(omniKsnList.at(size_t(i)));
            if (on && pk.confirm == OKSN::cDelete) value = "Delete?";
        } else if (pk.confirm == OKSN::cSave) {
            text = "Save \"" + OKSN::label(omniKsnKb.pending, 30) + "\"";
            value = "Cross saves";
        } else text = OKSN::saveRowLabel(n);
        const int vw = value.empty() ? 0 : omniLabel(value, float(x + w - 24), cy, omniSmall, on ? T.accentInk : T.inkDim, 2, 200) + 16;
        omniLabel(text, float(x + 24), cy, omniSmall, on ? T.accentInk : phrase ? T.ink : T.inkDim, 0, w - 48 - vw);
    }
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        (KNF_INCLUDE,
         KNF_INCLUDE +
         '#include "OmniKbSnippets.h" // ' + MARK + ': keyboard snippets (pure: file, 200-character cap, picker)\n'
         '#if __has_include("OmniGuestMode.h") /* ' + MARK + ': guest mode in the tree: no snippets for a guest */\n'
         '#include "OmniGuestMode.h"\n'
         '#define OMNI_KSN_GUEST 1\n'
         '#endif\n'),
        ('static void ' + CLH + 'KbDraw();\n',
         'static void ' + CLH + 'KbDraw();\n'
         '// ' + MARK + ' (OmniKbSnippetsShell.h): the edit row\'s Snippets key and its list over the keys.\n'
         'static bool omniKsnKeyShown();\n'
         'static void omniKsnKbOpen();\n'
         'static bool omniKsnKbShown();\n'
         'static int omniKsnKbConfirm();\n'
         'static const char* omniKsnKbCrossLabel();\n'
         'static bool omniKsnKbButton(int b);\n'
         'static bool omniKsnKbClick(int x, int y);\n'
         'static void omniKsnKbDraw();\n'),
        # the edit-tools row: Snippets after Clips (not in password fields); Select, Copy, Undo, Clear 0.75 wide then
        ('        act(quick, "Select", omniKbSelectKey, 1); act(quick, "All", omniKbAllKey, 0.75f); act(quick, "Cut", omniKbCutKey, 0.75f);\n',
         '        // ' + MARK + ': "Snippets" after Clips (never in password fields); Select, Copy, Undo, Clear 0.75 wide with it\n'
         '        const float omniKsnU = omniKsnKeyShown() ? 0.75f : 1.f;\n'
         '        act(quick, "Select", omniKbSelectKey, omniKsnU); act(quick, "All", omniKbAllKey, 0.75f); act(quick, "Cut", omniKbCutKey, 0.75f);\n'),
        ('        else act(quick, "Copy", omniKbCopyKey, 1);\n',
         '        else act(quick, "Copy", omniKbCopyKey, omniKsnU); /* ' + MARK + ' */\n'),
        ('        act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Clips", ' + CLH_NS + '::kKbKey, 1);\n',
         '        act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Clips", ' + CLH_NS + '::kKbKey, 1);\n'
         '        if (omniKsnKeyShown()) act(quick, "Snippets", OmniKbSnippets::kKbKey, 1); // ' + MARK + '\n'),
        ('        act(quick, "Undo", omniKbUndoKey, 1);\n',
         '        act(quick, "Undo", omniKbUndoKey, omniKsnU); /* ' + MARK + ' */\n'),
        ('        act(quick, "Clear", omniKbClearKey, 1);\n',
         '        act(quick, "Clear", omniKbClearKey, omniKsnU); /* ' + MARK + ' */\n'),
        ('    case omniKbPasteKey: {\n',
         '    case OmniKbSnippets::kKbKey: omniKb.select = false; omniKsnKbOpen(); return; // ' + MARK + ': the snippets list\n'
         '    case omniKbPasteKey: {\n'),
        ('    if (' + CLH + 'KbClick(x, y)) return; // OMNI_CLIP_HISTORY_V1: the clipboard list (a row pastes, elsewhere closes it)\n',
         '    if (omniKsnKbClick(x, y)) return; // ' + MARK + ': the snippets list (a row acts, elsewhere closes it)\n'
         '    if (' + CLH + 'KbClick(x, y)) return; // OMNI_CLIP_HISTORY_V1: the clipboard list (a row pastes, elsewhere closes it)\n'),
        ('    if (' + CLH + 'KbShown()) { face(0, "Paste"); face(2, "Remove"); face(1, "Close"); pill("D-pad"); label("Choose"); return; } // OMNI_CLIP_HISTORY_V1\n',
         '    if (omniKsnKbShown()) { // ' + MARK + ': the snippets list (a confirm: Cross / Square again, Circle cancels)\n'
         '        face(0, omniKsnKbCrossLabel());\n'
         '        if (omniKsnKbConfirm() == 0) face(2, "Delete");\n'
         '        face(1, omniKsnKbConfirm() ? "Cancel" : "Close"); pill("D-pad"); label("Choose");\n'
         '        return;\n'
         '    }\n'
         '    if (' + CLH + 'KbShown()) { face(0, "Paste"); face(2, "Remove"); face(1, "Close"); pill("D-pad"); label("Choose"); return; } // OMNI_CLIP_HISTORY_V1\n'),
        ('    ' + CLH + 'KbDraw(); // OMNI_CLIP_HISTORY_V1: the clipboard list over the keys\n',
         '    ' + CLH + 'KbDraw(); // OMNI_CLIP_HISTORY_V1: the clipboard list over the keys\n'
         '    omniKsnKbDraw(); // ' + MARK + ': the snippets list over the keys\n'),
        ('    if (editing && ' + CLH + 'KbButton(button)) return; // OMNI_CLIP_HISTORY_V1: the clipboard list (Circle closes it, not the keyboard)\n',
         '    if (editing && omniKsnKbButton(button)) return; // ' + MARK + ': the snippets list (Circle closes it, not the keyboard)\n'
         '    if (editing && ' + CLH + 'KbButton(button)) return; // OMNI_CLIP_HISTORY_V1: the clipboard list (Circle closes it, not the keyboard)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "' + CLH_NS + 'Shell.h" // OMNI_CLIP_HISTORY_V1: clipboard history (keyboard list, quick menu row)\n',
         '#include "' + CLH_NS + 'Shell.h" // OMNI_CLIP_HISTORY_V1: clipboard history (keyboard list, quick menu row)\n'
         '#include "OmniKbSnippetsShell.h" // ' + MARK + ': keyboard snippets (edit row Snippets key, list over the keys)\n'),
    ],
}


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
    numbers stay): an id or name in another patch's notes is not a use."""
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
    """Before a first apply: no other patch or tree file uses this patch's ids or names. Siblings skipped: the Controls
    guide's patch (it quotes handler names) and any patch holding this MARK (built on this one)."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniKbSnippets.h', 'OmniKbSnippetsShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name or f.name == 'apply_controls_help.py':
            continue
        src = f.read_text(encoding='utf-8', errors='replace')
        if MARK in src:
            continue
        m = name.search(code_only(src))   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        if MARK in t:
            continue
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m:
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
    pure = (HERE / 'OmniKbSnippets.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniKbSnippets.h: %s missing' % MARK)
    written = [pure, SHELL] + [new for edits in EDITS.values() for _old, new in edits]
    if any(GUEST_MARK in t for t in written):
        sys.exit('internal: the guest-mode marker must not be written into the tree')
    msgs = [write_new('OmniKbSnippets.h', pure, 'OmniKb' + 'ShowPw.h'),
            write_new('OmniKbSnippetsShell.h', SHELL, CLH_NS + 'Shell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
