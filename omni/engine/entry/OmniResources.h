// Omni Engine: embedded resources. SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Writes CA bundle, fonts and fonts.conf under `root` (e.g. "/data/omni").
// Returns the number of files that could not be written.
int omniInstallResources(const char* root);
