#!/usr/bin/env python3
"""OMNI_QUICK_ANSWERS_V1 (2026-11-16): instant answers in the address suggestions, fully offline.

What the user sees
  Typing math or a conversion in the address bar puts an answer above every other suggestion (above the
  "Switch to tab" rows of OMNI_TAB_SEARCH_V1; the list stays at 5 rows):
      "= 87"                          Calculator  -  Cross copies it            (12*7+3)
      "= 3.10686 mi"                  5 km in mi  -  Cross copies it            (5 km in mi)
      "= 12:00 AM EST (next day)"     9:00 PM PST  -  Cross copies it           (9pm pst to est)
  Cross / Triangle / a click on that row copies the value ("87", "3.10686 mi", "12:00 AM") into the address
  field (Undo brings the typed text back) and into Omni's own clipboard (omniKbClipboard, the keyboard's Paste),
  notice "Copied 87"; nothing is loaded. Go on the keyboard still searches / opens the typed text as before
  (the keyboard's Go never goes through the suggestion rows).

What answers (pure: engine/entry/OmniQuickAnswers.h, from tools/OmniQuickAnswers.h; tests tools/test_quick_answers.cpp)
  calculator: recursive descent, + - * / ^ ** ( ) % (percent, or modulo when an operand follows) "of" (after a
    percent: "15% of 80") "mod" " x " (spaced only) ! (0..170), sqrt cbrt abs ln log log2 log10 exp sin cos tan
    floor ceil round, pi e tau; no eval, no JS engine.
  units: fixed factors only (length, mass, US volume, temperature, data SI + IEC + bits, duration, area, speed);
    compound left sides ("3 ft 4 in to cm"); no currency.
  time zones: fixed abbreviations / utc+-h[:mm]; "in my time" / "local" only when localtime_r gives a non-zero
    tm_gmtoff (zero = TZ unset, or really UTC: then no "my time" answers).
  Never: anything that is not entirely math ("2048 game", "route 66"), bare numbers, URLs / IPs / versions,
    digits joined by '-' alone (dates, phones, scores), d/d/yyyy dates, "24/7"-style phrases, > 120 bytes,
    > 32 levels of nesting, any non-finite value (2^10000, 171!, 1/0).

Shell (OmniBrowser.cpp, all inline): OmniSuggestion gets omniQanValue (non-empty: an answer row; its url holds the
dim detail text, shown by the existing omniShownURL path, never loaded); omniQanPrepend() after omniTqPrepend();
omniSuggestGo() hands answer rows to omniQanUse() before the tab-search branch. Namespace alias OQAN.

Anchors (exactly once each; MARK makes the file idempotent; whole lines only, new lines inserted after/before):
  OmniBrowser.cpp  the OmniTabSearch.h include line; the "struct OmniSuggestion {" line; the omniBareURL line;
                   the omniTqPrepend() call line of omniSuggestUpdate; the omniTqKind line of omniSuggestGo
                   (all apply_tab_search.py's or the base's).
Apply AFTER apply_tab_search.py.
usage: apply_quick_answers.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_QUICK_ANSWERS_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabSearch.h" // OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" address suggestions (pure)\n',
         '#include "OmniTabSearch.h" // OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" address suggestions (pure)\n'
         '#include "OmniQuickAnswers.h" // OMNI_QUICK_ANSWERS_V1: "= 87" calculator / unit / time-zone answers (pure)\n'),
        ('struct OmniSuggestion { std::string url, title; bool search = false; // OMNI_FEATURES_V3: search: a search-engine suggestion\n',
         'struct OmniSuggestion { std::string url, title; bool search = false; // OMNI_FEATURES_V3: search: a search-engine suggestion\n'
         '    std::string omniQanValue = std::string(); // OMNI_QUICK_ANSWERS_V1: non-empty: an instant answer (Cross copies it; url is its detail text)\n'),
        ('static std::string omniBareURL(const std::string& url) { return omniLower(omniShownURL(url)); }\n',
         'static std::string omniBareURL(const std::string& url) { return omniLower(omniShownURL(url)); }\n'
         '// OMNI_QUICK_ANSWERS_V1: "= 87" first (above the "Switch to tab" rows), 5 rows in all. Offline, no eval: the\n'
         '// parser is OmniQuickAnswers.h. The row\'s url is only its dim detail text; omniSuggestGo never loads it.\n'
         'namespace OQAN = OmniQuickAnswers;\n'
         'static void omniQanPrepend()\n'
         '{\n'
         '    time_t now = time(nullptr);\n'
         '    struct tm tmv {};\n'
         '    const bool known = localtime_r(&now, &tmv) && tmv.tm_gmtoff != 0;   // 0: TZ unset (or UTC): no "my time"\n'
         '    OQAN::Answer a;\n'
         '    if (!OQAN::answer(address, a, known, known ? int(tmv.tm_gmtoff / 60) : 0)) return;\n'
         '    OmniSuggestion s;\n'
         '    s.title = a.title;\n'
         '    s.url = a.detail + "  -  Cross copies it";\n'
         '    s.omniQanValue = a.value;\n'
         '    omniSuggestions.insert(omniSuggestions.begin(), std::move(s));\n'
         '    if (omniSuggestions.size() > 5) omniSuggestions.resize(5);\n'
         '}\n'
         '// Cross / Triangle / click on the answer: into the address field (Undo restores the text) and Omni\'s clipboard.\n'
         'static void omniQanUse(const std::string value)\n'
         '{\n'
         '    omniSuggestSel = -1;\n'
         '    omniKbClipboard = value;\n'
         '    omniKbPushUndo();\n'
         '    address = value;\n'
         '    omniKb.caret = omniKb.anchor = address.size();\n'
         '    omniSuggestFor = "\\x01";\n'
         '    notice("Copied " + value);\n'
         '    omniShellDirty = true;\n'
         '}\n'),
        ('    omniTqPrepend(); // OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" rows first, 5 rows in all\n',
         '    omniTqPrepend(); // OMNI_TAB_SEARCH_V1: "Switch to tab" / "Reopen" rows first, 5 rows in all\n'
         '    omniQanPrepend(); // OMNI_QUICK_ANSWERS_V1: "= 87" above the tab rows, still 5 rows\n'),
        ('    if (omniSuggestions[i].omniTqKind) { // OMNI_TAB_SEARCH_V1: switch to / reopen the tab instead of loading here\n',
         '    if (!omniSuggestions[i].omniQanValue.empty()) { omniQanUse(omniSuggestions[i].omniQanValue); return; } // OMNI_QUICK_ANSWERS_V1: copy, never load\n'
         '    if (omniSuggestions[i].omniTqKind) { // OMNI_TAB_SEARCH_V1: switch to / reopen the tab instead of loading here\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': 'OMNI_TAB_SEARCH_V1'}


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
    msgs = [write_new('OmniQuickAnswers.h', 'OmniQuickAnswers.h', 'OmniTabSearch.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
