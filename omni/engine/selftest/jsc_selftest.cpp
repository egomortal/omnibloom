/* Omni Engine - JavaScriptCore on-console self test.
 *
 * Embeds JavaScriptCore (WebKit's PlayStation port, built with the homebrew
 * SDK) through its public C API, runs a battery of checks covering the
 * language, the runtime library, ICU-backed Unicode/Intl and raw CPU speed,
 * and reports the outcome:
 *   - stdout (visible when sent with `nc` to elfldr on many setups)
 *   - /data/omni/jsc-selftest.txt
 *   - a PS5 system notification with the summary line
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include <JavaScriptCore/JavaScript.h>

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#ifdef __PROSPERO__
typedef struct {
  char useless1[45];
  char message[3075];
} notify_request_t;
extern "C" int sceKernelSendNotificationRequest(int, notify_request_t *, size_t, int);
static void notify(const char *msg) {
  notify_request_t req;
  memset(&req, 0, sizeof(req));
  snprintf(req.message, sizeof(req.message), "%s", msg);
  sceKernelSendNotificationRequest(0, &req, sizeof(req), 0);
}
#define LOG_DIR "/data/omni"
#else
static void notify(const char *msg) { fprintf(stderr, "[notify] %s\n", msg); }
#define LOG_DIR "/tmp"
#endif

/* Each test: name + JS expression that must evaluate to true. */
static const char *const TESTS[][2] = {
    {"arithmetic", "1 + 2 * 3 === 7 && 0.1 + 0.2 !== 0.3 && 2 ** 10 === 1024"},
    {"closures", "(() => { let c = 0; const inc = () => ++c; inc(); inc(); return c === 2; })()"},
    {"classes", "(() => { class A { #x = 1; get x() { return this.#x; } static s() { return 'S'; } }"
                " class B extends A { constructor() { super(); this.y = 2; } }"
                " const b = new B(); return b.x === 1 && b.y === 2 && B.s() === 'S'; })()"},
    {"destructuring+spread", "(() => { const {a, ...r} = {a: 1, b: 2, c: 3}; const [x, , z] = [1, 2, 3];"
                             " return a === 1 && Object.keys(r).join() === 'b,c' && x + z === 4"
                             " && Math.max(...[3, 9, 4]) === 9; })()"},
    {"generators", "(() => { function* g() { yield 1; yield 2; } return [...g()].join() === '1,2'; })()"},
    {"optional chaining", "(() => { const o = {a: {b: null}}; return o?.a?.b?.c === undefined && (o.x ?? 5) === 5; })()"},
    {"bigint", "(2n ** 64n).toString() === '18446744073709551616'"},
    {"Map/Set/WeakMap", "(() => { const m = new Map([[1, 'a']]); const s = new Set([1, 1, 2]);"
                        " const w = new WeakMap(); const k = {}; w.set(k, 3);"
                        " return m.get(1) === 'a' && s.size === 2 && w.get(k) === 3; })()"},
    {"JSON", "(() => { const o = {n: 1, s: 'x\\u00e9', a: [true, null], d: {e: 2.5}};"
             " return JSON.stringify(JSON.parse(JSON.stringify(o))) === JSON.stringify(o); })()"},
    {"RegExp", "(() => { const m = /(?<y>\\d{4})-(?<m>\\d{2})/u.exec('on 2026-10-17');"
               " return m.groups.y === '2026' && 'aXbXc'.replaceAll('X', '-') === 'a-b-c'"
               " && /\\p{L}+/u.test('\\u00fc\\u00f1\\u00ee'); })()"},
    {"typed arrays", "(() => { const b = new ArrayBuffer(16); const f = new Float64Array(b);"
                     " const u = new Uint8Array(b); f[0] = 1.5; return u[7] === 63 && u[6] === 248"
                     " && new DataView(b).getFloat64(0, true) === 1.5; })()"},
    {"Date", "(() => { const d = new Date(Date.UTC(2026, 9, 17, 12)); return d.toISOString()"
             " === '2026-10-17T12:00:00.000Z' && !isNaN(Date.now()); })()"},
    {"Promise jobs queued", "(() => { let r = 0; Promise.resolve(41).then(v => { r = v + 1; });"
                            " return typeof Promise.allSettled === 'function'; })()"},
    {"Proxy/Reflect", "(() => { const p = new Proxy({}, {get: (t, k) => k + '!'});"
                      " return p.hi === 'hi!' && Reflect.ownKeys({a: 1}).length === 1; })()"},
    {"Unicode case (ICU)", "'stra\\u00dfe'.toUpperCase() === 'STRASSE' && '\\u0130'.toLowerCase().length === 2"},
    {"normalize (ICU)", "'\\u0065\\u0301'.normalize('NFC') === '\\u00e9'"},
    {"Intl.NumberFormat", "new Intl.NumberFormat('en-US').format(1234567.891) === '1,234,567.891'"
                          " && new Intl.NumberFormat('de-DE').format(1234.5) === '1.234,5'"},
    {"Intl.DateTimeFormat", "new Intl.DateTimeFormat('en-US', {timeZone: 'UTC', year: 'numeric',"
                            " month: 'long'}).format(new Date(Date.UTC(2026, 9, 17))) === 'October 2026'"},
    {"Intl.Collator", "['z', '\\u00e4', 'a'].sort(new Intl.Collator('de').compare).join('') === 'a\\u00e4z'"},
    {"Intl.Segmenter", "typeof Intl.Segmenter !== 'function' ||"
                       " [...new Intl.Segmenter('en', {granularity: 'word'}).segment('hi there')]"
                       ".filter(s => s.isWordLike).length === 2"},
    {"localeCompare", "'a'.localeCompare('b') < 0 && 'resume'.localeCompare('r\\u00e9sum\\u00e9', 'en',"
                      " {sensitivity: 'base'}) === 0"},
    {"Array methods", "[3, 1, 2].toSorted().join() === '1,2,3' && [1, [2, [3]]].flat(2).length === 3"
                      " && [1, 2, 3].at(-1) === 3 && Array.from({length: 3}, (_, i) => i).join() === '0,1,2'"},
    {"Object.groupBy", "typeof Object.groupBy !== 'function' ||"
                       " Object.groupBy([1, 2, 3], x => x % 2 ? 'odd' : 'even').odd.length === 2"},
    {"eval/Function", "eval('1+1') === 2 && new Function('a', 'b', 'return a*b')(6, 7) === 42"},
    {"exceptions", "(() => { try { null.x; } catch (e) { return e instanceof TypeError; } })()"},
};

/* CPU benchmark: returns elapsed ms as a number */
static const char BENCH[] =
    "(() => {"
    "  const t0 = Date.now();"
    "  function fib(n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }"
    "  let acc = fib(27);"
    "  const a = []; for (let i = 0; i < 200000; i++) a.push((i * 7919) % 10007);"
    "  a.sort((x, y) => x - y); acc += a[1000];"
    "  let s = ''; for (let i = 0; i < 20000; i++) s += String.fromCharCode(97 + i % 26);"
    "  acc += s.split('a').length;"
    "  const o = {}; for (let i = 0; i < 50000; i++) o['k' + i] = i; acc += Object.keys(o).length;"
    "  for (let i = 0; i < 2000; i++) JSON.parse(JSON.stringify({i, v: [1, 2, 3], s: 'x'}));"
    "  return [Date.now() - t0, acc];"
    "})()";

static FILE *logf;

static void out(const char *fmt, ...) {
  char line[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(line, sizeof(line), fmt, ap);
  va_end(ap);
  fputs(line, stdout);
  fflush(stdout);
  if (logf) {
    fputs(line, logf);
    fflush(logf);
  }
}

static char *to_cstr(JSContextRef ctx, JSValueRef v) {
  JSStringRef s = JSValueToStringCopy(ctx, v, NULL);
  if (!s) return strdup("<unprintable>");
  size_t cap = JSStringGetMaximumUTF8CStringSize(s);
  char *buf = (char *)malloc(cap);
  JSStringGetUTF8CString(s, buf, cap);
  JSStringRelease(s);
  return buf;
}

static JSValueRef eval(JSContextRef ctx, const char *src, char **err) {
  JSStringRef script = JSStringCreateWithUTF8CString(src);
  JSValueRef exc = NULL;
  JSValueRef r = JSEvaluateScript(ctx, script, NULL, NULL, 1, &exc);
  JSStringRelease(script);
  *err = exc ? to_cstr(ctx, exc) : NULL;
  return r;
}

int main(void) {
  mkdir(LOG_DIR, 0777);
  logf = fopen(LOG_DIR "/jsc-selftest.txt", "w");
  out("Omni Engine - JavaScriptCore self test\n");
  notify("Omni Engine: JavaScriptCore self test starting");

  JSGlobalContextRef ctx = JSGlobalContextCreate(NULL);
  if (!ctx) {
    out("FATAL: could not create a JS context\n");
    notify("Omni Engine: JSC context creation FAILED");
    return 1;
  }

  int pass = 0, fail = 0;
  const int n = (int)(sizeof(TESTS) / sizeof(TESTS[0]));
  for (int i = 0; i < n; i++) {
    char *err = NULL;
    JSValueRef r = eval(ctx, TESTS[i][1], &err);
    bool ok = !err && r && JSValueIsBoolean(ctx, r) && JSValueToBoolean(ctx, r);
    if (ok) {
      pass++;
      out("  PASS  %s\n", TESTS[i][0]);
    } else {
      fail++;
      out("  FAIL  %s%s%s\n", TESTS[i][0], err ? "  -> " : "", err ? err : "");
    }
    free(err);
  }

  char *err = NULL;
  JSValueRef b = eval(ctx, BENCH, &err);
  char bench[128] = "benchmark failed";
  if (!err && b) {
    char *s = to_cstr(ctx, b);
    snprintf(bench, sizeof(bench), "bench [ms,checksum] = %s", s);
    free(s);
  } else if (err) {
    snprintf(bench, sizeof(bench), "benchmark threw: %.90s", err);
  }
  free(err);
  out("  %s\n", bench);

  char *ver = NULL;
  JSValueRef v = eval(ctx, "typeof Intl === 'object' ? Intl.DateTimeFormat().resolvedOptions().locale : 'no-intl'", &ver);
  char *loc = (!ver && v) ? to_cstr(ctx, v) : strdup("?");
  free(ver);

  char summary[256];
  snprintf(summary, sizeof(summary), "Omni Engine JSC: %d/%d passed, %s, locale %s", pass, n,
           bench, loc);
  free(loc);
  out("%s\n", summary);
  notify(summary);

  JSGlobalContextRelease(ctx);
  if (logf) fclose(logf);
  return fail ? 2 : 0;
}
