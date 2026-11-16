// OMNI_VIDEO_ENHANCE_V1: host test of the pure part (engine/entry/OmniVideoEnhance.h).
//   g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_video_enhance_shell.cpp -o t && ./t
#include "OmniVideoEnhance.h"
#include <cstring>
#include <cstdio>

static int fails = 0, n = 0;
#define CHECK(c) do { ++n; if (!(c)) { ++fails; printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main()
{
    namespace V = OmniVideoEnhance;
    CHECK(V::parse(nullptr) == 0); CHECK(V::parse("") == 0); CHECK(V::parse("junk") == 0); CHECK(V::parse("-1") == 0);
    CHECK(V::parse("1\n") == 1); CHECK(V::parse("  2") == 2); CHECK(V::parse("7") == 2); CHECK(V::parse("0") == 0);
    CHECK(V::step(0, 1) == 1); CHECK(V::step(1, 1) == 2); CHECK(V::step(2, 1) == 0);
    CHECK(V::step(0, -1) == 2); CHECK(V::step(2, -1) == 1); CHECK(V::step(9, 1) == 0);
    CHECK(!strcmp(V::settingValue(0), "Off")); CHECK(!strcmp(V::settingValue(1), "Smooth")); CHECK(!strcmp(V::settingValue(2), "Sharp"));
    CHECK(!strcmp(V::settingValue(-3), "Off")); CHECK(!strcmp(V::settingValue(5), "Sharp"));
    for (int l = 0; l < 3; ++l) { CHECK(strlen(V::settingDetail(l)) > 0 && strlen(V::settingDetail(l)) < 80); CHECK(strlen(V::changedNotice(l)) < 80); }
    CHECK(V::kRowId == 8463);
    CHECK(omni_gpu_video_set_enhance == nullptr);   // weak and not linked here: the shell must check it
    printf("VIDEO ENHANCE SHELL TESTS: %d checks, %d failed\n", n, fails);
    return fails ? 1 : 0;
}
