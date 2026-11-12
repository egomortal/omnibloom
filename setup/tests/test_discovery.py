"""Finding the PS5: every network this computer is on, the payload loader first, FTP second, and websrv's process
list to tell a PS5 from other devices.      python -m unittest tests.test_discovery -v   (from setup/)

Devices on "other networks" are other loopback addresses (127.0.1.1, 127.0.2.1, ...). Where the system only allows
127.0.0.1 (macOS by default) those tests are skipped.
"""
import http.server
import ipaddress
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fake_console import FakeConsole  # noqa: E402
from test_end_to_end import catalog_of, make_packages, new_console  # noqa: E402
from omnibloom_setup import config, oneclick, ps5  # noqa: E402

IPCONFIG = """
Windows IP Configuration

Ethernet adapter Ethernet:

   Connection-specific DNS Suffix  . : home
   IPv4 Address. . . . . . . . . . . : 192.168.50.23(Preferred)
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 192.168.50.1

Wireless LAN adapter Wi-Fi:

   IPv4-Adresse  . . . . . . . . . . : 10.20.30.40
   Subnetzmaske  . . . . . . . . . . : 255.255.255.0

Ethernet adapter Bluetooth Network Connection:

   Autoconfiguration IPv4 Address. . : 169.254.12.34(Preferred)
"""
IP_ADDR = """1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever
2: eth0    inet 192.168.50.23/24 brd 192.168.50.255 scope global dynamic eth0\\       valid_lft 86000sec
3: usb0    inet 172.20.10.5/28 brd 172.20.10.15 scope global usb0\\       valid_lft forever
"""
IFCONFIG = """en0: flags=8863<UP,BROADCAST,RUNNING> mtu 1500
\tinet 192.168.50.23 netmask 0xffffff00 broadcast 192.168.50.255
lo0: flags=8049<UP,LOOPBACK,RUNNING> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
"""


def can_bind(host):
    try:
        s = socket.socket()
        s.bind((host, 0))
        s.close()
        return True
    except OSError:
        return False


MULTI_LOOPBACK = can_bind("127.0.2.1")


def free_ports(n):
    socks = [socket.socket() for _ in range(n)]
    for s in socks:
        s.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in socks]
    for s in socks:
        s.close()
    return ports


class Listener:
    """A bare TCP port that accepts and closes (an FTP-only box, a loader-only device...)."""

    def __init__(self, host, port):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(8)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                c, _ = self.sock.accept()
                c.close()
            except OSError:
                return

    def close(self):
        self.sock.close()


def web(host, port, names):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"processes": [{"name": n, "pid": i} for i, n in enumerate(names)]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Interfaces(unittest.TestCase):
    def test_windows_ipconfig_any_language(self):
        self.assertEqual(ps5.addresses_from_text(IPCONFIG), ["192.168.50.23", "10.20.30.40", "169.254.12.34"])

    def test_linux_ip_and_ifconfig(self):
        self.assertEqual(ps5.addresses_from_text(IP_ADDR), ["127.0.0.1", "192.168.50.23", "172.20.10.5"])
        self.assertEqual(ps5.addresses_from_text(IFCONFIG), ["192.168.50.23", "127.0.0.1"])

    def test_every_private_interface_becomes_a_network(self):
        nets = ps5.local_networks(ps5.addresses_from_text(IPCONFIG) + ps5.addresses_from_text(IP_ADDR))
        self.assertEqual([str(n) for n in nets], ["10.20.30.0/24", "172.20.10.0/24", "192.168.50.0/24"])

    def test_this_computer_is_read_without_errors(self):
        for addr in ps5.computer_addresses():
            ipaddress.ip_address(addr)


@unittest.skipUnless(MULTI_LOOPBACK, "this system only allows 127.0.0.1")
class Sweep(unittest.TestCase):
    def setUp(self):
        self.ftp, self.loader, self.websrv = free_ports(3)
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-discovery-")
        self.cleanup = []

    def tearDown(self):
        for c in reversed(self.cleanup):
            c()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ps5(self, host):
        fc = FakeConsole(os.path.join(self.tmp, host)).start(ftp_port=self.ftp, loader_port=self.loader,
                                                             websrv_port=self.websrv, host=host)
        self.cleanup.append(fc.stop)
        return fc

    def listen(self, host, port):
        lis = Listener(host, port)
        self.cleanup.append(lis.close)

    def scan(self, *nets):
        return ps5.scan([ipaddress.ip_network(n) for n in nets], ftp_port=self.ftp, loader_port=self.loader,
                        websrv_port=self.websrv)

    def test_two_networks_ps5_on_the_second(self):
        self.ps5("127.0.2.1")
        found = self.scan("127.0.1.0/30", "127.0.2.0/30")
        self.assertEqual(found, [{"host": "127.0.2.1", "loader": True, "ftp": True, "confirmed": True}])

    def test_ftp_only_device_is_not_a_ps5(self):
        self.listen("127.0.1.1", self.ftp)               # e.g. a NAS with FTP on the same port
        self.ps5("127.0.2.1")
        self.assertEqual([f["host"] for f in self.scan("127.0.1.0/30", "127.0.2.0/30")], ["127.0.2.1"])

    def test_device_whose_websrv_shows_no_ps5_processes_is_refused(self):
        self.listen("127.0.3.1", self.loader)
        srv = web("127.0.3.1", self.websrv, ["init", "httpd", "smbd"])
        self.cleanup.append(srv.shutdown)
        self.assertEqual(self.scan("127.0.3.0/30"), [])

    def test_ps5_without_websrv_still_counts(self):
        fc = FakeConsole(os.path.join(self.tmp, "nows"), websrv=False).start(ftp_port=self.ftp, loader_port=self.loader,
                                                                              host="127.0.4.1")
        self.cleanup.append(fc.stop)
        self.assertEqual(self.scan("127.0.4.0/30"), [{"host": "127.0.4.1", "loader": True, "ftp": True, "confirmed": None}])

    def test_ps5_with_its_ftp_server_off_is_reported_as_such(self):
        self.listen("127.0.5.1", self.loader)
        srv = web("127.0.5.1", self.websrv, ["SceShellCore", "SceShellUI", "elfldr.elf"])
        self.cleanup.append(srv.shutdown)
        self.assertEqual(self.scan("127.0.5.0/30"), [{"host": "127.0.5.1", "loader": True, "ftp": False, "confirmed": True}])


@unittest.skipUnless(MULTI_LOOPBACK, "this system only allows 127.0.0.1")
class FindStep(unittest.TestCase):
    """The one-button find step: loader first; "found your PS5, but its FTP server isn't running" until it is."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-find-")
        self._env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp, "pc")
        self._timing = dict(oneclick.TIMING)
        oneclick.TIMING.update(poll=0.2, scan_poll=0.2, remind=5, smp_limit=5, smp_poll=0.1, smp_settle=0.05,
                               smp_settle_missing=0.05, status_timeout=10, no_websrv_pause=0.05)

    def tearDown(self):
        oneclick.TIMING.clear()
        oneclick.TIMING.update(self._timing)
        if self._env is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_says_ftp_is_off_then_carries_on_when_it_starts(self):
        zips, _ = make_packages(self.tmp)
        ftp, loader, websrv = free_ports(3)
        host = "127.0.6.1"
        lis = Listener(host, loader)                     # the PS5 is up, but only its loader runs so far
        events, started = [], []
        fc = FakeConsole(os.path.join(self.tmp, "console"))
        fc.write(config.AUTOLOAD_PATH, "shadowmountplus.elf\nkstuff-lite.elf\n")
        fc.write("/data/shadowmount/debug.log", "x\n")

        def report(e):
            events.append(e)
            if "FTP server isn't running" in e.get("text", "") and not started:
                started.append(True)                     # the user loads ftpsrv
                lis.close()
                fc.start(ftp_port=ftp, loader_port=loader, websrv_port=websrv, host=host)
        oc = oneclick.OneClick(ftp_port=ftp, loader_port=loader, websrv_port=websrv, catalog=catalog_of(zips),
                               report=report, sleep=lambda s: time.sleep(min(s, 0.05)), jdownloader=False,
                               networks=[ipaddress.ip_network("127.0.6.0/30")])
        try:
            result = oc.run()
        finally:
            if started:
                fc.stop()
        texts = [e.get("text", "") for e in events]
        self.assertTrue(result["ok"], texts)
        self.assertTrue(any("Found your PS5 at 127.0.6.1 (its payload loader answers" in t for t in texts), texts)
        self.assertTrue(any("Found your PS5 at 127.0.6.1." in t for t in texts), texts)
        self.assertEqual(fc.state["deletes"], [])


if __name__ == "__main__":
    unittest.main()
