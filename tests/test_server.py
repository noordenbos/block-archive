"""Verify public assets and local API boundaries without using real data."""
import http.client
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler, LocalServer


class ServerBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, body, headers={'Host': '127.0.0.1:8774', **(headers or {})})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_public_assets(self):
        for path in ('/', '/index.html', '/app.js', '/labels.html', '/artefacts/templates.html',
                     '/artefacts/FFPE-photography-A4.pdf', '/artefacts/FFPE-photography-Letter.pdf'):
            with self.subTest(path=path):
                status, body, headers = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_private_paths_and_listing_are_denied(self):
        for path in ('/.git/config', '/.local/blocked-capture-hashes.json', '/server.py', '/README.md',
                     '/blokids/ids.csv', '/dummies/', '/artefacts/', '/%2e%2e/.git/config',
                     '/artefacts/examples/dummy-mat-capture.jpg'):
            for method in ('GET', 'HEAD'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(method, path)[0], 404)

    def test_host_and_origin_guards(self):
        self.assertEqual(self.request('GET', '/', headers={'Host': 'attacker.invalid'})[0], 403)
        for headers in ({}, {'Origin': 'https://attacker.invalid', 'X-Spatial-Local': '1'},
                        {'Origin': 'http://127.0.0.1:8774'}, {'X-Spatial-Local': '1'}):
            self.assertEqual(self.request('POST', '/api/labels', 'TEST-0001', headers)[0], 403)

    def test_local_api_and_invalid_input(self):
        headers = {'Origin': 'http://127.0.0.1:8774', 'X-Spatial-Local': '1'}
        status, body, _ = self.request('POST', '/api/labels.pdf', 'TEST-0001\nTEST-0002', headers)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b'%PDF'))
        self.assertEqual(self.request('POST', '/api/analyze', b'not an image', headers)[0], 400)
        self.assertEqual(self.request('POST', '/api/labels', b'', {**headers, 'Content-Length': 'bad'})[0], 400)
        self.assertEqual(self.request('POST', '/api/labels', b'', {**headers, 'Content-Length': str(26 * 1024 * 1024)})[0], 413)


if __name__ == '__main__':
    unittest.main()
