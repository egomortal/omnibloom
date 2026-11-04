"""Scoped compatibility fixes to the extracted private SDK only."""
import difflib,hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent
C=json.loads((OUT/'linux-build-paths.json').read_text());SDK=Path(C['sdk'])
p=SDK/'bin/prospero-lld';old=p.read_text();new=old.replace('if [[ "$ARG" == "--shared" ]]; then','if [[ "$ARG" == "--shared" || "$ARG" == "-shared" ]]; then')
assert old!=new
p.write_text(new);p.chmod(0o755)
(OUT/'private-sdk-lld.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),str(p)+'.original',str(p))))
(OUT/'private-sdk-lld.json').write_text(json.dumps({'path':str(p),'before':hashlib.sha256(old.encode()).hexdigest(),'after':hashlib.sha256(new.encode()).hexdigest(),'reason':'LLVM21 passes -shared, but upstream SDK recognized only --shared and retained -pie','shared_sdk_changed':False},indent=2)+'\n')
