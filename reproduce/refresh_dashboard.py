#!/usr/bin/env python3
"""격리된 폴더에서 최신 전체 파이프라인을 실행하고 모든 검사가 통과할 때만 공개 데이터를 교체합니다."""
import argparse,gzip,json,shutil,subprocess,sys,tempfile,os,hashlib
from pathlib import Path
from pipeline_context import ROOT,utc_now,sha256

PROJECT=ROOT.parent

def atomic(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.partial');tmp.write_bytes(content);tmp.replace(path)

def fingerprint(folder):
    data=json.loads(gzip.decompress((folder/'dashboard_data.json.gz').read_bytes()))
    data['meta'].pop('refresh_status',None)
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def stamp(folder,status):
    path=folder/'dashboard_data.json.gz'
    data=json.loads(gzip.decompress(path.read_bytes()))
    data['meta']['refresh_status']={k:status.get(k) for k in ['mode','attempted_at','finished_at','status','next_scheduled_at','failed_stage']}
    atomic(path,gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()))
    subprocess.run([sys.executable,str(folder/'build_html.py')],cwd=folder,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['latest','snapshot'],default='latest')
    parser.add_argument('--work-dir',type=Path,help='감사 목적으로 실패 원천·로그까지 남길 새 작업 폴더')
    args=parser.parse_args()
    # 중복 갱신이 서로 결과를 덮어쓰지 않게 합니다. 잠금은 이번 프로세스에서만 제거합니다.
    lock=PROJECT/'.refresh-lock'
    try:lock.mkdir()
    except FileExistsError:raise SystemExit('다른 갱신이 진행 중입니다. 실행 종료 여부를 확인하세요.')
    try:
        stage=args.work_dir or Path(tempfile.mkdtemp(prefix='busan-refresh-'))/'project'
        if stage.exists():raise ValueError('--work-dir은 존재하지 않는 새 폴더여야 합니다.')
        if stage.resolve().is_relative_to(PROJECT.resolve()):raise ValueError('작업 폴더는 프로젝트 바깥에 지정하세요.')
        shutil.copytree(PROJECT,stage,ignore=shutil.ignore_patterns('.git','.refresh-lock','*.log','__pycache__','.venv*'))
        status=dict(mode=args.mode,attempted_at=utc_now(),status='running',next_scheduled_at=None)
        previous_fingerprint=fingerprint(PROJECT)
        log=stage/'refresh.log'
        env=os.environ.copy();env['BUSAN_ISOLATED_REFRESH']='1'
        with log.open('w') as stream:
            result=subprocess.run([sys.executable,'run_pipeline.py','--mode',args.mode],cwd=stage/'reproduce',env=env,stdout=stream,stderr=subprocess.STDOUT)
        report_path=stage/'reproduce/reports/pipeline_run.json'
        # 이전 실행 기록은 이번 검증의 근거로 사용하지 않습니다.
        report=json.loads(report_path.read_text()) if report_path.exists() else {}
        if report.get('started_at','')<status['attempted_at']:report={}
        status.update(finished_at=utc_now(),status='passed' if result.returncode==0 and report.get('status')=='passed' else 'failed')
        status['stages']=[{k:r[k] for k in ['name','exit_code','duration_seconds']} for r in report.get('stages',[])]
        status['failed_stage']=next((s['name'] for s in status['stages'] if s['exit_code']),None)
        status['log_path']=str(log)
        if status['status']=='passed':
            stamp(stage,status)
            # 주 분석 데이터와 모든 공개 CSV/JSON/HTML이 같은 실행에서 나와야 합니다.
            names=['coordinate_corrections.csv','coordinate_building_review.csv','coordinate_validation.json','dashboard_data.json.gz','data.json.gz','validation.json','model_summary.json','candidate_rankings_v3.csv','schedule_assumptions_audit.csv','schedule_assumptions_summary.json','schedule_exceptions_audit.csv','nmc_pharmacies_latest.csv','nmc_identity_review_latest.csv','nmc_conflict_resolutions.csv','remaining_sunday_errors.csv','grid_route_quality.json','sensitivity_results.json','sensitivity_rankings.csv','field_validation_plan.csv','build_manifest.json','dist/index.html']
            manifest=json.loads((stage/'build_manifest.json').read_text())
            extra=['dist/'+name for name in manifest.get('files',{})]
            if manifest.get('standalone'):extra += ['dist/'+manifest['standalone']['file'],'dist/index.html.gz']
            # 새 해시 파일을 먼저 복사하고 index.html은 마지막에 교체합니다.
            names=extra+names
            backup=stage/'previous_publication';backup.mkdir()
            replaced=[]
            try:
                for name in names:
                    src=stage/name;target=PROJECT/name
                    if not src.exists():raise ValueError('공개 결과 누락: '+name)
                    old=backup/name;old.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists():shutil.copy2(target,old)
                    atomic(target,src.read_bytes());replaced.append(name)
            except Exception:
                for name in replaced:
                    old=backup/name
                    if old.exists():atomic(PROJECT/name,old.read_bytes())
                    else:(PROJECT/name).unlink(missing_ok=True)
                raise
            status['published_html_sha256']=sha256(PROJECT/'dist/index.html')
            status['published_payload_sha256']=sha256(PROJECT/'dashboard_data.json.gz')
        else:
            # 실패 상태만 안내하고 기존 분석 수치/운영시간은 유지합니다.
            stamp(PROJECT,status)
            assert fingerprint(PROJECT)==previous_fingerprint,'실패한 갱신이 기존 데이터를 변경했습니다.'
            status['previous_data_preserved']=True
        atomic(PROJECT/'refresh_status.json',json.dumps(status,ensure_ascii=False,indent=2).encode())
        print(json.dumps({k:status[k] for k in ['status','failed_stage','finished_at','log_path']},ensure_ascii=False))
        if status['status']=='failed':raise SystemExit(1)
    finally:lock.rmdir()

if __name__=='__main__':main()
