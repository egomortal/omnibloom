"""Fail closed before signing a native title: ELF64 LOAD geometry and size policy.

omni-native-s0 copy of nxe-ps5/bigapp/tools/check_native_layout.py (Ex-Box Q7c guard), plus:
- policy "omni" (Omni's UI title: WebKit + JSC + Skia + FFmpeg + RADV), limits set in build.py
  from the measured layout, rounded up; overlap checks are unchanged;
- --sections: every SHF_EXECINSTR section must lie inside the first (text) LOAD, in both address
  and file ranges (an orphan executable section after rodata restarted the PS5: Q7c).

Limits are review bounds, not hardware capabilities. Editor growth above the
working dashboard baseline is allowed only by the named, documented policy.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

# Rounded-up maxima from working PPSA99735, ordered by LOAD index.
BASELINE = [14<<20, 17<<20, 1<<20, 1<<20, 1<<20]
POLICIES = {
    "dashboard": (BASELINE, "Working PPSA99735 baseline, rounded to MiB."),
    "smoke": (BASELINE, "Smoke is bounded by the working PPSA99735 baseline."),
    "omni": ([256<<20, 160<<20, 64<<20, 64<<20, 16<<20],
        "omni-native-s0: Omni UI title (WebKit/JSC/Skia/FFmpeg/curl/ICU + static RADV). "
        "Review bound only, NOT console validation; measured sizes are in the build report."),
    "editor": ([66<<20, 26<<20, 2<<20, 25<<20, 3<<20],
        "12581 generated guest code plus runtime/RADV: ~65 MiB code, unwind/pack "
        "constants ~25 MiB, guest static tables/BSS ~24 MiB, relocation metadata "
        "~3 MiB. Q7c report; local layout allowance, NOT console validation."),
}

def check_sections(path):
    """Every executable section inside the text LOAD (address and file range)."""
    data = Path(path).read_bytes()
    phoff = struct.unpack_from("<Q", data, 32)[0]; shoff = struct.unpack_from("<Q", data, 40)[0]
    phent, phnum, shent, shnum, shstrndx = struct.unpack_from("<HHHHH", data, 54)
    text = None
    for i in range(phnum):
        kind, flags, off, va, pa, filesz, memsz, align = struct.unpack_from("<II6Q", data, phoff+i*phent)
        if kind == 1 and flags & 1:
            if text is not None: raise ValueError("more than one executable LOAD")
            text = (off, va, filesz, memsz)
    if text is None: raise ValueError("no executable LOAD")
    if not shnum: return []
    secs = [struct.unpack_from("<IIQQQQIIQQ", data, shoff+i*shent) for i in range(shnum)]
    strtab = secs[shstrndx]; names = data[strtab[4]:strtab[4]+strtab[5]]
    found = []
    for name_off, kind, flags, addr, off, size, *_ in secs:
        if not flags & 0x4 or not size: continue
        name = names[name_off:names.index(b"\0", name_off)].decode()
        found.append(name)
        if not (text[1] <= addr and addr+size <= text[1]+text[3]):
            raise ValueError(f"executable section {name} at 0x{addr:x}+0x{size:x} outside the text LOAD")
        if kind != 8 and not (text[0] <= off and off+size <= text[0]+text[2]):
            raise ValueError(f"executable section {name} file range outside the text LOAD")
    return found

def inspect(path, policy):
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected little-endian ELF64")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    entsize, count = struct.unpack_from("<HH", data, 54)
    if entsize != 56 or not count or phoff + count*entsize > len(data):
        raise ValueError("Invalid program-header table")
    loads = []
    for i in range(count):
        kind, flags, off, va, pa, filesz, memsz, align = struct.unpack_from("<II6Q", data, phoff+i*entsize)
        if kind != 1:
            continue
        if filesz > memsz or off+filesz > len(data) or va+memsz > 1<<64:
            raise ValueError(f"LOAD {i}: invalid bounds")
        if align > 1 and (align & (align-1) or off % align != va % align):
            raise ValueError(f"LOAD {i}: invalid alignment")
        loads.append(dict(index=i, flags=flags, offset=off, address=va, filesz=filesz, memsz=memsz, alignment=align))
    limits, reason = POLICIES[policy] if policy else ([1 << 64] * len(loads), "geometry only (--policy none)")
    if len(loads) != len(limits):
        raise ValueError(f"Expected {len(limits)} LOADs; got {len(loads)}; review layout policy")
    for i, a in enumerate(loads):
        for b in loads[i+1:]:
            for start, size in (("address", "memsz"), ("offset", "filesz")):
                if a[size] and b[size] and max(a[start], b[start]) < min(a[start]+a[size], b[start]+b[size]):
                    raise ValueError(f"LOAD {a['index']} overlaps LOAD {b['index']} in {start}")
        if max(a['filesz'], a['memsz']) > limits[i]:
            raise ValueError(f"LOAD {a['index']} exceeds {policy} size limit {limits[i]}; recorded review required")
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), policy=policy,
                size_reason=reason, limits=limits, loads=loads, passed=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--policy", required=True, choices=[*POLICIES, "none"])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sections", action="store_true", help="also require every executable section inside the text LOAD")
    args = parser.parse_args()
    try:
        report = inspect(args.elf, None if args.policy == "none" else args.policy)
        if args.sections:
            report["executable_sections"] = check_sections(args.elf)
    except (ValueError, OSError, struct.error) as error:
        parser.exit(1, f"Native layout rejected: {error}\n")
    output = json.dumps(report, indent=2)+"\n"
    if args.report:
        args.report.write_text(output)
    print(output, end="")
