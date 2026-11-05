# SPDX-License-Identifier: GPL-3.0-or-later
"""Downloads service's own card and runtime metadata. Never launches an app."""
import json
import os
from pathlib import Path
import time

CARD = Path('/data/hub/apps/downloads.json')
RUNTIME = Path('/data/hub/runtime/downloads.json')


def read_port(path=CARD):
    with Path(path).open('rb') as stream:
        data = stream.read(32769)
    if len(data) > 32768:
        raise ValueError('Downloads card is too large')
    card = json.loads(data)
    if not isinstance(card, dict) or card.get('id') != 'downloads' or card.get('hub_api') != 1:
        raise ValueError('Downloads card is unavailable')
    port = card.get('port')
    if type(port) is not int or not 8761 <= port <= 8899:
        raise ValueError('Downloads card needs an assigned suite port')
    return port


def publish(port, path=RUNTIME, pid=None, started_at=None):
    if type(port) is not int or not 8761 <= port <= 8899:
        raise ValueError('Downloads runtime port is outside the suite range')
    pid = os.getpid() if pid is None else pid
    if type(pid) is not int or pid <= 0:
        raise ValueError('Downloads runtime PID is invalid')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + str(pid) + '.new')
    record = dict(id='downloads', host='127.0.0.1', port=port, pid=pid,
                  started_at=int(time.time()) if started_at is None else started_at)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def remove(path=RUNTIME, pid=None):
    pid = os.getpid() if pid is None else pid
    path = Path(path)
    try:
        with path.open('rb') as stream:
            data = stream.read(4097)
        if len(data) > 4096:
            return
        record = json.loads(data)
        if isinstance(record, dict) and record.get('id') == 'downloads' and record.get('pid') == pid:
            path.unlink()
    except (OSError, ValueError, UnicodeError):
        pass
