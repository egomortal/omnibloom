#!/usr/bin/env python3
"""Plan an isolated MSE configure; --configure executes after review. Never builds."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

WORK = Path('/opt/omni-build')
PRODUCTION = WORK / 'build-webkit'
EXPERIMENT = WORK / 'build-webkit-mse'
EXPLICIT = {
    'PORT', 'DEBUG_FISSION', 'DEVELOPER_MODE', 'ICU_ROOT',
    'MEMORY_EXTRA_INCLUDE_DIR', 'MEMORY_EXTRA_LIB', 'WEBKIT_LIBRARIES_DIR',
    'CMAKE_TOOLCHAIN_FILE', 'CMAKE_FIND_ROOT_PATH', 'CMAKE_PREFIX_PATH',
    'CMAKE_BUILD_TYPE', 'CMAKE_CXX_STANDARD_LIBRARIES', 'CMAKE_VERBOSE_MAKEFILE',
}


def read_cache(path):
    entries = {}
    for line in path.read_text().splitlines():
        match = re.match(r'^([^#/:][^:]*):([^=]+)=(.*)$', line)
        if match:
            entries[match[1]] = (match[2], match[3])
    return entries


def derive(entries):
    options = {}
    for key, (kind, value) in entries.items():
        if kind in ('INTERNAL', 'STATIC'):
            continue
        if (key in EXPLICIT or key.startswith(('ENABLE_', 'USE_', 'OMNI_'))
                or re.fullmatch(r'CMAKE_(C|CXX)_FLAGS(?:_[A-Z]+)?', key)):
            if str(PRODUCTION) in value:
                raise ValueError('Production build path embedded in option: ' + key)
            options[key] = (kind if kind != 'UNINITIALIZED' else 'STRING', value)
    for key, value in {'ENABLE_MEDIA_SOURCE': 'ON',
                       'ENABLE_MEDIA_SOURCE_IN_WORKERS': 'OFF',
                       'USE_GSTREAMER': 'OFF'}.items():
        options[key] = ('BOOL', value)
    return options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true', help='Execute isolated configure after reviewing default plan')
    args = parser.parse_args()
    cache = PRODUCTION / 'CMakeCache.txt'
    original = cache.read_bytes()
    entries = read_cache(cache)
    assert entries['ENABLE_MEDIA_SOURCE'][1] == 'OFF', 'Production MSE must remain OFF'
    assert entries['CMAKE_GENERATOR'][1] == 'Ninja'
    source = Path(entries['CMAKE_HOME_DIRECTORY'][1]).resolve()
    engine = Path(entries['OMNI_ENGINE_DIR'][1]).resolve()
    assert source == (WORK / 'webkit').resolve()
    assert engine == (WORK / 'omni-browser/engine').resolve()
    assert EXPERIMENT.resolve() == WORK / 'build-webkit-mse', 'Refuse symlink/path redirection'
    assert not EXPERIMENT.exists(), 'Use a NEW empty experiment path; no automatic deletion/reconfigure'
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    lock = json.loads((engine / 'build-lock.json').read_text())
    assert revision == lock['webkit']['commit'], 'Pinned WebKit revision mismatch'
    options = derive(entries)
    command = ['cmake', '-S', str(source), '-B', str(EXPERIMENT), '-G', 'Ninja']
    command += [f'-D{key}:{kind}={value}' for key, (kind, value) in sorted(options.items())]
    plan = {'production_cache_sha256': hashlib.sha256(original).hexdigest(),
            'source_revision': revision, 'source': str(source), 'engine': str(engine),
            'experiment': str(EXPERIMENT), 'command': command,
            'changes': {'ENABLE_MEDIA_SOURCE': 'ON', 'ENABLE_MEDIA_SOURCE_IN_WORKERS': 'OFF', 'USE_GSTREAMER': 'OFF'}}
    print(json.dumps(plan, indent=2), flush=True)
    if not args.configure:
        return
    # WSL virtual free space alone does not establish physical host capacity.
    for path in (WORK, Path('/mnt/c')):
        assert shutil.disk_usage(path).free >= 20 * 1024**3, f'Need 20 GiB free on {path}; configure/build headroom guard'
    try:
        subprocess.run(command, check=True)
        actual = read_cache(EXPERIMENT / 'CMakeCache.txt')
        for key, value in plan['changes'].items():
            assert actual[key][1] == value, f'Experimental {key} not honored'
        (EXPERIMENT / 'omni-mse-configure-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    finally:
        assert cache.read_bytes() == original, 'Production cache changed unexpectedly'
    print('Isolated configure only completed; no build or deployment performed.')


if __name__ == '__main__':
    main()
