# 부산 심야약국 접근성 지도

부산의 심야 약국 접근성을 100m 격자와 보행 도로망으로 분석하고, 공공심야약국 추가 지정 후보와 시민용 운영 약국 찾기를 한 화면에 제공합니다.

## 바로 실행

Python 외에는 설치할 필요가 없습니다.

```bash
python3 -m http.server 8000 --directory dist
```

브라우저에서 <http://localhost:8000>을 엽니다. `file://`로도 열리지만 OpenStreetMap 타일은 Referer 제한으로 403이 날 수 있습니다.

## 화면 수정 후 다시 만들기

`dashboard_data.json.gz`는 지도 약국 1,716곳과 최종 분석 결과를 포함한 독립 payload입니다. 외부 프로젝트 폴더를 참조하지 않습니다.

```bash
python3 build_html.py
node check_report.cjs
node check_finder.cjs
```

생성물은 `dist/index.html`입니다. 이 경로는 원천 수집이나 거리행렬 재계산을 하지 않습니다.

## 저장소 구성

- `dist/index.html` — 배포 가능한 단일 HTML
- `dashboard_data.json.gz` — 최종 화면용 독립 가공 데이터
- `app.js`, `finder.js`, `report.js`, `report.css` — 화면 코드
- `build_html.py` — 독립 payload로 HTML 생성
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
- 현재 영업 표시는 실시간 현장 확인이 아니므로 방문 전 전화 확인이 필요합니다.

## API 키

요청에 따라 `reproduce/.env`에 현재 공공데이터포털 키가 포함되어 있습니다. 이 저장소는 private으로 유지하고 키 만료·교체 시 해당 파일도 갱신해야 합니다. 공개 전환 전에는 키를 폐기하고 Git 기록에서도 제거해야 합니다.

## 포트폴리오 보완 기록

기준 원천을 다시 읽어 도로망·격자·거리행렬부터 계산하는 `snapshot` 모드와 API를 다시 조회하는 `latest` 모드를 제공합니다. 설정·입력 해시·검증·실행 기록은 [재현 안내](docs/REPRODUCING.md)와 [검사 기록](docs/VALIDATION_RUN.md)을 확인하세요.

후보 비교에는 3/4/5km/h, 일요일 휴무 가정, 격자 배분 방식을 바꾼 순위 비교가 있습니다. 운영 약국 찾기는 전체 목록 페이지 이동, 선택 요일 팝업, 실제 심야 겹침 시간, 데이터 조회일을 제공합니다.

사용자는 프로젝트를 거의 단독으로 수행했습니다. 포트폴리오의 기여·AI 활용·성과는 실제 수행 범위로 설명합니다. Cloud Run 배포, SQL·Docker·CI/CD, 실제 경로·운영시간 확인 등 남은 작업은 [다음 작업](docs/NEXT_STEPS.md)에 기록했습니다.
