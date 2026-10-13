"""독립 재현 패키지의 build_map_pharmacies에 연결합니다."""
from _reproduce_entry import load
def build_map_pharmacies(*args,**kwargs):
    return load('build_map_data').build_map_pharmacies(*args,**kwargs)
if __name__=='__main__':
    from _reproduce_entry import run
    run('build_map_data')
