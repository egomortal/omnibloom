"""Select actual headless FreeType providers without X11 font server calls."""
import difflib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());p=Path(C['source'])/'make/modules/java.desktop/lib/ClientLibraries.gmk';old=p.read_text()
needle='LIBFONTMANAGER_CFLAGS += $(X_CFLAGS) -DLE_STANDALONE -DHEADLESS';assert old.count(needle)==1
new=old.replace(needle,'ifeq ($(PS5_BOOTSTRAP), yes)\n  LIBFONTMANAGER_EXCLUDE_FILES += X11FontScaler.c X11TextRenderer.c\nendif\n\n'+needle);p.write_text(new)
(OUT/'awt-x11-fonts.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),str(p)+'.before',str(p))))
