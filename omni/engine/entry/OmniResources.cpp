// Omni Engine: resources embedded in the ELF and installed to /data/omni on
// first run (TLS root CAs, fonts, fontconfig). OMNI_RES_DIR is set by CMake.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniResources.h"

#include <stdio.h>
#include <string.h>
#include <string>
#include <sys/stat.h>

#define OMNI_STR2(x) #x
#define OMNI_STR(x) OMNI_STR2(x)

#define OMNI_EMBED(sym, file)                                         \
    __asm__(".section .rodata\n"                                      \
            ".balign 16\n"                                            \
            ".global " #sym "_start\n" #sym "_start:\n"               \
            ".incbin \"" OMNI_STR(OMNI_RES_DIR) "/" file "\"\n"       \
            ".global " #sym "_end\n" #sym "_end:\n"                   \
            ".byte 0\n"                                               \
            ".previous\n");                                           \
    extern "C" const unsigned char sym##_start[], sym##_end[];

OMNI_EMBED(omni_res_cacert, "cacert.pem")
OMNI_EMBED(omni_res_fontsconf, "fonts.conf")
OMNI_EMBED(omni_res_dejavu, "DejaVuSans.ttf")
OMNI_EMBED(omni_res_dejavu_bold, "DejaVuSans-Bold.ttf")
OMNI_EMBED(omni_res_dejavu_serif, "DejaVuSerif.ttf")
OMNI_EMBED(omni_res_dejavu_mono, "DejaVuSansMono.ttf")

namespace {

struct Res {
    const char* path;
    const unsigned char* start;
    const unsigned char* end;
};

bool writeIfChanged(const Res& r)
{
    size_t size = (size_t)(r.end - r.start);
    struct stat st;
    if (!stat(r.path, &st) && (size_t)st.st_size == size) {
        if (FILE* old = fopen(r.path, "rb")) {
            unsigned char chunk[4096];
            size_t offset = 0;
            bool equal = true;
            while (offset < size) {
                size_t count = size - offset;
                if (count > sizeof(chunk))
                    count = sizeof(chunk);
                if (fread(chunk, 1, count, old) != count || memcmp(chunk, r.start + offset, count)) {
                    equal = false;
                    break;
                }
                offset += count;
            }
            fclose(old);
            if (equal)
                return true;
        }
    }
    const std::string temporary = std::string(r.path) + ".tmp";
    FILE* f = fopen(temporary.c_str(), "wb");
    if (!f)
        return false;
    bool ok = fwrite(r.start, 1, size, f) == size;
    if (fclose(f))
        ok = false;
    if (ok)
        ok = !rename(temporary.c_str(), r.path);
    if (!ok)
        remove(temporary.c_str());
    return ok;
}

} // namespace

int omniInstallResources(const char* root)
{
    char dir[256];
    mkdir(root, 0777);
    snprintf(dir, sizeof(dir), "%s/fonts", root);
    mkdir(dir, 0777);
    snprintf(dir, sizeof(dir), "%s/fontcache", root);
    mkdir(dir, 0777);

    char p[6][256];
    snprintf(p[0], 256, "%s/cacert.pem", root);
    snprintf(p[1], 256, "%s/fonts.conf", root);
    snprintf(p[2], 256, "%s/fonts/DejaVuSans.ttf", root);
    snprintf(p[3], 256, "%s/fonts/DejaVuSans-Bold.ttf", root);
    snprintf(p[4], 256, "%s/fonts/DejaVuSerif.ttf", root);
    snprintf(p[5], 256, "%s/fonts/DejaVuSansMono.ttf", root);
    const Res all[] = {
        { p[0], omni_res_cacert_start, omni_res_cacert_end },
        { p[1], omni_res_fontsconf_start, omni_res_fontsconf_end },
        { p[2], omni_res_dejavu_start, omni_res_dejavu_end },
        { p[3], omni_res_dejavu_bold_start, omni_res_dejavu_bold_end },
        { p[4], omni_res_dejavu_serif_start, omni_res_dejavu_serif_end },
        { p[5], omni_res_dejavu_mono_start, omni_res_dejavu_mono_end },
    };
    int failures = 0;
    for (auto& r : all)
        failures += !writeIfChanged(r);
    return failures;
}
