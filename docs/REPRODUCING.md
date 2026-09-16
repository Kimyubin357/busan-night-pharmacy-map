# 원천부터 재현하기

## 환경

- Python 3.12 권장
- RAM 최소 8GB, 권장 16GB 이상
- 빈 디스크 최소 5GB
- 네트워크 다운로드 약 0.5GB 이상
- OSM 파싱과 최단경로 계산은 장비에 따라 약 30분~2시간 이상
- 최종 HTML만 재생성하면 수 초 이내

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 전체 실행

```bash
cd reproduce
python download_inputs.py
python run_pipeline.py
cd ..
python build_html.py
node check_report.cjs
```

`download_inputs.py`는 도로명주소, 연령 생활인구, SGIS 파일과 OSM PBF를 지정 위치에 저장하고 SHA-256을 기록합니다. SGIS 서버가 직접 다운로드를 거부하면 `docs/DATA_SOURCES.md`의 출처에서 수동으로 내려받아 다음 위치에 둡니다.

```text
reproduce/team2/update_20260915/raw/sgis_grid_population.zip
reproduce/team2/update_20260915/raw/sgis_grid_mara.zip
reproduce/team2/update_20260915/raw/sgis_grid_mama.zip
reproduce/team2/update_20260915/raw/sgis_dong.zip
reproduce/team2/update_20260915/raw/sgis_codebook.zip
reproduce/team2/osm/south-korea-260913.osm.pbf
```

## 실행 단계

1. `team1_pipeline.py`: 약국·공공심야·생활인구 수집 및 정제
2. `monday_analysis.py`: 기존 분석용 시간표와 보완 감사표 생성
3. `team2_pipeline.py`: 동별 수요, 대표주소, 공급 시나리오 생성
4. `supplement_hira_hours.py`: 포함된 HIRA 비교 스냅샷 적용
5. `collect_nmc_hours.py`: NMC 부산 약국 전 페이지 수집·대조
6. `sgis_population_weights.py`: SGIS 격자 분할과 수요 배분
7. `osm_network.py`: OSM 파싱, 보행 그래프와 대표점 경로 생성
8. `dashboard_v3/grid_routes.py`: 21,963개 격자와 약국 거리행렬 생성
9. `dashboard_v3/build_data.py`: 접근성·후보점수·경계 payload 생성
10. `publish_dashboard_data.py`: 저장소 루트의 독립 payload 갱신
11. `build_html.py`: 단일 HTML 생성

## Git에서 제외한 파일

PBF, SGIS ZIP, OSM 그래프, 37,249,248개 격자×약국 거리행렬과 불확실성 배열은 다운로드 또는 위 코드로 재생성합니다. 현재 검증본 기준으로 거리행렬은 약 142MB, 불확실성 배열은 약 36MB입니다.

## 동일성에 관한 주의

`dashboard_data.json.gz`는 대회 분석 당시 스냅샷의 고정 결과입니다. API와 Geofabrik `latest` 파일을 다시 받으면 최신 스냅샷으로 계산되므로 결과가 달라지는 것이 정상입니다. 과거와 바이트 단위로 같아야 한다면 `source_manifest.json`의 SHA-256과 동일한 원천 파일을 확보해야 합니다.
