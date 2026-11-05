#!/usr/bin/env python3
"""omni-gpu-pages: two small Mesa patches for running Zink + EGL surfaceless inside a PS5 process. Idempotent.
Both are compiled out unless their macro is defined, so a plain build of the same tree is unchanged.
SPDX-License-Identifier: MIT (same licence as the Mesa files they change)

1. OGP_ZINK_STATIC_ICD=<symbol>  (zink_screen.c)
   A PS5 title cannot dlopen a Vulkan loader ("a title cannot load a graphics module at run time"), and the
   title already links RADV statically and calls it through its ICD entry point (vk_icdGetInstanceProcAddr).
   With the macro, Zink takes vkGetInstanceProcAddr from that symbol instead of util_dl_open("libvulkan.so.1"),
   and vkGetDeviceProcAddr through a trampoline that resolves it from Zink's own (single) VkInstance.
3. meson.build: lets Zink's DRI frontend (and so EGL) build without DRM when radv-winsys=ps5 on a non-Linux
   host, the same exception upstream already makes for macOS and KGSL. Linux builds are unchanged.
2. OGP_SURFACELESS_ZINK_NO_DRM  (platform_surfaceless.c)
   The PS5 has no DRM nodes. Upstream only reaches the no-DRM probe when LIBGL_ALWAYS_SOFTWARE is set, which
   also tells Zink to pick a CPU device. With the macro, when the DRM probe finds nothing and Zink is requested
   (eglInitialize's own retry sets Options.Zink), the no-DRM probe loads Zink in hardware mode, so Zink takes
   the first Vulkan device (RADV).
"""
import sys
from pathlib import Path
root = Path(sys.argv[1])
done = []

f = root / 'src/gallium/drivers/zink/zink_screen.c'; s = f.read_text()
if 'OGP_ZINK_STATIC_ICD' not in s:
    anchor = 'static VkInstance instance;\n'
    assert s.count(anchor) == 1, 'zink anchor 1'
    s = s.replace(anchor, anchor + '''
#ifdef OGP_ZINK_STATIC_ICD
/* [omni-gpu-pages] the Vulkan driver is linked into the process; there is no loader to open */
extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL OGP_ZINK_STATIC_ICD(VkInstance inst, const char *name);
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
ogp_static_GetDeviceProcAddr(VkDevice device, const char *name)
{
   static PFN_vkGetDeviceProcAddr real;
   if (!real)
      real = (PFN_vkGetDeviceProcAddr)OGP_ZINK_STATIC_ICD(instance, "vkGetDeviceProcAddr");
   return real ? real(device, name) : NULL;
}
#endif
''')
    old = '''   screen->loader_lib = util_dl_open(VK_LIBNAME);
   if (!screen->loader_lib) {'''
    assert s.count(old) == 1, 'zink anchor 2'
    new = '''#ifdef OGP_ZINK_STATIC_ICD
   screen->vk_GetInstanceProcAddr = (PFN_vkGetInstanceProcAddr)OGP_ZINK_STATIC_ICD;
   screen->vk_GetDeviceProcAddr = (PFN_vkGetDeviceProcAddr)ogp_static_GetDeviceProcAddr;
#else
   screen->loader_lib = util_dl_open(VK_LIBNAME);
   if (!screen->loader_lib) {'''
    s = s.replace(old, new)
    old2 = '''         mesa_loge("ZINK: failed to get proc address");
      goto fail;
   }
'''
    assert s.count(old2) == 1, 'zink anchor 3'
    s = s.replace(old2, old2 + '#endif /* OGP_ZINK_STATIC_ICD */\n')
    f.write_text(s); done.append('patched zink_screen.c (OGP_ZINK_STATIC_ICD)')
else:
    done.append('already zink_screen.c')

f = root / 'src/egl/drivers/dri2/platform_surfaceless.c'; s = f.read_text()
if 'OGP_SURFACELESS_ZINK_NO_DRM' not in s:
    old = '''      driver_loaded = surfaceless_probe_device_sw(disp);
   }
'''
    assert s.count(old) == 1, 'surfaceless anchor'
    s = s.replace(old, old + '''#ifdef OGP_SURFACELESS_ZINK_NO_DRM
   /* [omni-gpu-pages] no DRM nodes (PS5): Zink in hardware mode on the first Vulkan device */
   if (!driver_loaded && disp->Options.Zink && !disp->Options.ForceSoftware) {
      _eglLog(_EGL_DEBUG, "surfaceless: no DRM device, trying Zink on the first Vulkan device.");
      driver_loaded = surfaceless_probe_device_sw(disp);
   }
#endif
''')
    f.write_text(s); done.append('patched platform_surfaceless.c (OGP_SURFACELESS_ZINK_NO_DRM)')
else:
    done.append('already platform_surfaceless.c')
f = root / 'meson.build'; s = f.read_text()
if 'omni-gpu-pages' not in s:
    old = "if with_gallium and (system_has_kms_drm or (with_gallium_zink and (freedreno_kmds.contains('kgsl') or host_machine.system() == 'darwin')))"
    assert s.count(old) == 1, 'meson anchor'
    new = ("# [omni-gpu-pages] Zink's DRI frontend without DRM on the PS5 too (as on macOS and KGSL): EGL surfaceless over RADV\n"
           "if with_gallium and (system_has_kms_drm or (with_gallium_zink and (freedreno_kmds.contains('kgsl') or host_machine.system() == 'darwin'"
           " or (get_option('radv-winsys') == 'ps5' and host_machine.system() != 'linux'))))")
    s = s.replace(old, new); f.write_text(s); done.append('patched meson.build (zink DRI without DRM for radv-winsys=ps5)')
else:
    done.append('already meson.build')
print('\n'.join(done))
