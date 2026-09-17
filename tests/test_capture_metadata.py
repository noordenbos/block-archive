import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from test_api import client, create, photo, image_bytes, TOKEN
from test_inventory import items, selection, entry
from server import create_app
import capture_review


def preview(client, text, column=None):
    return client.post('/api/v1/metadata/preview',json={'text':text,'id_column':column})


def apply(client, result, mode='fill'):
    return client.post('/api/v1/metadata',json={'actor':'TEST','mode':mode,'entries':[
        {key:row[key] for key in ('matching_id','fields','expected_version')} for row in result['rows']]})


def test_metadata_csv_quoting_matching_and_waiting_ids(client):
    create(client,code='00042')
    response=preview(client,'\ufeffMatching ID,Material,Description\r\n00042,OCT,"Lung, left"\r\nFUTURE,FFPE,"Line one\nLine two"\r\n')
    assert response.status_code==200,response.text
    result=response.json();assert result['matched']==1 and result['unmatched']==1
    assert result['rows'][0]['matching_id']=='00042'
    assert apply(client,result).status_code==200
    assert items(client)[0]['metadata']=={'Material':'OCT','Description':'Lung, left'}
    create(client,number='2',code='future')
    assert next(item for item in items(client) if item['name']=='future')['metadata']['Material']=='FFPE'


def test_pasted_table_column_choice_and_duplicates(client):
    text='Material\tCustom key\tCohort\nOCT\tTEST-A\tPilot\nOCT\tTEST-B\tPilot\n'
    schema=client.post('/api/v1/metadata/columns',json={'text':text})
    assert schema.status_code==200 and 'Custom key' in schema.json()['headers']
    assert preview(client,text).status_code==422
    result=preview(client,text,'Custom key').json()
    assert result['rows'][0]['matching_id']=='TEST-A'
    assert apply(client,result).status_code==200
    assert preview(client,'ID,x\nSame,1\n same ,2').status_code==422
    assert preview(client,'ID,x,X\nA,1,2').status_code==422
    assert preview(client,'ID,x\nA,1,extra').status_code==422


def test_metadata_merge_overwrite_clear_and_atomic_versions(client):
    first=preview(client,'ID,Material,Project\nTEST-A,OCT,Pilot\nTEST-B,FFPE,Archive').json()
    assert apply(client,first).status_code==200
    next_preview=preview(client,'ID,material,Project,Site\nTEST-A,FFPE,,North').json()
    assert next_preview['conflicts']==1
    assert apply(client,next_preview).status_code==200
    rows=client.get('/api/v1/metadata').json()['records'];a=next(row for row in rows if row['matching_id']=='TEST-A')
    assert a['fields']=={'Material':'OCT','Project':'Pilot','Site':'North'}
    assert apply(client,next_preview,'overwrite').status_code==409
    fresh=preview(client,'ID,material,Project\nTEST-A,FFPE,').json()
    assert apply(client,fresh,'overwrite').status_code==200
    a=next(row for row in client.get('/api/v1/metadata').json()['records'] if row['matching_id']=='TEST-A')
    assert a['fields']['Material']=='FFPE' and a['fields']['Project']=='Pilot'
    before=client.get('/api/v1/metadata').json()
    payload={'actor':'TEST','mode':'replace','entries':[{'matching_id':'TEST-A','fields':{'Project':''},'expected_version':a['version']},
        {'matching_id':'TEST-B','fields':{'Project':'changed'},'expected_version':0}]}
    assert client.post('/api/v1/metadata',json=payload).status_code==409
    assert client.get('/api/v1/metadata').json()==before
    payload['entries']=payload['entries'][:1]
    assert client.post('/api/v1/metadata',json=payload).status_code==200
    a=next(row for row in client.get('/api/v1/metadata').json()['records'] if row['matching_id']=='TEST-A')
    assert a['fields']=={'Project':''}


def import_pair(client,tmp_path,features=(0,30),calibrated=True,codes=('TEST-GROUP','TEST-GROUP')):
    store=client.app.state.archive
    for index,color in enumerate(('red','blue')):
        path=tmp_path/(color+'.png');path.write_bytes(image_bytes(color))
        ident,_=store.import_image(path,barcodes=[codes[index]] if codes[index] else [])
        capture_review.record_analysis(store,ident,{'qrValues':[codes[index]] if codes[index] else [],'calibration':{'scale':1} if calibrated else None,
            'rotationDegrees':0 if calibrated else None,'labelFeatures':features[index],'markerIds':[0,1,2,3]})
    return items(client)


def review_body(item,roles,group=None,accept=True):
    return {'actor':'TEST','key':item['key'],'revision':item['revision'],'accept_qc':accept,'photos':[
        {'photo_id':photo['id'],'group_name':group or item['name'],'role':role} for photo,role in zip(item['photos'],roles)]}


def test_clear_pairs_automatically_ready_and_plan_without_confirmation(client,tmp_path):
    group=import_pair(client,tmp_path)[0]
    assert group['qc']['status']=='ready' and group['qc']['method']=='automatic'
    assert not group['qc']['problems']
    body=selection(group);body['entries'][0].update(tissue_id=group['qc']['tissue_id'],identifier_id=group['qc']['identifier_id'],confirmed=False)
    response=client.post('/api/v1/planning-selections',json=body)
    assert response.status_code==201,response.text
    plan=client.get('/api/v1/planning-selections/'+response.json()['id']).json()
    assert not plan['items'][0]['identity_reviewed']
    body['entries'][0]['tissue_id'],body['entries'][0]['identifier_id']=body['entries'][0]['identifier_id'],body['entries'][0]['tissue_id']
    assert client.post('/api/v1/planning-selections',json=body).status_code==422


def test_ambiguous_sides_flags_manual_review_and_staleness(client,tmp_path):
    group=import_pair(client,tmp_path,features=(8,9),calibrated=False)[0]
    assert group['qc']['status']=='needs_review'
    assert any('ambiguous' in problem for problem in group['qc']['problems'])
    body=review_body(group,['tissue','identifier'])
    assert client.post('/api/v1/inventory/review',json=body).status_code==200
    updated=items(client)[0]
    assert updated['qc']['status']=='ready' and updated['qc']['method']=='reviewed'
    assert any('calibration' in problem for problem in updated['qc']['problems'])
    assert client.post('/api/v1/inventory/review',json=body).status_code==409
    # A new image invalidates a prior group review rather than inheriting its acceptance.
    path=tmp_path/'third.png';path.write_bytes(image_bytes('green'));client.app.state.archive.import_image(path,barcodes=['TEST-GROUP'])
    assert items(client)[0]['qc']['status']=='needs_review'


def test_regroup_missing_qr_and_persist_review_metadata_backup(client,tmp_path):
    groups=import_pair(client,tmp_path,calibrated=False,codes=(None,None))
    assert len(groups)==2
    assert client.post('/api/v1/inventory/labels',json={'actor':'TEST','entries':[entry(groups[0])],'labels':['frozen']}).status_code==200
    groups=items(client)
    assert client.post('/api/v1/inventory/review',json=review_body(groups[0],['tissue'],'TEST-CORRECT',False)).status_code==200
    other=next(item for item in items(client) if item['name']!='TEST-CORRECT')
    assert client.post('/api/v1/inventory/review',json=review_body(other,['identifier'],'TEST-CORRECT')).status_code==200
    merged=items(client)[0]
    assert len(items(client))==1 and merged['name']=='TEST-CORRECT'
    assert merged['qc']['status']=='ready' and merged['labels']==['frozen']
    assert apply(client,preview(client,'ID,Cohort\nTEST-CORRECT,Pilot').json()).status_code==200
    destination=tmp_path/'restored'
    with zipfile.ZipFile(io.BytesIO(client.get('/api/v1/backup').content)) as backup:backup.extractall(destination)
    restored=TestClient(create_app(destination,{'http://testserver'},TOKEN),headers={'Authorization':'Bearer '+TOKEN})
    group=items(restored)[0]
    assert group['metadata']=={'Cohort':'Pilot'} and group['qc']['status']=='ready'


def test_incomplete_roles_stay_flagged_and_no_cross_group_images(client,tmp_path):
    group=import_pair(client,tmp_path,features=(7,8))[0]
    assert client.post('/api/v1/inventory/review',json=review_body(group,['tissue','unknown'],accept=False)).status_code==200
    updated=items(client)[0]
    assert updated['qc']['status']=='needs_review'
    body=review_body(updated,['tissue','identifier']);body['photos'][0]['photo_id']='00000000-0000-0000-0000-000000000000'
    assert client.post('/api/v1/inventory/review',json=body).status_code==422


def test_metadata_snapshot_and_review_invalidated_by_edit(client,tmp_path):
    group=import_pair(client,tmp_path)[0]
    assert apply(client,preview(client,'ID,Material\nTEST-GROUP,OCT').json()).status_code==200
    assert client.post('/api/v1/planning-selections',json=selection(group)).status_code==409
    fresh=items(client)[0];body=selection(fresh)
    body['entries'][0].update(tissue_id=fresh['qc']['tissue_id'],identifier_id=fresh['qc']['identifier_id'],confirmed=False)
    response=client.post('/api/v1/planning-selections',json=body)
    assert response.status_code==201
    assert client.get('/api/v1/planning-selections/'+response.json()['id']).json()['items'][0]['metadata']=={'Material':'OCT'}


def test_v2_recovers_missed_pair_but_never_overrides_declared_sides(client,tmp_path):
    group=import_pair(client,tmp_path,features=(4,6))[0]
    assert group['qc']['status']=='needs_review'
    for index,photo in enumerate(group['photos']):
        capture_review.record_analysis(client.app.state.archive,photo['id'],{
            'qrValues':['TEST-GROUP'],'calibration':{'scale':1},'rotationDegrees':0,'labelFeatures':[4,6][index],
            'printingEvidence':{'version':'rim-text-v2','score':5 if index==0 else 0,'heightVariation':.2 if index==0 else None}})
    improved=items(client)[0]
    assert improved['qc']['status']=='ready'
    assert improved['qc']['identifier_id']==group['photos'][0]['id']
    assert improved['qc']['side_detector']=='rim-text-v2'
    assert client.post('/api/v1/inventory/review',json=review_body(improved,['tissue','identifier'])).status_code==200
    declared=items(client)[0]
    assert declared['qc']['tissue_id']==group['photos'][0]['id']
    assert declared['qc']['identifier_id']==group['photos'][1]['id']
    assert declared['qc']['method']=='reviewed'


@pytest.mark.parametrize('present,missing',[('identifier','tissue'),('tissue','identifier')])
def test_explicit_missing_side_can_plan_and_new_photo_invalidates(client,tmp_path,present,missing):
    path=tmp_path/'single.png';path.write_bytes(image_bytes())
    client.app.state.archive.import_image(path,barcodes=['TEST-MISSING'])
    item=items(client)[0];body=review_body(item,[present]);body['missing_side']=missing
    unacknowledged={**body,'accept_qc':False}
    assert client.post('/api/v1/inventory/review',json=unacknowledged).status_code==422
    assert client.post('/api/v1/inventory/review',json={**body,'missing_side':present}).status_code==422
    assert client.post('/api/v1/inventory/review',json=body).status_code==200
    ready=items(client)[0]
    assert ready['qc']['status']=='ready' and ready['qc']['missing_side']==missing
    plan=selection(ready);plan['entries'][0].update(tissue_id=ready['qc']['tissue_id'],identifier_id=ready['qc']['identifier_id'],confirmed=False)
    response=client.post('/api/v1/planning-selections',json=plan)
    assert response.status_code==201,response.text
    saved=client.get('/api/v1/planning-selections/'+response.json()['id']).json()['items'][0]
    assert saved['missing_side']==missing
    path=tmp_path/'second.png';path.write_bytes(image_bytes('blue'))
    client.app.state.archive.import_image(path,barcodes=['TEST-MISSING'])
    assert items(client)[0]['qc']['status']=='needs_review'
