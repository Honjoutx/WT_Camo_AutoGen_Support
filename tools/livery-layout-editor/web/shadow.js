(function(root){
 'use strict';
 const defaults=()=>({enabled:false,blur:12,distance:18,angle:135,opacity:.45,color:'#123845'});
 function normalize(s){return{...defaults(),...s};}
 function spec(id,shadow,meta){
  const s=normalize(shadow),[x,y]=meta.view_origin||[0,0],[w,h]=meta.viewbox,pad=3*s.blur+s.distance+2,a=s.angle*Math.PI/180;
  return{attrs:{id:'editor-shadow-'+id,filterUnits:'userSpaceOnUse',primitiveUnits:'userSpaceOnUse',x:x-pad,y:y-pad,width:w+2*pad,height:h+2*pad,'color-interpolation-filters':'sRGB'},children:[['feGaussianBlur',{in:'SourceAlpha',stdDeviation:s.blur,result:'shadow-blur'}],['feOffset',{in:'shadow-blur',dx:Math.cos(a)*s.distance,dy:Math.sin(a)*s.distance,result:'shadow-offset'}],['feFlood',{'flood-color':s.color,'flood-opacity':s.opacity,result:'shadow-color'}],['feComposite',{in:'shadow-color',in2:'shadow-offset',operator:'in',result:'shadow-only'}],['feMerge',{},[['feMergeNode',{in:'shadow-only'}],['feMergeNode',{in:'SourceGraphic'}]]]]};
 }
 function apply(canvas,nodes,layer,meta,svg){
  const s=normalize(layer.shadow),id='editor-shadow-'+layer.id;let f=canvas.querySelector('#'+id);
  if(!s.enabled){if(f)f.remove();nodes.effect.removeAttribute('filter');nodes.effect.removeAttribute('opacity');nodes.wrapper.setAttribute('opacity',layer.opacity);return;}
  const definition=spec(layer.id,s,meta);let defs=canvas.querySelector(':scope > defs');if(!defs){defs=svg('defs');canvas.prepend(defs);}
  if(!f){f=svg('filter');defs.append(f);}for(const[k,v]of Object.entries(definition.attrs))f.setAttribute(k,v);f.replaceChildren();
  for(const [name,attrs,children]of definition.children){const e=svg(name,attrs);for(const[c,ca]of children||[])e.append(svg(c,ca));f.append(e);}
  nodes.wrapper.setAttribute('opacity',1);nodes.effect.setAttribute('filter','url(#'+id+')');nodes.effect.setAttribute('opacity',layer.opacity);
 }
 const api={defaults,normalize,spec,apply};if(typeof module!=='undefined')module.exports=api;else root.LiveryShadow=api;
})(typeof window!=='undefined'?window:globalThis);
