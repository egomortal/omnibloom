// OMNI_PW_LOCK_V1: host tests for engine/entry/OmniPwLock.h (pure part of "Lock passwords and autofill").
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pw_lock.cpp -o t && ./t
//   with the real KDF too:  g++ -std=c++20 -Wall -Wextra -DOPWL_TEST_OPENSSL -I<tree>/engine/entry test_pw_lock.cpp -lcrypto -o t && ./t
#include "OmniPwLock.h"
#include <cstdio>
#ifdef OPWL_TEST_OPENSSL
#include "OmniVault.h"
#endif

namespace L = OmniPwLock;
namespace P = OmniParental;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n   got  [%s]\n   want [%s]\n", __FILE__, __LINE__, #a, x_.c_str(), y_.c_str()); } } while (0)

static int kdfCalls = 0, lastIterations = 0;
static bool fakeKdf(const std::string& pin, const std::string& salt, int it, uint8_t out[32])
{
    ++kdfCalls; lastIterations = it;
    for (int i = 0; i < 32; ++i) out[i] = uint8_t(i * 7 + it);
    for (size_t i = 0; i < pin.size(); ++i) out[i % 32] ^= uint8_t(pin[i] * 31 + i);
    for (size_t i = 0; i < salt.size(); ++i) out[(i + 5) % 32] ^= uint8_t(salt[i]);
    return true;
}
static P::Pin pinOf(const std::string& digits, char saltByte)
{
    P::Pin p;
    const bool ok = P::makePin(digits, std::string(16, saltByte), P::kDefaultIterations, fakeKdf, &p);
    CHECK(ok);
    return p;
}

int main()
{
    const int64_t T0 = 5'000'000;   // an arbitrary steady_clock reading (ms)

    // --- unlock window: 10 minutes from the right PIN, monotonic ---------------------------------------------------------
    {
        L::Window w;
        CHECK(!w.isOpen(T0));
        w.open(T0);
        CHECK(w.isOpen(T0));
        CHECK(w.isOpen(T0 + L::kUnlockMs - 1));
        CHECK(!w.isOpen(T0 + L::kUnlockMs));
        CHECK(w.leftMs(T0 + 60'000) == L::kUnlockMs - 60'000);
        CHECK(w.leftMs(T0 + L::kUnlockMs + 5) == 0);
        CHECK(!w.isOpen(T0 - 1));            // a clock that went backwards closes it (never extends it)
        w.close();
        CHECK(!w.isOpen(T0 + 1));
        CHECK(L::kUnlockMs == 600'000);
    }

    // --- limiter: attempt count + monotonic wait ---------------------------------------------------------------------
    {
        CHECK(L::waitFor(0) == 0 && L::waitFor(4) == 0);
        CHECK(L::waitFor(5) == 60'000);
        CHECK(L::waitFor(6) == 120'000);
        CHECK(L::waitFor(9) == 960'000);
        CHECK(L::waitFor(10) == L::kMaxWaitMs);
        CHECK(L::waitFor(5000) == L::kMaxWaitMs);

        L::Limiter l;
        int64_t now = T0;
        for (int i = 0; i < 4; ++i) { CHECK(!l.failed(now)); CHECK(!l.locked(now)); now += 1000; }
        CHECK(l.triesLeft() == 1);
        CHECK(l.failed(now));                       // the 5th wrong PIN starts 1 minute
        CHECK(l.remainingMs(now) == 60'000);
        CHECK(l.locked(now + 59'999));
        CHECK(!l.locked(now + 60'000));
        now += 60'000;
        CHECK(l.failed(now));                       // 6th: 2 minutes
        CHECK(l.remainingMs(now + 1) == 119'999);
        // the console clock is not involved at all: only the monotonic `now` the shell passes
        l.succeeded();
        CHECK(l.fails == 0 && !l.locked(now) && l.triesLeft() == 5);
    }
    {   // a restart can't skip or shorten the wait: the count comes from the file, the wait starts over in full
        L::Store s; s.enabled = true; s.pin = pinOf("1234", 'a'); s.limiter.fails = 7;
        L::Store back = L::parse(L::serialize(s));
        CHECK(back.limiter.fails == 7);              // never cut back on reading (parental clamps to 4: a restart reset it)
        const int64_t boot = 42;                     // steady_clock restarts low after a reboot
        back.limiter.started(boot);
        CHECK(back.limiter.remainingMs(boot) == L::waitFor(7));
        CHECK(back.limiter.locked(boot + L::waitFor(7) - 1));
        L::Limiter fresh; fresh.fails = 3; fresh.started(boot);
        CHECK(!fresh.locked(boot));
        L::Limiter unknown; unknown.fails = 5;     // no started(): unknown start = a full wait from the first look
        CHECK(unknown.remainingMs(T0) == 60'000);
        CHECK(unknown.remainingMs(T0 - 10) == 60'000);   // backwards: full wait again, never shorter
    }
    {
        L::Limiter big; big.fails = L::kMaxStoredFails;
        big.failed(T0);
        CHECK(big.fails == L::kMaxStoredFails);
        L::Store s; s.limiter.fails = 123456;
        CHECK(L::parse(L::serialize(s)).limiter.fails == L::kMaxStoredFails);
    }

    // --- which PIN unlocks ---------------------------------------------------------------------------------------------
    {
        const P::Pin parental = pinOf("2468", 'p'), own = pinOf("1357", 'o');
        L::Store s;
        CHECK(L::pinFor(s, P::Pin()) == nullptr);
        CHECK(!L::active(s, parental));
        s.enabled = true;
        CHECK(!L::active(s, P::Pin()));             // on but no PIN anywhere: off (a damaged file fails open)
        s.pin = own;
        CHECK(L::pinFor(s, parental) == &s.pin);    // not linked: our own PIN even if parental has one
        s.linkParental = true; s.pin = parental;
        CHECK(L::pinFor(s, parental) == &parental);
        const P::Pin changed = pinOf("9999", 'q');  // parental's Change PIN carries over while linked
        CHECK(L::pinFor(s, changed) == &changed);
        CHECK(L::pinFor(s, P::Pin()) == &s.pin);    // parental.txt deleted: the copy keeps working
        CHECK(L::active(s, P::Pin()));
        CHECK(!L::startActive(s, P::Pin()));
        s.startLock = true;
        CHECK(L::startActive(s, P::Pin()));
        CHECK(L::samePin(parental, parental) && !L::samePin(parental, changed));
    }

    // --- checking a PIN: same work whether or not one is stored ------------------------------------------------------
    {
        const P::Pin p = pinOf("4321", 's');
        kdfCalls = 0;
        CHECK(L::verifyOrDummy(&p, "4321", fakeKdf));
        CHECK(kdfCalls == 1 && lastIterations == P::kDefaultIterations);
        kdfCalls = 0;
        CHECK(!L::verifyOrDummy(&p, "4320", fakeKdf));
        CHECK(kdfCalls == 1);
        kdfCalls = 0; lastIterations = 0;
        CHECK(!L::verifyOrDummy(nullptr, "4321", fakeKdf));   // no PIN stored: one derivation of the same cost anyway
        CHECK(kdfCalls == 1 && lastIterations == P::kDefaultIterations);
        kdfCalls = 0;
        P::Pin broken = p; broken.hashHex = "zz";
        CHECK(!L::verifyOrDummy(&broken, "4321", fakeKdf));
        CHECK(kdfCalls == 1);
        kdfCalls = 0;
        CHECK(!L::verifyOrDummy(&p, "12", fakeKdf));          // invalid input: still one derivation
        CHECK(kdfCalls == 1);
    }

    // --- pw-lock.txt -----------------------------------------------------------------------------------------------------
    {
        L::Store s; s.enabled = true; s.startLock = true; s.linkParental = true; s.pin = pinOf("8642", 'x'); s.limiter.fails = 2;
        const std::string text = L::serialize(s);
        EQ(text.substr(0, text.find('\n')), "omni-pw-lock\t1");
        CHECK(text.find("enabled\t1\n") != std::string::npos);
        CHECK(text.find("start\t1\n") != std::string::npos);
        CHECK(text.find("link\tparental\n") != std::string::npos);
        CHECK(text.find("pin\tpbkdf2-sha256\t100000\t" + s.pin.saltHex + "\t" + s.pin.hashHex + "\n") != std::string::npos);
        CHECK(text.find("fails\t2\n") != std::string::npos);
        CHECK(text.find("8642") == std::string::npos);        // the PIN itself is never written
        CHECK(s.pin.saltHex.size() == 32);                     // 16-byte salt
        bool ok = false;
        const L::Store back = L::parse(text, &ok);
        CHECK(ok);
        CHECK(back.enabled && back.startLock && back.linkParental && back.limiter.fails == 2);
        CHECK(L::samePin(back.pin, s.pin));
        CHECK(L::serialize(back) == text);                     // round trip
        std::string crlf;
        for (char c : text) { if (c == '\n') crlf += '\r'; crlf += c; }
        CHECK(L::serialize(L::parse(crlf)) == text);           // CRLF (edited on a PC) reads the same

        CHECK(L::serialize(L::Store()) == "omni-pw-lock\t1\nenabled\t0\nstart\t0\n");
        ok = true;
        const L::Store other = L::parse("omni-parental\t1\nenabled\t1\n", &ok);   // another header: off
        CHECK(!ok && !other.enabled);
        CHECK(!L::parse("", &ok).enabled && !ok);
        const L::Store bad = L::parse("omni-pw-lock\t1\nenabled\t1\npin\tpbkdf2-sha256\t100000\tnothex\tzz\nfails\t-3\n", &ok);
        CHECK(ok && bad.enabled && !bad.pin.ok() && bad.limiter.fails == 0);
        CHECK(!L::active(bad, P::Pin()));                       // damaged PIN record: lock off
        const L::Store weak = L::parse("omni-pw-lock\t1\npin\tpbkdf2-sha256\t5\t" + std::string(32, 'a') + "\t" + std::string(64, 'b') + "\n");
        CHECK(!weak.pin.ok());                                  // too few rounds is not a PIN
    }

    // --- texts -------------------------------------------------------------------------------------------------------------
    EQ(L::padForgot(), "Forgot? Reset from Omnibloom Setup");
    EQ(L::waitText(60'000), "Too many wrong PINs. Try again in 1:00");
    EQ(L::waitText(119'001), "Too many wrong PINs. Try again in 2:00");
    EQ(L::waitText(1), "Too many wrong PINs. Try again in 0:01");
    EQ(L::triesText(1), "Wrong PIN: 1 try left");
    EQ(L::triesText(3), "Wrong PIN: 3 tries left");
    EQ(L::padTitle(L::kWhyStart), "Enter the PIN to open Omni");
    CHECK(L::rowDetail(L::Store(), P::Pin()).find("doesn't encrypt") != std::string::npos);

#ifdef OPWL_TEST_OPENSSL
    {   // the real KDF the shell uses (OmniVault::deriveKey) with OmniVault::randomBytes salt
        std::string salt(16, '\0');
        CHECK(OmniVault::randomBytes(&salt[0], 16));
        P::Pin p;
        CHECK(P::makePin("2468", salt, P::kMinIterations, OmniVault::deriveKey, &p));
        CHECK(L::verifyOrDummy(&p, "2468", OmniVault::deriveKey));
        CHECK(!L::verifyOrDummy(&p, "2469", OmniVault::deriveKey));
        CHECK(!L::verifyOrDummy(nullptr, "2468", OmniVault::deriveKey));
        L::Store s; s.enabled = true; s.pin = p;
        CHECK(L::verifyOrDummy(L::pinFor(L::parse(L::serialize(s)), P::Pin()), "2468", OmniVault::deriveKey));
    }
#endif

    printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
