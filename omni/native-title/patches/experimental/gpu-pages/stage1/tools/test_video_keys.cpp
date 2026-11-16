// OMNI_VIDEO_KEYS_V1: host tests of the pure full-screen video keys (OmniVideoKeys.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_video_keys.cpp -o t && ./t      (run in tools/, or -I<tree>/engine/entry)
//   ./t --emit <dir>   also writes the page scripts node test_video_keys.cjs runs (and node --check reads).
#include "OmniVideoKeys.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>

namespace V = OmniVideoKeys;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static std::string answer(const char* out, const char* state, const char* pos, const char* dur, const char* rate = "1.00",
    const char* muted = "0", const char* cap = "", const char* aud = "", const char* resume = "", const char* note = "", const char* yt = "0")
{
    return std::string("omni-vk1\n") + out + "\n" + state + "\n" + pos + "\n" + dur + "\n" + rate + "\n" + muted + "\n" + cap + "\n"
        + aud + "\n" + resume + "\n" + note + "\n" + yt;
}
static bool sameKey(const V::Key& a, const V::Key& b)
{
    auto eq = [](const char* x, const char* y) { return (!x && !y) || (x && y && std::strcmp(x, y) == 0); };
    return eq(a.text, b.text) && eq(a.identifier, b.identifier) && a.keysym == b.keysym;
}

int main(int argc, char** argv)
{
    // --- plan: the old keys stay the fallbacks; R2 chords; untouched buttons ---
    {
        V::Press p = V::plan(V::pSquare, false);
        CHECK(p.act == V::kToggle && p.fallback == V::fbKey && sameKey(p.key, V::keyK()) && (p.flags & V::fYtKey));
        p = V::plan(V::pL1, false);
        CHECK(p.act == V::kSeek && p.amount == -10 && sameKey(p.key, V::keyJ()) && (p.flags & V::fYtKey));
        p = V::plan(V::pR1, false);
        CHECK(p.act == V::kSeek && p.amount == 10 && sameKey(p.key, V::keyL()));
        p = V::plan(V::pLeft, false);
        CHECK(p.act == V::kSeek && p.amount == -5 && sameKey(p.key, V::keyLeft()) && (p.flags & V::fBoxKey) && (p.flags & V::fYtKey));
        p = V::plan(V::pRight, false);
        CHECK(p.act == V::kSeek && p.amount == 5 && p.key.keysym == 0xff53 && p.key.text == nullptr);
        p = V::plan(V::pTriangle, false);
        CHECK(p.act == V::kCaptions && sameKey(p.key, V::keyC()));
        p = V::plan(V::pL3, false);
        CHECK(p.act == V::kMute && sameKey(p.key, V::keyM()));
        p = V::plan(V::pCross, false);
        CHECK(p.act == V::kConfirm && p.fallback == V::fbClick && p.flags == 0);
        p = V::plan(V::pR3, false);
        CHECK(p.act == V::kInfo && p.fallback == V::fbNone);
        p = V::plan(V::pTouchpad, false);
        CHECK(p.act == V::kInfo && p.speedFirst && p.fallback == V::fbNone);
        CHECK(V::plan(V::pOther, false).act == V::kNone);
        CHECK(V::plan(V::pOther, true).act == V::kNone);

        p = V::plan(V::pL1, true);
        CHECK(p.act == V::kSeek && p.amount == -60 && p.fallback == V::fbNone && p.flags == 0);
        p = V::plan(V::pR1, true);
        CHECK(p.act == V::kSeek && p.amount == 60 && p.fallback == V::fbNone);
        p = V::plan(V::pLeft, true);
        CHECK(p.act == V::kFrame && p.amount == -1 && sameKey(p.key, V::keyComma()) && p.flags == V::fYtKey);
        p = V::plan(V::pRight, true);
        CHECK(p.act == V::kFrame && p.amount == 1 && sameKey(p.key, V::keyPeriod()));
        p = V::plan(V::pTriangle, true);
        CHECK(p.act == V::kCapTrack && p.flags == 0 && sameKey(p.key, V::keyC()));
        p = V::plan(V::pSquare, true);
        CHECK(p.act == V::kAudio && p.fallback == V::fbNone);
        // R2 + a button without a chord: as without R2
        CHECK(V::plan(V::pCross, true).act == V::kConfirm);
        CHECK(V::plan(V::pL3, true).act == V::kMute);
        CHECK(V::plan(V::pR3, true).act == V::kInfo);
    }

    // --- script text ---
    {
        const std::string s = V::script(V::plan(V::pL1, true));
        CHECK(s.size() > 1000);
        CHECK(s.compare(0, 12, "(function(A,") == 0);
        CHECK(s.size() >= 10 && s.substr(s.size() - 10) == ")(2,-60,0)");
        CHECK(V::script(V::plan(V::pLeft, false)).find(")(2,-5,3)") != std::string::npos);
        CHECK(V::script(V::plan(V::pCross, false)).find(")(8,0,0)") != std::string::npos);
        CHECK(s.find("setInterval") == std::string::npos && s.find("setTimeout") == std::string::npos);   // no polling
        CHECK(s.find("</") == std::string::npos);
    }

    // --- parse ---
    {
        V::Info i = V::parse(answer("acted", "playing", "65.25", "240.00", "1.25", "0", "English", "", "", "", "0"));
        CHECK(i.ok && i.outcome == V::oActed && i.state == V::sPlaying && i.position == 65.25 && i.duration == 240 && i.rate == 1.25);
        CHECK(i.muted == 0 && i.captions == "English" && i.audio.empty() && i.resumeAt.empty() && !i.youtube);
        i = V::parse(answer("key", "paused", "10.00", "live", "1.00", "1", "on", "", "12:05\tno", "", "1"));
        CHECK(i.ok && i.outcome == V::oKey && i.duration == V::kLive && i.muted == 1 && i.youtube);
        CHECK(i.resumeAt == "12:05" && i.resumeFocused && i.resumeNo);
        i = V::parse(answer("acted", "paused", "1.00", "2.00", "1.00", "0", "", "", "1:02:03\t-"));
        CHECK(i.resumeAt == "1:02:03" && !i.resumeFocused && !i.resumeNo);
        i = V::parse(answer("none", "none", "", "", "", "", "", "", "", "noaudio"));
        CHECK(i.ok && i.outcome == V::oNone && i.state == V::sNone && i.position < 0 && i.muted == -1 && i.note == "noaudio");
        CHECK(!V::parse("").ok);
        CHECK(!V::parse("omni-np1\n...").ok);
        CHECK(!V::parse(answer("weird", "playing", "1", "2")).ok);
        CHECK(!V::parse(answer("acted", "playing", "1", "2") + "\nextra").ok);
        i = V::parse(answer("acted", "playing", "-3", "nan", "abc"));
        CHECK(i.ok && i.position == -1 && i.duration == -1 && i.rate == -1);
        // labels: control characters, length cut at a UTF-8 boundary
        std::string longLabel(58, 'a');
        longLabel += "\xC3\xA9\xC3\xA9";   // 62 bytes, the cut falls inside the second é
        i = V::parse(answer("acted", "playing", "1", "2", "1", "0", longLabel.c_str(), "Esp\x01" "a\xC3\xB1ol"));
        CHECK(i.captions.size() == 60 && i.captions.substr(58) == "\xC3\xA9");
        CHECK(i.audio == "Esp a\xC3\xB1ol");
    }

    // --- fallbacks: the old action when the page did not answer or said "key" ---
    {
        const V::Press sq = V::plan(V::pSquare, false), cross = V::plan(V::pCross, false), big = V::plan(V::pR1, true);
        CHECK(V::fallbackFor(sq, V::Info()) == V::fbKey);
        CHECK(V::fallbackFor(sq, V::parse(answer("key", "playing", "1", "2"))) == V::fbKey);
        CHECK(V::fallbackFor(sq, V::parse(answer("acted", "playing", "1", "2"))) == V::fbNone);
        CHECK(V::fallbackFor(cross, V::Info()) == V::fbClick);
        CHECK(V::fallbackFor(cross, V::parse(answer("key", "playing", "1", "2"))) == V::fbClick);
        CHECK(V::fallbackFor(cross, V::parse(answer("acted", "playing", "1", "2", "1", "0", "", "", "", "resume"))) == V::fbNone);
        CHECK(V::fallbackFor(big, V::Info()) == V::fbNone);
        CHECK(V::fallbackFor(big, V::parse(answer("key", "none", "", ""))) == V::fbNone);
    }

    // --- texts ---
    {
        CHECK(V::clock(65) == "1:05" && V::clock(3723) == "1:02:03" && V::clock(-1).empty() && V::clock(0) == "0:00");
        CHECK(V::rateLabel(1) == "1\xC3\x97" && V::rateLabel(1.25) == "1.25\xC3\x97" && V::rateLabel(0.5) == "0.5\xC3\x97" && V::rateLabel(-1).empty());
        CHECK(V::seekLabel(-10) == "-10 s" && V::seekLabel(60) == "+1 min" && V::seekLabel(-60) == "-1 min" && V::seekLabel(5) == "+5 s");
    }

    // --- OSD ---
    {
        // acted seek on a plain page: answer after the seek
        V::Press p = V::plan(V::pR1, true);
        V::Info i = V::parse(answer("acted", "playing", "120.00", "600.00", "1.25", "0", "off"));
        V::Osd o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "+1 min" && o.clock == "2:00 / 10:00" && o.fraction == 0.2 && o.right == "1.25\xC3\x97   CC off" && o.resume.empty());
        CHECK(V::shown(o));
        // YouTube j: predicted from the answer before the key
        p = V::plan(V::pL1, false);
        i = V::parse(answer("key", "playing", "5.00", "600.00", "1.00", "0", "on", "", "", "", "1"));
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "-10 s" && o.clock == "0:00 / 10:00" && o.fraction == 0 && o.right == "1\xC3\x97   CC on");
        // YouTube k: flips
        p = V::plan(V::pSquare, false);
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "Paused");
        // YouTube c: flips the known state; Triangle shows it in the title, not on the right
        p = V::plan(V::pTriangle, false);
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "Captions off" && o.right == "1\xC3\x97");
        // YouTube m
        p = V::plan(V::pL3, false);
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "Muted");
        // frame step: paused, 1/30 s
        p = V::plan(V::pRight, true);
        i = V::parse(answer("acted", "paused", "30.03", "60.00"));
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "Frame +1" && o.clock == "0:30 / 1:00");
        i = V::parse(answer("key", "playing", "30.00", "60.00", "1.00", "0", "", "", "", "", "1"));
        CHECK(V::predicted(p, i, V::fbKey).state == V::sPaused);
        CHECK(std::fabs(V::predicted(p, i, V::fbKey).position - (30.0 + 1.0 / 30)) < 1e-9);
        // captions on a plain page: the label
        p = V::plan(V::pTriangle, true);
        i = V::parse(answer("acted", "playing", "1", "100", "1", "0", "Deutsch"));
        CHECK(V::osd(p, i, V::fbNone).title == "Captions: Deutsch");
        // no captions on a plain page: the key was sent, the OSD stays neutral
        i = V::parse(answer("key", "playing", "1", "100"));
        CHECK(V::osd(p, i, V::fallbackFor(p, i)).title == "Captions");
        // audio
        p = V::plan(V::pSquare, true);
        CHECK(V::osd(p, V::parse(answer("acted", "playing", "1", "100", "1", "0", "", "Espa\xC3\xB1ol")), V::fbNone).title == "Audio: Espa\xC3\xB1ol");
        CHECK(V::osd(p, V::parse(answer("none", "playing", "1", "100", "1", "0", "", "", "", "noaudio")), V::fbNone).title == "No other audio tracks");
        CHECK(V::osd(p, V::parse(answer("none", "none", "", "", "", "", "", "", "", "")), V::fbNone).title == "No video found on this page");
        // a cross-origin player: no video in reach, its key was sent: nothing claimed
        p = V::plan(V::pR1, false);
        i = V::parse(answer("key", "none", "", ""));
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(!V::shown(o));
        // R2 + R1 there: said so
        p = V::plan(V::pR1, true);
        CHECK(V::osd(p, i, V::fallbackFor(p, i)).title == "No video found on this page");
        // the page did not answer
        CHECK(V::osd(p, V::Info(), V::fbNone).title == "The page didn't answer");
        CHECK(!V::shown(V::osd(V::plan(V::pSquare, false), V::Info(), V::fbKey)));
        // live stream
        p = V::plan(V::pR3, false);
        o = V::osd(p, V::parse(answer("acted", "playing", "75", "live")), V::fbNone);
        CHECK(o.title == "Playing" && o.clock == "1:15 (live)" && o.fraction < 0);
        // Cross on a page without the prompt: no OSD (the click is the page's)
        p = V::plan(V::pCross, false);
        i = V::parse(answer("key", "playing", "5", "100"));
        CHECK(!V::shown(V::osd(p, i, V::fallbackFor(p, i))));
        // Cross on the prompt
        i = V::parse(answer("acted", "playing", "725", "3000", "1", "0", "", "", "", "resume"));
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "Resumed" && o.clock == "12:05 / 50:00" && o.resume.empty());
        i = V::parse(answer("acted", "playing", "0", "3000", "1", "0", "", "", "", "over"));
        CHECK(V::osd(p, i, V::fbNone).title == "Starting over");
        // the prompt up (focused): D-pad is its arrow, the OSD says where the focus went
        p = V::plan(V::pRight, false);
        i = V::parse(answer("key", "paused", "0", "3000", "1", "0", "", "", "12:05\tyes"));
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "Resume from 12:05?" && o.resume == "Cross: Start over   D-pad left / right: choose" && o.clock == "0:00 / 50:00");
        CHECK(V::predicted(p, i, V::fbKey).position == 0);   // the arrow went to the prompt, not the video
        // the prompt up but not focused (YouTube): the arrow seeks there
        i = V::parse(answer("key", "playing", "10", "3000", "1", "0", "", "", "12:05\t-", "", "1"));
        o = V::osd(p, i, V::fallbackFor(p, i));
        CHECK(o.title == "+5 s" && o.clock == "0:15 / 50:00" && o.resume == "Cross: Resume   D-pad left / right: choose");
        // R3 with the prompt up: it leads
        o = V::osd(V::plan(V::pR3, false), V::parse(answer("acted", "paused", "0", "3000", "1", "0", "", "", "12:05\tno")), V::fbNone);
        CHECK(o.title == "Paused" && o.resume == "Cross: Start over   D-pad left / right: choose");
        // touchpad: the speed read after the speed was set
        p = V::plan(V::pTouchpad, false);
        CHECK(V::osd(p, V::parse(answer("acted", "playing", "1", "100", "1.50")), V::fbNone).title == "Speed: 1.5\xC3\x97");
        CHECK(V::osd(p, V::parse(answer("none", "none", "", "")), V::fbNone).title.empty());
        // equality (the shell redraws only on change)
        CHECK(V::osd(p, V::parse(answer("acted", "playing", "1", "100", "1.50")), V::fbNone)
            == V::osd(p, V::parse(answer("acted", "playing", "1", "100", "1.50")), V::fbNone));
    }

    if (argc == 3 && std::strcmp(argv[1], "--emit") == 0) {
        struct { const char* name; V::Pad pad; bool r2; } list[] = {
            { "info", V::pR3, false }, { "toggle", V::pSquare, false }, { "back10", V::pL1, false }, { "fwd10", V::pR1, false },
            { "left", V::pLeft, false }, { "right", V::pRight, false }, { "captions", V::pTriangle, false }, { "mute", V::pL3, false },
            { "confirm", V::pCross, false }, { "speed", V::pTouchpad, false }, { "back60", V::pL1, true }, { "fwd60", V::pR1, true },
            { "frameback", V::pLeft, true }, { "framefwd", V::pRight, true }, { "captrack", V::pTriangle, true }, { "audio", V::pSquare, true },
        };
        for (auto& e : list) std::ofstream(std::string(argv[2]) + "/vk-" + e.name + ".js", std::ios::binary) << V::script(V::plan(e.pad, e.r2));
    }
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
