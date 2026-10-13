"""추가 자료의 실제 산출물을 검사하고 출처·해시를 기록합니다. ZIP은 만들지 않습니다."""
from pathlib import Path
import hashlib,json
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'team2/update_20260915'

def main():
    source=__import__('pipeline_context').processed_source()
    original=pd.read_csv(source/'pharmacy_opening_hours_analysis.csv')
    updated=pd.read_csv(OUT/'pharmacy_opening_hours_supplemented.csv')
    # 원본 원시 시각과 행 순서 보존. 조회·추정값은 별도 컬럼으로만 기록합니다.
    for col in ['pharmacy_id','day_code','start_raw','end_raw']:
        pd.testing.assert_series_equal(original[col],updated[col],check_dtype=False)
    changed=updated.supplement_applied
    for col in ['start_effective','start_minute','end_minute_unwrapped','hours_status']:
        pd.testing.assert_series_equal(original.loc[~changed,col],updated.loc[~changed,col],check_dtype=False)
    assert updated.loc[changed,'hours_status'].eq('estimated').all()
    assert (updated.loc[changed,'end_minute_unwrapped']>updated.loc[changed,'start_minute']).all()
    comparisons=pd.read_csv(OUT/'hira_hours_comparison.csv')
    conflicts=comparisons[comparisons.action.eq('conflict_not_applied')]
    assert not updated.merge(conflicts[['pharmacy_id','day_code']],on=['pharmacy_id','day_code']).supplement_applied.any()
    grid=pd.read_csv(OUT/'sgis_grid_demand.csv',dtype={'dong_code':str})
    assert grid.grid_node_id.is_unique
    assert grid.weight_within_dong.between(0,1).all()
    # 하나의 격자 인구를 여러 동에 중복하여 전량 집계하지 않았는지 검사합니다.
    assert grid.groupby('grid_id').intersection_area_fraction.sum().max()<=1+1e-7
    assert np.allclose(grid.groupby('dong_code').weight_within_dong.sum(),1)
    hourly=pd.read_csv(OUT/'sgis_grid_hourly_demand.csv',dtype={'dong_code':str})
    assert len(hourly)==len(grid)*3
    assert np.allclose(hourly[['allocated_resident','allocated_worker','allocated_visitor']].sum(axis=1),hourly.allocated_total_population_proxy)
    sources={
        'hira_202606.zip':{'source':'https://opendata.hira.or.kr/op/opc/selectOpenData.do?sno=11925','file_id':'326801','reference_date':'2026-06-30'},
        'sgis_grid_population.zip':{'source':'https://link.mods.go.kr/view/pss/downloadList','download_filename':'/census/reqdoc/1789222868357.zip','reference_year':2024},
        'sgis_grid_mara.zip':{'source':'https://link.mods.go.kr/view/pss/downloadList','download_filename':'/grid_border/grid_2025/grid_마라/grid_마라.zip'},
        'sgis_grid_mama.zip':{'source':'https://link.mods.go.kr/view/pss/downloadList','download_filename':'/grid_border/grid_2025/grid_마마/grid_마마.zip'},
        'sgis_dong.zip':{'source':'https://link.mods.go.kr/view/pss/downloadList','download_filename':'/census/bnd_data/bnd_dong/bnd_dong_00_2025_2Q.zip','boundary_date':'2025-06-30'},
        'sgis_codebook.zip':{'source':'https://link.mods.go.kr/contents/include/download.jsp?filename=ref_code.zip&path=/board/&type=board'},
        'nmc_guide':{'source':'https://www.data.go.kr/data/15000576/openapi.do','data_access_status':'see_nmc_update_summary'},
    }
    for filename,meta in sources.items():
        p=OUT/'raw'/filename
        meta.update(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    (OUT/'source_manifest.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
    manifest={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.csv')}
    status={'validation_passed':True,'grid_nodes':len(grid),'hourly_grid_rows':len(hourly),'hours_supplemented':int(changed.sum()),
            'nmc_status':'HTTP403; utilization approval needs user confirmation',
            'route_recalculation_complete':False,'new_ranking_available':False,'teammate_zips_created':False,
            'assumptions':['SGIS resident distribution is a proxy, not observed nighttime grid population',
                           'Boundary cells split by area, assuming uniform population within each 100m cell',
                           'No age-specific 100m population in the downloaded files',
                           'HIRA supplements use June snapshot and remain estimated; conflicting days left unchanged'],
            'processed_sha256':manifest}
    if (OUT/'nmc_update_summary.json').exists():
        nmc=pd.read_csv(OUT/'pharmacy_opening_hours_nmc.csv')
        assert len(nmc)==len(original)
        for col in ['pharmacy_id','day_code','start_raw','end_raw']:
            pd.testing.assert_series_equal(original[col],nmc[col],check_dtype=False)
        mask=nmc.nmc_applied
        assert nmc.loc[mask,'hours_status'].eq('known').all()
        assert nmc.loc[mask,'end_minute_unwrapped'].gt(nmc.loc[mask,'start_minute']).all()
        assert nmc.loc[mask,'start_value_source'].eq('nmc_direct_api').all()
        for col in ['start_effective','end_effective','hours_status','start_minute','end_minute_unwrapped']:
            pd.testing.assert_series_equal(updated.loc[~mask,col],nmc.loc[~mask,col],check_dtype=False)
        status['nmc_status']='success; original API hours preserved, unknown/estimated replaced by complete NMC intervals'
        status['nmc_summary']=json.loads((OUT/'nmc_update_summary.json').read_text())
    (OUT/'update_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
    print({k:v for k,v in status.items() if k not in ['processed_sha256','assumptions']})

if __name__=='__main__':main()
