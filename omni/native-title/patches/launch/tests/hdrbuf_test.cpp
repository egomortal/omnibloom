// Host unit test for OMNI_NET_HDRBUF_V1 (omni-net HTTP/2 fix B).
// It compiles the SHIPPED sources unchanged -- src/h2b-hdrbuf.h.inc and src/h2b-hdrbuf.cpp.inc -- behind a minimal
// WTF shim, and drives them through a model of the patched CurlRequest::didReceiveData / resume / finalize control
// flow (kept line-for-line in step with tools/apply_h2fix.py's NEW_PAUSE block).
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <span>
#include <string>
#include <unistd.h>
#include <utility>
#include <vector>

namespace WTF { using std::move; }

template<typename T> class Vector {
public:
    Vector() = default;
    size_t size() const { return m_v.size(); }
    bool isEmpty() const { return m_v.empty(); }
    T* data() { return m_v.data(); }
    const T* data() const { return m_v.data(); }
    void grow(size_t n) { m_v.resize(n); }          // WTF::Vector::grow only ever grows
    void clear() { m_v.clear(); m_v.shrink_to_fit(); }
    std::span<const T> span() const { return { m_v.data(), m_v.size() }; }
    std::span<T> mutableSpan() { return { m_v.data(), m_v.size() }; }
private:
    std::vector<T> m_v;
};

template<typename T, typename U> void memcpySpan(std::span<T> dst, std::span<U> src)
{
    if (!src.empty()) memcpy(dst.data(), src.data(), src.size() * sizeof(U));
}

#include "h2b-hdrbuf.h.inc"
#include "h2b-hdrbuf.cpp.inc"

static int failures = 0;
static void check(bool ok, const char* what)
{
    if (!ok) { printf("  FAIL %s\n", what); ++failures; }
    else printf("  ok   %s\n", what);
}

// ---- a model of the patched CurlRequest, exactly the control flow apply_h2fix.py installs ----
static constexpr long kPause = -1;
static constexpr long kError = -2;

struct FakeRequest {
    OmniHdrBuf m_omniHdrBuf;
    size_t m_totalReceivedSize { 0 };
    bool m_didReceiveResponse { false };
    bool m_didNotifyResponse { false };
    bool m_cancelled { false };
    bool m_multipartHandle { false };
    long statusCode { 200 };
    long httpConnectCode { 0 };
    bool curlThinksPaused { false };
    std::vector<std::string> delivered;

    bool needToInvokeDidReceiveResponse() const { return m_didReceiveResponse && !m_didNotifyResponse; }
    void headers(long code = 200) { m_didReceiveResponse = true; statusCode = code; }

    void deliver(std::span<const uint8_t> d) { delivered.emplace_back(reinterpret_cast<const char*>(d.data()), d.size()); }

    long didReceiveData(std::span<const uint8_t> receivedData)
    {
        if (m_cancelled)
            return kError;

        if (needToInvokeDidReceiveResponse()) {
            bool omniHdrBufOk = !omniHdrBufOff() && !m_multipartHandle && !httpConnectCode
                && statusCode >= 200 && statusCode < 300;
            m_didNotifyResponse = true; // invokeDidReceiveResponse()
            if (!omniHdrBufOk) { curlThinksPaused = true; return kPause; }
            m_omniHdrBuf.begin();
        }

        if (m_omniHdrBuf.isBuffering()) {
            if (!m_omniHdrBuf.take(receivedData)) {
                m_omniHdrBuf.state = 2;
                curlThinksPaused = true;
                return kPause;
            }
            m_totalReceivedSize += receivedData.size();
            return static_cast<long>(receivedData.size());
        }

        m_totalReceivedSize += receivedData.size();
        deliver(receivedData);
        return static_cast<long>(receivedData.size());
    }

    // the resume lambda: runs on the same worker thread as didReceiveData
    void resume()
    {
        bool omniWasPaused = m_omniHdrBuf.transferIsPaused();
        if (m_cancelled) { m_omniHdrBuf.drop(); return; }
        if (m_omniHdrBuf.state == 1 || m_omniHdrBuf.state == 2) {
            Vector<uint8_t> omniEarly;
            if (m_omniHdrBuf.claim(omniEarly))
                deliver({ omniEarly.data(), omniEarly.size() });
        }
        if (omniWasPaused)
            curlThinksPaused = false; // curl re-delivers the chunk it was holding
    }

    void finalizeTransfer() { m_omniHdrBuf.drop(); }
};

static std::span<const uint8_t> sp(const std::string& s)
{
    return { reinterpret_cast<const uint8_t*>(s.data()), s.size() };
}
static size_t charged() { return omniHdrBufChargedTotal.load(); }

int main(int argc, char** argv)
{
    bool wantOff = argc > 1 && !strcmp(argv[1], "offcheck");

    printf("caps: per-response %zu, process %zu, kill switch off=%d\n",
        omniHdrBufPerResponseCap, omniHdrBufProcessCap, (int)omniHdrBufOff());

    if (wantOff) {
        // Run with /data/omni/net-off-hdrbuf.flag present.
        printf("T0 kill switch\n");
        check(omniHdrBufOff(), "flag is seen");
        FakeRequest r; r.headers(200);
        std::string a = "AAAA";
        check(r.didReceiveData(sp(a)) == kPause, "200 takes the original pause when hdrbuf is off");
        check(r.m_omniHdrBuf.state == 0 && !charged(), "nothing buffered, no budget held");
        printf(failures ? "\nFAILURES: %d\n" : "\nall kill-switch checks passed\n", failures);
        return failures ? 1 : 0;
    }

    {
        printf("T1 short header pause under the cap: body flows, delivered in order, counted once\n");
        FakeRequest r; r.headers(200);
        std::string a = "AAA", b = "BB", c = "C", d = "DDDD";
        check(r.didReceiveData(sp(a)) == 3, "first chunk accepted, not paused");
        check(r.didReceiveData(sp(b)) == 2, "second chunk accepted");
        check(r.didReceiveData(sp(c)) == 1, "third chunk accepted");
        check(!r.curlThinksPaused, "the transfer was never paused (this is the whole fix)");
        check(r.delivered.empty(), "nothing delivered before the header decision");
        check(charged() == 6, "6 bytes held against the process budget");
        r.resume();
        check(r.delivered.size() == 1 && r.delivered[0] == "AAABBC", "early body flushed once, in order");
        check(!charged(), "budget released at the flush");
        r.didReceiveData(sp(d));
        check(r.delivered.size() == 2 && r.delivered[1] == "DDDD", "live bytes arrive after the early body");
        check(r.m_totalReceivedSize == 10, "every byte counted exactly once");
        r.finalizeTransfer();
        check(!charged(), "budget clean after finalize");
    }
    {
        printf("T2 per-response cap: pause past the cap is real backpressure, no byte lost or doubled\n");
        FakeRequest r; r.headers(200);
        std::string chunk(16 * 1024, 'x');
        size_t accepted = 0;
        while (r.didReceiveData(sp(chunk)) == static_cast<long>(chunk.size()))
            accepted += chunk.size();
        check(accepted == omniHdrBufPerResponseCap, "accepted exactly the per-response cap");
        check(r.curlThinksPaused && r.m_omniHdrBuf.state == 2, "paused once the cap was reached");
        check(r.m_omniHdrBuf.body.size() == omniHdrBufPerResponseCap, "buffer is bounded at the cap");
        check(r.m_omniHdrBuf.peak == omniHdrBufPerResponseCap, "peak recorded for the diagnostic");
        size_t beforeResume = r.m_totalReceivedSize;
        r.resume();
        check(r.delivered.size() == 1 && r.delivered[0].size() == omniHdrBufPerResponseCap, "cap-sized flush");
        check(!r.curlThinksPaused, "unpaused after the flush");
        check(!charged(), "budget released");
        // curl re-delivers the chunk it was holding when we paused
        r.didReceiveData(sp(chunk));
        check(r.delivered.size() == 2 && r.delivered[1].size() == chunk.size(), "held chunk delivered live");
        check(r.m_totalReceivedSize == beforeResume + chunk.size(), "held chunk counted exactly once");
        r.finalizeTransfer();
    }
    {
        printf("T3 process budget: memory is bounded across responses, the rest fall back to pausing\n");
        const size_t n = omniHdrBufProcessCap / omniHdrBufPerResponseCap + 4;
        std::vector<FakeRequest*> rs;
        std::string chunk(16 * 1024, 'y');
        size_t fullyBuffered = 0, pausedEarly = 0, peakCharged = 0;
        for (size_t i = 0; i < n; ++i) {
            auto* r = new FakeRequest(); rs.push_back(r); r->headers(200);
            size_t got = 0;
            while (got < omniHdrBufPerResponseCap && r->didReceiveData(sp(chunk)) == static_cast<long>(chunk.size()))
                got += chunk.size();
            if (charged() > peakCharged) peakCharged = charged();
            if (got == omniHdrBufPerResponseCap) ++fullyBuffered; else ++pausedEarly;
            if (r->curlThinksPaused) { /* backpressure, as intended */ }
        }
        check(peakCharged <= omniHdrBufProcessCap, "the process budget was never exceeded");
        check(fullyBuffered == omniHdrBufProcessCap / omniHdrBufPerResponseCap, "exactly the budget's worth buffered");
        check(pausedEarly == 4, "the rest paused instead of buffering");
        for (auto* r : rs) { r->finalizeTransfer(); delete r; }
        check(!charged(), "budget fully released when every response finalizes");
    }
    {
        printf("T4 cancel: buffered bytes are dropped cleanly and never delivered\n");
        FakeRequest r; r.headers(200);
        std::string a = "SECRET";
        r.didReceiveData(sp(a));
        check(charged() == 6, "bytes buffered");
        r.m_cancelled = true;       // the client cancelled on the header decision
        r.resume();                 // the resume lambda sees isCompletedOrCancelled()
        check(r.delivered.empty(), "nothing was delivered to a cancelled load");
        check(!charged(), "budget released on cancel");
        r.finalizeTransfer();
        check(!charged(), "drop is idempotent");
        Vector<uint8_t> out;
        check(!r.m_omniHdrBuf.claim(out), "claim after a drop yields nothing");
        check(!charged(), "and still holds no budget");
    }
    {
        printf("T5 the header decisions that restart a transfer keep the original pause\n");
        for (long code : { 100L, 301L, 302L, 304L, 401L, 407L, 500L }) {
            FakeRequest r; r.headers(code);
            std::string a = "body";
            bool paused = r.didReceiveData(sp(a)) == kPause;
            char buf[64]; snprintf(buf, sizeof(buf), "status %ld pauses as before", code);
            check(paused && r.m_omniHdrBuf.state == 0 && !charged(), buf);
        }
        { FakeRequest r; r.headers(200); r.m_multipartHandle = true; std::string a = "part";
          check(r.didReceiveData(sp(a)) == kPause && !charged(), "multipart pauses as before"); }
        { FakeRequest r; r.headers(200); r.httpConnectCode = 200; std::string a = "tunnel";
          check(r.didReceiveData(sp(a)) == kPause && !charged(), "CONNECT tunnel pauses as before"); }
        { FakeRequest r; r.headers(206); std::string a = "range";
          check(r.didReceiveData(sp(a)) == 5, "206 Partial Content is buffered"); r.finalizeTransfer(); }
    }
    {
        printf("T6 ordering when the decision resolves mid-stream\n");
        FakeRequest r; r.headers(200);
        std::string a = "A", b = "B", c = "C";
        r.didReceiveData(sp(a));
        r.resume();
        r.didReceiveData(sp(b));
        r.didReceiveData(sp(c));
        check(r.delivered.size() == 3 && r.delivered[0] == "A" && r.delivered[1] == "B" && r.delivered[2] == "C",
            "early body first, then live bytes in order");
        check(r.m_totalReceivedSize == 3, "counted once each");
        r.finalizeTransfer();
    }
    {
        printf("T7 a zero-length write and an empty response do not disturb the budget\n");
        FakeRequest r; r.headers(200);
        std::string empty;
        check(r.didReceiveData(sp(empty)) == 0, "empty chunk accepted (as upstream does)");
        check(!charged(), "no budget held for nothing");
        r.resume();
        check(r.delivered.empty(), "nothing flushed");
        check(r.m_omniHdrBuf.state == 3, "state advanced to flushed");
        r.finalizeTransfer();
    }
    printf(failures ? "\nFAILURES: %d\n" : "\nall checks passed\n", failures);
    return failures ? 1 : 0;
}
