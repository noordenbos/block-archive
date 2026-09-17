'use strict';
window.ProjectFormat={validate:function(s,Geo,dummyPhoto=()=>null){const str=x=>typeof x==='string'&&x.length<=10000,num=x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=1e6,points=p=>Array.isArray(p)&&p.length<=5000&&p.every(q=>Array.isArray(q)&&q.length===2&&q.every(num)),img=x=>x===null||(typeof x==='string'&&/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(x))||(typeof x==='string'&&[1,2].some(n=>x===dummyPhoto(n)||x===dummyPhoto(n,true)));if(!s||s.version!==1||!str(s.name)||!Array.isArray(s.blocks)||s.blocks.length>1000||!Array.isArray(s.slides)||!s.slides.length||s.slides.length>200)throw Error('Unsupported project structure.');let c=s.config;if(!c||!['Xenium','CosMx','Custom / future platform'].includes(c.assay)||!['product','source','revision'].every(k=>str(c[k]))||!['width','height'].every(k=>num(c[k])&&c[k]>0&&c[k]<=100)||!['margin','gap'].every(k=>num(c[k])&&c[k]>=0&&c[k]<=100)||2*c.margin>=Math.min(c.width,c.height)||typeof c.verified!=='boolean')throw Error('Invalid assay configuration.');let ids=new Set(),regions=new Set();function id(x){if(!str(x)||!/^[a-zA-Z0-9_-]+$/.test(x)||ids.has(x))throw Error('Invalid or duplicate record ID.');ids.add(x)}for(let b of s.blocks){id(b.id);if(!['name','donor','orientation','notes'].every(k=>str(b[k]))||!img(b.photo)||!img(b.identifier)||!(b.mmPerPx===null||(num(b.mmPerPx)&&b.mmPerPx>0))||!Array.isArray(b.scores)||!b.scores.every(p=>points(p)&&p.length===2)||!Array.isArray(b.regions))throw Error('Invalid block.');if(b.calibration&&(!points(b.calibration.points)||b.calibration.points.length!==2||!num(b.calibration.length)||b.calibration.length<=0))throw Error('Invalid calibration.');for(let r of b.regions){id(r.id);regions.add(r.id);if(!str(r.name)||!points(r.points)||!Geo.simple(r.points)||!/^#[0-9a-f]{6}$/i.test(r.color)||!b.mmPerPx)throw Error('Invalid retained piece.')}}for(let sld of s.slides){id(sld.id);if(!str(sld.name)||!Array.isArray(sld.placements))throw Error('Invalid slide.');for(let p of sld.placements){id(p.id);if(!regions.has(p.regionId)||!['x','y','angle'].every(k=>num(p[k]))||!str(p.section)||typeof p.mirror!=='boolean'||typeof p.confirmed!=='boolean')throw Error('Invalid placement.')}}return s}};
// Portable inventory experiments carry the working tissue image once. Keep
// geometry and calibration byte-for-byte; old source duplicates are expendable.
ProjectFormat.compact=function(project){
  const result=structuredClone(project);
  for(const block of result.blocks||[]){
    if(!block.inventory)continue;
    block.identifier=null;
    for(const source of block.sources||[]){delete source.image;delete source.canonical;delete source.source}
    if(block.analysis){delete block.analysis.photo;delete block.analysis.canonical}
    block.inventory.storageVersion=2;
  }
  return result;
};
