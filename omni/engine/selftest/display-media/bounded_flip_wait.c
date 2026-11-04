#include <stdint.h>

/* Original diagnostic wrapper, linked only into omni-display-chart.elf.
 * PS5 timeout pointer/usecs and 0x8002003c are corroborated by ProsperoLight
 * src/native_agc_present.cpp; see README. No production SDL changes.
 */
extern int __real_sceKernelWaitEqueue(void*, void*, int, int*, unsigned int*);
int __wrap_sceKernelWaitEqueue(void* queue, void* event, int count,
                             int* received, unsigned int* requested)
{
    unsigned int timeout = requested && *requested < 500000u ? *requested : 500000u;
    if (received) *received = 0;
    int result = __real_sceKernelWaitEqueue(queue, event, count, received, &timeout);
    // A successful call without an event is not permission to recycle scanout.
    if (!result && (!received || *received < 1))
        return (int32_t)UINT32_C(0x8002003c);
    return result;
}
