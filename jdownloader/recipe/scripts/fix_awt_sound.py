"""Do not build unavailable optional ALSA sound provider for downloader worker."""
import difflib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent;C=json.loads((OUT/'linux-build-paths.json').read_text());p=Path(C['source'])/'make/modules/java.desktop/Lib.gmk';old=p.read_text()
start='ifeq ($(call isTargetOs, aix), false)';end='ifeq ($(call isTargetOs, macosx), true)\n  ##############################################################################\n  # Build libosxapp'
assert old.count(start)==1 and old.count(end)==1
new=old.replace(start,'# PS5 downloader has no ALSA sound service.\nifneq ($(PS5_BOOTSTRAP), yes)\n'+start).replace(end,'endif # PS5 optional sound service\n\n'+end);p.write_text(new)
(OUT/'awt-sound.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),str(p)+'.before',str(p))))
