// 자정과 종료 경계 및 정책 시간 중첩에 대한 회귀 검사.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={};vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/finder.js','utf8'),ctx);
const calc=(schedule,day=6)=>JSON.parse(JSON.stringify(ctx.pharmacyNightIntervals(schedule,day)));
let s=Array.from({length:7},()=>[]);
s[6]=[[540,1320]];assert.deepStrictEqual(calc(s),[]); // 22시 폐점은 영업에 포함하지 않음
s[6]=[[540,1380]];assert.deepStrictEqual(calc(s),[[1320,1380]]); // 23시까지만 영업
s[6]=[[540,1440],[1320,1500]];s[0]=[[0,60]];
assert.deepStrictEqual(calc(s),[[1320,1500]]); // 정책·원본·익일 시간이 겹쳐도 한 구간
s[6]=[];s[0]=[[30,120]];assert.deepStrictEqual(calc(s),[[1470,1500]]); // 월요일 00:30부터 이어지는 일요일 밤
s[0]=[[60,120]];assert.deepStrictEqual(calc(s),[]); // 익일 01시 시작은 검색구간 밖
s[6]=null;s[0]=[];assert.deepStrictEqual(calc(s),[]); // 결측으로 영업을 만들어내지 않음
console.log('Finder time boundaries: 6 scenarios passed.');
const current=(p,n)=>JSON.parse(JSON.stringify(ctx.pharmacyCurrentInfo(p,n)));
const p={schedule:Array.from({length:7},()=>[]),scheduleSources:{monday:'observed',sunday:'assumed_sunday_closed_original_blank'}};
p.schedule[0]=[[510,1170],[1320,1500]];
assert.equal(current(p,{date:'2026-10-12',day:0,minutes:1200}).state,'closed');
assert.equal(current(p,{date:'2026-10-12',day:0,minutes:1320}).state,'open');
let info=current(p,{date:'2026-10-13',day:1,minutes:30});assert.equal(info.state,'open');assert.equal(info.carry,true);assert.equal(info.end,60);assert.equal(info.remaining,30);
assert.equal(current(p,{date:'2026-10-13',day:1,minutes:60}).state,'closed');
p.schedule[6]=[[540,1320]];p.scheduleExceptions={recurring:[{day:6,weeks:[1,3],kind:'closed'}]};
assert.equal(current(p,{date:'2026-10-04',day:6,minutes:600}).state,'closed');
assert.equal(current(p,{date:'2026-10-11',day:6,minutes:600}).state,'open');
p.scheduleExceptions={recurring:[{day:6,weeks:[1,3],kind:'open_only'}]};p.schedule[6]=[];
assert.equal(current(p,{date:'2026-10-04',day:6,minutes:600}).state,'unknown');
assert.equal(current(p,{date:'2026-10-11',day:6,minutes:600}).state,'closed');
assert.equal(ctx.pharmacyAssumption(p,6),true);
console.log('Break, carry-over, end boundary, monthly closure and assumption: 9 assertions passed.');
