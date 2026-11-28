# Release process

A release has three kinds of files:

1. **Console packages**: `omnibloom-console-<version>.zip` (and Master Control's, from its own repository).
2. **Setup apps**: one each for Windows, macOS and Linux, built by CI.
3. **Integrity files**: a `.sha256` for each asset, `SHA256SUMS` and `RELEASE-MANIFEST.json`.

The tool for most steps is `tools/build_release.py`. `docs/BUILD.md` has more detail on each mode.

## 1. Keep `SOURCE-MANIFEST.json` current

`SOURCE-MANIFEST.json` lists every file in the repository with its size and SHA-256. `tools/build_release.py`
refuses to verify if any file is missing, changed or unlisted. So **refresh it in every change that adds, removes
or edits a file**, including docs.

Format (check the bytes; it matters):

- JSON with a 2-space indent and **CRLF** line endings, ending in `}` and CRLF.
- Shape: `{"schema": 1, "files": [{"path": ..., "bytes": ..., "sha256": ...}, ...]}`, with keys in that order.
- One row for every file except anything under `.git` or `__pycache__`, and except the manifest itself
  (`source_files` in `tools/build_release.py`).
- Rows are in the order `source_files()` returns on Windows. That is a case-insensitive sort by path part (Python's
  `sorted()` of `PureWindowsPath`).

The tool never writes the manifest (`docs/BUILD.md`). Regenerate it with a few lines of Python from the repository
root:

```python
import hashlib, json
from pathlib import Path, PureWindowsPath

root = Path('.')
skip = {'.git', '__pycache__'}
files = [p for p in root.rglob('*') if p.is_file()
         and not skip.intersection(p.relative_to(root).parts)
         and p.relative_to(root).as_posix() != 'SOURCE-MANIFEST.json']
files.sort(key=lambda p: PureWindowsPath(p.relative_to(root).as_posix()))
rows = [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
text = json.dumps({'schema': 1, 'files': rows}, indent=2)
Path('SOURCE-MANIFEST.json').write_bytes((text + '\n').replace('\n', '\r\n').encode('utf-8'))
```

Then check it:

```sh
python tools/build_release.py
```

Success prints `"sourceVerified": true`. Failure prints `BUILD STOPPED: ...` and exits 2.

Make the manifest refresh its own commit, or the last part of your commit, so a reviewer can see what changed.
Hash files as they are checked out. If git converts line endings on your machine, the hashes will not match.

## 2. Build the console package

`setup/tools/make_package.py` turns a staged copy of the console's folders into a package:

```sh
cd setup
python tools/make_package.py --package omnibloom --stage <folder that mirrors the console's /> --version 0.5.2 --out dist
```

- `--package` is `omnibloom`, `master-control` or `omnibloom-jd-engine`.
- `--app-version id=1.2.3` sets one app's version. `--jd-engine-ready` marks the JD engine package as ready.
- Every staged file must belong to exactly one app's roots (`APPS` in the same file), or the build stops.
- It writes the zip, opens it again with Setup's own checker (`Package(...).verify_all()`) and writes `<zip>.sha256`.

## 3. Optional: a source archive

```sh
python tools/build_release.py --source-zip ../omnibloom-source-<version>.zip
```

The archive is deterministic and holds exactly the listed files plus the manifest. The tool never overwrites an
existing file.

## 4. Write the release checksums and `RELEASE-MANIFEST.json`

Put every finished asset in one new folder **outside** the repository, then run:

```sh
python tools/build_release.py --release-assets ../release-assets --tag v0.5.2 --commit <40-character commit>
```

It verifies the source first, then writes:

- `<asset>.sha256` for each asset (an existing one must agree), one line `<hash>  <name>`;
- `SHA256SUMS`;
- `RELEASE-MANIFEST.json`:

```json
{
  "schema": "omnibloom-release-manifest/v1",
  "tag": "v0.5.2",
  "source": {"commit": "...", "sourceManifestSha256": "...", "sourceFiles": 0},
  "assets": [{"name": "omnibloom-console-0.5.2.zip", "bytes": 0, "sha256": "..."}],
  "releaseApproved": false
}
```

**Upload all of them with the release.** Setup refuses a package unless the manifest, the `.sha256` file and the
download agree (`setup/omnibloom_setup/release.py`, `download_release`). These files prove integrity, not who
published them.

## 5. Setup apps: the CI workflow

`.github/workflows/omnibloom-setup.yml` builds Setup on Windows, macOS and Linux.

**When it runs:**

- when a GitHub release is **published**;
- by hand (**workflow_dispatch**), with an optional `tag` input.

**What each job does:**

1. Installs Python 3.12 and pinned `pyinstaller`, `pyftpdlib` and `pillow`.
2. Runs the fake-console tests (`tests.test_end_to_end`, `tests.test_oneclick`, `tests.test_discovery`).
3. On Linux, runs the window walk-through under xvfb.
4. Builds the one-file app from `setup/omnibloom-setup.spec`.
5. Writes `<asset>.sha256`.
6. On a release, or when `tag` is set, attaches both files to that release (`gh release upload ... --clobber`).
7. Always keeps them as a workflow artifact.

**Re-attach the Setup apps to an existing release.** If the files are missing or need rebuilding, run the
workflow by hand with the tag:

```sh
gh workflow run omnibloom-setup.yml -f tag=v0.5.1
```

With an empty `tag`, it only builds; the files are kept as workflow artifacts.

`setup/ci/github-workflow-omnibloom-setup.yml` is an older copy without the `tag` input. The live workflow is the
one in `.github/workflows/`.

## 6. Notes and checks

- Add a `CHANGELOG.md` entry: `## vX.Y.Z (Month D, YYYY)`, with plain-language bullets that start with a bold
  summary and say how it was proven ("proven on the console", "built").
- Update `KNOWN-ISSUES.md` when a release fixes or adds a known issue.
- The public repository has original art only, and no personal data: no console addresses (use the documentation
  address `192.0.2.10`), no user names, no private e-mail addresses.
- `sourceVerified` is not release approval. A release still needs its console tests.

## Checklist

1. Changes merged; `SOURCE-MANIFEST.json` refreshed; `python tools/build_release.py` passes.
2. Console package built with `make_package.py` and tested on a console.
3. Tag and publish the GitHub release with the package and its `.sha256`.
4. CI attaches the Setup apps (or run the workflow with `tag`).
5. Download every asset into one folder, run `--release-assets`, and upload the `.sha256` files, `SHA256SUMS` and
   `RELEASE-MANIFEST.json`.
6. Try Setup from the release on a clean console, or at least on the fake console.
