'use strict';
const $=s=>document.querySelector(s);
async function call(path,body){const r=await fetch('/desktop/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Archive-Request':'1'}:{},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(data.detail||'Could not complete this change.');return data;}
function error(e){$('#message').textContent=e.message;}
call('status').then(data=>{$('#storage').textContent=data.storage;$('#folder').value=data.storage;$('#version').textContent='Version '+data.version;if(data.first_run)$('#message').textContent='First start: confirm this storage location or choose a different folder below.';}).catch(error);
$('#open').onclick=()=>call('ready',{}).then(()=>location.href='/').catch(error);
$('#change').onclick=async()=>{try{const result=await call('storage',{path:$('#folder').value});$('#message').textContent=result.restarting?'Restarting with the selected folder. A new browser page will open.':'Storage location saved.';}catch(e){error(e);}};
$('#quit').onclick=()=>call('quit',{}).then(()=>{$('#message').textContent='Block Archive has stopped. You can close this page.';document.querySelectorAll('button').forEach(b=>b.disabled=true);}).catch(error);
