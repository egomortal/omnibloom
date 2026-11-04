# Omni Engine: open stand-in for the PlayStationModule.cmake that Sony's
# official SDK provides. The homebrew build links everything statically into
# one ELF, so "modules" (separately loaded .sprx/.prx) are not used.
# SPDX-License-Identifier: BSD-2-Clause

macro(playstation_module _name)
    # Sony: wraps a library as a loadable system module. Homebrew: nothing.
endmacro()

macro(playstation_setup_libc _target)
    # Sony: selects SCE libc variant. Homebrew: SDK libc is linked by default.
endmacro()

macro(playstation_setup_fp _target)
    # Sony: floating-point environment setup. Homebrew: defaults are fine.
endmacro()
