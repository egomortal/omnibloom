// OMNI_SITE_ZOOM_V1 host test for engine/entry/OmniSiteZoom.h (written by apply_site_zoom.py).
// g++ -std=c++17 -Wall -Wextra -Werror -I <tree>/engine/entry test_site_zoom.cpp -o t && ./t
#include "OmniSiteZoom.h"
#include <cstdio>
#include <string>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniSiteZoom;

int main()
{
    // steps
    CHECK(step(100, 1) == 110); CHECK(step(100, -1) == 90);
    CHECK(step(200, 1) == 200); CHECK(step(50, -1) == 50);
    CHECK(step(105, 1) == 110); CHECK(step(105, -1) == 100);   // between steps
    CHECK(step(250, -1) == 200); CHECK(step(250, 1) == 200);   // a 250 % default setting
    CHECK(step(30, 1) == 50); CHECK(step(67, 1) == 75); CHECK(step(67, -1) == 50);
    CHECK(step(150, 0) == 150); CHECK(step(999, 0) == 200);
    int p = 50, n = 0; while (p < 200 && n < 50) { p = step(p, 1); ++n; }
    CHECK(n == kStepCount - 1);
    CHECK(toPercent(1.1) == 110); CHECK(toPercent(0.67) == 67); CHECK(toPercent(0) == 100); CHECK(toPercent(2.5) == 250);

    // host keys
    CHECK(hostKey("www.Example.COM") == "example.com");
    CHECK(hostKey("example.com.") == "example.com");
    CHECK(hostKey("www.com") == "www.com");            // nothing after "www." would remain a domain
    CHECK(hostKey("  m.youtube.com\r\n") == "m.youtube.com");
    CHECK(hostKey("xn--bcher-kva.de") == "xn--bcher-kva.de");
    CHECK(hostKey("").empty()); CHECK(hostKey("a b.com").empty()); CHECK(hostKey("a/b").empty());
    CHECK(hostKey("evil\tx").empty()); CHECK(hostKey(".com").empty()); CHECK(hostKey(std::string(254, 'a')).empty());
    CHECK(hostKey("localhost") == "localhost"); CHECK(hostKey("10.0.0.2") == "10.0.0.2");

    // values: percent or an older factor
    CHECK(parseValue("110") == 110); CHECK(parseValue("110%") == 110); CHECK(parseValue("1.250") == 125);
    CHECK(parseValue("0.670\r\n") == 67); CHECK(parseValue("2.500") == 200); CHECK(parseValue("0.3") == 50);
    CHECK(parseValue("") == 0); CHECK(parseValue("abc") == 0); CHECK(parseValue("0") == 0); CHECK(parseValue("5000") == 0);
    CHECK(parseValue("110x") == 0); CHECK(parseValue("nan") == 0); CHECK(parseValue("-1.1") == 0); CHECK(parseValue("29") == 0);

    // store
    Store s;
    CHECK(s.get("example.com") == 0);
    CHECK(s.set("www.example.com", 125)); CHECK(s.get("example.com") == 125); CHECK(s.get("WWW.EXAMPLE.COM") == 125);
    CHECK(!s.set("bad host", 110)); CHECK(s.size() == 1);
    CHECK(s.set("a.org", 900)); CHECK(s.get("a.org") == 200);       // clamped
    CHECK(s.set("example.com", 90)); CHECK(s.size() == 2);
    CHECK(s.serialize() == "a.org\t200\nexample.com\t90\n");         // newest change last
    CHECK(s.erase("www.example.com")); CHECK(!s.erase("example.com")); CHECK(s.size() == 1);

    // parse: old and new lines, CRLF, junk, later line wins, keys normalized
    Store f;
    f.parse("old.com\t1.250\nnew.com\t150\r\nWWW.Mixed.Org\t80\njunk\n\tnohost 1\nbad.com\tx\nold.com\t175\nlast.net\t2.000");
    CHECK(f.size() == 4);
    CHECK(f.get("old.com") == 175); CHECK(f.get("new.com") == 150); CHECK(f.get("mixed.org") == 80); CHECK(f.get("last.net") == 200);
    CHECK(f.serialize() == "new.com\t150\nmixed.org\t80\nold.com\t175\nlast.net\t200\n");
    Store g; g.parse(f.serialize()); CHECK(g.serialize() == f.serialize());   // round trip
    CHECK(Store().serialize().empty());

    // the 500 cap: the oldest changes are dropped, on set and on load
    Store c;
    for (int i = 0; i < 600; ++i) c.set("h" + std::to_string(i) + ".com", 110);
    CHECK(c.size() == kMaxEntries); CHECK(c.get("h99.com") == 0); CHECK(c.get("h100.com") == 110); CHECK(c.get("h599.com") == 110);
    c.set("h100.com", 90);                          // a change makes it newest
    c.set("x.com", 110);
    CHECK(c.get("h100.com") == 90); CHECK(c.get("h101.com") == 0); CHECK(c.size() == kMaxEntries);
    std::string big;
    for (int i = 0; i < 700; ++i) big += "s" + std::to_string(i) + ".net\t125\n";
    Store b; b.parse(big);
    CHECK(b.size() == kMaxEntries); CHECK(b.get("s199.net") == 0); CHECK(b.get("s200.net") == 125); CHECK(b.get("s699.net") == 125);
    CHECK(b.serialize().size() < 500 * 32);

    // one fgets() line as omniPrefsLoad passes it (newline kept)
    Store l; CHECK(l.parseLine("site.io\t110\n")); CHECK(l.get("site.io") == 110); CHECK(!l.parseLine("nothing\n"));

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
