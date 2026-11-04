"""Mark desktop fontconfig font-directory enumeration unavailable on PS5."""
import difflib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());p=Path(C['source'])/'make/modules/java.desktop/lib/AwtLibraries.gmk';old=p.read_text();needle='LIBAWT_HEADLESS_EXCLUDE_FILES += CUPSfuncs.c';assert old.count(needle)==1
new=old.replace(needle,needle+' fontpath.c');p.write_text(new)
(OUT/'awt-fontpath.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),str(p)+'.before',str(p))))
