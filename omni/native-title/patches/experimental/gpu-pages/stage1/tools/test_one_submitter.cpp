// OMNI_GPU_ONE_SUBMITTER_V1 host stress test: the REAL stage1/src-title/omni_gpu_one_submitter.c text, against a fake
// AGC driver that detects overlapping driver calls and checks that a broker submission runs with the TF ring it set.
//   g++ -std=c++17 -O1 -g -fsanitize=thread -pthread test_one_submitter.cpp -o t && ./t
// Threads (as in the title): a "title RADV" submitter (unbracketed SubmitDcb, sometimes its own TF ring set first, as
// radv_ps5_cs_submit does), its kick thread (unbracketed SuspendPoint), and two "broker client" threads (the broker's
// per-client threads: bracket, tf_is, set TF ring when needed, SubmitDcb, leave; then kick under a bracket).
// A negative control calls the fake driver unlocked to prove the detector sees overlap.
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

extern "C" {
// The fake driver: the __real_ functions the wraps call.
struct ps5_agc_submit_description { void *words; uint32_t word_count; uint8_t flag; uint8_t padding[3]; };
static std::atomic<int> g_inside{0}, g_overlaps{0};
static std::atomic<uint64_t> g_tf{0};          // the ring the "GPU" uses now
static std::atomic<uint64_t> g_wrong_ring{0}, g_driver_calls{0};
static void enter_driver()
{
    if (g_inside.fetch_add(1) != 0) g_overlaps.fetch_add(1);
    g_driver_calls.fetch_add(1);
    for (volatile int i = 0; i < 200; i++) {}    // widen the window
}
static void leave_driver() { g_inside.fetch_sub(1); }
int32_t __real_sceAgcDriverSubmitDcb(struct ps5_agc_submit_description *d)
{
    enter_driver();
    // words[0]: the TF ring this submission needs (0: none). It must be the one the GPU uses now.
    const uint64_t need = *static_cast<uint64_t *>(d->words);
    if (need && need != g_tf.load()) g_wrong_ring.fetch_add(1);
    leave_driver();
    return 0;
}
int32_t __real_sceAgcSuspendPoint(void) { enter_driver(); leave_driver(); return 0; }
int32_t __real_sceAgcDriverSetTFRing(uintptr_t a, uint32_t) { enter_driver(); g_tf.store(a); leave_driver(); return 0; }
int32_t __real_sceAgcDriverSetHsOffchipParam(uint32_t, uint32_t) { enter_driver(); leave_driver(); return 0; }
int32_t __real_sceAgcInit(uint32_t) { enter_driver(); leave_driver(); return 0; }
#include "../src-title/omni_gpu_one_submitter.c"
}

static constexpr int kIters = 20000;
static constexpr uint64_t kTitleRing = 0x1000, kBrokerRing = 0x2000;

static void title_radv(bool use_tess)
{
    for (int i = 0; i < kIters; i++) {
        uint64_t need = 0;
        // As radv_ps5_cs_submit: its queue lock (not modelled), a ring set, then the submission - not atomic with
        // respect to the broker, as the archive is not patched; only every 64th submission uses tessellation.
        if (use_tess && i % 64 == 0) { __wrap_sceAgcDriverSetTFRing(kTitleRing, 64); }
        ps5_agc_submit_description d{&need, 8, 0, {}};
        __wrap_sceAgcDriverSubmitDcb(&d);
    }
}
static void title_kick()
{
    for (int i = 0; i < kIters; i++) __wrap_sceAgcSuspendPoint();
}
static void broker_client(uint64_t ring)
{
    for (int i = 0; i < kIters / 2; i++) {
        uint64_t need = ring;
        omni_gpu_one_submitter_enter(OMNI_GPU_SUBMITTER_BROKER);
        if (!omni_gpu_one_submitter_tf_is(ring, 64)) __wrap_sceAgcDriverSetTFRing(ring, 64);
        if (!omni_gpu_one_submitter_offchip_is(1, 2)) __wrap_sceAgcDriverSetHsOffchipParam(1, 2);
        ps5_agc_submit_description d{&need, 8, 0, {}};
        __wrap_sceAgcDriverSubmitDcb(&d);
        omni_gpu_one_submitter_leave();
        omni_gpu_one_submitter_enter(OMNI_GPU_SUBMITTER_BROKER);
        __wrap_sceAgcSuspendPoint();
        omni_gpu_one_submitter_leave();
    }
}

static int run(bool title_tess)
{
    g_overlaps = 0; g_wrong_ring = 0; g_driver_calls = 0;
    std::vector<std::thread> t;
    t.emplace_back(title_radv, title_tess);
    t.emplace_back(title_kick);
    t.emplace_back(broker_client, kBrokerRing);
    t.emplace_back(broker_client, kBrokerRing);   // two client threads, one broker ring (the broker's lock is not modelled)
    for (auto &x : t) x.join();
    struct omni_gpu_one_submitter_stats s;
    omni_gpu_one_submitter_stats(&s);
    printf("run(title_tess=%d): driver calls %llu, overlaps %d, broker submissions on a wrong ring %llu | submits title=%llu "
           "broker=%llu switches=%llu waits title=%llu broker=%llu tf_conflicts=%llu\n", title_tess,
           (unsigned long long)g_driver_calls.load(), g_overlaps.load(), (unsigned long long)g_wrong_ring.load(),
           (unsigned long long)s.submits[0], (unsigned long long)s.submits[1], (unsigned long long)s.switches,
           (unsigned long long)s.waits[0], (unsigned long long)s.waits[1], (unsigned long long)s.tf_conflicts);
    int fails = 0;
    if (g_overlaps.load()) { printf("FAIL: overlapping driver calls\n"); fails++; }
    if (g_wrong_ring.load()) { printf("FAIL: a broker submission ran on a ring it did not set\n"); fails++; }
    if (!s.switches) { printf("FAIL: the submitters never interleaved (the test did not stress anything)\n"); fails++; }
    if (title_tess && !s.tf_conflicts) { printf("FAIL: conflicting TF ring sets were not counted\n"); fails++; }
    if (!title_tess && s.tf_conflicts) { printf("FAIL: a conflict was counted with one ring only\n"); fails++; }
    return fails;
}

// Negative control: the same driver called with no lock must show overlap, or the detector proves nothing.
static int control()
{
    g_overlaps = 0;
    auto body = [] {
        uint64_t need = 0;
        ps5_agc_submit_description d{&need, 8, 0, {}};
        for (int i = 0; i < kIters; i++) __real_sceAgcDriverSubmitDcb(&d);
    };
    std::thread a(body), b(body);
    a.join(); b.join();
    printf("control (no lock): overlaps %d\n", g_overlaps.load());
    return g_overlaps.load() ? 0 : 1;
}

int main()
{
    int fails = 0;
    fails += run(false);
    fails += run(true);
    // recursion: a bracket around wrapped calls, nested twice, on one thread
    omni_gpu_one_submitter_enter(OMNI_GPU_SUBMITTER_BROKER);
    omni_gpu_one_submitter_enter(OMNI_GPU_SUBMITTER_BROKER);
    __wrap_sceAgcInit(1);
    omni_gpu_one_submitter_leave();
    omni_gpu_one_submitter_leave();
    if (control()) { printf("FAIL: the control saw no overlap: the detector is blind\n"); fails++; }
    printf(fails ? "FAILED (%d)\n" : "PASS\n", fails);
    return fails ? 1 : 0;
}
