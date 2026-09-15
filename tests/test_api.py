import io
import zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from archive import Archive
from server import create_app

TOKEN = 'test-token-used-only-for-synthetic-tests'


def image_bytes(color='gold'):
    output = io.BytesIO()
    Image.new('RGB', (160, 120), color).save(output, 'PNG')
    return output.getvalue()


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, {'http://testserver'}, TOKEN)
    with TestClient(app, headers={'Authorization': 'Bearer ' + TOKEN}) as client:
        yield client


def create(client, number='001234', suffix='B4', code=None):
    payload = {'block_code': code or f'TEST-2026-{number}-{suffix}', 'archive_year': 2026,
               'case_number': number, 'subspecimen': suffix[0], 'cassette_number': int(suffix[1:]),
               'description': 'Synthetic tissue example', 'actor': 'TEST-TECH'}
    response = client.post('/api/v1/blocks', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def move(client, block, action, **extra):
    return client.post(f'/api/v1/blocks/{block["id"]}/{action}', json={
        'actor': 'TEST-TECH', 'expected_version': block['version'], **extra})


def photo(client, block, color='gold', kind='baseline'):
    return client.post(f'/api/v1/blocks/{block["id"]}/photos',
                       data={'actor': 'TEST-TECH', 'expected_version': block['version'], 'kind': kind},
                       files={'file': ('synthetic.png', image_bytes(color), 'image/png')})


def archive_initial(client, block):
    response = photo(client, block)
    assert response.status_code == 201, response.text
    block = response.json()
    response = move(client, block, 'rearchive', photo_id=block['photos'][0]['id'])
    assert response.status_code == 200, response.text
    return response.json()


def test_full_cut_return_cycle_and_images(client):
    block = archive_initial(client, create(client))
    baseline = block['current_photo_id']
    assert block['status'] == 'archived'
    assert block['location'] == '2026-001234 / B4'
    block = move(client, block, 'checkout').json()
    assert block['cycle'] == 1 and block['status'] == 'checked_out'
    assert photo(client, block, 'red', 'post_cut').status_code == 409
    block = move(client, block, 'complete-cut').json()
    assert move(client, block, 'rearchive', photo_id=baseline).status_code == 409
    assert photo(client, block, kind='post_cut').status_code == 409
    response = photo(client, block, 'orange', 'post_cut')
    assert response.status_code == 201, response.text
    block = response.json(); new_photo = block['photos'][0]
    block = move(client, block, 'rearchive', photo_id=new_photo['id'], note='Filed in sequence').json()
    assert block['status'] == 'archived' and block['current_photo_id'] != baseline
    assert len(block['photos']) == 2
    assert client.get(new_photo['url']).content == image_bytes('orange')
    thumbnail = client.get(new_photo['thumbnail_url'])
    assert thumbnail.status_code == 200 and not Image.open(io.BytesIO(thumbnail.content)).getexif()
    assert [event['type'] for event in reversed(block['events'])] == [
        'registered', 'photo_added', 'rearchive', 'checkout', 'complete_cut', 'photo_added', 'rearchive']


def test_archive_order_case_lookup_and_link_search(client):
    for suffix in ('B10', 'B4', 'A1'):
        create(client, suffix=suffix)
    create(client, '000002')
    results = client.get('/api/v1/blocks').json()['items']
    assert [(b['case_number'], b['subspecimen'], b['cassette_number']) for b in results] == [
        ('000002', 'B', 4), ('001234', 'A', 1), ('001234', 'B', 4), ('001234', 'B', 10)]
    siblings = client.get('/api/v1/blocks', params={'year': 2026, 'case_number': '1234'}).json()
    assert siblings['total'] == 3
    assert client.get('/api/v1/blocks', params={'query': '1234'}).json()['total'] == 3
    assert client.get('/api/v1/blocks', params={'query': '2026-1234'}).json()['total'] == 3
    assert client.get('/api/v1/blocks', params={'query': '2026-1234-B4'}).json()['total'] == 1
    block = results[-1]
    lookup = client.get('/api/v1/blocks/by-code', params={'block_code': block['block_code'].lower()})
    assert lookup.json()['id'] == block['id']
    response = client.put(f'/api/v1/blocks/{block["id"]}/external-links', json={
        'actor': 'TEST-TECH', 'expected_version': block['version'], 'system': 'Synthetic dataset',
        'external_id': 'TEST-RESEARCH-LINK-42', 'url': 'https://example.org/test-record'})
    assert response.status_code == 200, response.text
    assert client.get('/api/v1/blocks', params={'query': 'research-link'}).json()['total'] == 1
    assert client.get('/api/v1/blocks', params={'query': "' OR 1=1; --"}).status_code == 200
    results = client.get('/api/v1/blocks', params={'limit': 2}).json()
    assert results['next_offset'] == 2
    assert client.get('/api/v1/blocks', params={'offset': 2, 'limit': 2}).json()['next_offset'] is None


def test_duplicate_identity_and_punctuation(client):
    block = create(client, code='TEST/2026/001234/B4')
    assert client.get('/api/v1/blocks/by-code', params={'block_code': block['block_code']}).json()['id'] == block['id']
    payload = {'block_code': 'ANOTHER-CODE', 'archive_year': 2026, 'case_number': '1234',
               'subspecimen': 'B', 'cassette_number': 4, 'actor': 'TEST-TECH'}
    assert client.post('/api/v1/blocks', json=payload).status_code == 409
    assert len(client.get('/api/v1/events').json()['items']) == 1


def test_stale_updates_and_invalid_transitions(client):
    initial = create(client)
    assert move(client, initial, 'checkout').status_code == 409
    fresh = photo(client, initial).json()
    assert move(client, initial, 'rearchive', photo_id=fresh['photos'][0]['id']).status_code == 409
    other = create(client, suffix='A1')
    assert move(client, other, 'rearchive', photo_id=fresh['photos'][0]['id']).status_code == 409
    reference = photo(client, other, 'blue', 'reference').json()
    assert move(client, reference, 'rearchive', photo_id=reference['photos'][0]['id']).status_code == 409


def test_validation_and_private_files(client):
    block = create(client)
    response = client.post(f'/api/v1/blocks/{block["id"]}/photos',
        data={'actor': 'TEST-TECH', 'expected_version': block['version'], 'kind': 'baseline'},
        files={'file': ('bad.png', b'not an image', 'image/png')})
    assert response.status_code == 422
    for path in ('/.git/config', '/.localdata/api-token', '/archive.py', '/static/../server.py', '/static/nope'):
        assert client.get(path).status_code == 404
    assert client.get('/api/v1/blocks', headers={'Host': 'hostile.invalid'}).status_code == 403
    assert client.get('/api/v1/blocks', headers={'Authorization': '', 'Origin': 'https://example.org'}).status_code == 403
    assert client.get('/api/v1/blocks', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/v1/blocks', params={'limit': 10000}).status_code == 422
    assert not list(client.app.state.archive.images.iterdir())


def test_cookie_session_csrf_and_schema(tmp_path):
    app = create_app(tmp_path, {'http://testserver'}, TOKEN)
    with TestClient(app) as browser:
        assert browser.get('/api/v1/blocks').status_code == 401
        response = browser.get('/')
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
        assert browser.get('/api/v1/blocks').status_code == 200
        payload = {'actor': 'TEST-TECH', 'block_code': 'TEST-CASE-B4', 'archive_year': 2026,
                   'case_number': '1', 'subspecimen': 'B', 'cassette_number': 4}
        assert browser.post('/api/v1/blocks', json=payload).status_code == 403
        response = browser.post('/api/v1/blocks', json=payload,
                                headers={'Origin': 'http://testserver', 'X-Archive-Request': '1'})
        assert response.status_code == 201
        schema = browser.get('/openapi.json').json()
        assert 'HTTPBearer' in schema['components']['securitySchemes']
        assert schema['paths']['/api/v1/blocks/by-code']['get']['security']


def test_event_cursor_and_consistent_backup(client, tmp_path):
    block = archive_initial(client, create(client))
    first = client.get('/api/v1/events', params={'limit': 2}).json()
    rest = client.get('/api/v1/events', params={'after': first['next_cursor']}).json()
    assert first['has_more'] and not rest['has_more']
    assert {e['sequence'] for e in first['items']}.isdisjoint(e['sequence'] for e in rest['items'])
    response = client.get('/api/v1/backup')
    assert response.status_code == 200
    destination = tmp_path / 'restored'; destination.mkdir()
    with zipfile.ZipFile(io.BytesIO(response.content)) as backup:
        assert set(backup.namelist()) == {'archive.sqlite3', f'images/{block["current_photo_id"]}.source', f'images/{block["current_photo_id"]}.jpg'}
        backup.extractall(destination)
    restored = Archive(destination).by_code(block['block_code'])
    assert restored['id'] == block['id'] and restored['status'] == 'archived'
    assert len(restored['photos']) == 1
    assert not list(client.app.state.archive.directory.glob('block-archive-*.zip'))


def test_persistence_across_server_restart(tmp_path):
    app = create_app(tmp_path, {'http://testserver'}, TOKEN)
    with TestClient(app, headers={'Authorization': 'Bearer ' + TOKEN}) as client:
        original = archive_initial(client, create(client))
    again = create_app(tmp_path, {'http://testserver'}, TOKEN)
    with TestClient(again, headers={'Authorization': 'Bearer ' + TOKEN}) as client:
        saved = client.get('/api/v1/blocks/by-code', params={'block_code': original['block_code']}).json()
        assert saved['id'] == original['id'] and len(saved['photos']) == 1


def test_concurrent_checkout_records_one_cycle(client):
    from concurrent.futures import ThreadPoolExecutor
    block = archive_initial(client, create(client))
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: move(client, block, 'checkout').status_code, range(2)))
    assert sorted(statuses) == [200, 409]
    saved = client.get(f'/api/v1/blocks/{block["id"]}').json()
    assert saved['cycle'] == 1
    assert len([e for e in saved['events'] if e['type'] == 'checkout']) == 1


def test_post_cut_from_previous_cycle_stays_invalid(client):
    block = archive_initial(client, create(client))
    block = move(client, block, 'checkout').json()
    block = move(client, block, 'complete-cut').json()
    block = photo(client, block, 'orange', 'post_cut').json()
    previous = block['photos'][0]['id']
    block = move(client, block, 'rearchive', photo_id=previous).json()
    block = move(client, block, 'checkout').json()
    block = move(client, block, 'complete-cut').json()
    assert move(client, block, 'rearchive', photo_id=previous).status_code == 409
    assert client.get(f'/api/v1/blocks/{block["id"]}').json()['status'] == 'awaiting_archive'


def test_import_inbox_search_confirm_and_backup(client, tmp_path):
    store = client.app.state.archive
    source = tmp_path / 'camera.png'
    original = image_bytes('purple')
    source.write_bytes(original)
    image_id, created = store.import_image(source, label_text='TEST-CASE-LABEL', barcodes=['TEST-CODE'])
    assert created
    assert store.import_image(source)[1] is False
    assert source.read_bytes() == original
    results = client.get('/api/v1/imports', params={'query': 'TEST-CODE'}).json()
    assert results['total'] == results['pending'] == 1
    entry = results['items'][0]
    assert client.get(entry['url']).content == original
    assert not Image.open(io.BytesIO(client.get(entry['thumbnail_url']).content)).getexif()
    assert client.get('/api/v1/imports', params={'query': "' OR 1=1; --"}).status_code == 200
    # Pending images must survive backup/restore, even before any block exists.
    backup = tmp_path / 'pending.zip'
    store.backup(backup)
    restored = tmp_path / 'restored'
    with zipfile.ZipFile(backup) as bundle:
        bundle.extractall(restored)
    assert Archive(restored).inbox_path(image_id)[0].read_bytes() == original
    block = create(client)
    body = {'actor': 'TEST-TECH', 'block_id': block['id'], 'expected_version': 1,
            'expected_block_version': block['version']}
    route = f'/api/v1/imports/{image_id}/confirm'
    assert client.post(route, json=body | {'expected_block_version': 999}).status_code == 409
    assert client.get('/api/v1/imports').json()['pending'] == 1
    response = client.post(route, json=body)
    assert response.status_code == 200
    block = response.json()
    assert block['photos'][0]['kind'] == 'reference'
    assert block['status'] == 'awaiting_archive' and block['cycle'] == 0
    assert block['current_photo_id'] is None and block['cut_completed_at'] is None
    assert move(client, block, 'rearchive', photo_id=image_id).status_code == 409
    assert client.post(route, json=body).status_code == 409
    assert client.get('/api/v1/imports').json()['pending'] == 0
    assert client.get('/api/v1/imports', params={'status': 'linked'}).json()['total'] == 1
    assert client.get(block['photos'][0]['url']).content == original
    store.backup(tmp_path / 'linked.zip')
    with zipfile.ZipFile(tmp_path / 'linked.zip') as bundle:
        assert len(bundle.namelist()) == len(set(bundle.namelist()))
    with TestClient(client.app) as anonymous:
        assert anonymous.get('/api/v1/imports').status_code == 401
        assert anonymous.get(entry['url']).status_code == 401
        assert anonymous.post(route, json=body).status_code == 401


def test_folder_import_resume_and_reject_invalid(client, tmp_path):
    from tools.import_folder import import_folder
    folder = tmp_path / 'input'
    folder.mkdir()
    (folder / 'one.jpg').write_bytes(image_bytes())
    (folder / 'duplicate.jpg').write_bytes(image_bytes())
    (folder / 'bad.jpg').write_bytes(b'not an image')
    counts, _ = import_folder(client.app.state.archive, folder)
    assert counts == {'failed': 1, 'imported': 1, 'already_present': 1}
    counts, _ = import_folder(client.app.state.archive, folder)
    assert counts == {'failed': 1, 'already_present': 2}
    assert client.get('/api/v1/imports').json()['pending'] == 1
