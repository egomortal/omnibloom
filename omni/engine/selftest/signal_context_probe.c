// Read only the context of our own signal; no other processes are inspected.
#include <signal.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <ucontext.h>
#include <unistd.h>
static volatile uintptr_t expectedStack, oldStack, correctedStack, savedCanary;
static volatile sig_atomic_t passed, received;
static void handler(int signal, siginfo_t* info, void* context) {
    (void)signal; (void)info;
    oldStack = ((ucontext_t*)context)->uc_mcontext.mc_rsp;
    const mcontext_t* machine = (const mcontext_t*)((const unsigned char*)context + 64);
    correctedStack = machine->mc_rsp;
    savedCanary = machine->mc_r12;
    uintptr_t distance = correctedStack > expectedStack ? correctedStack - expectedStack : expectedStack - correctedStack;
    if (distance < 16384 && savedCanary == UINT64_C(0x1122334455667788)) ++passed;
    ++received;
}
int main(void) {
    struct sigaction action = {0};
    action.sa_sigaction = handler; action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGUSR2, &action, 0)) return 2;
    volatile int local = 0;
    expectedStack = (uintptr_t)&local;
    register uintptr_t canary __asm__("r12") = UINT64_C(0x1122334455667788);
    for (int i = 0; i < 100; ++i) {
        __asm__ volatile("" : "+r"(canary));
        raise(SIGUSR2);
        __asm__ volatile("" : "+r"(canary));
    }
    FILE* file = fopen("/data/omni/signal-context-test.txt", "w");
    if (!file) return 3;
    fprintf(file,"SDK offset=%zu verified candidate=64 received=%d passed=%d\nold-sp=%lx corrected-sp=%lx local-sp=%lx r12=%lx\n%s\n",offsetof(ucontext_t,uc_mcontext),(int)received,(int)passed,(unsigned long)oldStack,(unsigned long)correctedStack,(unsigned long)expectedStack,(unsigned long)savedCanary,passed==100?"PASS":"FAIL");
    fclose(file); return passed==100?0:1;
}
