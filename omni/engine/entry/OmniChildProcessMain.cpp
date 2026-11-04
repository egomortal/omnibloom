// Omni Engine: entry point for WebKit child processes on a jailbroken PS5.
// Replaces Sony's EntryPoint/playstation/*ProcessMain.cpp, which dlopen() a
// chain of Sony system modules. Omni links everything statically, and gets
// its role arguments + IPC socket from the Omni launcher (elfldr-spawned).
//
// Compiled once per process type with OMNI_PROCESS_{WEB,NETWORK,GPU}.
// SPDX-License-Identifier: BSD-2-Clause
#include "config.h"

#if defined(OMNI_PROCESS_WEB)
#include "WebProcessMain.h"
#define OMNI_PROCESS_MAIN WebKit::WebProcessMain
#elif defined(OMNI_PROCESS_NETWORK)
#include "NetworkProcessMain.h"
#define OMNI_PROCESS_MAIN WebKit::NetworkProcessMain
#elif defined(OMNI_PROCESS_GPU)
#include "GPUProcessMain.h"
#define OMNI_PROCESS_MAIN WebKit::GPUProcessMain
#else
#error "define OMNI_PROCESS_WEB, OMNI_PROCESS_NETWORK or OMNI_PROCESS_GPU"
#endif

#include <omni-launcher.h>
#include <process-launcher.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char** argv)
{
    char* assigned[16];
    int assignedCount = 0;
    char* coreProcessIdentifier = nullptr;

    if (omni_child_bootstrap(assigned, 16, &assignedCount) == OMNI_ROLE_CHILD && assignedCount >= 2) {
        // assigned[0] = process path WebKit asked for, assigned[1] = core process id
        coreProcessIdentifier = assigned[1];
    } else if (argc >= 2) {
        // Direct launch (debugging): argv[1] = core process id, socket via env.
        coreProcessIdentifier = argv[1];
    } else {
        fprintf(stderr, "omni: child process started without a launcher assignment\n");
        return EXIT_FAILURE;
    }

    char connectionIdentifier[16];
    snprintf(connectionIdentifier, sizeof(connectionIdentifier), "%d", PlayStation::getConnectionIdentifier());

    char program[] = "omni";
    char* internalArgv[] = { program, coreProcessIdentifier, connectionIdentifier, nullptr };
    return OMNI_PROCESS_MAIN(3, internalArgv);
}
