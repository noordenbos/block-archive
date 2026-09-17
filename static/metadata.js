'use strict';
let metadataRecords = new Map(), metadataPreview = null, previewText = '', metadataEditing = null;
let metadataLoadGeneration = 0, metadataPreviewGeneration = 0;
const metadataKey = value => value.trim().toLocaleLowerCase();
function updateMetadataFilters(){
  const field=$('#metadataField').value;
  const names=[...new Set([...items.values()].flatMap(item=>Object.keys(item.metadata||{})))].sort();
  $('#metadataField').innerHTML='<option value="">Any field</option>'+names.map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');
  $('#metadataField').value=names.includes(field)?field:'';updateMetadataValues();
}
function updateMetadataValues(){
  const field=$('#metadataField').value,value=$('#metadataValue').value;
  const values=[...new Set([...items.values()].map(item=>item.metadata?.[field]).filter(Boolean))].sort();
  $('#metadataValue').innerHTML='<option value="">Any value</option>'+values.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');
  $('#metadataValue').value=values.includes(value)?value:'';$('#metadataValue').disabled=!field;
}
$('#metadataField').onchange=()=>{updateMetadataValues();filter();};$('#metadataValue').onchange=filter;
async function loadMetadata(){
  const generation=++metadataLoadGeneration;
  const data=await api('/api/v1/metadata');if(generation!==metadataLoadGeneration)return;
  metadataRecords=new Map(data.records.map(record=>[metadataKey(record.matching_id),record]));renderMetadata();
}
function renderMetadata(){
  const merged=new Map(metadataRecords);
  for(const item of items.values())if(!merged.has(metadataKey(item.name)))merged.set(metadataKey(item.name),{matching_id:item.name,fields:{},version:0});
  const query=$('#metadataSearch').value.trim().toLocaleLowerCase();
  const records=[...merged.values()].filter(record=>[record.matching_id,...Object.entries(record.fields).flat()].join('\n').toLocaleLowerCase().includes(query)).sort((a,b)=>a.matching_id.localeCompare(b.matching_id));
  const headers=[...new Set(records.flatMap(record=>Object.keys(record.fields)))].sort();
  $('#metadataCount').textContent=`${records.length} matching IDs · ${metadataRecords.size} saved metadata records. IDs without photos are kept for future imports.`;
  $('#metadataTable').innerHTML=records.length?`<table><thead><tr><th>Matching ID</th><th>Photos</th>${headers.map(header=>`<th>${esc(header)}</th>`).join('')}<th></th></tr></thead><tbody>${records.slice(0,250).map(record=>`<tr><th>${esc(record.matching_id)}</th><td>${[...items.values()].some(item=>metadataKey(item.name)===metadataKey(record.matching_id))?'In inventory':'Awaiting photos'}</td>${headers.map(header=>`<td>${esc(record.fields[header]||'')}</td>`).join('')}<td><button data-edit-metadata="${esc(record.matching_id)}">Edit values</button></td></tr>`).join('')}</tbody></table>${records.length>250?'<p>Showing the first 250 matches. Narrow the search to find more records.</p>':''}`:'<div class="inventory-empty"><h2>Add information in the way that suits you.</h2><p>Create a record, paste rows from a spreadsheet, or drop a CSV above.</p></div>';
  document.querySelectorAll('[data-edit-metadata]').forEach(button=>button.onclick=()=>openMetadataEditor(merged.get(metadataKey(button.dataset.editMetadata))));
}
function addMetadataField(name='',value=''){
  const row=document.createElement('div');row.className='metadata-field-row';
  row.innerHTML=`<label>Column name<input class="metadata-field-name" maxlength="80" value="${esc(name)}" required></label><label>Value<textarea class="metadata-field-value" maxlength="2000" rows="2">${esc(value)}</textarea></label><button type="button" aria-label="Remove metadata column">Remove</button>`;
  row.querySelector('button').onclick=()=>row.remove();$('#metadataFields').append(row);
}
function openMetadataEditor(record=null){
  metadataEditing=record;$('#metadataId').value=record?.matching_id||'';$('#metadataId').readOnly=!!record;
  $('#metadataFields').replaceChildren();$('#metadataEditError').textContent='';
  const entries=Object.entries(record?.fields||{});if(entries.length)for(const pair of entries)addMetadataField(...pair);else addMetadataField();
  $('#metadataEditor').showModal();
}
$('#newMetadata').onclick=()=>openMetadataEditor();$('#addMetadataField').onclick=()=>addMetadataField();
$('#metadataSearch').oninput=renderMetadata;
$('#metadataEditorForm').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  try{const operator=actor(),fields=Object.create(null),seen=new Set();
    for(const row of document.querySelectorAll('.metadata-field-row')){const name=row.querySelector('input').value.trim();if(seen.has(name.toLocaleLowerCase()))throw Error('Column names must be unique.');seen.add(name.toLocaleLowerCase());fields[name]=row.querySelector('textarea').value;}
    busy=true;$('#saveMetadataRecord').disabled=true;
    await api('/api/v1/metadata',{method:'POST',body:{actor:operator,mode:'replace',entries:[{matching_id:$('#metadataId').value.trim(),fields,expected_version:metadataEditing?.version||0}]}});
    $('#metadataEditor').close();await load();await loadMetadata();message('Metadata saved and available for inventory search and filters.');
  }catch(error){$('#metadataEditError').textContent=error.message;}finally{busy=false;$('#saveMetadataRecord').disabled=false;selectionUI();}
};
async function previewMetadata(column=null){
  const generation=++metadataPreviewGeneration;
  $('#metadataError').textContent='';$('#applyMetadata').disabled=true;metadataPreview=null;
  try{
    if(!column){
      const schema=await api('/api/v1/metadata/columns',{method:'POST',body:{text:previewText}});
      if(generation!==metadataPreviewGeneration)return;
      $('#metadataPreview').hidden=false;$('#matchingColumn').innerHTML=schema.headers.map(header=>`<option value="${esc(header)}">${esc(header)}</option>`).join('');
      $('#matchingColumn').value=schema.id_column;column=schema.id_column;
      $('#metadataPreviewTable').replaceChildren();$('#metadataPreviewSummary').textContent='Choose the matching ID column. Previewing…';
    }
    const result=await api('/api/v1/metadata/preview',{method:'POST',body:{text:previewText,id_column:column}});
    if(generation!==metadataPreviewGeneration)return;metadataPreview=result;
    $('#metadataPreview').hidden=false;$('#matchingColumn').innerHTML=result.headers.map(header=>`<option value="${esc(header)}">${esc(header)}</option>`).join('');$('#matchingColumn').value=result.id_column;
    $('#metadataPreviewSummary').textContent=`${result.rows.length} rows · ${result.matched} IDs match the inventory · ${result.unmatched} await photos · ${result.conflicts} existing values differ. Nothing has been changed yet.`;
    const fields=result.headers.filter(header=>header!==result.id_column);
    $('#metadataPreviewTable').innerHTML=`<table><thead><tr><th>Matching ID</th><th>Match</th>${fields.map(field=>`<th>${esc(field)}</th>`).join('')}</tr></thead><tbody>${result.rows.slice(0,30).map(row=>`<tr><th>${esc(row.matching_id)}</th><td>${row.matched?'In inventory':'Awaiting photos'}</td>${fields.map(field=>`<td>${esc(row.fields[field])}</td>`).join('')}</tr>`).join('')}</tbody></table>${result.rows.length>30?'<p>Previewing 30 rows; saving will include every row.</p>':''}`;
    $('#applyMetadata').disabled=false;
  }catch(error){if(generation===metadataPreviewGeneration){$('#metadataError').textContent=error.message;$('#metadataPreviewSummary').textContent='Correct the table or choose a different matching ID column, then preview again.';}}
}
$('#previewMetadata').onclick=()=>{previewText=$('#metadataPaste').value;previewMetadata();};
$('#matchingColumn').onchange=()=>previewMetadata($('#matchingColumn').value);
$('#cancelMetadataPreview').onclick=()=>{metadataPreview=null;++metadataPreviewGeneration;$('#metadataPreview').hidden=true;};
$('#applyMetadata').onclick=async()=>{
  if(busy||!metadataPreview)return;
  try{const operator=actor();busy=true;$('#applyMetadata').disabled=true;
    const entries=metadataPreview.rows.map(row=>({matching_id:row.matching_id,fields:row.fields,expected_version:row.expected_version}));
    await api('/api/v1/metadata',{method:'POST',body:{actor:operator,mode:$('#metadataMode').value,entries}});
    metadataPreview=null;$('#metadataPreview').hidden=true;await load();await loadMetadata();message(`Saved metadata for ${entries.length} matching IDs.`);
  }catch(error){$('#metadataError').textContent=error.message;}finally{busy=false;$('#applyMetadata').disabled=!metadataPreview;selectionUI();}
};
async function readMetadataFile(file){
  try{if(!file)return;if(file.size>2*1024*1024)throw Error('Choose a CSV or TSV file up to 2 MB.');previewText=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());$('#metadataPaste').value=previewText;await previewMetadata();}
  catch(error){$('#metadataError').textContent=error.message;}
}
$('#metadataFile').onchange=async event=>{await readMetadataFile(event.target.files[0]);event.target.value='';};
$('#metadataDrop').ondragover=event=>{event.preventDefault();$('#metadataDrop').classList.add('drag-over');};
$('#metadataDrop').ondragleave=()=>$('#metadataDrop').classList.remove('drag-over');
$('#metadataDrop').ondrop=event=>{event.preventDefault();$('#metadataDrop').classList.remove('drag-over');readMetadataFile(event.dataTransfer.files[0]);};
updateMetadataFilters();
