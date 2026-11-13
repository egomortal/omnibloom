"""OMNI_MEDIA_HEALTH_V2 (2026-11-13): the Media downloads shortcut (LT / double bumper) reported "Media downloads
unavailable" while the worker was running and answering (Bloom Core saw it up; the worker's page opened in a tab).
Omni's native start-up check gave /healthz only 800 ms and treated any slow or failed answer (not a refusal) as
final. The Python worker can take longer than that to answer when the console has it paged down in the background.
Now: up to 4 s per health request, and a slow/failed answer is retried within the existing 30 s window (still no
launch unless the port refuses: a port someone else owns is still left alone)."""
import sys
p = sys.argv[1]
b = open(p, 'rb').read(); nl = b'\r\n' if b'\r\n' in b else b'\n'
s = b.decode('utf-8'); NL = nl.decode()

def rep(a, c):
    global s
    a = a.replace('\n', NL); c = c.replace('\n', NL)
    if s.count(a) != 1: sys.exit('anchor count %d: %r' % (s.count(a), a[:70]))
    s = s.replace(a, c, 1)

rep('''    HttpResult health = hooks.fetch(workerPort, "/healthz", 800);
    if (healthy(health)) { if (readyPort) *readyPort = workerPort; return Outcome::Ready; }
    // Only connection refusal establishes an unused listener. Any other owner/failure is left alone.
    if (health.state != HttpState::Refused) return Outcome::Unavailable;''',
'''    HttpResult health = hooks.fetch(workerPort, "/healthz", 4000); // OMNI_MEDIA_HEALTH_V2: was 800 ms
    if (healthy(health)) { if (readyPort) *readyPort = workerPort; return Outcome::Ready; }
    // OMNI_MEDIA_HEALTH_V2: a slow or failed answer (not a refusal, not a wrong one) is retried for up to 30 s; the
    // worker can be slow to answer while the console has it paged down in the background.
    if (health.state != HttpState::Refused && health.state != HttpState::Complete) {
        const uint64_t retryUntil = hooks.clock() + 30000;
        while (hooks.clock() < retryUntil && health.state != HttpState::Refused && health.state != HttpState::Complete) {
            hooks.sleep(500);
            health = hooks.fetch(workerPort, "/healthz", 4000);
            if (healthy(health)) { if (readyPort) *readyPort = workerPort; return Outcome::Ready; }
        }
    }
    // Only connection refusal establishes an unused listener. Any other owner/failure is left alone.
    if (health.state != HttpState::Refused) return Outcome::Unavailable;''')
rep('''    do {
        health = hooks.fetch(workerPort, "/healthz", 800);''', '''    do {
        health = hooks.fetch(workerPort, "/healthz", 4000); // OMNI_MEDIA_HEALTH_V2: was 800 ms''')
open(p, 'wb').write(s.encode('utf-8'))
print('applied OMNI_MEDIA_HEALTH_V2 (2 anchors)')
