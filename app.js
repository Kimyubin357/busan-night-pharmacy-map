(async()=>{
'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=n=>Math.round(n).toLocaleString('ko-KR'),pct=(a,b)=>(b?100*a/b:0).toFixed(1)+'%';
try {
 const bytes=Uint8Array.from(atob($('payload').textContent.trim()),c=>c.charCodeAt(0));
 const D=await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
 const S={t:15,day:1,hour:23,mode:'api',view:'access',after:false,j:D.models.api.rankings['15'][0].j,dong:null};
 const map=L.map('map',{preferCanvas:true}),canvas=L.canvas({padding:.3}), colors={known:'#168473',unknown:'#d49a32',outside:'#a9b7c5',added:'#1765df'};
 const boundaries=L.geoJSON(D.boundaries,{style:{color:'#879bad',weight:1,fillColor:'#fff',fillOpacity:.7},onEachFeature:(f,l)=>l.on('click',()=>{S.dong=f.properties.i;renderDetails();})}).addTo(map);
 map.fitBounds(boundaries.getBounds());
 const dots=D.grids.lat.map((lat,i)=>L.circleMarker([lat,D.grids.lon[i]],{renderer:canvas,radius:2.5,stroke:false,fillOpacity:.8}).on('click',()=>{S.dong=D.grids.dong[i];renderDetails();}).addTo(map));
 const pharmacies=D.mapPharmacies||D.pharmacies;
 map.createPane('pharmacyPoints');map.getPane('pharmacyPoints').style.zIndex=450;
 const pharmacyCanvas=L.canvas({pane:'pharmacyPoints',padding:.3});
 const allPharmacies=L.layerGroup().addTo(map),publicPharmacies=L.layerGroup().addTo(map);
 const sourceLabel=s=>({observed:'조회 시간표',unknown:'오류·미상 (시간표 결측)',nmc_conflict_resolved:'자료 충돌 → NMC 조회값 적용',assumed_weekend_closed_original_blank:'원본·NMC 토·일 공란 + 화~금 기록 있음 → 주말 휴무 가정',assumed_monday_tue_fri_equal:'화~금 동일 시간으로 추정',assumed_sunday_closed_original_blank:'원본·API 공란 + 화~토 기록 있음 → 휴무 가정',assumed_public_sunday_policy:'공공심야 일요일 정책 운영 가정'}[s]||s);
 const clock=n=>`${String(Math.floor(n/60)%24).padStart(2,'0')}:${String(n%60).padStart(2,'0')}${n>=1440?' (익일)':''}`;
 const scheduleText=iv=>iv===null||iv===undefined?'오류·미상':iv.length?iv.map(([a,b])=>clock(a)+'–'+clock(b)).join(', '):'휴무 가정';
 const pharmacyInfo=p=>`<strong>${esc(p.name)}</strong><br>${p.designated?'공공심야약국 지정':'일반 약국'}<br>${esc(p.address)}${p.phone?'<br>전화 '+esc(p.phone):''}<br>월요일: ${esc(scheduleText(p.schedule?.[0]))}<br><small>${esc(sourceLabel(p.scheduleSources?.monday||'unknown'))}</small><br>토요일: ${esc(scheduleText(p.schedule?.[5]))}<br><small>${esc(sourceLabel(p.scheduleSources?.saturday||'unknown'))}</small><br>일요일: ${esc(scheduleText(p.schedule?.[6]))}<br><small>${esc(sourceLabel(p.scheduleSources?.sunday||'unknown'))}</small><br><small>${esc(p.source||'기존 부산 약국 목록')}<br>위치 표시 · 선택 시간의 영업 여부와 무관</small>`;
 pharmacies.forEach(p=>{
  L.circleMarker([p.lat,p.lon],{renderer:pharmacyCanvas,radius:5,color:'#fff',weight:1.2,fillColor:'#e05a24',fillOpacity:.95})
   .bindTooltip(esc(p.name)).bindPopup(pharmacyInfo(p)).addTo(allPharmacies);
  if(p.designated)L.marker([p.lat,p.lon],{zIndexOffset:100,icon:L.divIcon({className:'',html:'<span class="public-pin">+</span>',iconSize:[18,18],iconAnchor:[9,9]})})
   .bindTooltip(esc(p.name)+' · 공공심야약국').bindPopup(pharmacyInfo(p)).addTo(publicPharmacies);
 });
 $('allPharmacyCount').textContent=fmt(pharmacies.length)+'곳';
 $('publicPharmacyCount').textContent=fmt(pharmacies.filter(p=>p.designated).length)+'곳';
 function renderPharmacyLegend(){
  $('legend').insertAdjacentHTML('beforeend','<div id="pharmacyLegend" class="pharmacy-legend"></div>');
  $('pharmacyLegend').innerHTML=($('allPharmacies').checked?'<div><span class="swatch" style="background:#e05a24;border-radius:50%"></span>전체 약국</div>':'')+($('publicPharmacies').checked?'<div><span class="swatch" style="background:#7c3aed"></span>공공심야약국 (+)</div>':'')+`<div><span class="swatch" style="background:#1765df;border-radius:50%"></span>선택한 추가 지정 후보 (+)</div><p class="sub">월요일 동일시간 추정 · 주말 휴무 가정 포함<br>약국 위치: ${esc(D.meta.pharmacy_collected_at?.slice(0,10)||'2026-09-15')} 조회 기준</p>`;
 }
 function togglePharmacies(id,layer){$(id).onchange=e=>{if(e.target.checked)layer.addTo(map);else map.removeLayer(layer);$('pharmacyLegend')?.remove();renderPharmacyLegend();};}
 togglePharmacies('allPharmacies',allPharmacies);togglePharmacies('publicPharmacies',publicPharmacies);
 const pin=L.marker([0,0],{icon:L.divIcon({className:'',html:'<span class="candidate-pin">+</span>',iconSize:[24,24]})}).addTo(map);
 map.createPane('coverageReference');map.getPane('coverageReference').style.zIndex=430;
 const coverageReference=L.circle([0,0],{pane:'coverageReference',radius:1000,color:'#008574',weight:2,dashArray:'7 6',fill:false});
 let tiles=null,agg=[],tot=null;
 const demandStops=[[226,229,233],[243,179,163],[227,74,51],[127,0,0]];
 const demandColor=v=>{const x=Math.min(1,Math.max(0,Math.log1p(v)/Math.log(1001)))*(demandStops.length-1),i=Math.min(demandStops.length-2,Math.floor(x)),f=x-i;return `rgb(${demandStops[i].map((a,k)=>Math.round(a+(demandStops[i+1][k]-a)*f)).join(',')})`;};
 const coveredDemandColor=v=>{const f=Math.min(1,Math.max(0,Math.log1p(v)/Math.log(1001)));return `rgb(${[199,238,232].map((a,k)=>Math.round(a+([0,83,73][k]-a)*f)).join(',')})`;};
 const ranks=()=>D.models[S.mode].rankings[String(S.t)];
 const range=(a,b)=>fmt(a)+'–'+fmt(b)+'명';
 function renderList(){
  const q=$('search').value.trim(),rows=ranks().filter(r=>{let p=D.pharmacies[r.j];return(p.name+' '+p.district).includes(q);});
  $('ranking').innerHTML=rows.slice(0,100).map(r=>{const p=D.pharmacies[r.j];return `<button class="rankitem ${r.j===S.j?'active':''}" data-j="${r.j}"><span class="ranknum">${r.rank}</span><span class="rankbody"><strong>${esc(p.name)}</strong><small>${esc(p.district)}</small><div class="rankscore">${range(r.low,r.high)}</div><div class="spark"><span style="width:${100*r.low/(ranks()[0].low||1)}%"></span></div></span></button>`;}).join('')||'<p class="error">검색 결과가 없습니다.</p>';
  $('rankCount').textContent=`${fmt(rows.length)}곳 중 상위 ${Math.min(100,rows.length)}곳 표시 · 전체는 CSV`;
 }
 function bar(id,a,after){const parts=after?[[a.lo,colors.known],[a.al-a.lo,colors.added],[a.ah-a.al,colors.unknown]]:[[a.lo,colors.known],[a.hi-a.lo,colors.unknown]];$(id).innerHTML=parts.map(([v,c])=>`<span style="width:${a.w?100*v/a.w:0}%;background:${c}"></span>`).join('');}
 function renderDetails(){
  if(!tot)return;const a=S.dong===null?tot:agg[S.dong];$('areaTitle').textContent=S.dong===null?'부산 전체 · 선택 시간대':D.dongs[S.dong].name+' · 선택 시간대';
  $('areaDetail').innerHTML=`배분된 잠재수요 <strong>${fmt(a.w)}명</strong><br>추가 접근 하한–상한<br><strong>${range(a.gl,a.gh)}</strong>`;
  $('beforeText').textContent=pct(a.lo,a.w)+'–'+pct(a.hi,a.w);$('afterText').textContent=pct(a.al,a.w)+'–'+pct(a.ah,a.w);bar('beforeBar',a,false);bar('afterBar',a,true);
  boundaries.eachLayer(l=>l.setStyle({weight:l.feature.properties.i===S.dong?3:1,color:l.feature.properties.i===S.dong?'#1765df':'#879bad'}));
 }
 function render(){
  const hiIdx=[22,23,0].indexOf(S.hour),slot=(S.day-1)*3+hiIdx,model=D.models[S.mode],w=D.grids.weight[hiIdx],p=D.pharmacies[S.j],limit=S.t*60;
  const cl=new Uint8Array(w.length),ch=new Uint8Array(w.length);p.reach.forEach((i,k)=>{if(p.seconds[k]<=limit)cl[i]=ch[i]=1;});p.uncertain.forEach((i,k)=>{if(p.uncertainSeconds[k]<=limit)ch[i]=1;});
  const blank=()=>({w:0,lo:0,hi:0,al:0,ah:0,gl:0,gh:0});agg=D.dongs.map(blank);tot=blank();
  w.forEach((v,i)=>{const lo=model.known[slot][i]>=0&&model.known[slot][i]<=limit,hi=model.possible[slot][i]>=0&&model.possible[slot][i]<=limit,al=lo||!!cl[i],ah=hi||!!ch[i];const vals={w:v,lo:v*lo,hi:v*hi,al:v*al,ah:v*ah,gl:v*(cl[i]&&!hi),gh:v*(ch[i]&&!lo)};for(const k in vals){tot[k]+=vals[k];agg[D.grids.dong[i]][k]+=vals[k];}
   let c=S.after&&cl[i]&&!lo?colors.added:lo?colors.known:hi?colors.unknown:colors.outside;
   if(S.view==='demand')c=S.after&&cl[i]&&!hi?coveredDemandColor(v):S.after&&cl[i]&&!lo?colors.added:demandColor(v);
   if(S.view==='need')c=S.after&&cl[i]&&!hi?coveredDemandColor(v):S.after&&cl[i]&&!lo?colors.added:lo?'#dfe5eb':hi?'#d49a32':demandColor(v);
   dots[i].setStyle({fillColor:c,fillOpacity:S.view==='access'?.8:.95});
  });
  const showCoverage=S.view!=='access'&&S.after;
  coverageReference.setLatLng([p.lat,p.lon]).setRadius(S.t*4000/60);
  coverageReference.unbindTooltip().bindTooltip(`${esc(p.name)} · ${S.t}분 직선 참고범위<br>실제 도보 커버는 색이 바뀐 격자로 확인`);
  if(showCoverage){if(!map.hasLayer(coverageReference))coverageReference.addTo(map);}else if(map.hasLayer(coverageReference))map.removeLayer(coverageReference);
  $('kpiAccess').textContent=pct(tot.lo,tot.w);$('kpiAccessSub').textContent=`${fmt(tot.lo)}명 / 배분 수요 ${fmt(tot.w)}명`;$('kpiUnknown').textContent=pct(tot.hi-tot.lo,tot.w);$('kpiGain').textContent=range(tot.gl,tot.gh);
  const r=ranks().find(x=>x.j===S.j);$('candidateRank').textContent=`${r.rank}위 · ${S.t}분 기준`;$('candidateName').textContent=p.name;$('candidateAddress').textContent=p.address;$('candidatePhone').textContent=p.phone?'전화 '+p.phone:'';$('weeklyGain').textContent=range(r.low,r.high);
  $('eligibility').textContent=p.name.includes('한약국')?'명칭상 한약국입니다. 취급 의약품·지정 자격 확인이 필요하며 참여·인력은 미확인입니다.':'입지 효과 비교 후보입니다. 참여 의향·야간 약사 인력은 확인되지 않았습니다.';
  pin.setLatLng([p.lat,p.lon]).unbindTooltip().bindTooltip(esc(p.name)+'<br>추가 지정 비교 후보');
  $('affected').innerHTML=agg.map((a,i)=>({i,...a})).filter(a=>a.gh>0).sort((a,b)=>b.gh-a.gh).slice(0,5).map(a=>`<button data-dong="${a.i}">${esc(D.dongs[a.i].name)}</button>`).join('');
  $('legend').innerHTML=S.view==='demand'?'<strong>배분된 심야 잠재수요</strong><p>연한 회색: 적음 · 짙은 빨강: 많음</p><div style="height:12px;border-radius:3px;background:linear-gradient(to right,#e2e5e9,#f3b3a3,#e34a33,#7f0000)"></div><div style="justify-content:space-between"><span>0명</span><span>1,000명 이상</span></div><p class="sub">100m 격자·동 경계 조각의 대표점<br>색 기준은 모든 시각에 동일합니다.<br>실측 심야 격자인구가 아닙니다.</p>':`<strong>${S.t}분 보행 · ${S.after?'1곳 추가 후':'현재'}</strong>`+[[colors.known,'시간표·가정상 접근'],[colors.unknown,'정보 부족 · 판단 유보'],[colors.outside,'모형상 기준 밖'],...(S.after?[[colors.added,'후보 추가 후 모형상 접근']]:[])].map(([c,t])=>`<div><span class="swatch" style="background:${c}"></span>${t}</div>`).join('')+'<p class="sub">작은 점: 격자 대표점<br>도로 배경만 인터넷 연결 필요</p>';
  if(showCoverage)$('legend').insertAdjacentHTML('beforeend',`<div><span class="swatch" style="background:#00695c"></span>청록: 추가 접근 하한에 기여</div><div><span style="width:18px;border-top:2px dashed #008574;flex:none"></span>${S.t}분 직선 참고범위</div><p class="sub">청록의 진함도 수요량을 나타냅니다.<br>수요가 줄어든 것이 아닙니다.<br>파랑: 기존 미상에서 가정상 접근으로 변경. 하한 증가와 구분합니다.</p>`);
  if(S.view==='need')$('legend').innerHTML=`<strong>기존 공급으로 채우지 못한 수요</strong><div><span class="swatch" style="background:#a22"></span>빨강: 기준 밖 · 진할수록 수요 많음</div><div><span class="swatch" style="background:#d49a32"></span>황색: 정보 부족 · 판단 유보</div><div><span class="swatch" style="background:#dfe5eb"></span>회색: 이미 시간표·가정상 접근</div>${S.after?'<div><span class="swatch" style="background:#00695c"></span>청록: 추가 접근 하한에 기여</div><div><span class="swatch" style="background:#1765df"></span>파랑: 미상 → 가정상 접근</div>':''}<p class="sub">${S.t}분 · ${S.after?'후보 추가 후':'현재'}<br>점선 원은 직선 참고범위입니다.<br>실제 도보 범위는 색이 바뀐 격자입니다.</p>`;
  renderPharmacyLegend();
  const next=ranks().find(x=>x.rank>r.rank),gap=next&&r.rank===1?`${fmt(r.low-next.low)}명 (${(100*(r.low-next.low)/(r.low||1)).toFixed(2)}%)`:null;
  $('candidateReason').innerHTML=`<strong>왜 이 후보인가?</strong><p>① 생활인구로 잠재수요를 배분합니다.<br>② 기존 약국의 운영시간·도보 접근을 제외합니다.<br>③ 후보의 실제 도로 ${S.t}분권에 남은 수요를 더합니다.</p><p>선택 시간: 최소 <b>${fmt(tot.gl)}명</b><br>21개 시간대 평균: 최소 <b>${fmt(r.low)}명</b>${gap?`<br>2위와 차이: ${gap}`:''}</p>${r.rank===1&&D.sensitivity?'<p class="sub">보행속도·가정에 따른 순위 변화는<br>03 후보 비교에서 확인하세요.</p>':''}<button id="showUnmetDemand">미충족 수요와 추가 범위 보기</button>`;
  $('showUnmetDemand').onclick=()=>{S.view='need';S.after=true;$('allPharmacies').checked=false;map.removeLayer(allPharmacies);document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===S.view));render();focus();};
  document.querySelectorAll('[data-after]').forEach(b=>b.classList.toggle('active',Boolean(+b.dataset.after)===S.after));renderList();renderDetails();
 }
 function focus(){const p=D.pharmacies[S.j];map.setView([p.lat,p.lon],14);}
 $('ranking').onclick=e=>{const b=e.target.closest('[data-j]');if(b){S.j=+b.dataset.j;S.dong=null;S.after=true;render();focus();}};
 $('affected').onclick=e=>{const b=e.target.closest('[data-dong]');if(b){S.dong=+b.dataset.dong;renderDetails();boundaries.eachLayer(l=>{if(l.feature.properties.i===S.dong)map.fitBounds(l.getBounds());});}};
 $('search').oninput=renderList;$('day').onchange=e=>{S.day=+e.target.value;render();};$('hour').onchange=e=>{S.hour=+e.target.value;render();};$('source').onchange=e=>{S.mode=e.target.value;S.j=ranks()[0].j;render();};
 $('threshold').onclick=e=>{if(e.target.dataset.t){S.t=+e.target.dataset.t;S.j=ranks()[0].j;document.querySelectorAll('[data-t]').forEach(b=>b.classList.toggle('active',+b.dataset.t===S.t));render();}};
 $('mapView').onclick=e=>{if(e.target.dataset.view){S.view=e.target.dataset.view;document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===S.view));render();}};
 $('beforeAfter').onclick=e=>{if(e.target.dataset.after!==undefined){S.after=!!+e.target.dataset.after;render();}};
 $('roads').onchange=e=>{if(e.target.checked){tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(map);boundaries.setStyle({fillOpacity:.08});}else{if(tiles)map.removeLayer(tiles);boundaries.setStyle({fillOpacity:.7});}};
 map.attributionControl.addAttribution('SGIS 2025 경계 · © OpenStreetMap contributors');$('resetMap').onclick=()=>{S.dong=null;map.fitBounds(boundaries.getBounds());renderDetails();};$('focusCandidate').onclick=focus;
 $('methodBtn').onclick=()=>$('method').showModal();$('closeMethod').onclick=()=>$('method').close();
 $('downloadCsv').onclick=()=>{const quote=x=>'"'+String(x).replace(/"/g,'""')+'"';const rows=[['순위','약국ID','약국명','구군','주소','도보기준_분','운영시나리오','21시간대평균_추가수요하한','21시간대평균_추가수요상한'],...ranks().map(r=>{let p=D.pharmacies[r.j];return[r.rank,p.id,p.name,p.district,p.address,S.t,S.mode,r.low,r.high];})];const url=URL.createObjectURL(new Blob(['\ufeff'+rows.map(r=>r.map(quote).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`busan-v3-${S.mode}-${S.t}min.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 render();mountReport(D,map,(j,mode,t)=>{S.j=j;S.mode=mode;S.t=t;S.after=true;S.dong=null;$('source').value=mode;document.querySelectorAll('[data-t]').forEach(b=>b.classList.toggle('active',+b.dataset.t===t));render();focus();});$('loading').remove();
}catch(e){$('loading').innerHTML='<div class="error"><h2>데이터를 불러오지 못했습니다.</h2><p>최신 Chrome·Edge·Safari에서 다시 열어주세요.</p><pre>'+esc(e.message)+'</pre></div>';console.error(e);}
})();
