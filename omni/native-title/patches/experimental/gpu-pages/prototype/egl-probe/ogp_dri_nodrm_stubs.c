/* omni-gpu-pages: link stand-ins for the parts of Mesa's DRI frontend that are only built with DRM (src/gallium/
 * frontends/dri/dri2.c) and for SysV shared memory (used by the X11 SHM path of the sw winsys). With no DRM on the
 * PS5, EGL surfaceless + Zink (kopper, pbuffers only) should never call them; each one logs once and returns
 * 0 / NULL / -1, so a console run shows whether any is reached. A proper fix is a Mesa build change that compiles
 * dri2.c's DRM-free parts; this file keeps the first console probe small.
 * SPDX-License-Identifier: MIT */
#include <errno.h>
#include <stdio.h>
static void ogp_hit(const char *name)
{
    static int seen[32]; static const char *names[32]; int i;
    for (i = 0; i < 32 && names[i]; i++) if (names[i] == name) return;
    if (i < 32) { names[i] = name; seen[i] = 1; }
    fprintf(stderr, "ogp: no-DRM stand-in reached: %s\n", name);
}
#define OGP_ZERO(name) void *name(void) { ogp_hit(#name); return 0; }
OGP_ZERO(dri2_init_drawable)
OGP_ZERO(dri2_init_screen)
OGP_ZERO(dri2_query_compression_rates)
OGP_ZERO(dri_create_image)
OGP_ZERO(dri_image_drawable_get_buffers)
OGP_ZERO(dri_interop_export_object)
OGP_ZERO(dri_interop_flush_objects)
OGP_ZERO(dri_interop_query_device_info)
OGP_ZERO(dri_set_blob_cache_funcs)
OGP_ZERO(dri_set_damage_region)
OGP_ZERO(dri_swrast_kms_init_screen)
#define OGP_FAIL(name) long name(void) { ogp_hit(#name); errno = ENOSYS; return -1; }
OGP_FAIL(shmget)
OGP_FAIL(shmctl)
OGP_FAIL(shmdt)
void *shmat(void) { ogp_hit("shmat"); errno = ENOSYS; return (void *)-1; }
