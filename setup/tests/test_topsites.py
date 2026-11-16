"""S14: most-visited sites from PC history -> a "Most visited" bookmarks folder (no network, no console)."""
import os
import sqlite3
import tempfile
import unittest

from omnibloom_setup import bookmarks, topsites


class SiteOf(unittest.TestCase):
    def test_hosts(self):
        self.assertEqual(topsites.site_of("https://www.youtube.com/watch?v=x"), "youtube.com")
        self.assertEqual(topsites.site_of("https://m.wikipedia.org/wiki/A"), "wikipedia.org")
        self.assertEqual(topsites.site_of("http://news.example.co.uk/a"), "news.example.co.uk")
        self.assertEqual(topsites.site_of("https://www.co/"), "www.co", "two labels keep www")

    def test_skipped(self):
        for u in ("ftp://x.example/", "javascript:alert(1)", "https://192.168.0.10/", "http://[::1]/", "http://localhost:8080/",
                  "http://nas.local/", "http://router.lan/", "http://intranet/", "https://login.example.com/",
                  "https://accounts.google.com/", "https://mail.example.com/", "https://www.paypal.com/x",
                  "https://mybank.example.com/", "", None, "not a url"):
            self.assertIsNone(topsites.site_of(u), u)


class Aggregate(unittest.TestCase):
    def test_pool_rank_and_titles(self):
        rows = [("https://www.youtube.com/watch?v=1", "Video one", 50), ("https://youtube.com/", "YouTube", 80),
                ("https://example.org/a", "Ex A", 10), ("https://example.org/b", None, 25), ("https://192.168.0.1/", "Router", 999),
                ("https://z.example/", "Z", 10), ("https://bad.example/", "x", "lots")]
        sites = topsites.aggregate(rows, top=10)
        self.assertEqual([s.host for s in sites], ["youtube.com", "example.org", "z.example"])
        self.assertEqual((sites[0].visits, sites[0].title, sites[0].url), (130, "YouTube", "https://youtube.com/"))
        self.assertEqual(sites[1].title, "Ex A", "the most visited row had no title: the best titled one is kept")
        self.assertEqual(len(topsites.aggregate([("https://s%d.example/" % i, "t", i) for i in range(50)])), topsites.TOP)

    def test_titles_are_cleaned(self):
        s = topsites.aggregate([("https://a.example/", "A\x00\x07 title " + "x" * 600, 3)])[0]
        self.assertNotIn("\x00", s.title)
        self.assertLessEqual(len(s.title.encode("utf-8")), 600)


class Databases(unittest.TestCase):
    def _db(self, table):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "History" if table == "urls" else "places.sqlite")
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE %s (url TEXT, title TEXT, visit_count INTEGER, hidden INTEGER)" % table)
        db.executemany("INSERT INTO %s VALUES (?,?,?,?)" % table, [("https://a.example/", "A", 9, 0), ("https://b.example/", "B", 4, 0),
                                                                 ("https://hidden.example/", "H", 99, 1)])
        db.commit()
        db.close()
        return tmp, path

    def test_chromium_and_firefox(self):
        tmp, hist = self._db("urls")
        src = bookmarks.Source("Chrome", "Default", os.path.join(tmp, "Bookmarks"), "chromium")
        self.assertEqual([s.host for s in topsites.top_sites([src])], ["a.example", "b.example"])
        tmp2, places = self._db("moz_places")
        ff = bookmarks.Source("Firefox", "default", places, "firefox")
        self.assertEqual([s.host for s in topsites.top_sites([ff, src])][:1], ["a.example"])

    def test_missing_or_broken_history(self):
        tmp = tempfile.mkdtemp()
        src = bookmarks.Source("Chrome", "Default", os.path.join(tmp, "Bookmarks"), "chromium")
        self.assertEqual(topsites.top_sites([src]), [])
        with open(os.path.join(tmp, "History"), "wb") as f:
            f.write(b"not a database")
        self.assertEqual(topsites.top_sites([src]), [])
        self.assertIsNotNone(src.error)

    def test_bookmarks_folder(self):
        b = topsites.as_bookmarks(topsites.aggregate([("https://a.example/x", "A", 3)]))
        self.assertEqual(b, [bookmarks.Bookmark("https://a.example/", "A", False, "Most visited")])


if __name__ == "__main__":
    unittest.main()
