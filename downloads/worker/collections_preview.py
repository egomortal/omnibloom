"""Bounded collection quotes over an injected public-network extractor. GPL-3.0-or-later."""
import hashlib,ipaddress,secrets,threading,time
from urllib.parse import urlsplit

def public_url(value):
    if not isinstance(value,str) or len(value)>4096:raise ValueError('Invalid link')
    u=urlsplit(value)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:raise ValueError('Invalid link')
    h=u.hostname.lower()
    if h=='localhost' or h.endswith(('.local','.localhost','.internal')) or '.' not in h:raise ValueError('Public link required')
    try:
        if not ipaddress.ip_address(h).is_global:raise ValueError('Public link required')
    except ValueError as error:
        if str(error)=='Public link required':raise
    return value

class Collections:
    def __init__(self,extract,create_job,clock=time.monotonic):
        self.extract,self.create_job,self.clock=extract,create_job,clock
        self.lock=threading.Lock();self.previews={}
    def inspect(self,url):
        public_url(url)
        # Extractor must enforce public DNS/redirect policy for every request.
        data=self.extract(url,{'extract_flat':'in_playlist','playlistend':101,'skip_download':True,'noplaylist':False,'ignoreerrors':True})
        if not isinstance(data,dict):raise ValueError('Invalid collection metadata')
        raw=data.get('entries')
        if raw is None:raise ValueError('This link is not a collection')
        entries=[];truncated=False
        for index,row in enumerate(raw):
            if index>=100:truncated=True;break
            if not isinstance(row,dict):continue
            if row.get('is_live') or row.get('live_status') in ('is_live','is_upcoming'):continue
            url=row.get('webpage_url') or row.get('url')
            try:public_url(url)
            except (ValueError,TypeError):continue
            size=row.get('filesize') or row.get('filesize_approx')
            if type(size) is not int or not 0<=size<=2**53-1:size=None
            entries.append({'id':str(index),'title':str(row.get('title') or 'Untitled video')[:240],'url':url,'bytes':size})
        identity=secrets.token_hex(16);record={'id':identity,'title':str(data.get('title') or 'Collection')[:240],'entries':entries,'truncated':truncated,'expires':self.clock()+300,'accepted':{}}
        with self.lock:
            self.previews={k:v for k,v in self.previews.items() if v['expires']>self.clock()}
            while len(self.previews)>=8:self.previews.pop(next(iter(self.previews)))
            self.previews[identity]=record
        return {k:([{x:y for x,y in e.items() if x!='url'} for e in v] if k=='entries' else v) for k,v in record.items() if k not in ('expires','accepted')}
    def submit(self,identity,ids):
        if not isinstance(ids,list) or not 1<=len(ids)<=8 or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):raise ValueError('Choose1 to8 distinct entries')
        with self.lock:
            record=self.previews.get(identity)
            if not record or record['expires']<=self.clock():raise ValueError('Preview expired; inspect again')
            selected=[]
            for entry_id in ids:
                entry=next((e for e in record['entries'] if e['id']==entry_id),None)
                if not entry:raise ValueError('Entry is not in this preview')
                selected.append(entry)
            accepted=[];error=None
            for entry in selected:
                key=entry['id']
                if key not in record['accepted']:
                    request_id=hashlib.sha256((identity+':'+key).encode()).hexdigest()[:32]
                    try:record['accepted'][key]=self.create_job(entry['url'],demo=False,request_id=request_id,engine='ytdlp',auto_fallback=False)
                    except Exception:
                        error='Queue did not confirm this entry; inspect the queue before retrying.';break
                accepted.append({'entryId':key,'jobId':record['accepted'][key]})
            return {'accepted':accepted,'error':error}
