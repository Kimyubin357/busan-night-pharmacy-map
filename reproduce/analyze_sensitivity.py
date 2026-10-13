"""기준 모형과 단일 가정 변경의 후보 순위를 재계산합니다. 통계적 신뢰도가 아닙니다."""
from pathlib import Path
import gzip,json,copy
import numpy as np
import pandas as pd
from pyproj import Transformer
from pipeline_context import ROOT, context

CASES=[('baseline','기준: 4km/h · 원래 가정',4,False,False),
       ('speed3','보행속도 3km/h',3,False,False),
       ('speed5','보행속도 5km/h',5,False,False),
       ('sunday_unknown','일요일 일반약국 휴무 가정 → 미상',4,True,False),
       ('uniform','거주인구 비중 → 격자 면적 비중',4,False,True)]

def evaluate(data,speed,unknown_sunday,uniform,mode):
    ph=data['pharmacies'];N=len(data['grids']['lat']);base=np.asarray(data['grids']['weight'],float)
    W=base.copy();dong=np.asarray(data['grids']['dong'],int)
    if uniform:
        grid=pd.read_csv(ROOT/'dashboard_v3/grid_nodes_routing.csv')
        mass=grid.intersection_area_fraction.to_numpy(float)
        totals=np.bincount(dong,weights=mass,minlength=len(data['dongs']))
        share=mass/totals[dong]
        for h in range(3):W[h]=share*np.bincount(dong,weights=base[h],minlength=len(totals))[dong]
        for h in range(3):assert np.allclose(np.bincount(dong,weights=W[h]),np.bincount(dong,weights=base[h]))
    W=W[np.arange(21)%3]
    schedules={p['id']:{d+1:copy.deepcopy(v) for d,v in enumerate(p['schedule'])} for p in ph}
    if unknown_sunday:
        for p in ph:
            if not p['designated'] and str(p['scheduleSources']['sunday']).startswith('assumed_'):
                schedules[p['id']][7]=None
    policy=pd.read_csv(ROOT/'team2/outputs/public_policy_hours.csv').set_index('pharmacy_id')
    paths=[];maybe=[];route_unknown=np.full(N,np.inf)
    transformer=Transformer.from_crs(4326,5179,always_xy=True)
    gx,gy=transformer.transform(data['grids']['lon'],data['grids']['lat'])
    for p in ph:
        ix=np.asarray(p['reach'],int);mi=np.asarray(p['seconds'],float)/60*4/speed;paths.append((ix,mi))
        ui=np.asarray(p['uncertain'],int);um=np.asarray(p['uncertainSeconds'],float)/60*4/speed;maybe.append((ui,um))
        np.minimum.at(route_unknown,ui,um)
    known=np.full((21,N),np.inf);possible=np.full((21,N),np.inf)
    for slot,(day,hour) in enumerate((d,h) for d in range(1,8) for h in [22,23,0]):
        possible[slot]=route_unknown.copy()
        for j,p in enumerate(ph):
            ix,mins=paths[j]
            if not len(ix):continue
            w=schedules[p['id']]
            if mode=='policy' and p['id'] in policy.index:
                row=policy.loc[p['id']];w={d:[[float(row.start_minute),float(row.end_minute)]] for d in range(1,8)}
            arr=hour*60+mins;opened=np.zeros(len(ix),bool);unknown=False
            for shift in [0,-1]:
                iv=w.get((day-1+shift)%7+1)
                if iv is None:unknown=True;continue
                for a,b in iv:opened|=(arr>=a+shift*1440)&(arr<b+shift*1440)
            np.minimum.at(known[slot],ix[opened],mins[opened]);np.minimum.at(possible[slot],ix[opened|unknown],mins[opened|unknown])
    result={}
    for threshold in [5,10,15]:
        lo=known<=threshold;hi=possible<=threshold
        need_low=(W*(~hi)).mean(axis=0);need_high=(W*(~lo)).mean(axis=0);rows=[]
        for j,p in enumerate(ph):
            if p['designated']:continue
            ix,mi=paths[j];ix=ix[mi<=threshold];ui,um=maybe[j];ui=ui[um<=threshold]
            rows.append({'j':j,'low':float(need_low[ix].sum()),'high':float(need_high[ix].sum()+need_high[ui].sum())})
        rows.sort(key=lambda r:(-r['low'],-r['high'],ph[r['j']]['id']))
        last=None;rank=0
        for pos,row in enumerate(rows):
            if last is None or not np.isclose(last,row['low'],rtol=0,atol=1e-6):rank=pos+1;last=row['low']
            row['rank']=rank
        result[str(threshold)]={'rows':rows,'lower':float((W*lo).sum()/21),'upper':float((W*hi).sum()/21),'total':float(W.sum()/21)}
    return result

def main():
    ctx=context()
    if ctx['distance_limit_m']<1250:raise ValueError('5km/h·15분 검증에는 거리행렬을 최소 1250m까지 계산해야 합니다.')
    data=json.loads(gzip.decompress((ROOT/'dashboard_v3/data.json.gz').read_bytes()))
    models={};csvrows=[];baseline_error=0
    for mode in ['api','policy']:
        views={str(t):[] for t in [5,10,15]}
        for key,label,speed,sunday,uniform in CASES:
            computed=evaluate(data,speed,sunday,uniform,mode)
            for t,value in computed.items():
                leader=data['models'][mode]['rankings'][t][0];byj={r['j']:r for r in value['rows']};lead=byj[leader['j']];winner=value['rows'][0]
                if key=='baseline':
                    ref=data['models'][mode]
                    differences=[abs(value[s]-ref['summary'][t][s]) for s in ['lower','upper','total']]
                    for row in ref['rankings'][t]:differences.extend(abs(row[s]-byj[row['j']][s]) for s in ['low','high'])
                    baseline_error=max(baseline_error,max(differences));assert max(differences)<.1
                top=[{**r,'id':data['pharmacies'][r['j']]['id'],'name':data['pharmacies'][r['j']]['name']} for r in value['rows'][:10]]
                views[t].append({'id':key,'label':label,'speed_kmh':speed,'baseLeaderRank':lead['rank'],'baseLeaderLow':lead['low'],'winner':top[0],'top10':top})
                csvrows.extend({'mode':mode,'threshold':int(t),'scenario':key,**r,'pharmacy_id':data['pharmacies'][r['j']]['id'],'name':data['pharmacies'][r['j']]['name']} for r in value['rows'])
            print('sensitivity',mode,key,flush=True)
        models[mode]=views
    output={'description':'한 번에 하나의 가정만 변경한 순위 비교. 확률·신뢰구간·현장 검증이 아닙니다.',
            'uniform_scope':'SGIS 인구가 있는 분석 격자 조각 안에서 면적 비중으로 배분하며 동별 시간대 총량을 보존합니다.',
            'baseline_max_error':baseline_error,'scenario_count':len(CASES),'models':models}
    (ROOT/'sensitivity_results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    pd.DataFrame(csvrows).to_csv(ROOT/'sensitivity_rankings.csv',index=False)
    # 현장 검증으로 오인하지 않도록 체크리스트는 명시적으로 미실시 상태로 생성합니다.
    records=[]
    for r in data['models']['api']['rankings']['15'][:5]:
        p=data['pharmacies'][r['j']];ix=np.asarray(p['reach'],int);seconds=np.asarray(p['seconds']);eligible=ix[seconds<=900]
        weight=np.asarray(data['grids']['weight']).mean(axis=0)
        for i in sorted(eligible,key=lambda i:-weight[i])[:3]:
            records.append({'pharmacy_id':p['id'],'name':p['name'],'phone':p['phone'],'grid_index':int(i),'origin_lat':data['grids']['lat'][i],'origin_lon':data['grids']['lon'][i],'destination_lat':p['lat'],'destination_lon':p['lon'],'walking_route_field_check':'미실시','opening_hours_phone_check':'미실시','checked_at':'','evidence':''})
    pd.DataFrame(records).to_csv(ROOT/'field_validation_plan.csv',index=False)
    print('PASS baseline max error',baseline_error,flush=True)

if __name__=='__main__':main()
