"""루트의 기존 분석 명령을 독립 reproduce 패키지로 연결합니다."""
from pathlib import Path
import importlib.util, subprocess, sys
ROOT=Path(__file__).resolve().parent

def load(name):
    sys.path.insert(0,str(ROOT/'reproduce'))
    sys.path.insert(0,str(ROOT/'reproduce/dashboard_v3'))
    spec=importlib.util.spec_from_file_location('_busan_'+name,ROOT/'reproduce/dashboard_v3'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def run(name):
    result=subprocess.run([sys.executable,str(ROOT/'reproduce/dashboard_v3'/(name+'.py')),*sys.argv[1:]],cwd=ROOT/'reproduce')
    raise SystemExit(result.returncode)
