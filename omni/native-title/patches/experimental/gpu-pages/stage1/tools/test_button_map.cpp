// OMNI_BUTTON_MAP_V1: host tests for OmniButtonMap.h (the pure part of Controller shortcuts), plus a cross-check
// against the tree's Controls guide table (OmniControlsHelp.h): every remappable button's default row is found once.
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_button_map.cpp -o t && ./t
#include "OmniButtonMap.h"
#include "OmniControlsHelp.h"

#include <cstdio>
#include <cstring>
#include <set>
#include <string>

namespace B = OmniButtonMap;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void testTables()
{
    // Defaults = today's mapping (button()'s browsing tail and omniL2Chord in the patched tree).
    const B::Map d = B::defaults();
    CHECK(d.a[B::sTriangle] == B::aAddressBar);
    CHECK(d.a[B::sSquare] == B::aNewTab);
    CHECK(d.a[B::sR3] == B::aCloseTab);
    CHECK(d.a[B::sL3] == B::aAddShortcut);
    CHECK(d.a[B::sTouchpad] == B::aTranslate);
    CHECK(d.a[B::sL2Square] == B::aCopy);
    CHECK(d.a[B::sL2Triangle] == B::aPaste);
    CHECK(d.a[B::sL2Cross] == B::aOptionsMenu);
    CHECK(d.a[B::sL2Circle] == B::aBrowserSettings);
    CHECK(B::changed(d) == 0);
    CHECK(B::summary(d) == "Default");
    for (int s = 0; s < B::kSlotCount; ++s) CHECK(B::isDefault(d, s));
    CHECK(!B::isDefault(d, -1) && !B::isDefault(d, B::kSlotCount));
    // Keys and labels: unique, non-empty; only Nothing has no hint.
    std::set<std::string> keys, labels;
    for (int a = 0; a < B::kActionCount; ++a) {
        CHECK(std::strlen(B::action(a).key) > 0);
        CHECK(std::strlen(B::action(a).label) > 0);
        CHECK((std::strlen(B::action(a).hint) == 0) == (a == B::aNone));
        keys.insert(B::action(a).key);
        labels.insert(B::action(a).label);
        CHECK(B::actionFromKey(B::action(a).key) == a);
    }
    CHECK(int(keys.size()) == B::kActionCount && int(labels.size()) == B::kActionCount);
    std::set<std::string> skeys;
    for (int s = 0; s < B::kSlotCount; ++s) {
        skeys.insert(B::slot(s).key);
        CHECK(B::slotFromKey(B::slot(s).key) == s);
        CHECK(B::slot(s).l2 == (s >= B::sL2Square));
        CHECK(B::slotName(s, true) == B::slot(s).ps && B::slotName(s, false) == B::slot(s).xbox);
    }
    CHECK(int(skeys.size()) == B::kSlotCount);
    CHECK(B::slotName(B::sL2Cross, false) == "LT + A" && B::slotName(B::sR3, true) == "R3");
    // The list offers every action exactly once, Nothing last.
    std::set<int> seen(B::choices().begin(), B::choices().end());
    CHECK(int(seen.size()) == B::kActionCount && int(B::choices().size()) == B::kActionCount);
    CHECK(B::choices().back() == B::aNone && B::choices().front() == B::aAddressBar);
    CHECK(B::actionFromKey("nope") == -1 && B::slotFromKey("cross") == -1);
    CHECK(std::strcmp(B::action(-3).key, "none") == 0 && std::strcmp(B::action(999).key, "none") == 0);
    CHECK(std::string(B::hint(d, B::sTriangle)) == "Address" && std::string(B::hint(d, B::sSquare)) == "New tab");
}

static void testFile()
{
    const B::Map d = B::defaults();
    CHECK(B::parse("") == d);
    CHECK(B::parse(B::serialize(d)) == d);
    B::Map m = d;
    m.a[B::sTriangle] = B::aReload; m.a[B::sR3] = B::aNone; m.a[B::sL2Circle] = B::aMagnifier;
    CHECK(B::parse(B::serialize(m)) == m);
    CHECK(B::changed(m) == 3 && B::summary(m) == "3 changed");
    // CRLF, spaces, case, '=', comments, unknown and broken lines; a later line wins.
    const B::Map p = B::parse("# comment\r\nTRIANGLE\t Reload \r\nsquare=find\r\nbogus\tback\r\nr3\tteleport\r\nl3\r\n\r\n"
                              "touchpad\tqr\r\ntouchpad\tbookmark\r\n#l2+cross\tnone\r\nl2+cross\tnone");
    CHECK(p.a[B::sTriangle] == B::aReload);
    CHECK(p.a[B::sSquare] == B::aFind);
    CHECK(p.a[B::sR3] == B::aCloseTab);
    CHECK(p.a[B::sL3] == B::aAddShortcut);
    CHECK(p.a[B::sTouchpad] == B::aBookmark);
    CHECK(p.a[B::sL2Cross] == B::aNone);
    CHECK(p.a[B::sL2Square] == B::aCopy);
    // Only the first kMaxFileBytes count.
    std::string big(B::kMaxFileBytes, '\n');
    CHECK(B::parse(big + "triangle\tback\n") == d);
    CHECK(B::parse(std::string(B::kMaxFileBytes - 20, '\n') + "triangle\tback\n").a[B::sTriangle] == B::aBack);
    // Garbage bytes never crash and keep the defaults.
    std::string junk;
    for (int i = 0; i < 3000; ++i) junk += char((i * 37 + 11) & 0xff);
    CHECK(B::parse(junk) == d);
    // serialize writes every button, a header comment, one line each; a bad value falls back to the default.
    const std::string s = B::serialize(d);
    CHECK(s.rfind("# ", 0) == 0);
    int lines = 0;
    for (char c : s) lines += c == '\n';
    CHECK(lines == B::kSlotCount + 1);
    CHECK(s.find("triangle\taddress\n") != std::string::npos && s.find("l2+circle\tsettings\n") != std::string::npos);
    B::Map bad = d;
    bad.a[B::sSquare] = 77;
    CHECK(B::parse(B::serialize(bad)) == d);
}

static void testStep()
{
    const auto& c = B::choices();
    int a = c[0];
    std::set<int> visited;
    for (size_t i = 0; i < c.size(); ++i) { visited.insert(a); a = B::stepAction(a, 1); }
    CHECK(a == c[0] && visited.size() == c.size());
    CHECK(B::stepAction(c[0], -1) == c.back());
    CHECK(B::stepAction(c.back(), 1) == c[0]);
    CHECK(B::stepAction(B::aNewTab, -1) == B::aAddressBar);
    CHECK(B::stepAction(999, 1) == c[1]);
    for (size_t i = 0; i < c.size(); ++i) CHECK(B::choiceIndex(c[i]) == int(i));
    CHECK(B::choiceIndex(999) == 0);
}

static bool has(const std::vector<B::Conflict>& v, int kind, int slot, int other = -2)
{
    for (const auto& c : v) if (c.kind == kind && c.slot == slot && (other == -2 || c.other == other)) return true;
    return false;
}

static void testConflicts()
{
    const B::Map d = B::defaults();
    CHECK(B::conflicts(d, -1).empty());
    for (int s = 0; s < B::kSlotCount; ++s) CHECK(B::slotDetail(d, s, -1, true).empty());
    // Duplicates: both buttons say so.
    B::Map m = d;
    m.a[B::sR3] = B::aNewTab;
    auto v = B::conflicts(m, -1);
    CHECK(has(v, B::kDuplicate, B::sR3, B::sSquare) && has(v, B::kDuplicate, B::sSquare, B::sR3));
    CHECK(B::slotDetail(m, B::sR3, -1, true) == "Also on Square");
    CHECK(B::slotDetail(m, B::sSquare, -1, false) == "Also on RS");
    CHECK(B::usedBy(m, B::aNewTab, B::sSquare, true) == "Also on R3");
    CHECK(B::usedBy(m, B::aReload, B::sSquare, true).empty());
    // Nothing on two buttons is no conflict.
    m = d; m.a[B::sL3] = B::aNone; m.a[B::sTouchpad] = B::aNone;
    CHECK(B::conflicts(m, -1).empty());
    CHECK(B::slotDetail(m, B::sL3, -1, true) == "Default: Add this page to shortcuts");
    CHECK(B::usedBy(m, B::aNone, B::sR3, true).empty());
    // The add-on quick switch owns its button.
    v = B::conflicts(d, B::sL3);
    CHECK(v.size() == 1 && has(v, B::kAddonOwns, B::sL3));
    CHECK(B::slotDetail(d, B::sL3, B::sL3, true).find("add-on") != std::string::npos);
    CHECK(B::conflicts(d, B::sR3).empty());   // only L3 / touchpad can be add-on buttons
    // No address bar: a panel-wide note (also when it is only on the add-on's button).
    m = d; m.a[B::sTriangle] = B::aReload;
    v = B::conflicts(m, -1);
    CHECK(has(v, B::kNoAddressBar, -1));
    CHECK(B::panelNote(m, -1, true).find("address bar") != std::string::npos);
    CHECK(B::panelNote(d, -1, true).find("Triangle") != std::string::npos);
    CHECK(B::panelNote(d, -1, false).find("Y: ") != std::string::npos);
    m.a[B::sTouchpad] = B::aAddressBar;
    CHECK(!has(B::conflicts(m, -1), B::kNoAddressBar, -1));
    CHECK(has(B::conflicts(m, B::sTouchpad), B::kNoAddressBar, -1));
    // Tab switcher without L2: told how to switch; on an L2 chord it is not.
    m = d; m.a[B::sSquare] = B::aTabSwitcher;
    CHECK(has(B::conflicts(m, -1), B::kSwitcherNoL2, B::sSquare));
    CHECK(B::slotDetail(m, B::sSquare, -1, true) == "Tab switcher: Cross switches, Circle cancels");
    m = d; m.a[B::sL2Square] = B::aTabSwitcher;
    CHECK(B::conflicts(m, -1).empty());
    CHECK(B::slotDetail(m, B::sL2Square, -1, true) == "Default: Copy the text, link or page address");
}

static void testGuide()
{
    // Every remappable button's default row is in the tree's Controls guide table exactly once.
    int found[B::kSlotCount] = {};
    for (const auto& e : OmniControlsHelp::table()) {
        const int s = B::guideSlot(e.action, e.where);
        if (s < 0) continue;
        ++found[s];
        CHECK(std::string(e.action) == B::action(B::slot(s).def).label);   // the guide says what the default is
    }
    for (int s = 0; s < B::kSlotCount; ++s) {
        if (found[s] != 1) std::printf("guide rows for %s: %d\n", B::slot(s).key, found[s]);
        CHECK(found[s] == 1);
    }
    // Rows that only look alike stay alone.
    CHECK(B::guideSlot("Options menu", "button() omniFxQuickMenuShow") == -1);
    CHECK(B::guideSlot("Browser settings", "button() omniFxSettingsShow (OMNI_SETTINGS_CREATE_V1)") == -1);
    CHECK(B::guideSlot("Find bar: search for something else", "omniFindButton") == -1);
    CHECK(B::guideSlot("New tab", "omniFxTabsInput") == -1);
    CHECK(B::guideSlot(nullptr, "button()") == -1 && B::guideSlot("New tab", nullptr) == -1);
    // The text a remapped row shows.
    B::Map m = B::defaults();
    std::string a, n;
    CHECK(!B::guideText(m, B::sTriangle, -1, a, n));
    CHECK(!B::guideText(m, -1, -1, a, n));
    m.a[B::sTriangle] = B::aReader;
    CHECK(B::guideText(m, B::sTriangle, -1, a, n) && a == "Reader view" && n.find("Controller shortcuts") != std::string::npos);
    m.a[B::sL3] = B::aNone;
    CHECK(B::guideText(m, B::sL3, B::sL3, a, n) && a == "Nothing" && n.find("add-on") != std::string::npos);
}

int main()
{
    testTables();
    testFile();
    testStep();
    testConflicts();
    testGuide();
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
