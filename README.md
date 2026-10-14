# 부산 심야약국 접근성 지도

부산의 심야 약국 접근성을 100m 격자와 보행 도로망으로 분석하고, 공공심야약국 추가 지정 후보와 시민용 운영 약국 찾기를 한 화면에 제공합니다.

**[배포된 대시보드 열기](https://busan-night-pharmacy-map-768810209035.asia-east1.run.app/)** — DB 없이 Cloud Run에서 제공합니다. 자료 기준일은 화면에 표시하며, 실시간 운영정보 갱신 서비스는 아닙니다. 배포 구성·재배포·비용 기준은 [Cloud Run 안내](docs/CLOUD_RUN.md)를 확인하세요.

## 바로 실행

Python 외에는 설치할 필요가 없습니다.

```bash
python3 serve.py --port 8000
```

브라우저에서 <http://localhost:8000>을 엽니다. 이 서버는 gzip 전송·ETag·내용 해시 파일 캐시를 적용합니다. 기존 `python3 -m http.server 8000 --directory dist`로도 화면은 실행되지만, 코드·스타일의 HTTP 압축과 장기 캐시는 적용되지 않습니다.

한 파일로 전달할 때는 `dist/downloads/busan-night-pharmacy.html`을 사용합니다. 데이터·코드·글꼴이 내장된 독립 HTML입니다. 도로 배경 타일은 인터넷 연결이 필요하고 `file://`에서는 제공처 제한으로 403이 날 수 있습니다.

## 화면 수정 후 다시 만들기

`dashboard_data.json.gz`는 지도 약국 1,716곳과 최종 분석 결과를 포함한 독립 payload입니다. 외부 프로젝트 폴더를 참조하지 않습니다.

```bash
python3 build_html.py
python3 check_build.py
node check_report.cjs
node check_finder.cjs
```

웹용 `dist/index.html`과 독립 실행용 `dist/downloads/busan-night-pharmacy.html`을 함께 만듭니다. 이 경로는 원천 수집이나 거리행렬 재계산을 하지 않습니다. `python3 build_html.py --export /path/to/demo.html`은 독립 HTML을 추가 저장합니다.

웹 게시에는 **`dist` 전체**가 필요합니다. `index.html`만 복사하면 분리된 자료를 읽지 못합니다. 처음에는 요약 자료만 읽고, 운영 약국 찾기와 접근성 지도는 해당 탭을 처음 열 때 자료·코드를 불러옵니다. 동일한 자료 요청은 페이지 안에서 재사용합니다. 파일명에 내용 해시를 넣어 갱신 시 이전 캐시와 섞이지 않게 합니다. 원천 재수집 게시에서는 새 파일을 먼저 복사하고 HTML을 교체하며, 기존 해시 파일은 이미 열린 세션을 위해 유지합니다.

## 저장소 구성

- `dist/index.html`, `dist/assets/` — 탭별로 자료를 읽는 웹 배포본
- `dist/downloads/busan-night-pharmacy.html` — 데이터·글꼴 내장 독립 HTML
- `dashboard_data.json.gz` — 최종 화면용 독립 가공 데이터
- `bootstrap.js`, `app.js`, `finder.js`, `report.js`, `report.css` — 공통 로더와 화면 코드
- `theme.css`, `fonts/` — 화면 테마와 내장 글꼴 Wanted Sans(OFL, `fonts/OFL.txt`, 축소 스크립트 `fonts/subset_fonts.py`)
- `build_html.py`, `check_build.py` — 독립 payload로 두 배포본 생성·분리 데이터 일치 검사
- `serve.py`, `test_static_server.py` — 압축·캐시를 적용하는 정적 서버와 HTTP 검사
- `prepare_cloud_run.py`, `deploy/cloudrun/`, `.gcloudignore` — Dockerfile 없는 최소 소스 배포 준비
- `build_data.py`, `grid_routes.py`, `schedule_assumptions.py` — 최종 분석 단계 원본
- `reproduce/` — 원천 수집부터 도로망·격자·거리행렬·payload까지 재현하는 코드
- `docs/DATA_SOURCES.md` — 출처와 취득 방법
- `docs/METHODOLOGY.md` — 자료가 최종 지표로 변환되는 과정
- `docs/REPRODUCING.md` — 전체 재실행 순서와 자원 요구량
- `validation.json`, `schedule_assumptions_audit.csv` — 검증과 가정 감사자료

## 두 가지 재현 수준

1. **현재 결과 재현:** 저장된 `dashboard_data.json.gz`로 HTML을 다시 만들면 현재 화면과 동일합니다.
2. **원천부터 새로 계산:** `reproduce/`에서 API와 원천파일을 다시 받아 전체 파이프라인을 실행합니다. 외부 자료가 갱신되므로 수치가 현재 스냅샷과 달라질 수 있습니다.

## 중요한 해석 범위

- 수요는 실제 약국 이용자 수가 아니라 생활인구를 SGIS 거주인구 비중으로 배분한 잠재수요입니다.
- 접근성은 등록 운영시간과 명시한 결측 가정, OSM 보행망, 4km/h 속도를 사용합니다.
- 후보 순위는 머신러닝 예측이 아니라 후보 한 곳을 독립적으로 추가하는 공간 시나리오 계산입니다.
- 현재 영업 표시는 2026-10-13 조회 시간표로 현재 시각을 판정하는 기준일 데모입니다. 실시간 현장 확인이 아니므로 방문 전 전화 확인이 필요합니다.

## API 키

키는 저장소에 포함하지 않습니다. `latest` 모드로 공공데이터포털 API를 다시 조회하려면 [공공데이터포털](https://www.data.go.kr)에서 활용승인받은 키를 `reproduce/.env`에 넣습니다.

```bash
cp reproduce/.env.example reproduce/.env
```

`snapshot` 모드와 HTML 재생성(`build_html.py`)은 키 없이 동작합니다.

저장소는 비공개로 유지합니다. 과거 API 키 파일의 이력을 정리한 후에는 팀원도 새로 clone하고, 이전 이력을 다시 push하지 않습니다. Git 이력 제거와 API 키 폐기·재발급은 별개입니다. 키 자체는 변경하지 않았습니다.

## 포트폴리오 보완 기록

기준 원천을 다시 읽어 도로망·격자·거리행렬부터 계산하는 `snapshot` 모드와 API를 다시 조회하는 `latest` 모드를 제공합니다. 설정·입력 해시·검증·실행 기록은 [재현 안내](docs/REPRODUCING.md)와 [검사 기록](docs/VALIDATION_RUN.md)을 확인하세요.

후보 비교에는 3/4/5km/h, 일요일 휴무 가정, 격자 배분 방식을 바꾼 순위 비교가 있습니다. 운영 약국 찾기는 전체 목록 페이지 이동, 선택 요일 팝업, 실제 심야 겹침 시간, 데이터 조회일을 제공합니다.

외부 데이터 선정, 운영시간 검색·교차 대조와 전처리, 보행거리 기반 후보 분석 아이디어는 본인이 담당했고 나머지 구현은 AI의 도움을 받았습니다. Cloud Run 배포는 유지하며 DB는 사용하지 않습니다. Dockerfile은 제거하고 다음 배포를 위한 최소 소스 구성을 준비했습니다. 전화·현장 검증은 수행하지 않았고 수행 계획도 없습니다. 포트폴리오 사이트 반영은 보류하며 나머지 상태는 [다음 작업](docs/NEXT_STEPS.md)에 기록했습니다.

## 약국 위치 검토

동명 약국은 시설 ID·주소·전화별로 유지합니다. 2026-10-14에 주소/좌표 구 불일치 8곳을 부산시 도로명주소의 정확 일치 건물점으로 보정하고 도로망·거리행렬·접근성·민감도를 다시 계산했습니다. `coordinate_corrections.csv`와 `docs/validation/coordinate_correction_run.json`에 근거와 검사 기록이 있습니다. 추가 건물점 거리 차이 21건은 `coordinate_building_review.csv` 및 화면에서 위치 확인 필요로 구분합니다. 출입구 현장 검증은 아닙니다.
