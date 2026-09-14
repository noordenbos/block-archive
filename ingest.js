'use strict';
// Keep placement rotation beside the map even when the inspector wraps below it.
const originalRenderSlides=renderSlides;
renderSlides=function(){
  originalRenderSlides();
  const slide=currentSlide(),stage=document.querySelector('.slide-stage');
  const controls=document.createElement('div');controls.className='placement-rotation';
  const choice=document.createElement('select');choice.setAttribute('aria-label','Piece to rotate');
  const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Select a piece to rotate';choice.append(placeholder);
  for(const [i,p] of slide.placements.entries()){const option=document.createElement('option');option.value=p.id;option.textContent=`${i+1}. ${regionInfo(p.regionId)?.r.name||p.section}`;choice.append(option)}
  choice.value=selected||'';choice.onchange=()=>{selected=choice.value;render()};controls.append(choice);
  const p=slide.placements.find(p=>p.id===selected);
  const row=document.createElement('div');row.className='toolbar';controls.append(row);
  function rotate(value){if(!p||!Number.isFinite(value))return;p.angle=((value%360)+360)%360;p.confirmed=false;angle.value=p.angle;slider.value=p.angle;$('#angle').value=p.angle;$('#confirmed').checked=false;const holder=document.createElement('div');holder.innerHTML=slideSVG(slide,true);$('#slideSvg').innerHTML=holder.firstChild.innerHTML;updateValidation()}
  for(const [text,delta] of [['↶ 90°',-90],['↶ 15°',-15],['↷ 15°',15],['↷ 90°',90]]){const button=document.createElement('button');button.textContent=text;button.disabled=!p;button.setAttribute('aria-label',`Rotate ${Math.abs(delta)} degrees ${delta<0?'counterclockwise':'clockwise'}`);button.onclick=()=>{rotate(p.angle+delta);save()};row.append(button)}
  const label=document.createElement('label');label.textContent='Clockwise angle (°)';label.className='field';
  const angle=document.createElement('input');angle.type='number';angle.step='1';angle.value=p?.angle||0;angle.disabled=!p;angle.setAttribute('aria-label','Placement rotation degrees');angle.oninput=()=>{if(angle.value!=='')rotate(Number(angle.value))};angle.onchange=()=>save();label.append(angle);row.append(label);
  const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='359';slider.step='1';slider.value=p?.angle||0;slider.disabled=!p;slider.setAttribute('aria-label','Rotate selected piece');slider.oninput=()=>rotate(Number(slider.value));slider.onchange=()=>save();controls.append(slider);
  const map=document.createElement('div');map.className='placement-map';stage.before(map);map.append(controls,stage);
};
// Folder workflow supersedes the original demo-only ingest controls.
const legacyRender=render, legacySave=save;
let ingestBusy=false;
function scoringEdges(b){return b.regions.flatMap(r=>r.points.map((p,i)=>[p,r.points[(i+1)%r.points.length]]))}
save=function(){for(const b of state.blocks){if(!b.legacyScores&&b.scores.length)b.legacyScores=structuredClone(b.scores);b.scores=scoringEdges(b)}legacySave()};
function boundaryError(b){
  if(!b.analysis)return null;
  const settings=state.captureBounds||{maxHeight:12,minDistance:350,tolerance:1};
  let span=0;for(const r of b.regions){const p=footprint(r.id);if(p)for(const a of p)for(const c of p)span=Math.max(span,Math.hypot(a[0]-c[0],a[1]-c[1]))}
  // Full-span bound (conservative) for h/D perspective magnification, plus pixel allowance.
  return {mm:span*settings.maxHeight/(settings.minDistance-settings.maxHeight)+.15,settings};
}
const legacyIssues=issues;
issues=function(s){const list=legacyIssues(s);for(const p of s.placements){const info=regionInfo(p.regionId);if(!info)continue;const bound=boundaryError(info.b);if(bound&&bound.mm>bound.settings.tolerance)list.push(`${info.b.name}: estimated boundary error ${bound.mm.toFixed(2)} mm exceeds ${bound.settings.tolerance} mm scoring tolerance.`)}return [...new Set(list)]};
render=function(){legacyRender();if(tab!=='blocks')return;
  if(location.protocol==='file:'&&!document.querySelector('#fileProtocolNotice')){const n=document.createElement('div');n.id='fileProtocolNotice';n.className='notice';n.innerHTML='<b>Run the local server first.</b> This page was opened as a file. Open <a href="http://127.0.0.1:8774/">http://127.0.0.1:8774</a> after starting <code>python server.py</code>; folder ingest cannot call the analyzer from file://.';$('#content').prepend(n)}
  const old=$('#folderUpload');if(old)old.parentElement.remove();
  const actions=$('#addBlock').parentElement;
  const label=document.createElement('label');label.className='button';label.innerHTML='Ingest photo folder<input type="file" webkitdirectory multiple hidden accept="image/jpeg,image/png,image/webp">';label.querySelector('input').onchange=ingestFolder;actions.prepend(label);
  const link=document.createElement('a');link.className='button';link.href='labels.html';link.target='_blank';link.textContent='Print ID + QR labels';actions.append(link);
  document.querySelector('[data-mode="score"]')?.remove();$('#undoScore')?.remove();
  const outline=document.querySelector('[data-mode="roi"]');if(outline)outline.textContent='Draw scoring polygon';
  if($('#drawHint'))$('#drawHint').textContent='Draw the retained piece boundary. Each polygon edge is a scoring line. Click Finish piece to save, then Continue to slide mapping.';
  if($('#finishROI'))$('#finishROI').classList.add('primary');
  if($('#finishROI')){const next=document.createElement('button');next.textContent='Continue to slide mapping →';next.onclick=()=>{if(draft.length){notify('Finish or cancel the current polygon first.');return}tab='slides';render()};$('#finishROI').parentElement.append(next)}
  const b=currentBlock();if(b?.analysis){document.querySelector('[data-mode="calibrate"]')?.remove();const a=b.analysis,err=boundaryError(b),note=document.createElement('div');note.className='notice';note.innerHTML=`Auto-oriented from marker IDs ${a.markerIds.join(', ')}. Scale: 20 px/mm, from the printed block zone. Perspective corrected.<br>Height is not measured. Assumed upper bound ${err.settings.maxHeight} mm at camera distance ≥${err.settings.minDistance} mm. Boundary error estimate: ${err.mm.toFixed(2)} mm; tolerance ${err.settings.tolerance} mm.`;$('.photo-area').before(note)}
  const details=document.createElement('details');details.className='card';details.style.marginTop='18px';details.innerHTML='<summary>Capture geometry and scoring tolerance</summary><p>Bounds are capture assumptions, not measurements recovered from the photograph. Print the mat at actual size. No per-photo ruler clicks are needed.</p>';
  const settings=state.captureBounds||{maxHeight:12,minDistance:350,tolerance:1};
  for(const [key,title] of [['maxHeight','Maximum block-face height above paper (mm)'],['minDistance','Minimum camera distance to paper (mm)'],['tolerance','Allowed scoring error (mm)']]){const l=document.createElement('label');l.className='field';l.textContent=title;const input=document.createElement('input');input.type='number';input.min='.1';input.value=settings[key];input.onchange=()=>{const value=Number(input.value),next={...settings,[key]:value};if(!Number.isFinite(value)||value<=0||next.maxHeight>=next.minDistance){notify('Use positive values, with height smaller than camera distance.');return}state.captureBounds=next;save();render()};l.append(input);details.append(l)}$('#content').append(details);
  renderIngestSummary();
};
function renderIngestSummary(){
  $('#ingestSummary')?.remove();if(!state.ingestReport?.length)return;
  const box=document.createElement('section');box.className='card';box.id='ingestSummary';box.style.marginTop='18px';const title=document.createElement('h3');title.textContent='Folder ingest results';box.append(title);
  const successes=state.ingestReport.filter(r=>/^Paired/.test(r.status)),failures=state.ingestReport.filter(r=>!/^Paired/.test(r.status));
  const summary=document.createElement('p');summary.className=successes.length===state.ingestReport.length?'good':'notice';summary.textContent=`${successes.length}/${state.ingestReport.length} cases paired, oriented and calibrated automatically.`;box.append(summary);
  if(failures.length){const details=document.createElement('details');details.open=true;const heading=document.createElement('summary');heading.textContent=`${failures.length} cases need attention`;details.append(heading);for(const r of failures){const row=document.createElement('p');row.textContent=`${r.id||r.name}: ${r.status}`;details.append(row)}box.append(details)}
  if(state.pendingCaptures?.some(p=>p.source)){
    const retry=document.createElement('button');retry.textContent='Reanalyze retained photos';retry.disabled=ingestBusy;
    retry.onclick=async()=>{if(ingestBusy)return;retry.disabled=true;try{const files=[];for(const p of state.pendingCaptures){if(!p.source?.startsWith('data:image/'))continue;const blob=await(await fetch(p.source)).blob();files.push(new File([blob],p.name,{type:blob.type}))}await ingestFolder({target:{files,value:''}})}catch(e){notify('Reanalysis failed: '+e.message)}finally{retry.disabled=false}};box.append(retry);
  }
  if(state.pendingCaptures?.length){const p=document.createElement('p');p.textContent=`${state.pendingCaptures.length} unresolved images retained across this project and its backup.`;box.append(p);for(const capture of state.pendingCaptures){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=capture.name;details.append(summary);const evidence=document.createElement('p');evidence.className='muted';evidence.textContent=`QR: ${capture.qrValues?.join(', ')||'unreadable'} · markers: ${capture.markerIds?.join(', ')||'none'} · grid features: ${capture.gridFeatures??'n/a'} · calibrated: ${capture.calibration?'yes':'no'}`;details.append(evidence);const img=new Image();img.src=capture.canonical||capture.source;img.style.maxWidth='360px';img.alt='Preserved capture '+capture.name;details.append(img);if(capture.qrValues?.length===1&&capture.calibration){const tools=document.createElement('div');tools.className='toolbar';for(const [role,label] of [['tissue','Use as tissue side'],['identifier','Use as identifier side']]){const button=document.createElement('button');button.textContent=label;button.onclick=()=>manualResolve(capture.hash,role);tools.append(button)}details.append(tools)}box.append(details)}}$('#content').prepend(box);
}
function createPairedBlock(id,tissue,identifier,status='Paired, oriented and calibrated automatically. Ready to draw scoring polygon.'){
  const b={id:uid(),name:id,donor:'',photo:tissue.photo,identifier:identifier.canonical,mmPerPx:.05,
    calibration:{points:[[0,0],[1300,0]],length:65,provisional:false,method:'Automatic marker registration'},
    analysis:{...tissue,photo:undefined,canonical:undefined,source:undefined},
    sources:[tissue,identifier].map(a=>({name:a.name,hash:a.hash,image:a.source,canonical:a.canonical,transform:a.transform,role:a===tissue?'tissue':'identifier'})),
    orientation:'TOP / LABEL END is up. Page registered from the numbered corner markers; no reflection applied.',notes:'Polygon edges are the scoring boundary; separate surrounding padding in the water bath.',scores:[],regions:[]};
  state.blocks.push(b);blockId=b.id;state.pendingCaptures=(state.pendingCaptures||[]).filter(p=>p.hash!==tissue.hash&&p.hash!==identifier.hash);state.ingestReport.push({id,status});return b;
}
function manualResolve(hash,role){
  const chosen=state.pendingCaptures.find(p=>p.hash===hash);if(!chosen||chosen.qrValues?.length!==1)return notify('This capture has no single usable QR ID.');
  const id=chosen.qrValues[0],pair=state.pendingCaptures.filter(p=>p.qrValues?.length===1&&p.qrValues[0]===id&&p.calibration);
  if(pair.length!==2)return notify(`Manual assignment needs exactly two calibrated captures for ${id}.`);
  if(pair.some(p=>p.identityConflict))return notify('Correct the conflicting QR label before pairing these photos.');
  if(state.blocks.some(b=>b.name===id))return notify(`Block ${id} already exists.`);
  const other=pair.find(p=>p.hash!==hash);createPairedBlock(id,role==='tissue'?chosen:other,role==='identifier'?chosen:other,'Paired after manual tissue/identifier assignment. Ready to draw scoring polygon.');save();photoZoom=1;draft=[];render();notify(`${id} paired from the retained captures.`);
}
const fileData=f=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(f)});
ingestFolder=async function(e){
  if(location.protocol==='file:'){e.target.value='';return notify('Folder ingest needs the local server. Start python server.py, then open http://127.0.0.1:8774.');}
  if(ingestBusy)return notify('An ingest is already running.');
  const files=[...e.target.files].filter(f=>/\.(jpe?g|png|webp)$/i.test(f.name));if(!files.length)return notify('No supported photos found.');
  if(files.reduce((s,f)=>s+f.size,0)>100*1024*1024)return notify('Import batches up to 100 MB to keep local browser storage manageable.');
  ingestBusy=true;state.ingestReport=[];state.pendingCaptures=state.pendingCaptures||[];const analyzed=[];
  try{for(let i=0;i<files.length;i++){
    const f=files[i];notify(`Analyzing image ${i+1} of ${files.length} locally…`);
    try{if(f.size>25*1024*1024)throw Error('Image exceeds 25 MB.');const response=await fetch('/api/analyze',{method:'POST',headers:{'X-Spatial-Local':'1','Content-Type':'application/octet-stream'},body:f});if(!response.ok)throw Error('Image analysis failed.');const a=await response.json();a.name=f.name;a.source=await fileData(f);analyzed.push(a)}catch(err){state.ingestReport.push({name:f.name,status:err.message});state.pendingCaptures.push({name:f.name,source:await fileData(f),error:err.message})}
  }
  const groups=new Map();for(const a of analyzed){const key=a.qrValues.length===1?a.qrValues[0]:'UNRESOLVED-'+a.hash;if(!groups.has(key))groups.set(key,[]);if(!groups.get(key).some(x=>x.hash===a.hash))groups.get(key).push(a)}
  for(const [id,pair] of groups){
    let reason='';if(id.startsWith('UNRESOLVED-'))reason='No single readable QR; image retained.';
    else if(pair.some(a=>a.identityConflict))reason=pair.find(a=>a.identityConflict).identityConflict;
    else if(pair.length!==2)reason=`Expected two distinct views, found ${pair.length}. Images retained.`;
    else if(pair.some(a=>!a.calibration||a.rotationDegrees===null))reason='Template orientation or block-zone geometry missing.';
    const sorted=[...pair].sort((a,b)=>(a.labelFeatures??0)-(b.labelFeatures??0));
    if(!reason&&(!pair.every(a=>Number.isFinite(a.labelFeatures))||sorted[1].labelFeatures<12||sorted[1].labelFeatures-sorted[0].labelFeatures<10))reason='Upper-rim printing does not clearly distinguish the two sides; images retained for manual assignment.';
    if(!reason&&state.blocks.some(b=>b.name===id))reason='A block with this ID already exists; existing scoring preserved. Images retained.';
    if(reason){for(const a of pair){const existing=state.pendingCaptures.findIndex(p=>p.hash===a.hash);if(existing>=0)state.pendingCaptures[existing]=a;else state.pendingCaptures.push(a)}state.ingestReport.push({id,status:reason});continue}
    const [tissue,identifier]=sorted;createPairedBlock(id,tissue,identifier);
  }
  save();photoZoom=1;draft=[];render();notify('Folder ingest complete. Results and unresolved captures are listed below.');
  }finally{ingestBusy=false;e.target.value=''}
};
// Replace the former hard-coded rename action with the standalone label tool.
const listControl=$('#idListUpload');if(listControl){const a=document.createElement('a');a.className='button';a.href='labels.html';a.target='_blank';a.textContent='ID + QR labels';listControl.parentElement.replaceWith(a)}
