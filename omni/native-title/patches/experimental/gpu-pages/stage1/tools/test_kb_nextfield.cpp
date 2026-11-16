// OMNI_KB_NEXTFIELD_V1 host tests: g++ -std=c++20 -Wall -Wextra -I. test_kb_nextfield.cpp -o t && ./t   (in tools/)
#include "OmniKbNextField.h"
#include <cstdio>
#include <string>

namespace N = OmniKbNextField;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // script(): one placeholder, the mode put in; the raw string keeps its end
    const std::string raw = N::kScript;
    CHECK(raw.find("__M__") != std::string::npos);
    CHECK(raw.find("__M__", raw.find("__M__") + 1) == std::string::npos);
    CHECK(raw.size() > 5 && raw.compare(raw.size() - 5, 5, "}})()") == 0);
    CHECK(N::script('n').find("var M='n'") != std::string::npos);
    CHECK(N::script('p').find("var M='p'") != std::string::npos);
    CHECK(N::script('c').find("var M='c'") != std::string::npos);
    CHECK(N::script('x').find("var M='c'") != std::string::npos);
    CHECK(N::script('n').find("__M__") == std::string::npos);
    CHECK(N::script('n').size() == raw.size() - 4);
    // the same frame walk as OMNI_KEYBOARD_V2's probe
    CHECK(raw.find("while(e&&e.tagName==='IFRAME'&&n<4)") != std::string::npos);

    // parse
    auto p = N::parse("moved,2,5");
    CHECK(p.kind == N::kMoved && p.index == 2 && p.total == 5);
    p = N::parse("edge,4,5");
    CHECK(p.kind == N::kEdge && p.index == 4 && p.total == 5);
    p = N::parse("edge,-1,0");
    CHECK(p.kind == N::kEdge && p.index == -1 && p.total == 0);
    p = N::parse("count,0,1");
    CHECK(p.kind == N::kCount && p.index == 0 && p.total == 1);
    p = N::parse("count,-1,3");
    CHECK(p.kind == N::kCount && p.index == -1 && p.total == 3);
    CHECK(N::parse("none").kind == N::kNone);
    CHECK(N::parse("").kind == N::kBad);
    CHECK(N::parse("moved,-1,3").kind == N::kBad);     // a move always lands on a listed box
    CHECK(N::parse("moved,3,3").kind == N::kBad);
    CHECK(N::parse("count,0,0").kind == N::kBad);
    CHECK(N::parse("count,-2,3").kind == N::kBad);
    CHECK(N::parse("count,1,-1").kind == N::kBad);
    CHECK(N::parse("count,1,3,4").kind == N::kBad);
    CHECK(N::parse("count,1").kind == N::kBad);
    CHECK(N::parse("count,a,3").kind == N::kBad);
    CHECK(N::parse("count,,3").kind == N::kBad);
    CHECK(N::parse("count,1,99999999").kind == N::kBad);
    CHECK(N::parse("jumped,1,3").kind == N::kBad);
    CHECK(N::parse("Moved,1,3").kind == N::kBad);
    CHECK(N::parse("-").kind == N::kBad);

    // step
    CHECK(N::step(N::parse("moved,1,3"), 1) == N::sReopen);
    CHECK(N::step(N::parse("moved,0,3"), -1) == N::sReopen);
    CHECK(N::step(N::parse("edge,2,3"), 1) == N::sDone);
    CHECK(N::step(N::parse("edge,0,3"), -1) == N::sFirst);
    CHECK(N::step(N::parse("edge,-1,0"), 1) == N::sDone);
    CHECK(N::step(N::parse("none"), 1) == N::sNoField);
    CHECK(N::step(N::parse("garbage"), -1) == N::sNoField);
    CHECK(N::step(N::parse("count,1,3"), 1) == N::sStay);

    // the hint: Next text box, Done on the last one
    CHECK(std::string(N::nextLabel(true, 2, 3)) == "Done");
    CHECK(std::string(N::nextLabel(true, 0, 1)) == "Done");
    CHECK(std::string(N::nextLabel(true, 1, 3)) == "Next text box");
    CHECK(std::string(N::nextLabel(false, 2, 3)) == "Next text box");   // not known for this session
    CHECK(std::string(N::nextLabel(true, -1, 3)) == "Next text box");
    CHECK(std::string(N::nextLabel(true, -1, 0)) == "Next text box");
    CHECK(!N::isLast(true, 0, 0));

    // Shift undo
    CHECK(N::capsAfterChord(1, 0, true) == 0);
    CHECK(N::capsAfterChord(2, 1, true) == 1);
    CHECK(N::capsAfterChord(0, 2, true) == 2);
    CHECK(N::capsAfterChord(1, 0, false) == 1);

    // busy window (with tick wrap)
    CHECK(N::busy(true, 1000, 1200));
    CHECK(!N::busy(true, 1000, 1000 + N::kBusyMs));
    CHECK(!N::busy(false, 1000, 1001));
    CHECK(N::busy(true, 0xfffffff0u, 0x10u));

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "OK", checks, fails);
    return fails ? 1 : 0;
}
