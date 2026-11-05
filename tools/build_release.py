#!/usr/bin/env python3
"""Validate PC/UI source, archive source, package Setup for the host OS, or write release provenance.
No engine build, fetch, installation or console contact. GPL-3.0-or-later.
"""
import argparse, ast, hashlib, json, re, subprocess, sys, zipfile, os, tempfile
from pathlib import Path, PurePosixPath
MANIFEST = 'SOURCE-MANIFEST.json'
RELEASE_MANIFEST = 'RELEASE-MANIFEST.json'   # read by Setup before it installs a package (audit RL-01)
SUMS = 'SHA256SUMS'
ASSET_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\Z')
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
def release_assets(root, folder, tag, commit=None):
    """Write <asset>.sha256, SHA256SUMS and RELEASE-MANIFEST.json for the finished assets in `folder`,
    tied to this verified source tree. Nothing existing is overwritten (audit RL-01)."""
    manifest = verify(root)
    folder = Path(folder).resolve()
    if not folder.is_dir() or folder.is_symlink(): raise ValueError('Release asset folder not found')
    if not re.fullmatch(r'v?[0-9][0-9A-Za-z.+-]{0,63}', tag or ''): raise ValueError('Bad release tag')
    if commit is not None and not re.fullmatch(r'[0-9a-f]{40}', commit): raise ValueError('Bad commit id')
    for name in (RELEASE_MANIFEST, SUMS):
        if (folder/name).exists(): raise ValueError(name+' already exists; use a fresh asset folder')
    rows = []
    for item in sorted(folder.iterdir()):
        if item.name.endswith('.sha256'): continue
        if item.is_symlink() or not item.is_file() or not ASSET_NAME.fullmatch(item.name): raise ValueError('Unsafe release asset: '+item.name)
        raw = item.read_bytes()
        rows.append({'name':item.name,'bytes':len(raw),'sha256':sha(raw)})
    if not rows: raise ValueError('No release assets')
    for row in rows:   # an existing checksum file must agree; a missing one is written
        side = folder/(row['name']+'.sha256'); line = '%s  %s\n' % (row['sha256'], row['name'])
        if side.exists():
            if side.is_symlink() or side.read_text(encoding='ascii').split() != line.split(): raise ValueError('Checksum file disagrees: '+side.name)
        else:
            with open(side, 'x', encoding='ascii', newline='\n') as f: f.write(line)
    source_sha = sha((root/MANIFEST).read_bytes())
    release = {'schema':'omnibloom-release-manifest/v1','tag':tag,
               'source':{'commit':commit,'sourceManifestSha256':source_sha,'sourceFiles':len(manifest['files'])},
               'assets':rows,'releaseApproved':False}
    with open(folder/SUMS, 'x', encoding='ascii', newline='\n') as f:
        f.writelines('%s  %s\n' % (r['sha256'], r['name']) for r in rows)
    with open(folder/RELEASE_MANIFEST, 'x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(release, indent=2)+'\n')
    return {'releaseManifest':str(folder/RELEASE_MANIFEST),'assets':len(rows),'sourceManifestSha256':source_sha}
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
    group.add_argument('--release-assets',type=Path,help='Write checksums and RELEASE-MANIFEST.json for the finished assets in this folder')
    parser.add_argument('--tag',help='Release tag, with --release-assets')
    parser.add_argument('--commit',help='Source commit (40 hex), with --release-assets')
    args = parser.parse_args(argv)
    try:
        root=args.root.resolve(); manifest=verify(root)
        result={'checkedFiles':len(manifest['files']),'sourceVerified':True,'releaseApproved':False}
        if args.release_assets:
            if root == args.release_assets.resolve() or args.release_assets.resolve().is_relative_to(root): raise ValueError('Asset folder must be outside source tree')
            result.update(release_assets(root,args.release_assets,args.tag,args.commit))
        elif args.source_zip:
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
