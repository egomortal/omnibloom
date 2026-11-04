"""Reproduce JD004 then add private carry/errno-correct at-function adapters."""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());BASE=OUT/'packages/jd-004';TARGET=OUT/'packages/jd-005';TARGET.mkdir(exist_ok=True);FROZEN=TARGET/'source';FROZEN.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if (FROZEN/'relink_filesystem.py').exists() and not (FROZEN/'relink_filesystem.initial.py').exists():shutil.copyfile(FROZEN/'relink_filesystem.py',FROZEN/'relink_filesystem.initial.py')
for name in ('filesystem_compat.cpp','test_filesystem_compat.cpp','relink_filesystem.py','package_payload.py'):shutil.copyfile(OUT/name,FROZEN/name)
shutil.copyfile(BASE/'source/java_worker.cpp',FROZEN/'java_worker.cpp')
env=os.environ.copy();env['LLVM_CONFIG']='/usr/bin/llvm-config-21'
command=[json.loads(line) for line in (BASE/'link-command.json').read_text().splitlines()]
baseline=FROZEN/'baseline-relink.elf';check=list(command);check[check.index('-o')+1]=str(baseline)
subprocess.run(check,check=True,env=env)
assert sha(baseline)==sha(BASE/'java-worker.elf')=='399afe234b5a8e2ebf272374afe263deb21576755f8a4e4143de847372923c50','JD004 runtime input objects changed'
sdk=Path(C['sdk']);obj=TARGET/'filesystem-compat.o';compiler='/usr/lib/llvm-21/bin/clang++'
compile_command=[compiler,'-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',str(sdk),'-isystem',str(sdk/'target/include/c++/v1'),'-isystem',str(sdk/'target/include'),'-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-stack-protector','-fno-plt','-femulated-tls','-fno-exceptions','-fno-rtti','-c',str(FROZEN/'filesystem_compat.cpp'),'-o',str(obj)]
subprocess.run(compile_command,check=True)
elf=TARGET/'java-worker.elf';updated=[str(elf) if p==str(BASE/'java-worker.elf') else p for p in command]
updated += [str(obj),'--wrap=fstatat','--wrap=mkdirat','--wrap=openat']
subprocess.run(updated,check=True,env=env)
host=TARGET/'filesystem-host-test';host_command=[compiler,'-std=c++20','-O2','-Wall','-Wextra','-Werror','-DOMNI_FS_HOST_TEST',str(FROZEN/'filesystem_compat.cpp'),str(FROZEN/'test_filesystem_compat.cpp'),'-o',str(host)]
subprocess.run(host_command,check=True);proof=subprocess.run([str(host)],check=True,text=True,capture_output=True);host_result=json.loads(proof.stdout)
(FROZEN/'host-test.json').write_text(json.dumps(host_result,indent=2)+'\n')
disassembly=subprocess.run(['/usr/lib/llvm-21/bin/llvm-objdump','-dr','--no-show-raw-insn',str(obj)],capture_output=True,text=True,check=True).stdout
(FROZEN/'filesystem-compat.disassembly.txt').write_text(disassembly)
assert disassembly.count('syscall')==3 and len(re.findall(r'syscall\n[^\n]*setb',disassembly))==3,'Carry must be captured immediately after all three actual syscalls'
assert '__error' in disassembly,'Target errno getter relocation absent'
for symbol in ('__wrap_fstatat','__wrap_mkdirat','__wrap_openat'):
 native=subprocess.run(['/usr/lib/llvm-21/bin/llvm-objdump','-d','--no-show-raw-insn','--disassemble-symbols='+symbol,str(elf)],capture_output=True,text=True,check=True).stdout
 (FROZEN/(symbol+'.disassembly.txt')).write_text(native)
 assert 'syscall' in native and 'setb' in native and 'callq\t*' in native,'Final adapter lacks syscall/carry/errno import call; object relocation verifies exact __error symbol'
(FROZEN/'compile-command.json').write_text(json.dumps(compile_command,indent=2)+'\n');(FROZEN/'host-compile-command.json').write_text(json.dumps(host_command,indent=2)+'\n');(TARGET/'link-command.json').write_text('\n'.join(json.dumps(p) for p in updated)+'\n')
runtime_inputs=[{'path':p,'sha256':sha(Path(p)),'bytes':Path(p).stat().st_size} for p in command if Path(p).is_file() and Path(p).suffix in ('.o','.a','.ld')]
(FROZEN/'runtime-inputs.json').write_text(json.dumps(runtime_inputs,indent=2)+'\n')
image=json.loads((BASE/'export-receipt.json').read_text());result={'status':'BUILT_NOT_TARGET_TESTED','change':'Private link-wrap adapters fstatat493/mkdirat496/openat499: capture real syscall carry, publish actual kernel errno, return-1 only on carry; no shared SDK/source/image changes','source_sha256':sha(FROZEN/'filesystem_compat.cpp'),'native_entry_sha256':sha(FROZEN/'java_worker.cpp'),'baseline_relinked_byte_identical':True,'baseline_sha256':sha(baseline),'host_controlled_syscall_result_test':host_result,'target_disassembly_carry_errno_checked':True,'elf':{'path':str(elf),'bytes':elf.stat().st_size,'sha256':sha(elf)},'archive':image['archive'],'manifest':image['manifest'],'file_count':image['file_count'],'uncompressed_bytes':image['uncompressed_bytes'],'console_tested':False}
(TARGET/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
