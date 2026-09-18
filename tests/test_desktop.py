"""Desktop lifecycle and data separation checks using temporary archives."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from block_archive.desktop import configure_storage, storage_directory, instance_lock, desktop_app
from block_archive.archive import Archive


def test_storage_switch_preserves_previous_archive_and_rejects_unrelated_folder(tmp_path):
    home=tmp_path/'settings';home.mkdir()
    original=storage_directory(home)
    Archive(original)
    before=(original/'archive.sqlite3').read_bytes()
    unrelated=tmp_path/'unrelated';unrelated.mkdir();(unrelated/'important.txt').write_text('Keep me')
    with pytest.raises(ValueError):configure_storage(home,str(unrelated))
    assert not (home/'settings.json').exists()
    destination=tmp_path/'new-archive'
    configure_storage(home,str(destination))
    assert storage_directory(home)==destination
    assert (original/'archive.sqlite3').read_bytes()==before
    assert (unrelated/'important.txt').read_text()=='Keep me'
    configure_storage(home,str(original))
    assert storage_directory(home)==original


def test_single_instance_lock_releases(tmp_path):
    with instance_lock(tmp_path) as first:
        assert first
        with instance_lock(tmp_path) as second:assert not second
    with instance_lock(tmp_path) as third:assert third


def test_desktop_controls_require_local_session_and_origin(tmp_path):
    home=tmp_path/'home';home.mkdir()
    app=desktop_app(home,home/'archive',8789,'synthetic-desktop-session-key',lambda:None,lambda:None)
    with TestClient(app,base_url='http://127.0.0.1:8789') as client:
        assert client.get('/desktop/status').status_code==401
        assert client.post('/desktop/ready',json={}).status_code==401
        assert client.get('/desktop').status_code==200
        assert client.get('/desktop/status').json()['first_run']
        assert client.post('/desktop/ready',json={}).status_code==403
        headers={'Origin':'http://evil.example','X-Archive-Request':'1'}
        assert client.post('/desktop/ready',json={},headers=headers).status_code==403
        headers['Origin']='http://127.0.0.1:8789'
        assert client.post('/desktop/ready',json={},headers=headers).status_code==200
        assert not client.get('/desktop/status').json()['first_run']
        assert client.get('/desktop/assets/api-token').status_code==404
        assert json.loads((home/'settings.json').read_text())['data_directory']==str(home/'archive')


def test_planner_supports_bundle_resource_link_but_rejects_escape(tmp_path,monkeypatch):
    import block_archive.server as server
    resources=tmp_path/'resources';(resources/'planner').mkdir(parents=True)
    (resources/'planner/index.html').write_text('Synthetic planner')
    root=tmp_path/'bundle';root.mkdir()
    try:(root/'planner').symlink_to(resources/'planner',target_is_directory=True)
    except OSError:pytest.skip('Symlinks require platform permissions')
    monkeypatch.setattr(server,'ROOT',root)
    app=server.create_app(tmp_path/'archive',{'http://testserver'},'synthetic-api-token-long-enough')
    with TestClient(app) as client:
        assert client.get('/planner/').text=='Synthetic planner'
        secret=tmp_path/'private.txt';secret.write_text('private')
        (resources/'planner/app.js').symlink_to(secret)
        assert client.get('/planner/app.js').status_code==404
