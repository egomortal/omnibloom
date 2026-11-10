// OMNI_JANK_PAGE_V1 host gate: compiles the EXACT sink the applier appends to WTF/wtf/MainThread.cpp
// (src/jank-sink.inc) against stand-ins for the OMNI_YTPROF_V1 sink that normally shares that translation
// unit, and checks the frame records, the category delta, the histogram, the bucket edges, the flag gate and
// the line budgets. Lines are captured instead of written to fd 2.
// clang++ -std=c++17 -Wall -Wextra -Werror -I<src dir> -DOMNI_JANK_FLAG_PATH='"<temp flag>"'
#include <atomic>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <string>
#include <vector>

// ---- stand-ins for the ytprof sink in the same translation unit ----------------------------------------
namespace WTF {
bool omniTestMainThread = true;
inline bool isMainThread() { return omniTestMainThread; }
}
enum { OMNI_YP_TASK, OMNI_YP_JS, OMNI_YP_COMPILE, OMNI_YP_GC, OMNI_YP_SWEEP, OMNI_YP_STYLE, OMNI_YP_LAYOUT,
    OMNI_YP_PAINT, OMNI_YP_RASTER, OMNI_YP_DECODE, OMNI_YP_PARSE, OMNI_YP_CSSPARSE, OMNI_YP_RUPD, OMNI_YP_COUNT };
namespace {
const char* const omniYpNames[OMNI_YP_COUNT] = { "task", "js", "compile", "gc", "sweep", "style", "layout",
    "paint", "raster", "decode", "parse", "cssparse", "rupd" };
struct OmniYpStateStub { uint64_t self[OMNI_YP_COUNT]; };
OmniYpStateStub omniYp;
uint64_t omniTestClockNs = 0;                 // the test owns the clock
inline uint64_t omniYpNow() { return omniTestClockNs; }
std::vector<std::string> omniTestLines;
std::vector<std::string> omniAllLines;
void omniYpWrite(const char* b, int len) { if (len > 0) { omniTestLines.emplace_back(b, size_t(len)); omniAllLines.emplace_back(b, size_t(len)); } }
} // namespace

#include "jank-common.inc"
#include "jank-sink.inc"

static int failures = 0, checks = 0;

static void check(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; printf("FAIL %s\n", what); }
}

static const std::string* find(const char* prefix, size_t from = 0)
{
    for (size_t i = from; i < omniTestLines.size(); ++i)
        if (omniTestLines[i].compare(0, strlen(prefix), prefix) == 0)
            return &omniTestLines[i];
    return nullptr;
}

static void frame(double ms, double rupd = 0, double raster = 0, unsigned rects = 1, double mpx = 1.0)
{
    omniTestClockNs += uint64_t(ms * 1e6);
    omni_jank_frame(ms, rupd, raster, rects, mpx);
}

static bool emit = false;

int main(int argc, char** argv)
{
    for (int i = 1; i < argc; ++i) if (!strcmp(argv[i], "--emit")) emit = true;
    check(omni_jank_on() == 1, "the flag file enables the sink");
    check(find("OMNI JANK on pid=") != nullptr, "the sink announces itself once");

    // 1. a short frame writes no pframe line
    omniTestLines.clear();
    frame(5.0);
    frame(6.0);
    check(find("OMNI JANK pframe") == nullptr, "short frames write nothing");

    // 2. a long frame writes a pframe line naming the dominant category
    omniTestLines.clear();
    omniYp.self[OMNI_YP_JS] += 40000000ull;         // 40 ms of JS since the previous frame
    omniYp.self[OMNI_YP_PAINT] += 12000000ull;      // 12 ms of paint
    frame(60.0, 50.0, 3.0, 1, 2.07);
    const std::string* line = find("OMNI JANK pframe");
    check(line != nullptr, "a long frame writes a pframe line");
    if (line) {
        check(line->find("top=js") != std::string::npos, "the dominant category is JS");
        check(line->find("js=40.0") != std::string::npos, "the JS delta is the frame's own");
        check(line->find("paint=12.0") != std::string::npos, "the paint delta is the frame's own");
        check(line->find("disp=60.0") != std::string::npos, "the display time is reported");
        check(line->find("mpx=2.07") != std::string::npos, "the painted megapixels are reported");
        check(line->back() == '\n', "the line is terminated");
    }

    // 3. the next frame's categories are a delta, not a running total
    omniTestLines.clear();
    omniYp.self[OMNI_YP_JS] += 5000000ull;
    frame(40.0);
    line = find("OMNI JANK pframe");
    check(line && line->find("js=5.0") != std::string::npos, "the category split is per frame");

    // 4. the ack, the damage and the slow scrolls reach the record
    omniTestLines.clear();
    omni_jank_ack(170.0);
    omni_jank_damage(0.5, 0);
    omni_jank_damage(2.07, 1);
    omni_jank_slowscroll(2.07);
    frame(30.0);
    line = find("OMNI JANK pframe");
    check(line && line->find("ack=170.0") != std::string::npos, "the UI round trip is reported");
    check(line && line->find("damage=2/2.57Mpx full=1") != std::string::npos, "the damage reports are counted");
    check(line && line->find("slow=1") != std::string::npos, "the slow scroll is counted");
    // damage is per frame: the next frame starts from zero
    omniTestLines.clear();
    frame(30.0);
    line = find("OMNI JANK pframe");
    check(line && line->find("damage=0/0.00Mpx") != std::string::npos, "damage resets each frame");

    // 5. the dirty-region decision is counted
    omni_jank_rects(1, 14, 0.0);
    omni_jank_rects(0, 3, 0.9);
    omni_jank_rects(1, 2, 0.1);

    // 6. the histogram after 5 s of frames: buckets, long counts, the category sums
    omniTestLines.clear();
    omniTestClockNs += 5100000000ull;
    frame(8.0);
    const std::string* hist = find("OMNI JANK phist");
    check(hist != nullptr, "a histogram line is written once per 5 s");
    if (hist) {
        check(hist->find("<=8.3=") != std::string::npos && hist->find(">200=") != std::string::npos,
            "the histogram names every bucket");
        check(hist->find("collapsed=2/3") != std::string::npos, "the dirty-region decisions are reported");
        check(hist->find("ack mean=") != std::string::npos, "the ack round trip is in the histogram");
        check(hist->find("slowScroll=1/2.1") != std::string::npos, "the slow scrolls are in the histogram");
        check(hist->find("in long frames:") != std::string::npos, "the long-frame category sums are reported");
        for (int i = 0; i < OMNI_YP_COUNT; ++i)
            check(hist->find(omniYpNames[i]) != std::string::npos, "the histogram names every category");
        check(hist->back() == '\n', "the histogram line is terminated");
    }
    // the window restarts
    omniTestLines.clear();
    omniTestClockNs += 5100000000ull;
    frame(8.0);
    hist = find("OMNI JANK phist");
    check(hist && hist->find("collapsed=0/0") != std::string::npos, "the window restarts after a report");
    check(hist && hist->find("slowScroll=0/0.0") != std::string::npos, "the slow-scroll count restarts");

    // 7. absurd inputs are refused, not recorded
    omniTestLines.clear();
    omni_jank_ack(-5.0);
    omni_jank_ack(1e12);
    omni_jank_damage(-1.0, 0);
    omni_jank_slowscroll(1e12);
    frame(-1.0);
    check(find("OMNI JANK pframe") == nullptr, "a negative frame time writes nothing");

    // 8. a non-main thread is ignored
    omniTestLines.clear();
    WTF::omniTestMainThread = false;
    omniYp.self[OMNI_YP_JS] += 900000000ull;
    frame(500.0);
    omni_jank_damage(9.0, 1);
    check(find("OMNI JANK pframe") == nullptr, "off-main-thread calls are ignored");
    WTF::omniTestMainThread = true;

    // 9. the pframe line budget holds
    omniTestLines.clear();
    for (int i = 0; i < 600; ++i)
        frame(80.0);
    size_t pframes = 0;
    for (const auto& l : omniTestLines)
        if (l.compare(0, 16, "OMNI JANK pframe") == 0)
            ++pframes;
    check(pframes <= 400, "the pframe budget is at most 400 lines");
    check(pframes > 0, "some pframe lines were written");

    printf("%d jank sink checks, %d failures (%zu lines captured)\n", checks, failures, omniTestLines.size());
    if (emit) for (const auto& l : omniAllLines) fputs(l.c_str(), stdout);
    return failures ? 1 : 0;
}
