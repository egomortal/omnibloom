#!/usr/bin/env python3
"""Opt-in SDL PS5 allocation hygiene; does not alter platform close ordering."""
from pathlib import Path
import sys

ALLOC = '    this->hidden->mixbuf = (Uint8 *)SDL_calloc(1, this->hidden->mixlen);\n'
CHECK = ALLOC + '''    /* Omni alteration: let SDL core unwind the open native handle on OOM. */
    if (!this->hidden->mixbuf) {
        return SDL_OutOfMemory();
    }
'''
CLOSE = '''    if (this->hidden->mixbuf) {
        free(this->hidden->mixbuf);
        this->hidden->mixbuf = 0;
    }
'''
CLEAN = '''    /* Omni alteration: backend owns both allocations, including failed opens. */
    SDL_free(this->hidden->mixbuf);
    SDL_free(this->hidden);
    this->hidden = NULL;
'''


def patch_source(source):
    for before, after in ((ALLOC, CHECK), (CLOSE, CLEAN)):
        if after in source:
            if source.count(after) != 1:
                raise ValueError('Duplicate SDL audio patch block')
            continue
        if source.count(before) != 1:
            raise ValueError('Unexpected SDL PS5 audio source; refusing partial patch')
        source = source.replace(before, after)
    return source


if __name__ == '__main__':
    path = Path(sys.argv[1]) / 'src/audio/ps5/SDL_ps5audio.c'
    original = path.read_text()
    result = patch_source(original)
    if result != original:
        path.write_text(result)
