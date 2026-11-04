"""Inventory only the target build's selected desktop objects, excluding stale files."""
import hashlib,json,shlex
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());BASE=Path(C['source'])/'build/ps5-bootstrap/support/native/java.desktop'
rows=[];audit=[]
for name in ('awt','awt_headless','mlib_image','lcms','javajpeg','freetype','fontmanager'):
 folder=BASE/('lib'+name);lists=list(folder.glob('*objectfilenames.txt'))
 if lists:objects=[Path(p) for p in shlex.split(lists[0].read_text())]
 else:
  commands=list(folder.glob('*run_ld.cmdline'));assert len(commands)==1,name
  objects=[Path(p) for p in shlex.split(commands[0].read_text()) if p.endswith('.o') and p.startswith(str(folder)+'/')]
 # Exact upstream static-library exception: base AWT owns this definition.
 if name=='awt_headless':objects=[p for p in objects if p.name!='systemScale.o']
 assert objects and len(objects)==len(set(objects))
 for p in objects:assert p.is_file() and p.parent==folder,(name,p)
 assert not any(p.name in ('CUPSfuncs.o','fontpath.o','X11FontScaler.o','X11TextRenderer.o') for p in objects),name
 rows.append({'name':name,'objects':[str(p) for p in objects]})
 audit.append({'name':name,'objects':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in objects]})
(OUT/'resident-libraries.json').write_text(json.dumps(rows,indent=2)+'\n')
(OUT/'resident-object-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
print([(r['name'],len(r['objects'])) for r in rows])
