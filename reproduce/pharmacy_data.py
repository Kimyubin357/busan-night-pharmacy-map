"""팀원 1 — 부산 약국 API 전체 수집, 지정 여부 연결, 요일별 영업시간 정제.

전국 자료를 먼저 다운로드하는 대신 부산 전체를 제공하는 공식 API를 사용합니다.
따라서 수집 범위는 '이 API에 등록된 부산 약국'이며 현장 전수조사와 같지는 않습니다.
공공심야약국은 전체 약국의 부분집합입니다. 매칭되면 기존 행에 속성을 붙입니다.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, unquote
import pandas as pd
from public_data import request_bytes, snapshot_file

API = 'https://apis.data.go.kr/6260000/PharmacyInfoService/getPharmacyInfo'
# 공식 Swagger에서 확인한 필드명입니다. 월요일 시작 필드만 명명 규칙이 다릅니다.
START = ['monSalsBgngTm', 'tueMdexmBgngTm', 'wedMdexmBgngTm', 'thurMdexmBgngTm',
         'friMdexmBgngTm', 'satMdexmBgngTm', 'sunMdexmBgngTm', 'lhldyMdexmBgngTm']
END = [day + 'MdexmEndTm' for day in ['mon', 'tue', 'wed', 'thur', 'fri', 'sat', 'sun', 'lhldy']]
DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일', '공휴일']


def read_key(root: Path):
    """환경변수 또는 프로젝트 .env에서 읽습니다. 키 자체는 출력하지 않습니다."""
    key = os.environ.get('DATA_GO_KR_SERVICE_KEY', '').strip()
    if not key and (root / '.env').exists():
        for line in (root / '.env').read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('DATA_GO_KR_SERVICE_KEY='):
                key = line.split('=', 1)[1].strip().strip('\"\'')
    # Encoding 키의 %2B 등을 한 번 풀고 urlencode가 한 번 인코딩하게 합니다.
    # unquote_plus는 +를 공백으로 바꾸므로 사용하면 안 됩니다.
    return unquote(key)


def parse_page(content):
    """성공 코드/전체 건수/응답 구조를 검사합니다. 오류 응답을 빈 데이터로 취급하지 않습니다."""
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('API가 JSON 대신 오류/다른 형식을 반환했습니다. 인증키 활용승인 확인 필요') from None
    response = obj.get('response', obj)
    code = str(response.get('header', {}).get('resultCode', ''))
    if code not in ('00', '0', '0000'):
        # 외부 응답 전체를 예외에 넣으면 인증키가 반사되어 노출될 가능성이 있어 코드만 기록합니다.
        raise ValueError('API 성공 코드가 아닙니다: ' + re.sub(r'[^0-9A-Za-z_]', '', code)[:30])
    body = response.get('body', {})
    total = int(body['totalCount'])
    items = body.get('items') or {}
    items = items.get('item', []) if isinstance(items, dict) else items
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise ValueError('API item 응답 구조 변경')
    return total, items


def collect_api(run, key):
    """totalCount에 도달할 때까지 페이지를 받습니다. 중간 실패/반복 페이지는 중단합니다."""
    rows, seen, page, expected = [], set(), 1, None
    while True:
        # 약국명 조건을 넣지 않아 이 서비스가 제공하는 부산 전체 약국을 수집합니다.
        params = {'serviceKey': key, 'pageNo': page, 'numOfRows': 100, 'resultType': 'json'}
        stored = snapshot_file(f'pharmacy_api_page_{page:03}.json')
        content = stored.read_bytes() if stored else request_bytes(API + '?' + urlencode(params))
        total, items = parse_page(content)
        if expected is None:
            expected = total
        if total != expected or expected <= 0:
            raise ValueError('수집 중 전체 건수 변경 또는 전체 건수 0: 다시 수집해야 합니다')
        signature = hashlib.sha256(content).hexdigest()
        if signature in seen or not items:
            raise ValueError('반복/빈 페이지: 전체 수집으로 인정할 수 없습니다')
        seen.add(signature)
        (run.raw / f'pharmacy_api_page_{page:03}.json').write_bytes(content)
        run.sources.append({'dataset_id': '15163576', 'url_without_key': API,
            'page': page, 'requested_page_size': 100, 'received_rows': len(items),
            'total_count': total, 'sha256': signature,
            'retrieved_at_utc': next(x['retrieved_at_utc'] for x in json.loads((stored.parent / 'sources.json').read_text()) if x.get('page') == page) if stored else datetime.now(timezone.utc).isoformat()})
        rows.extend(items)
        print(f'약국 API {page}페이지: {len(items)}건, 누적 {len(rows)}/{expected}', flush=True)
        if page == 1:
            run.inspect('pharmacy_api_first_page', pd.DataFrame(items))
        if len(rows) >= expected:
            break
        page += 1
        if page > 1000:
            raise ValueError('비정상 페이지 수: 수집 중단')
    if len(rows) != expected:
        raise ValueError('totalCount와 실제 받은 행 수 불일치')
    df = pd.DataFrame(rows)
    required = ['pmcyId', 'pmcyNm', 'pmcyLctnRoadNmAddr', 'rprsTelno', 'lat', 'lot'] + START + END
    if set(required) - set(df):
        raise ValueError(f'API 컬럼 변경: {sorted(set(required) - set(df))}')
    ids = df['pmcyId'].astype('string').str.strip()
    if ids.isna().any() or ids.eq('').any() or ids.duplicated().any():
        raise ValueError('API ID 누락/중복: 임의 중복 제거 없이 원본 검토 필요')
    run.save('pharmacy_api_all_raw_columns', df)
    return df


def normal(value):
    """이름 비교용 공백/기호 정규화. 이름만 같은 약국을 자동 연결하지는 않습니다."""
    return '' if pd.isna(value) else re.sub(r'[^가-힣A-Za-z0-9]', '', str(value)).lower()


def phone(value):
    return '' if pd.isna(value) else re.sub(r'\D', '', str(value))


def address(value):
    """괄호/쉼표 뒤 부가주소를 제외한 본 주소. 도로명/건물번호를 유지합니다."""
    if pd.isna(value):
        return ''
    base = re.split(r'[,(]', str(value))[0].replace('부산광역시', '부산')
    return normal(base)


def match_designations(master, designated):
    """강한 식별정보 2개를 만족하고 유일한 경우에만 자동 연결합니다.

    ① 이름+전화번호, ② 이름+도로명주소, ③ 전화번호+도로명주소. 규칙들이 서로 다른 약국을
    가리키면 충돌로 남깁니다. 한 API 약국에 지정명단 두 행이 연결되어도
    자동 확정하지 않습니다. 미매칭은 별도 검토표에 반드시 남깁니다.
    """
    m = master.copy()
    m['public_designation_status'] = 'not_matched_to_list'
    m['designation_id'] = pd.Series(pd.NA, index=m.index, dtype='string')
    m['designation_reference_date'] = pd.Series(pd.NA, index=m.index, dtype='string')
    m['designation_match_method'] = pd.Series(pd.NA, index=m.index, dtype='string')
    mn, mp, ma = m['name'].map(normal), m['phone'].map(phone), m['address'].map(address)
    proposals, audit = [], []
    for _, d in designated.iterrows():
        n, p, a = normal(d['name']), phone(d['phone']), address(d['address'])
        by_phone = set(m.index[(mn == n) & (mp == p)]) if n and p else set()
        by_address = set(m.index[(mn == n) & (ma == a)]) if n and a else set()
        by_phone_address = set(m.index[(mp == p) & (ma == a)]) if p and a else set()
        candidates = by_phone | by_address | by_phone_address
        chosen = next(iter(candidates)) if len(candidates) == 1 else None
        status = 'matched' if chosen is not None else ('ambiguous' if candidates else 'unmatched')
        method = '+'.join(x for x, s in [('name_phone', by_phone), ('name_address', by_address), ('phone_address', by_phone_address)] if s)
        # 약한 이름/전화 일치는 검토 후보로만 표시하며 자동 확정하지 않습니다.
        review = candidates or set(m.index[(mn == n) | ((mp == p) & (mp != ''))])
        audit.append({**d.to_dict(), 'match_status': status, 'match_method': method,
                      'candidate_api_ids': '|'.join(sorted(m.loc[list(review), 'pharmacy_id'].tolist()))})
        proposals.append(chosen)
    from collections import Counter
    count = Counter(x for x in proposals if x is not None)
    for i, chosen in enumerate(proposals):
        if chosen is None:
            continue
        if count[chosen] != 1:
            audit[i]['match_status'] = 'many_designations_to_one_api_review'
            continue
        d = designated.iloc[i]
        m.loc[chosen, ['public_designation_status', 'designation_id', 'designation_reference_date', 'designation_match_method']] = [
            'matched_designated', d['designation_id'], d['reference_date'], audit[i]['match_method']]
    # not_matched_to_list는 미지정 확정이 아닙니다. 미매칭 지정약국이 남을 수 있습니다.
    return m, pd.DataFrame(audit)


def minute(value, *, is_end=False):
    """HHMM/HH:MM을 분으로 바꿉니다. 종료의 2500은 익일 01:00(1500분)입니다."""
    if pd.isna(value) or str(value).strip() == '':
        return None
    raw = str(value).strip().replace(':', '')
    if not re.fullmatch(r'\d{3,4}', raw):
        return None
    hour, mins = divmod(int(raw), 100)
    # 원본은 자정 이후 종료를 2500처럼 24 이상 시각으로도 제공합니다.
    # 이미 다음날 기준 분이므로 interval에서 1440을 다시 더하지 않습니다.
    if is_end and 24 <= hour < 48 and 0 <= mins < 60:
        return hour * 60 + mins
    return hour * 60 + mins if 0 <= hour < 24 and 0 <= mins < 60 else None


def interval(start, end):
    """종료가 시작보다 이르면 다음날 종료. 동일시각은 24시간/휴무를 구별 못해 unknown."""
    s, e = minute(start), minute(end, is_end=True)
    if s is None or e is None or s == e:
        return None
    e = e + 1440 if e < s else e
    # 24시간을 초과하는 단일 영업은 이 표의 해석 범위 밖이므로 검토합니다.
    return (s, e) if 0 < e - s <= 1440 else None


def opening_state(today, yesterday, at_minute):
    """오늘 시작 영업과 전날부터 이어진 영업을 합쳐 open/closed/unknown을 반환합니다.

    종료 시각 자체는 영업에 포함하지 않습니다([시작, 종료)).
    두 요일 중 필요한 시간정보가 불명확하면 closed로 단정하지 않습니다.
    이는 공휴일이 없는 보통 주간의 스케줄 판정이며 실시간 영업확인이 아닙니다.
    """
    if not 0 <= at_minute < 1440:
        raise ValueError('검사시각은 0~1439분이어야 합니다')
    if today and today[0] <= at_minute < today[1]:
        return 'open'
    if yesterday and yesterday[0] <= at_minute + 1440 < yesterday[1]:
        return 'open'
    return 'unknown' if today is None or yesterday is None else 'closed'


def process_pharmacies(run, raw, designated):
    names = {'pmcyId': 'pharmacy_id', 'pmcyNm': 'name', 'pmcyLctnRoadNmAddr': 'address',
             'rprsTelno': 'phone', 'lat': 'latitude', 'lot': 'longitude', 'rmrkCn': 'notes'}
    received_count = len(raw)
    # 부산 전용 API에도 주소의 일부에 '부산'이 포함된 타지역 행이 섞여 있었습니다.
    # 원본은 이미 모두 저장했으며, 여기서 주소 시작이 부산인 행만 분석 대상으로 제한합니다.
    busan_mask = raw['pmcyLctnRoadNmAddr'].astype('string').str.match(r'^부산(?:광역시)?\s').fillna(False)
    run.save('pharmacy_excluded_non_busan', raw[~busan_mask])
    raw = raw[busan_mask].reset_index(drop=True)
    master = raw.rename(columns=names)[list(names.values())].copy()
    master['pharmacy_id'] = master['pharmacy_id'].astype('string').str.strip()
    # 부산 전용 API이지만 주소를 한 번 더 검사합니다. 잘못된 주소를 몰래 제외하지 않습니다.
    master['is_busan_address'] = master['address'].astype('string').str.match(r'^부산(?:광역시)?\s').fillna(False)
    master['district'] = master['address'].astype('string').str.extract(r'^부산(?:광역시)?\s+(\S+[구군])\s', expand=False)
    for col in ('latitude', 'longitude'):
        master[col] = pd.to_numeric(master[col], errors='coerce')
    # 넓은 부산 주변 사각형은 이상값 탐지용입니다. 부산 경계 내 존재를 증명하는 공간조인은 아닙니다.
    master['coordinate_plausible'] = master['latitude'].between(34.8, 35.5) & master['longitude'].between(128.7, 129.4)
    master['coordinate_check_method'] = 'rough_bbox_only_not_administrative_boundary'
    master, audit = match_designations(master, designated)
    api_sources = [x for x in run.sources if x.get('page')]
    master['api_collected_date'] = datetime.fromisoformat(api_sources[0]['retrieved_at_utc']).astimezone().date().isoformat() if api_sources else datetime.now().date().isoformat()
    master['has_notes_requires_review'] = master['notes'].fillna('').astype(str).str.strip().ne('')
    run.save('pharmacy_master', master)
    run.save('designation_match_audit', audit)
    run.save('designation_match_review', audit[audit['match_status'] != 'matched'])
    # 팀원2용: 지정약국 원본을 기준으로 left join하므로 미매칭 약국도 사라지지 않습니다.
    matched = master[master['public_designation_status'].eq('matched_designated')]
    enriched = designated.merge(matched[['designation_id', 'pharmacy_id', 'latitude', 'longitude',
        'coordinate_plausible', 'designation_match_method', 'notes']], on='designation_id', how='left', validate='one_to_one')
    enriched['policy_start'] = '22:00'
    enriched['policy_end_next_day'] = '01:00'
    enriched['policy_hours_evidence'] = '15127987 제공기관 설명문: 개별 현장 영업확인 아님'
    run.save('public_night_enriched', enriched)
    run.save('pharmacy_location_review', master[~master['coordinate_plausible'] | ~master['is_busan_address'] | master['district'].isna()])
    hour_rows, status_rows = [], []
    for _, row in raw.iterrows():
        schedules = []
        for day, (sc, ec) in enumerate(zip(START, END), start=1):
            parsed = interval(row[sc], row[ec])
            schedules.append(parsed)
            hour_rows.append({'pharmacy_id': row['pmcyId'], 'day_code': day,
                'day_name': DAY_NAMES[day - 1], 'start_raw': row[sc], 'end_raw': row[ec],
                'start_minute': parsed[0] if parsed else None,
                'end_minute_unwrapped': parsed[1] if parsed else None,
                'hours_status': 'known' if parsed else 'unknown',
                'crosses_midnight': parsed[1] > 1440 if parsed else None})
        # 공휴일에는 실제 날짜와 전날의 공휴일 여부가 추가로 필요합니다.
        # day=8을 임의로 일요일 다음날에 붙이지 않고 원본 시간표만 전달합니다.
        for day in range(7):
            for hour in (0, 22, 23):
                status_rows.append({'pharmacy_id': row['pmcyId'], 'day_code': day + 1,
                    'hour': hour, 'schedule_status': opening_state(schedules[day], schedules[(day - 1) % 7], hour * 60),
                    'calendar_assumption': 'today_and_yesterday_are_non_holidays'})
    hours = pd.DataFrame(hour_rows)
    status = pd.DataFrame(status_rows)
    status = status.merge(master[['pharmacy_id', 'public_designation_status', 'has_notes_requires_review']], on='pharmacy_id', validate='many_to_one')
    # API상 closed와 지정 사업의 22~01시 정책 안내가 충돌하면 현장/기관 확인 대상으로 표시합니다.
    status['policy_schedule_conflict'] = status['public_designation_status'].eq('matched_designated') & status['schedule_status'].eq('closed')
    run.save('pharmacy_opening_hours', hours)
    run.save('pharmacy_night_weekly_status', status)
    run.save('designation_schedule_review', status[status['public_designation_status'].eq('matched_designated') & status['schedule_status'].ne('open')])
    completeness = hours.groupby(['day_code', 'day_name', 'hours_status']).size().rename('pharmacy_count').reset_index()
    run.save('pharmacy_hours_completeness', completeness)
    run.quality['pharmacy'] = {'api_rows': received_count, 'busan_rows': len(raw), 'excluded_non_busan': received_count - len(raw), 'master_rows': len(master),
        'matched_designated': int(master['public_designation_status'].eq('matched_designated').sum()),
        'designated_rows': len(designated), 'match_review_rows': int(audit['match_status'].ne('matched').sum()),
        'location_review_rows': int((~master['coordinate_plausible'] | ~master['is_busan_address'] | master['district'].isna()).sum()),
        'unknown_hours_rows': int(hours['hours_status'].eq('unknown').sum()),
        'full_week_schedule_complete': bool(hours['hours_status'].eq('known').all()),
        'monday_start_missing_count': int(raw[START[0]].fillna('').astype(str).str.strip().eq('').sum()),
        'designation_policy_conflict_slots': int(status['policy_schedule_conflict'].sum()),
        'note': '부산 전용 API 전 페이지. 공휴일 실제 일자 분석/현장 영업검증/행정동 공간조인은 별도.'}
    # 사용자가 승인한 보완: 지정심야약국만 화~금 공통 개점시각으로 월요일을 추정합니다.
    # 분석은 22시~익일01시 접근성이므로 오전 개점시각보다 심야운영·종료시각이 중요합니다.
    # raw 파일/원본 기준 시간표는 그대로 두고 분석용 파일에만 추정값과 근거를 표시합니다.
    from monday_analysis import build_monday_analysis
    build_monday_analysis(run, raw, master, hours, status)
    return master
