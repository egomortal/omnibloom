# Test-only stand-in so the real worker accepts a job; any real use fails immediately (no network).
class YoutubeDL:
    def __init__(self, *a, **k): raise RuntimeError('test stand-in: no downloads in tests')
version = type('v', (), {'__version__': '0.test'})
