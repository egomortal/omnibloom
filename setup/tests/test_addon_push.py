"""Push an add-on to Omni (addon_push.py, S12): the loader's manifest rules, package safety (zip-slip, links, sizes,
file types), id clashes, the 40 add-on cap, and the upload order (temp folder, verified files, .prev, rename into
place) on a fake console. The last class runs against the fake FTP PS5 and is skipped without pyftpdlib."""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from omnibloom_setup import addon_push as ap  # noqa: E402

U = ap.USER_ROOT
NOW = 1700000000


def manifest(**over):
    m = {"manifest_version": 1, "id": "my-tool", "name": "My tool", "version": "1.0.0", "licence": "MIT",
         "matches": ["https://*.example.com/*"], "js": ["main.js"], "css": ["style.css"]}
    m.update(over)
    return {k: v for k, v in m.items() if v is not None}


def files(m=None, **extra):
    out = {"manifest.json": json.dumps(manifest() if m is None else m).encode(), "main.js": b"console.log(1);\n",
           "style.css": b"body{}\n", "LICENSE": b"MIT\n"}
    out.update(extra)
    return out


def make_zip(entries, root=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            if isinstance(data, zipfile.ZipInfo):
                z.writestr(data, b"x")
            else:
                z.writestr(root + name, data)
    return buf.getvalue()


class FakeConsole:
    """Files and folders in dicts; every write recorded in order."""

    def __init__(self):
        self.files, self.dirs, self.ops = {}, set(), []

    def add_dir(self, path):
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            self.dirs.add("/" + "/".join(parts[:i]))

    def add_addon(self, root, aid, version="1.0.0"):
        self.add_dir(root + aid)
        self.files[root + aid + "/manifest.json"] = json.dumps(manifest(id=aid, version=version)).encode()

    def listing(self, d):
        d = d.rstrip("/")
        out = {}
        for p in self.dirs:
            if p.rsplit("/", 1)[0] == d:
                out[p.rsplit("/", 1)[1]] = {"dir": True, "size": 0}
        for p, data in self.files.items():
            if p.rsplit("/", 1)[0] == d:
                out[p.rsplit("/", 1)[1]] = {"dir": False, "size": len(data)}
        return out

    def exists(self, path):
        return path in self.files or path.rstrip("/") in self.dirs

    def read(self, path, limit=None):
        return self.files[path]

    def makedirs(self, path):
        self.ops.append(("mkdir", path))
        self.add_dir(path)

    def put_verified(self, path, data, readback=True):
        self.ops.append(("put", path))
        self.files[path + ".omnibloom-new"] = data
        return path + ".omnibloom-new"

    def rename(self, src, dst):
        self.ops.append(("rename", src, dst))
        assert not self.exists(dst), "rename onto an existing name"
        if src in self.files:
            self.files[dst] = self.files.pop(src)
            return
        assert src in self.dirs, "rename of a missing name " + src
        for p in [p for p in self.dirs if p == src or p.startswith(src + "/")]:
            self.dirs.discard(p)
            self.dirs.add(dst + p[len(src):])
        for p in [p for p in self.files if p.startswith(src + "/")]:
            self.files[dst + p[len(src):]] = self.files.pop(p)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def zip_pkg(self, entries, root=""):
        p = os.path.join(self.tmp.name, "a.zip")
        with open(p, "wb") as f:
            f.write(make_zip(entries, root))
        return p

    def folder_pkg(self, entries):
        d = os.path.join(self.tmp.name, "pkg")
        for name, data in entries.items():
            full = os.path.join(d, *name.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(data)
        return d

    def refused(self, entries, needle, root=""):
        with self.assertRaises(ap.AddonError) as cm:
            ap.load_package(self.zip_pkg(entries, root))
        self.assertIn(needle, str(cm.exception))


class Manifests(Base):
    def bad(self, needle, **over):
        with self.assertRaises(ap.AddonError) as cm:
            ap.validate_manifest(json.dumps(manifest(**over)).encode())
        self.assertIn(needle, str(cm.exception))

    def test_good_and_defaults(self):
        m = ap.validate_manifest(json.dumps(manifest(matches=["<all_urls>"], hosts=["API.example.org"])).encode())
        self.assertEqual(m["matches"], ["*://*/*"])
        self.assertEqual(m["hosts"], ["api.example.org"])
        self.assertEqual((m["run_at"], m["private_safe"], m["live_toggle"], m["css_level"]),
                         ("document_end", False, True, "user"))

    def test_bundled_manifests_pass(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addons", "bundled")
        if not os.path.isdir(root):
            self.skipTest("bundled add-ons not in this checkout")
        for aid in sorted(os.listdir(root)):
            with open(os.path.join(root, aid, "manifest.json"), "rb") as f:
                self.assertEqual(ap.validate_manifest(f.read())["id"], aid)

    def test_bad_manifests(self):
        self.bad("manifest_version", manifest_version=2)
        self.bad("manifest needs id", id=None)
        self.bad("manifest needs licence", licence=None)
        self.bad("bad id", id="My_Tool")
        self.bad("bad id", id="-tool")
        self.bad("bad id", id="a" * 41)
        self.bad("bad name", name="x" * 61)
        self.bad("bad version", version="1\n2")
        self.bad("run_at", run_at="document_load")
        self.bad("https URL", source="http://example.com")
        self.bad("matches needed", matches=[])
        self.bad("too many matches", matches=["https://a.com/*"] * 33)
        self.bad("no scheme", matches=["example.com/*"])
        self.bad("only http", matches=["file:///*"])
        self.bad("no path", matches=["https://example.com"])
        self.bad("ports", matches=["https://example.com:8080/*"])
        self.bad("local addresses", matches=["*://192.168.0.2/*"])
        self.bad("local addresses", matches=["*://printer.local/*"])
        self.bad("bad host", matches=["*://exa mple.com/*"])
        self.bad("bad character", excludes=["*://*/a\"b"])
        self.bad("needs js or css", js=[], css=[])
        self.bad("bad js file", js=["../up.js"])
        self.bad("bad js file", js=["/abs.js"])
        self.bad("bad css file", css=["style.txt"])
        self.bad("too many js", js=["a%d.js" % i for i in range(9)])
        self.bad("bad fetch host", hosts=["localhost"])
        self.bad("bad fetch host", hosts=["10.0.0.1"])
        self.bad("bad fetch host", hosts=["intranet"])
        self.bad("private_safe must be true or false", private_safe="yes")
        self.bad("css_level", css_level="page")
        self.bad("unknown type", settings=[{"key": "a", "type": "color", "label": "A", "default": 1}])
        self.bad("duplicate setting", settings=[{"key": "a", "type": "bool", "label": "A", "default": True}] * 2)
        self.bad("default outside", settings=[{"key": "a", "type": "range", "label": "A", "default": 9, "min": 0, "max": 5}])
        self.bad("one of the choices", settings=[{"key": "a", "type": "choice", "label": "A", "default": "z", "choices": ["x"]}])

    def test_not_json_or_duplicates_or_too_big(self):
        for raw, needle in ((b"[1]", "not an object"), (b"{", "manifest.json"),
                            (b'{"id":"a","id":"b"}', "duplicate"), (b" " * (64 * 1024 + 1), "too big")):
            with self.assertRaises(ap.AddonError) as cm:
                ap.validate_manifest(raw)
            self.assertIn(needle, str(cm.exception))


class Packages(Base):
    def test_zip_and_folder_and_top_folder(self):
        for path in (self.zip_pkg(files()), self.folder_pkg(files()), self.zip_pkg(files(), root="my-tool-1.0/")):
            pkg = ap.load_package(path)
            self.assertEqual(sorted(pkg.files), ["LICENSE", "main.js", "manifest.json", "style.css"])

    def test_junk_skipped_unlisted_warned(self):
        pkg = ap.load_package(self.zip_pkg(files(**{"__MACOSX/._x": b"", "extra.js": b"1", "README.md": b"hi"})))
        self.assertEqual(pkg.skipped, ["__MACOSX/._x"])
        self.assertTrue(any("extra.js" in w for w in pkg.warnings))

    def test_traversal(self):
        self.refused(files(**{"../evil.js": b"x"}), "unsafe path")
        self.refused(files(**{"a/../../evil.js": b"x"}), "unsafe path")
        self.refused(files(**{"/etc/evil.js": b"x"}), "unsafe path")
        self.refused(files(**{"..\\evil.js": b"x"}), "unsafe path")   # zipfile turns \\ into / on Windows
        self.refused(files(**{"C:/evil.js": b"x"}), "unsafe path")
        self.refused({"/abs/" + k: v for k, v in files().items()}, "unsafe path")

    def test_symlink_member(self):
        info = zipfile.ZipInfo("link.js")
        info.external_attr = (0o120777 << 16)
        self.refused(dict(files(), link=info), "links are not allowed")

    def test_oversize(self):
        self.refused(files(**{"main.js": b"x" * (ap.MAX_JS_FILE + 1)}), "too big")
        self.refused(files(**{"style.css": b"x" * (ap.MAX_CSS_TOTAL + 1)}), "too big")
        self.refused(files(**{"LICENSE": b"x" * (ap.MAX_DOC + 1)}), "too big")
        m = manifest(js=["a.js", "b.js", "c.js"])
        big = os.urandom(ap.MAX_JS_FILE - 10)   # incompressible, so only the total trips
        self.refused(files(m, **{"a.js": big, "b.js": big, "c.js": big}), "scripts too big")
        self.refused(files(**{"n%d.md" % i: b"x" for i in range(40)}), "more than")

    def test_wrong_types_and_names(self):
        self.refused(files(**{"icon.png": b"\x89PNG"}), "images")
        self.refused(files(**{"run.exe": b"MZ"}), "file type not allowed")
        self.refused(files(**{"tool.sh": b"#!"}), "file type not allowed")
        self.refused(files(**{".hidden.js": b"1"}), "no hidden files")
        self.refused(files(**{"sp ace.js": b"1"}), "file names")
        self.refused(files(**{"a/b/c/d/e.md": b"1"}), "nested too deep")

    def test_missing_files(self):
        f = files()
        del f["main.js"]
        self.refused(f, "main.js missing")
        f = files()
        del f["manifest.json"]
        self.refused(f, "manifest.json is missing")

    def test_case_clash(self):
        self.refused(files(**{"Readme.md": b"1", "README.md": b"2"}), "differ only in case")

    def test_summary(self):
        m = ap.validate_manifest(json.dumps(manifest(matches=["<all_urls>"], private_safe=True, hosts=["api.example.org"],
                                                     default_on=True)).encode())
        text = "\n".join(ap.access_summary(m))
        for needle in ("every website", "also runs there", "https://api.example.org", "ON for every"):
            self.assertIn(needle, text)


class ConsideringTheConsole(Base):
    def pkg(self, **over):
        return ap.load_package(self.zip_pkg(files(manifest(**over))))

    def console(self, title=("dark-reader",), user=(), dev=(), flag=False):
        c = FakeConsole()
        c.add_dir(ap.TITLE_ROOT)
        c.add_dir(ap.USER_ROOT)
        for a in title:
            c.add_addon(ap.TITLE_ROOT, a)
        for a in user:
            c.add_addon(ap.USER_ROOT, a)
        for a in dev:
            c.add_addon(ap.DEV_ROOT, a)
        if flag:
            c.files[ap.DEV_FLAG] = b""
        return c

    def test_clash_with_bundled(self):
        c = self.console()
        with self.assertRaises(ap.AddonError) as cm:
            ap.plan(c, self.pkg(id="dark-reader"))
        self.assertIn("comes with Omni", str(cm.exception))
        with self.assertRaises(ap.AddonError):        # a known bundled id even when the title lists others
            ap.plan(c, self.pkg(id="omni-sponsorblock"), update=True)
        self.assertEqual(c.ops, [])

    def test_existing_user_addon_needs_update(self):
        c = self.console(user=("my-tool",))
        with self.assertRaises(ap.AddonError) as cm:
            ap.plan(c, self.pkg())
        self.assertIn("Update", str(cm.exception))
        info = ap.plan(c, self.pkg(version="2.0.0"), update=True)
        self.assertTrue(info["update"])
        self.assertEqual(info["old_version"], "1.0.0")

    def test_cap_refused(self):
        c = self.console(title=["t%d" % i for i in range(30)], user=["u%d" % i for i in range(10)])
        with self.assertRaises(ap.AddonError) as cm:
            ap.push(c, self.pkg(), confirm=lambda *a: self.fail("asked before refusing"))
        self.assertIn("at most 40", str(cm.exception))
        self.assertEqual(c.ops, [])

    def test_cap_counts_dev_only_with_flag_and_allows_update(self):
        title, user = ["t%d" % i for i in range(30)], ["u%d" % i for i in range(8)] + ["my-tool"]
        self.assertEqual(ap.plan(self.console(title, user, dev=["d1", "d2"]), self.pkg(), update=True)["count"], 39)
        with self.assertRaises(ap.AddonError):
            ap.plan(self.console(title, user[:-1], dev=["d1", "d2"], flag=True), self.pkg())
        self.assertEqual(ap.plan(self.console(title, user[:-1] + ["u9"]), self.pkg(id="u9"), update=True)["count"], 39)

    def test_unlisted_title_assumes_shipped_count(self):
        c = FakeConsole()
        c.add_dir(ap.USER_ROOT)
        for i in range(14):
            c.add_addon(ap.USER_ROOT, "u%d" % i)
        with self.assertRaises(ap.AddonError):      # 26 assumed + 14 = 40
            ap.plan(c, self.pkg())

    def test_cancel_writes_nothing(self):
        c = self.console()
        self.assertIsNone(ap.push(c, self.pkg(), confirm=lambda lines, info: False))
        self.assertEqual(c.ops, [])

    def test_atomic_upload_order(self):
        c = self.console(user=("my-tool",))
        c.files[U + "my-tool.prev/manifest.json"] = b"{}"
        c.add_dir(U + "my-tool.prev")
        pkg = ap.load_package(self.zip_pkg(files(manifest(version="2.0.0"), **{"docs/notes.md": b"n"})))
        seen = []
        final = ap.push(c, pkg, update=True, confirm=lambda lines, info: seen.append(info) or True, now=NOW)
        self.assertEqual(final, U + "my-tool")
        temp = U + "my-tool.uploading-" + ap._stamp(NOW)
        kinds = [op[0] for op in c.ops]
        self.assertEqual(c.ops[0], ("mkdir", temp))
        # every file goes into the temp folder, verified, before anything at the live name moves
        first_live = next(i for i, op in enumerate(c.ops) if op[0] == "rename" and op[1].startswith(U + "my-tool.prev"))
        self.assertTrue(all(op[1].startswith(temp) for op in c.ops[:first_live]))
        self.assertEqual(kinds[:first_live].count("put"), len(pkg.files))
        self.assertEqual(c.ops[first_live:], [
            ("rename", U + "my-tool.prev", U + "my-tool.prev-" + ap._stamp(NOW)),
            ("rename", U + "my-tool", U + "my-tool.prev"),
            ("rename", temp, U + "my-tool"),
        ])
        self.assertEqual(json.loads(c.files[U + "my-tool/manifest.json"])["version"], "2.0.0")
        self.assertEqual(c.files[U + "my-tool/docs/notes.md"], b"n")
        self.assertEqual(json.loads(c.files[U + "my-tool.prev/manifest.json"])["version"], "1.0.0")
        self.assertFalse(any(k.endswith(".omnibloom-new") for k in c.files))
        self.assertTrue(seen and seen[0]["update"])

    def test_failed_swap_restores_previous(self):
        c = self.console(user=("my-tool",))
        real = c.rename

        def flaky(src, dst):
            if ".uploading-" in src and dst == U + "my-tool":
                raise IOError("550 rename failed")
            real(src, dst)
        c.rename = flaky
        with self.assertRaises(IOError):
            ap.push(c, self.pkg(version="2.0.0"), update=True, now=NOW)
        self.assertEqual(json.loads(c.files[U + "my-tool/manifest.json"])["version"], "1.0.0")
        self.assertNotIn(U + "my-tool.prev", c.dirs)

    def test_list_remove_rollback(self):
        c = self.console(user=("my-tool", "other"))
        c.add_dir(U + "broken")
        c.files[U + "broken/manifest.json"] = b"{"
        ap.push(c, self.pkg(version="2.0.0"), update=True, now=NOW)
        got = {a.id: a for a in ap.list_installed(c)}
        self.assertEqual(sorted(got), ["broken", "my-tool", "other"])   # .prev / .uploading names are not add-ons
        self.assertTrue(got["my-tool"].has_prev and got["my-tool"].ok)
        self.assertFalse(got["broken"].ok)
        ap.rollback(c, "my-tool", now=NOW)
        self.assertEqual(json.loads(c.files[U + "my-tool/manifest.json"])["version"], "1.0.0")
        dest = ap.remove(c, "other", now=NOW)
        self.assertEqual(dest, U + "other.removed-" + ap._stamp(NOW))
        self.assertIn(dest + "/manifest.json", c.files)
        self.assertNotIn("other", {a.id for a in ap.list_installed(c)})
        with self.assertRaises(ap.AddonError):
            ap.remove(c, "../x")


try:
    import pyftpdlib  # noqa: F401
    HAVE_FTP = True
except ImportError:
    HAVE_FTP = False


@unittest.skipUnless(HAVE_FTP, "pyftpdlib not installed")
class OverFtp(Base):
    def test_push_update_remove(self):
        from fake_console import FakeConsole as FtpConsole
        from omnibloom_setup import ps5
        root = os.path.join(self.tmp.name, "ps5")
        fc = FtpConsole(root).start()
        self.addCleanup(fc.stop)
        fc.write(ap.TITLE_ROOT + "dark-reader/manifest.json", b"{}")
        os.makedirs(fc.path(ap.USER_ROOT), exist_ok=True)
        c = ps5.Console("127.0.0.1", ftp_port=fc.ftp_port).connect()
        self.addCleanup(c.close)
        ap.push(c, self.zip_pkg(files()), now=NOW)
        ap.push(c, self.zip_pkg(files(manifest(version="2.0.0"))), update=True, now=NOW + 1)
        self.assertIn("my-tool.prev", fc.listdir(ap.USER_ROOT))
        self.assertEqual(json.loads(fc.read(U + "my-tool/manifest.json"))["version"], "2.0.0")
        ap.remove(c, "my-tool", now=NOW)
        self.assertEqual(fc.state["deletes"], [])


if __name__ == "__main__":
    unittest.main()
