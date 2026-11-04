"""Build an actual standalone PS5 Java payload; no native-app converter required."""
import argparse,hashlib,json,os,re,shutil,subprocess,time,zipfile
from pathlib import Path
OUT=Path(__file__).resolve().parent
C=json.loads((OUT/'linux-build-paths.json').read_text());PORT=Path(C['port']);SOURCE=Path(C['source']);SDK=Path(C['sdk']);LLVM=Path('/usr/lib/llvm-21/bin')
BUILD=SOURCE/'build/ps5-bootstrap';WORK=PORT/'build/java25';ENV=dict(os.environ,LLVM_CONFIG='/usr/bin/llvm-config-21',JAVA25_BOOT_JDK=C['jdk']);ENV['PATH']=str(LLVM)+':'+ENV['PATH']
def run(*args,**kw):subprocess.run([str(x) for x in args],check=True,env=ENV,**kw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rsp(p,args):p.write_text('\n'.join(json.dumps(str(x)) for x in args)+'\n')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--modules',default='java.base');parser.add_argument('--management',action='store_true');parser.add_argument('--external-libraries');args=parser.parse_args()
 if not re.fullmatch('[a-z0-9-]{1,60}',args.name):raise ValueError('Invalid evidence name')
 evidence=OUT/'packages'/args.name;evidence.mkdir(parents=True)
 frozen=evidence/'source';frozen.mkdir()
 for name in ('java_worker.cpp','package_payload.py','build_step.py','resident_spec.py'):
  shutil.copyfile(OUT/name,frozen/name)
 references=[{'path':str(p.relative_to(OUT)),'sha256':sha(p)} for p in sorted(OUT.glob('*.patch'))]
 (frozen/'input-references.json').write_text(json.dumps({'pinned_inputs':C['input_sha256'],'private_patches':references,'worker_source_sha256':sha(frozen/'java_worker.cpp')},indent=2)+'\n')
 WORK.mkdir(parents=True,exist_ok=True)
 objects=sorted((BUILD/'hotspot/variant-server/libjvm/objs').glob('*.o'));assert len(objects)>1000
 rsp(WORK/'jvm-objects.rsp',objects)
 merged=WORK/'embedded-jvm.o';run(LLVM/'ld.lld','-r','@'+str(WORK/'jvm-objects.rsp'),'-o',merged)
 sections=subprocess.check_output([str(LLVM/'llvm-readelf'),'-SW',str(merged)],text=True)
 names=sorted(set(re.findall(r'\]\s+(\.(?:init_array|ctors)\S*)\s',sections)));assert names
 run(LLVM/'llvm-objcopy',*[v for name in names for v in ('--rename-section',name+'=.data.rel.ro.jvm_init_array'+name)],merged)
 libc=WORK/'native-libc.a';shutil.copyfile(SDK/'target/lib/libc.a',libc);run(LLVM/'llvm-ar','d',libc,'mman.o')
 backends=[]
 for member,expected,rebound,source in [
  ('emutls.o','f12a423ab50bab567caab55986904949f3b15074d253e95b151374054b57d94d',{'malloc':'ps5_emutls_malloc','realloc':'ps5_emutls_realloc','free':'ps5_emutls_free','pthread_setspecific':'ps5_emutls_setspecific','pthread_getspecific':'ps5_emutls_getspecific','pthread_key_create':'ps5_emutls_key_create'},'emutls_alloc.cpp'),
  ('netdb.o','ccf0c18495f3e1329570d4f0dac5157a00c5ab9625f2102b197e2575944197f4',{'malloc':'ps5_dns_malloc','free':'ps5_dns_free','strdup':'ps5_dns_strdup','getaddrinfo':'ps5_sdk_getaddrinfo','sceNetPoolCreate':'ps5_dns_pool_create','sceNetPoolDestroy':'ps5_dns_pool_destroy','sceNetResolverCreate':'ps5_dns_resolver_create','sceNetResolverDestroy':'ps5_dns_resolver_destroy','sceNetResolverStartNtoa':'ps5_dns_ntoa'},'netdb_alloc.cpp')]:
  folder=WORK/member;folder.mkdir(exist_ok=True);run(LLVM/'llvm-ar','x',libc,member,cwd=folder);obj=folder/member;assert sha(obj)==expected,member
  run(LLVM/'llvm-objcopy',*['--redefine-sym='+a+'='+b for a,b in rebound.items()],obj);run(LLVM/'llvm-ar','r',libc,obj)
  backend=folder/'backend.o';run(LLVM/'clang++','-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',SDK,'-isystem',SDK/'target/include/c++/v1','-isystem',SDK/'target/include','-std=c++20','-O2','-fno-exceptions','-fno-rtti','-fno-stack-protector','-femulated-tls','-c',PORT/'java25/probe'/source,'-o',backend);backends.append(backend)
 run('python3',PORT/'tools/java25_boot_image.py','--modules',args.modules)
 run('python3',PORT/'tools/java25_builtin_runtime.py',*(['--management'] if args.management else []),*(['--external-libraries',args.external_libraries] if args.external_libraries else []))
 assets=evidence/'java25';shutil.copytree(WORK/'boot-image',assets)
 native=BUILD/'support/modules_libs/java.base';(assets/'lib/server').mkdir(parents=True,exist_ok=True)
 shutil.copyfile(native/'server/libjvm.so',assets/'lib/server/libjvm.so')
 for name in ('java','zip','jimage','net','nio','verify'):shutil.copyfile(native/('lib'+name+'.so'),assets/'lib'/('lib'+name+'.so'))
 if args.management:shutil.copyfile(native.parent/'java.management/libmanagement.so',assets/'lib/libmanagement.so')
 if args.external_libraries:
  for row in json.loads(Path(args.external_libraries).read_text()):
   library=native.parent/'java.desktop'/('lib'+row['name']+'.so');assert library.is_file(),library
   shutil.copyfile(library,assets/'lib'/library.name)
 (assets/'classes').mkdir();run(Path(C['jdk'])/'bin/javac','--release','25','-d',assets/'classes',PORT/'java25/tests/Hello25.java')
 probe=OUT.parent/'jd-consumer/NativeProviderProbe.java'
 if args.external_libraries and probe.is_file():run(Path(C['jdk'])/'bin/javac','--release','25','-d',assets/'classes',probe)
 included_modules=re.search(r'^MODULES="([^"]+)"',(assets/'release').read_text(),re.M).group(1).split()
 for module in included_modules:
  legal=SOURCE/'src'/module/'share/legal'
  if legal.is_dir():shutil.copytree(legal,assets/'legal'/module,dirs_exist_ok=True)
 headers=BUILD/'support/modules_include/java.base';entry=evidence/'java-worker.o'
 run(LLVM/'clang++','-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',SDK,'-isystem',SDK/'target/include/c++/v1','-isystem',SDK/'target/include','-I',headers,'-I',headers/'freebsd','-I',PORT/'java25/probe','-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-stack-protector','-fno-plt','-femulated-tls','-fno-exceptions','-fno-rtti','-c',frozen/'java_worker.cpp','-o',entry)
 layout=(SDK/'ldscripts/elf_x86_64.x').read_text();needle='\t.data.rel.ro : { *(.data.rel.ro .data.rel.ro.*); }'
 assert needle in layout
 layout=layout.replace(needle,'\t.data.rel.ro : {\n PROVIDE_HIDDEN(__jvm_init_array_start = .);\n KEEP(*(SORT_BY_INIT_PRIORITY(.data.rel.ro.jvm_init_array.*)))\n KEEP(*(.data.rel.ro.jvm_init_array))\n PROVIDE_HIDDEN(__jvm_init_array_end = .);\n *(.data.rel.ro .data.rel.ro.*); }')
 script=evidence/'payload.ld';script.write_text(layout)
 wraps=['memcpy','memmove','memcmp','strcmp','strlen','memset','strncmp','strncpy','strchr','memchr','strcpy','malloc','calloc','realloc','free','strdup','abort','exit','_exit','pthread_create','pthread_join']
 # Keep the SDK payload CRT and its own loader implementation, but isolate its
 # private entry points from the JVM's actual resident-library adapter. Strong
 # definitions are renamed only in this copy, never ignored or zeroed.
 crt=evidence/'payload-crt1.o';shutil.copyfile(SDK/'target/lib/crt1.o',crt)
 with zipfile.ZipFile(OUT/'downloads/sdk-v0.42.zip') as z:
  assert sha(crt)==hashlib.sha256(z.read('ps5-payload-sdk/target/lib/crt1.o')).hexdigest()
 crt_before=sha(crt)
 run(LLVM/'llvm-objcopy',*['--redefine-sym=__dl'+name+'=omni_sdk_dl'+name for name in ('open','sym','close','error','addr')],crt)
 (evidence/'crt-adaptation.json').write_text(json.dumps({'before':crt_before,'after':sha(crt),'operation':'Scoped rename __dlopen/__dlsym/__dlclose/__dlerror/__dladdr in exact pinned SDK CRT only; real resident providers remain separate'},indent=2)+'\n')
 absent=['__cxa_thread_atexit_impl','collector_func_load']
 elf=evidence/'java-worker.elf';links=json.loads((WORK/'builtin-link-inputs.json').read_text())
 command=[SDK/'bin/prospero-lld','-T',script,'-e','_start','-o',elf,*['--wrap='+x for x in wraps],*['--defsym='+x+'=0' for x in absent],crt,entry,'--start-group',merged,*links,*backends,libc,SDK/'target/lib/libpthread.a',SDK/'target/lib/libc++.a',SDK/'target/lib/libc++abi.a',SDK/'target/lib/libunwind.a','--end-group','-L'+str(SDK/'target/lib'),'-lkernel_sys','-lSceLibcInternal','-lSceNet']
 rsp(evidence/'link-command.json',command)
 run(*command)
 symbols=subprocess.check_output([str(LLVM/'llvm-nm'),str(elf)],text=True);(evidence/'symbols.txt').write_text(symbols)
 values={fields[2]:int(fields[0],16) for line in symbols.splitlines() if len(fields:=line.split())==3 and re.fullmatch('[a-fA-F0-9]+',fields[0])}
 assert values['__jvm_init_array_end']>values['__jvm_init_array_start']
 dynamic=subprocess.check_output([str(LLVM/'llvm-readelf'),'-d',str(elf)],text=True);(evidence/'dynamic.txt').write_text(dynamic)
 inventory=[{'path':str(p.relative_to(evidence)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(evidence.rglob('*')) if p.is_file()]
 receipt={'status':'BUILT_NOT_TARGET_TESTED','console_tested':False,'hotspot_objects':len(objects),'staged_constructor_count':(values['__jvm_init_array_end']-values['__jvm_init_array_start'])//8,'elf':str(elf),'elf_sha256':sha(elf),'image':str(assets),'modules':args.modules,'files':inventory}
 (evidence/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='files'},indent=2),flush=True)
if __name__=='__main__':main()
