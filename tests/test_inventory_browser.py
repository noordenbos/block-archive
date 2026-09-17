"""Exercise the inventory-to-planning workflow with isolated synthetic data."""
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from block_archive.server import create_app
from test_api import image_bytes
from block_archive import inventory
from block_archive import capture_review
with tempfile.TemporaryDirectory(prefix='inventory-browser-') as temporary:
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    app = create_app(Path(temporary)/'data', {origin}, 'synthetic-inventory-browser-token')
    store = app.state.archive
    for number in range(1, 41):
        block = store.create(f'TEST-B{number}', 'Synthetic tissue', 'TEST', 2026, '1', 'B', number)
        store.add_photo(block['id'], image_bytes(), 'baseline', 'TEST', '', block['version'])
    for item in inventory.list_items(store):
        capture_review.save_review(store,item['key'],item['revision'],[{'photo_id':item['photos'][0]['id'],'group_name':item['name'],'role':'tissue'}],'TEST',True,'identifier')
    imported = Path(temporary)/'unverified.png'; imported.write_bytes(image_bytes('blue'))
    store.import_image(imported, barcodes=['TEST-UNVERIFIED'])
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='error'))
    thread = threading.Thread(target=lambda:server.run(sockets=[sock]), daemon=True); thread.start()
    for _ in range(200):
        if server.started: break
        time.sleep(.025)
    assert server.started
    try:
        with sync_playwright() as playwright:
            options = {'headless':True}
            if os.environ.get('SPATIAL_BROWSER_PATH'): options['executable_path']=os.environ['SPATIAL_BROWSER_PATH']
            browser = playwright.chromium.launch(**options)
            context = browser.new_context(viewport={'width':1440,'height':1000})
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin) else route.abort())
            page = context.new_page(); errors=[]; violations=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('console',lambda message:violations.append(message.text) if 'Content Security Policy' in message.text else None)
            page.goto(origin)
            expect(page.get_by_role('heading',name='Photograph once. Plan from your archive.')).to_be_visible()
            expect(page.get_by_role('link',name='A4 mat ↓')).to_be_visible()
            expect(page.get_by_role('link',name='Letter mat ↓')).to_be_visible()
            expect(page.get_by_role('link',name='Open QR label generator')).to_be_visible()
            page.locator('#operator').fill('TEST-TECH'); page.locator('#operator').press('Tab')
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                capture_folder=Path(os.environ['BLOCK_ARCHIVE_SCREENSHOTS']);capture_folder.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(capture_folder/'capture-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(capture_folder/'capture-mobile.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})
            with page.expect_popup() as qr_popup:
                page.get_by_role('link',name='Open QR label generator').click()
            labels_page=qr_popup.value
            labels_page.locator('#ids').fill('TEST-B1\nTEST-B2')
            labels_page.locator('#generate').click()
            expect(labels_page.locator('#sheet .label')).to_have_count(2)
            labels_page.close()
            page.locator('#reviewTab').click()
            expect(page.locator('.qc-group')).to_have_count(1)
            expect(page.locator('#qcSummary')).to_contain_text('40 groups ready')
            page.locator('.qc-group summary').click()
            page.locator('.qc-role').select_option('tissue')
            page.locator('.qc-missing-side').select_option('identifier');page.locator('.qc-accept').check()
            page.get_by_role('button',name='Save grouping & sides').click()
            expect(page.locator('#qcSummary')).to_contain_text('41 groups ready')
            expect(page.locator('.qc-group')).to_have_count(0)
            page.locator('#metadataTab').click()
            page.locator('#metadataFile').set_input_files({'name':'synthetic.csv','mimeType':'text/csv','buffer':b'ID,Material,Project\nTEST-B1,OCT,Pilot\nTEST-B2,OCT,Pilot\nFUTURE-B1,FFPE,Next'})
            expect(page.locator('#metadataPreviewSummary')).to_contain_text('2 IDs match')
            page.locator('#applyMetadata').click()
            expect(page.locator('#metadataPreview')).not_to_be_visible()
            page.locator('[data-edit-metadata="TEST-B1"]').click()
            page.locator('.metadata-field-value').first.fill('Frozen')
            page.locator('#saveMetadataRecord').click()
            expect(page.locator('#metadataEditor')).not_to_be_visible()
            page.locator('#metadataPaste').fill('Custom key\tSite\nTEST-B1\tNorth')
            page.locator('#previewMetadata').click()
            expect(page.locator('#applyMetadata')).to_be_enabled()
            page.locator('#applyMetadata').click()
            expect(page.locator('#metadataPreview')).not_to_be_visible()
            page.locator('#newMetadata').click()
            page.locator('#metadataId').fill('MANUAL-FUTURE')
            page.locator('.metadata-field-name').fill('Project')
            page.locator('.metadata-field-value').fill('Direct entry')
            page.locator('#saveMetadataRecord').click()
            expect(page.locator('#metadataEditor')).not_to_be_visible()
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                page.screenshot(path=str(capture_folder/'metadata-desktop.png'),full_page=True)
            page.locator('#inventoryTab').click()
            page.locator('#metadataField').select_option('Material')
            page.locator('#metadataValue').select_option('Frozen')
            expect(page.locator('.inventory-card')).to_have_count(1)
            page.locator('#clearFilters').click()
            expect(page.locator('#resultsCount')).to_contain_text('41 matching')
            expect(page.locator('.inventory-card')).to_have_count(36)
            page.locator('#operator').fill('TEST-TECH'); page.locator('#operator').press('Tab')
            page.locator('#kindFilter').select_option('block')
            expect(page.locator('#selectAll')).to_have_text('Select all 40 matches')
            page.locator('#selectAll').click()
            expect(page.locator('#selectionCount')).to_contain_text('40 selected')
            page.locator('#next').click()
            expect(page.locator('.inventory-card input:checked')).to_have_count(4)
            page.locator('#editLabels').click(); page.locator('#labelsInput').fill('OCT, pilot')
            page.locator('#saveLabels').click(); expect(page.locator('#labelsDialog')).not_to_be_visible()
            page.locator('#labelFilter').select_option('oct')
            expect(page.locator('#resultsCount')).to_contain_text('40 matching')
            page.locator('#searchMode').select_option('regex')
            page.locator('#search').fill('[')
            expect(page.locator('#filterError')).to_contain_text('Invalid regular expression')
            expect(page.locator('#selectAll')).to_be_disabled()
            page.locator('#search').fill('^TEST-B[12]$')
            expect(page.locator('.inventory-card')).to_have_count(2)
            expect(page.locator('#selectionCount')).to_contain_text('38 outside this filter')
            page.locator('#unselectAll').click(); expect(page.locator('#selectionCount')).to_contain_text('No blocks selected'); page.locator('#selectAll').click()
            expect(page.locator('#selectionCount')).to_contain_text('2 selected')
            page.reload()
            expect(page.locator('#selectionCount')).to_contain_text('2 selected')
            page.locator('#selectedOnly').check()
            expect(page.locator('.inventory-card')).to_have_count(2)
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                folder=Path(os.environ['BLOCK_ARCHIVE_SCREENSHOTS']);folder.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(folder/'inventory-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                page.screenshot(path=str(folder/'inventory-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#plan').click()
            page.locator('#experimentName').fill('Synthetic pilot experiment')
            expect(page.locator('.review-item')).to_have_count(2)
            expect(page.locator('.ready-review')).to_contain_text('2 groups ready')
            page.locator('#createPlan').click()
            page.wait_for_url('**/planner/')
            expect(page.locator('aside h2')).to_have_text('Synthetic pilot experiment')
            assert page.evaluate('state.blocks.length') == 2
            assert page.evaluate('state.blocks.every(b=>b.inventory.blockId && b.labels.includes("oct") && b.photo && b.mmPerPx===null)')
            selection_id=page.evaluate('state.inventorySelectionId')
            page.evaluate("state.blocks[0].notes='Scoring review retained'; save()")
            page.evaluate('saving')
            page.goto(origin+'/planner/?selection='+selection_id)
            page.wait_for_url('**/planner/')
            assert page.evaluate('state.blocks[0].notes') == 'Scoring review retained'
            page.get_by_role('button',name='New experiment',exact=True).click()
            page.locator('dialog input').fill('Separate experiment')
            page.get_by_role('button',name='Create experiment',exact=True).click()
            expect(page.locator('aside h2')).to_have_text('Separate experiment')
            page.goto(origin+'/planner/?selection='+selection_id)
            page.wait_for_url('**/planner/')
            expect(page.locator('aside h2')).to_have_text('Synthetic pilot experiment')
            assert page.evaluate('state.blocks[0].notes') == 'Scoring review retained'
            with page.expect_response('**/api/v1/local-saves/experiment') as local_save:
                page.get_by_role('button',name='Save experiment',exact=True).click()
            assert local_save.value.ok
            assert Path(local_save.value.json()['path']).is_file()
            with page.expect_download() as download:
                page.get_by_role('button',name='Export experiment JSON',exact=True).click()
            assert download.value.failure() is None
            assert page.evaluate('state.blocks[0].metadata.Site') == 'North'
            page.evaluate("state.blocks[0].mmPerPx=.1;state.blocks[0].regions=[{id:'rotation-test-region',name:'Synthetic piece',points:[[0,0],[20,0],[20,10],[0,10]],color:'#d99e84'}];save()")
            expect(page.locator('main .experiment-actions').get_by_role('button',name='Save experiment',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='Phone → laptop')).to_have_count(0)
            expect(page.get_by_role('link',name='Download photo mats')).to_have_count(0)
            page.locator('[data-tab="overview"]').click()
            page.locator('#slideCount').fill('35');page.locator('#createSlides').click()
            expect(page.locator('[data-slide-name]')).to_have_count(35)
            assert page.locator('[data-slide-name]').nth(34).input_value()=='Synthetic pilot experiment_slide_035'
            page.locator('[data-slide-name]').nth(30).fill('Custom slide 31')
            page.locator('[data-slide-name]').nth(30).press('Tab')
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                page.screenshot(path=str(folder/'slide-overview.png'),full_page=True)
            page.locator('[data-tab="blocks"]').click()
            page.locator('#findTargetSlide').fill('Custom slide')
            expect(page.locator('#blockTargetSlide option')).to_have_count(1)
            if os.environ.get('BLOCK_ARCHIVE_SCREENSHOTS'):
                page.screenshot(path=str(folder/'block-assignment.png'),full_page=True)
            page.locator('#assignBlockPieces').click()
            assert page.evaluate('state.slides[30].placements.length')==1
            page.locator('#assignBlockPieces').click()
            assert page.evaluate('state.slides[30].placements.length')==1
            page.locator('[data-block]').nth(1).click()
            assert page.locator('#blockTargetSlide option').nth(0).text_content()=='Custom slide 31'
            assert page.locator('#blockTargetSlide option').nth(1).text_content()=='Synthetic pilot experiment_slide_032'
            expect(page.locator('#blockTargetSlide optgroup[label="Recent & next"] option')).to_have_count(2)
            expect(page.locator('#blockTargetSlide optgroup[label="All slides"] option')).to_have_count(35)
            assert page.locator('#blockTargetSlide optgroup[label="All slides"] option').nth(30).text_content()=='Custom slide 31'
            page.reload()
            expect(page.locator('aside h2')).to_have_text('Synthetic pilot experiment')
            assert page.evaluate('state.slides.length')==35
            page.locator('#openTargetSlide').click()
            expect(page.locator('#slideSelect')).to_have_value(page.evaluate('state.slides[30].id'))
            page.get_by_role('combobox',name='Piece to rotate').select_option(page.evaluate('state.slides[30].placements[0].id'))
            assert page.locator('#confirmed').count()==0
            before=page.locator('#slideSvg [data-placement] polygon').get_attribute('points')
            page.locator('#angle').fill('45')
            assert page.evaluate('currentSlide().placements[0].angle')==45
            assert page.locator('#slideSvg [data-placement] polygon').get_attribute('points')!=before
            before=page.locator('#slideSvg [data-placement] polygon').get_attribute('points')
            page.get_by_role('slider',name='Rotate selected piece').evaluate("element=>{element.value='90';element.dispatchEvent(new Event('input',{bubbles:true}))}")
            assert page.evaluate('currentSlide().placements[0].angle')==90
            assert page.locator('#slideSvg [data-placement] polygon').get_attribute('points')!=before
            page.get_by_role('spinbutton',name='Placement rotation degrees').fill('120')
            assert page.evaluate('currentSlide().placements[0].angle')==120
            page.get_by_role('spinbutton',name='Placement rotation degrees').dispatch_event('change')
            expect(page.locator('#content')).to_contain_text('Slide')
            page.locator('[data-tab="handoff"]').click()
            with page.expect_download() as download:
                page.locator('#exportDeck').click()
            assert download.value.failure() is None
            # A pathological regex must time out without blocking the UI thread.
            page.goto(origin+'/#inventory')
            expect(page.locator('#resultsCount')).to_contain_text('41 matching')
            page.evaluate("items.values().next().value.evidence='a'.repeat(10000)+'!'; startWorker()")
            page.locator('#searchMode').select_option('regex'); page.locator('#search').fill('^(a+)+$')
            expect(page.locator('#filterError')).to_contain_text('too long')
            page.locator('#clearFilters').click()
            expect(page.locator('#resultsCount')).to_contain_text('41 matching')
            # Explicitly accept an identifier-only group, then plan without a QC loop.
            page.locator('#reviewTab').click();page.locator('#showAllQC').check()
            group=page.locator('.qc-group').filter(has=page.locator('summary',has_text='TEST-UNVERIFIED'))
            group.locator('summary').click()
            group.locator('.qc-role').select_option('identifier')
            group.locator('.qc-missing-side').select_option('tissue')
            group.locator('.qc-accept').check()
            group.get_by_role('button',name='Save grouping & sides').click()
            expect(page.locator('#qcSummary')).to_contain_text('41 groups ready')
            page.locator('#inventoryTab').click();page.locator('#clearSelection').click()
            page.locator('#search').fill('TEST-UNVERIFIED')
            expect(page.locator('.inventory-card')).to_have_count(1)
            expect(page.locator('.inventory-card')).to_contain_text('Tissue photo unavailable')
            page.locator('#selectAll').click();page.locator('#plan').click()
            page.locator('#experimentName').fill('Record-only experiment')
            page.locator('#createPlan').click();page.wait_for_url('**/planner/')
            expect(page.locator('aside h2')).to_have_text('Record-only experiment')
            assert page.evaluate('state.blocks.length===1 && state.blocks[0].photo===null && state.blocks[0].identifier===null')
            assert page.evaluate("state.blocks[0].sources.every(s=>!s.image && !s.source && !s.canonical)")
            with page.expect_download() as record_download:
                page.get_by_role('button',name='Export experiment JSON',exact=True).click()
            assert record_download.value.failure() is None
            assert not errors, errors
            assert not violations, violations
            browser.close()
        print('PASS: inventory filtering, regex timeout, labels, cross-page selection, responsive layout, photo review, planning, reopen and exports.')
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
