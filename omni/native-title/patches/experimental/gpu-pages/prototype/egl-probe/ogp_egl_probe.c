/* omni-gpu-pages: EGL surfaceless + GLES 3 probe (Zink over Vulkan).
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * What it proves, in order (each step prints "STEP <name> PASS|FAIL ..."):
 *   1 client   EGL_MESA_platform_surfaceless is offered by the EGL client library
 *   2 display  eglGetPlatformDisplay(SURFACELESS) + eglInitialize
 *   3 context  a GLES 3.0 context with no surface (EGL_KHR_surfaceless_context, EGL_KHR_no_config_context)
 *   4 clear    FBO (RGBA8 texture, 256x256) cleared to a known colour, glReadPixels exact
 *   5 draw     GLSL ES 3.00 program draws a triangle; inside/outside pixels exact
 *   6 threads  two threads, each with its own context current at the same time, each clears its own FBO
 *              to its own colour 200 times and reads it back. This is the property WebKit's PlayStation
 *              port says Sony's GL lacks ("does not dispatch to the context bound to the current thread"),
 *              and the reason it compiles Skia GL out with coordinated graphics.
 *   7 share    a texture made in context A is sampled in a shared context B (WebKit's compositor shares
 *              Skia's textures this way)
 *   8 teardown eglTerminate + eglReleaseThread
 * Exit 0 only when every step passes. Console build (OGP_CONSOLE): same steps, log to OGP_LOG_PATH.
 * Nothing here touches VideoOut, Agc or any file other than its own log. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef OGP_LOG_PATH
#define OGP_LOG_PATH "/data/omni/gpu-pages/egl-probe.log"
#endif

static FILE *g_log;
static int g_fail;
static void say(const char *fmt, ...)
{
    va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    fputc('\n', g_log); fflush(g_log);
}
static void step(const char *name, int ok, const char *fmt, ...)
{
    char buf[512]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    say("STEP %-8s %s %s", name, ok ? "PASS" : "FAIL", buf);
    if (!ok) g_fail++;
}
static double now_ms(void)
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
static int has_ext(const char *list, const char *ext)
{
    size_t n = strlen(ext);
    for (const char *p = list; p && (p = strstr(p, ext)); p += n)
        if ((p == list || p[-1] == ' ') && (p[n] == ' ' || p[n] == 0)) return 1;
    return 0;
}

#define W 256
#define H 256

static EGLDisplay g_dpy;
static EGLConfig g_cfg = EGL_NO_CONFIG_KHR;

static EGLContext make_context(EGLContext share)
{
    static const EGLint attrs[] = { EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 0, EGL_NONE };
    return eglCreateContext(g_dpy, g_cfg, share, attrs);
}

static GLuint make_fbo(GLuint *tex_out)
{
    GLuint tex, fbo;
    glGenTextures(1, &tex);
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, W, H);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    if (tex_out) *tex_out = tex;
    return glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE ? fbo : 0;
}

static uint32_t read_px(int x, int y)
{
    uint8_t p[4] = {0};
    glReadPixels(x, y, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, p);
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static int count_px(uint32_t want)
{
    static uint8_t buf[W * H * 4];
    glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, buf);
    int n = 0;
    for (int i = 0; i < W * H; i++) {
        uint32_t v = (uint32_t)buf[i*4] << 24 | (uint32_t)buf[i*4+1] << 16 | (uint32_t)buf[i*4+2] << 8 | buf[i*4+3];
        n += v == want;
    }
    return n;
}

static GLuint compile(GLenum type, const char *src)
{
    GLuint s = glCreateShader(type); GLint ok = 0;
    glShaderSource(s, 1, &src, NULL); glCompileShader(s);
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) { char log[512]; glGetShaderInfoLog(s, sizeof log, NULL, log); say("shader log: %s", log); return 0; }
    return s;
}

static GLuint program(const char *vs, const char *fs)
{
    GLuint v = compile(GL_VERTEX_SHADER, vs), f = compile(GL_FRAGMENT_SHADER, fs);
    if (!v || !f) return 0;
    GLuint p = glCreateProgram(); GLint ok = 0;
    glAttachShader(p, v); glAttachShader(p, f); glLinkProgram(p);
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    glDeleteShader(v); glDeleteShader(f);
    return ok ? p : 0;
}

static const char *VS =
    "#version 300 es\n"
    "const vec2 P[3] = vec2[3](vec2(-1.0,-1.0), vec2(1.0,-1.0), vec2(-1.0,1.0));\n"
    "out vec2 uv;\n"
    "void main(){ uv = P[gl_VertexID]*0.5+0.5; gl_Position = vec4(P[gl_VertexID],0.0,1.0); }\n";
static const char *FS_SOLID =
    "#version 300 es\nprecision mediump float;\nout vec4 o;\n"
    "void main(){ o = vec4(0.0, 1.0, 0.0, 1.0); }\n";
static const char *FS_TEX =
    "#version 300 es\nprecision mediump float;\nin vec2 uv;\nuniform sampler2D t;\nout vec4 o;\n"
    "void main(){ o = texture(t, uv); }\n";

/* step 6 */
struct worker { EGLContext ctx; uint32_t colour; int rounds, good; double ms; };
static void *worker_main(void *arg)
{
    struct worker *w = arg;
    if (!eglMakeCurrent(g_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, w->ctx)) return NULL;
    GLuint fbo = make_fbo(NULL);
    double t0 = now_ms();
    for (int i = 0; fbo && i < w->rounds; i++) {
        glClearColor(((w->colour >> 24) & 255) / 255.0f, ((w->colour >> 16) & 255) / 255.0f,
                     ((w->colour >> 8) & 255) / 255.0f, (w->colour & 255) / 255.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        w->good += read_px(i % W, (i * 7) % H) == w->colour;
    }
    w->ms = now_ms() - t0;
    eglMakeCurrent(g_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglReleaseThread();
    return NULL;
}

int ogp_egl_probe_run(void)
{
    double t_start = now_ms();
    /* 1 */
    const char *cext = eglQueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS);
    int surfaceless = has_ext(cext, "EGL_MESA_platform_surfaceless");
    step("client", surfaceless && has_ext(cext, "EGL_EXT_platform_base"), "client extensions: %s", cext ? cext : "(none)");
    if (!surfaceless) return 1;
    /* 2 */
    PFNEGLGETPLATFORMDISPLAYEXTPROC getPlatformDisplay =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    g_dpy = getPlatformDisplay ? getPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL) : EGL_NO_DISPLAY;
    EGLint major = 0, minor = 0;
    int init = g_dpy != EGL_NO_DISPLAY && eglInitialize(g_dpy, &major, &minor);
    step("display", init, "EGL %d.%d vendor=%s", major, minor, init ? eglQueryString(g_dpy, EGL_VENDOR) : "-");
    if (!init) return 1;
    const char *dext = eglQueryString(g_dpy, EGL_EXTENSIONS);
    say("display extensions: %s", dext);
    /* 3 */
    eglBindAPI(EGL_OPENGL_ES_API);
    if (!has_ext(dext, "EGL_KHR_no_config_context")) {
        static const EGLint want[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_NONE };
        EGLint n = 0; eglChooseConfig(g_dpy, want, &g_cfg, 1, &n);
        if (!n) g_cfg = NULL;
    }
    EGLContext a = make_context(EGL_NO_CONTEXT);
    int cur = a != EGL_NO_CONTEXT && has_ext(dext, "EGL_KHR_surfaceless_context")
              && eglMakeCurrent(g_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, a) && glGetString(GL_VERSION) != NULL;
    step("context", cur, "GL_VERSION=%s | GL_RENDERER=%s | GLSL=%s", cur ? (const char *)glGetString(GL_VERSION) : "-",
         cur ? (const char *)glGetString(GL_RENDERER) : "-", cur ? (const char *)glGetString(GL_SHADING_LANGUAGE_VERSION) : "-");
    if (!cur) return 1;
    GLint maxtex = 0; glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxtex);
    GLint samples = 0; glGetIntegerv(GL_MAX_SAMPLES, &samples);
    say("GL_MAX_TEXTURE_SIZE=%d GL_MAX_SAMPLES=%d (WebKit's Skia uses MSAA when > 0; 4K tiles need >= 4096)", maxtex, samples);
    /* 4 */
    GLuint tex = 0, fbo = make_fbo(&tex);
    glViewport(0, 0, W, H);
    glClearColor(1.0f, 0.0f, 1.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    int clear_n = fbo ? count_px(0xff00ffffu) : 0;
    step("clear", fbo && clear_n == W * H, "%d/%d pixels = ff00ffff", clear_n, W * H);
    /* 5 */
    GLuint prog = program(VS, FS_SOLID);
    GLuint vao = 0; glGenVertexArrays(1, &vao); glBindVertexArray(vao);
    if (prog) { glUseProgram(prog); glDrawArrays(GL_TRIANGLES, 0, 3); }
    uint32_t in = read_px(10, 10), out = read_px(W - 10, H - 10);
    int green = count_px(0x00ff00ffu);
    /* the triangle covers the lower-left half: (W*H - W)/2 + W pixels on its diagonal rule, so check a range */
    step("draw", prog && in == 0x00ff00ffu && out == 0xff00ffffu && green > W * H * 45 / 100 && green < W * H * 55 / 100,
         "inside=%08x outside=%08x green=%d", in, out, green);
    /* 6 */
    struct worker w[2] = { { make_context(EGL_NO_CONTEXT), 0x112233ffu, 200, 0, 0 },
                           { make_context(EGL_NO_CONTEXT), 0xccbbaaffu, 200, 0, 0 } };
    pthread_t th[2];
    for (int i = 0; i < 2; i++) pthread_create(&th[i], NULL, worker_main, &w[i]);
    for (int i = 0; i < 2; i++) pthread_join(th[i], NULL);
    step("threads", w[0].good == 200 && w[1].good == 200, "thread A %d/200 (%.1f ms), thread B %d/200 (%.1f ms)",
         w[0].good, w[0].ms, w[1].good, w[1].ms);
    eglDestroyContext(g_dpy, w[0].ctx); eglDestroyContext(g_dpy, w[1].ctx);
    /* 7: tex (magenta + green triangle) made in A is sampled in a shared context B */
    glFinish();
    EGLContext b = make_context(a);
    int share_ok = 0; uint32_t s_in = 0, s_out = 0;
    if (b != EGL_NO_CONTEXT && eglMakeCurrent(g_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, b)) {
        GLuint tex2 = 0, fbo2 = make_fbo(&tex2);
        GLuint p2 = program(VS, FS_TEX), vao2 = 0;
        glGenVertexArrays(1, &vao2); glBindVertexArray(vao2);
        glViewport(0, 0, W, H);
        glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
        if (fbo2 && p2) {
            glUseProgram(p2); glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, tex);
            glUniform1i(glGetUniformLocation(p2, "t"), 0);
            glDrawArrays(GL_TRIANGLES, 0, 3);
            s_in = read_px(10, 10); s_out = read_px(W - 10, H - 10);
            share_ok = s_in == 0x00ff00ffu && s_out == 0x000000ffu;
        }
        eglMakeCurrent(g_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        eglDestroyContext(g_dpy, b);
    }
    step("share", share_ok, "sampled shared texture: inside=%08x outside=%08x", s_in, s_out);
    /* 8 */
    eglMakeCurrent(g_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(g_dpy, a);
    int term = eglTerminate(g_dpy);
    eglReleaseThread();
    step("teardown", term, "total %.1f ms", now_ms() - t_start);
    say("RESULT %s (%d failed)", g_fail ? "FAIL" : "PASS", g_fail);
    return g_fail ? 1 : 0;
}

#ifndef OGP_NO_MAIN
int main(void)
{
#ifdef OGP_CONSOLE
    /* a title has no environment: ask EGL for Zink on the no-DRM surfaceless path (OGP_SURFACELESS_ZINK_NO_DRM),
     * and keep the first run free of shader-cache writes */
    setenv("MESA_LOADER_DRIVER_OVERRIDE", "zink", 1);
    setenv("MESA_SHADER_CACHE_DISABLE", "1", 1);
    g_log = fopen(OGP_LOG_PATH, "w");
    if (!g_log) g_log = stderr;
#else
    g_log = stdout;
#endif
    say("ogp_egl_probe v1");
    return ogp_egl_probe_run();
}
#endif
