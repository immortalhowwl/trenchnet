import unittest, importlib.util

class AddressTests(unittest.TestCase):
    def test_accepts_only_32_byte_base58_addresses(self):
        self.assertIsNotNone(importlib.util.find_spec('server'), 'server validation is not implemented')
        from server import valid_address
        self.assertTrue(valid_address('CDAC33JvozJ1UjxBMkvZgJcVXoxdH9iGxeBXUJdXpump'))
        for value in ('', '../etc/passwd', 'https://localhost', '0'*44, 'z'*44, '1'*31, '<script>'):
            self.assertFalse(valid_address(value), value)

class ProxyTests(unittest.TestCase):
    def test_client_ip_only_from_explicitly_trusted_loopback_proxy(self):
        from server import client_identity
        self.assertEqual(client_identity('127.0.0.1', '203.0.113.9', True), '203.0.113.9')
        self.assertEqual(client_identity('198.51.100.1', '203.0.113.9', True), '198.51.100.1')
        self.assertEqual(client_identity('127.0.0.1', '203.0.113.9', False), '127.0.0.1')
        self.assertEqual(client_identity('127.0.0.1', 'invalid', True), '127.0.0.1')

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile, pathlib, threading
        from server import create_server
        cls.tmp = tempfile.TemporaryDirectory()
        web = pathlib.Path(cls.tmp.name) / 'web'
        web.mkdir()
        (web / 'index.html').write_text('<html>TRENCHNET</html>')
        (web / 'utils.mjs').write_text('export const value = 1;')
        cls.http = create_server('127.0.0.1', 0, pathlib.Path(cls.tmp.name) / 'db.sqlite', web, snapshot_fn=lambda _: {'markets': [], 'trades': [], 'traders': [], 'decisions': [], 'graph': {'nodes': [], 'edges': []}, 'status': {'collector': 'starting'}, 'updatedAt': None})
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        import urllib.request
        return urllib.request.urlopen(self.base + path, timeout=5)

    def test_read_only_health_snapshot_export(self):
        import json
        for path in ('/api/health', '/api/snapshot', '/api/export'):
            with self.get(path) as response:
                self.assertEqual(response.status, 200)
                self.assertIsInstance(json.load(response), dict)
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_invalid_address_rejected(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get('/api/token?address=https://localhost')
        self.assertEqual(cm.exception.code, 400)

    def test_missing_wallet_is_honest(self):
        import json
        with self.get('/api/wallet?address=CDAC33JvozJ1UjxBMkvZgJcVXoxdH9iGxeBXUJdXpump') as r:
            result = json.load(r)
        self.assertEqual(result['trades'], [])
        self.assertIsNone(result['profile'])
        self.assertIn('sample', result['coverage'])

    def test_static_and_traversal(self):
        import urllib.error
        with self.get('/') as r:
            self.assertIn(b'TRENCHNET', r.read())
            self.assertIn('Content-Security-Policy', r.headers)
        for path in ('/../server.py', '/%2e%2e/server.py', '/api/secret', '/.env'):
            with self.assertRaises(urllib.error.HTTPError) as cm: self.get(path)
            self.assertEqual(cm.exception.code, 404)

    def test_module_assets_supported(self):
        with self.get('/utils.mjs') as r:
            self.assertEqual(r.status, 200)
            self.assertIn('javascript', r.headers['Content-Type'])

    def test_post_disabled(self):
        import urllib.request, urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(urllib.request.Request(self.base + '/api/snapshot', data=b'{}'), timeout=5)
        self.assertEqual(cm.exception.code, 405)

if __name__ == '__main__': unittest.main()
