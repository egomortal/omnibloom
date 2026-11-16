// OMNI_KB_EMOJI_V1: tests of the pure part (OmniKbEmoji.h, written by apply_kb_emoji.py).
//   python3 apply_kb_emoji.py --header /tmp/h/OmniKbEmoji.h
//   g++ -std=c++20 -Wall -Wextra -I/tmp/h test_kb_emoji.cpp -o t && ./t
#include "OmniKbEmoji.h"
#include <cstdio>
#include <set>

namespace E = OmniKbEmoji;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static bool validCell(const std::string& s, bool flag)
{
    const auto cps = E::codepoints(s);
    // re-encode: the cell must be exactly valid UTF-8
    std::string back;
    for (uint32_t cp : cps) {
        if (cp < 0x80) back += char(cp);
        else if (cp < 0x800) { back += char(0xc0 | (cp >> 6)); back += char(0x80 | (cp & 0x3f)); }
        else if (cp < 0x10000) { back += char(0xe0 | (cp >> 12)); back += char(0x80 | ((cp >> 6) & 0x3f)); back += char(0x80 | (cp & 0x3f)); }
        else { back += char(0xf0 | (cp >> 18)); back += char(0x80 | ((cp >> 12) & 0x3f)); back += char(0x80 | ((cp >> 6) & 0x3f)); back += char(0x80 | (cp & 0x3f)); }
    }
    if (back != s) return false;
    if (flag) return cps.size() == 2 && E::isRegionalIndicator(cps[0]) && E::isRegionalIndicator(cps[1]);
    if (cps.size() == 2) return cps[1] == 0xfe0f && cps[0] >= 0xa9;
    return cps.size() == 1 && cps[0] >= 0xa9 && cps[0] != 0x200d && !E::isRegionalIndicator(cps[0]);
}

int main()
{
    // The table: valid single-emoji cells, no duplicates anywhere, the categories asked for.
    std::set<std::string> all;
    size_t total = 0;
    CHECK(std::string(E::category(E::kRecent).list).empty());
    for (int c = E::kSmileys; c < E::kCatCount; ++c) {
        const auto cells = E::split(E::category(c).list);
        CHECK(cells.size() >= 40);
        for (const auto& s : cells) {
            if (!validCell(s, c == E::kFlags)) { std::printf("bad cell in %s\n", E::category(c).name); CHECK(false); }
            CHECK(all.insert(s).second);
            CHECK(s.find(' ') == std::string::npos);
        }
        total += cells.size();
    }
    std::printf("table: %zu cells\n", total);
    CHECK(std::string(E::category(E::kSmileys).tab) == "Smileys" && std::string(E::category(E::kFlags).tab) == "Flags");
    CHECK(std::string(E::category(99).tab) == "Flags");   // clamped
    // UTF-8 helpers
    CHECK(E::codepoints("\xf0\x9f\x98\x80") == std::vector<uint32_t>{ 0x1f600 });
    CHECK(E::codepoints("a\xff" "b").size() == 2);                       // invalid byte skipped
    CHECK(E::codepoints("\xe2\x9d").empty());                            // truncated sequence skipped
    CHECK(E::display("\xe2\x9d\xa4\xef\xb8\x8f") == "\xe2\x9d\xa4");     // heart without VS16
    CHECK(E::display("\xf0\x9f\x98\x80") == "\xf0\x9f\x98\x80");
    CHECK(E::split("a b  c") == (std::vector<std::string>{ "a", "b", "c" }));
    CHECK(E::split("").empty());
    CHECK(std::string(E::kKeyLabel) == "\xf0\x9f\x98\x80");
    CHECK(all.count("\xe2\x9d\xa4\xef\xb8\x8f"));   // the heart carries U+FE0F (text default)
    CHECK(all.count("\xf0\x9f\x87\xba\xf0\x9f\x87\xb8"));   // US flag

    // build(): the predicate sees display text; flags only when allowed.
    {
        E::Picker p;
        int calls = 0;
        bool sawVs = false;
        p.build([&](const std::string& s) { ++calls; if (s.find("\xef\xb8\x8f") != std::string::npos) sawVs = true; return true; }, false);
        CHECK(p.built && calls > 0 && !sawVs);
        CHECK(p.items[E::kFlags].empty());
        CHECK(p.items[E::kSmileys].size() == E::split(E::category(E::kSmileys).list).size());
        CHECK(!p.items[E::kFlags].size());
        E::Picker q;
        q.build([](const std::string&) { return true; }, true);
        CHECK(q.items[E::kFlags].size() == E::split(E::category(E::kFlags).list).size());
    }
    // Only smileys + symbols drawable (like the shipped fonts, roughly): tabs skip empty categories, Recent hidden.
    E::Picker p;
    p.build([](const std::string& s) {
        const auto cps = E::codepoints(s);
        return cps.size() == 1 && ((cps[0] >= 0x1f600 && cps[0] <= 0x1f640) || (cps[0] >= 0x2600 && cps[0] <= 0x26ff));
    }, false);
    CHECK(p.tabs().size() >= 2 && p.tabs().front() == E::kSmileys);
    for (int c : p.tabs()) CHECK(p.hasItems(c));
    CHECK(!p.hasItems(E::kRecent) && !p.hasItems(E::kFlags));
    CHECK(p.items[E::kFood].size() == 1);   // only the hot beverage (U+2615) of Food is in the predicate's range
    p.open();
    CHECK(p.cat == E::kSmileys && p.sel == 0 && p.top == 0 && !p.onActions);
    const int n = p.count();
    CHECK(n > E::kCols * E::kRows);   // scrolls
    // Category switching wraps over the non-empty tabs only.
    const auto tabs = p.tabs();
    p.switchCategory(1);
    CHECK(p.cat == tabs[1] && p.sel == 0);
    p.switchCategory(-1);
    CHECK(p.cat == tabs[0]);
    p.switchCategory(-1);
    CHECK(p.cat == tabs.back());
    p.switchCategory(1);
    CHECK(p.cat == tabs.front());
    // Left/right walk in order and wrap.
    p.move(-1, 0);
    CHECK(p.sel == n - 1 && !p.onActions);
    CHECK(p.top == p.rowCount() - E::kRows);   // scrolled to the end
    p.move(1, 0);
    CHECK(p.sel == 0 && p.top == 0);
    p.move(1, 0); p.move(1, 0);
    CHECK(p.sel == 2);
    // Down by rows, scrolling once past the 4 visible rows.
    for (int i = 0; i < 4; ++i) p.move(0, 1);
    CHECK(p.sel == 2 + 4 * E::kCols && p.top == 1);
    CHECK(p.current() && *p.current() == p.list()[size_t(p.sel)]);
    // Up back to row 0, then up again onto the action row (action under the column: col 2 -> action 1).
    for (int i = 0; i < 4; ++i) p.move(0, -1);
    CHECK(p.sel == 2 && p.top == 0);
    p.move(0, -1);
    CHECK(p.onActions && p.action == 1 && !p.current());
    // Action row: left/right wrap over the 5 keys.
    p.move(-1, 0); p.move(-1, 0);
    CHECK(p.action == E::kActClose);
    p.move(1, 0);
    CHECK(p.action == E::kActLetters);
    // Down from the action row: the first row, column 2*action.
    p.action = E::kActGo;
    p.move(0, 1);
    CHECK(!p.onActions && p.sel == 6 && p.top == 0);
    // Up from the action row: the last row (scrolled), clamped to the last cell.
    p.move(0, -1);   // row 0 -> actions (col 6 -> action 3)
    CHECK(p.onActions && p.action == 3);
    p.move(0, -1);
    CHECK(!p.onActions && p.sel == std::min((p.rowCount() - 1) * E::kCols + 6, n - 1));
    CHECK(p.top == p.rowCount() - E::kRows);
    // Down past the last row: onto the action row.
    p.move(0, 1);
    CHECK(p.onActions);
    // A short last row: down from a column the last row lacks lands on the last cell.
    if (n % E::kCols) {
        p.onActions = false;
        p.sel = (p.rowCount() - 2) * E::kCols + E::kCols - 1;
        p.ensureVisible();
        p.move(0, 1);
        CHECK(p.sel == n - 1 && !p.onActions);
    }
    // Pointer: cells in the visible window, tabs by position.
    p.select(E::kSmileys);
    CHECK(p.cellAt(0, 0) == 0 && p.cellAt(3, 9) == 39 && p.cellAt(4, 0) == -1 && p.cellAt(0, 10) == -1);
    p.top = 1;
    CHECK(p.cellAt(0, 0) == E::kCols);
    CHECK(p.tabAt(0, 88) == tabs[0] && p.tabAt(88, 88) == tabs[1] && p.tabAt(-1, 88) == -1 && p.tabAt(88 * 10, 88) == -1);
    // Recent: newest first, no duplicates, at most kRecentMax, memory only; becomes a tab and the opening category.
    p.select(E::kSmileys);
    const auto& sm = p.items[E::kSmileys];
    p.remember(sm[0]); p.remember(sm[1]); p.remember(sm[0]);
    CHECK(p.recent.size() == 2 && p.recent[0] == sm[0] && p.recent[1] == sm[1]);
    CHECK(p.tabs().front() == E::kRecent);
    p.open();
    CHECK(p.cat == E::kRecent && p.count() == 2);
    p.remember(sm[1]);   // used again while Recent is shown: order kept
    CHECK(p.recent[0] == sm[0] && p.recent[1] == sm[1]);
    p.select(E::kSmileys);
    p.remember(sm[1]);   // from another tab: to the front
    CHECK(p.recent[0] == sm[1]);
    for (size_t i = 0; i < sm.size() && i < 30; ++i) p.remember(sm[i]);
    CHECK(p.recent.size() == E::kRecentMax && p.recent[0] == sm[std::min<size_t>(29, sm.size() - 1)]);
    std::set<std::string> uniq(p.recent.begin(), p.recent.end());
    CHECK(uniq.size() == p.recent.size());
    // Nothing drawable: the page opens on the action row and the D-pad stays safe.
    E::Picker z;
    z.build([](const std::string&) { return false; }, false);
    CHECK(z.tabs().empty());
    z.open();
    CHECK(z.onActions && z.action == E::kActLetters && !z.current());
    z.move(0, 1); z.move(1, 0); z.move(0, -1); z.switchCategory(1);
    CHECK(z.onActions && !z.current() && z.cellAt(0, 0) == -1 && z.tabAt(0, 88) == -1);
    // A one-cell category: every move keeps a valid focus.
    E::Picker one;
    one.build([](const std::string& s) { return s == "\xf0\x9f\x98\x80"; }, false);
    one.open();
    CHECK(one.count() == 1 && one.sel == 0);
    one.move(1, 0); CHECK(one.sel == 0);
    one.move(-1, 0); CHECK(one.sel == 0);
    one.move(0, 1); CHECK(one.onActions);
    one.move(0, 1); CHECK(!one.onActions && one.sel == 0);
    one.move(0, -1); CHECK(one.onActions);
    one.move(0, -1); CHECK(!one.onActions && one.sel == 0);

    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
