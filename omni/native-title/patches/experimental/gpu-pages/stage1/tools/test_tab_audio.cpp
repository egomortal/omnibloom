// OMNI_TAB_AUDIO_V1: host tests for engine/entry/OmniTabAudio.h (written by apply_tab_audio.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_audio.cpp -o t && ./t
#include "OmniTabAudio.h"
#include <cstdio>
#include <cstring>

static int fails = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); ++fails; } } while (0)

int main()
{
    namespace TA = OmniTabAudio;
    // badge
    CHECK(TA::badge(false, false) == TA::kNone);
    CHECK(TA::badge(true, false) == TA::kPlaying);
    CHECK(TA::badge(true, true) == TA::kMuted);
    CHECK(TA::badge(false, true) == TA::kMuted);   // muted but silent: still shown, so it can be unmuted

    // change detection: redraw only on a change
    uint8_t stored = 0;
    CHECK(!TA::update(stored, TA::kNone));
    CHECK(TA::update(stored, TA::kPlaying) && stored == TA::kPlaying);
    CHECK(!TA::update(stored, TA::kPlaying));
    CHECK(TA::update(stored, TA::kMuted) && stored == TA::kMuted);
    CHECK(TA::update(stored, TA::kNone) && stored == 0);

    // poll: first call due, then at most every 500 ms; wrap-safe
    TA::Poll p;
    CHECK(p.due(0));
    CHECK(!p.due(1));
    CHECK(!p.due(499));
    CHECK(p.due(500));
    CHECK(!p.due(999));
    CHECK(p.due(1700));   // late tick: next is 2200, not 1500
    CHECK(!p.due(2199));
    CHECK(p.due(2200));
    TA::Poll w;
    CHECK(w.due(0xFFFFFF00u));
    CHECK(!w.due(0xFFFFFFF0u));
    CHECK(!w.due(0x00000000u));   // 256 ms after, across the wrap
    CHECK(w.due(0x000000F4u));    // 0xFFFFFF00 + 500 wraps to 0xF4
    int polls = 0;
    TA::Poll q;
    for (uint32_t t = 0; t < 10000; t += 16) polls += q.due(t);   // a 60 fps tick for 10 s
    CHECK(polls >= 19 && polls <= 20);

    // labels
    CHECK(!std::strcmp(TA::toggleLabel(false), "Mute this tab"));
    CHECK(!std::strcmp(TA::toggleLabel(true), "Unmute this tab"));
    CHECK(!std::strcmp(TA::faceLabel(false), "Mute tab"));
    CHECK(!std::strcmp(TA::faceLabel(true), "Unmute tab"));
    CHECK(!std::strcmp(TA::toggledNotice(true), "Tab muted"));
    CHECK(!std::strcmp(TA::toggledNotice(false), "Tab sound on"));
    CHECK(!std::strcmp(TA::rowValue(TA::kNone), ""));
    CHECK(!std::strcmp(TA::rowValue(TA::kPlaying), "Playing"));
    CHECK(!std::strcmp(TA::rowValue(TA::kMuted), "Muted"));
    CHECK(TA::mutedAfterSleep(true) && !TA::mutedAfterSleep(false));

    // ids do not collide with the other Options tiles
    CHECK(TA::kTile != 420 && TA::kTile != 421 && TA::kTile != 380 && TA::kTile != 381 && TA::kTile < 700 && TA::kTile > 399);

    // <= 4 tabs: no badge keeps the old title edge (byte-for-byte layout); the icon (20 wide) stays clear of
    // the close cross (hit area x+208..232, icon x+211..225) and of the private badge (x+142..202)
    for (int i = 0; i < 4; ++i) {
        const int x = 100 + i * 240;
        CHECK(TA::fixedSlot(x, false, false).titleRight == x + 202);
        CHECK(TA::fixedSlot(x, true, false).titleRight == x + 136);
        const TA::Slot n = TA::fixedSlot(x, false, true), v = TA::fixedSlot(x, true, true);
        CHECK(n.iconX + 10 <= x + 208 && n.iconX - 10 >= n.titleRight);
        CHECK(v.iconX + 10 <= x + 142 && v.iconX - 10 >= v.titleRight);
        CHECK(n.titleRight - (x + 16) >= 140);   // still room for a title
    }
    // compact strip: tabs 112..232 px wide
    for (int w = 112; w <= 232; w += 8) {
        const int x = 130;
        for (int c = 0; c < 2; ++c) {
            const bool closable = c;
            CHECK(TA::compactSlot(x, w, closable, false).titleRight == x + w - (closable ? 30 : 10));
            const TA::Slot s = TA::compactSlot(x, w, closable, true);
            CHECK(s.iconX + 10 <= x + w - (closable ? 24 : 0));   // left of the close cross's hit area / the tab end
            CHECK(s.iconX - 10 >= s.titleRight);
            CHECK(s.titleRight - (x + 32) >= 20);                  // a spinner + some title still fit
        }
    }
    std::printf(fails ? "%d FAILED\n" : "all tab audio tests passed\n", fails);
    return fails != 0;
}
