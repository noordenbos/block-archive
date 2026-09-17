"""Portable project round-trips and isolation use only synthetic records/photos."""
import base64
import copy
import json
from fastapi.testclient import TestClient
from test_api import client, create, photo, TOKEN
import capture_review
import inventory
import metadata


def experiment():
    return {'version':1,'name':'Synthetic plan','experimentId':'test-plan','blocks':[],
            'slides':[{'id':'slide-one','name':'SLIDE-001','placements':[]}],
            'config':{'assay':'Xenium','product':'test','source':'','revision':'','width':10,'height':22,'margin':.5,'gap':.5,'verified':False}}


def populated_export(client):
    block=create(client)
    response=photo(client,block)
    assert response.status_code == 201
    store=client.app.state.archive
    item=inventory.list_items(store)[0]
    capture_review.save_review(store,item['key'],item['revision'],[{'photo_id':item['photos'][0]['id'],'group_name':item['name'],'role':'tissue'}],'TEST',True,'identifier')
    item=inventory.list_items(store)[0]
    inventory.label_items(store,[{'key':item['key'],'revision':item['revision']}],['frozen'],'add','TEST')
    metadata.save(store,[{'matching_id':item['name'],'fields':{'Material':'OCT','Cohort':'Synthetic'},'expected_version':0}],'TEST','fill')
    entries=[{'key':'current','value':experiment()},{'key':'experiment:test-plan','value':experiment()}]
    response=client.post('/api/v1/projects/export',json={'entries':entries})
    assert response.status_code == 200,response.text
    return response.json(),inventory.list_items(store)


def test_full_project_roundtrip(client):
    document,before=populated_export(client)
    assert len(document['archive']['images']) == 2
    assert 'api-token' not in json.dumps(document)
    response=client.post('/api/v1/projects/import',files={'file':('project.json',json.dumps(document),'application/json')})
    assert response.status_code == 201,response.text
    ident=response.json()['id']
    assert client.get('/api/v1/inventory').json()['items']==before
    headers={'X-Archive-Project':ident}
    assert client.get('/api/v1/inventory',headers=headers).json()['items']==before
    assert client.get('/api/v1/projects/'+ident+'/experiments').json()==document['experiments']
    again=client.post('/api/v1/projects/export',json=document['experiments'],headers=headers).json()
    assert again['archive']==document['archive']
    assert again['experiments']==document['experiments']
    for image in document['archive']['images']:
        assert (client.app.state.projects.directory(ident)/'images'/image['name']).read_bytes()==base64.b64decode(image['data'])


def test_new_project_and_stale_browser_tab(client):
    create(client)
    initial=client.get('/api/v1/inventory').json()
    with TestClient(client.app) as browser:
        browser.get('/')
        headers={'Origin':'http://testserver','X-Archive-Request':'1','X-Archive-Project':'local'}
        new=browser.post('/api/v1/projects',json={'name':'Fresh archive'},headers=headers)
        assert new.status_code==201
        ident=new.json()['id']
        assert browser.post('/api/v1/projects/'+ident+'/open',json={},headers=headers).status_code==200
        assert browser.get('/api/v1/project').json()['id']==ident
        assert browser.get('/api/v1/inventory',headers={'X-Archive-Project':ident}).json()=={'items':[]}
        assert browser.get('/api/v1/inventory',headers={'X-Archive-Project':'local'}).status_code==409
        assert browser.post('/api/v1/projects',json={'name':'stale tab'},headers=headers).status_code==409
        assert browser.post('/api/v1/projects',json={'name':'unguarded'},headers={'Origin':'http://testserver','X-Archive-Request':'1'}).status_code==409
        assert browser.post('/api/labels',content='TEST-QR',headers={'Origin':'http://testserver','X-Archive-Request':'1'}).status_code==200
        headers['X-Archive-Project']=ident
        assert browser.post('/api/v1/projects/local/open',json={},headers=headers).status_code==200
        assert browser.get('/api/v1/inventory').json()==initial
    # Token clients continue to use the original inventory unless explicitly selecting a project.
    assert client.get('/api/v1/inventory').json()==initial


def test_invalid_project_never_changes_existing_data(client):
    document,before=populated_export(client)
    variants=[]
    bad=copy.deepcopy(document);bad['archive']['images'][0]['name']='../api-token';variants.append(bad)
    bad=copy.deepcopy(document);bad['archive']['images'][0]['data']=base64.b64encode(b'tampered').decode();variants.append(bad)
    bad=copy.deepcopy(document);bad['archive']['tables']['blocks'][0]['unexpected']='value';variants.append(bad)
    bad=copy.deepcopy(document);bad['archive']['tables']['inventory_metadata'][0]['fields']='[]';variants.append(bad)
    bad=copy.deepcopy(document);bad['experiments']['entries'][0]['key']='arbitrary-key';variants.append(bad)
    for bad in variants:
        response=client.post('/api/v1/projects/import',files={'file':('project.json',json.dumps(bad),'application/json')})
        assert response.status_code==422,response.text
        assert client.get('/api/v1/inventory').json()['items']==before
        assert len(client.get('/api/v1/projects').json()['items'])==1
    assert client.post('/api/v1/projects/local/open',json={}).status_code==200
    assert client.post('/api/v1/projects/not-a-project/open',json={}).status_code==404


def test_older_project_without_missing_side_column(client):
    document,_=populated_export(client)
    for row in document['archive']['tables']['capture_reviews']:
        row.pop('missing_side')
    response=client.post('/api/v1/projects/import',files={'file':('old.json',json.dumps(document),'application/json')})
    assert response.status_code==201,response.text
    item=client.get('/api/v1/inventory').json()['items'][0]
    assert item['qc']['status']=='ready'
    assert item['qc']['missing_side']=='identifier'


def test_local_saves_default_custom_and_project_isolation(client,tmp_path):
    from pathlib import Path
    document,_=populated_export(client)
    root=client.app.state.archive.directory
    state=experiment()
    response=client.post('/api/v1/local-saves/experiment',json=state)
    assert response.status_code==200,response.text
    saved=Path(response.json()['path'])
    assert saved.parent==root/'saved'
    assert json.loads(saved.read_text())==state
    state['name']='Changed plan'
    assert client.post('/api/v1/local-saves/experiment',json=state).json()['path']==str(saved)
    assert json.loads(saved.read_text())['name']=='Changed plan'
    entries=client.get('/api/v1/projects/local/experiments').json()['entries']
    assert any(e['value']['name']=='Changed plan' for e in entries)
    custom=tmp_path/'custom';custom.mkdir()
    response=client.post('/api/v1/save-location',json={'folder':str(custom)})
    assert response.status_code==200,response.text
    assert response.json()['destination']==str(custom/'BlockArchive/local')
    response=client.post('/api/v1/local-saves/project',json=document['experiments'])
    assert response.status_code==200,response.text
    project_file=Path(response.json()['path'])
    assert project_file.parent==custom/'BlockArchive/local'
    assert json.loads(project_file.read_text())['archive']==document['archive']
    other=client.post('/api/v1/projects',json={'name':'Separate saves'}).json()['id']
    other_location=client.get('/api/v1/save-location',headers={'X-Archive-Project':other}).json()
    assert other_location['default'] and other_location['destination']!=str(project_file.parent)
    assert client.post('/api/v1/save-location',json={'folder':'relative/path'}).status_code==422
    invalid={**state,'experimentId':'../../escape'}
    assert client.post('/api/v1/local-saves/experiment',json=invalid).status_code==422
    assert client.post('/api/v1/save-location',json={'folder':''}).json()['default']
    assert saved.exists() and project_file.exists()


def test_failed_local_save_preserves_previous_file(client,monkeypatch):
    import local_saves
    from pathlib import Path
    state=experiment()
    response=client.post('/api/v1/local-saves/experiment',json=state)
    path=Path(response.json()['path']);before=path.read_bytes()
    def fail_replace(*args):raise OSError('Synthetic disk error')
    monkeypatch.setattr(local_saves.os,'replace',fail_replace)
    state['name']='Unsaved edit'
    assert client.post('/api/v1/local-saves/experiment',json=state).status_code==422
    assert path.read_bytes()==before
    assert not list(path.parent.glob('.saving-*'))
