'use strict';
const LiveryExportGpu=(()=>{
 const el=id=>document.getElementById(id),key='livery-export-gpu';
 let probe=null;
 function init(){
  try{el('export-gpu').checked=localStorage.getItem(key)==='1';}catch{}
  el('export-gpu').onchange=()=>{try{localStorage.setItem(key,el('export-gpu').checked?'1':'0');}catch{}};
 }
 async function configure(project,mode){
  const control=el('export-gpu-control'),input=el('export-gpu');
  control.hidden=project.project_type!=='surface-planes'||mode==='boards';
  if(control.hidden)return;
  input.disabled=true;control.title='正在检测 GPU…';
  probe ||= fetch('/api/export-acceleration').then(async response=>{
   const value=await response.json();if(!response.ok)throw Error(value.error||'GPU 检测失败');return value;
  }).catch(error=>({available:false,reason:error.message}));
  const capability=await probe;input.disabled=!capability.available;
  control.title=capability.available?capability.device+' · 加速法线与平滑计算；异常时回退 CPU':capability.reason||'GPU 贴图加速不可用';
 }
 function get(project,mode){return project.project_type==='surface-planes'&&mode!=='boards'&&el('export-gpu').checked&&!el('export-gpu').disabled?'gpu':'cpu';}
 return {init,configure,get};
})();
