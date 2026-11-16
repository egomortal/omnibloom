// OMNI_UI_ACCENT_V1: the pure part of Browser settings > "Accent colour" (no SDL, no WebKit).
// The accent replaces a theme's accent / accentInk / accent2 at omniTheme() lookup time (one place), so focus rings,
// selected rows, progress bars, switches, the new-tab page and the controller light bar all follow. "Theme default"
// keeps the theme's own colours; the High contrast theme always keeps its yellow (accentFor returns nullptr).
// Every accent is checked (WCAG 2 formula from OmniHighContrast.h) against every theme surface it can sit on:
// >= 3:1 for focus rings, and the text drawn on it (black or white, picked automatically) >= 4.5:1.
// Shell side: tools/apply_ui_accent.py. Tested on the host with g++ (tools/test_ui_accent.cpp).
#pragma once
#include <cctype>
#include <cstring>
#include <string>
#include <string_view>
#include "OmniHighContrast.h"

namespace OmniUiAccent {

using Rgb = OmniHighContrast::Rgb;
using OmniHighContrast::contrast;   // WCAG 2 contrast ratio (reused, not copied)

inline constexpr double kFocusMin = 3.0;   // WCAG 2.2 non-text contrast (focus ring vs what it sits on)
inline constexpr double kTextMin = 4.5;    // WCAG AA text drawn on the accent (selected rows, keys, chips)
inline constexpr Rgb kBlack { 0, 0, 0 }, kWhite { 255, 255, 255 };

struct Accent { const char* id; const char* name; Rgb colour; };
// index 0 = Theme default (no colour). ids are what /data/omni/ui-accent.txt holds; no id is a prefix of another.
inline constexpr Accent kAccents[] = {
    { "default", "Theme default", { 0, 0, 0 } },
    { "blue",    "Blue",          { 77, 163, 255 } },
    { "teal",    "Teal",          { 45, 212, 191 } },
    { "green",   "Green",         { 74, 222, 128 } },
    { "amber",   "Amber",         { 251, 191, 36 } },
    { "orange",  "Orange",        { 251, 146, 60 } },
    { "red",     "Red",           { 248, 113, 113 } },
    { "pink",    "Pink",          { 244, 114, 182 } },
    { "violet",  "Violet",        { 167, 139, 250 } },
};
inline constexpr int kCount = int(sizeof(kAccents) / sizeof(kAccents[0]));
inline constexpr int kRowId = 832;   // Browser settings row (830-833, 843, 844, 849 were free on 2026-11-16)
inline constexpr const char* kFile = "ui-accent.txt";
inline constexpr const char* kRowLabel = "Accent colour";
inline constexpr const char* kRowDetail = "High contrast keeps its yellow";

inline int clampIndex(int i) { return i >= 0 && i < kCount ? i : 0; }
inline const char* name(int i) { return kAccents[clampIndex(i)].name; }
inline int step(int i, int dir) { return ((clampIndex(i) + dir) % kCount + kCount) % kCount; }

// Text on the accent: black or white, whichever contrasts more.
inline Rgb inkOn(Rgb c) { return contrast(kBlack, c) >= contrast(kWhite, c) ? kBlack : kWhite; }
// accent2 (the active tab line fades accent -> accent2): the accent lightened 30% toward white.
inline Rgb lighter(Rgb c, int pct = 30)
{
    auto ch = [pct](uint8_t v) { return uint8_t(v + (255 - v) * pct / 100); };
    return { ch(c.r), ch(c.g), ch(c.b) };
}
struct Override { Rgb accent, accentInk, accent2; };
// nullptr-like: ok == false means "keep the theme's own accent" (Theme default, or the High contrast theme).
struct Pick { bool ok; Override o; };
inline Pick accentFor(int index, const char* themeId)
{
    index = clampIndex(index);
    if (index == 0 || (themeId && !std::strcmp(themeId, OmniHighContrast::kThemeId))) return { false, {} };
    const Rgb c = kAccents[index].colour;
    const Rgb c2 = lighter(c);
    return { true, { c, inkOn(c), c2 } };
}

// /data/omni/ui-accent.txt: one id; anything else (empty, unknown) is Theme default.
inline int parse(std::string_view text)
{
    size_t a = 0, b = text.size();
    while (a < b && std::isspace(static_cast<unsigned char>(text[a]))) ++a;
    while (b > a && std::isspace(static_cast<unsigned char>(text[b - 1]))) --b;
    std::string v(text.substr(a, b - a));
    for (char& ch : v) ch = char(std::tolower(static_cast<unsigned char>(ch)));
    for (int i = 0; i < kCount; ++i) if (v == kAccents[i].id) return i;
    return 0;
}
inline std::string serialize(int index) { return std::string(kAccents[clampIndex(index)].id) + "\n"; }

} // namespace OmniUiAccent
