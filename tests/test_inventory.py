import io
import json
import zipfile
from fastapi.testclient import TestClient
from test_api import client, create, photo, image_bytes, TOKEN
from server import create_app


def items(client):
    response = client.get('/api/v1/inventory')
    assert response.status_code == 200, response.text
    return response.json()['items']


def entry(item):
    return {'key': item['key'], 'revision': item['revision']}


def selection(item):
    return {'name': 'Synthetic experiment', 'actor': 'TEST-TECH', 'entries': [dict(entry(item),
        name=item['name'], tissue_id=item['photos'][0]['id'], identifier_id=None, confirmed=True)]}


def test_inventory_labels_selection_and_snapshot(client, tmp_path):
    block = photo(client, create(client)).json()
    original = items(client)[0]
    body = {'entries': [entry(original)], 'labels': [' OCT ', 'Pilot'], 'action': 'add', 'actor': 'TEST-TECH'}
    assert client.post('/api/v1/inventory/labels', json=body).status_code == 200
    updated = items(client)[0]
    assert updated['labels'] == ['oct', 'pilot']
    assert updated['revision'] != original['revision']
    assert client.post('/api/v1/inventory/labels', json=body).status_code == 409
    assert client.post('/api/v1/planning-selections', json=selection(original)).status_code == 409
    response = client.post('/api/v1/planning-selections', json=selection(updated))
    assert response.status_code == 201, response.text
    selection_id = response.json()['id']
    frozen = client.get('/api/v1/planning-selections/' + selection_id).json()
    assert frozen['items'][0]['block_id'] == block['id']
    assert frozen['items'][0]['photos'][0]['id'] == block['photos'][0]['id']
    body.update(entries=[entry(updated)], labels=['oct'], action='remove')
    assert client.post('/api/v1/inventory/labels', json=body).status_code == 200
    assert items(client)[0]['labels'] == ['pilot']
    assert client.get('/api/v1/planning-selections/' + selection_id).json()['items'][0]['labels'] == ['oct', 'pilot']
    destination = tmp_path / 'restored'
    with zipfile.ZipFile(io.BytesIO(client.get('/api/v1/backup').content)) as backup:
        backup.extractall(destination)
    restored = TestClient(create_app(destination, {'http://testserver'}, TOKEN), headers={'Authorization':'Bearer '+TOKEN})
    assert items(restored)[0]['labels'] == ['pilot']
    assert restored.get('/api/v1/planning-selections/' + selection_id).json() == frozen


def test_selection_rejects_wrong_photos_duplicate_names_and_unreviewed(client):
    photo(client, create(client, suffix='A1'))
    photo(client, create(client, suffix='B2'), 'blue')
    first, second = items(client)
    body = selection(first)
    body['entries'][0]['tissue_id'] = second['photos'][0]['id']
    assert client.post('/api/v1/planning-selections', json=body).status_code == 422
    body = selection(first); body['entries'][0]['confirmed'] = False
    assert client.post('/api/v1/planning-selections', json=body).status_code == 422
    body = selection(first); body['entries'][0]['identifier_id'] = body['entries'][0]['tissue_id']
    assert client.post('/api/v1/planning-selections', json=body).status_code == 422
    body = selection(first); body['entries'].append(selection(second)['entries'][0]); body['entries'][1]['name'] = body['entries'][0]['name']
    assert client.post('/api/v1/planning-selections', json=body).status_code == 422
    body = selection(first); body['entries'] *= 2
    assert client.post('/api/v1/planning-selections', json=body).status_code == 422
    assert client.post('/api/v1/planning-selections', json={'name':'Empty','actor':'TEST','entries':[]}).status_code == 422


def test_provisional_groups_and_labels_follow_confirmed_links(client, tmp_path):
    store = client.app.state.archive
    for color in ('red','blue'):
        path = tmp_path / (color+'.png'); path.write_bytes(image_bytes(color))
        store.import_image(path, barcodes=['TEST-PROVISIONAL'])
    group = items(client)[0]
    assert group['kind'] == 'candidate' and len(group['photos']) == 2 and group['block_id'] is None
    assert client.post('/api/v1/inventory/labels', json={'entries':[entry(group)],'labels':['frozen'],'actor':'TEST'}).status_code == 200
    group = items(client)[0]
    block = create(client)
    imported = group['photos'][0]
    assert client.post('/api/v1/imports/'+imported['id']+'/confirm', json={'block_id':block['id'],'expected_version':imported['version'],
        'expected_block_version':block['version'],'actor':'TEST'}).status_code == 200
    result = items(client)
    assert len(result) == 2
    assert all(item['labels'] == ['frozen'] for item in result)
    assert sum(len(item['photos']) for item in result) == 2
    assert client.post('/api/v1/planning-selections', json=selection(group)).status_code == 409


def test_bulk_labels_are_atomic(client):
    create(client, suffix='A1'); create(client, suffix='B2')
    first, second = items(client)
    body = {'entries':[entry(first),dict(entry(second),revision='0'*64)],'labels':['pilot'],'actor':'TEST'}
    assert client.post('/api/v1/inventory/labels', json=body).status_code == 409
    assert all(not item['labels'] for item in items(client))


def test_browser_photo_import_deduplicates_and_validates(client):
    response = client.post('/api/v1/inventory/photos', data={'actor':'TEST'}, files={'file':('synthetic.png',image_bytes(),'image/png')})
    assert response.status_code == 201, response.text
    assert response.json()['created']
    assert items(client)[0]['photos'][0]['filename'] == 'synthetic.png'
    assert not client.post('/api/v1/inventory/photos', data={'actor':'TEST'}, files={'file':('again.png',image_bytes(),'image/png')}).json()['created']
    assert client.post('/api/v1/inventory/photos', data={'actor':'TEST'}, files={'file':('bad.png',b'bad','image/png')}).status_code == 422
    assert not list(client.app.state.archive.directory.glob('*.upload'))


def test_planner_assets_api_auth_and_image_analysis(client):
    assert 'Start with your blocks' in client.get('/').text
    assert 'Block Archive' in client.get('/archive').text
    assert 'inventory-bridge.js' in client.get('/planner/').text
    assert "img-src 'self' data: blob:" in client.get('/planner/').headers['content-security-policy']
    for path in ('/planner/vision.py','/planner/../server.py','/planner/.localdata/api-token'):
        assert client.get(path).status_code == 404
    client.cookies.clear()
    assert client.get('/api/v1/inventory',headers={'Authorization':''}).status_code == 401
    assert client.post('/api/analyze', content=image_bytes(),headers={'Authorization':''}).status_code == 401
    assert client.post('/api/analyze', content=b'bad').status_code == 422
    result = client.post('/api/analyze', content=image_bytes())
    assert result.status_code == 200 and result.json()['calibration'] is None
    assert client.post('/api/labels', content='TEST-SYNTHETIC').json()[0]['id'] == 'TEST-SYNTHETIC'
    assert client.post('/api/labels.pdf', content='TEST-SYNTHETIC').content.startswith(b'%PDF')
    client.get('/')
    assert client.post('/api/v1/inventory/labels', json={'entries':[]},headers={'Authorization':''}).status_code == 403


def test_block_preview_is_cropped_cached_and_project_scoped(client,tmp_path):
    import io
    from pathlib import Path
    from PIL import Image,ImageDraw
    from test_api import create
    template=Path(__file__).resolve().parents[1]/'planner/artefacts/preview/FFPE-photography-A4.png'
    image=Image.open(template).convert('RGB')
    ImageDraw.Draw(image).rectangle((360,450,515,625),fill=(180,70,35))
    buffer=io.BytesIO();image.save(buffer,'PNG');raw=buffer.getvalue()
    block=create(client)
    response=client.post('/api/v1/blocks/'+block['id']+'/photos',files={'file':('test.png',raw,'image/png')},data={'actor':'TEST','kind':'baseline','expected_version':block['version']})
    assert response.status_code==201,response.text
    photo=response.json()['photos'][0]
    url=photo['url'].replace('/image','/block-preview')
    cropped=client.get(url);assert cropped.status_code==200,cropped.text
    with Image.open(io.BytesIO(cropped.content)) as output:
        assert output.size==(780,660)
        assert all(abs(a-b)<8 for a,b in zip(output.getpixel((390,330)),(180,70,35)))
    working_url=photo['url'].replace('/image','/experiment-image')
    working=client.get(working_url).json()
    assert working['mmPerPx']==.05 and working['framing']=='block-zone'
    assert (working['width'],working['height'])==(1300,1100)
    assert client.get(working_url).json()==working
    assert client.get(url).content==cropped.content
    assert client.get(photo['url']).content==raw
    other=client.post('/api/v1/projects',json={'name':'Separate project'}).json()['id']
    assert client.get(url,headers={'X-Archive-Project':other}).status_code==404
    assert client.get(working_url,headers={'X-Archive-Project':other}).status_code==404
    client.headers.pop('Authorization')
    assert client.get(url).status_code==401
    assert client.get(working_url).status_code==401


def test_large_original_does_not_limit_compact_experiment(client):
    block=photo(client,create(client)).json();item=items(client)[0]
    source=client.app.state.archive.images/(block['photos'][0]['id']+'.source')
    # A sparse synthetic file reproduces the former size gate without allocating 110 MB.
    with source.open('ab') as file:file.truncate(110*1024*1024)
    response=client.post('/api/v1/planning-selections',json=selection(item))
    assert response.status_code==201,response.text
    asset=client.get(block['photos'][0]['url'].replace('/image','/experiment-image'))
    assert asset.status_code==200
    assert asset.json()['mmPerPx'] is None
    assert len(asset.content)<100000
