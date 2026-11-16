// OMNI_QUICK_ANSWERS_V1: host tests of the pure part (OmniQuickAnswers.h).
//   g++ -std=c++20 -Wall -Wextra -fsanitize=address,undefined -I<dir with OmniQuickAnswers.h> test_quick_answers.cpp -o t && ./t
#include "OmniQuickAnswers.h"
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <vector>

namespace Q = OmniQuickAnswers;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static std::string val(const std::string& in, bool known = false, int off = 0)
{
    Q::Answer a;
    if (!Q::answer(in, a, known, off)) return "<none>";
    return a.value;
}
static std::string title(const std::string& in, bool known = false, int off = 0)
{
    Q::Answer a;
    if (!Q::answer(in, a, known, off)) return "<none>";
    return a.title;
}
#define EQ(in, want) do { ++checks; const std::string got = val(in); if (got != (want)) { ++fails; std::printf("FAIL %d: \"%s\" -> \"%s\", want \"%s\"\n", __LINE__, std::string(in).c_str(), got.c_str(), std::string(want).c_str()); } } while (0)
#define NONE(in) EQ(in, "<none>")

int main()
{
    // --- calculator: the asked-for examples
    EQ("12*7+3", "87");
    EQ("2^10", "1024");
    EQ("sqrt(2)", "1.41421356237");
    EQ("15% of 80", "12");
    EQ("(1+2)*3", "9");
    EQ("1.5*4", "6");
    EQ("0.1+0.2", "0.3");
    CHECK(title("12*7+3") == "= 87");
    // precedence / associativity
    EQ("2+3*4", "14");
    EQ("10 - 4 - 3", "3");
    NONE("10-4-3");                         // digits and '-' only: dates / phones / scores
    EQ("100/10/5", "2");
    EQ("2^3^2", "512");
    EQ("-2^2", "-4");
    EQ("(-2)^2", "4");
    EQ("2^-1", "0.5");
    EQ("2**8", "256");
    EQ("-3+5", "2");
    EQ("--3+1", "4");
    EQ("3 x 4", "12");
    EQ("7 / 2", "3.5");
    EQ("10 % 3", "1");
    EQ("10 mod 4", "2");
    EQ("50% * 2", "1");
    EQ("200 * 15%", "30");
    EQ("5!", "120");
    EQ("3!+1", "7");
    EQ("sqrt 16 + 1", "5");
    EQ("sqrt(16)+sqrt(9)", "7");
    EQ("abs(-5)+1", "6");
    EQ("cbrt(27)", "3");
    EQ("log(1000)", "3");
    EQ("log10(100)", "2");
    EQ("log2(8)", "3");
    EQ("ln(e)", "1");
    EQ("2*pi", "6.28318530718");
    EQ("sin(pi)", "0");
    EQ("cos(0)", "1");
    EQ("round(2.5)+0", "3");
    EQ("floor(2.7)", "2");
    EQ("ceil(2.1)", "3");
    EQ("1e3+1", "1001");
    EQ("1/3", "0.333333333333");
    EQ("2/3", "0.666666666667");
    EQ("22/7", "3.14285714286");
    EQ("= 2+2", "4");
    EQ("2+2 =", "4");
    EQ("  2 + 2  ", "4");
    EQ("((((1+1))))", "2");
    EQ("2^40", "1099511627776");
    EQ("2^60", "1.15292150461e18");
    EQ("1/1024/1024", "9.53674316406e-7");
    EQ("1000000*1000000", "1000000000000");
    EQ("0.000001*2", "0.000002");
    EQ(".5+.5", "1");
    EQ("5.+1", "6");
    EQ("3\xC3\x97" "4", "12");             // multiplication sign
    EQ("8\xC3\xB7" "2", "4");              // division sign
    EQ("5 \xE2\x88\x92 3", "2");          // minus sign (digits and a minus without spaces never answer)
    EQ("2\xCF\x80", "<none>");             // "2pi": no implicit multiplication
    EQ("\xE2\x88\x9A" "9", "3");           // square root sign
    EQ("2^1000", "1.07150860719e301");
    EQ("170!/169!", "170");
    EQ("12 * 7 + 3", "87");
    EQ("100/10/5", "2");
    NONE("12/25/24");
    EQ("1-1 ", "<none>");                  // digits and '-' only: never

    // --- failures / overflow / domain: show nothing
    NONE("1/0");
    NONE("5 % 0");
    NONE("0^-1");
    NONE("2^10000");
    NONE("2^1024");
    NONE("10^308*10");
    NONE("1e400+1");
    NONE("171!");
    NONE("2.5!");
    NONE("(-1)!");
    NONE("sqrt(-1)");
    NONE("ln(0)");
    NONE("log(-1)");
    NONE("(-8)^(1/3)");
    NONE("exp(1000)");
    NONE("1+");
    NONE("*2");
    NONE("(1+2");
    NONE("1+2)");
    NONE("()");
    NONE("1++");
    NONE("2(3)");
    NONE("2 3");
    NONE("1,000+1");
    NONE("1..2+1");
    NONE("1.2.3+1");
    NONE("sqrt");
    NONE("sqrt()");
    NONE("foo(2)");
    EQ("pi*e", "8.53973422267");
    NONE("pi e");
    NONE("2*x");
    NONE("4x4");
    NONE("1920x1080");
    NONE("2+2;alert(1)");
    NONE("2+2\n");
    NONE("eval(1+1)");
    NONE("Math.pow(2,3)");
    NONE("[1]+1");
    NONE("1+1 // x");

    // --- limits
    {
        std::string deep(32, '('); deep += "1"; deep += std::string(32, ')'); deep += "+1";
        NONE(deep);                          // 32 parens + the unary levels inside exceed 32
        std::string ok(15, '('); ok += "1+1"; ok += std::string(15, ')');
        EQ(ok, "2");
        std::string neg(40, '-'); neg += "1+1";
        NONE(neg);
        std::string longx = "1"; while (longx.size() < 119) longx += "+1";
        CHECK(longx.size() == 119);
        EQ(longx, "60");
        std::string toolong = longx + "+1";
        CHECK(toolong.size() == 121);
        NONE(toolong);
        NONE(std::string(200, '('));
        NONE("123456789012345678901234567890123+1");   // literal over 32 characters
        EQ("1234567890123456789012345678901+0", "1.23456789012e30");
        std::string pows = "2"; for (int i = 0; i < 30; ++i) pows += "^2";
        NONE(pows);                                    // overflows
        std::string facts = "3"; for (int i = 0; i < 10; ++i) facts += "!";
        NONE(facts);
    }

    // --- must not trigger
    const char* const never[] = {
        "2048 game", "route 66", "2048", "66", "-5", "+5", "(5)", "3.14", "1e5", "10%", "pi", "e", "x", "abc",
        "google.com", "www.1+1.com", "http://1+1.com", "https://example.com/a?b=1+2", "192.168.0.1", "10.0.0.1",
        "2024-01-05", "1/2/2024", "12/25/2024", "555-1234", "1-800-555-1234", "(555) 123-4567", "+1 555 123 4567",
        "12345-6789", "3-1", "24/7", "9/11", "50/50", "4/20", "7/11", "20/20", "iphone 15", "ps5", "covid-19",
        "covid 19", "4 in 1", "2 in 1 laptop", "top 10", "9 to 5", "1 to 1", "1 in 10", "50 cent", "c++", "c#",
        "f1", "f-150", "x-men", "a+b", "1 + a", "1080p", "4k", "5g", "60 fps", "5 km", "km to mi", "5 km in",
        "5 km in banana", "5 m to s", "5 kg in km", "3 ft 4 to cm", "10 c to f to k", "9 pst", "9 pst to est",
        "2pm", "9pm pst", "25:00 utc to est", "13pm est to pst", "9:60 est to pst", "9pm abc to est",
        "9pm in my time", "9pm pst in my time", "windows 10", "ios 17.1", "v1.2.3", "rx 7900", "3d", "100 days",
        "1 2 3", "007", "1.", "4 + 4 = 8 game", "what is 2+2", "2+2 cats", "how many km in a mile",
        "\xE2\x82\xAC" "5", "5 \xC2\xA5", "5 usd to eur", "5 eur in usd", "100 btc to usd", "1 gb", "mb to gb",
    };
    for (const char* n : never) NONE(n);

    // --- units: the asked-for examples
    EQ("5 km in mi", "3.10686 mi");
    EQ("72 f to c", "22.2222 \xC2\xB0" "C");
    EQ("3 ft 4 in to cm", "101.6 cm");
    EQ("500 g in lb", "1.10231 lb");
    EQ("1 gb in mb", "1000 MB");
    CHECK(title("5 km in mi") == "= 3.10686 mi");
    // more units / spellings
    EQ("5km in mi", "3.10686 mi");
    EQ("5 KM IN MI", "3.10686 mi");
    EQ("72\xC2\xB0" "f to c", "22.2222 \xC2\xB0" "C");
    EQ("72 \xC2\xB0" "F to \xC2\xB0" "C", "22.2222 \xC2\xB0" "C");
    EQ("100 c to f", "212 \xC2\xB0" "F");
    EQ("-40 c to f", "-40 \xC2\xB0" "F");
    EQ("0 k to c", "-273.15 \xC2\xB0" "C");
    EQ("300 kelvin in fahrenheit", "80.33 \xC2\xB0" "F");
    NONE("-300 c to k");                     // below absolute zero
    EQ("1 mile to km", "1.60934 km");
    EQ("1 mi = km", "1.60934 km");
    EQ("1 mi -> ft", "5280 ft");
    EQ("10 in to cm", "25.4 cm");
    EQ("5 in in cm", "12.7 cm");
    EQ("3 ft 4 in in cm", "101.6 cm");
    EQ("6 feet 2 inches to m", "1.8796 m");
    EQ("5'10\" to cm", "177.8 cm");
    EQ("180 cm to ft", "5.90551 ft");
    EQ("1 lb in g", "453.592 g");
    EQ("1 kg in lbs", "2.20462 lb");
    EQ("10 st in kg", "63.5029 kg");
    EQ("5 lb 3 oz in kg", "2.35301 kg");
    EQ("16 oz to lb", "1 lb");
    EQ("1 gal to l", "3.78541 L");
    EQ("2 cups in ml", "473.176 ml");
    EQ("8 fl oz to ml", "236.588 ml");
    EQ("1 tbsp in tsp", "3 tsp");
    EQ("1 tb in gb", "1000 GB");
    EQ("1 gib in mib", "1024 MiB");
    EQ("1 gb in gib", "0.931323 GiB");
    EQ("100 mbit in mb", "12.5 MB");
    EQ("1 h 30 min in min", "90 min");
    EQ("1 day in s", "86400 s");
    EQ("1 year in days", "365 days");
    EQ("1 yr in s", "31536000 s");
    EQ("100 km/h in mph", "62.1371 mph");
    EQ("60 mph to km/h", "96.5606 km/h");
    EQ("10 m/s to km/h", "36 km/h");
    EQ("1 acre in m2", "4046.86 m\xC2\xB2");
    EQ("1 sq mi to km2", "2.58999 km\xC2\xB2");
    EQ("100 sq ft to sq m", "9.2903 m\xC2\xB2");
    EQ("1 ha in acres", "2.47105 acres");
    EQ("1 nmi to km", "1.852 km");
    EQ("30 knots to mph", "34.5234 mph");
    EQ("0.5 kg to g", "500 g");
    EQ(".5 kg to g", "500 g");
    EQ("1 mm in km", "0.000001 km");
    EQ("1 um in km", "<none>");
    EQ("1 m in mm", "1000 mm");
    EQ("1e3 m in km", "<none>");             // no exponents in conversions
    NONE("10 c to f c");
    NONE("1 c 2 c to f");                    // compound temperature
    NONE("5 km 3 kg to m");                  // mixed dimensions

    // --- time zones
    EQ("9pm pst to est", "12:00 AM");
    CHECK(title("9pm pst to est") == "= 12:00 AM EST (next day)");
    EQ("9:30pm pst in est", "12:30 AM");
    EQ("21:00 utc to jst", "06:00");
    CHECK(title("21:00 utc to jst") == "= 06:00 JST (next day)");
    EQ("1am jst to pst", "8:00 AM");
    CHECK(title("1am jst to pst") == "= 8:00 AM PST (previous day)");
    EQ("noon est to cet", "6:00 PM");
    EQ("midnight utc to ist", "5:30 AM");
    EQ("12am utc to utc+5:30", "5:30 AM");
    EQ("3pm gmt-3 to utc", "6:00 PM");
    EQ("12pm pdt to edt", "3:00 PM");
    NONE("9pm pst in my time");              // offset unknown
    CHECK(val("9pm pst in my time", true, 60) == "6:00 AM");
    CHECK(title("9pm pst in my time", true, 60) == "= 6:00 AM your time (next day)");
    CHECK(val("9pm pst to local", true, -480) == "9:00 PM");
    CHECK(val("9pm in pst", true, 60) == "12:00 PM");
    CHECK(val("9pm in my time", true, 60) == "<none>");   // no explicit zone
    NONE("0am pst to est");
    NONE("13pm pst to est");
    NONE("9:5pm pst to est");
    NONE("9pm pt to et");
    NONE("9pm utc+15 to est");

    // --- formatting
    CHECK(Q::format(0, 6) == "0");
    CHECK(Q::format(-0.0, 6) == "0");
    CHECK(Q::format(1e-7, 6) == "1e-7");
    CHECK(Q::format(1234567.891, 6) == "1234568");
    CHECK(Q::format(3.10685596, 6) == "3.10686");
    CHECK(Q::format(1e15, 12) == "1e15");
    CHECK(Q::format(-2.5, 12) == "-2.5");
    CHECK(Q::format(1.0 / 0.0, 12).empty());

    // --- fuzz: random byte strings and random math-alphabet strings never crash; answers are finite and short
    {
        std::mt19937 rng(12345);
        const std::string alpha = "0123456789+-*/^%!().e x ofpisqrtlnkmigbftcin:pmaestu'\"=>";
        Q::Answer a;
        int answered = 0;
        for (int n = 0; n < 300000; ++n) {
            std::string s;
            const int len = int(rng() % 40);
            const bool bytes = (n % 7) == 0;
            for (int i = 0; i < len; ++i) s += bytes ? char(rng() % 256) : alpha[rng() % alpha.size()];
            if (Q::answer(s, a, (n & 1) != 0, int(rng() % 1500) - 750)) {
                ++answered;
                ++checks;
                if (a.value.empty() || a.value.size() > 40 || a.title.find("nan") != std::string::npos || a.title.find("inf") != std::string::npos) {
                    ++fails; std::printf("FAIL fuzz: \"%s\" -> \"%s\"\n", s.c_str(), a.title.c_str());
                }
            }
        }
        std::printf("fuzz: %d of 300000 answered\n", answered);
        // deep nesting attempts of every kind
        for (int d = 0; d < 200; d += 7) {
            std::string s(size_t(d), '('); s += "2"; s += std::string(size_t(d), ')');
            Q::answer(s + "+1", a);
            Q::answer(std::string(size_t(d), '-') + "2+1", a);
            std::string f; for (int i = 0; i < d; ++i) f += "sqrt "; f += "2+1";
            Q::answer(f, a);
            std::string p = "2"; for (int i = 0; i < d; ++i) p += "^-1";
            Q::answer(p, a);
        }
    }

    std::printf("%d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
