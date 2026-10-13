"""최신 갱신 실패와 오래된 성공 기록으로 정상 데이터를 교체하지 않는 검사."""
import gzip,json,subprocess,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import refresh_dashboard as refresh
class SafeRefresh(unittest.TestCase):
 def run_failure(self,stale):
  with TemporaryDirectory() as folder:
   base=Path(folder);project=base/'project';project.mkdir();(project/'reproduce').mkdir()
   original={'meta':{},'models':{'api':{'result':123}},'mapPharmacies':[{'id':'kept','schedule':[[[510,1500]]]}]}
   (project/'dashboard_data.json.gz').write_bytes(gzip.compress(json.dumps(original).encode()))
   (project/'build_html.py').write_text("from pathlib import Path\nPath(__file__).with_name('rendered.txt').write_text('built')\n")
   before=refresh.fingerprint(project);real_run=subprocess.run
   def execute(command,**kwargs):
    if command[1]=='run_pipeline.py':
     reports=Path(kwargs['cwd'])/'reports';reports.mkdir(exist_ok=True)
     (reports/'pipeline_run.json').write_text(json.dumps({'started_at':'2000-01-01' if stale else refresh.utc_now(),'status':'passed' if stale else 'failed','stages':[{'name':'collect_nmc_hours.py','exit_code':1,'duration_seconds':0}]}))
     return subprocess.CompletedProcess(command,0 if stale else 1)
    return real_run(command,**kwargs)
   with patch.object(refresh,'PROJECT',project),patch.object(sys,'argv',['refresh_dashboard.py','--work-dir',str(base/'stage')]),patch.object(refresh.subprocess,'run',side_effect=execute):
    with self.assertRaises(SystemExit) as error:refresh.main()
    self.assertEqual(error.exception.code,1)
   self.assertEqual(refresh.fingerprint(project),before)
   status=json.loads((project/'refresh_status.json').read_text());self.assertEqual(status['status'],'failed');self.assertTrue(status['previous_data_preserved'])
   self.assertFalse((project/'.refresh-lock').exists())
 def test_failed_stage_preserves_existing_schedule_and_model(self):self.run_failure(False)
 def test_old_success_cannot_pass_this_refresh(self):self.run_failure(True)
if __name__=='__main__':unittest.main()
