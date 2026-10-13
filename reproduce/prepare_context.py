"""시간별·연령별 자료의 공통 월을 선택하고 원천 파일 해시와 조회일을 기록합니다."""
from pathlib import Path
import json, os
import pandas as pd
import osmium
from pipeline_context import ROOT, config, sha256, processed_source, utc_now

def select_month(hourly_months, age_months, requested):
    common=sorted(set(hourly_months)&set(age_months))
    month=common[-1] if common and requested=='latest_common' else str(requested)
    if month not in common:raise ValueError(f'시간·연령 자료의 공통 기준 월 없음: {month}; 가능한 월 {common}')
    return month,common

def main():
    cfg = config(); source = processed_source()
    catalog=json.loads((ROOT/'input_catalog.json').read_text())
    pop_entry=catalog['team2/update_20260915/raw/sgis_grid_population.zip']
    boundary_entry=catalog['team2/update_20260915/raw/sgis_dong.zip']
    if cfg['grid_year']!=pop_entry['grid_year'] or cfg['boundary_date']!=boundary_entry['boundary_date']:
        raise ValueError('SGIS 기준을 바꾸려면 input_catalog.json의 원천 URL·해시·실제 기준도 함께 갱신해야 합니다.')
    hourly = pd.read_csv(source / 'living_population_hourly.csv', dtype={'month': str, 'dong_code': str})
    age = pd.read_excel(ROOT / 'team2/inputs/PD_LP00002.xlsx', dtype=str)
    month,common=select_month(hourly.month,age['기준년월'],cfg['population_month'])
    night = pd.read_csv(source / 'living_population_night_by_dong.csv', dtype={'month': str, 'dong_code': str})
    selected = night[night.month.eq(month)]
    if selected.empty: raise ValueError('선택 월의 심야 생활인구 없음')
    selected.to_csv(source / 'living_population_night_latest.csv', index=False, encoding='utf-8-sig')
    pbf = ROOT / 'team2/osm' / cfg['osm_filename']
    reader = osmium.io.Reader(str(pbf))
    try: stamp = reader.header().get('osmosis_replication_timestamp') or None
    finally: reader.close()
    master = pd.read_csv(source / 'pharmacy_master.csv', dtype=str)
    files = [ROOT / 'team2/inputs/15028854.csv', ROOT / 'team2/inputs/PD_LP00002.xlsx', pbf]
    files += sorted((ROOT / 'team2/update_20260915/raw').glob('sgis_*.zip'))
    files.append(ROOT/'team2/update_20260915/hira_busan_pharmacy_details.csv')
    raw = ROOT / 'data/raw' / json.loads((ROOT / 'reports/latest_run.json').read_text())['run_id']
    files += sorted(p for p in raw.glob('*') if p.is_file())
    manifest = {str(p.relative_to(ROOT)): {'sha256': sha256(p), 'bytes': p.stat().st_size} for p in files}
    ctx = {**cfg, 'population_month': month, 'population_month_candidates': common,
           'mode':os.environ.get('BUSAN_RUN_MODE','snapshot'),'created_at': utc_now(), 'pharmacy_collected_at': master.api_collected_date.max(),
           'osm_timestamp': stamp, 'osm_date': stamp[:10] if stamp else None,
           'osm_sha256': sha256(pbf), 'inputs': manifest}
    (ROOT / 'reports/run_context.json').write_text(json.dumps(ctx, ensure_ascii=False, indent=2))
    print('기준 월', month, 'OSM 실제 기준시각', stamp or '헤더에 없음', '입력 해시', len(manifest))

if __name__ == '__main__': main()
