#!/usr/bin/env python3
"""OMNI_KB_LAYOUTS_V1 (2026-11-16): on-screen keyboard layouts and accented letters.

What the user sees
  - Browser settings has a new row before "Word suggestions":
        "Keyboard layout"   QWERTY (default) / AZERTY (French) / QWERTZ (German) / Nordic (Swedish, Finnish) /
                            Nordic (Danish, Norwegian) / Spanish / Portuguese      (Left / Right / Cross step)
    Saved in /data/omni/kb-layout.txt (the layout id, e.g. "azerty"); missing / unknown = QWERTY. Self-test modes
    always use QWERTY.
    Only the three letter rows change. The number row, the quick row, the action row, the symbols and number-pad
    layers and the field tails (text ' , . ?  url - . / ?  email - . _ @) are the same in every layout. Layouts with
    extra letters (ü ö ä å æ ø) have 11-key rows (each key 10/11 wide); AZERTY / Spanish / Portuguese move the
    row-2 tail key (' or -) to the start of row 3's tail. Shift / Caps upper-cases the extra letters too (Ä Ø Ñ).
  - Accents: hold Cross on a letter (450 ms) that has variants -> a popup row above the key:
        a: à á â ä æ å ã ā ą   e: é è ê ë ē ę ě   i: í ì î ï ī   o: ó ò ô ö ø õ œ ō ő   u: ú ù û ü ū ů ű
        c: ç ć č   n: ñ ń ň   s: ß ś š   y: ý ÿ   z: ž ź ż   l: ł      (upper case when the key is: É, Ñ, Ø ...;
        ß stays ß). D-pad left / right picks (wraps), Cross inserts, Circle cancels; any other button closes the
    popup and acts as usual (Square deletes, Triangle types a space ...). Pointer: a click on a variant inserts it,
    a click elsewhere closes the popup. Hint bar while open: Cross Insert, Circle Cancel, D-pad Choose accent.
    A letter WITH variants is typed when Cross is released (before 450 ms) instead of when pressed; every other key
    still types on press. A second button press while a letter waits types that letter first (order kept).
    Why Cross-hold and not R2: L2/R2 already move the caret by word on the keyboard (omniKbTick), L1/R1 by
    character, R3 symbols, L3 shift, touchpad Sites/Edit; every button is taken.
  - Text goes through omniKbType -> append(), the path of every key: InsertText (UTF-8) for webpage fields, the
    caret-aware local insert for the address bar and dialog fields. A one-shot Shift is used up by an upper-case
    accented letter too (OmniKbLayouts::isUpperLetter; before only A-Z).

Word suggestions (OMNI_KB_WORDS_V1, OmniKbWords.h, unchanged): it accepts ASCII letters and apostrophes only.
fragment() returns nothing when a non-ASCII byte touches the word, finishedWord() therefore never yields "caf" from
"café", clean() / Learned::add / parse reject non-ASCII words. So words with accents are skipped whole: no chips while
the caret is in or right after such a word, nothing learned from it, kb-words.txt lines with them are dropped on
load; the next ASCII word gets chips as before. Checked by test_kb_layouts.cpp.

Pure part: engine/entry/OmniKbLayouts.h (layout tables, compose, id parse / serialize, UTF-8 encode / decode, case
of Latin-1 / Latin Extended-A letters, accent variants, hold timing, popup position).
Tested by tools/test_kb_layouts.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_kb_layouts.cpp -o t && ./t
Shell side: OmniBrowser.cpp (namespace alias OKBL), OmniBrowserSettings.h (row id 848; 836, 845-847, 850, 860, 861,
870, 880, 890, 891, 895, 900+ are taken).

Anchors (exactly once each; MARK makes each file idempotent; CRLF / LF kept):
  OmniBrowser.cpp
    the OmniKbWordsData.h include (apply_kb_words.py's)            -> + OmniKbLayouts.h include
    "// Rows 0-3 characters, row 4 quick keys ..." comment          -> layout state + loader before it
    omniKbRows: the cache-key line ("|" + go;), the upper-case line of chars(), the three letter rows
    omniKbType: the one-shot shift line
    "// Shortcuts page (address keyboard) ..." comment               -> popup logic before it (after omniKbRepeating)
    omniKbButton case A: the omniKbFocusClamp + Delete-repeat lines  -> hold start between them
    omniKbClick: the omniKwClick line (apply_kb_words.py's)          -> popup click before it
    omniDrawKeyboard: its first lines (popup drawing before it), the last key label line + braces (the call)
    omniKbHints: the shortcuts-page hint block's end                 -> popup hints
    button(): the "editing && (B || BACK)" dismiss line              -> popup buttons before it
    omniKbTick: the omniKwTick line (apply_kb_words.py's)            -> omniKblTick after it
    the omniKwOtherFocus line (apply_kb_words.py's)                  -> settings row functions after it
    (the keyboard hint line face(0, ...) / OMNI_KB_WORDS_V1 is NOT an anchor: it differs between trees)
  OmniBrowserSettings.h  the omniKwSettingsInput declaration, the omniKwSettingsRows call, the omniKwRowChips input line
Apply AFTER apply_kb_words.py.
usage: apply_kb_layouts.py <engine tree>   (re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_KB_LAYOUTS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_KB_LAYOUTS_V1: the pure part of the on-screen keyboard's layouts and accent popup (no SDL, no WebKit).
// Layouts: the three letter rows of the letters layer (QWERTY default, AZERTY, QWERTZ, Nordic x2, Spanish, Portuguese);
// the number row, the field-specific punctuation tails (text ' , . ?  /  url - . / ?  /  email - . _ @), the quick row
// and the action row are the same in every layout. Accents: hold Cross on a letter -> a row of variants (e -> é è ê ...),
// in the case of the key. Everything is UTF-8; one key = one code point. Shell side and reasons: tools/apply_kb_layouts.py.
// Tested on the host with g++ (tools/test_kb_layouts.cpp).
#pragma once
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace OmniKbLayouts {

struct Layout { const char* id; const char* name; const char* row1; const char* row2; const char* row3; };
// Letters only (space separated); compose() adds the tails. Rows of 10 or 11 keys fill the 10-unit keyboard width.
inline constexpr Layout kLayouts[] = {
    { "qwerty", "QWERTY", "q w e r t y u i o p", "a s d f g h j k l", "z x c v b n m" },
    { "azerty", "AZERTY (French)", "a z e r t y u i o p", "q s d f g h j k l m", "w x c v b n" },
    { "qwertz", "QWERTZ (German)", "q w e r t z u i o p \xc3\xbc", "a s d f g h j k l \xc3\xb6 \xc3\xa4", "y x c v b n m" },
    { "nordic", "Nordic (Swedish, Finnish)", "q w e r t y u i o p \xc3\xa5", "a s d f g h j k l \xc3\xb6 \xc3\xa4", "z x c v b n m" },
    { "danish", "Nordic (Danish, Norwegian)", "q w e r t y u i o p \xc3\xa5", "a s d f g h j k l \xc3\xa6 \xc3\xb8", "z x c v b n m" },
    { "spanish", "Spanish", "q w e r t y u i o p", "a s d f g h j k l \xc3\xb1", "z x c v b n m" },
    { "portuguese", "Portuguese", "q w e r t y u i o p", "a s d f g h j k l \xc3\xa7", "z x c v b n m" },
};
constexpr int kCount = int(sizeof(kLayouts) / sizeof(kLayouts[0]));
constexpr uint32_t kHoldMs = 450;   // Cross held this long on a letter opens the accent popup

enum Tail { kTailText = 0, kTailUrl, kTailEmail };

inline int clampLayout(int i) { return i >= 0 && i < kCount ? i : 0; }
inline int stepLayout(int i, int dir) { return ((clampLayout(i) + dir) % kCount + kCount) % kCount; }
// kb-layout.txt holds the layout id ("azerty"); anything else (missing, empty, unknown) is QWERTY.
inline int parseId(std::string_view text)
{
    while (!text.empty() && (text.front() == ' ' || text.front() == '\t' || text.front() == '\r' || text.front() == '\n')) text.remove_prefix(1);
    while (!text.empty() && (text.back() == ' ' || text.back() == '\t' || text.back() == '\r' || text.back() == '\n')) text.remove_suffix(1);
    for (int i = 0; i < kCount; ++i) if (text == kLayouts[i].id) return i;
    return 0;
}
inline std::string serialize(int i) { return std::string(kLayouts[clampLayout(i)].id) + "\n"; }

inline std::vector<std::string> tokens(std::string_view s)
{
    std::vector<std::string> out;
    size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && s[i] == ' ') ++i;
        size_t j = i;
        while (j < s.size() && s[j] != ' ') ++j;
        if (j > i) out.emplace_back(s.substr(i, j - i));
        i = j;
    }
    return out;
}
inline int countTokens(std::string_view s) { return int(tokens(s).size()); }

// The three letter rows (keyboard rows 1-3) for a layout and a field kind. The row-2 tail key (' or -) stays on row 2
// when that row has fewer than 10 letters, else it starts row 3's tail. QWERTY gives exactly the rows used before.
struct Rows { std::string rows[3]; };
inline Rows compose(int layout, int tail)
{
    const Layout& L = kLayouts[clampLayout(layout)];
    const char* tail2 = tail == kTailText ? "'" : "-";
    const char* tail3 = tail == kTailUrl ? ". / ?" : tail == kTailEmail ? ". _ @" : ", . ?";
    Rows r;
    r.rows[0] = L.row1;
    r.rows[1] = L.row2;
    r.rows[2] = L.row3;
    if (countTokens(L.row2) < 10) r.rows[1] += std::string(" ") + tail2;
    else r.rows[2] += std::string(" ") + tail2;
    r.rows[2] += std::string(" ") + tail3;
    return r;
}

// UTF-8 ------------------------------------------------------------------------------------------------------------
inline std::string utf8(uint32_t cp)
{
    std::string o;
    if (cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) cp = 0xFFFD;
    if (cp < 0x80) o += char(cp);
    else if (cp < 0x800) { o += char(0xC0 | (cp >> 6)); o += char(0x80 | (cp & 0x3F)); }
    else if (cp < 0x10000) { o += char(0xE0 | (cp >> 12)); o += char(0x80 | ((cp >> 6) & 0x3F)); o += char(0x80 | (cp & 0x3F)); }
    else { o += char(0xF0 | (cp >> 18)); o += char(0x80 | ((cp >> 12) & 0x3F)); o += char(0x80 | ((cp >> 6) & 0x3F)); o += char(0x80 | (cp & 0x3F)); }
    return o;
}
// One strict code point at the start of s (no overlongs, surrogates or > U+10FFFF); false on bad input.
inline bool decodeOne(std::string_view s, uint32_t& cp, size_t& len)
{
    if (s.empty()) return false;
    const unsigned char c = s[0];
    uint32_t min = 0;
    if (c < 0x80) { cp = c; len = 1; return true; }
    if ((c & 0xE0) == 0xC0) { cp = c & 0x1F; len = 2; min = 0x80; }
    else if ((c & 0xF0) == 0xE0) { cp = c & 0x0F; len = 3; min = 0x800; }
    else if ((c & 0xF8) == 0xF0) { cp = c & 0x07; len = 4; min = 0x10000; }
    else return false;
    if (s.size() < len) return false;
    for (size_t i = 1; i < len; ++i) {
        const unsigned char d = s[i];
        if ((d & 0xC0) != 0x80) return false;
        cp = (cp << 6) | (d & 0x3F);
    }
    return cp >= min && cp <= 0x10FFFF && !(cp >= 0xD800 && cp <= 0xDFFF);
}
inline bool validUtf8(std::string_view s)
{
    uint32_t cp; size_t len;
    while (!s.empty()) { if (!decodeOne(s, cp, len)) return false; s.remove_prefix(len); }
    return true;
}
inline bool singleCodePoint(std::string_view s, uint32_t& cp)
{
    size_t len = 0;
    return decodeOne(s, cp, len) && len == s.size();
}

// Case of the letters the keyboard can type: ASCII, Latin-1 (à..þ, ÿ) and Latin Extended-A. ß has no single-letter
// capital here (stays ß).
inline uint32_t upperCp(uint32_t cp)
{
    if (cp >= 'a' && cp <= 'z') return cp - 0x20;
    if (cp >= 0xE0 && cp <= 0xFE && cp != 0xF7) return cp - 0x20;
    if (cp == 0xFF) return 0x178;
    if (cp == 0x131) return 'I';
    if ((cp >= 0x100 && cp <= 0x12F) || (cp >= 0x132 && cp <= 0x137) || (cp >= 0x14A && cp <= 0x177)) return cp & 1 ? cp - 1 : cp;
    if ((cp >= 0x139 && cp <= 0x148) || (cp >= 0x179 && cp <= 0x17E)) return cp & 1 ? cp : cp - 1;
    return cp;
}
inline uint32_t lowerCp(uint32_t cp)
{
    if (cp >= 'A' && cp <= 'Z') return cp + 0x20;
    if (cp >= 0xC0 && cp <= 0xDE && cp != 0xD7) return cp + 0x20;
    if (cp == 0x178) return 0xFF;
    if ((cp >= 0x100 && cp <= 0x12F) || (cp >= 0x132 && cp <= 0x137) || (cp >= 0x14A && cp <= 0x177)) return cp & 1 ? cp : cp + 1;
    if ((cp >= 0x139 && cp <= 0x148) || (cp >= 0x179 && cp <= 0x17E)) return cp & 1 ? cp + 1 : cp;
    return cp;
}
// A key's label in upper case: one-code-point letters only (".com", "www.", digits and symbols are unchanged).
inline std::string upperToken(const std::string& token)
{
    uint32_t cp;
    if (!singleCodePoint(token, cp)) return token;
    const uint32_t u = upperCp(cp);
    return u == cp ? token : utf8(u);
}
// One upper-case letter (A, Ä, É, Ł ...): a one-shot Shift is used up by it.
inline bool isUpperLetter(std::string_view s)
{
    uint32_t cp;
    return singleCodePoint(s, cp) && lowerCp(cp) != cp;
}

// Accent popup ------------------------------------------------------------------------------------------------------
struct Accent { const char* base; const char* list; };
inline constexpr Accent kAccents[] = {
    { "a", "\xc3\xa0 \xc3\xa1 \xc3\xa2 \xc3\xa4 \xc3\xa6 \xc3\xa5 \xc3\xa3 \xc4\x81 \xc4\x85" },   // à á â ä æ å ã ā ą
    { "e", "\xc3\xa9 \xc3\xa8 \xc3\xaa \xc3\xab \xc4\x93 \xc4\x99 \xc4\x9b" },                     // é è ê ë ē ę ě
    { "i", "\xc3\xad \xc3\xac \xc3\xae \xc3\xaf \xc4\xab" },                                       // í ì î ï ī
    { "o", "\xc3\xb3 \xc3\xb2 \xc3\xb4 \xc3\xb6 \xc3\xb8 \xc3\xb5 \xc5\x93 \xc5\x8d \xc5\x91" },   // ó ò ô ö ø õ œ ō ő
    { "u", "\xc3\xba \xc3\xb9 \xc3\xbb \xc3\xbc \xc5\xab \xc5\xaf \xc5\xb1" },                     // ú ù û ü ū ů ű
    { "c", "\xc3\xa7 \xc4\x87 \xc4\x8d" },                                                         // ç ć č
    { "n", "\xc3\xb1 \xc5\x84 \xc5\x88" },                                                         // ñ ń ň
    { "s", "\xc3\x9f \xc5\x9b \xc5\xa1" },                                                         // ß ś š
    { "y", "\xc3\xbd \xc3\xbf" },                                                                  // ý ÿ
    { "z", "\xc5\xbe \xc5\xba \xc5\xbc" },                                                         // ž ź ż
    { "l", "\xc5\x82" },                                                                           // ł
};
// The variants for a key (in the key's case); empty: the key has none (Cross types it at once).
inline std::vector<std::string> variants(std::string_view key)
{
    uint32_t cp;
    if (!singleCodePoint(key, cp)) return {};
    const uint32_t low = lowerCp(cp);
    const bool upper = low != cp;
    const std::string base = utf8(low);
    for (const Accent& a : kAccents) {
        if (base != a.base) continue;
        std::vector<std::string> out = tokens(a.list);
        if (upper)
            for (auto& v : out) { uint32_t c; if (singleCodePoint(v, c)) v = utf8(upperCp(c)); }
        return out;
    }
    return {};
}
inline int step(int sel, int n, int dir) { return n <= 0 ? 0 : ((sel + dir) % n + n) % n; }
// The hold has lasted long enough (SDL tick wrap-safe).
inline bool holdOpens(uint32_t since, uint32_t now) { return int32_t(now - since) >= int32_t(kHoldMs); }
// Left edge of a popup of n cells centred on centreX, kept inside [minX, maxX].
inline int popupLeft(int centreX, int n, int cellW, int minX, int maxX)
{
    const int w = n * cellW;
    int x = centreX - w / 2;
    if (x + w > maxX) x = maxX - w;
    if (x < minX) x = minX;
    return x;
}

} // namespace OmniKbLayouts
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniKbWordsData.h" // OMNI_KB_WORDS_V1: the built-in word list (generated)\n',
         '#include "OmniKbWordsData.h" // OMNI_KB_WORDS_V1: the built-in word list (generated)\n'
         '#include "OmniKbLayouts.h" // OMNI_KB_LAYOUTS_V1: keyboard layouts, accent variants, UTF-8 (pure)\n'),
        ('// Rows 0-3 characters, row 4 quick keys (or the edit tools), row 5 actions; each row is 10 units wide.\n',
         '// OMNI_KB_LAYOUTS_V1: the layout of the letter rows (Browser settings > Keyboard layout, kb-layout.txt; read once)\n'
         '// and the accent popup (hold Cross on a letter). Pure part: OmniKbLayouts.h; reasons: tools/apply_kb_layouts.py.\n'
         'namespace OKBL = OmniKbLayouts;\n'
         'static std::string omniData(const char* name);\n'
         'static void omniIoQueue(const std::string& path, std::string data, bool append);\n'
         'static int omniKblLayoutIndex = -1;   // -1: not read yet\n'
         'static int omniKblLayout()\n'
         '{\n'
         '    if (omniTestMode()) return 0;   // self-tests keep QWERTY\n'
         '    if (omniKblLayoutIndex < 0) {\n'
         '        std::string text;\n'
         '        if (FILE* f = fopen(omniData("kb-layout.txt").c_str(), "rb")) { char b[64]; const size_t n = fread(b, 1, sizeof(b), f); fclose(f); text.assign(b, n); }\n'
         '        omniKblLayoutIndex = OKBL::parseId(text);\n'
         '    }\n'
         '    return OKBL::clampLayout(omniKblLayoutIndex);\n'
         '}\n'
         'struct OmniKblState {\n'
         '    bool pending = false;          // Cross is down on a letter with accents: typed on release, popup on hold\n'
         '    std::string pendingKey;\n'
         '    uint32_t pendingSince = 0;\n'
         '    int pendingSession = -1;\n'
         '    bool open = false;             // the popup\n'
         '    std::vector<std::string> items;\n'
         '    int sel = 0, row = 0, col = 0, session = -1;\n'
         '};\n'
         'static OmniKblState omniKbl;\n'
         '// Rows 0-3 characters, row 4 quick keys (or the edit tools), row 5 actions; each row is 10 units wide.\n'),
        ('        + "|" + std::to_string(omniKb.tools) + "|" + std::to_string(omniKb.kind == 0) + "|" + go;\n',
         '        + "|" + std::to_string(omniKb.tools) + "|" + std::to_string(omniKb.kind == 0) + "|" + go\n'
         '        + "|" + std::to_string(omniKblLayout()); // OMNI_KB_LAYOUTS_V1\n'),
        ("                    if (upper && token.size() == 1 && token[0] >= 'a' && token[0] <= 'z') token[0] = char(token[0] - 'a' + 'A');\n",
         "                    if (upper) token = OKBL::upperToken(token); // OMNI_KB_LAYOUTS_V1: one-letter keys, ASCII and accented (was a-z only)\n"),
        ('        chars(rows[1], "q w e r t y u i o p", 1);\n'
         '        chars(rows[2], url || email ? "a s d f g h j k l -" : "a s d f g h j k l \'", 1);\n'
         '        chars(rows[3], url ? "z x c v b n m . / ?" : email ? "z x c v b n m . _ @" : "z x c v b n m , . ?", 1);\n',
         '        // OMNI_KB_LAYOUTS_V1: the letter rows of the chosen layout (QWERTY = the rows used before); 10 or 11 keys a row.\n'
         '        const OKBL::Rows letters = OKBL::compose(omniKblLayout(), url ? OKBL::kTailUrl : email ? OKBL::kTailEmail : OKBL::kTailText);\n'
         '        for (int i = 0; i < 3; ++i) chars(rows[1 + i], letters.rows[i].c_str(), 10.f / float(std::max(1, OKBL::countTokens(letters.rows[i]))));\n'),
        ("    if (omniKb.caps == 1 && value.size() == 1 && value[0] >= 'A' && value[0] <= 'Z') { omniKb.caps = 0; shift = false; }   // one-shot shift\n",
         "    if (omniKb.caps == 1 && OKBL::isUpperLetter(value)) { omniKb.caps = 0; shift = false; }   // one-shot shift (OMNI_KB_LAYOUTS_V1: accented capitals too)\n"),
        ('// Shortcuts page (address keyboard): tiles 0-19, then the action row 20 Letters, 21 Go, 22 Close.\n',
         '// OMNI_KB_LAYOUTS_V1: the accent popup. Cross on a letter with variants waits: released before OKBL::kHoldMs it types\n'
         '// the letter (omniKblFlush), held it opens the popup (omniKblTick). Any other button first types a waiting letter.\n'
         'static void omniKblClose() { if (omniKbl.open) omniShellDirty = true; omniKbl.open = false; omniKbl.items.clear(); }\n'
         'static void omniKblFlush()\n'
         '{\n'
         '    if (!omniKbl.pending) return;\n'
         '    omniKbl.pending = false;\n'
         '    if (editing && omniKbl.pendingSession == omniKb.session) omniKbType(omniKbl.pendingKey);\n'
         '    omniShellDirty = true;\n'
         '}\n'
         '// Cross on the focused key: true when it is a letter with accents (it now waits for the release or the hold).\n'
         'static bool omniKblHoldStart()\n'
         '{\n'
         '    omniKblFlush();\n'
         '    if (omniKbRepeating || omniTestMode() || omniKb.layer != omniKbLetters || !controller) return false;\n'
         '    const auto& rows = omniKbRows();\n'
         '    const OmniKbKey& k = rows[omniKb.row][omniKb.col];\n'
         '    if (k.action != omniKbInsert || OKBL::variants(k.insert).empty()) return false;\n'
         '    omniKbl.pending = true;\n'
         '    omniKbl.pendingKey = k.insert;\n'
         '    omniKbl.pendingSince = SDL_GetTicks();\n'
         '    omniKbl.pendingSession = omniKb.session;\n'
         '    omniKbl.row = omniKb.row;\n'
         '    omniKbl.col = omniKb.col;\n'
         '    return true;\n'
         '}\n'
         '// Every main-loop pass (omniKbTick): the release types the letter, the hold opens the popup.\n'
         'static void omniKblTick()\n'
         '{\n'
         '    if (omniKbl.open && (!editing || omniKbl.session != omniKb.session || omniKb.layer != omniKbLetters || (omniKb.kind == 0 && omniKbPage != 0))) omniKblClose();\n'
         '    if (!omniKbl.pending) return;\n'
         '    if (!editing || omniKbl.pendingSession != omniKb.session) { omniKbl.pending = false; return; }\n'
         '    if (!controller || !SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_A)) { omniKblFlush(); return; }\n'
         '    if (!OKBL::holdOpens(omniKbl.pendingSince, SDL_GetTicks())) return;\n'
         '    omniKbl.pending = false;\n'
         '    omniKbl.items = OKBL::variants(omniKbl.pendingKey);\n'
         '    if (omniKbl.items.empty()) { omniKbType(omniKbl.pendingKey); return; }\n'
         '    omniKbl.open = true;\n'
         '    omniKbl.sel = 0;\n'
         '    omniKbl.session = omniKb.session;\n'
         '    omniChromeWake();\n'
         '    omniShellDirty = true;\n'
         '}\n'
         '// Controller buttons while the keyboard is open (button(), before Circle closes it): true when the popup used it.\n'
         'static bool omniKblButton(int b)\n'
         '{\n'
         '    omniKblFlush();\n'
         '    if (!omniKbl.open) return false;\n'
         '    const int n = int(omniKbl.items.size());\n'
         '    omniShellDirty = true;\n'
         '    switch (b) {\n'
         '    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniKbl.sel = OKBL::step(omniKbl.sel, n, -1); return true;\n'
         '    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniKbl.sel = OKBL::step(omniKbl.sel, n, 1); return true;\n'
         '    case SDL_CONTROLLER_BUTTON_DPAD_UP: case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return true;\n'
         '    case SDL_CONTROLLER_BUTTON_A: {\n'
         '        const std::string v = n ? omniKbl.items[size_t(std::clamp(omniKbl.sel, 0, n - 1))] : std::string();\n'
         '        omniKblClose();\n'
         '        if (!v.empty()) omniKbType(v);\n'
         '        return true;\n'
         '    }\n'
         '    case SDL_CONTROLLER_BUTTON_B: omniKblClose(); return true;\n'
         '    default: omniKblClose(); return false;   // Square, Triangle, shoulders, Options ... act as usual\n'
         '    }\n'
         '}\n'
         '// Where the popup is (layout coordinates): cells of cw x ch above the key it belongs to.\n'
         'static void omniKblGeometry(int& x, int& y, int& cw, int& ch)\n'
         '{\n'
         '    cw = 56; ch = 48;\n'
         '    const auto& rows = omniKbRows();\n'
         '    const int r = std::clamp(omniKbl.row, 0, int(rows.size()) - 1), c = std::clamp(omniKbl.col, 0, int(rows[r].size()) - 1);\n'
         '    const int centre = keyboardX + int(omniKbKeyCentre(rows[r], c) * keyWidth + 0.5f) - 2;\n'
         '    x = OKBL::popupLeft(centre, int(omniKbl.items.size()), cw, keyboardX - 8, keyboardX + keyboardWidth + 8);\n'
         '    y = (r < 5 ? keyboardY + r * keyHeight : actionY) - ch - 8;\n'
         '}\n'
         '// Pointer clicks while the keyboard is open: a variant inserts it, anywhere else closes the popup. true: used.\n'
         'static bool omniKblClick(int x, int y)\n'
         '{\n'
         '    omniKblFlush();\n'
         '    if (!omniKbl.open) return false;\n'
         '    int px, py, cw, ch;\n'
         '    omniKblGeometry(px, py, cw, ch);\n'
         '    const int n = int(omniKbl.items.size());\n'
         '    std::string v;\n'
         '    if (y >= py && y < py + ch && x >= px && x < px + n * cw) v = omniKbl.items[size_t((x - px) / cw)];\n'
         '    omniKblClose();\n'
         '    if (!v.empty()) omniKbType(v);\n'
         '    return true;\n'
         '}\n'
         '// Shortcuts page (address keyboard): tiles 0-19, then the action row 20 Letters, 21 Go, 22 Close.\n'),
        ('        omniKbFocusClamp();\n'
         '        if (omniKbRepeating && omniKbRepeatCount > 12 && omniKbRows()[omniKb.row][omniKb.col].action == omniKbBackKey) omniKbDeleteWord();\n',
         '        omniKbFocusClamp();\n'
         '        if (omniKblHoldStart()) break; // OMNI_KB_LAYOUTS_V1: a letter with accents types on release, opens the popup when held\n'
         '        if (omniKbRepeating && omniKbRepeatCount > 12 && omniKbRows()[omniKb.row][omniKb.col].action == omniKbBackKey) omniKbDeleteWord();\n'),
        ('    if (omniKwClick(x, y)) return; // OMNI_KB_WORDS_V1: a word chip in the preview row\n',
         '    if (omniKblClick(x, y)) return; // OMNI_KB_LAYOUTS_V1: the accent popup\n'
         '    if (omniKwClick(x, y)) return; // OMNI_KB_WORDS_V1: a word chip in the preview row\n'),
        ('static void omniDrawKeyboard()\n{\n    omniKbEnsure();\n',
         '// OMNI_KB_LAYOUTS_V1: the accent popup, drawn by omniDrawKeyboard over the keys (geometry: omniKblGeometry).\n'
         'static void omniKblDraw()\n'
         '{\n'
         '    if (!omniKbl.open || omniKbl.items.empty()) return;\n'
         '    const OmniTheme& T = omniTheme();\n'
         '    int x, y, cw, ch;\n'
         '    omniKblGeometry(x, y, cw, ch);\n'
         '    const int n = int(omniKbl.items.size());\n'
         '    omniShadow(x - 6, y - 6, n * cw + 12, ch + 12, omniRadius + 2, 12, 140, 4);\n'
         '    fillRounded(x - 6, y - 6, n * cw + 12, ch + 12, omniRadius + 2, T.panel);\n'
         '    for (int i = 0; i < n; ++i) {\n'
         '        const bool sel = i == omniKbl.sel;\n'
         '        fillRounded(x + i * cw + 2, y, cw - 4, ch, omniRadius, sel ? T.accent : T.key);\n'
         '        omniLabel(omniKbl.items[size_t(i)], x + i * cw + cw / 2.f, y + ch / 2.f, omniBody, sel ? T.accentInk : T.ink, 1, cw - 8);\n'
         '    }\n'
         '}\n'
         'static void omniDrawKeyboard()\n{\n    omniKbEnsure();\n'),
        ('            omniLabel(label, x0 + w / 2.f, y + keyH / 2.f, big ? omniBody : omniSmall, ink, 1, w - 8);\n'
         '        }\n'
         '    }\n'
         '}\n',
         '            omniLabel(label, x0 + w / 2.f, y + keyH / 2.f, big ? omniBody : omniSmall, ink, 1, w - 8);\n'
         '        }\n'
         '    }\n'
         '    omniKblDraw(); // OMNI_KB_LAYOUTS_V1: the accent popup over the keys\n'
         '}\n'),
        ('        pill(ps ? "R3" : "RS"); label("Translate page");\n'
         '        return;\n'
         '    }\n',
         '        pill(ps ? "R3" : "RS"); label("Translate page");\n'
         '        return;\n'
         '    }\n'
         '    if (omniKbl.open) { face(0, "Insert"); face(1, "Cancel"); pill("D-pad"); label("Choose accent"); return; } // OMNI_KB_LAYOUTS_V1\n'),
        ('    if (editing && (button == SDL_CONTROLLER_BUTTON_B || button == SDL_CONTROLLER_BUTTON_BACK)) {\n',
         '    if (editing && omniKblButton(button)) return; // OMNI_KB_LAYOUTS_V1: the accent popup (Circle cancels it, not the keyboard)\n'
         '    if (editing && (button == SDL_CONTROLLER_BUTTON_B || button == SDL_CONTROLLER_BUTTON_BACK)) {\n'),
        ('    omniKwTick(); // OMNI_KB_WORDS_V1: saves learned words once the keyboard is closed\n',
         '    omniKwTick(); // OMNI_KB_WORDS_V1: saves learned words once the keyboard is closed\n'
         '    omniKblTick(); // OMNI_KB_LAYOUTS_V1: Cross released / held on a letter with accents\n'),
        ('static bool omniKwOtherFocus() { return omniSuggestSelected() >= 0 || omniF2FillSel >= 0; } // OMNI_KB_WORDS_V1: a strip above the keyboard has the focus\n',
         'static bool omniKwOtherFocus() { return omniSuggestSelected() >= 0 || omniF2FillSel >= 0; } // OMNI_KB_WORDS_V1: a strip above the keyboard has the focus\n'
         '// OMNI_KB_LAYOUTS_V1: Browser settings > "Keyboard layout" (row id in OmniBrowserSettings.h).\n'
         'static void omniKblSettingsRow(OmniFxPanel& p)\n'
         '{\n'
         '    OmniFxRow r; r.id = omniKblRowId; r.label = "Keyboard layout"; r.value = OKBL::kLayouts[omniKblLayout()].name; r.stepper = true;\n'
         '    p.rows.push_back(r);\n'
         '}\n'
         'static bool omniKblSettingsInput(int b)\n'
         '{\n'
         '    const int dir = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT || b == SDL_CONTROLLER_BUTTON_A) ? 1 : 0;\n'
         '    if (!dir) return false;\n'
         '    omniKblLayoutIndex = OKBL::stepLayout(omniKblLayout(), dir);\n'
         '    omniIoQueue(omniData("kb-layout.txt"), OKBL::serialize(omniKblLayoutIndex), false);\n'
         '    omniKblClose();\n'
         '    omniFxRefresh();\n'
         '    return true;\n'
         '}\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniKwSettingsInput(int id, int b);\n',
         'static bool omniKwSettingsInput(int id, int b);\n'
         'constexpr int omniKblRowId = 848; // OMNI_KB_LAYOUTS_V1: "Keyboard layout" (OmniBrowser.cpp)\n'
         'static void omniKblSettingsRow(OmniFxPanel& p);\n'
         'static bool omniKblSettingsInput(int b);\n'),
        ('    omniKwSettingsRows(p); // OMNI_KB_WORDS_V1_R2: Word suggestions, Learn words I type, Clear learned words\n',
         '    omniKblSettingsRow(p); // OMNI_KB_LAYOUTS_V1: Keyboard layout\n'
         '    omniKwSettingsRows(p); // OMNI_KB_WORDS_V1_R2: Word suggestions, Learn words I type, Clear learned words\n'),
        ('    if (r.id >= omniKwRowChips && r.id <= omniKwRowClear) return omniKwSettingsInput(r.id, b); // OMNI_KB_WORDS_V1_R2 (before the >= 300 rows)\n',
         '    if (r.id == omniKblRowId) return omniKblSettingsInput(b); // OMNI_KB_LAYOUTS_V1 (before the >= 300 rows)\n'
         '    if (r.id >= omniKwRowChips && r.id <= omniKwRowClear) return omniKwSettingsInput(r.id, b); // OMNI_KB_WORDS_V1_R2 (before the >= 300 rows)\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
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
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    if 'OMNI_KB_WORDS_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_KB_WORDS_V1 missing: apply_kb_words.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniKbLayouts.h', PURE, 'OmniKbWords.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
