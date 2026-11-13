"""OMNI_DL9_OWN_DNS: a local 0.0.0.0 answer (nanoDNS block) or a failed local lookup falls back to the worker's own
DNS query; everything else is unchanged and the public-address rules still apply to the fallback's answers."""
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import probe  # noqa: E402

BLOCKED = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('0.0.0.0', 443))]
NORMAL = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]


class OwnDns(unittest.TestCase):
    def test_local_block_uses_upstream(self):
        with mock.patch.object(probe.socket, 'getaddrinfo', return_value=BLOCKED), \
             mock.patch.object(probe, '_dns_query', side_effect=lambda s, h, q, *a: ['142.250.185.110'] if q == 1 else []):
            self.assertEqual(probe.public_address('www.youtube.com', 443)[1], '142.250.185.110')

    def test_upstream_private_answer_still_refused(self):
        with mock.patch.object(probe.socket, 'getaddrinfo', return_value=BLOCKED), \
             mock.patch.object(probe, '_dns_query', side_effect=lambda s, h, q, *a: ['10.0.0.5'] if q == 1 else []):
            with self.assertRaises(probe.Refused):
                probe.public_address('www.youtube.com', 443)

    def test_block_and_no_upstream_answer_refused(self):
        with mock.patch.object(probe.socket, 'getaddrinfo', return_value=BLOCKED), \
             mock.patch.object(probe, '_dns_query', return_value=[]):
            with self.assertRaises(probe.Refused):
                probe.public_address('www.youtube.com', 443)

    def test_normal_answer_does_not_ask_upstream(self):
        with mock.patch.object(probe.socket, 'getaddrinfo', return_value=NORMAL), \
             mock.patch.object(probe, '_dns_query', side_effect=AssertionError('must not query')):
            self.assertEqual(probe.public_address('example.com', 443)[1], '93.184.216.34')

    def test_ip_literal_never_asks_upstream(self):
        with mock.patch.object(probe, '_dns_query', side_effect=AssertionError('must not query')):
            with self.assertRaises(probe.Refused):
                probe.public_address('0.0.0.0', 443)

    def test_local_failure_uses_upstream(self):
        with mock.patch.object(probe.socket, 'getaddrinfo', side_effect=socket.gaierror('no')), \
             mock.patch.object(probe, '_dns_query', side_effect=lambda s, h, q, *a: ['142.250.185.110'] if q == 1 else []):
            self.assertEqual(probe.public_address('www.youtube.com', 443)[1], '142.250.185.110')

    @unittest.skipUnless(__import__('os').environ.get('DL9_NET') == '1', 'set DL9_NET=1 to query real resolvers')
    def test_real_upstream_query(self):
        self.assertTrue(probe._dns_query('1.1.1.1', 'www.youtube.com', 1))


if __name__ == '__main__':
    unittest.main()
