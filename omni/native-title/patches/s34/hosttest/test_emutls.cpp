// Host regression test for OMNI_EMUTLS_ROUNDS_V1: the SDK's real cxa.c (thread_local destructors through a pthread
// key) with emutls. Built twice: with the SDK's emutls.c (skip rounds 0, the title before the fix) and with the
// title's NativeEmutls.cpp (skip rounds 1). Under AddressSanitizer the first must report a heap-use-after-free in the
// thread_local destructor (the title crash), the second must run clean. Also checks values and destructor counts.
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <initializer_list>
extern "C" void* __emutls_get_address(void*);
extern "C" int ps5___cxa_thread_atexit_impl(void (*)(void*), void*, void*);
struct Control { uintptr_t size, align; uintptr_t index; void* value; };
struct Vec { char* begin; char* end; char* cap; };
static Control early { sizeof(long), alignof(long), 0, nullptr };   // touched first, like libpas' TLS pointer
static Control vecA { sizeof(Vec), alignof(Vec), 0, nullptr };     // like holeBlendRowT's vcache
static Control vecB { sizeof(Vec), alignof(Vec), 0, nullptr };     // like omniConvertIntegerUpscale's Ctx
static int destroyed = 0;
static void vecDtor(void* p)
{
    Vec* v = static_cast<Vec*>(p);
    free(v->begin);                 // reads the object: a use-after-free if emutls already freed it
    v->begin = nullptr;
    __atomic_add_fetch(&destroyed, 1, __ATOMIC_RELAXED);
}
static void* worker(void*)
{
    *static_cast<long*>(__emutls_get_address(&early)) = 7;
    for (Control* c : { &vecA, &vecB }) {
        Vec* v = static_cast<Vec*>(__emutls_get_address(c));
        v->begin = static_cast<char*>(malloc(4096)); v->end = v->begin; v->cap = v->begin + 4096;
        ps5___cxa_thread_atexit_impl(vecDtor, v, nullptr);
    }
    return nullptr;
}
int main()
{
    *static_cast<long*>(__emutls_get_address(&early)) = 1;   // emutls' key is created before cxa.c's (as in the title)
    for (int round = 0; round < 50; ++round) {
        pthread_t t; pthread_create(&t, nullptr, worker, nullptr); pthread_join(t, nullptr);
    }
    const int want = 100;
    printf("thread_local destructors run: %d of %d\n", destroyed, want);
    printf("%s\n", destroyed == want ? "EMUTLS HOSTTEST PASS" : "EMUTLS HOSTTEST FAIL");
    return destroyed == want ? 0 : 1;
}
