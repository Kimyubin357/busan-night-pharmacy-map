"""심평원 2026년 6월 시간표로 부산 API의 결측만 보완합니다.

현재 API와 다른 시간을 덮어쓰지 않습니다. 동일 약국 검증과 요일별 충돌 검사,
원본값 보존을 거칩니다. 출처가 과거 분기 자료이므로 보완행은 estimated로
표시하며, 원래 자료만 사용한 분석과 비교할 수 있도록 별도 파일에 저장합니다.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from pyproj import Transformer
from pharmacy_data import normal, phone, minute, interval

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'team2/update_20260915'
DAYS=['월요일','화요일','수요일','목요일','금요일','토요일','일요일']

def hhmm(v):
    """엑셀의 900.0과 문자열 0900을 동일한 HHMM으로 정규화. 빈칸은 빈칸 유지."""
    if pd.isna(v) or str(v).strip()=='':return None
    try:
        n=float(v)
        if not n.is_integer():return None
        s=str(int(n)).zfill(4)
        if minute(s,is_end=True) is None:return None
        return s
    except (ValueError,TypeError):return None

def main():
    source=__import__('pipeline_context').processed_source()
    ph=pd.read_csv(source/'pharmacy_master.csv').fillna('')
    hira=pd.read_csv(OUT/'hira_busan_pharmacy_details.csv',dtype=str).fillna('')
    trans=Transformer.from_crs(4326,5179,always_xy=True)
    px,py=trans.transform(ph.longitude.to_numpy(),ph.latitude.to_numpy())
    matches=[];rejected=[]
    for _,r in hira.iterrows():
        x,y=trans.transform(float(r['좌표(X)']),float(r['좌표(Y)']))
        distance=np.hypot(px-x,py-y)
        options=[]
        for i in np.flatnonzero(distance<=200):
            p=ph.iloc[i]
            same_name=normal(r['요양기관명_약국'])==normal(p['name'])
            same_phone=bool(phone(r['전화번호'])) and phone(r['전화번호'])==phone(p.phone)
            if same_name and same_phone:options.append(i)
        if len(options)!=1:
            rejected.append({'hira_name':r['요양기관명_약국'],'eligible_matches':len(options),'reason':'requires_unique_name_phone_within_200m'})
            continue
        i=options[0]
        matches.append({**r.to_dict(),'pharmacy_id':ph.iloc[i].pharmacy_id,'match_distance_m':float(distance[i]),'match_method':'exact_normalized_name_and_phone_within_200m'})
    matched=pd.DataFrame(matches)
    # 같은 약국 ID가 중복 연결되면 시간표가 덮어써지므로 오류로 중단합니다.
    assert not matched.pharmacy_id.duplicated().any()
    matched.to_csv(OUT/'hira_pharmacy_matches.csv',index=False)
    pd.DataFrame(rejected).to_csv(OUT/'hira_pharmacy_match_review.csv',index=False)
    lookup=matched.set_index('pharmacy_id')
    hours=pd.read_csv(source/'pharmacy_opening_hours_analysis.csv')
    hours['baseline_start_effective']=hours.start_effective
    hours['baseline_end_raw']=hours.end_raw
    hours['end_effective']=hours.end_raw
    hours['baseline_hours_status']=hours.hours_status
    hours['supplement_source']=''
    hours['supplement_reference_date']=''
    hours['supplement_applied']=False
    logs=[]
    for i,row in hours.iterrows():
        if row.pharmacy_id not in lookup.index or row.day_code>7:continue
        r=lookup.loc[row.pharmacy_id];day=DAYS[int(row.day_code)-1]
        hs=hhmm(r['진료시작시간_'+day]);he=hhmm(r['진료종료시간_'+day])
        os=hhmm(row.start_effective);oe=hhmm(row.end_raw)
        if not hs or not he:continue
        # 서로 다른 시간표의 시작·종료를 합치지 않도록 충돌하는 요일은 보류합니다.
        conflict=(os is not None and os!=hs) or (oe is not None and oe!=he)
        action='conflict_not_applied' if conflict else 'already_complete'
        if not conflict and (os is None or oe is None):
            parsed=interval(hs,he)
            if parsed is None:continue
            start,end=parsed;cross=end>=1440
            hours.loc[i,['start_effective','end_effective','start_minute','end_minute_unwrapped']]=[int(hs),int(he),start,end]
            hours.loc[i,['hours_status','crosses_midnight','start_value_source']]=['estimated',cross,'hira_202606_supplement']
            hours.loc[i,['supplement_source','supplement_reference_date','supplement_applied']]=['HIRA quarterly detail snapshot','2026-06-30',True]
            action='filled_missing_historical_supplement'
        logs.append(dict(pharmacy_id=row.pharmacy_id,day_code=int(row.day_code),api_start=os,api_end=oe,hira_start=hs,hira_end=he,action=action))
    audit=pd.DataFrame(logs)
    audit.to_csv(OUT/'hira_hours_comparison.csv',index=False)
    hours.to_csv(OUT/'pharmacy_opening_hours_supplemented.csv',index=False)
    summary=dict(matched_detail_pharmacies=len(matched),unmatched_detail_pharmacies=len(rejected),
                 matched_monday_start_available=int(matched['진료시작시간_월요일'].ne('').sum()),
                 supplemented_day_rows=int(hours.supplement_applied.sum()),
                 supplemented_unique_pharmacies=int(hours.loc[hours.supplement_applied,'pharmacy_id'].nunique()),
                 supplemented_monday_rows=int((hours.supplement_applied & hours.day_code.eq(1)).sum()),
                 conflicts_not_applied=int(audit.action.eq('conflict_not_applied').sum()),
                 unknown_before=int(hours.baseline_hours_status.eq('unknown').sum()),
                 unknown_after=int(hours.hours_status.eq('unknown').sum()),
                 reference_date='2026-06-30',known_live_hours=False)
    (OUT/'hours_supplement_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(hours[hours.supplement_applied][['pharmacy_id','day_name','start_effective','end_effective','hours_status']].head().to_string(index=False))

if __name__=='__main__':main()
