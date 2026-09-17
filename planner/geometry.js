(function(root){
const transform=(points,x,y,angle,mirror=false)=>{const r=angle*Math.PI/180,c=Math.cos(r),s=Math.sin(r);return points.map(([px,py])=>{px*=mirror?-1:1;return [x+px*c-py*s,y+px*s+py*c]})};
const area=p=>Math.abs(p.reduce((a,v,i)=>{let n=p[(i+1)%p.length];return a+v[0]*n[1]-v[1]*n[0]},0))/2;
const inside=(p,poly)=>{let c=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];if(((a[1]>p[1])!==(b[1]>p[1]))&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])c=!c}return c};
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
const on=(a,b,p)=>Math.abs(cross(a,b,p))<1e-8&&p[0]>=Math.min(a[0],b[0])-1e-8&&p[0]<=Math.max(a[0],b[0])+1e-8&&p[1]>=Math.min(a[1],b[1])-1e-8&&p[1]<=Math.max(a[1],b[1])+1e-8;
const intersects=(a,b,c,d)=>{let x=cross(a,b,c),y=cross(a,b,d),u=cross(c,d,a),v=cross(c,d,b);return (x*y<0&&u*v<0)||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b)};
const pointSegment=(p,a,b)=>{let dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy,t=l?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l)):0;return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)};
const distance=(a,b)=>{if(inside(a[0],b)||inside(b[0],a))return 0;let min=Infinity;for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++){let p=a[i],q=a[(i+1)%a.length],r=b[j],s=b[(j+1)%b.length];if(intersects(p,q,r,s))return 0;min=Math.min(min,pointSegment(p,r,s),pointSegment(q,r,s),pointSegment(r,p,q),pointSegment(s,p,q))}return min};
const simple=p=>{if(p.length<3||area(p)<1e-6)return false;for(let i=0;i<p.length;i++)for(let j=i+1;j<p.length;j++){if(j===i+1||(i===0&&j===p.length-1))continue;if(intersects(p[i],p[(i+1)%p.length],p[j],p[(j+1)%p.length]))return false}return true};
const api={transform,area,distance,simple};if(typeof module!=='undefined')module.exports=api;else root.Geo=api;
})(globalThis);
