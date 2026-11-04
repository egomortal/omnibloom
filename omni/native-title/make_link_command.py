#!/usr/bin/env python3
"""omni-native-s1: the in-tree OmniEngine link command (ninja -t commands) as {cwd, command}, like baseline/DL1/build/link-command.json."""
import json, shlex, subprocess, sys
BD = '/home/builder/s1/build'
import os
# the link's response file is deleted after a successful link: relink once with -d keeprsp to keep it
if not any(f.endswith('.rsp') for f in os.listdir(BD + '/CMakeFiles')) :
    if os.path.exists(BD + '/bin/OmniEngine'): os.rename(BD + '/bin/OmniEngine', BD + '/bin/OmniEngine.prev')
    r = subprocess.run(['ninja', '-C', BD, '-d', 'keeprsp', 'OmniEngine'], capture_output=True, text=True)
    print('relink with keeprsp:', r.returncode, r.stdout[-300:])
lines = subprocess.run(['ninja', '-C', BD, '-t', 'commands', 'OmniEngine'], capture_output=True, text=True, check=True).stdout.splitlines()
line = lines[-1]
cwd = BD
parts = [p.strip() for p in line.split(' && ')]
parts = [p for p in parts if p and p != ':']
cmd = None
for p in parts:
    if p.startswith('cd '): cwd = shlex.split(p)[1]; continue
    if 'bin/OmniEngine' in p: cmd = shlex.split(p)
if not cmd: sys.exit('no link command found: ' + line[:300])
exp = []
for a in cmd:
    if a.startswith('@'):
        rsp = a[1:] if a[1:].startswith('/') else os.path.join(cwd, a[1:])
        exp += shlex.split(open(rsp).read())
        print('expanded', rsp)
    else: exp.append(a)
cmd = exp
json.dump({'cwd': cwd, 'command': cmd}, open('/home/builder/s1/link-command.json', 'w'), indent=0)
wl = sorted({a for a in cmd if a.startswith('-Wl,')})
print(f'cwd {cwd}; {len(cmd)} args; {sum(a.endswith(".o") for a in cmd)} .o, {sum(a.endswith(".a") for a in cmd)} .a, {sum(a.startswith("-l") for a in cmd)} -l')
print('driver', cmd[0]); print('-Wl flags', wl[:40])
print('archives', [a for a in cmd if a.endswith('.a')])
print('-l', [a for a in cmd if a.startswith('-l')])
print('other flags', sorted({a for a in cmd if a.startswith('-') and not a.startswith(('-Wl,', '-l'))})[:60])
