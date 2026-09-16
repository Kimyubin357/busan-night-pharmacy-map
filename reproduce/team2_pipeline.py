"""팀원 2 1단계: 수요 지표·대표지점·공급 시나리오·직선거리 예비 분석.

실행: python team2_pipeline.py
실제 도보시간은 계산하지 않습니다. 도로 경로가 없는 단계에서 직선거리를
도보 15분권으로 바꾸거나 대표지점의 결과를 동 전체 주민의 실제 접근률로
표현하지 않습니다. 이후 경로 CSV/API를 연결할 수 있는 입력 파일을 만듭니다.
"""
from pathlib import Path
import hashlib,json,re
from datetime import datetime,timezone
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'team2'; INPUT=BASE/'inputs'; OUTPUT=BASE/'outputs'; REPORT=BASE/'reports'


def normalize_dong(value):
    """구군+행정동 조합으로 비교. 법정동을 행정동으로 바꾸는 함수가 아닙니다."""
    return re.sub(r'[\s제·.,]','',str(value))


def haversine_m(lat1,lon1,lat2,lon2):
    """WGS84 경위도의 구면 직선거리 근사. 도로거리/도보시간과 다릅니다."""
    a,b=np.radians(lat1),np.radians(lat2)
    dlat=b-a; dlon=np.radians(lon2)-np.radians(lon1)
    h=np.sin(dlat/2)**2+np.cos(a)*np.cos(b)*np.sin(dlon/2)**2
    return 6371008.8*2*np.arcsin(np.sqrt(np.clip(h,0,1)))


def save(name,df):
    OUTPUT.mkdir(parents=True,exist_ok=True); REPORT.mkdir(parents=True,exist_ok=True)
    df.to_csv(OUTPUT/(name+'.csv'),index=False,encoding='utf-8-sig')
    preview=f'\n[{name}] shape={df.shape}\ncolumns={list(df.columns)}\nmissing={df.isna().sum().to_dict()}\n'+df.head().to_string(index=False)+'\n'
    print(preview,flush=True)
    with (REPORT/'head_preview.txt').open('a',encoding='utf-8') as f:f.write(preview)


def demand_tables(source):
    """수요는 잠재 노출 인구로 정의합니다. 실제 의약품 구매량을 추정하지 않습니다."""
    night=pd.read_csv(source/'living_population_night_latest.csv',dtype={'month':'string','dong_code':'string'})
    hourly=pd.read_csv(source/'living_population_hourly.csv',dtype={'month':'string','dong_code':'string'})
    # 행안부 2025-01-01 변경표: 강서구 26440 + 신호동 59000.
    # 법정동 11700과 구분합니다. 수요값은 바꾸지 않고 비어 있던 명칭만 복원합니다.
    for frame in (night, hourly):
        mask=frame.dong_code.eq('2644059000')
        frame.loc[mask,'dong_name']='강서구 신호동'
    latest=night.month.max()
    hourly=hourly[hourly.month.eq(latest)&hourly.hour.isin([0,22,23])].copy()
    night=night.rename(columns={'night_mean_total_population_proxy':'night_population_proxy'})
    night['night_visitor_share']=np.where(night.night_population_proxy>0,night.night_mean_visitor/night.night_population_proxy,np.nan)
    # 연령 파일은 시간대 차원이 없습니다. 아래 연령 비율은 심야 연령별 인구가 아닙니다.
    age=pd.read_excel(INPUT/'PD_LP00002.xlsx',dtype='string')
    age=age.rename(columns={'기준년월':'month','행정동코드':'dong_code','행정동명':'dong_name','나이대':'age_band',
        '평균주거인구수':'resident','평균직장인구수':'worker','평균방문인구수':'visitor'})
    if age.duplicated(['month','dong_code','age_band']).any():raise ValueError('연령 생활인구 중복키')
    for c in ['resident','worker','visitor']:
        age[c]=pd.to_numeric(age[c],errors='raise')
        if not np.isfinite(age[c]).all() or (age[c]<0).any():raise ValueError('연령 인구 비정상값')
    age=age[age.month.eq(latest)].copy()
    if age.empty:raise ValueError('시간 생활인구와 같은 최신 월의 연령 자료 없음')
    age['population_proxy']=age[['resident','worker','visitor']].sum(axis=1)
    pivot=age.pivot(index='dong_code',columns='age_band',values='population_proxy')
    expected={'20대미만','20대','30대','40대','50대','60대이상'}
    if set(pivot)!=expected or pivot.isna().any().any():raise ValueError('연령구간/완비성 확인 필요')
    pivot['age60plus_share_all_day']=pivot['60대이상']/pivot[list(expected)].sum(axis=1).replace(0,np.nan)
    night=night.merge(pivot[['age60plus_share_all_day']],on='dong_code',how='left',validate='one_to_one')
    night['demand_rank']=night.night_population_proxy.rank(method='min',ascending=False).astype(int)
    night['metric_note']='월평균 22·23·00시 잠재 노출 인구. 연령 비율은 전시간대 별도 보조지표.'
    save('demand_by_dong',night.sort_values(['demand_rank','dong_code']))
    save('demand_by_hour',hourly)
    save('age_profile_latest',age)
    return night,hourly


def representative_points(night):
    """행정동별 주소점 좌표 중앙값에 가장 가까운 실제 주소점을 대표지점으로 선택.

    각 주소에 동일 인구를 배분하지 않습니다. 중앙값은 인구 가중 중심이 아니며
    동 전체를 단일 점으로 표현하는 1차 모형용 위치입니다. 격자 인구가 들어오면
    이 점을 인구 가중 복수 지점으로 대체해야 합니다.
    """
    addresses=pd.read_csv(INPUT/'15028854.csv',dtype='string',encoding='cp949')
    addresses['district']=addresses['시군구명'].str.strip()
    addresses['admin_name']=addresses['관할행정동'].str.strip()
    addresses['join_key']=(addresses.district.fillna('')+addresses.admin_name.fillna('')).map(normalize_dong)
    codes=night[['dong_code','dong_name','district']].copy()
    codes['join_key']=codes.dong_name.map(normalize_dong)
    if codes.join_key.duplicated().any():raise ValueError('정규화 행정동명 중복: 수동 검토 필요')
    # 신호동으로 보이는 미상 코드도 이름만 추측해서 연결하지 않습니다.
    merged=addresses.merge(codes[['join_key','dong_code']],on='join_key',how='left',validate='many_to_one')
    for c,new in [('위도','latitude'),('경도','longitude')]:merged[new]=pd.to_numeric(merged[c],errors='coerce')
    merged['coordinate_plausible']=merged.latitude.between(34.8,35.5)&merged.longitude.between(128.7,129.4)
    merged['eligible']=merged.dong_code.notna()&merged.coordinate_plausible&merged['시도명'].eq('부산광역시')
    unmatched=merged[~merged.eligible]
    review=unmatched.groupby(['district','admin_name'],dropna=False).size().rename('address_rows').reset_index()
    save('address_dong_match_review',review)
    # 같은 도로명주소가 반복될 때 대표 위치 선택에 과대 반영되지 않도록 중복 주소를 제외.
    valid=merged[merged.eligible].drop_duplicates(['district','도로명','본번','부번']).copy()
    rows=[]; sensitivity=[]
    for code,group in valid.groupby('dong_code'):
        cy,cx=group.latitude.median(),group.longitude.median()
        ds=haversine_m(cy,cx,group.latitude.to_numpy(float),group.longitude.to_numpy(float))
        row=group.iloc[int(np.argmin(ds))]
        # 양 끝 실제 주소점 두 곳을 별도 민감도 점으로 보존합니다.
        # 이 점에 동 인구를 중복 배정하지 않습니다(수요 가중치 없음).
        first=int(np.argmax(ds))
        ds2=haversine_m(group.iloc[first].latitude,group.iloc[first].longitude,
                        group.latitude.to_numpy(float),group.longitude.to_numpy(float))
        for n,idx in enumerate([first,int(np.argmax(ds2))],1):
            a=group.iloc[idx]
            sensitivity.append({'dong_code':code,'node_id':str(code)+'_s'+str(n),
                'latitude':a.latitude,'longitude':a.longitude,'population_weight':None,
                'purpose':'spatial_sensitivity_only_no_population_allocation'})
        rows.append({'dong_code':code,'latitude':row.latitude,'longitude':row.longitude,
            'representative_address':str(row['시도명'])+' '+str(row.district)+' '+str(row['도로명'])+' '+str(row['본번'])+
            (('-'+str(row['부번'])) if row['부번'] not in ('0',None) and not pd.isna(row['부번']) else ''),
            'unique_address_count':len(group),'point_method':'actual_address_nearest_unweighted_coordinate_median',
            'address_spread_p90_m':float(np.quantile(ds,.9))})
    points=night.merge(pd.DataFrame(rows),on='dong_code',how='left',validate='one_to_one')
    points['node_id']=points.dong_code
    points['spatial_ready']=points.latitude.notna()&points.longitude.notna()
    # 상위 25% 공간 분산 동만 추가 요청합니다. 실측 우회율이라는 뜻은 아닙니다.
    high=points[points.address_spread_p90_m.ge(points.address_spread_p90_m.quantile(.75))]
    save('high_spread_dongs',high.sort_values('address_spread_p90_m',ascending=False))
    extra=pd.DataFrame(sensitivity)
    save('sensitivity_nodes',extra[extra.dong_code.isin(high.dong_code)])
    save('demand_nodes',points)
    save('demand_nodes_missing_location',points[~points.spatial_ready])
    save('address_dong_crosswalk',codes)
    return points,len(addresses),len(unmatched)


def supply_and_distances(source,nodes):
    """지정정책 기준과 API+월요일 보완 기준을 분리해 직선거리만 계산합니다."""
    master=pd.read_csv(source/'pharmacy_master.csv',dtype={'pharmacy_id':'string'})
    state=pd.read_csv(source/'pharmacy_night_weekly_analysis.csv',dtype={'pharmacy_id':'string'})
    designated=set(master.loc[master.public_designation_status.eq('matched_designated'),'pharmacy_id'])
    from team2_refinements import public_policy
    policy=public_policy(source)
    save('public_policy_hours',policy)
    midnight_closed=set(policy.loc[policy.end_minute.eq(1440),'pharmacy_id'])
    saves=[]
    for _,s in state.iterrows():
        public=s.pharmacy_id in designated
        # 공식 개별 시간 예외를 적용하되 현재 현장 운영 확인과는 구분합니다.
        policy_status='closed' if s.pharmacy_id in midnight_closed and s.hour==0 else 'open'
        # 그 밖의 일반 약국은 API 상태를 유지해 기존 공급에서 빠뜨리지 않습니다.
        for scenario,status in [('api_imputed',s.schedule_status),
                                ('policy_plus_api',policy_status if public else s.schedule_status),
                                ('policy_designated_only',policy_status if public else 'not_in_scope')]:
            saves.append({'scenario':scenario,'pharmacy_id':s.pharmacy_id,'day_code':s.day_code,
                'hour':s.hour,'supply_status':status,'is_designated':public})
    supply=pd.DataFrame(saves);save('supply_scenarios',supply)
    grouped=supply.groupby(['scenario','day_code','hour','supply_status']).size().rename('pharmacy_count').reset_index()
    save('supply_counts',grouped)
    active_nodes=nodes[nodes.spatial_ready].reset_index(drop=True)
    dist=haversine_m(active_nodes.latitude.to_numpy(float)[:,None],active_nodes.longitude.to_numpy(float)[:,None],
                     master.latitude.to_numpy(float)[None,:],master.longitude.to_numpy(float)[None,:])
    pid_index={pid:i for i,pid in enumerate(master.pharmacy_id)}
    results=[]; queue_pairs=set()
    for (scenario,day,hour),part in supply.groupby(['scenario','day_code','hour']):
        opened=part[part.supply_status.eq('open')]
        ids=[pid_index[x] for x in opened.pharmacy_id]
        if not ids: continue
        subset=dist[:,ids]; nearest=np.argmin(subset,axis=1)
        for i,node in active_nodes.iterrows():
            j=ids[int(nearest[i])]
            results.append({'scenario':scenario,'node_id':node.node_id,'dong_name':node.dong_name,
                'day_code':day,'hour':hour,'nearest_pharmacy_id':master.iloc[j].pharmacy_id,
                'straight_line_m':float(dist[i,j]),'unknown_supply_count':int(part.supply_status.eq('unknown').sum()),
                'interpretation':'대표지점-시간표상 공급의 직선거리. 실제 도보시간/동 전체 접근률 아님.'})
            # 첫 경로 수집 큐: 시나리오·시각별 직선거리 가까운 5곳의 합집합.
            # 이 후보 축소만으로 진짜 도보 최인접을 보장하지 않습니다.
            for k in np.argsort(subset[i])[:5]:queue_pairs.add((i,ids[int(k)]))
    # 정책 기준 19곳은 거리와 상관없이 모든 대표지점과 요청 계획을 만듭니다.
    for i in range(len(active_nodes)):
        for pid in designated:queue_pairs.add((i,pid_index[pid]))
    request=[]
    for i,j in sorted(queue_pairs):
        node=active_nodes.iloc[i]; ph=master.iloc[j]
        request.append({'node_id':node.node_id,'pharmacy_id':ph.pharmacy_id,
            'origin_latitude':node.latitude,'origin_longitude':node.longitude,
            'destination_latitude':ph.latitude,'destination_longitude':ph.longitude,
            'straight_line_m':dist[i,j],'destination_is_designated':ph.pharmacy_id in designated,
            'queue_scope':'all_designated_plus_top5_by_scenario_and_hour_not_exhaustive'})
    save('straight_line_access_screening',pd.DataFrame(results))
    req=pd.DataFrame(request).sort_values(['destination_is_designated','straight_line_m'],ascending=[False,True])
    # 먼저 동별 가까운 경로를 한 건씩 확보하고, 각 순회에서 공간 분산이 큰 동을 우선.
    req=req.merge(nodes[['node_id','address_spread_p90_m','night_population_proxy']],on='node_id',validate='many_to_one')
    req['node_round']=req.groupby('node_id').cumcount()
    req=req.sort_values(['node_round','address_spread_p90_m','night_population_proxy','straight_line_m'],ascending=[True,False,False,True])
    req['request_priority']=range(1,len(req)+1)
    save('route_request_plan',req)
    extras=pd.read_csv(OUTPUT/'sensitivity_nodes.csv',dtype={'node_id':'string','dong_code':'string'})
    exrows=[]
    for _,n in extras.iterrows():
        d=haversine_m(n.latitude,n.longitude,master.latitude.to_numpy(float),master.longitude.to_numpy(float))
        for j in np.argsort(d)[:5]:
            ph=master.iloc[j]
            exrows.append({'node_id':n.node_id,'pharmacy_id':ph.pharmacy_id,'origin_latitude':n.latitude,
                'origin_longitude':n.longitude,'destination_latitude':ph.latitude,'destination_longitude':ph.longitude,
                'straight_line_m':float(d[j]),'queue_scope':'sensitivity_nearest5_not_exhaustive'})
    save('route_request_plan_sensitivity',pd.DataFrame(exrows))
    # 모든 비지정 약국을 추가 지정 가능 후보로 남깁니다. 참여 의향/약사 인력은 미확인입니다.
    candidates=master[~master.pharmacy_id.isin(designated)].copy()
    candidates['candidate_status']='location_candidate_only_participation_and_staffing_unverified'
    from team2_refinements import candidate_features
    candidates=candidate_features(source,candidates)
    save('candidate_pharmacies',candidates)
    district=nodes.groupby('district').agg(night_population_proxy=('night_population_proxy','sum'),
        dong_count=('dong_code','size'),located_dongs=('spatial_ready','sum')).reset_index()
    counts=master[master.pharmacy_id.isin(designated)].groupby('district').size()
    district['designated_pharmacies']=district.district.map(counts).fillna(0).astype(int)
    save('district_demand_supply_context',district)
    return len(req)


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'head_preview.txt').write_text('',encoding='utf-8')
    inherited=json.loads((ROOT/'reports/latest_run.json').read_text())
    source=Path(inherited['output_dir'])
    if not source.is_relative_to(ROOT):raise ValueError('복사본 밖의 team1 경로를 참조하고 있습니다')
    night,hourly=demand_tables(source)
    nodes,address_count,unmatched=representative_points(night)
    requests=supply_and_distances(source,nodes)
    summary={'team1_run_id':inherited['run_id'],'team1_source':str(source),'population_month':str(night.month.max()),
        'demand_dongs':len(nodes),'located_dongs':int(nodes.spatial_ready.sum()),
        'unlocated_dongs':int((~nodes.spatial_ready).sum()),
        'unlocated_night_population_proxy':float(nodes.loc[~nodes.spatial_ready,'night_population_proxy'].sum()),
        'address_rows':address_count,'quarantined_address_rows':unmatched,'planned_route_pairs':requests,
        'stage':'demand_and_straight_line_screening_complete; walking_access_pending_routes',
        'walking_access_computed':False,'actual_drug_demand_computed':False,
        'point_assumption':'행정동별 비가중 주소 중앙값 인근 실제 주소점 1개. 인구분포 대표성 미검증.',
        'created_at_utc':datetime.now(timezone.utc).isoformat()}
    files=[]
    for directory in [INPUT,OUTPUT]:
        for path in sorted(directory.rglob("*")):
            if path.is_file():files.append({'file':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
    (REPORT/'manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
    (REPORT/'status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
