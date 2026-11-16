#!/usr/bin/env python3
"""OMNI_TEXT_SELECT_V1 (2026-11-16): select text on a web page with the controller, then Copy / Search for <text> /
Paste into address bar / Show as QR code.

What existed
  - Omni's own clipboard: omniKbClipboard (OmniBrowser.cpp, OMNI_KEYBOARD_V2), a std::string in memory only (never
    written to disk, gone when Omni exits; PS5 homebrew has no system clipboard). Filled by the keyboard's Copy / Cut
    (8 KB), the page menu's Copy link / image / page address (omniFxCopy) and L2 + Square (omniL2Copy, 8 KB).
  - Paste: the on-screen keyboard's Paste key (Touchpad in a text box: the edit-tools row, omniKbPasteKey; Ctrl+V on a
    USB keyboard) and L2 + Triangle (omniL2Paste, into the focused text box). No new key needed.
  - Pointer + held Cross does NOT select text: holding Cross 0.5 s opens the page menu (omniFxButtonEvent), a shorter
    press is one click on release; no drag is ever sent to the page. There was no way to select page text.
  - L2 + Square copies window.getSelection() first, but its probe was always a SyntaxError (omniL2Copy cut the last 2
    characters of a template ending "})(", dropping the IIFE's ')': the bug OMNI_SAVE_IMAGE_V1 fixed in
    omniFxContextQuery), so it always fell back to copying the page address. Fixed here the same way.
  - WebKit (WPE C API): no selection API in WKPage for the shell; the page side has window.getSelection(),
    document.caretRangeFromPoint, Selection.setBaseAndExtent / modify('extend', dir, 'word' | 'line'), Intl.Segmenter.

What the user sees now
  - Hold Cross over text that is not a link / image / video / form field: the page menu gets a first-group row "Select
    text" (the hit test, omniFxContextScript, now also reports "tx" when caretRangeFromPoint finds non-blank text
    within ~24 px of the pointer, same-origin frames followed).
  - Cross on it: the word under the pointer is selected (Intl.Segmenter word, else letters / digits / marks / '_' run,
    else a punctuation run; the page's own selection, painted by WebKit). A bar at the top: "3 words selected" and the
    quoted text; hints "Cross Actions, Circle Cancel, D-pad: extend by word / line".
  - D-pad right / left: extend by a word (Selection.modify('extend', 'forward' | 'backward', 'word')), down / up: by a
    line; the moving end is scrolled into view. Every other button is taken while selecting; Circle / Create / Options
    cancel (the page's selection is dropped).
  - Cross (or Cross with the pointer leading): "Selected text" panel: Copy / Search for "<text>" / Paste into address
    bar / Show as QR code. Circle there goes back to selecting.
      Copy: Omni's clipboard gets the text as selected (line breaks kept), at most 4 KB (UTF-8 boundary); notice "Copied
        N characters: the keyboard's Paste key or L2 + Triangle pastes it". Private tabs too: memory only, as before.
      Search for: whitespace collapsed, at most 400 bytes, the chosen engine (omniFxSearchPrefix) in a new tab (a
        private tab from a private tab: omniFxOpenInNewTab).
      Paste into address bar: the address keyboard opens holding the text (one line, at most 2048 bytes, selected, so
        Go opens / searches it and typing replaces it).
      Show as QR code: OMNI_QR_SHARE_V1's panel with the text (byte mode, at most 666 bytes; the row is disabled and
        says so when longer), heading "Scan to read this text on your phone". Nothing stored.
  - The selection ends when its tab is left / crashes / goes full screen, or the page drops it ("The selection is gone").

Pure part: engine/entry/OmniTextSelect.h (page script, script(op, x, y): only fixed op letters and finite numbers are
spliced in, no page or user text; clip / collapse / forAddress / query / encode / preview / status / actions).
Shell part: engine/entry/OmniTextSelectShell.h (state, layer, panel, actions), namespace alias OTSL.
Anchors (each once; whole lines; inserted lines before/after them, CRLF kept):
  OmniBrowser.cpp       the OmniQrShare.h include line (pure include after it); omniL2Copy's
                        'js.replace(js.size() - 2, 2, "(X,Y);})()");' line (replaced: the hit-test fix)
  OmniFeatures3.h       the OmniQrShareShell.h include line (shell include after it)
  OmniContextMenu.h     'static bool omniQrContextAction(int id);' (declarations after); the "Open video in new tab"
                        add() line (row after); 'if (omniQrContextAction(r.id)) return true;' (action after);
                        'omniFxJsonString(json, "video", p.text);' (tx after); the script's last line
                        'return JSON.stringify(r);...})()JS";' (tx probe line before it, inside the raw string: no comment)
  OmniQrShareShell.h    'bool trimmed = false;' member (title after); 'omniQr.trimmed = url != t->url;' (title cleared
                        after); the "Scan to open this page on your phone" label line (replaced: the title when set)
Controls guide (OmniControlsHelp.h) is not edited here; rows to add are listed in the report.
Tests: tools/test_text_select.cpp (g++, pure part; --emit <dir> writes the assembled scripts for node --check),
tools/test_text_select_js.cjs <dir> <OmniContextMenu.h> <OmniBrowser.cpp> (node: the select / extend script on mock
DOMs, the patched hit-test and L2 copy probes).
r2 (REV = OMNI_TEXT_SELECT_V1_R2): status() compares the page's full length (UTF-16 units) with utf16Units(text), not
  with codePoints(text): one emoji in a tiny selection no longer shows "(the first 4 KB is used)". Only OmniTextSelect.h
  changes; a tree patched by r1 gets it rewritten (write_new rewrites a header that differs), the anchored edits are
  untouched, so the result is byte-identical to a fresh apply.
usage: apply_text_select.py <engine tree>   (anchored, idempotent, keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_TEXT_SELECT_V1'
REV = 'OMNI_TEXT_SELECT_V1_R2'   # r2: status() counts UTF-16 units (non-BMP characters); in OmniTextSelect.h only
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TEXT_SELECT_V1: the pure part of "Select text" (no SDL, no WebKit): the page script that selects the word under
// the pointer and extends the selection (Selection.modify), the clipboard cap, the address-bar / search / QR text
// clean-up and the actions list. Shell side: OmniTextSelectShell.h; reasons in tools/apply_text_select.py.
// Tested on the host with g++ (tools/test_text_select.cpp) and node (tools/test_text_select_js.cjs).
// OMNI_TEXT_SELECT_V1_R2: status() compares UTF-16 units (utf16Units).
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <string>
#include <vector>

namespace OmniTextSelect {

constexpr size_t kClipMax = 4096;      // bytes kept by Copy (Omni's own clipboard: memory only, gone when Omni exits)
constexpr size_t kAddressMax = 2048;   // the address field's limit (omniKbLimit)
constexpr size_t kQueryMax = 400;      // bytes of a "Search for" query
constexpr size_t kPreviewMax = 60;     // bytes of the quoted text in the bar and the panel title
constexpr int kContextId = 985;        // hold-Cross page menu row (pinned tabs 960, QR 975)
constexpr int kContextMode = 0x7453;   // OmniFxPanel::mode of a page menu opened over text (the hit test said "tx")

// What the page script does. Start: select the word at (x, y) (CSS px of the main frame; same-origin frames followed).
// Right / Left: extend by a word; Down / Up: by a line. Clear: drop the selection (every same-origin frame).
enum class Op { Start, Right, Left, Up, Down, Clear };
inline const char* opCode(Op op)
{
    switch (op) {
    case Op::Start: return "s";
    case Op::Right: return "f";
    case Op::Left: return "b";
    case Op::Down: return "d";
    case Op::Up: return "u";
    case Op::Clear: return "c";
    }
    return "c";
}

// The page script: a function expression (op, x, y) returning a JSON string: {"ok":1,"t":<text, at most 4096 UTF-16
// units, no split surrogate pair>,"n":<full length>} or "{}" (no text there / no selection any more). Read-only apart
// from the page's own selection (and a scroll that keeps the moving end in view). Nothing is stored in the page.
static const char* const kScript = R"JS(function(op,x,y){try{var MAX=4096,W=window;
function wins(){var o=[W];for(var i=0;i<o.length&&o.length<12;i++){var f=null;try{f=o[i].frames;}catch(_){}for(var j=0;f&&j<f.length&&o.length<12;j++){try{if(f[j].document&&f[j].getSelection)o.push(f[j]);}catch(_){}}}return o;}
function sel(w){try{var s=w.getSelection();return s&&s.rangeCount?s:null;}catch(_){return null;}}
function cur(){var o=wins(),i,s;for(i=0;i<o.length;i++){s=sel(o[i]);if(s&&!s.isCollapsed)return{w:o[i],s:s};}for(i=0;i<o.length;i++){s=sel(o[i]);if(s)return{w:o[i],s:s};}return null;}
function clear(){var o=wins();for(var i=0;i<o.length;i++){var s=sel(o[i]);if(s)try{s.removeAllRanges();}catch(_){}}}
function res(s){var t=String(s),u=t.slice(0,MAX);if(u.length<t.length&&/[\uD800-\uDBFF]$/.test(u))u=u.slice(0,-1);return JSON.stringify({ok:1,t:u,n:t.length});}
var wre;try{wre=new RegExp('[\\p{L}\\p{N}\\p{M}_]','u');}catch(_){wre=/[A-Za-z0-9_À-￿]/;}
function isW(c){return c!==''&&wre.test(c);}
function word(t,o){o=Math.max(0,Math.min(o,t.length));
if(typeof Intl==='object'&&Intl.Segmenter){try{var sg=new Intl.Segmenter(undefined,{granularity:'word'}).segment(t),g=o<t.length?sg.containing(o):null;if(g&&g.isWordLike)return[g.index,g.index+g.segment.length];g=o>0?sg.containing(o-1):null;if(g&&g.isWordLike)return[g.index,g.index+g.segment.length];}catch(_){}}
var a=o,b;if(!isW(t.charAt(a))&&a>0&&isW(t.charAt(a-1)))a--;
if(isW(t.charAt(a))){b=a+1;while(a>0&&isW(t.charAt(a-1)))a--;while(b<t.length&&isW(t.charAt(b)))b++;return[a,b];}
if(a<t.length&&/\S/.test(t.charAt(a))){b=a+1;while(a>0&&/\S/.test(t.charAt(a-1))&&!isW(t.charAt(a-1)))a--;while(b<t.length&&/\S/.test(t.charAt(b))&&!isW(t.charAt(b)))b++;return[a,b];}
return null;}
if(op==='c'){clear();return'{"ok":1}';}
if(op==='s'){var d=document,e=d.elementFromPoint(x,y);
for(var k=0;k<3&&e&&e.tagName==='IFRAME';k++){var fd=null;try{fd=e.contentDocument;}catch(_){}if(!fd)break;var r0=e.getBoundingClientRect();x-=r0.left;y-=r0.top;d=fd;e=d.elementFromPoint(x,y);}
if(!e||/^(INPUT|TEXTAREA|SELECT|OPTION|BUTTON)$/.test(e.tagName))return'{}';
var cr=null;if(d.caretRangeFromPoint)cr=d.caretRangeFromPoint(x,y);else if(d.caretPositionFromPoint){var cp=d.caretPositionFromPoint(x,y);if(cp){cr=d.createRange();cr.setStart(cp.offsetNode,cp.offset);}}
if(!cr||!cr.startContainer||cr.startContainer.nodeType!==3)return'{}';
var n=cr.startContainer,w=word(n.data,cr.startOffset);if(!w)return'{}';
var rg=d.createRange();rg.setStart(n,w[0]);rg.setEnd(n,w[1]);var q=rg.getBoundingClientRect();
if(q.width>0&&(x<q.left-24||x>q.right+24||y<q.top-16||y>q.bottom+16))return'{}';
clear();var s=(d.defaultView||W).getSelection();s.setBaseAndExtent(n,w[0],n,w[1]);return res(s);}
if(op!=='f'&&op!=='b'&&op!=='u'&&op!=='d')return'{}';
var c=cur();if(!c)return'{}';
c.s.modify('extend',op==='f'||op==='d'?'forward':'backward',op==='u'||op==='d'?'line':'word');
try{if(c.s.focusNode){var fr=c.w.document.createRange();fr.setStart(c.s.focusNode,c.s.focusOffset);var r2=fr.getBoundingClientRect(),H=c.w.innerHeight;if(r2.height>0){if(r2.bottom>H-40)c.w.scrollBy(0,r2.bottom-H+80);else if(r2.top<40)c.w.scrollBy(0,r2.top-80);}}}catch(_){}
return res(c.s);}catch(err){return'{}';}})JS";

// A coordinate for the script: finite, within +-1e6, one decimal ("%.1f", '.' whatever the locale's digits).
inline std::string number(double v)
{
    if (!std::isfinite(v)) v = 0;
    if (v > 1e6) v = 1e6;
    if (v < -1e6) v = -1e6;
    char b[32];
    snprintf(b, sizeof(b), "%.1f", v);
    for (char* p = b; *p; ++p) if (*p == ',') *p = '.';
    return b;
}
// The whole script for one step. Only fixed op letters and numbers are spliced in: no page or user text.
inline std::string script(Op op, double x = 0, double y = 0)
{
    return std::string("(") + kScript + ")('" + opCode(op) + "'," + number(x) + "," + number(y) + ")";
}

// --- text helpers ------------------------------------------------------------------------------------------------
// The longest prefix of s of at most max bytes that does not split a UTF-8 sequence.
inline std::string utf8Cut(const std::string& s, size_t max)
{
    if (s.size() <= max) return s;
    size_t n = max;
    while (n > 0 && (static_cast<unsigned char>(s[n]) & 0xC0) == 0x80) --n;
    return s.substr(0, n);
}
// What Copy puts on Omni's clipboard: the text as selected (line breaks kept), at most kClipMax bytes.
inline std::string clip(const std::string& s) { return utf8Cut(s, kClipMax); }
inline size_t codePoints(const std::string& s)
{
    size_t n = 0;
    for (unsigned char c : s) if ((c & 0xC0) != 0x80) ++n;
    return n;
}
// OMNI_TEXT_SELECT_V1_R2: the length JavaScript gives the same text (UTF-16 code units: a 4-byte UTF-8 sequence, i.e. a
// character outside the BMP such as an emoji, is a surrogate pair = 2). The page's "n" is in these units.
inline size_t utf16Units(const std::string& s)
{
    size_t n = 0;
    for (unsigned char c : s) if ((c & 0xC0) != 0x80) n += c >= 0xF0 ? 2 : 1;
    return n;
}
// Whitespace runs (ASCII controls, spaces, U+00A0, U+2028 / U+2029) become one space; trimmed.
inline std::string collapse(const std::string& s)
{
    std::string out;
    bool space = false;
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        size_t skip = 0;
        if (c <= 0x20 || c == 0x7F) skip = 1;
        else if (c == 0xC2 && i + 1 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0xA0) skip = 2;
        else if (c == 0xE2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                 && (static_cast<unsigned char>(s[i + 2]) == 0xA8 || static_cast<unsigned char>(s[i + 2]) == 0xA9)) skip = 3;
        if (skip) { space = !out.empty(); i += skip - 1; continue; }
        if (space) { out += ' '; space = false; }
        out += char(c);
    }
    return out;
}
// "Paste into address bar": one line, at most the address field's limit.
inline std::string forAddress(const std::string& s) { return utf8Cut(collapse(s), kAddressMax); }
// "Search for": one line, at most kQueryMax bytes.
inline std::string query(const std::string& s) { return utf8Cut(collapse(s), kQueryMax); }
// Percent-encoding as destination() does for the address bar's searches (only A-Z a-z 0-9 - _ kept).
inline std::string encode(const std::string& s)
{
    static const char* const hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : s) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') out += char(c);
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}
// One line for the bar / titles: collapsed, longer ones cut at a character boundary with "...".
inline std::string preview(const std::string& s, size_t max = kPreviewMax)
{
    const std::string c = collapse(s);
    if (c.size() <= max) return c;
    return utf8Cut(c, max > 3 ? max - 3 : 0) + "...";
}
inline size_t words(const std::string& s)
{
    const std::string c = collapse(s);
    if (c.empty()) return 0;
    size_t n = 1;
    for (char ch : c) if (ch == ' ') ++n;
    return n;
}
// The bar's first line. total: the selection's full length (UTF-16 units, from the page); text holds at most 4096.
// OMNI_TEXT_SELECT_V1_R2: compared in the same units (an emoji is 2 there, 1 code point here: "(the first 4 KB is used)"
// showed on a tiny selection with one).
inline std::string status(const std::string& text, size_t total)
{
    const size_t w = words(text);
    if (!w) return "Nothing selected";
    std::string s = std::to_string(w) + (w == 1 ? " word selected" : " words selected");
    if (total > utf16Units(text) || text.size() > kClipMax) s += " (the first 4 KB is used)";
    return s;
}
inline std::string copiedNotice(const std::string& text)
{
    const std::string c = clip(text);
    const size_t n = codePoints(c);
    return "Copied " + std::to_string(n) + (n == 1 ? " character" : " characters")
        + (c.size() < text.size() ? " (the first 4 KB)" : "") + ": the keyboard's Paste key or L2 + Triangle pastes it";
}

// --- the actions panel (Cross while selecting) ---------------------------------------------------------------------
enum class Action { Copy, Search, Address, Qr };
struct Item { Action action; std::string label; bool enabled; };
// qrMax: OmniQr::maxBytes() (byte mode, version 20, level M: 666). Show as QR code uses the clipped text.
inline std::vector<Item> actions(const std::string& text, size_t qrMax)
{
    const bool any = !collapse(text).empty();
    const bool qrFits = any && clip(text).size() <= qrMax;
    std::vector<Item> v;
    v.push_back({ Action::Copy, "Copy", any });
    v.push_back({ Action::Search, any ? "Search for \"" + preview(text, 40) + "\"" : std::string("Search for the text"), any });
    v.push_back({ Action::Address, "Paste into address bar", any });
    v.push_back({ Action::Qr, qrFits || !any ? std::string("Show as QR code") : "Show as QR code (too long: " + std::to_string(qrMax) + " bytes at most)", qrFits });
    return v;
}

} // namespace OmniTextSelect
'''

SHELL = r'''// OMNI_TEXT_SELECT_V1: "Select text" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniQrShareShell.h). The pure part (page script, clipboard cap, text clean-up, actions) is
// OmniTextSelect.h; reasons in tools/apply_text_select.py.
// Hold Cross on a page's text > "Select text": the word under the pointer is selected (the page's own selection, painted
// by WebKit). D-pad right / left extends by a word, down / up by a line (Selection.modify); Cross: Copy / Search for /
// Paste into address bar / Show as QR code; Circle (or Options) cancels. Copy goes to Omni's own clipboard
// (omniKbClipboard: memory only, at most 4 KB from here, gone when Omni exits; private tabs too, never written anywhere).
// Main thread only.
#pragma once

namespace OTSL = OmniTextSelect;

struct OmniTslState {
    bool on = false;                 // selecting: the layer is open
    const void* tab = nullptr;       // the tab whose page holds the selection
    uint32_t gen = 0;                // results of an older selection are dropped
    std::string text;                // the selection's text (at most 4096 UTF-16 units from the page)
    size_t total = 0;                // its full length (UTF-16 units)
};
static OmniTslState omniTsl;
static uint32_t omniTslGen = 0;
struct OmniTslQuery { const void* tab; uint32_t gen; int op; };

static void omniTslResult(OTSL::Op op, const std::string& json);
static void omniTslRun(OTSL::Op op, double x = 0, double y = 0)
{
    Tab* t = active();
    if (!t || t->crashed) return;
    const std::string js = OTSL::script(op, x, y);
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    auto* q = new OmniTslQuery { t, omniTsl.gen, int(op) };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniTslQuery> q(static_cast<OmniTslQuery*>(context));
        if (q->op == int(OTSL::Op::Clear)) return;
        if (!omniTabAlive(q->tab) || active() != q->tab || q->gen != omniTsl.gen) return;
        omniTslResult(OTSL::Op(q->op), omniFxResultString(result, error));
    });
}
static void omniTslEnd(bool clearPage)
{
    if (clearPage && omniTsl.tab && active() == omniTsl.tab && omniTabAlive(omniTsl.tab)) omniTslRun(OTSL::Op::Clear);
    omniTsl = OmniTslState();
    omniTsl.gen = ++omniTslGen;
    omniShellDirty = true;
}
// px, py: the layout point the page menu was opened at.
static void omniTslStart(int px, int py)
{
    Tab* t = active();
    if (!t || t->crashed) return;
    omniTsl = OmniTslState();
    omniTsl.tab = t;
    omniTsl.gen = ++omniTslGen;
    const double k = omniFxCssPerLayout(t);
    omniTslRun(OTSL::Op::Start, px * k, (py - omniPageTop()) * k);
}
static void omniTslResult(OTSL::Op op, const std::string& json)
{
    double ok = 0, n = 0;
    std::string text;
    const bool good = omniFxJsonNumber(json, "ok", ok) && ok > 0 && omniFxJsonString(json, "t", text);
    omniFxJsonNumber(json, "n", n);
    if (op == OTSL::Op::Start) {
        if (!good || text.empty()) { omniTslEnd(false); notice("No text under the pointer: hold Cross on a word"); return; }
        if (editing || settingsOpen || pageFullscreen || omniOverlayOpen()) { omniTslEnd(true); return; }   // something opened meanwhile
        omniTsl.on = true;
    } else if (!good) {
        omniTslEnd(false);
        notice("The selection is gone (the page changed)");
        return;
    }
    omniTsl.text = std::move(text);
    omniTsl.total = n > 0 ? size_t(n) : 0;
    omniShellDirty = true;
}

// --- hold-Cross page menu ------------------------------------------------------------------------------------------
static void omniTslContextRow(OmniFxPanel& p)
{
    if (p.mode != OTSL::kContextMode) return;   // the hit test found text at the pointer (not a link / image / video)
    OmniFxRow r; r.id = OTSL::kContextId; r.label = "Select text";
    p.rows.push_back(r);
}
static bool omniTslContextAction(OmniFxPanel& p, int id)
{
    if (id != OTSL::kContextId) return false;
    const int px = p.anchorX, py = p.anchorY;   // p is gone after omniFxCloseAll
    omniFxCloseAll();
    omniTslStart(px, py);
    return true;
}

// --- actions (Cross while selecting) -------------------------------------------------------------------------------
static void omniTslQr(const std::string& text)
{
    const std::string s = OTSL::clip(text);
    OQR::Code code;
    if (!OQR::encode(s, code)) {
        notice("This text is too long for a QR code (" + std::to_string(s.size()) + " bytes, at most " + std::to_string(OQR::maxBytes()) + ")");
        return;
    }
    omniFxCloseAll();
    omniQr = OmniQrState();
    omniQr.code = std::move(code);
    omniQr.shown = OTSL::preview(s, 72);
    omniQr.title = "Scan to read this text on your phone";
    omniQr.open = true;
    omniShellDirty = true;
}
static void omniTslDo(OTSL::Action a, const std::string& text)
{
    switch (a) {
    case OTSL::Action::Copy:
        omniKbClipboard = OTSL::clip(text);   // memory only: never written to disk, gone when Omni exits
        notice(OTSL::copiedNotice(text));
        break;
    case OTSL::Action::Search: {
        const std::string q = OTSL::query(text);
        if (q.empty()) { notice("Nothing to search for"); break; }
        omniFxOpenInNewTab(omniFxSearchPrefix() + OTSL::encode(q), false, false);   // private tabs search in a private tab
        break;
    }
    case OTSL::Action::Address:
        editAddress();
        address = OTSL::forAddress(text);   // the keyboard opens with it selected: Go (Options) opens / searches it
        break;
    case OTSL::Action::Qr: omniTslQr(text); break;
    }
    omniShellDirty = true;
}
static void omniTslActionsBuild(OmniFxPanel& p)
{
    for (const auto& it : OTSL::actions(p.text, size_t(OQR::maxBytes()))) {
        OmniFxRow r; r.id = 1 + int(it.action); r.label = it.label; r.enabled = it.enabled;
        p.rows.push_back(r);
    }
}
static bool omniTslActionsInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;   // Circle: back to selecting (omniFxButton pops the panel)
    if (!r.enabled) return true;
    const std::string text = p.text;                  // p is gone after omniFxCloseAll
    omniFxCloseAll();
    omniTslEnd(true);
    omniTslDo(OTSL::Action(r.id - 1), text);
    return true;
}
static void omniTslActions()
{
    if (OTSL::collapse(omniTsl.text).empty()) { notice("Nothing selected: D-pad right selects the next word"); return; }
    OmniFxPanel p;
    p.title = "Selected text";
    p.subtitle = "\"" + OTSL::preview(omniTsl.text) + "\"";
    p.text = omniTsl.text;
    p.w = 560; p.rowH = 46; p.maxVisible = 6;
    p.build = omniTslActionsBuild; p.input = omniTslActionsInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- the selecting layer: a bar above the page, every button taken -------------------------------------------------
static bool omniTslOpen()
{
    if (!omniTsl.on) return false;
    if (!omniTabAlive(omniTsl.tab) || active() != omniTsl.tab || active()->crashed || pageFullscreen) { omniTslEnd(false); return false; }
    return true;
}
static bool omniTslButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniTslRun(OTSL::Op::Right); break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniTslRun(OTSL::Op::Left); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniTslRun(OTSL::Op::Down); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniTslRun(OTSL::Op::Up); break;
    case SDL_CONTROLLER_BUTTON_A: omniTslActions(); break;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: case SDL_CONTROLLER_BUTTON_START: omniTslEnd(true); break;
    default: break;                                   // the other buttons do nothing while selecting
    }
    omniShellDirty = true;
    return true;
}
static bool omniTslClick(int, int)
{
    if (omniPtrCross.inCross) omniTslActions();       // Cross while the pointer leads: the actions, as Cross
    else omniTslEnd(true);                            // a mouse click: cancel
    return true;
}
static void omniTslDraw()
{
    const OmniTheme& T = omniTheme();
    const int w = std::min(760, width - 40), h = 66, x = (width - w) / 2, y = omniPageTop() + 14;
    omniShadow(x, y, w, h, omniRadius + 2, 14, 140, 4);
    fillRounded(x, y, w, h, omniRadius + 2, T.panel);
    omniLabel(OTSL::status(omniTsl.text, omniTsl.total), x + 24, y + 22, omniBodyBold, T.ink, 0, w - 48);
    omniLabel(omniTsl.text.empty() ? std::string("D-pad: extend by word or line") : "\"" + OTSL::preview(omniTsl.text, 90) + "\"",
        x + 24, y + 47, omniSmall, T.inkDim, 0, w - 48);
    if (!omniFxPanelOpen() && !editing) omniPanelHints({ { 0, "Actions" }, { 1, "Cancel" } }, "D-pad: extend by word / line");
}
[[maybe_unused]] static const bool omniTslLayers = [] {
    omniOverlayLayers().push_back({ omniTslOpen, omniTslButton, omniTslClick, nullptr, omniTslDraw, true });
    return true;
}();
'''

# The hit test's text probe (inside the R"JS(...)JS" raw string: no C++ comment possible). e / x / y are the element
# and point after same-origin frames were followed; text only when nothing else (link, image, video) was found.
TX_JS = (r'''if(!r.link&&!r.img&&!r.video&&e&&!/^(INPUT|TEXTAREA|SELECT|OPTION|BUTTON)$/.test(e.tagName)&&!e.isContentEditable){try{'''
         r'''var od=e.ownerDocument||d,cr=od.caretRangeFromPoint?od.caretRangeFromPoint(x,y):null,tn=cr&&cr.startContainer;'''
         r'''if(tn&&tn.nodeType===3&&/\S/.test(tn.data)){var to=Math.max(0,Math.min(cr.startOffset,tn.data.length-1)),tr=od.createRange();'''
         r'''tr.setStart(tn,to);tr.setEnd(tn,to+1);var tq=tr.getBoundingClientRect();'''
         r'''if(!(tq.width>0)||(x>=tq.left-24&&x<=tq.right+24&&y>=tq.top-16&&y<=tq.bottom+16))r.tx=1;}}catch(_){}}''' + '\n')
CTX_END = r'''return JSON.stringify(r);}catch(err){return'{}';}})()JS";''' + '\n'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniQrShare.h" // OMNI_QR_SHARE_V1: Show QR code (pure encoder)\n',
         '#include "OmniQrShare.h" // OMNI_QR_SHARE_V1: Show QR code (pure encoder)\n'
         '#include "OmniTextSelect.h" // ' + MARK + ': Select text (pure: page script, clipboard cap, actions)\n'),
        # omniL2Copy: the raw string ends "})(" (its delimiter ")JS\"" takes the last ')'): cutting 2 characters dropped
        # the IIFE's ')' and every probe was a SyntaxError, so L2 + Square always copied the page address.
        ('    js.replace(js.size() - 2, 2, "(X,Y);})()");\n',
         '    if (js.size() >= 2 && js.compare(js.size() - 2, 2, "()") == 0) js.resize(js.size() - 2); /* ' + MARK + ': the template ends "})(" */\n'
         '    else if (!js.empty() && js.back() == \'(\') js.pop_back();\n'
         '    js += "(X,Y);})()";   /* call it with X, Y */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n',
         '#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n'
         '#include "OmniTextSelectShell.h" // ' + MARK + ': Select text (page menu row, selecting layer, actions)\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniQrContextAction(int id);\n',
         'static bool omniQrContextAction(int id);\n'
         'static void omniTslContextRow(OmniFxPanel& p); // ' + MARK + ' (OmniTextSelectShell.h)\n'
         'static bool omniTslContextAction(OmniFxPanel& p, int id);\n'),
        ('        if (!p.text.empty()) add(omniCxVideoTab, "Open video in new tab", !four);\n',
         '        if (!p.text.empty()) add(omniCxVideoTab, "Open video in new tab", !four);\n'
         '        omniTslContextRow(p); // ' + MARK + ': Select text (over text only)\n'),
        ('    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n',
         '    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n'
         '    if (omniTslContextAction(p, r.id)) return true; // ' + MARK + '\n'),
        ('    omniFxJsonString(json, "video", p.text);\n',
         '    omniFxJsonString(json, "video", p.text);\n'
         '    { double tx = 0; if (omniFxJsonNumber(json, "tx", tx) && tx > 0) p.mode = OmniTextSelect::kContextMode; } // ' + MARK + ': text at the pointer\n'),
        (CTX_END, TX_JS + CTX_END),
    ],
    'OmniQrShareShell.h': [
        ('    bool trimmed = false;                          // tracking parameters were dropped\n',
         '    bool trimmed = false;                          // tracking parameters were dropped\n'
         '    std::string title;                             // ' + MARK + ': another heading (selected text); empty: the page one\n'),
        ('    omniQr.trimmed = url != t->url;\n',
         '    omniQr.trimmed = url != t->url;\n'
         '    omniQr.title.clear(); // ' + MARK + '\n'),
        ('    omniLabel("Scan to open this page on your phone", g.x + g.w / 2.f, g.y + 34, omniBodyBold, T.ink, 1, g.w - 48);\n',
         '    omniLabel(omniQr.title.empty() ? std::string("Scan to open this page on your phone") : omniQr.title, g.x + g.w / 2.f, g.y + 34, omniBodyBold, T.ink, 1, g.w - 48); // ' + MARK + '\n'),
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
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    s = (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    for need, tool in (('OMNI_QR_SHARE_V1', 'apply_qr_share.py'), ('OMNI_L2_CHORDS_V1', 'apply_l2_chords.py')):
        if need not in s:
            sys.exit('OmniBrowser.cpp: %s missing: %s first' % (need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTextSelect.h', PURE, 'OmniQrShare.h'),
            write_new('OmniTextSelectShell.h', SHELL, 'OmniQrShareShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
