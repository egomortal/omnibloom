// OMNI_PAINT_RECTS_V1 host gate: compiles the EXACT text the applier inserts into
// DrawingAreaCoordinatedGraphics.cpp (patches-jank/paint-rects.inc) against minimal stubs and checks the
// dirty-region decision, the kill switch and the division guard.
// clang++ -std=c++17 -Wall -Wextra -Werror -I<patches-jank dir>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {

struct IntRect {
    int m_x = 0, m_y = 0, m_w = 0, m_h = 0;
    IntRect() = default;
    IntRect(int x, int y, int w, int h) : m_x(x), m_y(y), m_w(w), m_h(h) { }
    int width() const { return m_w; }
    int height() const { return m_h; }
};

template<typename T, int = 1> struct Vector : std::vector<T> {
    using std::vector<T>::vector;
};

int rectsCollapsed = 0, rectsKept = 0;
unsigned lastRects = 0;
double lastWasted = -1;

} // namespace

extern "C" void omni_jank_rects(int collapsed, unsigned rects, double wastedSpace)
{
    if (collapsed)
        ++rectsCollapsed;
    else
        ++rectsKept;
    lastRects = rects;
    lastWasted = wastedSpace;
}

#include "paint-rects.inc"

static int failures = 0, checks = 0;

static void check(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; printf("FAIL %s\n", what); }
}

static Vector<IntRect, 1> grid(int count, int side, int stride)
{
    Vector<IntRect, 1> v;
    for (int i = 0; i < count; ++i)
        v.push_back(IntRect(0, i * stride, side, side));
    return v;
}

int main()
{
    // the kill switch is read once, so each setting needs its own process; the harness runs both
    const char* mode = getenv("OMNI_PAINT_RECTS");
    const bool tight = !(mode && !strcmp(mode, "0"));
    printf("# OMNI_PAINT_RECTS=%s (%s thresholds)\n", mode ? mode : "<unset>", tight ? "tight" : "upstream");
    check(omniPaintRectsOn() == tight, "the kill switch is honoured");

    // 1. a single rect is always the bounds
    {
        Vector<IntRect, 1> one = grid(1, 100, 100);
        check(shouldPaintBoundsRect(IntRect(0, 0, 100, 100), one), "one rect paints the bounds");
    }
    // 2. an empty region cannot divide by zero
    {
        Vector<IntRect, 1> two = grid(2, 0, 0);
        check(shouldPaintBoundsRect(IntRect(0, 0, 0, 0), two), "a zero-area bounds is refused safely");
    }
    // 3. two small rects far apart: nearly all the bounding box is wasted, so both policies keep the rects
    {
        Vector<IntRect, 1> v;
        v.push_back(IntRect(0, 0, 100, 40));
        v.push_back(IntRect(0, 1000, 100, 40));
        check(!shouldPaintBoundsRect(IntRect(0, 0, 100, 1040), v), "two distant small rects stay rects");
    }
    // 4. two rects that nearly fill their box: both policies collapse (wasted 0.5 > 0.25 keeps it under tight)
    {
        Vector<IntRect, 1> v;
        v.push_back(IntRect(0, 0, 100, 100));
        v.push_back(IntRect(0, 100, 100, 100));
        check(shouldPaintBoundsRect(IntRect(0, 0, 100, 200), v), "two adjacent rects collapse to the bounds");
    }
    // 5. the threshold that matters: wasted space 0.5 (half the box is untouched)
    {
        Vector<IntRect, 1> v;
        v.push_back(IntRect(0, 0, 100, 50));
        v.push_back(IntRect(0, 150, 100, 50));
        const bool collapsed = shouldPaintBoundsRect(IntRect(0, 0, 100, 200), v);
        check(tight ? !collapsed : collapsed, "50% wasted: upstream collapses, tight keeps the rects");
    }
    // 6. the rect-count threshold: 12 rects
    {
        Vector<IntRect, 1> v = grid(12, 40, 100);
        const bool collapsed = shouldPaintBoundsRect(IntRect(0, 0, 40, 1140), v);
        check(tight ? !collapsed : collapsed, "12 rects: upstream exceeds its limit of 10, tight does not");
    }
    // 7. above the tight limit too, everything collapses
    {
        Vector<IntRect, 1> v = grid(40, 40, 100);
        check(shouldPaintBoundsRect(IntRect(0, 0, 40, 3940), v), "40 rects collapse under both policies");
        check(lastRects == 40, "the decision reports the rect count");
    }
    // 8. every decision is reported exactly once
    {
        const int before = rectsCollapsed + rectsKept;
        Vector<IntRect, 1> v = grid(3, 10, 1000);
        (void)shouldPaintBoundsRect(IntRect(0, 0, 10, 2010), v);
        check(rectsCollapsed + rectsKept == before + 1, "one decision is reported per call");
        check(lastWasted > 0.9, "the wasted-space fraction is reported");
    }
    printf("%d paint-rects checks, %d failures (collapsed=%d kept=%d)\n", checks, failures, rectsCollapsed, rectsKept);
    return failures ? 1 : 0;
}
