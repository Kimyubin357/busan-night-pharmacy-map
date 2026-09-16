"""팀원 1 — 인증키 없이 받을 수 있는 공식 파일과 생활인구 계산.

원본은 그대로 보존하고, 정제/계산은 별도의 DataFrame에서 진행합니다.
생활인구는 통신사가 이미 추정한 월별 일평균입니다. 이 코드가 통신 신호로
사람 수를 새로 추정하거나 약국 이용 환자 수를 계산하는 것은 아닙니다.
"""
from __future__ import annotations
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

WAVE = 'https://data.busan.go.kr/bdip/opendata/'


def request_bytes(url, payload=None):
    """GET 또는 JSON POST. 인증키가 URL에 있어도 예외 메시지로 노출하지 않습니다."""
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = {'User-Agent': 'BusanTeam1Research/1.0'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # 인증 오류는 재시도로 해결되지 않으므로 즉시 알립니다.
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'HTTP {error.code}: 인증/서버 상태 확인 필요') from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('네트워크 요청 실패: 주소 또는 연결 상태 확인 필요') from None
        time.sleep(2 ** attempt)


class Run:
    """실행마다 별도 폴더에 저장하여 이전 결과를 새 결과로 오인하지 않게 합니다."""
    def __init__(self, root: Path):
        self.root = root
        self.id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.raw = root / 'data' / 'raw' / self.id
        self.out = root / 'data' / 'processed' / self.id
        self.reports = root / 'reports' / self.id
        for folder in (self.raw, self.out, self.reports):
            folder.mkdir(parents=True, exist_ok=True)
        self.sources = []
        self.quality = {'run_id': self.id, 'stages': {}, 'tables': {}}

    def inspect(self, label, frame):
        """요청하신 head(), 컬럼, dtype, 결측치 검사를 화면과 파일에 함께 남깁니다."""
        details = {
            'rows': len(frame), 'columns': list(frame.columns),
            'dtypes': {c: str(t) for c, t in frame.dtypes.items()},
            'missing': {c: int(n) for c, n in frame.isna().sum().items()},
            'blank_strings': {c: int(frame[c].astype('string').str.strip().eq('').sum()) for c in frame},
        }
        self.quality['tables'][label] = details
        preview = (f'\n[{label}] {len(frame):,}행 × {len(frame.columns)}열\n'
                   + json.dumps(details, ensure_ascii=False, indent=2)
                   + '\nhead(5):\n' + frame.head(5).to_string(index=False) + '\n')
        print(preview, flush=True)
        with (self.reports / 'head_preview.txt').open('a', encoding='utf-8') as stream:
            stream.write(preview)

    def save(self, label, frame):
        self.inspect(label, frame)
        # UTF-8 BOM: Excel에서 한국어가 깨지는 문제를 줄입니다.
        frame.to_csv(self.out / f'{label}.csv', index=False, encoding='utf-8-sig')

    def finish(self):
        for filename, value in [('sources.json', self.sources), ('quality_report.json', self.quality)]:
            (self.reports / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        # 최신 실행 위치와 각 단계의 성공 여부만 기록합니다. 이전 성공 파일을 재사용하지 않습니다.
        pointer = {**self.quality, 'output_dir': str(self.out), 'report_dir': str(self.reports)}
        (self.root / 'reports' / 'latest_run.json').write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding='utf-8')


def download_wave(run, pk, label, extension):
    """사이트 FILE 탭이 사용하는 공개 메타데이터에서 실제 다운로드 URL을 찾습니다."""
    metadata = json.loads(request_bytes(WAVE + 'selectFileData.do', {'publicdatapk': pk}))
    (run.raw / f'{label}_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    files = [item for item in metadata.get('fileList', [])
             if str(item.get('ext', '')).lower() == extension and item.get('downurl')]
    if not files:
        raise ValueError(f'{label}: 다운로드 가능한 {extension} 파일 없음')
    # 여기서는 메타데이터 수정일이 가장 최근인 파일을 선택합니다. 실제 데이터 기간은 읽은 뒤 검증합니다.
    chosen = max(files, key=lambda item: str(item.get('updatedAt') or ''))
    content = request_bytes(chosen['downurl'])
    path = run.raw / f'{label}.{extension}'
    path.write_bytes(content)
    run.sources.append({
        'dataset_id': pk, 'title': chosen.get('title'), 'metadata_updated_at': chosen.get('updatedAt'),
        'download_url': chosen['downurl'], 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
        'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content), 'raw_file': str(path),
        'description': chosen.get('description'),
    })
    return content


def collect_designated(run):
    """지정약국 명단을 받습니다. CSV에 없는 좌표/영업시간을 임의로 만들지 않습니다."""
    content = download_wave(run, '15127987', 'public_night_original', 'csv')
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            frame = pd.read_csv(io.BytesIO(content), encoding=encoding, dtype='string')
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('공공심야약국 CSV 인코딩을 확인하세요')
    frame.columns = frame.columns.str.strip()
    run.inspect('public_night_raw', frame)
    names = {'연번': 'designation_id', '약국명': 'name', '소재지(도로명)': 'address',
             '전화번호': 'phone', '관리지역': 'district', '데이터 기준일': 'reference_date'}
    missing = set(names) - set(frame)
    if missing:
        raise ValueError(f'지정약국 컬럼 변경: {sorted(missing)}')
    result = frame.rename(columns=names).copy()
    for col in names.values():
        result[col] = result[col].str.strip()
    if result['designation_id'].isna().any() or result['designation_id'].duplicated().any():
        raise ValueError('지정약국 연번 누락/중복: 원본 확인 필요')
    # 정책 안내문에 적힌 22~01시는 별도 메타데이터에 보존합니다.
    # 이것을 API에서 확인한 개별 약국의 실제 영업시간으로 덮어쓰지 않습니다.
    result['designation_source'] = '부산광역시_공공심야약국_15127987'
    run.save('public_night_pharmacies', result)
    run.save('public_night_district_counts', result.groupby('district').size().rename('designated_count').reset_index())
    return result


def process_population(run, frame):
    """월·행정동·시간 단위의 관측값을 정제하고 심야 3개 시간대 평균을 계산합니다."""
    run.inspect('population_raw', frame)
    rename = {'기준년월': 'month', '행정동코드': 'dong_code', '행정동명': 'dong_name',
              '시간대': 'hour', '평균주거인구수': 'resident',
              '평균직장인구수': 'worker', '평균방문인구수': 'visitor'}
    if set(rename) - set(frame):
        raise ValueError(f'생활인구 컬럼 변경: {sorted(set(rename) - set(frame))}')
    df = frame[list(rename)].rename(columns=rename).copy()
    for col in ('month', 'dong_code', 'dong_name'):
        df[col] = df[col].astype('string').str.strip()
    if not df['month'].str.fullmatch(r'\d{6}').fillna(False).all():
        raise ValueError('잘못된 기준년월')
    pd.to_datetime(df['month'], format='%Y%m', errors='raise')
    if not df['dong_code'].str.fullmatch(r'26\d{8}').fillna(False).all():
        raise ValueError('부산 10자리 행정동코드가 아닌 값 존재')
    df['hour'] = pd.to_numeric(df['hour'].astype('string').str.replace('시', '', regex=False), errors='raise')
    if not df['hour'].isin(range(24)).all():
        raise ValueError('시간대가 0~23 정수가 아님')
    df['hour'] = df['hour'].astype(int)
    for col in ('resident', 'worker', 'visitor'):
        df[col] = pd.to_numeric(df[col], errors='raise')
        if df[col].isna().any() or not df[col].ge(0).all() or not df[col].lt(float('inf')).all():
            raise ValueError(f'{col}: 인구 결측/음수/비정상 값')
    if df[['month', 'dong_code', 'hour']].isna().any().any():
        raise ValueError('생활인구 식별정보 결측')
    if df.duplicated(['month', 'dong_code', 'hour']).any():
        raise ValueError('월·행정동·시간 키 중복: 합산하면 이중계산되므로 중단')
    groups = df.groupby(['month', 'dong_code'])
    if not groups['hour'].nunique().eq(24).all() or not groups['dong_name'].nunique(dropna=False).eq(1).all():
        raise ValueError('월·행정동별 24시간 미완비 또는 동명 충돌')
    # 제공기관 설명상 주거/직장/방문 분류를 합한 잠재 노출 인구입니다.
    # 서로 다른 시간의 동일인을 식별할 수 없으므로 시간 합계를 순인구로 부르면 안 됩니다.
    df['total_population_proxy'] = df[['resident', 'worker', 'visitor']].sum(axis=1)
    # 원본에 공백뿐인 동명이 실제 존재합니다. 행정동코드는 남아 있으므로
    # 그 행을 삭제하거나 인구를 0으로 만들지 않습니다. 공식 동명은 추정하지 않습니다.
    df['dong_name_raw'] = df['dong_name']
    df['dong_name_missing'] = df['dong_name'].isna() | df['dong_name'].eq('')
    df['district'] = df['dong_name'].str.extract(r'^(\S+[구군])\s', expand=False)
    df['district_code'] = df['dong_code'].str[:5]
    # 같은 원본에서 확인되는 5자리 시군구코드-구군명의 일대일 관계만 사용합니다.
    mapping = df.dropna(subset=['district'])[['district_code', 'district']].drop_duplicates()
    if mapping['district_code'].duplicated().any():
        raise ValueError('시군구코드와 구군명 매핑 충돌')
    district_map = mapping.set_index('district_code')['district']
    df['district_from_code'] = df['district'].isna()
    df['district'] = df['district'].fillna(df['district_code'].map(district_map))
    if df['district'].isna().any():
        raise ValueError('행정동코드로도 구군 확인 불가')
    # 아래 표시는 공식 동명이 아니라 식별용 라벨입니다. 원본 공백과 플래그도 보존합니다.
    df.loc[df['dong_name_missing'], 'dong_name'] = '동명미제공_' + df.loc[df['dong_name_missing'], 'dong_code']
    run.save('population_missing_dong_names', df[df['dong_name_missing']][
        ['month', 'dong_code', 'dong_name_raw', 'dong_name', 'district', 'hour']])
    df = df.sort_values(['month', 'dong_code', 'hour']).reset_index(drop=True)
    run.save('living_population_hourly', df)
    # 22시, 23시, 00시의 월평균값을 동등 가중 평균합니다.
    # 날짜 자료가 없어 실제 특정 날짜 밤이나 월말 익일을 재구성하지 않습니다.
    night = df[df['hour'].isin([22, 23, 0])]
    metrics = ['resident', 'worker', 'visitor', 'total_population_proxy']
    summary = night.groupby(['month', 'dong_code', 'dong_name', 'district'])[metrics].mean().reset_index()
    summary = summary.rename(columns={c: 'night_mean_' + c for c in metrics})
    summary['hours_used'] = '22,23,00'
    summary['unit'] = '명: 월평균 시간대값 3개의 산술평균(순방문자수 아님)'
    run.save('living_population_night_by_dong', summary)
    latest = summary[summary['month'].eq(summary['month'].max())].copy()
    run.save('living_population_night_latest', latest)
    district = summary.groupby(['month', 'district'])[['night_mean_' + c for c in metrics]].sum().reset_index()
    run.save('living_population_night_by_district', district)
    coverage = df.groupby('month').agg(rows=('hour', 'size'), dong_count=('dong_code', 'nunique')).reset_index()
    run.save('population_month_coverage', coverage)
    # 행정동 신설/폐지와 명칭 변화는 시계열 비교 전에 팀원이 확인할 수 있게 별도 전달합니다.
    changes = []
    previous = None
    for month, part in df.groupby('month', sort=True):
        current = dict(part[['dong_code', 'dong_name']].drop_duplicates().itertuples(index=False, name=None))
        if previous is not None:
            for code in sorted(set(current) | set(previous)):
                if current.get(code) != previous.get(code):
                    changes.append({'month': month, 'dong_code': code, 'before': previous.get(code), 'after': current.get(code)})
        previous = current
    run.save('population_dong_changes', pd.DataFrame(changes, columns=['month', 'dong_code', 'before', 'after']))
    run.quality['population'] = {'period_min': df['month'].min(), 'period_max': df['month'].max(),
        'rows': len(df), 'latest_dongs': len(latest), 'duplicate_key_count': 0,
        'missing_dong_name_rows': int(df['dong_name_missing'].sum()),
        'note': '월별 시간대 평균; 요일/일자/약국 이용수요 자료 아님. 2026 약국과 결합 시 시점 차이 명시.'}
    return df


def collect_population(run):
    content = download_wave(run, 'PD_LP00003', 'population_original', 'xlsx')
    # openpyxl은 읽기에만 사용합니다. 결과는 팀원이 바로 불러올 수 있는 CSV입니다.
    frame = pd.read_excel(io.BytesIO(content), dtype='string', engine='openpyxl')
    return process_population(run, frame)
