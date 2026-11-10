#!/usr/bin/env python3
"""SPIR-V -> C++ header (uint32 array). Usage: spv_to_header.py in.spv out.h ArrayName source-name"""
import struct, sys
src, out, name, comp = sys.argv[1:5]
data = open(src, 'rb').read(); assert len(data) % 4 == 0
words = struct.unpack('<%dI' % (len(data) // 4), data)
lines = ['// SPDX-License-Identifier: GPL-3.0-or-later',
         f'// Generated from {comp}: glslangValidator 15.1 -V --target-env vulkan1.1 (spirv-val clean). Do not edit.',
         '#pragma once', '#include <cstdint>', f'static const uint32_t {name}[] = {{']
for i in range(0, len(words), 8):
    lines.append('    ' + ', '.join('0x%08xu' % w for w in words[i:i + 8]) + ',')
lines.append('};'); open(out, 'w').write('\n'.join(lines) + '\n')
