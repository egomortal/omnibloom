// OMNI_PC_LINKS_V1 host test:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pc_links.cpp -o t && ./t
// (OmniPcLinks.h needs OmniSendLink.h from the tree, as in the build.)
#include "OmniPcLinks.h"
#include <cstdio>

static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)
namespace P = OmniPcLinks;

int main()
{
    // names: exactly what Setup writes (pclinks.file_name)
    CHECK(P::inboxName("links-20261116-123005-a1b2c3.txt"));
    for (const char* n : { "links-20261116-123005-A1B2C3.txt", "links-2026111-123005-a1b2c3.txt", "links-20261116-123005-a1b2c3.txt.omnibloom-new",
                           "../links-20261116-123005-a1b2c3.txt", "links-20261116-123005-a1b2c.txt", "other.txt", "", "links-20261116-123005-a1b2cg.txt" })
        CHECK(!P::inboxName(n));

    // the link check
    std::string u;
    CHECK(P::validUrl("https://example.com/a?b#c", u) && u == "https://example.com/a?b#c");
    CHECK(P::validUrl("  HTTPS://Example.com/X\r", u) && u == "https://Example.com/X");
    CHECK(P::validUrl("https://[2001:db8::1]:8443/", u));
    CHECK(P::validUrl("https://b\xc3\xbc" "cher.de/", u));
    const std::string base = "https://a.com/";
    CHECK(P::validUrl(base + std::string(2048 - base.size(), 'a'), u));
    CHECK(!P::validUrl(base + std::string(2049 - base.size(), 'a'), u));
    for (const char* bad : { "", "ftp://a.com", "javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "https://u:p@a.com/",
                             "https://u@a.com", "https://a b.com", "https://a.com/\x01", "https://a\\b.com", "https://", "https://a.com:0/",
                             "https://a.com:65536/", "https://a:1:2/", "https://a.com/\xe2\x80\xa8", "https://exa$mple.com/", "https://a.com/\xff" })
        CHECK(!P::validUrl(bad, u));

    // the file
    P::Parsed p = P::parse("omni-pc-links\t1\nhttps://a.com\r\n\nftp://x\nhttps://a.com\nhttps://b.org/x\n");
    CHECK(!p.badHeader && p.links.size() == 2 && p.links[0] == "https://a.com" && p.links[1] == "https://b.org/x" && p.rejected == 1);
    CHECK(P::parse("").badHeader && P::parse("").links.empty());
    CHECK(P::parse("https://a.com\n").badHeader && P::parse("https://a.com\n").links.empty());
    CHECK(P::parse("omni-pc-links\t2\nhttps://a.com\n").badHeader);
    std::string many = "omni-pc-links\t1\n";
    for (int i = 0; i < 25; ++i) many += "https://s" + std::to_string(i) + ".example.com/\n";
    p = P::parse(many);
    CHECK(p.links.size() == 20 && p.rejected == 5 && p.links[19] == "https://s19.example.com/");
    CHECK(P::parse("omni-pc-links\t1").links.empty() && !P::parse("omni-pc-links\t1").badHeader);   // no newline at the end

    // host / shown
    CHECK(P::host("https://WWW.Example.com:8443/x") == "www.example.com");
    CHECK(P::host("http://[::1]:9/") == "[::1]");
    CHECK(P::host("https://a.com?q") == "a.com");
    CHECK(P::host("nope").empty());
    CHECK(P::host("https://" + std::string(80, 'a') + ".com/").size() == 64);
    CHECK(P::shown(std::string(10, 'x')) == std::string(10, 'x'));
    const std::string longUrl = "https://a.com/" + std::string(300, 'x');
    CHECK(P::shown(longUrl).size() == 200 && P::shown(longUrl).substr(197) == "...");
    const std::string utf = "https://a.com/" + std::string(182, 'x') + "\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9";   // an 'é' at bytes 196-197
    CHECK(P::shown(utf) == utf.substr(0, 196) + "...");

    // the waiting list
    P::Queue q;
    std::vector<std::string> a;
    for (int i = 0; i < 18; ++i) a.push_back("https://q" + std::to_string(i) + ".com");
    CHECK(q.add(a) == 0 && q.items.size() == 18);
    CHECK(q.add({ "https://q0.com", "https://n1.com", "https://n2.com", "https://n3.com" }) == 1);   // repeat skipped, 1 over
    CHECK(q.items.size() == 20 && !q.room() && q.items.back() == "https://n2.com");

    // poll timing
    P::Poll poll;
    bool full = false;
    CHECK(!poll.due(1000, false, full));             // not on screen: never
    CHECK(poll.due(1000, true, full) && full);       // first look (and back on screen): full
    CHECK(!poll.due(3000, true, full));
    CHECK(poll.due(6000, true, full) && !full);      // 5 s later: a stat only
    CHECK(!poll.due(7000, false, full));             // left the screen
    CHECK(poll.due(7100, true, full) && full);       // back: at once, full
    CHECK(poll.due(12100, true, full) && !full);
    CHECK(poll.due(67100, true, full) && full);      // 60 s since the last full look
    P::Poll wrap; wrap.due(0xfffff000u, true, full);
    CHECK(wrap.due(0xfffff000u + 5000u, true, full) && !full);   // SDL ticks wrap

    // texts
    CHECK(P::askTitle("a.com") == "Link from your PC: a.com" && P::askTitle("") == "Link from your PC: a website");
    CHECK(P::fullNotice(1) == "1 link from your PC didn't fit: 20 are waiting");
    CHECK(P::blockedNotice("x.com").find("parental controls") != std::string::npos);

    std::printf(fails ? "%d FAILED\n" : "all passed\n", fails);
    return fails ? 1 : 0;
}
