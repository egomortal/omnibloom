#!/usr/bin/env python3
"""OMNI_CAPTION_STYLE_V1 (2026-11-16): Browser settings > "Captions": how video captions look, set for the sofa.

What the user sees
  - Browser settings has a new row after the Autoplay row:
        "Captions"     value: "Default" or what differs from it, e.g. "150%, Yellow, Outline"
    Cross opens a small panel (title "Captions", subtitle "Captions in videos on any site. YouTube has its own: CC >
    Settings"):
        [live preview: a dark "video" with "This is how captions will look" drawn in the chosen look]
        Size            75% / 100% / 150% / 200% / 250%
        Text colour     White / Yellow / Cyan
        Background      None / Shaded (semi-transparent black) / Solid (black)
        Font            Default / Sans / Serif / Monospace
        Edge            None / Outline / Shadow (drop shadow)
        Position        Bottom / Higher
        Reset to default   (only when something differs)
    Cross / D-pad right: next value, D-pad left: previous, Y: that row back to its default. Every change redraws the
    preview and restyles captions already on screen (no reload). The preview lines take no focus (D-pad skips them).
  - One global choice: normal and private tabs, every site, every frame (embedded players included).

How captions are drawn in this port (checked in the s3 WebKit tree)
  - WebKit draws <track> / addTextTrack() captions itself: VTTCue builds a display tree inside the <video>'s user-agent
    shadow root (the media controls' text track container; RenderThemePlayStation::mediaControlsScripts returns Omni's
    modern media controls, which HTMLMediaElement::ensureMediaControls needs before any cue is shown). The default
    look is Modules/modern-media-controls/controls/text-tracks.css: ::cue { font: 5cqmin/normal sans-serif; white;
    background rgba(0,0,0,.8) } inside a container with container-type:size (cqmin = the video box).
  - Omni's own players (OmniMediaPlayer / OmniMSEPlayer, hole-punch plane) render no text: no InbandTextTrack, the
    HLS parser keeps only TYPE=AUDIO renditions (SUBTITLES are skipped), the WebM demuxer drops subtitle tracks. The
    captions of their videos are therefore WebKit's DOM cues above the plane (out-of-band <track>, or a JS player such
    as hls.js that feeds VTTCues to a TextTrack): all covered by ::cue.
  - CaptionUserPreferences (font scale, colours, captionsStyleSheetOverride) lives in the web process page group; the
    C API only has WKPreferencesSetShouldDisplayCaptions (no style), the override setter is Internals (testing) only.
    So the look is a user style sheet instead: ElementRuleCollector matches the document's *user* rule set against
    user-agent shadow-tree parts (collectMatchingUserAgentPartRules -> cuePseudoRules), RuleSet clones a ::cue
    rule's background onto the cue background box (::-internal-cue-background), and a user !important beats every
    author rule (also the font-size <style> CaptionUserPreferences may add to a generic cue).
  - YouTube draws its captions as its own DOM (.ytp-caption-segment, and its own TV-app nodes) with inline styles, not
    ::cue, and has its own caption settings (CC > Settings > Options, kept per account). A site tweak could restyle
    those nodes, but it would fight YouTube's own settings and break when its class names change, so it is left
    alone; the panel's subtitle says where YouTube's settings are. Same for any player that draws captions as DOM.

The sheet (OmniCaptionStyle::css; nothing at all while every row is at its default = WebKit's own look, zero cost)
  ::cue { font-size: 3.75 / 5 / 7.5 / 10 / 12.5cqmin (75-250% of WebKit's 5cqmin); color #ffffff / #ffff00 / #00ffff;
          background transparent / rgba(0,0,0,0.8) / #000000; font-family "DejaVu Sans",sans-serif / "DejaVu Serif",
          serif / "DejaVu Sans Mono",monospace (the fonts Omni ships, fonts.conf maps the generic names to them; CJK
          falls back to the Noto fonts as before); text-shadow: 8 hard 0.06em offsets (outline) or one 0.08em blurred
          offset (drop shadow) } - only the properties that differ from the default, all !important. Every one is in
          WebKit's ::cue property allow list (PropertyAllowlist.cpp); "Default" font / "Shaded" background / no edge
          leave the site's own ::cue styles alone.
  video::-webkit-media-text-track-region { background ... } (VTT regions draw their own box) when the background
          differs; its own rule, so a selector WebKit refused could only drop that rule.
  video::-webkit-media-text-track-container { max-height: 88% } for "Higher": cue positions are cqh of that
          container (container-type:size), so bottom lines move up by 12% of the video, top lines stay. ::cue cannot
          move cues (position properties are not in the allow list); the container is a plain UA part.

The sheet is installed by a new OmniBlocker.cpp function, bool omniCaptionCssSet(css): one API::UserStyleSheet
(UserStyleLevel::User, InjectInAllFrames, no allow / block list = every URL) added to both user-content controllers,
replaced in place (remove + add, css "" removes). WebUserContentControllerProxy add / removeUserStyleSheet invalidate
the injected style sheets of every open page, so captions on screen restyle without a reload.

File: /data/omni/captions.txt (omniIoQueue, whole file): "# Omni captions v1" then "size\\t150", "colour\\tyellow",
"background\\tsolid", "font\\tserif", "edge\\toutline", "position\\thigher". Unknown keys / values are skipped (the
default stays); 4 KB read cap. In test mode nothing is read or written (self-tests see WebKit's own look).

Pure part: engine/entry/OmniCaptionStyle.h (no SDL / WebKit): choices, file parse / serialize, CSS, CSS string
escaping, summary, preview geometry and word wrap. Tested by tools/test_caption_style.cpp:
    g++ -std=c++20 -Wall -Wextra -Wshadow -Werror -I<tree>/engine/entry test_caption_style.cpp
Shell side: engine/entry/OmniCaptionStyleShell.h (included from OmniFeatures3.h after OmniSiteTweaksShell.h): the
panel, the Browser settings row, the preview (SDL_ttf: the chosen DejaVu file at the chosen size, outline via
TTF_SetFontOutline; one font + the line surfaces cached while the panel is open, freed by omniCcsTick when it closes).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniPlaybackSpeed.h include line (pure include after it).
  OmniBrowserSettings.h  the omniApSettingsInput declaration (row declarations after it); the omniApSettingsRow call
                         (Captions row after it); the omniApRowId input line (ours before it). Row id 865
                         (OmniCaptionStyle::kSettingsRowId; 834-839, 845-899 minus 865, 900+ are other patches'
                         rows - 838/839 apply_high_contrast.py; the script refuses a tree where 865 already appears).
  OmniFeatures3Decl.h    the omniTgRowMark declaration (omniCcsRowDraw / omniCcsNoFocus after it).
  OmniFeaturesPanel.h    the list branch's "if (sel) fillRounded(...)" line (the preview hook before it); the D-pad
                         up/down "p.sel = n <= 12 ? ..." line (skip the preview rows after it).
  OmniFeatures3.h        the OmniSiteTweaksShell.h include line; the omniStTick() (site tweaks) line of omniF3Tick.
  OmniBlocker.h          the omniSiteCssSet declaration (omniCaptionCssSet after it).
  OmniBlocker.cpp        the omniAddonsRemove definition's first two lines (omniCaptionCssSet before them).
  OmniSettingsSearch.h   the Media section rule's last phrases ("caption", "subtitle" added: "Captions" is a Media
                         row); the "reset" synonym (subtitles / cc -> captions before it).
Apply AFTER apply_site_css.py, apply_autoplay.py, apply_tab_groups.py and apply_settings_search.py (their lines are
anchors). Names: namespace alias OCAP, prefix omniCcs (omniCap* is taken by the screenshot capture code; OST is
taken twice, by the sleep timer and the old site-tweaks alias).
usage: apply_caption_style.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_CAPTION_STYLE_V1'
ROW_ID = 865
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_CAPTION_STYLE_V1: the pure part of Browser settings > "Captions" (no SDL, no WebKit): how WebKit-drawn video
// captions (::cue) look, as one global user style sheet, plus the panel's choices, captions.txt and the preview layout.
// The shell side is OmniCaptionStyleShell.h; the reasons are in tools/apply_caption_style.py. Tested on the host with
// g++ (tools/test_caption_style.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniCaptionStyle {

constexpr const char* kFileName = "captions.txt";
constexpr const char* kHeader = "# Omni captions v1";
constexpr long kMaxFileBytes = 4096;
constexpr int kSettingsRowId = 865;   // Browser settings row (apply_caption_style.py refuses a tree that uses 865)
constexpr const char* kSample = "This is how captions will look";
constexpr const char* kSubtitle = "Captions in videos on any site. YouTube has its own: CC > Settings";
constexpr const char* kHints = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   Y default   Applies at once, no reload";

// --- choices ------------------------------------------------------------------------------------------------------
enum Field { fSize = 0, fColour, fBackground, fFont, fEdge, fPosition, kFieldCount };
enum { kEdgeNone = 0, kEdgeOutline = 1, kEdgeShadow = 2 };
enum { kFontDefault = 0, kFontSans = 1, kFontSerif = 2, kFontMono = 3 };
enum { kBgNone = 0, kBgShaded = 1, kBgSolid = 2 };

struct Choice { const char* token; const char* name; const char* summary; };
struct FieldInfo { const char* key; const char* label; const char* detail; const Choice* choices; int count; int def; };

inline const FieldInfo& field(int f)
{
    static const Choice sizes[] = { { "75", "75%", "75%" }, { "100", "100%", "100%" }, { "150", "150%", "150%" },
                                    { "200", "200%", "200%" }, { "250", "250%", "250%" } };
    static const Choice colours[] = { { "white", "White", "White" }, { "yellow", "Yellow", "Yellow" }, { "cyan", "Cyan", "Cyan" } };
    static const Choice backgrounds[] = { { "none", "None", "No background" }, { "semi", "Shaded", "Shaded" },
                                          { "solid", "Solid", "Solid background" } };
    static const Choice fonts[] = { { "default", "Default", "Default font" }, { "sans", "Sans", "Sans" },
                                    { "serif", "Serif", "Serif" }, { "mono", "Monospace", "Monospace" } };
    static const Choice edges[] = { { "none", "None", "No edge" }, { "outline", "Outline", "Outline" }, { "shadow", "Shadow", "Shadow" } };
    static const Choice positions[] = { { "bottom", "Bottom", "Bottom" }, { "higher", "Higher", "Higher" } };
    static const FieldInfo fields[kFieldCount] = {
        { "size", "Size", "Text size of the captions", sizes, 5, 1 },
        { "colour", "Text colour", "", colours, 3, 0 },
        { "background", "Background", "Box behind the text", backgrounds, 3, 1 },
        { "font", "Font", "", fonts, 4, 0 },
        { "edge", "Edge", "Keeps text readable on bright scenes", edges, 3, 0 },
        { "position", "Position", "Higher: clear of a TV's bottom edge", positions, 2, 0 },
    };
    return fields[(f >= 0 && f < kFieldCount) ? f : 0];
}

struct Style {
    int v[kFieldCount] = { 1, 0, 1, 0, 0, 0 };   // indexes into field(f).choices; the defaults = WebKit's own look
    int get(int f) const { return f >= 0 && f < kFieldCount ? v[f] : 0; }
    bool operator==(const Style& o) const { for (int f = 0; f < kFieldCount; ++f) if (v[f] != o.v[f]) return false; return true; }
    bool operator!=(const Style& o) const { return !(*this == o); }
};
inline bool isDefault(const Style& s, int f) { return s.get(f) == field(f).def; }
inline bool isDefault(const Style& s) { return s == Style(); }
inline void set(Style& s, int f, int index)
{
    if (f < 0 || f >= kFieldCount) return;
    s.v[f] = index >= 0 && index < field(f).count ? index : field(f).def;
}
inline void step(Style& s, int f, int dir)
{
    if (f < 0 || f >= kFieldCount) return;
    const int n = field(f).count;
    s.v[f] = ((s.get(f) + (dir < 0 ? -1 : 1)) % n + n) % n;
}
inline void resetField(Style& s, int f) { if (f >= 0 && f < kFieldCount) s.v[f] = field(f).def; }
inline const char* valueName(const Style& s, int f) { return field(f).choices[s.get(f)].name; }
inline int sizePercent(const Style& s) { static const int pct[] = { 75, 100, 150, 200, 250 }; return pct[s.get(fSize)]; }

// --- panel rows -----------------------------------------------------------------------------------------------------
constexpr int kRowPreview0 = 1, kPreviewRows = 3;   // the preview spans three rows (ids 1-3), takes no focus
constexpr int kRowFirstField = 10, kRowReset = 20;
inline bool isPreviewRow(int id) { return id >= kRowPreview0 && id < kRowPreview0 + kPreviewRows; }
inline int rowOfField(int f) { return kRowFirstField + f; }
inline int fieldOfRow(int id) { return id >= kRowFirstField && id < kRowFirstField + kFieldCount ? id - kRowFirstField : -1; }

// --- file ---------------------------------------------------------------------------------------------------------
// "# Omni captions v1" then "<key>\t<token>" lines. Unknown keys and values are skipped (that field keeps its default),
// so a file from a newer Omni still loads; "color" is read as "colour".
inline Style parse(const std::string& text)
{
    Style s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(pos, nl - pos);
        pos = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        std::string key = line.substr(0, tab);
        const std::string value = line.substr(tab + 1);
        if (key == "color") key = "colour";
        for (int f = 0; f < kFieldCount; ++f) {
            if (key != field(f).key) continue;
            for (int i = 0; i < field(f).count; ++i)
                if (value == field(f).choices[i].token) s.v[f] = i;
        }
    }
    return s;
}
inline std::string serialize(const Style& s)
{
    std::string out = std::string(kHeader) + "\n";
    for (int f = 0; f < kFieldCount; ++f) out += std::string(field(f).key) + "\t" + field(f).choices[s.get(f)].token + "\n";
    return out;
}

// --- texts ------------------------------------------------------------------------------------------------------------
// The Browser settings row value: "Default", or what differs from it ("150%, Yellow, Outline").
inline std::string summary(const Style& s)
{
    std::string out;
    for (int f = 0; f < kFieldCount; ++f) {
        if (isDefault(s, f)) continue;
        if (!out.empty()) out += ", ";
        out += field(f).choices[s.get(f)].summary;
    }
    return out.empty() ? std::string("Default") : out;
}

// --- the style sheet ----------------------------------------------------------------------------------------------
// A CSS string literal ("..."): backslash, quote and control characters escaped (the font names are fixed, but nothing
// that reaches the sheet should be able to end a string or a rule).
inline std::string cssString(const std::string& s)
{
    static const char* hex = "0123456789abcdef";
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += char(c); }
        else if (c < 0x20 || c == 0x7f) { out += '\\'; out += hex[c >> 4]; out += hex[c & 15]; out += ' '; }
        else out += char(c);
    }
    return out + "\"";
}
inline const char* fontName(int font)
{
    return font == kFontSerif ? "DejaVu Serif" : font == kFontMono ? "DejaVu Sans Mono" : "DejaVu Sans";
}
inline std::string fontFamily(int font)
{
    if (font == kFontDefault) return std::string();
    return cssString(fontName(font)) + (font == kFontSerif ? ",serif" : font == kFontMono ? ",monospace" : ",sans-serif");
}
// hundredths -> "3.75", "5", "7.5"
inline std::string decimal(int hundredths)
{
    std::string s = std::to_string(hundredths / 100);
    int frac = hundredths % 100;
    if (frac) { s += '.'; s += char('0' + frac / 10); if (frac % 10) s += char('0' + frac % 10); }
    return s;
}
inline const char* colourCss(int c) { return c == 1 ? "#ffff00" : c == 2 ? "#00ffff" : "#ffffff"; }
inline const char* backgroundCss(int b) { return b == kBgNone ? "transparent" : b == kBgSolid ? "#000000" : "rgba(0,0,0,0.8)"; }
inline const char* edgeCss(int e)
{
    if (e == kEdgeOutline)
        return "-0.06em -0.06em 0 #000,0 -0.06em 0 #000,0.06em -0.06em 0 #000,0.06em 0 0 #000,"
               "0.06em 0.06em 0 #000,0 0.06em 0 #000,-0.06em 0.06em 0 #000,-0.06em 0 0 #000";
    if (e == kEdgeShadow) return "0.08em 0.08em 0.1em rgba(0,0,0,0.9)";
    return "none";
}
// One user-level sheet (its !important beats the page's own ::cue !important). Empty while everything is default.
inline std::string css(const Style& s)
{
    std::string cue;
    if (!isDefault(s, fSize)) cue += "font-size:" + decimal(sizePercent(s) * 5) + "cqmin!important;";
    if (!isDefault(s, fColour)) cue += std::string("color:") + colourCss(s.get(fColour)) + "!important;";
    if (!isDefault(s, fBackground)) cue += std::string("background:") + backgroundCss(s.get(fBackground)) + "!important;";
    if (!isDefault(s, fFont)) cue += "font-family:" + fontFamily(s.get(fFont)) + "!important;";
    if (!isDefault(s, fEdge)) cue += std::string("text-shadow:") + edgeCss(s.get(fEdge)) + "!important;";
    std::string out;
    if (!cue.empty()) { cue.pop_back(); out += "::cue{" + cue + "}\n"; }
    if (!isDefault(s, fBackground))
        out += std::string("video::-webkit-media-text-track-region{background:") + backgroundCss(s.get(fBackground)) + "!important}\n";
    if (!isDefault(s, fPosition))
        out += "video::-webkit-media-text-track-container{max-height:88%!important}\n";
    return out;
}

// --- the preview ----------------------------------------------------------------------------------------------------
struct Rgb { uint8_t r, g, b; };
constexpr int kPreviewBasePx = 20;   // layout px of "100%" in the preview (250% = 50 px: two lines fit its 142 px)
inline int previewPx(const Style& s) { return kPreviewBasePx * sizePercent(s) / 100; }
inline Rgb textRgb(const Style& s)
{
    const int c = s.get(fColour);
    return c == 1 ? Rgb { 255, 255, 0 } : c == 2 ? Rgb { 0, 255, 255 } : Rgb { 255, 255, 255 };
}
inline uint8_t backgroundAlpha(const Style& s) { const int b = s.get(fBackground); return b == kBgNone ? 0 : b == kBgSolid ? 255 : 204; }
inline const char* fontFile(const Style& s)
{
    const int f = s.get(fFont);
    return f == kFontSerif ? "/data/omni/fonts/DejaVuSerif.ttf" : f == kFontMono ? "/data/omni/fonts/DejaVuSansMono.ttf"
                                                                                  : "/data/omni/fonts/DejaVuSans.ttf";
}
inline int previewRaise(const Style& s, int frameH) { return isDefault(s, fPosition) ? 0 : frameH * 10 / 100; }
inline int outlinePx(int fontPx) { return fontPx / 14 > 1 ? fontPx / 14 : 1; }
inline int shadowPx(int fontPx) { return fontPx / 12 > 1 ? fontPx / 12 : 1; }
// Greedy word wrap at spaces; measure(text) -> width. A word wider than maxW stays alone on its line.
template <class Measure>
inline std::vector<std::string> wrap(const std::string& text, int maxW, Measure measure)
{
    std::vector<std::string> lines;
    std::string line;
    size_t i = 0;
    while (i < text.size()) {
        while (i < text.size() && text[i] == ' ') ++i;
        if (i >= text.size()) break;
        size_t j = text.find(' ', i);
        if (j == std::string::npos) j = text.size();
        const std::string word = text.substr(i, j - i);
        i = j;
        const std::string candidate = line.empty() ? word : line + " " + word;
        if (line.empty() || measure(candidate) <= maxW) line = candidate;
        else { lines.push_back(line); line = word; }
    }
    if (!line.empty()) lines.push_back(line);
    return lines;
}

}  // namespace OmniCaptionStyle
'''

SHELL = r'''// OMNI_CAPTION_STYLE_V1: Browser settings > "Captions" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniSiteTweaksShell.h). The pure part is OmniCaptionStyle.h; the reasons are in
// tools/apply_caption_style.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OCAP = OmniCaptionStyle;
static OCAP::Style omniCcsStyle;
static bool omniCcsLoaded = false, omniCcsInstalled = false;

static void omniCcsLoad()
{
    if (omniCcsLoaded) return;
    omniCcsLoaded = true;
    if (omniTestMode()) return;   // self-tests see WebKit's own caption look
    FILE* f = fopen(omniData(OCAP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OCAP::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniCcsStyle = OCAP::parse(text);
}
static void omniCcsWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OCAP::kFileName), OCAP::serialize(omniCcsStyle), false);
}
// One global user style sheet in both controllers; WebKit restyles open pages (captions on screen change, no reload).
static void omniCcsApply()
{
    if (!omniCaptionCssSet(OCAP::css(omniCcsStyle))) fprintf(stderr, "OMNI CAPTIONS: controllers not ready\n");
}

// --- the preview: one font + the rendered lines, kept while the panel is open ---------------------------------------
struct OmniCcsPreview {
    TTF_Font* font = nullptr;
    std::string fontKey, key;
    std::vector<std::string> lines;
    std::vector<SDL_Surface*> surfaces;   // per line: the text, then its edge (outline / shadow) or nullptr
};
static OmniCcsPreview omniCcsPv;
static void omniCcsFreeLines()
{
    for (SDL_Surface* s : omniCcsPv.surfaces) if (s) SDL_FreeSurface(s);
    omniCcsPv.surfaces.clear();
    omniCcsPv.lines.clear();
    omniCcsPv.key.clear();
}
static void omniCcsPreviewFree()
{
    omniCcsFreeLines();
    if (omniCcsPv.font) TTF_CloseFont(omniCcsPv.font);
    omniCcsPv.font = nullptr;
    omniCcsPv.fontKey.clear();
}
static void omniCcsPanelBuild(OmniFxPanel& p);
static bool omniCcsPanelOpen()
{
    for (const auto& q : omniFxStack) if (q.build == omniCcsPanelBuild) return true;
    return false;
}
// From omniF3Tick: install the saved look once the user-content controllers exist; free the preview once closed.
static void omniCcsTick()
{
    if (!omniCcsInstalled && omniBlockerController()) {
        omniCcsInstalled = true;
        omniCcsLoad();
        omniCcsApply();
        fprintf(stderr, "OMNI CAPTIONS: %s\n", OCAP::summary(omniCcsStyle).c_str());
    }
    if (omniCcsPv.font && !omniCcsPanelOpen()) omniCcsPreviewFree();
}
// omniFxDrawPanel hook: the three preview rows are one picture, drawn from the first (true: the row is drawn).
static bool omniCcsRowDraw(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int w, int h)
{
    if (p.build != omniCcsPanelBuild || !OCAP::isPreviewRow(r.id)) return false;
    if (r.id != OCAP::kRowPreview0) return true;
    const OmniTheme& T = omniTheme();
    const int fx = x + 16, fy = y + 4, fw = w - 32, fh = h * OCAP::kPreviewRows - 8;
    fillRounded(fx, fy, fw, fh, omniRadius, SDL_Color { 24, 30, 40, 255 });             // a dark video frame
    fillRounded(fx, fy, fw, fh * 3 / 5, omniRadius, SDL_Color { 58, 78, 104, 255 }, 255, omniCornersTop);   // sky
    fillRounded(fx + fw * 3 / 5, fy + fh / 4, fw / 4, fh * 3 / 4, 2, SDL_Color { 40, 52, 66, 255 });         // a building
    omniLabel("Preview", fx + 12, fy + 14, omniCaption, T.inkFaint);
    const int px = physical(OCAP::previewPx(omniCcsStyle));
    const std::string file = OCAP::fontFile(omniCcsStyle);
    const std::string fontKey = file + "|" + std::to_string(px);
    if (fontKey != omniCcsPv.fontKey) {
        omniCcsPreviewFree();
        omniCcsPv.fontKey = fontKey;
        omniCcsPv.font = TTF_OpenFont(file.c_str(), px);
        if (!omniCcsPv.font) omniCcsPv.font = TTF_OpenFont("/data/omni/fonts/DejaVuSans.ttf", px);
    }
    TTF_Font* f = omniCcsPv.font;
    if (!f) { omniLabel(OCAP::kSample, fx + fw / 2.f, fy + fh - 24.f, omniBody, SDL_Color { 255, 255, 255, 255 }, 1, fw - 24); return true; }
    const int maxW = physical(fw - 48), outline = OCAP::outlinePx(px), shadow = OCAP::shadowPx(px);
    const int edge = omniCcsStyle.get(OCAP::fEdge);
    const std::string key = OCAP::serialize(omniCcsStyle) + std::to_string(maxW);
    if (key != omniCcsPv.key) {
        omniCcsFreeLines();
        omniCcsPv.key = key;
        omniCcsPv.lines = OCAP::wrap(OCAP::kSample, maxW, [&](const std::string& s) { int tw = 0, th = 0; TTF_SizeUTF8(f, s.c_str(), &tw, &th); return tw; });
        const OCAP::Rgb c = OCAP::textRgb(omniCcsStyle);
        for (const auto& line : omniCcsPv.lines) {
            omniCcsPv.surfaces.push_back(TTF_RenderUTF8_Blended(f, line.c_str(), SDL_Color { c.r, c.g, c.b, 255 }));
            SDL_Surface* e = nullptr;
            if (edge == OCAP::kEdgeOutline) {
                TTF_SetFontOutline(f, outline);
                e = TTF_RenderUTF8_Blended(f, line.c_str(), SDL_Color { 0, 0, 0, 255 });
                TTF_SetFontOutline(f, 0);
            } else if (edge == OCAP::kEdgeShadow) e = TTF_RenderUTF8_Blended(f, line.c_str(), SDL_Color { 0, 0, 0, 255 });
            omniCcsPv.surfaces.push_back(e);
        }
    }
    const int n = int(omniCcsPv.lines.size()), lineH = TTF_FontLineSkip(f);
    int ty = physical(fy + fh - 8 - OCAP::previewRaise(omniCcsStyle, fh)) - n * lineH;
    const int cx = physical(fx + fw / 2), padX = std::max(2, px / 4);
    const uint8_t bgA = OCAP::backgroundAlpha(omniCcsStyle);
    for (int i = 0; i < n && size_t(2 * i + 1) < omniCcsPv.surfaces.size(); ++i, ty += lineH) {
        SDL_Surface* s = omniCcsPv.surfaces[size_t(2 * i)];
        SDL_Surface* e = omniCcsPv.surfaces[size_t(2 * i + 1)];
        if (!s) continue;
        const int tx = cx - s->w / 2;
        if (bgA) omniRectPx({ tx - padX, ty, s->w + 2 * padX, lineH }, SDL_Color { 0, 0, 0, 255 }, bgA);
        if (e && edge == OCAP::kEdgeOutline) omniBlitText(e, tx - outline, ty - outline, 0, 255);
        if (e && edge == OCAP::kEdgeShadow) omniBlitText(e, tx + shadow, ty + shadow, 0, 220);
        omniBlitText(s, tx, ty, 0, 255);
    }
    return true;
}
// omniFxButton hook: D-pad up / down passes over the preview rows.
static bool omniCcsNoFocus(const OmniFxPanel& p, int row)
{
    return p.build == omniCcsPanelBuild && row >= 0 && row < int(p.rows.size()) && OCAP::isPreviewRow(p.rows[size_t(row)].id);
}

// --- the "Captions" panel ---------------------------------------------------------------------------------------------
static void omniCcsPanelBuild(OmniFxPanel& p)
{
    omniCcsLoad();
    for (int i = 0; i < OCAP::kPreviewRows; ++i) { OmniFxRow r; r.id = OCAP::kRowPreview0 + i; r.enabled = false; p.rows.push_back(r); }
    for (int f = 0; f < OCAP::kFieldCount; ++f) {
        OmniFxRow r;
        r.id = OCAP::rowOfField(f); r.label = OCAP::field(f).label; r.detail = OCAP::field(f).detail;
        r.value = OCAP::valueName(omniCcsStyle, f); r.stepper = true;
        p.rows.push_back(r);
    }
    OmniFxRow reset; reset.id = OCAP::kRowReset; reset.label = "Reset to default"; reset.enabled = !OCAP::isDefault(omniCcsStyle);
    p.rows.push_back(reset);
}
static bool omniCcsPanelInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A, left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    const bool right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, y = b == SDL_CONTROLLER_BUTTON_Y;
    if (r.id == OCAP::kRowReset) {
        if (!a) return left || right;
        if (!r.enabled) return true;
        omniCcsStyle = OCAP::Style();
        omniCcsWrite(); omniCcsApply();
        notice("Captions: back to the default look");
        return true;
    }
    const int f = OCAP::fieldOfRow(r.id);
    if (f < 0) return a || left || right;   // the preview
    const OCAP::Style before = omniCcsStyle;
    if (y) OCAP::resetField(omniCcsStyle, f);
    else if (a || right) OCAP::step(omniCcsStyle, f, 1);
    else if (left) OCAP::step(omniCcsStyle, f, -1);
    else return false;
    if (omniCcsStyle != before) { omniCcsWrite(); omniCcsApply(); }
    return true;
}

// --- Browser settings > Captions ---------------------------------------------------------------------------------------
static void omniCcsSettingsRow(OmniFxPanel& p)
{
    omniCcsLoad();
    OmniFxRow r; r.id = OCAP::kSettingsRowId; r.label = "Captions"; r.value = OCAP::summary(omniCcsStyle);
    p.rows.push_back(r);
}
static bool omniCcsSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    OmniFxPanel p;
    p.title = "Captions"; p.subtitle = OCAP::kSubtitle; p.w = 820; p.maxVisible = 10;
    p.build = omniCcsPanelBuild; p.input = omniCcsPanelInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = OCAP::kHints;
    omniFxPush(std::move(p));
    return true;
}
'''

BLOCKER_FN = r'''// OMNI_CAPTION_STYLE_V1: Browser settings > Captions (OmniCaptionStyleShell.h decides the CSS). One global user style
// sheet (UserStyleLevel::User: its !important beats the page's own ::cue rules), every frame, every URL (no allow / block
// list), in both controllers (normal and private tabs share the choice); replaced in place, css "" removes it. WebKit
// restyles open pages when a sheet is added or removed, so captions on screen change without a reload.
namespace {
RefPtr<API::UserStyleSheet> omniCcsSheet;
std::string omniCcsText;
}
bool omniCaptionCssSet(const std::string& css)
{
    if (!controller) return false;
    if (css == omniCcsText && (omniCcsSheet || css.empty())) return true;
    if (omniCcsSheet) {
        WebKit::toImpl(controller.get())->removeUserStyleSheet(*omniCcsSheet);
        if (privateController) WebKit::toImpl(privateController.get())->removeUserStyleSheet(*omniCcsSheet);
        omniCcsSheet = nullptr;
    }
    omniCcsText = css;
    if (css.empty()) return true;
    WebCore::UserStyleSheet sheet { addonString(css), WTF::URL { }, { }, { },
        WebCore::UserContentInjectedFrames::InjectInAllFrames,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins, WebCore::UserStyleLevel::User };
    auto world = API::ContentWorld::sharedWorldWithName(addonString("omni-captions"));
    Ref<API::UserStyleSheet> userSheet = API::UserStyleSheet::create(WTF::move(sheet), world.get());
    WebKit::toImpl(controller.get())->addUserStyleSheet(userSheet.get());
    if (privateController) WebKit::toImpl(privateController.get())->addUserStyleSheet(userSheet.get());
    omniCcsSheet = userSheet.ptr();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n',
         '#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n'
         '#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniApSettingsInput(int b);\n',
         'static bool omniApSettingsInput(int b);\n'
         'static void omniCcsSettingsRow(OmniFxPanel& p); // OMNI_CAPTION_STYLE_V1: "Captions" (OmniCaptionStyleShell.h)\n'
         'static bool omniCcsSettingsInput(int b);\n'),
        ('    omniApSettingsRow(p); // OMNI_AUTOPLAY_V1: Allow / Block sound / Block all\n',
         '    omniApSettingsRow(p); // OMNI_AUTOPLAY_V1: Allow / Block sound / Block all\n'
         '    omniCcsSettingsRow(p); // OMNI_CAPTION_STYLE_V1: Captions (opens its panel)\n'),
        ('    if (r.id == omniApRowId) return omniApSettingsInput(b); // OMNI_AUTOPLAY_V1 (before the >= 300 rows)\n',
         '    if (r.id == OmniCaptionStyle::kSettingsRowId) return omniCcsSettingsInput(b); // OMNI_CAPTION_STYLE_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniApRowId) return omniApSettingsInput(b); // OMNI_AUTOPLAY_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n',
         'static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n'
         'static bool omniCcsRowDraw(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int w, int h); // OMNI_CAPTION_STYLE_V1: the preview\n'
         'static bool omniCcsNoFocus(const OmniFxPanel& p, int row); // OMNI_CAPTION_STYLE_V1: D-pad passes over the preview\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('            if (sel) fillRounded(g.x + 12, ry + 2, g.w - 24, p.rowH - 4, omniRadius, on ? T.accent : T.key);\n',
         '            if (omniCcsRowDraw(p, r, g.x, ry, g.w, p.rowH)) continue; // OMNI_CAPTION_STYLE_V1: the live caption preview\n'
         '            if (sel) fillRounded(g.x + 12, ry + 2, g.w - 24, p.rowH - 4, omniRadius, on ? T.accent : T.key);\n'),
        ('        p.sel = n <= 12 ? (p.sel + d + n) % n : std::clamp(p.sel + d, 0, n - 1);\n',
         '        p.sel = n <= 12 ? (p.sel + d + n) % n : std::clamp(p.sel + d, 0, n - 1);\n'
         '        for (int k = 0; k < n && omniCcsNoFocus(p, p.sel); ++k) p.sel = n <= 12 ? (p.sel + d + n) % n : std::clamp(p.sel + d, 0, n - 1); // OMNI_CAPTION_STYLE_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteTweaksShell.h" // OMNI_SITE_TWEAKS_V1\n',
         '#include "OmniSiteTweaksShell.h" // OMNI_SITE_TWEAKS_V1\n'
         '#include "OmniCaptionStyleShell.h" // OMNI_CAPTION_STYLE_V1\n'),
        ('    omniStTick();       // OMNI_SITE_TWEAKS_V1: saved page tweaks, once the controllers exist\n',
         '    omniStTick();       // OMNI_SITE_TWEAKS_V1: saved page tweaks, once the controllers exist\n'
         '    omniCcsTick();      // OMNI_CAPTION_STYLE_V1: saved caption look once the controllers exist; preview cleanup\n'),
    ],
    'OmniBlocker.h': [
        ('bool omniSiteCssSet(const std::string& key, const std::string& css, const std::vector<std::string>& allow, bool privateTabs);\n',
         'bool omniSiteCssSet(const std::string& key, const std::string& css, const std::vector<std::string>& allow, bool privateTabs);\n'
         '// OMNI_CAPTION_STYLE_V1: the one global caption (::cue) user style sheet, all frames, all URLs, normal + private\n'
         '// controllers; css "" removes it. false: controllers not ready.\n'
         'bool omniCaptionCssSet(const std::string& css);\n'),
    ],
    'OmniBlocker.cpp': [
        ('void omniAddonsRemove(const std::string& id)\n{\n',
         BLOCKER_FN + 'void omniAddonsRemove(const std::string& id)\n{\n'),
    ],
    'OmniSettingsSearch.h': [
        ('"audio", "sleep timer", nullptr } },\n',
         '"audio", "sleep timer", "caption", "subtitle", nullptr } }, // OMNI_CAPTION_STYLE_V1: caption, subtitle\n'),
        ('        { "reset", { "clear", nullptr } },\n',
         '        { "subtitles", { "captions", nullptr } }, // OMNI_CAPTION_STYLE_V1\n'
         '        { "cc", { "captions", nullptr } },\n'
         '        { "reset", { "clear", nullptr } },\n'),
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def check_row_id():
    """The Browser settings row id must be ours alone: refuse when any source in the tree already uses it."""
    if MARK in (root / 'OmniBrowserSettings.h').read_bytes().decode('utf-8'):
        return
    rx = re.compile(r'\b%d\b' % ROW_ID)
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc') or f.name in ('OmniCaptionStyle.h', 'OmniCaptionStyleShell.h'):
            continue
        t = f.read_text(encoding='utf-8', errors='replace')
        for i, (line, code) in enumerate(zip(t.split('\n'), cpp_code(t).split('\n')), 1):
            if rx.search(code) and MARK not in line:
                sys.exit('row id %d already used: %s:%d: %s' % (ROW_ID, f.name, i, line.strip()[:120]))


def main():
    needs = [('OmniFeatures3.h', 'OMNI_SITE_TWEAKS_V1', 'apply_site_css.py'),
             ('OmniBrowserSettings.h', 'OMNI_AUTOPLAY_V1', 'apply_autoplay.py'),
             ('OmniFeatures3Decl.h', 'OMNI_TAB_GROUPS_V1', 'apply_tab_groups.py'),
             ('OmniBrowserSettings.h', 'OMNI_SETTINGS_SEARCH_V1', 'apply_settings_search.py'),
             ('OmniBrowser.cpp', 'OMNI_PLAYBACK_SPEED_V1', 'apply_playback_speed.py')]
    for name, mark, script in needs:
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, script))
    check_row_id()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniCaptionStyle.h', PURE, 'OmniSiteTweaks.h'),
            write_new('OmniCaptionStyleShell.h', SHELL, 'OmniSiteTweaksShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
