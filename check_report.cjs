// 브라우저 실행 대신 보고서 생성 함수와 집계값을 검사합니다.
const fs=require('fs'),vm=require('vm'),zlib=require('zlib'),assert=require('assert');
const D=JSON.parse(zlib.gunzipSync(fs.readFileSync(__dirname+'/dashboard_data.json.gz')));
const els=new Map();function el(id){if(!els.has(id))els.set(id,{id,innerHTML:'',textContent:'',dataset:{},setAttribute(){}});return els.get(id);}
const ctx={mountPharmacyFinder:()=>({open(){}}),document:{getElementById:el,querySelectorAll:()=>[]},console,setTimeout:()=>{},window:{print(){},addEventListener(){}},L:{}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/report.js','utf8'),ctx);ctx.mountReport(D,{},()=>{});
for(const id of ['thresholdChart','weekChart','candidateChart','candidateThresholdChart']){assert(el(id).innerHTML.includes('<svg'));assert(!/NaN|undefined/.test(el(id).innerHTML));fs.writeFileSync(__dirname+'/'+id+'.svg',el(id).innerHTML);}
assert(el('comparisonTable').innerHTML.includes(D.pharmacies[D.models.api.rankings['15'][0].j].name));
for(const t of [5,10,15]){el('compareT').onchange({target:{value:String(t)}});assert(el('candidateChart').innerHTML.includes(t+'분'));}
el('compareMode').onchange({target:{value:'policy'}});assert(el('comparisonTable').innerHTML.includes(D.pharmacies[D.models.policy.rankings['15'][0].j].name));
console.log('Report generation: 4 charts, 3 thresholds, 2 operating scenarios passed.');
