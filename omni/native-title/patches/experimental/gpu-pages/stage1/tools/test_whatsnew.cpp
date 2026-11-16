// OMNI_WHATSNEW_V1: host tests for OmniWhatsNew.h.
// g++ -std=c++20 -Wall -Wextra -Werror -I. test_whatsnew.cpp -o t && ./t
#include "OmniWhatsNew.h"

#include <cstdio>
#include <string>

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

namespace W = OmniWhatsNew;

int main()
{
    // dataId: the generator's layout, compact JSON, bad values
    CHECK(W::dataId("{\n \"schema\": 1,\n \"id\": \"0123456789abcdef\",\n \"groups\": []}") == "0123456789abcdef");
    CHECK(W::dataId("{\"schema\":1,\"id\":\"deadbeef\"}") == "deadbeef");
    CHECK(W::dataId("{\"id\" :\r\n \"deadbeef00\"}") == "deadbeef00");
    CHECK(W::dataId("{\"id\":\"DEADBEEF\"}").empty());          // upper case: not ours
    CHECK(W::dataId("{\"id\":\"abc\"}").empty());               // too short
    CHECK(W::dataId("{\"id\":\"deadbeefdeadbeef").empty());     // cut off (head ends inside the value)
    CHECK(W::dataId("{\"id\":12345678}").empty());
    CHECK(W::dataId("{\"schema\":1}").empty());
    CHECK(W::dataId("").empty());
    CHECK(W::dataId("{\"id\":\"" + std::string(65, 'a') + "\"}").empty());
    CHECK(W::dataId("{\"id\":\"" + std::string(64, 'a') + "\"}") == std::string(64, 'a'));
    CHECK(W::dataId("{\"id\":\"de\\\"adbeef\"}").empty());

    // seenFrom
    CHECK(W::seenFrom("0.5.3+abcdef12\n") == "0.5.3+abcdef12");
    CHECK(W::seenFrom("  0.5.3 \r\nmore") == "0.5.3");
    CHECK(W::seenFrom("").empty());
    CHECK(W::seenFrom("\n0.5.3").empty());
    CHECK(W::seenFrom("0.5\x01.3").empty());
    CHECK(W::seenFrom(std::string(500, 'x')).size() == W::kSeenMax);

    // key / versionOf
    CHECK(W::key("0.5.3", "abcdef12") == "0.5.3+abcdef12");
    CHECK(W::key("0.5.3", "") == "0.5.3");
    CHECK(W::key("", "abcdef12").empty());
    CHECK(W::versionOf("0.5.3+abcdef12") == "0.5.3");
    CHECK(W::versionOf("0.5.3") == "0.5.3");
    CHECK(W::versionOf("").empty());

    // decide
    CHECK(W::decide("", "0.5.3+aa", false) == W::kRecord);     // fresh install
    CHECK(W::decide("", "0.5.3+aa", true) == W::kShow);        // updated from a build without this feature
    CHECK(W::decide("0.5.3+aa", "0.5.3+aa", true) == W::kNone);
    CHECK(W::decide("0.5.3+aa", "0.5.3+bb", true) == W::kShow); // new changelog entries on the same version
    CHECK(W::decide("0.5.2", "0.5.3+aa", false) == W::kShow);   // a saved key always counts as earlier data
    CHECK(W::decide("0.5.3", "", true) == W::kNone);            // no version known: never shown

    // actions
    CHECK(W::action("controls") == W::aControls);
    CHECK(W::action("site-settings") == W::aSiteSettings);
    CHECK(W::action("screenshots") == W::aScreenshots);
    CHECK(W::action("") == W::aNone);
    CHECK(W::action("Controls") == W::aNone);
    CHECK(W::action("javascript:alert(1)") == W::aNone);
    CHECK(W::action(std::string(40, 'a')) == W::aNone);
    for (int a = W::aNone + 1; a < W::aActionCount; ++a) CHECK(W::action(W::actionName(a)) == a);
    CHECK(std::string(W::actionName(0)).empty() && std::string(W::actionName(W::aActionCount)).empty());

    // infoJson
    const std::string j = W::infoJson("0.5.3", "0.5.2+ab", "fr", true);
    CHECK(j.find("\"version\":\"0.5.3\"") != std::string::npos);
    CHECK(j.find("\"previous\":\"0.5.2\"") != std::string::npos);
    CHECK(j.find("\"lang\":\"fr\"") != std::string::npos);
    CHECK(j.find("\"afterUpdate\":true") != std::string::npos);
    CHECK(j.find("\"actions\":[\"controls\",\"options\",") != std::string::npos);
    CHECK(j.back() == '}' && j.find("\"screenshots\"]}") != std::string::npos);
    CHECK(W::infoJson("1", "", "", false).find("\"lang\":\"en\",\"afterUpdate\":false") != std::string::npos);
    CHECK(W::jsonQuote("a\"b\\c\n") == "\"a\\\"b\\\\c\\u000a\"");
    CHECK(W::rowValue("0.5.3") == "Omni 0.5.3" && W::rowValue("").empty());

    std::printf(failures ? "%d FAILED\n" : "all whatsnew tests passed\n", failures);
    return failures ? 1 : 0;
}
