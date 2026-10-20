/* Storage choices are independent of layout data and remembered per project. */
(()=>{'use strict';
 const select=document.createElement('select');select.id='storage-mode';select.setAttribute('aria-label','存档方式');
 select.innerHTML='<option value="compact">轻量存档（推荐）</option><option value="portable">独立副本（便于搬运）</option>';
 select.title='轻量：复用缓存资源，下载时打包，支持的预览模型外链贴图。独立：生成常驻 ZIP，支持的预览模型内嵌贴图。';
 const help=document.createElement('small');help.id='storage-help';help.style.cssText='display:block;padding:7px 15px;color:#6b7c70;font-size:11px;line-height:1.6';
 document.querySelector('.generate-bar').insertBefore(select,document.getElementById('generate'));
 document.querySelector('.generate-bar').style.flexWrap='wrap';document.querySelector('.generate-bar>div').style.minWidth='145px';
 document.querySelector('.generate-bar').after(help);let project='';
 function explain(){help.textContent=select.value==='compact'?'轻量存档：相同缓存共享空间，ZIP 下载时生成。支持的预览模型依赖本机共享资源；搬运工程请选择独立副本。':'独立副本：保留常驻 ZIP；支持的预览模型内嵌贴图，可单独搬运，占用空间较多。';}
 select.onchange=()=>{localStorage.setItem('livery-storage-'+project,select.value);explain();};
 window.addEventListener('livery:project',e=>{project=e.detail.id;const saved=localStorage.getItem('livery-storage-'+project);select.value=['compact','portable'].includes(saved)?saved:'compact';explain();});
 window.LiveryStorage={choice:()=>select.value};explain();
})();
