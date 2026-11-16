// OMNI_SETTINGS_SEARCH_V1: host tests of the pure part (OmniSettingsSearch.h).
//   g++ -std=c++20 -Wall -Wextra -I<dir with OmniSettingsSearch.h> test_settings_search.cpp -o t && ./t
#include "OmniSettingsSearch.h"
#include <cstdio>
#include <string>
#include <vector>

namespace S = OmniSettingsSearch;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

// Browser settings as built today (labels / values from omniFxSettingsBuild and the patches' rows, + in-progress ones)
static std::vector<S::Entry> panel()
{
    const std::vector<std::pair<std::string, std::string>> rows = {
        { "Search engine", "Google" }, { "Home page", "New-tab page" }, { "Continue watching on start page", "On" },
        { "Default page zoom", "100%" }, { "Text size", "100%" }, { "Pointer speed", "Normal" },
        { "Pointer snaps to links", "On" }, { "Pointer style", "Arrow  (1 of 6)" }, { "Pointer size", "100%" },
        { "Pointer colour", "White" }, { "Pointer outline", "On (contrasting)" }, { "Pointer opacity", "100%" },
        { "Stick dead zone", "Medium" }, { "D-pad left / right", "Back / forward" }, { "Dark mode", "Natural" },
        { "Search suggestions", "On" }, { "Tab limit", "8" }, { "Tabs kept loaded", "4" },
        { "Tab memory", "2 of 3 loaded \xc2\xb7 900 MiB free" }, { "Block pages from reaching the console", "On (recommended)" },
        { "Word suggestions", "On" }, { "Learn words I type", "On" }, { "Clear learned words", "" },
        { "Web pages can use the controller", "Off" }, { "Autoplay", "Block sound" }, { "HTTPS-only mode", "Off" },
        { "Ask sites not to sell or share my data", "On" }, { "Reload pages when back online", "On" },
        { "YouTube", "TV mode" }, { "Tell sites this is Omni", "On" }, { "JavaScript JIT (faster pages)", "On" },
        { "Quick bar and apps...", "L2 + Cross" }, { "Quick access buttons...", "" }, { "Quick access row", "Shown" },
        { "Bottom button bar", "Shown" }, { "Interface size", "Normal" }, { "Night light", "Off" },
        { "Show controls guide", "All shortcuts" }, { "Controller, theme and display...", "" },
        { "Send links from your phone", "Off" }, { "Passwords", "None" }, { "Autofill", "Off" },
        { "Site permissions", "" }, { "Keyboard layout", "English (US)" }, { "Video quality", "Auto" },
        { "Content blocker (uBlock Origin)", "On" }, { "About Omni", "F3 \xc2\xb7 Nov 16 2026" },
    };
    std::vector<S::Entry> v;
    int id = 1;
    for (const auto& [l, val] : rows) v.push_back({ id++, S::sectionOf(l), l, val });
    return v;
}
static std::vector<std::string> labels(const std::vector<S::Entry>& list, const std::vector<size_t>& pick)
{
    std::vector<std::string> o;
    for (size_t i : pick) o.push_back(list[i].label);
    return o;
}
static bool has(const std::vector<std::string>& v, const std::string& s) { for (auto& x : v) if (x == s) return true; return false; }
static int pos(const std::vector<std::string>& v, const std::string& s) { for (size_t i = 0; i < v.size(); ++i) if (v[i] == s) return int(i); return -1; }

int main()
{
    // normalization
    CHECK(S::norm("  HTTPS-only   mode ") == "https only mode");
    CHECK(S::norm("D-pad left / right") == "d pad left right");
    CHECK(S::norm("Quick bar and apps...") == "quick bar and apps");
    CHECK(S::norm("") == "");
    CHECK(S::cleanQuery("  dark \t mode \n") == "dark mode");
    CHECK(S::cleanQuery("   ").empty());
    CHECK(S::cleanQuery(std::string(100, 'a')).size() == S::kMaxQuery);
    {   // never cuts inside a UTF-8 sequence
        std::string q(59, 'a'); q += "\xc3\xa9\xc3\xa9";
        const std::string c = S::cleanQuery(q);
        CHECK(c.size() == 59);
    }
    CHECK(S::wordPrefix("pointer snaps to links", "snap"));
    CHECK(!S::wordPrefix("pointer snaps to links", "naps"));

    // sections
    CHECK(S::sectionOf("HTTPS-only mode") == "Privacy");
    CHECK(S::sectionOf("Ask sites not to sell or share my data") == "Privacy");
    CHECK(S::sectionOf("Learn words I type") == "Keyboard");
    CHECK(S::sectionOf("Clear learned words") == "Keyboard");
    CHECK(S::sectionOf("Autoplay") == "Media");
    CHECK(S::sectionOf("YouTube") == "Media");
    CHECK(S::sectionOf("Dark mode") == "Display");
    CHECK(S::sectionOf("Interface size") == "Display");
    CHECK(S::sectionOf("Night light") == "Display");
    CHECK(S::sectionOf("Controller, theme and display...") == "Display");
    CHECK(S::sectionOf("Pointer speed") == "Controls");
    CHECK(S::sectionOf("D-pad left / right") == "Controls");
    CHECK(S::sectionOf("Show controls guide") == "Controls");
    CHECK(S::sectionOf("Tab limit") == "Tabs");
    CHECK(S::sectionOf("Reload pages when back online") == "Network");
    CHECK(S::sectionOf("Search engine") == "Browsing");
    CHECK(S::sectionOf("About Omni") == "General");
    CHECK(S::sectionOf("Some future row") == "General");

    const auto list = panel();
    // empty query: everything, in order
    {
        const auto p = S::filter(list, "");
        CHECK(p.size() == list.size());
        CHECK(p.front() == 0 && p.back() == list.size() - 1);
        CHECK(S::filter(list, "   ").size() == list.size());
    }
    // word-prefix before substring, case-insensitive
    {
        const auto l = labels(list, S::filter(list, "PoInT"));
        CHECK(l.size() >= 6);
        CHECK(l[0] == "Pointer speed");   // label start, panel order
        CHECK(has(l, "Pointer opacity"));
    }
    {
        const auto l = labels(list, S::filter(list, "size"));
        CHECK(pos(l, "Text size") >= 0 && pos(l, "Pointer size") >= 0 && pos(l, "Interface size") >= 0);
    }
    {   // "tab": label starts first, then word starts, then mid-word ("start page" holds "tab" nowhere; "Stick" no)
        const auto l = labels(list, S::filter(list, "tab"));
        CHECK(l[0] == "Tab limit");
        CHECK(pos(l, "Tab limit") < pos(l, "Default page zoom") || pos(l, "Default page zoom") < 0);
        CHECK(has(l, "Tabs kept loaded"));
    }
    {   // substring after word-prefix: "light" (word) then "ight" mid-word
        const auto l = labels(list, S::filter(list, "ight"));
        CHECK(has(l, "Night light"));
        CHECK(has(l, "D-pad left / right"));
    }
    {   // squashed: "dpad" finds "D-pad", "https only" finds HTTPS-only
        CHECK(labels(list, S::filter(list, "dpad"))[0] == "D-pad left / right");
        CHECK(labels(list, S::filter(list, "https only"))[0] == "HTTPS-only mode");
        CHECK(labels(list, S::filter(list, "httpsonly"))[0] == "HTTPS-only mode");
    }
    {   // all words in any order
        const auto l = labels(list, S::filter(list, "opacity pointer"));
        CHECK(l.size() >= 1 && l[0] == "Pointer opacity");
        const auto y = labels(list, S::filter(list, "youtube tv"));
        CHECK(!y.empty() && y[0] == "YouTube");
    }
    {   // values match too, after labels
        const auto l = labels(list, S::filter(list, "natural"));
        CHECK(l.size() == 1 && l[0] == "Dark mode");
        const auto u = labels(list, S::filter(list, "english"));
        CHECK(u.size() == 1 && u[0] == "Keyboard layout");
    }
    // synonyms
    {
        const auto l = labels(list, S::filter(list, "dark"));
        CHECK(l[0] == "Dark mode");
        CHECK(has(l, "Controller, theme and display..."));
        CHECK(has(l, "Night light"));
    }
    {
        const auto l = labels(list, S::filter(list, "ads"));
        CHECK(has(l, "Content blocker (uBlock Origin)"));
    }
    {
        const auto l = labels(list, S::filter(list, "privacy"));
        CHECK(has(l, "HTTPS-only mode"));
        CHECK(has(l, "Ask sites not to sell or share my data"));
        CHECK(has(l, "Learn words I type"));
        CHECK(has(l, "Clear learned words"));
        CHECK(has(l, "Passwords"));
        CHECK(!has(l, "Pointer speed"));
        // the prefix of a key works too
        CHECK(has(labels(list, S::filter(list, "priv")), "HTTPS-only mode"));
    }
    {
        const auto l = labels(list, S::filter(list, "video"));
        CHECK(l[0] == "Video quality");
        CHECK(has(l, "Autoplay") && has(l, "YouTube") && has(l, "Continue watching on start page"));
    }
    {
        const auto l = labels(list, S::filter(list, "keyboard"));
        CHECK(l[0] == "Keyboard layout");
        CHECK(has(l, "Word suggestions") && has(l, "Learn words I type"));
    }
    {
        const auto l = labels(list, S::filter(list, "text size"));
        CHECK(l[0] == "Text size");
        CHECK(has(l, "Interface size") && has(l, "Default page zoom"));
        CHECK(!has(l, "Pointer size"));
    }
    {   // section names: "media" -> every Media row
        const auto l = labels(list, S::filter(list, "media"));
        CHECK(has(l, "Autoplay") && has(l, "YouTube") && has(l, "Video quality"));
    }
    // nothing
    CHECK(S::filter(list, "zzqx").empty());
    CHECK(S::countText(0, 47, "zzqx") == "No settings match \"zzqx\"");
    CHECK(S::countText(3, 47, "dark") == "3 of 47 settings match \"dark\"");

    // view(): steady while in use
    {
        std::vector<int> shown;
        auto v = list;
        auto p1 = S::view(v, "on", shown);   // label "on" words, values "On"
        CHECK(!p1.empty());
        // toggle a row whose value made it match: it stays, same place
        size_t hi = 0;
        for (size_t i = 0; i < p1.size(); ++i) if (v[p1[i]].label == "Pointer snaps to links") hi = i;
        CHECK(v[p1[hi]].label == "Pointer snaps to links");
        for (auto& e : v) if (e.label == "Pointer snaps to links") e.value = "Off";
        CHECK(S::tierOf(v[6], S::norm("on"), S::synonymPhrases("on")) == S::NoMatch);
        const auto p2 = S::view(v, "on", shown);
        CHECK(p2.size() == p1.size());
        CHECK(v[p2[hi]].label == "Pointer snaps to links");
        CHECK(p1 == p2);
        // a row that newly matches is appended
        CHECK(!has(labels(v, p1), "Autofill"));
        for (auto& e : v) if (e.label == "Autofill") e.value = "On";
        const auto p3 = S::view(v, "on", shown);
        CHECK(p3.size() == p1.size() + 1 && v[p3.back()].label == "Autofill");
        // a row that disappears from the panel is skipped
        v.erase(v.begin() + 6);
        const auto p4 = S::view(v, "on", shown);
        CHECK(p4.size() == p3.size() - 1);
        // empty query: everything, list cleared
        const auto p5 = S::view(v, "", shown);
        CHECK(p5.size() == v.size() && shown.empty());
    }
    // a row from a future patch is searchable with no table change
    {
        auto v = list;
        v.push_back({ 999, S::sectionOf("Clear browsing data range"), "Clear browsing data range", "Last hour" });
        const auto l = labels(v, S::filter(v, "range"));
        CHECK(l.size() == 1 && l[0] == "Clear browsing data range");
        CHECK(v.back().section == "Privacy");
        CHECK(has(labels(v, S::filter(v, "hour")), "Clear browsing data range"));
    }
    // ids are outside every Browser settings range (1..~30, 300+, 730.., 836..., 900+)
    CHECK(S::kSearchRowId < 0 && S::kNoMatchRowId < 0 && S::kSearchRowId != S::kNoMatchRowId);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
