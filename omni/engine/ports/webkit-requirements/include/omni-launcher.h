// Omni Engine launcher: entry points used by Omni's multi-call main().
// SPDX-License-Identifier: BSD-2-Clause
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

enum {
    OMNI_ROLE_ERROR = -1,
    OMNI_ROLE_FIRST = 0, // no launcher answered: this is the UI process
    OMNI_ROLE_CHILD = 1, // assignment received; argv filled, IPC fd stored
};

// Starts a copy of the multi-call ELF at `path`. Return <0 on failure.
typedef int (*omni_spawn_fn)(const char* path);
void omni_launcher_set_spawner(omni_spawn_fn fn);
void omni_launcher_set_dir(const char* dir);
void omni_launcher_set_socket_path(const char* path);
int omni_launcher_listen(void);

// Call first thing in main(). On OMNI_ROLE_CHILD, argvOut[0] is the process
// path WebKit asked for (selects Web/Network/GPU), followed by WebKit's args.
int omni_child_bootstrap(char** argvOut, int maxArgs, int* argcOut);

#ifdef __cplusplus
}
#endif
