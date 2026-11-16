// OMNI_DL_STORAGE_METER_V1: pure storage meter rows.   node tests/test-storage-meter.cjs
'use strict';
const a=require('node:assert/strict'),M=require('../worker/assets/storage-meter.js');
let n=0;const t=(name,fn)=>{fn();n++;};
const GB=1073741824;
t('a normal place',()=>{const r=M.rows([{id:'internal',label:'Console storage',free_bytes:200*GB,total_bytes:800*GB}]);
  a.equal(r.length,1);a.equal(r[0].used_pct,75);a.equal(r[0].text,'200.0 GB free of 800.0 GB');a.equal(r[0].low,false);});
t('low by share and by bytes',()=>{a.equal(M.rows([{id:'internal',label:'C',free_bytes:30*GB,total_bytes:1000*GB}])[0].low,true);
  a.equal(M.rows([{id:'usb0',label:'U',free_bytes:1.5*GB,total_bytes:16*GB}])[0].low,true);
  a.equal(M.rows([{id:'usb0',label:'U',free_bytes:3*GB,total_bytes:16*GB}])[0].low,false);});
t('unknown sizes, bad ids and junk are skipped',()=>{a.deepEqual(M.rows([{id:'internal',label:'C',free_bytes:null,total_bytes:null},
  {id:'evil',label:'X',free_bytes:1,total_bytes:2},{id:'usb9',label:'X',free_bytes:1,total_bytes:2},{id:'usb1',label:'U',free_bytes:-1,total_bytes:2},
  {id:'usb2',label:'U',free_bytes:1,total_bytes:0},null,'x']),[]);a.deepEqual(M.rows(null),[]);a.deepEqual(M.rows({}),[]);});
t('free above total is clamped, label capped, at most 9 rows',()=>{const r=M.rows([{id:'usb0',label:'L'.repeat(90),free_bytes:20*GB,total_bytes:10*GB}]);
  a.equal(r[0].used_pct,0);a.equal(r[0].label.length,40);
  a.equal(M.rows(Array.from({length:12},(_,i)=>({id:'internal',label:'C'+i,free_bytes:GB*5,total_bytes:GB*10}))).length,9);});
t('sizes read naturally',()=>{a.equal(M.size(512),'512 B');a.equal(M.size(2048),'2 KB');a.equal(M.size(5*1048576),'5.0 MB');a.equal(M.size(2*1099511627776),'2.0 TB');});
console.log('STORAGE METER PASS: '+n+' checks');
