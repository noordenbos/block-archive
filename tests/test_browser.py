"""Browser regressions using an isolated profile and synthetic data only."""
import sys, threading, hashlib, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
http = server.LocalServer(('127.0.0.1', 0), server.Handler)
origin = f'http://127.0.0.1:{http.server_port}'
server.ALLOWED_HOSTS.add(f'127.0.0.1:{http.server_port}')
server.ALLOWED_ORIGINS.add(origin)
thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
try:
    with sync_playwright() as p:
        options = {'headless': True}
        if os.environ.get('SPATIAL_BROWSER_PATH'):
            options['executable_path'] = os.environ['SPATIAL_BROWSER_PATH']
        browser = p.chromium.launch(**options)
        context = browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin) or route.request.url.startswith('data:') else route.abort())
        page = context.new_page(); errors=[]; page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto(origin); page.wait_for_selector('#addBlock')
        assert page.locator('.badge').inner_text() == 'LOCAL RESEARCH SOFTWARE'
        assert page.locator('.block-item').count() == 0
        page.locator('#addBlock').click();page.wait_for_selector('#blockName')
        assert page.locator('#blockName').input_value() == 'BLOCK-001'
        for tab in ('config','slides','handoff','blocks'):
            page.locator(f'button[data-tab="{tab}"]').click()
        page.get_by_role('link',name='Download photo mats').click()
        assert page.get_by_role('heading',name='Download your photography mat').is_visible()
        assert page.locator('details').evaluate('(e)=>e.open') is False
        assert page.locator('img[src*="preview/"]').count()==0
        for size in ('A4','Letter'):
            with page.expect_download() as info:
                page.get_by_role('link',name=f'Download {size} PDF').click()
            download=info.value
            assert download.failure() is None
            path=Path(download.path()); assert len(PdfReader(path).pages)==2
            assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256((ROOT / f'artefacts/FFPE-photography-{size}.pdf').read_bytes()).digest()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('summary').click();page.locator('img').wait_for(state='visible')
        page.wait_for_function('()=>Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
        page.goto(origin+'/labels.html');page.locator('#ids').fill('TEST-0001\nTEST-0002');page.locator('#generate').click()
        page.wait_for_function('()=>document.querySelectorAll("#sheet .label").length===2')
        assert not errors,errors
        browser.close()
        print('PASS: isolated browser startup, registration, navigation, desktop/mobile downloads, example, label API; no JS errors.')
finally:
    http.shutdown();http.server_close();thread.join()
