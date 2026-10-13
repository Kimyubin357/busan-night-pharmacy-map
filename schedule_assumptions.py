"""독립 재현 패키지의 build_schedules에 연결합니다."""
from _reproduce_entry import load
def build_schedules(*args,**kwargs):
    return load('schedule_assumptions').build_schedules(*args,**kwargs)
if __name__=='__main__':
    from _reproduce_entry import run
    run('schedule_assumptions')
