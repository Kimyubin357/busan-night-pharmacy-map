"""KST 도착시각의 영업상태 판정. 달력 미확인을 평일로 치환하지 않습니다.

weekly[약국ID][요일1..8] = [(시작 분, 종료 분)] 또는 None(미상).
빈 목록은 확인된 휴무입니다. 점심 휴게/심야 재개는 여러 구간으로 표현합니다.
월요일 추정값은 원본과 구분된 분석 시간표에서만 읽습니다.
22~익일01시 분석에서는 아침 개점보다 도착 순간의 심야 운영/폐점이 중요합니다.
"""
from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo
import math
import numpy as np
import pandas as pd
KST=ZoneInfo('Asia/Seoul')

def state_at(pharmacy_id,arrival,weekly,calendar,exceptions=None):
    """calendar는 date:공휴일 여부의 완비된 날짜별 사전. 범위 밖은 미상.

    exceptions[(약국ID,date)]는 그 날짜에 시작하는 영업 구간의 대체 값입니다.
    전날부터 이어진 구간을 포함하므로 자정/휴일 전후도 같은 방식으로 판정합니다.
    종료 순간은 영업에 포함하지 않습니다. 구간 길이는 최대 24시간입니다.
    """
    if arrival.tzinfo is None:raise ValueError('Asia/Seoul 등 시간대가 있는 datetime 필요')
    arrival=arrival.astimezone(KST);unknown=False;exceptions=exceptions or {}
    for offset in (0,1):
        day=arrival.date()-timedelta(days=offset)
        if (pharmacy_id,day) in exceptions: intervals=exceptions[(pharmacy_id,day)]
        elif day not in calendar: intervals=None
        else:intervals=weekly.get(pharmacy_id,{}).get(8 if calendar[day] else day.weekday()+1)
        if intervals is None:unknown=True;continue
        base=datetime.combine(day,time(),KST)
        for start,end in intervals:
            if not (math.isfinite(start) and math.isfinite(end) and 0<=start<1440 and start<end<=start+1440):
                raise ValueError('영업 구간이 비정상입니다')
            if base+timedelta(minutes=start)<=arrival<base+timedelta(minutes=end):return 'open'
    return 'unknown' if unknown else 'closed'

def load_weekly(source,policy=None):
    """API 분석 시간표 로딩. 정책 시나리오는 지정약국의 심야 구간만 대체합니다."""
    h=pd.read_csv(source/'pharmacy_opening_hours_analysis.csv');result={}
    for r in h.itertuples():
        interval=None if pd.isna(r.start_minute) or pd.isna(r.end_minute_unwrapped) else [(float(r.start_minute),float(r.end_minute_unwrapped))]
        result.setdefault(r.pharmacy_id,{})[int(r.day_code)]=interval
    if policy is not None:
        for r in policy.itertuples():result[r.pharmacy_id]={d:[(float(r.start_minute),float(r.end_minute))] for d in range(1,9)}
    return result

def arrival_accessibility(minutes,pharmacy_ids,departure,weekly,calendar,threshold=15,exceptions=None):
    """각 출발점마다 다른 도착시각으로 공급을 판정한 뒤 접근성 경계를 계산.

    경로 미수집이면 낙관 경계만 열어 둡니다. 실제 도보시간 없이 사각지대를 확정하지
    않습니다. 결과는 대표지점 모형이며 동 전체의 실제 인구 접근률이 아닙니다.
    """
    values=np.asarray(minutes,float)
    if values.ndim!=2 or values.shape[1]!=len(pharmacy_ids):raise ValueError('입력 차원 불일치')
    if not math.isfinite(threshold) or threshold<=0 or (values[~np.isnan(values)]<0).any():raise ValueError('잘못된 이동시간')
    rows=[]
    for line in values:
        confirmed=False;possible=False
        for duration,pid in zip(line,pharmacy_ids):
            if np.isnan(duration):possible=True;continue
            if duration>threshold:continue
            status=state_at(pid,departure+timedelta(minutes=float(duration)),weekly,calendar,exceptions)
            confirmed |= status=='open';possible |= status!='closed'
        rows.append({'confirmed_representative_point_access':confirmed,'possible_representative_point_access':possible,
            'unresolved':possible and not confirmed,'confirmed_no_access':not possible})
    return pd.DataFrame(rows)
