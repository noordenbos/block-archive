"""Full-project controls, portable experiments and automatic sides in a real browser."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from block_archive.server import create_app
from test_api import image_bytes
from test_projects import experiment
from block_archive import capture_review
from block_archive import metadata
with tempfile.TemporaryDirectory(prefix='projects-browser-') as temporary:
    folder=Path(temporary)
    sock=socket.socket();sock.bind(('127.0.0.1',0));origin='http://127.0.0.1:'+str(sock.getsockname()[1])
    app=create_app(folder/'data',{origin},'synthetic-project-browser-token')
    for score,color in ((0,'red'),(30,'blue')):
        photo=folder/(color+'.png');photo.write_bytes(image_bytes(color))
        ident,_=app.state.archive.import_image(photo,barcodes=['TEST-PAIR'])
        capture_review.record_analysis(app.state.archive,ident,{'qrValues':['TEST-PAIR'],'calibration':{'scale':1},'rotationDegrees':0,'labelFeatures':score,'markerIds':[0,1,2,3]})
    metadata.save(app.state.archive,[{'matching_id':'TEST-PAIR','fields':{'Material':'OCT'},'expected_version':0}],'TEST','fill')
    server=uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(200):
        if server.started:break
        time.sleep(.025)
    assert server.started
    try:
        with sync_playwright() as p:
            options={'headless':True}
            if os.environ.get('SPATIAL_BROWSER_PATH'):options['executable_path']=os.environ['SPATIAL_BROWSER_PATH']
            browser=p.chromium.launch(**options);context=browser.new_context(viewport={'width':1440,'height':1000})
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin) else route.abort())
            page=context.new_page();errors=[];violations=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:violations.append(m.text) if 'Content Security Policy' in m.text else None)
            page.goto(origin+'/#inventory')
            expect(page.locator('#resultsCount')).to_contain_text('1 matching')
            expect(page.locator('.inventory-tissue-view')).to_have_count(1)
            expect(page.locator('.inventory-photo-pair')).to_have_count(0)
            expect(page.locator('.qc-status')).to_contain_text('Sides detected automatically')
            page.locator('#reviewTab').click();page.locator('#showAllQC').check();page.locator('.qc-group summary').click()
            expect(page.locator('.side-explanation')).to_contain_text('Upper-rim')
            page.goto(origin+'/planner/')
            expect(page.locator('#saveStatus')).to_have_text('Saved on this browser')
            page.evaluate('(value)=>{state=value;blockId=null;slideId=state.slides[0].id;save();render()}',experiment())
            # A second archived experiment must survive together with the current plan.
            page.get_by_role('button',name='New experiment',exact=True).click()
            page.locator('dialog[open] input').fill('Second plan');page.get_by_role('button',name='Create experiment',exact=True).click()
            expect(page.locator('aside h2')).to_have_text('Second plan')
            page.get_by_role('link',name='← Block inventory').click()
            page.get_by_role('button',name='Save location',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('Current destination:')
            page.get_by_role('button',name='Use default',exact=True).click()
            page.get_by_role('button',name='Use this location',exact=True).click()
            expect(page.get_by_role('dialog')).not_to_be_visible()
            with page.expect_response('**/api/v1/local-saves/project') as local_save:
                page.get_by_role('button',name='Save project',exact=True).click()
            assert local_save.value.ok
            assert Path(local_save.value.json()['path']).is_file()
            with page.expect_download() as download:
                page.get_by_role('button',name='Export project JSON',exact=True).click()
            saved=folder/'portable.json';download.value.save_as(saved)
            document=json.loads(saved.read_text())
            assert len(document['archive']['images'])==4
            assert {e['value']['name'] for e in document['experiments']['entries']}=={'Synthetic plan','Second plan'}
            assert len(document['archive']['tables']['inventory_metadata'])==1
            stale=context.new_page();stale.goto(origin)
            expect(stale.locator('.project-bar>strong')).to_have_text('Local archive')
            page.get_by_role('button',name='New project',exact=True).click();page.locator('.project-dialog input').fill('Fresh project')
            page.get_by_role('button',name='Create project',exact=True).click()
            expect(page.locator('.project-bar>strong')).to_have_text('Fresh project')
            page.locator('#inventoryTab').click();expect(page.locator('#resultsCount')).to_contain_text('0 matching')
            code=stale.evaluate("async()=>{const r=await fetch('/api/v1/projects',{method:'POST',headers:{'Content-Type':'application/json','X-Archive-Request':'1'},body:JSON.stringify({name:'Stale tab'})});return r.status}")
            assert code==409
            # Import into a fresh browser profile proves experiments are in the JSON.
            other=browser.new_context(viewport={'width':1440,'height':1000});restored=other.new_page()
            restored.on('pageerror',lambda e:errors.append(str(e)))
            restored.goto(origin)
            restored.get_by_role('button',name='Open project',exact=True).click()
            restored.locator('.project-dialog input[type=file]').set_input_files(saved)
            expect(restored.locator('.project-bar>strong')).to_have_text('Local archive (imported)')
            restored.locator('#inventoryTab').click();expect(restored.locator('#resultsCount')).to_contain_text('1 matching')
            expect(restored.locator('.inventory-metadata')).to_contain_text('Material: OCT')
            expect(restored.locator('.qc-status')).to_contain_text('Sides detected automatically')
            restored.get_by_role('link',name='Prepare spatial experiment',exact=True).click()
            expect(restored.locator('aside h2')).to_have_text('Second plan')
            restored.get_by_role('button',name='Open experiment',exact=True).click()
            restored.get_by_role('button',name='Synthetic plan · 0 blocks',exact=True).click()
            expect(restored.locator('aside h2')).to_have_text('Synthetic plan')
            # Original inventory is still available from the project list.
            page.get_by_role('button',name='Open project',exact=True).click()
            page.locator('.project-list').get_by_role('button',name='Local archive',exact=True).click()
            expect(page.locator('.project-bar>strong')).to_have_text('Local archive')
            page.locator('#inventoryTab').click();expect(page.locator('#resultsCount')).to_contain_text('1 matching')
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                output=Path(os.environ['BLOCK_ARCHIVE_SCREENSHOTS']);output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/'project-inventory.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/'project-mobile.png'),full_page=True)
            assert not errors,errors
            assert not violations,violations
            browser.close()
        print('PASS: full JSON restore in a fresh browser, all experiments, metadata, photos, sides, new/open isolation and stale-tab guard.')
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
