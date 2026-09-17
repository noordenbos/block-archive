'use strict';
let currentCSV='';
const el=id=>document.getElementById(id);
async function generate(){
  currentCSV=el('ids').value;el('pdf').disabled=true;el('generate').disabled=true;el('sheet').replaceChildren();el('status').textContent='Generating locally…';
  try{const r=await fetch('/api/labels',{method:'POST',headers:{'X-Archive-Request':'1'},body:currentCSV});if(!r.ok)throw Error('Cannot generate labels. Use a one-column CSV (1–2000 IDs).');
    const rows=await r.json();for(const row of rows){const label=document.createElement('article');label.className='label';const img=new Image();img.src=row.png;img.alt='QR for '+row.id;const text=document.createElement('b');text.className='code';text.textContent=row.id;label.append(img,text);el('sheet').append(label)}
    el('status').textContent=`${rows.length} unique labels generated on this PC. Print the PDF at 100%.`;el('pdf').disabled=false;
  }catch(e){el('status').textContent=e.message}finally{el('generate').disabled=false}
}
el('csv').onchange=async e=>{if(e.target.files[0]){el('ids').value=await e.target.files[0].text();await generate()}e.target.value=''};
el('generate').onclick=generate;
el('clear').onclick=()=>{currentCSV='';el('ids').value='';el('sheet').replaceChildren();el('pdf').disabled=true;el('status').textContent='List cleared from this page.'};
el('pdf').onclick=async()=>{const r=await fetch('/api/labels.pdf',{method:'POST',headers:{'X-Archive-Request':'1'},body:currentCSV});if(!r.ok){el('status').textContent='PDF generation failed.';return}const a=document.createElement('a'),url=URL.createObjectURL(await r.blob());a.href=url;a.download='spatial-id-qr-labels.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)};
