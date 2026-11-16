#!/usr/bin/env python3
"""OMNI_LINK_PREVIEW_V1 (2026-11-16): show where a link goes before it is pressed.

What the user sees
  - The pointer rests on a link for ~250 ms: a small pill at the bottom-left of the page area shows the link's host + path,
    shortened ("example.com/news/article…"; "www." dropped, the default port dropped, a query shown as "?…", a host too
    long for the pill loses its LEFT part so the registrable end stays visible: "…login.paypal.com.evil.xyz").
      https          lock icon (focus colour)
      javascript:    "Script link"          data:   "Data link"          other schemes: the URL as it is (mailto:...)
      IDN hosts      shown in Unicode (münchen.de) when every label is one script (or Latin + Han/kana/Hangul/Bopomofo),
                     else as punycode with a warning (Latin + Cyrillic mixes, аррӏе.com-style whole-script look-alikes
                     under an ASCII TLD, zero-width / IPA / full-width / math letters)
    Warning colour (amber edge + text, alert disc instead of the lock) with a short reason after a middle dot:
      the link's visible text is itself an address naming another site   "paypa1-login.xyz/verify · not paypal.com"
        (registrable-domain compare: text "paypal.com" -> target www.paypal.com is fine; known shorteners / outbound
        redirectors such as t.co, bit.ly, youtu.be, out.reddit.com are exempt since they show the destination as text)
      look-alike letters in the target host                                "xn--80ak6aa92e.com · look-alike letters"
      a user name before the host (https://paypal.com@evil.example/)      "evil.example · not paypal.com"
  - The pill stays while the pointer moves within the same link, hides at once on another link / off links, moves to
    the bottom-right while the pointer is near its corner, and sits above the centred notice toast when they'd overlap.
    It is anchored to omniPageBottom() (the page's own bottom edge), so it never covers the bottom button bar however that
    bar is sized or hidden (the interface-size work changes the bar's drawing; nothing here touches omniHints()).
  - Not shown over menus, panels, dialogs, the keyboard, Browser settings, fullscreen pages, or in test modes.
  - Browser settings: "Show link address on hover"  On / Off (default On; Off = /data/omni/link-preview-off.flag).
    Cross / D-pad left-right toggles, notice "Link address on hover: On|Off".
  - Private tabs: the same; nothing is stored or logged anywhere (the hovered URL lives in memory until the pointer
    leaves the link, a navigation happens or the tab changes).

Where the link comes from: WebKit's own UI-client callback, no page script.
  WKPageUIClientV19::mouseDidMoveOverElement(page, WKHitTestResultRef, modifiers, userData, clientInfo); the result gives
  WKHitTestResultCopyAbsoluteLinkURL and WKHitTestResultCopyLinkLabel (the link element's text content), both exported
  (UIProcess/API/C/WKHitTestResultRef.cpp is in WebKit's Sources.txt). This port delivers it for the shell's synthetic
  pointer: mouse() -> WKPageHandleMouseEvent (PlayStation C API) builds a wpe motion event with no button ->
  NativeWebMouseEvent -> WebPageProxy::handleMouseEvent -> WebFrame::handleMouseEvent case MouseMoved ->
  EventHandler::mouseMoved (non-Cocoa: always) -> Chrome::mouseDidMoveOverElement -> WebChromeClient (IPC) ->
  WebPageProxy::mouseDidMoveOverElement -> the C client (version 19 > 0: the hit-test variant). WebKit's fake mouse
  moves after scrolling / layout take the same EventHandler::mouseMoved path, so a link scrolled under a resting pointer
  is reported too. No client set this slot before (grep), so nothing is displaced. Checked by reading the source of
  the engine's WebKit tree (s1/webkit) only; delivery on the console is not verified yet (if it never fires, the pill simply never
  shows: the fallback would be a debounced elementFromPoint query when the stick is released, as omniFxSnapRequest does).
  The 250 ms rest is timed by the shell pass (pointer unchanged), not by WebKit.

Pure part: engine/entry/OmniLinkPreview.h (no SDL / WebKit): UTF-8, punycode decode (RFC 3492), script classes and
look-alike skeletons, IDN display policy, registrable domain (two labels, three under co.uk-style second levels and a
short list of shared-hosting suffixes such as github.io), "is this link text an address" (domainInText), the URL
shortening, the preview / warning decision, the 250 ms dwell, the pill placement and the setting texts.
Tested by tools/test_link_preview.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_link_preview.cpp -o t && ./t
Shell side: engine/entry/OmniLinkPreviewShell.h (included from OmniFeatures3.h after OmniWebAppsShell.h).

Anchors (each exactly once, whole lines; MARK makes each file idempotent):
  OmniBrowser.cpp          the OmniCaptionStyle.h include line (apply_caption_style.py's): pure include + WKHitTestResultRef.h
                           the omniDialogsInstall forward declaration: our omniLpvInstallUI declaration after it
                           WKPageSetPageUIClient(tab->page, &ui.base) in newTab(): omniLpvInstallUI(ui) before it
  OmniFeatures3.h          the OmniWebAppsShell.h include line (apply_web_apps.py's): our shell after it
                           the omniTmvTick line of omniF3Tick (apply_tab_memory_view.py's): omniLpvTick after it
  OmniBrowserSettings.h    the omniPtrSettingsInput declaration: our declarations after it
                           the omniPtrSettingsRows call: our row after it (next to the pointer rows)
                           the omniSliRowId input line (apply_site_list.py's): ours before it (before the >= 300 rows)
  None of these lines is an anchor of any other apply_*.py in stage1/tools (checked 2026-11-16).
Row id 863 (OmniLinkPreview::kRowId): unused by every apply_*.py and the tree; the script refuses a tree where 863
  already appears outside our own files.
Apply AFTER apply_caption_style.py, apply_tab_memory_view.py, apply_site_list.py and apply_web_apps.py.
usage: apply_link_preview.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_LINK_PREVIEW_V1'
ROW_ID = 863
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_LINK_PREVIEW_V1: the pure part of "Show link address on hover" (no SDL, no WebKit). The shell side is
// OmniLinkPreviewShell.h; the reasons are in tools/apply_link_preview.py. Tested on the host with g++
// (test_link_preview.cpp).
// What it does: an absolute link URL + the link's visible text (both from WebKit's hit test) -> the pill's text
// ("example.com/news/article…", "Script link", "Data link"), the lock (https), and a warning when the visible text
// names a different site than the target (registrable-domain compare), the host uses look-alike letters (IDN shown as
// punycode then), or the URL hides a user name before the host (https://paypal.com@evil.example/).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniLinkPreview {

constexpr uint32_t kDwellMs = 250;        // the pointer rests this long on a link before the pill shows
constexpr size_t kMaxChars = 60;          // code points of the address part of the pill
constexpr size_t kNoteChars = 28;         // code points of the domain named in a warning note
constexpr size_t kUrlMax = 8192;          // bytes kept of the hovered URL (data: URLs can be megabytes)
constexpr size_t kLabelMax = 256;         // bytes kept of the link's text
constexpr int kRowId = 863;               // Browser settings row (apply_link_preview.py refuses a tree that uses 863)
constexpr const char* kFlagName = "link-preview-off.flag";   // present: Off (default On)

// --- UTF-8 ---------------------------------------------------------------------------------------------------------
inline void appendUtf8(std::string& out, uint32_t c)
{
    if (c < 0x80) out += char(c);
    else if (c < 0x800) { out += char(0xC0 | (c >> 6)); out += char(0x80 | (c & 0x3F)); }
    else if (c < 0x10000) { out += char(0xE0 | (c >> 12)); out += char(0x80 | ((c >> 6) & 0x3F)); out += char(0x80 | (c & 0x3F)); }
    else { out += char(0xF0 | (c >> 18)); out += char(0x80 | ((c >> 12) & 0x3F)); out += char(0x80 | ((c >> 6) & 0x3F)); out += char(0x80 | (c & 0x3F)); }
}
// Invalid bytes become U+FFFD (one per byte).
inline std::vector<uint32_t> decodeUtf8(const std::string& s)
{
    std::vector<uint32_t> out;
    for (size_t i = 0; i < s.size();) {
        const unsigned char b = static_cast<unsigned char>(s[i]);
        int n = b < 0x80 ? 0 : (b & 0xE0) == 0xC0 ? 1 : (b & 0xF0) == 0xE0 ? 2 : (b & 0xF8) == 0xF0 ? 3 : -1;
        uint32_t c = n == 0 ? b : n == 1 ? (b & 0x1Fu) : n == 2 ? (b & 0x0Fu) : (b & 0x07u);
        bool ok = n >= 0;
        for (int k = 1; ok && k <= n; ++k) {
            if (i + size_t(k) >= s.size()) { ok = false; break; }
            const unsigned char cb = static_cast<unsigned char>(s[i + size_t(k)]);
            if ((cb & 0xC0) != 0x80) { ok = false; break; }
            c = (c << 6) | (cb & 0x3Fu);
        }
        if (ok && ((n == 1 && c < 0x80) || (n == 2 && c < 0x800) || (n == 3 && (c < 0x10000 || c > 0x10FFFF)) || (c >= 0xD800 && c <= 0xDFFF))) ok = false;
        if (!ok) { out.push_back(0xFFFD); ++i; continue; }
        out.push_back(c);
        i += size_t(n) + 1;
    }
    return out;
}
inline std::string encodeUtf8(const std::vector<uint32_t>& v) { std::string s; for (uint32_t c : v) appendUtf8(s, c); return s; }
inline size_t utf8Length(const std::string& s) { size_t n = 0; for (char c : s) n += (static_cast<unsigned char>(c) & 0xC0) != 0x80; return n; }
// At most maxBytes, never splitting a character.
inline std::string utf8Cut(const std::string& s, size_t maxBytes)
{
    if (s.size() <= maxBytes) return s;
    size_t n = maxBytes;
    while (n > 0 && (static_cast<unsigned char>(s[n]) & 0xC0) == 0x80) --n;
    return s.substr(0, n);
}
inline std::string headChars(const std::string& s, size_t n) { std::vector<uint32_t> v = decodeUtf8(s); if (v.size() > n) v.resize(n); return encodeUtf8(v); }
inline std::string tailChars(const std::string& s, size_t n) { std::vector<uint32_t> v = decodeUtf8(s); if (v.size() > n) v.erase(v.begin(), v.end() - long(n)); return encodeUtf8(v); }
constexpr const char* kEllipsis = "\xe2\x80\xa6";

inline char lowerAscii(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline std::string lowerAscii(const std::string& s) { std::string o = s; for (char& c : o) c = lowerAscii(c); return o; }
inline bool startsWith(const std::string& s, const char* p) { size_t i = 0; for (; p[i]; ++i) if (i >= s.size() || s[i] != p[i]) return false; return true; }
inline bool isAscii(const std::string& s) { for (char c : s) if (static_cast<unsigned char>(c) >= 0x80) return false; return true; }
inline std::vector<std::string> splitDots(const std::string& h)
{
    std::vector<std::string> out;
    size_t a = 0;
    while (true) { const size_t d = h.find('.', a); out.push_back(h.substr(a, d == std::string::npos ? std::string::npos : d - a)); if (d == std::string::npos) break; a = d + 1; }
    return out;
}
inline std::string joinDots(const std::vector<std::string>& v, size_t from)
{
    std::string s;
    for (size_t i = from; i < v.size(); ++i) { if (i > from) s += '.'; s += v[i]; }
    return s;
}

// --- punycode (RFC 3492), decode only --------------------------------------------------------------------------------
// in: the part after "xn--". false for anything malformed (the label is then shown as it is).
inline bool punycodeDecode(const std::string& in, std::vector<uint32_t>& out)
{
    constexpr uint32_t base = 36, tmin = 1, tmax = 26, skew = 38, damp = 700, maxInt = 0x7FFFFFFF;
    out.clear();
    if (in.empty() || in.size() > 59) return false;
    const size_t dash = in.rfind('-');
    size_t pos = 0;
    if (dash != std::string::npos) {
        for (size_t i = 0; i < dash; ++i) {
            const unsigned char c = static_cast<unsigned char>(in[i]);
            if (c >= 0x80) return false;
            out.push_back(c);
        }
        pos = dash + 1;
    }
    auto adapt = [&](uint32_t delta, uint32_t points, bool first) {
        delta = first ? delta / damp : delta / 2;
        delta += delta / points;
        uint32_t k = 0;
        while (delta > ((base - tmin) * tmax) / 2) { delta /= base - tmin; k += base; }
        return k + (base - tmin + 1) * delta / (delta + skew);
    };
    uint32_t n = 128, i = 0, bias = 72;
    if (pos >= in.size()) return false;   // nothing encoded: not an IDN label
    while (pos < in.size()) {
        const uint32_t oldi = i;
        uint32_t w = 1;
        for (uint32_t k = base;; k += base) {
            if (pos >= in.size()) return false;
            const char ch = lowerAscii(in[pos++]);
            const uint32_t digit = ch >= 'a' && ch <= 'z' ? uint32_t(ch - 'a') : ch >= '0' && ch <= '9' ? uint32_t(ch - '0' + 26) : base;
            if (digit >= base) return false;
            if (digit > (maxInt - i) / w) return false;
            i += digit * w;
            const uint32_t t = k <= bias ? tmin : k >= bias + tmax ? tmax : k - bias;
            if (digit < t) break;
            if (w > maxInt / (base - t)) return false;
            w *= base - t;
        }
        const uint32_t count = uint32_t(out.size()) + 1;
        bias = adapt(i - oldi, count, oldi == 0);
        if (i / count > maxInt - n) return false;
        n += i / count;
        i %= count;
        if (n < 0x80 || n > 0x10FFFF || (n >= 0xD800 && n <= 0xDFFF)) return false;
        out.insert(out.begin() + long(i), n);
        ++i;
        if (out.size() > 63) return false;
    }
    return true;
}

// --- scripts and look-alike letters ----------------------------------------------------------------------------------
enum class Script : uint8_t { Common, Latin, Greek, Cyrillic, Armenian, Hebrew, Arabic, Thai, Georgian, Indic, Hangul, Han,
    Hiragana, Katakana, Bopomofo, Other, Bad };
inline Script scriptOf(uint32_t c)
{
    if ((c >= '0' && c <= '9') || c == '-') return Script::Common;
    if (c >= 'a' && c <= 'z') return Script::Latin;
    if (c < 0x80) return Script::Bad;   // upper case / punctuation never survive host canonicalisation
    if (c == 0xD7 || c == 0xF7 || c == 0x131 || c == 0x237 || c == 0x138) return Script::Bad;   // ×, ÷, dotless i / j, kra
    if ((c >= 0xC0 && c <= 0x24F) || (c >= 0x1E00 && c <= 0x1EFF)) return Script::Latin;
    if (c >= 0x370 && c <= 0x3FF) return c == 0x37E || c == 0x387 ? Script::Bad : Script::Greek;   // Greek ";" and "·"
    if (c >= 0x1F00 && c <= 0x1FFF) return Script::Greek;
    if (c >= 0x400 && c <= 0x52F) return Script::Cyrillic;
    if (c >= 0x530 && c <= 0x58F) return Script::Armenian;
    if (c >= 0x5D0 && c <= 0x5FF) return Script::Hebrew;
    if ((c >= 0x620 && c <= 0x64A) || (c >= 0x660 && c <= 0x6FF) || (c >= 0x750 && c <= 0x77F)) return Script::Arabic;
    if (c >= 0x900 && c <= 0xDFF) return Script::Indic;
    if (c >= 0xE00 && c <= 0xE7F) return Script::Thai;
    if (c >= 0x10A0 && c <= 0x10FF) return Script::Georgian;
    if ((c >= 0xAC00 && c <= 0xD7AF) || (c >= 0x1100 && c <= 0x11FF) || (c >= 0x3130 && c <= 0x318F)) return Script::Hangul;
    if (c >= 0x3041 && c <= 0x309F) return Script::Hiragana;
    if (c >= 0x30A0 && c <= 0x30FF) return Script::Katakana;   // (30FC, the long-vowel mark, is used with both kana)
    if (c >= 0x3105 && c <= 0x312F) return Script::Bopomofo;
    if ((c >= 0x4E00 && c <= 0x9FFF) || (c >= 0x3400 && c <= 0x4DBF) || (c >= 0x20000 && c <= 0x2A6DF) || c == 0x3005 || c == 0x3007)
        return Script::Han;
    // Combining marks, IPA, spacing modifiers, small capitals, zero-width / bidi controls, general punctuation, letter-like
    // and number forms (ⅼ), full-width forms, mathematical letters: spoofing material, never shown as Unicode.
    if ((c >= 0x250 && c <= 0x36F) || (c >= 0x1D00 && c <= 0x1DFF) || (c >= 0x2000 && c <= 0x2BFF) || (c >= 0x3000 && c <= 0x303F)
        || (c >= 0xFE00 && c <= 0xFE0F) || (c >= 0xFF00 && c <= 0xFFEF) || c == 0xFEFF || c == 0xAD || c == 0xFFFD
        || (c >= 0x1D400 && c <= 0x1D7FF) || (c >= 0xE0000 && c <= 0xE007F))
        return Script::Bad;
    return Script::Other;
}
// The ASCII letter a character is commonly mistaken for (0: none). Lower case only (hosts are lower case).
inline uint32_t confusable(uint32_t c)
{
    switch (c) {
    // Cyrillic
    case 0x430: return 'a'; case 0x435: return 'e'; case 0x43E: return 'o'; case 0x440: return 'p'; case 0x441: return 'c';
    case 0x443: return 'y'; case 0x445: return 'x'; case 0x455: return 's'; case 0x456: return 'i'; case 0x458: return 'j';
    case 0x501: return 'd'; case 0x4CF: return 'l'; case 0x4BB: return 'h'; case 0x51B: return 'q'; case 0x51D: return 'w';
    case 0x4AF: return 'y'; case 0x43A: return 'k'; case 0x432: return 'b'; case 0x43D: return 'h'; case 0x43F: return 'n';
    case 0x442: return 't'; case 0x433: return 'r'; case 0x450: return 'e'; case 0x451: return 'e'; case 0x457: return 'i';
    case 0x44C: return 'b'; case 0x4E9: return 'o'; case 0x4D5: return 'a';
    // Greek
    case 0x3B1: return 'a'; case 0x3BF: return 'o'; case 0x3BD: return 'v'; case 0x3B9: return 'i'; case 0x3BA: return 'k';
    case 0x3C1: return 'p'; case 0x3C4: return 't'; case 0x3C5: return 'u'; case 0x3C7: return 'x'; case 0x3F2: return 'c';
    case 0x3B5: return 'e'; case 0x3B3: return 'y'; case 0x3F3: return 'j'; case 0x3C9: return 'w';
    // Armenian
    case 0x561: return 'w'; case 0x570: return 'h'; case 0x578: return 'n'; case 0x57D: return 'u'; case 0x585: return 'o';
    case 0x563: return 'q'; case 0x566: return 'q'; case 0x584: return 'f';
    // Latin look-alikes
    case 0x131: return 'i'; case 0x237: return 'j'; case 0x251: return 'a'; case 0x261: return 'g'; case 0x269: return 'i';
    case 0x29F: return 'l'; case 0x1D0F: return 'o'; case 0x1D04: return 'c'; case 0x2170: return 'i'; case 0x217C: return 'l';
    case 0x217D: return 'c'; case 0x217E: return 'd'; case 0x217F: return 'm';
    default: break;
    }
    if (c >= 0xFF41 && c <= 0xFF5A) return 'a' + (c - 0xFF41);   // full-width a-z
    if (c >= 0xFF10 && c <= 0xFF19) return '0' + (c - 0xFF10);
    return 0;
}
// A lower-case comparison key in which look-alikes collapse: confusable letters -> ASCII, 0 -> o, 1 -> l,
// "rn" -> "m", "vv" -> "w", "cl" -> "d". Two names with the same skeleton look the same at a glance.
inline std::string skeleton(const std::string& s)
{
    std::string a;
    for (uint32_t c : decodeUtf8(s)) {
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        const uint32_t m = c < 0x80 ? c : confusable(c);
        if (m) {
            const char ch = char(m);
            a += ch == '0' ? 'o' : ch == '1' ? 'l' : ch;
        } else appendUtf8(a, c);
    }
    std::string out;
    for (size_t i = 0; i < a.size(); ++i) {
        if (i + 1 < a.size() && a[i] == 'r' && a[i + 1] == 'n') { out += 'm'; ++i; }
        else if (i + 1 < a.size() && a[i] == 'v' && a[i + 1] == 'v') { out += 'w'; ++i; }
        else if (i + 1 < a.size() && a[i] == 'c' && a[i + 1] == 'l') { out += 'd'; ++i; }
        else out += a[i];
    }
    return out;
}

struct LabelView { std::string unicode; bool idn = false, decodable = true, deceptive = false; };
// One host label (lower-case ASCII as WebKit canonicalises it). asciiTld: the host's last label is ASCII (a whole
// Cyrillic / Greek / Armenian label made only of Latin look-alikes is allowed under its own script's TLD only).
inline LabelView viewLabel(const std::string& label, bool asciiTld)
{
    LabelView v;
    v.unicode = label;
    if (label.size() < 5 || !startsWith(lowerAscii(label), "xn--")) return v;
    v.idn = true;
    std::vector<uint32_t> cps;
    if (!punycodeDecode(label.substr(4), cps)) { v.decodable = false; return v; }
    v.unicode = encodeUtf8(cps);
    bool has[size_t(Script::Bad) + 1] = {};
    for (uint32_t c : cps) has[size_t(scriptOf(c))] = true;
    if (has[size_t(Script::Bad)]) { v.deceptive = true; return v; }
    int scripts = 0;
    for (size_t s = size_t(Script::Latin); s < size_t(Script::Bad); ++s) scripts += has[s];
    const bool latin = has[size_t(Script::Latin)];
    const bool cjk = has[size_t(Script::Han)] || has[size_t(Script::Hiragana)] || has[size_t(Script::Katakana)]
        || has[size_t(Script::Hangul)] || has[size_t(Script::Bopomofo)];
    if (scripts > 1) {
        // Allowed mixes (as browsers' IDN policies): Latin + Han + kana (Japanese), Latin + Han + Hangul (Korean),
        // Latin + Han + Bopomofo (Chinese). Everything else mixing scripts (Latin + Cyrillic ...) is a spoof sign.
        const bool kana = has[size_t(Script::Hiragana)] || has[size_t(Script::Katakana)];
        const bool japanese = !has[size_t(Script::Hangul)] && !has[size_t(Script::Bopomofo)];
        const bool korean = !kana && !has[size_t(Script::Bopomofo)];
        const bool chinese = !kana && !has[size_t(Script::Hangul)];
        int other = scripts - latin;
        for (Script s : { Script::Han, Script::Hiragana, Script::Katakana, Script::Hangul, Script::Bopomofo }) other -= has[size_t(s)];
        if (!(cjk && other == 0 && (japanese || korean || chinese))) v.deceptive = true;
        return v;
    }
    // One script: a word written only with letters that look Latin (аррӏе = "apple") is a spoof under an ASCII TLD.
    if (asciiTld && (has[size_t(Script::Cyrillic)] || has[size_t(Script::Greek)] || has[size_t(Script::Armenian)])) {
        bool allLookLatin = true;
        for (uint32_t c : cps) if (c >= 0x80 && !confusable(c)) { allLookLatin = false; break; }
        if (allLookLatin) v.deceptive = true;
    }
    return v;
}

struct HostView { std::string shown, unicode; bool idn = false, deceptive = false; };
// shown: Unicode when every IDN label is safe to show, else the ASCII (punycode) host. unicode: always decoded
// (for comparing with what the link text says).
inline HostView viewHost(const std::string& asciiHost)
{
    HostView h;
    const std::vector<std::string> labels = splitDots(asciiHost);
    const bool asciiTld = labels.empty() || !startsWith(lowerAscii(labels.back()), "xn--");
    std::vector<std::string> uni;
    for (const std::string& l : labels) {
        const LabelView v = viewLabel(l, asciiTld);
        h.idn |= v.idn;
        h.deceptive |= v.deceptive || (v.idn && !v.decodable);
        uni.push_back(v.unicode);
    }
    h.unicode = joinDots(uni, 0);
    h.shown = h.deceptive ? asciiHost : h.unicode;
    return h;
}

// --- hosts and sites -------------------------------------------------------------------------------------------------
inline bool isIPv4(const std::string& h)
{
    int parts = 0, digits = 0, value = 0;
    for (size_t i = 0; i <= h.size(); ++i) {
        if (i == h.size() || h[i] == '.') {
            if (!digits || value > 255) return false;
            ++parts; digits = 0; value = 0;
            continue;
        }
        if (h[i] < '0' || h[i] > '9' || ++digits > 3) return false;
        value = value * 10 + (h[i] - '0');
    }
    return parts == 4;
}
inline bool isIPLiteral(const std::string& h) { return isIPv4(h) || h.find(':') != std::string::npos || (!h.empty() && h[0] == '['); }

// Suffixes under which every name is a different owner (a small part of the Public Suffix List's private section:
// the ones a phishing page is likely to be hosted on).
inline bool sharedSuffix(const std::string& s)
{
    static const char* const k[] = { "github.io", "gitlab.io", "blogspot.com", "netlify.app", "herokuapp.com", "vercel.app",
        "pages.dev", "workers.dev", "web.app", "firebaseapp.com", "appspot.com", "azurewebsites.net", "cloudfront.net",
        "wordpress.com", "tumblr.com", "wixsite.com", "weebly.com", "glitch.me", "onrender.com", "fly.dev", "surge.sh",
        "neocities.org", "substack.com", "myshopify.com", "000webhostapp.com", "ngrok.io", "ngrok-free.app", "duckdns.org",
        "no-ip.org", "translate.goog", "sharepoint.com", "r2.dev", "repl.co", "s3.amazonaws.com", "blogspot.co.uk" };
    for (const char* e : k) if (s == e) return true;
    return false;
}
// Second levels under a country code that are registries' own (co.uk, com.au, ne.jp ...).
inline bool ccSecondLevel(const std::string& sld)
{
    static const char* const k[] = { "co", "com", "net", "org", "gov", "edu", "ac", "ltd", "plc", "sch", "nhs", "ne", "or", "go",
        "gob", "gouv", "nic", "mil", "info", "biz", "web", "me", "nom", "gen", "firm", "ind", "res", "lg", "ed", "gr" };
    for (const char* e : k) if (sld == e) return true;
    return false;
}
// The registrable domain ("site") of a host, approximately as the Public Suffix List would give it: the last two
// labels, three under co.uk-style registry second levels and under shared hosting suffixes (alice.github.io).
// Works on ASCII or decoded Unicode hosts (labels are only compared as strings). IP literals stay whole.
inline std::string registrableDomain(const std::string& host0)
{
    std::string host = lowerAscii(host0);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || isIPLiteral(host)) return host;
    const std::vector<std::string> l = splitDots(host);
    for (const std::string& x : l) if (x.empty()) return host;
    const size_t n = l.size();
    if (n <= 2) return host;
    size_t keep = 2;
    if (sharedSuffix(joinDots(l, n - 2))) keep = 3;
    else if (n >= 3 && sharedSuffix(joinDots(l, n - 3))) keep = 4;
    else if (l[n - 1].size() == 2 && ccSecondLevel(l[n - 2])) keep = 3;
    if (n <= keep) return host;
    return joinDots(l, n - keep);
}
// Link shorteners and outbound-link redirectors: their links show the destination as text by design (t.co on X/Twitter,
// out.reddit.com ...), so a text/target difference there is not a warning sign.
inline bool isRedirector(const std::string& host)
{
    static const char* const k[] = { "t.co", "bit.ly", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly", "lnkd.in", "is.gd", "rb.gy",
        "cutt.ly", "shorturl.at", "tiny.cc", "youtu.be", "amzn.to", "a.co", "fb.me", "l.facebook.com", "lm.facebook.com",
        "out.reddit.com", "l.instagram.com", "href.li", "dlvr.it", "trib.al", "redirect.viglink.com", "flip.it", "spoti.fi",
        "apple.co", "g.co", "msft.it", "steamcommunity.com", "discord.gg", "x.gd", "click.redditmail.com", "l.messenger.com" };
    for (const char* e : k) if (host == e) return true;
    return false;
}

// --- what the link's text claims -------------------------------------------------------------------------------------
inline bool commonTld(const std::string& t)
{
    // Plain text "readme.md" or "setup.py" is a file name, not a site: such TLDs need a scheme / www. / path to count.
    static const char* const k[] = { "com", "net", "org", "edu", "gov", "mil", "int", "info", "biz", "io", "co", "me", "tv",
        "app", "dev", "ai", "uk", "us", "ca", "de", "fr", "es", "it", "nl", "be", "ch", "at", "se", "no", "dk", "fi", "pl",
        "ru", "ua", "cz", "sk", "hu", "ro", "bg", "gr", "pt", "ie", "jp", "cn", "kr", "tw", "hk", "sg", "in", "au", "nz",
        "br", "ar", "mx", "cl", "za", "tr", "il", "ae", "sa", "eg", "ng", "ke", "vn", "th", "id", "my", "ph", "pk", "eu",
        "xyz", "online", "site", "shop", "store", "top", "club", "live", "news", "blog", "page", "tech", "cloud", "gg",
        "ly", "to", "fm", "am", "cc", "ws", "asia", "mobi", "name", "pro", "moe", "link", "icu", "one", "lt", "lv", "ee",
        "is", "lu", "si", "hr", "rs", "by", "kz", "ir", "co.uk", "org.uk", "com.au", "co.jp" };
    for (const char* e : k) if (t == e) return true;
    return false;
}
// The host the link's visible text names when the whole text is an address ("paypal.com", "www.paypal.com/login",
// "https://PayPal.com"), lower-cased; empty when the text is anything else (words, a title, an e-mail address).
inline std::string domainInText(const std::string& label0)
{
    std::string s = label0;
    auto space = [](const std::string& x, size_t i) -> size_t {   // bytes of a white-space character at i (0: none)
        const unsigned char c = static_cast<unsigned char>(x[i]);
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') return 1;
        if (c == 0xC2 && i + 1 < x.size() && static_cast<unsigned char>(x[i + 1]) == 0xA0) return 2;   // NBSP
        if (c == 0xE2 && i + 2 < x.size() && static_cast<unsigned char>(x[i + 1]) == 0x80
            && (static_cast<unsigned char>(x[i + 2]) <= 0x8B || static_cast<unsigned char>(x[i + 2]) == 0xAF)) return 3;   // U+2000-200B, 202F
        return 0;
    };
    size_t a = 0;
    while (a < s.size()) { const size_t n = space(s, a); if (!n) break; a += n; }
    s = s.substr(a);
    while (!s.empty()) {   // trailing white space
        size_t back = 0;
        for (size_t k = 1; k <= 3 && k <= s.size(); ++k) if (space(s, s.size() - k) == k) { back = k; break; }
        if (!back) break;
        s.resize(s.size() - back);
    }
    if (s.empty() || s.size() > 200) return std::string();
    for (size_t i = 0; i < s.size(); ++i) if (space(s, i) || s[i] == '@') return std::string();
    bool explicitSite = false;
    const std::string low = lowerAscii(s);
    if (startsWith(low, "https://")) { s = s.substr(8); explicitSite = true; }
    else if (startsWith(low, "http://")) { s = s.substr(7); explicitSite = true; }
    const size_t cut = s.find_first_of("/?#");
    if (cut != std::string::npos) { if (cut + 1 < s.size()) explicitSite = true; s = s.substr(0, cut); }
    const size_t colon = s.rfind(':');
    if (colon != std::string::npos) {   // :port
        for (size_t i = colon + 1; i < s.size(); ++i) if (s[i] < '0' || s[i] > '9') return std::string();
        s = s.substr(0, colon);
    }
    if (!s.empty() && s.back() == '.') s.pop_back();
    // "examp…" style display truncation inside the host: what is left can't be trusted.
    if (s.find(kEllipsis) != std::string::npos || s.find("..") != std::string::npos) return std::string();
    s = lowerAscii(s);
    if (startsWith(s, "www.")) explicitSite = true;
    const std::vector<std::string> labels = splitDots(s);
    if (labels.size() < 2) return std::string();
    for (const std::string& l : labels) {
        if (l.empty() || l.size() > 63 || l.front() == '-' || l.back() == '-') return std::string();
        for (char c : l) {
            const unsigned char u = static_cast<unsigned char>(c);
            if (!(u >= 0x80 || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return std::string();
        }
    }
    const std::string& tld = labels.back();
    if (!isAscii(tld) || startsWith(tld, "xn--")) return s;   // an internationalised TLD is a site, not a file
    for (char c : tld) if (c < 'a' || c > 'z') return std::string();   // "1.2.3", "v2.0"
    if (tld.size() < 2 || tld.size() > 24) return std::string();
    if (!explicitSite && !commonTld(tld)) return std::string();
    return s;
}
// A Unicode-or-punycode host -> its Unicode spelling (each xn-- label decoded when it can be).
inline std::string unicodeHost(const std::string& h)
{
    std::vector<std::string> l = splitDots(h);
    for (std::string& x : l) {
        if (x.size() < 5 || !startsWith(x, "xn--")) continue;
        std::vector<uint32_t> cps;
        if (punycodeDecode(x.substr(4), cps)) x = encodeUtf8(cps);
    }
    return joinDots(l, 0);
}

// --- URLs ----------------------------------------------------------------------------------------------------------
struct Url { bool ok = false, hierarchical = false; std::string scheme, user, host, port, path, query, fragment; };
inline Url parseUrl(const std::string& url)
{
    Url u;
    const size_t colon = url.find(':');
    if (colon == std::string::npos || colon == 0) return u;
    for (size_t i = 0; i < colon; ++i) {
        const char c = url[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (i && ((c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.')))) return u;
    }
    u.scheme = lowerAscii(url.substr(0, colon));
    u.ok = true;
    std::string rest = url.substr(colon + 1);
    if (rest.compare(0, 2, "//") != 0) { u.path = rest; return u; }
    u.hierarchical = true;
    rest = rest.substr(2);
    const size_t end = rest.find_first_of("/?#");
    std::string auth = rest.substr(0, end);
    rest = end == std::string::npos ? std::string() : rest.substr(end);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) { u.user = auth.substr(0, at); auth = auth.substr(at + 1); }
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos) { u.ok = false; return u; }
        u.host = auth.substr(0, close + 1);
        if (close + 1 < auth.size() && auth[close + 1] == ':') u.port = auth.substr(close + 2);
    } else {
        const size_t pc = auth.rfind(':');
        u.host = auth.substr(0, pc);
        if (pc != std::string::npos) u.port = auth.substr(pc + 1);
    }
    u.host = lowerAscii(u.host);
    const size_t hash = rest.find('#');
    if (hash != std::string::npos) { u.fragment = rest.substr(hash + 1); rest = rest.substr(0, hash); }
    const size_t q = rest.find('?');
    if (q != std::string::npos) { u.query = rest.substr(q + 1); rest = rest.substr(0, q); }
    u.path = rest;
    return u;
}

// host (never cut in the middle: when too long its left part goes, keeping the registrable end visible) + rest.
inline std::string shorten(const std::string& host, const std::string& rest, size_t maxChars = kMaxChars)
{
    const size_t hl = utf8Length(host), rl = utf8Length(rest);
    if (hl + rl <= maxChars) return host + rest;
    if (hl + 1 >= maxChars) return kEllipsis + tailChars(host, maxChars - 1);
    const size_t room = maxChars - hl - 1;   // characters of rest before the ellipsis
    return host + headChars(rest, room) + kEllipsis;
}

enum class Kind : uint8_t { None, Web, Script, Data, Other };
enum class Reason : uint8_t { None, TextMismatch, LookAlike, DeceptiveIdn, UserInfo };
struct Preview {
    Kind kind = Kind::None;
    bool secure = false, warn = false;
    Reason reason = Reason::None;
    std::string text;   // the address part ("example.com/news/article…")
    std::string note;   // with warn: why ("not paypal.com", "look-alike letters", "hidden user name")
    std::string shown() const { return note.empty() ? text : text + " \xc2\xb7 " + note; }
};
inline std::string elideLeft(const std::string& s, size_t n) { return utf8Length(s) <= n ? s : kEllipsis + tailChars(s, n - 1); }

// url: WebKit's absolute link URL; label: the link's text content (may be empty, e.g. an image link).
inline Preview make(const std::string& url0, const std::string& label)
{
    Preview p;
    size_t a = 0;
    while (a < url0.size() && static_cast<unsigned char>(url0[a]) <= 0x20) ++a;
    const std::string url = url0.substr(a);
    if (url.empty()) return p;
    const Url u = parseUrl(url);
    if (u.ok && u.scheme == "javascript") { p.kind = Kind::Script; p.text = "Script link"; return p; }
    if (u.ok && u.scheme == "data") { p.kind = Kind::Data; p.text = "Data link"; return p; }
    const bool web = u.ok && u.hierarchical && (u.scheme == "http" || u.scheme == "https" || u.scheme == "ftp") && !u.host.empty();
    if (!web) {
        p.kind = Kind::Other;
        std::string s;
        for (char c : url) s += static_cast<unsigned char>(c) < 0x20 ? ' ' : c;
        p.text = utf8Length(s) > kMaxChars ? headChars(s, kMaxChars - 1) + kEllipsis : s;
        return p;
    }
    p.kind = Kind::Web;
    p.secure = u.scheme == "https";
    const HostView hv = viewHost(u.host);
    std::string host = hv.shown;
    if (startsWith(host, "www.") && host.find('.', 4) != std::string::npos) host = host.substr(4);
    const bool defaultPort = u.port.empty() || (u.scheme == "http" && u.port == "80") || (u.scheme == "https" && u.port == "443")
        || (u.scheme == "ftp" && u.port == "21");
    if (!defaultPort) host += ":" + u.port;
    std::string rest = u.path == "/" ? std::string() : u.path;
    for (char& c : rest) if (static_cast<unsigned char>(c) < 0x20) c = ' ';
    if (!u.query.empty()) rest += std::string("?") + kEllipsis;
    p.text = shorten(host, rest);
    // Warnings, most telling first: the text names another site; look-alike letters; a user name before the host.
    const std::string claimed = domainInText(label);
    if (!claimed.empty() && !isRedirector(u.host)) {
        const std::string claimedSite = registrableDomain(unicodeHost(claimed));
        const std::string targetSite = registrableDomain(hv.unicode);
        if (claimedSite != targetSite) {
            p.reason = skeleton(claimedSite) == skeleton(targetSite) ? Reason::LookAlike : Reason::TextMismatch;
            std::string c = unicodeHost(claimed);
            if (startsWith(c, "www.") && c.find('.', 4) != std::string::npos) c = c.substr(4);
            p.note = "not " + elideLeft(c, kNoteChars);
        }
    }
    if (p.reason == Reason::None && hv.deceptive) { p.reason = Reason::DeceptiveIdn; p.note = "look-alike letters"; }
    if (p.reason == Reason::None && !u.user.empty()) {
        p.reason = Reason::UserInfo;
        const size_t colon = u.user.find(':');
        const std::string named = domainInText(u.user.substr(0, colon));
        p.note = named.empty() ? std::string("hidden user name") : "not " + elideLeft(named, kNoteChars);
    }
    p.warn = p.reason != Reason::None;
    return p;
}

// --- the 250 ms rest -------------------------------------------------------------------------------------------------
// Fed once per shell pass: hovered = the link under the pointer ("" none, or not allowed now), moved = the pointer moved
// since the last pass. Shows after the pointer rested kDwellMs on one link; stays while the pointer moves within that
// link; a different link (or none) hides it at once.
struct Dwell {
    std::string url;
    uint32_t since = 0;
    bool shown = false;
    void reset() { url.clear(); since = 0; shown = false; }
    bool update(const std::string& hovered, bool moved, uint32_t now)
    {
        if (hovered.empty()) { reset(); return false; }
        if (hovered != url) { url = hovered; since = now; shown = false; return false; }
        if (!shown) {
            if (moved) since = now;
            else if (uint32_t(now - since) >= kDwellMs) shown = true;
        }
        return shown;
    }
};

// --- placement (layout px) -------------------------------------------------------------------------------------------
struct Rect { int x = 0, y = 0, w = 0, h = 0; };
// Bottom-left of the page area, just above its bottom edge (pageBottom: where the page ends and the bottom button bar,
// when shown, begins - the pill never reaches that bar). Moves to the bottom-right while the pointer is on or near it,
// and above the centred notice toast when the two would overlap (toastX1 <= toastX0: no toast).
inline Rect place(int w, int h, int screenW, int pageBottom, int px, int py, int toastX0, int toastX1, int toastTop)
{
    constexpr int margin = 12, gap = 10, near = 24;
    Rect r;
    r.w = w; r.h = h; r.x = margin; r.y = pageBottom - gap - h;
    auto close = [&](const Rect& q) { return px >= q.x - near && px < q.x + q.w + near && py >= q.y - near && py < q.y + q.h + near; };
    if (close(r)) r.x = screenW - margin - w;
    if (toastX1 > toastX0 && r.x < toastX1 + 8 && r.x + r.w > toastX0 - 8 && r.y + r.h > toastTop - 8) r.y = toastTop - 8 - h;
    return r;
}

// --- texts -----------------------------------------------------------------------------------------------------------
inline const char* settingLabel() { return "Show link address on hover"; }
inline const char* settingValue(bool on) { return on ? "On" : "Off"; }
inline const char* settingDetail() { return "Rest the pointer on a link to see where it goes (bottom left). Amber: the link text names a different site"; }
inline const char* toggledNotice(bool on) { return on ? "Link address on hover: On" : "Link address on hover: Off"; }

}   // namespace OmniLinkPreview
'''

SHELL = r'''// OMNI_LINK_PREVIEW_V1: "Show link address on hover" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace) after OmniWebAppsShell.h. The pure part is OmniLinkPreview.h; the reasons are in
// tools/apply_link_preview.py. Main thread only (WebKit's UI client callbacks and the shell pass both run there).
// Nothing is stored or logged: the hovered link lives in memory until the pointer leaves it (private tabs alike).
#pragma once

namespace OLPV = OmniLinkPreview;
struct OmniLpvState {
    int on = -1;                  // -1: not read yet (absent link-preview-off.flag = On)
    WKPageRef page = nullptr;     // the page the last hover came from (only compared, never used)
    std::string tabUrl;           // the active tab's address when that hover came (a navigation drops it)
    std::string url, label;       // the link under the pointer and its text ("" none)
    OLPV::Preview pv;
    float px = -1, py = -1;       // the pointer at the last pass
    OLPV::Dwell dwell;
};
static OmniLpvState omniLpv;

static bool omniLpvOn()
{
    if (omniLpv.on < 0) omniLpv.on = access(omniData(OLPV::kFlagName).c_str(), F_OK) == 0 ? 0 : 1;
    return omniLpv.on == 1;
}
static void omniLpvForget()
{
    if (omniLpv.dwell.shown) omniShellDirty = true;
    omniLpv.page = nullptr; omniLpv.url.clear(); omniLpv.label.clear(); omniLpv.pv = OLPV::Preview {}; omniLpv.dwell.reset();
}
// WebKit: EventHandler::mouseMoved -> Chrome::mouseDidMoveOverElement -> WebPageProxy -> here, for every pointer move
// mouse() sends (WKPageHandleMouseEvent motion, no button) and for WebKit's own fake moves after scrolling / layout.
static void omniLpvHover(WKPageRef page, WKHitTestResultRef hit, WKEventModifiers, WKTypeRef, const void*)
{
    if (!omniLpvOn() || omniTestMode()) return;
    Tab* t = active();
    if (!t || t->page != page) return;
    std::string url, label;
    if (hit) {
        auto link = adoptWK(WKHitTestResultCopyAbsoluteLinkURL(hit));
        if (link) url = OmniTest::toStd(adoptWK(WKURLCopyString(link.get())).get());
        if (!url.empty()) label = OmniTest::toStd(adoptWK(WKHitTestResultCopyLinkLabel(hit)).get());
    }
    url = OLPV::utf8Cut(url, OLPV::kUrlMax);
    label = OLPV::utf8Cut(label, OLPV::kLabelMax);
    if (omniLpv.page != page) omniLpv.tabUrl = t->url;
    omniLpv.page = page;
    if (url == omniLpv.url && label == omniLpv.label) return;
    omniLpv.url = std::move(url);
    omniLpv.label = std::move(label);
    omniLpv.pv = omniLpv.url.empty() ? OLPV::Preview {} : OLPV::make(omniLpv.url, omniLpv.label);
}
static void omniLpvInstallUI(WKPageUIClientV19& ui) { ui.mouseDidMoveOverElement = omniLpvHover; }

// Where the pill may show: the pointer on the page, nothing on top of it (menus, panels, dialogs, the keyboard).
static bool omniLpvPlaceOk()
{
    Tab* t = active();
    return t && !t->crashed && !pageFullscreen && !settingsOpen && !editing && !omniOverlayOpen() && omniFxStack.empty()
        && pointerY >= omniPageTop() && pointerY < omniPageBottom();
}
// omniF3Tick, every pass: the 250 ms rest, stale hovers (another tab, a navigation).
static void omniLpvTick(uint32_t now)
{
    Tab* t = active();
    if (omniLpv.page && (!t || t->page != omniLpv.page || t->url != omniLpv.tabUrl)) omniLpvForget();
    const bool moved = pointerX != omniLpv.px || pointerY != omniLpv.py;
    omniLpv.px = pointerX; omniLpv.py = pointerY;
    const bool allowed = omniLpvOn() && !omniTestMode() && omniLpv.pv.kind != OLPV::Kind::None && omniLpvPlaceOk();
    const bool was = omniLpv.dwell.shown;
    omniLpv.dwell.update(allowed ? omniLpv.url : std::string(), moved, now);
    if (omniLpv.dwell.shown != was) omniShellDirty = true;
}

// --- the pill (an overlay layer that never takes input) -------------------------------------------------------------
static bool omniLpvShown() { return omniLpv.dwell.shown && omniLpv.pv.kind != OLPV::Kind::None && omniLpvOn() && omniLpvPlaceOk(); }
static void omniLpvDraw()
{
    const OLPV::Preview& pv = omniLpv.pv;
    const OmniTheme& T = omniTheme();
    const int iconW = pv.warn || pv.secure ? 20 : 0, padL = 12, padR = 14, h = 32;
    const int maxW = std::min(560, width * 45 / 100);
    const std::string shown = omniFit(omniSmall, pv.shown(), physical(maxW - padL - padR - iconW));
    const int w = padL + iconW + int(omniTextWidthPx(omniSmall, shown) / displayScale + 0.5) + padR;
    // The centred notice toast (same size rule as its own draw): the pill goes above it when they would overlap.
    int toastX0 = 0, toastX1 = 0;
    if (!omniToastText.empty()) {
        const int tw = int(omniTextWidthPx(omniSmall, omniFit(omniSmall, omniToastText, physical(940))) / displayScale + 0.5) + 48 + 28;
        toastX0 = (width - tw) / 2; toastX1 = toastX0 + tw;
    }
    const int pageBottom = omniPageBottom();
    const OLPV::Rect r = OLPV::place(w, h, width, pageBottom, int(pointerX), int(pointerY), toastX0, toastX1,
        std::min(pageBottom, height - bottom) - 18 - 44);
    const SDL_Color edge = pv.warn ? omniWarn : omniMix(T.raised, T.line, 0.6f);
    omniShadow(r.x, r.y, r.w, r.h, r.h / 2, 10, 90, 2);
    fillRounded(r.x, r.y, r.w, r.h, r.h / 2, edge);
    fillRounded(r.x + 1, r.y + 1, r.w - 2, r.h - 2, r.h / 2 - 1, pv.warn ? omniMix(T.raised, omniWarn, 0.12f) : T.raised);
    const float cy = r.y + r.h / 2.f;
    if (pv.warn) { omniDisc(r.x + padL + 8, cy, 8, omniWarn); omniIcon(omniIconAlert, r.x + padL + 8, cy, T.bg); }
    else if (pv.secure) omniIcon(omniIconLock, r.x + padL + 7, cy, T.accent);
    omniLabel(shown, float(r.x + padL + iconW), cy, omniSmall, pv.warn ? omniWarn : T.ink);
}
[[maybe_unused]] static const bool omniLpvLayer = [] {
    omniOverlayLayers().push_back({ omniLpvShown, nullptr, nullptr, nullptr, omniLpvDraw, false });
    return true;
}();

// --- Browser settings ------------------------------------------------------------------------------------------------
static void omniLpvSettingsRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = OLPV::kRowId; r.label = OLPV::settingLabel(); r.value = OLPV::settingValue(omniLpvOn());
    r.stepper = true; r.detail = OLPV::settingDetail();
    p.rows.push_back(r);
}
static bool omniLpvSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData(OLPV::kFlagName);
    const bool on = !omniLpvOn();
    if (on) unlink(flag.c_str());
    else if (FILE* f = fopen(flag.c_str(), "w")) { fputs("off\n", f); fclose(f); }
    omniLpv.on = on ? 1 : 0;
    if (!on) omniLpvForget();
    notice(OLPV::toggledNotice(on));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n',
         '#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n'
         '#include "OmniLinkPreview.h" // OMNI_LINK_PREVIEW_V1: link address on hover: shortening, IDN, look-alike check (pure)\n'
         '#include <WebKit/WKHitTestResultRef.h> // OMNI_LINK_PREVIEW_V1: link URL / text under the pointer\n'),
        ('static void omniDialogsInstall(WKPageUIClientV19& ui);\n',
         'static void omniDialogsInstall(WKPageUIClientV19& ui);\n'
         'static void omniLpvInstallUI(WKPageUIClientV19& ui); // OMNI_LINK_PREVIEW_V1 (OmniLinkPreviewShell.h)\n'),
        ('    WKPageSetPageUIClient(tab->page, &ui.base);\n',
         '    omniLpvInstallUI(ui); // OMNI_LINK_PREVIEW_V1: mouseDidMoveOverElement (link address on hover)\n'
         '    WKPageSetPageUIClient(tab->page, &ui.base);\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n',
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'
         '#include "OmniLinkPreviewShell.h" // OMNI_LINK_PREVIEW_V1\n'),
        ('    omniTmvTick(now);   // OMNI_TAB_MEMORY_VIEW_V1: Memory panel numbers every 2 s while it is on top\n',
         '    omniTmvTick(now);   // OMNI_TAB_MEMORY_VIEW_V1: Memory panel numbers every 2 s while it is on top\n'
         '    omniLpvTick(now);   // OMNI_LINK_PREVIEW_V1: the 250 ms rest of the link-address pill\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniPtrSettingsInput(int id, int b);\n',
         'static bool omniPtrSettingsInput(int id, int b);\n'
         'static void omniLpvSettingsRow(OmniFxPanel& p); // OMNI_LINK_PREVIEW_V1: "Show link address on hover" (OmniLinkPreviewShell.h)\n'
         'static bool omniLpvSettingsInput(int b);\n'),
        ('    omniPtrSettingsRows(p); // OMNI_POINTER_STYLE_V1: style, size, colour, outline, opacity\n',
         '    omniPtrSettingsRows(p); // OMNI_POINTER_STYLE_V1: style, size, colour, outline, opacity\n'
         '    omniLpvSettingsRow(p); // OMNI_LINK_PREVIEW_V1: Show link address on hover (On / Off)\n'),
        ('    if (r.id == omniSliRowId) return omniSliSettingsInput(b); // OMNI_SITE_LIST_V1 (before the >= 300 rows)\n',
         '    if (r.id == OmniLinkPreview::kRowId) return omniLpvSettingsInput(b); // OMNI_LINK_PREVIEW_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniSliRowId) return omniSliSettingsInput(b); // OMNI_SITE_LIST_V1 (before the >= 300 rows)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': 'OMNI_CAPTION_STYLE_V1', 'OmniFeatures3.h': 'OMNI_TAB_MEMORY_VIEW_V1',
         'OmniBrowserSettings.h': 'OMNI_SITE_LIST_V1'}
OURS = ('OmniLinkPreview.h', 'OmniLinkPreviewShell.h')


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
    if NEEDS[name] not in s:
        sys.exit('%s: %s missing: apply its script first' % (name, NEEDS[name]))
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def check_row_id():
    """Refuse a tree where our row id is already taken (anything but our own files and lines)."""
    pat = re.compile(r'(?<![\w.])%d(?![\w.])' % ROW_ID)
    for p in sorted(root.iterdir()):
        if p.suffix not in ('.h', '.cpp', '.inc') or p.name in OURS:
            continue
        t = p.read_bytes().decode('utf-8', 'replace')
        for n, (line, code) in enumerate(zip(t.split('\n'), cpp_code(t).split('\n')), 1):
            if MARK not in line and pat.search(code):
                sys.exit('%s:%d: row id %d already used: %s' % (p.name, n, ROW_ID, line.strip()[:120]))


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
    if 'kRowId = %d' % ROW_ID not in PURE:
        sys.exit('internal: ROW_ID and OmniLinkPreview::kRowId differ')
    for name, edits in EDITS.items():   # every anchor (and the row id) is checked before anything is written
        check(name, edits)
    check_row_id()
    msgs = [write_new('OmniLinkPreview.h', PURE, 'OmniCaptionStyle.h'),
            write_new('OmniLinkPreviewShell.h', SHELL, 'OmniWebAppsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
