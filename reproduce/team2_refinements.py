"""공식 정책 시간의 예외와 후보 상담 우선순위를 재현하는 보조 함수."""
import numpy as np
import pandas as pd

POLICY_URL='https://www.busan.go.kr/news/totalnews01/view?curPage=5&dataNo=72418'

def public_policy(source):
    p=pd.read_csv(source/'public_night_enriched.csv',dtype={'pharmacy_id':'string'})
    # 과거 18곳 기사로 최신 19곳의 지정 명단을 교체하지 않습니다.
    # 이름+구군을 확인한 세 곳의 시간 예외만 적용합니다. 사하구 하나약국과 구분.
    exceptions={('중구','영주약국'),('해운대구','365 하나약국'),('기장군','튼튼약국')}
    mask=p.apply(lambda r:(r.district,r['name']) in exceptions,axis=1)
    if mask.sum()!=3:raise ValueError('정책 시간 예외 약국의 명칭/구군 재확인 필요')
    p['start_minute']=np.where(mask,1260,1320)
    p['end_minute']=np.where(mask,1440,1500)
    p['policy_start']=np.where(mask,'21:00','22:00')
    p['policy_end_next_day']=np.where(mask,'00:00','01:00')
    p['hours_source']=np.where(mask,POLICY_URL,'https://www.data.go.kr/data/15127987/fileData.do')
    p['hours_evidence_date']=np.where(mask,'2026-02-14','2026-08-10')
    p['policy_hours_evidence']=np.where(mask,'부산시 개별 시간 예외 안내','제공기관 일반 정책 설명')
    p['operating_assumption']='daily_policy_not_live_verification'
    p['verification_needed']='최신 요일별/공휴일/임시휴무 확인; 서로 다른 시점의 명단과 시간 안내'
    return p

def candidate_features(source,candidates):
    h=pd.read_csv(source/'pharmacy_opening_hours_analysis.csv')
    h=h[h.day_code.between(1,7)].copy()
    h['known']=h.hours_status.isin(['known','estimated'])
    h['late']=h.known & h.end_minute_unwrapped.gt(1320)
    agg=h.groupby('pharmacy_id').agg(known_schedule_days=('known','sum'),late_after22_days=('late','sum'))
    c=candidates.merge(agg,on='pharmacy_id',validate='one_to_one')
    # 기존 늦은 영업은 상담 우선순위의 대리 지표이지 인력/참여 의향의 증거가 아닙니다.
    c['contact_tier']=np.select([c.late_after22_days.gt(0),c.known_schedule_days.ge(4)],
        ['existing_late_hours_contact_first','several_days_known_contact_needed'],default='schedule_review_first')
    c['chain_affiliation']='unverified'
    c['staffing_and_participation']='unverified'
    return c
