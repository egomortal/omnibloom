import hashlib, os, sys
up, rec_path, label = sys.argv[1:4]
rec = {}
for l in open(rec_path):
    x = l.split()
    if x and x[0] == 'same': rec[x[-1]] = x[1]
ok = bad = 0; out = []
for root, dirs, files in os.walk(up):
    rel = os.path.relpath(root, up)
    if rel == 'build' or rel.startswith('build/'): dirs[:] = []; continue
    for f in files:
        p = './' + os.path.normpath(os.path.join(rel, f))
        if os.path.basename(p).startswith('.') or p.endswith('link-command.json'): continue
        h = hashlib.sha256(open(os.path.join(up, p), 'rb').read()).hexdigest()
        if rec.get(p) == h: ok += 1; out.append(f'same {h} {p}')
        else: bad += 1; out.append(f'DIFF {h} {p} (recorded {rec.get(p)})')
for p in rec:
    if not os.path.exists(os.path.join(up, p)): bad += 1; out.append(f'MISSING {p}')
print('\n'.join(sorted(out))); print(f'RESULT {label}: {ok} changed files = the recorded launch text, {bad} not')
sys.exit(1 if bad else 0)
