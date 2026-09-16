#!/usr/bin/env python3
"""원천 수집부터 최종 대시보드 데이터까지 순서대로 실행합니다."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parent
PY=sys.executable
STEPS=[
 ['team1_pipeline.py'],['monday_analysis.py'],['team2_pipeline.py'],
 ['supplement_hira_hours.py'],['collect_nmc_hours.py'],['sgis_population_weights.py'],
 ['osm_network.py'],['dashboard_v3/grid_routes.py'],['dashboard_v3/build_data.py'],
 ['publish_dashboard_data.py']]
REQUIRED=[ROOT/'team2/inputs/15028854.csv',ROOT/'team2/inputs/PD_LP00002.xlsx',
 ROOT/'team2/update_20260915/raw/sgis_grid_population.zip',ROOT/'team2/update_20260915/raw/sgis_dong.zip',
 ROOT/'team2/osm/south-korea-260913.osm.pbf']
def main():
    missing=[str(x.relative_to(ROOT)) for x in REQUIRED if not x.exists()]
    if missing: raise SystemExit('먼저 python download_inputs.py 실행 필요:\n- '+'\n- '.join(missing))
    for i,args in enumerate(STEPS,1):
        print(f'[{i}/{len(STEPS)}]',*args,flush=True)
        subprocess.run([PY,*args],cwd=ROOT,check=True)
if __name__=='__main__':main()
