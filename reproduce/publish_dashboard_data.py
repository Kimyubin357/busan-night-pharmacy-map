"""재계산 결과를 저장소 루트의 독립 대시보드 payload로 내보냅니다."""
from pathlib import Path
import sys,json,gzip
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dashboard_v3'))
from build_map_data import build_map_pharmacies
source=ROOT/'dashboard_v3/data.json.gz'
data=json.loads(gzip.decompress(source.read_bytes()))
data['mapPharmacies']=build_map_pharmacies(data)
target=ROOT.parent/'dashboard_data.json.gz'
target.write_bytes(gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()))
print(target,target.stat().st_size)
