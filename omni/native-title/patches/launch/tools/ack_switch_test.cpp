// omni-launch OMNI_ACK_SWITCH_V1 gate: compiles the SHIPPED ack-policy.inc (after apply_launch_switches.py --ack) and
// checks one policy per process (the policy is cached per process, as in the child). Usage: ack_switch_test <expect>
// where <expect> is "on" (credits 2, 1001/60 ms), "off" (credits 0), or "c3hz30" (credits 3, 1000/30 ms).
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "ack-policy.inc"
int main(int argc, char** argv)
{
    const char* want = argc > 1 ? argv[1] : "on";
    const OmniAckPolicy p = omniAckPolicy();
    (void)omniAckSchedule;
    bool ok = false;
    if (!strcmp(want, "on")) ok = p.credits == 2 && std::fabs(p.periodMs - 1001.0 / 60) < 1e-6;
    else if (!strcmp(want, "off")) ok = p.credits == 0;
    else if (!strcmp(want, "c3hz30")) ok = p.credits == 3 && std::fabs(p.periodMs - 1000.0 / 30) < 1e-6;
    printf("%s ack switch: expect %s, got credits=%u period=%.3f\n", ok ? "PASS" : "FAIL", want, p.credits, p.periodMs);
    return ok ? 0 : 1;
}
