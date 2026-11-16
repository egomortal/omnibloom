// OMNI_PAUSE_INFO_V1: host tests of OmniPauseInfo.h (the pause info strip's pure part).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_pause_info.cpp -o t && ./t
//   ./t --emit <dir>   also writes the page script (pzi.js) for node test_pause_info.cjs <dir> and node --check.
#include "OmniPauseInfo.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>

namespace OPZ = OmniPauseInfo;
namespace VK = OmniVideoKeys;

static int checks = 0, fails = 0;
static void check(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++fails; std::printf("FAIL %s\n", what); }
}
static void eq(const std::string& got, const std::string& want, const char* what)
{
    ++checks;
    if (got != want) { ++fails; std::printf("FAIL %s: got \"%s\", want \"%s\"\n", what, got.c_str(), want.c_str()); }
}

// An answer as the page script writes it.
static std::string answer(const std::string& title, const std::string& state, const std::string& pos, const std::string& dur,
                          const std::string& rate = "1.00", const std::string& resume = "")
{
    return "omni-pzi1\n" + title + "\nomni-vk1\nnone\n" + state + "\n" + pos + "\n" + dur + "\n" + rate + "\n0\n\n\n" + resume + "\n\n0";
}

int main(int argc, char** argv)
{
    // hhmm
    eq(OPZ::hhmm(0), "00:00", "hhmm 0");
    eq(OPZ::hhmm(22 * 60 + 41), "22:41", "hhmm 22:41");
    eq(OPZ::hhmm(1440), "00:00", "hhmm wraps 1440");
    eq(OPZ::hhmm(-1), "23:59", "hhmm wraps -1");
    eq(OPZ::hhmm(1440 * 3 + 65), "01:05", "hhmm wraps days");

    // endsAtMinute
    check(OPZ::endsAtMinute(21 * 60 + 12, 0, 89 * 60 + 5, 1) == 22 * 60 + 41, "ends 21:12:00 + 1:29:05 = 22:41");
    check(OPZ::endsAtMinute(21 * 60 + 12, 40, 89 * 60, 1) == 22 * 60 + 42, "rounds to the nearest minute (22:41:40 -> 22:42)");
    check(OPZ::endsAtMinute(21 * 60 + 12, 20, 89 * 60, 1) == 22 * 60 + 41, "rounds down below 30 s");
    check(OPZ::endsAtMinute(23 * 60 + 50, 0, 30 * 60, 1) == 20, "crosses midnight -> 00:20");
    check(OPZ::endsAtMinute(20 * 60, 0, 60 * 60, 2) == 20 * 60 + 30, "2x: an hour of video ends in 30 min");
    check(OPZ::endsAtMinute(20 * 60, 0, 60 * 60, 0.5) == 22 * 60, "0.5x: two hours");
    check(OPZ::endsAtMinute(20 * 60, 0, 60 * 60, -1) == 21 * 60, "unknown rate: 1x");
    check(OPZ::endsAtMinute(20 * 60, 0, -1, 1) == -1, "unknown remaining");
    check(OPZ::endsAtMinute(20 * 60, 0, 90000, 1) == -1, "more than a day away");
    check(OPZ::endsAtMinute(20 * 60, 0, 0, 1) == 20 * 60, "nothing left: now");

    // fade
    check(OPZ::fadeT(true, 0) == 1.f, "reduce motion: no fade");
    check(OPZ::fadeMs(true) == 0 && OPZ::fadeMs(false) == OPZ::kFadeMs, "fade durations");
    check(OPZ::fadeT(false, 0) == 0.f && OPZ::fadeT(false, OPZ::kFadeMs / 2) == 0.5f && OPZ::fadeT(false, 5000) == 1.f, "fade ramp");

    // minute timer
    check(OPZ::msToNextMinute(0) == 60050 && OPZ::msToNextMinute(59) == 1050 && OPZ::msToNextMinute(75) == 1050, "next minute");

    // parse / shows
    {
        const OPZ::Answer a = OPZ::parse(answer("Big Buck Bunny", "paused", "725.00", "2710.00", "1.50"));
        check(a.ok && a.title == "Big Buck Bunny", "parse ok + title");
        check(a.info.state == VK::sPaused && a.info.position == 725 && a.info.duration == 2710 && a.info.rate == 1.5, "parse info");
        check(OPZ::shows(a), "paused shows");
    }
    check(!OPZ::shows(OPZ::parse(answer("x", "playing", "1.00", "10.00"))), "playing: no strip");
    check(!OPZ::shows(OPZ::parse(answer("x", "none", "", ""))), "no video: no strip");
    check(!OPZ::shows(OPZ::parse(answer("x", "paused", "9.80", "10.00"))), "at the end: no strip");
    check(!OPZ::shows(OPZ::parse(answer("x", "paused", "5.00", "10.00", "1.00", "12:05\tyes"))), "resume prompt up: no strip");
    check(OPZ::shows(OPZ::parse(answer("x", "paused", "5.00", "live"))), "paused live stream shows");
    check(OPZ::shows(OPZ::parse(answer("", "paused", "5.00", ""))), "no duration shows");
    check(!OPZ::parse("omni-pzi1\nonly title").ok, "truncated answer");
    check(!OPZ::parse("omni-vk1\nx\n").ok, "wrong magic");
    check(!OPZ::parse("").ok, "empty answer");
    check(!OPZ::parse("omni-pzi1\nt\nomni-vk1\nnone\npaused").ok, "short vk answer");

    // titles
    eq(OPZ::displayTitle("  Song\tName \n", "Tab"), "Song Name", "meta title cleaned");
    eq(OPZ::displayTitle("", "My tab - YouTube"), "My tab - YouTube", "tab title fallback");
    eq(OPZ::displayTitle(" ", ""), "Paused", "no title");
    {
        std::string longT;
        for (int i = 0; i < 200; ++i) longT += "\xC3\xA9";   // 400 bytes of 2-byte characters
        const std::string c = OPZ::cleanTitle(longT);
        check(c.size() <= OPZ::kTitleMax && c.size() % 2 == 0, "title cut at a UTF-8 boundary");
    }

    // the strip
    {
        const OPZ::Answer a = OPZ::parse(answer("Big Buck Bunny", "paused", "725.00", "2710.00"));
        const VK::Osd o = OPZ::strip(a, "tab", 21 * 60 + 12, 0);
        eq(o.title, "Big Buck Bunny", "strip title");
        eq(o.right, "21:12", "strip clock");
        eq(o.clock, "12:05 / 45:10", "strip position / duration");
        check(o.fraction > 0.267 && o.fraction < 0.268, "strip bar");
        eq(o.resume, "33:05 left   Ends at 21:45", "strip left + ends at");
        check(VK::shown(o), "strip is a shown OSD");
    }
    {
        const OPZ::Answer a = OPZ::parse(answer("", "paused", "0.00", "5345.00"));
        eq(OPZ::strip(a, "Film", 21 * 60 + 12, 0).resume, "1:29:05 left   Ends at 22:41", "the backlog's example");
        eq(OPZ::strip(a, "Film", 21 * 60 + 12, 0).title, "Film", "tab title in the strip");
    }
    {
        const OPZ::Answer a = OPZ::parse(answer("", "paused", "", "600.00"));
        eq(OPZ::strip(a, "", 0, 0).clock, "0:00 / 10:00", "unknown position: 0:00");
        eq(OPZ::strip(a, "", 0, 0).resume, "10:00 left   Ends at 00:10", "unknown position: whole video left");
    }
    {
        const OPZ::Answer a = OPZ::parse(answer("Live", "paused", "65.00", "live"));
        const VK::Osd o = OPZ::strip(a, "", 600, 0);
        eq(o.resume, "Live", "live: no ends at");
        eq(o.clock, "1:05 (live)", "live clock");
        check(o.fraction < 0, "live: no bar");
    }
    {
        const OPZ::Answer a = OPZ::parse(answer("", "paused", "65.00", ""));
        eq(OPZ::strip(a, "", 600, 0).resume, "", "no duration: no second line");
    }
    {
        const OPZ::Answer a = OPZ::parse(answer("", "paused", "0.00", "3600.00", "2.00"));
        eq(OPZ::strip(a, "", 600, 0).resume, "1:00:00 left   Ends at 10:30", "2x: ends sooner, time left in video time");
    }

    // the script
    {
        const std::string s = OPZ::script();
        check(s.rfind("(function(){var r=(function(A,N,F){", 0) == 0, "script head wraps the video keys script");
        check(s.find("})(0,0,0);var t=") != std::string::npos, "video keys' kInfo press (A=0, N=0, F=0)");
        check(s.size() > 7 && s.compare(s.size() - 7, 7, "+r;})()") == 0, "script tail intact");
        check(s.find("omni-pzi1") != std::string::npos, "answer magic in the script");
    }

    if (argc == 3 && std::strcmp(argv[1], "--emit") == 0) {
        std::ofstream(std::string(argv[2]) + "/pzi.js") << OPZ::script();
        std::printf("wrote %s/pzi.js\n", argv[2]);
    }
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
