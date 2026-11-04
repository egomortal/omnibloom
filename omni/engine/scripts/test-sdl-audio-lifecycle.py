#!/usr/bin/env python3
"""Host C mock test of patched real SDL open/close functions. Pass SDL root."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

spec = importlib.util.spec_from_file_location('patch', Path(__file__).with_name('patch-sdl-audio-lifecycle.py'))
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
source = (Path(sys.argv[1]) / 'src/audio/ps5/SDL_ps5audio.c').read_text()
patched = patch.patch_source(source)
assert patch.patch_source(patched) == patched
try:
    patch.patch_source('unrecognized source')
except ValueError:
    pass
else:
    raise AssertionError('Unexpected input accepted')

def function(name):
    start = patched.index('static ', patched.rfind('\n', 0, patched.index(name)))
    opening = patched.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (patched[end] == '{') - (patched[end] == '}')
        end += 1
    return patched[start:end]

mock = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t Uint16;
typedef uint8_t Uint8;
typedef int SDL_AudioFormat;
#define AUDIO_S16LSB 1
#define AUDIO_F32LSB 2
#define PROSPERO_AUDIO_OUT_PARAM_FORMAT_S16_MONO 0
#define PROSPERO_AUDIO_OUT_PARAM_FORMAT_S16_STEREO 1
#define PROSPERO_AUDIO_OUT_PARAM_FORMAT_FLOAT_MONO 3
#define PROSPERO_AUDIO_OUT_PARAM_FORMAT_FLOAT_STEREO 4
#define PROSPERO_USER_SERVICE_USER_ID_SYSTEM 255
#define PROSPERO_AUDIO_OUT_PORT_TYPE_MAIN 0
struct SDL_PrivateAudioData { int handle; Uint8 *mixbuf; int mixlen; };
typedef struct { struct SDL_PrivateAudioData *hidden;
    struct { int format,channels,samples,freq,size; } spec; } Device;
#define _THIS Device *this
static int allocations, calls, fail_at, ports, open_fails;
static void *SDL_calloc(size_t a,size_t b) {
    if (++calls==fail_at) return NULL;
    void *p=calloc(a,b); if(p) allocations++; return p;
}
static void SDL_free(void *p) { if(p) { allocations--; free(p); } }
static int SDL_OutOfMemory(void) { return -1; }
static int SDL_SetError(const char *format,...) { (void)format; return -1; }
static int SDL_FirstAudioFormat(int f) { return f; }
static int SDL_NextAudioFormat(void) { return 0; }
static void SDL_CalculateAudioSpec(void *d) { (void)d; }
static int sceAudioOutOpen(int a,int b,int c,int d,int e,int f) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;
    if(open_fails) return -1; ports++; return 1;
}
static int sceAudioOutClose(int h) { assert(h==1); ports--; return 0; }
'''
tail = r'''
static void attempt(int failure,int native_failure,int format,int expected) {
    Device d={0}; d.spec.format=format;d.spec.channels=2;
    d.spec.samples=1024;d.spec.size=4096;
    calls=0;fail_at=failure;open_fails=native_failure;
    int r=PS5AUDIO_OpenDevice(&d,NULL); assert((r==0)==expected);
    /* SDL core invokes backend close iff hidden exists, even on open failure. */
    if(d.hidden) PS5AUDIO_CloseDevice(&d);
    assert(!d.hidden);assert(allocations==0);assert(ports==0);
}
int main(void) {
    for(int i=0;i<1000;i++) attempt(0,0,AUDIO_S16LSB,1);
    attempt(1,0,AUDIO_S16LSB,0); /* private allocation fails */
    attempt(2,0,AUDIO_S16LSB,0); /* mix buffer fails after native open */
    attempt(0,1,AUDIO_S16LSB,0); /* native open fails */
    attempt(0,0,99,0);          /* unsupported format */
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='omni-audio-mock-') as directory:
    c = Path(directory) / 'test.c'
    exe = Path(directory) / 'test'
    c.write_text(mock + '\n'.join(function(n) for n in
        ('PS5AUDIO_SampleSize', 'PS5AUDIO_OpenDevice', 'PS5AUDIO_CloseDevice')) + tail)
    subprocess.run(['cc', '-std=c99', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: 1000 lifecycles, four failure paths, idempotency, source drift refusal')
