"""휴게·정기휴무 원문을 오독해 영업을 없애거나 늘리지 않는 검사."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'dashboard_v3'))
from schedule_exceptions import parse_notes,subtract
class Exceptions(unittest.TestCase):
 def notes(self,pid,text):return parse_notes({'hpid':pid,'dutyEtc':text})
 def test_break_subtracts_both_boundaries(self):
  self.assertEqual(subtract([[510,1500]],[[1170,1320]]),[[510,1170],[1320,1500]])
  self.assertIsNone(subtract(None,[[780,840]]));self.assertEqual(subtract([],[[780,840]]),[])
 def test_public_hours_are_not_parsed_as_break(self):
  e=self.notes('C1200495','휴게시간(19:30-22:00) / 공공심야약국 운영(22:00-25:00)')
  self.assertEqual(e['breaks'][0],[(1170,1320)])
 def test_no_lunch_is_not_closure(self):
  self.assertFalse(any(self.notes('x','점심시간없음')['breaks']))
 def test_weekday_and_saturday_are_separate(self):
  e=self.notes('C1201298','월~금요일 휴게시간 18:30~22:00, 토요일 휴게시간 13:00~22:00')
  self.assertEqual(e['breaks'][0],[(1110,1320)]);self.assertEqual(e['breaks'][5],[(780,1320)]);self.assertEqual(e['breaks'][6],[])
 def test_changed_source_invalidates_reviewed_rule(self):
  e=self.notes('C1201466','휴게시간: 월요일~토요일 21:00~22:00')
  self.assertFalse(any(e['breaks']));self.assertTrue(e['review'])
 def test_monthly_exception_does_not_become_weekly_closure(self):
  e=self.notes('C1200896','매월 첫째 주, 셋째 주 일요일은 휴무입니다.')
  self.assertEqual(e['recurring'][0]['weeks'],[1,3])
 def test_ambiguous_lunch_kept_for_review(self):
  e=self.notes('x','점심시간 전화 후 방문요망');self.assertFalse(any(e['breaks']));self.assertTrue(e['review'])
 def test_explicit_date_is_not_extrapolated_to_current_year(self):
  e=self.notes('x','26. 8. 30.(일) 공공심야약국 휴무');self.assertEqual(e['closedDates'],['2026-08-30'])
  self.assertEqual(self.notes('x','4.11(토), 4.24(금) 휴무')['closedDates'],[])
if __name__=='__main__':unittest.main()
