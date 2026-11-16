// OMNI_SITE_VOLUME_V1: host tests of the pure part (engine/entry/OmniSiteVolume.h, written by apply_site_volume.py; it
// includes OmniTabVolume.h from apply_tab_volume.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_volume.cpp -o t && ./t
#include "OmniSiteVolume.h"
#include <cstdio>
#include <string>

namespace V = OmniSiteVolume;
namespace TV = OmniTabVolume;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main()
{
    // --- 2 s settle ---------------------------------------------------------------------------------------------------
    V::Settle st;
    CHECK(st.empty());
    st.note(1, "", 30, false, 0);                         // no site: nothing
    CHECK(st.empty());
    st.note(1, "music.com", 30, false, 1000);
    CHECK(st.size() == 1 && st.take(2999).empty());
    st.note(1, "music.com", 20, false, 2500);              // a newer change restarts the 2 s
    CHECK(st.take(3000).empty() && st.take(4499).empty());
    auto got = st.take(4500);
    CHECK(got.size() == 1 && got[0].site == "music.com" && got[0].pct == 20 && !got[0].privateTab);
    CHECK(st.empty() && st.take(9000).empty());
    st.note(1, "a.com", 33, false, 0);                     // clamped to a step
    st.note(1, "b.com", 70, false, 100);                   // same tab, another site: both kept
    st.note(2, "a.com", 50, true, 100);                    // private tab
    CHECK(st.size() == 3);
    got = st.take(2000);
    CHECK(got.size() == 1 && got[0].site == "a.com" && got[0].pct == 30);
    st.cancelSite("a.com", false);                         // the normal one is gone already; private stays
    CHECK(st.size() == 2);
    st.cancelSite("a.com", true);
    CHECK(st.size() == 1);
    got = st.take(2100);
    CHECK(got.size() == 1 && got[0].site == "b.com" && got[0].pct == 70);
    st.note(3, "w.com", 40, false, 0xFFFFFC00u);           // SDL_GetTicks wrap: due 0x3D0
    CHECK(st.take(0xFFFFFFF0u).empty() && st.take(0x000003CFu).empty());
    CHECK(st.take(0x000003D0u).size() == 1);

    // --- hand change --------------------------------------------------------------------------------------------------
    CHECK(V::handChange(100, 90) && V::handChange(0, 10));
    CHECK(!V::handChange(70, 70) && !V::handChange(100, 104));

    // --- remember / forget ----------------------------------------------------------------------------------------------
    TV::Sites s;
    CHECK(V::remember(s, "music.com", 30) == V::Saved::kChanged);
    int pct = 0;
    CHECK(s.get("music.com", pct) && pct == 30);
    CHECK(V::remember(s, "music.com", 30) == V::Saved::kSame);
    CHECK(V::remember(s, "music.com", 54) == V::Saved::kChanged && s.get("music.com", pct) && pct == 50);
    CHECK(V::remember(s, "music.com", 100) == V::Saved::kChanged && !s.has("music.com"));   // 100 % = forget
    CHECK(V::remember(s, "music.com", 100) == V::Saved::kSame);
    CHECK(V::remember(s, "zero.com", 0) == V::Saved::kChanged && s.get("zero.com", pct) && pct == 0);
    CHECK(V::remember(s, "bad site", 30) == V::Saved::kFull && !s.has("bad site"));   // not storable
    TV::Sites full;
    for (size_t i = 0; i < TV::kMaxSites; ++i) full.set("s" + std::to_string(i) + ".com", 50);
    CHECK(V::remember(full, "new.com", 30) == V::Saved::kFull && !full.has("new.com"));
    CHECK(V::remember(full, "s1.com", 30) == V::Saved::kChanged);                         // existing: updated
    CHECK(V::remember(full, "s2.com", 100) == V::Saved::kChanged && full.size() == TV::kMaxSites - 1);
    // the file round trip stays tab volume's
    TV::Sites rt = TV::parse(TV::serialize(s));
    CHECK(rt.get("zero.com", pct) && pct == 0 && rt.size() == s.size());

    // --- commit -------------------------------------------------------------------------------------------------------
    CHECK(!V::dropOwn(TV::kUnset, "", "music.com", true));            // no own value: nothing to drop
    CHECK(!V::dropOwn(40, "music.com", "music.com", true));           // set by hand here: kept (reload / same site)
    CHECK(V::dropOwn(40, "news.com", "music.com", true));             // set on another site: the remembered one wins
    CHECK(V::dropOwn(40, "", "music.com", true));                     // own value not from a hand change (forget toggle)
    CHECK(!V::dropOwn(40, "news.com", "other.com", false));           // nothing remembered: tab keeps its value
    CHECK(!V::dropOwn(40, "news.com", "", false));                    // new-tab / omni:// page

    // --- texts --------------------------------------------------------------------------------------------------------
    CHECK(V::rowValue(false, false, 30) == "-");
    CHECK(V::rowValue(true, true, 30) == "30%");
    CHECK(V::rowValue(true, false, 30) == "100%");
    CHECK(V::rowDetail(true, true, false, false) == "Cross: Reset to 100%");
    CHECK(V::rowDetail(true, true, true, false).find("private") != std::string::npos);
    CHECK(V::rowDetail(true, true, false, true).find("Always mute") != std::string::npos);
    CHECK(V::rowDetail(true, false, false, false).find("Now playing") != std::string::npos);
    CHECK(V::rowDetail(false, false, false, false) == "Only for web sites");
    CHECK(V::resetNotice("music.com", false) == "Volume for music.com reset to 100%");
    CHECK(V::resetNotice("music.com", true) == "Volume for music.com reset to 100% (private tabs)");
    CHECK(V::kSiteRowId == 778 && V::kSettleMs == 2000);

    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
