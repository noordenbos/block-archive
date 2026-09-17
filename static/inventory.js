'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const PAGE_SIZE = 36;
let items = new Map(), matches = [], selected = new Set(), page = 0, generation = 0;
let worker, filterTimer, inputTimer, filterReady = false, reviewEntries = [], busy = false, loadGeneration = 0;
try { $('#operator').value = sessionStorage.getItem('archiveOperator') || ''; } catch (_) {}
function message(text, error = false) { $('#message').hidden = false; $('#message').textContent = text; $('#message').classList.toggle('error', error); }
function actor() { const value = $('#operator').value.trim(); if (!value) { $('#operator').focus(); throw Error('Enter your operator name or initials first.'); } return value; }
async function api(path, options = {}) {
  const headers = {...options.headers};
  if (options.method) headers['X-Archive-Request'] = '1';
  if (options.body && !(options.body instanceof FormData)) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body); }
  const response = await fetch(path, {...options, headers, credentials:'same-origin'});
  const data = await response.json();
  if (!response.ok) throw Error(Array.isArray(data.detail) ? data.detail.map(d => d.msg).join('; ') : data.detail || 'Request failed.');
  return data;
}
function saveSelection() { try { sessionStorage.setItem('inventory-selection:'+window.activeProject.id, JSON.stringify([...selected])); } catch (_) {} }
function selectionUI() {
  const hidden = [...selected].filter(key => !matches.includes(key)).length;
  $('#selectionCount').textContent = selected.size ? `${selected.size} selected${hidden ? ` · ${hidden} outside this filter` : ''}` : 'No blocks selected';
  $('#selectionHelp').textContent = selected.size ? 'Selection is kept when you search or change pages.' : 'Use the checkboxes or select all matching results.';
  for (const id of ['plan','editLabels','clearSelection','unselectAll']) $('#'+id).disabled = !selected.size || busy;
  saveSelection();
}
function tissuePreview(item) {
  const photo=item.qc.status==='ready'&&item.photos.find(photo=>photo.id===item.qc.tissue_id);
  if(!photo&&item.qc.missing_side==='tissue')return '<div class="inventory-cover crop-placeholder"><span>Tissue photo unavailable · included as a block record.</span></div>';
  if(!photo)return '<div class="inventory-cover crop-placeholder"><span>Complete Import & QC to show the tissue block.</span></div>';
  const url=photo.thumbnail_url.replace(/thumbnail$/, 'block-preview');
  return `<a href="${esc(url)}" target="_blank" rel="noopener" class="inventory-tissue-view" aria-label="Open tissue block of ${esc(item.name)}"><img src="${esc(url)}" alt="Tissue block of ${esc(item.name)}" loading="lazy"><span class="crop-placeholder" hidden>Block crop unavailable · review in Import & QC</span></a>`;
}
function bindTissuePreviews(container=document) {
  container.querySelectorAll('.inventory-tissue-view img').forEach(img=>{
    const failed=()=>{img.hidden=true;const link=img.parentElement;link.querySelector('span').hidden=false;link.href='/#review';link.removeAttribute('target');link.setAttribute('aria-label','Review unavailable tissue crop');};
    img.onerror=failed;if(img.complete&&!img.naturalWidth)failed();
  });
}
function render() {
  const pages = Math.max(1, Math.ceil(matches.length / PAGE_SIZE)); page = Math.min(page, pages - 1);
  const visible = matches.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  $('#resultsCount').textContent = `${matches.length} matching record${matches.length === 1 ? '' : 's'} · ${items.size} in inventory`;
  $('#pageCount').textContent = `Page ${page + 1} of ${pages}`;
  $('#previous').disabled = !page || !filterReady; $('#next').disabled = page + 1 >= pages || !filterReady;
  $('#selectAll').disabled = !matches.length || !filterReady; $('#selectPage').disabled = !visible.length || !filterReady;
  $('#selectAll').textContent = `Select all ${matches.length} matches`;
  $('#inventoryGrid').innerHTML = visible.length ? visible.map(key => {
    const item = items.get(key), photo = item.photos[0];
    const href = item.block_id ? '/archive?block='+encodeURIComponent(item.name) : '/imports?photo='+encodeURIComponent(photo.id);
    return `<article class="inventory-card ${selected.has(key) ? 'chosen' : ''}"><label class="choose"><input type="checkbox" data-key="${esc(key)}" ${selected.has(key) ? 'checked' : ''} aria-label="Select ${esc(item.name)}"><strong>${esc(item.name)}</strong></label>${tissuePreview(item)}<div class="card-meta"><small>${item.photos.length} photo${item.photos.length === 1 ? '' : 's'} · ${item.kind === 'block' ? 'Registered block' : 'Photo group'}</small><p>${esc(item.location || item.description)}</p><p class="qc-status ${esc(item.qc.status)}">${item.qc.status==='ready'?'Ready for planning': 'Import QC needs attention'} · ${item.qc.method==='automatic'?(item.qc.tissue_id&&item.qc.identifier_id?'Sides detected automatically':'Side detection needs review'):'Sides assigned by operator'}</p><p class="inventory-metadata">${Object.entries(item.metadata||{}).slice(0,3).map(([key,value])=>esc(key)+': '+esc(value)).join(' · ')}</p><div class="inventory-tags">${item.labels.map(label => `<span class="inventory-tag">${esc(label)}</span>`).join('')}</div><a href="${esc(href)}">${item.kind === 'block' ? 'View block record' : 'Review photo identity'} ↗</a></div></article>`;
  }).join('') : `<div class="inventory-empty"><h2>${items.size ? 'No records match these filters.' : 'Your inventory starts with photographs.'}</h2><p>${items.size ? 'Change the search or clear filters. Your selection is kept.' : 'Import a photo folder above, or register a block in Block checkout & return.'}</p></div>`;
  document.querySelectorAll('[data-key]').forEach(input => input.onchange = () => {
    input.checked ? selected.add(input.dataset.key) : selected.delete(input.dataset.key);
    if ($('#selectedOnly').checked) filter(); else render();
  });
  bindTissuePreviews();
  selectionUI();
}
function startWorker() {
  worker?.terminate(); worker = new Worker('/static/inventory-filter.js');
  worker.postMessage({records:[...items.values()].map(item => ({key:item.key, kind:item.kind, labels:item.labels, metadata:item.metadata||{},
    fields:[item.name, item.description, item.location, ...item.labels, ...Object.entries(item.metadata||{}).flat(), ...item.references.flatMap(r=>[r.system,r.external_id]), ...item.evidence.split('\n')]}))});
  worker.onmessage = ({data}) => {
    if (data.generation !== generation) return;
    clearTimeout(filterTimer); filterReady = !data.error;
    $('#filterError').textContent = data.error || ''; matches = data.keys || []; render();
  };
  worker.onerror = () => { clearTimeout(filterTimer); filterReady = false; matches = []; $('#filterError').textContent = 'Search could not run. Refresh the inventory.'; render(); };
}
function filter() {
  clearTimeout(filterTimer); ++generation; page = 0; filterReady = false;
  $('#selectAll').disabled = true; $('#selectPage').disabled = true;
  $('#filterError').textContent = ''; $('#resultsCount').textContent = 'Filtering…';
  worker.postMessage({generation, mode:$('#searchMode').value, query:$('#search').value.trim(), label:$('#labelFilter').value,
    kind:$('#kindFilter').value, metadataField:$('#metadataField').value, metadataValue:$('#metadataValue').value, selected:$('#selectedOnly').checked ? [...selected] : null});
  const current = generation;
  filterTimer = setTimeout(() => {
    if (current !== generation) return;
    startWorker(); filterReady = false; matches = [];
    $('#filterError').textContent = 'This search took too long. Use a simpler expression or text search.'; render();
  }, 750);
}
async function load() {
  const request = ++loadGeneration;
  try {
    const data = await api('/api/v1/inventory'); if (request !== loadGeneration) return;
    items = new Map(data.items.map(item => [item.key,item]));
    const oldSize = selected.size; selected = new Set([...selected].filter(key => items.has(key)));
    if (selected.size < oldSize) message('Some photo groups were linked or changed and have been removed from your selection. Review the inventory.');
    const label = $('#labelFilter').value, labels = [...new Set(data.items.flatMap(item => item.labels))].sort();
    $('#labelFilter').innerHTML = '<option value="">All labels</option>'+labels.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');
    $('#labelFilter').value = labels.includes(label) ? label : '';
    document.dispatchEvent(new Event('inventory-loaded'));startWorker(); filter();
  } catch (error) { filterReady = false; $('#selectAll').disabled = true; $('#selectPage').disabled = true; message(error.message,true); }
}
function review() {
  try { actor(); } catch (error) { return message(error.message,true); }
  if (selected.size > 1000) return message('Plan up to 1000 blocks at a time. Narrow the selection first.',true);
  reviewEntries = [...selected].map(key => items.get(key));
  const problems=reviewEntries.filter(item=>item.qc.status!=='ready');
  if(problems.length){showPanel('review');return message(`${problems.length} selected groups need import QC. Correct their grouping or sides, or acknowledge a known limitation, then return to your selection.`,true);}
  $('#reviewError').textContent = ''; $('#experimentName').value = '';
  $('#reviewItems').innerHTML='<p class="ready-review">'+reviewEntries.length+' groups ready. Saved side assignments and metadata will be used.</p>'+reviewEntries.map(item=>`<details class="review-item"><summary>${esc(item.name)}</summary>${tissuePreview(item)}</details>`).join('');
  bindTissuePreviews($('#reviewItems'));
  $('#reviewDialog').showModal(); $('#experimentName').focus();
}
$('#reviewForm').onsubmit = async event => {
  event.preventDefault(); if (busy) return;
  try {
    busy = true; $('#createPlan').disabled = true;
    const entries = reviewEntries.map(item=>({key:item.key,revision:item.revision,name:item.name,
      tissue_id:item.qc.tissue_id,identifier_id:item.qc.identifier_id,confirmed:false}));
    const result = await api('/api/v1/planning-selections', {method:'POST',body:{name:$('#experimentName').value.trim(), actor:actor(), entries}});
    location.assign(result.url);
  } catch (error) { $('#reviewError').textContent = error.message; }
  finally { busy = false; $('#createPlan').disabled = false; }
};
$('#labelsForm').onsubmit = async event => {
  event.preventDefault(); if (busy) return;
  try {
    busy = true; $('#saveLabels').disabled = true;
    const labels = $('#labelsInput').value.split(',').map(s=>s.trim()).filter(Boolean);
    await api('/api/v1/inventory/labels',{method:'POST',body:{actor:actor(),labels,action:$('#labelAction').value,
      entries:[...selected].map(key=>({key,revision:items.get(key).revision}))}});
    $('#labelsDialog').close(); await load(); message('Labels saved to the inventory.');
  } catch (error) { $('#labelsError').textContent = error.message; }
  finally { busy = false; $('#saveLabels').disabled = false; selectionUI(); }
};
$('#editLabels').onclick = () => { try { actor(); $('#labelsError').textContent = ''; $('#labelsInput').value = ''; $('#labelsDialog').showModal(); } catch (error) { message(error.message,true); } };
$('#operator').onchange = () => { try { sessionStorage.setItem('archiveOperator',$('#operator').value); } catch (_) {} };
$('#search').oninput = () => { clearTimeout(inputTimer); clearTimeout(filterTimer); ++generation; filterReady=false; $('#selectAll').disabled=true; $('#selectPage').disabled=true; inputTimer=setTimeout(filter,180); };
for (const id of ['searchMode','labelFilter','kindFilter','selectedOnly']) $('#'+id).onchange = filter;
$('#selectAll').onclick = () => { if (!filterReady) return; matches.forEach(key=>selected.add(key)); render(); };
$('#selectPage').onclick = () => { if (!filterReady) return; matches.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE).forEach(key=>selected.add(key)); render(); };
$('#unselectAll').onclick = $('#clearSelection').onclick = () => { selected.clear(); $('#selectedOnly').checked ? filter() : render(); };
$('#clearFilters').onclick = () => { $('#search').value=''; $('#searchMode').value='text'; $('#labelFilter').value=''; $('#kindFilter').value=''; $('#selectedOnly').checked=false; $('#metadataField').value=''; updateMetadataValues(); filter(); };
$('#previous').onclick = () => { --page; render(); }; $('#next').onclick = () => { ++page; render(); };
$('#refresh').onclick = load; $('#plan').onclick = review;
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>document.getElementById(button.dataset.close).close());
$('#importFolder').onchange = async event => {
  if(busy)return;
  const files = [...event.target.files].filter(file=>/\.(jpe?g|png|webp)$/i.test(file.name));
  try {
    const operator = actor(); if (!files.length) throw Error('Choose a folder containing JPEG, PNG or WebP photographs.');
    busy=true; event.target.disabled=true; $('#captureImport').disabled=true; selectionUI(); let added=0, skipped=0, failed=0;
    for (const [index,file] of files.entries()) {
      message(`Importing photo ${index+1} of ${files.length}…`);
      const body = new FormData(); body.append('file',file); body.append('actor',operator);
      try { const result=await api('/api/v1/inventory/photos',{method:'POST',body}); result.created ? ++added : ++skipped; }
      catch (_) { ++failed; }
    }
    await load(); showPanel('review'); message(`Import complete: ${added} added, ${skipped} already present, ${failed} failed.${failed ? ' Failed files can be retried; use single-frame images up to 20 MB and 40 megapixels.' : ''}`, failed>0);
  } catch (error) { message(error.message,true); }
  finally { busy=false; event.target.value=''; event.target.disabled=false; $('#captureImport').disabled=false; selectionUI(); renderQC(); }
};
window.workspaceReady.then(()=>{try{selected=new Set(JSON.parse(sessionStorage.getItem("inventory-selection:"+window.activeProject.id)||"[]"))}catch(_){};load()}).catch(error=>message(error.message,true));
// Preserve old record bookmarks while making the inventory the new home page.
const legacyCode = new URLSearchParams(location.search).get('block');
if (legacyCode) location.replace('/archive?block='+encodeURIComponent(legacyCode));
