# PyInstaller spec: one file, no console window.   pyinstaller omnibloom-setup.spec
import sys

a = Analysis(
    ["run_setup.py"],
    pathex=["."],
    datas=[("assets/omnibloom-256.png", "assets"), ("assets/omnibloom.ico", "assets")],
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
