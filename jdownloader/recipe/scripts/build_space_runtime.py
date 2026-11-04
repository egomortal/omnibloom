"""Private008: real, target-proven capacity and bounded mount backends only."""
import hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());SRC=Path(C['source']);SDK=Path(C['sdk']);BASE=OUT/'packages/jd-007';TARGET=OUT/'packages/jd-008';TARGET.mkdir();FROZEN=TARGET/'source';FROZEN.mkdir();LLVM=Path('/usr/lib/llvm-21/bin');env=dict(os.environ,LLVM_CONFIG='/usr/bin/llvm-config-21',JAVA25_BOOT_JDK=C['jdk']);env['PATH']=str(Path(C['temporary_build_root'])/'host-tools/bin')+':'+C['jdk']+'/bin:'+str(LLVM)+':'+env['PATH']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(argv,**kwargs):return subprocess.run([str(x)for x in argv],check=True,env=env,**kwargs)
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
process=dict(pid=os.getpid(),started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),status='BASELINE')
def checkpoint(status):process['status']=status;(TARGET/'process.json').write_text(json.dumps(process,indent=2)+'\n')
checkpoint('BASELINE')
for name in('space_compat.cpp','test_space_compat.cpp','ps5MountSnapshot.h','test_mount_snapshot.cpp','build_space_runtime.py'):shutil.copyfile(OUT/name,FROZEN/name)
shutil.copyfile(BASE/'source/java_worker.cpp',FROZEN/'java_worker.cpp');shutil.copyfile(BASE/'source/own_uid.hpp',FROZEN/'own_uid.hpp')
command=[json.loads(line)for line in(BASE/'link-command.json').read_text().splitlines()];baseline=FROZEN/'baseline-relink.elf';test=list(command);test[test.index('-o')+1]=str(baseline);run(test)
assert sha(baseline)==sha(BASE/'java-worker.elf')=='3f78951c09fb9ce686b6031d8552e57461a3853a9ae48f0a0acae769e0e40e49','Accepted007 provider inputs changed'
paths={'UnixFileSystem_md.c':SRC/'src/java.base/unix/native/libjava/UnixFileSystem_md.c','UnixNativeDispatcher.c':SRC/'src/java.base/unix/native/libnio/fs/UnixNativeDispatcher.c','BsdNativeDispatcher.c':SRC/'src/java.base/bsd/native/libnio/fs/BsdNativeDispatcher.c'}
for name,path in paths.items():shutil.copyfile(path,FROZEN/(name+'.prior'))
for name,begin,end in [('UnixFileSystem_md.c','Java_java_io_UnixFileSystem_getSpace','JNIEXPORT jlong JNICALL\nJava_java_io_UnixFileSystem_getNameMax0'),('UnixNativeDispatcher.c','Java_sun_nio_fs_UnixNativeDispatcher_statvfs0','JNIEXPORT void JNICALL\nJava_sun_nio_fs_UnixNativeDispatcher_mknod0')]:
 path=paths[name];text=path.read_text();start=text.index(begin);stop=text.index(end,start);body=text[start:stop];first=body.index('#ifdef __PROSPERO__');otherwise=body.index('#else',first);body=body[:first]+body[otherwise+len('#else'):];last=body.rfind('\n#endif');assert last>=0;body=body[:last]+body[last+len('\n#endif'):];text=text[:start]+body+text[stop:];path.write_text(text)
path=paths['BsdNativeDispatcher.c'];text=path.read_text();start=text.index('Java_sun_nio_fs_BsdNativeDispatcher_getfsstat');stop=text.index('\nJNIEXPORT jint JNICALL',start);body=text[start:stop];otherwise=body.index('#else');first=body.index('#ifdef __PROSPERO__')
replacement='''#ifdef __PROSPERO__
    struct fsstat_iter *iter = malloc(sizeof(*iter));
    if (iter == NULL) { JNU_ThrowOutOfMemoryError(env, "native heap"); return 0; }
    iter->buf = NULL; iter->pos = 0; iter->nentries = 0;
    if (ps5_mount_snapshot(getfsstat, &iter->buf, &iter->nentries) < 0) {
        int error = errno; free(iter); throwUnixException(env, error); return 0;
    }
    for (int i = 0; i < iter->nentries; ++i) {
        struct statfs *entry = &iter->buf[i];
        if (entry->f_version != STATFS_VERSION ||
            memchr(entry->f_fstypename, 0, sizeof(entry->f_fstypename)) == NULL ||
            memchr(entry->f_mntfromname, 0, sizeof(entry->f_mntfromname)) == NULL ||
            memchr(entry->f_mntonname, 0, sizeof(entry->f_mntonname)) == NULL) {
            free(iter->buf); free(iter); throwUnixException(env, EIO); return 0;
        }
    }
    return (jlong)iter;
'''
body=body[:first]+replacement+body[otherwise:];text=text[:start]+body+text[stop:];text=text.replace('#include "sun_nio_fs_BsdNativeDispatcher.h"','#include "sun_nio_fs_BsdNativeDispatcher.h"\n#ifdef __PROSPERO__\n#include "ps5MountSnapshot.h"\n#endif');path.write_text(text);shutil.copyfile(FROZEN/'ps5MountSnapshot.h',path.with_name('ps5MountSnapshot.h'))
for name,path in paths.items():shutil.copyfile(path,FROZEN/name)
checkpoint('HOST_TESTS')
tests={}
for name,flags,sources in [('space',['-DOMNI_SPACE_HOST_TEST'],['space_compat.cpp','test_space_compat.cpp']),('mount',[],['test_mount_snapshot.cpp'])]:
 host=TARGET/(name+'-host-test');args=[LLVM/'clang++','-std=c++20','-O2','-Wall','-Wextra','-Werror',*flags,*[FROZEN/p for p in sources],'-o',host];run(args);result=run([host],capture_output=True,text=True);tests[name]=json.loads(result.stdout)
(FROZEN/'host-tests.json').write_text(json.dumps(tests,indent=2)+'\n')
checkpoint('REBUILDING_PRIVATE_NATIVE_LIBRARIES')
with(TARGET/'native-libraries-build.log').open('x')as log:
 child=subprocess.Popen(['gmake','CONF=ps5-bootstrap','java.base-libs'],cwd=SRC,env=env,stdout=log,stderr=subprocess.STDOUT);process['owned_build_pid']=child.pid;checkpoint('REBUILDING_PRIVATE_NATIVE_LIBRARIES');code=child.wait(timeout=1200);assert code==0,'Private native build failed; log retained'
checkpoint('MERGING_CHANGED_PROVIDERS');build=SRC/'build/ps5-bootstrap';old={};replacements={}
for name in('java','nio'):
 old_path=Path(C['port'])/'build/java25'/('embedded-'+name+'.o');old[name]=pin(old_path);objects=sorted((build/'support/native/java.base'/('lib'+name)).glob('*.o'));assert objects
 rsp=TARGET/(name+'-objects.rsp');rsp.write_text('\n'.join(json.dumps(str(p))for p in objects)+'\n');merged=TARGET/('embedded-'+name+'.o');run([LLVM/'ld.lld','-r','@'+str(rsp),'-o',merged]);symbols=subprocess.check_output([str(LLVM/'llvm-nm'),'--defined-only','--extern-only',str(merged)],text=True);options=[]
 for entry in('JNI_OnLoad','JNI_OnUnload'):
  if re.search(r'\b'+entry+r'$',symbols,re.M):options+=['--redefine-sym',entry+'=ps5_'+name+'_'+entry]
 if name=='java':
  for entry in('jio_snprintf','jio_fprintf'):options+=['--redefine-sym',entry+'=ps5_java_'+entry]
 if options:run([LLVM/'llvm-objcopy',*options,merged])
 sections=subprocess.check_output([str(LLVM/'llvm-readelf'),'-SW',str(merged)],text=True);names=sorted(set(re.findall(r'\]\s+(\.(?:init_array|ctors)\S*)\s',sections)))
 if names:run([LLVM/'llvm-objcopy',*[x for section in names for x in('--rename-section',section+'=.data.rel.ro.jvm_init_array.'+name+section)],merged])
 def exported(p):return {line.split()[-1]for line in subprocess.check_output([str(LLVM/'llvm-nm'),'--defined-only','--extern-only',str(p)],text=True).splitlines()if len(line.split())==3}
 assert exported(merged)==exported(old_path),'Resident exported symbol table changed'
 replacements[str(old_path)]=str(merged);(FROZEN/(name+'-native-inputs.json')).write_text(json.dumps([pin(p)for p in objects],indent=2)+'\n')
space=TARGET/'space-compat.o';compile=[LLVM/'clang++','-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',SDK,'-isystem',SDK/'target/include/c++/v1','-isystem',SDK/'target/include','-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-stack-protector','-fno-plt','-femulated-tls','-fno-exceptions','-fno-rtti','-c',FROZEN/'space_compat.cpp','-o',space];run(compile)
disassembly=subprocess.check_output([str(LLVM/'llvm-objdump'),'-dr','--no-show-raw-insn',str(space)],text=True);(FROZEN/'space-compat.disassembly.txt').write_text(disassembly);assert disassembly.count('syscall')==3 and len(re.findall(r'syscall\n[^\n]*setb',disassembly))==3 and '__error' in disassembly
checkpoint('FINAL_LINK');elf=TARGET/'java-worker.elf';updated=[str(elf)if p==str(BASE/'java-worker.elf')else replacements.get(p,p)for p in command]+[str(space),'--wrap=statfs','--wrap=fstatfs','--wrap=getfsstat'];run(updated)
(TARGET/'link-command.json').write_text('\n'.join(json.dumps(str(x))for x in updated)+'\n');(FROZEN/'space-compile-command.json').write_text(json.dumps([str(x)for x in compile],indent=2)+'\n')
image=json.loads((BASE/'export-receipt.json').read_text());result=dict(status='BUILT_NOT_TARGET_TESTED',change='Real target-proven statfs396/fstatfs397/getfsstat395 with actual carry/errno; restored native java.io+NIO capacity, bounded complete mount enumeration; same007entry,005atcompat,002image',baseline_relinked_byte_identical=True,baseline_sha256=sha(baseline),native_entry_sha256=sha(FROZEN/'java_worker.cpp'),elf=pin(elf),archive=image['archive'],manifest=image['manifest'],file_count=image['file_count'],uncompressed_bytes=image['uncompressed_bytes'],compat_object_sha256=image['compat_object_sha256'],space_compat=pin(space),changed_providers={name:dict(before=old[name],after=pin(TARGET/('embedded-'+name+'.o')))for name in('java','nio')},host_tests=tests,native_sources={name:sha(FROZEN/name)for name in paths},console_tested=False)
(TARGET/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n');checkpoint('COMPLETE');print(json.dumps(result,indent=2))
