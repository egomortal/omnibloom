"""Expand Clang's response-file arguments before deciding shared/PIE mode."""
import hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());p=Path(C['sdk'])/'bin/prospero-lld';old=p.read_text()
new='''#!/usr/bin/env python3
import os,shlex,subprocess,sys
from pathlib import Path
sdk=Path(__file__).resolve().parent.parent
args=sys.argv[1:]
for depth in range(5):
 expanded=[];changed=False
 for arg in args:
  if arg.startswith('@'):
   source=Path(arg[1:]);assert source.stat().st_size<16*1024*1024
   expanded.extend(shlex.split(source.read_text()));changed=True
  else:expanded.append(arg)
 args=expanded
 if not changed:break
else:raise SystemExit('Response file recursion exceeded')
llvm=Path(subprocess.check_output([str(sdk/'bin/prospero-llvm-config'),'--bindir'],text=True).strip())
mode=[] if any(a in ('--shared','-shared','-r','--static') for a in args) else ['-pie']
layout=[] if any(a in ('--script','-T') for a in args) else ['-T'+str(sdk/'ldscripts/elf_x86_64.x')]
command=[str(llvm/'ld.lld'),'-m','elf_x86_64',*mode,*layout,'--eh-frame-hdr','-z','max-page-size=0x4000','-mllvm','-emulated-tls',*args,'--hash-style=gnu']
os.execv(command[0],command)
'''
p.write_text(new);p.chmod(0o755)
(OUT/'private-sdk-response-wrapper.before').write_text(old)
(OUT/'private-sdk-response-wrapper.py').write_text(new)
(OUT/'private-sdk-response-wrapper.json').write_text(json.dumps({'before':hashlib.sha256(old.encode()).hexdigest(),'after':hashlib.sha256(new.encode()).hexdigest(),'reason':'LLVM21 uses response file for large HotSpot link; shell SDK failed to see --shared inside it','private_sdk_only':True},indent=2)+'\n')
