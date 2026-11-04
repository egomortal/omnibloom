"""Bundled on-console worker entry. Never deploys or discovers consoles."""
import argparse
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / '.deps'))


_detached_output_configured = False


def configure_detached_output():
    """Discard server diagnostics when the loader supplies no output reader.

    Redirect descriptors as well as Python streams: native libraries may write
    directly to fd1/fd2. No URLs, cookies or diagnostics are persisted to a log.
    Self-test mode deliberately does not call this policy.
    """
    global _detached_output_configured
    if _detached_output_configured:
        return
    descriptor = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(descriptor, 1)
        os.dup2(descriptor, 2)
    finally:
        if descriptor not in (1, 2):
            os.close(descriptor)
    # Initial stdout/stderr can be None or closed when the loader detached them.
    sys.stdout = open(1, 'w', encoding='utf-8', errors='backslashreplace', buffering=1, closefd=False)
    sys.stderr = open(2, 'w', encoding='utf-8', errors='backslashreplace', buffering=1, closefd=False)
    sys.__stdout__ = sys.stdout
    sys.__stderr__ = sys.stderr
    _detached_output_configured = True


def _hashlib_self_test():
    # Known-answer fixtures from CPython 3.12.12 Lib/test/test_hashlib.py.
    # SHAKE vectors request 32 output bytes; expected values are never generated
    # by the target implementation being tested.
    vectors = {
        'md5': (b'abc', '900150983cd24fb0d6963f7d28e17f72'),
        'sha1': (b'abc', 'a9993e364706816aba3e25717850c26c9cd0d89d'),
        'sha224': (b'abc', '23097d223405d8228642a477bda255b32aadbce4bda0b3f7e36c9da7'),
        'sha256': (b'abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'),
        'sha384': (b'abc', 'cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed'
                           '8086072ba1e7cc2358baeca134c825a7'),
        'sha512': (b'abc', 'ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a'
                           '2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f'),
        'blake2b': (b'abc', 'ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d1'
                            '7d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923'),
        'blake2s': (b'abc', '508c5e8c327c14e2e1a72ba34eeb452f37458b209ed63a294d999b4c86675982'),
        'sha3_224': (b'', '6b4e03423667dbb73b6e15454f0eb1abd4597f9a1b078e3f5b5a6bc7'),
        'sha3_256': (b'', 'a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a'),
        'sha3_384': (b'', '0c63a75b845e4f7d01107d852e4c2485c51a50aaaa94fc61995e71bbee983a2a'
                          'c3713831264adb47fb6bd1e058d5f004'),
        'sha3_512': (b'', 'a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a6'
                          '15b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26'),
        'shake_128': (b'', '7f9c2ba4e88f827d616045507605853ed73b8093f6efbc88eb1a6eacfa66ef26'),
        'shake_256': (b'', '46b9dd2b0ba88d13233b3feb743eeb243fcd52ea62b81b82b50c27646ed5762f'),
    }
    try:
        import hashlib
    except Exception as error:
        return {'passed': False, 'error': repr(error), 'algorithms': {}}
    guaranteed = set(hashlib.algorithms_guaranteed)
    checks = {}
    # Keep checking the baseline fixtures even if a broken port incorrectly
    # omits a name from algorithms_guaranteed. New untested guarantees fail too.
    for name in sorted(guaranteed | vectors.keys()):
        try:
            data, expected = vectors[name]
            constructor = getattr(hashlib, name)
            direct = constructor(data)
            streamed = constructor()
            midpoint = len(data) // 2
            streamed.update(data[:midpoint])
            streamed = streamed.copy()
            streamed.update(data[midpoint:])
            generic = hashlib.new(name, data)
            args = (32,) if name.startswith('shake_') else ()
            digests = [value.hexdigest(*args) for value in (direct, streamed, generic)]
            checks[name] = {'passed': all(value == expected for value in digests),
                            'digest': digests[0], 'message_bytes': len(data)}
            if not checks[name]['passed']:
                checks[name].update(expected=expected, digests=digests)
        except Exception as error:
            checks[name] = {'passed': False, 'error': repr(error)}
    return {'passed': all(item['passed'] for item in checks.values()),
            'algorithms_guaranteed': sorted(guaranteed), 'algorithms': checks}


def self_test():
    import importlib
    import _omni_native
    report = {'native': True, 'imports': {}, 'network_contacted': False}
    modules = ('ssl', 'hashlib', 'socket', 'select', 'threading', 'zlib', 'bz2', 'lzma',
               'xml.etree.ElementTree', 'concurrent.futures', 'http.server', 'subprocess', 'yt_dlp', 'yt_dlp_ejs')
    for module in modules:
        try:
            importlib.import_module(module)
            report['imports'][module] = True
        except Exception as error:
            report['imports'][module] = str(error)
    report['javascript'] = _omni_native.evaluate('console.log(6*7)') == '42'
    report['hashlib'] = _hashlib_self_test()
    report['passed'] = (report['javascript'] and report['hashlib']['passed']
                        and all(value is True for value in report['imports'].values()))
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--downloads', default='/data/omni/downloads/media-worker')
    parser.add_argument('--state', default='/data/omni-downloader/state/jobs.json')
    parser.add_argument('--jdownloader-ready', default='/data/omni-downloader/jdownloader/bridge-ready.json')
    args = parser.parse_args()
    if args.self_test:
        raise SystemExit(self_test())
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    configure_detached_output()
    os.environ.setdefault('SSL_CERT_FILE', str(root / '.deps/certifi/cacert.pem'))
    from worker import make_server
    from ready_adapter import ReadyFileJDownloaderAdapter
    lifecycle = None
    # Only an explicitly packaged native lifecycle module may request a local
    # native launch. The worker never uses Python subprocess/fork for Java.
    if (root / 'jd_lifecycle.py').is_file():
        try:
            from jd_lifecycle import create_lifecycle
            lifecycle = create_lifecycle(Path(args.downloads), Path(args.jdownloader_ready))
        except Exception:
            lifecycle = None
    server = make_server(args.port, args.downloads, args.state,
                         jd_adapter=ReadyFileJDownloaderAdapter(args.jdownloader_ready),
                         jd_lifecycle=lifecycle)
    try:
        server.serve_forever()
    finally:
        server.server_close()
