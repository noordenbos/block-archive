'use strict';
// View state never changes source pixels, calibration, outlines or placements.
const annotationViews=new Map();
let annotationObserver=null;
function annotationView(block){
  let view=annotationViews.get(block.id);
  if(!view||view.photo!==block.photo){view={photo:block.photo,zoom:1.6,x:.5,y:.45};annotationViews.set(block.id,view)}
  return view;
}
function sizeAnnotation(canvas,holder,view){
  const scale=Math.min(holder.clientWidth/canvas.width,holder.clientHeight/canvas.height)*view.zoom;
  canvas.style.width=(canvas.width*scale)+'px';canvas.style.height=(canvas.height*scale)+'px';
  holder.scrollLeft=canvas.offsetLeft+canvas.clientWidth*view.x-holder.clientWidth/2;
  holder.scrollTop=canvas.offsetTop+canvas.clientHeight*view.y-holder.clientHeight/2;
  const value=$('#annotationZoom');if(value)value.textContent=Math.round(view.zoom*100)+'% of fit';
  if($('#zoomOutPhoto'))$('#zoomOutPhoto').disabled=view.zoom<=.5;
  if($('#zoomInPhoto'))$('#zoomInPhoto').disabled=view.zoom>=5;
}
drawBlock=async function(){
  const block=currentBlock(),canvas=$('#blockCanvas');if(!canvas||!block)return;
  const image=await blockImage(block);if(!canvas.isConnected||currentBlock()!==block)return;
  canvas.width=image?.width||900;canvas.height=image?.height||600;
  paint(canvas.getContext('2d'),block,image,true);
  sizeAnnotation(canvas,canvas.parentElement,annotationView(block));
};
const renderWithAnnotation=render;
render=function(){
  annotationObserver?.disconnect();renderWithAnnotation();
  if(tab!=='blocks'||!currentBlock()||!$('#blockCanvas'))return;
  const block=currentBlock(),canvas=$('#blockCanvas'),holder=canvas.parentElement,view=annotationView(block);
  const shell=document.createElement('section');shell.className='annotation-workspace';shell.setAttribute('aria-label','Tissue annotation workspace');holder.before(shell);
  const controls=document.createElement('div');controls.className='annotation-controls';shell.append(controls);
  const drawing=$('#finishROI').parentElement,zoom=$('#fitPhoto').parentElement,hint=$('#drawHint');
  controls.append(drawing,zoom);shell.append(holder,hint);
  const assignments=document.querySelector('.block-slide-assignment');if(assignments)shell.after(assignments);
  const out=document.createElement('button');out.id='zoomOutPhoto';out.textContent='−';out.setAttribute('aria-label','Zoom out tissue photo');
  const into=document.createElement('button');into.id='zoomInPhoto';into.textContent='+';into.setAttribute('aria-label','Zoom in tissue photo');
  const status=document.createElement('span');status.id='annotationZoom';status.className='muted';status.setAttribute('aria-live','polite');
  zoom.replaceChildren(out,into,$('#fitPhoto'),$('#focusPhoto'),status);
  $('#fitPhoto').textContent='Fit whole photo';$('#focusPhoto').textContent='Focus block';
  function setZoom(value){view.zoom=Math.max(.5,Math.min(5,value));sizeAnnotation(canvas,holder,view)}
  out.onclick=()=>setZoom(view.zoom/1.25);into.onclick=()=>setZoom(view.zoom*1.25);
  $('#fitPhoto').onclick=()=>{view.x=.5;view.y=.5;setZoom(1)};
  $('#focusPhoto').onclick=()=>{view.x=.5;view.y=.45;setZoom(1.6)};
  holder.onscroll=()=>{view.x=(holder.scrollLeft+holder.clientWidth/2-canvas.offsetLeft)/canvas.clientWidth;view.y=(holder.scrollTop+holder.clientHeight/2-canvas.offsetTop)/canvas.clientHeight};
  annotationObserver=new ResizeObserver(()=>{if(canvas.isConnected)sizeAnnotation(canvas,holder,view)});annotationObserver.observe(holder);
  drawBlock();
};
