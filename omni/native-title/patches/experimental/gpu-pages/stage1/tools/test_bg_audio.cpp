// OMNI_BG_AUDIO_V1: host tests of OmniBgAudio.h ("Background audio" setting) and of the tab media release gate
// (../media/OmniTabMediaRelease.h, Gate::decide) as patched by apply_bg_audio.py.
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry -I<tree>/engine/media test_bg_audio.cpp -o t && ./t <tree>
// With <tree> it also checks that the media header reads the very flag the shell writes.
#include "OmniBgAudio.h"
#include "OmniTabMediaRelease.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

namespace B = OmniBgAudio;
using Gate = OmniMedia::TabMedia::Gate;
using Act = Gate::Act;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

struct Switches {
    bool on = true, keep = false;
    int onAsked = 0, keepAsked = 0;
};
static Act step(Gate& g, Switches& s, double now, bool visible, bool hwVideo, bool paused, bool audible)
{
    return g.decide(now, visible, hwVideo, paused, audible, [&] { ++s.onAsked; return s.on; }, [&] { ++s.keepAsked; return s.keep; });
}

int main(int argc, char** argv)
{
    // --- texts / ids
    {
        CHECK(std::strcmp(B::settingLabel(), "Background audio") == 0);
        CHECK(std::strcmp(B::settingValue(false), "Off") == 0);
        CHECK(std::strcmp(B::settingValue(true), "Keep playing audio") == 0);
        CHECK(std::strstr(B::settingDetail(true), "uses more memory"));
        CHECK(std::strstr(B::settingDetail(false), "uses more memory"));
        CHECK(std::strstr(B::toggledNotice(true), "on"));
        CHECK(std::strstr(B::toggledNotice(false), "off"));
        CHECK(std::string(B::kFlagPath) == std::string("/data/omni/") + B::kFlagName);   // OMNI_DATA_DIR + name in the shell
        CHECK(B::kRowId == 835);
        CHECK(B::kApplyMs == 2000);
    }
    // --- Off (flag absent): exactly the old gate: hidden playing audible video released after the grace
    {
        Gate g; Switches s;
        CHECK(step(g, s, 0, false, true, false, true) == Act::None);       // hidden: grace starts
        CHECK(step(g, s, 1000, false, true, false, true) == Act::None);
        CHECK(s.onAsked == 0 && s.keepAsked == 0);                         // nothing asked inside the grace
        CHECK(step(g, s, 1600, false, true, false, true) == Act::Release);
        CHECK(s.onAsked == 1 && s.keepAsked == 1);
        g.released(true);
        CHECK(step(g, s, 1700, false, false, true, true) == Act::None);    // paused, released: stays
        CHECK(step(g, s, 1800, false, false, false, true) == Act::Repause);   // the page played it: paused again
        g.repaused();
        CHECK(step(g, s, 1900, true, false, true, true) == Act::Reacquire);   // shown: open again
        CHECK(g.reacquired());                                             // we paused it: plays on
    }
    // --- On: a playing audible video keeps playing hidden (decoder kept)
    {
        Gate g; Switches s; s.keep = true;
        CHECK(step(g, s, 0, false, true, false, true) == Act::None);
        CHECK(step(g, s, 5000, false, true, false, true) == Act::None);
        CHECK(step(g, s, 60000, false, true, false, true) == Act::None);
        CHECK(!g.isReleased);
        // paused there (Now playing, sleep timer): released, memory back
        CHECK(step(g, s, 61000, false, true, true, true) == Act::Release);
        g.released(false);
        CHECK(!g.pausedByUs);
        // played again while hidden: the stream opens again (was: Repause)
        CHECK(step(g, s, 62000, false, false, false, true) == Act::Reacquire);
        CHECK(!g.reacquired());                                            // not paused by us: no extra play()
        CHECK(step(g, s, 62100, false, true, false, true) == Act::None);  // plays on hidden
        // ended (paused) and shown: plain visible path
        CHECK(step(g, s, 63000, true, true, true, true) == Act::None);
    }
    // --- On, but muted / silent / volume 0: released as before
    {
        Gate g; Switches s; s.keep = true;
        CHECK(step(g, s, 0, false, true, false, false) == Act::None);
        CHECK(step(g, s, 1600, false, true, false, false) == Act::Release);
        CHECK(s.keepAsked == 0);                                           // keep asked only for audible playing media
        g.released(true);
        CHECK(step(g, s, 1700, false, false, false, false) == Act::Repause);   // inaudible play while released: paused
    }
    // --- On: hidden reacquire fails (no free decode channel): paused again, next play retries after a second
    {
        Gate g; Switches s; s.keep = true;
        CHECK(step(g, s, 0, false, true, true, true) == Act::None);
        CHECK(step(g, s, 1600, false, true, true, true) == Act::Release); // paused hidden video: released
        g.released(false);
        CHECK(step(g, s, 2000, false, false, false, true) == Act::Reacquire);
        g.retryLater(2000);                                                // player: no channel
        CHECK(!g.giveUp(2000));                                            // hidden: never gives up to software
        CHECK(step(g, s, 2100, false, false, false, true) == Act::Repause);
        g.repaused();
        CHECK(step(g, s, 2500, false, false, true, true) == Act::None);   // paused: stays
        CHECK(step(g, s, 3100, false, false, false, true) == Act::Reacquire);   // played again after 1 s: retry
        CHECK(g.reacquired());                                             // we had paused it (repause): plays on
    }
    // --- the setting switched off while a video plays hidden: released at the next decision
    {
        Gate g; Switches s; s.keep = true;
        CHECK(step(g, s, 0, false, true, false, true) == Act::None);
        CHECK(step(g, s, 1600, false, true, false, true) == Act::None);
        s.keep = false;
        CHECK(step(g, s, 3600, false, true, false, true) == Act::Release);
    }
    // --- release disabled (kill switch): never released, keep not asked
    {
        Gate g; Switches s; s.on = false; s.keep = true;
        CHECK(step(g, s, 0, false, true, false, true) == Act::None);
        CHECK(step(g, s, 5000, false, true, false, true) == Act::None);
        CHECK(s.keepAsked == 0);
    }
    // --- exempt (local pages) and software video: untouched in both modes
    {
        Gate g; Switches s; g.exempt = true;
        CHECK(step(g, s, 0, false, true, false, true) == Act::None);
        CHECK(step(g, s, 5000, false, true, false, true) == Act::None);
        Gate h; Switches t;
        CHECK(step(h, t, 0, false, false, false, true) == Act::None);
        CHECK(step(h, t, 5000, false, false, false, true) == Act::None);
    }
    // --- tick() is decide() with the real switches (host: release on unless OMNI_TAB_MEDIA_RELEASE=0, no flag file)
    {
        Gate g, h; Switches s; s.on = OmniMedia::TabMedia::enabled(); s.keep = false;
        const double t0 = OmniMedia::TabMedia::nowMs();
        const double at[] = { t0, t0 + 1000, t0 + 1600, t0 + 1700 };
        for (double now : at) CHECK(g.tick(now, false, true, false, true) == step(h, s, now, false, true, false, true));
    }
    // --- the media header reads the flag the shell writes
    if (argc > 1) {
        const std::string path = std::string(argv[1]) + "/engine/media/OmniTabMediaRelease.h";
        std::ifstream in(path, std::ios::binary);
        std::stringstream ss; ss << in.rdbuf();
        const std::string text = ss.str();
        CHECK(!text.empty());
        CHECK(text.find(std::string("flagFile(\"") + B::kFlagPath + "\")") != std::string::npos);
        CHECK(text.find("OMNI_BG_AUDIO_V1") != std::string::npos);
    }
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
