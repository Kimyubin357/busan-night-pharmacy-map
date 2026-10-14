// 브라우저 실행 대신 보고서 생성 함수와 집계값을 검사합니다.
const fs=require('fs'),vm=require('vm'),zlib=require('zlib'),assert=require('assert');
const D=JSON.parse(zlib.gunzipSync(fs.readFileSync(__dirname+'/dashboard_data.json.gz')));
const els=new Map();function el(id){if(!els.has(id))els.set(id,{id,innerHTML:'',textContent:'',dataset:{},setAttribute(){}});return els.get(id);}
const ctx={mountPharmacyFinder:()=>({open(){}}),document:{getElementById:el,querySelectorAll:()=>[]},console,setTimeout:()=>{},window:{print(){},addEventListener(){}},L:{}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/report.js','utf8'),ctx);ctx.mountReport(D,()=>{});
for(const id of ['thresholdChart','weekChart','candidateChart','candidateThresholdChart']){assert(el(id).innerHTML.includes('<svg'));assert(!/NaN|undefined/.test(el(id).innerHTML));fs.writeFileSync(__dirname+'/'+id+'.svg',el(id).innerHTML);}
assert(el('comparisonTable').innerHTML.includes(D.pharmacies[D.models.api.rankings['15'][0].j].name));
for(const t of [5,10,15]){el('compareT').onchange({target:{value:String(t)}});assert(el('candidateChart').innerHTML.includes(t+'분'));}
el('compareMode').onchange({target:{value:'policy'}});assert(el('comparisonTable').innerHTML.includes(D.pharmacies[D.models.policy.rankings['15'][0].j].name));
console.log('Report generation: 4 charts, 3 thresholds, 2 operating scenarios passed.');

// 웹용 요약 데이터도 전체 payload와 동일한 네 차트를 생성해야 합니다.
const manifest=JSON.parse(fs.readFileSync(__dirname+'/build_manifest.json','utf8'));
if(manifest.resources){
 const ids=['thresholdChart','weekChart','candidateChart','candidateThresholdChart','overviewPane','comparePane','evidencePane','summaryStats'];
 ctx.mountReport(D,()=>{});const before=ids.map(id=>el(id).innerHTML);
 const split=JSON.parse(zlib.gunzipSync(fs.readFileSync(__dirname+'/dist/'+manifest.resources.data.reports)));
 ctx.mountReport(split,()=>{});before.forEach((html,i)=>assert.equal(el(ids[i]).innerHTML,html,ids[i]));
 console.log('Split report data: all charts, report panes and counts match the original payload.');
}
