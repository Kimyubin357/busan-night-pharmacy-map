"""수집 결과를 원본과 독립적으로 대조합니다. 실행: python verify_outputs.py

단순히 파일이 존재하는지만 검사하지 않습니다. API 행 집합, 지정약국 관계,
엑셀 원본으로 다시 계산한 심야평균, 구군 합계, 원본 해시까지 비교합니다.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pharmacy_data import START


def main():
    root = Path(__file__).resolve().parent
    latest = json.loads((root / 'reports/latest_run.json').read_text())
    output = Path(latest['output_dir'])
    reports = Path(latest['report_dir'])
    raw_dir = root / 'data/raw' / latest['run_id']
    assert all(v == 'complete' for v in latest['stages'].values()), '먼저 모든 수집 단계를 완료하세요'
    checks = []

    def read(name):
        return pd.read_csv(output / (name + '.csv'), dtype={'pharmacy_id': 'string', 'dong_code': 'string', 'month': 'string'})

    master = read('pharmacy_master')
    original = read('pharmacy_api_all_raw_columns')
    expected = original[original['pmcyLctnRoadNmAddr'].str.match(r'^부산(?:광역시)?\s')]
    assert set(master['pharmacy_id']) == set(expected['pmcyId'])
    assert master['pharmacy_id'].is_unique
    assert len(read('pharmacy_excluded_non_busan')) + len(master) == len(original)
    checks.append('원본 전체 = 부산 약국 + 제외 행; 부산 약국 ID 집합 일치·중복 없음')
    designated = read('public_night_pharmacies')
    enriched = read('public_night_enriched')
    assert len(enriched) == len(designated)
    assert enriched['pharmacy_id'].notna().all() and enriched['pharmacy_id'].is_unique
    joined = enriched.merge(master, on='pharmacy_id', validate='one_to_one', suffixes=('_d', '_m'))
    assert np.allclose(joined['latitude_d'], joined['latitude_m'])
    assert np.allclose(joined['longitude_d'], joined['longitude_m'])
    checks.append('지정약국 전 건 일대일 연결·전체 약국과 좌표 일치')

    # 정제 코드의 함수 호출 대신 원본 한국어 컬럼에서 별도로 평균을 계산합니다.
    pop = pd.read_excel(raw_dir / 'population_original.xlsx', dtype='string')
    pop['total_check'] = pop[['평균주거인구수', '평균직장인구수', '평균방문인구수']].astype(float).sum(axis=1)
    selected = pop[pop['시간대'].isin(['22시', '23시', '00시'])]
    calculated = selected.groupby(['기준년월', '행정동코드'])['total_check'].mean().sort_index()
    saved = read('living_population_night_by_dong').set_index(['month', 'dong_code'])['night_mean_total_population_proxy'].sort_index()
    assert list(calculated.index) == list(saved.index)
    assert np.allclose(calculated.values, saved.values, rtol=0, atol=1e-6)
    assert len(read('living_population_hourly')) == len(pop)
    dong = read('living_population_night_by_dong')
    expected_district = dong.groupby(['month', 'district'])['night_mean_total_population_proxy'].sum().sort_index()
    saved_district = read('living_population_night_by_district').set_index(['month', 'district'])['night_mean_total_population_proxy'].sort_index()
    assert list(expected_district.index) == list(saved_district.index)
    assert np.allclose(expected_district.values, saved_district.values, rtol=0, atol=1e-6)
    checks.append('엑셀 원본에서 독립 재계산한 모든 월·동 심야 평균 및 구군 합계 일치')

    hours = read('pharmacy_opening_hours')
    states = read('pharmacy_night_weekly_status')
    assert len(hours) == len(master) * 8
    assert len(states) == len(master) * 7 * 3
    assert not hours.duplicated(['pharmacy_id', 'day_code']).any()
    assert not states.duplicated(['pharmacy_id', 'day_code', 'hour']).any()
    checks.append('약국×8종 요일 시간표, 약국×7요일×3시간 상태표의 키/행 수 일치')
    sources = json.loads((reports / 'sources.json').read_text())
    for source in sources:
        file = Path(source['raw_file']) if 'raw_file' in source else raw_dir / f"pharmacy_api_page_{source['page']:03}.json"
        assert hashlib.sha256(file.read_bytes()).hexdigest() == source['sha256']
    checks.append('모든 원본 파일의 SHA-256 해시 일치')

    # 추가 품질지표를 기존 실행 보고서에 반영합니다. 영업시간 값은 변경하지 않습니다.
    latest['pharmacy'].update({
        'full_week_schedule_complete': bool(hours['hours_status'].eq('known').all()),
        'monday_start_missing_count': int(expected[START[0]].fillna('').astype(str).str.strip().eq('').sum()),
        'designation_policy_conflict_slots': int(states['policy_schedule_conflict'].sum()),
    })
    quality = json.loads((reports / 'quality_report.json').read_text())
    quality['pharmacy'] = latest['pharmacy']
    (reports / 'quality_report.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding='utf-8')
    (root / 'reports/latest_run.json').write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding='utf-8')
    text = '\n'.join('PASS: ' + c for c in checks) + '\n'
    (reports / 'verification.txt').write_text(text, encoding='utf-8')
    print(text)
    print('API 원본:', len(original), '부산 약국:', len(master), '지정약국:', len(enriched))
    print('생활인구 원본:', len(pop), '월·동별 심야 평균:', len(saved))


if __name__ == '__main__':
    main()
