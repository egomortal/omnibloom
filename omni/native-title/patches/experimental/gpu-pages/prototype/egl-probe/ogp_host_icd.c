/* omni-gpu-pages host-only glue: stands in for a statically linked Vulkan driver, so the OGP_ZINK_STATIC_ICD
 * path (no loader) can be exercised on a PC with lavapipe. Opens the lavapipe ICD library directly and hands out
 * its vk_icdGetInstanceProcAddr. On the console, RADV's own vk_icdGetInstanceProcAddr is linked in instead.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
typedef void (*vkfn)(void);
typedef vkfn (*icd_gipa)(void *instance, const char *name);
static icd_gipa real;
__attribute__((visibility("default"))) vkfn ogp_host_icd(void *instance, const char *name)
{
    if (!real) {
        const char *lib = getenv("OGP_HOST_ICD_LIB");
        void *h = dlopen(lib ? lib : "libvulkan_lvp.so", RTLD_NOW | RTLD_LOCAL);
        real = h ? (icd_gipa)dlsym(h, "vk_icdGetInstanceProcAddr") : NULL;
        if (!real) { fprintf(stderr, "ogp_host_icd: cannot open the ICD (%s)\n", dlerror()); return NULL; }
    }
    return real(instance, name);
}
