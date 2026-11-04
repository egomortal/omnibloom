/* Omni Engine: the SDK's <malloc.h> is an #error stub (FreeBSD style).
 * WTF/Skia include it Linux-style; <stdlib.h> + <malloc_np.h> (for
 * malloc_usable_size, exported by libSceLibcInternal) cover their needs.
 * SPDX-License-Identifier: BSD-2-Clause */
#pragma once
#include <stdlib.h>
#include <malloc_np.h>
