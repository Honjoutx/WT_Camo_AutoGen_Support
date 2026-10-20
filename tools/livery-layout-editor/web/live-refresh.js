/* Poll cheap file revisions; rebuild only after a stable change, preserving edits. */
(()=>{'use strict';
 const $=id=>document.getElementById(id),bar=document.createElement('div');bar.className='live-strip';
 bar.innerHTML='<label><input id="live-toggle" type="checkbox" checked>实时同步</label><span id="live-status" role="status">正在连接…</span><button id="live-export" hidden>导出本地副本</button><button id="live-apply" hidden>备份并刷新</button><button id="live-reload-ui" hidden>刷新界面</button>';
 document.querySelector('.toolbar').after(bar);
 const style=document.createElement('style');style.textContent='.live-strip{display:flex;align-items:center;flex-wrap:wrap;gap:9px;min-height:31px;padding:4px 15px;font-size:11px;background:#f8fbfa;border-bottom:1px solid #d9e7e2;color:#658076}.live-strip label{display:flex;align-items:center;gap:4px;white-space:nowrap}.live-strip input{accent-color:#22a899}.live-strip button{font-size:10px;padding:3px 7px}.live-strip[data-pending="true"]{background:#fff8e8;color:#806941}.live-loading .workspace,.live-loading .inspector,.live-loading .project-picker{pointer-events:none}';document.head.append(style);
 let pid=null,cursor=null,candidate=null,latest=null,timer=null,inFlight=false,refreshing=false,pending=false,retry=900,uiVersion=null,styleVersion=null;
 const enabled=()=>$('live-toggle').checked;
 $('live-toggle').checked=localStorage.getItem('livery-live-enabled')!=='false';
 function status(text,blocked=false){$('live-status').textContent=text;bar.dataset.pending=String(blocked);}
 function actions(local=false,ui=false){$('live-export').hidden=!local;$('live-apply').hidden=!local;$('live-reload-ui').hidden=!ui;}
 function schedule(ms=900){clearTimeout(timer);if(pid&&enabled())timer=setTimeout(tick,ms);}
 function api(path){return fetch(path+(path.includes('?')?'&':'?')+'project='+encodeURIComponent(pid),{cache:'no-store'}).then(async r=>{const j=await r.json();if(!r.ok)throw Error(j.error||r.statusText);return j;});}
 function blocked(){const s=window.LiveryStudio?.liveStatus?.();return !s||s.project_id!==pid||s.dirty||s.conflict||s.saving||s.loading||s.dragging||s.editing;}
 function reloadUI(){
  if(blocked()||window.LiveryChat?.busy||window.LiveryChat?.hasDraft){status('界面有更新，等待当前编辑或对话完成',true);const s=window.LiveryStudio?.liveStatus?.();actions(!!(s?.dirty||s?.conflict),true);return;}
  sessionStorage.setItem('livery-ui-view',JSON.stringify(window.LiveryStudio.captureView()));
  const panel=$('codex-panel');if(panel&&!panel.hidden)sessionStorage.setItem('livery-ui-chat',JSON.stringify({open:true,full:panel.classList.contains('full'),dark:panel.classList.contains('studio-dark')}));
  location.reload();
 }
 function styles(revision){
  for(const link of document.querySelectorAll('link[rel="stylesheet"]')){const u=new URL(link.href,location.href);if(u.origin===location.origin){u.searchParams.set('_live',revision);link.href=u.href;}}
 }
 async function tick(){
  if(inFlight||refreshing)return schedule();
  if(!pid||!enabled())return;
  if(document.visibilityState==='hidden')return schedule(2500);
  const captured=pid;inFlight=true;
  try{
   const r=await api('/api/studio/revision');if(pid!==captured)return;latest=r;retry=900;
   if(!cursor){cursor={...r};uiVersion??=r.ui_revision;styleVersion??=r.style_revision;return;}
   if(r.style_revision!==styleVersion){styles(r.style_revision);styleVersion=r.style_revision;}
   if(r.ui_revision!==uiVersion){pending=true;reloadUI();return;}
   if(r.registry_revision!==cursor.registry_revision){await window.LiveryStudio.updateRegistry();if(pid!==captured)return;cursor.registry_revision=r.registry_revision;}
   const changed=r.design_revision!==cursor.design_revision||r.state_revision!==cursor.state_revision||cursor.stable===false;
   if(!changed){candidate=null;pending=false;actions();status('已同步');return;}
   pending=true;
   const token=r.design_revision+':'+r.state_revision;
   if(candidate!==token){candidate=token;status('检测到更新，等待文件稳定…');return;}
   if(blocked()){status('后台已有更新，本地操作已保留',true);const local=window.LiveryStudio.liveStatus();actions(local.dirty||local.conflict);return;}
   refreshing=true;status('正在同步布局…');await window.LiveryStudio.refresh();
   pending=false;candidate=null;actions();status('布局已实时更新');
  }catch(e){status(e.blocked?e.message:'等待后台连接或文件写入…',!!e.blocked);retry=e.blocked?900:2500;}
  finally{inFlight=false;refreshing=false;schedule(retry);}
 }
 window.addEventListener('livery:project',e=>{
  pid=e.detail.id;cursor=e.detail.live?{...e.detail.live}:null;if(cursor){uiVersion??=cursor.ui_revision;styleVersion??=cursor.style_revision;}candidate=null;latest=null;pending=false;actions();status(enabled()?'已同步':'实时同步已暂停');schedule();
  const saved=sessionStorage.getItem('livery-ui-chat');if(saved){sessionStorage.removeItem('livery-ui-chat');try{const s=JSON.parse(saved);if(s.open){window.LiveryChat?.open?.();$('codex-panel')?.classList.toggle('full',!!s.full);$('codex-panel')?.classList.toggle('studio-dark',!!s.dark);}}catch{}}
 });
 window.addEventListener('livery:saved',e=>{if(cursor&&e.detail.project_id===pid){if(e.detail.state_revision)cursor.state_revision=e.detail.state_revision;if(e.detail.design_revision)cursor.design_revision=e.detail.design_revision;}});
 window.addEventListener('livery:conflict',e=>{latest=e.detail;pending=true;status('后台已有更新，本地修改已保留',true);actions(true);schedule(50);});
 window.addEventListener('livery:fileschanged',()=>schedule(100));
 window.addEventListener('focus',()=>schedule(100));document.addEventListener('visibilitychange',()=>schedule(100));
 $('live-toggle').onchange=()=>{localStorage.setItem('livery-live-enabled',String(enabled()));status(enabled()?'正在同步…':'实时同步已暂停');if(enabled())schedule(0);else clearTimeout(timer);};
 $('live-export').onclick=()=>window.LiveryStudio.exportLocal();
 $('live-reload-ui').onclick=reloadUI;
 $('live-apply').onclick=async()=>{try{refreshing=true;status('备份本地布局并同步…');await window.LiveryStudio.refresh({backup:true});actions();status('本地布局已备份，后台设计已同步');}catch(e){status(e.message,true);}finally{refreshing=false;schedule();}};
 window.LiveryLive={kick:()=>schedule(0),get pending(){return pending;},get revision(){return cursor;}};
})();
