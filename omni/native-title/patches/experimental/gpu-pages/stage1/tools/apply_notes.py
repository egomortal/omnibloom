#!/usr/bin/env python3
"""OMNI_NOTES_V1 (2026-11-16): "Notes": a small notepad inside Omni (a code, a list, a link), typed with the on-screen
keyboard, plus "Add to notes" from Select text and "Add page to notes" from the page menu.

What existed (grep of the patched tree, chain_final order)
  omniKbEdit(std::string*, const char* label, done) (OMNI_DIALOGS_V1) edits a shell string with the on-screen keyboard
  as kind 2 ("dialog field"): Enter / Go submits (submitKeyboard -> omniKbTargetDone(true)), the field type is text or
  password, at most 1024 bytes (omniKbLimit). Multi-line editing (omniKbFieldMulti, the New line key) exists only for a
  web page's <textarea> (kind 1). So the keyboard has NO multi-line mode for shell strings, and this patch does not
  change the keyboard: a note is edited LINE BY LINE (each line one omniKbEdit; "Add line" appends one). A pasted text
  with line breaks becomes several lines. A line longer than 1024 bytes (from Add to notes) can be shortened with the
  keyboard but not lengthened (the keyboard's own cap).
  The label pointer is kept by the keyboard (omniKbLabel): only string literals are passed.

What the user sees
  - Options > Browse > "Notes" (value: how many). The panel: "New note" (Cross: the keyboard opens for the first line;
    Go creates the note and opens it), then the notes, last changed first: title = the note's first non-empty line,
    detail "N lines", value its date (Today / Yesterday / 12 Nov 2026). Corner "n / 200".
      Cross: opens the note's editor.   Triangle: "Copy" (Omni's clipboard via omniFxCopy, which also tells clipboard
      history (OMNI_CLIP_HISTORY_V1's omniClhNote) when that patch is in).   Square: "Delete this note?" (asks once).
  - The editor: one row per line ("(empty line)" for an empty one), then "Add line". Subtitle "N lines . x / 4096 bytes".
      Cross on a line: the keyboard edits it (Go keeps, Cancel drops the change). Cross on Add line: the keyboard for a
      new last line. Square on a line: deletes it (deleting the only line asks "Delete this note?"). Triangle: copies the
      whole note. A note emptied by editing is deleted ("Note deleted: it was empty"). Over 4 KB: cut, notice.
  - Select text (OMNI_TEXT_SELECT_V1): the "Selected text" panel gets a row "Add to notes" after Highlight; the selection
    becomes a new note (line breaks kept, cut at 4 KB: "Added to notes (the first 4 KB): ...").
  - Page menu (hold Cross on a page, no link / image): "Add page to notes" after "Save page for later" (web pages only):
    a note "page title\\naddress".
Private tabs: adding from a private tab (selection or page menu) asks "Save to notes?" / "Notes are kept after private
  browsing" (Save / Cancel) once per private session: after Save it does not ask again until the last private tab has
  closed (omniNtsTick, the same rule as clipboard history). Cancel saves nothing and asks again next time. Notes typed
  in the Notes panel never ask (they don't come from a page).
Guest mode (OMNI_GUEST_MODE_V1, not in the current chain): when its pure header OmniGuestMode.h is in the tree,
  OmniBrowser.cpp defines OMNI_NOTES_GUEST (__has_include) and omniNtsGuest() is omniGuest(): the guest sees and edits
  a separate in-memory list (never written, never asks), dropped when guest mode ends; the owner's notes are neither
  read nor shown nor written meanwhile. Without that header omniNtsGuest() is false. The inserted tree text never
  contains the guest patch's marker (that patch skips any file that does).
Store: /data/omni/notes.txt (omniIoQueue whole-file rewrite on every change; nothing written in test modes or guest
  mode), read once on first use (4 MB cap). Format: "omni-notes 1" then one note per line
  "id TAB created TAB modified TAB text", text escaped (\\ \\n \\t \\r); readers ignore fields after the fourth and unknown
  lines (forward / backward compatible; a file without the header line reads the same). Caps: 200 notes x 4096 bytes
  (UTF-8 boundary); text cleaned (valid UTF-8, CR LF -> LF, control characters dropped, trailing blanks trimmed); a
  larger file keeps the newest 200.

Pure part: engine/entry/OmniNotes.h (from tools/OmniNotes.h). Tests: tools/test_notes.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_notes.cpp -o t && ./t).
Shell part: engine/entry/OmniNotesShell.h (written by this script), namespace alias ONTS, names omniNts*.
Ids: Options tile 427 (Browse), "Selected text" row 21 (text select 1..4, highlights 20), page menu row 8621.

Anchors (each exactly once, whole lines, inserted after them unless noted; CRLF / LF kept; MARK makes files idempotent):
  OmniBrowser.cpp        the OmniHighlights.h include line (pure include + the guest-mode __has_include block)
  OmniFeatures3.h        the OmniHighlightsShell.h include line (shell include); the omniRlTick line of omniF3Tick (tick)
  OmniQuickMenu.h        the omniHltQuickAction declaration, the omniHltQuickTiles(p) line, the highlights Browse case
                         line, the omniHltQuickAction(r.id) input line (all apply_highlights.py's)
  OmniContextMenu.h      the omniRlContextRows declaration, the omniRlContextRows(p) call, the omniRlContextAction input
                         line (apply_reading_list.py's)
  OmniTextSelectShell.h  'static void omniTslActionsBuild(OmniFxPanel& p)' (declarations BEFORE it), the
                         omniHltActionRow(p) line, the highlights kActionId input line (apply_highlights.py's)
Apply AFTER apply_text_select.py, apply_reading_list.py, apply_highlights.py (and apply_clip_history.py if wanted).
usage: apply_notes.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_NOTES_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_notes.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('8621', '427')
NAMES = ('ONTS', 'omniNts', 'OmniNotes', 'OMNI_NOTES')
ACTION_ID = re.compile(r'kActionId\s*=\s*21\b')   # another "Selected text" row with the same id

SHELL = r'''// OMNI_NOTES_V1: Notes (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous namespace, after
// OmniHighlightsShell.h). Pure part: OmniNotes.h; reasons in tools/apply_notes.py.
// Options > Browse > Notes lists the notes (Cross opens the line editor, Triangle copies, Square deletes); "Add to notes"
// in the "Selected text" panel and "Add page to notes" in the page menu add one (a private tab asks once per private
// session). The owner's notes are /data/omni/notes.txt (omniIoQueue; not in test modes); in guest mode a separate
// in-memory list is used. Main thread only.
#pragma once

namespace ONTS = OmniNotes;
static std::vector<ONTS::Note> omniNtsOwner;       // the owner's notes (notes.txt), once loaded
static std::vector<ONTS::Note> omniNtsGuestList;   // guest mode: memory only, dropped when it ends
static bool omniNtsLoaded = false;
static ONTS::PrivateGate omniNtsGate;
static std::string omniNtsBuf;                     // what the keyboard edits
static long long omniNtsEditId = 0;                // the note the editor shows
static std::vector<long long> omniNtsShown;        // list rows -> note ids
enum { omniNtsRowNew = 1, omniNtsRowAddLine = 2, omniNtsRowFirst = 1000 };

static bool omniNtsGuest()
{
#ifdef OMNI_NOTES_GUEST
    return omniGuest();
#else
    return false;
#endif
}
static void omniNtsLoad()
{
    if (omniNtsLoaded || omniNtsGuest()) return;
    omniNtsLoaded = true;
    if (FILE* f = fopen(omniData(ONTS::kFileName).c_str(), "rb")) {
        std::string text;
        char buf[8192];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) <= ONTS::kMaxFileBytes) text.append(buf, n);
        fclose(f);
        omniNtsOwner = ONTS::parse(text);
    }
}
static std::vector<ONTS::Note>& omniNtsList()
{
    if (omniNtsGuest()) return omniNtsGuestList;
    omniNtsLoad();
    return omniNtsOwner;
}
static void omniNtsSave()
{
    if (omniNtsGuest() || omniTestMode() || !omniNtsLoaded) return;
    omniIoQueue(omniData(ONTS::kFileName), ONTS::serialize(omniNtsOwner), false);
}
static long long omniNtsNow() { return static_cast<long long>(time(nullptr)); }
static bool omniNtsAnyPrivate()
{
    for (auto& t : tabs) if (t && t->omniPrivate) return true;
    return false;
}
// Every pass (omniF3Tick): the private session ends with the last private tab; guest notes go when guest mode ends.
static void omniNtsTick()
{
    omniNtsGate.tick(omniNtsAnyPrivate());
    if (!omniNtsGuestList.empty() && !omniNtsGuest()) omniNtsGuestList.clear();
}
static void omniNtsListBuild(OmniFxPanel& p);
static void omniNtsEditorBuild(OmniFxPanel& p);
static bool omniNtsPanelShown()
{
    return !omniFxStack.empty() && (omniFxStack.back().build == omniNtsListBuild || omniFxStack.back().build == omniNtsEditorBuild);
}

// --- adding -----------------------------------------------------------------------------------------------------------
static void omniNtsAddNow(const std::string& text)
{
    bool cut = false;
    const ONTS::Add a = ONTS::add(omniNtsList(), text, omniNtsNow(), nullptr, &cut);
    if (a == ONTS::Add::Full) { notice(ONTS::fullNotice()); return; }
    if (a == ONTS::Add::Empty) { notice(ONTS::emptyNotice()); return; }
    omniNtsSave();
    notice(ONTS::addedNotice(cut, omniNtsGuest()));
    if (omniNtsPanelShown()) omniFxRefresh();
    omniShellDirty = true;
}
// From a page (Select text, the page menu): a private tab asks once per private session.
static void omniNtsAddFromPage(const std::string& text, bool privateTab)
{
    if (ONTS::clean(text).empty()) { notice(ONTS::emptyNotice()); return; }
    if (omniNtsList().size() >= ONTS::kMaxNotes) { notice(ONTS::fullNotice()); return; }
    if (!omniNtsGate.needAsk(privateTab, omniNtsGuest())) { omniNtsAddNow(text); return; }
    omniAsk(ONTS::privateAskTitle(), ONTS::privateAskBody(), "Save", [text](bool ok) {
        if (!ok) { notice("Not added to notes"); return; }
        omniNtsGate.accept();
        omniNtsAddNow(text);
    });
}
// "Selected text" panel (OmniTextSelectShell.h calls these)
static void omniNtsActionRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r; r.id = ONTS::kActionId; r.label = "Add to notes";
    r.enabled = !ONTS::clean(p.text).empty();
    if (omniNtsGuest()) r.value = "Not saved";
    else if (t && t->omniPrivate && !omniNtsGate.asked) r.value = "Asks first";
    p.rows.push_back(r);
}
static void omniNtsAddSelection(const std::string& text)
{
    Tab* t = active();
    omniNtsAddFromPage(text, t && t->omniPrivate);
}
// Page menu (OmniContextMenu.h calls these)
static void omniNtsContextRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r; r.id = ONTS::kContextId; r.label = "Add page to notes";
    r.enabled = t && omniWebURL(t->url);
    p.rows.push_back(r);
}
static bool omniNtsContextAction(int id)
{
    if (id != ONTS::kContextId) return false;
    omniFxCloseAll();
    Tab* t = active();
    if (t) omniNtsAddFromPage(ONTS::pageNote(t->title, t->url), t->omniPrivate);
    return true;
}

// --- the editor (a note, line by line) -----------------------------------------------------------------------------------
static void omniNtsEditorClose()
{
    if (!omniFxStack.empty() && omniFxStack.back().build == omniNtsEditorBuild) omniFxPop();
}
static void omniNtsDeleteNote(long long id)
{
    if (!ONTS::remove(omniNtsList(), id)) return;
    omniNtsSave();
    notice("Note deleted");
    if (omniNtsEditId == id) omniNtsEditorClose();
    if (omniNtsPanelShown()) omniFxRefresh();
}
static void omniNtsAskDelete(long long id)
{
    ONTS::Note* n = ONTS::find(omniNtsList(), id);
    if (!n) return;
    omniAsk(ONTS::deleteTitle(), "\"" + ONTS::title(n->text) + "\" (" + ONTS::lineDetail(n->text) + ")", "Delete", [id](bool ok) {
        if (ok) omniNtsDeleteNote(id);
    });
}
// The new text of note id (cleaned by the caller); an empty text deletes the note.
static void omniNtsStore(long long id, const std::string& text, bool cut)
{
    ONTS::Note* n = ONTS::find(omniNtsList(), id);
    if (!n) return;
    if (text.empty()) {
        ONTS::remove(omniNtsList(), id);
        omniNtsSave();
        notice("Note deleted: it was empty");
        omniNtsEditorClose();
        return;
    }
    if (cut) notice(ONTS::cutNotice());
    if (text == n->text) return;
    n->text = text;
    n->modified = omniNtsNow();
    omniNtsSave();
    omniShellDirty = true;
}
// Cross on a line (append: Add line): the keyboard edits that line; Go stores it.
static void omniNtsEditLine(long long id, size_t index, bool append)
{
    ONTS::Note* n = ONTS::find(omniNtsList(), id);
    if (!n) return;
    const std::vector<std::string> ls = ONTS::lines(n->text);
    if (!append && index >= ls.size()) return;
    omniNtsBuf = append ? std::string() : ls[index];
    omniKbEdit(&omniNtsBuf, append ? "Add a line to the note" : "Edit this line of the note", [id, index, append](bool ok) {
        const std::string line = omniNtsBuf;
        omniNtsBuf.clear();
        if (!ok) return;
        ONTS::Note* m = ONTS::find(omniNtsList(), id);
        if (!m || (append && ONTS::clean(line).empty())) return;
        std::string text = m->text;
        bool cut = false;
        if (!ONTS::setLine(text, append ? ONTS::lines(text).size() : index, line, &cut)) return;
        omniNtsStore(id, text, cut);
        if (omniNtsPanelShown()) omniFxRefresh();
    });
}
static void omniNtsEditorBuild(OmniFxPanel& p)
{
    ONTS::Note* n = ONTS::find(omniNtsList(), omniNtsEditId);
    if (!n) { p.title = "Note"; p.subtitle = "This note was deleted"; return; }
    p.title = ONTS::title(n->text);
    p.subtitle = ONTS::editorSubtitle(n->text);
    const std::vector<std::string> ls = ONTS::lines(n->text);
    for (size_t i = 0; i < ls.size(); ++i) {
        OmniFxRow r; r.id = omniNtsRowFirst + int(i);
        r.label = ls[i].empty() ? std::string("(empty line)") : ONTS::preview(ls[i], 200);
        if (r.label.empty()) r.label = "(blank line)";
        p.rows.push_back(r);
    }
    OmniFxRow a; a.id = omniNtsRowAddLine; a.label = "Add line"; a.icon = omniIconPlus;
    a.enabled = n->text.size() < ONTS::kMaxBytes;
    if (!a.enabled) a.value = "4 KB full";
    p.rows.push_back(a);
}
static bool omniNtsEditorInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const long long id = omniNtsEditId;
    ONTS::Note* n = ONTS::find(omniNtsList(), id);
    if (!n) return false;
    if (b == SDL_CONTROLLER_BUTTON_Y) { omniFxCopy(n->text, "Note"); return true; }
    if (r.id == omniNtsRowAddLine) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        if (!r.enabled) { notice(ONTS::cutNotice()); return true; }
        omniNtsEditLine(id, 0, true);
        return true;
    }
    if (r.id < omniNtsRowFirst) return false;
    const size_t i = size_t(r.id - omniNtsRowFirst);
    if (b == SDL_CONTROLLER_BUTTON_A) { omniNtsEditLine(id, i, false); return true; }
    if (b != SDL_CONTROLLER_BUTTON_X) return false;
    std::string text = n->text;
    if (!ONTS::removeLine(text, i)) return true;
    if (text.empty()) { omniNtsAskDelete(id); return true; }   // the only line: the note goes (asks)
    omniNtsStore(id, text, false);
    notice("Line deleted");
    return true;
}
static void omniNtsEditorShow(long long id)
{
    omniNtsEditId = id;
    OmniFxPanel p;
    p.title = "Note"; p.w = 1000; p.rowH = 52; p.maxVisible = 9;
    p.build = omniNtsEditorBuild; p.input = omniNtsEditorInput;
    p.faces = { { 0, "Edit line" }, { 3, "Copy note" }, { 2, "Delete line" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- the Notes panel (Options > Browse > Notes) ----------------------------------------------------------------------
static void omniNtsListBuild(OmniFxPanel& p)
{
    std::vector<ONTS::Note>& v = omniNtsList();
    omniNtsShown.clear();
    OmniFxRow nr; nr.id = omniNtsRowNew; nr.label = "New note"; nr.icon = omniIconPlus;
    nr.enabled = v.size() < ONTS::kMaxNotes;
    if (!nr.enabled) nr.value = "Full";
    p.rows.push_back(nr);
    const long long now = omniNtsNow();
    for (size_t i : ONTS::order(v)) {
        const ONTS::Note& n = v[i];
        OmniFxRow r; r.id = omniNtsRowFirst + int(omniNtsShown.size());
        r.label = ONTS::title(n.text);
        r.detail = ONTS::lineDetail(n.text);
        r.value = ONTS::dateText(n.modified, now);
        p.rows.push_back(r);
        omniNtsShown.push_back(n.id);
    }
    p.subtitle = ONTS::panelSubtitle(v.size(), omniNtsGuest());
    p.corner = std::to_string(v.size()) + " / " + std::to_string(ONTS::kMaxNotes);
}
static bool omniNtsListInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id == omniNtsRowNew) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        if (!r.enabled) { notice(ONTS::fullNotice()); return true; }
        omniNtsBuf.clear();
        omniKbEdit(&omniNtsBuf, "New note: its first line (Add line adds more)", [](bool ok) {
            const std::string line = omniNtsBuf;
            omniNtsBuf.clear();
            if (!ok) return;
            long long id = 0;
            bool cut = false;
            const ONTS::Add a = ONTS::add(omniNtsList(), line, omniNtsNow(), &id, &cut);
            if (a == ONTS::Add::Full) { notice(ONTS::fullNotice()); return; }
            if (a != ONTS::Add::Ok) return;
            omniNtsSave();
            if (cut) notice(ONTS::cutNotice());
            if (omniNtsPanelShown()) omniNtsEditorShow(id);
            omniShellDirty = true;
        });
        return true;
    }
    if (r.id < omniNtsRowFirst) return false;
    const size_t i = size_t(r.id - omniNtsRowFirst);
    if (i >= omniNtsShown.size()) return false;
    const long long id = omniNtsShown[i];
    ONTS::Note* n = ONTS::find(omniNtsList(), id);
    if (!n) return true;
    if (b == SDL_CONTROLLER_BUTTON_A) { omniNtsEditorShow(id); return true; }
    if (b == SDL_CONTROLLER_BUTTON_Y) { omniFxCopy(n->text, "Note"); return true; }
    if (b == SDL_CONTROLLER_BUTTON_X) { omniNtsAskDelete(id); return true; }
    return false;
}
static void omniNtsShow()
{
    OmniFxPanel p;
    p.title = "Notes"; p.w = 1000; p.rowH = 56; p.maxVisible = 8;
    p.build = omniNtsListBuild; p.input = omniNtsListInput;
    p.faces = { { 0, "Open" }, { 3, "Copy" }, { 2, "Delete" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
// Options > Browse tile (OmniQuickMenu.h)
static void omniNtsQuickTiles(OmniFxPanel& p)
{
    OmniFxRow r; r.id = ONTS::kTileList; r.label = "Notes"; r.value = std::to_string(omniNtsList().size());
    p.rows.push_back(r);
}
static bool omniNtsQuickAction(int id)
{
    if (id != ONTS::kTileList) return false;
    omniNtsShow();   // on top of the menu (Circle comes back)
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHighlights.h" // OMNI_HIGHLIGHTS_V1: highlights (pure: store, URL key, page script)\n',
         '#include "OmniHighlights.h" // OMNI_HIGHLIGHTS_V1: highlights (pure: store, URL key, page script)\n'
         '#include "OmniNotes.h" // ' + MARK + ': Notes (pure: notes.txt format, caps, line editing, texts)\n'
         '#if __has_include("OmniGuestMode.h") // ' + MARK + ': guest mode is in the tree: guest notes stay in memory\n'
         '#include "OmniGuestMode.h"\n'
         '#define OMNI_NOTES_GUEST 1\n'
         '#endif\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniHighlightsShell.h" // OMNI_HIGHLIGHTS_V1: Highlight, re-apply on load, Highlights panel\n',
         '#include "OmniHighlightsShell.h" // OMNI_HIGHLIGHTS_V1: Highlight, re-apply on load, Highlights panel\n'
         '#include "OmniNotesShell.h" // ' + MARK + ': Notes panel, line editor, Add to notes, Add page to notes\n'),
        ('    omniRlTick(now);    // OMNI_READING_LIST_V1\n',
         '    omniRlTick(now);    // OMNI_READING_LIST_V1\n'
         '    omniNtsTick();      // ' + MARK + ': private-session ask resets with the last private tab; guest notes\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniHltQuickAction(int id); // OMNI_HIGHLIGHTS_V1\n',
         'static bool omniHltQuickAction(int id); // OMNI_HIGHLIGHTS_V1\n'
         'static void omniNtsQuickTiles(OmniFxPanel& p); // ' + MARK + ' (OmniNotesShell.h)\n'
         'static bool omniNtsQuickAction(int id); // ' + MARK + '\n'),
        ('    omniHltQuickTiles(p); // OMNI_HIGHLIGHTS_V1: Highlights\n',
         '    omniHltQuickTiles(p); // OMNI_HIGHLIGHTS_V1: Highlights\n'
         '    omniNtsQuickTiles(p); // ' + MARK + ': Notes\n'),
        ('    case OmniHighlights::kTileList: return 1; // OMNI_HIGHLIGHTS_V1: Browse\n',
         '    case OmniHighlights::kTileList: return 1; // OMNI_HIGHLIGHTS_V1: Browse\n'
         '    case OmniNotes::kTileList: return 1; // ' + MARK + ': Browse\n'),
        ('    if (omniHltQuickAction(r.id)) return true; // OMNI_HIGHLIGHTS_V1\n',
         '    if (omniHltQuickAction(r.id)) return true; // OMNI_HIGHLIGHTS_V1\n'
         '    if (omniNtsQuickAction(r.id)) return true; // ' + MARK + '\n'),
    ],
    'OmniContextMenu.h': [
        ('static void omniRlContextRows(OmniFxPanel& p); // OMNI_READING_LIST_V1\n',
         'static void omniRlContextRows(OmniFxPanel& p); // OMNI_READING_LIST_V1\n'
         'static void omniNtsContextRow(OmniFxPanel& p); // ' + MARK + ' (OmniNotesShell.h): Add page to notes\n'
         'static bool omniNtsContextAction(int id); // ' + MARK + '\n'),
        ('        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n',
         '        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n'
         '        omniNtsContextRow(p); // ' + MARK + ': Add page to notes\n'),
        ('    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n',
         '    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n'
         '    if (omniNtsContextAction(r.id)) return true; // ' + MARK + '\n'),
    ],
    'OmniTextSelectShell.h': [
        ('static void omniTslActionsBuild(OmniFxPanel& p)\n',
         'static void omniNtsActionRow(OmniFxPanel& p); // ' + MARK + ' (OmniNotesShell.h): the Add to notes row\n'
         'static void omniNtsAddSelection(const std::string& text);\n'
         'static void omniTslActionsBuild(OmniFxPanel& p)\n'),
        ('    omniHltActionRow(p); // OMNI_HIGHLIGHTS_V1: Highlight\n',
         '    omniHltActionRow(p); // OMNI_HIGHLIGHTS_V1: Highlight\n'
         '    omniNtsActionRow(p); // ' + MARK + ': Add to notes\n'),
        ('    if (r.id == OmniHighlights::kActionId) { omniFxCloseAll(); omniHltCreate(); omniTslEnd(true); return true; }'
         ' // OMNI_HIGHLIGHTS_V1: the page script reads the selection before the clear\n',
         '    if (r.id == OmniHighlights::kActionId) { omniFxCloseAll(); omniHltCreate(); omniTslEnd(true); return true; }'
         ' // OMNI_HIGHLIGHTS_V1: the page script reads the selection before the clear\n'
         '    if (r.id == OmniNotes::kActionId) { const std::string sel = p.text; omniFxCloseAll(); omniTslEnd(true);'
         ' omniNtsAddSelection(sel); return true; } // ' + MARK + ': p is gone after omniFxCloseAll\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_TEXT_SELECT_V1', 'OMNI_HIGHLIGHTS_V1'),
         'OmniFeatures3.h': ('OMNI_HIGHLIGHTS_V1', 'OMNI_READING_LIST_V1'),
         'OmniQuickMenu.h': ('OMNI_HIGHLIGHTS_V1',),
         'OmniContextMenu.h': ('OMNI_READING_LIST_V1',),
         'OmniTextSelectShell.h': ('OMNI_TEXT_SELECT_V1', 'OMNI_HIGHLIGHTS_V1')}
GUEST_MARK = 'OMNI_GUEST' + '_MODE_V1'   # must never appear in tree text written here (that patch skips such files)


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
    mine = {'OmniNotes.h', 'OmniNotesShell.h'}
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
        if f.name in mine or not f.is_file() or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        if MARK in t:
            continue
        c = cpp_code(t)
        m = word.search(c) or name.search(c) or ACTION_ID.search(c)
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
    pure = (HERE / 'OmniNotes.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniNotes.h: %s missing' % MARK)
    for text in [pure, SHELL] + [new for edits in EDITS.values() for _, new in edits]:
        if GUEST_MARK in text:
            sys.exit('internal: the guest-mode marker must not be written into the tree')
    msgs = [write_new('OmniNotes.h', pure, 'OmniHighlights.h'),
            write_new('OmniNotesShell.h', SHELL, 'OmniHighlightsShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
