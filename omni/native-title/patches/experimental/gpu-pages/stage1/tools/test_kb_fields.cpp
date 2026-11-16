// OMNI_KB_FIELDS_V1 host tests: g++ -std=c++20 -Wall -Wextra -I. test_kb_fields.cpp -o t && ./t   (in tools/)
#include "OmniKbFields.h"
#include <cmath>
#include <cstdio>
#include <set>
#include <string>

namespace F = OmniKbFields;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

static bool has(const std::vector<F::Key>& row, const char* label, int kind)
{
    for (const auto& k : row) if (std::string(k.label) == label && k.kind == kind) return true;
    return false;
}

int main()
{
    // hasToken
    CHECK(F::hasToken("one-time-code", "one-time-code"));
    CHECK(F::hasToken("section-login  one-time-code", "one-time-code"));
    CHECK(!F::hasToken("one-time-codes", "one-time-code"));
    CHECK(!F::hasToken("", "one-time-code"));
    CHECK(!F::hasToken("off", "one-time-code"));

    // padKind: type, inputmode, autocomplete
    CHECK(F::padKind("input", "tel", "", "") == F::kTel);
    CHECK(F::padKind("input", "number", "", "") == F::kDecimal);
    CHECK(F::padKind("input", "text", "numeric", "") == F::kDigits);
    CHECK(F::padKind("input", "text", "decimal", "") == F::kDecimal);
    CHECK(F::padKind("input", "text", "tel", "") == F::kTel);
    CHECK(F::padKind("input", "text", "", "one-time-code") == F::kCode);
    CHECK(F::padKind("input", "", "", "one-time-code") == F::kCode);
    CHECK(F::padKind("input", "number", "", "one-time-code") == F::kCode);
    CHECK(F::padKind("input", "tel", "numeric", "one-time-code") == F::kCode);
    CHECK(F::padKind("input", "text", "text", "one-time-code") == F::kNone);       // alphanumeric codes keep letters
    CHECK(F::padKind("input", "password", "numeric", "one-time-code") == F::kNone); // passwords keep Show / Hide
    CHECK(F::padKind("input", "email", "", "one-time-code") == F::kNone);
    CHECK(F::padKind("input", "number", "text", "") == F::kNone);                  // inputmode wins
    CHECK(F::padKind("input", "text", "", "") == F::kNone);
    CHECK(F::padKind("input", "search", "", "") == F::kNone);
    CHECK(F::padKind("textarea", "textarea", "numeric", "") == F::kNone);
    CHECK(F::padKind("ce", "contenteditable", "tel", "") == F::kNone);
    CHECK(F::padKind("none", "", "", "") == F::kNone);

    // settle: with the shell's field kind
    CHECK(F::settle(F::kCode, false, true) == F::kCode);        // text input with one-time-code -> pad
    CHECK(F::settle(F::kCode, true, false) == F::kCode);
    CHECK(F::settle(F::kCode, false, false) == F::kNone);       // e.g. an e-mail field
    CHECK(F::settle(F::kTel, true, false) == F::kTel);
    CHECK(F::settle(F::kDigits, true, false) == F::kDigits);
    CHECK(F::settle(F::kNone, true, false) == F::kDecimal);     // number field the attributes didn't name
    CHECK(F::settle(F::kTel, false, true) == F::kNone);
    CHECK(F::settle(F::kNone, false, true) == F::kNone);
    CHECK(F::settle(-3, true, false) == F::kDecimal);
    CHECK(F::settle(99, false, false) == F::kNone);

    // Tables: every row is 10 units wide and non-empty; 0-9 exactly once in the grid; Delete / Done reachable.
    for (int p = F::kDigits; p < F::kPadCount; ++p) {
        std::multiset<std::string> digits;
        for (int r = 0; r < 4; ++r) {
            const auto row = F::gridRow(p, r);
            CHECK(row.size() == 3);
            CHECK(std::fabs(F::units(row) - 10.f) < 0.01f);
            for (const auto& k : row) if (k.kind == F::kInsert && k.label[0] >= '0' && k.label[0] <= '9' && !k.label[1]) digits.insert(k.label);
        }
        CHECK(digits.size() == 10);
        for (char c = '0'; c <= '9'; ++c) CHECK(digits.count(std::string(1, c)) == 1);
        const auto q = F::quickRow(p);
        CHECK(!q.empty());
        CHECK(std::fabs(F::units(q) - 10.f) < 0.01f);
        CHECK(has(q, "Paste", F::kPaste));
        CHECK(has(q, "Clips", F::kClips));
        for (const auto& k : q) CHECK(k.kind != F::kInsert || std::string(k.label).size() == 1);
    }
    const auto act = F::actionRow();
    CHECK(std::fabs(F::units(act) - 10.f) < 0.01f);
    CHECK(has(act, "Delete", F::kDelete));
    CHECK(has(act, "Done", F::kDone));
    CHECK(has(act, "ABC", F::kLayer));
    CHECK(has(act, "Close", F::kClose));
    CHECK(has(act, "Edit", F::kTools));
    // tel: + * #
    CHECK(has(F::gridRow(F::kTel, 3), "*", F::kInsert));
    CHECK(has(F::gridRow(F::kTel, 3), "#", F::kInsert));
    CHECK(has(F::quickRow(F::kTel), "+", F::kInsert));
    // codes and digits: Delete and Done beside the 0, like a phone's PIN pad
    for (int p : { int(F::kCode), int(F::kDigits) }) {
        const auto r3 = F::gridRow(p, 3);
        CHECK(r3[0].kind == F::kDelete && std::string(r3[1].label) == "0" && r3[2].kind == F::kDone);
    }
    CHECK(has(F::gridRow(F::kDecimal, 3), ".", F::kInsert));
    CHECK(has(F::gridRow(F::kDecimal, 3), "-", F::kInsert));
    CHECK(F::quickRow(F::kCode).size() == 2);   // codes: nothing to type but digits

    std::printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
