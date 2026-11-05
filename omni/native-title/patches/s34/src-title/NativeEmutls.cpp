//===---------- NativeEmutls.cpp - __emutls_get_address for the Omni title ---------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
// OMNI_EMUTLS_ROUNDS_V1 (omni-jit2, 2026-11-04): compiler-rt's emutls.c (PS5_PayloadSDK/libc/emutls.c, POSIX part)
// with ONE change: EMUTLS_SKIP_DESTRUCTOR_ROUNDS is 1 (upstream uses 1 only on Bionic, 0 elsewhere).
//
// Why: the title has no native TLS; every thread_local lives in memory emutls mallocs, and emutls frees it from its
// pthread key destructor. C++ thread_local DESTRUCTORS are run by libps5platform's cxa.c (ps5___cxa_thread_atexit_impl)
// from ANOTHER pthread key destructor. Keys' destructors run in key order, and emutls' key is created first (the
// first TLS access happens long before the first thread_local with a destructor), so on a thread's exit emutls freed
// the objects, then cxa.c ran ~vector() on freed memory: begin now held dlmalloc's free-list link, free() of it
// read a garbage chunk size and faulted in mspace_free called from run_destructors (the YouTube-soak title crash,
// SIGSEGV at 0x400025f560, 2026-11-03). Skipping one destructor round keeps the objects alive until cxa.c has run
// their destructors (POSIX: up to PTHREAD_DESTRUCTOR_ITERATIONS rounds; a value set again in a destructor gets
// another round). The libc.a copy is weak; this strong definition replaces it in the title link.
//===----------------------------------------------------------------------------------------===//
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifndef EMUTLS_SKIP_DESTRUCTOR_ROUNDS
#define EMUTLS_SKIP_DESTRUCTOR_ROUNDS 1
#endif

extern "C" {
__attribute__((used)) const char omni_emutls_marker[] = "OMNI_EMUTLS_ROUNDS_V1 skip=1";

typedef struct emutls_address_array {
    uintptr_t skip_destructor_rounds;
    uintptr_t size; // number of elements in the 'data' array
    void* data[1];  // really [size]
} emutls_address_array;
static const uintptr_t kHeaderBytes = 2 * sizeof(uintptr_t);

static void emutls_shutdown(emutls_address_array* array);
static pthread_mutex_t emutls_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_key_t emutls_pthread_key;
typedef unsigned int gcc_word __attribute__((mode(word)));

static inline void* emutls_memalign_alloc(size_t align, size_t size)
{
    const size_t extra = align - 1 + sizeof(void*);
    char* object = static_cast<char*>(malloc(extra + size));
    if (!object) abort();
    void* base = reinterpret_cast<void*>((reinterpret_cast<uintptr_t>(object + extra)) & ~uintptr_t(align - 1));
    static_cast<void**>(base)[-1] = object;
    return base;
}
static inline void emutls_memalign_free(void* base) { free(static_cast<void**>(base)[-1]); }
static inline void emutls_setspecific(emutls_address_array* value) { pthread_setspecific(emutls_pthread_key, value); }
static inline emutls_address_array* emutls_getspecific() { return static_cast<emutls_address_array*>(pthread_getspecific(emutls_pthread_key)); }
static void emutls_key_destructor(void* ptr)
{
    emutls_address_array* array = static_cast<emutls_address_array*>(ptr);
    if (array->skip_destructor_rounds > 0) {
        // Delay the deallocation one round: thread_local destructors (cxa.c's key) still use these objects.
        array->skip_destructor_rounds--;
        emutls_setspecific(array);
    } else {
        emutls_shutdown(array);
        free(ptr);
    }
}
static void emutls_init()
{
    if (pthread_key_create(&emutls_pthread_key, emutls_key_destructor) != 0) abort();
}
static inline void emutls_init_once()
{
    static pthread_once_t once = PTHREAD_ONCE_INIT;
    pthread_once(&once, emutls_init);
}
static size_t emutls_num_object = 0;
static void emutls_shutdown(emutls_address_array* array)
{
    if (!array) return;
    for (uintptr_t i = 0; i < array->size; ++i)
        if (array->data[i]) emutls_memalign_free(array->data[i]);
}
typedef struct __emutls_control {
    gcc_word size;  // size of the object in bytes
    gcc_word align; // alignment of the object in bytes
    union {
        uintptr_t index; // data[index-1] is the object address
        void* address;   // object address, when in single thread env
    } object;
    void* value; // null or non-zero initial value for the object
} __emutls_control;
static inline void* emutls_allocate_object(__emutls_control* control)
{
    size_t size = control->size, align = control->align;
    if (align < sizeof(void*)) align = sizeof(void*);
    if ((align & (align - 1)) != 0) abort();
    void* base = emutls_memalign_alloc(align, size);
    if (control->value) memcpy(base, control->value, size);
    else memset(base, 0, size);
    return base;
}
static inline uintptr_t emutls_get_index(__emutls_control* control)
{
    uintptr_t index = __atomic_load_n(&control->object.index, __ATOMIC_ACQUIRE);
    if (!index) {
        emutls_init_once();
        pthread_mutex_lock(&emutls_mutex);
        index = control->object.index;
        if (!index) {
            index = ++emutls_num_object;
            __atomic_store_n(&control->object.index, index, __ATOMIC_RELEASE);
        }
        pthread_mutex_unlock(&emutls_mutex);
    }
    return index;
}
static inline void emutls_check_array_set_size(emutls_address_array* array, uintptr_t size)
{
    if (!array) abort();
    array->size = size;
    emutls_setspecific(array);
}
static inline uintptr_t emutls_new_data_array_size(uintptr_t index)
{
    const uintptr_t header_words = kHeaderBytes / sizeof(void*);
    return ((index + header_words + 15) & ~uintptr_t(15)) - header_words;
}
static inline uintptr_t emutls_asize(uintptr_t n) { return n * sizeof(void*) + kHeaderBytes; }
static inline emutls_address_array* emutls_get_address_array(uintptr_t index)
{
    emutls_address_array* array = emutls_getspecific();
    if (!array) {
        const uintptr_t new_size = emutls_new_data_array_size(index);
        array = static_cast<emutls_address_array*>(malloc(emutls_asize(new_size)));
        if (array) {
            memset(array->data, 0, new_size * sizeof(void*));
            array->skip_destructor_rounds = EMUTLS_SKIP_DESTRUCTOR_ROUNDS;
        }
        emutls_check_array_set_size(array, new_size);
    } else if (index > array->size) {
        const uintptr_t orig_size = array->size, new_size = emutls_new_data_array_size(index);
        array = static_cast<emutls_address_array*>(realloc(array, emutls_asize(new_size)));
        if (array) memset(array->data + orig_size, 0, (new_size - orig_size) * sizeof(void*));
        emutls_check_array_set_size(array, new_size);
    }
    return array;
}
__attribute__((visibility("default"))) void* __emutls_get_address(__emutls_control* control)
{
    uintptr_t index = emutls_get_index(control);
    emutls_address_array* array = emutls_get_address_array(index--);
    if (!array->data[index]) array->data[index] = emutls_allocate_object(control);
    return array->data[index];
}
}
