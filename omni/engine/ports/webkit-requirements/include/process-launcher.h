// Omni Engine: open implementation of the process-launcher API that WebKit's
// PlayStation port expects (UIProcess/Launcher/playstation/ProcessLauncherPlayStation.cpp).
// SPDX-License-Identifier: BSD-2-Clause
#pragma once
#include <stdint.h>

namespace PlayStation {

struct LaunchParam {
    int sock;    // client end of the IPC socket pair, handed to the child
    int userId;  // PS5 user id (unused by the homebrew launcher)
};

// Spawn `path` with `argv` (nullptr-terminated, argv[0] is the first real
// argument as WebKit passes it). Returns the child pid or a negative error.
int32_t launchProcess(const char* path, char* argv[], LaunchParam param);
int terminateProcess(int32_t pid);

// In a child: the IPC socket received from the launcher.
int getConnectionIdentifier();

} // namespace PlayStation
