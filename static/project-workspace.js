'use strict';
(() => {
  const nativeFetch=window.fetch.bind(window);
  const databaseName=id=>id==='local'?'spatial-prep-local':'spatial-prep-local:'+id;
  const openDatabase=id=>new Promise((resolve,reject)=>{const r=indexedDB.open(databaseName(id),1);r.onupgradeneeded=()=>r.result.createObjectStore('projects');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
  const readEntries=db=>new Promise((resolve,reject)=>{const r=db.transaction('projects').objectStore('projects').openCursor(),entries=[];r.onsuccess=()=>{const cursor=r.result;if(!cursor)return resolve(entries);if(cursor.key==='current'||String(cursor.key).startsWith('experiment:'))entries.push({key:cursor.key,value:cursor.value});cursor.continue()};r.onerror=()=>reject(r.error)});
  function validate(collection){
    if(!collection||!Array.isArray(collection.entries))throw Error('Invalid experiment collection.');
    const keys=new Set();
    for(const entry of collection.entries){if(!entry||typeof entry.key!=='string'||!(entry.key==='current'||/^experiment:[A-Za-z0-9_-]{1,120}$/.test(entry.key))||keys.has(entry.key))throw Error('Invalid experiment key.');keys.add(entry.key);ProjectFormat.validate(entry.value,Geo,typeof dummyPhoto==='function'?dummyPhoto:()=>null)}
    return collection;
  }
  async function responseData(response){if(!response.ok){let data=await response.json();throw Error(typeof data.detail==='string'?data.detail:'The project request failed.')}return response.json()}
  async function restoreIfEmpty(id){
    const db=await openDatabase(id);
    try{
      const entries=await readEntries(db);if(entries.length)return;
      const collection=validate(await responseData(await nativeFetch('/api/v1/projects/'+encodeURIComponent(id)+'/experiments')));
      if(!collection.entries.length)return;
      await new Promise((resolve,reject)=>{const tx=db.transaction('projects','readwrite'),store=tx.objectStore('projects');for(const e of collection.entries)store.put(e.value,e.key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Experiment restore was interrupted.'))});
    }finally{db.close()}
  }
  window.workspaceReady=(async()=>{
    const project=await responseData(await nativeFetch('/api/v1/project'));
    window.activeProject=project;window.projectDatabaseName=databaseName(project.id);
    await restoreIfEmpty(project.id);
    return project;
  })();
  window.fetch=async(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(url.origin===location.origin&&url.pathname.startsWith('/api/')){
      await window.workspaceReady;
      const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));headers.set('X-Archive-Project',window.activeProject.id);
      return nativeFetch(input,{...options,headers});
    }
    return nativeFetch(input,options);
  };
  async function request(path,body){return responseData(await fetch(path,body===undefined?{}:{method:'POST',headers:{'X-Archive-Request':'1',...(body instanceof FormData?{}:{'Content-Type':'application/json'})},body:body instanceof FormData?body:JSON.stringify(body)}))}
  let bar,status;
  function report(text,error=false){status.textContent=text;status.classList.toggle('project-error',error)}
  async function flush(){if(typeof archiveExperiment==='function')await archiveExperiment()}
  async function open(id){await flush();await restoreIfEmpty(id);await request('/api/v1/projects/'+encodeURIComponent(id)+'/open',{});if(location.pathname==='/'){location.hash='capture';location.reload()}else location.assign('/#capture')}
  function dialog(title,description){
    const box=document.createElement('dialog');box.className='project-dialog';
    const heading=document.createElement('h2');heading.textContent=title;box.append(heading);
    const text=document.createElement('p');text.textContent=description;box.append(text);
    const error=document.createElement('p');error.className='project-error';error.setAttribute('role','alert');
    const actions=document.createElement('div');actions.className='project-actions';
    const cancel=document.createElement('button');cancel.textContent='Cancel';cancel.onclick=()=>box.close();actions.append(cancel);
    box.append(error,actions);box.onclose=()=>box.remove();document.body.append(box);box.showModal();
    return {box,actions,error};
  }
  function newProject(){
    const {box,actions,error}=dialog('New project','Start an empty inventory and experiment collection. Your current project stays available under Open project.');
    const label=document.createElement('label');label.textContent='Project name';const input=document.createElement('input');input.maxLength=160;input.value='Untitled project';label.append(input);box.insertBefore(label,error);
    const create=document.createElement('button');create.className='primary';create.textContent='Create project';actions.prepend(create);input.select();
    create.onclick=async()=>{if(!input.value.trim()){error.textContent='Enter a project name.';return}create.disabled=true;try{await flush();const project=await request('/api/v1/projects',{name:input.value.trim()});await open(project.id)}catch(e){error.textContent=e.message;create.disabled=false}};
  }
  async function openProject(){
    const {box,actions,error}=dialog('Open project','Open a project saved on this laptop, or restore a complete project JSON into a separate inventory.');
    const list=document.createElement('div');list.className='project-list';box.insertBefore(list,error);
    try{const {items}=await request('/api/v1/projects');for(const project of items){const button=document.createElement('button');button.textContent=project.name+(project.id===window.activeProject.id?' · current':'');button.onclick=async()=>{button.disabled=true;try{await open(project.id)}catch(e){error.textContent=e.message;button.disabled=false}};list.append(button)}}catch(e){error.textContent=e.message}
    const label=document.createElement('label');label.className='button';label.textContent='Open project JSON';const input=document.createElement('input');input.type='file';input.accept='.json,application/json';input.hidden=true;label.append(input);actions.prepend(label);
    input.onchange=async()=>{const file=input.files[0];if(!file)return;if(file.size>2*1024**3){error.textContent='Project exceeds the 2 GB JSON limit.';return}input.disabled=true;error.textContent='Restoring inventory and experiments…';try{await flush();const form=new FormData();form.append('file',file);const project=await request('/api/v1/projects/import',form);await open(project.id)}catch(e){error.textContent=e.message;input.disabled=false;input.value=''}};
  }
  async function saveProject(button,exportFile=false){
    button.disabled=true;report('Saving full project JSON…');
    try{
      await flush();const db=await openDatabase(window.activeProject.id);let entries;
      try{entries=await readEntries(db)}finally{db.close()}
      entries=entries.map(entry=>({...entry,value:ProjectFormat.compact(entry.value)}));
      validate({entries});
      if(!exportFile){const result=await request('/api/v1/local-saves/project',{entries});report('Saved to '+result.path);return}
      const response=await fetch('/api/v1/projects/export',{method:'POST',headers:{'X-Archive-Request':'1','Content-Type':'application/json'},body:JSON.stringify({entries})});
      if(!response.ok)await responseData(response);
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=(window.activeProject.name.replace(/[^a-z0-9_-]+/gi,'-')||'project')+'-project.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
      report('Downloaded inventory, photos, metadata, QC and all experiments saved in this browser.');
    }catch(e){report('Could not save project: '+e.message,true)}finally{button.disabled=false}
  }
  async function storageDialog(){
    const {box,actions,error}=dialog('Save location','Save directly on this computer. Leave the folder empty to use the installation’s private data folder. This setting applies to this archive project and its experiments; it does not move existing files or the live archive.');
    const label=document.createElement('label');label.textContent='Folder';const input=document.createElement('input');input.placeholder='Default installation storage';label.append(input);box.insertBefore(label,error);
    const destination=document.createElement('p');box.insertBefore(destination,error);
    try{const current=await request('/api/v1/save-location');input.value=current.folder;destination.textContent='Current destination: '+current.destination}catch(e){error.textContent=e.message}
    const browse=document.createElement('button');browse.textContent='Choose folder…';browse.onclick=async()=>{browse.disabled=true;try{const result=await request('/api/v1/save-location/browse',{});if(result.folder)input.value=result.folder}catch(e){error.textContent=e.message}finally{browse.disabled=false}};
    const reset=document.createElement('button');reset.textContent='Use default';reset.onclick=()=>input.value='';
    const apply=document.createElement('button');apply.textContent='Use this location';apply.onclick=async()=>{apply.disabled=true;try{const result=await request('/api/v1/save-location',{folder:input.value});report('Save location: '+result.destination);box.close()}catch(e){error.textContent=e.message;apply.disabled=false}};
    actions.prepend(browse,reset,apply);
  }
  window.saveLocalExperiment=value=>request('/api/v1/local-saves/experiment',value);
  function mount(){
    bar=document.createElement('section');bar.className='project-bar';bar.setAttribute('aria-label','Project workspace');
    const scope=document.createElement('span');scope.className='project-scope';scope.textContent='Archive project';bar.append(scope);
    const name=document.createElement('strong');name.textContent='Loading project…';bar.append(name);
    const buttons=document.createElement('div');buttons.className='project-actions';bar.append(buttons);
    for(const [title,action] of [['New project',newProject],['Open project',openProject],['Save project',saveProject],['Save location',storageDialog],['Export project JSON',button=>saveProject(button,true)]]){const b=document.createElement('button');b.textContent=title;b.disabled=true;b.onclick=()=>action(b);buttons.append(b)}
    status=document.createElement('span');status.className='project-status';status.setAttribute('role','status');bar.append(status);
    document.querySelector('header').after(bar);
    window.workspaceReady.then(project=>{name.textContent=project.name;name.title='Whole inventory + experiments';buttons.querySelectorAll('button').forEach(b=>b.disabled=false);const archiveLink=document.createElement('a');archiveLink.className='button';archiveLink.href='/archive';archiveLink.textContent='Block checkout & return';archiveLink.title='Physical block records and cutting history in '+project.name;buttons.append(archiveLink);if(['/archive','/imports'].includes(location.pathname)){const photos=document.createElement('a');photos.className='button';photos.href='/imports';photos.textContent='Link photos to block records';photos.title='Attach imported photographs to registered blocks in '+project.name;buttons.append(photos)}}).catch(e=>report('Project could not open: '+e.message,true));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
