"""NMC 비고의 명확한 휴게 구간만 반영하고, 모호한 예외는 확인 필요로 보존합니다.

요일별로 직접 검토한 규칙은 원문 조각이 그대로 존재할 때만 적용합니다.
월별 휴무는 특정 날짜를 알 수 없는 분석 모형에서는 미상으로 두고,
시민 화면에서는 실제 날짜의 해당 요일 회차를 확인합니다.
"""
import csv, json, re
from datetime import date
from pathlib import Path

P = Path(__file__).resolve().parent
DAYS = list(range(7))  # 월=0
SPECIAL = {
    'C1202436': [('(월~금) 18:30 ~ 22:00', range(5), 1110, 1320), ('(토) 13:00~22:00', [5], 780, 1320)],
    'C1201274': [('월~금 휴게시간: 17:00~22:00', range(5), 1020, 1320), ('토요일 휴게시간: 12:00~22:00', [5], 720, 1320)],
    'C1201466': [('월요일~토요일 20:00~22:00', range(6), 1200, 1320)],
    'C1201298': [('월~금요일 휴게시간 18:30~22:00', range(5), 1110, 1320), ('토요일 휴게시간 13:00~22:00', [5], 780, 1320)],
    'C1202042': [('(월~금)19:30~22:00', range(5), 1170, 1320), ('(토)15:00~22:00', [5], 900, 1320)],
    'C1200268': [('월~금 휴게시간:16:00~22:00', range(5), 960, 1320)],
    'C1200806': [('휴게시간: 18:00~22:00 (금요일 13:00~22:00)', [0,1,2,3], 1080, 1320), ('휴게시간: 18:00~22:00 (금요일 13:00~22:00)', [4], 780, 1320)],
    'C1200889': [('(월~금) 18:30~22:00', range(5), 1110, 1320), ('(토) 13:30~22:00', [5], 810, 1320)],
    'C1201302': [('월,화,목,금 18:00~22:00', [0,1,3,4], 1080, 1320), ('수,토 13:00~22:00', [2,5], 780, 1320)],
    'C1200563': [('화~금 18:30-22:00', [1,2,3,4], 1110, 1320), ('토 13:00-22:00', [5], 780, 1320)],
    'C1201180': [('평일 점심시간 13:00~14:00', range(5), 780, 840)],
    'C1200837': [('점심시간 월~금 13:00~14:00', range(5), 780, 840)],
    'C1200808': [('주중 점심시간은 오후1시30분부터 2시까지', range(5), 810, 840)],
}
RECURRING = {
    'C1200447': [('첫째, 둘째, 셋째 주 화요일 휴무',1,[1,2,3],'closed'), ('둘째 주 일요일 휴무',6,[2],'closed')],
    'C1202062': [('매월 2,4째주 일요일 운영',6,[2,4],'open_only')],
    'C1201361': [('토요일 1,3.5째주만 운영',5,[1,3,5],'open_only')],
    'C1202472': [('둘째,넷째주 토요일 휴무',5,[2,4],'closed')],
    'C1200765': [('매월 둘째주일요일 휴무',6,[2],'closed')],
    'C1202893': [('1째주,3째주 일요일 영업',6,[1,3],'open_only')],
    'C1201459': [('4째주 일요일만 가능',6,[4],'open_only')],
    'C1200112': [('토요일 2, 4째주만 운영',5,[2,4],'open_only')],
    'C1200896': [('매월 첫째 주, 셋째 주 일요일은 휴무',6,[1,3],'closed')],
}
BREAK = re.compile(r'(?:휴게|휴식|점심|검심)')
TIME = re.compile(r'(?<!\d)(\d{1,2})(?::(\d{2})|시)?\s*[~–-]\s*(\d{1,2})(?::(\d{2})|시)?(?!\d)')

def subtract(intervals, breaks):
    if intervals is None: return None
    result = [list(v) for v in intervals]
    for x,y in breaks:
        updated=[]
        for a,b in result:
            if y<=a or x>=b: updated.append([a,b]); continue
            if a<x: updated.append([a,x])
            if y<b: updated.append([y,b])
        result=updated
    return result

def parse_notes(row):
    pid=row['hpid'];notes='\n'.join(dict.fromkeys(row.get(k,'').strip() for k in ['dutyInf','dutyMapimg','dutyEtc'] if row.get(k,'').strip()))
    breaks=[[] for _ in DAYS];recurring=[];review=[]
    special=SPECIAL.get(pid,[])
    for text,days,a,b in special:
        if text in notes:
            for d in days: breaks[d].append([a,b])
        else: review.append('기존 요일별 휴게 규칙과 원문 불일치')
    # 일반 휴게시간: 같은 줄에 요일·다른 운영시간이 섞이면 자동 해석하지 않습니다.
    for line in notes.splitlines():
        if not BREAK.search(line): continue
        if re.search(r'(없음|없이|없습니다)',line): continue
        if special and any(text in line for text,_,_,_ in special): continue
        if '오후' in line or re.search(r'[월화수목금토일](?:요일|[~,])|평일|주중',line):
            if not special: review.append('휴게시간 요일/문장 해석 필요: '+line)
            continue
        matches=list(TIME.finditer(line));valid=[]
        for match in matches:
            a=int(match[1])*60+int(match[2] or 0);b=int(match[3])*60+int(match[4] or 0)
            if 0<=a<b<=1440: valid.append([a,b])
        # 광제 등의 '/ 공공심야 운영' 뒤 시간은 휴게 구간으로 읽지 않습니다.
        segment=line.split('/')[0]
        first=TIME.search(segment)
        if first and valid:
            a=int(first[1])*60+int(first[2] or 0);b=int(first[3])*60+int(first[4] or 0)
            if 0<=a<b<=1440:
                for d in DAYS: breaks[d].append([a,b])
        elif not valid: review.append('휴게시간 확인 필요: '+line)
    for text,day,weeks,kind in RECURRING.get(pid,[]):
        if text in notes: recurring.append(dict(day=day,weeks=weeks,kind=kind,evidence=text))
        else: review.append('기존 정기휴무 규칙과 원문 불일치')
    for line in notes.splitlines():
        if any(k in line for k in ['휴무','쉬는','문의','전화','째주','째 주']):
            if not any(text in line for text,_,_,_ in RECURRING.get(pid,[])) and not BREAK.search(line):
                review.append('날짜별 휴무/운영 확인 필요: '+line)
    closed_dates=[]
    for match in re.finditer(r'(\d{4}|\d{2})[.년/-]\s*(\d{1,2})[.월/-]\s*(\d{1,2})[.일]?[^\n]{0,30}?휴무',notes):
        year=int(match[1]);year=year+2000 if year<100 else year
        try:closed_dates.append(date(year,int(match[2]),int(match[3])).isoformat())
        except ValueError:review.append('유효하지 않은 휴무 날짜 확인 필요')
    return dict(notes=notes,closedDates=sorted(set(closed_dates)),breaks=[sorted({tuple(v) for v in day}) for day in breaks],recurring=recurring,review=list(dict.fromkeys(review)))

def load_exceptions():
    with (P.parent/'team2/update_20260915/nmc_busan_pharmacies.csv').open(encoding='utf-8-sig',newline='') as f:
        return {r['hpid']:parse_notes(r) for r in csv.DictReader(f)}

def apply_exceptions(weekly,audit):
    exceptions=load_exceptions();records=[]
    for pid,w in weekly.items():
        e=exceptions.get(pid,dict(breaks=[[]]*7,recurring=[],review=[],notes=''))
        for day in range(1,8): w[day]=subtract(w[day],e['breaks'][day-1])
        audit[pid]['finder_schedule']=json.dumps([w[d] for d in range(1,8)])
        # 월별 예외 요일은 날짜가 없는 주간 분석에서 확정 영업으로 세지 않습니다.
        for rule in e['recurring']: w[rule['day']+1]=None
        audit[pid]['exception_days']=json.dumps(sorted({r['day']+1 for r in e['recurring']}))
        records.append(dict(pharmacy_id=pid,notes=e['notes'],breaks=json.dumps(e['breaks']),recurring=json.dumps(e['recurring'],ensure_ascii=False),closed_dates=json.dumps(e.get('closedDates',[])),review=json.dumps(e['review'],ensure_ascii=False)))
    with (P/'schedule_exceptions_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['pharmacy_id','notes','breaks','recurring','closed_dates','review']);writer.writeheader();writer.writerows(records)
    return exceptions
