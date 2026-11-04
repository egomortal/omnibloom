#include <assert.h>
#include <stdint.h>
#include <stdio.h>
int __wrap_sceKernelWaitEqueue(void*,void*,int,int*,unsigned int*);
static unsigned expected;
static int fakeResult, fakeCount;
int __real_sceKernelWaitEqueue(void* q,void* event,int count,int* out,unsigned int* timeout) {
    (void)q;(void)event;assert(count==1);assert(timeout && *timeout==expected);
    if(out)*out=fakeCount;
    return fakeResult;
}
int main(void) {
    int count=99; expected=500000;fakeResult=0;fakeCount=1;
    assert(!__wrap_sceKernelWaitEqueue(0,0,1,&count,0));assert(count==1);
    unsigned request=900000; assert(!__wrap_sceKernelWaitEqueue(0,0,1,&count,&request));assert(request==900000);
    expected=20;request=20;assert(!__wrap_sceKernelWaitEqueue(0,0,1,&count,&request));
    expected=0;request=0;assert(!__wrap_sceKernelWaitEqueue(0,0,1,&count,&request));
    expected=500000;fakeCount=0;
    assert((uint32_t)__wrap_sceKernelWaitEqueue(0,0,1,&count,0)==UINT32_C(0x8002003c));
    fakeResult=-12;assert(__wrap_sceKernelWaitEqueue(0,0,1,&count,0)==-12);
    puts("PASS finite timeout, clamp, poll, no-event failure, unchanged error");
}
