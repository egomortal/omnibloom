// OMNI_TEXT_SELECT_V1: host tests for engine/entry/OmniTextSelect.h (written by apply_text_select.py).
//   g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_text_select.cpp -o t && ./t [--emit <dir>]
// --emit <dir>: also writes the assembled page scripts (s.js f.js b.js u.js d.js c.js, odd.js) for node --check /
// tools/test_text_select_js.cjs.
#include "OmniTextSelect.h"
#include "OmniQrShare.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

namespace OTSL = OmniTextSelect;

static bool validUtf8(const std::string& s)
{
    for (size_t i = 0; i < s.size();) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        const size_t n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 0;
        if (!n || i + n > s.size()) return false;
        for (size_t k = 1; k < n; ++k) if ((static_cast<unsigned char>(s[i + k]) & 0xC0) != 0x80) return false;
        i += n;
    }
    return true;
}

int main(int argc, char** argv)
{
    // --- script building: fixed op letters, finite numbers, nothing else spliced in
    CHECK(OTSL::number(12.34) == "12.3");
    CHECK(OTSL::number(-5) == "-5.0");
    CHECK(OTSL::number(std::numeric_limits<double>::quiet_NaN()) == "0.0");
    CHECK(OTSL::number(std::numeric_limits<double>::infinity()) == "0.0");
    CHECK(OTSL::number(5e9) == "1000000.0");
    CHECK(OTSL::number(-5e9) == "-1000000.0");
    const std::string s = OTSL::script(OTSL::Op::Start, 100.04, 200.06);
    CHECK(s.rfind("(function(op,x,y){", 0) == 0);
    const std::string tail = "})('s',100.0,200.1)";
    CHECK(s.size() > tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0);
    CHECK(OTSL::script(OTSL::Op::Right).find("('f',0.0,0.0)") != std::string::npos);
    CHECK(OTSL::script(OTSL::Op::Left).find("('b',0.0,0.0)") != std::string::npos);
    CHECK(OTSL::script(OTSL::Op::Up).find("('u',") != std::string::npos);
    CHECK(OTSL::script(OTSL::Op::Down).find("('d',") != std::string::npos);
    CHECK(OTSL::script(OTSL::Op::Clear).find("('c',") != std::string::npos);
    CHECK(std::string(OTSL::kScript).find(")JS") == std::string::npos);
    CHECK(std::string(OTSL::kScript).find("//") == std::string::npos);   // no line comments in a one-line-joinable script

    // --- utf8Cut / clip: 4 KB, never splitting a character
    CHECK(OTSL::utf8Cut("abc", 5) == "abc");
    CHECK(OTSL::utf8Cut("abc", 2) == "ab");
    CHECK(OTSL::utf8Cut("a\xC3\xA9", 2) == "a");             // e-acute not split
    CHECK(OTSL::utf8Cut("a\xF0\x9F\x98\x80z", 4) == "a");    // emoji not split
    CHECK(OTSL::utf8Cut("a\xF0\x9F\x98\x80z", 5) == "a\xF0\x9F\x98\x80");
    CHECK(OTSL::utf8Cut("", 0).empty());
    CHECK(OTSL::clip(std::string(5000, 'x')).size() == 4096);
    std::string euro;
    for (int i = 0; i < 2000; ++i) euro += "\xE2\x82\xAC";   // 6000 bytes of 3-byte characters
    CHECK(OTSL::clip(euro).size() == 4095 && validUtf8(OTSL::clip(euro)));
    CHECK(OTSL::clip("line one\nline two") == "line one\nline two");   // Copy keeps line breaks
    CHECK(OTSL::codePoints("a\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80") == 4);

    // --- collapse / forAddress / query / encode / preview
    CHECK(OTSL::collapse("  Hello \n\t world  ") == "Hello world");
    CHECK(OTSL::collapse("a\xC2\xA0" "b") == "a b");            // no-break space
    CHECK(OTSL::collapse("a\xE2\x80\xA8" "b\xE2\x80\xA9") == "a b");   // U+2028 / U+2029
    CHECK(OTSL::collapse("\r\n\r\n") == "");
    CHECK(OTSL::collapse("caf\xC3\xA9") == "caf\xC3\xA9");      // other multibyte kept
    CHECK(OTSL::collapse(std::string("a\0b", 3)) == "a b");     // NUL is a control
    CHECK(OTSL::forAddress("example.com/\npath") == "example.com/ path");
    CHECK(OTSL::forAddress(std::string(3000, 'a')).size() == 2048);
    CHECK(OTSL::query(std::string(1000, 'q')).size() == 400);
    CHECK(OTSL::encode("caf\xC3\xA9 & co/1?") == "caf%C3%A9%20%26%20co%2F1%3F");
    CHECK(OTSL::encode("A-z_09") == "A-z_09");
    CHECK(OTSL::encode("'\"<>#") == "%27%22%3C%3E%23");
    CHECK(OTSL::preview("short") == "short");
    CHECK(OTSL::preview(std::string(100, 'a')).size() == 60);
    CHECK(OTSL::preview(std::string(100, 'a')).compare(57, 3, "...") == 0);
    CHECK(validUtf8(OTSL::preview(euro, 20)));
    CHECK(OTSL::preview(" a \n b ", 10) == "a b");

    // --- words / status / notice
    CHECK(OTSL::words("") == 0);
    CHECK(OTSL::words("   ") == 0);
    CHECK(OTSL::words("one") == 1);
    CHECK(OTSL::words(" one\ntwo  three ") == 3);
    CHECK(OTSL::status("", 0) == "Nothing selected");
    CHECK(OTSL::status("word", 4) == "1 word selected");
    CHECK(OTSL::status("two words", 9) == "2 words selected");
    CHECK(OTSL::status("cut", 9000).find("(the first 4 KB is used)") != std::string::npos);
    // OMNI_TEXT_SELECT_V1_R2: the page's length is in UTF-16 units; a non-BMP character (U+1F600) is 2 there
    CHECK(OTSL::utf16Units("a\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80") == 5);   // a, e-acute, euro: 1 each; the emoji: 2
    CHECK(OTSL::utf16Units("") == 0);
    CHECK(OTSL::status("hi \xF0\x9F\x98\x80", 5) == "2 words selected");   // "hi 😀" whole: JS length 5, nothing cut
    CHECK(OTSL::status("\xF0\x9F\x98\x80\xF0\x9F\x8E\x89", 4) == "1 word selected");   // two emoji: JS length 4
    CHECK(OTSL::status("hi \xF0\x9F\x98\x80", 6).find("(the first 4 KB is used)") != std::string::npos);   // the page had more
    {   // 4096 units with emoji: the page sent all of it (n == 4096): not cut; n larger: cut
        std::string t;
        for (int i = 0; i < 2048; ++i) t += "\xF0\x9F\x98\x80";
        CHECK(OTSL::utf16Units(t) == 4096);
        CHECK(OTSL::status(t, 4096).find("(the first 4 KB is used)") != std::string::npos);   // 8192 bytes: over the 4 KB clip
        CHECK(OTSL::status(t.substr(0, 400), 200).find("(the first") == std::string::npos);   // 100 emoji, n 200: whole
    }
    CHECK(OTSL::copiedNotice("hello").rfind("Copied 5 characters: ", 0) == 0);
    CHECK(OTSL::copiedNotice("x").rfind("Copied 1 character: ", 0) == 0);
    CHECK(OTSL::copiedNotice(std::string(5000, 'x')).find("Copied 4096 characters (the first 4 KB)") == 0);
    CHECK(OTSL::copiedNotice("x").find("L2 + Triangle") != std::string::npos);

    // --- actions
    const size_t qrMax = size_t(OmniQr::maxBytes());
    CHECK(qrMax == 666);
    auto a = OTSL::actions("hello world", qrMax);
    CHECK(a.size() == 4);
    CHECK(a[0].action == OTSL::Action::Copy && a[0].label == "Copy" && a[0].enabled);
    CHECK(a[1].action == OTSL::Action::Search && a[1].label == "Search for \"hello world\"" && a[1].enabled);
    CHECK(a[2].action == OTSL::Action::Address && a[2].label == "Paste into address bar" && a[2].enabled);
    CHECK(a[3].action == OTSL::Action::Qr && a[3].label == "Show as QR code" && a[3].enabled);
    a = OTSL::actions(std::string(667, 'x'), qrMax);
    CHECK(a[0].enabled && !a[3].enabled && a[3].label.find("too long") != std::string::npos);
    a = OTSL::actions(std::string(666, 'x'), qrMax);
    CHECK(a[3].enabled);
    a = OTSL::actions(std::string(80, 'w'), qrMax);
    CHECK(a[1].label.size() == std::string("Search for \"\"").size() + 40 && a[1].label.find("...\"") != std::string::npos);
    a = OTSL::actions(" \n ", qrMax);
    CHECK(!a[0].enabled && !a[1].enabled && !a[2].enabled && !a[3].enabled && a[3].label == "Show as QR code");
    // the QR encoder takes what Show as QR code passes (clipped text, any bytes)
    OmniQr::Code code;
    CHECK(OmniQr::encode(OTSL::clip("Selected text\nwith a line break and caf\xC3\xA9"), code) && code.size > 0);
    CHECK(!OmniQr::encode(OTSL::clip(std::string(700, 'x')), code));

    // --- ids
    CHECK(OTSL::kContextId != 960 && OTSL::kContextId != 975);

    if (argc == 3 && !std::strcmp(argv[1], "--emit")) {
        const struct { const char* name; std::string js; } out[] = {
            { "s.js", OTSL::script(OTSL::Op::Start, 100, 50) }, { "f.js", OTSL::script(OTSL::Op::Right) },
            { "b.js", OTSL::script(OTSL::Op::Left) }, { "u.js", OTSL::script(OTSL::Op::Up) },
            { "d.js", OTSL::script(OTSL::Op::Down) }, { "c.js", OTSL::script(OTSL::Op::Clear) },
            { "odd.js", OTSL::script(OTSL::Op::Start, std::nan(""), 1e300) },
        };
        for (const auto& o : out) {
            const std::string path = std::string(argv[2]) + "/" + o.name;
            FILE* f = std::fopen(path.c_str(), "wb");
            if (!f) { std::printf("cannot write %s\n", path.c_str()); return 2; }
            std::fwrite(o.js.data(), 1, o.js.size(), f);
            std::fclose(f);
        }
    }
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
