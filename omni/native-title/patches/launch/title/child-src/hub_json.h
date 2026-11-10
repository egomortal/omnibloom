/* hub_json.h: small strict JSON parser and writer for the Hub (HUB_API_V1).
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Strict RFC 8259 parser into an arena-backed tree:
 *   - nesting at most HJ_MAX_DEPTH, at most HJ_MAX_NODES values, strings at most HJ_MAX_STR bytes;
 *   - valid UTF-8 only, no raw control characters, no \u0000, no lone surrogates;
 *   - duplicate object keys are rejected, and so is anything after the value.
 * The writer escapes '<', '>', '&' and control characters, so its output is safe to put in a page.
 * Everything is static, so including this header is enough (one translation unit, no link step).
 */
#ifndef HUB_JSON_H
#define HUB_JSON_H
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HJ_MAX_DEPTH 16
#define HJ_MAX_NODES 4096
#define HJ_MAX_STR 4096
#define HJ_ARENA_CHUNK (16u * 1024u)
#define HJ_ARENA_MAX (1u << 20)

typedef enum { HJ_NULL, HJ_FALSE, HJ_TRUE, HJ_NUM, HJ_STR, HJ_ARR, HJ_OBJ } hj_type;

typedef struct hj {
    hj_type t;
    struct hj* next;   /* next sibling (array element or object member) */
    char* key;         /* member name when the parent is an object */
    double num;
    char* str;         /* HJ_STR: NUL-terminated (no embedded NUL is accepted) */
    size_t len;
    struct hj* child;  /* HJ_ARR / HJ_OBJ: first element or member */
} hj;

typedef struct hj_chunk { struct hj_chunk* next; size_t used, cap; } hj_chunk;
typedef struct { hj_chunk* head; size_t total; int nodes; size_t max; } hj_arena;   /* max 0 = HJ_ARENA_MAX */

static void hj_arena_free(hj_arena* a)
{
    hj_chunk* c = a->head;
    while (c) { hj_chunk* n = c->next; free(c); c = n; }
    a->head = NULL; a->total = 0; a->nodes = 0; a->max = 0;
}

static void* hj_alloc(hj_arena* a, size_t n)
{
    n = (n + 15u) & ~(size_t)15u;
    if (!a->head || a->head->cap - a->head->used < n) {
        size_t cap = n > HJ_ARENA_CHUNK ? n : HJ_ARENA_CHUNK;
        if (a->total + cap > (a->max ? a->max : HJ_ARENA_MAX)) return NULL;
        hj_chunk* c = (hj_chunk*)malloc(sizeof(hj_chunk) + cap + 16);
        if (!c) return NULL;
        c->next = a->head; c->used = 0; c->cap = cap;
        a->head = c; a->total += cap;
    }
    unsigned char* base = (unsigned char*)(a->head + 1);
    base += (16 - ((size_t)base & 15)) & 15;
    void* p = base + a->head->used;
    a->head->used += n;
    memset(p, 0, n);
    return p;
}

typedef struct { const char* p; const char* end; hj_arena* a; int depth; const char* err; int max_nodes; } hj_parser;

static void hj_ws(hj_parser* ps)
{
    while (ps->p < ps->end && (*ps->p == ' ' || *ps->p == '\t' || *ps->p == '\n' || *ps->p == '\r')) ps->p++;
}

static hj* hj_new(hj_parser* ps, hj_type t)
{
    if (++ps->a->nodes > ps->max_nodes) { ps->err = "too many values"; return NULL; }
    hj* v = (hj*)hj_alloc(ps->a, sizeof(hj));
    if (!v) { ps->err = "out of memory"; return NULL; }
    v->t = t;
    return v;
}

static int hj_hex4(const char* s, unsigned* out)
{
    unsigned v = 0;
    for (int i = 0; i < 4; i++) {
        char c = s[i];
        int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
        if (d < 0) return -1;
        v = v * 16 + (unsigned)d;
    }
    *out = v;
    return 0;
}

/* Length of one valid UTF-8 sequence at s (n bytes available), or 0 if invalid. */
static size_t hj_utf8_len(const unsigned char* s, size_t n)
{
    unsigned c = s[0];
    if (c < 0x80) return 1;
    if (c >= 0xC2 && c <= 0xDF) return n >= 2 && (s[1] & 0xC0) == 0x80 ? 2 : 0;
    if (c >= 0xE0 && c <= 0xEF) {
        if (n < 3 || (s[1] & 0xC0) != 0x80 || (s[2] & 0xC0) != 0x80) return 0;
        if (c == 0xE0 && s[1] < 0xA0) return 0;   /* overlong */
        if (c == 0xED && s[1] >= 0xA0) return 0;  /* UTF-16 surrogate */
        return 3;
    }
    if (c >= 0xF0 && c <= 0xF4) {
        if (n < 4 || (s[1] & 0xC0) != 0x80 || (s[2] & 0xC0) != 0x80 || (s[3] & 0xC0) != 0x80) return 0;
        if (c == 0xF0 && s[1] < 0x90) return 0;   /* overlong */
        if (c == 0xF4 && s[1] >= 0x90) return 0;  /* above U+10FFFF */
        return 4;
    }
    return 0;
}

static size_t hj_put_utf8(char* o, unsigned cp)
{
    if (cp < 0x80) { o[0] = (char)cp; return 1; }
    if (cp < 0x800) { o[0] = (char)(0xC0 | (cp >> 6)); o[1] = (char)(0x80 | (cp & 63)); return 2; }
    if (cp < 0x10000) { o[0] = (char)(0xE0 | (cp >> 12)); o[1] = (char)(0x80 | ((cp >> 6) & 63)); o[2] = (char)(0x80 | (cp & 63)); return 3; }
    o[0] = (char)(0xF0 | (cp >> 18)); o[1] = (char)(0x80 | ((cp >> 12) & 63)); o[2] = (char)(0x80 | ((cp >> 6) & 63)); o[3] = (char)(0x80 | (cp & 63));
    return 4;
}

/* Parses a string starting at the opening quote; returns an arena copy, sets *len. */
static char* hj_string(hj_parser* ps, size_t* len)
{
    ps->p++; /* opening quote */
    const char* start = ps->p;
    size_t raw = 0;
    while (ps->p < ps->end && *ps->p != '"') {
        if (*ps->p == '\\') { ps->p++; if (ps->p >= ps->end) break; }
        ps->p++; raw++;
        if (raw > HJ_MAX_STR * 2) { ps->err = "string too long"; return NULL; }
    }
    if (ps->p >= ps->end) { ps->err = "unterminated string"; return NULL; }
    const char* stop = ps->p;
    ps->p++; /* closing quote */
    char* out = (char*)hj_alloc(ps->a, (size_t)(stop - start) + 1);
    if (!out) { ps->err = "out of memory"; return NULL; }
    size_t o = 0;
    for (const char* s = start; s < stop;) {
        unsigned char c = (unsigned char)*s;
        if (c < 0x20) { ps->err = "control character in string"; return NULL; }
        if (c == '\\') {
            s++;
            char e = *s++;
            switch (e) {
            case '"': out[o++] = '"'; break;
            case '\\': out[o++] = '\\'; break;
            case '/': out[o++] = '/'; break;
            case 'b': out[o++] = '\b'; break;
            case 'f': out[o++] = '\f'; break;
            case 'n': out[o++] = '\n'; break;
            case 'r': out[o++] = '\r'; break;
            case 't': out[o++] = '\t'; break;
            case 'u': {
                unsigned cp;
                if (stop - s < 4 || hj_hex4(s, &cp)) { ps->err = "bad \\u escape"; return NULL; }
                s += 4;
                if (cp >= 0xD800 && cp <= 0xDBFF) {
                    unsigned lo;
                    if (stop - s < 6 || s[0] != '\\' || s[1] != 'u' || hj_hex4(s + 2, &lo) || lo < 0xDC00 || lo > 0xDFFF) {
                        ps->err = "lone surrogate"; return NULL;
                    }
                    s += 6;
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                } else if (cp >= 0xDC00 && cp <= 0xDFFF) { ps->err = "lone surrogate"; return NULL; }
                if (cp == 0) { ps->err = "\\u0000 not allowed"; return NULL; }
                o += hj_put_utf8(out + o, cp);
                break;
            }
            default: ps->err = "bad escape"; return NULL;
            }
        } else {
            size_t n = hj_utf8_len((const unsigned char*)s, (size_t)(stop - s));
            if (!n) { ps->err = "invalid UTF-8"; return NULL; }
            memcpy(out + o, s, n); o += n; s += n;
        }
        if (o > HJ_MAX_STR) { ps->err = "string too long"; return NULL; }
    }
    out[o] = 0;
    *len = o;
    return out;
}

static hj* hj_value(hj_parser* ps);

static hj* hj_number(hj_parser* ps)
{
    const char* s = ps->p;
    if (ps->p < ps->end && *ps->p == '-') ps->p++;
    if (ps->p >= ps->end) { ps->err = "bad number"; return NULL; }
    if (*ps->p == '0') ps->p++;
    else if (*ps->p >= '1' && *ps->p <= '9') { while (ps->p < ps->end && *ps->p >= '0' && *ps->p <= '9') ps->p++; }
    else { ps->err = "bad number"; return NULL; }
    if (ps->p < ps->end && *ps->p == '.') {
        ps->p++;
        if (ps->p >= ps->end || *ps->p < '0' || *ps->p > '9') { ps->err = "bad number"; return NULL; }
        while (ps->p < ps->end && *ps->p >= '0' && *ps->p <= '9') ps->p++;
    }
    if (ps->p < ps->end && (*ps->p == 'e' || *ps->p == 'E')) {
        ps->p++;
        if (ps->p < ps->end && (*ps->p == '+' || *ps->p == '-')) ps->p++;
        if (ps->p >= ps->end || *ps->p < '0' || *ps->p > '9') { ps->err = "bad number"; return NULL; }
        while (ps->p < ps->end && *ps->p >= '0' && *ps->p <= '9') ps->p++;
    }
    size_t n = (size_t)(ps->p - s);
    if (n > 64) { ps->err = "number too long"; return NULL; }
    char tmp[72];
    memcpy(tmp, s, n); tmp[n] = 0;
    hj* v = hj_new(ps, HJ_NUM);
    if (!v) return NULL;
    v->num = strtod(tmp, NULL);
    if (v->num != v->num || v->num > 1.7e308 || v->num < -1.7e308) { ps->err = "number out of range"; return NULL; }
    return v;
}

static int hj_lit(hj_parser* ps, const char* w)
{
    size_t n = strlen(w);
    if ((size_t)(ps->end - ps->p) < n || memcmp(ps->p, w, n)) return -1;
    ps->p += n;
    return 0;
}

static hj* hj_value(hj_parser* ps)
{
    hj_ws(ps);
    if (ps->p >= ps->end) { ps->err = "unexpected end"; return NULL; }
    char c = *ps->p;
    if (c == '{' || c == '[') {
        if (++ps->depth > HJ_MAX_DEPTH) { ps->err = "nested too deeply"; return NULL; }
        int obj = c == '{';
        hj* v = hj_new(ps, obj ? HJ_OBJ : HJ_ARR);
        if (!v) return NULL;
        ps->p++;
        hj_ws(ps);
        hj** tail = &v->child;
        if (ps->p < ps->end && *ps->p == (obj ? '}' : ']')) { ps->p++; ps->depth--; return v; }
        for (;;) {
            char* key = NULL;
            if (obj) {
                hj_ws(ps);
                if (ps->p >= ps->end || *ps->p != '"') { ps->err = "expected member name"; return NULL; }
                size_t kl;
                key = hj_string(ps, &kl);
                if (!key) return NULL;
                for (hj* m = v->child; m; m = m->next)
                    if (!strcmp(m->key, key)) { ps->err = "duplicate key"; return NULL; }
                hj_ws(ps);
                if (ps->p >= ps->end || *ps->p != ':') { ps->err = "expected ':'"; return NULL; }
                ps->p++;
            }
            hj* e = hj_value(ps);
            if (!e) return NULL;
            e->key = key;
            *tail = e; tail = &e->next;
            hj_ws(ps);
            if (ps->p >= ps->end) { ps->err = "unexpected end"; return NULL; }
            if (*ps->p == ',') { ps->p++; continue; }
            if (*ps->p == (obj ? '}' : ']')) { ps->p++; break; }
            ps->err = obj ? "expected ',' or '}'" : "expected ',' or ']'";
            return NULL;
        }
        ps->depth--;
        return v;
    }
    if (c == '"') {
        hj* v = hj_new(ps, HJ_STR);
        if (!v) return NULL;
        v->str = hj_string(ps, &v->len);
        return v->str ? v : NULL;
    }
    if (c == '-' || (c >= '0' && c <= '9')) return hj_number(ps);
    if (!hj_lit(ps, "true")) return hj_new(ps, HJ_TRUE);
    if (!hj_lit(ps, "false")) return hj_new(ps, HJ_FALSE);
    if (!hj_lit(ps, "null")) return hj_new(ps, HJ_NULL);
    ps->err = "unexpected character";
    return NULL;
}

/* Parses buf[0..n) into arena a with at most max_nodes values. Returns the root, or NULL with *err set. */
static hj* hj_parse_lim(const char* buf, size_t n, hj_arena* a, const char** err, int max_nodes)
{
    hj_parser ps = { buf, buf + n, a, 0, NULL, max_nodes };
    hj* v = hj_value(&ps);
    if (v) {
        hj_ws(&ps);
        if (ps.p != ps.end) { v = NULL; ps.err = "trailing characters"; }
    }
    if (!v && err) *err = ps.err ? ps.err : "parse error";
    return v;
}
static hj* hj_parse(const char* buf, size_t n, hj_arena* a, const char** err) { return hj_parse_lim(buf, n, a, err, HJ_MAX_NODES); }

static hj* hj_get(const hj* obj, const char* key)
{
    if (!obj || obj->t != HJ_OBJ) return NULL;
    for (hj* m = obj->child; m; m = m->next) if (!strcmp(m->key, key)) return m;
    return NULL;
}
static const char* hj_getstr(const hj* obj, const char* key)
{
    hj* v = hj_get(obj, key);
    return v && v->t == HJ_STR ? v->str : NULL;
}
/* Integer member in [lo, hi], or -1 when missing, not a number, fractional or out of range. */
static long hj_getint(const hj* obj, const char* key, long lo, long hi)
{
    hj* v = hj_get(obj, key);
    if (!v || v->t != HJ_NUM) return -1;
    if (v->num != (double)(long)v->num || v->num < (double)lo || v->num > (double)hi) return -1;
    return (long)v->num;
}

/* ------------------------------------------------------------- growable output buffer */
typedef struct { char* p; size_t n, cap, max; int overflow; } hsb;

static void hsb_init(hsb* b, size_t max) { b->p = NULL; b->n = 0; b->cap = 0; b->max = max; b->overflow = 0; }
static void hsb_free(hsb* b) { free(b->p); b->p = NULL; b->n = b->cap = 0; }
static int hsb_grow(hsb* b, size_t extra)
{
    if (b->overflow) return -1;
    if (b->n + extra + 1 > b->max) { b->overflow = 1; return -1; }
    if (b->n + extra + 1 <= b->cap) return 0;
    size_t cap = b->cap ? b->cap : 1024;
    while (cap < b->n + extra + 1) cap *= 2;
    if (cap > b->max + 1) cap = b->max + 1;
    char* p = (char*)realloc(b->p, cap);
    if (!p) { b->overflow = 1; return -1; }
    b->p = p; b->cap = cap;
    return 0;
}
static void hsb_put(hsb* b, const char* s, size_t n)
{
    if (hsb_grow(b, n)) return;
    memcpy(b->p + b->n, s, n); b->n += n; b->p[b->n] = 0;
}
static void hsb_puts(hsb* b, const char* s) { hsb_put(b, s, strlen(s)); }
static void hsb_printf(hsb* b, const char* fmt, ...)
{
    char tmp[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof tmp) n = (int)sizeof tmp - 1;
    hsb_put(b, tmp, (size_t)n);
}
static void hsb_jstr(hsb* b, const char* s)
{
    static const char hex[] = "0123456789abcdef";
    hsb_put(b, "\"", 1);
    for (const unsigned char* c = (const unsigned char*)s; *c; c++) {
        if (*c == '"') hsb_put(b, "\\\"", 2);
        else if (*c == '\\') hsb_put(b, "\\\\", 2);
        else if (*c < 0x20 || *c == '<' || *c == '>' || *c == '&' || *c == 0x7f) {
            char e[6] = { '\\', 'u', '0', '0', hex[*c >> 4], hex[*c & 15] };
            hsb_put(b, e, 6);
        } else hsb_put(b, (const char*)c, 1);
    }
    hsb_put(b, "\"", 1);
}
static void hj_emit(hsb* b, const hj* v)
{
    switch (v->t) {
    case HJ_NULL: hsb_puts(b, "null"); break;
    case HJ_FALSE: hsb_puts(b, "false"); break;
    case HJ_TRUE: hsb_puts(b, "true"); break;
    case HJ_NUM:
        if (v->num == (double)(long long)v->num && v->num < 9e15 && v->num > -9e15) hsb_printf(b, "%lld", (long long)v->num);
        else hsb_printf(b, "%.17g", v->num);
        break;
    case HJ_STR: hsb_jstr(b, v->str); break;
    case HJ_ARR:
    case HJ_OBJ: {
        int obj = v->t == HJ_OBJ;
        hsb_put(b, obj ? "{" : "[", 1);
        for (const hj* e = v->child; e; e = e->next) {
            if (e != v->child) hsb_put(b, ",", 1);
            if (obj) { hsb_jstr(b, e->key); hsb_put(b, ":", 1); }
            hj_emit(b, e);
        }
        hsb_put(b, obj ? "}" : "]", 1);
        break;
    }
    }
}
#endif
