// OMNI_AUDIO_BAR_V1: host tests of OmniAudioBar.h (the mini audio bar's pure part) as written by apply_audio_bar.py.
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_audio_bar.cpp -o t && ./t [<tree>]
// With <tree> it also checks the patched shell files: every hook is there once, in the right place and order.
#include "OmniAudioBar.h"
#include "OmniUiScale.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace AB = OmniAudioBar;
namespace MC = OmniMediaControls;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static AB::Candidate tab(uintptr_t key, bool active, bool audible, bool muted = false, bool usable = true)
{
    AB::Candidate c; c.key = key; c.active = active; c.audible = audible; c.muted = muted; c.usable = usable; return c;
}
static std::string readFile(const std::string& p)
{
    std::ifstream f(p, std::ios::binary);
    std::stringstream s; s << f.rdbuf();
    return s.str();
}
static size_t count(const std::string& s, const std::string& what)
{
    size_t n = 0;
    for (size_t at = s.find(what); at != std::string::npos; at = s.find(what, at + 1)) ++n;
    return n;
}

int main(int argc, char** argv)
{
    // --- which tab --------------------------------------------------------------------------------------------------
    {
        CHECK(!AB::enabled(false, false) && !AB::enabled(false, true) && !AB::enabled(true, true) && AB::enabled(true, false));
        std::vector<AB::Candidate> t = { tab(1, true, true), tab(2, false, false), tab(3, false, true), tab(4, false, true) };
        CHECK(AB::pick(t, 0, 0, false) == 3);            // the shown tab playing never counts; first playing behind
        CHECK(AB::pick(t, 4, 0, false) == 4);            // the one already shown stays (no flapping)
        CHECK(AB::pick(t, 2, 0, false) == 3);            // the shown one went quiet: the next playing tab
        t[2].muted = true;
        CHECK(AB::pick(t, 3, 0, false) == 4);            // tab mute: not "playing"
        t[3].usable = false;
        CHECK(AB::pick(t, 0, 0, false) == 0);            // crashed / lazy / no page
        std::vector<AB::Candidate> only = { tab(1, true, true) };
        CHECK(AB::pick(only, 1, 0, false) == 0);         // only the shown tab plays: no bar
        std::vector<AB::Candidate> p = { tab(1, true, false), tab(2, false, false) };
        CHECK(AB::pick(p, 2, 2, true) == 2);             // chord-paused: stays to be resumed
        CHECK(AB::pick(p, 2, 2, false) == 0);            // ... not after kPausedKeepMs
        p[1].active = true; p[0].active = false;
        CHECK(AB::pick(p, 2, 2, true) == 0);             // brought to the front: no bar
        std::vector<AB::Candidate> q = { tab(1, true, false), tab(2, false, false), tab(3, false, true) };
        CHECK(AB::pick(q, 2, 2, true) == 3);             // another tab playing wins over the paused one
        CHECK(AB::pick({}, 5, 5, true) == 0);            // closed
    }
    {
        CHECK(!AB::keepPaused(0, 0, 0, false));
        CHECK(AB::keepPaused(7, 100, 7, true));          // WebKit still says playing just after the pause
        CHECK(AB::keepPaused(7, 100, 7, false));
        CHECK(!AB::keepPaused(7, AB::kSettleMs, 7, true));   // really playing again
        CHECK(AB::keepPaused(7, AB::kPausedKeepMs - 1, 7, false));
        CHECK(!AB::keepPaused(7, AB::kPausedKeepMs, 7, false));
        CHECK(!AB::keepPaused(7, 100, 8, false));        // another tab shown
    }
    // --- script schedule: one per tab change, then every 5 s at most, one at a time --------------------------------
    {
        CHECK(!AB::fetchDue(0, 0, 0, false, 0, 100000));
        CHECK(AB::fetchDue(5, 0, 0, false, 0, 10));                       // first time
        CHECK(AB::fetchDue(5, 4, 99000, true, 99000, 99001));             // tab change: at once, even with one out
        CHECK(!AB::fetchDue(5, 5, 10000, false, 9000, 10000 + AB::kRefreshMs - 1));
        CHECK(AB::fetchDue(5, 5, 10000, false, 9000, 10000 + AB::kRefreshMs));
        CHECK(!AB::fetchDue(5, 5, 0, true, 20000, 20000 + AB::kAbandonMs - 1));   // one out
        CHECK(AB::fetchDue(5, 5, 0, true, 20000, 20000 + AB::kAbandonMs));       // given up
        CHECK(AB::fetchDue(5, 5, 4294967000u, false, 4294967000u, 4294967000u + AB::kRefreshMs));   // tick wrap
        // a 60 s listen with the bar up: 1 script at the change + 1 per 5 s = 13 at most
        int sent = 0; uint32_t last = 0, sentAt = 0; uintptr_t fetched = 0; bool out = false;
        for (uint32_t now = 1000; now <= 61000; now += AB::kCheckMs) {
            if (out && now - sentAt >= 200) { out = false; last = now; }   // answers in 200 ms
            if (AB::fetchDue(9, fetched, last, out, sentAt, now)) { ++sent; fetched = 9; sentAt = now; out = true; }
        }
        CHECK(sent >= 11 && sent <= 13);
    }
    // --- texts ---------------------------------------------------------------------------------------------------
    {
        const MC::Info music = MC::parse("omni-np1\nplaying\n65.0\n240.0\n0\n1\n0\nblob:x\nSong\nBand\nSong - Band | Site");
        CHECK(music.ok);
        CHECK(AB::title(music, true, "Tab title", false) == "Song - Band");
        CHECK(AB::title(music, true, "Tab title", true) == "Private tab");      // private: never the title
        CHECK(AB::title(music, false, "Tab title", true) == "Private tab");
        const MC::Info page = MC::parse("omni-np1\nplaying\n5.0\n\n0\n0\n0\nx\n\n\nEpisode 12 - Podcast");
        CHECK(AB::title(page, true, "Tab", false) == "Episode 12 - Podcast");  // no metadata: the page title
        CHECK(AB::title(MC::Info(), false, "  Tab title ", false) == "Tab title");   // before an answer: the tab's
        CHECK(AB::title(MC::Info(), false, "", false) == "Untitled");
        const std::string longT(400, 'a');
        CHECK(AB::title(MC::Info(), false, longT, false).size() <= AB::kTitleMax);
        CHECK(AB::title(MC::Info(), false, "a\tb", false) == "a b");
        // time: extrapolated while WebKit says playing, clamped to the duration
        CHECK(AB::timeText(music, true, 1000, 1000, true) == "1:05 / 4:00");
        CHECK(AB::timeText(music, true, 1000, 11000, true) == "1:15 / 4:00");
        CHECK(AB::timeText(music, true, 1000, 11000, false) == "1:05 / 4:00");  // paused since: stays
        CHECK(AB::timeText(music, true, 1000, 1000 + 600000, true) == "4:00 / 4:00");
        CHECK(AB::timeText(music, false, 1000, 1000, true).empty());
        const MC::Info live = MC::parse("omni-np1\nplaying\n751.0\nlive\n0\n0\n0\nx\n\n\nRadio");
        CHECK(AB::timeText(live, true, 0, 0, true) == "12:31 (live)");
        const MC::Info liveNoPos = MC::parse("omni-np1\nplaying\n\nlive\n0\n0\n0\nx\n\n\nRadio");
        CHECK(AB::timeText(liveNoPos, true, 0, 0, true) == "Live");
        const MC::Info noDur = MC::parse("omni-np1\npaused\n3725.0\n\n0\n0\n0\nx\n\n\nT");
        CHECK(AB::timeText(noDur, true, 0, 50000, true) == "1:02:05");         // paused answer: not moved
        const MC::Info none = MC::parse("omni-np1\nnone\n\n\n0\n0\n0\n\n\n\nT");
        CHECK(none.ok && AB::timeText(none, true, 0, 0, true).empty());
        CHECK(AB::hint(true, true) == "L2 + Right: Pause");
        CHECK(AB::hint(false, false) == "LT + Right: Play");
        CHECK(std::strcmp(AB::settingLabel(), "Show mini audio bar") == 0);
        CHECK(std::strcmp(AB::settingValue(true), "On") == 0 && std::strcmp(AB::settingValue(false), "Off") == 0);
        CHECK(std::strstr(AB::settingDetail(true, false, true), "Background audio"));
        CHECK(std::strstr(AB::settingDetail(true, true, true), "L2 + Right"));
        CHECK(std::strstr(AB::settingDetail(true, true, false), "LT + Right"));
        CHECK(std::strstr(AB::toggledNotice(true), "on") && std::strstr(AB::toggledNotice(false), "off"));
        CHECK(std::strlen(AB::settingDetail(true, true, true)) <= 90);
        CHECK(AB::kRowId == 894);
    }
    // --- what is shown: a draw only when something visible changes -------------------------------------------------
    {
        AB::Shown a, b;
        CHECK(a == b);
        b.title = "x";                    // hidden: contents do not matter
        CHECK(a == b);
        a.visible = b.visible = true;
        CHECK(a != b);
        a.title = "x"; a.time = "0:01"; b.time = "0:01"; a.hint = b.hint = "h";
        CHECK(a == b);
        b.time = "0:02";
        CHECK(a != b);
        b.time = a.time; b.playing = true;
        CHECK(a != b);
    }
    // --- layout: fits at every interface size, never on the hints bar or its soft edge, text room left --------------
    {
        CHECK(AB::kBarW - AB::kTextX - AB::kPadR - AB::kHintMaxW - AB::kTimeMaxW - 2 * AB::kGap >= 4 * AB::kMinTitleW);
        for (int level = 0; level < OmniUiScale::kLevelCount; ++level)
            for (double ds : { 1.5, 3.0 })                   // 1080p, 4K canvases (1280 x 720 layout)
                for (int hints : { 32, 0 }) {               // hints bar shown / hidden (omniPageBottom)
                    const double z = level == OmniUiScale::Normal ? 1.0 : OmniUiScale::scaleOf(level);
                    const int base = 720 - hints, W = OmniUiScale::zoomedW(z);
                    const AB::Geo g = AB::geometry(W, OmniUiScale::toZoomed(base, z));
                    CHECK(g.x >= AB::kSideMargin && g.x + g.w <= W - AB::kSideMargin && g.w > 0);
                    CHECK(g.y > 0);
                    const int canvasH = int(720 * ds);
                    int r0 = 0, r1 = 0;
                    AB::canvasRows(g, ds * z, canvasH, r0, r1);
                    CHECK(r1 > r0 && r0 >= 0 && r1 <= canvasH);
                    CHECK(r0 <= int(g.y * ds * z) && r1 >= int((g.y + g.h) * ds * z));   // the pill is inside its rows
                    const int fade0 = canvasH - int(hints * ds + 0.5) - int(4 * ds + 0.5);   // omniZones().fadeBot0
                    CHECK(r1 <= fade0);                                                       // above the soft edge
                }
        const AB::Geo narrow = AB::geometry(300, 600);
        CHECK(narrow.w == 300 - 2 * AB::kSideMargin && narrow.x == AB::kSideMargin);
        int r0 = 5, r1 = 5;
        AB::canvasRows(AB::Geo(), 1.5, 0, r0, r1);
        CHECK(r0 == 0 && r1 == 0);
    }
    // --- the patched tree --------------------------------------------------------------------------------------------
    if (argc > 1) {
        const std::string e = std::string(argv[1]) + "/engine/entry/";
        const std::string cpp = readFile(e + "OmniBrowser.cpp"), f3 = readFile(e + "OmniFeatures3.h");
        const std::string st = readFile(e + "OmniBrowserSettings.h"), help = readFile(e + "OmniControlsHelp.h");
        const std::string shell = readFile(e + "OmniAudioBarShell.h");
        CHECK(!cpp.empty() && !f3.empty() && !st.empty() && !help.empty() && !shell.empty());
        CHECK(count(cpp, "#include \"OmniAudioBar.h\"") == 1);
        CHECK(count(cpp, "omniAbrDraw();") == 3);            // declaration, whole draw, regional draw
        CHECK(count(cpp, "omniAbrPlan(R)") == 1 && count(cpp, "close(omniAbrRow0, omniAbrRow1, omniAbrRegional)") == 1);
        const size_t decl = cpp.find("static bool omniAbrPlan("), plan = cpp.find("static int omniPlanDraw(");
        const size_t poPlan = cpp.find("omniPoPlan(R)"), abPlan = cpp.find("omniAbrPlan(R)"), ret2 = cpp.find("if (!changed) return 2;", poPlan);
        CHECK(decl < plan && plan < poPlan && poPlan < abPlan && abPlan < ret2);
        const size_t poClose = cpp.find("close(omniPoRow0"), abClose = cpp.find("close(omniAbrRow0");
        CHECK(poClose < abClose && abClose < cpp.find("if (count >= unsigned(h))", abClose));
        const size_t dr = cpp.find("\nvoid draw()"), hb = cpp.find("if (omniRegion.bottomBar) omniDrawHintBar();", dr);
        const size_t rd = cpp.find("if (omniAbrRegional) omniAbrDraw();", dr), po = cpp.find("if (omniPoRegional) omniPoDraw();", dr);
        CHECK(dr != std::string::npos && hb < rd && rd < cpp.find("omniDrawToast();", rd) && rd < po);
        const size_t bars = cpp.find("    omniDrawBars();", dr), whole = cpp.find("omniAbrDraw(); // OMNI_AUDIO_BAR_V1", dr);
        CHECK(bars < whole && whole < cpp.find("omniDrawToast();", whole) && cpp.find("omniDrawToast();", whole) < cpp.find("if (editing) omniDrawKeyboard();", whole));
        const size_t l2 = cpp.find("static bool omniL2Chord(const SDL_ControllerButtonEvent& event)\n");
        const size_t l2b = cpp.find("static bool omniL2Chord(const SDL_ControllerButtonEvent& event)\r\n");
        const size_t l2at = l2 != std::string::npos ? l2 : l2b;
        const size_t chord = cpp.find("if (omniAbrChord(event.button))", l2at);
        CHECK(l2at != std::string::npos && chord != std::string::npos && chord < cpp.find("const bool omniZoomChord", l2at));
        CHECK(cpp.find("#include \"OmniFeatures3.h\"") < l2at);   // the chord's definition is seen first
        const size_t mcInc = f3.find("#include \"OmniMediaControlsShell.h\""), bgInc = f3.find("#include \"OmniBgAudioShell.h\"");
        const size_t abInc = f3.find("#include \"OmniAudioBarShell.h\"");
        CHECK(mcInc < abInc && bgInc < abInc && abInc != std::string::npos);
        CHECK(count(f3, "omniAbrTick(now);") == 1 && f3.find("omniAbrTick(now);") > f3.find("static void omniF3Tick()"));
        CHECK(count(st, "omniAbrSettingsRow(p);") == 1 && st.find("omniAbrSettingsRow(p);") > st.find("omniBgaSettingsRow(p);"));
        CHECK(count(st, "constexpr int omniAbrRowId = 894;") == 1 && count(st, "return omniAbrSettingsInput(b);") == 1);
        CHECK(count(help, "omniAbrChord (OMNI_AUDIO_BAR_V1)") == 1);
        CHECK(shell.find("kOffFlagName") != std::string::npos && shell.find("OmniUisZoomScope") != std::string::npos);
        // no other settings row uses 894 (the help table / docs may name it)
        CHECK(count(cpp + f3 + st, "894") == 1);
    }
    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
