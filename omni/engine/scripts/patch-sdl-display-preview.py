#!/usr/bin/env python3
"""Isolated SDL diagnostic: choose a bounded startup scanout resolution."""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'src/video/ps5/SDL_ps5video.c'
text = path.read_text()
anchor = '    mode.w = 1920;\n    mode.h = 1080;\n'
if 'OMNI_SDL_HEIGHT' not in text:
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''    /* Omni alteration: opt-in startup mode for isolated display tests. */
    const char *requested = SDL_getenv("OMNI_SDL_HEIGHT");
    if (requested && SDL_strcmp(requested, "1440") == 0) {
        mode.w = 2560; mode.h = 1440;
    } else if (requested && SDL_strcmp(requested, "2160") == 0) {
        mode.w = 3840; mode.h = 2160;
    }
    if (PS5_Tilemap_BufferSize(mode.w, mode.h) > 0x2000000)
        return SDL_SetError("Omni requested mode exceeds the video buffer capacity");
''')
    path.write_text(text)
path = pathlib.Path(sys.argv[1]) / 'src/dynapi/SDL_dynapi.h'
text = path.read_text()
if '#elif defined(__PROSPERO__)' not in text:
    text = text.replace('#elif defined(__NGAGE__)', '#elif defined(__PROSPERO__)\n#define SDL_DYNAMIC_API 0 /* Omni alteration: statically linked PS5 diagnostic. */\n#elif defined(__NGAGE__)')
    path.write_text(text)
