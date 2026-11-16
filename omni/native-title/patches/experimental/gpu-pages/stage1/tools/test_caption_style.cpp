// OMNI_CAPTION_STYLE_V1: host tests of the pure part (engine/entry/OmniCaptionStyle.h).
//   g++ -std=c++20 -Wall -Wextra -Wshadow -Werror -I<tree>/engine/entry test_caption_style.cpp -o t && ./t
#include "OmniCaptionStyle.h"
#include <cstdio>

namespace OCAP = OmniCaptionStyle;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static bool has(const std::string& s, const std::string& sub) { return s.find(sub) != std::string::npos; }
static int count(const std::string& s, char c) { int n = 0; for (char x : s) n += x == c; return n; }
// Every rule is "selector{...}\n": balanced braces, no stray quote, no line break inside a rule.
static bool wellFormed(const std::string& css)
{
    if (count(css, '{') != count(css, '}') || count(css, '"') % 2) return false;
    int depth = 0;
    for (char c : css) {
        if (c == '{') { if (depth++) return false; }
        else if (c == '}') { if (--depth) return false; }
        else if (c == '\n' && depth) return false;
    }
    return depth == 0;
}

int main()
{
    using OCAP::Style;
    const Style d;

    // defaults = WebKit's own look: no sheet at all
    CHECK(OCAP::isDefault(d));
    CHECK(OCAP::css(d).empty());
    CHECK(OCAP::summary(d) == "Default");
    CHECK(OCAP::sizePercent(d) == 100);
    for (int f = 0; f < OCAP::kFieldCount; ++f) CHECK(OCAP::isDefault(d, f) && OCAP::field(f).count >= 2);
    CHECK(std::string(OCAP::valueName(d, OCAP::fBackground)) == "Shaded");

    // the choices the panel offers
    const int sizes[] = { 75, 100, 150, 200, 250 };
    const char* sizeCss[] = { "3.75cqmin", "", "7.5cqmin", "10cqmin", "12.5cqmin" };
    for (int i = 0; i < 5; ++i) {
        Style s; OCAP::set(s, OCAP::fSize, i);
        CHECK(OCAP::sizePercent(s) == sizes[i]);
        CHECK(i == 1 ? OCAP::css(s).empty() : has(OCAP::css(s), std::string("font-size:") + sizeCss[i] + "!important"));
        CHECK(OCAP::previewPx(s) == 20 * sizes[i] / 100);
    }
    CHECK(OCAP::decimal(375) == "3.75" && OCAP::decimal(500) == "5" && OCAP::decimal(750) == "7.5" && OCAP::decimal(1250) == "12.5");
    CHECK(OCAP::field(OCAP::fColour).count == 3 && OCAP::field(OCAP::fBackground).count == 3 && OCAP::field(OCAP::fFont).count == 4
          && OCAP::field(OCAP::fEdge).count == 3 && OCAP::field(OCAP::fPosition).count == 2 && OCAP::field(OCAP::fSize).count == 5);

    // step / set / reset
    Style s;
    OCAP::step(s, OCAP::fSize, 1); CHECK(OCAP::sizePercent(s) == 150);
    OCAP::step(s, OCAP::fSize, 1); OCAP::step(s, OCAP::fSize, 1); CHECK(OCAP::sizePercent(s) == 250);
    OCAP::step(s, OCAP::fSize, 1); CHECK(OCAP::sizePercent(s) == 75);   // wraps
    OCAP::step(s, OCAP::fSize, -1); CHECK(OCAP::sizePercent(s) == 250);
    OCAP::resetField(s, OCAP::fSize); CHECK(OCAP::isDefault(s));
    OCAP::step(s, OCAP::fPosition, -1); CHECK(s.get(OCAP::fPosition) == 1);
    OCAP::step(s, OCAP::fPosition, -1); CHECK(s.get(OCAP::fPosition) == 0);
    OCAP::set(s, OCAP::fColour, 99); CHECK(s.get(OCAP::fColour) == 0);   // out of range -> default
    OCAP::set(s, 42, 1); OCAP::step(s, -1, 1); OCAP::resetField(s, 9); CHECK(OCAP::isDefault(s));   // bad field: no-op

    // rows
    CHECK(OCAP::isPreviewRow(1) && OCAP::isPreviewRow(3) && !OCAP::isPreviewRow(4) && !OCAP::isPreviewRow(0));
    for (int f = 0; f < OCAP::kFieldCount; ++f) CHECK(OCAP::fieldOfRow(OCAP::rowOfField(f)) == f && !OCAP::isPreviewRow(OCAP::rowOfField(f)));
    CHECK(OCAP::fieldOfRow(OCAP::kRowReset) == -1 && OCAP::fieldOfRow(1) == -1);
    CHECK(OCAP::kSettingsRowId == 865);

    // the sheet
    Style all;
    OCAP::set(all, OCAP::fSize, 3); OCAP::set(all, OCAP::fColour, 1); OCAP::set(all, OCAP::fBackground, 2);
    OCAP::set(all, OCAP::fFont, 2); OCAP::set(all, OCAP::fEdge, 1); OCAP::set(all, OCAP::fPosition, 1);
    const std::string c = OCAP::css(all);
    CHECK(wellFormed(c));
    CHECK(has(c, "::cue{font-size:10cqmin!important;color:#ffff00!important;background:#000000!important;"));
    CHECK(has(c, "font-family:\"DejaVu Serif\",serif!important"));
    CHECK(has(c, "text-shadow:-0.06em -0.06em 0 #000,") && count(c, '#') >= 8);
    CHECK(has(c, "video::-webkit-media-text-track-region{background:#000000!important}"));
    CHECK(has(c, "video::-webkit-media-text-track-container{max-height:88%!important}"));
    CHECK(!has(c, ";}"));   // the last declaration has no stray ';'
    CHECK(OCAP::summary(all) == "200%, Yellow, Solid background, Serif, Outline, Higher");
    {
        Style t; OCAP::set(t, OCAP::fPosition, 1);
        CHECK(OCAP::css(t) == "video::-webkit-media-text-track-container{max-height:88%!important}\n");
        CHECK(OCAP::summary(t) == "Higher");
        Style u; OCAP::set(u, OCAP::fBackground, 0);
        CHECK(OCAP::css(u) == "::cue{background:transparent!important}\nvideo::-webkit-media-text-track-region{background:transparent!important}\n");
        Style v; OCAP::set(v, OCAP::fEdge, 2);
        CHECK(OCAP::css(v) == "::cue{text-shadow:0.08em 0.08em 0.1em rgba(0,0,0,0.9)!important}\n");
        Style w; OCAP::set(w, OCAP::fColour, 2); OCAP::set(w, OCAP::fFont, 3);
        CHECK(OCAP::css(w) == "::cue{color:#00ffff!important;font-family:\"DejaVu Sans Mono\",monospace!important}\n");
        Style x; OCAP::set(x, OCAP::fFont, 1);
        CHECK(has(OCAP::css(x), "\"DejaVu Sans\",sans-serif"));
    }
    // every combination: well formed, only allow-listed ::cue properties, round trip through the file
    int combos = 0;
    for (int a = 0; a < 5; ++a) for (int b = 0; b < 3; ++b) for (int g = 0; g < 3; ++g)
    for (int f = 0; f < 4; ++f) for (int e = 0; e < 3; ++e) for (int p = 0; p < 2; ++p) {
        Style t;
        OCAP::set(t, OCAP::fSize, a); OCAP::set(t, OCAP::fColour, b); OCAP::set(t, OCAP::fBackground, g);
        OCAP::set(t, OCAP::fFont, f); OCAP::set(t, OCAP::fEdge, e); OCAP::set(t, OCAP::fPosition, p);
        const std::string x = OCAP::css(t);
        ++combos;
        if (!wellFormed(x)) { CHECK(wellFormed(x)); continue; }
        if (OCAP::isDefault(t) != x.empty()) CHECK(OCAP::isDefault(t) == x.empty());
        if (has(x, "position") || has(x, "transform") || has(x, "top:")) CHECK(!has(x, "position:"));
        if (OCAP::parse(OCAP::serialize(t)) != t) CHECK(OCAP::parse(OCAP::serialize(t)) == t);
        if ((p == 1) != has(x, "max-height")) CHECK(false);
        if ((g != 1) != has(x, "track-region")) CHECK(false);
    }
    CHECK(combos == 1080);

    // file
    CHECK(OCAP::serialize(d) == "# Omni captions v1\nsize\t100\ncolour\twhite\nbackground\tsemi\nfont\tdefault\nedge\tnone\nposition\tbottom\n");
    CHECK(OCAP::parse("") == d);
    CHECK(OCAP::parse("garbage\nno tab here\n\t\n#size\t250\n") == d);
    {
        const Style p = OCAP::parse("# Omni captions v1\r\nsize\t250\r\ncolor\tcyan\r\nbackground\tnone\r\nfont\tmono\r\nedge\tshadow\r\nposition\thigher\r\n");
        CHECK(OCAP::sizePercent(p) == 250 && p.get(OCAP::fColour) == 2 && p.get(OCAP::fBackground) == 0
              && p.get(OCAP::fFont) == 3 && p.get(OCAP::fEdge) == 2 && p.get(OCAP::fPosition) == 1);
        const Style q = OCAP::parse("size\t300\ncolour\tpink\nfont\tComic Sans\nnewkey\tx\nedge\toutline");   // no final newline
        CHECK(OCAP::sizePercent(q) == 100 && q.get(OCAP::fColour) == 0 && q.get(OCAP::fFont) == 0 && q.get(OCAP::fEdge) == 1);
        CHECK(OCAP::parse("size\t150 \n").get(OCAP::fSize) == 1);   // values must match exactly
        CHECK(OCAP::parse("size\t75\nsize\t200\n").get(OCAP::fSize) == 3);   // the last line wins
    }

    // escaping
    CHECK(OCAP::cssString("DejaVu Sans") == "\"DejaVu Sans\"");
    CHECK(OCAP::cssString("a\"b\\c") == "\"a\\\"b\\\\c\"");
    CHECK(OCAP::cssString("x\ny}") == "\"x\\0a y}\"");
    CHECK(OCAP::cssString(std::string("\x7f", 1)) == "\"\\7f \"");
    CHECK(OCAP::fontFamily(OCAP::kFontDefault).empty());

    // preview
    CHECK(std::string(OCAP::fontFile(d)) == "/data/omni/fonts/DejaVuSans.ttf");
    {
        Style t; OCAP::set(t, OCAP::fFont, 2); CHECK(has(OCAP::fontFile(t), "DejaVuSerif.ttf"));
        OCAP::set(t, OCAP::fFont, 3); CHECK(has(OCAP::fontFile(t), "DejaVuSansMono.ttf"));
        OCAP::set(t, OCAP::fFont, 1); CHECK(has(OCAP::fontFile(t), "DejaVuSans.ttf"));
        OCAP::set(t, OCAP::fColour, 1); CHECK(OCAP::textRgb(t).r == 255 && OCAP::textRgb(t).g == 255 && OCAP::textRgb(t).b == 0);
        OCAP::set(t, OCAP::fColour, 2); CHECK(OCAP::textRgb(t).r == 0 && OCAP::textRgb(t).b == 255);
        OCAP::set(t, OCAP::fBackground, 0); CHECK(OCAP::backgroundAlpha(t) == 0);
        OCAP::set(t, OCAP::fBackground, 2); CHECK(OCAP::backgroundAlpha(t) == 255);
        CHECK(OCAP::backgroundAlpha(d) == 204);
        CHECK(OCAP::previewRaise(d, 142) == 0);
        OCAP::set(t, OCAP::fPosition, 1); CHECK(OCAP::previewRaise(t, 142) == 14);
    }
    CHECK(OCAP::outlinePx(10) == 1 && OCAP::outlinePx(75) == 5 && OCAP::shadowPx(30) == 2);
    {
        auto w10 = [](const std::string& t) { return int(t.size()) * 10; };   // 10 px a character
        auto one = OCAP::wrap(OCAP::kSample, 1000, w10);
        CHECK(one.size() == 1 && one[0] == OCAP::kSample);
        auto two = OCAP::wrap(OCAP::kSample, 200, w10);   // 20 characters a line
        CHECK(two.size() == 2 && two[0] == "This is how captions" && two[1] == "will look");
        auto narrow = OCAP::wrap("a verylongword b", 50, w10);
        CHECK(narrow.size() == 3 && narrow[1] == "verylongword");
        CHECK(OCAP::wrap("", 100, w10).empty() && OCAP::wrap("   ", 100, w10).empty());
        CHECK(OCAP::wrap("  two  spaces ", 1000, w10).size() == 1 && OCAP::wrap("  two  spaces ", 1000, w10)[0] == "two spaces");
        // the real panel: 820 - 32 - 48 = 740 layout px; DejaVu ~0.6 em a character: 250% (50 px) needs two lines
        auto big = OCAP::wrap(OCAP::kSample, 740, [](const std::string& t) { return int(t.size()) * 30; });
        CHECK(big.size() == 2);
    }

    std::printf("%s: %d/%d checks passed\n", fails ? "FAILED" : "OK", checks - fails, checks);
    return fails ? 1 : 0;
}
