"""SGIS 100m 거주인구로 동 내부 수요를 배분하는 별도 시나리오.

2024년 격자인구는 2025년 12월 심야 생활인구와 다른 통계입니다. 따라서 원본
생활인구를 바꾸지 않고, 동 내 분포를 추정하는 가중치로만 사용합니다.
경계를 가로지르는 격자는 행정동과 겹치는 면적 비율로 나눕니다. 이는 격자
내 균등분포 가정이며, 개인정보 보호를 위해 조정된 격자인구의 한계도 남습니다.
동별 합계를 보존하고 신호동 등 행정동 매칭 누락은 오류로 중단합니다.
"""
from pathlib import Path
from zipfile import ZipFile
import io, json, re
import numpy as np
import pandas as pd
import shapefile
from shapely.geometry import shape
from shapely.strtree import STRtree
from pyproj import CRS, Transformer

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'team2/update_20260915'
RAW=OUT/'raw'

def reader(filename, suffix):
    z=ZipFile(RAW/filename)
    stem=next(n[:-4] for n in z.namelist() if n.endswith(suffix+'.shp'))
    crs=CRS.from_wkt(z.read(stem+'.prj').decode())
    # ESRI WKT의 측지기준 명칭이 달라도 투영 파라미터를 모두 대조합니다.
    actual=crs.to_dict(); expected=CRS.from_epsg(5179).to_dict()
    assert all(actual.get(k)==expected.get(k) for k in ['proj','lat_0','lon_0','k','x_0','y_0','ellps','units'])
    return shapefile.Reader(**{e:io.BytesIO(z.read(stem+'.'+e)) for e in ['shp','shx','dbf']},
                            encoding=z.read(stem+'.cpg').decode().strip())

def normalize(s):
    # '하단제1동'/'하단1동' 등 표기만 통일. 이름만으로 타 구의 동을 합치지 않습니다.
    return re.sub(r'[\s·ㆍ.]','',str(s)).replace('제','')

def main():
    ctx=__import__('pipeline_context').context();month=ctx['population_month']
    demand=pd.read_csv(ROOT/'team2/outputs/demand_nodes.csv',dtype={'dong_code':str,'node_id':str})
    z=ZipFile(RAW/'sgis_codebook.zip')
    codefile=next(n for n in z.namelist() if 'adm_code' in n)
    codes=pd.read_excel(io.BytesIO(z.read(codefile)),sheet_name=f"{ctx['boundary_date'][:4]}년 {int(ctx['boundary_date'][5:7])}월",header=1,dtype=str)
    codes=codes[codes['시도명칭'].eq('부산광역시')].copy()
    codes['sgis_code']=codes['시도코드'].str.zfill(2)+codes['시군구코드'].str.zfill(3)+codes['읍면동코드'].str.zfill(3)
    codes['key']=codes['시군구명칭'].map(normalize)+'|'+codes['읍면동명칭'].map(normalize)
    demand['key']=demand.district.map(normalize)+'|'+demand.apply(lambda r: normalize(str(r.dong_name).removeprefix(str(r.district))),axis=1)
    assert not codes.key.duplicated().any() and not demand.key.duplicated().any()
    cross=demand.merge(codes[['key','sgis_code']],on='key',how='left',validate='one_to_one')
    cross.to_csv(OUT/'sgis_dong_crosswalk.csv',index=False)
    if cross.sgis_code.isna().any():
        raise ValueError('SGIS 동 연결 실패: '+str(cross.loc[cross.sgis_code.isna(),['dong_name','key']].to_dict('records')))
    lookup=cross.set_index('sgis_code')
    geoms=[]; ids=[]
    for rec in reader('sgis_dong.zip','2025_2Q').iterShapeRecords():
        code=rec.record['ADM_CD']
        if code in lookup.index:
            g=shape(rec.shape.__geo_interface__)
            assert g.is_valid
            ids.append(code);geoms.append(g)
    assert set(ids)==set(lookup.index)
    tree=STRtree(geoms)
    popzip=ZipFile(RAW/'sgis_grid_population.zip')
    pieces=[]; grids_seen=0; missing=0
    for tile,label in [('마라','mara'),('마마','mama')]:
        pop=pd.read_csv(io.BytesIO(popzip.read(f'2024년_인구_{tile}_100M.csv')),encoding='cp949',
                        header=None,names=['year','grid_id','item','value'],dtype={'grid_id':str,'item':str})
        pop=pop[pop.item.eq('to_in_001')].copy()
        assert not pop.grid_id.duplicated().any()
        pop['value']=pd.to_numeric(pop.value,errors='coerce')
        values=pop.set_index('grid_id').value.to_dict()
        for rec in reader(f'sgis_grid_{label}.zip','100M').iterShapeRecords():
            gid=rec.record['GRID_CD']
            if gid not in values:continue
            g=shape(rec.shape.__geo_interface__)
            candidates=tree.query(g,predicate='intersects')
            if not len(candidates):continue
            grids_seen+=1
            value=values[gid]
            if not np.isfinite(value):missing+=1;continue
            if value<=0:continue
            for j in candidates:
                inter=g.intersection(geoms[j])
                if inter.area<.01:continue
                # 경계 격자는 중복 집계하지 않고 원래 격자 면적에 대한 비율로 나눕니다.
                fraction=inter.area/g.area
                point=inter.representative_point()
                pieces.append(dict(grid_id=gid,sgis_code=ids[j],source_grid_population=value,
                    intersection_area_fraction=fraction,resident_mass=value*fraction,
                    x_5179=point.x,y_5179=point.y))
    grid=pd.DataFrame(pieces)
    assert not grid[['grid_id','sgis_code']].duplicated().any()
    grid=grid.merge(cross[['sgis_code','dong_code','dong_name','district','night_population_proxy','night_mean_resident']],on='sgis_code',validate='many_to_one')
    assert grid.dong_code.nunique()==len(demand)
    # 동별로 정규화하여 원래 각 행정동의 생활인구 총량을 보존합니다.
    grid['weight_within_dong']=grid.resident_mass/grid.groupby('dong_code').resident_mass.transform('sum')
    grid['allocated_night_total_proxy']=grid.weight_within_dong*grid.night_population_proxy
    grid['allocated_night_resident_proxy']=grid.weight_within_dong*grid.night_mean_resident
    grid['population_year']=ctx['grid_year']
    grid['boundary_date']=ctx['boundary_date']
    grid['living_population_month']=month
    grid['allocation_method']='resident_grid_share_area_split'
    inverse=Transformer.from_crs(5179,4326,always_xy=True)
    grid['longitude'],grid['latitude']=inverse.transform(grid.x_5179.to_numpy(),grid.y_5179.to_numpy())
    # 같은 격자가 행정동 경계에서 나뉘어도 각 조각에 고유 키를 부여합니다.
    grid['grid_node_id']=grid.dong_code+'_'+grid.grid_id
    grid.to_csv(OUT/'sgis_grid_demand.csv',index=False)
    # 22시·23시·00시를 평균으로 뭉개지 않고 각 시간대 총량도 따로 보존합니다.
    source=__import__('pipeline_context').processed_source()
    hourly=pd.read_csv(source/'living_population_hourly.csv',dtype={'dong_code':str,'month':str})
    hourly=hourly[hourly.month.eq(month) & hourly.hour.isin([22,23,0])]
    hourly=hourly[['dong_code','hour','resident','worker','visitor','total_population_proxy']]
    expanded=grid[['grid_node_id','dong_code','weight_within_dong']].merge(hourly,on='dong_code',validate='many_to_many')
    for col in ['resident','worker','visitor','total_population_proxy']:
        expanded['allocated_'+col]=expanded.weight_within_dong*expanded[col]
    # worker/visitor 배분도 같은 거주인구 비중을 쓰는 가정입니다. 실측 분포가 아닙니다.
    expanded['allocation_method']='resident_share_proxy_not_observed_night_grid_population'
    assert not expanded[['grid_node_id','hour']].duplicated().any()
    original=hourly.groupby(['dong_code','hour']).total_population_proxy.sum().sort_index()
    allocated=expanded.groupby(['dong_code','hour']).allocated_total_population_proxy.sum().sort_index()
    assert original.index.equals(allocated.index) and np.allclose(original,allocated,atol=1e-7)
    expanded.to_csv(OUT/'sgis_grid_hourly_demand.csv',index=False)
    summaries=[]
    forward=Transformer.from_crs(4326,5179,always_xy=True)
    for code,sub in grid.groupby('dong_code'):
        base=cross.loc[cross.dong_code.eq(code)].iloc[0]
        x=float((sub.x_5179*sub.weight_within_dong).sum());y=float((sub.y_5179*sub.weight_within_dong).sum())
        # 가중 중심이 도로 위라는 보장은 없습니다. 진단용이며 경로 출발점으로 바로 쓰지 않습니다.
        ox,oy=forward.transform(base.longitude,base.latitude)
        lon,lat=inverse.transform(x,y)
        summaries.append(dict(dong_code=code,dong_name=base.dong_name,grid_nodes=len(sub),
            weight_sum=sub.weight_within_dong.sum(),allocated_total=sub.allocated_night_total_proxy.sum(),
            original_total=base.night_population_proxy,total_error=sub.allocated_night_total_proxy.sum()-base.night_population_proxy,
            weighted_center_longitude=lon,weighted_center_latitude=lat,
            displacement_from_old_point_m=float(np.hypot(x-ox,y-oy))))
    audit=pd.DataFrame(summaries)
    assert np.allclose(audit.weight_sum,1) and np.allclose(audit.allocated_total,audit.original_total,atol=1e-7)
    audit.to_csv(OUT/'sgis_weighting_audit.csv',index=False)
    summary=dict(dongs=len(audit),grid_nodes=len(grid),unique_grids=grid.grid_id.nunique(),
                 intersecting_grid_records=grids_seen,missing_value_grid_records=missing,
                 total_original=float(audit.original_total.sum()),total_allocated=float(audit.allocated_total.sum()),
                 max_dong_total_error=float(audit.total_error.abs().max()),
                 median_center_shift_m=float(audit.displacement_from_old_point_m.median()),
                 route_recalculation_complete=False,elderly_grid_population_available=False,
                 note='2024년 거주인구 비중으로 2025년12월 심야 수요를 배분한 추정 시나리오. 관측 심야 격자인구가 아님. 미수록 격자는 인구 0으로 확정하지 않음.')
    (OUT/'sgis_weighting_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2));print(grid.head(3).to_string(index=False))

if __name__=='__main__':main()
