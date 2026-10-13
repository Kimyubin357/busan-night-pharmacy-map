"""NMC 시간표·SGIS 격자·OSM 보행망으로 v3의 수치와 화면 입력을 생성합니다.
후보는 하나씩 독립 지정(매일22~01시)하며, 21개 시간대 평균 추가 접근 수요를
평가합니다. 확정 개선 하한과 가능 개선 상한을 섞지 않습니다.
"""
from pathlib import Path
import sys,json,gzip,hashlib
import numpy as np,pandas as pd
from pyproj import Transformer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sgis_population_weights import reader
from shapely.geometry import shape,mapping
from shapely.ops import transform
from schedule_assumptions import build_schedules
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'dashboard_v3';UP=ROOT/'team2/update_20260915'
SLOTS=[(d,h) for d in range(1,8) for h in [22,23,0]]
def main():
 ctx=__import__('pipeline_context').context()
 source=__import__('pipeline_context').processed_source()
 ph=pd.read_csv(source/'pharmacy_master.csv').fillna('');grid=pd.read_csv(OUT/'grid_nodes_routing.csv',dtype={'dong_code':str});dongs=pd.read_csv(UP/'sgis_dong_crosswalk.csv',dtype={'dong_code':str,'sgis_code':str});dongids=list(dongs.dong_code);dmap={k:i for i,k in enumerate(dongids)};di=grid.dong_code.map(dmap).to_numpy();N=len(grid)
 hourly=pd.read_csv(UP/'sgis_grid_hourly_demand.csv');weights=np.array([hourly[hourly.hour.eq(h)].set_index('grid_node_id').reindex(grid.grid_node_id).allocated_total_population_proxy.to_numpy() for h in [22,23,0]])
 dist=np.load(OUT/'grid_distance_m.npy',mmap_mode='r');unc=np.load(OUT/'grid_route_uncertain.npy')
 project=Transformer.from_crs(4326,5179,always_xy=True);px,py=project.transform(ph.longitude.to_numpy(),ph.latitude.to_numpy())
 weekly,schedule_audit,schedule_summary=build_schedules()
 conflicts=pd.read_csv(UP/'nmc_hours_comparison.csv');conflicts=conflicts[conflicts.conflict & ~conflicts.applied]
 policy=pd.read_csv(ROOT/'team2/outputs/public_policy_hours.csv').set_index('pharmacy_id')
 paths=[];maybe=[];routeUnknown=np.full(N,np.inf)
 for j,p in ph.iterrows():
  idx=np.flatnonzero(np.isfinite(dist[:,j]));mins=dist[idx,j].astype(float)/ (4000/60);paths.append((idx,mins))
  direct=np.hypot(grid.x_5179.to_numpy()-px[j],grid.y_5179.to_numpy()-py[j]);ix=np.flatnonzero(unc[:,j]&~np.isfinite(dist[:,j])&(direct<=ctx['distance_limit_m']));mi=direct[ix]/(4000/60);maybe.append((ix,mi));np.minimum.at(routeUnknown,ix,mi)
 public=ph.public_designation_status.eq('matched_designated').to_numpy();candidates=np.flatnonzero(~public)
 models={};rankcsv=[]
 for mode in ['api','policy']:
  known=np.full((21,N),np.inf);possible=np.full((21,N),np.inf)
  for slot,(day,hour) in enumerate(SLOTS):
   possible[slot]=routeUnknown.copy()
   for j,p in ph.iterrows():
    idx,mins=paths[j]
    if not len(idx):continue
    w=weekly.get(p.pharmacy_id,{})
    if mode=='policy' and p.pharmacy_id in policy.index:
     pol=policy.loc[p.pharmacy_id];w={d:[(pol.start_minute,pol.end_minute)] for d in range(1,8)}
    arr=hour*60+mins;opened=np.zeros(len(idx),bool);unknown=False
    for shift in [0,-1]:
     iv=w.get((day-1+shift)%7+1)
     if iv is None:unknown=True;continue
     for a,b in iv:opened|=(arr>=a+shift*1440)&(arr<b+shift*1440)
    np.minimum.at(known[slot],idx[opened],mins[opened]);np.minimum.at(possible[slot],idx[opened|unknown],mins[opened|unknown])
   print(mode,'slot',slot,flush=True)
  ranks={};stats={}
  W=weights[np.arange(21)%3]
  for threshold in [5,10,15]:
   lo=known<=threshold;hi=possible<=threshold
   needLow=(W*(~hi)).mean(axis=0);needHigh=(W*(~lo)).mean(axis=0)
   ranking=[]
   for j in candidates:
    ix,mi=paths[j];ix=ix[mi<=threshold];ux,um=maybe[j];ux=ux[um<=threshold]
    gl=float(needLow[ix].sum());gu=float(needHigh[ix].sum()+needHigh[ux].sum())
    ranking.append(dict(j=int(j),low=gl,high=gu))
   ranking.sort(key=lambda r:(-r['low'],-r['high'],ph.iloc[r['j']].pharmacy_id))
   last=None;rank=0
   for pos,r in enumerate(ranking):
    if last is None or not np.isclose(r['low'],last,rtol=0,atol=1e-6):rank=pos+1;last=r['low']
    r['rank']=rank;rankcsv.append(dict(mode=mode,threshold=threshold,pharmacy_id=ph.iloc[r['j']].pharmacy_id,name=ph.iloc[r['j']]['name'],district=ph.iloc[r['j']].district,**r))
   ranks[str(threshold)]=ranking
   stats[str(threshold)]=dict(total=float(W.sum()/21),lower=float((W*lo).sum()/21),upper=float((W*hi).sum()/21))
  # 접근 시간 배열은 초 단위 소수로 보존. 미확보는 -1로 표시하여 0분과 구분합니다.
  pack=lambda a:np.where(np.isfinite(a),np.round(a*60,5),-1).tolist()
  models[mode]=dict(known=pack(known),possible=pack(possible),rankings=ranks,summary=stats)
 pd.DataFrame(rankcsv).to_csv(OUT/'candidate_rankings_v3.csv',index=False)
 # 출처가 검증된 SGIS 행정동 경계로 v2의 출처 미기재 경계를 교체합니다.
 inv=Transformer.from_crs(5179,4326,always_xy=True);sgis_to_index={r.sgis_code:i for i,r in dongs.iterrows()};features=[]
 for r in reader('sgis_dong.zip','2025_2Q').iterShapeRecords():
  code=r.record['ADM_CD']
  if code in sgis_to_index:
   geom=transform(inv.transform,shape(r.shape.__geo_interface__).simplify(12,preserve_topology=True));features.append(dict(type='Feature',properties={'i':sgis_to_index[code]},geometry=mapping(geom)))
 pharmacies=[]
 for j,p in ph.iterrows():
  idx,mins=paths[j];ui,um=maybe[j]
  schedule=[]
  for d in range(1,8):
   iv=weekly.get(p.pharmacy_id,{}).get(d);schedule.append(iv)
  pharmacies.append(dict(id=p.pharmacy_id,name=p['name'],district=p.district,address=p.address,phone=p.phone,lat=p.latitude,lon=p.longitude,designated=bool(public[j]),reach=idx.tolist(),seconds=np.round(mins*60,5).tolist(),uncertain=ui.tolist(),uncertainSeconds=np.round(um*60,5).tolist(),schedule=schedule,scheduleSources={'monday':schedule_audit[p.pharmacy_id]['monday_source'],'sunday':schedule_audit[p.pharmacy_id]['sunday_source'],'saturday':schedule_audit[p.pharmacy_id]['saturday_source']}))
 data=dict(meta={'title':'부산 심야약국 접근성','version':3,'population_month':ctx['population_month'][:4]+'-'+ctx['population_month'][4:],'grid_year':ctx['grid_year'],'boundary_date':ctx['boundary_date'],'osm_date':ctx['osm_date'],'exception_scope':'명확한 비고 휴게구간을 차감합니다. 월별 정기휴무가 있는 요일은 날짜 없는 주간 분석에서 미상으로 두며, 시민 화면은 실제 날짜로 판정합니다. 정책 시나리오는 매일 22–01시 운영 가정입니다.','nmc_identity_review_count':json.loads((UP/'nmc_update_summary.json').read_text())['identity_review'],'nmc_rows':len(pd.read_csv(UP/'nmc_busan_pharmacies.csv')),'pharmacy_collected_at':json.loads((UP/'raw/nmc'/json.loads((ROOT/'reports/latest_run.json').read_text())['run_id']/'manifest.json').read_text())['collected_at'],'input_manifest':ctx['inputs'],'monday_known':sum(weekly[pid][1] is not None for pid in ph.pharmacy_id),'monday_unknown':sum(weekly[pid][1] is None for pid in ph.pharmacy_id),'schedule_assumptions':schedule_summary,'conflicting_days':len(conflicts),'unique_grid_count':int(grid.grid_id.nunique()),'grid_count':N,'pharmacy_count':len(ph),'designated_count':int(public.sum()),'route_quality':json.loads((OUT/'grid_route_quality.json').read_text())},
  dongs=[dict(code=r.dong_code,name=r.dong_name,district=r.district,age60plus=r.age60plus_share_all_day) for r in dongs.itertuples()],boundaries={'type':'FeatureCollection','features':features},
  grids={'lat':grid.latitude.round(7).tolist(),'lon':grid.longitude.round(7).tolist(),'dong':di.tolist(),'weight':np.round(weights,6).tolist(),'snapAccepted':grid.route_snap_accepted.tolist()},pharmacies=pharmacies,models=models)
 payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode();(OUT/'data.json.gz').write_bytes(gzip.compress(payload));(OUT/'model_summary.json').write_text(json.dumps({m:models[m]['summary'] for m in models},indent=2));print('payload',len(payload),'gzip',len(gzip.compress(payload)),flush=True)
if __name__=='__main__':main()
