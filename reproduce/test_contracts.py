"""기간 혼용·저장 원본 오염·실행 폴더 밖 참조를 막는 회귀 검사."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,unittest,hashlib
from prepare_context import select_month
from public_data import snapshot_file
import pipeline_context

class PipelineContracts(unittest.TestCase):
    def test_latest_common_month_changes_with_new_input(self):
        self.assertEqual(select_month(['202512','202601','202602'],['202512','202601'],'latest_common')[0],'202601')
    def test_explicit_period_must_exist_in_both_sources(self):
        with self.assertRaises(ValueError):select_month(['202512'],['202601'],'202512')
    def test_fixed_period_is_respected(self):
        self.assertEqual(select_month(['202512','202601'],['202512','202601'],'202512')[0],'202512')
    def test_replayed_source_tampering_is_rejected(self):
        with TemporaryDirectory() as folder:
            p=Path(folder);(p/'page.json').write_bytes(b'original')
            (p/'manifest.json').write_text(json.dumps({'page.json':hashlib.sha256(b'original').hexdigest()}))
            with patch.dict('os.environ',{'BUSAN_SNAPSHOT_DIR':folder}):
                self.assertEqual(snapshot_file('page.json').read_bytes(),b'original')
                (p/'page.json').write_bytes(b'changed')
                with self.assertRaises(ValueError):snapshot_file('page.json')
    def test_moving_checkout_keeps_processed_pointer_valid(self):
        with TemporaryDirectory() as folder:
            p=Path(folder).resolve();(p/'reports').mkdir()
            (p/'reports/latest_run.json').write_text(json.dumps({'output_dir':'data/processed/run'}))
            with patch.object(pipeline_context,'ROOT',p):
                self.assertEqual(pipeline_context.processed_source(),p/'data/processed/run')
                (p/'reports/latest_run.json').write_text(json.dumps({'output_dir':'../../outside'}))
                with self.assertRaises(ValueError):pipeline_context.processed_source()

if __name__=='__main__':unittest.main()
