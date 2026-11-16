"""OMNI_DL_LIBRARY_V1: the real worker with a filled Saved folder, for test-library.cjs.
Usage: serve_library_worker.py PORT   (prints "ready <port> <tmp>"; delete <tmp> afterwards)"""
import math, os, struct, sys, tempfile, time, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import worker

tmp = Path(tempfile.mkdtemp(prefix='dl-library-ui-'))
saved = tmp / 'Saved'
(saved / 'Music').mkdir(parents=True)
(saved / 'Batch').mkdir()
now = int(time.time())


def stamp(path, age):
    os.utime(path, (now - age, now - age))


# 30 s of quiet tone: a real file the browser can play and seek in.
with wave.open(str(saved / 'Music' / 'Tone.wav'), 'wb') as out:
    out.setnchannels(1); out.setsampwidth(1); out.setframerate(8000)
    out.writeframes(bytes(int(128 + 20 * math.sin(i * 2 * math.pi * 440 / 8000)) for i in range(8000 * 30)))
stamp(saved / 'Music' / 'Tone.wav', 10)
# 1x1 PNG
png = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6360f8cf000000030101005e2bd5f20000000049454e44ae426082')
(saved / 'Picture.png').write_bytes(png); stamp(saved / 'Picture.png', 20)
(saved / 'Clip.mp4').write_bytes(b'\0' * 2048); stamp(saved / 'Clip.mp4', 5)
(saved / 'Archive.zip').write_bytes(b'PK\5\6' + b'\0' * 18); stamp(saved / 'Archive.zip', 30)
for n in range(52):
    path = saved / 'Batch' / ('Part %02d.bin' % n)
    path.write_bytes(b'x' * (n + 1)); stamp(path, 1000 + n)
(saved / '.omni-work').mkdir()
(saved / '.omni-work' / 'Hidden.mp4').write_bytes(b'h')

server = worker.make_server(int(sys.argv[1]), tmp, tmp / 'history.json')
server.jobs.set_paused(True)
with server.jobs.lock:
    server.jobs.jobs['ab' * 8] = dict(id='ab' * 8, url='https://example.com/tone.wav', demo=False, audio=True, state='completed',
                                      progress=100, title='A finished tone', error='', engine='ytdlp', engine_requested='ytdlp',
                                      filepath=str(saved / 'Music' / 'Tone.wav'), note='Downloaded by yt-dlp.')
print('ready', server.server_port, tmp, flush=True)
server.serve_forever()
