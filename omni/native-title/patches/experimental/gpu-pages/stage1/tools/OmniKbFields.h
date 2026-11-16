// OMNI_KB_FIELDS_V1: the pure part of the field-aware keyboard (no SDL, no WebKit): which number pad a webpage field
// gets (from the mirror probe's element kind, type, inputmode and autocomplete) and the pad's key tables.
// Shell side and reasons: tools/apply_kb_fields.py. Tested on the host with g++ (tools/test_kb_fields.cpp).
// URL and e-mail fields need nothing here: OMNI_KEYBOARD_V2's quick row already has https:// www. .com .org .net
// (URL) and @ .com .net @gmail.com @outlook.com (e-mail), and OMNI_KB_LAYOUTS_V1's letter-row tails have . / ? and . _ @.
#pragma once
#include <string_view>
#include <vector>

namespace OmniKbFields {

// The pad a field gets. kNone: not a number field (letters, symbols, the old number layer are unchanged).
enum Pad : int { kNone = 0, kDigits, kDecimal, kTel, kCode, kPadCount };

// What a key does; the shell maps these to its own key actions (omniKbBackKey, omniKbGoKey ...).
enum Kind : int { kInsert = 0, kDelete, kDone, kPaste, kClips, kLayer, kTools, kSpace, kClose };
struct Key { const char* label; int kind; float units; };   // units: of the 10-unit keyboard width

// One space-separated token list contains `word` (autocomplete="one-time-code", "section-x one-time-code" ...).
inline bool hasToken(std::string_view list, std::string_view word)
{
    size_t i = 0;
    while (i < list.size()) {
        while (i < list.size() && (list[i] == ' ' || list[i] == '\t' || list[i] == '\n' || list[i] == '\r' || list[i] == '\f')) ++i;
        size_t j = i;
        while (j < list.size() && !(list[j] == ' ' || list[j] == '\t' || list[j] == '\n' || list[j] == '\r' || list[j] == '\f')) ++j;
        if (list.substr(i, j - i) == word) return true;
        i = j;
    }
    return false;
}

// The pad the attributes ask for. elem: the probe's kind ("input", "textarea", "ce", "none"); type, mode and
// autocomplete are lower case (the probe lower-cases them). inputmode wins over type, as in browsers.
//   one-time-code (on a text / number / tel / untyped input; inputmode empty, numeric or tel) -> kCode
//   inputmode tel -> kTel;  numeric -> kDigits;  decimal -> kDecimal
//   no inputmode: type tel -> kTel, type number -> kDecimal
// Never for passwords (they keep the letters and Show / Hide), text areas or editors.
inline int padKind(std::string_view elem, std::string_view type, std::string_view mode, std::string_view autocomplete)
{
    if (elem != "input" || type == "password") return kNone;
    const bool typeOk = type.empty() || type == "text" || type == "number" || type == "tel";
    if (hasToken(autocomplete, "one-time-code") && typeOk && (mode.empty() || mode == "numeric" || mode == "tel")) return kCode;
    if (mode == "tel") return kTel;
    if (mode == "numeric") return kDigits;
    if (mode == "decimal") return kDecimal;
    if (!mode.empty()) return kNone;   // inputmode text / email / url / search / none: not a pad
    if (type == "tel") return kTel;
    if (type == "number") return kDecimal;
    return kNone;
}

// After the shell decided its field kind: a one-time-code box (often a plain text input) becomes a number field;
// any other number field gets a pad (kDecimal when the attributes named none); everything else gets none.
inline int settle(int pad, bool numberField, bool textField)
{
    if (pad < kNone || pad >= kPadCount) pad = kNone;
    if (pad == kCode && (numberField || textField)) return kCode;
    if (!numberField) return kNone;
    return pad == kNone || pad == kCode ? kDecimal : pad;
}

// Rows 0-3: a phone-style grid, three keys a row (row 3: Delete 0 Done for digits / codes, - 0 . decimal, * 0 # tel).
inline std::vector<Key> gridRow(int pad, int row)
{
    constexpr float w = 10.f / 3;
    switch (row) {
    case 0: return { { "1", kInsert, w }, { "2", kInsert, w }, { "3", kInsert, w } };
    case 1: return { { "4", kInsert, w }, { "5", kInsert, w }, { "6", kInsert, w } };
    case 2: return { { "7", kInsert, w }, { "8", kInsert, w }, { "9", kInsert, w } };
    default: break;
    }
    if (pad == kTel) return { { "*", kInsert, w }, { "0", kInsert, w }, { "#", kInsert, w } };
    if (pad == kDecimal) return { { "-", kInsert, w }, { "0", kInsert, w }, { ".", kInsert, w } };
    return { { "Delete", kDelete, w }, { "0", kInsert, w }, { "Done", kDone, w } };
}

// Row 4 (the quick row; the Edit tools replace it as before): a few symbols for the field, then Paste and Clips.
inline std::vector<Key> quickRow(int pad)
{
    if (pad == kCode) return { { "Paste", kPaste, 5 }, { "Clips", kClips, 5 } };
    std::vector<Key> r;
    if (pad == kTel) r = { { "+", kInsert, 1.5f }, { "(", kInsert, 1.5f }, { ")", kInsert, 1.5f }, { "-", kInsert, 1.5f } };
    else if (pad == kDecimal) r = { { ",", kInsert, 1.5f }, { "+", kInsert, 1.5f }, { "e", kInsert, 1.5f }, { "/", kInsert, 1.5f } };
    else r = { { "-", kInsert, 1.5f }, { "/", kInsert, 1.5f }, { ".", kInsert, 1.5f }, { ",", kInsert, 1.5f } };
    r.push_back({ "Paste", kPaste, 2 });
    r.push_back({ "Clips", kClips, 2 });
    return r;
}

// Row 5 (the action row): no Shift on a pad; Delete and Done are the widest keys.
inline std::vector<Key> actionRow()
{
    return { { "ABC", kLayer, 1.5f }, { "Edit", kTools, 1.25f }, { "Space", kSpace, 1.25f },
             { "Delete", kDelete, 2 }, { "Done", kDone, 2.5f }, { "Close", kClose, 1.5f } };
}

inline float units(const std::vector<Key>& row)
{
    float u = 0;
    for (const Key& k : row) u += k.units;
    return u;
}

} // namespace OmniKbFields
