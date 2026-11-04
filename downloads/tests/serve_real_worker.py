"""Start the real dl6 worker server (no console, temp state) for GUI tool tests. Usage: serve_real_worker.py PORT"""
import sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import worker
tmp = tempfile.mkdtemp()
server = worker.make_server(int(sys.argv[1]), tmp, Path(tmp) / 'history.json')
print('ready', server.server_port, flush=True)
server.serve_forever()
