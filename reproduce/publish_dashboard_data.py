"""재계산 결과를 저장소 루트의 독립 대시보드 payload로 내보냅니다."""
from pathlib import Path
import sys,json,gzip
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dashboard_v3'))
from build_map_data import build_map_pharmacies
source=ROOT/'dashboard_v3/data.json.gz'
data=json.loads(gzip.decompress(source.read_bytes()))
data['mapPharmacies']=build_map_pharmacies(data)
data['sensitivity']=json.loads((ROOT/'sensitivity_results.json').read_text())
data['validation']=json.loads((ROOT/'dashboard_v3/validation.json').read_text())
# 브라우저의 주모형은 4km/h·최대 15분입니다. 민감도 계산용 1250m 경로는
# 분석 원본에 유지하고 화면에 필요한 1000m 이내 경로만 전달합니다.
for p in data['pharmacies']:
    for indices,times in [('reach','seconds'),('uncertain','uncertainSeconds')]:
        keep=[k for k,s in enumerate(p[times]) if s<=900]
        p[indices]=[p[indices][k] for k in keep]
        p[times]=[p[times][k] for k in keep]
data['meta']['display_distance_limit_m']=1000
target=ROOT.parent/'dashboard_data.json.gz'
target.write_bytes(gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()))
for name in ['data.json.gz','validation.json','model_summary.json','candidate_rankings_v3.csv','schedule_assumptions_audit.csv','schedule_assumptions_summary.json','nmc_conflict_resolutions.csv','remaining_sunday_errors.csv','grid_route_quality.json']:
    path=ROOT/'dashboard_v3'/name
    if path.exists(): (ROOT.parent/name).write_bytes(path.read_bytes())
for name in ['sensitivity_results.json','sensitivity_rankings.csv','field_validation_plan.csv']:
    (ROOT.parent/name).write_bytes((ROOT/name).read_bytes())
print(target,target.stat().st_size)
