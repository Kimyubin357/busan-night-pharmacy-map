#!/usr/bin/env python3
"""원천 수집/스냅샷 재독해 → 공간 분석 → 검증 → 독립 HTML까지 실행하고 기록합니다."""
import argparse, json, os, subprocess, sys, time
from pipeline_context import ROOT, config, sha256, utc_now

STEPS=[['test_contracts.py'],['test_schedule_exceptions.py'],['test_refresh.py'],['team1_pipeline.py'],['prepare_context.py'],['monday_analysis.py'],['team2_pipeline.py'],
       ['supplement_hira_hours.py'],['collect_nmc_hours.py'],['test_pharmacy_locations.py'],['reconcile_locations.py'],['sgis_population_weights.py'],
       ['osm_network.py'],['dashboard_v3/grid_routes.py'],['dashboard_v3/build_data.py'],
       ['dashboard_v3/verify_v3.py'],['analyze_sensitivity.py'],['publish_dashboard_data.py'],['verify_location_publication.py']]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['snapshot','latest'],default='snapshot')
    args=parser.parse_args()
    if args.mode=='latest' and os.environ.get('BUSAN_ISOLATED_REFRESH')!='1':
        # 직접 실행해도 최신 수집은 검증 전 공개 결과를 바꾸지 않습니다.
        raise SystemExit(subprocess.run([sys.executable,str(ROOT/'refresh_dashboard.py'),'--mode','latest'],cwd=ROOT).returncode)
    cfg=config();catalog=json.loads((ROOT/'input_catalog.json').read_text())
    missing=[rel for rel in catalog if not (ROOT/rel).exists()]
    if missing and args.mode=='snapshot':raise SystemExit('먼저 python download_inputs.py --mode '+args.mode+' 실행 필요:\n- '+'\n- '.join(missing))
    if args.mode=='snapshot':
        for rel,entry in catalog.items():
            if sha256(ROOT/rel)!=entry['snapshot_sha256']:raise ValueError('입력 스냅샷 해시 불일치: '+rel)
    env=os.environ.copy();env['BUSAN_RUN_MODE']=args.mode
    if args.mode=='snapshot':env['BUSAN_SNAPSHOT_DIR']=str(ROOT/'snapshots'/cfg['snapshot_id'])
    else:env.pop('BUSAN_SNAPSHOT_DIR',None)
    started=utc_now();stages=[];report=ROOT/'reports/pipeline_run.json';report.parent.mkdir(exist_ok=True)
    steps=[*STEPS,['../build_html.py'],['../check_finder.cjs'],['../check_report.cjs']]
    if args.mode=='latest':steps.insert(4,['download_inputs.py','--mode','latest'])
    try:
        for i,argv in enumerate(steps,1):
            name=argv[0];print(f'[{i}/{len(steps)}] {name}',flush=True);begin=time.monotonic()
            command=['node',*argv] if name.endswith('.cjs') else [sys.executable,*argv]
            result=subprocess.run(command,cwd=ROOT,env=env)
            stages.append({'name':name,'exit_code':result.returncode,'duration_seconds':round(time.monotonic()-begin,3)})
            if result.returncode:raise RuntimeError('단계 실패: '+name)
        outputs={str(p.relative_to(ROOT.parent)):sha256(p) for p in [ROOT.parent/'dashboard_data.json.gz',ROOT.parent/'dist/index.html',ROOT/'dashboard_v3/validation.json',ROOT/'sensitivity_results.json']}
        status='passed'
    except Exception:
        status='failed';outputs={};raise
    finally:
        code={str(p.relative_to(ROOT.parent)):sha256(p) for p in [*ROOT.rglob('*.py'),ROOT.parent/'build_html.py',ROOT.parent/'finder.js',ROOT.parent/'app.js',ROOT.parent/'report.js',ROOT.parent/'report.css',ROOT.parent/'ui.css',ROOT.parent/'ui.js',ROOT.parent/'theme.css',*ROOT.parent.glob('fonts/*.woff'),ROOT/'pharmacy_location_overrides.json',ROOT.parent/'dist/template.html'] if '__pycache__' not in p.parts}
        report.write_text(json.dumps({'mode':args.mode,'started_at':started,'finished_at':utc_now(),'status':status,'stages':stages,'output_sha256':outputs,'code_sha256':code},ensure_ascii=False,indent=2))
    print('PASS: 전체 파이프라인, 수치 검증, 민감도 기준 일치, HTML 검사',flush=True)

if __name__=='__main__':main()
