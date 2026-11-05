"""Command-line mode (also used by the automated tests). The window (gui.py) is the default.

  --cli scan
  --cli check   --ip <ps5>
  --cli list    --ip <ps5>                     installed apps, versions and available updates
  --cli install --ip <ps5> --apps omni,downloads,files-broker,master-control [--autoload master-control] [--start master-control]
  --cli repair  --ip <ps5> --app master-control
  --cli uninstall --ip <ps5> --app master-control
  --cli status  --ip <ps5>                     what Bloom Core reports (status.json), with reasons
  --cli jd-setup --ip <ps5> [--jd-folder <JDownloader 2 folder>]   engine + your JDownloader 2 + console check
"""
import argparse
import json
import sys

from . import checks, config, installer, jd, ps5, release


def _console(a):
    return ps5.Console(a.ip, ftp_port=a.ftp_port, loader_port=a.loader_port, websrv_port=a.websrv_port,
                       launcher_port=a.launcher_port)


def _catalog(a, log):
    if a.package:
        return release.Catalog([release.Package(p) for p in a.package])
    return release.load_catalog(online=not a.offline, api_base=a.api, log=log)


def _csv(text):
    return [x for x in (text or "").split(",") if x]


def main(argv=None):
    p = argparse.ArgumentParser(prog="omnibloom-setup", description=config.APP_NAME)
    p.add_argument("command", choices=["scan", "check", "list", "install", "repair", "uninstall", "status", "jd-detect", "jd-setup", "jd-copy"])
    p.add_argument("--ip")
    p.add_argument("--ftp-port", type=int, default=config.FTP_PORT)
    p.add_argument("--loader-port", type=int, default=config.LOADER_PORT)
    p.add_argument("--websrv-port", type=int, default=config.WEBSRV_PORT)
    p.add_argument("--launcher-port", type=int, default=config.LAUNCHER_PORT)
    p.add_argument("--package", action="append", help="a package zip to use (repeatable); default: next to Setup, then GitHub")
    p.add_argument("--offline", action="store_true", help="don't download; only use packages next to Setup")
    p.add_argument("--api", default=config.GITHUB_API)
    p.add_argument("--apps", default="omni,downloads,files-broker,master-control")
    p.add_argument("--app")
    p.add_argument("--autoload", default="", help="apps to start automatically at boot (comma list)")
    p.add_argument("--start", default="", help="apps to start now (comma list)")
    p.add_argument("--quick", action="store_true", help="skip the 18 s ShadowMountPlus activity check")
    p.add_argument("--jd-folder")
    p.add_argument("--network", action="append", help="subnet to scan, e.g. 192.168.0.0/24")
    a = p.parse_args(argv)
    log = lambda m: print(m, flush=True)

    if a.command == "scan":
        import ipaddress
        nets = [ipaddress.ip_network(n, strict=False) for n in a.network] if a.network else None
        found = ps5.scan(nets, ftp_port=a.ftp_port, loader_port=a.loader_port)
        print(json.dumps(found, indent=1))
        return 0 if found else 1
    if a.command == "jd-detect":
        print(json.dumps([jd.summary(f) for f in jd.detect()], indent=1))
        return 0
    if not a.ip:
        p.error("--ip is required for this command")

    with _console(a) as c:
        if a.command == "check":
            items, summary = checks.run_checks(c, quick=a.quick)
            for it in items:
                print("[%s] %s: %s" % (it["status"].upper(), it["label"], it["detail"]))
            return 0 if summary["can_install"] else 2
        if a.command == "uninstall":
            installer.uninstall_app(c, a.app or p.error("--app is required"), log=log)
            return 0
        if a.command == "status":
            status = installer.read_status(c)
            print(json.dumps(status, indent=1))
            for line in installer.explain_status(status):
                log(line)
            return 0 if status else 1
        cat = _catalog(a, log)
        if a.command == "list":
            inst = installer.installed_apps(c)
            ups = installer.updates(c, cat)
            print(json.dumps({"installed": {k: r["version"] for k, r in inst.items()},
                              "available": cat.versions(), "updates": ups}, indent=1))
            return 0
        if a.command == "install":
            items, summary = checks.run_checks(c, quick=a.quick)
            if not summary["can_install"]:
                for it in items:
                    if it["status"] == "bad":
                        log("Can't install yet: %s: %s" % (it["label"], it["detail"]))
                return 2
            installer.install(c, cat, _csv(a.apps), autoload=_csv(a.autoload), start=_csv(a.start), log=log)
            return 0
        if a.command == "repair":
            installer.repair_app(c, cat, a.app or p.error("--app is required"), log=log)
            return 0
        if a.command in ("jd-setup", "jd-copy"):
            if not config.jd_enabled():      # audit JD-03: held back before anything is downloaded or touched
                log(config.JD_HELD_REASON)
                return 3
            folder = a.jd_folder or next(iter(jd.detect()), None)
            if not folder:
                p.error("JDownloader 2 wasn't found on this computer; pass --jd-folder")
            for line in jd.credit_lines():
                log(line)
            release.load_engine(cat, online=not a.offline, api_base=a.api, log=log)
            try:
                jd.setup_jdownloader(c, cat, folder, log=log)
            except jd.CheckFailed as e:
                log("JDownloader 2 wasn't switched on: %s" % e)
                return 3
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
