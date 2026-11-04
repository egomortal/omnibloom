"""Bounded reproducible native build steps; called only inside WSL."""
import datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
CONFIG=json.loads((OUT/'linux-build-paths.json').read_text())
PORT=Path(CONFIG['port']);SOURCE=Path(CONFIG['source']);BASE=Path(CONFIG['temporary_build_root'])
ENV=dict(os.environ,LLVM_CONFIG='/usr/bin/llvm-config-21',JAVA25_BOOT_JDK=CONFIG['jdk'])
ENV['PATH']=str(BASE/'host-tools/bin')+':'+CONFIG['jdk']+'/bin:/usr/lib/llvm-21/bin:'+ENV['PATH']
def run(name,args,cwd,timeout=1800):
 logs=OUT/'logs';logs.mkdir(exist_ok=True)
 log=logs/(name+'.log')
 if log.exists():raise ValueError('Refusing existing evidence: '+str(log))
 start=time.time()
 with log.open('x') as f:
  p=subprocess.Popen([str(a) for a in args],cwd=cwd,env=ENV,stdout=f,stderr=subprocess.STDOUT)
  record={'name':name,'pid':p.pid,'args':[str(a) for a in args],'cwd':str(cwd),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'temporary_build_root':str(BASE)}
  (logs/(name+'-process.json')).write_text(json.dumps(record,indent=2)+'\n')
  try:code=p.wait(timeout)
  except subprocess.TimeoutExpired:p.terminate();code=p.wait(10);record['timeout']=True
 record.update(exit_code=code,elapsed_seconds=time.time()-start,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
 (logs/(name+'-receipt.json')).write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record,indent=2),flush=True)
 print(log.read_text(errors='replace')[-6000:],flush=True)
 return code
def main():
 step=sys.argv[1]
 if step.startswith('autoconf'):
  auto=Path(CONFIG['autoconf'])
  if run(step+'-configure',['bash','configure','--prefix='+str(BASE/'host-tools')],auto):return 1
  return run(step+'-install',['make','-j4','install'],auto)
 if step.startswith('configure'):
  wrapper=PORT/'tools/java25_cc.py';wrapper.chmod(0o755)
  command=['bash','configure',*(['--build=x86_64-pc-linux-gnu'] if step!='configure-001' else []),'--openjdk-target=x86_64-unknown-freebsd','--with-jvm-variants=server','--with-boot-jdk='+CONFIG['jdk'],'--disable-warnings-as-errors','--enable-headless-only','--with-toolchain-type=clang','--with-native-debug-symbols=none','--with-freetype=bundled','CC='+str(wrapper),'CXX='+CONFIG['sdk']+'/bin/prospero-clang++','--enable-ps5-bootstrap','--with-conf-name=ps5-bootstrap','--with-jobs=4','--with-sysroot='+CONFIG['sdk'],'--with-stdc++lib=dynamic','--with-extra-cxxflags=-fno-stack-protector','--with-jvm-features=-dtrace']
  if step not in ('configure-001','configure-002'):command+=['BUILD_CC=/usr/lib/llvm-21/bin/clang','BUILD_CXX=/usr/lib/llvm-21/bin/clang++']
  return run(step,command,SOURCE)
 if step.startswith('hotspot'):return run(step,['gmake','CONF=ps5-bootstrap','hotspot'],SOURCE,7200)
 if step.startswith('base'):return run(step,['gmake','CONF=ps5-bootstrap','java.base-java','java.base-libs'],SOURCE,7200)
 if step.startswith('desktop'):return run(step,['gmake','CONF=ps5-bootstrap','java.desktop-libs'],SOURCE,3600)
 if step.startswith('modules'):return run(step,['gmake','CONF=ps5-bootstrap',*[m+'-java' for m in ('java.desktop','java.management','java.naming','java.prefs','java.rmi','java.scripting','java.sql','jdk.httpserver','jdk.unsupported','jdk.crypto.ec')],'java.management-libs'],SOURCE,3600)
 if step.startswith('package-hello'):return run(step,['python3',OUT/'package_payload.py','--name',step.removeprefix('package-'),'--modules','java.base'],OUT,3600)
 if step.startswith('package-jd'):return run(step,['python3',OUT/'package_payload.py','--name',step.removeprefix('package-'),'--modules','java.base,java.desktop,java.management,java.naming,java.prefs,java.rmi,java.scripting,java.sql,jdk.httpserver,jdk.unsupported','--management','--external-libraries',OUT/'resident-libraries.json'],OUT,3600)
 if step=='uncompressed-hello-001':return run(step,['python3',OUT/'uncompressed_image.py'],OUT,3600)
 raise ValueError(step)
if __name__=='__main__':raise SystemExit(main())
