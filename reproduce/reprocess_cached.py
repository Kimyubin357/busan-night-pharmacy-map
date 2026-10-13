"""다운로드 원본을 해시 검증 후 새 실행 폴더에서 재처리합니다.
인증키나 API 재요청 없이 정제 규칙 수정 결과를 재현할 때 사용합니다.
이전 결과는 덮어쓰지 않습니다. python reprocess_cached.py
"""
import hashlib
import json
import shutil
from pathlib import Path
import pandas as pd
from public_data import Run, process_population
from pharmacy_data import parse_page, process_pharmacies


def main():
    root = Path(__file__).resolve().parent
    previous = json.loads((root / 'reports/latest_run.json').read_text())
    old_raw = root / 'data/raw' / previous['run_id']
    old_reports = root / previous['report_dir']
    sources = json.loads((old_reports / 'sources.json').read_text())
    # 먼저 모든 원본 해시를 확인합니다. 검증 실패 시 새 결과를 만들지 않습니다.
    for source in sources:
        file = root / source['raw_file'] if 'raw_file' in source else old_raw / f"pharmacy_api_page_{source['page']:03}.json"
        if hashlib.sha256(file.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('원본 해시 불일치: ' + file.name)
    run = Run(root)
    run.quality['reprocessed_from'] = previous['run_id']
    for file in old_raw.iterdir():
        if file.is_file():
            shutil.copy2(file, run.raw / file.name)
    for source in sources:
        if 'raw_file' in source:
            source['raw_file'] = str(run.raw / Path(source['raw_file']).name)
    run.sources = sources
    try:
        # 명단 CSV는 원본으로 재독해하고 컬럼 이름만 일관되게 바꿉니다.
        path = run.raw / 'public_night_original.csv'
        try:
            d = pd.read_csv(path, dtype='string', encoding='utf-8-sig')
        except UnicodeDecodeError:
            d = pd.read_csv(path, dtype='string', encoding='cp949')
        run.inspect('public_night_raw', d)
        d = d.rename(columns={'연번':'designation_id','약국명':'name','소재지(도로명)':'address',
                             '전화번호':'phone','관리지역':'district','데이터 기준일':'reference_date'})
        for c in d:
            d[c] = d[c].str.strip()
        if d.designation_id.isna().any() or not d.designation_id.is_unique:
            raise ValueError('지정명단 ID 오류')
        d['designation_source'] = '부산광역시_공공심야약국_15127987'
        run.save('public_night_pharmacies', d)
        run.save('public_night_district_counts', d.groupby('district').size().rename('designated_count').reset_index())
        run.quality['stages']['designated'] = 'complete'
        process_population(run, pd.read_excel(run.raw / 'population_original.xlsx', dtype='string'))
        run.quality['stages']['population'] = 'complete'
        rows, totals = [], set()
        for source in sorted((x for x in sources if 'page' in x), key=lambda x: x['page']):
            total, items = parse_page((run.raw / f"pharmacy_api_page_{source['page']:03}.json").read_bytes())
            totals.add(total)
            rows.extend(items)
        raw = pd.DataFrame(rows)
        if totals != {len(raw)} or raw.pmcyId.isna().any() or not raw.pmcyId.is_unique:
            raise ValueError('API 원본 페이지 건수/ID 불일치')
        run.save('pharmacy_api_all_raw_columns', raw)
        process_pharmacies(run, raw, d)
        run.quality['stages']['pharmacy'] = 'complete'
        # 재처리 날짜와 API 수집 날짜는 다를 수 있으므로 원본 수집 날짜를 유지합니다.
        # API 자료의 정확한 수집시각은 sources.json에 원래 값 그대로 보존됩니다.
        master_path = run.out / 'pharmacy_master.csv'
        master = pd.read_csv(master_path, dtype='string')
        api_sources = [x for x in sources if 'page' in x]
        from datetime import datetime
        day = datetime.fromisoformat(api_sources[0]['retrieved_at_utc']).astimezone().date().isoformat()
        master['api_collected_date'] = day
        master.to_csv(master_path, index=False, encoding='utf-8-sig')
    except Exception as error:
        run.quality['stages']['reprocess'] = 'failed: ' + str(error)
        raise
    finally:
        run.finish()
    print('재처리 결과:', run.out)


if __name__ == '__main__':
    main()
