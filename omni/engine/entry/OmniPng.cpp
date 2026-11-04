// Omni Engine: minimal PNG writer for page snapshots (libpng from PacBrew).
// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniPng.h"

#include <png.h>
#include <stdio.h>
#include <stdlib.h>

// Input: Skia N32 premultiplied (BGRA in memory on little-endian). Output: RGB PNG.
bool omniWritePng(const char* path, const unsigned char* bgra, int width, int height, int stride)
{
    FILE* f = fopen(path, "wb");
    if (!f)
        return false;
    png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
    png_infop info = png ? png_create_info_struct(png) : nullptr;
    unsigned char* row = (unsigned char*)malloc((size_t)width * 3);
    if (!png || !info || !row || setjmp(png_jmpbuf(png))) {
        if (png)
            png_destroy_write_struct(&png, info ? &info : nullptr);
        free(row);
        fclose(f);
        return false;
    }
    png_init_io(png, f);
    png_set_IHDR(png, info, width, height, 8, PNG_COLOR_TYPE_RGB, PNG_INTERLACE_NONE,
        PNG_COMPRESSION_TYPE_DEFAULT, PNG_FILTER_TYPE_DEFAULT);
    png_set_compression_level(png, 6);
    png_write_info(png, info);
    for (int y = 0; y < height; y++) {
        const unsigned char* src = bgra + (size_t)y * stride;
        for (int x = 0; x < width; x++) {
            unsigned a = src[4 * x + 3];
            // composite premultiplied pixel over white
            row[3 * x + 0] = (unsigned char)(src[4 * x + 2] + (255 - a));
            row[3 * x + 1] = (unsigned char)(src[4 * x + 1] + (255 - a));
            row[3 * x + 2] = (unsigned char)(src[4 * x + 0] + (255 - a));
        }
        png_write_row(png, row);
    }
    png_write_end(png, nullptr);
    png_destroy_write_struct(&png, &info);
    free(row);
    fclose(f);
    return true;
}
