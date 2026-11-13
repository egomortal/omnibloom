#!/usr/bin/env python3
"""omni-gpu-pages stage 1: the extra link inputs of the stage-1 child, as a JSON list for child_build.py.
Exactly the set the CP-2 client linked with 0 undefined / 0 duplicate (stage 2, build-omni-gpupages-cp2.sh), with
our stage-1 objects in place of the CP-2 client's own: Mesa EGL/GLES/gallium target objects, the Mesa archives
(Zink without its duplicate dispatch table), and the gpu-broker client RADV last.
usage: s1_link_inputs.py OUT.json MESA_BUILD CP2_DIR S1_OBJ_DIR"""
import glob, json, sys
out, mb, cp2, obj = sys.argv[1:5]
objs = [f'{obj}/ogp-s1-child.o', f'{obj}/ogp_dri_nodrm_stubs_weak.o', f'{obj}/ogp_payload_libc_weak.o']
# Mesa's own C11 threads (src/c11/impl/threads_posix.c, MIT), built by build-omni-gpupages-cp2.sh: CP-2 try 2 showed the
# payload libc's mtx_init failing inside Zink's vkCreateInstance in a loader child; this keeps Mesa off that path.
import os
c11 = f'{cp2}/obj/c11_threads_posix.o'
if os.environ.get('OGP_S1_LIBC_C11') != '1':
    if not os.path.exists(c11): sys.exit(f'missing {c11} (run build-omni-gpupages-cp2.sh) or set OGP_S1_LIBC_C11=1')
    objs.append(c11)
mesa = sorted(glob.glob(f'{mb}/src/egl/libEGL.so.1.0.0.p/*.o') + glob.glob(f'{mb}/src/mesa/glapi/es2api/libGLESv2.so.2.0.0.p/*.o')
              + glob.glob(f'{mb}/src/gallium/targets/dri/libgallium-26.2.0.so.p/*.o'))
if not mesa: sys.exit('no Mesa target objects in ' + mb)
arch = [f'{mb}/src/gallium/frontends/dri/libdri.a', f'{cp2}/libzink-ogp.a', f'{mb}/src/gallium/winsys/zink/drm/libzinkwinsys.a',
        f'{mb}/src/gallium/auxiliary/pipe-loader/libpipe_loader_static.a', f'{mb}/src/gallium/winsys/sw/null/libws_null.a',
        f'{mb}/src/gallium/winsys/sw/wrapper/libwsw.a', f'{mb}/src/gallium/winsys/sw/dri/libswdri.a', f'{mb}/src/gallium/auxiliary/libgallium.a',
        f'{mb}/src/gallium/auxiliary/libgalliumvl.a', f'{mb}/src/mesa/libmesa.a', f'{mb}/src/mesa/libmesa_sse41.a',
        f'{mb}/src/mesa/glapi/shared-glapi/libglapi.a', f'{mb}/src/compiler/glsl/libglsl.a', f'{mb}/src/compiler/glsl/glcpp/libglcpp.a',
        f'{mb}/src/loader/libloader.a', f'{cp2}/client.a']
# --wrap=dladdr: the cache-UUID fallback in ogp-s1-child.c (a pass-through while stage 1 is off).
# OGP_S1_MAP=<path>: also write a link map with a cross-reference table (the libc convention audit reads it).
extra = ['-Wl,--wrap=dladdr', '-Wl,--wrap=pthread_create']   # pthread_create: the big-stack minimum in ogp-s1-child.c
# The weakly referenced Vulkan runtime/WSI/layer symbols the CP-2 client's link forced in (CP-2 try 4: a weak reference
# never pulls an archive member, so vk_common_GetPhysicalDeviceProperties2 & co. were NULL in the dispatch tables).
rsp = f'{cp2}/force-u.rsp'
if not os.path.exists(rsp): sys.exit(f'missing {rsp} (run build-omni-gpupages-cp2t5.sh)')
extra.append(f'-Wl,@{rsp}')
if os.environ.get('OGP_S1_MAP'): extra += [f"-Wl,-Map={os.environ['OGP_S1_MAP']}", '-Wl,--cref']
json.dump(objs + mesa + ['-Wl,--start-group'] + arch + ['-Wl,--end-group'] + extra, open(out, 'w'), indent=0)
print(f'{len(objs)} stage-1 objects, {len(mesa)} Mesa objects, {len(arch)} archives -> {out}')
