// OMNI_MIN_TEXT_V1: Browser settings > "Minimum text size" (pure part; no WebKit, no SDL). Kept next to
// tools/apply_min_text.py, which copies it into engine/entry. Tested by tools/test_min_text.cpp.
// The shell (OmniMinTextShell.h) hands px() to WebKit's own hard minimum, WKPreferencesSetMinimumFontSize on the one
// shared `preferences` object (every tab, private tabs too; WebCore restyles open pages, no reload). 0 = Off (WebKit's
// default for MinimumFontSize). The minimum is compared with the text size after page zoom and Text size, in CSS px.
#pragma once
#include <cstdint>
#include <string>

namespace OmniMinText {

constexpr int kRowId = 817;                                  // Browser settings row (handled before the >= 300 rows)
constexpr const char* kFileName = "min-text.txt";           // in the data folder: "off" / "12" ... "20"
constexpr const char* kRowLabel = "Minimum text size";
constexpr const char* kRowDetail = "Smaller text on every page is shown at this size (some layouts may overflow)";
constexpr const char* kTestDetail = "Off in test modes";
constexpr int kSizes[] = { 0, 12, 14, 16, 18, 20 };          // 0 = Off
constexpr int kCount = int(sizeof(kSizes) / sizeof(kSizes[0]));

// Index of px in kSizes; -1 when px is not one of the offered sizes.
inline int indexOf(int px)
{
    for (int i = 0; i < kCount; ++i)
        if (kSizes[i] == px) return i;
    return -1;
}
inline bool valid(int px) { return indexOf(px) >= 0; }

// min-text.txt: "off" or one of the sizes (surrounding spaces / newline allowed). Anything else: Off.
inline int parse(const std::string& text)
{
    size_t a = 0, b = text.size();
    while (a < b && (text[a] == ' ' || text[a] == '\t' || text[a] == '\r' || text[a] == '\n')) ++a;
    while (b > a && (text[b - 1] == ' ' || text[b - 1] == '\t' || text[b - 1] == '\r' || text[b - 1] == '\n')) --b;
    const std::string t = text.substr(a, b - a);
    if (t.empty() || t.size() > 3) return 0;
    int v = 0;
    for (char c : t) {
        if (c < '0' || c > '9') return 0;
        v = v * 10 + (c - '0');
    }
    return valid(v) ? v : 0;
}
inline std::string serialize(int px) { return valid(px) && px ? std::to_string(px) + "\n" : std::string("off\n"); }

// Row value: "Off" / "16 px".
inline std::string rowValue(int px) { return valid(px) && px ? std::to_string(px) + " px" : std::string("Off"); }
inline std::string noticeText(int px)
{
    return valid(px) && px ? "Minimum text size " + std::to_string(px) + " px" : std::string("Minimum text size off");
}

// D-pad left / right: one size smaller / larger, stopping at Off and at the largest; Cross: next, wrapping to Off.
inline int stepped(int px, int dir)
{
    int i = indexOf(px);
    if (i < 0) i = 0;
    i += dir < 0 ? -1 : dir > 0 ? 1 : 0;
    if (i < 0) i = 0;
    if (i >= kCount) i = kCount - 1;
    return kSizes[i];
}
inline int cycled(int px)
{
    const int i = indexOf(px);   // an unknown value counts as Off
    return kSizes[((i < 0 ? 0 : i) + 1) % kCount];
}

// The value WebKit gets (WKPreferencesSetMinimumFontSize): test modes always 0 (self-tests measure normal layouts).
inline uint32_t webkitValue(int px, bool testMode) { return testMode || !valid(px) ? 0u : uint32_t(px); }

// WebCore's hard minimum (Style::usedFontSizeFromComputedSize, "minSize"), copied for the tests: a 0 px font stays 0
// (hidden text), otherwise max(computed * zoom, minimum).
inline float usedSize(float computedPx, float zoom, int minimumPx)
{
    if (computedPx == 0.f) return 0.f;
    const float z = computedPx * zoom;
    return z < float(minimumPx) ? float(minimumPx) : z;
}

} // namespace OmniMinText
