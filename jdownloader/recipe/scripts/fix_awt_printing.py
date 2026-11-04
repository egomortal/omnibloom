"""Exclude unavailable optional CUPS printer native service on PS5 only."""
import difflib,hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());p=Path(C['source'])/'make/modules/java.desktop/lib/AwtLibraries.gmk';old=p.read_text()
needle='  LIBAWT_HEADLESS_EXTRA_HEADER_DIRS := '
replacement='''  # PS5 downloader has no CUPS print service. Do not compile a provider whose
  # headers/libraries are unavailable; image/raster/Font JNI remain real.
  ifeq ($(PS5_BOOTSTRAP), yes)
    LIBAWT_HEADLESS_EXCLUDE_FILES += CUPSfuncs.c
  endif

'''+needle
assert old.count(needle)==1;new=old.replace(needle,replacement);p.write_text(new)
(OUT/'awt-printing.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),str(p)+'.before',str(p))))
