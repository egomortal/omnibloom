"""Omnibloom Setup entry point (this is what PyInstaller turns into the one-file app).

  Omnibloom-Setup            opens the setup window
  Omnibloom-Setup --cli ...  command-line mode (see omnibloom_setup/cli.py)
  python run_setup.py --fake-console   developer test: a fake PS5 on this computer (needs pyftpdlib)
"""
import os
import sys

if getattr(sys, "frozen", False):
    sys.path.insert(0, getattr(sys, "_MEIPASS", ""))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def fake_console_mode():
    import tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))
    from test_end_to_end import make_packages, new_console
    from omnibloom_setup import gui, release

    tmp = tempfile.mkdtemp(prefix="omnibloom-fake-")
    fc = new_console(os.path.join(tmp, "console"))
    zips, _ = make_packages(tmp)
    os.chdir(os.path.dirname(zips[0]))  # Setup picks up the packages next to it
    load = release.load_catalog
    release.load_catalog = lambda **kw: load(online=False)
    print("Fake PS5 at 127.0.0.1 (FTP %d, loader %d); files in %s" % (fc.ftp_port, fc.loader_port, fc.root))
    gui.main(test_ports={"ftp": fc.ftp_port, "loader": fc.loader_port, "websrv": fc.websrv_port, "host": "127.0.0.1"})


def _cli_output():
    """The windowed exe has no console: attach to the one it was started from, or log to a file."""
    if sys.stdout is not None:
        return
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                return
        except Exception:
            pass
    from omnibloom_setup.release import cache_dir
    sys.stdout = sys.stderr = open(os.path.join(cache_dir(), "setup-cli.log"), "a", encoding="utf-8")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--cli"]:
        _cli_output()
        from omnibloom_setup import cli
        sys.exit(cli.main(args[1:]))
    if args[:1] == ["--fake-console"]:
        fake_console_mode()
        return
    from omnibloom_setup import gui
    gui.main()


if __name__ == "__main__":
    main()
