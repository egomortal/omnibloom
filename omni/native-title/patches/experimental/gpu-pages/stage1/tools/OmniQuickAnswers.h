// OMNI_QUICK_ANSWERS_V1: instant answers for the address suggestions (pure: no SDL, no WebKit, no JS engine).
// A calculator ("12*7+3", "2^10", "sqrt(2)", "15% of 80"), fixed-factor unit conversion ("5 km in mi",
// "72 f to c", "3 ft 4 in to cm", "500 g in lb", "1 gb in mb") and time zones ("9pm pst to est"; "in my time"
// only when the console's UTC offset is known). Everything is a small hand-written recursive-descent parser with
// strict limits (input <= 120 bytes, nesting <= 32, any non-finite value -> no answer). It answers only when the
// whole text is math / a conversion: "2048 game", "route 66", dates, phone numbers and URLs never answer.
// The shell side is in OmniBrowser.cpp (tools/apply_quick_answers.py); tests: tools/test_quick_answers.cpp.
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace OmniQuickAnswers {

constexpr size_t kMaxInput = 120;   // bytes, before normalising
constexpr int kMaxDepth = 32;       // nested parentheses / unary signs / functions
constexpr int kMaxTokens = 64;
constexpr size_t kMaxNumber = 32;   // characters in one number literal

enum Kind { None = 0, Calc = 1, Units = 2, TimeZone = 3 };

struct Answer {
    int kind = None;
    std::string title;   // "= 87", "= 3.10686 mi", "= 12:00 AM EST (next day)"
    std::string value;   // what Cross copies: "87", "3.10686 mi", "12:00 AM"
    std::string detail;  // the dim text after the title
};

// --- number formatting -------------------------------------------------------------------------------------------
// sig significant digits, never more than needed ("0.30000000000000004" -> "0.3"); the integer part is never rounded
// below 1e15 ("31536000", not "3.15360e7"); scientific outside [1e-6, 1e15).
inline std::string format(double v, int sig)
{
    if (!std::isfinite(v)) return std::string();
    if (v == 0) return "0";
    char b[64];
    const double a = std::fabs(v);
    if (a >= 1e15 || a < 1e-6) {
        snprintf(b, sizeof(b), "%.*e", sig - 1, v);
        std::string s(b);
        const size_t e = s.find('e');
        std::string m = s.substr(0, e), x = s.substr(e + 1);
        if (m.find('.') != std::string::npos) {
            while (!m.empty() && m.back() == '0') m.pop_back();
            if (!m.empty() && m.back() == '.') m.pop_back();
        }
        // exponent: drop '+' and leading zeros ("e+05" -> "e5", "e-07" -> "e-7")
        std::string sign;
        size_t k = 0;
        if (k < x.size() && (x[k] == '+' || x[k] == '-')) { if (x[k] == '-') sign = "-"; ++k; }
        while (k + 1 < x.size() && x[k] == '0') ++k;
        return m + "e" + sign + x.substr(k);
    }
    int mag = int(std::floor(std::log10(a)));
    int dec = sig - 1 - mag;
    if (dec < 0) dec = 0;
    if (dec > 17) dec = 17;
    snprintf(b, sizeof(b), "%.*f", dec, v);
    std::string s(b);
    if (s.find('.') != std::string::npos) {
        while (!s.empty() && s.back() == '0') s.pop_back();
        if (!s.empty() && s.back() == '.') s.pop_back();
    }
    if (s == "-0") s = "0";
    return s;
}

// --- normalising ---------------------------------------------------------------------------------------------------
// Lowercase ASCII; a few UTF-8 symbols mapped (x-sign, division sign, minus sign, pi, square root, degree, ^2 ^3);
// any other non-ASCII byte or control character: no answer. Leading '=' and trailing '=' / spaces dropped.
inline bool normalise(const std::string& in, std::string& out)
{
    out.clear();
    if (in.empty() || in.size() > kMaxInput) return false;
    for (size_t i = 0; i < in.size();) {
        const unsigned char c = (unsigned char)in[i];
        if (c < 0x80) {
            if (c < 0x20 || c == 0x7f) { if (c == '\t') { out += ' '; ++i; continue; } return false; }
            out += (c >= 'A' && c <= 'Z') ? char(c + 32) : char(c);
            ++i;
            continue;
        }
        auto is = [&](const char* seq) {
            size_t n = 0;
            while (seq[n]) ++n;
            return in.compare(i, n, seq) == 0 ? n : size_t(0);
        };
        size_t n;
        if ((n = is("\xC3\x97"))) { out += '*'; i += n; }                 // multiplication sign
        else if ((n = is("\xC3\xB7"))) { out += '/'; i += n; }            // division sign
        else if ((n = is("\xE2\x88\x92"))) { out += '-'; i += n; }        // minus sign
        else if ((n = is("\xCF\x80"))) { out += "pi"; i += n; }           // pi
        else if ((n = is("\xE2\x88\x9A"))) { out += "sqrt "; i += n; }    // square root
        else if ((n = is("\xC2\xB0"))) { i += n; }                        // degree sign (72 degF -> 72 f)
        else if ((n = is("\xC2\xB2"))) { out += '2'; i += n; }
        else if ((n = is("\xC2\xB3"))) { out += '3'; i += n; }
        else return false;
    }
    size_t a = out.find_first_not_of(' ');
    if (a == std::string::npos) return false;
    out.erase(0, a);
    while (!out.empty() && out.back() == ' ') out.pop_back();
    if (!out.empty() && out[0] == '=') {
        out.erase(0, 1);
        while (!out.empty() && out[0] == ' ') out.erase(0, 1);
    }
    while (!out.empty() && (out.back() == '=' || out.back() == ' ')) out.pop_back();
    return !out.empty() && out.size() <= kMaxInput;
}

inline bool isDigit(char c) { return c >= '0' && c <= '9'; }
inline bool isAlpha(char c) { return c >= 'a' && c <= 'z'; }

// Reads an unsigned decimal literal at s[i] (digits [. digits] [e [+-] digits]); false when there is none / too long.
inline bool readNumber(const std::string& s, size_t& i, double& v, bool allowExp)
{
    const size_t start = i;
    uint64_t mant = 0;
    int digits = 0, scale = 0;
    bool any = false;
    while (i < s.size() && isDigit(s[i])) {
        any = true;
        if (digits < 19) { mant = mant * 10 + uint64_t(s[i] - '0'); if (mant) ++digits; }
        else ++scale;
        ++i;
    }
    if (i < s.size() && s[i] == '.' && i + 1 < s.size() && isDigit(s[i + 1])) {
        ++i;
        while (i < s.size() && isDigit(s[i])) {
            any = true;
            if (digits < 19) { mant = mant * 10 + uint64_t(s[i] - '0'); if (mant) ++digits; --scale; }
            ++i;
        }
    } else if (i < s.size() && s[i] == '.' && any && !(i + 1 < s.size() && s[i + 1] == '.')) {
        // "5." is a number; "5.." is not
        if (i + 1 < s.size() && isAlpha(s[i + 1])) return false;   // "5.x" (domains, versions)
        ++i;
    }
    if (!any) { i = start; return false; }
    if (allowExp && i + 1 < s.size() && s[i] == 'e') {
        size_t j = i + 1;
        bool neg = false;
        if (j < s.size() && (s[j] == '+' || s[j] == '-')) { neg = s[j] == '-'; ++j; }
        if (j < s.size() && isDigit(s[j])) {
            int e = 0;
            while (j < s.size() && isDigit(s[j])) { if (e < 100000) e = e * 10 + (s[j] - '0'); ++j; }
            scale += neg ? -e : e;
            i = j;
        }
    }
    if (i - start > kMaxNumber) return false;
    static const double p10[] = { 1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11,
        1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22 };
    const double m = double(mant);
    if (mant == 0) v = 0;
    else if (scale >= 0 && scale <= 22) v = m * p10[scale];
    else if (scale < 0 && scale >= -22) v = m / p10[-scale];
    else if (scale > 400) v = HUGE_VAL;
    else if (scale < -400) v = 0;
    else v = m * std::pow(10.0, double(scale));
    return std::isfinite(v);
}

// --- calculator ---------------------------------------------------------------------------------------------------
// expr    := term (('+' | '-') term)*
// term    := unary (('*' | '/' | ' x ' | '%' (modulo, an operand follows) | 'of' (after a percent) | 'mod') unary)*
// unary   := ('-' | '+') unary | power
// power   := postfix (('^' | '**') unary)?            (right-associative; -2^2 = -4, 2^-1 = 0.5)
// postfix := primary ('!' | '%')*                     ('%' divides by 100 unless an operand follows)
// primary := number | '(' expr ')' | constant | function ( '(' expr ')' | unary )
// constants: pi, e, tau. functions: sqrt cbrt abs ln log (base 10) log2 exp sin cos tan (radians) floor ceil round.
// An answer needs a "math signal": a binary operator, a function or a factorial ("5", "-5", "(5)", "10%" are not).
class Calculator {
public:
    explicit Calculator(const std::string& s) : s_(s) {}
    bool run(double& v)
    {
        if (!expr(v)) return false;
        ws();
        return i_ == s_.size() && ok_ && signals_ > 0 && std::isfinite(v);
    }
private:
    const std::string& s_;
    size_t i_ = 0;
    int depth_ = 0, signals_ = 0;
    bool ok_ = true, lastPercent_ = false;

    void ws() { while (i_ < s_.size() && s_[i_] == ' ') ++i_; }
    bool fail() { ok_ = false; return false; }
    bool finite(double v) { return std::isfinite(v) ? true : fail(); }
    bool word(const char* w)   // a whole word at i_
    {
        size_t n = 0;
        while (w[n]) ++n;
        if (s_.compare(i_, n, w) != 0) return false;
        return i_ + n >= s_.size() || !isAlpha(s_[i_ + n]);
    }
    bool operandAhead()   // after '%': does an operand follow (then it is modulo)?
    {
        size_t j = i_;
        while (j < s_.size() && s_[j] == ' ') ++j;
        if (j >= s_.size()) return false;
        const char c = s_[j];
        if (isDigit(c) || c == '.' || c == '(') return true;
        if (isAlpha(c)) {
            size_t k = j;
            while (k < s_.size() && isAlpha(s_[k])) ++k;
            const std::string w = s_.substr(j, k - j);
            return w != "of" && w != "x" && w != "mod";
        }
        return false;
    }
    bool expr(double& v)
    {
        if (!term(v)) return false;
        for (;;) {
            ws();
            if (i_ >= s_.size()) return true;
            const char c = s_[i_];
            if (c != '+' && c != '-') return true;
            ++i_;
            double r;
            if (!term(r)) return false;
            v = c == '+' ? v + r : v - r;
            ++signals_;
            if (!finite(v)) return false;
        }
    }
    bool term(double& v)
    {
        if (!unary(v)) return false;
        for (;;) {
            const bool percentBefore = lastPercent_;
            ws();
            if (i_ >= s_.size()) return true;
            int op = 0;
            const char c = s_[i_];
            if (c == '*' && !(i_ + 1 < s_.size() && s_[i_ + 1] == '*')) { op = '*'; ++i_; }
            else if (c == '/') { op = '/'; ++i_; }
            else if (c == '%') { op = '%'; ++i_; }   // postfix took it when no operand follows
            else if (c == 'x' && i_ > 0 && s_[i_ - 1] == ' ' && i_ + 1 < s_.size() && s_[i_ + 1] == ' ') { op = '*'; ++i_; }
            else if (word("of") && percentBefore) { op = '*'; i_ += 2; }
            else if (word("mod")) { op = '%'; i_ += 3; }
            else return true;
            double r;
            if (!unary(r)) return false;
            ++signals_;
            if (op == '*') v *= r;
            else if (op == '/') { if (r == 0) return fail(); v /= r; }
            else { if (r == 0) return fail(); v = std::fmod(v, r); }
            if (!finite(v)) return false;
        }
    }
    bool unary(double& v)
    {
        if (++depth_ > kMaxDepth) return fail();
        ws();
        bool r;
        if (i_ < s_.size() && (s_[i_] == '-' || s_[i_] == '+')) {
            const bool neg = s_[i_] == '-';
            ++i_;
            r = unary(v);
            if (r && neg) v = -v;
        } else r = power(v);
        --depth_;
        return r;
    }
    bool power(double& v)
    {
        if (!postfix(v)) return false;
        ws();
        if (i_ < s_.size() && (s_[i_] == '^' || (s_[i_] == '*' && i_ + 1 < s_.size() && s_[i_ + 1] == '*'))) {
            i_ += s_[i_] == '^' ? 1 : 2;
            double e;
            if (!unary(e)) return false;
            if (v == 0 && e < 0) return fail();
            v = std::pow(v, e);
            ++signals_;
            lastPercent_ = false;
            return finite(v);
        }
        return true;
    }
    bool postfix(double& v)
    {
        if (!primary(v)) return false;
        lastPercent_ = false;
        for (;;) {
            ws();
            if (i_ >= s_.size()) return true;
            if (s_[i_] == '!' && !(i_ + 1 < s_.size() && s_[i_ + 1] == '=')) {
                ++i_;
                if (v < 0 || v > 170 || v != std::floor(v)) return fail();
                double f = 1;
                for (int k = 2; k <= int(v); ++k) f *= k;
                v = f;
                ++signals_;
                lastPercent_ = false;
                continue;
            }
            if (s_[i_] == '%') {
                ++i_;
                if (operandAhead()) { --i_; return true; }   // modulo: the term loop takes it
                v /= 100;
                lastPercent_ = true;
                continue;
            }
            return true;
        }
    }
    bool primary(double& v)
    {
        ws();
        if (i_ >= s_.size()) return fail();
        const char c = s_[i_];
        if (c == '(') {
            if (++depth_ > kMaxDepth) return fail();
            ++i_;
            if (!expr(v)) return false;
            ws();
            if (i_ >= s_.size() || s_[i_] != ')') return fail();
            ++i_;
            --depth_;
            return true;
        }
        if (isDigit(c) || c == '.') {
            if (!readNumber(s_, i_, v, true)) return fail();
            if (i_ < s_.size() && (isAlpha(s_[i_]) || s_[i_] == '.' || s_[i_] == '(')) return fail();   // "2048game", "1.2.3", "2(3)"
            return true;
        }
        if (!isAlpha(c)) return fail();
        size_t j = i_;
        while (j < s_.size() && isAlpha(s_[j])) ++j;
        const std::string name = s_.substr(i_, j - i_);
        if (name == "log" && j < s_.size() && s_[j] == '2' && (j + 1 >= s_.size() || !isDigit(s_[j + 1]))) {
            i_ = j + 1;
            return func("log2", v);
        }
        if (name == "log" && j + 1 < s_.size() && s_[j] == '1' && s_[j + 1] == '0' && (j + 2 >= s_.size() || !isDigit(s_[j + 2]))) {
            i_ = j + 2;
            return func("log", v);
        }
        if (j < s_.size() && isDigit(s_[j])) return fail();   // "x4", "f1", "ps5"
        i_ = j;
        if (name == "pi") { v = 3.14159265358979323846; return true; }
        if (name == "tau") { v = 6.28318530717958647692; return true; }
        if (name == "e") { v = 2.71828182845904523536; return true; }
        static const char* const fns[] = { "sqrt", "cbrt", "abs", "ln", "log", "exp", "sin", "cos", "tan",
            "floor", "ceil", "round" };
        for (const char* f : fns) if (name == f) return func(f, v);
        return fail();
    }
    bool func(const std::string& f, double& v)
    {
        ws();
        if (i_ < s_.size() && s_[i_] == '(') {
            if (++depth_ > kMaxDepth) return fail();
            ++i_;
            if (!expr(v)) return false;
            ws();
            if (i_ >= s_.size() || s_[i_] != ')') return fail();
            ++i_;
            --depth_;
        } else if (!unary(v)) return false;
        ++signals_;
        if (f == "sqrt") { if (v < 0) return fail(); v = std::sqrt(v); }
        else if (f == "cbrt") v = std::cbrt(v);
        else if (f == "abs") v = std::fabs(v);
        else if (f == "ln") { if (v <= 0) return fail(); v = std::log(v); }
        else if (f == "log") { if (v <= 0) return fail(); v = std::log10(v); }
        else if (f == "log2") { if (v <= 0) return fail(); v = std::log2(v); }
        else if (f == "exp") v = std::exp(v);
        else if (f == "sin") v = std::sin(v);
        else if (f == "cos") v = std::cos(v);
        else if (f == "tan") v = std::tan(v);
        else if (f == "floor") v = std::floor(v);
        else if (f == "ceil") v = std::ceil(v);
        else if (f == "round") v = std::round(v);
        // sin(pi) = 1.2e-16: below 1e-12 of the operand scale it is zero
        if (std::fabs(v) < 1e-12 && (f == "sin" || f == "cos" || f == "tan")) v = 0;
        return finite(v);
    }
};

// Texts that parse as math but are not meant as math: dates, phone numbers, scores ("2024-01-05", "555-1234",
// "1/2/2024"), and a few phrases ("24/7", "9/11", "50/50").
inline bool looksLikeNotMath(const std::string& s)
{
    bool onlyDigitsDash = true, onlyDigitsSlash = true;
    int dashes = 0, slashes = 0;
    for (char c : s) {
        if (c == '-') ++dashes; else if (c == '/') ++slashes;
        if (!isDigit(c) && c != '-') onlyDigitsDash = false;
        if (!isDigit(c) && c != '/') onlyDigitsSlash = false;
    }
    if (onlyDigitsDash && dashes > 0) return true;           // never subtraction without spaces: dates, phones, scores
    if (onlyDigitsSlash && slashes == 2) {                   // 1/2/2024, 12/25/24 (not 100/10/5)
        const size_t a = s.find('/'), b = s.find('/', a + 1);
        const size_t n1 = a, n2 = b - a - 1, n3 = s.size() - b - 1;
        if (n1 >= 1 && n1 <= 2 && n2 >= 1 && n2 <= 2 && (n3 == 2 || n3 == 4)) return true;
    }
    static const char* const phrases[] = { "24/7", "9/11", "50/50", "4/20", "7/11", "20/20", "24/365", "1/1" };
    for (const char* p : phrases) if (s == p) return true;
    return false;
}

// --- units --------------------------------------------------------------------------------------------------------
enum Dim { Length = 1, Mass, Volume, Temperature, Data, Duration, Area, Speed };
struct Unit { const char* names; const char* symbol; int dim; double factor, offset; };
// factor / offset: base = value * factor + offset (base: metre, kilogram, litre, kelvin, byte, second, m^2, m/s).
// US customary volumes. Names: '|'-separated, lowercase; two-word names have one space.
inline const std::vector<Unit>& units()
{
    static const std::vector<Unit> t = {
        { "mm|millimeter|millimeters|millimetre|millimetres", "mm", Length, 0.001, 0 },
        { "cm|centimeter|centimeters|centimetre|centimetres", "cm", Length, 0.01, 0 },
        { "m|meter|meters|metre|metres", "m", Length, 1, 0 },
        { "km|kilometer|kilometers|kilometre|kilometres", "km", Length, 1000, 0 },
        { "in|inch|inches|\"", "in", Length, 0.0254, 0 },
        { "ft|foot|feet|'", "ft", Length, 0.3048, 0 },
        { "yd|yard|yards", "yd", Length, 0.9144, 0 },
        { "mi|mile|miles", "mi", Length, 1609.344, 0 },
        { "nmi|nautical mile|nautical miles", "nmi", Length, 1852, 0 },
        { "mg|milligram|milligrams", "mg", Mass, 1e-6, 0 },
        { "g|gram|grams|gramme|grammes", "g", Mass, 0.001, 0 },
        { "kg|kilo|kilos|kilogram|kilograms", "kg", Mass, 1, 0 },
        { "t|tonne|tonnes|metric ton|metric tons", "t", Mass, 1000, 0 },
        { "oz|ounce|ounces", "oz", Mass, 0.028349523125, 0 },
        { "lb|lbs|pound|pounds", "lb", Mass, 0.45359237, 0 },
        { "st|stone|stones", "st", Mass, 6.35029318, 0 },
        { "ml|milliliter|milliliters|millilitre|millilitres", "ml", Volume, 0.001, 0 },
        { "cl|centiliter|centiliters|centilitre|centilitres", "cl", Volume, 0.01, 0 },
        { "l|liter|liters|litre|litres", "L", Volume, 1, 0 },
        { "gal|gallon|gallons", "gal", Volume, 3.785411784, 0 },
        { "qt|quart|quarts", "qt", Volume, 0.946352946, 0 },
        { "pt|pint|pints", "pt", Volume, 0.473176473, 0 },
        { "cup|cups", "cups", Volume, 0.2365882365, 0 },
        { "floz|fl oz|fluid ounce|fluid ounces", "fl oz", Volume, 0.0295735295625, 0 },
        { "tbsp|tablespoon|tablespoons", "tbsp", Volume, 0.01478676478125, 0 },
        { "tsp|teaspoon|teaspoons", "tsp", Volume, 0.00492892159375, 0 },
        { "c|celsius|centigrade", "\xC2\xB0" "C", Temperature, 1, 273.15 },
        { "f|fahrenheit", "\xC2\xB0" "F", Temperature, 5.0 / 9.0, 459.67 * 5.0 / 9.0 },
        { "k|kelvin|kelvins", "K", Temperature, 1, 0 },
        { "bit|bits", "bits", Data, 0.125, 0 },
        { "kbit|kilobit|kilobits", "kbit", Data, 125, 0 },
        { "mbit|megabit|megabits", "Mbit", Data, 125e3, 0 },
        { "gbit|gigabit|gigabits", "Gbit", Data, 125e6, 0 },
        { "b|byte|bytes", "B", Data, 1, 0 },
        { "kb|kilobyte|kilobytes", "kB", Data, 1e3, 0 },
        { "mb|megabyte|megabytes", "MB", Data, 1e6, 0 },
        { "gb|gigabyte|gigabytes", "GB", Data, 1e9, 0 },
        { "tb|terabyte|terabytes", "TB", Data, 1e12, 0 },
        { "pb|petabyte|petabytes", "PB", Data, 1e15, 0 },
        { "kib|kibibyte|kibibytes", "KiB", Data, 1024.0, 0 },
        { "mib|mebibyte|mebibytes", "MiB", Data, 1048576.0, 0 },
        { "gib|gibibyte|gibibytes", "GiB", Data, 1073741824.0, 0 },
        { "tib|tebibyte|tebibytes", "TiB", Data, 1099511627776.0, 0 },
        { "ms|millisecond|milliseconds", "ms", Duration, 0.001, 0 },
        { "s|sec|secs|second|seconds", "s", Duration, 1, 0 },
        { "min|mins|minute|minutes", "min", Duration, 60, 0 },
        { "h|hr|hrs|hour|hours", "h", Duration, 3600, 0 },
        { "d|day|days", "days", Duration, 86400, 0 },
        { "wk|week|weeks", "weeks", Duration, 604800, 0 },
        { "yr|yrs|year|years", "years", Duration, 31536000, 0 },   // 365 days
        { "m2|sq m|square meter|square meters|square metre|square metres", "m\xC2\xB2", Area, 1, 0 },
        { "km2|sq km|square kilometer|square kilometers|square kilometre|square kilometres", "km\xC2\xB2", Area, 1e6, 0 },
        { "ft2|sq ft|square foot|square feet", "sq ft", Area, 0.09290304, 0 },
        { "in2|sq in|square inch|square inches", "sq in", Area, 0.00064516, 0 },
        { "mi2|sq mi|square mile|square miles", "sq mi", Area, 2589988.110336, 0 },
        { "acre|acres", "acres", Area, 4046.8564224, 0 },
        { "ha|hectare|hectares", "ha", Area, 10000, 0 },
        { "km/h|kmh|kph|kmph", "km/h", Speed, 1000.0 / 3600.0, 0 },
        { "mph|mi/h", "mph", Speed, 0.44704, 0 },
        { "m/s|mps", "m/s", Speed, 1, 0 },
        { "kn|kt|knot|knots", "knots", Speed, 1852.0 / 3600.0, 0 },
    };
    return t;
}
inline const Unit* findUnit(const std::string& name)
{
    for (const Unit& u : units()) {
        const char* p = u.names;
        while (*p) {
            const char* q = p;
            while (*q && *q != '|') ++q;
            if (name.size() == size_t(q - p) && name.compare(0, name.size(), p, size_t(q - p)) == 0) return &u;
            p = *q ? q + 1 : q;
        }
    }
    return nullptr;
}

struct Token { bool num = false; double v = 0; std::string text; };
// Numbers (a sign only as the very first token), words ([a-z][a-z0-9/]*), and the single characters ' " : + - = >.
inline bool tokenize(const std::string& s, std::vector<Token>& out)
{
    out.clear();
    for (size_t i = 0; i < s.size();) {
        const char c = s[i];
        if (c == ' ') { ++i; continue; }
        if (int(out.size()) >= kMaxTokens) return false;
        Token t;
        const bool signedStart = out.empty() && (c == '-' || c == '+') && i + 1 < s.size() && (isDigit(s[i + 1]) || s[i + 1] == '.');
        if (isDigit(c) || (c == '.' && i + 1 < s.size() && isDigit(s[i + 1])) || signedStart) {
            const size_t st = i;
            if (signedStart) ++i;
            double v;
            if (!readNumber(s, i, v, false)) return false;
            if (i < s.size() && s[i] == '.') return false;    // "1.2.3"
            t.num = true; t.v = c == '-' ? -v : v; t.text = s.substr(st, i - st);
        } else if (isAlpha(c)) {
            const size_t st = i;
            while (i < s.size() && (isAlpha(s[i]) || isDigit(s[i]) || s[i] == '/')) ++i;
            t.text = s.substr(st, i - st);
        } else if (c == '\'' || c == '"' || c == ':' || c == '+' || c == '-' || c == '=' || c == '>') {
            if (c == '-' && i + 1 < s.size() && s[i + 1] == '>') { t.text = "->"; i += 2; }
            else { t.text = std::string(1, c); ++i; }
        } else return false;
        out.push_back(std::move(t));
    }
    return !out.empty();
}

inline bool isConnector(const std::string& w) { return w == "in" || w == "to" || w == "into" || w == "as" || w == "=" || w == "->"; }

// A unit made of tokens [a, b): one or two words.
inline const Unit* unitAt(const std::vector<Token>& t, size_t a, size_t b)
{
    if (b - a == 1 && !t[a].num) return findUnit(t[a].text);
    if (b - a == 2 && !t[a].num && !t[a + 1].num) return findUnit(t[a].text + " " + t[a + 1].text);
    return nullptr;
}

// "(number unit)+ connector unit"; compound quantities ("3 ft 4 in", "1 h 30 min") add up, not for temperatures.
inline bool convert(const std::vector<Token>& t, Answer& out)
{
    if (t.size() < 4 || !t[0].num) return false;
    for (size_t k = t.size() - 1; k >= 2; --k) {   // the last connector that leaves a unit on its right
        if (t[k].num || !isConnector(t[k].text)) continue;
        const Unit* to = unitAt(t, k + 1, t.size());
        if (!to) continue;
        // the left side: number unit [number unit]...
        double base = 0;
        int dim = 0, pairs = 0;
        size_t i = 0;
        bool good = true;
        std::string from;
        while (i < k) {
            if (!t[i].num || (i > 0 && t[i].v < 0)) { good = false; break; }
            const Unit* u = nullptr;
            size_t n = 0;
            if (i + 2 <= k && (u = unitAt(t, i + 1, i + 2))) n = 1;
            if (i + 3 <= k && (i + 3 == k || t[i + 3].num) && unitAt(t, i + 1, i + 3)) { u = unitAt(t, i + 1, i + 3); n = 2; }
            if (!u) { good = false; break; }
            if (dim && u->dim != dim) { good = false; break; }
            dim = u->dim;
            base += t[i].v * u->factor + u->offset;
            from += (from.empty() ? "" : " ") + format(t[i].v, 12) + " " + u->symbol;
            ++pairs;
            i += 1 + n;
        }
        if (!good || !pairs || dim != to->dim) continue;
        if (dim == Temperature && pairs > 1) return false;
        const double v = (base - to->offset) / to->factor;
        if (!std::isfinite(v) || std::fabs(v) > 1e300) return false;
        if (dim == Temperature && base < -1e-9) return false;   // below absolute zero
        const std::string n = format(v, 6);
        if (n.empty()) return false;
        out.kind = Units;
        out.value = n + " " + to->symbol;
        out.title = "= " + out.value;
        out.detail = from + " in " + to->symbol;
        return true;
    }
    return false;
}

// --- time zones ---------------------------------------------------------------------------------------------------
// Fixed abbreviations (a standard-time name is its standard offset all year: "pst" is UTC-8 even in July; "pdt"
// is UTC-7). Generic "pt" / "et" (DST-dependent) are not accepted. utc / gmt with an offset: "utc+5:30", "gmt-3".
struct Zone { const char* name; int minutes; };
inline const std::vector<Zone>& zones()
{
    static const std::vector<Zone> z = {
        { "utc", 0 }, { "gmt", 0 }, { "wet", 0 }, { "west", 60 }, { "bst", 60 }, { "cet", 60 }, { "cest", 120 },
        { "eet", 120 }, { "eest", 180 }, { "msk", 180 }, { "ist", 330 }, { "pkt", 300 }, { "ict", 420 },
        { "sgt", 480 }, { "hkt", 480 }, { "awst", 480 }, { "jst", 540 }, { "kst", 540 }, { "acst", 570 },
        { "acdt", 630 }, { "aest", 600 }, { "aedt", 660 }, { "nzst", 720 }, { "nzdt", 780 },
        { "hst", -600 }, { "akst", -540 }, { "akdt", -480 }, { "pst", -480 }, { "pdt", -420 }, { "mst", -420 },
        { "mdt", -360 }, { "cst", -360 }, { "cdt", -300 }, { "est", -300 }, { "edt", -240 }, { "ast", -240 },
        { "adt", -180 }, { "nst", -210 }, { "ndt", -150 }, { "brt", -180 }, { "art", -180 },
    };
    return z;
}
// A zone at t[i]: sets minutes east of UTC and the label; advances i.
inline bool zoneAt(const std::vector<Token>& t, size_t& i, int& minutes, std::string& label)
{
    if (i >= t.size() || t[i].num) return false;
    for (const Zone& z : zones()) {
        if (t[i].text != z.name) continue;
        minutes = z.minutes;
        label = t[i].text;
        for (char& c : label) c = char(c - 32);
        ++i;
        if ((t[i - 1].text == "utc" || t[i - 1].text == "gmt") && i + 1 < t.size() && !t[i].num && (t[i].text == "+" || t[i].text == "-") && t[i + 1].num) {
            const bool neg = t[i].text == "-";
            const std::string& h = t[i + 1].text;
            int hh = 0, mm = 0;
            if (h.find('.') != std::string::npos || h.size() > 2) return false;
            hh = std::stoi(h);
            size_t j = i + 2;
            if (j + 1 < t.size() && t[j].text == ":" && t[j + 1].num && t[j + 1].text.size() == 2 && t[j + 1].text.find('.') == std::string::npos) {
                mm = std::stoi(t[j + 1].text);
                j += 2;
            }
            if (hh > 14 || mm > 59 || (mm != 0 && mm != 30 && mm != 45)) return false;
            minutes = (neg ? -1 : 1) * (hh * 60 + mm);
            label += (neg ? "-" : "+") + std::to_string(hh) + (mm ? ":" + std::to_string(mm) : "");
            i = j;
        }
        return true;
    }
    return false;
}
inline bool isIntText(const std::string& s, size_t maxLen)
{
    if (s.empty() || s.size() > maxLen) return false;
    for (char c : s) if (!isDigit(c)) return false;
    return true;
}
inline std::string clock(int minutesOfDay, bool twelve)
{
    const int h = minutesOfDay / 60, m = minutesOfDay % 60;
    char b[16];
    if (twelve) snprintf(b, sizeof(b), "%d:%02d %s", h % 12 == 0 ? 12 : h % 12, m, h < 12 ? "AM" : "PM");
    else snprintf(b, sizeof(b), "%02d:%02d", h, m);
    return b;
}
// time [zone] (in|to) (zone | my time | local [time] | my time zone | my timezone); at least one explicit zone;
// the time needs am / pm, a colon, "noon" or "midnight" ("9 pst" is not a time).
inline bool timeZone(const std::vector<Token>& t, bool localKnown, int localMinutes, Answer& out)
{
    size_t i = 0;
    int minutes = 0;
    bool twelve = false;
    if (i < t.size() && !t[i].num && (t[i].text == "noon" || t[i].text == "midnight")) {
        minutes = t[i].text == "noon" ? 720 : 0; twelve = true; ++i;
    } else {
        if (i >= t.size() || !t[i].num || !isIntText(t[i].text, 2)) return false;
        int h = std::stoi(t[i].text), m = 0;
        ++i;
        bool colon = false;
        if (i + 1 < t.size() && t[i].text == ":" && t[i + 1].num && isIntText(t[i + 1].text, 2) && t[i + 1].text.size() == 2) {
            m = std::stoi(t[i + 1].text); colon = true; i += 2;
        }
        if (i < t.size() && !t[i].num && (t[i].text == "am" || t[i].text == "pm")) {
            if (h < 1 || h > 12) return false;
            h = (h % 12) + (t[i].text == "pm" ? 12 : 0);
            twelve = true; ++i;
        } else if (!colon || h > 23) return false;
        if (m > 59) return false;
        minutes = h * 60 + m;
    }
    int from = 0;
    std::string fromLabel;
    const bool hasFrom = zoneAt(t, i, from, fromLabel);
    if (i >= t.size() || t[i].num || (t[i].text != "in" && t[i].text != "to")) return false;
    ++i;
    int to = 0;
    std::string toLabel;
    bool toLocal = false;
    if (!zoneAt(t, i, to, toLabel)) {
        std::string rest;
        for (size_t j = i; j < t.size(); ++j) rest += (rest.empty() ? "" : " ") + t[j].text;
        if (rest == "my time" || rest == "local" || rest == "local time" || rest == "my time zone" || rest == "my timezone") toLocal = true;
        else return false;
        i = t.size();
    }
    if (i != t.size()) return false;
    if (!hasFrom && toLocal) return false;
    if ((!hasFrom || toLocal) && !localKnown) return false;   // the console's offset is unknown: no answer
    if (!hasFrom) { from = localMinutes; fromLabel = "your time"; }
    if (toLocal) { to = localMinutes; toLabel = "your time"; }
    const int total = minutes - from + to;
    const int day = total >= 0 ? total / 1440 : -((-total + 1439) / 1440);
    const int mod = total - day * 1440;
    out.kind = TimeZone;
    out.value = clock(mod, twelve);
    out.title = "= " + out.value + " " + toLabel + (day > 0 ? " (next day)" : day < 0 ? " (previous day)" : "");
    out.detail = clock(minutes, twelve) + " " + fromLabel;
    return true;
}

// --- entry ----------------------------------------------------------------------------------------------------------
// localKnown / localMinutes: the console's UTC offset (minutes east), only for "my time" / "in pst" from local.
inline bool answer(const std::string& text, Answer& out, bool localKnown = false, int localMinutes = 0)
{
    out = Answer();
    std::string s;
    if (!normalise(text, s)) return false;
    if (s.find("://") != std::string::npos || s.rfind("www.", 0) == 0) return false;
    bool digit = false;
    for (char c : s) if (isDigit(c)) { digit = true; break; }
    std::vector<Token> t;
    if ((digit || s.find("noon") != std::string::npos || s.find("midnight") != std::string::npos) && tokenize(s, t)) {
        if (timeZone(t, localKnown, localMinutes, out)) return true;
        out = Answer();
        if (convert(t, out)) return true;
        out = Answer();
    }
    if (looksLikeNotMath(s)) return false;   // (a calculation needs an operator or a function: "pi" alone is no answer)
    double v;
    Calculator c(s);
    if (!c.run(v)) return false;
    const std::string n = format(v, 12);
    if (n.empty()) return false;
    out.kind = Calc;
    out.value = n;
    out.title = "= " + n;
    out.detail = "Calculator";
    return true;
}

} // namespace OmniQuickAnswers
