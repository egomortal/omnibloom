// OMNI_CRASH_CHOICES_V1 pure tests: g++ -std=c++20 -Wall -Wextra -I<tools> test_crash_choices.cpp -o t && ./t
#include "OmniCrashChoices.h"
#include <cstdio>

namespace C = OmniCrashChoices;
static int fails = 0;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); ++fails; } } while (0)

int main()
{
    // host keys
    CHECK(C::hostKey("https://www.Example.com/a?b") == "example.com");
    CHECK(C::hostKey("http://user:pw@Sub.Example.COM.:8080/x") == "sub.example.com");
    CHECK(C::hostKey("https://[::1]:443/") == "[::1]");
    CHECK(C::hostKey("https://www./") == "www");
    CHECK(C::hostKey("omni://start") == "");
    CHECK(C::hostKey("about:blank") == "");
    CHECK(C::hostKey("") == "");

    // counting per host
    C::Ledger L;
    CHECK(L.count("a.com") == 0);
    CHECK(L.note("a.com", 1000) == 1);
    CHECK(L.note("b.com", 2000) == 1);
    CHECK(L.note("a.com", 3000) == 2);
    CHECK(L.count("a.com") == 2 && L.count("b.com") == 1);
    CHECK(!C::showAdvice("a.com", 1) && C::showAdvice("a.com", 2) && C::showAdvice("a.com", 5));
    CHECK(!C::showAdvice("", 3));   // non-web pages never get the advice

    // loop guard: the first crash may auto-reload; a 2nd within 5 min may not; later ones only if spaced out
    C::Ledger G;
    G.note("v.com", 10000);
    CHECK(G.autoReloadOk("v.com"));
    G.note("v.com", 10000 + C::kLoopWindowMs - 1);
    CHECK(!G.autoReloadOk("v.com"));
    G.note("v.com", 10000 + C::kLoopWindowMs - 1 + C::kLoopWindowMs);   // exactly 5 min later
    CHECK(G.autoReloadOk("v.com"));
    G.note("v.com", 10000 + 2 * C::kLoopWindowMs + 100);                // < 5 min after the previous
    CHECK(!G.autoReloadOk("v.com"));
    CHECK(G.autoReloadOk("other.com"));
    // wrap-safe: crashes either side of the 32-bit tick wrap
    C::Ledger W;
    W.note("w.com", 0xFFFFFF00u);
    W.note("w.com", 0x00000100u);   // 512 ms later
    CHECK(!W.autoReloadOk("w.com"));
    W.note("w.com", 0x00000100u + C::kLoopWindowMs);
    CHECK(W.autoReloadOk("w.com"));

    // ledger cap: the oldest host goes
    C::Ledger M;
    for (size_t i = 0; i < C::kMaxHosts; ++i) M.note("h" + std::to_string(i), uint32_t(i));
    M.note("h0", 999);   // h0 is now the newest
    M.note("new", 1000);
    CHECK(M.size() == C::kMaxHosts);
    CHECK(M.count("h0") == 2 && M.count("h1") == 0 && M.count("new") == 1);

    // choices
    auto all = C::choices(true, true);
    CHECK(all.size() == 5 && all[0] == C::Reload && all[1] == C::Reader && all[2] == C::DataSaver
          && all[3] == C::UnloadOthers && all[4] == C::CloseTab);
    auto lone = C::choices(true, false);
    CHECK(lone.size() == 4 && lone[3] == C::CloseTab);
    auto local = C::choices(false, true);
    CHECK(local.size() == 3 && local[1] == C::UnloadOthers);
    CHECK(std::string(C::label(C::DataSaver, false)) == "Reload with Data saver");
    CHECK(std::string(C::label(C::DataSaver, true)) == "Reload (Data saver is on)");

    // focus
    CHECK(C::moveFocus(0, -1, 5) == 0);
    CHECK(C::moveFocus(0, 1, 5) == 1);
    CHECK(C::moveFocus(4, 1, 5) == 4);
    CHECK(C::moveFocus(7, 0, 3) == 2);
    CHECK(C::moveFocus(3, 0, 0) == 0);

    // layout and hit test
    const C::Layout a = C::layout(2, true, 5), b = C::layout(2, false, 5);
    CHECK(a.h == b.h + 34 && a.adviceY > 108 && a.listY > a.adviceY);
    CHECK(a.h <= 520);
    CHECK(C::rowAt(a, 5, C::kRowX + 5, C::rowY(a, 0) + 1) == 0);
    CHECK(C::rowAt(a, 5, C::kRowX + 5, C::rowY(a, 4) + C::kRowH - 1) == 4);
    CHECK(C::rowAt(a, 5, C::kRowX + 5, C::rowY(a, 1) - 1) == -1);   // the gap
    CHECK(C::rowAt(a, 5, C::kRowX - 1, C::rowY(a, 0) + 1) == -1);
    CHECK(C::rowAt(a, 5, C::kRowX + 5, C::rowY(a, 5) + 1) == -1);

    // texts: logs never name a host
    CHECK(C::unloadNotice(0).find("No other") == 0 && C::unloadNotice(1) == "Unloaded 1 tab. Reloading..."
          && C::unloadNotice(3) == "Unloaded 3 tabs. Reloading...");
    const std::string lg = C::logLine(2, true, false);
    CHECK(lg.find("crash 2") != std::string::npos && lg.find("private tab") != std::string::npos);

    std::printf(fails ? "%d FAILED\n" : "all crash choices tests passed\n", fails);
    return fails ? 1 : 0;
}
