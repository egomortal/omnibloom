/* host stand-in for the SDK header: only what cxa.c needs */
#include <stdbool.h>
int ps5___cxa_thread_atexit_impl(void (*destructor)(void *), void *object, void *dso);
