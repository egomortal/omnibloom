"""Pinned, isolated input acquisition. No console or global tool installation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib, json, shutil, time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parents[1]/'omni-downloader-tile-integration-20261025/java-native-build/downloads'
HOST=ROOT.parents[1]/'omni-jdownloader-prototype/host-java25'
REUSE={
 'port.tar.gz':(OLD/'port.tar.gz','e7e73cc3f91135590c4d8b85bcd19de19e7ead16adab1c1bb08137df24062863'),
 'sdk-v0.42.zip':(OLD/'sdk-v0.42.zip','8cfbc7cd5811e719eb4f0c47eea668d3dc7b40bc8ab11c4a5031d40c23ec02da'),
 'host-jdk.tar.gz':(HOST/'OpenJDK25U-jdk_x64_linux_hotspot_25.0.4_7.tar.gz','e58fcdcd637b25c03ca84cbbcefc70d11efb8f4b4cbd05decc9f661769d77f94')}
FETCH={
 'openjdk.tar.gz':'https://codeload.github.com/freebsd/openjdk/tar.gz/b219cdec88ca2e165711f63b8158ab78303facc8',
 'native.tar.gz':'https://codeload.github.com/blackbearreloaded/ps5-native-app-boilerplate/tar.gz/e79502f4ce3c278e41c172fe14b6ffe5164b29d3',
 'autoconf.tar.gz':'https://ftp.gnu.org/gnu/autoconf/autoconf-2.72.tar.gz'}

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()

def fetch(item):
 name,url=item;out=ROOT/'downloads'/name;start=time.monotonic();size=0
 with urlopen(Request(url,headers={'User-Agent':'Omni-isolated-native-Java-build'}),timeout=60) as response,out.open('xb') as f:
  while b:=response.read(1024*1024):
   size+=len(b)
   if size>512*1024**2 or time.monotonic()-start>1200:raise ValueError('Bound exceeded')
   f.write(b)
 print(json.dumps({'download':name,'bytes':size,'sha256':digest(out)}),flush=True)
 return dict(file=name,url=url,bytes=size,sha256=digest(out))

def main():
 (ROOT/'downloads').mkdir(exist_ok=True)
 rows=[]
 for name,(src,expected) in REUSE.items():
  actual=digest(src)
  if actual!=expected:raise ValueError('Pinned source differs: '+str(src))
  target=ROOT/'downloads'/name
  if target.exists():
   if digest(target)!=expected:raise ValueError('Existing target differs')
  else:shutil.copyfile(src,target)
  rows.append(dict(file=name,source=str(src),bytes=target.stat().st_size,sha256=actual))
 with ThreadPoolExecutor(max_workers=3) as pool:rows.extend(pool.map(fetch,FETCH.items()))
 (ROOT/'acquisition.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),inputs=rows),indent=2)+'\n')

if __name__=='__main__':main()
