// OMNI_AUTOPLAY_V1: host tests for engine/entry/OmniAutoplay.h (written by apply_autoplay.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_autoplay.cpp -o t && ./t
#include "OmniAutoplay.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniAutoplay;

int main()
{
    // host keys
    CHECK(siteKey("https://www.Example.COM/path?q=1") == "example.com");
    CHECK(siteKey("http://user:pw@News.example.org:8080/a") == "news.example.org");
    CHECK(siteKey("https://example.com.") == "example.com");
    CHECK(siteKey("https://[::1]:8443/x") == "[::1]");
    CHECK(siteKey("http://127.0.0.1:8080/fs/x") == "127.0.0.1");
    CHECK(siteKey("about:blank").empty());
    CHECK(siteKey("data:text/html,hi").empty());
    CHECK(siteKey("omni://pages/start").empty());
    CHECK(siteKey("https:///nohost").empty());
    CHECK(siteKey("https://bad host/").empty());
    CHECK(siteKey("https://www.") == "www");     // "www." alone: trailing dot dropped, nothing stripped

    // defaults: Allow everywhere, no policy at all (today's behaviour)
    Store s; std::map<std::string, Mode> sess;
    Decision d = decide(s, sess, "https://news.example.com/");
    CHECK(d.mode == kAllow && d.source == kGlobal && !needsPolicy(d));
    CHECK(!needsPolicy(decide(s, sess, "https://www.youtube.com/watch?v=x")));
    CHECK(decide(s, sess, "about:blank").source == kNotWeb && !needsPolicy(decide(s, sess, "about:blank")));

    // global Block sound: policy everywhere except the video sites and Omni's own apps
    s.global = kNoSound;
    d = decide(s, sess, "https://news.example.com/");
    CHECK(d.mode == kNoSound && d.source == kGlobal && needsPolicy(d));
    d = decide(s, sess, "https://m.youtube.com/watch?v=x");
    CHECK(d.mode == kAllow && d.source == kBuiltIn && needsPolicy(d));
    CHECK(decide(s, sess, "https://www.twitch.tv/x").source == kBuiltIn);
    CHECK(decide(s, sess, "http://127.0.0.1:8080/").source == kBuiltIn);
    CHECK(decide(s, sess, "https://notyoutube.com/").source == kGlobal);
    CHECK(decide(s, sess, "https://youtube.com.evil.net/").source == kGlobal);

    // site rules cover subdomains, most specific wins, and beat the built-in list
    CHECK(setSite(s.sites, "example.com", kBlock));
    CHECK(setSite(s.sites, "video.example.com", kAllow));
    CHECK(setSite(s.sites, "youtube.com", kNoSound));
    d = decide(s, sess, "https://news.example.com/");
    CHECK(d.mode == kBlock && d.source == kSite && d.rule == "example.com");
    CHECK(decide(s, sess, "https://a.video.example.com/").mode == kAllow);
    CHECK(decide(s, sess, "https://www.youtube.com/").mode == kNoSound);
    CHECK(decide(s, sess, "https://example.org/").mode == kNoSound);
    // a rule never matches through a bare TLD
    CHECK(setSite(s.sites, "com", kAllow));
    CHECK(decide(s, sess, "https://other.com/").source == kGlobal);
    CHECK(setSite(s.sites, "com", kDefault) && !s.sites.count("com"));

    // private session rules win; a session Default means "global" even over a saved rule
    sess["example.com"] = kAllow;
    CHECK(decide(s, sess, "https://news.example.com/").mode == kAllow);
    sess["example.com"] = kDefault;
    d = decide(s, sess, "https://example.com/");
    CHECK(d.mode == kNoSound && d.source == kGlobal);
    CHECK(siteValue(s, sess, "example.com") == "Default (Block sound)");
    sess.clear();
    CHECK(siteValue(s, sess, "example.com") == "Block all");
    CHECK(siteValue(s, sess, "news.example.com") == "Block all (from example.com)");
    CHECK(siteValue(s, sess, "twitch.tv") == "Allow (video site)");
    CHECK(siteValue(s, sess, "example.org") == "Default (Block sound)");

    // file round trip, tolerant parse
    const std::string text = serialize(s);
    CHECK(text.rfind("omni-autoplay\t1\nglobal\tnosound\n", 0) == 0);
    Store back = parse(text);
    CHECK(back.global == kNoSound && back.sites == s.sites);
    Store junk = parse("omni-autoplay\t1\r\nglobal\tbogus\r\nsite\tWWW.Foo.com\tblock\r\nsite\tbad host\tallow\nsite\tx.org\tdefault\nnoise\n"
                       "site\tonly-two-fields\nglobal\tblock\n");
    CHECK(junk.global == kBlock && junk.sites.size() == 1 && junk.sites.at("foo.com") == kBlock);
    CHECK(parse("").global == kAllow && parse("").sites.empty());

    // caps
    Store big;
    for (size_t i = 0; i < kMaxSites; ++i) CHECK(setSite(big.sites, "s" + std::to_string(i) + ".com", kBlock));
    CHECK(!setSite(big.sites, "one-more.com", kBlock));
    CHECK(setSite(big.sites, "s1.com", kAllow));          // changing an existing one still works
    CHECK(setSite(big.sites, "s2.com", kDefault) && big.sites.size() == kMaxSites - 1);
    std::string many = "global\tallow\n";
    for (size_t i = 0; i < kMaxSites + 50; ++i) many += "site\tp" + std::to_string(i) + ".net\tblock\n";
    CHECK(parse(many).sites.size() == kMaxSites);

    // cycling
    CHECK(cycleGlobal(kAllow, 1) == kNoSound && cycleGlobal(kNoSound, 1) == kBlock && cycleGlobal(kBlock, 1) == kAllow);
    CHECK(cycleGlobal(kAllow, -1) == kBlock && cycleGlobal(kBlock, -1) == kNoSound);
    CHECK(cycleSite(kDefault, 1) == kAllow && cycleSite(kBlock, 1) == kDefault && cycleSite(kDefault, -1) == kBlock);

    // texts
    CHECK(std::string(name(kNoSound)) == "Block sound");
    CHECK(globalNotice(kBlock) == "Autoplay: Block all. Applies to pages you open from now on");
    CHECK(siteNotice("foo.com", kAllow, true, false) == "Autoplay on foo.com: Allow (this session only). Reloading...");
    CHECK(siteNotice("foo.com", kDefault, false, false) == "Autoplay on foo.com: default. Reloading...");
    CHECK(siteNotice("foo.com", kAllow, false, true).find("500") != std::string::npos);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
