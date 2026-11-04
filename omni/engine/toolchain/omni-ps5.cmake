# Omni Engine toolchain: ps5-payload-sdk + wrappers that fix -E/-S handling.
# SPDX-License-Identifier: BSD-2-Clause
if (DEFINED ENV{PS5_PAYLOAD_SDK})
    set(_omni_sdk "$ENV{PS5_PAYLOAD_SDK}")
else ()
    set(_omni_sdk "/opt/ps5-payload-sdk")
endif ()
include("${_omni_sdk}/toolchain/prospero.cmake")
set(CMAKE_C_COMPILER "${CMAKE_CURRENT_LIST_DIR}/omni-clang" CACHE PATH "" FORCE)
set(CMAKE_CXX_COMPILER "${CMAKE_CURRENT_LIST_DIR}/omni-clang++" CACHE PATH "" FORCE)
# WebKit ships Find modules that define the target names it links against;
# the SDK prefers package config files (e.g. harfbuzz::harfbuzz), which breaks that.
set(CMAKE_FIND_PACKAGE_PREFER_CONFIG FALSE)
