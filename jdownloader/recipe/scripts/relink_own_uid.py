"""Reproduce JD006, then change only its native entry for proven own-UID alignment."""
import hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());BASE=OUT/'packages/jd-006';TARGET=OUT/'packages/jd-007';TARGET.mkdir();FROZEN=TARGET/'source';FROZEN.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in('java_worker.cpp','own_uid.hpp','test_own_uid.cpp','relink_own_uid.py','package_payload.py'):shutil.copyfile(OUT/name,FROZEN/name)
env=os.environ.copy();env['LLVM_CONFIG']='/usr/bin/llvm-config-21';process={'pid':os.getpid(),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'BUILDING'};(TARGET/'process.json').write_text(json.dumps(process,indent=2)+'\n')
command=[json.loads(line)for line in(BASE/'link-command.json').read_text().splitlines()]
baseline=FROZEN/'baseline-relink.elf';check=list(command);check[check.index('-o')+1]=str(baseline);subprocess.run(check,check=True,env=env)
assert sha(baseline)==sha(BASE/'java-worker.elf')=='e7bc9a7efaaa1a82a05d09fb65e11df8f2ee7fed291ce4d8a3409852046002c0','Accepted JD006 objects changed'
compiler='/usr/lib/llvm-21/bin/clang++';host=TARGET/'own-uid-host-test';host_command=[compiler,'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(FROZEN/'test_own_uid.cpp'),'-o',str(host)]
subprocess.run(host_command,check=True);proof=subprocess.run([str(host)],capture_output=True,text=True,check=True);host_result=json.loads(proof.stdout);(FROZEN/'host-own-uid-tests.json').write_text(json.dumps(host_result,indent=2)+'\n')
sdk=Path(C['sdk']);port=Path(C['port']);headers=Path(C['source'])/'build/ps5-bootstrap/support/modules_include/java.base';entry=TARGET/'java-worker.o'
compile_command=[compiler,'-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',str(sdk),'-isystem',str(sdk/'target/include/c++/v1'),'-isystem',str(sdk/'target/include'),'-I',str(headers),'-I',str(headers/'freebsd'),'-I',str(port/'java25/probe'),'-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-stack-protector','-fno-plt','-femulated-tls','-fno-exceptions','-fno-rtti','-c',str(FROZEN/'java_worker.cpp'),'-o',str(entry)]
subprocess.run(compile_command,check=True)
old_entry=BASE/'java-worker.o';elf=TARGET/'java-worker.elf';updated=[str(elf)if p==str(BASE/'java-worker.elf')else str(entry)if p==str(old_entry)else p for p in command];assert str(entry)in updated and str(old_entry)not in updated
subprocess.run(updated,check=True,env=env)
disassembly=subprocess.run(['/usr/lib/llvm-21/bin/llvm-objdump','-dr','--no-show-raw-insn',str(entry)],capture_output=True,text=True,check=True).stdout;(FROZEN/'entry-disassembly.txt').write_text(disassembly)
relocations=subprocess.run(['/usr/lib/llvm-21/bin/llvm-readelf','-r',str(entry)],capture_output=True,text=True,check=True).stdout;(FROZEN/'entry-relocations.txt').write_text(relocations)
assert len(re.findall(r'\bsetuid\s+[+-]',relocations))==1,'Expected one imported setuid pointer relocation'
runtime_inputs=[{'path':p,'sha256':sha(Path(p)),'bytes':Path(p).stat().st_size}for p in command if Path(p).is_file()and Path(p).suffix in('.o','.a','.ld')]
(FROZEN/'runtime-inputs.json').write_text(json.dumps(runtime_inputs,indent=2)+'\n');(FROZEN/'compile-command.json').write_text(json.dumps(compile_command,indent=2)+'\n');(FROZEN/'host-compile-command.json').write_text(json.dumps(host_command,indent=2)+'\n');(TARGET/'link-command.json').write_text('\n'.join(json.dumps(p)for p in updated)+'\n')
image=json.loads((BASE/'export-receipt.json').read_text());result={'status':'BUILT_NOT_TARGET_TESTED','change':'Only native entry aligns its own real UID with inherited effective UID before constructors/JNI: exact1/0 setuid(currenteUID) once, already0/0 accepted, unexpected IDs/API/group mismatch fail closed. No groups/chmod/other process changes.','source_sha256':sha(FROZEN/'java_worker.cpp'),'uid_helper_sha256':sha(FROZEN/'own_uid.hpp'),'baseline_relinked_byte_identical':True,'baseline_sha256':sha(baseline),'shared_helper_mock_tests':host_result,'elf':{'path':str(elf),'bytes':elf.stat().st_size,'sha256':sha(elf)},'archive':image['archive'],'manifest':image['manifest'],'file_count':image['file_count'],'uncompressed_bytes':image['uncompressed_bytes'],'compat_object_sha256':image['compat_object_sha256'],'console_tested':False}
(TARGET/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n');process.update(status='COMPLETE',exit_code=0,finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()));(TARGET/'process.json').write_text(json.dumps(process,indent=2)+'\n');print(json.dumps(result,indent=2))
