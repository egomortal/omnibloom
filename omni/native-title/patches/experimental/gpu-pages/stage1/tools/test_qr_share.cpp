// OMNI_QR_SHARE_V1: host tests for engine/entry/OmniQrShare.h (written by apply_qr_share.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_qr_share.cpp -o t && ./t [refs.txt]
// refs.txt comes from tools/test_qr_share_ref.py (segno + python-qrcode); without it only the built-in checks run
// (capacities, one "HELLO WORLD" matrix taken from segno 1.6.6, the address cleaner, the layout).
#include "OmniQrShare.h"
#include <cstdio>
#include <fstream>
#include <sstream>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniQr;

static std::string bitsOf(const Code& c)
{
    std::string s;
    for (uint8_t d : c.dark) s += d ? '1' : '0';
    return s;
}
static std::string unhex(const std::string& h)
{
    std::string s;
    for (size_t i = 0; i + 1 < h.size(); i += 2) s += char(std::stoi(h.substr(i, 2), nullptr, 16));
    return s;
}
// The mask a matrix's format bits name (level M): row 8, columns 0-5, 7, 8 and (7, 8) hold bits 0-8 of the format.
static int formatMask(const std::string& rows, int size)
{
    auto at = [&](int x, int y) { return rows[size_t(y) * size + x] == '1'; };
    int bits = 0;
    for (int i = 0; i <= 5; ++i) bits |= at(8, i) << i;
    bits |= at(8, 7) << 6; bits |= at(8, 8) << 7; bits |= at(7, 8) << 8;
    for (int i = 9; i < 15; ++i) bits |= at(14 - i, 8) << i;
    bits ^= 0x5412;
    return (bits >> 10) & 7;
}

int main(int argc, char** argv)
{
    // capacities (ISO/IEC 18004 table 7, level M, byte mode)
    static const int cap[21] = { 0, 14, 26, 42, 62, 84, 106, 122, 152, 180, 213, 251, 287, 331, 362, 412, 450, 504, 560, 624, 666 };
    for (int v = 1; v <= 20; ++v) CHECK(byteCapacity(v) == cap[v]);
    CHECK(maxBytes() == 666);
    CHECK(dataCodewords(1) == 16 && dataCodewords(7) == 124 && dataCodewords(10) == 216 && dataCodewords(20) == 669);

    Code c;
    CHECK(!encode("", c));
    CHECK(!encode(std::string(667, 'a'), c));
    CHECK(encode(std::string(666, 'a'), c) && c.version == 20 && c.size == 97);
    CHECK(encode(std::string(14, 'a'), c) && c.version == 1 && c.size == 21);
    CHECK(encode(std::string(15, 'a'), c) && c.version == 2);

    // "HELLO WORLD", byte mode, level M, mask 2 forced: version 1, the matrix python-qrcode 8.2 makes
    static const char* hello[21] = {
        "111111100000101111111", "100000100101001000001", "101110101110101011101", "101110101010101011101",
        "101110101010101011101", "100000101101001000001", "111111101010101111111", "000000001010000000000",
        "101111100011001111100", "011000010111111101100", "101100110000111001110", "011101001111110011100",
        "100010110110110000101", "000000001110100001000", "111111100101001000110", "100000101110010101111",
        "101110101001000100101", "101110101000111111000", "101110101100100100100", "100000100010110011100",
        "111111101011100010110" };
    std::string want;
    for (auto* r : hello) want += r;
    CHECK(encode("HELLO WORLD", c, 2) && c.version == 1 && c.mask == 2);
    const bool helloOk = bitsOf(c) == want;
    CHECK(helloOk);
    if (!helloOk) for (int y = 0; y < c.size; ++y) { for (int x = 0; x < c.size; ++x) std::putchar(c.at(x, y) ? '#' : '.'); std::putchar('\n'); }
    CHECK(formatMask(bitsOf(c), c.size) == 2);
    CHECK(encode("HELLO WORLD", c) && c.version == 1 && formatMask(bitsOf(c), c.size) == c.mask);

    // reference matrices (python-qrcode: every mask forced, and its own choice; segno: its own choice, information)
    // and the codes for the OpenCV decode (argv[2])
    int forcedN = 0, forcedOk = 0, autoN = 0, autoSame = 0, segnoN = 0, segnoMask = 0;
    if (argc > 1) {
        std::ifstream f(argv[1]);
        CHECK(bool(f));
        std::ofstream dump;
        if (argc > 2) dump.open(argv[2]);
        std::string line, lastHex;
        while (std::getline(f, line)) {
            std::istringstream in(line);
            std::string lib, hex, rows;
            int forced = 0, ver = 0, size = 0;
            if (!(in >> lib >> hex >> forced >> ver >> size >> rows)) continue;
            const std::string data = unhex(hex);
            Code mine;
            const bool ok = encode(data, mine, forced);
            CHECK(ok && mine.version == ver && mine.size == size);
            const int theirs = formatMask(rows, size);
            if (lib == "qrcode" && forced >= 0) {
                ++forcedN;
                const bool same = ok && bitsOf(mine) == rows && theirs == forced;
                forcedOk += same;
                if (!same) std::printf("MISMATCH python-qrcode mask %d, %zu bytes, version %d\n", forced, data.size(), ver);
            } else if (lib == "qrcode") {
                ++autoN;
                autoSame += ok && mine.mask == theirs;
                Code alt; encode(data, alt, theirs);
                CHECK(penalty(mine) <= penalty(alt));   // a different choice only where this scorer rates theirs worse
                if (ok && mine.mask != theirs)
                    std::printf("  mask choice: %zu bytes v%d: mine %d (penalty %ld), python-qrcode %d (penalty %ld)\n",
                        data.size(), ver, mine.mask, penalty(mine), theirs, penalty(alt));
                if (dump && hex != lastHex) dump << hex << ' ' << mine.size << ' ' << bitsOf(mine) << '\n';
                lastHex = hex;
            } else {
                ++segnoN; segnoMask += ok && mine.mask == theirs;
            }
        }
        CHECK(forcedN == 8 * autoN && forcedN > 0 && forcedOk == forcedN);
        std::printf("refs: python-qrcode forced masks %d/%d identical; same mask choice as python-qrcode %d/%d, as segno %d/%d\n",
            forcedOk, forcedN, autoSame, autoN, segnoMask, segnoN);
        if (dump) {
            for (const char* s : { "HELLO WORLD", "https://example.com/watch?v=abc", "http://192.0.2.7:8080/a?b=1" }) {
                Code k; encode(s, k);
                std::string h; char b2[3];
                for (unsigned char ch : std::string(s)) { std::snprintf(b2, sizeof(b2), "%02x", ch); h += b2; }
                dump << h << ' ' << k.size << ' ' << bitsOf(k) << '\n';
            }
        }
    }

    // penalty choice: the chosen mask has the lowest score of the eight (lowest index on ties)
    for (const char* s : { "HELLO WORLD", "https://example.com/", "https://example.org/a?b=c#d" }) {
        Code best; encode(s, best);
        for (int m = 0; m < 8; ++m) {
            Code k; encode(s, k, m);
            CHECK(penalty(k) > penalty(best) || (penalty(k) == penalty(best) && m >= best.mask));
        }
    }

    // the address cleaner
    CHECK(cleanURL("https://example.com/") == "https://example.com/");
    CHECK(cleanURL("https://example.com/a?utm_source=x&utm_medium=y") == "https://example.com/a");
    CHECK(cleanURL("https://example.com/a?id=4&utm_source=x&b=2") == "https://example.com/a?id=4&b=2");
    CHECK(cleanURL("https://example.com/a?fbclid=AbC&x=1#top") == "https://example.com/a?x=1#top");
    CHECK(cleanURL("https://example.com/a?gclid=1#frag?utm_x=1") == "https://example.com/a#frag?utm_x=1");   // fragment untouched
    CHECK(cleanURL("https://example.com/watch?v=abc&si=XYZ") == "https://example.com/watch?v=abc");
    CHECK(cleanURL("https://example.com/a?UTM_Campaign=1&FBCLID=2&q=3") == "https://example.com/a?q=3");
    CHECK(cleanURL("https://example.com/a?sid=1&size=2&utm=3&gclidx=4") == "https://example.com/a?sid=1&size=2&utm=3&gclidx=4");
    CHECK(cleanURL("https://example.com/a?q=a%26utm_source%3Dx") == "https://example.com/a?q=a%26utm_source%3Dx");   // encoded stays
    CHECK(cleanURL("https://example.com/a?&&x=1&&") == "https://example.com/a?x=1");
    CHECK(cleanURL("https://example.com/a?") == "https://example.com/a");
    CHECK(cleanURL("https://example.com/a?si") == "https://example.com/a");
    CHECK(cleanURL("https://example.com/a?flag&utm_id") == "https://example.com/a?flag");
    CHECK(cleanURL("https://example.com/#x?utm_source=1") == "https://example.com/#x?utm_source=1");
    CHECK(trackingKey("utm_") && trackingKey("Utm_Term") && trackingKey("si") && !trackingKey("sig") && !trackingKey("utm"));

    CHECK(shareable("https://example.com/") && shareable("HTTP://example.com") && !shareable("https://"));
    CHECK(!shareable("omni://newtab") && !shareable("about:blank") && !shareable("") && !shareable("file:///data/x") && !shareable("data:text/html,x"));

    CHECK(shownURL("https://www.example.com/") == "example.com");
    CHECK(shownURL("http://example.com/a/b/") == "example.com/a/b");
    CHECK(shownURL("HTTPS://WWW.Example.com/A") == "Example.com/A");
    CHECK(shownURL("https://wwwexample.com/") == "wwwexample.com");
    const std::string longURL = "https://example.com/" + std::string(200, 'x') + "/end-of-path";
    const std::string sh = shownURL(longURL, 72);
    CHECK(sh.size() <= 72 && sh.compare(0, 12, "example.com/") == 0 && sh.find("...") != std::string::npos && sh.substr(sh.size() - 11) == "end-of-path");
    const std::string utf = shownURL("https://example.com/" + std::string(40, 'a') + "\xe6\x97\xa5\xe6\x97\xa5\xe6\x97\xa5\xe6\x97\xa5" + std::string(40, 'b'), 72);
    CHECK(utf.size() <= 72);
    for (size_t i = 0; i < utf.size(); ++i)   // no broken sequence: every continuation byte follows a lead / continuation byte
        if ((static_cast<unsigned char>(utf[i]) & 0xC0) == 0x80) CHECK(i > 0 && (static_cast<unsigned char>(utf[i - 1]) & 0x80));
    for (size_t n = 60; n < 90; ++n) {
        const std::string s = shownURL("https://example.com/" + std::string(30, 'c') + "\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9" + std::string(30, 'd'), n);
        size_t lead = 0, cont = 0;
        for (unsigned char ch : s) { if ((ch & 0xE0) == 0xC0) ++lead; if ((ch & 0xC0) == 0x80) ++cont; }
        CHECK(lead == cont && s.size() <= n);
    }

    // the square: 60% of the height in whole-pixel modules, quiet zone included
    Square q = square(21, 1080);
    CHECK(q.module == 22 && q.side == 22 * 29 && q.side <= 648);
    q = square(97, 720);
    CHECK(q.module == 4 && q.side == 4 * 105);
    q = square(97, 2160);
    CHECK(q.module == 12 && q.side <= 1296);
    q = square(97, 100);
    CHECK(q.module == 1);
    CHECK(square(0, 1080).side == 0 && square(21, 0).side == 0);

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
