// OMNI_PAD_FEEDBACK_V1: host tests of OmniPadFeedback.h (pure part of "Controller light & rumble").
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pad_feedback.cpp -o t && ./t
#include "OmniPadFeedback.h"
#include <cstdio>
#include <cstring>

namespace P = OmniPadFeedback;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static P::Context base()
{
    P::Context c;
    c.enabled = true; c.focused = true;
    c.accent = { 112, 228, 209 };
    return c;
}

int main()
{
    // --- colour by context
    {
        P::Context c = base();
        P::Light l = P::choose(c);
        CHECK(l.want == P::Want::Set && P::same(l.colour, c.accent));
        c.grouped = true; c.group = { 234, 67, 53 };
        l = P::choose(c);
        CHECK(l.want == P::Want::Set && P::same(l.colour, P::Rgb { 234, 67, 53 }));
        c.privateTab = true;   // private wins over a group (private tabs can't be grouped anyway)
        CHECK(P::same(P::choose(c).colour, P::kPrivate));
        c.fullscreen = true;   // fullscreen video wins over everything: off
        CHECK(P::same(P::choose(c).colour, P::kOff));
        c.enabled = false;
        CHECK(P::choose(c).want == P::Want::Leave);
        c = base(); c.focused = false;
        CHECK(P::choose(c).want == P::Want::Leave);
        P::Context d;   // default: Off
        CHECK(P::choose(d).want == P::Want::Leave);
    }
    // --- memo: only changes are sent; restore once after driving; never restore what we never set
    {
        P::Memo m;
        P::Light leave {};
        CHECK(P::step(m, leave, 1) == P::Send::Nothing);
        P::Light a { P::Want::Set, { 1, 2, 3 } };
        CHECK(P::step(m, a, 1) == P::Send::Colour);
        CHECK(P::step(m, a, 1) == P::Send::Nothing);
        CHECK(P::step(m, a, 2) == P::Send::Colour);              // a pad came / went: send again
        P::Light b { P::Want::Set, { 1, 2, 4 } };
        CHECK(P::step(m, b, 2) == P::Send::Colour && P::same(m.last, b.colour));
        CHECK(P::step(m, leave, 2) == P::Send::Restore);
        CHECK(P::step(m, leave, 2) == P::Send::Nothing);         // once
        CHECK(P::step(m, b, 2) == P::Send::Colour);              // taken again after focus returns
    }
    // --- pads signature
    {
        uintptr_t none[8] = {}, one[8] = { 0x1000 }, other[8] = { 0, 0x1000 }, two[8] = { 0x1000, 0x2000 };
        const uintptr_t s0 = P::padsSignature(none, 8), s1 = P::padsSignature(one, 8), s2 = P::padsSignature(other, 8), s3 = P::padsSignature(two, 8);
        CHECK(s0 != s1 && s1 != s2 && s1 != s3 && s0 != s3);
        CHECK(P::padsSignature(one, 8) == s1);
    }
    // --- cue table: every cue short, low, never continuous
    {
        int known = 0;
        for (int cue = -2; cue < 10; ++cue) {
            P::CueSpec s;
            if (!P::cueSpec(cue, s)) continue;
            ++known;
            CHECK(s.ms > 0 && s.ms <= P::kCueMaxMs);
            CHECK(s.low <= P::kCueMaxStrength && s.high <= P::kCueMaxStrength);
            CHECK(s.low || s.high);
        }
        CHECK(known == 4);
        P::CueSpec s;
        CHECK(P::cueSpec(P::kLoadError, s) && P::cueSpec(P::kPopupBlocked, s) && P::cueSpec(P::kDownload, s) && P::cueSpec(P::kSleepTimer, s));
        CHECK(!P::cueSpec(0, s) && !P::cueSpec(5, s));
    }
    // --- rate limiter: one per second, wrap-safe
    {
        P::Limiter l;
        CHECK(l.allow(0));
        CHECK(!l.allow(1));
        CHECK(!l.allow(999));
        CHECK(l.allow(1000));
        CHECK(!l.allow(1500));
        CHECK(l.allow(2600));
        P::Limiter w;
        CHECK(w.allow(0xFFFFFF00u));
        CHECK(!w.allow(0x00000100u));     // 512 ms later across the wrap
        CHECK(w.allow(0x00000400u));      // 1280 ms later
        P::Limiter z;   // first ever cue at tick 5 is allowed (no "last = 0" false block)
        CHECK(z.allow(5));
    }
    // --- gate and texts
    {
        CHECK(P::cueAllowed(true, true, false));
        CHECK(!P::cueAllowed(false, true, false));
        CHECK(!P::cueAllowed(true, false, false));
        CHECK(!P::cueAllowed(true, true, true));
        CHECK(!std::strcmp(P::settingValue(false), "Off") && !std::strcmp(P::settingValue(true), "On"));
        CHECK(!std::strcmp(P::settingLabel(), "Controller light & rumble"));
        CHECK(std::strlen(P::settingDetail()) < 120);
        CHECK(std::strcmp(P::toggledNotice(true), P::toggledNotice(false)) != 0);
    }
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
