"""Link real headless glyph cache provider into PS5 fontmanager dependency set."""
import difflib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());p=Path(C['source'])/'make/modules/java.desktop/lib/ClientLibraries.gmk';old=p.read_text()
needle='ifeq ($(PS5_BOOTSTRAP), yes)\n  LIBFONTMANAGER_EXCLUDE_FILES += X11FontScaler.c X11TextRenderer.c';assert old.count(needle)==1
new=old.replace(needle,needle+'\n  LIBFONTMANAGER_JDK_LIBS += libawt_headless');p.write_text(new)
(OUT/'awt-font-dependency.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),str(p)+'.before',str(p))))
