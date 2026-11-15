// omni-gpu-pages stage 1 (OMNI_GPU_PAGES_STAGE1_V1): the WebProcess side of GPU compositing, part 2 of 2.
// SPDX-License-Identifier: GPL-3.0-or-later (this file); WebKit's own files keep their licences.
// Included once, into AcceleratedSurfacePlayStation.cpp. No WebKit header changes.
//
// On this port a surfaceless display has NO render target: SwapChain stays Type::Invalid, createTarget()
// returns null and window() returns 0 (only the compiled-out WPE backend has one), so compositing renders into
// nothing. This adds the target: the compositor's frame goes into an offscreen framebuffer (RGBA8 colour +
// depth/stencil, which TextureMapper clips with), is flipped on the GPU into GL's bottom-up row order turned
// top-down, read back straight into a ShareableBitmap, and handed to the main thread for delivery as an
// ordinary Update (ogp-s1-drawingarea.inc). frameDone() is then posted to the compositing run loop at once:
// the compositor never waits for the UI process.
// Environment knobs (raster-env.txt): OMNI_GPU_PAGES_FLIP=0 if pages ever arrive upside down,
// OMNI_GPU_PAGES_RGBA=1 to read RGBA and swizzle on the CPU if colours ever arrive swapped.

#include <EGL/egl.h>
#include <GLES2/gl2ext.h>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <atomic>
#include <time.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>
#include <algorithm>
#include <cstdio>
#include <wtf/Lock.h>
#include <wtf/NeverDestroyed.h>
#include <cerrno>       // OMNI_GPUPAGES_ZEROCOPY_V1: the control page
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>

#ifndef GL_READ_FRAMEBUFFER
#define GL_READ_FRAMEBUFFER 0x8CA8
#endif
#ifndef GL_DRAW_FRAMEBUFFER
#define GL_DRAW_FRAMEBUFFER 0x8CA9
#endif
#ifndef GL_PACK_ROW_LENGTH
#define GL_PACK_ROW_LENGTH 0x0D02
#endif
#ifndef GL_BGRA_EXT
#define GL_BGRA_EXT 0x80E1
#endif
#ifndef GL_DEPTH24_STENCIL8
#define GL_DEPTH24_STENCIL8 0x88F0
#endif
#ifndef GL_DEPTH_STENCIL_ATTACHMENT
#define GL_DEPTH_STENCIL_ATTACHMENT 0x821A
#endif
// GLES 3.0 (Zink: 3.2). WEAK: the child links our static Mesa, which defines it; the TITLE also links this WebProcess
// code (its in-process engine) against Omni's lazy GL trampolines, which do not have it (stage 1b pair build). Stage 1
// never runs in the title (its entry points are weak and absent there), and a missing blit only turns the GPU flip off.
extern "C" void glBlitFramebuffer(GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLbitfield, GLenum) __attribute__((weak));
// OMNI_GPUPAGES_TILES_V1 (GLES 3.0, weak for the same reason): a VAO of our own for the tile-diff draw.
extern "C" void glGenVertexArrays(GLsizei, GLuint*) __attribute__((weak));
extern "C" void glBindVertexArray(GLuint) __attribute__((weak));
extern "C" void glDeleteVertexArrays(GLsizei, const GLuint*) __attribute__((weak));
#ifndef GL_VERTEX_ARRAY_BINDING
#define GL_VERTEX_ARRAY_BINDING 0x85B5
#endif
// OMNI_GPUPAGES_ASYNCREAD_V1 (GLES 3.0, weak for the same reason, and under private names bound to the real symbols so
// no GLES3 header can clash): pixel-pack buffers, mapping and fences for the pipelined readback.
extern "C" void* omniGlMapBufferRange(GLenum, GLintptr, GLsizeiptr, GLbitfield) __asm__("glMapBufferRange") __attribute__((weak));
extern "C" GLboolean omniGlUnmapBuffer(GLenum) __asm__("glUnmapBuffer") __attribute__((weak));
extern "C" void* omniGlFenceSync(GLenum, GLbitfield) __asm__("glFenceSync") __attribute__((weak));
extern "C" GLenum omniGlClientWaitSync(void*, GLbitfield, uint64_t) __asm__("glClientWaitSync") __attribute__((weak));
extern "C" void omniGlDeleteSync(void*) __asm__("glDeleteSync") __attribute__((weak));
#define OMNI_GL_PIXEL_PACK_BUFFER 0x88EB
#define OMNI_GL_STREAM_READ 0x88E1
#define OMNI_GL_MAP_READ_BIT 0x0001
#define OMNI_GL_SYNC_GPU_COMMANDS_COMPLETE 0x9117
#define OMNI_GL_SYNC_FLUSH_COMMANDS_BIT 0x00000001
#define OMNI_GL_ALREADY_SIGNALED 0x911A
#define OMNI_GL_CONDITION_SATISFIED 0x911C

namespace WebKit {

bool omniGpuPagesProcessReady();   // ogp-s1-drawingarea.inc
// OMNI_GPUPAGES_TILES_V1: a frame is either full (bounds = the whole device frame) or partial: only the changed 64x64
// tiles since the previous frame, as device-pixel rects inside bounds; the bitmap covers bounds.
void omniGpuPagesDeliverFrame(WebCore::PageIdentifier, Ref<WebCore::ShareableBitmap>&&, WebCore::IntSize deviceSize,
    WebCore::IntRect deviceBounds, Vector<WebCore::IntRect>&& deviceRects, bool full, double readbackMs);
bool omniGpuPagesTakeFullRequest();   // the main thread dropped something: the next frame must be full
bool omniGpuPagesPartialAllowed();    // false when the page scale cannot map tiles exactly (non-integer scale)
void omniGpuPagesCountUnchanged();    // a frame identical to the previous one: nothing delivered

namespace OmniGpuPagesS1Surface {
static std::atomic<uint64_t> s_willCount { 0 }, s_didCount { 0 };   // OMNI_GPUPAGES_BEAT_V1

static constexpr int kTile = 64;
static constexpr int kCell = 16;   // OMNI_GPUPAGES_TILES_V2: diff cells (8160 GPU threads at 1080p), grouped into 64-px tiles on the CPU
struct Target { GLuint fbo { 0 }, color { 0 }, depthStencil { 0 }; };
struct State {
    explicit State(WebCore::PageIdentifier pageID) : page(pageID) { }   // PageIdentifier has no default
    WebCore::PageIdentifier page;
    bool active { false }, checked { false }, bgra { true }, flip { true }, broken { false };
    EGLContext context { EGL_NO_CONTEXT };
    WebCore::IntSize size;
    Target draw, flipped, flipped2, mask;   // flipped/flipped2 alternate: this frame and the previous one
    unsigned glErrors { 0 };
    int cur { 0 };
    bool havePrev { false }, progTried { false };
    GLuint prog { 0 }, vao { 0 };
    GLint locA { -1 }, locB { -1 }, locSize { -1 };
    std::vector<uint8_t> maskBuf;
    double tWill { 0 };   // OMNI_GPUPAGES_TIMING_V2
    double lastStart { 0 };   // OMNI_GPUPAGES_PACE_V1: start of the previous frame
    unsigned frameNo { 0 };
    // OMNI_GPUPAGES_ASYNCREAD_V1: a ring of pixel-pack buffers; frame N is read into one by the GPU (no wait) and handed
    // on when its fence has passed: at the start of a later frame, or by the idle flush when no later frame comes.
    struct Slot { GLuint pbo { 0 }; size_t bytes { 0 }; void* fence { nullptr }; WebCore::IntSize size; double tIssued { 0 }; };
    static constexpr int kRing = 3;
    Slot ring[kRing];
    int ringHead { 0 }, ringPending { 0 };
    bool flushScheduled { false };
    uint64_t asyncIssued { 0 }, asyncDelivered { 0 }, asyncBlocked { 0 }, asyncIdleFlushes { 0 };
    // OMNI_GPUPAGES_ZEROCOPY_V1: the frame number a ring slot was handed to the title as (0: not held by the title)
    uint64_t zcHeld[kRing] { 0, 0, 0 };
    uint64_t zcPublished { 0 }, zcOverruns { 0 }, zcBitmapFrames { 0 };
    double asyncCopyMs { 0 }, asyncLastReport { 0 };
};

static Lock s_lock;
static std::unordered_map<const void*, std::unique_ptr<State>>& table()   // under s_lock
{
    static NeverDestroyed<std::unordered_map<const void*, std::unique_ptr<State>>> map;
    return map.get();
}
static State* find(const void* surface)
{
    Locker locker { s_lock };
    auto it = table().find(surface);
    return it == table().end() ? nullptr : it->second.get();
}

static void asyncDrop(State&);   // OMNI_GPUPAGES_ASYNCREAD_V1 (defined with the ring, below; willRender uses it)

static double nowMs()
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

// main thread, from the AcceleratedSurface constructor
static void created(const void* surface, WebCore::PageIdentifier page)
{
    if (!omniGpuPagesProcessReady()) return;   // the default: nothing is recorded, upstream runs unchanged
    auto state = std::make_unique<State>(page);   // State is not fast-malloc allocated: std, not WTF makeUnique
    state->active = WebCore::PlatformDisplay::sharedDisplay().type() == WebCore::PlatformDisplay::Type::Surfaceless;
    fprintf(stderr, "OMNI GPUPAGES surface created t=%.3f pid=%d\n", nowMs() / 1000.0, getpid());
    Locker locker { s_lock };
    table()[surface] = WTF::move(state);
}

static bool make(Target& target, WebCore::IntSize size, bool depthStencil)
{
    if (!target.color) glGenTextures(1, &target.color);
    glBindTexture(GL_TEXTURE_2D, target.color);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size.width(), size.height(), 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    if (!target.fbo) glGenFramebuffers(1, &target.fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, target.fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, target.color, 0);
    if (depthStencil) {
        if (!target.depthStencil) glGenRenderbuffers(1, &target.depthStencil);
        glBindRenderbuffer(GL_RENDERBUFFER, target.depthStencil);
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, size.width(), size.height());
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, target.depthStencil);
    }
    return glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
}

// compositing thread, context current: bind our framebuffer for the frame about to be painted
static bool willRender(const void* surface, const WebCore::IntSize& size)
{
    State* state = find(surface);
    if (!state || !state->active) return false;
    state->tWill = nowMs();
    ++s_willCount;
    EGLContext current = eglGetCurrentContext();
    if (state->context != current) {   // a new context: every GL name we held belonged to the old one
        state->draw = { }; state->flipped = { }; state->flipped2 = { }; state->mask = { };
        state->prog = 0; state->vao = 0; state->progTried = false; state->havePrev = false;
        asyncDrop(*state);   // OMNI_GPUPAGES_ASYNCREAD_V1: those buffers and fences belonged to the old context
        state->size = { };
        state->context = current;
        state->checked = false;
    }
    if (!state->checked) {
        const char* extensions = reinterpret_cast<const char*>(glGetString(GL_EXTENSIONS));
        const char* rgba = getenv("OMNI_GPU_PAGES_RGBA");
        const char* flip = getenv("OMNI_GPU_PAGES_FLIP");
        state->bgra = !(rgba && !strcmp(rgba, "1")) && extensions && strstr(extensions, "GL_EXT_read_format_bgra");
        state->flip = !(flip && !strcmp(flip, "0")) && glBlitFramebuffer;
        state->checked = true;
        fprintf(stderr, "OMNI GPUPAGES surface pid=%d: readback %s, flip %s\n", getpid(),
            state->bgra ? "BGRA (GL_EXT_read_format_bgra)" : "RGBA + CPU swizzle", state->flip ? "on the GPU (blit)" : "off");
    }
    if (size != state->size && !size.isEmpty()) {
        bool ok = make(state->draw, size, true) && (!state->flip || (make(state->flipped, size, false) && make(state->flipped2, size, false)));
        if (ok && state->flip) {
            WebCore::IntSize cells((size.width() + kCell - 1) / kCell, (size.height() + kCell - 1) / kCell);
            if (!make(state->mask, cells, false)) state->mask = { };   // no mask: every frame is read back whole
            state->maskBuf.assign(static_cast<size_t>(cells.width()) * cells.height() * 4, 0);
        }
        state->havePrev = false;
        state->size = size;
        if (!ok && !state->broken) {
            state->broken = true;
            fprintf(stderr, "OMNI GPUPAGES surface pid=%d: framebuffer %dx%d INCOMPLETE: this page will not draw (report it)\n",
                getpid(), size.width(), size.height());
        }
        if (ok) state->broken = false;
    }
    glBindFramebuffer(GL_FRAMEBUFFER, state->draw.fbo);
    glViewport(0, 0, size.width(), size.height());
    return true;
}

// OMNI_GPUPAGES_TILES_V1: the tile-diff program. One fragment per 64x64 tile of the frame: 1 when any pixel of that tile
// differs between this frame (uA) and the previous one (uB), else 0. Compiled once per context; a failure only turns
// partial frames off (every frame is then read back whole, as before).
static bool ensureDiffProgram(State& s)
{
    if (s.progTried) return s.prog;
    s.progTried = true;
    if (!glGenVertexArrays || !glBindVertexArray || !s.mask.fbo) return false;
    static const char* vs =
        "#version 300 es\n"
        "void main() { vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }\n";
    static const char* fs =
        "#version 300 es\n"
        "precision highp float; precision highp int;\n"
        "uniform highp sampler2D uA; uniform highp sampler2D uB; uniform ivec2 uSize;\n"
        "out vec4 o;\n"
        "void main() {\n"
        "  ivec2 b = ivec2(gl_FragCoord.xy) * 16; ivec2 e = min(b + 16, uSize);\n"
        "  for (int y = b.y; y < e.y; ++y) for (int x = b.x; x < e.x; ++x)\n"
        "    if (texelFetch(uA, ivec2(x, y), 0) != texelFetch(uB, ivec2(x, y), 0)) { o = vec4(1.0); return; }\n"
        "  o = vec4(0.0);\n"
        "}\n";
    auto compile = [](GLenum type, const char* text) -> GLuint {
        GLuint sh = glCreateShader(type);
        glShaderSource(sh, 1, &text, nullptr);
        glCompileShader(sh);
        GLint ok = 0; glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
        if (!ok) {
            char log[512] = ""; glGetShaderInfoLog(sh, sizeof log, nullptr, log);
            fprintf(stderr, "OMNI GPUPAGES tiles pid=%d: shader compile FAILED (%s): whole frames only\n", getpid(), log);
            glDeleteShader(sh); return 0;
        }
        return sh;
    };
    GLuint v = compile(GL_VERTEX_SHADER, vs), f = v ? compile(GL_FRAGMENT_SHADER, fs) : 0;
    if (!v || !f) { if (v) glDeleteShader(v); return false; }
    GLuint p = glCreateProgram();
    glAttachShader(p, v); glAttachShader(p, f); glLinkProgram(p);
    glDeleteShader(v); glDeleteShader(f);
    GLint ok = 0; glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[512] = ""; glGetProgramInfoLog(p, sizeof log, nullptr, log);
        fprintf(stderr, "OMNI GPUPAGES tiles pid=%d: program link FAILED (%s): whole frames only\n", getpid(), log);
        glDeleteProgram(p); return false;
    }
    s.prog = p;
    s.locA = glGetUniformLocation(p, "uA"); s.locB = glGetUniformLocation(p, "uB"); s.locSize = glGetUniformLocation(p, "uSize");
    glGenVertexArrays(1, &s.vao);
    fprintf(stderr, "OMNI GPUPAGES tiles pid=%d: tile diff on (%dx%d px tiles): only changed tiles are read back\n", getpid(), kTile, kTile);
    return true;
}

// Runs the diff into the mask and reads it back; restores every piece of GL state it touches (TextureMapper's).
static bool diffTiles(State& s, const Target& curT, const Target& prevT, int cellsX, int cellsY)
{
    GLint program = 0, active = 0, tex0 = 0, tex1 = 0, vao = 0, viewport[4] = { 0, 0, 0, 0 }, packAlign = 4;
    GLboolean mask[4] = { GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE };
    glGetIntegerv(GL_CURRENT_PROGRAM, &program); glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
    glActiveTexture(GL_TEXTURE0); glGetIntegerv(GL_TEXTURE_BINDING_2D, &tex0);
    glActiveTexture(GL_TEXTURE1); glGetIntegerv(GL_TEXTURE_BINDING_2D, &tex1);
    glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao); glGetIntegerv(GL_VIEWPORT, viewport); glGetIntegerv(GL_PACK_ALIGNMENT, &packAlign);
    glGetBooleanv(GL_COLOR_WRITEMASK, mask);
    const GLenum caps[] = { GL_BLEND, GL_SCISSOR_TEST, GL_DEPTH_TEST, GL_STENCIL_TEST, GL_CULL_FACE };
    GLboolean was[5];
    for (int i = 0; i < 5; ++i) { was[i] = glIsEnabled(caps[i]); glDisable(caps[i]); }

    glBindFramebuffer(GL_FRAMEBUFFER, s.mask.fbo);
    glViewport(0, 0, cellsX, cellsY);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glUseProgram(s.prog);
    glBindVertexArray(s.vao);
    glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, prevT.color);
    glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, curT.color);
    glUniform1i(s.locA, 0); glUniform1i(s.locB, 1); glUniform2i(s.locSize, s.size.width(), s.size.height());
    glDrawArrays(GL_TRIANGLES, 0, 3);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glReadPixels(0, 0, cellsX, cellsY, GL_RGBA, GL_UNSIGNED_BYTE, s.maskBuf.data());
    bool ok = glGetError() == GL_NO_ERROR;

    for (int i = 0; i < 5; ++i) if (was[i]) glEnable(caps[i]);
    glColorMask(mask[0], mask[1], mask[2], mask[3]);
    glPixelStorei(GL_PACK_ALIGNMENT, packAlign);
    glViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
    glBindVertexArray(static_cast<GLuint>(vao));
    glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, static_cast<GLuint>(tex1));
    glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, static_cast<GLuint>(tex0));
    glActiveTexture(static_cast<GLenum>(active));
    glUseProgram(static_cast<GLuint>(program));
    return ok;
}

// OMNI_GPUPAGES_ASYNCREAD_V1: the pipelined readback. The synchronous path waits on the title's shared GPU queue twice
// per frame (the tile-diff mask, then the pixels: ~6 ms p50, tails to 50+ ms), all on the compositor thread. Here the
// GPU copies the flipped frame into a pixel-pack buffer and the thread goes on; the frame is handed to the main thread
// once its fence has passed. Frames are always whole (no diff: while scrolling ~77% of frames were whole anyway).
// Opt-in while it is tested: /data/omni/gpu-pages-asyncread.flag; gpu-pages-asyncread-off.flag wins. Any failure
// (missing entry point, no buffer, no mapping) turns it off for the process and the synchronous path runs as before.
static std::atomic<int> s_asyncBroken { 0 };
static bool asyncReadOn()
{
    static const bool wanted = !access("/data/omni/gpu-pages-asyncread.flag", F_OK) && access("/data/omni/gpu-pages-asyncread-off.flag", F_OK);
    static const bool have = omniGlMapBufferRange && omniGlUnmapBuffer && omniGlFenceSync && omniGlClientWaitSync && omniGlDeleteSync;
    static std::atomic<bool> logged { false };
    if (wanted && !logged.exchange(true))
        fprintf(stderr, "OMNI GPUPAGES asyncread pid=%d: %s\n", getpid(), have ? "ON (pipelined readback, ring of 3)" : "OFF: GLES 3 entry points missing");
    return wanted && have && !s_asyncBroken.load();
}

static void asyncDrop(State& s)   // the context went away or broke: forget the ring without touching GL
{
    for (auto& slot : s.ring) slot = { };
    s.ringHead = 0; s.ringPending = 0;
}

static void asyncFreeGL(State& s)   // context current
{
    for (auto& slot : s.ring) {
        if (slot.fence) omniGlDeleteSync(slot.fence);
        if (slot.pbo) glDeleteBuffers(1, &slot.pbo);
        slot = { };
    }
    s.ringHead = 0; s.ringPending = 0;
}

// OMNI_GPUPAGES_ZEROCOPY_V1 (see outputs/omni-gpu-pages/ZERO-COPY-DESIGN.md). The ring's buffers are broker host memory:
// mapped at the SAME address in the title, which can import them for its GPU. When the title asks for it (consumer == 1
// in the control page), a finished frame is published as {frame, address, size} instead of being copied into a
// ShareableBitmap; its slot is then left alone until the title reports it consumed. Otherwise: the bitmap path.
struct OmniZcCtl {
    uint32_t magic, version;
    int32_t pid, consumer;       // consumer: written by the title (1: GPU, addresses; 0: bitmaps)
    uint32_t seq;                // odd while the engine writes a frame record
    uint32_t slot, width, height, stride, pad;
    uint64_t address, frame;     // the published frame (frame numbers start at 1)
    uint64_t consumed;           // written by the title: the last frame its GPU finished reading
    uint64_t titleBeat;          // written by the title each time it looks
    uint64_t engineBeat;         // written here each frame
};
static constexpr uint32_t kZcMagic = 0x5a43504fu;   // "OPCZ"
static bool zcWanted()
{
    static const bool on = !access("/data/omni/gpu-pages-zerocopy.flag", F_OK) && access("/data/omni/gpu-pages-zerocopy-off.flag", F_OK);
    return on;
}
static std::atomic<int> s_zcBroken { 0 };
static OmniZcCtl* zcCtl()
{
    static OmniZcCtl* ctl = nullptr;
    static bool tried = false;
    if (tried) return ctl;
    tried = true;
    char path[96]; snprintf(path, sizeof path, "/data/omni/gpu-pages/zc-%d.ctl", getpid());
    int fd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0666);
    if (fd < 0 || ftruncate(fd, 4096)) { fprintf(stderr, "OMNI GPUPAGES zerocopy pid=%d: control page %s FAILED (%s): bitmaps only\n", getpid(), path, strerror(errno)); if (fd >= 0) close(fd); return nullptr; }
    void* m = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (m == MAP_FAILED) { fprintf(stderr, "OMNI GPUPAGES zerocopy pid=%d: control page map FAILED: bitmaps only\n", getpid()); return nullptr; }
    ctl = static_cast<OmniZcCtl*>(m);
    memset(ctl, 0, sizeof *ctl);
    ctl->version = 1; ctl->pid = getpid();
    __atomic_store_n(&ctl->magic, kZcMagic, __ATOMIC_RELEASE);
    fprintf(stderr, "OMNI GPUPAGES zerocopy pid=%d: control page %s ready (the title chooses GPU or bitmaps)\n", getpid(), path);
    return ctl;
}
// The broker's host windows (gpu-broker/protocol.h): the only memory the title can see at the same address.
static bool zcInBrokerWindow(uint64_t a, uint64_t bytes)
{
    auto in = [&](uint64_t base, uint64_t len) { return a >= base && bytes <= len && a - base <= len - bytes; };
    return in(UINT64_C(0x240000000), UINT64_C(512) << 20) || in(UINT64_C(0x3000000000), UINT64_C(16) << 30);
}
// The slot is about to be written again: if the title still holds it, wait a little for its GPU to finish reading.
static void zcWaitSlot(State& s, int index)
{
    OmniZcCtl* ctl = zcCtl();
    if (!ctl || !s.zcHeld[index]) return;
    for (int i = 0; i < 20 && __atomic_load_n(&ctl->consumed, __ATOMIC_ACQUIRE) < s.zcHeld[index]; ++i) usleep(1000);
    if (__atomic_load_n(&ctl->consumed, __ATOMIC_ACQUIRE) < s.zcHeld[index]) ++s.zcOverruns;   // reused anyway (counted)
    s.zcHeld[index] = 0;
}
// Publishes the oldest slot (fence passed) to the title. false: the title does not want GPU frames (or this cannot work).
static bool zcPublish(State& s, State::Slot& slot, int index)
{
    if (!zcWanted() || s_zcBroken.load()) return false;
    OmniZcCtl* ctl = zcCtl();
    if (!ctl) return false;
    __atomic_store_n(&ctl->engineBeat, ctl->engineBeat + 1, __ATOMIC_RELAXED);
    if (__atomic_load_n(&ctl->consumer, __ATOMIC_ACQUIRE) != 1) return false;
    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, slot.pbo);
    void* p = omniGlMapBufferRange(OMNI_GL_PIXEL_PACK_BUFFER, 0, static_cast<GLsizeiptr>(slot.bytes), OMNI_GL_MAP_READ_BIT);
    if (p) omniGlUnmapBuffer(OMNI_GL_PIXEL_PACK_BUFFER);   // only the address is needed: the memory stays where it is
    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, 0);
    const uint64_t a = reinterpret_cast<uint64_t>(p);
    if (!p || !zcInBrokerWindow(a, slot.bytes)) {
        if (!s_zcBroken.exchange(1))
            fprintf(stderr, "OMNI GPUPAGES zerocopy pid=%d: frame buffer at %p (%zu bytes) is %s: bitmaps only\n", getpid(), p, slot.bytes,
                p ? "OUTSIDE the broker's shared windows" : "not mappable");
        return false;
    }
    const uint64_t frame = ++s.zcPublished;
    uint32_t seq = __atomic_load_n(&ctl->seq, __ATOMIC_RELAXED);
    __atomic_store_n(&ctl->seq, seq + 1, __ATOMIC_RELEASE);   // odd: writing
    ctl->slot = static_cast<uint32_t>(index); ctl->width = static_cast<uint32_t>(slot.size.width()); ctl->height = static_cast<uint32_t>(slot.size.height());
    ctl->stride = static_cast<uint32_t>(slot.size.width() * 4); ctl->address = a; ctl->frame = frame;
    __atomic_store_n(&ctl->seq, seq + 2, __ATOMIC_RELEASE);   // even: complete
    s.zcHeld[index] = frame;
    if (frame == 1 || !(frame % 600))
        fprintf(stderr, "OMNI GPUPAGES zerocopy pid=%d: published frame %llu at %p %dx%d (consumed %llu, overruns %llu, bitmap frames %llu)\n", getpid(),
            (unsigned long long)frame, p, slot.size.width(), slot.size.height(), (unsigned long long)__atomic_load_n(&ctl->consumed, __ATOMIC_ACQUIRE),
            (unsigned long long)s.zcOverruns, (unsigned long long)s.zcBitmapFrames);
    return true;
}

// Hands the oldest pending frame to the main thread if its fence has passed (or, with waitMs > 0, once it passes within
// waitMs). Context current. false: nothing pending, or not ready yet.
static bool asyncDeliverOldest(State& s, double waitMs)
{
    if (!s.ringPending) return false;
    State::Slot& slot = s.ring[s.ringHead];
    const uint64_t timeout = waitMs > 0 ? static_cast<uint64_t>(waitMs * 1e6) : 0;
    const GLenum r = omniGlClientWaitSync(slot.fence, waitMs > 0 ? OMNI_GL_SYNC_FLUSH_COMMANDS_BIT : 0, timeout);
    if (r != OMNI_GL_ALREADY_SIGNALED && r != OMNI_GL_CONDITION_SATISFIED) return false;
    if (waitMs > 0) ++s.asyncBlocked;
    if (zcPublish(s, slot, s.ringHead)) {   // OMNI_GPUPAGES_ZEROCOPY_V1: the title reads it in place; no bitmap, no copy
        omniGlDeleteSync(slot.fence); slot.fence = nullptr;
        s.ringHead = (s.ringHead + 1) % State::kRing; --s.ringPending;
        ++s.asyncDelivered;
        return true;
    }
    if (zcWanted()) ++s.zcBitmapFrames;
    const double t0 = nowMs();
    const int w = slot.size.width(), h = slot.size.height();
    WebCore::IntRect bounds(0, 0, w, h);
    WebCore::ShareableBitmapConfiguration configuration { bounds.size() };
    const unsigned stride = configuration.bytesPerRow();
    RefPtr bitmap = WebCore::ShareableBitmap::create(configuration);
    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, slot.pbo);
    const uint8_t* src = static_cast<const uint8_t*>(omniGlMapBufferRange(OMNI_GL_PIXEL_PACK_BUFFER, 0, static_cast<GLsizeiptr>(slot.bytes), OMNI_GL_MAP_READ_BIT));
    bool ok = src && bitmap && bitmap->mutableSpan().size() >= static_cast<size_t>(stride) * h;
    if (ok) {
        uint8_t* dst = bitmap->mutableSpan().data();
        const size_t row = static_cast<size_t>(w) * 4;
        for (int y = 0; y < h; ++y) memcpy(dst + static_cast<size_t>(y) * stride, src + static_cast<size_t>(y) * row, row);
        if (!s.bgra)
            for (int y = 0; y < h; ++y) { uint8_t* p = dst + static_cast<size_t>(y) * stride; for (int x = 0; x < w; ++x) std::swap(p[x * 4], p[x * 4 + 2]); }
    }
    if (src) omniGlUnmapBuffer(OMNI_GL_PIXEL_PACK_BUFFER);
    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, 0);
    omniGlDeleteSync(slot.fence); slot.fence = nullptr;
    s.ringHead = (s.ringHead + 1) % State::kRing; --s.ringPending;
    if (!ok) {
        if (!s_asyncBroken.exchange(1))
            fprintf(stderr, "OMNI GPUPAGES asyncread pid=%d: %s: back to the synchronous readback\n", getpid(), src ? "no bitmap memory" : "map FAILED");
        return false;
    }
    const double copyMs = nowMs() - t0, latencyMs = nowMs() - slot.tIssued;
    s.asyncCopyMs += copyMs; ++s.asyncDelivered;
    if (nowMs() - s.asyncLastReport >= 2000) {
        fprintf(stderr, "OMNI GPUPAGES asyncread pid=%d: issued=%llu delivered=%llu blocked=%llu idleFlush=%llu copyMs/frame=%.2f lastLatencyMs=%.1f\n",
            getpid(), (unsigned long long)s.asyncIssued, (unsigned long long)s.asyncDelivered, (unsigned long long)s.asyncBlocked,
            (unsigned long long)s.asyncIdleFlushes, s.asyncDelivered ? s.asyncCopyMs / s.asyncDelivered : 0.0, latencyMs);
        s.asyncLastReport = nowMs();
    }
    Vector<WebCore::IntRect> rects; rects.append(bounds);
    RunLoop::mainSingleton().dispatch([page = s.page, bitmap = bitmap.releaseNonNull(), size = slot.size, bounds, rects = WTF::move(rects), copyMs]() mutable {
        omniGpuPagesDeliverFrame(page, WTF::move(bitmap), size, bounds, WTF::move(rects), true, copyMs);
    });
    return true;
}

// No later frame came: hand on whatever is still pending, so the last frame of a burst is never held back.
static void asyncIdleFlush(const void* surface)
{
    State* s = find(surface);
    if (!s) return;
    s->flushScheduled = false;
    if (!s->ringPending) return;
    // frames still coming: the next frame hands these on; look again later rather than block the compositor here
    const double newest = s->ring[(s->ringHead + s->ringPending - 1) % State::kRing].tIssued;
    if (nowMs() - newest < 20) {
        s->flushScheduled = true;
        RunLoop::currentSingleton().dispatchAfter(Seconds::fromMilliseconds(25), [surface] { asyncIdleFlush(surface); });
        return;
    }
    EGLContext prev = eglGetCurrentContext();
    EGLDisplay display = WebCore::PlatformDisplay::sharedDisplay().eglDisplay();
    EGLSurface prevDraw = eglGetCurrentSurface(EGL_DRAW), prevRead = eglGetCurrentSurface(EGL_READ);
    const bool switched = prev != s->context;
    if (switched && !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, s->context)) return;   // try again next frame
    ++s->asyncIdleFlushes;
    while (s->ringPending && asyncDeliverOldest(*s, 100)) { }
    if (switched) eglMakeCurrent(display, prevDraw, prevRead, prev);
}

// The flipped frame (source FBO) goes into the next ring buffer; earlier frames whose copies are done are handed on first.
static bool didRenderAsync(const void* surface, State& s, GLuint source, int w, int h)
{
    while (asyncDeliverOldest(s, 0)) { }                                  // done copies, oldest first, no waiting
    if (s.ringPending == State::kRing && !asyncDeliverOldest(s, 100)) {   // ring full: wait for the oldest (bounded)
        if (s_asyncBroken.load()) return false;
        asyncFreeGL(s);                                                    // a copy that never finished: start over
    }
    if (s_asyncBroken.load()) return false;
    const int slotIndex = (s.ringHead + s.ringPending) % State::kRing;
    zcWaitSlot(s, slotIndex);   // OMNI_GPUPAGES_ZEROCOPY_V1: not while the title's GPU may still read it
    State::Slot& slot = s.ring[slotIndex];
    const size_t bytes = static_cast<size_t>(w) * h * 4;
    if (!slot.pbo) glGenBuffers(1, &slot.pbo);
    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, slot.pbo);
    if (slot.bytes != bytes) { glBufferData(OMNI_GL_PIXEL_PACK_BUFFER, static_cast<GLsizeiptr>(bytes), nullptr, OMNI_GL_STREAM_READ); slot.bytes = bytes; }
    glBindFramebuffer(GL_FRAMEBUFFER, source);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glReadPixels(0, 0, w, h, s.bgra ? GL_BGRA_EXT : GL_RGBA, GL_UNSIGNED_BYTE, nullptr);   // into the buffer: no wait
    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, 0);
    slot.fence = omniGlFenceSync(OMNI_GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    if (slot.fence) omniGlClientWaitSync(slot.fence, OMNI_GL_SYNC_FLUSH_COMMANDS_BIT, 0);   // flushes the copy to the GPU without waiting (no glFlush: the title's SDK stub lacks it)
    glBindFramebuffer(GL_FRAMEBUFFER, s.draw.fbo);
    if (GLenum error = glGetError(); error != GL_NO_ERROR || !slot.fence) {
        if (!s_asyncBroken.exchange(1))
            fprintf(stderr, "OMNI GPUPAGES asyncread pid=%d: issue FAILED (GL error 0x%x, fence %p): back to the synchronous readback\n", getpid(), error, slot.fence);
        if (slot.fence) { omniGlDeleteSync(slot.fence); slot.fence = nullptr; }
        return false;
    }
    slot.size = WebCore::IntSize(w, h); slot.tIssued = nowMs();
    ++s.ringPending; ++s.asyncIssued;
    if (s.flip) { s.cur ^= 1; s.havePrev = false; }   // whole frames only: the diff's previous frame is not kept
    if (!s.flushScheduled) {
        s.flushScheduled = true;
        RunLoop::currentSingleton().dispatchAfter(Seconds::fromMilliseconds(25), [surface] { asyncIdleFlush(surface); });
    }
    return true;
}

// compositing thread, context current, frame painted: read it back (whole, or only its changed tiles) and send it to
// the main thread
static bool didRenderImpl(const void* surface)
{
    State* state = find(surface);
    if (!state || !state->active) return false;
    if (state->broken || state->size.isEmpty()) return true;
    double t0 = nowMs();
    const int w = state->size.width(), h = state->size.height();
    const bool fullRequested = omniGpuPagesTakeFullRequest();
    GLuint source = state->draw.fbo;
    Target* curT = state->cur ? &state->flipped2 : &state->flipped;
    Target* prevT = state->cur ? &state->flipped : &state->flipped2;
    if (state->flip) {
        glBindFramebuffer(GL_READ_FRAMEBUFFER, state->draw.fbo);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, curT->fbo);
        glBlitFramebuffer(0, 0, w, h, 0, h, w, 0, GL_COLOR_BUFFER_BIT, GL_NEAREST);
        source = curT->fbo;
    }
    // OMNI_GPUPAGES_ASYNCREAD_V1: pipelined whole-frame readback when on; its failure falls through to the code below
    if (asyncReadOn() && didRenderAsync(surface, *state, source, w, h)) {
        if (++state->frameNo <= 40 || !(state->frameNo % 500))
            fprintf(stderr, "OMNI GPUPAGES frame n=%u t=%.3f paint=%.1f read=%.1f full=1 rects=1 async=1\n", state->frameNo, nowMs() / 1000.0,
                t0 - state->tWill, nowMs() - t0);
        return true;
    }

    // Which part to read: whole, nothing (unchanged), or the changed tiles merged into rects.
    bool full = true;
    Vector<WebCore::IntRect> rects;
    const int tilesX = (w + kTile - 1) / kTile, tilesY = (h + kTile - 1) / kTile;
    const int cellsX = (w + kCell - 1) / kCell, cellsY = (h + kCell - 1) / kCell;
    std::vector<uint8_t> tileMask;
    if (state->flip && state->havePrev && !fullRequested && omniGpuPagesPartialAllowed() && ensureDiffProgram(*state)
        && state->maskBuf.size() == static_cast<size_t>(cellsX) * cellsY * 4 && diffTiles(*state, *curT, *prevT, cellsX, cellsY)) {
        full = false;
        tileMask.assign(static_cast<size_t>(tilesX) * tilesY, 0);
        const int per = kTile / kCell;
        for (int cy = 0; cy < cellsY; ++cy)
            for (int cx = 0; cx < cellsX; ++cx)
                if (state->maskBuf[(static_cast<size_t>(cy) * cellsX + cx) * 4]) tileMask[static_cast<size_t>(cy / per) * tilesX + cx / per] = 1;
        long dirty = 0;
        struct Run { int x0, x1, y0, y1; };
        std::vector<Run> open, done;
        for (int ty = 0; ty < tilesY; ++ty) {
            std::vector<Run> row;
            for (int tx = 0; tx < tilesX; ) {
                if (!tileMask[static_cast<size_t>(ty) * tilesX + tx]) { ++tx; continue; }
                int start = tx;
                while (tx < tilesX && tileMask[static_cast<size_t>(ty) * tilesX + tx]) ++tx;
                row.push_back({ start, tx, ty, ty + 1 });
                dirty += tx - start;
            }
            std::vector<Run> next;
            for (auto& r : row) {   // a run with the same columns as an open rect ending on the row above extends it
                bool merged = false;
                for (auto& o : open)
                    if (o.x0 == r.x0 && o.x1 == r.x1 && o.y1 == ty) { o.y1 = ty + 1; next.push_back(o); o.y1 = -1; merged = true; break; }
                if (!merged) next.push_back(r);
            }
            for (auto& o : open) if (o.y1 != -1) done.push_back(o);
            open = std::move(next);
        }
        for (auto& o : open) done.push_back(o);
        if (!dirty) {   // nothing changed: nothing to send; this frame becomes the previous one
            state->cur ^= 1;
            glBindFramebuffer(GL_FRAMEBUFFER, state->draw.fbo);
            omniGpuPagesCountUnchanged();
            return true;
        }
        if (dirty * 2 > static_cast<long>(tilesX) * tilesY || done.size() > 48)
            full = true;   // most of the frame changed: one whole read is cheaper than many pieces
        else
            for (auto& r : done)
                rects.append(WebCore::IntRect(r.x0 * kTile, r.y0 * kTile,
                    std::min(r.x1 * kTile, w) - r.x0 * kTile, std::min(r.y1 * kTile, h) - r.y0 * kTile));
    }

    WebCore::IntRect bounds(0, 0, w, h);
    if (full) { rects.clear(); rects.append(bounds); }
    else {
        bounds = rects[0];
        for (auto& r : rects) bounds.unite(r);
    }
    WebCore::ShareableBitmapConfiguration configuration { bounds.size() };
    const unsigned stride = configuration.bytesPerRow();
    RefPtr bitmap = WebCore::ShareableBitmap::create(configuration);
    if (!bitmap || bitmap->mutableSpan().size() < static_cast<size_t>(stride) * bounds.height() || stride % 4) {
        glBindFramebuffer(GL_FRAMEBUFFER, state->draw.fbo);
        state->havePrev = false;   // no memory for this frame: skip it; the next one is read whole
        return true;
    }
    glBindFramebuffer(GL_FRAMEBUFFER, source);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glPixelStorei(GL_PACK_ROW_LENGTH, static_cast<GLint>(stride / 4));
    uint8_t* pixels = bitmap->mutableSpan().data();
    // OMNI_GPUPAGES_TILES_V2: one read per frame (each read is a GPU submit + wait on the title's shared queue)
    glReadPixels(bounds.x(), bounds.y(), bounds.width(), bounds.height(), state->bgra ? GL_BGRA_EXT : GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    if (!state->bgra) {
        for (int y = 0; y < bounds.height(); ++y) {
            uint8_t* row = pixels + static_cast<size_t>(y) * stride;
            for (int x = 0; x < bounds.width(); ++x) std::swap(row[x * 4], row[x * 4 + 2]);
        }
    }
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glBindFramebuffer(GL_FRAMEBUFFER, state->draw.fbo);
    if (GLenum error = glGetError(); error != GL_NO_ERROR && state->glErrors++ < 5)
        fprintf(stderr, "OMNI GPUPAGES surface pid=%d: GL error 0x%x after readback\n", getpid(), error);
    if (state->flip) { state->cur ^= 1; state->havePrev = true; }
    double readbackMs = nowMs() - t0;
    if (++state->frameNo <= 40 || !(state->frameNo % 500))
        fprintf(stderr, "OMNI GPUPAGES frame n=%u t=%.3f paint=%.1f read=%.1f full=%d rects=%zu\n", state->frameNo, nowMs() / 1000.0,
            t0 - state->tWill, readbackMs, full ? 1 : 0, rects.size());
    RunLoop::mainSingleton().dispatch([page = state->page, bitmap = bitmap.releaseNonNull(), size = state->size, bounds, rects = WTF::move(rects), full, readbackMs]() mutable {
        omniGpuPagesDeliverFrame(page, WTF::move(bitmap), size, bounds, WTF::move(rects), full, readbackMs);
    });
    return true;
}

// OMNI_GPUPAGES_PACE_V1: the surface signals frameDone() as soon as a frame is read back, so without pacing the
// compositor (and the page's requestAnimationFrame) ran flat out: ~85-230 full GPU frames a second, each with a diff and
// a readback on the title's one GPU queue, which the video shares. One frame per display refresh (16.7 ms) at most: the
// compositor thread waits out the rest of the interval here, before frameDone is dispatched.
// /data/omni/gpu-pages-nopace.flag turns it off.
static bool didRender(const void* surface)
{
    bool ours = didRenderImpl(surface);
    if (!ours) return false;
    ++s_didCount;
    static const bool pace = access("/data/omni/gpu-pages-nopace.flag", F_OK) != 0;
    State* state = find(surface);
    if (!pace || !state) return true;
    constexpr double kIntervalMs = 1000.0 / 60.0;
    double wait = state->tWill + kIntervalMs - nowMs();   // this frame began at tWill (willRender)
    if (wait > 0.5) usleep(static_cast<useconds_t>(std::min(wait, kIntervalMs) * 1000));
    return true;
}

// compositing thread, context current, before the context goes away
static void destroyed(const void* surface)
{
    std::unique_ptr<State> state;
    {
        Locker locker { s_lock };
        auto it = table().find(surface);
        if (it == table().end()) return;
        state = WTF::move(it->second);
        table().erase(it);
    }
    if (state->context != eglGetCurrentContext()) return;   // not ours to delete in another context
    if (asyncReadOn()) {   // OMNI_GPUPAGES_ASYNCREAD_V1: hand on what is still pending, then free the ring
        while (state->ringPending && asyncDeliverOldest(*state, 100)) { }
        asyncFreeGL(*state);
    }
    if (state->prog) glDeleteProgram(state->prog);
    if (state->vao && glDeleteVertexArrays) glDeleteVertexArrays(1, &state->vao);
    for (Target* target : { &state->draw, &state->flipped, &state->flipped2, &state->mask }) {
        if (target->fbo) glDeleteFramebuffers(1, &target->fbo);
        if (target->color) glDeleteTextures(1, &target->color);
        if (target->depthStencil) glDeleteRenderbuffers(1, &target->depthStencil);
    }
}

} // namespace OmniGpuPagesS1Surface
} // namespace WebKit

// OMNI_GPUPAGES_BEAT_V1: read by the hangdog thread in ogp-s1-drawingarea.inc
extern "C" void omniGpuPagesSurfaceCounts(uint64_t* will, uint64_t* did)
{
    *will = WebKit::OmniGpuPagesS1Surface::s_willCount.load();
    *did = WebKit::OmniGpuPagesS1Surface::s_didCount.load();
}
