// OMNI_HARD_RELOAD_V1 pure tests: g++ -std=c++20 -Wall -Wextra -Werror -I. test_hard_reload.cpp -o t && ./t
#include "OmniHardReload.h"
#include <cstdio>
#include <cstring>

static int fails = 0;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); ++fails; } } while (0)

int main()
{
    namespace H = OmniHardReload;
    CHECK(H::offered("https://www.example.com/", false, false, false));
    CHECK(H::offered("http://example.com", false, false, false));
    CHECK(H::offered("HTTPS://Example.com/a?b#c", false, false, false));
    CHECK(H::offered("http://192.168.0.2:8080/x", false, false, false));
    CHECK(H::offered("https://[::1]/", false, false, false));
    CHECK(!H::offered("omni://pages/settings", false, false, false));
    CHECK(!H::offered("omni://home", false, false, false));
    CHECK(!H::offered("https://www.example.com/", true, false, false));    // omni://pages tab flag
    CHECK(!H::offered("https://www.example.com/", false, true, false));    // new-tab page
    CHECK(!H::offered("https://www.example.com/", false, false, true));    // crashed
    CHECK(!H::offered("about:blank", false, false, false));
    CHECK(!H::offered("file:///data/omni/x.html", false, false, false));
    CHECK(!H::offered("data:text/html,hi", false, false, false));
    CHECK(!H::offered("blob:https://example.com/1", false, false, false));
    CHECK(!H::offered("javascript:alert(1)", false, false, false));
    CHECK(!H::offered("", false, false, false));
    CHECK(!H::offered("https://", false, false, false));
    CHECK(!H::offered("http:///path", false, false, false));
    CHECK(!H::offered("https:/example.com", false, false, false));
    CHECK(!H::offered("httpx://example.com", false, false, false));
    CHECK(H::kContextRowId != H::kQuickRowId && H::kQuickRowId >= 900);
    CHECK(std::strcmp(H::kNotice, "Reloaded without cache") == 0);
    CHECK(std::strcmp(H::kLabel, "Reload without cache") == 0);
    std::printf(fails ? "%d FAILED\n" : "all hard-reload tests passed\n", fails);
    return fails ? 1 : 0;
}
