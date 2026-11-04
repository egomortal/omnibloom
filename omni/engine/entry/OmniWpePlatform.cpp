// WPE services for WebKit's non-WPE-renderer PlayStation configuration.
// Rendering uses the PlayStation view/bitmap path. libwpe is still required
// for input types and its generic process-local clipboard. Its static loader
// requires this interface even when no WPE graphics backend is selected.
// SPDX-License-Identifier: GPL-3.0-or-later
#include <wpe/wpe.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void* loadOmniWpeObject(const char* name)
{
    // libwpe's pasteboard.c explicitly falls back to generic_pasteboard_interface
    // when this optional platform interface is absent. That is a working local
    // clipboard, not the no-op clipboard implementation.
    if (name && !strcmp(name, "_wpe_pasteboard_interface"))
        return nullptr;
    // A renderer request means the build selected an incompatible path. Fail
    // visibly instead of pretending to provide graphics objects.
    fprintf(stderr, "Omni: unexpected WPE backend request: %s\n", name ? name : "(null)");
    abort();
}

extern "C" {
struct wpe_loader_interface _wpe_loader_interface = {
    loadOmniWpeObject, nullptr, nullptr, nullptr, nullptr
};
}
