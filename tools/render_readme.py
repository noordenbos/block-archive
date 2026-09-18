"""Render README panels in an isolated app using demonstration records.

Run with requirements-dev.txt. Set SPATIAL_BROWSER_PATH for an installed Chrome.
Only the reviewed documentation tissue crop is used; no live archive or browser profile is opened.
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
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
from block_archive.server import create_app
from block_archive import capture_review
from block_archive import inventory
def synthetic_photo(index):
    image=Image.new('RGB',(900,600),'#edf0e6')
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((110,55,790,525),radius=40,fill='#bcc3b2')
    draw.rounded_rectangle((145,90,755,485),radius=25,fill='#efdfb9')
    palette=['#c78673','#b9a184','#be8493','#d3a066']
    draw.ellipse((250+index*7,160,500+index*12,360),fill=palette[index])
    draw.ellipse((400,210-index*8,620,390),fill=palette[index])
    draw.line([(330,230),(400,280),(520,310)],fill='#9b786c',width=6)
    draw.text((175,110),'SYNTHETIC TISSUE',fill='#5b6554')
    data=io.BytesIO();image.save(data,'PNG');return data.getvalue()


def data_url(path):
    return ('data:image/jpeg;base64,' if path.suffix=='.jpg' else 'data:image/png;base64,')+base64.b64encode(path.read_bytes()).decode()


def main():
    with tempfile.TemporaryDirectory(prefix='readme-synthetic-') as tmp:
        folder=Path(tmp);sock=socket.socket();sock.bind(('127.0.0.1',0));origin='http://127.0.0.1:'+str(sock.getsockname()[1])
        app=create_app(folder/'data',{origin},'synthetic-readme-only-token');store=app.state.archive
        for i in range(4):
            block=store.create(f'DEMO-B{i+1}', 'Synthetic tissue block', 'DEMO',2026,'1','B',i+1)
            store.add_photo(block['id'],synthetic_photo(i),'baseline','DEMO','',block['version'])
        for i,item in enumerate(inventory.list_items(store)):
            photo=item['photos'][0]
            capture_review.save_review(store,item['key'],item['revision'],[{'photo_id':photo['id'],'group_name':item['name'],'role':'tissue'}],'DEMO',True,'identifier')
            # Previews use the same synthetic fixture, never photographs from an archive.
            cache=store.directory/'preview-cache/block-zone-v1';cache.mkdir(parents=True,exist_ok=True)
            Image.open(io.BytesIO(synthetic_photo(i))).save(cache/(photo['id']+'.jpg'))
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
                    const points=[[[394,201],[416,202],[415,340],[388,387],[377,381],[397,337]],[[419,204],[440,214],[441,260],[427,324],[438,378],[399,418],[388,406],[419,374],[412,325],[427,259]]];
                    const b={id:'demo-block',name:'DEMO-B1',donor:'',photo,identifier:null,mmPerPx:65/780,calibration:null,orientation:'Label end up',notes:'Synthetic demonstration',scores:[],regions:points.map((p,i)=>({id:'piece-'+i,name:'DEMO-B1 / '+(i+1),points:p,color:['#ca9987','#a7baa3'][i]}))};
                    state.blocks=[b];state.slides[0].placements=points.map((p,i)=>({id:'place-'+i,regionId:'piece-'+i,x:i?7:2.7,y:i?11.5:10.2,angle:0,mirror:false,confirmed:true,section:'Section '+(i+1)}));
                    // Additional demonstration blocks create a multiplexed layout.
                    // Sizes are in millimetres; the photographed block keeps its real scale.
                    const patches=[
                        [2,1.8,2,1.4,8], [5,1.8,2.2,1.4,-6], [8.3,2,1.4,2,12],
                        [8.65,6.7,.9,3,-5],
                        [2,11.1,2,1.2,5], [5.1,11.1,2.2,1.2,-5], [8.2,11.1,1.7,1.2,3],
                        [1.55,15.9,1.3,3.8,4],
                        [2,20.8,2,1.1,-4], [5.1,20.8,2.1,1.1,3], [8.1,20.8,1.8,1.1,-7]
                    ];
                    const palette=['#bdacc7','#d7be85','#91b6be','#baa995','#afbea0'];
                    patches.forEach(([x,y,w,h,angle],i)=>{
                        const outline=[[0,.15*h],[.65*w,0],[w,.25*h],[.9*w,.85*h],[.35*w,h],[0,.7*h]];
                        const region={id:'multiplex-'+i,name:'DEMO-B'+(i+2),points:outline,color:palette[i%palette.length]};
                        state.blocks.push({id:'other-block-'+i,name:region.name,donor:'',photo:null,identifier:null,mmPerPx:1,calibration:null,orientation:'Demonstration',notes:'Illustrative tissue geometry',scores:[],regions:[region]});
                        const placement={id:'other-place-'+i,regionId:region.id,x,y,angle,mirror:false,confirmed:true,section:'Section 1'};
                        const fits=()=>{const polygon=placed(placement);return polygon.every(([px,py])=>px>=.5&&px<=9.5&&py>=.5&&py<=21.5)&&state.slides[0].placements.every(other=>Geo.distance(polygon,placed(other))>.5)};
                        if(!fits()){
                            let found=false;
                            search:for(const rotation of [angle,0,90])for(let py=1;py<=21;py+=.3)for(let px=1;px<=9;px+=.3){
                                Object.assign(placement,{x:px,y:py,angle:rotation});
                                if(fits()){found=true;break search}
                            }
                            if(!found)throw Error('Demonstration tissue does not fit');
                        }
                        state.slides[0].placements.push(placement);
                    });
                    blockId=b.id;slideId=state.slides[0].id;selected=null;tab='slides';save();render();
                    const problems=issues(currentSlide()).filter(message=>/outside permitted|true polygon overlap|clearance is/.test(message));
                    if(problems.length)throw Error(problems.join('; '));
                }''',data_url(ROOT/'docs/assets/tissue-block.jpg'))
                planning=folder/'planning.png';page.locator('#slideSvg').screenshot(path=str(planning))
                page.evaluate("async () => {tab='blocks';render();await drawBlock()}")
                scoring=folder/'scoring.png';page.locator('#blockCanvas').screenshot(path=str(scoring))
                # Compose existing setup illustration and actual UI captures in HTML.
                setup=ROOT/'planner/artefacts/examples/phone-stand-17cm.png'
                cards=[('01','Photograph','Mat + matching QR labels',setup),('02','Archive','Review, label and select blocks',archive),('03','Plan spatial experiments','Score tissue. Assign recipient slides.',planning)]
                html='''<html><head><style>*{box-sizing:border-box}body{margin:0;background:#eef2eb;color:#234a40;font-family:Arial,sans-serif}.banner{width:1800px;padding:42px}.brand{font-size:17px;letter-spacing:3px;margin-bottom:26px}.panels{display:grid;grid-template-columns:.9fr 1fr 1.6fr;gap:24px}.panel{background:white;border:1px solid #d4dfd3;border-radius:20px;overflow:hidden}.head{padding:25px 26px 18px;height:136px}.step{font-size:15px;font-weight:bold;color:#78927a}h2{font-size:29px;letter-spacing:-.5px;margin:9px 0}p{font-size:18px;color:#6d7d70;margin:0}.image{height:555px;padding:12px 18px 22px;display:flex;align-items:center;justify-content:center;background:#fafbf7}img{max-width:100%;max-height:100%;object-fit:contain}.split{display:grid;grid-template-columns:1.4fr 1fr;gap:16px;align-items:center}.subpanel{height:504px;display:grid;grid-template-rows:30px 400px 50px;gap:12px;min-width:0}.subpanel h3{font-size:19px;margin:0;color:#426c5b}.subpanel img{height:400px;width:100%;object-fit:contain;min-height:0}.subpanel p{font-size:16px;line-height:1.4}.foot{display:flex;justify-content:space-between;font-size:15px;color:#677e6c;padding-top:23px}</style></head><body><div class="banner"><div class="brand">BLOCK ARCHIVE + SPATIAL PREP</div><div class="panels">'''
                for step,title,subtitle,path in cards:
                    html+=f'<section class="panel"><div class="head"><div class="step">{step}</div><h2>{title}</h2><p>{subtitle}</p></div>'
                    if step=='03':
                        html+=f'<div class="image split"><div class="subpanel"><h3>3a · Prepare the block</h3><img src="{data_url(scoring)}"><p>Outline retained tissue.<br>Dashed edges mark scoring lines.</p></div><div class="subpanel"><h3>3b · Multiplex tissues</h3><img src="{data_url(planning)}"><p>Pieces 1–2 from this block,<br>multiplexed with 11 other tissues.</p></div></div>'
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
