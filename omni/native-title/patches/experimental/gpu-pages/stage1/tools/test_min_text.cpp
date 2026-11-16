// OMNI_MIN_TEXT_V1: host test of the pure part (OmniMinText.h).
//   g++ -std=c++20 -Wall -Wextra -I. test_min_text.cpp -o t && ./t [<tree>/engine/entry [<webkit>/Source]]
// With the tree's entry folder it checks each patched site (or, before apply_min_text.py, that the anchors are there
// once). With WebKit's Source folder it checks the C API, the preference's yaml entry and the hard-minimum lines that
// OmniMinText::usedSize copies.
#include "OmniMinText.h"
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

namespace M = OmniMinText;
static int failures = 0, checks = 0;
static void expect(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL: %s\n", what); }
}
static std::string slurp(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}
static size_t count(const std::string& s, const std::string& what)
{
    size_t n = 0;
    for (size_t p = s.find(what); p != std::string::npos; p = s.find(what, p + 1)) ++n;
    return n;
}

static void testFile()
{
    expect(M::parse("") == 0 && M::parse("off") == 0 && M::parse("off\n") == 0, "parse: Off");
    expect(M::parse("16") == 16 && M::parse("16\n") == 16 && M::parse(" 20\r\n") == 20 && M::parse("12") == 12, "parse: sizes");
    expect(M::parse("15") == 0 && M::parse("0") == 0 && M::parse("160") == 0 && M::parse("1600") == 0, "parse: other numbers -> Off");
    expect(M::parse("-16") == 0 && M::parse("16px") == 0 && M::parse("1 6") == 0 && M::parse("abc") == 0, "parse: junk -> Off");
    for (int px : M::kSizes) expect(M::parse(M::serialize(px)) == px, "serialize / parse round trip");
    expect(M::serialize(0) == "off\n" && M::serialize(18) == "18\n" && M::serialize(13) == "off\n", "serialize");
}

static void testRow()
{
    expect(M::kCount == 6 && M::kSizes[0] == 0 && M::kSizes[5] == 20, "Off / 12 / 14 / 16 / 18 / 20");
    for (int i = 1; i < M::kCount; ++i) expect(M::kSizes[i] > M::kSizes[i - 1], "sizes ascending");
    expect(M::rowValue(0) == "Off" && M::rowValue(14) == "14 px" && M::rowValue(7) == "Off", "rowValue");
    expect(M::noticeText(0) == "Minimum text size off" && M::noticeText(20) == "Minimum text size 20 px", "noticeText");
    expect(M::stepped(0, -1) == 0 && M::stepped(0, 1) == 12 && M::stepped(12, 1) == 14 && M::stepped(20, 1) == 20
           && M::stepped(20, -1) == 18 && M::stepped(12, -1) == 0 && M::stepped(16, 0) == 16, "stepped: clamps at both ends");
    expect(M::stepped(13, 1) == 12 && M::stepped(13, -1) == 0, "stepped: unknown value counts as Off");
    int px = 0, n = 0;
    do { px = M::cycled(px); ++n; } while (px != 0 && n < 20);
    expect(n == M::kCount, "cycled: visits every size, wraps to Off");
    expect(M::cycled(20) == 0 && M::cycled(99) == 12, "cycled: wrap / unknown");
    expect(M::webkitValue(16, false) == 16u && M::webkitValue(0, false) == 0u && M::webkitValue(16, true) == 0u
           && M::webkitValue(15, false) == 0u, "webkitValue: Off, test modes and unknown sizes send 0");
    expect(std::string(M::kFileName) == "min-text.txt" && M::kRowId == 817, "file name, row id");
}

static void testRule()
{
    expect(M::usedSize(10, 1, 16) == 16 && M::usedSize(20, 1, 16) == 20 && M::usedSize(16, 1, 16) == 16, "hard minimum");
    expect(M::usedSize(0, 1, 16) == 0, "0 px text stays hidden");
    expect(M::usedSize(10, 2, 16) == 20 && M::usedSize(10, 0.5f, 16) == 16, "minimum applies after zoom");
    expect(M::usedSize(10, 1, 0) == 10, "Off: unchanged");
}

static void testTree(const std::string& dir)
{
    const std::string browser = slurp(dir + "/OmniBrowser.cpp"), settings = slurp(dir + "/OmniBrowserSettings.h"),
        f3 = slurp(dir + "/OmniFeatures3.h"), search = slurp(dir + "/OmniSettingsSearch.h");
    expect(!browser.empty() && !settings.empty() && !f3.empty() && !search.empty(), "tree files found");
    const bool patched = count(browser, "OMNI_MIN_TEXT_V1") > 0;
    std::printf("tree: %s\n", patched ? "patched" : "not patched yet");
    expect(count(browser, "    WKPreferencesSetFullScreenEnabled(preferences.get(), true);") == 1, "tree: preferences anchor once");
    expect(count(browser, "#include \"OmniCaptionStyle.h\"") == 1, "tree: caption include once");
    expect(count(settings, "    omniCcsSettingsRow(p);") == 1 && count(settings, "return omniCcsSettingsInput(b);") == 1,
           "tree: Captions row and dispatch once");
    if (!patched) {
        expect(count(browser + settings + f3, "omniMtx") == 0 && count(browser, "WKPreferencesSetMinimumFontSize") == 0,
               "tree: nothing of ours yet, no other minimum-font call");
        return;
    }
    const std::string shell = slurp(dir + "/OmniMinTextShell.h"), pure = slurp(dir + "/OmniMinText.h");
    expect(count(pure, "constexpr int kRowId = 817;") == 1, "tree: pure header copied");
    expect(count(shell, "WKPreferencesSetMinimumFontSize(preferences.get(), OMTX::webkitValue(") == 1, "tree: shell calls WebKit");
    expect(count(browser, "#include \"OmniMinText.h\"") == 1 && count(browser, "namespace OMTX = OmniMinText;") == 1, "tree: include + alias");
    expect(count(browser, "    omniMtxApplyStartup();") == 1
           && browser.find("    omniMtxApplyStartup();") > browser.find("    WKPreferencesSetFullScreenEnabled(preferences.get(), true);"),
           "tree: startup call after the preferences are made");
    expect(browser.find("#include \"OmniFeatures3.h\"") < browser.find("    omniMtxApplyStartup();"), "tree: shell included before main uses it");
    expect(count(settings, "    omniMtxSettingsRow(p);") == 1
           && settings.find("    omniMtxSettingsRow(p);") > settings.find("    omniCcsSettingsRow(p);"), "tree: row after Captions");
    const size_t disp = settings.find("if (r.id == OMTX::kRowId) return omniMtxSettingsInput(b);");
    expect(disp != std::string::npos && disp < settings.find("if (r.id >= 300) return omniF3SettingsInput"), "tree: dispatch before the >= 300 rows");
    expect(disp < settings.find("if (r.id >= 900) return omniF2SettingsInput"), "tree: dispatch before the >= 900 rows");
    expect(count(f3, "#include \"OmniMinTextShell.h\"") == 1
           && f3.find("#include \"OmniMinTextShell.h\"") > f3.find("#include \"OmniCaptionStyleShell.h\""), "tree: shell include");
    expect(count(search, "{ \"readable\", { \"minimum text size\"") == 1, "tree: settings-search synonyms");
    expect(count(browser + settings + f3 + shell, "WKPreferencesSetMinimumFontSize(") == 1, "tree: one WebKit call site");
}

static void testWebKit(const std::string& src)
{
    const std::string ref = slurp(src + "/WebKit/UIProcess/API/C/WKPreferencesRef.h"),
        cpp = slurp(src + "/WebKit/UIProcess/API/C/WKPreferences.cpp"),
        yaml = slurp(src + "/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml"),
        style = slurp(src + "/WebCore/style/StyleFontSizeFunctions.cpp"),
        prefs = slurp(src + "/WebKit/UIProcess/WebPreferences.cpp");
    expect(count(ref, "WK_EXPORT void WKPreferencesSetMinimumFontSize(WKPreferencesRef preferencesRef, uint32_t);") == 1, "webkit: C API declared");
    expect(count(cpp, "void WKPreferencesSetMinimumFontSize(WKPreferencesRef preferencesRef, uint32_t size)") == 1
           && count(cpp, "void WKPreferencesSetFullScreenEnabled(") == 1, "webkit: defined next to a function Omni links");
    const size_t y = yaml.find("\nMinimumFontSize:\n");
    expect(y != std::string::npos, "webkit: MinimumFontSize preference");
    if (y != std::string::npos) {
        const std::string e = yaml.substr(y, yaml.find("\n\n", y + 1) - y);
        expect(count(e, "webcoreOnChange: setNeedsRecalcStyleInAllFrames") == 1, "webkit: open pages restyle on change");
        expect(count(e, "defaultValue: 0") == 1, "webkit: default 0 (= Off)");
    }
    expect(count(style, "if (std::abs(computedSize) < std::numeric_limits<float>::epsilon())") == 1
           && count(style, "float zoomedSize = computedSize * zoomFactor;") == 1
           && count(style, "zoomedSize = std::max(zoomedSize, static_cast<float>(minSize));") == 1, "webkit: hard-minimum rule as copied");
    const size_t u = prefs.find("void WebPreferences::updateDoubleValueForKey(");
    expect(u != std::string::npos && prefs.find("update();", u) < prefs.find("\n}", u), "webkit: a double key change updates every page");
}

int main(int argc, char** argv)
{
    testFile();
    testRow();
    testRule();
    if (argc > 1) testTree(argv[1]);
    if (argc > 2) testWebKit(argv[2]);
    std::printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
