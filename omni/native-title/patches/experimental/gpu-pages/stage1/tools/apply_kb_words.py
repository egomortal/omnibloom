#!/usr/bin/env python3
"""OMNI_KB_WORDS_V1 (2026-11-16): word suggestions on Omni's on-screen keyboard, so typing with the controller takes
fewer presses.

What the user sees: while typing a word in a webpage text / search / multi-line field, or search words (not an address)
in the address bar, up to 3 completions of the word at the caret appear as chips in the preview row (the field's text
row, directly above the keys), in place of the field name. The typed case is kept ("Hel" -> "Hello", "HEL" -> "HELLO").
  - D-pad up from the top row of keys moves onto the chips (it wrapped to the action row before; it still goes on up to
    the autofill strip / address suggestions, or wraps to the action row when there is nothing above). On the chips:
    left/right pick, Cross uses the word (the rest of the word + a space is typed at the caret), down goes back to the
    keys. Square, Triangle (space), L1/R1, the triggers and the sticks keep working on the text from the chips.
    No face button is taken: every one already has a keyboard job (Cross type, Square delete, Triangle space, Circle
    close, L3 shift, R3 symbols, touchpad Edit/Sites, Options Go). A pointer click on a chip uses it too.
  - The hint bar says "Use word" for Cross while the chips have the focus.
  - Never for password, e-mail, URL or number fields, dialog fields (Find on page, passwords...), the number pad,
    while selecting, in test modes, or when the address bar holds an address.
Words: a built-in list of ~8000 English words (OmniKbWordsData.h, generated from kb_words_en.txt beside this script by
gen_kb_words.py: a short everyday list written for this project, then the words of this project's own Markdown
prose ranked by count; no third-party list, so no outside licence), plus learned words in /data/omni/kb-words.txt
("omni-kb-words\t1" then "word\tcount\tstamp"; at most 2000, the least used/oldest go first).
Privacy (r2, shared consoles): learning is OPT-IN. Browser settings (after "Search suggestions"):
  - "Word suggestions" On/Off (default On; Off = /data/omni/kb-words-off.flag): no chips, nothing learned.
  - "Learn words I type" Off/On (default Off; On = /data/omni/kb-words-learn.flag). While Off, learned words are neither
    learned nor shown (the built-in list still is); switching it Off writes pending words and drops them from memory.
  - "Clear learned words" (asks once): deletes /data/omni/kb-words.txt and empties memory.
With learning on, a word is learned when a separator (space . , ! ? ; : ) " - newline) ends a word the user was
typing, when Go/Enter ends it, or when a chip is used; never in private tabs or test modes, never from password /
e-mail / URL / number fields (no chips there), and never from login-ish fields: a once-per-field probe reads the
focused element's autocomplete, name, id, type, tag and whether its form (or, outside a form, its document) has a
password field (OmniKbWords::isLoginField: autocomplete username/email/one-time-code/*-password/tel*/cc-*/address-*/
street-address/postal-code; name or id containing user/login/email/account/otp/code/card). Until that probe answers,
or when the field is in a cross-origin frame (the probe cannot see it), nothing is learned. Learned words are written
once the keyboard closes, as one full rewrite on the background writer (omniIoQueue).
Cost: a 64-byte FNV hash of the text before the caret per frame (no allocation); the prefix search (binary search in
the sorted table + a scan of that prefix's range, learned words scanned linearly) runs only when that text changes.
Webpage fields: the chips use the existing mirror probe (omniKbProbe); while a probe is on its way the chips stay as
they were and Cross on them waits (the mirror would be one key behind).

Pure logic: engine/entry/OmniKbWords.h (no SDL/WebKit) + OmniKbWordsData.h (generated), tested by test_kb_words.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_kb_words.cpp -o t && ./t kb_words_en.txt
Anchors in OmniBrowser.cpp (exactly once each, in this order; checked before anything is written; MARK = idempotent):
  1. the '#include "OmniHistoryPlus.h"' line (the includes go after it)
  2. 'static bool omniKbAtTopRow() { return editing && omniKbPage == 0 && omniKb.row == 0; }' (replaced)
  3. 'void submitKeyboard() {' + its OMNI_DIALOGS_V1 first line (learns the word Go ends)
  4. the '// Hold-to-repeat: ...' comment (the shell block goes before it)
  5. omniKbButton's shortcut-page line; 6. omniKbClick's first lines; 7. omniKbHints' 'face(0, "Type")'
  8. the '// OMNI_STYLE_V1 / OMNI_KEYBOARD_V2: on-screen keyboard' heading (the draw goes before it)
  9. omniDrawKeyboard's nameW line and 10. its keysFocused line
  11. 'static void omniKbTick()' + '{' (saves learned words once the keyboard is closed)
  12. '#include "OmniFeatures2.h" // OMNI_FEATURES_V2' (omniKwOtherFocus + the settings rows after it)
Anchors in OmniBrowserSettings.h (none is an anchor of apply_continue_watching / autoplay / https_only):
  'static std::string omniFxHomeEdit;' (declarations before it), the 'omniF3SettingsRows(p);' line (rows after it),
  the 'if (r.id >= 900) return omniF2SettingsInput(r, b);' line (input routing before it).
Upgrade: a tree that already has the first OMNI_KB_WORDS_V1 (no REV marker) gets its shell block (from its heading to
the hold-to-repeat comment) and its omniKwOtherFocus line replaced, the settings added; a fresh tree gets everything.
Apply after apply_history_plus.py (and the rest of the current chain).
usage: apply_kb_words.py <engine tree>   (keeps the file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_KB_WORDS_V1'
REV = 'OMNI_KB_WORDS_V1_R2'   # r2: opt-in learning, login-field exclusion, settings rows, Clear learned words
here = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_KB_WORDS_V1: the pure part of the keyboard's word suggestions (no SDL, no WebKit): the word being typed at the
// caret, prefix search in the built-in list (OmniKbWordsData.h: sorted, front-coded, decoded once), the learned words
// (kb-words.txt: parse / serialize / 2000-word cap / eviction), ranking of both, the case of the typed prefix, the
// "address is search text, not a URL" test and the word a separator just finished. ASCII letters and apostrophes only.
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <string_view>
#include <vector>

namespace OmniKbWords {

constexpr size_t maxLearned = 2000, maxWordLen = 24, maxShown = 3;

inline bool isLetter(unsigned char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
inline bool isWordChar(unsigned char c) { return isLetter(c) || c == '\''; }
inline char lowerChar(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline char upperChar(char c) { return c >= 'a' && c <= 'z' ? char(c - ('a' - 'A')) : c; }

// A learnable / suggestible word: ASCII letters with inner apostrophes, 2..24 long; returned lower case.
inline bool clean(std::string_view raw, std::string& out)
{
    out.clear();
    if (raw.size() < 2 || raw.size() > maxWordLen || raw.front() == '\'' || raw.back() == '\'') return false;
    size_t letters = 0;
    for (size_t i = 0; i < raw.size(); ++i) {
        const unsigned char c = raw[i];
        if (!isWordChar(c)) return false;
        if (c == '\'' && raw[i - 1] == '\'') return false;
        letters += c != '\'';
        out += lowerChar(char(c));
    }
    if (letters < 2) { out.clear(); return false; }
    return true;
}

// The word fragment that ends at the caret: `before` is the text before the caret, `after` the text after it.
// Empty when the caret is not at the end of a word, or the word touches a digit, a non-ASCII character, '_', '@',
// '/', '.', '-' etc. on its left (part of a name, an address or a number) or anything word-like on its right.
inline std::string_view fragment(std::string_view before, std::string_view after)
{
    if (!after.empty()) {
        const unsigned char c = after.front();
        if (isWordChar(c) || (c >= '0' && c <= '9') || c >= 0x80 || c == '_' || c == '@') return {};
    }
    size_t i = before.size();
    while (i && isWordChar(static_cast<unsigned char>(before[i - 1]))) --i;
    while (i < before.size() && before[i] == '\'') ++i;   // a leading quote is punctuation
    if (i == before.size() || before.size() - i > maxWordLen) return {};
    if (i) {
        const unsigned char c = before[i - 1];
        if ((c >= '0' && c <= '9') || c >= 0x80 || c == '_' || c == '@' || c == '/' || c == '.' || c == '-' || c == '\\'
            || c == '#' || c == '&' || c == '=' || c == '%' || c == '+' || c == ':') return {};
    }
    return before.substr(i);
}

// The word a separator just finished: `before` ends with 1..3 separators (space, , . ! ? ; : ) " -) after a word.
inline std::string_view finishedWord(std::string_view before)
{
    size_t i = before.size(), seps = 0;
    while (i && seps < 4) {
        const char c = before[i - 1];
        if (c == ' ' || c == ',' || c == '.' || c == '!' || c == '?' || c == ';' || c == ':' || c == ')' || c == '"'
            || c == '\n' || c == '-') { --i; ++seps; }
        else break;
    }
    if (!seps || seps > 3) return {};
    return fragment(before.substr(0, i), {});
}

// The address bar holds search text (words), not an address: no "://", and with no space no '.', '/', ':' or '@'.
inline bool isSearchText(std::string_view t)
{
    while (!t.empty() && t.front() == ' ') t.remove_prefix(1);
    while (!t.empty() && t.back() == ' ') t.remove_suffix(1);
    if (t.empty() || t.find("://") != std::string_view::npos) return false;
    if (t.find(' ') != std::string_view::npos) return true;
    return t.find_first_of("./:@") == std::string_view::npos;
}

// Login / account fields: words typed there are never learned, even with "Learn words I type" on. A field is one
// when its form (or, for a field outside any form, its document) has a password field; its type is email / tel /
// password / number; an autocomplete token is username, email, one-time-code, current-/new-password, tel*, cc-*,
// address-*, street-address or postal-code; or its name or id contains user, login, email, account, otp, code or card.
inline std::string lowerAll(std::string_view s) { std::string o(s); for (auto& c : o) c = lowerChar(c); return o; }
inline bool isLoginField(std::string_view autocomplete, std::string_view name, std::string_view id, std::string_view type, bool passwordNearby)
{
    if (passwordNearby) return true;
    const std::string t = lowerAll(type);
    if (t == "email" || t == "tel" || t == "password" || t == "number") return true;
    const std::string ac = lowerAll(autocomplete);
    for (size_t i = 0; i < ac.size();) {
        while (i < ac.size() && (ac[i] == ' ' || ac[i] == '\t' || ac[i] == '\n')) ++i;
        size_t j = i;
        while (j < ac.size() && ac[j] != ' ' && ac[j] != '\t' && ac[j] != '\n') ++j;
        const std::string_view tok(ac.data() + i, j - i);
        if (tok == "username" || tok == "email" || tok == "one-time-code" || tok == "current-password" || tok == "new-password"
            || tok == "street-address" || tok == "postal-code" || tok.substr(0, 3) == "tel" || tok.substr(0, 3) == "cc-"
            || tok.substr(0, 8) == "address-") return true;
        i = j;
    }
    static const char* const parts[] = { "user", "login", "email", "account", "otp", "code", "card" };
    for (const std::string& v : { lowerAll(name), lowerAll(id) })
        for (const char* p : parts) if (v.find(p) != std::string::npos) return true;
    return false;
}
// The field probe's answer: "ok" US autocomplete US name US id US type US password-nearby ("1"/"0") US tagName.
// Anything else (no field, a script error) or a frame / plug-in element counts as a login field: nothing is learned.
inline bool fieldProbeSaysLogin(std::string_view s)
{
    if (std::count(s.begin(), s.end(), '\x1f') != 6) return true;
    std::string_view part[7];
    size_t from = 0;
    for (int n = 0; n < 7; ++n) {
        const size_t at = s.find('\x1f', from);
        part[n] = s.substr(from, at == std::string_view::npos ? std::string_view::npos : at - from);
        from = at == std::string_view::npos ? s.size() : at + 1;
    }
    if (part[0] != "ok") return true;
    const std::string tag = lowerAll(part[6]);
    if (tag.empty() || tag == "iframe" || tag == "frame" || tag == "object" || tag == "embed") return true;
    return isLoginField(part[1], part[2], part[3], part[4], part[5] == "1");
}

// `word` (lower case, starts with lower(typed)) shown in the typed prefix's case: the typed letters kept as typed,
// the rest upper case when the prefix is ALL CAPS (2+ letters), else as listed.
inline std::string caseLike(std::string_view word, std::string_view typed)
{
    size_t upper = 0, letters = 0;
    for (char c : typed) if (isLetter(static_cast<unsigned char>(c))) { ++letters; upper += c >= 'A' && c <= 'Z'; }
    const bool allCaps = letters >= 2 && upper == letters;
    std::string out(typed);
    for (size_t i = typed.size(); i < word.size(); ++i) out += allCaps ? upperChar(word[i]) : word[i];
    return out;
}

inline bool startsWithLower(std::string_view word, std::string_view lowerPrefix)
{
    return word.size() >= lowerPrefix.size() && word.compare(0, lowerPrefix.size(), lowerPrefix) == 0;
}

// Built-in list -------------------------------------------------------------------------------------------------
// Data: per word, in alphabetical order: one digit (letters shared with the previous word, 0-9), the rest of the
// word ([a-z']), then its frequency rank as three letters A-Z (base 26, 0 = most frequent).
struct Dict {
    std::string chars;                 // every word, NUL-terminated, alphabetical
    std::vector<uint32_t> offset;      // start of word i in chars
    std::vector<uint16_t> rank;        // 0 = most frequent
    bool decode(const char* data)
    {
        chars.clear(); offset.clear(); rank.clear();
        std::string prev;
        const char* p = data;
        while (*p) {
            if (*p < '0' || *p > '9') return false;
            const size_t shared = size_t(*p++ - '0');
            if (shared > prev.size()) return false;
            std::string w = prev.substr(0, shared);
            while (*p && (*p == '\'' || (*p >= 'a' && *p <= 'z'))) w += *p++;
            int r = 0;
            for (int k = 0; k < 3; ++k) {
                if (*p < 'A' || *p > 'Z') return false;
                r = r * 26 + (*p++ - 'A');
            }
            if (w.empty() || (!prev.empty() && !(prev < w)) || r > 65535) return false;
            offset.push_back(uint32_t(chars.size()));
            chars += w; chars += '\0';
            rank.push_back(uint16_t(r));
            prev = std::move(w);
        }
        return !offset.empty();
    }
    size_t size() const { return offset.size(); }
    std::string_view word(size_t i) const { return std::string_view(chars.data() + offset[i]); }
    size_t lowerBound(std::string_view key) const
    {
        size_t lo = 0, hi = size();
        while (lo < hi) { const size_t mid = (lo + hi) / 2; if (word(mid) < key) lo = mid + 1; else hi = mid; }
        return lo;
    }
    bool contains(std::string_view w) const { const size_t i = lowerBound(w); return i < size() && word(i) == w; }
};

// Encoder for the generator / tests: words in rank order (most frequent first) -> data string.
inline std::string encode(std::vector<std::string> byRank)
{
    std::vector<std::pair<std::string, int>> v;
    for (size_t i = 0; i < byRank.size(); ++i) v.push_back({ byRank[i], int(i) });
    std::sort(v.begin(), v.end());
    std::string out, prev;
    for (auto& [w, r] : v) {
        if (w == prev) continue;
        size_t shared = 0;
        while (shared < 9 && shared < w.size() && shared < prev.size() && w[shared] == prev[shared]) ++shared;
        out += char('0' + shared);
        out += w.substr(shared);
        out += char('A' + r / 676); out += char('A' + r / 26 % 26); out += char('A' + r % 26);
        prev = w;
    }
    return out;
}

// Learned words ---------------------------------------------------------------------------------------------------
struct Learned {
    struct Entry { std::string word; uint32_t count = 0, stamp = 0; };
    std::vector<Entry> words;
    uint32_t clock = 0;                // bumped per learn: recency without a wall clock

    Entry* find(std::string_view w)
    {
        for (auto& e : words) if (e.word == w) return &e;
        return nullptr;
    }
    // The least useful word (fewest uses, then the oldest), never `keep`.
    void evictOne(const Entry* keep)
    {
        size_t worst = words.size();
        for (size_t i = 0; i < words.size(); ++i) {
            if (&words[i] == keep) continue;
            if (worst == words.size() || words[i].count < words[worst].count
                || (words[i].count == words[worst].count && words[i].stamp < words[worst].stamp)) worst = i;
        }
        if (worst < words.size()) words.erase(words.begin() + long(worst));
    }
    // One use of a word (cleaned first; false when it is not a word). Keeps at most maxLearned words.
    bool add(std::string_view raw, uint32_t times = 1)
    {
        std::string w;
        if (!clean(raw, w)) return false;
        ++clock;
        if (Entry* e = find(w)) { e->count = std::min<uint32_t>(e->count + times, 1000000); e->stamp = clock; return true; }
        words.push_back({ std::move(w), std::min<uint32_t>(times, 1000000), clock });
        while (words.size() > maxLearned) {
            const std::string kept = words.back().word;
            evictOne(&words.back());
            if (words.empty() || words.back().word != kept) break;   // defensive: never loop
        }
        return true;
    }
    // kb-words.txt: "omni-kb-words\t1" then "word\tcount\tstamp" lines. Bad lines are skipped, duplicates merged,
    // the cap applied (most used kept).
    void parse(const std::string& text)
    {
        words.clear(); clock = 0;
        size_t from = 0;
        while (from < text.size()) {
            size_t end = text.find('\n', from);
            if (end == std::string::npos) end = text.size();
            std::string_view line(text.data() + from, end - from);
            from = end + 1;
            if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
            const size_t a = line.find('\t');
            if (a == std::string_view::npos) continue;
            const size_t b = line.find('\t', a + 1);
            std::string w;
            if (!clean(line.substr(0, a), w)) continue;
            const std::string countText(line.substr(a + 1, b == std::string_view::npos ? std::string_view::npos : b - a - 1));
            const long c = strtol(countText.c_str(), nullptr, 10);
            const long s = b == std::string_view::npos ? 0 : strtol(std::string(line.substr(b + 1)).c_str(), nullptr, 10);
            if (c <= 0) continue;
            const uint32_t count = uint32_t(std::min(c, 1000000L)), stamp = uint32_t(std::clamp(s, 0L, 2000000000L));
            if (Entry* e = find(w)) { e->count = std::min<uint32_t>(e->count + count, 1000000); e->stamp = std::max(e->stamp, stamp); }
            else words.push_back({ std::move(w), count, stamp });
            clock = std::max(clock, stamp);
        }
        if (words.size() > maxLearned) {
            std::stable_sort(words.begin(), words.end(), [](const Entry& x, const Entry& y) {
                return x.count != y.count ? x.count > y.count : x.stamp > y.stamp; });
            words.resize(maxLearned);
        }
    }
    std::string serialize() const
    {
        std::string out = "omni-kb-words\t1\n";
        for (auto& e : words) out += e.word + "\t" + std::to_string(e.count) + "\t" + std::to_string(e.stamp) + "\n";
        return out;
    }
};

// Ranking ---------------------------------------------------------------------------------------------------------
// Built-in words score 100 (most frequent) down to 1; learned words 45 + 25 per use (max 10 uses) + 10 when used in
// the last 50 learns, and a word in both gets the larger score + 5. So a word you typed twice beats every built-in
// word, one typed once only the less common four fifths of them (a one-off typo stays low). Ties: shorter, then
// alphabetical.
struct Pick { std::string word; int score = 0; };
inline bool better(const Pick& a, const Pick& b)
{
    if (a.score != b.score) return a.score > b.score;
    if (a.word.size() != b.word.size()) return a.word.size() < b.word.size();
    return a.word < b.word;
}
inline int builtinScore(const Dict& d, size_t i) { return d.size() ? 100 - int(99 * size_t(d.rank[i]) / d.size()) : 0; }
inline int learnedScore(const Learned& l, const Learned::Entry& e)
{
    return 45 + 25 * int(std::min<uint32_t>(e.count, 10)) + (l.clock - e.stamp < 50 ? 10 : 0);
}
// Up to maxShown completions of `typed` (the fragment as typed), in the typed case. The typed word itself is never
// offered (nothing to complete).
inline std::vector<std::string> suggest(const Dict* dict, const Learned* learned, std::string_view typed, size_t limit = maxShown)
{
    std::vector<std::string> out;
    if (typed.empty() || typed.size() > maxWordLen) return out;
    std::string key;
    for (char c : typed) key += lowerChar(c);
    std::vector<Pick> mine;                       // learned matches (few)
    if (learned)
        for (auto& e : learned->words)
            if (e.word.size() > key.size() && startsWithLower(e.word, key)) mine.push_back({ e.word, learnedScore(*learned, e) });
    std::sort(mine.begin(), mine.end(), [](const Pick& a, const Pick& b) { return a.word < b.word; });   // binary search
    std::vector<Pick> top;                        // best built-in words not learned, kept sorted, at most `limit`
    if (dict && dict->size()) {
        for (size_t i = dict->lowerBound(key); i < dict->size(); ++i) {
            const std::string_view w = dict->word(i);
            if (!startsWithLower(w, key)) break;
            if (w.size() == key.size()) continue;
            const int s = builtinScore(*dict, i);
            auto it = std::lower_bound(mine.begin(), mine.end(), w, [](const Pick& p, std::string_view v) { return p.word < v; });
            if (it != mine.end() && it->word == w) { it->score = std::max(it->score, s) + 5; continue; }
            if (top.size() == limit && s < top.back().score) continue;
            Pick p { std::string(w), s };
            top.insert(std::upper_bound(top.begin(), top.end(), p, better), std::move(p));
            if (top.size() > limit) top.pop_back();
        }
    }
    for (auto& p : top) mine.push_back(std::move(p));
    std::sort(mine.begin(), mine.end(), better);
    for (size_t i = 0; i < mine.size() && out.size() < limit; ++i) out.push_back(caseLike(mine[i].word, typed));
    return out;
}

// What to insert to accept `shown` (a suggestion for `typed`): the rest of the word, plus a space unless the text
// after the caret already starts with white space or punctuation that follows a word.
inline std::string completion(std::string_view shown, std::string_view typed, std::string_view after)
{
    if (shown.size() <= typed.size()) return {};
    std::string out(shown.substr(typed.size()));
    const bool spaced = !after.empty() && (after.front() == ' ' || after.front() == '\n' || after.front() == ','
        || after.front() == '.' || after.front() == '!' || after.front() == '?' || after.front() == ';' || after.front() == ':'
        || after.front() == ')');
    if (!spaced) out += ' ';
    return out;
}

} // namespace OmniKbWords
'''

INCLUDE_AT = '#include "OmniHistoryPlus.h"'
INCLUDE = ('#include "OmniKbWords.h" // OMNI_KB_WORDS_V1: keyboard word suggestions, learned words (pure)\n'
           '#include "OmniKbWordsData.h" // OMNI_KB_WORDS_V1: the built-in word list (generated)\n')

TOPROW_OLD = 'static bool omniKbAtTopRow() { return editing && omniKbPage == 0 && omniKb.row == 0; }\n'
TOPROW_NEW = r'''static bool omniKwFocused();   // OMNI_KB_WORDS_V1: the word chips have the focus
static bool omniKwAny();       // OMNI_KB_WORDS_V1: word chips are shown (brings them up to date)
static void omniKwSubmit();    // OMNI_KB_WORDS_V1: Go/Enter ends the word being typed
// OMNI_KB_WORDS_V1: "at the top" (the strips above may take D-pad up) is the word chips, or the top row of keys when
// there are no chips (up from the top row first moves onto the chips).
static bool omniKbAtTopRow()
{
    if (!editing || omniKbPage != 0) return false;
    const bool any = omniKwAny();
    return omniKwFocused() || (omniKb.row == 0 && !any);
}
'''

SUBMIT_OLD = ('void submitKeyboard() {\n'
              '    if (omniKbTarget) { omniKbTargetDone(true); return; } // OMNI_DIALOGS_V1\n')
SUBMIT_NEW = ('void submitKeyboard() {\n'
              '    omniKwSubmit(); // OMNI_KB_WORDS_V1: learns the word Go / Enter ends (not in dialogs, passwords, private tabs)\n'
              '    if (omniKbTarget) { omniKbTargetDone(true); return; } // OMNI_DIALOGS_V1\n')

BLOCK_AT = '// Hold-to-repeat: the button pressed last repeats while it is held (driven by omniKbTick()).\n'
BLOCK = r'''// OMNI_KB_WORDS_V1 ---------------------------------------------------------------------------------------------
// Word suggestions: up to 3 completions of the word at the caret (OmniKbWords.h), shown as chips in the preview row.
// D-pad up from the top row of keys moves onto them; left/right pick; Cross uses one; down goes back to the keys; up
// goes on to the strips above (autofill, address suggestions) or wraps to the action row. Recomputed only when the
// text before the caret changes (a hash per frame, no allocation). Learned words: /data/omni/kb-words.txt.
// OMNI_KB_WORDS_V1_R2: learning is opt-in (kb-words-learn.flag), the chips can be turned off (kb-words-off.flag), and
// login-ish fields (OmniKbWords::isLoginField, read by a once-per-field probe) never teach words.
static std::string omniData(const char* name);
static void omniIoQueue(const std::string& path, std::string data, bool append);
static bool omniKwOtherFocus();   // the address suggestions or the autofill strip have the focus (after OmniFeatures2.h)
static int omniKwLearnFlag = -1, omniKwOffFlag = -1;   // -1: not read yet (read once, then kept by the settings rows)
static bool omniKwLearnOn() { if (omniKwLearnFlag < 0) omniKwLearnFlag = access(omniData("kb-words-learn.flag").c_str(), F_OK) == 0 ? 1 : 0; return omniKwLearnFlag == 1; }
static bool omniKwChipsOn() { if (omniKwOffFlag < 0) omniKwOffFlag = access(omniData("kb-words-off.flag").c_str(), F_OK) == 0 ? 1 : 0; return omniKwOffFlag != 1; }
struct OmniKwState {
    OmniKbWords::Dict dict;
    OmniKbWords::Learned learned;
    bool dictReady = false, learnedLoaded = false, dirty = false;
    int fieldAsked = -1, fieldSession = -1;   // the webpage-field probe: asked for / answered for this omniKb.session
    bool fieldSafe = false;                   // the answered field is not a login field (words may be learned there)
    bool hashValid = false;
    uint64_t hash = 0;
    uint32_t gen = 0;                 // bumped when the learned words change
    int session = -1;                 // omniKb.session the state belongs to
    std::string typed, after;         // the fragment the chips complete (as typed) and the text right after the caret
    std::string lastTyped;            // the fragment before the last change: a separator after it learns the word
    std::vector<std::string> items;   // the chips (typed case)
    int focus = -1;
    int chipX[3] = {}, chipW[3] = {}, chipY = 0, chipH = 0;   // layout coordinates of the drawn chips (clicks)
};
static OmniKwState omniKw;
static void omniKwLoadLearned()
{
    if (omniKw.learnedLoaded) return;
    omniKw.learnedLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData("kb-words.txt").c_str(), "rb")) {
        char buffer[8192];
        size_t n;
        while ((n = fread(buffer, 1, sizeof(buffer), f)) > 0 && text.size() < 512 * 1024) text.append(buffer, n);
        fclose(f);
    }
    omniKw.learned.parse(text);
}
static void omniKwLoad()
{
    if (!omniKw.dictReady) {
        omniKw.dictReady = true;
        if (!omniKw.dict.decode(OmniKbWords::builtinData)) { omniKw.dict = OmniKbWords::Dict(); fprintf(stderr, "OMNI_KB_WORDS_V1: built-in word list did not decode\n"); }
    }
    if (omniKwLearnOn()) omniKwLoadLearned();   // learned words are read (and shown) only while learning is on
}
static void omniKwLearn(std::string_view word)
{
    if (!omniKwLearnOn()) return;
    omniKwLoad();
    if (omniKw.learned.add(word)) { omniKw.dirty = true; ++omniKw.gen; }
}
// Once per webpage field (keyboard session): is it a login / account field? Until the answer, nothing is learned.
static const char* const omniKwFieldScript = R"JS((function(){try{var d=document,e=d.activeElement,n=0,S=String.fromCharCode(31);
while(e&&e.tagName==='IFRAME'&&n<4){try{var cd=e.contentDocument;if(!cd)break;d=cd;e=d.activeElement;n++;}catch(x){break;}}
if(!e)return 'none';
var g=function(a){return String((e.getAttribute&&e.getAttribute(a))||'').split(S).join(' ');};
var f=e.form||(e.closest?e.closest('form'):null),pw=(f||d).querySelector('input[type=password]')?'1':'0';
return ['ok',g('autocomplete'),g('name'),g('id'),String(e.type||''),pw,String(e.tagName||'')].join(S);
}catch(x){return 'none';}})())JS";
static void omniKwFieldProbe()
{
    if (!omniKwLearnOn() || omniKb.kind != 1 || !active() || omniKw.fieldAsked == omniKb.session) return;
    omniKw.fieldAsked = omniKb.session;
    auto script = adoptWK(WKStringCreateWithUTF8CString(omniKwFieldScript));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), reinterpret_cast<void*>(intptr_t(omniKb.session)), [](WKTypeRef result, WKErrorRef error, void* context) {
        const std::string value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : "none";
        if (intptr_t(context) != omniKb.session) return;   // the keyboard moved on to another field
        omniKw.fieldSession = int(intptr_t(context));
        omniKw.fieldSafe = !OmniKbWords::fieldProbeSaysLogin(value);
    });
}
// The text around the caret, or false when this field gets no chips. `learn`: words typed here may be learned.
static bool omniKwContext(std::string_view& before, std::string_view& after, bool& learn)
{
    if (!editing || omniKbPage != 0 || omniKb.select || omniKb.layer == omniKbNumpad || omniTestMode() || !omniKwChipsOn()) return false;
    learn = omniKwLearnOn() && !(active() && active()->omniPrivate)   // OMNI_KB_WORDS_V1_R2: opt-in, never private tabs
        && (omniKb.kind == 0 || (omniKw.fieldSession == omniKb.session && omniKw.fieldSafe));   // nor login fields
    if (omniKb.kind == 0) {
        omniKbClamp();
        if (omniKb.caret != omniKb.anchor || !OmniKbWords::isSearchText(address)) return false;
        before = std::string_view(address).substr(0, omniKb.caret);
        after = std::string_view(address).substr(omniKb.caret);
        return true;
    }
    if (omniKb.kind != 1 || !omniKb.mirrorValid || omniKb.mirrorNoSel || omniKb.probing || omniKb.probeAgain || !omniKb.selected.empty()) return false;
    if (omniKb.field != omniKbFieldText && omniKb.field != omniKbFieldSearch && omniKb.field != omniKbFieldMulti) return false;
    before = omniKb.before;
    after = omniKb.after;
    return true;
}
static uint64_t omniKwHash(std::string_view before, std::string_view after)
{
    uint64_t h = 1469598103934665603ull;
    auto mix = [&h](uint64_t v) { h ^= v; h *= 1099511628211ull; };
    mix(uint64_t(omniKb.kind + 2)); mix(uint64_t(omniKb.field)); mix(uint64_t(uint32_t(omniKb.session))); mix(omniKw.gen); mix(omniKwLearnOn());
    for (size_t i = before.size() > 64 ? before.size() - 64 : 0; i < before.size(); ++i) mix(static_cast<unsigned char>(before[i]));
    mix(0x1ff);
    mix(after.empty() ? 0x100 : static_cast<unsigned char>(after[0]));
    return h;
}
static void omniKwClear()
{
    if (!omniKw.items.empty()) omniShellDirty = true;
    omniKw.items.clear();
    omniKw.focus = -1;
    for (int& w : omniKw.chipW) w = 0;
}
static void omniKwRefresh()
{
    if (omniKw.session != omniKb.session) { omniKw.session = omniKb.session; omniKw.lastTyped.clear(); omniKw.hashValid = false; omniKwClear(); }
    std::string_view before, after;
    bool learn = false;
    if (!omniKwContext(before, after, learn)) {
        // A webpage probe on its way: keep the chips (Cross on them waits) instead of blinking them off per key.
        if (editing && omniKb.kind == 1 && omniKb.mirrorValid && (omniKb.probing || omniKb.probeAgain)) return;
        omniKwClear();
        omniKw.hashValid = false;
        omniKw.lastTyped.clear();
        return;
    }
    if (omniKb.kind == 1) omniKwFieldProbe();   // once per field, only while learning is on
    const uint64_t h = omniKwHash(before, after);
    if (omniKw.hashValid && h == omniKw.hash) return;
    omniKw.hash = h;
    omniKw.hashValid = true;
    omniKwLoad();
    const std::string_view typed = OmniKbWords::fragment(before, after);
    if (learn && typed.empty() && !omniKw.lastTyped.empty()) {   // a separator just ended the word being typed
        const std::string_view done = OmniKbWords::finishedWord(before);
        std::string a, b;
        if (OmniKbWords::clean(done, a) && OmniKbWords::clean(omniKw.lastTyped, b) && OmniKbWords::startsWithLower(a, b)) {
            omniKwLearn(done);
            omniKw.hash = omniKwHash(before, after);   // the learn bumped gen: this text is still current
        }
    }
    omniKw.lastTyped.assign(typed);
    omniKw.typed.assign(typed);
    omniKw.after.assign(after.substr(0, 1));
    const int focus = omniKw.focus;
    omniKwClear();
    if (!typed.empty()) omniKw.items = OmniKbWords::suggest(&omniKw.dict, omniKwLearnOn() ? &omniKw.learned : nullptr, typed);
    omniKw.focus = omniKw.items.empty() ? -1 : std::min(focus, int(omniKw.items.size()) - 1);
    omniShellDirty = true;
}
static bool omniKwAny() { omniKwRefresh(); return !omniKw.items.empty(); }
static bool omniKwFocused() { return omniKw.focus >= 0 && !omniKw.items.empty(); }
static void omniKwUse(int i)
{
    omniKbEnsure();
    omniKwRefresh();
    if (i < 0 || i >= int(omniKw.items.size())) return;
    std::string_view before, after;
    bool learn = false;
    if (!omniKwContext(before, after, learn)) return;   // a webpage probe on its way: wait for the text to settle
    const std::string word = omniKw.items[size_t(i)];
    const std::string add = OmniKbWords::completion(word, omniKw.typed, omniKw.after);
    if (learn) omniKwLearn(word);
    omniKwClear();
    omniKw.lastTyped.clear();   // the word is counted once (not again when the space lands)
    if (!add.empty()) append(add);
    if (omniKb.caps == 1) { omniKb.caps = 0; shift = false; }   // one-shot shift is used up by the word
}
static void omniKwSubmit()
{
    omniKbEnsure();
    std::string_view before, after;
    bool learn = false;
    if (!omniKwContext(before, after, learn) || !learn) return;
    const std::string_view typed = OmniKbWords::fragment(before, after);
    if (!typed.empty()) omniKwLearn(typed);
    omniKw.lastTyped.clear();
}
// Controller buttons while the keyboard (letters page) is open: true when the chips used the button.
static bool omniKwButton(int b)
{
    omniKwRefresh();
    const int n = int(omniKw.items.size());
    if (omniKw.focus < 0) {
        if (b == SDL_CONTROLLER_BUTTON_DPAD_UP && n > 0 && omniKb.row == 0) { omniKw.focus = 0; return true; }
        return false;
    }
    if (n == 0) { omniKw.focus = -1; return false; }
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniKw.focus = (omniKw.focus + n - 1) % n; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniKw.focus = (omniKw.focus + 1) % n; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniKw.focus = -1; return true;                          // back to the top row
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniKw.focus = -1; omniKbFocus(0, -1); return true;        // nothing above took it: wrap
    case SDL_CONTROLLER_BUTTON_A: omniKwUse(omniKw.focus); return true;
    default: return false;   // Square, Triangle, L1/R1, L3/R3, touchpad, Options still act on the text
    }
}
static bool omniKwClick(int x, int y)
{
    omniKwRefresh();
    for (int i = 0; i < int(omniKw.items.size()) && i < 3; ++i)
        if (omniKw.chipW[i] > 0 && x >= omniKw.chipX[i] && x < omniKw.chipX[i] + omniKw.chipW[i] && y >= omniKw.chipY && y < omniKw.chipY + omniKw.chipH) {
            omniKwUse(i);
            return true;
        }
    return false;
}
// Saves the learned words once the keyboard has closed (one full rewrite on the background writer).
static void omniKwTick()
{
    if (!omniKw.dirty || editing) return;
    omniKw.dirty = false;
    omniIoQueue(omniData("kb-words.txt"), omniKw.learned.serialize(), false);
}
'''

KBBUTTON_OLD = '    if (omniKb.kind == 0 && omniKbPage == 1) { omniKbShortcutButton(b); return; }\n'
KBBUTTON_NEW = KBBUTTON_OLD + '    if (omniKwButton(b)) return; // OMNI_KB_WORDS_V1: the word chips (D-pad up from the top row)\n'

KBCLICK_OLD = 'static void omniKbClick(int x, int y)\n{\n    omniKbEnsure();\n'
KBCLICK_NEW = KBCLICK_OLD + '    if (omniKwClick(x, y)) return; // OMNI_KB_WORDS_V1: a word chip in the preview row\n'

HINTS_OLD = '    face(0, "Type"); face(2, "Delete");'
HINTS_NEW = '    face(0, omniKwFocused() ? "Use word" : "Type"); face(2, "Delete"); /* OMNI_KB_WORDS_V1 */'  # block comment: the line goes on (review fix)

DRAW_AT = '// OMNI_STYLE_V1 / OMNI_KEYBOARD_V2: on-screen keyboard ---'
DRAW = r'''// OMNI_KB_WORDS_V1: the word chips, right-aligned in the preview row (fy..fy+fh); returns the width they take (0: none).
static int omniKwDraw(int fy, int fh)
{
    omniKwRefresh();
    for (int& w : omniKw.chipW) w = 0;
    const int n = std::min<int>(3, int(omniKw.items.size()));
    if (n == 0) return 0;
    const OmniTheme& T = omniTheme();
    const bool focused = omniKw.focus >= 0 && !omniKwOtherFocus();
    int w[3] = {}, total = 0;
    for (int i = 0; i < n; ++i) w[i] = std::min(200, int(omniTextWidthPx(omniSmall, omniKw.items[size_t(i)].c_str()) / displayScale + 0.5) + 28);
    for (int i = 0; i < n; ++i) total += w[i] + 6;
    if (total > 470) { total = 0; for (int i = 0; i < n; ++i) { w[i] = std::min(w[i], 150); total += w[i] + 6; } }
    int x = keyboardX + keyboardWidth - total;
    omniKw.chipY = fy + 5;
    omniKw.chipH = fh - 10;
    if (!focused) omniLabel("\xe2\x96\xb2", float(x - 6), fy + fh / 2.f, omniCaption, T.inkFaint, 2);   // "up" hint
    for (int i = 0; i < n; ++i) {
        const bool sel = focused && omniKw.focus == i;
        fillRounded(x, omniKw.chipY, w[i], omniKw.chipH, omniRadius, sel ? T.accent : T.key);
        omniLabel(omniKw.items[size_t(i)], x + w[i] / 2.f, fy + fh / 2.f, omniSmall, sel ? T.accentInk : T.ink, 1, w[i] - 12);
        omniKw.chipX[i] = x;
        omniKw.chipW[i] = w[i];
        x += w[i] + 6;
    }
    return total + 20;
}
'''

NAMEW_OLD = '    const int nameW = omniLabel(name, float(keyboardX + keyboardWidth - 14), fcy, omniSmall, T.inkDim, 2, 300);\n'
NAMEW_NEW = ('    int nameW = omniKwDraw(fy, fh); // OMNI_KB_WORDS_V1: word suggestions in place of the field name\n'
             '    if (!nameW) nameW = omniLabel(name, float(keyboardX + keyboardWidth - 14), fcy, omniSmall, T.inkDim, 2, 300);\n')

KEYSF_OLD = '    const bool keysFocused = omniSuggestSelected() < 0;   // the address suggestions may have the focus\n'
KEYSF_NEW = ('    const bool keysFocused = omniSuggestSelected() < 0 && !omniKwFocused();   // the address suggestions or the word '
             'chips (OMNI_KB_WORDS_V1) may have the focus\n')

F2_AT = '#include "OmniFeatures2.h" // OMNI_FEATURES_V2\n'
F2 = ('static bool omniKwOtherFocus() { return omniSuggestSelected() >= 0 || omniF2FillSel >= 0; } '
      '// OMNI_KB_WORDS_V1: a strip above the keyboard has the focus\n')
F2_SETTINGS = r'''// OMNI_KB_WORDS_V1_R2: Browser settings rows (after "Search suggestions"; ids in OmniBrowserSettings.h).
static void omniKwSetFlag(const char* name, bool present)
{
    const std::string path = omniData(name);
    if (!present) unlink(path.c_str());
    else if (FILE* f = fopen(path.c_str(), "w")) { fputs("1\n", f); fclose(f); }
}
static void omniKwSettingsRows(OmniFxPanel& p)
{
    auto add = [&](int id, const char* label, std::string value, bool stepper) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = stepper; p.rows.push_back(r); };
    add(omniKwRowChips, "Word suggestions", omniKwChipsOn() ? "On" : "Off", true);
    add(omniKwRowLearn, "Learn words I type", omniKwLearnOn() ? "On" : "Off", true);
    add(omniKwRowClear, "Clear learned words", "", false);
}
static bool omniKwSettingsInput(int id, int b)
{
    const bool step = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT || b == SDL_CONTROLLER_BUTTON_A;
    if (id == omniKwRowChips) {
        if (!step) return false;
        omniKwOffFlag = omniKwChipsOn() ? 1 : 0;
        omniKwSetFlag("kb-words-off.flag", omniKwOffFlag == 1);
        omniKwClear();
        omniKw.hashValid = false;
        omniFxRefresh();
        return true;
    }
    if (id == omniKwRowLearn) {
        if (!step) return false;
        const bool on = !omniKwLearnOn();
        if (!on) {   // write what was learned so far, then forget it here (Clear learned words deletes the file)
            if (omniKw.dirty) omniIoQueue(omniData("kb-words.txt"), omniKw.learned.serialize(), false);
            omniKw.dirty = false;
            omniKw.learned = OmniKbWords::Learned();
            omniKw.learnedLoaded = false;
        }
        omniKwLearnFlag = on ? 1 : 0;
        omniKwSetFlag("kb-words-learn.flag", on);
        ++omniKw.gen;
        omniKw.hashValid = false;
        notice(on ? "Omni will learn words you type (never passwords, logins or private tabs)" : "Omni no longer learns words. Clear learned words deletes the saved ones");
        omniFxRefresh();
        return true;
    }
    if (id == omniKwRowClear) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        omniAsk("Clear learned words?", "The words Omni learned from your typing will be deleted from this console.", "Clear", [](bool ok) {
            if (!ok) return;
            omniKw.learned = OmniKbWords::Learned();
            omniKw.learnedLoaded = true;   // empty; the file is gone
            omniKw.dirty = false;
            ++omniKw.gen;
            omniKw.hashValid = false;
            const std::string path = omniData("kb-words.txt");
            omniIoQueue(path, "", false);   // drops any queued write of the file ...
            omniIoFlush();                  // ... and waits (at most 0.8 s) for the writer
            unlink(path.c_str());
            unlink((path + ".tmp").c_str());
            notice("Learned words cleared");
        });
        return true;
    }
    return false;
}
'''
F2_NEW = F2 + F2_SETTINGS

SET_DECL_AT = 'static std::string omniFxHomeEdit;\n'
SET_DECL = ('constexpr int omniKwRowChips = 845, omniKwRowLearn = 846, omniKwRowClear = 847; // OMNI_KB_WORDS_V1_R2 (OmniBrowser.cpp)\n'
            'static void omniKwSettingsRows(OmniFxPanel& p);\n'
            'static bool omniKwSettingsInput(int id, int b);\n')
SET_ROWS_AT = '    omniF3SettingsRows(p); // OMNI_FEATURES_V3: dark pages, suggestions, tab limit, tabs kept loaded, tab memory\n'
SET_ROWS = '    omniKwSettingsRows(p); // OMNI_KB_WORDS_V1_R2: Word suggestions, Learn words I type, Clear learned words\n'
SET_INPUT_AT = '    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n'
SET_INPUT = ('    if (r.id >= omniKwRowChips && r.id <= omniKwRowClear) return omniKwSettingsInput(r.id, b); '
             '// OMNI_KB_WORDS_V1_R2 (before the >= 300 rows)\n')
OLD_BLOCK_START = '// OMNI_KB_WORDS_V1 ---------------------------------------------------------------------------------------------\n'

TICK_OLD = 'static void omniKbTick()\n{\n'
TICK_NEW = TICK_OLD + '    omniKwTick(); // OMNI_KB_WORDS_V1: saves learned words once the keyboard is closed\n'


def unique(s, what, name):
    n = s.count(what)
    if n != 1:
        sys.exit('OmniBrowser.cpp: %s found %d times: %r' % (name, n, what[:90]))
    return s.index(what)


def data_header(nl):
    words = []
    for line in (here / 'kb_words_en.txt').read_text(encoding='ascii').splitlines():
        w = line.strip()
        if w:
            if not all(c == "'" or 'a' <= c <= 'z' for c in w) or len(w) > 24:
                sys.exit('kb_words_en.txt: bad word %r' % w)
            words.append(w)
    if not 1000 <= len(words) <= 17576:
        sys.exit('kb_words_en.txt: %d words' % len(words))
    order = sorted((w, r) for r, w in enumerate(words))
    out, prev = [], None
    for w, r in order:
        if w == prev:
            continue
        p = prev or ''
        shared = 0
        while shared < 9 and shared < len(w) and shared < len(p) and w[shared] == p[shared]:
            shared += 1
        out.append('%d%s%s%s%s' % (shared, w[shared:], chr(65 + r // 676), chr(65 + r // 26 % 26), chr(65 + r % 26)))
        prev = w
    data = ''.join(out)
    lines = ['// OMNI_KB_WORDS_V1: the built-in word list, generated by apply_kb_words.py from kb_words_en.txt (%d words; see'
             % len(out),
             "// gen_kb_words.py: an everyday list written for this project + counts over the project's own prose; no",
             '// third-party list). Per word, alphabetical: shared-prefix digit, the rest of the word, rank as 3 letters A-Z.',
             '// Do not edit: re-run the generator / apply script.',
             '#pragma once',
             'namespace OmniKbWords {',
             'inline const char* const builtinData =']
    for i in range(0, len(data), 110):
        lines.append('    "%s"' % data[i:i + 110])
    lines[-1] += ';'
    lines += ['} // namespace OmniKbWords', '']
    return nl.join(lines).encode('ascii')


def write_if(path, data, msgs):
    if path.exists() and path.read_bytes() == data:
        msgs.append('%s: already' % path.name)
    else:
        path.write_bytes(data)
        msgs.append('%s: written' % path.name)


def read(path):
    raw = path.read_bytes()
    s = raw.decode('utf-8')
    crlf = raw.count(b'\r\n') * 2 > raw.count(b'\n')
    return (s.replace('\r\n', '\n') if crlf else s), crlf


def settings_text(t):
    """OmniBrowserSettings.h with the r2 rows (None: already there)."""
    if REV in t:
        return None
    at = [unique(t, SET_DECL_AT, 'OmniBrowserSettings.h omniFxHomeEdit'), unique(t, SET_ROWS_AT, 'OmniBrowserSettings.h omniF3SettingsRows'),
          unique(t, SET_INPUT_AT, 'OmniBrowserSettings.h >= 900 input line')]
    if at != sorted(at):
        sys.exit('OmniBrowserSettings.h: anchors out of order: %r' % at)
    t = t.replace(SET_DECL_AT, SET_DECL + SET_DECL_AT, 1)
    t = t.replace(SET_ROWS_AT, SET_ROWS_AT + SET_ROWS, 1)
    return t.replace(SET_INPUT_AT, SET_INPUT + SET_INPUT_AT, 1)


def browser_text(t):
    """OmniBrowser.cpp with OMNI_KB_WORDS_V1 r2: (text, 'applied' / 'upgraded'), or (None, 'already')."""
    if REV in t:
        return None, 'already'
    if MARK in t:   # the first OMNI_KB_WORDS_V1: new shell block, new omniKwOtherFocus line + settings
        a = unique(t, OLD_BLOCK_START, 'old OMNI_KB_WORDS_V1 block heading')
        b = unique(t, BLOCK_AT, 'hold-to-repeat comment')
        unique(t, F2_AT + F2, 'old omniKwOtherFocus line')
        if not a < b:
            sys.exit('OmniBrowser.cpp: old OMNI_KB_WORDS_V1 block not before the hold-to-repeat comment')
        t = t[:a] + BLOCK + t[b:]
        return t.replace(F2_AT + F2, F2_AT + F2_NEW, 1), 'upgraded'
    if True:
        if 'OMNI_KEYBOARD_V2' not in t or 'OMNI_HISTORY_PLUS_V1' not in t:
            sys.exit('OmniBrowser.cpp: needs the OMNI_KEYBOARD_V2 tree with apply_history_plus.py applied')
        # every anchor is checked before anything is written
        i = unique(t, INCLUDE_AT, 'include anchor')
        if t.rfind('\n', 0, i) + 1 != i:
            sys.exit('OmniBrowser.cpp: include anchor not at a line start')
        inc_end = t.index('\n', i) + 1
        at = [inc_end, unique(t, TOPROW_OLD, 'omniKbAtTopRow'), unique(t, SUBMIT_OLD, 'submitKeyboard'),
              unique(t, BLOCK_AT, 'hold-to-repeat comment'), unique(t, KBBUTTON_OLD, 'omniKbButton shortcut line'),
              unique(t, KBCLICK_OLD, 'omniKbClick'), unique(t, HINTS_OLD, 'omniKbHints Type'),
              unique(t, DRAW_AT, 'keyboard draw heading'), unique(t, NAMEW_OLD, 'omniDrawKeyboard nameW'),
              unique(t, KEYSF_OLD, 'omniDrawKeyboard keysFocused'), unique(t, TICK_OLD, 'omniKbTick'),
              unique(t, F2_AT, 'OmniFeatures2 include')]
        if at != sorted(at):
            sys.exit('OmniBrowser.cpp: anchors out of order: %r' % at)
        t = t[:inc_end] + INCLUDE + t[inc_end:]
        t = t.replace(TOPROW_OLD, TOPROW_NEW, 1).replace(SUBMIT_OLD, SUBMIT_NEW, 1)
        t = t.replace(BLOCK_AT, BLOCK + BLOCK_AT, 1).replace(KBBUTTON_OLD, KBBUTTON_NEW, 1)
        t = t.replace(KBCLICK_OLD, KBCLICK_NEW, 1).replace(HINTS_OLD, HINTS_NEW, 1)
        t = t.replace(DRAW_AT, DRAW + DRAW_AT, 1).replace(NAMEW_OLD, NAMEW_NEW, 1).replace(KEYSF_OLD, KEYSF_NEW, 1)
        t = t.replace(F2_AT, F2_AT + F2_NEW, 1).replace(TICK_OLD, TICK_NEW, 1)
        return t, 'applied'


def main():
    msgs = []
    pb, ps = root / 'OmniBrowser.cpp', root / 'OmniBrowserSettings.h'
    tb, crlf_b = read(pb)
    ts, crlf_s = read(ps)
    new_b, how = browser_text(tb)      # every anchor in both files is checked before anything is written
    new_s = settings_text(ts)
    if new_b is not None:
        pb.write_bytes((new_b.replace('\n', '\r\n') if crlf_b else new_b).encode('utf-8'))
    msgs.append('OmniBrowser.cpp: ' + how)
    if new_s is not None:
        ps.write_bytes((new_s.replace('\n', '\r\n') if crlf_s else new_s).encode('utf-8'))
    msgs.append('OmniBrowserSettings.h: ' + ('already' if new_s is None else 'applied'))
    like = (root / 'OmniSearchTiles.h').read_bytes()
    nl = '\r\n' if like.count(b'\r\n') * 2 > like.count(b'\n') else '\n'
    write_if(root / 'OmniKbWords.h', PURE.replace('\n', nl).encode('utf-8'), msgs)
    write_if(root / 'OmniKbWordsData.h', data_header(nl), msgs)
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
