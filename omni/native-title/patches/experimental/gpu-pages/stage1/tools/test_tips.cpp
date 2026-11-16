// OMNI_TIPS_V1: host tests for OmniTips.h (the pure part of the one-time tips), plus cross-checks against the tree:
//   - every tip's "facts" (the buttons its text names) are rows of the Controls guide table (OmniControlsHelp.h),
//   - every {token} a template uses is a button the guide knows, with the guide's PlayStation / Xbox names,
//   - with OmniButtonMap.h: the translate tip's default button (Touchpad) is that table's default for "Translate page".
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tips.cpp -o t && ./t [probe.js]
// (argv[1]: the two probe scripts are written there, one per line, for a node syntax check.)
#include "OmniTips.h"
#include "OmniControlsHelp.h"
#if __has_include("OmniButtonMap.h")
#include "OmniButtonMap.h"
#define HAVE_BMAP 1
#else
#define HAVE_BMAP 0
#endif

#include <cstdio>
#include <cstring>
#include <set>
#include <string>

namespace T = OmniTips;
namespace H = OmniControlsHelp;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static std::vector<T::Variant> allVariants()
{
    std::vector<T::Variant> v;
    for (int m = 0; m < 16; ++m) { T::Variant x; x.npExtras = m & 1; x.highlights = m & 2; x.readingProgress = m & 4; x.wordChips = m & 8; v.push_back(x); }
    return v;
}

static void testTable()
{
    std::set<std::string> keys;
    for (int i = 0; i < T::kCount; ++i) {
        const T::Info& in = T::info(i);
        CHECK(T::validKey(in.key));
        CHECK(keys.insert(in.key).second);
        CHECK(T::idFromKey(in.key) == i);
        CHECK(in.freshMs >= 15000 && in.freshMs <= 120000);
        CHECK(std::strlen(in.trigger) > 0);
        CHECK(in.remap == (i == T::tTranslate));
        for (const T::Variant& v : allVariants()) {
            const std::string t = T::templ(i, v);
            CHECK(!t.empty() && t.size() <= 110);
            // every token is a known button (or {@} on the remap tip only)
            for (size_t p = t.find('{'); p != std::string::npos; p = t.find('{', p + 1)) {
                const size_t q = t.find('}', p);
                CHECK(q != std::string::npos);
                const std::string tok = t.substr(p + 1, q - p - 1);
                CHECK(tok == "@" ? in.remap : T::buttonName(tok, true) != nullptr);
            }
            CHECK((t.find("{@}") != std::string::npos) == in.remap);
            const std::string ps = T::expand(t, true, "Touchpad"), xb = T::expand(t, false, "Touchpad");
            CHECK(!ps.empty() && ps.find('{') == std::string::npos && xb.find('{') == std::string::npos);
        }
    }
    CHECK(T::idFromKey("nope") == -1);
    CHECK(T::kShowRowId == 851 && T::kResetRowId == 852);
    // variants pick the right words
    T::Variant v;
    v.highlights = false; CHECK(std::string(T::templ(T::tSelectText, v)).find("Highlight") == std::string::npos);
    v.highlights = true; CHECK(std::string(T::templ(T::tSelectText, v)).find("Highlight") != std::string::npos);
    v.readingProgress = true; CHECK(std::string(T::templ(T::tReadingList, v)).find("how far") != std::string::npos);
    v.wordChips = false; CHECK(std::string(T::templ(T::tKeyboard, v)).find("D-pad") == std::string::npos);
    v.npExtras = false; CHECK(std::string(T::templ(T::tVideo, v)).find("sleep timer") == std::string::npos);
}

// The tokens' names are the Controls guide's glyph names (PlayStation and Xbox).
static void testNamesMatchGuide()
{
    static const struct { const char* tok; int glyph; } k[] = {
        { "Cross", H::gCross }, { "Circle", H::gCircle }, { "Square", H::gSquare }, { "Triangle", H::gTriangle },
        { "L1", H::gL1 }, { "R1", H::gR1 }, { "L2", H::gL2 }, { "R2", H::gR2 }, { "L3", H::gL3 }, { "R3", H::gR3 },
        { "Options", H::gOptions }, { "Create", H::gCreate } };
    for (const auto& e : k) {
        CHECK(std::string(T::buttonName(e.tok, true)) == H::glyphName(e.glyph, true));
        CHECK(std::string(T::buttonName(e.tok, false)) == H::glyphName(e.glyph, false));
        // and expand() agrees with the guide's own expand()
        const std::string s = std::string("x {") + e.tok + "} y";
        CHECK(T::expand(s, true) == H::expand(s, true));
        CHECK(T::expand(s, false) == H::expand(s, false));
    }
    CHECK(T::buttonName("Nope", true) == nullptr);
}

// The guide row's keys by PlayStation names: "L2 + L1 / R1", "Cross", ...
static std::string rowKeys(const H::Entry& e)
{
    std::string out;
    int n = 0;
    for (int g : e.keys) {
        if (g == H::gNone) break;
        if (n++) out += e.join == '/' ? " / " : " + ";
        out += H::glyphName(g, true);
    }
    return out;
}
static void testFactsAgainstGuide()
{
    int facts = 0;
    for (int i = 0; i < T::kCount; ++i)
        for (const T::Fact& f : T::info(i).facts) {
            if (!f.keys) continue;
            ++facts;
            bool found = false;
            for (const H::Entry& e : H::table())
                if (rowKeys(e) == f.keys && e.hold == f.hold
                    && (std::string(e.action).find(f.text) != std::string::npos || std::string(e.note).find(f.text) != std::string::npos))
                    found = true;
            if (!found) std::printf("  fact not in the Controls guide: tip %s: %s%s -> %s\n", T::info(i).key, f.hold ? "hold " : "", f.keys, f.text);
            CHECK(found);
        }
    CHECK(facts >= 15);
    // Each tip whose text names a button has at least one fact (the image viewer's keys are not in the guide).
    for (int i = 0; i < T::kCount; ++i) if (i != T::tImage) CHECK(T::info(i).facts[0].keys != nullptr);
}

static void testRemap()
{
    const std::string t = T::templ(T::tTranslate, T::Variant());
    CHECK(T::expand(t, true, "Touchpad") == "Press Touchpad to translate this page (Google Translate)");
    CHECK(T::expand(t, true, "R3") == "Press R3 to translate this page (Google Translate)");
    CHECK(T::expand(t, false, "LT + Y") == "Press LT + Y to translate this page (Google Translate)");
    CHECK(T::expand(t, true, "").empty());   // no button runs it now: skipped
    CHECK(T::expand("{Cross} and {Bogus}", true) == "Cross and {Bogus}");
    CHECK(T::expand("{Cross", true) == "{Cross");
    CHECK(T::expand("{L2} + {L3}", false) == "LT + LS");
#if HAVE_BMAP
    namespace B = OmniButtonMap;
    // The default the shell falls back to without the map is the map's own default slot for "translate".
    CHECK(B::slot(B::sTouchpad).def == B::aTranslate);
    CHECK(B::slotName(B::sTouchpad, true) == "Touchpad");
    int n = 0;
    for (int s = 0; s < B::kSlotCount; ++s) n += B::slot(s).def == B::aTranslate ? 1 : 0;
    CHECK(n == 1);
    // The other buttons the tips name are not remappable (Cross, Circle, L1 / R1, L2 + L1 / R1, L2 + L3, Options, Create).
    for (int s = 0; s < B::kSlotCount; ++s) {
        const std::string ps = B::slot(s).ps;
        CHECK(ps != "Cross" && ps != "Circle" && ps != "L1" && ps != "R1" && ps != "Options" && ps != "Create" && ps != "L2 + L3");
    }
    std::printf("  (button map present: remap checks run)\n");
#else
    std::printf("  (no OmniButtonMap.h in this tree: remap table checks skipped)\n");
#endif
}

static void testStore()
{
    T::Store s = T::parse("");
    CHECK(s.enabled && s.seen == 0 && s.other.empty() && s.seenCount() == 0);
    s.markSeen(T::tVideo); s.markSeen(T::tQrShare); s.markSeen(-1); s.markSeen(T::kCount);
    CHECK(s.isSeen(T::tVideo) && s.isSeen(T::tQrShare) && !s.isSeen(T::tFindBar) && s.seenCount() == 2);
    s.enabled = false;
    s.other.push_back("future-tip");
    const std::string text = T::serialize(s);
    CHECK(text.rfind("omni-tips\t1\n", 0) == 0);
    CHECK(text.find("enabled\t0\n") != std::string::npos);
    CHECK(text.find("seen\tvideo\n") != std::string::npos && text.find("seen\tqr-share\n") != std::string::npos);
    const T::Store r = T::parse(text);
    CHECK(!r.enabled && r.seen == s.seen && r.other.size() == 1 && r.other[0] == "future-tip");
    CHECK(T::serialize(r) == text);
    // CRLF, blanks, comments, junk, duplicates, bad keys, bad enabled values
    const T::Store q = T::parse("omni-tips\t1\r\n\r\n# hi\r\nenabled\tmaybe\r\nseen\tfind-bar\r\nseen\tfind-bar\r\nseen\tBAD KEY\r\n"
                                "seen\tx-1\r\nseen\tx-1\r\njunk\r\nseen\t\r\nenabled\t1\r\n");
    CHECK(q.enabled && q.isSeen(T::tFindBar) && q.seenCount() == 1 && q.other.size() == 1 && q.other[0] == "x-1");
    // size cap: a line after kMaxFileBytes is not read
    std::string big = "omni-tips\t1\n" + std::string(T::kMaxFileBytes, '#') + "\nseen\tvideo\n";
    CHECK(!T::parse(big).isSeen(T::tVideo));
    // at most kMaxOtherKeys unknown keys
    std::string many;
    for (int i = 0; i < 100; ++i) many += "seen\tk" + std::to_string(i) + "\n";
    CHECK(T::parse(many).other.size() == T::kMaxOtherKeys);
    T::Store z = r; z.reset();
    CHECK(z.seen == 0 && z.other.empty() && !z.enabled);   // reset keeps the On / Off choice
}

static void testGate()
{
    T::Context c;
    CHECK(!T::quiet(c));   // no tab
    c.haveTab = true;
    CHECK(T::quiet(c) && T::mayStart(c));
    c.toast = true; CHECK(T::quiet(c) && !T::mayStart(c)); c.toast = false;
    c.fullscreen = true; CHECK(!T::quiet(c) && !T::mayStart(c)); c.fullscreen = false;
    c.typing = true; CHECK(!T::quiet(c)); c.typing = false;
    c.covered = true; CHECK(!T::quiet(c)); c.covered = false;
    c.testMode = true; CHECK(!T::quiet(c)); c.testMode = false;

    T::Rate r;
    CHECK(!T::rateOk(r, 100000));   // not started
    T::start(r, 1000);
    T::start(r, 50000);             // only the first start counts
    CHECK(r.startedAt == 1000);
    CHECK(!T::rateOk(r, 1000 + T::kStartQuietMs - 1));
    CHECK(T::rateOk(r, 1000 + T::kStartQuietMs));
    T::shown(r, 70000);
    CHECK(!T::rateOk(r, 70000 + T::kGapMs - 1));
    CHECK(T::rateOk(r, 70000 + T::kGapMs));
    // wrap-around of SDL_GetTicks()
    T::Rate w; T::start(w, 0xFFFFF000u);
    CHECK(!T::rateOk(w, 0x00000100u));
    CHECK(T::rateOk(w, 0xFFFFF000u + T::kStartQuietMs));
    T::shown(w, 0xFFFFFF00u);
    CHECK(!T::rateOk(w, 0x00001000u));
    CHECK(T::rateOk(w, uint32_t(0xFFFFFF00u + T::kGapMs)));
}

static void testArms()
{
    T::Arms a;
    T::Store s;
    const unsigned all = (1u << T::kCount) - 1;
    CHECK(!a.any() && a.pick(0, s, all) == -1);
    a.arm(T::tVideo, 1000);
    a.arm(T::tKeyboard, 5000);
    CHECK(a.any());
    CHECK(a.pick(6000, s, all) == T::tKeyboard);                         // most recent
    CHECK(a.pick(6000, s, all & ~(1u << T::tKeyboard)) == T::tVideo);    // not available: the next one
    s.markSeen(T::tKeyboard);
    CHECK(a.pick(6000, s, all) == T::tVideo);                            // seen: never again
    CHECK(a.pick(1000 + T::info(T::tVideo).freshMs, s, all) == T::tVideo);
    CHECK(a.pick(1000 + T::info(T::tVideo).freshMs + 1, s, all) == -1);  // stale
    a.expire(1000 + T::info(T::tVideo).freshMs + 1);
    CHECK(!a.on[T::tVideo]);
    a.arm(T::tFindBar, 0xFFFFFFF0u);                                     // wraps
    CHECK(a.pick(0x10, s, all) == T::tFindBar);
    a.clear(T::tFindBar);
    CHECK(a.pick(0x10, s, all) == -1);
    a.arm(T::tQrShare, 1); a.arm(-1, 1); a.arm(T::kCount, 1);
    a.clearAll();
    CHECK(!a.any());
}

static void testCard()
{
    const int base = 720 - 32 - 18;
    T::Card c = T::card(30, 500, 1280, base, false);
    CHECK(c.x == T::kMarginX && c.h == T::kCardH && c.y + c.h == base);
    CHECK(c.w == T::kPadX + 30 + T::kGap + 500 + T::kGap + T::kCloseW + T::kPadX);
    CHECK(T::textRoom(c, 30) >= 500);
    T::Card up = T::card(30, 500, 1280, base, true);
    CHECK(up.y == c.y - T::kAbove);
    T::Card wide = T::card(30, 5000, 1280, base, false);
    CHECK(wide.x + wide.w == 1280 - T::kMarginX);
    CHECK(T::textRoom(wide, 30) < 5000 && T::textRoom(wide, 30) > 1000);
    T::Card small = T::card(10, 10, 1280, base, false);
    CHECK(small.w == T::kMinW);
    CHECK(T::inside(c, c.x, c.y) && T::inside(c, c.x + c.w - 1, c.y + c.h - 1));
    CHECK(!T::inside(c, c.x - 1, c.y) && !T::inside(c, c.x, c.y + c.h) && !T::inside(c, c.x + c.w, c.y));
    T::Card top = T::card(30, 500, 1280, 20, true);
    CHECK(top.y >= 8);
    // the card stays above the hint bar and the toast's line
    CHECK(c.y + c.h <= 720 - 32);
}

static void testPages()
{
    CHECK(T::foreignLang("de") && T::foreignLang("fr-CA") && T::foreignLang(" ES ") && T::foreignLang("pt_BR") && T::foreignLang("fil"));
    CHECK(!T::foreignLang("") && !T::foreignLang("en") && !T::foreignLang("EN-gb") && !T::foreignLang("en_US") && !T::foreignLang("und")
          && !T::foreignLang("zxx") && !T::foreignLang("mul") && !T::foreignLang("x") && !T::foreignLang("english") && !T::foreignLang("1a"));
    CHECK(T::youtubeDesktop("https://www.youtube.com/") && T::youtubeDesktop("https://www.youtube.com/watch?v=abc")
          && T::youtubeDesktop("https://m.youtube.com/") && T::youtubeDesktop("http://youtube.com") && T::youtubeDesktop("https://WWW.YouTube.com:443/x")
          && T::youtubeDesktop("https://www.youtube.com/tvshows"));
    CHECK(!T::youtubeDesktop("https://www.youtube.com/tv") && !T::youtubeDesktop("https://www.youtube.com/tv#/watch?v=a")
          && !T::youtubeDesktop("https://www.youtube.com/tv/x") && !T::youtubeDesktop("https://www.youtube.com/tv?x=1")
          && !T::youtubeDesktop("https://youtube.com.evil.example/") && !T::youtubeDesktop("https://music.youtube.com/")
          && !T::youtubeDesktop("omni://start") && !T::youtubeDesktop("https://example.com/youtube.com"));
    const std::string p = T::textProbe(123.45, 67.8);
    CHECK(p.rfind("(function(X,Y){", 0) == 0);
    CHECK(p.find("})(123.") != std::string::npos && p.compare(p.size() - 6, 6, ",67.8)") == 0);
    CHECK(p.find("caretRangeFromPoint") != std::string::npos && p.find("return'text'") != std::string::npos);
    CHECK(T::isText("text") && !T::isText("no") && !T::isText(""));
    CHECK(std::string(T::langProbe()).find("documentElement.lang") != std::string::npos);
}

int main(int argc, char** argv)
{
    testTable();
    testNamesMatchGuide();
    testFactsAgainstGuide();
    testRemap();
    testStore();
    testGate();
    testArms();
    testCard();
    testPages();
    if (argc > 1) {
        if (FILE* f = std::fopen(argv[1], "w")) {
            std::fprintf(f, "%s;\n%s;\n", T::textProbe(10, 20).c_str(), T::langProbe());
            std::fclose(f);
        }
    }
    // the texts, for the report
    for (int i = 0; i < T::kCount; ++i) std::printf("  %-13s %s\n", T::info(i).key, T::expand(T::templ(i, T::Variant()), true, "Touchpad").c_str());
    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "OK", checks, fails);
    return fails ? 1 : 0;
}
