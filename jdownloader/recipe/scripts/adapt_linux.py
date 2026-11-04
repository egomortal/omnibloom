"""Only private pinned-source adaptations for Linux host and owned PS5 paths."""
import difflib,hashlib,json,os
from pathlib import Path
OUT=Path(__file__).resolve().parent
C=json.loads((OUT/'linux-build-paths.json').read_text());PORT=Path(C['port']);SOURCE=Path(C['source'])
rows=[];diffs=[]
def change(p,text):
 old=p.read_text()
 if old==text:return
 rows.append({'path':str(p),'before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(text.encode()).hexdigest()})
 diffs.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),str(p)+'.before',str(p)))
 p.write_text(text)
for p in SOURCE.joinpath('src').rglob('*'):
 if p.suffix not in ('.c','.cpp','.hpp','.java','.h'):continue
 old=p.read_text(errors='strict')
 if '/app0/assets/java25' not in old and '/download0' not in old:continue
 new=old.replace('/app0/assets/java25/jars/','/data/omni-downloader/jdownloader/runtime/')
 new=new.replace('/app0/assets/java25','/data/omni-downloader/jdownloader/native/java25')
 new=new.replace('/download0','/data/omni-downloader/jdownloader/native')
 # Default working directory only; explicit per-session properties override it.
 new=new.replace('sprops.user_dir = "/app0"','sprops.user_dir = "/data/omni-downloader/jdownloader/runtime"')
 change(p,new)
for name in ('java25_builtin_runtime.py','package_java25_jni.py','package_native.py'):
 p=PORT/'tools'/name;old=p.read_text();new=old.replace('"/opt/homebrew/opt/openjdk@25/bin/javac"','str(Path(os.environ["JAVA25_BOOT_JDK"])/"bin/javac")')
 if name=='java25_builtin_runtime.py':
  new=new.replace('import hashlib','import hashlib\nimport os')
  new=new.replace("['/opt/homebrew/opt/llvm/bin/llvm-config','--bindir']","[os.environ['LLVM_CONFIG'],'--bindir']")
  new=new.replace("LLD = Path(subprocess.check_output(['brew','--prefix','lld'],text=True).strip())/'bin/ld.lld'","LLD = LLVM/'ld.lld'")
  new=new.replace('/app0/assets/java25','/data/omni-downloader/jdownloader/native/java25')
 change(p,new)
(OUT/'private-adaptations.json').write_text(json.dumps(rows,indent=2)+'\n')
(OUT/'private-adaptations.patch').write_text(''.join(diffs))
print(json.dumps({'private_adaptations':len(rows),'shared_changes':False}))
