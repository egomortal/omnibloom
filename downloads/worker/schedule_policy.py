"""UTC start windows and cooperative average-rate limits. GPL-3.0-or-later."""
import datetime,json,os,threading,time
from pathlib import Path
DEFAULT={'schema':1,'enabled':False,'start':1320,'end':360,'days':list(range(7)),'rate':0,'playingRate':0}
def validate(p):
    if not isinstance(p,dict) or type(p.get('enabled')) is not bool:raise ValueError('Invalid schedule')
    for key in ('start','end'):
        if type(p.get(key)) is not int or not 0<=p[key]<1440:raise ValueError('Invalid time')
    if p['enabled'] and p['start']==p['end']:raise ValueError('Start and end must differ')
    days=p.get('days')
    if not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<7 for d in days) or len(set(days))!=len(days):raise ValueError('Invalid weekdays')
    for key in ('rate','playingRate'):
        if type(p.get(key)) is not int or p[key]!=0 and not 65536<=p[key]<=33554432:raise ValueError('Invalid rate')
    return {'schema':1,**{k:p[k] for k in ('enabled','start','end','rate','playingRate')},'days':list(days)}
class Policy:
    def __init__(self,path=None,clock=time.monotonic):
        self.path=Path(path) if path else None;self.clock=clock;self.lock=threading.Lock();self.value=validate(DEFAULT);self.playing=None;self.updated=None
        if self.path and self.path.exists():
            try:
                with self.path.open('rb') as source:data=source.read(4097)
                if len(data)>4096:raise ValueError('Large schedule')
                self.value=validate(json.loads(data))
            except (OSError,ValueError,TypeError):pass
    def save(self,value):
        value=validate(value)
        with self.lock:
            if self.path:
                self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.new')
                with temp.open('w',encoding='utf8') as dest:json.dump(value,dest);dest.flush();os.fsync(dest.fileno())
                os.replace(temp,self.path)
            self.value=value
        return {'accepted':True}
    def mark_playing(self,playing):
        if type(playing) is not bool:raise ValueError('Gaming state must be boolean')
        with self.lock:self.playing=playing;self.updated=self.clock()
    def rate(self):
        with self.lock:
            limits=[self.value['rate']]
            if self.updated is None or self.clock()-self.updated>10 or self.playing:limits.append(self.value['playingRate'])
        return min((n for n in limits if n),default=0)
    def allow_start(self,now=None):
        now=now or datetime.datetime.now(datetime.timezone.utc)
        if now.tzinfo is None:raise ValueError('UTC-aware clock required')
        now=now.astimezone(datetime.timezone.utc)
        with self.lock:p=dict(self.value)
        if not p['enabled']:return True
        day=now.weekday();minute=now.hour*60+now.minute
        if p['start']<p['end']:return day in p['days'] and p['start']<=minute<p['end']
        return day in p['days'] if minute>=p['start'] else minute<p['end'] and (day-1)%7 in p['days']
class RateLimiter:
    def __init__(self,rate,clock=time.monotonic,sleep=time.sleep):
        self.rate=rate;self.clock=clock;self.sleep=sleep;self.last=clock();self.tokens=None
    def charge(self,size,cancelled=lambda:False):
        if type(size) is not int or size<0:raise ValueError('Invalid byte count')
        rate=self.rate()
        if not rate:self.tokens=None;self.last=self.clock();return
        burst=min(rate*.25,262144);now=self.clock()
        self.tokens=burst if self.tokens is None else min(burst,self.tokens+max(0,now-self.last)*rate)
        self.last=now;self.tokens-=size
        while self.tokens < -0.000001:
            if cancelled():raise InterruptedError('Cancelled')
            rate=self.rate()
            if not rate:self.tokens=None;return
            self.sleep(min(.1,-self.tokens/rate));now=self.clock();self.tokens=min(min(rate*.25,262144),self.tokens+max(0,now-self.last)*rate);self.last=now
