"""Stub of the omni-media-worker HTTP surface for GUI testing.
Serves the GUI files with the same allowlist (ASSETS parsed from the package's worker.py),
the same security headers/CSP, token substitution, and an in-memory fake API."""
import ast, json, os, re, sys, secrets, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); WORKER = Path(sys.argv[2]); PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8765
src = WORKER.read_text(encoding='utf-8')
m = re.search(r"ASSETS = (\{.*?\})\n", src, re.S); ASSETS = ast.literal_eval(m.group(1))
TOKEN = secrets.token_urlsafe(24)
PROBE = os.environ.get('STUB_PROBE') == '1'  # downloader-5: worker link checks on
SEEN_DEEP = {}
def V(h, fps, bw, dur, w=None):
    return dict(width=w or h * 16 // 9, height=h, fps=fps, vcodec='H.264', acodec='AAC', bandwidth=bw, size=int(bw * dur / 8))
def fake_probe(url, deep):
    base = dict(ok=False, message='', kind=None, container=None, duration=None, size=None, size_estimated=False, video=None,
                audio=None, variants=[], audio_tracks=[], subtitles=[], encrypted='none', source='parse', title=None)
    if 'drm' in url:
        return dict(base, status='protected', message="Protected stream (DRM). It can't be downloaded.", kind='hls', encrypted='drm')
    if 'gone' in url:
        return dict(base, status='dead', message='Dead link: the file is gone.')
    if deep:
        SEEN_DEEP[url] = SEEN_DEEP.get(url, 0) + 1
        if SEEN_DEEP[url] == 1:
            return dict(base, status='slow', message='Still checking the site. This can take a moment.', kind='page', source='yt-dlp')
        vs = [V(1080, 30, 4500000, 634.5), V(720, 30, 2500000, 634.5)]
        return dict(base, status='ok', ok=True, kind='page', container='Generic', source='yt-dlp', duration=634.5, variants=vs,
                    size=vs[0]['size'], size_estimated=True, video=dict(width=1920, height=1080, fps=30, vcodec='H.264'), audio=dict(codec='AAC'),
                    audio_tracks=[dict(lang='en', name='', codec='AAC', default=False)], title='Big Buck Bunny')
    if url.endswith('x36xhzz.m3u8'):
        vs = [V(1080, 60, 5000000, 634.5), V(720, 30, 2800000, 634.5), V(480, None, 1100000, 634.5, 854)]
        return dict(base, status='ok', ok=True, kind='hls', container='HLS', duration=634.5, variants=vs, size=vs[0]['size'],
                    size_estimated=True, video=dict(width=1920, height=1080, fps=60, vcodec='H.264'), audio=dict(codec='AAC'),
                    audio_tracks=[dict(lang='en', name='English', codec='AAC', default=True), dict(lang='es', name='Español', codec='AAC', default=False)],
                    subtitles=[dict(lang='en', name='English')])
    if url.endswith('.m3u8'):
        return dict(base, status='ok', ok=True, kind='hls', container='HLS', duration=634.5)
    return dict(base, status='ok', ok=True, kind='file', container='MP4', size=245000000, duration=192.0,
                video=dict(width=1920, height=1080, fps=None, vcodec='H.264'), audio=dict(codec='AAC'))
LOCK = threading.Lock()
STATE = dict(jobs=[], links=[], paused=False)
def hexid(n=16): return secrets.token_hex(n // 2)
STATE['links'] = [dict(id=hexid(), url=u, created_at=int(time.time()) - i) for i, u in enumerate([
    'https://example.com/video-one.mp4', 'https://example.org/some/page', 'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8'])]
STATE['jobs'] = [dict(id=hexid(), state='completed', engine='ytdlp', demo=False, audio=False, url='https://developer.mozilla.org/shared-assets/videos/flower.mp4', title='flower.mp4', error='', progress=100, filepath='/data/omni-downloader/downloads/flower.mp4', note='Downloaded by yt-dlp.', engine_requested='ytdlp')]
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
       "frame-ancestors 'self'; base-uri 'none'; object-src 'none'; form-action 'self'")
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_body(self, status, body, ctype):
        self.send_response(status); self.send_header('Content-Type', ctype); self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff'); self.send_header('Content-Length', str(len(body)))
        if ctype.startswith('text/html'): self.send_header('Content-Security-Policy', CSP)
        self.end_headers(); self.wfile.write(body)
    def reply(self, status, value): self.send_body(status, json.dumps(value).encode(), 'application/json')
    def trusted(self): return self.headers.get('X-Omni-Token') == TOKEN
    def status(self):
        return dict(api_version=1, service='omni-media-worker', jobs=STATE['jobs'], ytdlp=True, jdownloader=True,
                    jdownloader_status='Stub JD ready', backend='stub', ffmpeg=True, quickjs=True, folder='/data/omni-downloader/downloads',
                    history_error='', max_pending=8, queue_paused=STATE['paused'], jd_lifecycle=dict(can_start=True, status='stub'),
                    # OMNI_DL_SAVE_V1: places to save (console storage + one USB drive) for the save form tests
                    places=[dict(id='internal', label='Console storage', free_bytes=312_400_000_000, total_bytes=825_000_000_000),
                            dict(id='usb0', label='USB drive 1', free_bytes=900_000_000, total_bytes=64_000_000_000)], save_v1=True,
                    **({'probe': True} if PROBE else {}))
    def do_GET(self):
        if self.path in ('/', '/downloads'):
            body = (ROOT / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN).encode()
            return self.send_body(200, body, 'text/html; charset=utf-8')
        if self.path in ASSETS:
            name, ctype = ASSETS[self.path]; p = ROOT / name
            if not p.is_file(): return self.reply(404, {'error': 'Asset unavailable'})
            return self.send_body(200, p.read_bytes(), ctype)
        if self.path == '/favicon.ico': return self.send_body(204, b'', 'image/x-icon')
        if not self.trusted(): return self.reply(403, {'error': 'Forbidden'})
        with LOCK:
            if self.path == '/api/status': return self.reply(200, self.status())
            if self.path == '/api/saved-links': return self.reply(200, dict(links=STATE['links'], max_links=64, writable=True, persistent=True, error=''))
            if self.path == '/api/_last-job': return self.reply(200, STATE.get('last_job') or {})
        self.reply(404, {'error': 'Not found'})
    def do_POST(self):
        if not self.trusted(): return self.reply(403, {'error': 'Forbidden'})
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/probe':
            if not PROBE: return self.reply(404, {'error': 'Not found'})
            time.sleep(0.25)
            with LOCK: value = fake_probe(body['url'], body.get('deep') is True)
            return self.reply(200, value)
        with LOCK:
            if self.path == '/api/saved-links':
                for l in STATE['links']:
                    if l['url'] == body['url']: return self.reply(200, dict(id=l['id'], created=False, present=True, replayed=False))
                l = dict(id=hexid(), url=body['url'], created_at=int(time.time())); STATE['links'].insert(0, l)
                return self.reply(201, dict(id=l['id'], created=True, present=True, replayed=False))
            if self.path == '/api/saved-links/delete':
                n = len(STATE['links']); STATE['links'] = [l for l in STATE['links'] if l['id'] != body['id']]
                return self.reply(200, dict(removed=len(STATE['links']) < n))
            if self.path == '/api/jobs':
                STATE['last_job'] = body
                j = dict(id=hexid(), state='queued', engine=body.get('engine', 'ytdlp'), demo=body.get('demo', True), audio=body.get('audio', False), url=body['url'], title=body['url'].rsplit('/', 1)[-1] or 'job', error='', progress=0, engine_requested=body.get('engine', 'ytdlp'))
                STATE['jobs'].append(j); return self.reply(201, dict(id=j['id']))
            if self.path == '/api/cancel':
                for j in STATE['jobs']:
                    if j['id'] == body['id']: j['state'] = 'cancelled'
                return self.reply(200, dict(ok=True))
            if self.path == '/api/queue':
                STATE['paused'] = bool(body['paused']); return self.reply(200, dict(queue_paused=STATE['paused']))
            # OMNI_DL_RESUME_V1: pause / resume / retry, with the real worker's rules (simplified: a pause is immediate).
            if self.path in ('/api/jobs/pause', '/api/jobs/resume', '/api/jobs/retry'):
                if set(body) != {'id'}: return self.reply(400, {'error': 'This request requires only id.'})
                j = next((j for j in STATE['jobs'] if j['id'] == body['id']), None)
                if j is None: return self.reply(400, {'error': 'Unknown download.'})
                action = self.path.rsplit('/', 1)[1]
                STATE.setdefault('actions', []).append([action, j['id']])
                if action == 'pause' and j['state'] in ('queued', 'extracting', 'downloading', 'processing'):
                    j.update(state='paused', speed_bps=None, eta_seconds=None)
                elif action in ('resume', 'retry') and j.get('url') and j['state'] in (('failed',) if action == 'retry' else ('paused', 'interrupted', 'failed')):
                    j.update(state='queued', error='', attempt=1 if action == 'retry' else j.get('attempt', 1) + 1, retries=j.get('retries', 0) + (action == 'retry'))
                else:
                    return self.reply(400, {'error': 'Not possible for this download now.'})
                return self.reply(200, dict(ok=True, id=j['id'], state=j['state']))
            if self.path == '/api/_seed-resume':
                # Test hook: one slow running job, one failed job (link kept), one interrupted job (link kept) and an
                # old interrupted record whose link was not kept.
                def job(state, name, **extra):
                    return dict(dict(id=hexid(), state=state, engine='ytdlp', demo=False, audio=False, url='https://example.com/' + name, title=name,
                                     error='', progress=40, engine_requested='ytdlp', downloaded_bytes=560_000_000, total_bytes=1_400_000_000), **extra)
                seeded = [job('downloading', 'running.mp4', slow=True), job('failed', 'broken.mp4', error='Direct download was interrupted.'),
                          job('interrupted', 'stopped.mp4', error='Worker stopped; resume to continue.'),
                          job('interrupted', 'old.mp4', url='', error='Worker stopped; submit the link again.', restored=True)]
                STATE['jobs'] = [j for j in STATE['jobs'] if j['state'] == 'completed'] + seeded
                return self.reply(200, dict(ids={j['title']: j['id'] for j in seeded}))
            if self.path == '/api/_actions':
                return self.reply(200, dict(actions=STATE.get('actions', [])))
        self.reply(404, {'error': 'Not found'})
def tick():
    while True:
        time.sleep(0.5)
        with LOCK:
            for j in STATE['jobs']:
                if j['state'] in ('queued', 'downloading'):
                    j['state'] = 'downloading'; j['progress'] = min(100, (j['progress'] or 0) + (1 if j.get('slow') else 10))
                    # OMNI_DL_SAVE_V1: byte counts as the real worker reports them (video + audio counted together)
                    j['total_bytes'] = 1_400_000_000; j['downloaded_bytes'] = j['total_bytes'] * j['progress'] // 100
                    j['speed_bps'] = 4_200_000; j['eta_seconds'] = (j['total_bytes'] - j['downloaded_bytes']) // j['speed_bps']
                    if j['progress'] >= 100: j['state'] = 'completed'; j['filepath'] = '/data/omni/downloads/media-worker/Saved/' + (j['url'].rsplit('/', 1)[-1] or 'file')
threading.Thread(target=tick, daemon=True).start()
print('ready', PORT, flush=True)
ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
