"""Reproduce JD005 then change only entry to call existing metadata sampler."""
import hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());BASE=OUT/'packages/jd-005';TARGET=OUT/'packages/jd-006';TARGET.mkdir();FROZEN=TARGET/'source';FROZEN.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('java_worker.cpp','relink_sampling.py','test_metadata_sampler.cpp','package_payload.py'):shutil.copyfile(OUT/name,FROZEN/name)
header=Path(C['source'])/'src/hotspot/share/runtime/ps5StartupTrace.hpp';shutil.copyfile(header,FROZEN/'ps5StartupTrace.hpp')
env=os.environ.copy();env['LLVM_CONFIG']='/usr/bin/llvm-config-21';process={'pid':os.getpid(),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'BUILDING'};(TARGET/'process.json').write_text(json.dumps(process,indent=2)+'\n')
command=[json.loads(line)for line in (BASE/'link-command.json').read_text().splitlines()]
baseline=FROZEN/'baseline-relink.elf';check=list(command);check[check.index('-o')+1]=str(baseline);subprocess.run(check,check=True,env=env)
assert sha(baseline)==sha(BASE/'java-worker.elf')=='ab87a9feb618b5b6c29c3e15c7a11889733706301360a9305f38b1f32dc9dacd','JD005 runtime objects changed'
sdk=Path(C['sdk']);port=Path(C['port']);headers=Path(C['source'])/'build/ps5-bootstrap/support/modules_include/java.base';entry=TARGET/'java-worker.o';compiler='/usr/lib/llvm-21/bin/clang++'
compile_command=[compiler,'-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',str(sdk),'-isystem',str(sdk/'target/include/c++/v1'),'-isystem',str(sdk/'target/include'),'-I',str(headers),'-I',str(headers/'freebsd'),'-I',str(port/'java25/probe'),'-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-stack-protector','-fno-plt','-femulated-tls','-fno-exceptions','-fno-rtti','-c',str(FROZEN/'java_worker.cpp'),'-o',str(entry)]
subprocess.run(compile_command,check=True)
old_entry=OUT/'packages/jd-004/java-worker.o';elf=TARGET/'java-worker.elf';updated=[str(elf)if p==str(BASE/'java-worker.elf')else str(entry)if p==str(old_entry)else p for p in command];assert str(entry)in updated and str(old_entry)not in updated
subprocess.run(updated,check=True,env=env)
host=TARGET/'metadata-sampler-host-test';host_command=[compiler,'-std=c++20','-O2','-Wall','-Wextra','-Werror','-D__PROSPERO__','-I',str(FROZEN),str(FROZEN/'test_metadata_sampler.cpp'),'-pthread','-o',str(host)]
subprocess.run(host_command,check=True);proof=subprocess.run([str(host)],capture_output=True,text=True,check=True);host_result=json.loads(proof.stdout);(FROZEN/'host-sampling-test.json').write_text(json.dumps(host_result,indent=2)+'\n')
symbols=subprocess.run(['/usr/lib/llvm-21/bin/llvm-nm',str(elf)],capture_output=True,text=True,check=True).stdout
interval=[line for line in symbols.splitlines()if line.endswith('_ZZ24ps5_vm_metadata_intervalvE5value')];assert len(interval)==1,'Sampler singleton not uniquely linked'
(FROZEN/'metadata-singleton-symbol.txt').write_text('\n'.join(interval)+'\n')
disassembly=subprocess.run(['/usr/lib/llvm-21/bin/llvm-objdump','-dr','--no-show-raw-insn',str(entry)],capture_output=True,text=True,check=True).stdout;(FROZEN/'entry-disassembly.txt').write_text(disassembly)
assert '_ZZ24ps5_vm_metadata_intervalvE5value' in disassembly and 'JNI_CreateJavaVM' in disassembly,'Entry lacks actual sampler/JNI relocations'
assert disassembly.index('_ZZ24ps5_vm_metadata_intervalvE5value')<disassembly.index('JNI_CreateJavaVM'),'Sampler must be configured before JNI'
runtime_inputs=[{'path':p,'sha256':sha(Path(p)),'bytes':Path(p).stat().st_size}for p in command if Path(p).is_file()and Path(p).suffix in('.o','.a','.ld')]
(FROZEN/'runtime-inputs.json').write_text(json.dumps(runtime_inputs,indent=2)+'\n');(FROZEN/'compile-command.json').write_text(json.dumps(compile_command,indent=2)+'\n');(FROZEN/'host-compile-command.json').write_text(json.dumps(host_command,indent=2)+'\n');(TARGET/'link-command.json').write_text('\n'.join(json.dumps(p)for p in updated)+'\n')
image=json.loads((BASE/'export-receipt.json').read_text());result={'status':'BUILT_NOT_TARGET_TESTED','change':'Only native entry calls existing shared metadata sampler before constructors/JNI; default1000, optional config metadata_interval0..1000000; all fault/signal/native-call context remains','source_sha256':sha(FROZEN/'java_worker.cpp'),'trace_header_sha256':sha(FROZEN/'ps5StartupTrace.hpp'),'baseline_relinked_byte_identical':True,'baseline_sha256':sha(baseline),'host_actual_header_sampling_test':host_result,'shared_sampler_singleton':interval,'elf':{'path':str(elf),'bytes':elf.stat().st_size,'sha256':sha(elf)},'archive':image['archive'],'manifest':image['manifest'],'file_count':image['file_count'],'uncompressed_bytes':image['uncompressed_bytes'],'compat_object_sha256':sha(BASE/'filesystem-compat.o'),'console_tested':False}
(TARGET/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n');process.update(status='COMPLETE',exit_code=0,finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()));(TARGET/'process.json').write_text(json.dumps(process,indent=2)+'\n');print(json.dumps(result,indent=2))
