"""OMNI_DL9_IPV4_FIRST: public_address prefers IPv4 among all-public addresses and still refuses any private one."""
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import probe  # noqa: E402

V6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2a00:1450:4001:80b::200e', 443, 0, 0))
V4 = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('142.250.185.110', 443))
V4_PRIVATE = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.10', 443))


class Ipv4First(unittest.TestCase):
    def pick(self, infos):
        with mock.patch.object(probe.socket, 'getaddrinfo', return_value=infos):
            return probe.public_address('www.youtube.com', 443)

    def test_ipv6_listed_first_ipv4_chosen(self):
        self.assertEqual(self.pick([V6, V4])[1], '142.250.185.110')

    def test_ipv6_only_still_works(self):
        self.assertEqual(self.pick([V6])[1], '2a00:1450:4001:80b::200e')

    def test_ipv4_first_unchanged(self):
        self.assertEqual(self.pick([V4, V6])[1], '142.250.185.110')

    def test_any_private_address_still_refused(self):
        with self.assertRaises(probe.Refused):
            self.pick([V6, V4_PRIVATE])


if __name__ == '__main__':
    unittest.main()
