'use strict';
function nextSlideName(){
  let n=state.slides.length+1,name;
  do{name=`${state.name}_slide_${String(n++).padStart(3,'0')}`}while(state.slides.some(s=>s.name===name));
  return name;
}
function addNamedSlide(){
  if(state.slides.length>=200)return null;
  const slide={id:uid(),name:nextSlideName(),placements:[]};state.slides.push(slide);return slide;
}
function preferredSlides(){
  const index=state.slides.findIndex(s=>s.id===state.lastAssignedSlideId);
  return index<0?[]:[state.slides[index],state.slides[index+1]].filter(Boolean);
}
function assignPieces(block,regions,targetId){
  const slide=state.slides.find(s=>s.id===targetId);
  if(!slide||!block.photo||!block.mmPerPx)return notify('A calibrated tissue photo is required before assigning pieces.');
  for(const region of regions){
    if(slide.placements.some(p=>p.regionId===region.id))continue;
    slide.placements.push({id:uid(),regionId:region.id,x:state.config.width/2,y:state.config.height/2,angle:0,mirror:false,confirmed:false,section:`SEC-${slide.placements.length+1}`});
  }
  state.lastAssignedSlideId=slide.id;slideId=slide.id;selected=null;save();render();
  notify('Pieces assigned. Arrange them in Slide mapping.');
}
function renderSlideOverview(){
  $('#content').innerHTML=pageHead('EXPERIMENT / RECIPIENT SLIDES','Slide overview','Name slides in preparation order. Assign retained pieces from each block.', '')+`<section class="card"><div class="toolbar"><label class="field">Number of slides<input id="slideCount" type="number" min="1" max="200" value="${state.slides.length}"></label><button id="createSlides">Add slides up to this number</button></div><details><summary>Paste slide names · one per line</summary><p>Updates names in list order and adds slides if needed. Existing placements stay on their slide; later slides are kept.</p><textarea id="slideNames" aria-label="Slide names" placeholder="One slide name per line"></textarea><button id="applySlideNames">Apply names</button></details><p id="slideListError" role="alert"></p><div class="slide-overview-list">${state.slides.map((s,i)=>`<div class="slide-overview-row"><span>${i+1}</span><input data-slide-name="${s.id}" aria-label="Slide ${i+1} name" value="${esc(s.name)}" maxlength="160"><span>${s.placements.length} pieces</span><button data-open-slide="${s.id}">Open map</button></div>`).join('')}</div></section>`;
  $('#createSlides').onclick=()=>{const count=Number($('#slideCount').value);if(!Number.isInteger(count)||count<state.slides.length||count>200){$('#slideListError').textContent='Enter a total between the current slide count and 200. Use Slide mapping to delete a slide.';return}while(state.slides.length<count)addNamedSlide();save();render()};
  $('#applySlideNames').onclick=()=>{const names=$('#slideNames').value.split(/\r?\n/).map(x=>x.trim());if(!names.length||names.length>200||names.some(n=>!n||n.length>160)||new Set(names).size!==names.length||state.slides.slice(names.length).some(s=>names.includes(s.name))){$('#slideListError').textContent='Use unique, nonempty names, at most 160 characters each and 200 slides.';return}while(state.slides.length<names.length)addNamedSlide();names.forEach((name,i)=>state.slides[i].name=name);save();render()};
  document.querySelectorAll('[data-slide-name]').forEach(input=>input.onchange=()=>{const name=input.value.trim(),slide=state.slides.find(s=>s.id===input.dataset.slideName);if(!name||state.slides.some(s=>s.id!==slide.id&&s.name===name)){input.value=slide.name;return notify('Use a nonempty, unique slide name.')}slide.name=name;save()});
  document.querySelectorAll('[data-open-slide]').forEach(button=>button.onclick=()=>{slideId=button.dataset.openSlide;selected=null;tab='slides';render()});
}
const renderWithAssignments=render;
render=function(){
  renderWithAssignments();
  // Capture belongs in the inventory; keep experiment actions focused on planning.
  if(tab==='blocks')document.querySelectorAll('#addBlock + a, .page-head input[webkitdirectory]').forEach(el=>el.matches('input')?el.parentElement.remove():el.remove());
  if(tab==='slides'){
    $('#addSlide').onclick=()=>{const s=addNamedSlide();if(!s)return notify('Up to 200 slides per experiment.');slideId=s.id;selected=null;save();render()};
    document.querySelectorAll('[data-add-region]').forEach(button=>{const previous=button.onclick;button.onclick=()=>{state.lastAssignedSlideId=slideId;previous()}});
  }
  if(tab!=='blocks'||!currentBlock())return;
  const block=currentBlock(),panel=document.createElement('section');panel.className='card block-slide-assignment';
  panel.innerHTML='<h3>Assign retained tissue to a slide</h3><p class="muted">Last used slide first, then the next in your list. Existing assignments are kept.</p><div class="fields"><label class="field">Find slide<input id="findTargetSlide" type="search" placeholder="Search slide names"></label><label class="field">Recipient slide<select id="blockTargetSlide"></select></label></div><div class="toolbar"><button id="assignBlockPieces">Assign all pieces to slide</button><button id="openTargetSlide">Open slide map</button><button id="manageSlides">Name / add slides</button></div><div id="pieceAssignments"></div>';
  $('.photo-area').before(panel);
  const choice=panel.querySelector('select');
  function choices(query=''){const prior=choice.value;choice.replaceChildren();for(const [label,slides] of [['Recent & next',preferredSlides()],['All slides',state.slides]]){const matching=slides.filter(s=>s.name.toLowerCase().includes(query.toLowerCase()));if(!matching.length)continue;const group=document.createElement('optgroup');group.label=label;for(const s of matching){const option=document.createElement('option');option.value=s.id;option.textContent=s.name;group.append(option)}choice.append(group)}if([...choice.options].some(o=>o.value===prior))choice.value=prior;$('#assignBlockPieces').disabled=!choice.value||!block.regions.length||!block.photo||!block.mmPerPx;$('#openTargetSlide').disabled=!choice.value;panel.querySelectorAll('[data-assign-piece]').forEach(b=>b.disabled=!choice.value||!block.photo||!block.mmPerPx)}
  $('#pieceAssignments').innerHTML=block.regions.map(r=>`<div class="region-row"><span><b>${esc(r.name)}</b><br>${state.slides.filter(s=>s.placements.some(p=>p.regionId===r.id)).map(s=>esc(s.name)).join(', ')||'Unassigned'}</span><button data-assign-piece="${r.id}">Assign piece</button></div>`).join('');
  choices();$('#findTargetSlide').oninput=e=>choices(e.target.value);
  $('#assignBlockPieces').onclick=()=>assignPieces(block,block.regions,choice.value);
  panel.querySelectorAll('[data-assign-piece]').forEach(button=>button.onclick=()=>assignPieces(block,[block.regions.find(r=>r.id===button.dataset.assignPiece)],choice.value));
  $('#openTargetSlide').onclick=()=>{slideId=choice.value;selected=null;tab='slides';render()};
  $('#manageSlides').onclick=()=>{tab='overview';render()};
};
