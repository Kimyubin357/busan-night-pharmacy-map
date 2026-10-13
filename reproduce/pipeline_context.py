"""분석 기준과 원천 이력을 공유합니다. 모든 경로는 이 파이프라인 안에서 해석합니다."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

ROOT = Path(__file__).resolve().parent

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while b := f.read(1024 * 1024): h.update(b)
    return h.hexdigest()

def config():
    return json.loads((ROOT / 'config.json').read_text())

def context():
    path = ROOT / 'reports/run_context.json'
    if not path.exists():
        raise RuntimeError('먼저 prepare_context.py를 실행해 기준 월과 입력 파일을 검증하세요.')
    return json.loads(path.read_text())

def processed_source():
    p = json.loads((ROOT / 'reports/latest_run.json').read_text())['output_dir']
    path = (ROOT / p).resolve()
    if not path.is_relative_to(ROOT.resolve()): raise ValueError('프로젝트 외부의 처리 결과를 참조할 수 없습니다.')
    return path

def utc_now():
    return datetime.now(timezone.utc).isoformat()
