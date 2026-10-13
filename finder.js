/* 시민이 등록 운영시간을 빠르게 확인하는 약국 찾기 화면. */
function pharmacyNightIntervals(schedule,day){
 const clipped=[...(schedule?.[day]||[]),...(schedule?.[(day+1)%7]||[]).map(([a,b])=>[a+1440,b+1440])]
  .filter(([a,b])=>a<1500&&b>1320).map(([a,b])=>[Math.max(a,1320),Math.min(b,1500)]).sort((a,b)=>a[0]-b[0]);
 const merged=[];for(const [a,b] of clipped){const last=merged.at(-1);if(last&&a<=last[1])last[1]=Math.max(last[1],b);else merged.push([a,b]);}return merged;
}
function pharmacyShiftDate(date,offset){const d=new Date(date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+offset);return d.toISOString().slice(0,10);}
function pharmacyDaySchedule(p,day,date){
 let v=p.schedule?.[day];const rules=p.scheduleExceptions?.recurring||[];
 if(date&&(p.scheduleExceptions?.closedDates||[]).includes(date))return [];
 for(const r of rules.filter(r=>r.day===day)){
  if(!date)return null;
  const included=r.weeks.includes(Math.ceil(Number(date.slice(8,10))/7));
  if(r.kind==='closed'&&included||r.kind==='open_only'&&!included)return [];
  if(r.kind==='open_only'&&included&&(!v||!v.length))return null;
 }
 return v;
}
function pharmacyAssumption(p,day){return String(p.scheduleSources?.[{0:'monday',5:'saturday',6:'sunday'}[day]]||'').startsWith('assumed_');}
function pharmacyCurrentInfo(p,n){
 const today=pharmacyDaySchedule(p,n.day,n.date),prevDay=(n.day+6)%7,prev=pharmacyDaySchedule(p,prevDay,pharmacyShiftDate(n.date,-1));
 const active=[...(today||[]).map(([a,b])=>({a,b,day:n.day,carry:false})),...(prev||[]).map(([a,b])=>({a:a-1440,b:b-1440,day:prevDay,carry:true}))].filter(x=>n.minutes>=x.a&&n.minutes<x.b);
 if(active.length){const end=Math.max(...active.map(x=>x.b));return {state:'open',end,remaining:end-n.minutes,carry:active.every(x=>x.carry),day:active.find(x=>x.b===end).day,assumed:active.every(x=>pharmacyAssumption(p,x.day))};}
 return {state:today==null||prev==null?'unknown':'closed',day:n.day,assumed:pharmacyAssumption(p,n.day)};
}
function mountPharmacyFinder(D){
 const $=id=>document.getElementById(id),E=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pharmacies=D.mapPharmacies||D.pharmacies,days=['월','화','수','목','금','토','일'];
 const formatter=new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
 const nowParts=()=>{const o={};formatter.formatToParts(new Date()).forEach(x=>o[x.type]=x.value);return {date:`${o.year}-${o.month}-${o.day}`,day:{월:0,화:1,수:2,목:3,금:4,토:5,일:6}[o.weekday[0]],minutes:+o.hour*60+(+o.minute),label:`${o.weekday} ${o.hour}:${o.minute}`};};
 const clock=n=>`${String(Math.floor(n/60)%24).padStart(2,'0')}:${String(n%60).padStart(2,'0')}${n>=1440?' 익일':''}`;
 const hours=(p,d,date)=>{const v=pharmacyDaySchedule(p,d,date);return v==null?'확인 필요':v.length?v.map(([a,b])=>`${clock(a)}–${clock(b)}`).join(', '):pharmacyAssumption(p,d)?'휴무 가정':'등록 시간표상 휴무'};
 const currentState=(p,n=nowParts())=>pharmacyCurrentInfo(p,n).state;
 const selectedDate=d=>{const n=nowParts();return pharmacyShiftDate(n.date,(d-n.day+7)%7);};
 const nightIntervals=(p,d)=>{const date=selectedDate(d),schedule=p.schedule.slice();schedule[d]=pharmacyDaySchedule(p,d,date);schedule[(d+1)%7]=pharmacyDaySchedule(p,(d+1)%7,pharmacyShiftDate(date,1));return pharmacyNightIntervals(schedule,d);};
 const nightState=(p,d)=>nightIntervals(p,d).length?'open':'unknown';
 const nightHours=(p,d)=>nightIntervals(p,d).map(([a,b])=>`${clock(a)}–${clock(b)}`).join(', ');
 const sourceNote=(p,d)=>pharmacyAssumption(p,d)?'운영시간 가정 포함 · 실제 영업 확인 필요':'등록 운영시간 · 현장 확인 아님';
 const exceptionNote=p=>{const e=p.scheduleExceptions||{};return `${e.breaks?.some(x=>x.length)?'휴게시간 비고 반영':''}${e.recurring?.length||e.closedDates?.length?' · 날짜별 휴무 반영':''}${e.review?.length?' · 추가 운영정보 확인 필요':''}`.replace(/^ · /,'');};
 const currentText=(p,n)=>{const info=pharmacyCurrentInfo(p,n);return info.state==='open'?`${info.carry?'전날 '+days[info.day]+'요일 영업 이어짐 · ':''}${clock(info.end)} 종료${info.remaining<=30?' · 곧 종료 ('+Math.ceil(info.remaining)+'분 남음)':''}`:hours(p,n.day,n.date);};
 const caution=(p,d)=>`${pharmacyAssumption(p,d)?'<b class="state assumed">운영시간 가정 포함</b>':''}${p.scheduleExceptions?.review?.length?'<b class="state unknown">추가 확인 필요</b>':''}`;
 const shortDong=p=>String(p.dong||'').replace(new RegExp('^'+p.district+'\\s*'),'');
 const sourceDates=pharmacies.map(p=>String(p.source||'').match(/\d{4}-\d{2}-\d{2}/)?.[0]).filter(Boolean).sort();
 const refresh=D.meta.refresh_status||{},refreshText=refresh.status==='failed'?`최근 갱신 실패 (${(refresh.attempted_at||'').slice(0,10)}) · 이전 정상 데이터 유지`:refresh.status==='passed'?`갱신 성공 (${(refresh.finished_at||'').slice(0,10)})`:'자동 갱신 미설정';
 const updated=D.meta.pharmacy_collected_at?.slice(0,10)||sourceDates.at(-1)||'조회일 미기록';
 const districts=[...new Set(pharmacies.map(p=>p.district).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));
 const n=nowParts();
 $('finderPane').innerHTML=`<div class="finderpage"><div class="finderhead"><div><div class="overline">05 / OPEN PHARMACY FINDER</div><h2>지금 갈 수 있는 약국 찾기</h2><p>부산 약국의 등록 운영시간을 지도와 목록에서 확인하세요.</p></div><div class="finder-now"><span>부산 현재 시각</span><strong id="finderNow">${E(n.label)}</strong></div></div><div class="finderfilters"><label class="findersearch"><span>약국명·주소</span><input id="finderSearch" type="search" placeholder="예: 서면, 365약국"></label><label><span>구·군</span><select id="finderDistrict"><option value="">부산 전체</option>${districts.map(x=>`<option>${E(x)}</option>`).join('')}</select></label><label><span>동</span><select id="finderDong"><option value="">전체 동</option></select></label><label><span>심야 기준 요일</span><select id="finderDay">${days.map((x,i)=>`<option value="${i}" ${i===n.day?'selected':''}>${x}요일</option>`).join('')}</select></label></div><div class="finderchips" id="finderMode" role="group" aria-label="약국 운영 필터"><button data-mode="current" class="active">● 현재 영업 중</button><button data-mode="night" id="finderNightMode">오늘 밤 22–01시</button><button data-mode="public">공공심야약국</button><button data-mode="all">전체 약국</button></div><div class="findernote">등록 운영시간 기준이며 임시휴무·공휴일·현장 상황은 반영하지 않습니다. 방문 전 전화로 확인하세요.</div><div class="finderlayout"><section class="findermapwrap" aria-label="운영 약국 지도"><div id="finderMap"></div><div class="finderlegend"><span><i class="open"></i>조건 충족</span><span><i class="public"></i>공공심야</span></div></section><aside class="finderresults"><div class="finderresulthead"><strong id="finderCount">—</strong><span id="finderStatus"></span></div><div id="finderList" class="finderlist"></div></aside></div></div>`;
 $('finderPane').querySelector('.findernote').innerHTML=`<strong>운영시간 조회 ${E(updated)}</strong> · 현재 시각으로 저장된 시간표를 판정합니다. 휴게·정기휴무는 비고에서 확인 가능한 범위를 반영합니다. 미확인 임시휴무·공휴일은 전화 확인하세요.<br><span id="finderRefresh">${E(refreshText)}${refresh.next_scheduled_at?' · 다음 갱신 '+E(refresh.next_scheduled_at):' · 다음 갱신 미예약'}</span>`;
 const pager=document.createElement('div');pager.className='finderpagination';pager.innerHTML='<button id="finderPrev" aria-label="이전 약국 목록">이전</button><span id="finderPage" aria-live="polite"></span><button id="finderNext" aria-label="다음 약국 목록">다음</button>';$('finderPane').querySelector('.finderresults').append(pager);
 let mode='current',finderMap,markers,normalRenderer,publicRenderer,opened=false,visible=[],timer=null,page=0,lastMinute='';const pageSize=100;
 const popup=p=>{const n=nowParts(),info=pharmacyCurrentInfo(p,n),d=mode==='night'?+$('finderDay').value:info.state==='open'?info.day:n.day,e=p.scheduleExceptions||{};return `<strong>${E(p.name)}</strong><br>${E(p.address)}${p.phone?`<br><a href="tel:${E(p.phone)}">${E(p.phone)}</a>`:''}<hr>${mode==='night'?`선택한 ${days[d]}요일 (${selectedDate(d)})<br>22–01시 중 운영: ${E(nightHours(p,d))}`:`${E(currentText(p,n))}<br>오늘 ${days[n.day]}요일: ${E(hours(p,n.day,n.date))}`}<br>${caution(p,d)}<br><small>${E(sourceNote(p,d))}<br>${E(exceptionNote(p))}<br>${E(p.source||'')}<br>조회 ${E(updated)} · 방문 전 전화 확인</small>${e.notes?`<details class="finder-notes"><summary>원천 운영 안내</summary><p>${E(e.notes).replace(/\n/g,'<br>')}</p></details>`:''}`;};
 function fillDongs(){const district=$('finderDistrict').value,select=$('finderDong');if(!district){select.innerHTML='<option value="">구·군을 먼저 선택</option>';select.value='';select.disabled=true;return;}const items=[...new Set(pharmacies.filter(p=>p.district===district).map(p=>p.dong).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));select.disabled=false;select.innerHTML='<option value="">전체 동</option>'+items.map(x=>`<option value="${E(x)}">${E(shortDong({dong:x,district}))}</option>`).join('');select.value='';}
 function initMap(){if(finderMap)return;finderMap=L.map('finderMap',{preferCanvas:true,zoomControl:true});if(L.tileLayer)L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(finderMap);L.geoJSON(D.boundaries,{style:{color:'#70869a',weight:1,fillColor:'#f5f7f9',fillOpacity:L.tileLayer ? .04 : .8}}).addTo(finderMap);finderMap.createPane('finderNormal');finderMap.getPane('finderNormal').style.zIndex=610;finderMap.createPane('finderPublic');finderMap.getPane('finderPublic').style.zIndex=650;normalRenderer=L.canvas({pane:'finderNormal',padding:.3});publicRenderer=L.canvas({pane:'finderPublic',padding:.3});markers=L.layerGroup().addTo(finderMap);finderMap.fitBounds(L.geoJSON(D.boundaries).getBounds());}
 function render(){if(!finderMap)return;const now=nowParts();$('finderNow').textContent=now.label;lastMinute=now.label;const q=$('finderSearch').value.trim().toLowerCase(),district=$('finderDistrict').value,dong=$('finderDong').value,day=+$('finderDay').value;visible=pharmacies.filter(p=>(!q||(p.name+' '+p.address).toLowerCase().includes(q))&&(!district||p.district===district)&&(!dong||p.dong===dong)&&(mode==='all'||mode==='public'&&p.designated||mode==='current'&&currentState(p,now)==='open'||mode==='night'&&nightState(p,day)==='open')).sort((a,b)=>Number(b.designated)-Number(a.designated)||a.name.localeCompare(b.name,'ko'));
  markers.clearLayers();visible.forEach((p,i)=>L.circleMarker([p.lat,p.lon],{renderer:p.designated?publicRenderer:normalRenderer,radius:p.designated?8:5,color:p.designated?'#fff':'#fff',weight:p.designated?2.5:1.5,fillColor:p.designated?'#7651c9':mode==='night'?'#c24e20':'#168473',fillOpacity:1}).bindPopup(()=>popup(p)).bindTooltip(E(p.name)).on('click',()=>select(i)).addTo(markers));
  $('finderNightMode').textContent=`${days[day]}요일 밤 22–01시 중 운영`;
  const qualifier=mode==='current'?'현재 영업 중':mode==='night'?`${days[day]}요일 (${selectedDate(day)}) 22–01시 중 운영`:mode==='public'?'공공심야약국':'등록 약국 전체';$('finderCount').textContent=`${visible.length.toLocaleString('ko-KR')}곳`;$('finderStatus').textContent=qualifier;
  page=Math.min(page,Math.max(0,Math.ceil(visible.length/pageSize)-1));
  $('finderList').innerHTML=visible.slice(page*pageSize,(page+1)*pageSize).map((p,i)=>{const info=pharmacyCurrentInfo(p,now),state=info.state,badge=mode==='current'?`<b class="state ${info.assumed?'assumed':'open'}">${info.assumed?'영업 가정':'시간표상 영업 중'}</b>`:mode==='night'?'<b class="state night">심야 운영</b>':p.designated?'<b class="state public">공공심야</b>':state==='open'?'<b class="state open">현재 영업</b>':state==='unknown'?'<b class="state unknown">시간 미상</b>':`<b class="state ${info.assumed?'assumed':'closed'}">${info.assumed?'휴무 가정':'시간표상 종료'}</b>`;return `<button class="finderitem" data-finder-i="${page*pageSize+i}"><span>${badge}${caution(p,mode==='night'?day:info.day)}<strong>${E(p.name)}</strong><small>${E(p.district)} ${E(shortDong(p))} · ${E(p.address)}</small><small>${mode==='night'?days[day]+'요일 ':days[nowParts().day]+'요일 '}${E(mode==='night'?nightHours(p,day):hours(p,now.day,now.date))}${p.phone?' · '+E(p.phone):''}</small>${mode!=='night'&&state==='open'?`<small class="finder-closing">${E(currentText(p,now))}</small>`:''}${exceptionNote(p)?`<small>${E(exceptionNote(p))}</small>`:''}</span><em>지도 보기</em></button>`;}).join('')||'<div class="finderempty">조건에 맞는 약국이 없습니다.<br>지역이나 필터를 바꿔보세요.</div>';
  const start=page*pageSize,end=Math.min(start+pageSize,visible.length);$('finderPage').textContent=visible.length?`${start+1}–${end} / ${visible.length.toLocaleString('ko-KR')}곳`:'0곳';$('finderPrev').disabled=page===0;$('finderNext').disabled=end>=visible.length;
 }
 function setPage(delta){page+=delta;render();$('finderList').scrollTop=0;}
 $('finderPrev').onclick=()=>setPage(-1);$('finderNext').onclick=()=>setPage(1);
 function resetRender(){page=0;render();$('finderList').scrollTop=0;}
 function select(i){const p=visible[i];if(!p)return;finderMap.setView([p.lat,p.lon],16);markers.eachLayer(l=>{const x=l.getLatLng();if(Math.abs(x.lat-p.lat)<1e-7&&Math.abs(x.lng-p.lon)<1e-7)l.openPopup();});}
 $('finderList').onclick=e=>{const b=e.target.closest('[data-finder-i]');if(b)select(+b.dataset.finderI);};$('finderSearch').oninput=resetRender;$('finderDistrict').onchange=()=>{fillDongs();resetRender();};$('finderDong').onchange=resetRender;$('finderDay').onchange=resetRender;$('finderMode').onclick=e=>{const b=e.target.closest('[data-mode]');if(!b)return;mode=b.dataset.mode;document.querySelectorAll('#finderMode button').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});resetRender();};fillDongs();
 return {open(){initMap();const t=nowParts();$('finderNow').textContent=t.label;render();setTimeout(()=>finderMap.invalidateSize(),0);opened=true;if(!timer)timer=setInterval(()=>{const t=nowParts();$('finderNow').textContent=t.label;if(lastMinute!==t.label){lastMinute=t.label;render();}},15000);},refresh(){if(opened)render();}};
}
