'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {archived:'In archive',checked_out:'Checked out',awaiting_archive:'To rearchive'};
const photoLabels = {baseline:'Initial archive',post_cut:'After cutting',reference:'Reference'};
const eventLabels = {import_confirmed:'Historical photo linked',registered:'Block registered',checkout:'Checked out for cutting',complete_cut:'Cutting completed',rearchive:'Returned to archive',photo_added:'Photo recorded',external_link_saved:'Data reference saved',details_updated:'Description updated'};
let selected=null, shownPhoto=null, filter='', offset=0, nextOffset=null, queryGeneration=0, selectionGeneration=0, busy=false;
const date = value => new Date(value).toLocaleString([], {year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
function message(text, error=false) { const box=$('#message'); box.hidden=false;box.classList.toggle('error',error);box.textContent=text; }
function actor() {const value=$('#operator').value.trim();if(!value){$('#operator').focus();throw Error('Enter the operator name or initials before recording a change.');}return value;}
async function api(path, options={}) {
  const headers={...options.headers};
  if(options.method && options.method!=='GET')headers['X-Archive-Request']='1';
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers,credentials:'same-origin'});
  if(!response.ok){let body;try{body=await response.json();}catch{body={detail:'Could not reach the archive.'};}
    const detail=Array.isArray(body.detail)?body.detail.map(d=>d.msg).join('; '):body.detail;
    const error=Error(detail||'Request failed.');error.status=response.status;throw error;}
  return response.json();
}
async function loadList(){
  const generation=++queryGeneration, params=new URLSearchParams({query:$('#search').value.trim(),sort:$('#sort').value,offset,limit:30});
  if(filter)params.set('status',filter);if($('#year').value)params.set('year',$('#year').value);
  try{const data=await api('/api/v1/blocks?'+params);if(generation!==queryGeneration)return;
    $('#archivedCount').textContent=data.counts.archived;$('#pendingCount').textContent=data.counts.awaiting_archive;$('#outCount').textContent=data.counts.checked_out;
    $('#resultsCount').textContent=`${data.total} ${data.total===1?'block':'blocks'}${data.total?' · '+(offset+1)+'–'+Math.min(offset+30,data.total):''}`;
    $('#blockList').innerHTML=data.items.length?data.items.map(b=>`<button class="block-card ${selected?.id===b.id?'selected':''}" data-block="${esc(b.id)}">${b.thumbnail_url?`<img class="thumb" src="${esc(b.thumbnail_url)}" alt="Archive photo of ${esc(b.block_code)}" loading="lazy">`:'<span class="thumb-placeholder" aria-hidden="true">▦</span>'}<div><strong>${esc(b.block_code)}</strong><small>${esc(b.location)} · ${b.photo_count} ${b.photo_count===1?'photo':'photos'}</small><span class="badge ${b.status}">${labels[b.status]}</span></div></button>`).join(''):'<div class="empty-note">No blocks match this view. Search another code or register a new block.</div>';
    document.querySelectorAll('[data-block]').forEach(button=>button.onclick=()=>selectBlock(button.dataset.block));
    nextOffset=data.next_offset;$('#previous').disabled=offset===0;$('#next').disabled=nextOffset===null;
  }catch(error){if(generation===queryGeneration)message(error.message,true);}
}
async function selectBlock(id, updateURL=true){
  const generation=++selectionGeneration;
  try{const record=await api('/api/v1/blocks/'+encodeURIComponent(id));if(generation!==selectionGeneration)return;
    selected=record;shownPhoto=record.current_photo_id||record.photos[0]?.id;renderRecord();
    document.querySelectorAll('[data-block]').forEach(b=>b.classList.toggle('selected',b.dataset.block===id));
    if(updateURL)history.pushState({},'', '/archive?block='+encodeURIComponent(record.block_code));
  }catch(error){message(error.message,true);}
}
function workflow(record){
  if(record.status==='archived')return `<h3>Ready in the archive</h3><p>Check this block out when it leaves its filing position for cutting.</p><label>Cutting note<textarea id="movementNote" maxlength="2000" placeholder="Optional reason or cutting instructions"></textarea></label><button class="primary" id="checkout" data-mutate>Check out for cutting</button>`;
  if(record.status==='checked_out')return `<h3>With the technician</h3><p>When cutting is finished, mark it complete. Then take a new photo before returning the block.</p><label>Cutting note<textarea id="movementNote" maxlength="2000" placeholder="Optional cutting details"></textarea></label><button class="primary" id="completeCut" data-mutate>Mark cutting complete</button>`;
  const kind=record.cycle?'post_cut':'baseline', candidate=record.photos.find(p=>p.cycle===record.cycle&&p.kind===kind);
  return `<h3>${record.cycle?'Photograph after cutting':'Record the first archive photo'}</h3><p>${record.cycle?'Take a new photo showing the block after cutting, then return it to its year–case filing position.':'Take a photo and confirm the block’s first position in the archive.'}</p><label>${record.cycle?'New post-cutting photo':'Initial block photo'}<input id="archivePhoto" type="file" accept="image/jpeg,image/png,image/webp" capture="environment"></label><p class="small">JPEG, PNG or WebP · up to 20 MB</p>${candidate?`<div class="ready">New photo recorded ${esc(date(candidate.created_at))} by ${esc(candidate.actor)}.</div>`:''}<label>Return note<textarea id="movementNote" maxlength="2000" placeholder="Optional note about this return"></textarea></label><button class="primary" id="rearchive" data-photo="${candidate?.id||''}" data-mutate ${candidate?'':'disabled'}>Confirm archived at ${esc(record.location)}</button>`;
}
function renderRecord(){
  const b=selected;if(!b)return;
  const photo=b.photos.find(p=>p.id===shownPhoto)||b.photos.find(p=>p.id===b.current_photo_id)||b.photos[0];
  $('#record').innerHTML=`<div class="record-header"><div><p class="eyebrow">CASE ${esc(b.archive_year)}-${esc(b.case_number)} · SUBSPECIMEN ${esc(b.subspecimen)} · CASSETTE ${b.cassette_number}</p><h2>${esc(b.block_code)}</h2><p class="muted">${esc(b.description||'No description recorded')}</p></div><div class="record-tools"><button id="copyLink">Copy record link</button><a class="button" href="/api/v1/blocks/${b.id}/label.pdf" download>QR label ↓</a></div></div><div class="record-body"><div><div class="hero-frame">${photo?`<img src="${esc(photo.url)}" alt="${esc(photoLabels[photo.kind])} photo of ${esc(b.block_code)}">`:'<div class="hero-placeholder"><span aria-hidden="true">▦</span>No image recorded yet</div>'}</div><div class="photo-caption">${photo?`<span>${esc(photoLabels[photo.kind])} · ${esc(date(photo.created_at))}<br>${esc(photo.actor)} · cycle ${photo.cycle}</span><a href="${esc(photo.url)}" target="_blank" rel="noopener noreferrer">Open original ↗</a>`:'<span>Photographs stay linked to this block code.</span>'}</div><div class="photo-strip" aria-label="Photo history">${b.photos.map(p=>`<button class="${p.id===photo?.id?'selected':''}" data-photo-view="${p.id}" aria-label="View ${esc(photoLabels[p.kind])} from ${esc(date(p.created_at))}"><img src="${esc(p.thumbnail_url)}" alt="${esc(photoLabels[p.kind])}" loading="lazy"><small>Cycle ${p.cycle}</small></button>`).join('')}</div></div><div><div class="filing-position"><p>${b.status==='archived'?'Archived at':'Filing position'}</p><strong>${esc(b.location)}</strong><span class="badge ${b.status}">${labels[b.status]}</span><p class="small">Year → case → subspecimen → cassette</p></div><div class="workflow">${workflow(b)}</div></div></div><section class="section-divider"><div class="section-title"><h3>Blocks in this case</h3></div><div id="caseBlocks" class="external-links"></div></section><section class="section-divider"><div class="section-title"><h3>Linked data</h3><button id="addLink" data-mutate>+ Add reference</button></div><div class="external-links">${b.external_links.length?b.external_links.map(link=>link.url?`<a class="external-link" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer"><small>${esc(link.system)}</small>${esc(link.external_id)} ↗</a>`:`<span class="external-link"><small>${esc(link.system)}</small>${esc(link.external_id)}</span>`).join(''):'<p class="empty-note">Link a slide, dataset or other system record using this block code.</p>'}</div></section><section class="section-divider"><div class="section-title"><h3>Archive history</h3><span class="muted">${b.events.length} events</span></div><ol class="history">${b.events.map(event=>`<li><strong>${esc(eventLabels[event.type]||event.type)}</strong><p>${esc(event.actor)}${event.data.location?' · '+esc(event.data.location):''}${event.data.kind?' · '+esc(photoLabels[event.data.kind]):''}</p>${event.data.note?`<p>${esc(event.data.note)}</p>`:''}<time datetime="${esc(event.occurred_at)}">${esc(date(event.occurred_at))}</time></li>`).join('')}</ol></section><section class="section-divider"><details><summary>Edit cassette contents</summary><form class="description-form" id="descriptionForm"><label class="field-help" for="description">Cassette contents / description</label><textarea id="description" maxlength="2000">${esc(b.description)}</textarea><button data-mutate>Save description</button></form></details></section>`;
  loadCaseBlocks(b);
  $('#copyLink').onclick=async()=>{try{await navigator.clipboard.writeText(location.origin+'/archive?block='+encodeURIComponent(b.block_code));message('Block record link copied.');}catch{message('Use the address bar to copy this block’s link.',true);}};
  document.querySelectorAll('[data-photo-view]').forEach(button=>button.onclick=()=>{shownPhoto=button.dataset.photoView;renderRecord();});
  const movement=(action,extra={})=>change(async()=>api(`/api/v1/blocks/${b.id}/${action}`,{method:'POST',body:{actor:actor(),expected_version:b.version,note:$('#movementNote')?.value||'',...extra}}),action==='rearchive'?'Block rearchived with its new photograph.':'Block status updated.');
  if($('#checkout'))$('#checkout').onclick=()=>movement('checkout');
  if($('#completeCut'))$('#completeCut').onclick=()=>movement('complete-cut');
  if($('#rearchive'))$('#rearchive').onclick=()=>movement('rearchive',{photo_id:$('#rearchive').dataset.photo});
  if($('#archivePhoto'))$('#archivePhoto').onchange=event=>{
    const file=event.target.files[0];if(!file)return;
    if(file.size>20*1024*1024){message('Choose a photo no larger than 20 MB.',true);event.target.value='';return;}
    change(async()=>{const body=new FormData();body.append('file',file);body.append('kind',b.cycle?'post_cut':'baseline');body.append('actor',actor());body.append('expected_version',b.version);return api(`/api/v1/blocks/${b.id}/photos`,{method:'POST',body});},'New photograph recorded. Return the block and confirm its archive position.',true);
  };
  $('#addLink').onclick=()=>{$('#linkForm').reset();$('#linkForm .form-error').textContent='';$('#linkDialog').showModal();};
  $('#descriptionForm').onsubmit=event=>{event.preventDefault();change(()=>api(`/api/v1/blocks/${b.id}`,{method:'PATCH',body:{actor:actor(),expected_version:b.version,description:$('#description').value}}),'Description saved.');};
}
async function change(operation,success,showLatest=false){
  if(busy)return;busy=true;const blockId=selected?.id;
  document.querySelectorAll('[data-mutate]').forEach(button=>button.disabled=true);
  try{const updated=await operation();if(selected?.id===blockId){selected=updated;if(showLatest)shownPhoto=updated.photos[0]?.id;renderRecord();}await loadList();message(success);return updated;}
  catch(error){message(error.message,true);if(error.status===409&&selected?.id===blockId)await selectBlock(blockId,false);return null;}
  finally{busy=false;document.querySelectorAll('[data-mutate]').forEach(button=>{button.disabled=button.id==='rearchive'&&!button.dataset.photo;});}
}
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>document.getElementById(button.dataset.close).close());
$('#operator').onchange=()=>{try{sessionStorage.setItem('archiveOperator',$('#operator').value);}catch{}};
try{$('#operator').value=sessionStorage.getItem('archiveOperator')||'';}catch{}
$('#newBlock').onclick=()=>{$('#registerForm').reset();$('#registerForm [name="archive_year"]').value=new Date().getFullYear();$('#registerForm .form-error').textContent='';$('#registerDialog').showModal();$('#registerForm [name="block_code"]').focus();};
$('#registerForm').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const form=event.target, fields=Object.fromEntries(new FormData(form));
  try{const operator=actor();busy=true;form.querySelector('[data-mutate]').disabled=true;
    const record=await api('/api/v1/blocks',{method:'POST',body:{...fields,archive_year:Number(fields.archive_year),cassette_number:Number(fields.cassette_number),actor:operator}});
    form.closest('dialog').close();filter='';offset=0;$('#search').value='';$('#year').value='';document.querySelectorAll('[data-status]').forEach(button=>button.classList.toggle('active',!button.dataset.status));
    await selectBlock(record.id);await loadList();message('Block registered. Add its initial archive photograph.');
  }catch(error){form.querySelector('.form-error').textContent=error.message;}
  finally{busy=false;form.querySelector('[data-mutate]').disabled=false;}
};
$('#linkForm').onsubmit=async event=>{
  event.preventDefault();const form=event.target,fields=Object.fromEntries(new FormData(form));
  try{const result=await change(()=>api(`/api/v1/blocks/${selected.id}/external-links`,{method:'PUT',body:{...fields,url:fields.url||null,actor:actor(),expected_version:selected.version}}),'Data reference saved.');if(result)form.closest('dialog').close();else form.querySelector('.form-error').textContent=$('#message').textContent;}
  catch(error){form.querySelector('.form-error').textContent=error.message;}
};
async function loadCaseBlocks(block,offset=0){
  try{const data=await api('/api/v1/blocks?'+new URLSearchParams({year:block.archive_year,case_number:block.case_number,limit:100,offset}));
    if(selected?.id!==block.id||selected.version!==block.version||!$('#caseBlocks'))return;
    if(!offset)$('#caseBlocks').replaceChildren();
    $('#moreCaseBlocks')?.remove();
    $('#caseBlocks').insertAdjacentHTML('beforeend',data.items.map(b=>`<button class="external-link ${b.id===block.id?'current-case-block':''}" data-sibling="${b.id}" title="${esc(b.description)}"><small>${esc(b.description||b.block_code)}</small>${esc(b.subspecimen)}${b.cassette_number} · ${labels[b.status]}</button>`).join(''));
    if(data.next_offset!==null){const more=document.createElement('button');more.id='moreCaseBlocks';more.textContent='Show more blocks in this case';more.onclick=()=>loadCaseBlocks(block,data.next_offset);$('#caseBlocks').append(more);}
    document.querySelectorAll('[data-sibling]').forEach(button=>button.onclick=()=>selectBlock(button.dataset.sibling));
  }catch{if($('#caseBlocks'))$('#caseBlocks').textContent='Case records could not be loaded.';}
}
$('#registerForm [name="subspecimen"]').oninput=event=>{event.target.value=event.target.value.toUpperCase();};
$('#registerForm [name="block_code"]').onchange=event=>{
  const match=event.target.value.trim().match(/(?:^|[^0-9])([0-9]{4}|[0-9]{2})[-/ ]+([0-9]{1,12})[-/ ]+([A-Za-z]{1,4})([0-9]{1,4})$/);
  if(!match)return;
  const form=$('#registerForm'),year=Number(match[1]),current=new Date().getFullYear();
  form.elements.archive_year.value=match[1].length===4?year:(year===current%100?current:'');
  form.elements.case_number.value=match[2];form.elements.subspecimen.value=match[3].toUpperCase();form.elements.cassette_number.value=Number(match[4]);
};
let timer;$('#search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{offset=0;loadList();},180);};
$('#search').onkeydown=async event=>{if(event.key!=='Enter')return;clearTimeout(timer);event.preventDefault();offset=0;await loadList();try{const record=await api('/api/v1/blocks/by-code?block_code='+encodeURIComponent($('#search').value.trim()));await selectBlock(record.id);}catch(error){if(error.status!==404)message(error.message,true);}};
for(const id of ['year','sort'])$('#'+id).onchange=()=>{offset=0;loadList();};
document.querySelectorAll('[data-status]').forEach(button=>button.onclick=()=>{filter=button.dataset.status;offset=0;document.querySelectorAll('[data-status]').forEach(b=>b.classList.toggle('active',b===button));loadList();});
$('#refresh').onclick=async()=>{await loadList();if(selected)await selectBlock(selected.id,false);};
$('#previous').onclick=()=>{offset=Math.max(0,offset-30);loadList();};$('#next').onclick=()=>{if(nextOffset!==null){offset=nextOffset;loadList();}};
async function openLinkedBlock(){const code=new URLSearchParams(location.search).get('block');if(!code)return;try{const record=await api('/api/v1/blocks/by-code?block_code='+encodeURIComponent(code));await selectBlock(record.id,false);}catch(error){message(error.message,true);}}
window.addEventListener('popstate',openLinkedBlock);
loadList();openLinkedBlock();
