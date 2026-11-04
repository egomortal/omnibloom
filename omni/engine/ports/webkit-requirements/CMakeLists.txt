# Omni Engine: open "WebKitRequirements" package for WebKit's PlayStation port.
# SPDX-License-Identifier: BSD-2-Clause
cmake_minimum_required(VERSION 3.20)
project(OmniWebKitRequirements CXX)
set(CMAKE_CXX_STANDARD 17)

add_library(WebKitRequirements STATIC src/process-launcher.cpp src/launcher-child.cpp src/support.cpp)
target_include_directories(WebKitRequirements PRIVATE include)

install(TARGETS WebKitRequirements ARCHIVE DESTINATION lib)
install(DIRECTORY include/ DESTINATION include)
install(FILES cmake/WebKitRequirementsConfig.cmake DESTINATION lib/cmake/WebKitRequirements)
