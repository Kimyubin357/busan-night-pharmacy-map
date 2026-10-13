# 원천부터 재현하기

## 환경

Python 3.12와 Node.js가 필요합니다. `requirements.txt`는 검사에 사용한 Python 패키지 버전입니다. RAM 최소 8GB, 권장 16GB 이상, 빈 디스크 최소 5GB를 준비합니다. 전체 한국 OSM PBF와 SGIS ZIP 등 약 0.5GB 이상을 내려받습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd reproduce
```

## 당시 원천 스냅샷으로 재계산

```bash
python download_inputs.py --mode snapshot
python run_pipeline.py --mode snapshot
```

약국 API 전 페이지 JSON, NMC 전 페이지 XML, 공공심야 명단 CSV, 생활인구 원본 XLSX는 `snapshots/20260915/`에 보관합니다. 매번 정제 결과를 새로 계산하며 원본 SHA-256을 확인합니다. 큰 도로명주소·연령인구·SGIS·OSM 파일은 `input_catalog.json`의 URL과 해시를 이용합니다. 다운로드 대상이 과거와 달라지면 중단합니다.

외부 제공기관이 과거 파일을 더 이상 제공하지 않으면 같은 SHA-256의 원본이 필요합니다. 원천 폴더를 직접 지정할 수도 있습니다.

```bash
python download_inputs.py --mode snapshot --local-inputs /path/to/original-input-folder
python run_pipeline.py --mode snapshot
```

원천 폴더의 상대 위치는 `input_catalog.json`의 `local_path`에 적혀 있습니다. 코드는 부모 프로젝트 폴더를 암묵적으로 읽지 않습니다. 수동 다운로드 파일도 검사에 통과해야 하며 최신 파일을 과거 파일로 바꿔 쓰지 않습니다.

## 외부 API를 다시 조회하는 최신 모드

```bash
python download_inputs.py --mode latest
python run_pipeline.py --mode latest
```

부산·NMC API를 새로 조회하고 생활인구·연령인구 파일의 최신 메타데이터를 가져옵니다. 새 NMC 원본은 실행별 폴더에 저장하므로 이전 조회 페이지와 섞이지 않습니다. SGIS 인구·경계는 명시한 2024/2025년 공간 배분 기준을 유지하고, OSM은 latest 파일을 받습니다. 외부 자료 변경으로 결과가 달라질 수 있습니다. 인증·컬럼·행정동 연결·정책 예외 검사가 실패하면 다음 단계와 최종 게시를 중단합니다.

`config.json`의 `population_month`는 기본적으로 `latest_common`입니다. 시간별 생활인구와 연령별 파일에 공통으로 존재하는 가장 최근 월을 선택합니다. `202512` 같은 고정 월도 지정할 수 있지만 두 파일에 모두 있어야 합니다. 격자 배분, 최종 payload와 화면의 기준 월은 선택된 값에서 만들어집니다.

OSM 기준시각은 PBF 헤더의 실제 replication timestamp를 읽습니다. 파일이 바뀌면 해시가 달라져 파싱 캐시도 새로 만듭니다. 날짜를 파일명만 보고 추정하지 않습니다.

## 실행 순서와 자동 검증

`run_pipeline.py`가 다음을 순서대로 실행합니다.

1. 기간·스냅샷·이동한 경로의 회귀 검사
2. 부산 약국·공공심야·생활인구 원천 수집 또는 해시 검사 후 재독해
3. 공통 기준 월 선택, 원천 파일 해시·조회일·OSM 실제 시각 기록
4. 월요일 보완, 공급·수요 정리, 정책 시간표 생성
5. HIRA 비교 및 NMC 기관·시간 대조
6. SGIS 공간조인·격자 배분과 동별 시간별 총량 보존 검사
7. OSM 파싱·보행 그래프·약국 및 출발점 연결
8. 격자×약국 거리행렬·경로 불확실성 생성
9. 접근성 및 후보 점수 생성
10. 모든 후보 점수 독립 재집계, 20개 출발점의 정방향 최단경로 대조
11. 3·4·5km/h, 일요일 결측, 수요 배분 민감도 재계산 및 기준 점수 일치 검사
12. 독립 payload·감사표 게시, 단일 HTML 생성, 보고서 생성 검사

도로 거리행렬은 5km/h·15분 민감도 계산까지 빠짐없이 비교하기 위해 1250m까지 생성합니다. 주모형은 기존 4km/h·5/10/15분이며 브라우저에는 이에 필요한 1000m 범위만 전달합니다.

`reports/run_context.json`에는 선택 기준과 입력 해시가, `reports/pipeline_run.json`에는 각 단계 종료코드·시간·최종 산출물 해시가 남습니다. 이전 성공 파일을 이번 성공으로 기록하지 않습니다. 최종 검증 성공 전에 루트 payload를 덮어쓰지 않습니다.

## 산출물과 해석

- 루트 `dashboard_data.json.gz`: 지도 목록과 분석·검증·민감도를 포함한 독립 화면 데이터
- 루트 `dist/index.html`: 브라우저에서 볼 단일 HTML
- 루트 `sensitivity_results.json` / `sensitivity_rankings.csv`: 가정별 후보 점수와 순위
- 루트 `field_validation_plan.csv`: 현장·전화 확인 체크리스트. 현재는 미실시
- `dashboard_v3/validation.json`: 수치·경로 알고리즘 일치 검사. 현장 검증과 구분

수집·원천 파싱 시간을 포함한 전체 실행시간은 장비와 네트워크에 따라 달라집니다. 이 프로젝트의 실제 로컬 검사 기록은 `docs/VALIDATION_RUN.md`에 보관합니다. 약 142MB 거리행렬, 약 36MB 불확실성 배열, OSM 그래프·PBF·SGIS ZIP은 Git에 넣지 않고 재생성합니다.

스냅샷 재실행에서는 기준 지표와 후보 점수가 재현되어야 합니다. 실행 시각·로그·gzip 헤더 등으로 파일 해시는 실행마다 달라질 수 있습니다. 현재 저장된 payload에서 HTML만 재생성하는 경로는 `python build_html.py`입니다.
