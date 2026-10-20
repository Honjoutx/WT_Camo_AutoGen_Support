'use strict';
const LiveryExportPerformance=(()=>{
 const key='livery-export-performance',modes=['max','balanced','serial'];
 function init(){
  const select=document.getElementById('export-performance');
  try{const saved=localStorage.getItem(key);select.value=modes.includes(saved)?saved:'max';}catch{}
  select.onchange=()=>{try{localStorage.setItem(key,select.value);}catch{}};
 }
 function get(){return document.getElementById('export-performance').value;}
 return {init,get};
})();
