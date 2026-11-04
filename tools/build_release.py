#!/usr/bin/env python3
"""Validate PC/UI source, archive source, or package Setup for the host OS.
No engine build, fetch, installation or console contact. GPL-3.0-or-later.
"""
import argparse, ast, hashlib, json, subprocess, sys, zipfile, os, tempfile
from pathlib import Path, PurePosixPath
MANIFEST = 'SOURCE-MANIFEST.json'
def sha(data): return hashlib.sha256(data).hexdigest()
def source_files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and not {'.git', '__pycache__'}.intersection(p.relative_to(root).parts) and p.relative_to(root).as_posix() != MANIFEST)
def verify(root):
    root = Path(root).resolve()
    data = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('files'), list): raise ValueError('Invalid manifest')
    expected = {}
    for row in data['files']:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str): raise ValueError('Invalid record')
        rel = PurePosixPath(row['path'])
        if not row['path'] or rel.as_posix() != row['path'] or rel.is_absolute() or '..' in rel.parts or '\\' in row['path'] or ':' in row['path'] or row['path'] in expected or row['path'] == MANIFEST: raise ValueError('Unsafe or duplicate path')
        file = root / rel
        if not file.is_file() or any(x.is_symlink() for x in [file, *file.parents] if x.is_relative_to(root)): raise ValueError('Missing file or symbolic link: ' + row['path'])
        raw = file.read_bytes()
        if sha(raw) != row.get('sha256') or len(raw) != row.get('bytes'): raise ValueError('Changed input: ' + row['path'])
        if file.suffix == '.py': ast.parse(raw.decode('utf-8-sig'), filename=row['path'])
        if file.suffix == '.json': json.loads(raw.decode('utf-8-sig'))
        expected[row['path']] = row
    actual = {p.relative_to(root).as_posix() for p in source_files(root)}
    if actual != set(expected): raise ValueError('Unlisted files: ' + ', '.join(sorted(actual-set(expected))[:8]))
    return data
def output_path(root, value):
    out = Path(value).expanduser().resolve()
    if out == root or out.is_relative_to(root) or root.is_relative_to(out): raise ValueError('Output must be outside source tree')
    if out.exists(): raise ValueError('Output exists; choose a fresh path')
    return out
def source_zip(root, out, manifest):
    expected = {x['path']:x for x in manifest['files']}
    paths = sorted(list(expected) + [MANIFEST])
    fd, name = tempfile.mkstemp(prefix='.'+out.name+'.', suffix='.partial', dir=out.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for rel in paths:
                    raw=(root/rel).read_bytes()
                    if rel == MANIFEST:
                        if json.loads(raw) != manifest: raise ValueError('Manifest changed during archive')
                    elif sha(raw) != expected[rel]['sha256']: raise ValueError('Source changed during archive: '+rel)
                    item = zipfile.ZipInfo(rel, date_time=(1980,1,1,0,0,0))
                    item.create_system = 3; item.external_attr = (0o100755 if raw.startswith(b'#!') else 0o100644) << 16
                    archive.writestr(item, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            stream.flush(); os.fsync(stream.fileno())
        digest=sha(temporary.read_bytes())
        # Windows rename refuses an existing destination; POSIX link supplies the same exclusive publication.
        # There is no replace/overwrite fallback.
        if os.name == 'nt': os.rename(temporary, out)
        else: os.link(temporary, out)
        return {'sha256':digest, 'members':len(paths), 'kind':'source-only', 'releaseApproved':False}
    finally:
        temporary.unlink(missing_ok=True)
def setup_plan(root, out):
    for rel in ('run_setup.py','omnibloom-setup.spec','assets/omnibloom-256.png','assets/omnibloom.ico'):
        if not (root/'setup'/rel).is_file(): raise ValueError('Missing Setup input: '+rel)
    return [sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(out/'dist'),'--workpath',str(out/'work'),'omnibloom-setup.spec']
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--source-zip',type=Path)
    group.add_argument('--setup',type=Path,help='Package Setup into a fresh external directory using already-installed PyInstaller')
    args = parser.parse_args(argv)
    try:
        root=args.root.resolve(); manifest=verify(root)
        result={'checkedFiles':len(manifest['files']),'sourceVerified':True,'releaseApproved':False}
        if args.source_zip:
            out=output_path(root,args.source_zip)
            if not out.parent.is_dir(): raise ValueError('Create output parent directory first')
            result.update(source_zip(root,out,manifest))
        elif args.setup:
            out=output_path(root,args.setup); command=setup_plan(root,out)
            subprocess.run([sys.executable,'-m','PyInstaller','--version'],check=True,capture_output=True,text=True)
            out.mkdir(parents=True); subprocess.run(command,cwd=root/'setup',check=True)
            files=[p for p in (out/'dist').rglob('*') if p.is_file()] if (out/'dist').exists() else []
            if not files: raise ValueError('Packager returned without an artifact')
            result['setupArtifacts']=[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(files)]
            verify(root)
            result['runtimeTested']=False
        print(json.dumps(result,indent=2)); return 0
    except (ValueError,OSError,SyntaxError,subprocess.CalledProcessError,zipfile.BadZipFile) as error:
        print('BUILD STOPPED: '+str(error),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
