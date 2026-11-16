#!/usr/bin/env python3
r"""OMNI_PW_LOCK_V1 (2026-11-16): Browser settings > "Lock passwords and autofill" (+ "Also lock Omni at start").
Backlog E29 (shared family console). Honest label: it deters, it does not encrypt (the vault's own PIN on the
Passwords page is what encrypts the logins; this lock is a gate in front of the shell's password and autofill UI).

What the user sees
  - Browser settings, right after "Passwords / Autofill / Site permissions" (OMNI_FEATURES_V2 rows):
        Lock passwords and autofill   Off / On      row id 881
        Also lock Omni at start       Off / On      row id 882 (greyed while the lock is off)
    The first On reuses the PARENTAL PIN when one is set (OMNI_PARENTAL_V1: the pad asks for it once); otherwise it
    asks for a new 4-6 digit PIN (typed twice). Turning either row off or changing "at start" needs the PIN (or an
    open unlock window).
  - While the lock is on, the PIN is asked once, then everything stays unlocked for 10 minutes (monotonic clock) or
    until Omni goes to the background (SDL_APP_WILLENTERBACKGROUND / DIDENTERBACKGROUND / window focus lost),
    whichever is first. When the window ends, open Passwords / Autofill / "Fill which login?" / Edit login panels
    are closed and a revealed password is hidden again. Asked for:
        opening Passwords (omniPwListShow, every entry point) and Autofill (omniAfPanelShow)
        filling a saved login (omniPwFillCurrent: keyboard strip, Site settings, Quick menu; omniPwFill: R1 on the
        list) and filling the form profile (omniAfFill)
        showing a saved password (Cross = reveal on the Passwords list; Triangle = Edit login shows it in the editor)
        omni:// pages: vault.status / vault.list answer "locked" (no logins listed) outside the window.
    Private tabs: unchanged by this patch (no new fill path; see the note at the end).
  - "Also lock Omni at start": the PIN pad shows BEFORE session restore. omniEverydayStart opens one blank tab (no
    URL, nothing loaded) and returns; an opaque cover (an overlay layer drawn below the pad, above the page and the
    bars) hides the shell; every button / click / scroll goes to the pad; any other panel or menu that opens is
    closed again; Circle can't dismiss it (the pad comes straight back). After the right PIN the restore runs, the
    blank tab becoming the first restored tab, so nothing from last time was ever loaded or visible before.
  - The pad is the parental pad (OmniParentalShell.h's omniParPadBuild: 3 x 4 grid, one dot per digit, never the
    digits; Square deletes, Triangle = OK) with its own submit, and its foot line says
        "Forgot? Reset from Omnibloom Setup"
    A forgotten PIN is only reset by Setup's Reset or by deleting /data/omni/pw-lock.txt (nothing in Omni resets it).

Hashing (same as parental, nothing new linked): OmniParental::makePin / verifyPin with OmniVault::deriveKey
(PBKDF2-HMAC-SHA256, 100,000 rounds), a 16-byte RAND_bytes salt (OmniVault::randomBytes), constant-time compare;
the PIN itself is never written. Timing: every check runs exactly one PBKDF2 of the default cost, also when no
usable PIN record exists (a dummy derivation on a zero salt, then "wrong"), so the time a PIN check takes says
nothing about whether a PIN is stored. The gates themselves only ask when the lock is on.

Rate limiting (fixes the parental review finding: parental's cooldown is console-clock time, so setting the clock
forward ends it). This lock counts attempts and measures waits on std::chrono::steady_clock (monotonic):
    wrong PINs 1-4: no wait; 5th wrong: 1 minute; every further wrong PIN doubles it (2, 4, 8, 16, then 30 min max)
    until a right PIN resets the count.
The count is persisted (fails\t<n> in pw-lock.txt, never cut back on reading); the end time is not (a monotonic
time means nothing after a restart). Restarting Omni with fails >= 5 starts the full wait again from the restart,
so neither a restart nor the console clock shortens it. While the PIN is the parental one, a wrong PIN also counts
on parental's limiter (and its wait is honoured), so the two pads together don't double the guessing rate.

Why a separate file (/data/omni/pw-lock.txt via omniIoQueue) and not parental.txt
  - OmniParental::parse keeps only the keys it knows and serialize rewrites the whole file: lines of ours in
    parental.txt would be dropped at parental's next write.
  - Separate resets: "forgot the parental PIN" (delete parental.txt) must not silently remove the password lock, and
    the other way round.
  - Sharing the PIN without sharing the file: "link\tparental" + a copy of the parental PIN record. While parental
    has a PIN, the lock checks THAT one (so parental's Change PIN carries over; the copy is refreshed after the next
    right PIN). If parental.txt is deleted, the copy keeps the lock working with the PIN the family knew.
    omni-pw-lock\t1 / enabled\t0|1 / start\t0|1 / link\tparental / pin\tpbkdf2-sha256\t<rounds>\t<salt hex>\t<hash hex>
    / fails\t<n>. Another header or a damaged / PIN-less file reads as "off" (fail open: the reset IS deleting it).

HONEST LIMITS: a 4-6 digit PIN; anyone with file access (FTP, PC Setup) can delete pw-lock.txt or brute-force the
copied hash offline. The lock gates Omni's own UI: the saved logins stay readable by anyone who can read the vault
files unless the vault PIN (Passwords > Set a PIN) is set. Self-test modes skip the lock entirely.
Note (checked 2026-11-16): the brief says private tabs never get autofill; in this tree omniF2FillItems /
omniAfFill / omniPwFillCurrent have no private-tab check (a private tab's keyboard strip offers "Fill login" and
"Fill form" like any tab). This patch keeps that behaviour unchanged and adds no fill path.

Pure part: engine/entry/OmniPwLock.h (unlock window, monotonic limiter, PIN choice, pw-lock.txt). Tested by
tools/test_pw_lock.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pw_lock.cpp -o t && ./t
    g++ -std=c++20 -Wall -Wextra -DOPWL_TEST_OPENSSL -I<tree>/engine/entry test_pw_lock.cpp -lcrypto -o t && ./t
Shell side: engine/entry/OmniPwLockShell.h (included from OmniFeatures3.h after OmniParentalShell.h).

Anchors (exactly once each; MARK makes each file idempotent; each file keeps its own line endings; inserted lines
use /* */ comments, nothing is appended after a line-prefix anchor):
  OmniBrowser.cpp        the OmniParental.h include (pure include after it); parental's omniParSettingsInput
                         declaration (ours after it); "omniPrefsLoad(); omniHistoryLoad();" in omniEverydayStart
                         (the start hold after them); the restore loop's newTab (the held tab first); the background
                         and focus lines of the event loop (omniPfFocus, OMNI_PAD_FEEDBACK_V1; ours after each).
  OmniBrowserSettings.h  the omniF2SettingsExtra call (rows after it); parental's omniParRowId input line (ours after).
  OmniPasswords.h        heads of omniPwFill, omniPwFillCurrent, omniPwListShow; the reveal and Edit lines.
  OmniAutofill.h         heads of omniAfFill and omniAfPanelShow.
  OmniPages.h            the vault.status / vault.list "locked" line (replaced: || omniPwlBridgeLocked()).
  OmniFeatures3.h        the OmniParentalShell.h include; the omniParTick line of omniF3Tick.
Apply AFTER apply_parental.py (its lines are anchors, its pad and PIN are reused). Refuses when row ids 881 / 882,
panel kind 7191 or the omniPwl / OPWL / OmniPwLock names are already used by another patch or the tree.
usage: apply_pw_lock.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PW_LOCK_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PW_LOCK_V1: the pure part of Browser settings > "Lock passwords and autofill" (no SDL, no WebKit, no OpenSSL).
// The shell side is OmniPwLockShell.h; the reasons are in tools/apply_pw_lock.py. Tested on the host with g++
// (test_pw_lock.cpp): the 10-minute unlock window, the wrong-PIN limiter on a monotonic clock (attempt count kept in
// the file, wait restarted after a restart), which PIN unlocks (parental's, or our own / the copy), the dummy-cost
// check when no PIN is stored, and pw-lock.txt parse / serialize. PIN hashing is OmniParental's (salt + PBKDF2 hash).
#pragma once
#include "OmniParental.h"
#include <cstdint>
#include <cstdio>
#include <string>

namespace OmniPwLock {

constexpr const char* kFileName = "pw-lock.txt";
constexpr const char* kHeader = "omni-pw-lock\t1";
constexpr long kMaxFileBytes = 4096;
constexpr int64_t kUnlockMs = 10LL * 60 * 1000;      // one right PIN: 10 minutes (or until Omni goes to the background)
constexpr int kFreeTries = 5;                         // wrong PINs before the first wait
constexpr int64_t kFirstWaitMs = 60LL * 1000;         // 5th wrong PIN: 1 minute, then doubling ...
constexpr int64_t kMaxWaitMs = 30LL * 60 * 1000;      // ... up to 30 minutes per try
constexpr int kMaxStoredFails = 9999;

enum Why { kWhyPasswords = 1, kWhyFill, kWhyShow, kWhyForm, kWhyAutofill, kWhySettings, kWhyStart };

// --- the unlock window (monotonic milliseconds, e.g. steady_clock) -----------------------------------------------------
struct Window {
    int64_t since = -1;
    void open(int64_t nowMs) { since = nowMs; }
    void close() { since = -1; }
    // A clock that went backwards (can't happen with steady_clock; defensive) closes the window.
    bool isOpen(int64_t nowMs) const { return since >= 0 && nowMs >= since && nowMs - since < kUnlockMs; }
    int64_t leftMs(int64_t nowMs) const { return isOpen(nowMs) ? kUnlockMs - (nowMs - since) : 0; }
};

// --- wrong-PIN limiter: attempt count (persisted) + monotonic wait (this run only) -------------------------------------
inline int64_t waitFor(int fails)
{
    if (fails < kFreeTries) return 0;
    int64_t w = kFirstWaitMs;
    for (int k = fails - kFreeTries; k > 0 && w < kMaxWaitMs; --k) w *= 2;
    return w < kMaxWaitMs ? w : kMaxWaitMs;
}
struct Limiter {
    int fails = 0;            // wrong PINs since the last right one (pw-lock.txt)
    int64_t lastFailMs = -1;  // monotonic time of the last wrong PIN (never written: meaningless after a restart)
    // After reading the file: a wait that was running starts over in full (a restart can't shorten it).
    void started(int64_t nowMs) { lastFailMs = fails >= kFreeTries ? nowMs : -1; }
    int64_t remainingMs(int64_t nowMs)
    {
        const int64_t w = waitFor(fails);
        if (!w) return 0;
        if (lastFailMs < 0 || nowMs < lastFailMs) lastFailMs = nowMs;   // unknown start / clock backwards: full wait from now
        const int64_t end = lastFailMs + w;
        return end > nowMs ? end - nowMs : 0;
    }
    bool locked(int64_t nowMs) { return remainingMs(nowMs) > 0; }
    // A wrong PIN. True: a wait starts now.
    bool failed(int64_t nowMs)
    {
        if (fails < kMaxStoredFails) ++fails;
        lastFailMs = nowMs;
        return waitFor(fails) > 0;
    }
    void succeeded() { fails = 0; lastFailMs = -1; }
    int triesLeft() const { return fails >= kFreeTries ? 0 : kFreeTries - fails; }
};

// --- the settings file -------------------------------------------------------------------------------------------------
struct Store {
    bool enabled = false, startLock = false;
    bool linkParental = false;    // the parental PIN unlocks while parental has one; `pin` is then its last copy
    OmniParental::Pin pin;        // our own PIN, or the copy of the parental one
    Limiter limiter;
};
inline bool samePin(const OmniParental::Pin& a, const OmniParental::Pin& b)
{
    return a.iterations == b.iterations && a.saltHex == b.saltHex && a.hashHex == b.hashHex;
}
// The record a typed PIN is checked against (nullptr: none usable).
inline const OmniParental::Pin* pinFor(const Store& s, const OmniParental::Pin& parental)
{
    if (s.linkParental && parental.ok()) return &parental;
    if (s.pin.ok()) return &s.pin;
    return nullptr;
}
inline bool active(const Store& s, const OmniParental::Pin& parental) { return s.enabled && pinFor(s, parental) != nullptr; }
inline bool startActive(const Store& s, const OmniParental::Pin& parental) { return active(s, parental) && s.startLock; }

// Always exactly one derivation of the default cost: with no usable record a dummy one runs and the answer is "wrong",
// so the time taken doesn't tell whether a PIN is stored.
template <class Kdf> inline bool verifyOrDummy(const OmniParental::Pin* p, const std::string& pin, Kdf kdf)
{
    if (p && p->ok() && OmniParental::validPin(pin)) return OmniParental::verifyPin(*p, pin, kdf);
    uint8_t key[32];
    const std::string salt(16, '\0');
    (void)kdf(OmniParental::validPin(pin) ? pin : std::string("000000"), salt, OmniParental::kDefaultIterations, key);
    for (auto& k : key) k = 0;
    return false;
}

inline Store parse(const std::string& text, bool* ok = nullptr)
{
    Store s;
    if (ok) *ok = false;
    size_t from = 0;
    bool first = true;
    while (from < text.size()) {
        size_t nl = text.find('\n', from);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(from, nl - from);
        from = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) { first = false; if (line != kHeader) return Store(); if (ok) *ok = true; continue; }
        const auto f = OmniParental::splitTabs(line);
        if (f.size() < 2) continue;
        const std::string& k = f[0];
        int64_t v = 0;
        if (k == "enabled") s.enabled = f[1] == "1";
        else if (k == "start") s.startLock = f[1] == "1";
        else if (k == "link") s.linkParental = f[1] == "parental";
        else if (k == "pin" && f.size() == 5 && f[1] == "pbkdf2-sha256" && OmniParental::parseInt64(f[2], &v)
                 && OmniParental::allHex(f[3]) && OmniParental::allHex(f[4])) {
            OmniParental::Pin p; p.iterations = int(v > OmniParental::kMaxIterations ? 0 : v); p.saltHex = f[3]; p.hashHex = f[4];
            if (p.ok()) s.pin = p;
        }
        else if (k == "fails" && OmniParental::parseInt64(f[1], &v)) s.limiter.fails = int(v > kMaxStoredFails ? kMaxStoredFails : v);   // never cut back
    }
    return s;
}
inline std::string serialize(const Store& s)
{
    std::string o = std::string(kHeader) + "\n";
    o += std::string("enabled\t") + (s.enabled ? "1" : "0") + "\n";
    o += std::string("start\t") + (s.startLock ? "1" : "0") + "\n";
    if (s.linkParental) o += "link\tparental\n";
    if (s.pin.ok()) o += "pin\tpbkdf2-sha256\t" + std::to_string(s.pin.iterations) + "\t" + s.pin.saltHex + "\t" + s.pin.hashHex + "\n";
    if (s.limiter.fails) o += "fails\t" + std::to_string(s.limiter.fails) + "\n";
    return o;
}

// --- texts -------------------------------------------------------------------------------------------------------------
inline std::string padTitle(int why)
{
    switch (why) {
    case kWhyPasswords: return "Enter the PIN to open Passwords";
    case kWhyFill: return "Enter the PIN to fill a saved login";
    case kWhyShow: return "Enter the PIN to show a saved password";
    case kWhyForm: return "Enter the PIN to fill the form";
    case kWhyAutofill: return "Enter the PIN to open Autofill";
    case kWhySettings: return "Enter the PIN to change the lock";
    case kWhyStart: return "Enter the PIN to open Omni";
    }
    return "Enter the PIN";
}
inline std::string padForgot() { return "Forgot? Reset from Omnibloom Setup"; }
inline std::string waitText(int64_t ms)
{
    const int64_t sec = (ms + 999) / 1000;
    char b[96];
    snprintf(b, sizeof b, "Too many wrong PINs. Try again in %lld:%02lld", (long long)(sec / 60), (long long)(sec % 60));
    return b;
}
inline std::string triesText(int left)
{
    return "Wrong PIN: " + std::to_string(left) + (left == 1 ? " try left" : " tries left");
}
inline std::string rowDetail(const Store& s, const OmniParental::Pin& parental)
{
    if (!active(s, parental)) return "PIN to open, fill or show saved logins. Deters, doesn't encrypt";
    return std::string(s.linkParental && parental.ok() ? "Parental PIN" : "Own PIN") + ", 10 min per unlock. Deters, doesn't encrypt";
}

} // namespace OmniPwLock
'''

SHELL = r'''// OMNI_PW_LOCK_V1: Browser settings > "Lock passwords and autofill" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniParentalShell.h: the pad, the parental PIN and its limiter are reused).
// The pure part is OmniPwLock.h; the reasons are in tools/apply_pw_lock.py. Main thread only; /data/omni/pw-lock.txt is
// written through omniIoQueue.
//   - omniPwlGate: the PIN once, then 10 minutes (steady_clock) or until the background; asked by the Passwords and
//     Autofill panels, every fill, reveal and Edit login (hooks in OmniPasswords.h / OmniAutofill.h).
//   - omniPwlStartHold: "Also lock Omni at start": a blank tab, an opaque cover and the pad before session restore.
#pragma once
#include <chrono>

namespace OPWL = OmniPwLock;
enum { omniPwlKindPad = 7191 };
static OPWL::Store omniPwlStore;
static bool omniPwlLoaded = false;
static OPWL::Window omniPwlWindow;
static bool omniPwlWasOpen = false;
static bool omniPwlStartLocked = false, omniPwlStartPassed = false;
static Tab* omniPwlHeld = nullptr;                 // the blank tab behind the start pad (becomes the first restored tab)
static int omniPwlPadMode = omniParPadVerify;
static std::function<void(bool)> omniPwlPadDone;

static int64_t omniPwlNowMs()
{
    return int64_t(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}
static void omniPwlLoad()
{
    if (omniPwlLoaded) return;
    omniPwlLoaded = true;
    omniParLoad();
    FILE* f = fopen(omniData(OPWL::kFileName).c_str(), "rb");
    if (f) {
        std::string text;
        char buf[1024];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OPWL::kMaxFileBytes) text.append(buf, n);
        fclose(f);
        bool ok = false;
        omniPwlStore = OPWL::parse(text, &ok);
        if (!ok) omniPwlStore = OPWL::Store();
    }
    omniPwlStore.limiter.started(omniPwlNowMs());
    fprintf(stderr, "OMNI PW LOCK: %s%s%s\n", OPWL::active(omniPwlStore, omniParStore.pin) ? "on" : "off",
            omniPwlStore.startLock ? ", at start" : "", omniPwlStore.limiter.fails ? ", wrong PINs pending" : ""); fflush(stderr);
}
static void omniPwlWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OPWL::kFileName), OPWL::serialize(omniPwlStore), false);
}
static bool omniPwlActive() { if (omniTestMode()) return false; omniPwlLoad(); return OPWL::active(omniPwlStore, omniParStore.pin); }
static bool omniPwlLinkedLive() { return omniPwlStore.linkParental && omniParStore.pin.ok(); }
static int64_t omniPwlWaitMs(int64_t now)
{
    int64_t w = omniPwlStore.limiter.remainingMs(now);
    if (omniPwlLinkedLive()) w = std::max<int64_t>(w, omniParStore.limiter.remaining(omniParNow()) * 1000);   // parental's own wait
    return w;
}
static bool omniPwlKindGuarded(int kind) { return kind == omniPwKindList || kind == omniPwKindChoose || kind == omniPwKindEdit || kind == omniAfKindPanel; }

// The window ended (10 minutes, background, Lock): guarded panels close, a revealed password is hidden.
static void omniPwlLockDown()
{
    const bool was = omniPwlWindow.since >= 0;
    omniPwlWindow.close();
    omniPwlWasOpen = false;
    if (!omniPwlActive()) return;
    omniPwRevealRow = -1;
    bool any = false;
    for (const auto& q : omniFxStack) any |= omniPwlKindGuarded(q.kind);
    if (!any) return;
    if (editing) dismissKeyboard();   // a password being typed into Edit login goes with its panel
    for (;;) {
        bool still = false;
        for (const auto& q : omniFxStack) still |= omniPwlKindGuarded(q.kind);
        if (!still || omniFxStack.empty()) break;
        omniFxPop();
    }
    if (was) notice("Passwords and autofill are locked again");
}
static void omniPwlBackground() { if (omniPwlLoaded && omniPwlWindow.since >= 0) { omniPwlLockDown(); fprintf(stderr, "OMNI PW LOCK: background, locked\n"); fflush(stderr); } }

// --- the PIN pad (parental's pad look: omniParPadBuild and its digit / note state; our own submit) ----------------
static void omniPwlStartRelease();
static void omniPwlPadFinish(bool ok)
{
    omniParWipeDigits();
    omniParPadNote.clear();
    std::function<void(bool)> done = std::move(omniPwlPadDone);
    omniPwlPadDone = nullptr;
    if (!omniFxStack.empty() && omniFxStack.back().kind == omniPwlKindPad) omniFxPop();
    if (done) done(ok);
}
static void omniPwlPadSubmit()
{
    if (!OPAR::validPin(omniParDigits)) { omniParPadNote = "Enter 4 to 6 digits"; return; }
    const int64_t now = omniPwlNowMs();
    if (omniPwlPadMode == omniParPadVerify) {
        const int64_t wait = omniPwlWaitMs(now);
        if (wait > 0) { omniParWipeDigits(); omniParPadNote = OPWL::waitText(wait); return; }
        const auto t0 = SDL_GetTicks();
        omniParLoad();
        const bool good = OPWL::verifyOrDummy(OPWL::pinFor(omniPwlStore, omniParStore.pin), omniParDigits, OmniVault::deriveKey);
        omniParWipeDigits();
        fprintf(stderr, "OMNI PW LOCK: PIN %s in %u ms\n", good ? "ok" : "wrong", SDL_GetTicks() - t0); fflush(stderr);
        if (good) {
            bool dirty = omniPwlStore.limiter.fails != 0;
            omniPwlStore.limiter.succeeded();
            if (omniPwlLinkedLive()) {
                if (omniParStore.limiter.fails || omniParStore.limiter.lockUntil) { omniParStore.limiter.succeeded(); omniParWrite(); }
                if (!OPWL::samePin(omniPwlStore.pin, omniParStore.pin)) { omniPwlStore.pin = omniParStore.pin; dirty = true; }   // parental's Change PIN
            }
            if (dirty && omniPwlStore.enabled) omniPwlWrite();
            omniPwlWindow.open(now);
            omniPwlWasOpen = true;
            const bool start = omniPwlStartLocked;
            omniPwlPadFinish(true);
            if (start) omniPwlStartRelease();
            return;
        }
        omniPwlStore.limiter.failed(now);
        if (omniPwlLinkedLive()) { omniParStore.limiter.failed(omniParNow()); omniParWrite(); }
        omniPwlWrite();   // the count survives a restart
        const int64_t w = omniPwlWaitMs(now);
        if (w > 0) {
            omniParPadNote = OPWL::waitText(w);
            if (!omniPwlStartLocked) { notice(omniParPadNote); omniPwlPadFinish(false); }
            return;
        }
        omniParPadNote = OPWL::triesText(omniPwlStore.limiter.triesLeft());
        return;
    }
    if (omniPwlPadMode == omniParPadNew) {
        omniParFirst = omniParDigits;
        OmniVault::wipe(omniParDigits);
        omniPwlPadMode = omniParPadAgain;
        omniParPadTitle = "Enter the new PIN again";
        omniParPadNote.clear();
        return;
    }
    if (omniParDigits != omniParFirst) {
        omniParWipeDigits();
        omniPwlPadMode = omniParPadNew;
        omniParPadTitle = "Choose a 4 to 6 digit PIN";
        omniParPadNote = "The PINs didn't match";
        return;
    }
    std::string salt(16, '\0');
    OPAR::Pin pin;
    const bool made = OmniVault::randomBytes(&salt[0], salt.size())
        && OPAR::makePin(omniParDigits, salt, OPAR::kDefaultIterations, OmniVault::deriveKey, &pin);
    OmniVault::wipe(salt);
    omniParWipeDigits();
    if (!made) { notice("Couldn't set the PIN (no random numbers available)"); omniPwlPadFinish(false); return; }
    omniPwlStore.pin = pin;
    omniPwlStore.linkParental = false;
    omniPwlStore.limiter.succeeded();
    omniPwlWindow.open(now);
    omniPwlWasOpen = true;
    omniPwlPadFinish(true);
}
static bool omniPwlPadInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b == SDL_CONTROLLER_BUTTON_X) { if (!omniParDigits.empty()) omniParDigits.pop_back(); return true; }   // Square: delete
    if (b == SDL_CONTROLLER_BUTTON_Y) { omniPwlPadSubmit(); return true; }                                    // Triangle: OK
    if (b != SDL_CONTROLLER_BUTTON_A) return true;   // nothing else reaches the page while the pad is up
    if (r.id >= omniParKey0 && r.id <= omniParKey0 + 9) {
        if (int(omniParDigits.size()) < OPAR::kPinMax) omniParDigits += char('0' + (r.id - omniParKey0));
        omniParPadNote.clear();
    } else if (r.id == omniParKeyDelete) { if (!omniParDigits.empty()) omniParDigits.pop_back(); }
    else if (r.id == omniParKeyOk) omniPwlPadSubmit();
    return true;
}
static void omniPwlPadPush(int mode, const std::string& title, std::function<void(bool)> done, bool start = false)
{
    if (editing) dismissKeyboard();   // a pad pushed from the page keyboard's fill strip would stay hidden behind it
    omniParWipeDigits();
    omniPwlPadMode = mode;
    omniParPadTitle = title;
    omniParPadNote.clear();
    omniPwlPadDone = std::move(done);
    OmniFxPanel p;
    p.kind = omniPwlKindPad;
    p.title = title; p.w = 560; p.cols = 3; p.rowH = 74; p.maxVisible = 4;
    p.build = omniParPadBuild; p.input = omniPwlPadInput;
    if (start) p.faces = { { 0, "Press" }, { 2, "Delete" }, { 3, "OK" } };
    else p.faces = { { 0, "Press" }, { 2, "Delete" }, { 3, "OK" }, { 1, "Cancel" } };
    p.extra = OPWL::padForgot();
    omniFxPush(std::move(p));
    if (mode == omniParPadVerify) { const int64_t w = omniPwlWaitMs(omniPwlNowMs()); if (w > 0) { omniParPadNote = OPWL::waitText(w); omniFxRefresh(); } }
}

// --- the gate --------------------------------------------------------------------------------------------------------
// False: go on (lock off, or unlocked). True: the pad (or the wait notice) took over; `then` runs after a right PIN.
static bool omniPwlGate(int why, std::function<void()> then)
{
    if (!omniPwlActive()) return false;
    const int64_t now = omniPwlNowMs();
    if (omniPwlWindow.isOpen(now)) return false;
    const int64_t wait = omniPwlWaitMs(now);
    if (wait > 0) { notice(OPWL::waitText(wait)); return true; }
    omniPwlPadPush(omniParPadVerify, OPWL::padTitle(why), [then](bool ok) { if (ok && then) then(); });
    return true;
}
static bool omniPwlBridgeLocked() { return omniPwlActive() && !omniPwlWindow.isOpen(omniPwlNowMs()); }

// --- "Also lock Omni at start" ------------------------------------------------------------------------------------------
static void omniPwlStartPad() { omniPwlPadPush(omniParPadVerify, OPWL::padTitle(OPWL::kWhyStart), nullptr, true); }
// From omniEverydayStart, before anything of the last session is read into tabs. True: held (restore runs after the PIN).
static bool omniPwlStartHold()
{
    if (omniPwlStartPassed || omniTestMode()) return false;
    omniPwlStartPassed = true;
    omniPwlLoad();
    if (!OPWL::startActive(omniPwlStore, omniParStore.pin)) return false;
    Tab* t = newTab();   // blank: no URL, nothing loaded; the cover hides it anyway
    if (!t) return false;
    omniPwlHeld = t;
    omniPwlStartLocked = true;
    omniPwlStartPad();
    fprintf(stderr, "OMNI PW LOCK: start held for the PIN (session not restored yet)\n"); fflush(stderr);
    return true;
}
// The restore loop's first tab: the held blank one (once), if it still exists.
static Tab* omniPwlTakeHeld()
{
    Tab* h = omniPwlHeld;
    if (!h || omniPwlStartLocked) return nullptr;
    omniPwlHeld = nullptr;
    for (const auto& t : tabs) if (t.get() == h) return h;
    return nullptr;
}
static void omniPwlStartRelease()
{
    omniPwlStartLocked = false;
    omniFxCloseAll();
    fprintf(stderr, "OMNI PW LOCK: start PIN ok, restoring the session\n"); fflush(stderr);
    omniEverydayStart();
    if (Tab* h = omniPwlTakeHeld()) omniOpenNewTabPage(h);   // the restore didn't need it
    omniShellDirty = true;
}
// The cover: first in the overlay list, so it is drawn under the pad (the FX panel layer) and over the page and bars,
// and asked first for input (everything goes to the pad).
static bool omniPwlCoverOpen() { return omniPwlStartLocked; }
static bool omniPwlCoverButton(int b) { if (omniFxPanelOpen()) omniFxButton(b); else omniPwlStartPad(); return true; }
static bool omniPwlCoverClick(int x, int y) { if (omniFxPanelOpen()) omniFxClick(x, y); return true; }
static bool omniPwlCoverScroll(double amount) { if (omniFxPanelOpen()) omniFxScroll(amount); return true; }
static void omniPwlCoverDraw()
{
    const OmniTheme& T = omniTheme();
    omniRectPx({ 0, 0, canvas->w, canvas->h }, T.bg, 255);
    omniLabel("Omni is locked", 640, 64, omniBodyBold, T.ink, 1);
}
[[maybe_unused]] static const bool omniPwlLayers = [] {
    auto& layers = omniOverlayLayers();
    layers.insert(layers.begin(), { omniPwlCoverOpen, omniPwlCoverButton, omniPwlCoverClick, omniPwlCoverScroll, omniPwlCoverDraw, true });
    return true;
}();

// --- Browser settings rows ------------------------------------------------------------------------------------------
static void omniPwlSettingsRows(OmniFxPanel& p)
{
    omniPwlLoad();
    const bool on = OPWL::active(omniPwlStore, omniParStore.pin);
    OmniFxRow r; r.id = omniPwlRowLock; r.label = "Lock passwords and autofill"; r.value = on ? "On" : "Off"; r.stepper = true;
    r.detail = OPWL::rowDetail(omniPwlStore, omniParStore.pin);
    p.rows.push_back(r);
    OmniFxRow s; s.id = omniPwlRowStart; s.label = "Also lock Omni at start"; s.value = on && omniPwlStore.startLock ? "On" : "Off";
    s.stepper = true; s.enabled = on; s.detail = "The PIN before your tabs come back";
    p.rows.push_back(s);
}
static bool omniPwlSettingsInput(int id, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A, side = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    if (!a && !side) return false;
    omniPwlLoad();
    const bool on = OPWL::active(omniPwlStore, omniParStore.pin);
    if (id == omniPwlRowStart) {
        if (!on) return true;
        auto flip = [] {
            omniPwlStore.startLock = !omniPwlStore.startLock; omniPwlWrite();
            notice(omniPwlStore.startLock ? "Omni asks for the PIN at start" : "Omni no longer asks for the PIN at start");
            omniFxRefresh();
        };
        if (!omniPwlGate(OPWL::kWhySettings, flip)) flip();
        return true;
    }
    if (on) {
        auto off = [] { omniPwlStore.enabled = false; omniPwlWrite(); omniPwlWindow.close(); notice("Passwords and autofill are no longer locked (the PIN is kept)"); omniFxRefresh(); };
        if (!omniPwlGate(OPWL::kWhySettings, off)) off();
        return true;
    }
    const int64_t wait = omniPwlWaitMs(omniPwlNowMs());
    if (wait > 0) { notice(OPWL::waitText(wait)); return true; }
    auto turnOn = [](bool ok) {
        if (!ok) return;
        omniPwlStore.enabled = true; omniPwlWrite();
        notice(omniPwlLinkedLive() ? "Passwords and autofill are locked with the parental PIN" : "Passwords and autofill are locked with your PIN");
        omniFxRefresh();
    };
    omniParLoad();
    if (omniParStore.pin.ok()) {   // reuse the parental PIN (it is asked once to prove it is known)
        omniPwlStore.linkParental = true;
        omniPwlStore.pin = omniParStore.pin;
        omniPwlPadPush(omniParPadVerify, "Enter the parental PIN to lock passwords", turnOn);
    } else if (omniPwlStore.pin.ok()) {
        omniPwlStore.linkParental = false;
        omniPwlPadPush(omniParPadVerify, "Enter your PIN to lock passwords", turnOn);
    } else {
        omniPwlStore.linkParental = false;
        omniPwlPadPush(omniParPadNew, "Choose a 4 to 6 digit PIN", turnOn);
    }
    return true;
}

// From omniF3Tick: the 10 minutes end; the start lock keeps only its pad on screen.
static void omniPwlTick(uint32_t)
{
    if (omniPwlStartLocked) {
        settingsOpen = false; omniMenuOpenFlag = false; omniHistoryOpenFlag = false;
        if (!(omniFxStack.size() == 1 && omniFxStack.back().kind == omniPwlKindPad)) { omniFxCloseAll(); omniPwlStartPad(); }
        return;
    }
    if (!omniPwlLoaded) return;
    const bool open = omniPwlWindow.isOpen(omniPwlNowMs());
    if (omniPwlWasOpen && !open) omniPwlLockDown();
    omniPwlWasOpen = open;
}
'''

DECLS = (
    'static bool omniPwlGate(int why, std::function<void()> then); /* OMNI_PW_LOCK_V1 (OmniPwLockShell.h): true = the PIN pad took over */\n'
    'static bool omniPwlStartHold(); /* OMNI_PW_LOCK_V1: "Also lock Omni at start" */\n'
    'static Tab* omniPwlTakeHeld(); /* OMNI_PW_LOCK_V1: the blank tab held behind the start PIN */\n'
    'static bool omniPwlBridgeLocked(); /* OMNI_PW_LOCK_V1: omni:// vault.status / vault.list */\n'
    'constexpr int omniPwlRowLock = 881, omniPwlRowStart = 882; /* OMNI_PW_LOCK_V1: Browser settings rows */\n'
    'static void omniPwlSettingsRows(OmniFxPanel& p); /* OMNI_PW_LOCK_V1 */\n'
    'static bool omniPwlSettingsInput(int id, int b); /* OMNI_PW_LOCK_V1 */\n'
)

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniParental.h" /* OMNI_PARENTAL_V1: Parental controls: host rules, safe search, PIN limiter, parental.txt (pure) */\n',
         '#include "OmniParental.h" /* OMNI_PARENTAL_V1: Parental controls: host rules, safe search, PIN limiter, parental.txt (pure) */\n'
         '#include "OmniPwLock.h" /* OMNI_PW_LOCK_V1: Lock passwords and autofill: unlock window, monotonic limiter, pw-lock.txt (pure) */\n'),
        ('static bool omniParSettingsInput(int b);\n',
         'static bool omniParSettingsInput(int b);\n' + DECLS),
        ('    omniPrefsLoad();\n    omniHistoryLoad();\n',
         '    omniPrefsLoad();\n    omniHistoryLoad();\n'
         '    if (omniPwlStartHold()) return true; /* OMNI_PW_LOCK_V1: "Also lock Omni at start": a blank tab under the PIN pad; this restore runs after the PIN */\n'),
        ('        Tab* tab = newTab();\n        if (!tab) break;\n        tab->omniLazyURL = url;\n',
         '        Tab* tab = omniPwlTakeHeld(); /* OMNI_PW_LOCK_V1: the blank tab held behind the start PIN takes the first restored page */\n'
         '        if (!tab) tab = newTab();\n        if (!tab) break;\n        tab->omniLazyURL = url;\n'),
        ('            omniPfFocus(false); // OMNI_PAD_FEEDBACK_V1: background: let go of the light bar\n',
         '            omniPfFocus(false); // OMNI_PAD_FEEDBACK_V1: background: let go of the light bar\n'
         '            omniPwlBackground(); /* OMNI_PW_LOCK_V1: the background locks passwords and autofill again */\n'),
        ('            omniPfFocus(event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED); // OMNI_PAD_FEEDBACK_V1\n',
         '            omniPfFocus(event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED); // OMNI_PAD_FEEDBACK_V1\n'
         '            if (event.window.event == SDL_WINDOWEVENT_FOCUS_LOST) omniPwlBackground(); /* OMNI_PW_LOCK_V1 */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions\n',
         '    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions\n'
         '    omniPwlSettingsRows(p); /* OMNI_PW_LOCK_V1: Lock passwords and autofill, Also lock Omni at start */\n'),
        ('    if (r.id == omniParRowId) return omniParSettingsInput(b); /* OMNI_PARENTAL_V1 (before the >= 300 rows) */\n',
         '    if (r.id == omniParRowId) return omniParSettingsInput(b); /* OMNI_PARENTAL_V1 (before the >= 300 rows) */\n'
         '    if (r.id == omniPwlRowLock || r.id == omniPwlRowStart) return omniPwlSettingsInput(r.id, b); /* OMNI_PW_LOCK_V1 (before the >= 300 rows) */\n'),
    ],
    'OmniPasswords.h': [
        ('static void omniPwFill(int index)\n{\n',
         'static void omniPwFill(int index)\n{\n'
         '    if (omniPwlGate(OmniPwLock::kWhyFill, [index] { omniPwFill(index); })) return; /* OMNI_PW_LOCK_V1 */\n'),
        ('static void omniPwFillCurrent()\n{\n',
         'static void omniPwFillCurrent()\n{\n'
         '    if (omniPwlGate(OmniPwLock::kWhyFill, [] { omniPwFillCurrent(); })) return; /* OMNI_PW_LOCK_V1 */\n'),
        ('    if (b == SDL_CONTROLLER_BUTTON_A) { omniPwRevealRow = omniPwRevealRow == r.id ? -1 : r.id; (void)p; return true; }   // reveal toggles on press\n',
         '    if (b == SDL_CONTROLLER_BUTTON_A && omniPwRevealRow != r.id && omniPwlGate(OmniPwLock::kWhyShow, [id = r.id] { omniPwRevealRow = id; omniFxRefresh(); })) return true; /* OMNI_PW_LOCK_V1 */\n'
         '    if (b == SDL_CONTROLLER_BUTTON_A) { omniPwRevealRow = omniPwRevealRow == r.id ? -1 : r.id; (void)p; return true; }   // reveal toggles on press\n'),
        ('    if (b == SDL_CONTROLLER_BUTTON_Y) { omniPwEditShow(index); return true; }\n',
         '    if (b == SDL_CONTROLLER_BUTTON_Y && omniPwlGate(OmniPwLock::kWhyShow, [index] { omniPwEditShow(index); })) return true; /* OMNI_PW_LOCK_V1: Edit login shows the password */\n'
         '    if (b == SDL_CONTROLLER_BUTTON_Y) { omniPwEditShow(index); return true; }\n'),
        ('static void omniPwListShow()\n{\n',
         'static void omniPwListShow()\n{\n'
         '    if (omniPwlGate(OmniPwLock::kWhyPasswords, [] { omniPwListShow(); })) return; /* OMNI_PW_LOCK_V1 */\n'),
    ],
    'OmniAutofill.h': [
        ('static void omniAfFill()\n{\n',
         'static void omniAfFill()\n{\n'
         '    if (omniPwlGate(OmniPwLock::kWhyForm, [] { omniAfFill(); })) return; /* OMNI_PW_LOCK_V1 */\n'),
        ('static void omniAfPanelShow()\n{\n',
         'static void omniAfPanelShow()\n{\n'
         '    if (omniPwlGate(OmniPwLock::kWhyAutofill, [] { omniAfPanelShow(); })) return; /* OMNI_PW_LOCK_V1 */\n'),
    ],
    'OmniPages.h': [
        ('        const bool locked = omniPwLocked(), broken = omniPwBroken();\n',
         '        const bool locked = omniPwLocked() || omniPwlBridgeLocked(), broken = omniPwBroken(); /* OMNI_PW_LOCK_V1: locked outside the unlock window */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniParentalShell.h" /* OMNI_PARENTAL_V1 */\n',
         '#include "OmniParentalShell.h" /* OMNI_PARENTAL_V1 */\n'
         '#include "OmniPwLockShell.h" /* OMNI_PW_LOCK_V1 (uses the parental pad and PIN) */\n'),
        ('    omniParTick(now);   /* OMNI_PARENTAL_V1: the PIN gate closes with the last panel */\n',
         '    omniParTick(now);   /* OMNI_PARENTAL_V1: the PIN gate closes with the last panel */\n'
         '    omniPwlTick(now);   /* OMNI_PW_LOCK_V1: the 10 minutes end; the start lock keeps only its pad */\n'),
    ],
}
NEEDS = {
    'OmniBrowser.cpp': ['OMNI_PARENTAL_V1', 'OMNI_PAD_FEEDBACK_V1', 'OMNI_EVERYDAY_V1'],
    'OmniBrowserSettings.h': ['OMNI_PARENTAL_V1', 'OMNI_FEATURES_V2'],
    'OmniFeatures3.h': ['OMNI_PARENTAL_V1'],
    'OmniParentalShell.h': ['omniParPadBuild', 'omniParWipeDigits'],
    'OmniPasswords.h': ['omniPwRevealRow'],
}
IDS = [r'881', r'882', r'7191']          # row ids, panel kind (engine tree only)
NAMES = [r'\bomniPwl', r'\bOPWL\b', r'\bOmniPwLock', r'pw-lock\.txt']
MINE = {'OmniPwLock.h', 'OmniPwLockShell.h'}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def check(name, edits):
    s = read(name)
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = read(name)
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'(?<![0-9A-Za-z_])(%s)(?![0-9A-Za-z_])' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in MINE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        if MARK in t:
            continue
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = read(fname)
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in read('OmniBrowser.cpp'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    msgs = [write_new('OmniPwLock.h', PURE, 'OmniParental.h'),
            write_new('OmniPwLockShell.h', SHELL, 'OmniParentalShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
