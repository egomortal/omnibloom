// OMNI_SITE_LIST_V1: tests of the pure part of "Sites with custom settings" (engine/entry/OmniSiteList.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_list.cpp -o t && ./t
// With OmniSettingsSearch.h next to it (OMNI_SETTINGS_SEARCH_V1), it also checks that the new Browser settings row
// is found by the settings search.
#include "OmniSiteList.h"
#if __has_include("OmniSettingsSearch.h")
#include "OmniSettingsSearch.h"
#define HAVE_SSR 1
#endif
// OMNI_SITE_LIST_V1_R4: with the three stores' pure headers in the tree, their own key functions are checked to group
// one host into one row (site volume's key is OmniMediaControls::site: IPv6 kept in brackets).
#if __has_include("OmniSiteMute.h") && __has_include("OmniMediaControls.h") && __has_include("OmniAutoFullscreen.h")
#include "OmniSiteMute.h"
#include "OmniMediaControls.h"
#include "OmniAutoFullscreen.h"
#define HAVE_R4_KEYS 1
#endif
#include <cstdio>

namespace SL = OmniSiteList;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)
#define EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++failures; std::printf("FAIL line %d: \"%s\" != \"%s\"\n", __LINE__, x_.c_str(), y_.c_str()); } } while (0)

static SL::Item item(SL::Kind k, const std::string& key, int v = 1, const std::string& name = {}, const std::string& owner = {})
{
    SL::Item it; it.kind = k; it.key = key; it.value = v; it.name = name; it.owner = owner; return it;
}

int main()
{
    // --- siteHost: grouping only ---
    EQ(SL::siteHost("www.example.com"), "example.com");
    EQ(SL::siteHost("WWW.Example.COM."), "example.com");
    EQ(SL::siteHost(" example.com\r\n"), "example.com");
    EQ(SL::siteHost("m.example.com"), "m.example.com");
    EQ(SL::siteHost("www.com"), "www.com");                 // no dot after "www.": a host of its own
    EQ(SL::siteHost("wwwexample.com"), "wwwexample.com");
    EQ(SL::siteHost("[::1]"), "::1");
    EQ(SL::siteHost("::1"), "::1");
    EQ(SL::siteHost("192.168.0.10"), "192.168.0.10");
    EQ(SL::siteHost(""), "");

    // --- merge: www. and bare in one row, every store's key kept ---
    std::vector<SL::Item> items = {
        item(SL::kPopupAllow, "example.com"),
        item(SL::kZoom, "example.com", 125),
        item(SL::kAutoplay, "example.com", 3),
        item(SL::kDark, "www.example.com", 1),        // site-dark.txt written by an older build with www.
        item(SL::kUblock, "news.example.org"),
        item(SL::kHttp, "192.168.0.10"),
        item(SL::kMobile, "m.example.net"),
        item(SL::kAddon, "example.org", 0, "Dark Reader", "darkreader"),
        item(SL::kTweaks, "example.org", 2),
        item(SL::kStorage, "example.org", 2),
        item(SL::kPopups, "example.org", 1),
        item(SL::kZoom, "", 150),                      // no host: dropped
    };
    const auto sites = SL::merge(items);
    CHECK(sites.size() == 5);
    EQ(sites[0].host, "192.168.0.10");
    EQ(sites[1].host, "example.com");
    EQ(sites[2].host, "example.org");
    EQ(sites[3].host, "m.example.net");
    EQ(sites[4].host, "news.example.org");
    CHECK(sites[1].items.size() == 4);
    CHECK(sites[1].items[0].kind == SL::kZoom);        // Kind order
    CHECK(sites[1].items[1].kind == SL::kDark);
    EQ(sites[1].items[1].key, "www.example.com");      // the store's own key, unchanged (its reset gets it as is)
    CHECK(sites[1].items[2].kind == SL::kAutoplay);
    CHECK(sites[1].items[3].kind == SL::kPopupAllow);
    CHECK(SL::find(sites, "example.com") == &sites[1]);
    CHECK(SL::find(sites, "www.example.com") == nullptr);

    // --- summary ---
    EQ(SL::summary(sites[1]), "Zoom 125% \xc2\xb7 Always dark \xc2\xb7 Autoplay blocked \xc2\xb7 Pop-ups allowed");
    EQ(SL::summary(sites[2]), "Pop-ups allowed \xc2\xb7 Cookie access (2) \xc2\xb7 2 page tweaks \xc2\xb7 Dark Reader off");
    EQ(SL::summary(sites[0]), "HTTP allowed");
    EQ(SL::summary(sites[3]), "Mobile site");
    EQ(SL::summary(sites[4]), "uBlock off");
    CHECK(SL::parts(sites[1]).size() == 4);
    EQ(SL::countText(1), "1 setting");
    EQ(SL::countText(4), "4 settings");
    // both pop-up stores allow: said once
    {
        const auto s = SL::merge({ item(SL::kPopups, "example.com", 1), item(SL::kPopupAllow, "www.example.com") });
        CHECK(s.size() == 1 && s[0].items.size() == 2);
        EQ(SL::summary(s[0]), "Pop-ups allowed");
    }
    // Block in Site permissions wins over the allow list
    {
        const auto s = SL::merge({ item(SL::kPopupAllow, "example.com"), item(SL::kPopups, "example.com", 2) });
        EQ(SL::summary(s[0]), "Pop-ups blocked");
    }
    // texts of every kind
    EQ(SL::itemText(item(SL::kDark, "example.com", 0)), "Never dark");
    EQ(SL::itemText(item(SL::kAutoplay, "example.com", 1)), "Autoplay allowed");
    EQ(SL::itemText(item(SL::kAutoplay, "example.com", 2)), "Autoplay without sound");
    EQ(SL::itemText(item(SL::kTweaks, "example.com", 1)), "1 page tweak");
    EQ(SL::itemText(item(SL::kAddon, "example.com", 1, "", "my-addon")), "my-addon on");
    EQ(SL::itemText(item(SL::kZoom, "example.com", 50)), "Zoom 50%");
    EQ(SL::itemText(item(SL::kReader, "example.com")), "Reader view always");   // OMNI_SITE_LIST_V1_R2
    EQ(SL::itemText(item(SL::kGame, "www.example.com")), "Game mode");            // OMNI_SITE_LIST_V1_R3
    CHECK(SL::merge({ item(SL::kGame, "www.example.com"), item(SL::kReader, "example.com") })[0].items[1].kind == SL::kGame);
    {
        const auto s = SL::merge({ item(SL::kUblock, "example.com"), item(SL::kReader, "www.example.com"), item(SL::kZoom, "example.com", 110) });
        CHECK(s.size() == 1);
        EQ(SL::summary(s[0]), "Zoom 110% · Reader view always · uBlock off");   // after page tweaks, before uBlock
    }

    // --- r4: always mute, site volume, video fullscreen (OMNI_SITE_LIST_V1_R4) ---
    EQ(SL::itemText(item(SL::kMute, "example.com")), "Always muted");
    EQ(SL::itemText(item(SL::kVolume, "example.com", 30)), "Volume 30%");
    EQ(SL::itemText(item(SL::kAutoFs, "example.com")), "Video fullscreen");
    CHECK(SL::percentOf("30%") == 30);
    CHECK(SL::percentOf("0%") == 0);
    CHECK(SL::percentOf("100%") == 100);
    CHECK(SL::percentOf("-") == -1);              // omniSvoSavedValue: nothing saved
    CHECK(SL::percentOf("") == -1);
    CHECK(SL::percentOf("%") == -1);
    CHECK(SL::percentOf("30") == -1);
    CHECK(SL::percentOf("3a%") == -1);
    CHECK(SL::percentOf("-5%") == -1);
    CHECK(SL::percentOf("99999%") == -1);
    {
        // one host from five stores: volume's key keeps IPv6 brackets, mute's / fullscreen's do not, dark's has www.
        const auto s = SL::merge({ item(SL::kAutoFs, "example.com"), item(SL::kVolume, "example.com", 30),
                                   item(SL::kMute, "example.com"), item(SL::kDark, "www.example.com", 1),
                                   item(SL::kZoom, "example.com", 110), item(SL::kUblock, "example.com"),
                                   item(SL::kVolume, "[::1]", 55), item(SL::kMute, "::1"), item(SL::kAutoFs, "::1") });
        CHECK(s.size() == 2);
        EQ(s[0].host, "::1");
        CHECK(s[0].items.size() == 3);
        EQ(s[0].items[1].key, "[::1]");            // reset gets volume's own key
        EQ(SL::summary(s[0]), "Always muted \xc2\xb7 Volume 55% \xc2\xb7 Video fullscreen");
        EQ(s[1].host, "example.com");
        // after autoplay (sound settings together), before HTTPS / pop-ups / tweaks / uBlock
        EQ(SL::summary(s[1]), "Zoom 110% \xc2\xb7 Always dark \xc2\xb7 Always muted \xc2\xb7 Volume 30% \xc2\xb7 Video fullscreen \xc2\xb7 uBlock off");
        EQ(SL::askBody(s[0], {}, {}), "Back to the defaults: Always muted, Volume 55%, Video fullscreen. Cookies and site data are kept.");
        CHECK(SL::merge({ item(SL::kAutoplay, "a.com", 3), item(SL::kMute, "a.com") })[0].items[1].kind == SL::kMute);
    }
#ifdef HAVE_R4_KEYS
    {
        namespace MC = OmniMediaControls;
        for (const char* url : { "https://WWW.Example.com:8443/watch?v=1", "http://user@example.com/", "https://example.com",
                                 "https://m.example.com/x", "https://[::1]:8080/", "https://[2001:db8::1]/a", "https://192.168.0.10/" }) {
            const std::string vk = MC::site(url), mk = OmniSiteMute::hostKey(url), fk = OmniAutoFullscreen::hostKey(url);
            const auto s = SL::merge({ item(SL::kVolume, vk, 40), item(SL::kMute, mk), item(SL::kAutoFs, fk) });
            ++checks;
            if (s.size() != 1 || s[0].items.size() != 3) {
                ++failures;
                std::printf("FAIL: %s not one row (volume \"%s\", mute \"%s\", fullscreen \"%s\")\n", url, vk.c_str(), mk.c_str(), fk.c_str());
            }
        }
        // the detail panel's URL for a listed host gives volume's own key back (brackets for IPv6), so its row reads it
        EQ(MC::site("https://" + std::string("[::1]") + "/"), "[::1]");
        EQ(MC::site("https://example.com/"), "example.com");
        EQ(OmniSiteMute::hostKey("https://example.com/"), "example.com");
        EQ(OmniAutoFullscreen::hostKey("https://example.com/"), "example.com");
        std::printf("r4 keys: checked against the tree's OmniMediaControls.h / OmniSiteMute.h / OmniAutoFullscreen.h\n");
    }
#endif

    // --- the filter ---
    EQ(SL::cleanQuery("  https://WWW.Example.com/path?q=1#x "), "example.com");
    EQ(SL::cleanQuery("example.com:8443"), "example.com");
    EQ(SL::cleanQuery("user@example.com"), "example.com");
    EQ(SL::cleanQuery("[::1]:8080"), "::1");
    EQ(SL::cleanQuery("www."), "www");           // nothing after it: kept (minus the trailing dot)
    EQ(SL::cleanQuery("EXAMPLE"), "example");
    EQ(SL::cleanQuery(""), "");
    {
        auto f = SL::filter(sites, "");
        CHECK(f.size() == 5);
        f = SL::filter(sites, "example");
        CHECK(f.size() == 4 && f[0] == 1 && f[1] == 2 && f[2] == 3 && f[3] == 4);
        f = SL::filter(sites, "www.example.org");
        CHECK(f.size() == 2 && f[0] == 2 && f[1] == 4);   // example.org and news.example.org
        f = SL::filter(sites, "https://example.com/watch");
        CHECK(f.size() == 1 && f[0] == 1);
        f = SL::filter(sites, "192.168");
        CHECK(f.size() == 1 && f[0] == 0);
        f = SL::filter(sites, "nothing-here");
        CHECK(f.empty());
    }

    // --- panel texts ---
    EQ(SL::listSubtitle(0, 0, ""), "No site has settings of its own");
    EQ(SL::listSubtitle(5, 5, ""), "5 sites with settings of their own");
    EQ(SL::listSubtitle(1, 1, ""), "1 site with settings of their own");
    EQ(SL::listSubtitle(5, 2, "example"), "2 of 5 sites match \"example\"");
    EQ(SL::searchValue(""), "Type part of an address");
    EQ(SL::searchValue("exa"), "\"exa\"");
    EQ(SL::emptyLabel(true), "No sites match");
    EQ(SL::detailSubtitle(nullptr), "Nothing saved: this site uses the defaults");
    EQ(SL::detailSubtitle(&sites[4]), "uBlock off");

    // --- reset texts ---
    {
        const std::vector<std::string> ub = { "example.com", "news.example.com", "other.org", "ample.com", "example.com" };
        const auto par = SL::coveringParents(ub, "news.example.com");
        CHECK(par.size() == 1 && par[0] == "example.com");   // itself, look-alikes ("ample.com") and duplicates are not parents
        CHECK(SL::coveringParents(ub, "example.com").empty());
        CHECK(SL::coveringParents(ub, "").empty());
        CHECK(SL::coveringParents({ "example.com", "a.example.com" }, "b.a.example.com").size() == 2);
        EQ(SL::joinList({ "a.com" }), "a.com");
        EQ(SL::joinList({ "a.com", "b.com" }), "a.com and b.com");
        EQ(SL::joinList({ "a.com", "b.com", "c.com" }), "a.com, b.com and c.com");
    }
    EQ(SL::askTitle("example.com"), "Reset settings for example.com?");
    EQ(SL::askBody(sites[1], {}, {}), "Back to the defaults: Zoom 125%, Always dark, Autoplay blocked, Pop-ups allowed. Cookies and site data are kept.");
    EQ(SL::askBody(sites[4], { "example.org" }, {}),
       "Back to the defaults: uBlock off. Cookies and site data are kept. uBlock is turned back on for example.org too (it covers this site).");
    EQ(SL::askBody(sites[1], {}, { "com.example" }).substr(SL::askBody(sites[1], {}, {}).size()),
       " Pop-ups from com.example are no longer always allowed either (it covers this site).");
    EQ(SL::resetNotice("example.com", false), "Settings reset for example.com");
    EQ(SL::resetNotice("example.com", true), "Settings reset for example.com, except uBlock (its list couldn't be saved)");

#ifdef HAVE_SSR
    // --- the Browser settings row is found by Search settings (OMNI_SETTINGS_SEARCH_V1 filters every row) ---
    {
        namespace SS = OmniSettingsSearch;
        std::vector<SS::Entry> list = {
            { 1, SS::sectionOf("Search engine"), "Search engine", "Google" },
            { 855, SS::sectionOf("Sites with custom settings"), "Sites with custom settings", "" },
            { 902, SS::sectionOf("Site permissions"), "Site permissions", "" },
            { 3, SS::sectionOf("Default page zoom"), "Default page zoom", "100%" },
        };
        for (const char* q : { "sites", "custom", "site settings", "custom settings", "Sites with" }) {
            std::vector<int> shown;
            const auto pick = SS::view(list, q, shown);
            bool found = false;
            for (size_t i : pick) found = found || list[i].id == 855;
            ++checks;
            if (!found) { ++failures; std::printf("FAIL: settings search \"%s\" doesn't find the row\n", q); }
        }
        std::printf("settings search: the row's section is \"%s\"\n", SS::sectionOf("Sites with custom settings").c_str());
    }
#endif

    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
