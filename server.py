"""Loopback-only research app: allowlisted assets and in-memory analysis."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import base64
import errno
import sys
import subprocess
from vision import analyze
from label_pdf import parse_ids, qr_png, pdf_bytes

ROOT = Path(__file__).resolve().parent
ALLOWED_HOSTS = {'127.0.0.1:8774', 'localhost:8774'}
ALLOWED_ORIGINS = {'http://' + host for host in ALLOWED_HOSTS}
PUBLIC_ASSETS = frozenset({
    'index.html', 'app.js', 'geometry.js', 'ingest.js', 'placement-workflow.js',
    'experiments.js', 'style.css', 'labels.html', 'labels.js',
    'artefacts/templates.html',
    'artefacts/FFPE-photography-A4.pdf', 'artefacts/FFPE-photography-Letter.pdf',
    'artefacts/preview/FFPE-photography-A4.png',
    'artefacts/preview/FFPE-photography-Letter.png',
    'artefacts/preview/FFPE-photography-A4-instructions.png',
    'artefacts/preview/FFPE-photography-Letter-instructions.png',
    'artefacts/examples/phone-stand-17cm.png',
})


def blocked_capture_hashes():
    """Optional local quarantine; never serve or distribute this file."""
    path = ROOT / '.local' / 'blocked-capture-hashes.json'
    if not path.exists():
        return frozenset()
    values = json.loads(path.read_text())
    if not isinstance(values, list) or any(
        not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v)
        for v in values
    ):
        raise ValueError('Invalid local capture quarantine')
    return frozenset(values)


BLOCKED_CAPTURE_HASHES = blocked_capture_hashes()


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):
        pass

    def send_head(self):
        if self.headers.get('Host', '') not in ALLOWED_HOSTS:
            self.send_error(403)
            return None
        path = unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
        if (path not in PUBLIC_ASSETS or not (ROOT / path).is_file()
                or (ROOT / path).resolve() != ROOT / path):
            self.send_error(404)
            return None
        self.path = "/" + path
        return super().send_head()

    def do_POST(self):
        if (self.headers.get('Host', '') not in ALLOWED_HOSTS
                or self.headers.get('Origin', '') not in ALLOWED_ORIGINS
                or self.headers.get('X-Spatial-Local') != '1'):
            self.send_error(403)
            return
        if self.path not in ('/api/analyze', '/api/labels', '/api/labels.pdf'):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.send_error(400)
            return
        if not 0 < length <= 25 * 1024 * 1024:
            self.send_error(413)
            return
        try:
            data = self.rfile.read(length)
            if self.path == '/api/analyze':
                result = analyze(data)
                if result['hash'] in BLOCKED_CAPTURE_HASHES:
                    result['identityConflict'] = 'Locally quarantined capture: label mismatch. Reprint and recapture.'
                body = json.dumps(result).encode()
                content = 'application/json'
            else:
                ids = parse_ids(data.decode('utf-8-sig'))
                if self.path.endswith('.pdf'):
                    body = pdf_bytes(ids)
                    content = 'application/pdf'
                else:
                    body = json.dumps([{'id': v, 'png': 'data:image/png;base64,'
                                       + base64.b64encode(qr_png(v)).decode()} for v in ids]).encode()
                    content = 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"Could not process input locally. Check file format and size."}')

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()


if __name__ == '__main__':
    host, port = '127.0.0.1', 8774
    print(f'Spatial Prep: http://{host}:{port} — local research software', flush=True)
    try:
        LocalServer((host, port), Handler).serve_forever()
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, 48, 98):
            pid = 'unknown'
            try:
                pid = subprocess.check_output(
                    ['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'],
                    text=True, stderr=subprocess.DEVNULL).strip().replace('\n', ', ')
            except Exception:
                pass
            print(f'Port {port} is already in use by PID {pid}. The app may already be running at http://{host}:{port}. '
                  'To inspect and stop it with confirmation, run: python stop_server.py', file=sys.stderr)
            raise SystemExit(0)
        raise
