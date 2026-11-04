#!/usr/bin/env python3
"""Check legacy migration and exact-host policy without touching a build tree."""
import importlib.util
from pathlib import Path
import re
import unittest

spec = importlib.util.spec_from_file_location('dns_patch', Path(__file__).with_name('patch-widget-dns.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
clean = '''    if (url.protocolIs("https"_s))
        enableSSL();
CURLcode CurlHandle::willSetupSslCtxCallback(CURL*, void* sslCtx, void* userData)
{
    return static_cast<CurlHandle*>(userData)->willSetupSslCtx(sslCtx);
}'''

class ResolverPatchTests(unittest.TestCase):
    def test_clean_and_legacy_converge_idempotently(self):
        current = module.patch_source(clean)
        self.assertEqual(current, module.patch_source(current))
        policy = re.search(r'    // \[omni-browser-dns-v3\][\s\S]*?bool widgetHost = .*?;', current).group()
        legacy = current.replace(policy, '    bool widgetHost = url.protocolIs("https"_s) && url.host() == "www.gstatic.com"_s;')
        self.assertEqual(current, module.patch_source(legacy))

    def test_browser_dns_and_tls_checks(self):
        current = module.patch_source(clean)
        self.assertIn('bool widgetHost = url.protocolIsInHTTPFamily() && !systemHost;', current)
        for domain in ['playstation.net', 'playstation.com', 'local', 'lan', 'sony.com']:
            self.assertIn('within("' + domain + '"_s)', current)
        self.assertIn('widgetHost ? "https://cloudflare-dns.com/dns-query" : nullptr', current)
        self.assertIn('CURLOPT_DOH_SSL_VERIFYPEER, 1L', current)
        self.assertIn('CURLOPT_DOH_SSL_VERIFYHOST, 2L', current)
        self.assertIn('while (dnsHost.endsWith', current)

    def test_unknown_existing_policy_rejected(self):
        current = module.patch_source(clean)
        with self.assertRaises(AssertionError):
            module.patch_source(current.replace('playstation.net','unknown.example'))
        with self.assertRaises(AssertionError):
            module.patch_source(current.replace('CURLOPT_DOH_SSL_VERIFYPEER, 1L','CURLOPT_DOH_SSL_VERIFYPEER, 0L'))

if __name__ == '__main__': unittest.main()
