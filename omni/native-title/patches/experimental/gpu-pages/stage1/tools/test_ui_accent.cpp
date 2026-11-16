// OMNI_UI_ACCENT_V1 host tests: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_ui_accent.cpp -o t && ./t [OmniBrowser.cpp]
// With the patched OmniBrowser.cpp as argument, the theme table below is checked against the real omniThemes[].
#include "OmniUiAccent.h"
#include <cstdio>
#include <fstream>
#include <regex>
#include <sstream>
#include <vector>

namespace A = OmniUiAccent;
using A::Rgb;
static int fails = 0, passes = 0;
#define CHECK(c) do { if (c) ++passes; else { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

// omniThemes[] field order: bg, bar, line, tab, hover, field, panel, raised, key, ink, inkDim, inkFaint, accent, accentInk, tabOn, edge, accent2
struct Theme { const char* id; Rgb c[17]; };
static const Theme kThemes[] = {
    { "dark", { {11,17,25}, {17,27,37}, {50,66,76}, {19,30,41}, {33,49,61}, {32,46,59}, {17,27,37}, {26,40,51}, {36,52,63}, {237,245,247}, {170,191,201}, {111,135,147}, {112,228,209}, {6,36,30}, {23,36,48}, {57,80,93}, {199,137,217} } },
    { "midnight", { {3,4,7}, {10,12,17}, {26,30,38}, {18,21,28}, {32,37,47}, {20,24,32}, {12,15,21}, {27,32,42}, {28,33,43}, {226,230,238}, {138,147,163}, {84,92,107}, {58,212,176}, {6,36,30}, {22,26,34}, {44,50,62}, {199,137,217} } },
    { "playstation", { {6,17,40}, {12,29,61}, {30,52,92}, {19,39,76}, {31,57,104}, {22,44,85}, {12,29,61}, {28,53,97}, {29,54,99}, {238,243,255}, {164,182,216}, {100,121,160}, {38,135,255}, {255,255,255}, {24,48,90}, {48,76,124}, {120,190,255} } },
    { "purple", { {16,13,24}, {26,22,37}, {45,39,60}, {35,30,49}, {51,44,70}, {38,33,54}, {26,22,37}, {45,39,63}, {48,41,66}, {239,235,247}, {170,161,191}, {108,100,128}, {170,132,255}, {26,14,52}, {43,37,60}, {66,58,88}, {255,150,210} } },
};
// The surfaces a focus ring / selected row / progress bar can sit on (not the hairlines line / edge, not text colours).
static const struct { int i; const char* n; } kSurfaces[] = { {0,"bg"}, {1,"bar"}, {3,"tab"}, {4,"hover"}, {5,"field"}, {6,"panel"}, {7,"raised"}, {8,"key"}, {14,"tabOn"} };

static bool same(Rgb a, Rgb b) { return a.r == b.r && a.g == b.g && a.b == b.b; }

// Parses `{ "id", "Name", {r,g,b,255}, ... }` entries of omniThemes[] from OmniBrowser.cpp (the four literal themes).
static void checkAgainstSource(const char* path)
{
    std::ifstream f(path, std::ios::binary);
    CHECK(bool(f));
    if (!f) return;
    std::stringstream ss; ss << f.rdbuf();
    const std::string s = ss.str();
    const size_t start = s.find("static const OmniTheme omniThemes[] = {");
    CHECK(start != std::string::npos);
    if (start == std::string::npos) return;
    const std::string table = s.substr(start, s.find("\n};", start) - start);
    for (const Theme& t : kThemes) {
        const size_t at = table.find(std::string("{ \"") + t.id + "\"");
        CHECK(at != std::string::npos);
        if (at == std::string::npos) continue;
        const std::string rest = table.substr(at);
        static const std::regex col(R"(\{(\d+),(\d+),(\d+),255\})");
        std::vector<Rgb> got;
        for (auto it = std::sregex_iterator(rest.begin(), rest.end(), col); it != std::sregex_iterator() && got.size() < 17; ++it)
            got.push_back({ uint8_t(std::stoi((*it)[1])), uint8_t(std::stoi((*it)[2])), uint8_t(std::stoi((*it)[3])) });
        CHECK(got.size() == 17);
        bool all = got.size() == 17;
        for (size_t k = 0; all && k < 17; ++k) all = same(got[k], t.c[k]);
        if (!all) std::printf("FAIL theme %s in %s differs from the tested copy\n", t.id, path);
        CHECK(all);
    }
}

int main(int argc, char** argv)
{
    // Every theme (the 4 colour themes + High contrast's palette, for the record) x every accent.
    double worstFocus = 99, worstText = 99, worstText2 = 99;
    for (int a = 1; a < A::kCount; ++a) {
        for (const Theme& t : kThemes) {
            const A::Pick p = A::accentFor(a, t.id);
            CHECK(p.ok);
            CHECK(same(p.o.accent, A::kAccents[a].colour));
            for (const auto& s : kSurfaces) {
                const double r = A::contrast(p.o.accent, t.c[s.i]);
                if (r < A::kFocusMin) std::printf("FAIL focus %s on %s.%s: %.2f\n", A::kAccents[a].name, t.id, s.n, r);
                CHECK(r >= A::kFocusMin);
                worstFocus = std::min(worstFocus, r);
            }
            const double txt = A::contrast(p.o.accentInk, p.o.accent), txt2 = A::contrast(p.o.accentInk, p.o.accent2);
            if (txt < A::kTextMin) std::printf("FAIL text on %s: %.2f\n", A::kAccents[a].name, txt);
            CHECK(txt >= A::kTextMin);
            CHECK(txt2 >= A::kTextMin);
            worstText = std::min(worstText, txt); worstText2 = std::min(worstText2, txt2);
            // the auto ink is the better of black / white
            CHECK(txt >= A::contrast(A::kBlack, p.o.accent) - 1e-9 && txt >= A::contrast(A::kWhite, p.o.accent) - 1e-9);
        }
        std::printf("  %-8s ink %s  text %.2f:1\n", A::kAccents[a].name, same(A::inkOn(A::kAccents[a].colour), A::kBlack) ? "black" : "white",
                    A::contrast(A::inkOn(A::kAccents[a].colour), A::kAccents[a].colour));
    }
    std::printf("worst focus ring vs surface %.2f:1 (>= 3), worst text on accent %.2f:1, on accent2 %.2f:1 (>= 4.5)\n", worstFocus, worstText, worstText2);

    // High contrast keeps its yellow; Theme default keeps the theme's colours.
    for (int a = 0; a < A::kCount; ++a) CHECK(!A::accentFor(a, OmniHighContrast::kThemeId).ok);
    for (const Theme& t : kThemes) CHECK(!A::accentFor(0, t.id).ok);
    CHECK(!A::accentFor(-3, "dark").ok);
    CHECK(!A::accentFor(A::kCount, "dark").ok);
    CHECK(A::accentFor(1, nullptr).ok);

    // auto text colour picks white on dark colours, black on light ones
    CHECK(same(A::inkOn({ 0, 0, 80 }), A::kWhite));
    CHECK(same(A::inkOn({ 255, 255, 0 }), A::kBlack));
    CHECK(same(A::lighter({ 0, 100, 255 }, 30), Rgb { 76, 146, 255 }));

    // file format, ids, stepping
    for (int a = 0; a < A::kCount; ++a) {
        CHECK(A::parse(A::serialize(a)) == a);
        for (int b = 0; b < A::kCount; ++b)
            if (a != b) CHECK(std::strncmp(A::kAccents[a].id, A::kAccents[b].id, std::strlen(A::kAccents[a].id)) != 0);
    }
    CHECK(A::parse("") == 0);
    CHECK(A::parse("  Teal\r\n") == 2);
    CHECK(A::parse("magenta") == 0);
    CHECK(A::parse("blue2") == 0);
    CHECK(A::step(0, -1) == A::kCount - 1);
    CHECK(A::step(A::kCount - 1, 1) == 0);
    CHECK(A::step(3, 1) == 4);
    CHECK(A::step(99, 1) == 1);
    CHECK(std::string(A::name(0)) == "Theme default");
    CHECK(std::string(A::name(8)) == "Violet");
    CHECK(A::kCount == 9);
    CHECK(A::kRowId == 832);

    if (argc > 1) checkAgainstSource(argv[1]);
    std::printf("%s: %d passed, %d failed\n", fails ? "FAIL" : "OK", passes, fails);
    return fails ? 1 : 0;
}
