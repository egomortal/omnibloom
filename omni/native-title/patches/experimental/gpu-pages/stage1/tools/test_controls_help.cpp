// OMNI_CONTROLS_HELP_V1: tests for OmniControlsHelp.h (pure). g++ -std=c++17 -I<entry> test_controls_help.cpp
#include "OmniControlsHelp.h"

#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <tuple>

namespace OCH = OmniControlsHelp;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static std::string prefixOf(const std::string& action)
{
    const size_t c = action.find(':');
    return c == std::string::npos ? std::string() : action.substr(0, c);
}

int main()
{
    const auto& t = OCH::table();
    CHECK(t.size() >= 60);

    // --- every row is complete --------------------------------------------------------------------------------------
    for (const auto& e : t) {
        CHECK(e.section >= 0 && e.section < OCH::kSectionCount);
        CHECK(e.action && *e.action);
        CHECK(e.note != nullptr);
        CHECK(e.where && *e.where);
        CHECK(e.keys[0] > OCH::gNone && e.keys[0] < OCH::gGlyphCount);
        int n = 0;
        for (int k : e.keys) { if (k == OCH::gNone) break; CHECK(k > OCH::gNone && k < OCH::gGlyphCount); ++n; }
        CHECK((n >= 2) == (e.join == '+' || e.join == '/'));
        CHECK(std::strlen(e.action) <= 44);
        CHECK(std::strlen(e.note) <= 70);
    }
    // --- sections: all present, each fits one page, glyphs fit their column -----------------------------------------
    for (int s = 0; s < OCH::kSectionCount; ++s) {
        const auto rows = OCH::entriesOf(s);
        CHECK(rows.size() >= 4);
        const OCH::Layout L = OCH::layout(int(rows.size()));
        CHECK(L.pages == 1);
        CHECK(*OCH::sectionTitle(s) && *OCH::sectionWhere(s));
        for (size_t i = 0; i < rows.size(); ++i) {
            const OCH::Slot sl = OCH::place(int(i), L);
            CHECK(sl.x >= OCH::kMarginX && sl.x + L.colW <= OCH::kScreenW - OCH::kMarginX);
            CHECK(sl.y >= OCH::kListTop && sl.y + OCH::kRowH <= OCH::kListBottom);
        }
    }
    for (const auto& e : t) {
        CHECK(OCH::comboWidth(e, true) <= OCH::kGlyphColW - 12);
        CHECK(OCH::comboWidth(e, false) <= OCH::kGlyphColW - 12);
    }
    // --- the same buttons twice in one section need a sub-context ("Find bar: ...") or a different note ---------------
    {
        std::set<std::tuple<int, int, int, int, int, bool, std::string, std::string>> seen;
        for (const auto& e : t) {
            const auto key = std::make_tuple(e.section, e.keys[0], e.keys[1], e.keys[2], int(e.join), e.hold, prefixOf(e.action), std::string(e.note));
            const bool fresh = seen.insert(key).second;
            if (!fresh) std::printf("duplicate: %s\n", e.action);
            CHECK(fresh);
        }
    }
    // --- names and tokens ---------------------------------------------------------------------------------------------
    CHECK(OCH::expand("{Cross} then {Options}", true) == "Cross then Options");
    CHECK(OCH::expand("{Cross} then {Options}", false) == "A then Menu");
    CHECK(OCH::expand("{L3} {R1} {Create} {Unknown}", false) == "LS RB View {Unknown}");
    for (const auto& e : t)
        for (bool ps : { true, false }) {
            CHECK(OCH::expand(e.action, ps).find('{') == std::string::npos);
            CHECK(OCH::expand(e.note, ps).find('{') == std::string::npos);
        }
    for (int s = 0; s < OCH::kSectionCount; ++s) CHECK(OCH::expand(OCH::sectionWhere(s), false).find('{') == std::string::npos);
    for (int g = OCH::gCross; g < OCH::gGlyphCount; ++g) { CHECK(*OCH::glyphName(g, true)); CHECK(*OCH::glyphName(g, false)); }
    CHECK(std::string(OCH::glyphName(OCH::gR3, true)) == "R3" && std::string(OCH::glyphName(OCH::gR3, false)) == "RS");
    CHECK(OCH::hintText(true) == "Press Options \xe2\x86\x92 Controls for all shortcuts");
    CHECK(OCH::hintText(false) == "Press Menu \xe2\x86\x92 Controls for all shortcuts");
    CHECK(std::string(OCH::kFlagPath) == "/data/omni/controls-hint-shown.flag");

    // --- section order and context ---------------------------------------------------------------------------------
    for (int first = 0; first < OCH::kSectionCount; ++first) {
        const auto o = OCH::order(first);
        CHECK(int(o.size()) == OCH::kSectionCount && o[0] == first);
        std::set<int> u(o.begin(), o.end());
        CHECK(int(u.size()) == OCH::kSectionCount);
    }
    CHECK(OCH::order(-3)[0] == OCH::kBrowsing && OCH::order(99)[0] == OCH::kBrowsing);
    CHECK(OCH::order(OCH::kTabs)[1] == OCH::kBrowsing);
    CHECK(OCH::step(0, -1, 8) == 7 && OCH::step(7, 1, 8) == 0 && OCH::step(3, 0, 8) == 3 && OCH::step(0, 1, 0) == 0);
    CHECK(OCH::sectionFor(OCH::kFromTabs) == OCH::kTabs && OCH::sectionFor(OCH::kFromSessions) == OCH::kTabs);
    CHECK(OCH::sectionFor(OCH::kFromNowPlaying) == OCH::kVideo && OCH::sectionFor(OCH::kFromSleep) == OCH::kVideo);
    CHECK(OCH::sectionFor(OCH::kFromFullscreen) == OCH::kVideo && OCH::sectionFor(OCH::kFromKeyboard) == OCH::kKeyboard);
    CHECK(OCH::sectionFor(OCH::kFromContextMenu) == OCH::kQuick && OCH::sectionFor(OCH::kFromReading) == OCH::kReading);
    CHECK(OCH::sectionFor(OCH::kFromDownloads) == OCH::kDownloads && OCH::sectionFor(OCH::kFromHistory) == OCH::kHistory);
    CHECK(OCH::sectionFor(OCH::kFromOptions) == OCH::kBrowsing && OCH::sectionFor(OCH::kFromSettings) == OCH::kBrowsing);
    CHECK(OCH::firstSection(OCH::kFromTabs, OCH::kFromReading, 10) == OCH::kTabs);              // the panel under it wins
    CHECK(OCH::firstSection(OCH::kFromNone, OCH::kFromReading, 1000) == OCH::kReading);         // just closed
    CHECK(OCH::firstSection(OCH::kFromOptions, OCH::kFromDownloads, OCH::kRecentMs) == OCH::kDownloads);
    CHECK(OCH::firstSection(OCH::kFromNone, OCH::kFromReading, OCH::kRecentMs + 1) == OCH::kBrowsing);   // too long ago
    CHECK(OCH::firstSection(OCH::kFromNone, OCH::kFromNone, 0) == OCH::kBrowsing);
    CHECK(!OCH::rememberable(OCH::kFromKeyboard) && !OCH::rememberable(OCH::kFromOptions) && OCH::rememberable(OCH::kFromHistory));

    // --- tabs and layout ---------------------------------------------------------------------------------------------
    for (int i = 0; i < OCH::kSectionCount; ++i) {
        const OCH::Tab a = OCH::tabRect(i, OCH::kSectionCount);
        CHECK(a.w >= 120 && a.x >= OCH::kMarginX && a.x + a.w <= OCH::kScreenW - OCH::kMarginX);
        if (i) { const OCH::Tab b = OCH::tabRect(i - 1, OCH::kSectionCount); CHECK(b.x + b.w < a.x); }
        CHECK(OCH::tabAt(a.x + a.w / 2, OCH::kTabsY + 5, OCH::kSectionCount) == i);
    }
    CHECK(OCH::tabAt(640, OCH::kTabsY - 1, OCH::kSectionCount) == -1 && OCH::tabAt(10, OCH::kTabsY + 5, OCH::kSectionCount) == -1);
    {
        const OCH::Layout one = OCH::layout(5);
        CHECK(one.cols == 1 && one.pages == 1 && one.colW <= 760);
        const OCH::Layout two = OCH::layout(17);
        const int rpc = (OCH::kListBottom - OCH::kListTop) / OCH::kRowH;
        CHECK(rpc >= 11 && two.cols == 2 && two.rowsPerCol == rpc && two.pages == 1);
        CHECK(OCH::place(rpc - 1, two).col == 0 && OCH::place(rpc, two).col == 1 && OCH::place(rpc, two).row == 0);
        const OCH::Layout many = OCH::layout(45);
        CHECK(many.pages == 3 && OCH::place(44, many).page == 2);
        CHECK(OCH::layout(0).pages == 1);
    }
    // --- first-launch hint -------------------------------------------------------------------------------------------
    CHECK(!OCH::hintDue(false, false, OCH::kHintDelayMs - 1));
    CHECK(OCH::hintDue(false, false, OCH::kHintDelayMs));
    CHECK(!OCH::hintDue(false, true, 60000));
    CHECK(!OCH::hintDue(true, false, 60000));
    // ids stay clear of the rows around them
    CHECK(OCH::kQuickTileId != 8100 && (OCH::kQuickTileId < 8000 || OCH::kQuickTileId > 8005));
    CHECK(OCH::kSettingsRowId < 845 && OCH::kSettingsRowId >= 300);

    std::printf("%s: %d checks, %d failed (%zu rows)\n", fails ? "FAILED" : "ok", checks, fails, t.size());
    return fails ? 1 : 0;
}
