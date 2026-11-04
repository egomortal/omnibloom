"""Authored subtitle selection, using injected existing extraction/network policy.

No HTTP endpoint. URLs remain server-side; UI gets opaque IDs only.
"""
import hashlib,re
from urllib.parse import urlsplit
MAX_BYTES=1024*1024
def extraction_options():
    return {'skip_download':True,'writesubtitles':False,'writeautomaticsub':False,
            'noplaylist':True,'cachedir':False,'socket_timeout':15,'quiet':True}
def tracks(info):
    result={}
    if not isinstance(info,dict):raise ValueError('Invalid media metadata')
    for language,formats in info.get('subtitles',{}).items():
        if not re.fullmatch(r'[A-Za-z0-9-]{1,35}',language):continue
        for item in formats[:50]:
            if item.get('ext') not in ('vtt','srt'):continue
            url=item.get('url','');parsed=urlsplit(url)
            if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:continue
            key=hashlib.sha256((language+'\0'+item['ext']+'\0'+url).encode()).hexdigest()[:24]
            result[key]={'name':language+' · '+item['ext'].upper(),'language':language,'format':item['ext'],'url':url}
            if len(result)>=100:return result
    return result
def public_rows(catalog):
    return [{'id':key,'name':row['name']} for key,row in catalog.items()]
def download(key,catalog,guarded_fetch):
    if key not in catalog:raise ValueError('Caption selection expired or unknown')
    row=catalog[key]
    # Native adapter MUST bound streaming bytes, every redirect/DNS resolution,
    # request timeout and public-address policy before returning data here.
    data=guarded_fetch(row['url'],max_bytes=MAX_BYTES,timeout_seconds=15)
    if not isinstance(data,bytes) or len(data)>MAX_BYTES:raise ValueError('Caption exceeds 1 MiB')
    text=data.decode('utf-8-sig',errors='strict')
    if '\x00' in text:raise ValueError('Binary caption response')
    return {'text':text,'format':row['format'],'name':row['name']}
