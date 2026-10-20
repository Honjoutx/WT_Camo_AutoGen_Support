'use strict';
const LiveryExportFiles=(()=>{
 let serial=0,identity='',rows=[],selected=new Set(),ready=false;
 const el=id=>document.getElementById(id),memo=new Map();
 function update(){
  const custom=el('export-specific').checked,count=custom?selected.size:rows.length;
  el('export-file-summary').textContent='导出文件 · '+(ready?(custom?count+' / '+rows.length+' 项':'全部 '+rows.length+' 项'):'读取文件列表…');
  el('export-file-controls').hidden=!custom;el('export-specific').disabled=!ready;
  if(custom&&ready)memo.set(identity,new Set(selected));else if(ready)memo.delete(identity);
 }
 function render(){
  const list=el('export-file-list'),query=el('export-file-search').value.trim().toLowerCase();list.replaceChildren();
  for(const row of rows.filter(r=>r.filename.toLowerCase().includes(query))){
   const label=document.createElement('label'),check=document.createElement('input'),text=document.createElement('span');
   check.type='checkbox';check.checked=selected.has(row.filename);check.dataset.filename=row.filename;
   check.onchange=()=>{if(check.checked)selected.add(row.filename);else selected.delete(row.filename);update();};
   text.textContent=row.filename;label.title=row.filename;label.append(check,text);list.append(label);
  }
  if(!list.children.length)list.textContent='没有匹配文件';update();
 }
 async function configure(project,preset,final){
  const panel=el('export-file-panel');panel.hidden=!final;if(!final)return;
  const key=project.id+':'+project.project_signature+':'+preset;if(key===identity&&ready)return;
  identity=key;const token=++serial;ready=false;rows=[];selected=new Set();el('export-specific').checked=false;el('export-file-search').value='';update();
  try{
   const response=await fetch('/api/export-files?project='+encodeURIComponent(project.id)+'&channels='+encodeURIComponent(preset));const data=await response.json();
   if(!response.ok)throw Error(data.error||'文件列表读取失败');if(token!==serial)return;
   rows=data.files;ready=true;const saved=memo.get(key);selected=saved?new Set([...saved].filter(n=>rows.some(r=>r.filename===n))):new Set(rows.map(r=>r.filename));el('export-specific').checked=!!saved;render();
  }catch(error){if(token===serial){el('export-file-summary').textContent=error.message;el('export-specific').disabled=true;}}
 }
 function get(){
  if(el('export-file-panel').hidden||!el('export-specific').checked)return null;
  if(!ready)throw Error('请等待贴图文件列表读取完成');if(!selected.size)throw Error('请至少勾选一个贴图文件');return [...selected].sort();
 }
 function init(){
  el('export-specific').onchange=()=>{if(el('export-specific').checked&&!selected.size)selected=new Set(rows.map(r=>r.filename));render();};
  el('export-file-search').oninput=render;
  for(const [id,add] of [['export-file-all',true],['export-file-none',false]])el(id).onclick=()=>{
   const query=el('export-file-search').value.trim().toLowerCase();for(const r of rows.filter(r=>r.filename.toLowerCase().includes(query)))if(add)selected.add(r.filename);else selected.delete(r.filename);render();
  };
 }
 return {configure,get,init};
})();
