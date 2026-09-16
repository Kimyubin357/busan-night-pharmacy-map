"""국립중앙의료원 부산 약국 목록 전체 수집 및 기존 시간표 결측 보완.

인증키는 .env에서 읽고 URL·오류문에 출력하지 않습니다. 페이지별 원본을 저장해
중단 후 재개할 수 있습니다. 빈 영업시간은 휴무로 단정하지 않습니다.
NMC 기관 ID가 같아도 이름·전화·위치가 일치하는지 확인한 뒤 연결합니다.
최신 조회 자료와 기존 자료의 충돌은 별도 표로 남기고 확정 시간은 덮어쓰지
않습니다. 원래 미상/추정 상태의 요일은 NMC의 완전한 시간표로 교체합니다.
"""
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import hashlib,json,time,math
import numpy as np
import pandas as pd
from pyproj import Transformer
from pharmacy_data import read_key,normal,phone,interval

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'team2/update_20260915'
RAW=OUT/'raw/nmc_approved'
URL='https://apis.data.go.kr/B552657/ErmctInsttInfoInqireService/getParmacyListInfoInqire'

def parse(b):
    x=ET.fromstring(b)
    if x.findtext('.//resultCode')!='00':raise ValueError('NMC non-success response')
    total=int(x.findtext('.//totalCount'))
    return total,[{c.tag:c.text or '' for c in i} for i in x.findall('.//item')]

def collect():
    RAW.mkdir(parents=True,exist_ok=True)
    key=read_key(ROOT)
    rows=[];total=None;page=1;hashes={}
    while total is None or len(rows)<total:
        path=RAW/f'page_{page:03d}.xml'
        if path.exists():b=path.read_bytes()
        else:
            u=URL+'?'+urlencode(dict(serviceKey=key,Q0='부산광역시',pageNo=page,numOfRows=100))
            for attempt in range(3):
                try:b=urlopen(u,timeout=30).read();parse(b);break
                except HTTPError as e:
                    if e.code in [401,403]:raise RuntimeError(f'NMC HTTP {e.code}; approval required') from None
                    if attempt==2:raise RuntimeError(f'NMC HTTP {e.code}') from None
                    time.sleep(2**attempt)
                except (URLError,TimeoutError):
                    if attempt==2:raise RuntimeError('NMC network timeout') from None
                    time.sleep(2**attempt)
            path.write_bytes(b)
        n,items=parse(b)
        if total is not None and n!=total:raise ValueError('Total changed during collection; retry in a fresh directory')
        total=n
        if not items:raise ValueError('Empty page before expected total')
        rows.extend(items);hashes[path.name]=hashlib.sha256(b).hexdigest()
        print(f'page {page}: {len(rows)}/{total}',flush=True);page+=1
    assert len(rows)==total
    df=pd.DataFrame(rows).fillna('');assert df.hpid.is_unique
    df.to_csv(OUT/'nmc_busan_pharmacies.csv',index=False)
    (RAW/'manifest.json').write_text(json.dumps(dict(endpoint=URL,region='부산광역시',collected_at=datetime.now(timezone.utc).isoformat(),rows=len(df),pages=page-1,sha256=hashes),ensure_ascii=False,indent=2))
    return df

def main():
    df=collect()
    # 모든 NMC 약국의 8개 요일(공휴일 포함)을 펼쳐, 새 ID도 누락 없이 보관합니다.
    long=[]
    for r in df.to_dict('records'):
        for d in range(1,9):
            s=r.get(f'dutyTime{d}s','');e=r.get(f'dutyTime{d}c','');v=interval(s,e)
            long.append(dict(pharmacy_id=r['hpid'],name=r['dutyName'],day_code=d,
                start_raw=s,end_raw=e,start_minute=v[0] if v else None,
                end_minute_unwrapped=v[1] if v else None,hours_status='known' if v else 'unknown'))
    long=pd.DataFrame(long)
    long.to_csv(OUT/'nmc_opening_hours_long.csv',index=False)
    long[long.end_minute_unwrapped.gt(1320)].to_csv(OUT/'nmc_late_hours.csv',index=False)
    source=Path(json.loads((ROOT/'reports/latest_run.json').read_text())['output_dir'])
    master=pd.read_csv(source/'pharmacy_master.csv').fillna('')
    nmc=df.set_index('hpid')
    matches=[];review=[]
    trans=Transformer.from_crs(4326,5179,always_xy=True)
    for r in master.itertuples():
        if r.pharmacy_id not in nmc.index:
            review.append(dict(pharmacy_id=r.pharmacy_id,reason='ID_absent_in_NMC'));continue
        q=nmc.loc[r.pharmacy_id]
        try:
            x,y=trans.transform(float(q.wgs84Lon),float(q.wgs84Lat));a,b=trans.transform(float(r.longitude),float(r.latitude));gap=float(np.hypot(x-a,y-b))
        except (ValueError,TypeError):gap=float('inf')
        same_name=normal(r.name)==normal(q.dutyName)
        same_phone=bool(phone(r.phone)) and phone(r.phone)==phone(q.dutyTel1)
        # 동명 약국이나 지점을 잘못 연결하지 않도록 위치도 함께 확인합니다.
        if gap<=200 and (same_name or same_phone):
            matches.append(dict(pharmacy_id=r.pharmacy_id,nmc_name=q.dutyName,name_match=same_name,phone_match=same_phone,distance_m=gap))
        else:review.append(dict(pharmacy_id=r.pharmacy_id,nmc_name=q.dutyName,reason='identity_needs_review',distance_m=gap))
    pd.DataFrame(matches).to_csv(OUT/'nmc_identity_matches.csv',index=False)
    pd.DataFrame(review).to_csv(OUT/'nmc_identity_review.csv',index=False)
    accepted={r['pharmacy_id'] for r in matches}
    df[~df.hpid.isin(master.pharmacy_id)].to_csv(OUT/'nmc_new_ids_for_review.csv',index=False)
    hours=pd.read_csv(OUT/'pharmacy_opening_hours_supplemented.csv')
    for c in ['start_effective','end_effective','hours_status','start_value_source']:
        hours['before_nmc_'+c]=hours[c]
    hours['nmc_applied']=False;hours['nmc_start_raw']='';hours['nmc_end_raw']=''
    audit=[]
    def fmt(v):
        return str(int(float(v))).zfill(4) if pd.notna(v) and str(v)!='' else ''
    for i,r in hours.iterrows():
        if r.pharmacy_id not in accepted:continue
        q=nmc.loc[r.pharmacy_id];d=int(r.day_code)
        s=q.get(f'dutyTime{d}s','');e=q.get(f'dutyTime{d}c','')
        hours.loc[i,['nmc_start_raw','nmc_end_raw']]=[s,e]
        parsed=interval(s,e)
        if parsed is None:continue
        conflict=bool((fmt(r.start_effective) and fmt(r.start_effective)!=s) or (fmt(r.end_effective) and fmt(r.end_effective)!=e))
        applied=r.hours_status in ['unknown','estimated']
        if applied:
            start,end=parsed
            hours.loc[i,['start_effective','end_effective','start_minute','end_minute_unwrapped']]=[int(s),int(e),start,end]
            hours.loc[i,['hours_status','start_value_source','crosses_midnight','start_imputed','nmc_applied']]=['known','nmc_direct_api',end>=1440,False,True]
        audit.append(dict(pharmacy_id=r.pharmacy_id,day_code=d,nmc_start=s,nmc_end=e,previous_start=fmt(r.start_effective),previous_end=fmt(r.end_effective),previous_status=r.hours_status,conflict=conflict,applied=applied))
    hours.to_csv(OUT/'pharmacy_opening_hours_nmc.csv',index=False)
    pd.DataFrame(audit).to_csv(OUT/'nmc_hours_comparison.csv',index=False)
    summary=dict(nmc_pharmacies=len(df),identity_matches=len(matches),identity_review=len(review),
                 new_ids=int((~df.hpid.isin(master.pharmacy_id)).sum()),
                 hours_rows_updated=int(hours.nmc_applied.sum()),
                 unknown_before=int(hours.before_nmc_hours_status.eq('unknown').sum()),
                 unknown_after=int(hours.hours_status.eq('unknown').sum()),
                 monday_known=int((hours.day_code.eq(1)&hours.hours_status.eq('known')).sum()),
                 monday_unknown=int((hours.day_code.eq(1)&hours.hours_status.eq('unknown')).sum()),
                 acquisition_success=True, live_operation_verified=False)
    (OUT/'nmc_update_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2));print(hours.loc[hours.nmc_applied,['pharmacy_id','day_name','start_effective','end_effective','hours_status']].head().to_string(index=False))

if __name__=='__main__':main()
