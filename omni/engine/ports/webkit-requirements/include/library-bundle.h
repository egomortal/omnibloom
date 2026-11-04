// Omni Engine: injected-bundle loader for WebKit's PlayStation port
// (WebProcess/InjectedBundle/playstation/InjectedBundlePlayStation.cpp).
// SPDX-License-Identifier: BSD-2-Clause
#pragma once

class LibraryBundle {
public:
    // Returns nullptr if the bundle can't be loaded. Never freed (WebKit leaks it too).
    static LibraryBundle* create(const char* path);
    void* resolve(const char* symbol);

private:
    explicit LibraryBundle(void* handle) : m_handle(handle) { }
    void* m_handle;
};
