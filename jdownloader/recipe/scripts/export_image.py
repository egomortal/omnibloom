"""Create deterministic target-only image archive and independently hash every file."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
folder=ROOT/'packages'/sys.argv[1]
archive=folder/'native-image.zip';rows=[]
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted((folder/'java25').rglob('*')):
  if not p.is_file():continue
  data=p.read_bytes();name=p.relative_to(folder).as_posix();info=zipfile.ZipInfo(name,date_time=(2026,10,26,0,0,0));info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
  rows.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
manifest=dict(schema='omni-java-native-image/v1',target_root='/data/omni-downloader/jdownloader/native',console_tested=False,files=rows)
(folder/'image-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
elf=folder/'java-worker.elf'
result=dict(archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest()),manifest=dict(path=str(folder/'image-manifest.json'),sha256=hashlib.sha256((folder/'image-manifest.json').read_bytes()).hexdigest()),elf=dict(path=str(elf),bytes=elf.stat().st_size,sha256=hashlib.sha256(elf.read_bytes()).hexdigest()),file_count=len(rows),uncompressed_bytes=sum(r['bytes'] for r in rows),console_tested=False)
(folder/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
