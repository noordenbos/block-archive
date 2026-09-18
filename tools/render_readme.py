"""Render README panels in an isolated app using demonstration records.

Run with requirements-dev.txt. Set SPATIAL_BROWSER_PATH for an installed Chrome.
Only reviewed documentation tissue crops are used; no live archive or browser profile is opened.
"""
import base64
import io
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import uvicorn
from PIL import Image
from playwright.sync_api import sync_playwright
from block_archive.server import create_app
from block_archive import capture_review
from block_archive import inventory
def documentation_photo(index):
    name='tissue-block.jpg' if index==0 else f'tissue-block-{index+1}.jpg'
    return (ROOT/'docs/assets'/name).read_bytes()


def data_url(path):
    return ('data:image/jpeg;base64,' if path.suffix=='.jpg' else 'data:image/png;base64,')+base64.b64encode(path.read_bytes()).decode()


def main():
    with tempfile.TemporaryDirectory(prefix='readme-synthetic-') as tmp:
        folder=Path(tmp);sock=socket.socket();sock.bind(('127.0.0.1',0));origin='http://127.0.0.1:'+str(sock.getsockname()[1])
        app=create_app(folder/'data',{origin},'synthetic-readme-only-token');store=app.state.archive
        for i in range(4):
            block=store.create(f'DEMO-B{i+1}', 'Demonstration block', 'DEMO',2026,'1','B',i+1)
            store.add_photo(block['id'],documentation_photo(i),'baseline','DEMO','',block['version'])
        for i,item in enumerate(inventory.list_items(store)):
            photo=item['photos'][0]
            capture_review.save_review(store,item['key'],item['revision'],[{'photo_id':photo['id'],'group_name':item['name'],'role':'tissue'}],'DEMO',True,'identifier')
            # Previews use reviewed documentation assets, never a live archive.
            cache=store.directory/'preview-cache/block-zone-v1';cache.mkdir(parents=True,exist_ok=True)
            Image.open(io.BytesIO(documentation_photo(i))).save(cache/(photo['id']+'.jpg'))
        for item in inventory.list_items(store):
            inventory.label_items(store,[{'key':item['key'],'revision':item['revision']}],['pilot','FFPE'],'add','DEMO')
        server=uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='error'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        try:
            for _ in range(200):
                if server.started:break
                time.sleep(.025)
            with sync_playwright() as pw:
                options={'headless':True}
                if os.environ.get('SPATIAL_BROWSER_PATH'):options['executable_path']=os.environ['SPATIAL_BROWSER_PATH']
                browser=pw.chromium.launch(**options)
                context=browser.new_context(viewport={'width':740,'height':1100},device_scale_factor=1)
                context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(origin) or r.request.url.startswith('data:') else r.abort())
                page=context.new_page();page.goto(origin+'/#inventory')
                page.locator('.inventory-card').first.wait_for()
                page.wait_for_function('() => [...document.querySelectorAll(".inventory-cover img")].every(i=>i.complete && i.naturalWidth>0)')
                page.locator('.inventory-card input').first.check()
                page.locator('.inventory-card input').nth(2).check()
                page.locator('.selection-tray').evaluate("element=>element.style.visibility='hidden'")
                archive=folder/'archive.png';page.locator('#inventoryGrid').screenshot(path=str(archive))
                page.set_viewport_size({'width':1440,'height':1000});page.goto(origin+'/planner/')
                page.wait_for_function('() => typeof state!=="undefined" && !!state')
                page.evaluate('''photo => {
                    state=emptyExperiment('Pilot');
                    const points=[[[390,207],[440,211],[430,394],[377,389]]];
                    const b={id:'demo-block',name:'DEMO-B1',donor:'',photo,identifier:null,mmPerPx:.07,calibration:null,orientation:'Label end up',notes:'Illustrative scoring demonstration',scores:[],regions:points.map((p,i)=>({id:'piece-'+i,name:'DEMO-B1-R01',points:p,color:'#ca9987'}))};
                    state.blocks=[b];state.slides[0].placements=[{id:'place-0',regionId:'piece-0',x:2.8,y:8,angle:0,mirror:false,confirmed:true,section:'Section 1'}];
                    // Four-piece arrangement matching the supplied slide-layout example.
                    const patches=[
                        {points:[[0,0],[3.6,0],[3.7,14.4],[.5,14.2]],x:7.5,y:8},
                        {points:[[.2,.2],[6.4,0],[7.3,2.8],[0,3.1]],x:4.7,y:17.25},
                        {points:[[0,.5],[8.9,0],[8.8,1.8],[0,1.8]],x:5,y:20.6}
                    ];
                    patches.forEach((patch,i)=>{
                        const region={id:'multiplex-'+i,name:'DEMO-B'+(i+2),points:patch.points,color:'#ca9987'};
                        state.blocks.push({id:'other-block-'+i,name:region.name,donor:'',photo:null,identifier:null,mmPerPx:1,calibration:null,orientation:'Demonstration',notes:'Illustrative tissue geometry',scores:[],regions:[region]});
                        state.slides[0].placements.push({id:'other-place-'+i,regionId:region.id,x:patch.x,y:patch.y,angle:0,mirror:false,confirmed:true,section:'Section 1'});
                    });
                    blockId=b.id;slideId=state.slides[0].id;selected='place-0';tab='slides';save();render();
                    const problems=issues(currentSlide()).filter(message=>/outside permitted|true polygon overlap|clearance is/.test(message));
                    if(problems.length)throw Error(problems.join('; '));
                }''',data_url(ROOT/'docs/assets/tissue-block.jpg'))
                planning=folder/'planning.png';page.locator('#slideSvg').screenshot(path=str(planning))
                page.evaluate("async () => {tab='blocks';render();await drawBlock()}")
                scoring=folder/'scoring.png'
                scoring.write_bytes(base64.b64decode(page.locator('#blockCanvas').evaluate("canvas=>canvas.toDataURL('image/png').split(',')[1]")))
                # Compose existing setup illustration and actual UI captures in HTML.
                setup=ROOT/'planner/artefacts/examples/phone-stand-17cm.png'
                cards=[('01','Photograph','Mat + matching QR labels',setup),('02','Archive','Review, label and select blocks',archive),('03','Plan spatial experiments','Score tissue. Assign recipient slides.',planning)]
                html='''<html><head><style>*{box-sizing:border-box}body{margin:0;background:#eef2eb;color:#234a40;font-family:Arial,sans-serif}.banner{width:1800px;padding:42px}.brand{font-size:17px;letter-spacing:3px;margin-bottom:26px}.panels{display:grid;grid-template-columns:.9fr 1fr 1.6fr;gap:24px}.panel{background:white;border:1px solid #d4dfd3;border-radius:20px;overflow:hidden}.head{padding:25px 26px 18px;height:136px}.step{font-size:15px;font-weight:bold;color:#78927a}h2{font-size:29px;letter-spacing:-.5px;margin:9px 0}p{font-size:18px;color:#6d7d70;margin:0}.image{height:555px;padding:12px 18px 22px;display:flex;align-items:center;justify-content:center;background:#fafbf7}img{max-width:100%;max-height:100%;object-fit:contain}.split{display:grid;grid-template-columns:1.4fr 1fr;gap:16px;align-items:center}.subpanel{height:504px;display:grid;grid-template-rows:30px 400px 50px;gap:12px;min-width:0}.subpanel h3{font-size:19px;margin:0;color:#426c5b}.subpanel img{height:400px;width:100%;object-fit:contain;min-height:0}.subpanel p{font-size:16px;line-height:1.4}.foot{display:flex;justify-content:space-between;font-size:15px;color:#677e6c;padding-top:23px}</style></head><body><div class="banner"><div class="brand">BLOCK ARCHIVE + SPATIAL PREP</div><div class="panels">'''
                for step,title,subtitle,path in cards:
                    html+=f'<section class="panel"><div class="head"><div class="step">{step}</div><h2>{title}</h2><p>{subtitle}</p></div>'
                    if step=='03':
                        html+=f'<div class="image split"><div class="subpanel"><h3>3a · Prepare the block</h3><img src="{data_url(scoring)}"><p>Outline retained tissue.<br>Dashed edges mark scoring lines.</p></div><div class="subpanel"><h3>3b · Multiplex tissues</h3><img src="{data_url(planning)}"><p>Retained tissue from this block,<br>alongside three other pieces.</p></div></div>'
                    else:
                        html+=f'<div class="image"><img src="{data_url(path)}"></div>'
                    html+='</section>'
                html+='</div><div class="foot"><span>One local workspace · from block photo to slide layout</span><span>Demonstration records · reviewed tissue-side crop</span></div></div></body></html>'
                page.set_viewport_size({'width':1800,'height':900});page.set_content(html)
                page.wait_for_function('() => [...document.images].every(i=>i.complete && i.naturalWidth>0)')
                output=ROOT/'docs/assets/workflow.png';page.locator('.banner').screenshot(path=str(output))
                browser.close();print('Rendered docs/assets/workflow.png with reviewed tissue crop and demonstration records.')
        finally:server.should_exit=True;thread.join(timeout=10);sock.close()


if __name__=='__main__':main()
