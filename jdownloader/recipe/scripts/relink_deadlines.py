"""Reproduce JD003 then change only its entry startup/destroy deadline budgets."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent
C=json.loads((OUT/'linux-build-paths.json').read_text())
BASE=OUT/'packages/jd-003';TARGET=OUT/'packages/jd-004';TARGET.mkdir();FROZEN=TARGET/'source';FROZEN.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('java_worker.cpp','relink_deadlines.py','package_payload.py'):shutil.copyfile(OUT/name,FROZEN/name)
command=[json.loads(line) for line in (BASE/'link-command.json').read_text().splitlines()]
baseline=FROZEN/'baseline-relink.elf';check=list(command);check[check.index('-o')+1]=str(baseline)
env=os.environ.copy();env['LLVM_CONFIG']='/usr/bin/llvm-config-21'
subprocess.run(check,check=True,env=env)
assert sha(baseline)==sha(BASE/'java-worker.elf')=='7e5d9cb2a8e201ddd0a8e464548919f231f36e5f51a06e5088aebade8bb4880e','JD003 runtime object inputs changed'
sdk=Path(C['sdk']);port=Path(C['port']);headers=Path(C['source'])/'build/ps5-bootstrap/support/modules_include/java.base';entry=TARGET/'java-worker.o'
compile_command=['/usr/lib/llvm-21/bin/clang++','-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',str(sdk),'-isystem',str(sdk/'target/include/c++/v1'),'-isystem',str(sdk/'target/include'),'-I',str(headers),'-I',str(headers/'freebsd'),'-I',str(port/'java25/probe'),'-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-stack-protector','-fno-plt','-femulated-tls','-fno-exceptions','-fno-rtti','-c',str(FROZEN/'java_worker.cpp'),'-o',str(entry)]
subprocess.run(compile_command,check=True)
elf=TARGET/'java-worker.elf';updated=[str(elf) if p==str(BASE/'java-worker.elf') else str(entry) if p==str(BASE/'java-worker.o') else p for p in command]
subprocess.run(updated,check=True,env=env)
runtime_inputs=[{'path':p,'sha256':sha(Path(p)),'bytes':Path(p).stat().st_size} for p in command if Path(p).is_file() and Path(p).suffix in ('.o','.a','.ld')]
(FROZEN/'compile-command.json').write_text(json.dumps(compile_command,indent=2)+'\n');(TARGET/'link-command.json').write_text('\n'.join(json.dumps(p) for p in updated)+'\n');(FROZEN/'runtime-inputs.json').write_text(json.dumps(runtime_inputs,indent=2)+'\n')
image=json.loads((BASE/'export-receipt.json').read_text());result={'status':'BUILT_NOT_TARGET_TESTED','change':'Only native entry startup_seconds 5..600 (default600), whole-worker=max_seconds+startup_seconds+60 destroy grace; watchdog mode fixed5s; no Java/image/provider/object changes','source_sha256':sha(FROZEN/'java_worker.cpp'),'baseline_relinked_byte_identical':True,'baseline_sha256':sha(baseline),'elf':{'path':str(elf),'bytes':elf.stat().st_size,'sha256':sha(elf)},'archive':image['archive'],'manifest':image['manifest'],'file_count':image['file_count'],'uncompressed_bytes':image['uncompressed_bytes'],'console_tested':False}
(TARGET/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
