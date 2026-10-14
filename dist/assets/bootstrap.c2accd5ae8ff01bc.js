/* 페이지 셸과 탭 전환만 먼저 실행하고, 데이터·지도 코드는 첫 사용 시 읽습니다. */
(async()=>{
 'use strict';
 const $=id=>document.getElementById(id);
 const resources=JSON.parse($('resources').textContent);
 const scripts=new Map(), styles=new Map(), datasets=new Map();
 let reportPromise, finderPromise, mapPromise, leafletPromise, accessibility, current;

 function script(url){
  if(!url)return Promise.resolve();
  if(!scripts.has(url))scripts.set(url,new Promise((resolve,reject)=>{
   const el=document.createElement('script');el.src=url;el.onload=resolve;
   el.onerror=()=>{scripts.delete(url);el.remove();reject(new Error('화면 파일을 읽지 못했습니다.'));};document.head.append(el);
  }));
  return scripts.get(url);
 }
 function style(url){
  if(!url)return Promise.resolve();
  if(!styles.has(url))styles.set(url,new Promise((resolve,reject)=>{
   const el=document.createElement('link');el.rel='stylesheet';el.href=url;el.onload=resolve;
   el.onerror=()=>{styles.delete(url);el.remove();reject(new Error('지도 스타일을 읽지 못했습니다.'));};document.head.insertBefore(el,$('dashboardStyles'));
  }));
  return styles.get(url);
 }
 async function decode(bytes){
  // 정적 서버가 Content-Encoding으로 이미 풀어 준 경우에도 한 번만 해제합니다.
  const stream=new Blob([bytes]).stream();
  return bytes[0]===31&&bytes[1]===139?new Response(stream.pipeThrough(new DecompressionStream('gzip'))).json():JSON.parse(new TextDecoder().decode(bytes));
 }
 function data(kind){
  const key=resources.mode==='standalone'?'inline':kind;
  if(!datasets.has(key)){
   const request=resources.mode==='standalone'
    ?decode(Uint8Array.from(atob($('payload').textContent.trim()),c=>c.charCodeAt(0)))
    :fetch(resources.data[kind]).then(response=>{if(!response.ok)throw new Error('자료 응답 오류: '+response.status);return response.arrayBuffer();}).then(buffer=>decode(new Uint8Array(buffer)));
   datasets.set(key,request.catch(error=>{datasets.delete(key);throw error;}));
  }
  return datasets.get(key);
 }
 function leaflet(){if(!leafletPromise)leafletPromise=(typeof L!=='undefined'?Promise.resolve():Promise.all([script(resources.scripts.leaflet),style(resources.leafletStyle)])).catch(error=>{leafletPromise=null;throw error;});return leafletPromise;}
 function reports(){
  if(!reportPromise)reportPromise=Promise.all([data('reports'),script(resources.scripts.report)]).then(([D])=>mountReport(D,async(j,mode,t)=>{await openTab('map');if(current==='map'&&accessibility)accessibility.select(j,mode,t);})).catch(error=>{reportPromise=null;throw error;});
  return reportPromise;
 }
 function finder(){
  if(!finderPromise)finderPromise=Promise.all([data('finder'),leaflet(),script(resources.scripts.ui),script(resources.scripts.finder)]).then(([D])=>mountPharmacyFinder(D)).catch(error=>{finderPromise=null;throw error;});
  return finderPromise;
 }
 function analysis(){
  if(!mapPromise)mapPromise=Promise.all([data('analysis'),data('finder'),leaflet(),script(resources.scripts.ui),script(resources.scripts.map)]).then(([D,F])=>{accessibility=mountAccessibilityMap({...D,mapPharmacies:F.mapPharmacies});return accessibility;}).catch(error=>{mapPromise=null;throw error;});
  return mapPromise;
 }
 function sizeMapPane(){
  if(current!=='map'||!accessibility)return;
  const pane=$('mapPane');pane.style.setProperty('--map-pane-top',`${Math.max(0,pane.getBoundingClientRect().top+scrollY)}px`);
  $('mapLegendMenu').open=innerWidth>1180&&innerHeight>860;accessibility.map.invalidateSize();
 }
 const names={overview:'분석 요약',map:'접근성 지도',compare:'후보 비교',evidence:'데이터·검증',finder:'운영 약국 찾기'};
 function busy(name){
  const pane=$(name+'Pane');pane.dataset.loading='true';pane.setAttribute('aria-busy','true');
  let box=pane.querySelector('.tab-load');if(!box){box=document.createElement('div');box.className='tab-load';box.setAttribute('role','status');pane.prepend(box);}
  box.textContent=names[name]+' 화면을 불러오는 중입니다.';
 }
 function clearBusy(name){const pane=$(name+'Pane');delete pane.dataset.loading;pane.setAttribute('aria-busy','false');pane.querySelector('.tab-load')?.remove();}
 async function openTab(name){
  current=name;
  document.querySelectorAll('.reportnav [role=tab]').forEach(b=>{const active=b.dataset.tab===name;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;if(active)b.scrollIntoView({block:'nearest',inline:'nearest'});});
  document.querySelectorAll('.viewpane').forEach(p=>p.hidden=p.id!==name+'Pane');$('printReport').hidden=name==='finder';$('printReport').disabled=true;
  busy(name);
  try{
   let view;if(name==='map')view=await analysis();else if(name==='finder')view=await finder();else await reports();
   clearBusy(name);
   if(current===name){if(name==='map'){sizeMapPane();view.open();}else if(name==='finder')view.open();$('printReport').disabled=false;}
  }catch(error){
   $(name+'Pane').setAttribute('aria-busy','false');
   const box=$(name+'Pane').querySelector('.tab-load');if(box){box.textContent='자료를 불러오지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요. ';const retry=document.createElement('button');retry.textContent='다시 시도';retry.onclick=()=>openTab(name);box.append(retry);}
   console.error(error);
  }finally{$('loading')?.remove();}
 }
 document.querySelectorAll('.reportnav [role=tab]').forEach(b=>{
  b.onclick=()=>openTab(b.dataset.tab);
  b.onkeydown=e=>{const all=[...document.querySelectorAll('.reportnav [role=tab]')],i=all.indexOf(b);let j;
   if(e.key==='ArrowRight')j=(i+1)%all.length;if(e.key==='ArrowLeft')j=(i+all.length-1)%all.length;if(e.key==='Home')j=0;if(e.key==='End')j=all.length-1;
   if(j!==undefined){e.preventDefault();all[j].focus();openTab(all[j].dataset.tab);}
  };
 });
 $('methodBtn').textContent='분석 방법과 한계';$('printReport').textContent='인쇄 · PDF';
 $('methodBtn').onclick=()=>$('method').showModal();$('closeMethod').onclick=()=>$('method').close();$('printReport').onclick=()=>print();
 window.addEventListener('resize',sizeMapPane);
 if(typeof ResizeObserver!=='undefined'){const observer=new ResizeObserver(sizeMapPane);observer.observe(document.querySelector('.top'));observer.observe(document.querySelector('.reportnav'));}
 let legendBeforePrint=false;
 window.addEventListener('beforeprint',()=>{legendBeforePrint=$('mapLegendMenu').open;$('mapLegendMenu').open=true;});
 window.addEventListener('afterprint',()=>{$('mapLegendMenu').open=legendBeforePrint;});
 const initial=Object.hasOwn(names,location.hash.slice(1))?location.hash.slice(1):'overview';
 await openTab(initial);
})();
