/* The same centre-based affine convention as affine.py. SVG screen coordinates: clockwise positive. */
(function(root){
 const defaults=()=>({scale:1,tx:0,ty:0,rotation:0,flip_x:false,flip_y:false,pivot_x:0,pivot_y:0});
 function matrix(t){const s=t.scale??1,r=(t.rotation??0)*Math.PI/180,co=Math.cos(r),si=Math.sin(r),fx=t.flip_x?-1:1,fy=t.flip_y?-1:1,px=t.pivot_x??0,py=t.pivot_y??0,a=s*co*fx,b=s*si*fx,c=-s*si*fy,d=s*co*fy;return[a,b,c,d,(t.tx??0)+s*px-a*px-c*py,(t.ty??0)+s*py-b*px-d*py];}
 function point(t,x,y){const[a,b,c,d,e,f]=matrix(t);return{x:a*x+c*y+e,y:b*x+d*y+f};}
 function box(t,b){const pts=[[b.x,b.y],[b.x+b.w,b.y],[b.x,b.y+b.h],[b.x+b.w,b.y+b.h]].map(([x,y])=>point(t,x,y)),xs=pts.map(p=>p.x),ys=pts.map(p=>p.y),x=Math.min(...xs),y=Math.min(...ys);return{x,y,w:Math.max(...xs)-x,h:Math.max(...ys)-y};}
 const api={defaults,matrix,point,box,svg:t=>'matrix('+matrix(t).map(v=>Number(v.toPrecision(15))).join(' ')+')'};root.LiveryTransform=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
