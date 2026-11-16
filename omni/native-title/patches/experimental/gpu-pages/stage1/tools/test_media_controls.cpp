// OMNI_MEDIA_CONTROLS_V1: host tests for engine/entry/OmniMediaControls.h (written by apply_media_controls.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_media_controls.cpp -o t && ./t
//   ./t --emit <dir>   also writes the scripts for node test_media_controls.cjs <dir>
#include "OmniMediaControls.h"
#include <cstdio>
#include <cstring>
#include <fstream>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniMediaControls;

static Candidate cand(uintptr_t key, bool audio, bool video, bool active, bool usable = true)
{
    Candidate c; c.key = key; c.audio = audio; c.video = video; c.active = active; c.usable = usable; return c;
}

int main(int argc, char** argv)
{
    // --- which tab
    CHECK(pickTarget({}, 0) == 0);
    CHECK(pickTarget({ cand(1, false, false, true), cand(2, false, false, false) }, 0) == 0);
    CHECK(pickTarget({ cand(1, false, false, true), cand(2, true, true, false) }, 0) == 2);       // background tab plays
    CHECK(pickTarget({ cand(1, true, false, false), cand(2, true, false, true) }, 0) == 2);       // active one wins
    CHECK(pickTarget({ cand(1, false, false, true), cand(2, false, false, false) }, 2) == 2);     // paused: last sound tab
    CHECK(pickTarget({ cand(1, false, false, true) }, 7) == 0);                                   // last tab closed
    CHECK(pickTarget({ cand(1, false, false, true), cand(3, true, false, false) }, 1) == 3);     // sound beats last
    CHECK(pickTarget({ cand(1, false, true, false), cand(2, false, false, false) }, 2) == 2);     // last beats muted video
    CHECK(pickTarget({ cand(1, false, true, false), cand(2, false, true, true) }, 0) == 2);       // active video first
    CHECK(pickTarget({ cand(1, false, true, false) }, 0) == 1);
    CHECK(pickTarget({ cand(1, true, false, true, false), cand(2, false, false, false) }, 1) == 0); // crashed / unloaded

    // --- parsing
    Info i = parse("omni-np1\nplaying\n65.0\n240.5\n1\n0\n1\nblob:https://www.youtube.com/abc\nSong\nBand\nSong - YouTube");
    CHECK(i.ok && i.state == kPlaying && i.position == 65.0 && i.duration == 240.5 && i.hasPrev && !i.hasNext);
    CHECK(i.did == kDidElement && i.src == "blob:https://www.youtube.com/abc" && i.title == "Song" && i.artist == "Band");
    CHECK(i.docTitle == "Song - YouTube");
    i = parse("omni-np1\npaused\n12.0\nlive\n0\n0\n0\nhttp://192.0.2.10/live.m3u8\n\n\nRadio");
    CHECK(i.ok && i.state == kPaused && i.duration == kLive && i.position == 12.0 && i.title.empty() && i.docTitle == "Radio");
    i = parse("omni-np1\nnone\n\n\n0\n1\n3\n\n\n\nA page");
    CHECK(i.ok && i.state == kNone && i.position == -1 && i.duration == -1 && i.hasNext && i.did == kDidKey && i.src.empty());
    CHECK(!parse("").ok);
    CHECK(!parse("omni-np2\nplaying\n1\n2\n0\n0\n0\ns\nt\na\nd").ok);
    CHECK(!parse("omni-np1\nplaying\n1\n2\n0\n0\n0\ns\nt\na").ok);            // a field missing
    CHECK(!parse("omni-np1\nplaying\n1\n2\n0\n0\n0\ns\nt\na\nd\nextra").ok);  // one too many
    i = parse("omni-np1\nplaying\nNaN\n-5\n0\n0\n9\ns\nt\na\nd");
    CHECK(i.ok && i.position == -1 && i.duration == -1 && i.did == kDidNothing);
    CHECK(parse("omni-np1\nplaying\n1\n2\n0\n0\n0\n" + std::string(5000, 's') + "\nt\na\nd").src.size() == kSrcMax);

    // --- texts
    CHECK(clock(0) == "0:00" && clock(65) == "1:05" && clock(599.9) == "9:59" && clock(3723) == "1:02:03");
    CHECK(clock(-1).empty());
    Info p; p.ok = true; p.state = kPlaying; p.position = 65; p.duration = 240;
    CHECK(position(p) == "1:05 / 4:00");
    p.duration = kLive; CHECK(position(p) == "1:05 (live)");
    p.position = -1; CHECK(position(p) == "Live");
    p.position = -1; p.duration = 100; CHECK(position(p) == "0:00 / 1:40");
    p.position = 30; p.duration = -1; CHECK(position(p) == "0:30");
    p.state = kNone; CHECK(position(p).empty());
    CHECK(site("https://user@WWW.Example.COM:8443/x?y") == "example.com");
    CHECK(site("http://10.0.0.5:8080/a") == "10.0.0.5");
    CHECK(site("http://[2001:db8::1]:80/") == "[2001:db8::1]");
    CHECK(site("about:blank").empty() && site("omni://pages/start").empty());
    CHECK(clip("abc", 3) == "abc" && clip("abcdef", 5) == "ab..." && clip("abcdef", 2).empty());
    CHECK(clip("aa\xc3\xa9\xc3\xa9", 5) == "aa...");          // never splits the two-byte e-acute
    CHECK(clip("a\xe2\x82\xac\xe2\x82\xac" "x", 7) == "a\xe2\x82\xac...");
    CHECK(clip("a\xe2\x82\xac\xe2\x82\xac" "x", 6) == "a...");
    CHECK(rowValue("  Song - YouTube ", "https://www.youtube.com/watch?v=1") == "Song - YouTube");
    CHECK(rowValue("", "https://radio.example.org/") == "radio.example.org");
    CHECK(rowValue("New tab", "http://192.0.2.7/") == "192.0.2.7");
    CHECK(rowValue(std::string(80, 'x'), "").size() == 34);
    Info d; d.ok = true; d.title = " "; d.docTitle = "Doc";
    CHECK(displayTitle(d, "Tab") == "Doc");
    d.docTitle.clear(); CHECK(displayTitle(d, "Tab") == "Tab");
    CHECK(displayTitle(d, "") == "Untitled");
    d.title = "Meta"; CHECK(displayTitle(d, "Tab") == "Meta");

    // --- the panel's view
    Info none;
    View v = view(none, false, true, "Song - YouTube", "https://www.youtube.com/watch?v=1", false, false, false);
    CHECK(v.playLabel == "Play / Pause" && v.position == "Reading..." && !v.hasMedia && !v.seekable);
    CHECK(v.subtitle == "Song - YouTube | youtube.com" && v.muteLabel == "Mute tab" && v.goLabel == "Go to tab");
    CHECK(v.prevDetail.empty() && v.nextDetail.empty());
    v = view(none, true, false, "T", "https://a.example/", true, true, true);
    CHECK(v.position == "The page didn't answer" && v.muteLabel == "Unmute tab" && v.goLabel == "Back to the page");
    CHECK(v.subtitle == "T | a.example (private)");
    i = parse("omni-np1\nplaying\n65.0\n240.0\n0\n1\n1\nsrc\nSong\nBand\nDoc");
    v = view(i, true, true, "Tab", "https://music.example.com/", false, false, false);
    CHECK(v.playLabel == "Pause" && v.position == "1:05 / 4:00" && v.hasMedia && v.seekable);
    CHECK(v.subtitle == "Song - Band | music.example.com");
    CHECK(!v.prevDetail.empty() && v.nextDetail.empty());
    v = view(i, true, false, "Tab", "https://music.example.com/", false, false, false);   // WebKit says paused now
    CHECK(v.playLabel == "Play");
    i = parse("omni-np1\nnone\n\n\n0\n0\n0\n\n\n\nDoc");
    v = view(i, true, false, "Tab", "", false, false, false);
    CHECK(v.position == "No video or audio found" && !v.hasMedia && v.subtitle == "Doc");
    i = parse("omni-np1\nplaying\n5.0\n\n0\n0\n1\nsrc\n\n\nDoc");           // unknown duration: no seeking
    CHECK(!view(i, true, true, "", "", false, false, false).seekable);
    Info longInfo; longInfo.ok = true; longInfo.title = std::string(200, 'T');
    v = view(longInfo, true, false, "", "https://example.com/", false, false, false);
    CHECK(v.subtitle.size() <= 96 + 3 && v.subtitle.find(" | example.com") != std::string::npos);

    // --- notices
    Info bad;
    CHECK(resultNotice(kProbe, bad).empty() && resultNotice(kToggle, bad) == "The page didn't answer");
    i = parse("omni-np1\nnone\n\n\n0\n0\n3\n\n\n\nDoc");
    CHECK(resultNotice(kToggle, i) == "No video or audio found on this page");
    CHECK(resultNotice(kNext, i) == "Sent \"Next track\" to the page; this site may ignore it");
    CHECK(resultNotice(kPrev, i) == "Sent \"Previous track\" to the page; this site may ignore it");
    CHECK(resultNotice(kProbe, i).empty());
    i = parse("omni-np1\nplaying\n1\n2\n0\n1\n2\ns\n\n\nd");
    CHECK(resultNotice(kNext, i).empty() && resultNotice(kForward, i).empty());

    // --- JS string literals
    CHECK(jsString("") == "\"\"");
    CHECK(jsString("abc") == "\"abc\"");
    CHECK(jsString("a\"b'c\\d") == "\"a\\\"b'c\\\\d\"");
    CHECK(jsString("x\ny\r\tz") == "\"x\\ny\\r\\tz\"");
    CHECK(jsString("</script>") == "\"\\x3c/script>\"");
    CHECK(jsString(std::string("a\0b", 3)) == "\"a\\x00b\"");
    CHECK(jsString("\x01\x1f\x7f") == "\"\\x01\\x1f\\x7f\"");
    CHECK(jsString("a\xe2\x80\xa8" "b\xe2\x80\xa9") == "\"a\\u2028b\\u2029\"");
    CHECK(jsString("\xc3\xa9\xe2\x82\xac") == "\"\xc3\xa9\xe2\x82\xac\"");           // other UTF-8 kept as is
    CHECK(jsString("\xe2\x80") == "\"\xe2\x80\"");                                  // truncated sequence: no overrun

    // --- script text
    const std::string s = script(kNext, "blob:https://x.example/\"q\"\n");
    CHECK(s.rfind("(function(A,S,D){", 0) == 0);
    CHECK(s.size() > 20 && s.substr(s.size() - 40).find("(3,\"blob:https://x.example/\\\"q\\\"\\n\",10)") != std::string::npos);
    CHECK(script(kProbe, "").find("})(0,\"\",10)") != std::string::npos);
    CHECK(script(kBack, "", 30).find("})(4,\"\",30)") != std::string::npos);
    CHECK(script(kProbe, std::string(5000, 'a')).size() < std::strlen(kScriptBody) + kSrcMax + 32);
    CHECK(std::string(kScriptBody).find("setInterval") == std::string::npos);   // no polling, nothing left behind
    CHECK(std::string(kScriptBody).find("addEventListener") == std::string::npos);
    CHECK(std::string(kScriptBody).find("fetch(") == std::string::npos && std::string(kScriptBody).find("XMLHttpRequest") == std::string::npos);

    if (argc == 3 && std::strcmp(argv[1], "--emit") == 0) {   // the scripts node test_media_controls.cjs runs
        const char* names[] = { "probe", "toggle", "prev", "next", "back", "forward" };
        for (int a = kProbe; a <= kForward; ++a) {
            std::ofstream(std::string(argv[2]) + "/np-" + names[a] + ".js", std::ios::binary) << script(Action(a), "");
            std::ofstream(std::string(argv[2]) + "/np-" + names[a] + "-src.js", std::ios::binary)
                << script(Action(a), "http://192.0.2.10/b.mp4");
        }
        std::ofstream(std::string(argv[2]) + "/np-escape.js", std::ios::binary) << script(kProbe, "a\"b\\c\n</script>\xe2\x80\xa8");
    }

    std::printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
