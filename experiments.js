'use strict';
function emptyExperiment(name='Untitled experiment'){
  return {version:1,experimentId:uid(),name,config:{assay:'Xenium',product:'Select exact slide product',width:10,height:22,margin:.5,gap:.5,source:'',revision:'',verified:false},blocks:[],slides:[{id:uid(),name:'SLIDE-001',placements:[]}],updated:new Date().toISOString()};
}
// Bootstrap waits for DOMContentLoaded, after all workflow scripts are installed.
seed=()=>emptyExperiment();
async function archiveExperiment(){
  if(!state||!db)return;
  if(!state.experimentId)state.experimentId=uid();
  await saving;
  await new Promise((resolve,reject)=>{const tx=db.transaction('projects','readwrite');tx.objectStore('projects').put(structuredClone(state),'experiment:'+state.experimentId);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error)});
}
async function switchExperiment(next){
  await archiveExperiment();state=next;state.experimentId||=uid();blockId=state.blocks[0]?.id;slideId=state.slides[0].id;selected=null;draft=[];imageCache={};photoZoom=1;tab='blocks';save();render();
}
function newExperimentDialog(){
  const dialog=document.createElement('dialog');dialog.innerHTML='<h2>New experiment</h2><p>Your current experiment will be kept on this browser so you can reopen it.</p><label class="field">Experiment name<input maxlength="160" value="Untitled experiment"></label><p>Starts with an empty block list and one recipient slide. Review assay dimensions before planning.</p><div class="toolbar"><button class="primary create">Create experiment</button><button class="cancel">Cancel</button></div>';
  dialog.querySelector('.create').onclick=async e=>{const name=dialog.querySelector('input').value.trim();if(!name)return; e.target.disabled=true;try{await switchExperiment(emptyExperiment(name));dialog.close();notify('New empty experiment created.')}catch(err){notify('Could not create experiment: '+err.message);e.target.disabled=false}};
  dialog.querySelector('.cancel').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();dialog.querySelector('input').select();
}
async function openExperimentDialog(){
  const dialog=document.createElement('dialog');dialog.innerHTML='<h2>Open experiment</h2><p>Saved on this browser. Download experiment files for a portable backup.</p><div class="saved-experiments"></div><div class="toolbar"><label class="button">Open experiment file<input type="file" accept=".json,application/json" hidden></label><button class="cancel">Cancel</button></div>';
  try{
    await archiveExperiment();
    const entries=await new Promise((resolve,reject)=>{const request=db.transaction('projects').objectStore('projects').openCursor(),list=[];request.onsuccess=()=>{const c=request.result;if(!c)return resolve(list);if(String(c.key).startsWith('experiment:'))list.push(c.value);c.continue()};request.onerror=()=>reject(request.error)});
    for(const entry of entries.sort((a,b)=>String(b.updated).localeCompare(String(a.updated)))){const button=document.createElement('button');button.className='block-item';button.textContent=`${entry.name} · ${entry.blocks.length} blocks${entry.experimentId===state.experimentId?' · current':''}`;button.onclick=async()=>{try{await switchExperiment(validateProject(entry));dialog.close()}catch(e){notify(e.message)}};dialog.querySelector('.saved-experiments').append(button)}
    dialog.querySelector('input').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>200*1024*1024)throw Error('Experiment file exceeds 200 MB.');const incoming=validateProject(JSON.parse(await f.text()));incoming.experimentId=uid();await switchExperiment(incoming);dialog.close();notify('Experiment file opened.')}catch(err){notify('Could not open experiment: '+err.message)}};
    dialog.querySelector('.cancel').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();
  }catch(err){notify('Could not list saved experiments: '+err.message)}
}
backup=async function(){try{await archiveExperiment();const name=state.name.replace(/[^a-z0-9_-]+/gi,'-').replace(/^-|-$/g,'')||'experiment';download(name+'.json',JSON.stringify(state,null,2),'application/json');notify('Experiment saved on this browser and downloaded with its source photos.')}catch(err){notify('Save failed: '+err.message)}};
const header=document.querySelector('.header-actions'),newButton=document.createElement('button');newButton.textContent='New experiment';newButton.onclick=newExperimentDialog;header.prepend(newButton);
$('#backupBtn').textContent='Save experiment';$('#backupBtn').onclick=backup;
const openButton=document.createElement('button');openButton.textContent='Open experiment';openButton.onclick=openExperimentDialog;$('#openProject').parentElement.replaceWith(openButton);
$('#resetBtn').textContent='New empty experiment';$('#resetBtn').onclick=newExperimentDialog;
const renderExperiment=render;
render=function(){renderExperiment();const heading=document.querySelector('aside h2');if(state)heading.textContent=state.name;
  if(tab==='blocks'&&$('#addBlock'))$('#addBlock').onclick=()=>{const b={id:uid(),name:`BLOCK-${String(state.blocks.length+1).padStart(3,'0')}`,donor:'',photo:null,identifier:null,mmPerPx:null,calibration:null,orientation:'',notes:'',scores:[],regions:[]};state.blocks.push(b);blockId=b.id;draft=[];save();render()};
  if(tab==='blocks'&&!state.blocks.length){const box=document.createElement('div');box.className='notice';box.textContent='Start by ingesting a photo folder or registering a block. No example blocks are added to this experiment.';$('#content').prepend(box)}
};
