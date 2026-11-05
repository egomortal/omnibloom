"""Audit RL-01 regression tests (GPL-3.0-or-later): Setup installs a package only when its published
checksum (and, for downloads, the release manifest) match it. Local files and a local HTTP stand-in
for the GitHub API only.   python -m unittest tests.test_release_provenance -v   (from the Setup folder)
"""
import hashlib
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_end_to_end import make_packages  # noqa: E402
from omnibloom_setup import release  # noqa: E402

sha = lambda b: hashlib.sha256(b).hexdigest()


class Offline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-rl01-")
        self.zips, _ = make_packages(self.tmp)
        self.folder = os.path.dirname(self.zips[0])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_package_with_matching_checksum_loads(self):
        cat = release.load_catalog(folder=self.folder, online=False)
        self.assertTrue(cat.has("omni"))
        cat.close()

    def test_package_without_checksum_refused(self):
        os.rename(self.zips[0] + ".sha256", self.zips[0] + ".sha256.away")
        with self.assertRaises(release.ReleaseError):
            release.load_catalog(folder=self.folder, online=False)

    def test_package_with_wrong_checksum_refused(self):
        with open(self.zips[0] + ".sha256", "w") as f:
            f.write("%s  %s\n" % ("0" * 64, os.path.basename(self.zips[0])))
        with self.assertRaises(release.ReleaseError):
            release.load_catalog(folder=self.folder, online=False)


class Online(unittest.TestCase):
    """A package and its .sha256 swapped together still disagree with the release manifest."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="omnibloom-rl01-")
        zips, _ = make_packages(self.tmp, version="1.2.3")
        self.zip = zips[0]
        self.name = os.path.basename(self.zip)
        self.raw = open(self.zip, "rb").read()
        self.served = {"zip": self.raw, "tag": "v1.2.3", "manifest": True,
                       "manifest_row": {"name": self.name, "bytes": len(self.raw), "sha256": sha(self.raw)}}
        test = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                base = "http://127.0.0.1:%d" % self.server.server_address[1]
                s = test.served
                if self.path == "/repos/egomortal/omnibloom/releases/latest":
                    assets = [{"name": test.name, "browser_download_url": base + "/zip", "size": len(s["zip"])},
                              {"name": test.name + ".sha256", "browser_download_url": base + "/sha"}]
                    if s["manifest"]:
                        assets.append({"name": "RELEASE-MANIFEST.json", "browser_download_url": base + "/manifest"})
                    body = json.dumps({"tag_name": "v1.2.3", "assets": assets}).encode()
                elif self.path == "/zip":
                    body = s["zip"]
                elif self.path == "/sha":
                    body = ("%s  %s\n" % (sha(s["zip"]), test.name)).encode()     # always matches what is served
                elif self.path == "/manifest":
                    body = json.dumps({"schema": "omnibloom-release-manifest/v1", "tag": s["tag"],
                                       "assets": [s["manifest_row"]]}).encode()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.api = "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.cache = os.path.join(self.tmp, "cache")
        os.makedirs(self.cache)

    def tearDown(self):
        self.srv.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetch(self):
        source = next(s for s in release.config.SOURCES if s["repo"].endswith("/omnibloom"))
        info = release.latest_release_info(source, api_base=self.api)
        return release.Package(release.download_release(info, dest_dir=self.cache))

    def test_consistent_release_loads(self):
        pkg = self.fetch()
        self.assertEqual(pkg.version, "1.2.3")
        pkg.close()

    def test_swapped_package_and_checksum_refused(self):
        other_tmp = os.path.join(self.tmp, "other")
        other, _ = make_packages(other_tmp, version="1.2.3", changed=b" swapped")
        self.served["zip"] = open(other[0], "rb").read()      # a different, self-consistent package + .sha256
        with self.assertRaises(release.ReleaseError):
            self.fetch()

    def test_missing_manifest_refused(self):
        self.served["manifest"] = False
        with self.assertRaises(release.ReleaseError):
            self.fetch()

    def test_manifest_from_another_release_refused(self):
        self.served["tag"] = "v1.2.2"
        with self.assertRaises(release.ReleaseError):
            self.fetch()


if __name__ == "__main__":
    unittest.main()
