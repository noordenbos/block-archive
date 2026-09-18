"""Local desktop launcher: per-user storage, single instance and browser controls."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser

VERSION = '1.0.0-preview.1'
ROOT = Path(__file__).resolve().parents[1]


def user_directory():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/Block Archive'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Block Archive'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'block-archive'


def save_json(path, value):
    fd, name = tempfile.mkstemp(prefix='.desktop-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(value, target)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def instance_lock(directory):
    handle = (directory / 'desktop.lock').open('a+b')
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b'0'); handle.flush()
    handle.seek(0)
    try:
        if sys.platform == 'win32':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        handle.close()


def storage_directory(home):
    settings = home / 'settings.json'
    data = json.loads(settings.read_text()) if settings.exists() else {}
    path = Path(data.get('data_directory', home / 'archive')).expanduser().resolve()
    if not path.is_absolute():
        raise ValueError('Storage location must be an absolute path.')
    return path


def configure_storage(home, raw):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 4096:
        raise ValueError('Enter the full path to a local folder.')
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError('Use an absolute folder path.')
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Refuse arbitrary nonempty folders: a new dedicated folder or an existing archive only.
    visible = [entry for entry in path.iterdir() if entry.name not in ('.DS_Store', 'desktop.ini')]
    if visible and not (path / 'archive.sqlite3').is_file():
        raise ValueError('Choose an empty folder or an existing Block Archive data folder.')
    if (path / 'archive.sqlite3').exists():
        import sqlite3
        with sqlite3.connect(f'file:{path / "archive.sqlite3"}?mode=ro', uri=True) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'blocks', 'photos', 'events'}.issubset(tables):
                raise ValueError('This is not a Block Archive database.')
    with tempfile.TemporaryFile(dir=path):
        pass
    save_json(home / 'settings.json', {'data_directory': str(path)})
    return path


def desktop_app(home, directory, port, key, stop, restart):
    from fastapi import Depends, HTTPException, Request
    from fastapi.responses import FileResponse
    from block_archive.server import create_app
    origin = f'http://127.0.0.1:{port}'
    app = create_app(directory, {origin, f'http://localhost:{port}'})
    def authorized(request: Request):
        if request.headers.get('origin') not in (None, origin):
            raise HTTPException(403, 'Use the local desktop controls.')
        supplied = request.headers.get('x-desktop-key') or request.cookies.get('block_archive_desktop', '')
        if not secrets.compare_digest(supplied, key):
            raise HTTPException(401, 'Open Block Archive from its desktop shortcut.')
        if request.method != 'GET' and (request.headers.get('origin') != origin or request.headers.get('x-archive-request') != '1'):
            raise HTTPException(403, 'Use the local desktop controls.')
    @app.get('/desktop', include_in_schema=False)
    def controls():
        response = FileResponse(ROOT / 'desktop_resources/index.html')
        response.set_cookie('block_archive_desktop', key, httponly=True, samesite='strict', path='/desktop')
        return response
    @app.get('/desktop/assets/{name}', include_in_schema=False)
    def asset(name: str):
        if name not in ('desktop.js', 'desktop.css'):
            raise HTTPException(404)
        return FileResponse(ROOT / 'desktop_resources' / name)
    @app.get('/desktop/status', dependencies=[Depends(authorized)], include_in_schema=False)
    def status():
        return {'application': 'Block Archive desktop', 'version': VERSION,
                'storage': str(directory), 'first_run': not (home / 'settings.json').exists()}
    @app.post('/desktop/ready', dependencies=[Depends(authorized)], include_in_schema=False)
    def ready():
        save_json(home / 'settings.json', {'data_directory': str(directory)})
        return {'ok': True}
    @app.post('/desktop/storage', dependencies=[Depends(authorized)], include_in_schema=False)
    async def storage(request: Request):
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('Enter a folder path.')
            path = configure_storage(home, body.get('path'))
        except (ValueError, OSError) as exc:
            raise HTTPException(422, 'Choose an empty, writable local folder or a valid archive folder.') from exc
        if path != directory:
            threading.Timer(.5, restart).start()
        return {'restarting': path != directory}
    @app.post('/desktop/quit', dependencies=[Depends(authorized)], include_in_schema=False)
    def quit_app():
        threading.Timer(.3, stop).start()
        return {'ok': True}
    return app


def serve(home, directory, open_browser=True, smoke=False):
    import uvicorn
    address = socket.socket()
    address.bind(('127.0.0.1', 0))
    port = address.getsockname()[1]
    key = secrets.token_urlsafe(36)
    should_restart = []
    server = None
    def stop():
        server.should_exit = True
    def restart():
        should_restart.append(True); stop()
    app = desktop_app(home, directory, port, key, stop, restart)
    # A windowed executable has no stdout/stderr; avoid console logging and request data.
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, log_level='critical'))
    errors = []
    def after_start():
        for _ in range(600):
            if server.started:
                break
            time.sleep(.05)
        else:
            errors.append('Local server did not start.'); stop(); return
        url = f'http://127.0.0.1:{port}'
        save_json(home / 'desktop-instance.json', {'url': url, 'key': key})
        if smoke:
            try:
                for route in ('/', '/desktop', '/static/inventory.js', '/planner/', '/api/v1/health'):
                    with urllib.request.urlopen(url+route) as response:
                        assert response.status == 200
                request = urllib.request.Request(url+'/desktop/status', headers={'x-desktop-key': key})
                with urllib.request.urlopen(request) as response:
                    assert json.load(response)['application'] == 'Block Archive desktop'
                # Exercise the native image dependency and bundled template.
                from block_archive.vision import reference_markers
                assert len(reference_markers()) == 4
                # Exercise database creation and a real backup using only the empty test archive.
                app.state.archive.backup(home / 'synthetic-backup.zip')
            except Exception as exc:
                errors.append(type(exc).__name__)
            finally:
                stop()
        elif open_browser:
            webbrowser.open(url+'/desktop')
    helper = threading.Thread(target=after_start, daemon=True)
    helper.start()
    try:
        server.run(sockets=[address])
    finally:
        address.close()
        helper.join(timeout=2)
        (home / 'desktop-instance.json').unlink(missing_ok=True)
    if errors:
        raise RuntimeError('Desktop startup check failed: ' + ', '.join(errors))
    return bool(should_restart)


def reopen(home):
    for _ in range(200):
        try:
            data = json.loads((home / 'desktop-instance.json').read_text())
            url = data['url']
            if not url.startswith('http://127.0.0.1:'):
                return False
            request = urllib.request.Request(url+'/desktop/status', headers={'x-desktop-key': data['key']})
            with urllib.request.urlopen(request, timeout=2) as response:
                if json.load(response)['application'] == 'Block Archive desktop':
                    webbrowser.open(url+'/desktop'); return True
        except (OSError, ValueError, KeyError):
            time.sleep(.1)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--desktop-home', type=Path, help='Override desktop settings location, primarily for isolated tests')
    args = parser.parse_args()
    os.umask(0o077)
    if args.smoke_test:
        with tempfile.TemporaryDirectory(prefix='block-archive-desktop-test-') as folder:
            home = Path(folder)
            serve(home, home/'archive', open_browser=False, smoke=True)
        return
    home = (args.desktop_home or user_directory()).resolve()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with instance_lock(home) as owned:
        if not owned:
            if not reopen(home):
                raise RuntimeError('Block Archive is starting or could not be reached. Try opening it again.')
            return
        while serve(home, storage_directory(home), open_browser=not args.no_browser):
            pass
