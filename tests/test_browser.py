"""Exercise the technician workflow in an isolated browser and temporary archive."""
from pathlib import Path
from contextlib import contextmanager
import io
import os
import socket
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect
from block_archive.server import create_app

TOKEN = 'synthetic-browser-test-api-token-only'


def specimen_image(label, cut=False):
    image = Image.new('RGB', (800, 600), '#ecefe7')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((150, 70, 650, 520), radius=30, fill='#dcac45', outline='#b38628', width=5)
    draw.rounded_rectangle((190, 150, 610, 450), radius=12, fill='#f7ebcf', outline='#bc963b', width=3)
    draw.ellipse((260, 220, 470 if cut else 520, 370), fill='#b56c53', outline='#92523d', width=5)
    draw.text((220, 110), label, fill='#352f20', font_size=28)
    draw.text((195, 480), 'SYNTHETIC TEST IMAGE', fill='#554626', font_size=23)
    output = io.BytesIO(); image.save(output, 'PNG'); return output.getvalue()


with tempfile.TemporaryDirectory(prefix='block-archive-browser-') as temporary:
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    app = create_app(Path(temporary)/'data', {origin}, TOKEN)
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True); thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.025)
    assert server.started
    try:
        with httpx.Client(base_url=origin, headers={'Authorization': 'Bearer '+TOKEN}) as api:
            for suffix, description in [('A1','Synthetic container A — first cassette'),('B4','Synthetic tissue face — sectioned block'),('B10','Synthetic container B — additional tissue')]:
                body={'actor':'TEST-TECH','block_code':f'TEST-2026-001234-{suffix}','archive_year':2026,'case_number':'001234',
                      'subspecimen':suffix[0],'cassette_number':int(suffix[1:]),'description':description}
                response=api.post('/api/v1/blocks',json=body);assert response.status_code==201,response.text;block=response.json()
                response=api.post(f'/api/v1/blocks/{block["id"]}/photos',data={'actor':'TEST-TECH','expected_version':block['version'],'kind':'baseline'},
                                  files={'file':('synthetic.png',specimen_image(suffix),'image/png')})
                assert response.status_code==201,response.text;block=response.json()
                response=api.post(f'/api/v1/blocks/{block["id"]}/rearchive',json={'actor':'TEST-TECH','expected_version':block['version'],'photo_id':block['photos'][0]['id']})
                assert response.status_code==200,response.text
        with sync_playwright() as p:
            options={'headless':True}
            if os.environ.get('SPATIAL_BROWSER_PATH'):
                options['executable_path']=os.environ['SPATIAL_BROWSER_PATH']
            browser=p.chromium.launch(**options)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin) else route.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(origin+'/archive');page.locator('#operator').fill('TEST-TECH')
            page.locator('#search').fill('TEST-2026-001234-B4');page.locator('#search').press('Enter')
            expect(page.locator('#record h2')).to_have_text('TEST-2026-001234-B4')
            page.locator('#checkout').click();expect(page.locator('#completeCut')).to_be_visible()
            page.locator('#completeCut').click();expect(page.locator('#rearchive')).to_be_disabled()
            page.locator('#archivePhoto').set_input_files({'name':'after-cut.png','mimeType':'image/png','buffer':specimen_image('B4',True)})
            expect(page.locator('#rearchive')).to_be_enabled()
            page.locator('#movementNote').fill('Returned to year-case sequence after cutting.')
            page.locator('#rearchive').click();expect(page.locator('#checkout')).to_be_visible()
            expect(page.locator('.photo-strip button')).to_have_count(2)
            expect(page.locator('[data-sibling]')).to_have_count(3)
            page.locator('#addLink').click()
            page.locator('#linkForm [name="system"]').fill('Synthetic research dataset')
            page.locator('#linkForm [name="external_id"]').fill('TEST-LINK-42')
            page.locator('#linkForm [name="url"]').fill('https://example.org/test-record')
            page.get_by_role('button',name='Save reference',exact=True).click()
            expect(page.locator('#linkDialog')).not_to_be_visible()
            page.locator('#search').fill('TEST-LINK-42')
            expect(page.locator('#blockList .block-card')).to_have_count(1)
            page.locator('#search').fill('');page.locator('#refresh').click()
            expect(page.locator('#blockList .block-card')).to_have_count(3)
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                folder=Path(os.environ['BLOCK_ARCHIVE_SCREENSHOTS']);folder.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(folder/'desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                page.screenshot(path=str(folder/'mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#newBlock').click()
            page.locator('#registerForm [name="block_code"]').fill('TEST-2026-001235-C2')
            page.locator('#registerForm [name="block_code"]').press('Tab')
            expect(page.locator('#registerForm [name="subspecimen"]')).to_have_value('C')
            expect(page.locator('#registerForm [name="cassette_number"]')).to_have_value('2')
            page.locator('#registerForm button.primary').click()
            expect(page.locator('#registerDialog')).not_to_be_visible()
            expect(page.locator('#record h2')).to_have_text('TEST-2026-001235-C2')
            expect(page.locator('#rearchive')).to_be_disabled()
            with page.expect_download() as download:
                page.get_by_role('link',name='Back up archive').click()
            assert download.value.failure() is None
            page.get_by_role('link',name='API guide').click()
            expect(page.get_by_role('heading',name='A stable link to every block.')).to_be_visible()
            # Review a historical photo without inventing a cutting/return event.
            imported = Path(temporary) / 'historical.png'
            imported.write_bytes(specimen_image('C2', True))
            app.state.archive.import_image(imported, label_text='TEST-2026-001235-C2', barcodes=['TEST-2026-001235-C2'])
            page.goto(origin+'/imports')
            page.locator('#operator').fill('TEST-TECH')
            page.locator('#search').fill('001235')
            expect(page.locator('[data-import]')).to_have_count(1)
            page.locator('[data-import]').click()
            expect(page.locator('#confirmForm')).to_be_visible()
            page.locator('#lookup').click()
            expect(page.locator('#match')).to_contain_text('Found:')
            page.locator('#verified').check()
            page.locator('#confirm').click()
            expect(page.locator('#openBlock')).to_be_visible()
            expect(page.locator('#pendingCount')).to_have_text('0')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('#openBlock').click()
            expect(page.locator('#record h2')).to_have_text('TEST-2026-001235-C2')
            expect(page.locator('#rearchive')).to_be_disabled()
            assert not errors,errors
            browser.close()
        print('PASS: browser search, case hierarchy, post-cut return, photo history, data links, registration, mobile layout and backup.')
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
