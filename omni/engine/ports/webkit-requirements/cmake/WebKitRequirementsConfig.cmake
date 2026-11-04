# Omni Engine: CMake config for the open WebKitRequirements package.
# Provides the targets WebKit's PlayStation port links against.
# SPDX-License-Identifier: BSD-2-Clause
get_filename_component(_omni_req_prefix "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(_omni_req_lib "${_omni_req_prefix}/lib/libWebKitRequirements.a")
set(_omni_req_inc "${_omni_req_prefix}/include")

foreach (_c ProcessLauncher WebKitResources)
    if (NOT TARGET WebKitRequirements::${_c})
        add_library(WebKitRequirements::${_c} STATIC IMPORTED GLOBAL)
        set_target_properties(WebKitRequirements::${_c} PROPERTIES
            IMPORTED_LOCATION "${_omni_req_lib}"
            INTERFACE_INCLUDE_DIRECTORIES "${_omni_req_inc}")
    endif ()
    set(WebKitRequirements_${_c}_FOUND TRUE)
endforeach ()

# libwpe (built from upstream source, static, installed in the same prefix)
if (NOT TARGET WPE::libwpe)
    add_library(WPE::libwpe STATIC IMPORTED GLOBAL)
    set_target_properties(WPE::libwpe PROPERTIES
        IMPORTED_LOCATION "${_omni_req_prefix}/lib/libwpe.a"
        INTERFACE_INCLUDE_DIRECTORIES "${_omni_req_prefix}/include/wpe-1.0")
endif ()
if (NOT TARGET WebKitRequirements::libwpe)
    add_library(WebKitRequirements::libwpe INTERFACE IMPORTED GLOBAL)
    set_target_properties(WebKitRequirements::libwpe PROPERTIES INTERFACE_LINK_LIBRARIES WPE::libwpe)
endif ()
set(WebKitRequirements_libwpe_FOUND TRUE)
set(WPE_FOUND TRUE)
set(WPE_VERSION 1.16.3)

# Optional components (JPEG, LibPSL, ...) are not bundled: WebKit then finds
# them individually from the PacBrew sysroot.
foreach (_c JPEG LibPSL LibXml2 SQLite3 WebP ZLIB)
    set(WebKitRequirements_${_c}_FOUND FALSE)
endforeach ()
set(WebKitRequirements_FOUND TRUE)
