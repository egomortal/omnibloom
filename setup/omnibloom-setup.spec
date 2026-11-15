# PyInstaller spec: one file, no console window.   pyinstaller omnibloom-setup.spec
import sys

a = Analysis(
    ["run_setup.py"],
    pathex=["."],
    datas=[("assets/omnibloom-256.png", "assets"), ("assets/omnibloom.ico", "assets")]
    # uBlock's rule files for Omni (installer.ensure_omni_ublock_files)
    + [("../omni/engine/resources/" + n, "assets/ublock")
       for n in ("ublock-engine.js", "ublock-compiled.txt", "public-suffix-list.dat", "ublock-popup-rules.txt")],
    hiddenimports=[],
    excludes=["pyftpdlib", "PIL", "unittest", "pydoc"],   # test-only, not shipped
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Omnibloom-Setup",
    console=False,
    icon="assets/omnibloom.ico",
    upx=False,
)
if sys.platform == "darwin":
    app = BUNDLE(exe, name="Omnibloom Setup.app", icon="assets/omnibloom-256.png", bundle_identifier="org.omnibloom.setup")
