'use strict';
let activePanel = 'capture';
const needsCaptureAnalysis=photo=>!photo.analysis||(photo.analysis.calibrated&&photo.analysis.printingEvidence?.version!=='rim-text-v2');
function showPanel(name) {
  if (!['capture','review','inventory','metadata'].includes(name)) name='capture';
  activePanel=name;
  for(const button of document.querySelectorAll('[data-panel]')){
    const chosen=button.dataset.panel===name;button.setAttribute('aria-selected',String(chosen));button.tabIndex=chosen?0:-1;
    document.getElementById(button.getAttribute('aria-controls')).hidden=!chosen;
  }
  history.replaceState({},'', '#'+name);
  if(name==='metadata')loadMetadata().catch(error=>message(error.message,true));
  if(name==='review')renderQC();
}
document.querySelectorAll('[data-panel]').forEach(button=>{
  button.onclick=()=>showPanel(button.dataset.panel);
  button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const buttons=[...document.querySelectorAll('[data-panel]')],index=buttons.indexOf(button);const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;showPanel(buttons[next].dataset.panel);buttons[next].focus();};
});
document.querySelectorAll('[data-go]').forEach(button=>button.onclick=()=>showPanel(button.dataset.go));
$('#captureImport').onclick=()=>$('#importFolder').click();
$('#showAllQC').onchange=renderQC;
function renderQC(){
  const records=[...items.values()],pending=records.filter(item=>item.qc.status!=='ready'),ready=records.length-pending.length;
  $('#qcSummary').textContent=`${ready} groups ready · ${pending.length} need attention. Clear pairs need no confirmation.`;
  $('#qcBadge').textContent=pending.length?String(pending.length):'';
  const unanalyzed=records.flatMap(item=>item.photos).filter(needsCaptureAnalysis).length;
  $('#analyzeExisting').textContent=unanalyzed?`Analyze / update ${unanalyzed} photos`:'Photo analysis is up to date';
  $('#analyzeExisting').disabled=!unanalyzed||busy;
  const shown=$('#showAllQC').checked?records:pending;
  $('#qcGroups').innerHTML=shown.length?shown.map(item=>{
    const qc=item.qc;
    return `<details class="qc-group" data-qc-key="${esc(item.key)}"><summary><strong>${esc(item.name)}</strong><span class="${qc.status==='ready'?'qc-ready':'qc-warning'}">${qc.status==='ready'?'Ready · '+qc.method:qc.problems.length+' checks to review'}</span></summary><div class="qc-body"><p class="side-explanation">${esc(qc.side_evidence||'')}</p>${qc.problems.length?`<ul>${qc.problems.map(problem=>`<li>${esc(problem)}</li>`).join('')}</ul>`:'<p>Two views, usable mat calibration, and distinct sides. Ready for planning.</p>'}<form class="qc-form"><div class="qc-photos">${item.photos.map(photo=>{
      const role=photo.assignment?.role||(photo.id===qc.tissue_id?'tissue':photo.id===qc.identifier_id?'identifier':'unknown');
      return `<section class="qc-photo" data-photo-id="${photo.id}"><a href="${esc(photo.url)}" target="_blank" rel="noopener"><img src="${esc(photo.thumbnail_url)}" alt="Review photo of ${esc(item.name)}" loading="lazy"></a><strong class="side-caption">${role==='tissue'?'Tissue side':role==='identifier'?'Identifier side':'Side not resolved'} · ${photo.assignment?.role&&photo.assignment.role!=='unknown'?'Operator assignment':role!=='unknown'?'Automatic detection':'Needs review'}</strong><small>${esc(photo.filename||photo.kind||'Archive photo')}</small><small>${photo.analysis?.printingEvidence?.version==='rim-text-v2'?'Aligned rim marks: '+(Number.isFinite(photo.analysis.printingEvidence.score)?photo.analysis.printingEvidence.score:'unavailable')+' · '+(photo.analysis.printingEvidence.polarity==='light'?'light contrast':'dark contrast')+' · detector v2':'Upper-rim printing features: '+(Number.isFinite(photo.analysis?.labelFeatures)?photo.analysis.labelFeatures:'not analyzed')}</small><small>QR: ${esc((photo.analysis?.qrValues||photo.barcodes||[]).join(' · ')||'No readable ID')} · Mat: ${photo.analysis?(photo.analysis.calibrated?'calibrated':'needs review'):'not analyzed'}</small><label>Matching block ID<input class="qc-name" value="${esc(item.name)}" maxlength="120" required ${item.kind==='block'?'readonly':''}></label><label>Side<select class="qc-role"><option value="unknown" ${role==='unknown'?'selected':''}>Choose side…</option><option value="tissue" ${role==='tissue'?'selected':''}>Tissue side</option><option value="identifier" ${role==='identifier'?'selected':''}>Identifier side</option></select></label><button type="button" class="analyze-one" data-source="${item.kind==='block'?'photos':'imports'}" data-id="${photo.id}">${photo.analysis?'Reanalyze':'Analyze photo'}</button></section>`;
    }).join('')}</div><label>Missing photo exception<select class="qc-missing-side"><option value="">Both sides required</option><option value="tissue" ${qc.missing_side==='tissue'?'selected':''}>Continue without tissue side</option><option value="identifier" ${qc.missing_side==='identifier'?'selected':''}>Continue without identifier side</option></select></label><label class="check-label"><input class="qc-accept" type="checkbox"> I checked grouping, photo sides and image quality, and reviewed the flags above.</label><p class="field-help">With missing mat calibration, the planner will still require manual calibration. A declared missing side can continue after QC confirmation. Without a tissue photo, the experiment keeps the block record but cannot score it. Saving groups lets you combine or split photos before accepting QC.</p><p class="form-error" role="alert"></p><button class="primary" type="submit">Save grouping & sides</button></form></div></details>`;
  }).join(''):'<div class="inventory-empty"><h2>No import problems to review.</h2><p>Continue to the inventory to select blocks for an experiment.</p></div>';
  document.querySelectorAll('.qc-form').forEach(form=>form.onsubmit=async event=>{
    event.preventDefault();if(busy)return;const group=form.closest('[data-qc-key]'),item=items.get(group.dataset.qcKey),button=form.querySelector('[type="submit"]');
    try{const operator=actor();busy=true;button.disabled=true;const photos=[...form.querySelectorAll('[data-photo-id]')].map(section=>({photo_id:section.dataset.photoId,group_name:section.querySelector('.qc-name').value.trim(),role:section.querySelector('.qc-role').value}));
      await api('/api/v1/inventory/review',{method:'POST',body:{key:item.key,revision:item.revision,photos,actor:operator,accept_qc:form.querySelector('.qc-accept').checked,missing_side:form.querySelector('.qc-missing-side').value}});
      await load();message('Grouping and sides saved. Only unresolved problems remain in the queue.');
    }catch(error){form.querySelector('.form-error').textContent=error.message;}finally{busy=false;button.disabled=false;selectionUI();$('#analyzeExisting').disabled=![...items.values()].some(item=>item.photos.some(needsCaptureAnalysis));}
  });
  document.querySelectorAll('.analyze-one').forEach(button=>button.onclick=()=>analyzeCaptures([{photo_id:button.dataset.id,source:button.dataset.source}]));
}
async function analyzeCaptures(entries){
  if(busy)return;
  try{const operator=actor();busy=true;selectionUI();$('#analyzeExisting').disabled=true;let failures=0;
    for(const [index,entry] of entries.entries()){message(`Checking photograph ${index+1} of ${entries.length}…`);try{const result=await api('/api/v1/inventory/analyze',{method:'POST',body:{...entry,actor:operator}});if(result.status!=='analyzed')failures++;}catch(_){failures++;}}
    await load();message(`Photo analysis complete.${failures?' '+failures+' photos need review.':''}`);
  }catch(error){message(error.message,true);}finally{busy=false;selectionUI();renderQC();}
}
$('#analyzeExisting').onclick=()=>analyzeCaptures([...items.values()].flatMap(item=>item.photos.filter(needsCaptureAnalysis).map(photo=>({photo_id:photo.id,source:item.kind==='block'?'photos':'imports'}))));
document.addEventListener('inventory-loaded',()=>{renderQC();if(typeof updateMetadataFilters==='function')updateMetadataFilters();if(activePanel==='metadata')loadMetadata().catch(error=>message(error.message,true));});
document.addEventListener('DOMContentLoaded',()=>{if(!new URLSearchParams(location.search).get('block'))showPanel(location.hash.slice(1)||'capture');});
