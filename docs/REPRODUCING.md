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

## 운영시간 예외와 안전한 최신 갱신 (2026-10-13 보완)

최신 데이터 교체는 프로젝트 루트에서 다음 명령을 사용합니다.

```bash
python reproduce/refresh_dashboard.py --mode latest
```

`run_pipeline.py --mode latest`도 이 격리 실행을 거칩니다. 별도 폴더에서 수집·분석·검증·HTML 검사를 마친 뒤에만 공개 payload와 CSV/HTML을 교체합니다. 실패하면 기존 시간표와 분석 수치를 유지하고 갱신 실패 상태만 표시합니다. `refresh_status.json`에 성공/실패·시각·실패 단계·로그 위치가 남습니다. 현재 공개 화면은 주기 운영 서비스가 아닌 기준일 자료 데모입니다. 화면에는 데이터 기준일을 표시하며 자동 갱신 예정 문구는 사용하지 않습니다.

- 시작·종료 시간에서 NMC 비고의 명확한 휴게 구간을 차감합니다.
- 요일별 복합 규칙은 `reproduce/dashboard_v3/schedule_exceptions.py`의 검토된 원문 조각이 일치할 때만 적용합니다. 문구가 달라지면 검토 대상으로 남깁니다.
- '점심시간 없음'은 휴무로 해석하지 않습니다. 모호한 안내·연도 없는 임시휴무는 임의 적용하지 않고 원문과 확인 필요 표시를 유지합니다.
- 월별 n번째 요일 휴무/영업은 시민 화면에서 실제 날짜로 판정합니다. 영업 회차라도 시간표가 없으면 확인 필요입니다. 날짜가 없는 주간 접근성 분석은 해당 예외 요일을 미상으로 처리하며 정책 시나리오의 매일 22–01시 가정과 구분합니다.
- 자정 이후 이어지는 전날 영업을 검사하고 그 영업의 출처·종료 시각·30분 이내 종료 안내를 표시합니다.
- 최종 원천 비고는 `nmc_pharmacies_latest.csv`, 해석 결과는 `schedule_exceptions_audit.csv`, 기관 연결 검토는 `nmc_identity_review_latest.csv`에서 볼 수 있습니다.

고정한 SGIS 원천의 임시 다운로드 링크가 만료될 수 있습니다. 2026-10-13 실제 실행에서는 같은 해시의 검증된 원본을 명시적으로 제공했습니다. 처음 실행하는 팀원도 공식 SGIS 포털에서 같은 연도·경계 기준의 파일을 확보하고 `download_inputs.py --mode snapshot --local-inputs ...`로 검증해야 합니다. 다른 기준 파일을 동일 원천으로 바꾸어 쓰면 안 됩니다. 최신 갱신 시 이미 존재하며 해시가 맞는 고정 연도 원천은 재사용합니다.

이번 최신 수집은 부산 API 1,701건, NMC 1,714건이며 합쳐진 지도 목록은 1,716곳입니다. 생활인구 공통 기준 월은 202607, OSM 실제 시각은 2026-10-12입니다. 현재 공개 결과와 기본 20260915 스냅샷 재실행 결과는 기준 원천이 달라 수치가 다릅니다. 자세한 기록은 `docs/VALIDATION_RUN.md`의 추가 검사 기록을 봅니다.

## 주소·좌표 대조와 보정 (2026-10-14)

`reconcile_locations.py`는 부산시 도로명주소 자료의 구·도로명·본번·부번이 정확히 일치하는 유일한 건물점을 대조합니다. 검토한 8개 시설의 규칙은 `pharmacy_location_overrides.json`에 있습니다. 이름만으로 연결하지 않으며 ID·이름·주소·전화와 기존 좌표를 검사합니다. 조건이 달라지면 보정을 중단합니다. 원본 API 파일은 그대로 보존합니다.

보정은 `osm_network.py` 이전의 약국 원장과 전체 지도 목록에 동일하게 적용됩니다. 도로망·거리행렬·접근성·민감도를 다시 계산한 뒤 `verify_location_publication.py`가 양쪽 좌표와 구 분류를 검사합니다. 전체 재실행 순서에도 포함됩니다. 최신 수집을 하지 않고 같은 입력으로 위치만 보정한 실행 기록은 `validation/coordinate_correction_run.json`입니다.

루트 `coordinate_corrections.csv`는 8개 시설의 변경 전후, `coordinate_building_review.csv`는 자동 이동하지 않은 추가 21개 거리 차이 기록, `coordinate_validation.json`은 전체 1,716곳 중 주소 건물점 정확 일치 1,693곳의 대조 요약입니다. 건물 대표점 보정은 약국 출입구·실제 영업 현장 검증과 다릅니다. 다른 건물점 거리 차이도 위치 오류로 확정하지 않습니다.
