"""Extract verified inputs into one fresh no-spaces Linux temporary build tree."""
import hashlib,json,os,subprocess,tarfile,zipfile
from pathlib import Path
OUT=Path(__file__).resolve().parent
BUILD=Path('/var/tmp/omni-jd-native-20261026-001')
PINS={'port.tar.gz':'e7e73cc3f91135590c4d8b85bcd19de19e7ead16adab1c1bb08137df24062863','sdk-v0.42.zip':'8cfbc7cd5811e719eb4f0c47eea668d3dc7b40bc8ab11c4a5031d40c23ec02da','host-jdk.tar.gz':'e58fcdcd637b25c03ca84cbbcefc70d11efb8f4b4cbd05decc9f661769d77f94','openjdk.tar.gz':'dd52da87ee131a68e8d10d56f7a9adc82d322f0448dcd7438e16e9b8d070fd7a','autoconf.tar.gz':'afb181a76e1ee72832f6581c0eddf8df032b83e2e0239ef79ebedc4467d92d6e'}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def tar(name,dest):
 dest.mkdir(parents=True)
 with tarfile.open(OUT/'downloads'/name) as a:
  members=a.getmembers();top={m.name.split('/')[0] for m in members}
  assert len(top)==1
  for m in members:
   assert not m.name.startswith('/') and '..' not in Path(m.name).parts
  a.extractall(dest,filter='data')
 return dest/next(iter(top))
def main():
 for name,pin in PINS.items():assert digest(OUT/'downloads'/name)==pin,name
 BUILD.mkdir()
 port=tar('port.tar.gz',BUILD/'port')/'Development'
 jdk=tar('host-jdk.tar.gz',BUILD/'host-jdk')
 source=tar('openjdk.tar.gz',BUILD/'source')
 auto=tar('autoconf.tar.gz',BUILD/'autoconf')
 sdk=port/'.tools/native-sdk';sdk.mkdir(parents=True)
 with zipfile.ZipFile(OUT/'downloads/sdk-v0.42.zip') as z:
  for row in z.infolist():assert not row.filename.startswith('/') and '..' not in Path(row.filename).parts
  z.extractall(sdk)
 for p in (sdk/'ps5-payload-sdk/bin').iterdir():p.chmod(0o755)
 cache=port/'.tools/java25';cache.mkdir(parents=True)
 (cache/'openjdk').symlink_to(source,target_is_directory=True)
 # Archive verification replaces git-object availability, preserving exact source pin.
 (source/'.omni-pinned-archive.json').write_text(json.dumps({'commit':'b219cdec88ca2e165711f63b8158ab78303facc8','archive_sha256':PINS['openjdk.tar.gz']}))
 for patch in sorted((port/'java25/patches').glob('*.patch')):
  subprocess.run(['git','apply','--check',str(patch)],cwd=source,check=True)
  subprocess.run(['git','apply',str(patch)],cwd=source,check=True)
 config={'temporary_build_root':str(BUILD),'port':str(port),'jdk':str(jdk),'source':str(source),'autoconf':str(auto),'sdk':str(sdk/'ps5-payload-sdk'),'input_sha256':PINS}
 (OUT/'linux-build-paths.json').write_text(json.dumps(config,indent=2)+'\n')
 print(json.dumps(config,indent=2),flush=True)
if __name__=='__main__':main()
