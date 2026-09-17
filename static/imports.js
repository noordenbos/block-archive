'use strict';
const $=selector=>document.querySelector(selector);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let offset=0,nextOffset=null,selected=null,listGeneration=0,detailGeneration=0,busy=false;
function message(text,error=false){const box=$('#message');box.hidden=false;box.textContent=text;box.classList.toggle('error',error);}
async function api(path,options={}){
  const headers={};if(options.body){headers['Content-Type']='application/json';headers['X-Archive-Request']='1';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers,credentials:'same-origin'});
  const data=await response.json();if(!response.ok){const error=Error(Array.isArray(data.detail)?data.detail.map(d=>d.msg).join('; '):data.detail||'Request failed.');error.status=response.status;throw error;}return data;
}
function operator(){const value=$('#operator').value.trim();if(!value){$('#operator').focus();throw Error('Enter your name or initials before confirming a link.');}return value;}
try{$('#operator').value=sessionStorage.getItem('archiveOperator')||'';}catch{}
$('#operator').onchange=()=>{try{sessionStorage.setItem('archiveOperator',$('#operator').value);}catch{}};
async function load(){const generation=++listGeneration;try{
  const result=await api('/api/v1/imports?'+new URLSearchParams({query:$('#search').value,status:$('#status').value,offset,limit:30}));
  if(generation!==listGeneration)return;
  $('#pendingCount').textContent=result.pending;$('#resultsCount').textContent=`${result.total} photos${result.total?' · '+(offset+1)+'–'+Math.min(offset+30,result.total):''}`;
  $('#photoList').innerHTML=result.items.length?result.items.map(item=>`<button class="block-card ${selected?.id===item.id?'selected':''}" data-import="${esc(item.id)}"><img class="thumb" src="${esc(item.thumbnail_url)}" alt="Imported block photograph" loading="lazy"><div><strong>${esc(item.barcodes.join(' · ')||item.filename)}</strong><small>${esc(item.filename)}</small><span class="badge">${item.block_id?'Linked':'Identity unconfirmed'}</span></div></button>`).join(''):'<p class="empty-note">No photos match this view.</p>';
  document.querySelectorAll('[data-import]').forEach(button=>button.onclick=()=>select(button.dataset.import));
  nextOffset=result.next_offset;$('#previous').disabled=!offset;$('#next').disabled=nextOffset===null;
}catch(error){message(error.message,true);}}
async function select(id){if(busy)return;const generation=++detailGeneration;try{const item=await api('/api/v1/imports/'+id);if(generation!==detailGeneration)return;selected=item;render();document.querySelectorAll('[data-import]').forEach(b=>b.classList.toggle('selected',b.dataset.import===id));history.replaceState({},'', '/imports?photo='+encodeURIComponent(id));}catch(error){message(error.message,true);}}
function render(){const item=selected;
  $('#record').innerHTML=`<div class="record-header"><div><p class="eyebrow">${item.block_id?'LINKED REFERENCE':'IDENTITY UNCONFIRMED'}</p><h2>${esc(item.barcodes.join(' · ')||'Review photo')}</h2><p class="muted">${esc(item.filename)}</p></div><a class="button" href="${esc(item.url)}" target="_blank" rel="noopener">Open full resolution ↗</a></div><div class="record-body"><div><div class="hero-frame"><img src="${esc(item.thumbnail_url)}" alt="Imported photograph for label review"></div><p class="photo-caption">Original preserved · imported ${esc(new Date(item.imported_at).toLocaleDateString())}</p><details open><summary>Label reading · unverified</summary><pre class="label-reading">${esc(item.label_text||'No readable text found. Inspect the original photo.')}</pre></details></div><div>${item.block_id?'<div class="workflow"><h3>Linked to a block</h3><p>This photo is retained as a historical reference.</p><button id="openBlock">Open block record</button></div>':`<form id="confirmForm"><h3>Confirm block identity</h3><p class="muted">Include the subspecimen and cassette suffix. A case barcode alone may not identify the individual block.</p><label>Full block code<input name="block_code" required maxlength="120" autocomplete="off" value="${esc(item.barcodes.length===1?item.barcodes[0]:'')}"></label><button type="button" id="lookup">Find existing block</button><p id="match" class="field-help"></p><details id="newFields"><summary>Register a new block</summary><p class="field-help">Required when the full code has no record yet.</p><div class="form-row"><label>Year<input name="archive_year" type="number" min="1900" max="2199"></label><label>Case number<input name="case_number" pattern="[0-9]{1,12}" maxlength="12"></label></div><div class="form-row"><label>Subspecimen<input name="subspecimen" pattern="[A-Z]{1,4}" maxlength="4"></label><label>Cassette<input name="cassette_number" type="number" min="1" max="9999"></label></div><label>Cassette contents<input name="description" maxlength="2000"></label></details><label class="confirm-check"><input id="verified" type="checkbox" required> I checked the full code and cassette against this photograph.</label><button class="primary" id="confirm">Confirm and link photo</button><p class="form-error" role="alert"></p></form>`}</div></div>`;
  if(item.block_id){$('#openBlock').onclick=async()=>{try{const block=await api('/api/v1/blocks/'+item.block_id);location.href='/archive?block='+encodeURIComponent(block.block_code);}catch(error){message(error.message,true);}};return;}
  const form=$('#confirmForm');let matched=null;
  const lookup=async()=>{matched=null;const code=form.elements.block_code.value.trim();if(!code)throw Error('Enter the full block code.');try{matched=await api('/api/v1/blocks/by-code?'+new URLSearchParams({block_code:code}));$('#match').textContent='Found: '+matched.location;$('#newFields').open=false;}catch(error){if(error.status!==404)throw error;$('#match').textContent='No existing record. Enter the case and cassette fields below.';$('#newFields').open=true;}return matched;};
  $('#lookup').onclick=()=>lookup().catch(error=>message(error.message,true));
  form.elements.block_code.oninput=()=>{matched=null;$('#match').textContent='';$('#verified').checked=false;};
  form.elements.subspecimen.oninput=event=>{event.target.value=event.target.value.toUpperCase();};
  form.onsubmit=async event=>{event.preventDefault();if(busy)return;busy=true;$('#confirm').disabled=true;try{
    const actor=operator(),fields=Object.fromEntries(new FormData(form));
    let block=await lookup();
    if(!block){if(!fields.archive_year||!fields.case_number||!fields.subspecimen||!fields.cassette_number)throw Error('Enter the archive year, case, subspecimen and cassette to register this block.');
      block=await api('/api/v1/blocks',{method:'POST',body:{...fields,archive_year:Number(fields.archive_year),cassette_number:Number(fields.cassette_number),actor}});}
    await api('/api/v1/imports/'+item.id+'/confirm',{method:'POST',body:{block_id:block.id,expected_version:item.version,expected_block_version:block.version,actor}});
    selected=await api('/api/v1/imports/'+item.id);render();offset=0;await load();message('Historical photo linked. No cutting or archive return was recorded.');
  }catch(error){if($('#confirmForm .form-error'))$('#confirmForm .form-error').textContent=error.message;else message(error.message,true);}
  finally{busy=false;if($('#confirm'))$('#confirm').disabled=false;}};
}
let timer;$('#search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{offset=0;load();},180);};
$('#status').onchange=()=>{offset=0;load();};$('#refresh').onclick=()=>load();
$('#previous').onclick=()=>{offset=Math.max(0,offset-30);load();};$('#next').onclick=()=>{if(nextOffset!==null){offset=nextOffset;load();}};
load();const imageId=new URLSearchParams(location.search).get('photo');if(imageId)select(imageId);
