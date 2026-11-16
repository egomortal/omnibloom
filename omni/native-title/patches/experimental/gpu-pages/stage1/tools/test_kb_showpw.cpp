// OMNI_KB_SHOWPW_V1: host tests of the pure "Show password while typing" guard (OmniKbShowPw.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_kb_showpw.cpp -o t && ./t      (run in tools/, or -I<tree>/engine/entry)
#include "OmniKbShowPw.h"
#include <cstdio>
#include <string>

namespace P = OmniKbShowPw;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

// Types `s` the way the shell does: typed() first, then the field is read again.
static void type(P::Guard& g, size_t& len, const std::string& s) { g.typed(P::cpCount(s)); len += P::cpCount(s); g.observe(len); }

int main()
{
    // --- counting ---
    CHECK(P::cpCount("") == 0);
    CHECK(P::cpCount("abc") == 3);
    CHECK(P::cpCount("p\xc3\xa4ss\xe2\x82\xac") == 5);      // ä (2 bytes), € (3 bytes)
    CHECK(P::cpCount("\xf0\x9f\x98\x80x") == 2);             // emoji (4 bytes)

    // --- off by default; empty field, typed here: shown on request, hidden on the second press ---
    {
        P::Guard g; g.reset(1, 5);
        CHECK(!g.reveal());
        CHECK(g.toggle() == P::Toggle::Pending);              // the field wasn't read yet
        CHECK(!g.reveal());
        size_t len = 0;
        g.observe(0);
        CHECK(g.clean() && !g.reveal());                      // never shown without a press
        type(g, len, "hunter"); type(g, len, "2");
        CHECK(g.clean() && !g.reveal());
        CHECK(g.toggle() == P::Toggle::Shown);
        CHECK(g.reveal());
        type(g, len, "!");
        CHECK(g.reveal());
        g.observe(len - 1);                                   // Delete: still only typed text
        CHECK(g.reveal());
        CHECK(g.toggle() == P::Toggle::Hidden);
        CHECK(!g.reveal());
        CHECK(g.toggle() == P::Toggle::Shown && g.reveal());
    }

    // --- a field that held text when the keyboard opened (a saved login filled before, a saved password edited) ---
    {
        P::Guard g; g.reset(2, 5);
        g.observe(7);                                         // "secret7" from the vault
        CHECK(!g.clean());
        CHECK(g.toggle() == P::Toggle::Refused && !g.reveal());
        g.typed(3); g.observe(10);                            // typing after it does not make it showable
        CHECK(g.toggle() == P::Toggle::Refused && !g.reveal());
        g.observe(0);                                         // Clear: from now on, what is typed can be shown
        size_t len = 0;
        type(g, len, "abc");
        CHECK(g.clean() && g.toggle() == P::Toggle::Shown && g.reveal());
    }

    // --- typing before the first read: the first read is not empty -> not showable ---
    {
        P::Guard g; g.reset(3, 5);
        g.typed(2);
        g.observe(2);
        CHECK(!g.clean() && g.toggle() == P::Toggle::Refused);
    }

    // --- a saved login filled while shown: hidden at once, and a shorter saved password can't slip in ---
    {
        P::Guard g; g.reset(4, 5);
        size_t len = 0;
        g.observe(0);
        type(g, len, "0123456789");                           // 10 typed
        CHECK(g.toggle() == P::Toggle::Shown && g.reveal());
        g.taint();                                            // Fill login
        CHECK(!g.reveal());
        g.observe(10);                                        // the mirror is one probe behind
        CHECK(!g.reveal());
        g.observe(7);                                         // the filled password (7 <= 10 typed): still hidden
        CHECK(!g.reveal() && g.toggle() == P::Toggle::Refused);
    }
    // --- the stale mirror said "empty" right after the fill: the fill's text is longer than what was typed since ---
    {
        P::Guard g; g.reset(5, 5);
        g.observe(0);
        g.taint();
        g.observe(0);                                         // read before the fill landed
        CHECK(g.clean());
        g.observe(7);                                         // the fill lands: 7 > 0 typed
        CHECK(!g.clean() && !g.reveal() && g.toggle() == P::Toggle::Refused);
    }

    // --- Undo may bring back text from before: hidden until seen empty ---
    {
        P::Guard g; g.reset(6, 5);
        g.observe(9);                                         // pre-filled
        g.observe(0);                                         // Clear
        size_t len = 0;
        type(g, len, "abcdefghijkl");                         // 12 typed
        CHECK(g.toggle() == P::Toggle::Shown);
        g.taint();                                            // Undo (x n) -> back to the 9 pre-filled characters
        g.observe(9);
        CHECK(!g.reveal() && g.toggle() == P::Toggle::Refused);
    }

    // --- text that appears from elsewhere (a page script) hides it ---
    {
        P::Guard g; g.reset(7, 5);
        size_t len = 0;
        g.observe(0);
        type(g, len, "ab");
        CHECK(g.toggle() == P::Toggle::Shown);
        g.observe(6);                                         // 6 > 2 typed
        CHECK(!g.reveal());
        g.observe(2);                                         // shrinking back does not bring it back
        CHECK(!g.reveal() && !g.clean());
    }

    // --- per session / field: a new session or field starts hidden (keyboard closed and reopened) ---
    {
        P::Guard g; g.reset(8, 5);
        size_t len = 0;
        g.observe(0); type(g, len, "x");
        CHECK(g.toggle() == P::Toggle::Shown && g.reveal());
        CHECK(g.same(8, 5) && !g.same(9, 5) && !g.same(8, 0));
        g.reset(9, 5);
        CHECK(!g.reveal() && !g.clean() && g.typedCount() == 0);
        g.observe(1);                                         // the same text, seen by the next session: not showable
        CHECK(g.toggle() == P::Toggle::Refused);
    }

    // --- Paste counts as typed (the user's own clipboard; passwords can't be copied) ---
    {
        P::Guard g; g.reset(10, 5);
        size_t len = 0;
        g.observe(0);
        type(g, len, "pasted text here");
        CHECK(g.toggle() == P::Toggle::Shown && g.reveal());
    }

    // --- overflow-safe counter ---
    {
        P::Guard g; g.reset(11, 5);
        g.observe(0);
        g.typed(size_t(-1)); g.typed(5);
        CHECK(g.typedCount() == size_t(-1));
    }

    // --- labels ---
    CHECK(std::string(P::keyLabel(false)) == "Show" && std::string(P::keyLabel(true)) == "Hide");
    CHECK(P::shownLabel("Password") == "Password (shown)");
    CHECK(P::shownLabel("Password (hidden)") == "Password (shown)");
    CHECK(P::shownLabel("Master password") == "Master password (shown)");
    CHECK(P::shownLabel("") == "Password (shown)");
    CHECK(P::shownLabel(" (hidden)") == "Password (shown)");
    for (auto t : { P::Toggle::Shown, P::Toggle::Hidden, P::Toggle::Pending, P::Toggle::Refused })
        CHECK(std::string(P::toggleNotice(t)).size() > 5);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
