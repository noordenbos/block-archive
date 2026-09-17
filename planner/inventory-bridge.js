'use strict';
// Selections are immutable server snapshots. Scoring remains in the planner's
// existing browser experiment store and portable experiment backups.
let inventoryImportBusy = false;
async function selectionRequest(path) {
  const response = await fetch(path, {credentials:'same-origin'});
  if (!response.ok) throw Error('The inventory selection or a source photo is unavailable. Return to the inventory to review it.');
  return response;
}
async function inventoryBlock(item) {
  const block = {id:uid(), name:item.name, donor:'', photo:null, identifier:null, mmPerPx:null, calibration:null,
    orientation:'Review orientation before scoring.', notes:item.description, scores:[], regions:[], labels:item.labels, metadata:item.metadata||{},
    inventory:{key:item.key, blockId:item.block_id, sourceName:item.source_name, revision:item.revision, tissueId:item.tissue_id,
      identifierId:item.identifier_id, identityReviewed:item.identity_reviewed}, sources:[]};
  block.inventory.missingSide=item.missing_side||item.qc?.missing_side||'';
  block.inventory.storageVersion=2;
  block.sources=item.photos.map(record=>({photoId:record.id,hash:record.sha256,role:record.id===item.tissue_id?'tissue':'identifier'}));
  const tissue=item.photos.find(record=>record.id===item.tissue_id);
  if(tissue){
    const url=tissue.url.replace(/image$/, 'experiment-image');
    const image=await (await selectionRequest(url)).json();
    block.photo=image.image;block.mmPerPx=image.mmPerPx;block.inventory.imageFraming=image.framing;
    if(image.mmPerPx){
      block.calibration={points:[[0,0],[image.width,0]],length:image.width*image.mmPerPx,provisional:false,method:'Automatic marker registration'};
      block.analysis={markerIds:tissue.analysis?.markerIds||[],registration:tissue.analysis?.registration};
      block.orientation='TOP / LABEL END is up. Registered from corner markers; no reflection applied.';
    }else block.notes+='\nMat crop unavailable: this is a reduced tissue preview. Calibrate manually before scoring.';
  }else block.notes+='\nTissue-side photograph unavailable. Included as a block record; add a tissue photo before scoring.';
  return block;
}
document.addEventListener('planner-ready', async () => {
  const selectionId = new URLSearchParams(location.search).get('selection');
  if (!selectionId || inventoryImportBusy) return;
  const panel=document.createElement('dialog');
  panel.innerHTML='<h2>Opening inventory selection</h2><p class="inventory-progress" role="status">Loading selected blocks…</p><div class="toolbar"><button class="inventory-retry" hidden>Retry</button><a class="button" href="/">Return to inventory</a></div>';
  document.body.append(panel);panel.showModal();panel.addEventListener('cancel',event=>event.preventDefault());
  const progress=panel.querySelector('.inventory-progress');
  async function open() {
    inventoryImportBusy=true;panel.querySelector('button').hidden=true;
    try {
      // Reloading the handoff URL reopens its saved experiment; never resets its scoring.
      await saving;
      const prior = await new Promise((resolve,reject)=>{
        const request=db.transaction('projects').objectStore('projects').openCursor();
        request.onerror=()=>reject(request.error);request.onsuccess=()=>{
          const cursor=request.result;if(!cursor)return resolve(null);
          if(cursor.value.inventorySelectionId===selectionId)return resolve(cursor.value);
          cursor.continue();
        };
      });
      if (state.inventorySelectionId===selectionId) { /* already current */ }
      else if (prior) await switchExperiment(validateProject(prior));
      else {
        const selection=await (await selectionRequest('/api/v1/planning-selections/'+encodeURIComponent(selectionId))).json();
        const next=emptyExperiment(selection.name);next.inventorySelectionId=selection.id;
        next.inventorySelectedAt=selection.created_at;next.inventoryActor=selection.actor;
        for (const [index,item] of selection.items.entries()) {
          progress.textContent=`Preparing block ${index+1} of ${selection.items.length}: ${item.name}`;
          next.blocks.push(await inventoryBlock(item));
        }
        if (JSON.stringify(next).length > 180*1024*1024) throw Error('This experiment is too large for portable backups. Select fewer blocks.');
        validateProject(next);await switchExperiment(next);await saving;await archiveExperiment();
      }
      history.replaceState({},'', '/planner/');panel.close();panel.remove();
      notify('Inventory selection opened. Review calibration and assay settings before scoring.');
    } catch(error) { progress.textContent='Could not open selection: '+error.message;panel.querySelector('button').hidden=false; }
    finally { inventoryImportBusy=false; }
  }
  panel.querySelector('button').onclick=open;await open();
});
const inventoryRender = render;
render = function() {
  inventoryRender();
  const block=currentBlock();
  if(tab==='blocks' && block?.inventory) {
    const note=document.createElement('div');note.className='notice';
    const link=document.createElement('a');link.href=block.inventory.blockId?'/archive?block='+encodeURIComponent(block.inventory.sourceName || block.name):'/';
    link.textContent='View source in block inventory';note.append(link);
    const text=document.createElement('p');text.textContent=block.labels?.length?'Inventory labels: '+block.labels.join(', '):'Created from the block inventory.';note.append(text);
    if(!block.photo){const warning=document.createElement('p');warning.textContent='No tissue-side photograph: this block is included as a record. Add a tissue photo before scoring or placing tissue.';note.append(warning);}
    else if(!block.mmPerPx){const warning=document.createElement('p');warning.textContent='This photo is not calibrated. Set a known reference length before drawing retained pieces.';note.append(warning);}
    $('#content').prepend(note);
  }
};
