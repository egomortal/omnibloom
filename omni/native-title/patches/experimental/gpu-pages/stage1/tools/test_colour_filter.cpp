// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_COLOUR_FILTER_V1 host test of the pure part (engine/entry/OmniColourFilter.h, written by tools/apply_colour_filter.py).
//   M1 Machado 2009 rows sum to 1      M2 daltonize = I + E (I - S), spot values      M3 white / black / greys kept
//   M4 a red-green (blue-yellow) confusion pair is further apart, as the viewer sees it, after correction
//   M5 greyscale = Rec. 709 luma        M6 invert: 0 <-> 1, twice = identity           M7 compose(N, F) = N (F c + f)
//   S1 settings round trip, garbage, CRLF          S2 cycle wraps both ways          S3 quick toggle keeps the last filter
// Build: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_colour_filter.cpp && ./a.out
#include "OmniColourFilter.h"
#include <cstdarg>
#include <cstdio>

namespace CF = OmniColourFilter;
static int fails = 0;
static void check(bool ok, const char* name, const char* fmt = "", ...) __attribute__((format(printf, 3, 4)));
static void check(bool ok, const char* name, const char* fmt, ...)
{
    char b[512] = ""; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a);
    printf("%s %s -> %s\n", name, b, ok ? "PASS" : "FAIL"); if (!ok) ++fails;
}
static void apply(const CF::Affine& a, const double* c, double* o)
{
    for (int i = 0; i < 3; ++i) o[i] = a.m[i * 4] * c[0] + a.m[i * 4 + 1] * c[1] + a.m[i * 4 + 2] * c[2] + a.m[i * 4 + 3];
}
static void sim(const CF::M3& s, const double* c, double* o)
{
    for (int i = 0; i < 3; ++i) o[i] = s.a[i][0] * c[0] + s.a[i][1] * c[1] + s.a[i][2] * c[2];
}
static double dist(const double* a, const double* b)
{
    return std::sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1]) + (a[2] - b[2]) * (a[2] - b[2]));
}
static void clamp01(double* c) { for (int i = 0; i < 3; ++i) c[i] = std::clamp(c[i], 0.0, 1.0); }

int main()
{
    // M1
    double worstRow = 0;
    for (const CF::M3* s : { &CF::kSimProtan, &CF::kSimDeutan, &CF::kSimTritan })
        for (int i = 0; i < 3; ++i) worstRow = std::max(worstRow, std::fabs(s->a[i][0] + s->a[i][1] + s->a[i][2] - 1));
    check(worstRow < 2e-6, "M1", "Machado 2009 severity 1.0 rows sum to 1 (worst %.2g)", worstRow);

    // M2: independent hand computation of entries: M[1][0] (deutan) = 0.7 (1 - s00) + 1 (0 - s10) = 0.7*0.632678 - 0.280085
    const CF::Affine d = CF::matrix(CF::kDeuteranopia), p = CF::matrix(CF::kProtanopia), t = CF::matrix(CF::kTritanopia);
    const double d10 = 0.7 * (1 - 0.367322) - 0.280085, p21 = 0.7 * (0 - 1.052583) + 1 * (0 - (-0.048116)), t02 = 1 * (0 - (-0.178779)) + 0.7 * (1 - 0.303900);
    check(std::fabs(d.m[4] - d10) < 1e-6 && std::fabs(p.m[9] - p21) < 1e-6 && std::fabs(t.m[2] - t02) < 1e-6, "M2",
          "deutan M10 %.6f (%.6f), protan M21 %.6f (%.6f), tritan M02 %.6f (%.6f)", d.m[4], d10, p.m[9], p21, t.m[2], t02);
    bool firstRowKept = d.m[0] == 1 && d.m[1] == 0 && d.m[2] == 0 && p.m[0] == 1 && t.m[8] == 0 && t.m[10] == 1;
    bool noOffset = true;
    for (CF::Filter f : { CF::kProtanopia, CF::kDeuteranopia, CF::kTritanopia, CF::kGreyscale })
        for (int i = 0; i < 3; ++i) noOffset = noOffset && CF::matrix(f).m[i * 4 + 3] == 0;
    check(firstRowKept && noOffset, "M2b", "red row kept (protan/deutan), blue row kept (tritan); no offsets except Invert");

    // M3: white, black, mid grey through every correction / greyscale
    double worstGrey = 0;
    for (CF::Filter f : { CF::kProtanopia, CF::kDeuteranopia, CF::kTritanopia, CF::kGreyscale })
        for (double v : { 0.0, 0.5, 1.0 }) {
            const double c[3] = { v, v, v }; double o[3]; apply(CF::matrix(f), c, o);
            for (double x : o) worstGrey = std::max(worstGrey, std::fabs(x - v));
        }
    check(worstGrey < 1e-5, "M3", "greys (0, 0.5, 1) unchanged by every correction and greyscale (worst %.2g)", worstGrey);

    // M4: confusion pairs, compared as the dichromat sees them (S applied), before and after the correction
    struct Pair { CF::Filter f; double a[3], b[3]; } pairs[] = {
        { CF::kProtanopia, { 0.8, 0.3, 0.2 }, { 0.4, 0.6, 0.2 } },
        { CF::kDeuteranopia, { 0.8, 0.3, 0.2 }, { 0.4, 0.6, 0.2 } },
        { CF::kTritanopia, { 0.2, 0.4, 0.8 }, { 0.2, 0.6, 0.4 } } };
    for (const Pair& q : pairs) {
        const CF::M3& s = *CF::simulation(q.f);
        double sa[3], sb[3], ca[3], cb[3], sca[3], scb[3];
        sim(s, q.a, sa); sim(s, q.b, sb);
        apply(CF::matrix(q.f), q.a, ca); apply(CF::matrix(q.f), q.b, cb); clamp01(ca); clamp01(cb);
        sim(s, ca, sca); sim(s, cb, scb);
        const double before = dist(sa, sb), after = dist(sca, scb);
        check(after > before * 1.3, "M4", "%s: seen distance %.4f -> %.4f after correction", CF::name(q.f), before, after);
    }

    // M5
    const CF::Affine g = CF::matrix(CF::kGreyscale);
    bool lumaOk = true;
    for (int i = 0; i < 3; ++i) lumaOk = lumaOk && std::fabs(g.m[i * 4] - 0.2126f) < 1e-7 && std::fabs(g.m[i * 4 + 1] - 0.7152f) < 1e-7 && std::fabs(g.m[i * 4 + 2] - 0.0722f) < 1e-7;
    uint8_t r = 255, gg = 0, b = 0; CF::applyPixel(g, r, gg, b);
    check(lumaOk && r == 54 && gg == 54 && b == 54, "M5", "greyscale rows = Rec. 709 luma; pure red -> %d %d %d (54)", r, gg, b);

    // M6
    const CF::Affine inv = CF::matrix(CF::kInvert);
    uint8_t r1 = 0, g1 = 255, b1 = 100; CF::applyPixel(inv, r1, g1, b1);
    uint8_t r2 = r1, g2 = g1, b2 = b1; CF::applyPixel(inv, r2, g2, b2);
    check(r1 == 255 && g1 == 0 && b1 == 155 && r2 == 0 && g2 == 255 && b2 == 100, "M6", "invert (0,255,100) -> (%d,%d,%d) -> (%d,%d,%d)", r1, g1, b1, r2, g2, b2);

    // M7: compose with a full night matrix vs applying the two in sequence (no clamp in between, as the pass)
    const float night[9] = { 1.0f, 0.05f, 0, 0.02f, 0.8f, 0.1f, 0, 0.1f, 0.5f };
    double worstC = 0;
    for (CF::Filter f : { CF::kDeuteranopia, CF::kInvert, CF::kTritanopia }) {
        const CF::Affine c = CF::compose(night, CF::matrix(f));
        for (double x : { 0.0, 0.3, 1.0 }) for (double y : { 0.1, 0.9 }) for (double z : { 0.0, 0.6 }) {
            const double in[3] = { x, y, z }; double fo[3], seq[3], one[3];
            apply(CF::matrix(f), in, fo);
            for (int i = 0; i < 3; ++i) seq[i] = night[i * 3] * fo[0] + night[i * 3 + 1] * fo[1] + night[i * 3 + 2] * fo[2];
            apply(c, in, one);
            for (int i = 0; i < 3; ++i) worstC = std::max(worstC, std::fabs(seq[i] - one[i]));
        }
    }
    const CF::Affine ci = CF::compose(night, CF::identity());
    bool idOk = true; for (int i = 0; i < 3; ++i) for (int j = 0; j < 3; ++j) idOk = idOk && std::fabs(ci.m[i * 4 + j] - night[i * 3 + j]) < 1e-7 && ci.m[i * 4 + 3] == 0;
    check(worstC < 1e-5 && idOk, "M7", "compose(N, F) = N (F c + f) (worst %.2g); compose(N, I) = N", worstC);

    // S1
    CF::Settings s; s.filter = CF::kTritanopia; s.last = CF::kTritanopia;
    const CF::Settings back = CF::parse(CF::serialize(s));
    const CF::Settings junk = CF::parse("filter\tsepia\nlast\toff\nfoo\tbar\n#filter\tinvert\nfilter invert\n");
    const CF::Settings crlf = CF::parse("filter\tinvert\r\nlast\tgreyscale\r\n");
    const CF::Settings def;
    check(back.filter == CF::kTritanopia && back.last == CF::kTritanopia && junk.filter == CF::kOff && junk.last == CF::kDeuteranopia
          && crlf.filter == CF::kInvert && crlf.last == CF::kGreyscale && def.filter == CF::kOff,
          "S1", "round trip, garbage keeps defaults (Off, last Deuteranopia), CRLF");

    // S2
    bool cyc = CF::cycle(CF::kOff, 1) == CF::kProtanopia && CF::cycle(CF::kInvert, 1) == CF::kOff && CF::cycle(CF::kOff, -1) == CF::kInvert
               && CF::cycle(CF::kGreyscale, -1) == CF::kTritanopia;
    CF::Filter f = CF::kOff; for (int i = 0; i < CF::kCount; ++i) f = CF::cycle(f, 1);
    check(cyc && f == CF::kOff, "S2", "cycle wraps both ways; %d steps return to Off", int(CF::kCount));

    // S3
    CF::Settings q; q = CF::quickToggle(q);
    const bool firstOn = q.filter == CF::kDeuteranopia;
    q = CF::setFilter(q, CF::kGreyscale); q = CF::quickToggle(q);
    const bool off = q.filter == CF::kOff && q.last == CF::kGreyscale;
    q = CF::quickToggle(q);
    check(firstOn && off && q.filter == CF::kGreyscale && CF::toggleNotice(q, true) == "Colour filter: Greyscale"
          && CF::toggleNotice(CF::Settings {}, true) == "Colour filter off", "S3", "quick toggle: Deuteranopia first, then Off <-> the last filter; notices");

    printf("%s (%d failed)\n", fails ? "FAIL" : "ALL PASS", fails);
    return fails ? 1 : 0;
}
