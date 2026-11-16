// OMNI_ZAPPER_V1: host tests of OmniZapper.h (rule store, cosmetic rule parsing, sheets, selector checks, script).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_zapper.cpp -o t && ./t [core.js]
// With an argument, the page script's core (one function expression) is written there for test_zapper_js.cjs.
#include "OmniZapper.h"
#include <cstdio>
#include <fstream>
#include <limits>

namespace OZ = OmniZapper;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

int main(int argc, char** argv)
{
    // hosts
    CHECK(OZ::validHost("example.com") && OZ::validHost("a-b.co.uk") && OZ::validHost("192.168.0.2"));
    CHECK(!OZ::validHost("") && !OZ::validHost(".a.com") && !OZ::validHost("a..com") && !OZ::validHost("A.com") && !OZ::validHost("~a.com")
          && !OZ::validHost("a.*") && !OZ::validHost("a.com.") && !OZ::validHost(std::string(254, 'a')));
    CHECK(OZ::hostCovers("example.com", "example.com") && OZ::hostCovers("example.com", "news.example.com"));
    CHECK(!OZ::hostCovers("example.com", "badexample.com") && !OZ::hostCovers("news.example.com", "example.com") && !OZ::hostCovers("", "a.com"));
    CHECK(OZ::allowPatterns("example.com") == std::vector<std::string>{ "*://*.example.com/*" });
    CHECK(OZ::allowPatterns("10.0.0.1") == std::vector<std::string>{ "*://10.0.0.1/*" });
    CHECK(OZ::allowPatterns("bad host").empty());

    // selectors
    CHECK(OZ::cssSafe("#cookie-banner") && OZ::cssSafe("div.a > span:nth-of-type(2)") && OZ::cssSafe("a[href*=\"x)y\"]"));
    CHECK(!OZ::cssSafe("a[href*=\"x}y\"]"));   // braces are refused even inside quotes
    CHECK(!OZ::cssSafe("") && !OZ::cssSafe("a{x}") && !OZ::cssSafe("a}b{") && !OZ::cssSafe("a;b") && !OZ::cssSafe("a/*x*/")
          && !OZ::cssSafe("@import x") && !OZ::cssSafe("a\nb") && !OZ::cssSafe("a[x") && !OZ::cssSafe("a(") && !OZ::cssSafe("a)")
          && !OZ::cssSafe("a[x=\"y]") && !OZ::cssSafe("> a") && !OZ::cssSafe("a\\") && !OZ::cssSafe(std::string(OZ::kMaxSelector + 1, 'a')));
    CHECK(!OZ::cssSafe("div:has-text(Ad)") && !OZ::cssSafe("div:style(color: red)") && !OZ::cssSafe("div:upward(2)") && OZ::cssSafe("div:has(> .ad)"));
    CHECK(OZ::generatedShape("#cookie") && OZ::generatedShape(".a.b") && OZ::generatedShape("div.x:nth-of-type(2) > span:nth-of-type(1)"));
    CHECK(!OZ::generatedShape("a[href]") && !OZ::generatedShape("div, span") && !OZ::generatedShape("div >") && !OZ::generatedShape("a  b")
          && !OZ::generatedShape("div ~ p") && !OZ::generatedShape("a\"b"));

    // line parsing
    {
        auto l = OZ::parseLine("example.com##.banner");
        CHECK(l.hosts == std::vector<std::string>{ "example.com" } && l.selector == ".banner");
        l = OZ::parseLine("  A.com, b.org ##div > p\r");
        CHECK((l.hosts == std::vector<std::string>{ "a.com", "b.org" }) && l.selector == "div > p");
        CHECK(OZ::parseLine("##.generic").hosts.empty());
        CHECK(OZ::parseLine("! comment ##x").hosts.empty());
        CHECK(OZ::parseLine("||ads.example.com^").hosts.empty());
        CHECK(OZ::parseLine("example.com#@#.banner").hosts.empty());
        CHECK(OZ::parseLine("~example.com##.banner").hosts.empty());
        CHECK(OZ::parseLine("example.*##.banner").hosts.empty());
        CHECK(OZ::parseLine("example.com##+js(nobab)").hosts.empty());
        CHECK(OZ::parseLine("example.com##^script").hosts.empty());
        CHECK(OZ::parseLine("example.com##div:has-text(Ad)").hosts.empty());
        CHECK(OZ::parseLine("example.com##a{color:red}").hosts.empty());
        CHECK(OZ::parseLine("example.com#?#div:has(.x)").hosts.empty());
    }

    // store: parse, keep unknown lines, serialize
    {
        const std::string text = "! my list\r\n||ads.example^\r\nexample.com##.banner\r\na.com,example.com##.banner\r\n##.generic\r\n\r\n\r\n";
        OZ::Store st = OZ::parse(text);
        CHECK(st.lines.size() == 5);
        CHECK(OZ::serialize(st) == "! my list\n||ads.example^\nexample.com##.banner\na.com,example.com##.banner\n##.generic\n");
        const auto rs = OZ::rules(st);
        CHECK(rs.size() == 2 && rs[0].host == "example.com" && rs[1].host == "a.com");   // the repeat is dropped
        CHECK(OZ::rulesFor(st, "www.example.com").size() == 1 && OZ::rulesFor(st, "a.com").size() == 1 && OZ::rulesFor(st, "b.com").empty());
        const auto sh = OZ::sheets(st);
        CHECK(sh.size() == 2 && sh[0].first == "example.com" && sh[0].second == ".banner{display:none!important}\n");
        // remove: the multi-host line keeps its other host; unrelated lines stay
        CHECK(OZ::remove(st, "example.com", ".banner") == 2);
        CHECK(OZ::serialize(st) == "! my list\n||ads.example^\na.com##.banner\n##.generic\n");
        CHECK(OZ::remove(st, "example.com", ".banner") == 0);
    }
    {
        OZ::Store st;
        CHECK(OZ::add(st, "example.com", "#cookie") == OZ::Added::Ok);
        CHECK(st.lines.size() == 2 && st.lines[0] == OZ::kHeader && st.lines[1] == "example.com###cookie");
        CHECK(OZ::add(st, "example.com", "#cookie") == OZ::Added::Exists);
        CHECK(OZ::add(st, "example.com", "a{b}") == OZ::Added::Invalid);
        CHECK(OZ::add(st, "Bad", "#x") == OZ::Added::Invalid);
        CHECK(OZ::add(st, "example.com", ".x:nth-of-type(2)") == OZ::Added::Ok);
        const auto sh = OZ::sheets(st);
        CHECK(sh.size() == 1 && sh[0].second == "#cookie{display:none!important}\n.x:nth-of-type(2){display:none!important}\n");
        CHECK(OZ::remove(st, "example.com", "#cookie") == 1 && OZ::remove(st, "example.com", ".x:nth-of-type(2)") == 1);
        CHECK(st.lines.empty());   // only the header was left: the file becomes empty
        for (size_t i = 0; i < OZ::kMaxPerHost; ++i) CHECK(OZ::add(st, "h.com", "#e" + std::to_string(i)) == OZ::Added::Ok);
        CHECK(OZ::add(st, "h.com", "#more") == OZ::Added::HostFull);
        CHECK(OZ::add(st, "other.com", "#more") == OZ::Added::Ok);
    }
    {
        OZ::Store st;
        for (size_t i = 0; i < OZ::kMaxLines; ++i) st.lines.push_back("x" + std::to_string(i) + ".com##.a");
        CHECK(OZ::add(st, "new.com", ".a") == OZ::Added::FileFull);
        // read caps: lines and bytes
        std::string big;
        for (size_t i = 0; i < OZ::kMaxLines + 50; ++i) big += "h" + std::to_string(i) + ".com##.a\n";
        CHECK(OZ::parse(big).lines.size() == OZ::kMaxLines);
        std::string huge(OZ::kMaxFileBytes - 10, '!');
        huge += "\nexample.com##.cut-in-the-middle\n";
        const OZ::Store h = OZ::parse(huge);
        CHECK(h.lines.size() == 1 && OZ::rules(h).empty());   // the partial last line is dropped
    }

    // script
    {
        const std::string s = OZ::script(OZ::Op::Hide, 0, 0, "#a\"</script>");
        CHECK(s.rfind("(function (OP, X, Y, SEL) {", 0) == 0);
        CHECK(s.find(")(\"hide\",0.0,0.0,\"#a\\\"\\u003c/script\\u003e\")") != std::string::npos);
        CHECK(s.size() > std::string(OZ::kCore).size());
        const std::string m = OZ::script(OZ::Op::Move, 12.25, 300.0);
        CHECK(m.find(")(\"move\",12.2,300.0,\"\")") != std::string::npos || m.find(")(\"move\",12.3,300.0,\"\")") != std::string::npos);
        CHECK(OZ::number(std::numeric_limits<double>::quiet_NaN()) == "0.0");
        CHECK(OZ::number(1e9) == "0.0");
        const std::string core = OZ::kCore;
        CHECK(core.back() == '}');   // a whole function expression: never cut by the caller
    }

    // texts
    CHECK(OZ::barTitle("div.banner", 640, 120) == "Hide this element: div.banner  (640 x 120)");
    CHECK(OZ::barDetail(3, false) == "Matches 3 elements on this page");
    CHECK(OZ::barDetail(1, true) == "Only this element. Private tab: hidden on this page only, not saved");
    CHECK(OZ::askManyTitle(37) == "Hide 37 elements?");
    CHECK(OZ::hiddenNotice("example.com", false, OZ::Added::Ok) == "Hidden on example.com. Undo: hold Cross > Undo hide element");
    CHECK(OZ::hiddenNotice("example.com", true, OZ::Added::Invalid).find("private tab") != std::string::npos);
    CHECK(OZ::rowValue(0) == "None" && OZ::rowValue(4) == "4");
    CHECK(OZ::shortSel(std::string(100, 'a'), 10) == "aaaaaaa...");

    if (argc > 1) {
        std::ofstream f(argv[1], std::ios::binary);
        f << OZ::kCore;
        std::ofstream g(std::string(argv[1]) + ".call.js", std::ios::binary);   // node --check: the whole script as sent
        g << OZ::script(OZ::Op::Start, 10, 20, "#x") << ";\n";
    }
    std::printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
