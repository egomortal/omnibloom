// OMNI_ONE_SOUND_V1: host tests of OmniOneSound.h ("Play sound from one tab at a time"), as written by apply_one_sound.py.
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_one_sound.cpp -o t && ./t [<tree>]
//   With <tree>: also checks the patched files (the hook is the last call of isPlayingAudioDidChange, the shell comes
//   after the audio bar's, the settings row follows "Show mini audio bar", the input line comes before the >= 300 rows).
// ./t --emit <file>: writes the page script (then: node --check <file>; node test_one_sound.cjs <file>).
#include "OmniOneSound.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

namespace S = OmniOneSound;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static std::string readFile(const std::string& p)
{
    std::ifstream f(p, std::ios::binary);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}
static size_t lineOf(const std::string& s, const std::string& needle)
{
    const size_t at = s.find(needle);
    if (at == std::string::npos) return 0;
    size_t n = 1;
    for (size_t i = 0; i < at; ++i) n += s[i] == '\n';
    return n;
}
static S::TabState tab(uintptr_t key, bool playing, bool muted = false, int vol = 100, bool usable = true)
{
    S::TabState t;
    t.key = key; t.playing = playing; t.muted = muted; t.volumePct = vol; t.usable = usable;
    return t;
}

static void treeChecks(const std::string& tree)
{
    const std::string e = tree + "/engine/entry/";
    const std::string cpp = readFile(e + "OmniBrowser.cpp"), set = readFile(e + "OmniBrowserSettings.h");
    const std::string f3 = readFile(e + "OmniFeatures3.h"), shell = readFile(e + "OmniOneSoundShell.h");
    CHECK(!cpp.empty() && !set.empty() && !f3.empty() && !shell.empty());
    // the callback: ours is the last call, after tab volume's
    const size_t cb = cpp.find("ui.isPlayingAudioDidChange = ");
    CHECK(cb != std::string::npos);
    if (cb != std::string::npos) {
        const std::string line = cpp.substr(cb, cpp.find('\n', cb) - cb);
        const size_t tv = line.find("omniTvMediaChanged(page);"), os = line.find("omniOsnMediaChanged(page);");
        CHECK(tv != std::string::npos && os != std::string::npos && tv < os);
        CHECK(line.find("}; //") > os);   // the lambda closes after our call, the comment stays last
        CHECK(line.find("OMNI_ONE_SOUND_V1") != std::string::npos);
    }
    CHECK(lineOf(cpp, "static void omniOsnMediaChanged(WKPageRef page);") > 0);
    CHECK(lineOf(cpp, "static void omniOsnMediaChanged(WKPageRef page);") < lineOf(cpp, "ui.isPlayingAudioDidChange = "));
    CHECK(lineOf(cpp, "#include \"OmniOneSound.h\"") > lineOf(cpp, "#include \"OmniAudioBar.h\""));
    CHECK(lineOf(cpp, "#include \"OmniOneSound.h\"") < lineOf(cpp, "#include \"OmniFeatures3.h\"") || lineOf(cpp, "#include \"OmniFeatures3.h\"") == 0);
    // the shell after the audio bar's (uses omniAbrKey / omniAbrPausedKey), tab volume's and Now playing's
    const size_t osInc = lineOf(f3, "#include \"OmniOneSoundShell.h\"");
    CHECK(osInc > lineOf(f3, "#include \"OmniAudioBarShell.h\"") && lineOf(f3, "#include \"OmniAudioBarShell.h\"") > 0);
    CHECK(osInc > lineOf(f3, "#include \"OmniTabVolumeShell.h\""));
    CHECK(osInc > lineOf(f3, "#include \"OmniMediaControlsShell.h\""));
    // settings: declarations, the row right after the bar's, the input before the generic rows
    CHECK(lineOf(set, "constexpr int omniOsnRowId = 873;") > 0);
    CHECK(lineOf(set, "omniOsnSettingsRow(p);") == lineOf(set, "omniAbrSettingsRow(p);") + 1);
    CHECK(lineOf(set, "omniAbrSettingsRow(p);") == lineOf(set, "omniBgaSettingsRow(p);") + 1);
    CHECK(lineOf(set, "if (r.id == omniOsnRowId) return omniOsnSettingsInput(b);") + 1 == lineOf(set, "if (r.id == omniAbrRowId) return omniAbrSettingsInput(b);"));
    // the shell reads the flag the pure part names, and never stores private titles
    CHECK(shell.find("omniData(OOSN::kFlagName)") != std::string::npos);
    CHECK(shell.find("omniAbrPausedKey = ask.key") != std::string::npos);
    CHECK(shell.find("kWKMediaAudioMuted") != std::string::npos && shell.find("kWKMediaNoneMuted") == std::string::npos);   // never unmutes
    CHECK(shell.find(".play(") == std::string::npos);   // never resumes
}

int main(int argc, char** argv)
{
    if (argc == 3 && std::strcmp(argv[1], "--emit") == 0) {
        std::ofstream f(argv[2], std::ios::binary);
        f << "var omniOsnResult = " << S::pauseScript() << ";\nif (typeof module !== 'undefined') module.exports = omniOsnResult;\n";
        return f ? 0 : 1;
    }

    // --- texts / ids
    CHECK(S::kRowId == 873);
    CHECK(std::string(S::kFlagName) == "one-sound.flag");
    CHECK(std::string(S::settingLabel()) == "Play sound from one tab at a time");
    CHECK(std::string(S::settingValue(false)) == "Off" && std::string(S::settingValue(true)) == "On");
    CHECK(std::string(S::settingDetail(false)) != S::settingDetail(true));
    CHECK(std::string(S::toggledNotice(true)) != S::toggledNotice(false));
    CHECK(S::pausedNotice("Song - Artist", false) == "Paused Song - Artist");
    CHECK(S::pausedNotice("Secret page", true) == "Paused a private tab");
    CHECK(S::mutedNotice("Radio", false) == "Muted Radio (couldn't pause it)");
    CHECK(S::fightNotice("Ad", false).find("started again by itself") != std::string::npos);
    CHECK(S::keptNotice("Music", false) == "Couldn't pause Music");
    CHECK(S::shortTitle("", false) == "a tab");
    CHECK(S::shortTitle("  \t\n ", false) == "a tab");
    CHECK(S::shortTitle("  a\r\nb  c ", false) == "a b c");
    {
        const std::string longT(100, 'x');
        const std::string s = S::shortTitle(longT, false);
        CHECK(s.size() <= S::kTitleMax && s.size() > 50 && s.substr(s.size() - 3) == "...");
        std::string u;   // 2-byte UTF-8 characters: never cut inside one
        for (int i = 0; i < 50; ++i) u += "\xc3\xa9";
        const std::string su = S::shortTitle(u, false);
        CHECK(su.size() <= S::kTitleMax);
        const std::string body = su.substr(0, su.size() - 3);
        CHECK(body.size() % 2 == 0);
        CHECK(S::shortTitle(std::string(S::kTitleMax, 'y'), false).size() == S::kTitleMax);   // fits: unchanged
    }

    // --- audible
    CHECK(S::audible(tab(1, true)));
    CHECK(!S::audible(tab(1, false)));
    CHECK(!S::audible(tab(1, true, true)));          // muted
    CHECK(!S::audible(tab(1, true, false, 0)));      // per-tab volume 0 %
    CHECK(S::audible(tab(1, true, false, 10)));
    CHECK(!S::audible(tab(1, true, false, 100, false)));   // crashed / no page

    // --- tracker: start edges
    {
        S::Tracker tr;
        CHECK(tr.observe(1, true));      // started
        CHECK(!tr.observe(1, true));     // still playing (another state change, e.g. video): not a start
        CHECK(!tr.observe(1, false));    // stopped
        CHECK(tr.observe(1, true));      // started again
        CHECK(tr.observe(2, true));
        CHECK(tr.playing(1) && tr.playing(2));
        tr.pausedByUs(2, 1000);
        CHECK(tr.fightingBack(2, 1000));
        CHECK(tr.fightingBack(2, 1000 + S::kFightMs - 1));
        CHECK(!tr.fightingBack(2, 1000 + S::kFightMs));
        CHECK(!tr.fightingBack(1, 1000));
        tr.pausedByUs(3, 0xFFFFFF00u);   // SDL_GetTicks wrap
        CHECK(tr.fightingBack(3, 0x00000100u));
        CHECK(!tr.fightingBack(3, 0xFFFFFF00u + S::kFightMs));
        CHECK(tr.tracked() == 4);
        tr.keepOnly({ 2 });
        CHECK(!tr.playing(1) && tr.playing(2) && !tr.fightingBack(3, 0x00000100u) && tr.tracked() == 2);
        tr.keepOnly({});
        CHECK(tr.tracked() == 0);
    }

    // --- plan
    CHECK(S::plan(false, true, tab(1, true), false, false) == S::Plan::kNothing);   // Off
    CHECK(S::plan(true, false, tab(1, true), false, false) == S::Plan::kNothing);   // not a start
    CHECK(S::plan(true, true, tab(1, true, true), false, false) == S::Plan::kNothing);   // muted starter: silent
    CHECK(S::plan(true, true, tab(1, true, false, 0), false, false) == S::Plan::kNothing);   // 0 % starter
    CHECK(S::plan(true, true, tab(1, true), false, false) == S::Plan::kPauseOthers);
    CHECK(S::plan(true, true, tab(1, true), true, false) == S::Plan::kMuteStarter);   // fights back: muted
    CHECK(S::plan(true, true, tab(1, true), true, true) == S::Plan::kPauseOthers);    // the bar's tab: the user's chord

    // --- victims: every other audible tab
    {
        std::vector<S::TabState> all = { tab(1, true), tab(2, true), tab(3, false), tab(4, true, true), tab(5, true, false, 0),
                                         tab(6, true, false, 100, false), tab(7, true, false, 30) };
        const auto v = S::victims(all, 1);
        CHECK(v.size() == 2 && v[0] == 2 && v[1] == 7);
        CHECK(S::victims(all, 99).size() == 3);
        CHECK(S::victims({ tab(1, true) }, 1).empty());
    }

    // --- after the pause answer
    CHECK(S::afterPause(1, true, false) == S::After::kPaused);
    CHECK(S::afterPause(3, true, true) == S::After::kPaused);
    CHECK(S::afterPause(0, true, false) == S::After::kMute);     // nothing pausable (cross-origin player): mute
    CHECK(S::afterPause(-1, true, false) == S::After::kMute);    // no answer
    CHECK(S::afterPause(0, true, true) == S::After::kLeave);     // the bar's tab is never muted
    CHECK(S::afterPause(-1, true, true) == S::After::kLeave);
    CHECK(S::afterPause(0, false, false) == S::After::kNothing); // stopped by itself meanwhile
    CHECK(S::afterPause(0, false, true) == S::After::kNothing);

    // --- answer parsing
    CHECK(S::parsePaused("omni-os1\n0") == 0);
    CHECK(S::parsePaused("omni-os1\n2") == 2);
    CHECK(S::parsePaused("omni-os1\n") == -1);
    CHECK(S::parsePaused("omni-os1\n2x") == -1);
    CHECK(S::parsePaused("omni-np1\n2") == -1);
    CHECK(S::parsePaused("") == -1);
    CHECK(S::parsePaused("omni-os1\n1234567") == -1);
    CHECK(S::parsePaused("omni-os1\n-1") == -1);

    // --- the script: one expression, pauses only (never play / mute / volume writes), its answer header
    {
        const std::string js = S::pauseScript();
        CHECK(js.rfind("(function(){", 0) == 0);
        CHECK(js.size() > 3 && js.substr(js.size() - 4) == "})()");
        CHECK(js.find("'omni-os1\\n'") != std::string::npos);   // the JS escape, not a raw newline
        CHECK(js.find(".pause()") != std::string::npos);
        CHECK(js.find(".play(") == std::string::npos);
        CHECK(js.find(".muted=") == std::string::npos && js.find(".volume=") == std::string::npos);
        CHECK(js.find("k>3") != std::string::npos);   // frame depth cap like Now playing's
    }

    if (argc == 2) treeChecks(argv[1]);
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
