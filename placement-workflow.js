'use strict';
const meanPoint=points=>points.reduce((a,p)=>[a[0]+p[0]/points.length,a[1]+p[1]/points.length],[0,0]);
function applyScoringShape(regionId,points){
  if(!Geo.simple(points))throw Error('Keep at least three corners and avoid crossing edges.');
  const {b,r}=regionInfo(regionId),old=meanPoint(r.points),next=meanPoint(points);
  // Compensate for the changed vertex-average center so unchanged corners stay
  // fixed on every recipient, including rotated and mirrored placements.
  const delta=[(next[0]-old[0])*b.mmPerPx,(next[1]-old[1])*b.mmPerPx];
  for(const s of state.slides)for(const p of s.placements)if(p.regionId===regionId){const [shift]=Geo.transform([delta],0,0,p.angle,p.mirror);p.x+=shift[0];p.y+=shift[1];p.confirmed=false}
  r.points=points.map(p=>[...p]);b.scores=scoringEdges(b);
}
const previousValidation=updateValidation;
updateValidation=function(){
  const container=$('#validation');if(!container)return;
  const list=issues(currentSlide()),geometry=[],review=[];
  for(const message of list)(/outside permitted|true polygon overlap|clearance is|missing source|No retained|exceeds/.test(message)?geometry:review).push(message);
  container.replaceChildren();
  for(const [title,items] of [['Layout problems to fix',geometry],['Review before laboratory use',review]]){
    const heading=document.createElement('h4');heading.textContent=`${title} (${items.length})`;container.append(heading);
    if(items.length){const ul=document.createElement('ul');ul.className='issues';for(const text of items){const li=document.createElement('li');li.textContent=text;ul.append(li)}container.append(ul)}
  }
  const help=document.createElement('p');help.textContent=geometry.length?'Move, rotate or edit pieces to resolve red overlaps and clearance warnings. A clearance warning can be acknowledged beside the selected placement.':'Layout fits. Continue to review and export the technician handoff.';container.append(help);
  const config=document.createElement('button');config.textContent='Review assay settings';config.onclick=()=>{tab='config';render()};container.append(config);
};
const renderSlidesWithRotation=renderSlides;
renderSlides=function(){
  renderSlidesWithRotation();
  const bar=document.querySelector('.placement-rotation'),p=currentSlide().placements.find(p=>p.id===selected);
  document.querySelector('#confirmed')?.closest('p')?.remove();
  if(p){const conflicts=currentSlide().placements.filter(q=>q.id!==p.id&&footprint(q.regionId)&&Geo.distance(placed(p),placed(q))>0&&Geo.distance(placed(p),placed(q))<=state.config.gap+1e-8);for(const q of conflicts){const accept=document.createElement('button');accept.textContent='Accept this clearance';accept.onclick=()=>{p.acceptedClearance=[...(p.acceptedClearance||[]),q.id];save();render()};bar.append(accept)}}
  const edit=document.createElement('button');edit.textContent='Edit scoring shape';edit.disabled=!p;edit.onclick=()=>editScoringShape(p);bar.append(edit);
  const next=document.createElement('button');next.className='primary';next.textContent='Continue to review & export →';next.onclick=()=>{tab='handoff';render()};const row=document.createElement('div');row.className='toolbar';row.append(next);document.querySelector('.placement-map').append(row);
};
const originalSlideSVGForWarnings=slideSVG;
slideSVG=function(slide,interactive=false){
  let html=originalSlideSVGForWarnings(slide,interactive);
  if(!interactive)return html;
  for(const p of slide.placements){const poly=footprint(p.regionId)&&placed(p),overlap=poly&&slide.placements.some(q=>q.id!==p.id&&footprint(q.regionId)&&Geo.distance(poly,placed(q))<=1e-8);if(overlap){const needle=`data-placement="${p.id}"`;html=html.replace(needle,needle+' data-overlap="true"');const re=new RegExp('(data-placement="'+p.id+'"[^>]*>[^<]*<polygon[^>]*stroke=")[^"]+');html=html.replace(re,'$1#b32929')}}
  return html;
};
async function editScoringShape(placement){
  const {b,r}=regionInfo(placement.regionId),img=await blockImage(b);if(!img)return notify('A tissue photo is needed to edit scoring.');
  let points=r.points.map(p=>[...p]),active=0,drag=null;
  const originalCenter=meanPoint(r.points),count=state.slides.reduce((n,s)=>n+s.placements.filter(p=>p.regionId===r.id).length,0);
  const dialog=document.createElement('dialog');dialog.className='shape-editor';
  dialog.innerHTML='<h2>Edit scoring shape</h2><p class="shape-context"></p><p>Drag the numbered corners over the tissue photo. The slide preview updates as you edit. Apply updates the source block’s scoring lines and every placement of this piece.</p><div class="two-col"><div><h3>Tissue-side scoring boundary</h3><svg class="shape-source" aria-label="Edit scoring polygon"></svg></div><div><h3>Slide fit preview</h3><div class="shape-preview"></div><p class="shape-status" role="status"></p></div></div><div class="toolbar"><label>Corner<select class="corner-choice"></select></label><label>X (photo pixels)<input class="corner-x" type="number" step="1"></label><label>Y (photo pixels)<input class="corner-y" type="number" step="1"></label><button class="add-corner">Add corner after selected</button><button class="remove-corner">Remove selected corner</button></div><div class="toolbar"><button class="apply primary">Apply shape to block & slides</button><button class="cancel">Cancel</button></div>';
  dialog.querySelector('.shape-context').textContent=`${r.name} · ${count} placement(s) share this scoring boundary.`;
  const source=dialog.querySelector('.shape-source');source.setAttribute('viewBox',`0 0 ${img.width} ${img.height}`);
  const ns='http://www.w3.org/2000/svg',photo=document.createElementNS(ns,'image');photo.setAttribute('href',b.photo);photo.setAttribute('width',img.width);photo.setAttribute('height',img.height);source.append(photo);
  const overlay=document.createElementNS(ns,'g');source.append(overlay);
  function draw(){
    overlay.replaceChildren();const polygon=document.createElementNS(ns,'polygon');polygon.setAttribute('points',points.map(p=>p.join(',')).join(' '));polygon.setAttribute('fill','#24665d44');polygon.setAttribute('stroke','#24665d');polygon.setAttribute('stroke-width',img.width/300);overlay.append(polygon);
    points.forEach((p,i)=>{const circle=document.createElementNS(ns,'circle');circle.dataset.vertex=i;circle.setAttribute('cx',p[0]);circle.setAttribute('cy',p[1]);circle.setAttribute('r',img.width/65);circle.setAttribute('fill',i===active?'#edb44c':'white');circle.setAttribute('stroke','#203e40');overlay.append(circle);const text=document.createElementNS(ns,'text');text.textContent=i+1;text.setAttribute('x',p[0]);text.setAttribute('y',p[1]);text.setAttribute('text-anchor','middle');text.setAttribute('dominant-baseline','middle');text.setAttribute('font-size',img.width/45);text.style.pointerEvents='none';overlay.append(text)});
    const choice=dialog.querySelector('.corner-choice');choice.replaceChildren();points.forEach((p,i)=>{const opt=document.createElement('option');opt.value=i;opt.textContent=i+1;choice.append(opt)});choice.value=active;dialog.querySelector('.corner-x').value=Math.round(points[active][0]);dialog.querySelector('.corner-y').value=Math.round(points[active][1]);
    const preview=dialog.querySelector('.shape-preview');preview.innerHTML=slideSVG(currentSlide(),true);preview.querySelector('svg').removeAttribute('id');
    const poly=Geo.transform(points.map(p=>[(p[0]-originalCenter[0])*b.mmPerPx,(p[1]-originalCenter[1])*b.mmPerPx]),placement.x,placement.y,placement.angle,placement.mirror);
    preview.querySelector(`[data-placement="${placement.id}"] polygon`).setAttribute('points',poly.map(p=>p.join(',')).join(' '));
    const c=state.config,bounds=poly.some(([x,y])=>x<c.margin||y<c.margin||x>c.width-c.margin||y>c.height-c.margin),clashes=currentSlide().placements.filter(p=>p.id!==placement.id&&p.regionId!==r.id&&Geo.distance(poly,placed(p))<=c.gap+1e-8).length;
    const valid=Geo.simple(points);dialog.querySelector('.apply').disabled=!valid;
    dialog.querySelector('.shape-status').textContent=!valid?'Polygon edges cross or area is zero. Adjust the corners.':`${(Geo.area(points)*b.mmPerPx**2).toFixed(1)} mm² · ${bounds?'Outside slide margin':'Within slide margin'} · ${clashes} spacing conflict(s) with other pieces. All placements are checked after applying.`;
  }
  source.onpointerdown=e=>{if(e.target.dataset.vertex===undefined)return;active=Number(e.target.dataset.vertex);drag=active;source.setPointerCapture(e.pointerId);draw()};
  source.onpointermove=e=>{if(drag===null)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(source.getScreenCTM().inverse());points[drag]=[Math.max(0,Math.min(img.width,p.x)),Math.max(0,Math.min(img.height,p.y))];draw()};
  source.onpointerup=source.onpointercancel=()=>{drag=null};
  dialog.querySelector('.corner-choice').onchange=e=>{active=Number(e.target.value);draw()};
  for(const [selector,axis,max] of [['.corner-x',0,img.width],['.corner-y',1,img.height]])dialog.querySelector(selector).onchange=e=>{const value=Number(e.target.value);if(Number.isFinite(value)){points[active][axis]=Math.max(0,Math.min(max,value));draw()}};
  dialog.querySelector('.add-corner').onclick=()=>{const a=points[active],b=points[(active+1)%points.length];points.splice(active+1,0,[(a[0]+b[0])/2,(a[1]+b[1])/2]);active++;draw()};
  dialog.querySelector('.remove-corner').onclick=()=>{if(points.length<=3)return;points.splice(active,1);active=Math.min(active,points.length-1);draw()};
  dialog.querySelector('.cancel').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();
  dialog.querySelector('.apply').onclick=()=>{applyScoringShape(r.id,points);save();dialog.close();render();notify('Scoring shape updated on the block and all its placements. Recheck section orientation.')};
  document.body.append(dialog);dialog.showModal();draw();
}
