/* Presentation-only localization. Never rewrites project/layout/asset data. */
(()=>{'use strict';
const dictionary=window.LiveryEnglish||{},records=new WeakMap(),attributes=new WeakMap();
const ignore='svg,script,style,code,textarea,.job-output,.checkpoint-item,#modal-content img,[data-i18n-ignore],.chat-rich,.chat-thread,.chat-tool pre,.chat-tool>p,#workflow-guide,#codex-requests p,#codex-requests input,#codex-title,#codex-context,#prop-text,#project-path,#project-subtitle,#project-label,#project-select option,#library-select option[value]:not([value=""]),#region-title,#region-note,#selected-name:not([data-i18n-label]),#regions,.layer-name,.asset-name,.asset-card img,#export-file-list span,#export-file-list label,#results a[download]';
let language='zh-CN',userSelected=false,scheduled=false,preferenceSave=Promise.resolve();
try{language=localStorage.getItem('livery-language')||(/^zh/i.test(navigator.language)?'zh-CN':'en');}catch{}
const pieces=Object.keys(dictionary).filter(k=>k.length>1&&/[\u4e00-\u9fff]/.test(k)).sort((a,b)=>b.length-a.length);
function t(text){
 if(language!=='en'||typeof text!=='string')return text;
 const core=text.trim();if(Object.hasOwn(dictionary,core))return text.replace(core,dictionary[core]);
 // These labels append runtime counts, device names or filenames. Longest
 // phrases win; user-owned text nodes are excluded before this function runs.
 let result=text;for(const key of pieces)if(result.includes(key))result=result.split(key).join(dictionary[key]);
 return result.replace(/(\d+) 项/g,'$1 items').replace(/(\d+) 面/g,'$1 faces');
}
function excluded(element){return !!element?.closest?.(ignore);}
function localize(node){
 if(node.nodeType===Node.TEXT_NODE){
  if(!node.parentElement||excluded(node.parentElement))return;
  const raw=node.nodeValue,old=records.get(node),source=old&&raw===old.last?old.source:raw;
  const output=t(source);records.set(node,{source,last:output});if(raw!==output)node.nodeValue=output;
  return;
 }
 if(node.nodeType!==Node.ELEMENT_NODE&&node.nodeType!==Node.DOCUMENT_NODE)return;
 if(node.nodeType===Node.ELEMENT_NODE){
  if(excluded(node))return;
  // Option labels may be localized, but category keys must remain unchanged.
  if(node.tagName==='OPTION'&&!node.hasAttribute('value'))node.value=node.textContent;
  let old=attributes.get(node);if(!old){old={};attributes.set(node,old);}
  for(const name of ['title','placeholder','aria-label','alt'])if(node.hasAttribute(name)){
   const raw=node.getAttribute(name),previous=old[name],source=previous&&raw===previous.last?previous.source:raw,output=t(source);
   old[name]={source,last:output};if(output!==raw)node.setAttribute(name,output);
  }
 }
 for(const child of node.childNodes)localize(child);
}
function apply(){scheduled=false;if(!document.body)return;localize(document.documentElement);document.documentElement.lang=language;const picker=document.getElementById('language-select');if(picker)picker.value=language;}
function schedule(){if(!scheduled){scheduled=true;queueMicrotask(apply);}}
async function setLanguage(value,persist=true){
 if(!['zh-CN','en'].includes(value))return;
 language=value;if(persist){userSelected=true;try{localStorage.setItem('livery-language',value);}catch{}
  preferenceSave=preferenceSave.catch(()=>{}).then(()=>fetch('/api/studio/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({language:value})}));
 }
 apply();window.dispatchEvent(new CustomEvent('livery:language',{detail:{language:value}}));
}
function init(){
 const label=document.createElement('label');label.className='language-picker';
 const select=document.createElement('select');select.id='language-select';select.setAttribute('aria-label','Language / 语言');
 select.innerHTML='<option value="zh-CN">简体中文</option><option value="en">English</option>';select.value=language;select.onchange=()=>setLanguage(select.value);label.append(select);document.querySelector('.top-actions').prepend(label);
 const observer=new MutationObserver(changes=>{if(changes.some(c=>!excluded(c.target.nodeType===Node.TEXT_NODE?c.target.parentElement:c.target)))schedule();});
 observer.observe(document.documentElement,{childList:true,characterData:true,subtree:true,attributes:true,attributeFilter:['title','placeholder','aria-label','alt']});apply();
 fetch('/api/studio/preferences').then(r=>r.json()).then(p=>{if(!userSelected&&p.language)setLanguage(p.language,false);}).catch(()=>{});
}
for(const name of ['alert','confirm','prompt']){const original=window[name].bind(window);window[name]=(message,...args)=>original(t(String(message)),...args);}
window.LiveryI18n={t,setLanguage,apply,get language(){return language;}};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
