#!/usr/bin/env python3
"""팀원 1 실행 파일: python team1_pipeline.py

진행 순서: 지정심야약국 → 생활인구 → 전체 약국 API → 지정 여부/시간 정제.
각 단계에서 head(), 컬럼, dtype, 결측치를 출력하고 실행 폴더에 보존합니다.
한 단계가 실패해도 독립적인 다른 자료는 계속 처리합니다. 실패를 성공으로
감추지 않도록 최종 종료코드는 실패/인증키 대기일 때 2입니다.
"""
import argparse
from pathlib import Path
from public_data import Run, collect_designated, collect_population
from pharmacy_data import read_key, collect_api, process_pharmacies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-only', action='store_true', help='인증키 없이 공개 파일 두 종류만 실행')
    args = parser.parse_args()
    run = Run(Path(__file__).resolve().parent)
    designated = None
    try:
        try:
            designated = collect_designated(run)
            run.quality['stages']['designated'] = 'complete'
        except Exception as error:
            run.quality['stages']['designated'] = 'failed: ' + str(error)
            print('지정명단 실패:', str(error), flush=True)
        try:
            collect_population(run)
            run.quality['stages']['population'] = 'complete'
        except Exception as error:
            run.quality['stages']['population'] = 'failed: ' + str(error)
            print('생활인구 실패:', str(error), flush=True)
        key = read_key(run.root)
        if args.public_only:
            run.quality['stages']['pharmacy'] = 'skipped_public_only'
        elif not key:
            run.quality['stages']['pharmacy'] = 'pending_api_key_in_dotenv'
            print('약국 API 대기: .env에 활용승인된 DATA_GO_KR_SERVICE_KEY를 입력하세요.', flush=True)
        else:
            try:
                raw = collect_api(run, key)
                if designated is None:
                    raise ValueError('API 원본은 수집했지만 지정명단 실패로 통합하지 못함')
                process_pharmacies(run, raw, designated)
                run.quality['stages']['pharmacy'] = 'complete'
            except Exception as error:
                # 예상치 못한 외부 오류도 인증키 문자열은 화면/파일에 남기지 않습니다.
                from urllib.parse import quote
                message = str(error).replace(key, '[REDACTED]').replace(quote(key, safe=''), '[REDACTED]')
                run.quality['stages']['pharmacy'] = 'failed: ' + message
                print('약국 처리 실패:', message, flush=True)
    finally:
        run.finish()
    print('\n단계 결과:', run.quality['stages'], flush=True)
    print('결과 폴더:', run.out, flush=True)
    print('검증 보고서:', run.reports, flush=True)
    return 0 if all(v in ('complete', 'skipped_public_only') for v in run.quality['stages'].values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
