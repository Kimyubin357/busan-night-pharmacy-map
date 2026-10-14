# Cloud Run 운영 안내

**공개 주소: <https://busan-night-pharmacy-map-768810209035.asia-east1.run.app/>**

대시보드는 DB 없이 `serve.py`와 `dist`의 정적 파일을 제공합니다. 자료 기준일은 2026-10-13이며 접속할 때마다 운영시간을 수집하지 않습니다.

## 현재 배포 유지

2026-10-14 사용자 요청에 따라 저장소에서 `Dockerfile`과 `.dockerignore`를 제거했습니다. 직접 Docker를 관리하거나 별도 VM을 운영할 필요가 없습니다. **이미 배포된 서비스와 실행 이미지는 유지합니다.** Cloud Run 자체는 컨테이너를 실행하는 플랫폼이므로 실행 이미지까지 없어지는 것은 아닙니다.

| 항목 | 현재 설정 |
| --- | --- |
| 프로젝트 / 리전 | `taobao2store` / `asia-east1` (대만) |
| 서비스 / 리비전 | `busan-night-pharmacy-map` / `busan-night-pharmacy-map-00001-vnv` |
| 자원 | 1 vCPU, 256MiB, 동시 요청 80, 요청 제한시간 60초 |
| 비용 설정 | 요청 기반 CPU 할당, 최소 인스턴스 0, 서비스·리비전 최대 1 |
| 실행 계정 | `busan-pharmacy-runtime@taobao2store.iam.gserviceaccount.com` (프로젝트 IAM 역할 없음) |
| 공개 범위 | 로그인 없이 대시보드 열람 |

현재 리비전은 Cloud Build `a4016dfb-7902-492f-84b7-052ef2358e29`의 이미지 `asia-east1-docker.pkg.dev/taobao2store/busan-night-pharmacy/dashboard@sha256:5685ee6ea98c82ee0b34d7c53a54cec28d92b1ba73ad4bbaa937f89db4033717`를 사용합니다. Ready와 트래픽 100%를 확인했습니다. 기존 `domino-drop-puzzle-00001-spg`, `batteryflow-00002-cmg` 리비전은 유지했습니다.

## 다음 배포: Dockerfile 없는 소스 배포

다음 절차는 Google Buildpacks가 실행 이미지를 자동 생성하는 방식입니다. 현재 서비스는 다시 배포하지 않았으며, 이 방식의 원격 빌드·배포는 아직 실행하지 않았습니다. 로컬에서 준비된 파일의 해시·실행 진입점·서버 응답을 확인합니다.

1. 화면을 수정했다면 `python3 build_html.py`를 실행하고 기존 검사를 통과시킵니다.
2. 저장소 밖의 **새 디렉터리**에 최소 실행 파일을 준비합니다.

```bash
python3 check_build.py
node check_finder.cjs
node check_report.cjs
python3 -m unittest test_static_server.py
python3 prepare_cloud_run.py /tmp/busan-pharmacy-source-NEW
```

`NEW`는 매번 다른 값으로 바꿉니다. 기존 디렉터리는 덮어쓰지 않습니다. 준비 스크립트는 빌드 명세의 해시와 압축 HTML을 검사한 뒤 `serve.py`, 현재 배포용 `dist`, Python 3.12 설정, `Procfile`, 런타임 전용 빈 `requirements.txt`만 복사합니다. 원천 자료·API 키·Git 이력·과거 템플릿은 포함하지 않습니다.

루트 `requirements.txt`는 분석용 패키지 목록입니다. 정적 서버에 필요 없는 NumPy·SciPy 등을 설치하지 않도록 `deploy/cloudrun/requirements.txt`와 분리했습니다.

3. 준비된 폴더의 업로드 목록을 확인하고, 재배포가 필요할 때 실행합니다.

```bash
cd /tmp/busan-pharmacy-source-NEW
gcloud meta list-files-for-upload
gcloud run deploy busan-night-pharmacy-map \
  --source . --project=taobao2store --region=asia-east1 \
  --set-build-env-vars='GOOGLE_ENTRYPOINT=python serve.py --host 0.0.0.0' \
  --service-account=busan-pharmacy-runtime@taobao2store.iam.gserviceaccount.com \
  --execution-environment=gen1 --cpu=1 --memory=256Mi \
  --concurrency=80 --port=8080 --timeout=60 \
  --cpu-throttling --no-cpu-boost \
  --min=0 --max=1 --min-instances=0 --max-instances=1 \
  --ingress=all --allow-unauthenticated
```

소스 배포는 기본 빌드 계정에 `roles/run.builder` 등 필요한 빌드 권한이 있어야 하며 최초 사용 시 Google Cloud가 별도 소스 배포 저장소를 만들 수 있습니다. 기존 수동 이미지 배포와 다른 빌드 경로이므로 빌드 완료와 새 리비전 Ready를 확인한 뒤 모든 탭·지도·필터·다운로드를 다시 확인합니다. 공식 [Python Buildpacks 안내](https://docs.cloud.google.com/docs/buildpacks/python)를 참고합니다.

## 비용과 검증 범위

2026-10-14 배포 준비 시 같은 결제 계정의 두 프로젝트에서 관측한 10월 사용량은 요청 91건, CPU 할당 약 234초, 메모리 할당 약 200GiB·초였습니다. 이는 확정 청구액이나 무료 잔여량이 아니며 다른 서비스 사용량과 함께 달라집니다.

- [Cloud Run](https://cloud.google.com/run/pricing)의 요청 기반 무료 기준은 월 CPU 180,000초, 메모리 360,000GiB·초, 요청 200만 건입니다. 결제 계정에서 공유합니다.
- [한국 방향 외부 전송](https://cloud.google.com/vpc/network-pricing)은 GiB당 $0.19를 계산에 사용했습니다. 첫 화면 약 1.02MB, 모든 탭 약 7MB이며 브라우저 캐시가 적용되면 감소합니다. 도로 타일은 외부 제공처에서 직접 받습니다.
- 현재 이미지는 62,227,018바이트이며, 기존 다른 프로젝트 저장량 약 1.33GB가 무료 0.5GiB 기준을 초과해 [추가 이미지 저장료](https://cloud.google.com/artifact-registry/pricing)는 월 약 $0.006로 추정합니다. 최초 빌드는 약 25초였습니다. 소스 방식으로 다시 배포하면 이미지 크기·빌드 시간은 달라질 수 있습니다.
- 현재 이미지 한 개와 월 20회 정도 접속을 가정한 추가 비용은 월 약 50~100원입니다. $1=1,400원으로 환산했으며 기존 서비스 요금·부가세는 제외합니다. 최대 인스턴스 1은 절대 지출 상한이 아닙니다.

배포 시 파일 25개의 해시, gzip, ETag 304, 캐시 및 비공개 경로 404를 확인했습니다. 인앱 브라우저 1280×720 / 390×844에서 다섯 탭, 도로 타일, 구→동 필터와 공공심야약국 선택을 확인했고 관련 콘솔 오류는 없었습니다. 전화·현장 검증은 수행하지 않았고 이 프로젝트에서는 수행할 계획도 없습니다. 계산 재현 검사와 현장 정확도는 구분합니다.
