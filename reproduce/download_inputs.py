#!/usr/bin/env python3
"""공개 원천파일을 재현 파이프라인의 정해진 위치에 내려받고 해시를 기록합니다."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
import hashlib, json

ROOT=Path(__file__).resolve().parent
INPUT=ROOT/'team2/inputs'; RAW=ROOT/'team2/update_20260915/raw'; OSM=ROOT/'team2/osm'

def get(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    print('download',path,flush=True)
    req=Request(url,headers={'User-Agent':'BusanNightPharmacyReproduction/1.0'})
    with urlopen(req,timeout=180) as r, path.open('wb') as f:
        while chunk:=r.read(1024*1024): f.write(chunk)
    return {'url':url,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def latest_from_metadata(name,out):
    meta=json.loads((INPUT/name).read_text())
    rows=[x for x in meta['fileList'] if x.get('downurl')]
    return get(max(rows,key=lambda x:str(x.get('updatedAt') or ''))['downurl'],INPUT/out)

def main():
    records={}
    records['road_address']=latest_from_metadata('15028854_metadata.json','15028854.csv')
    records['age_population']=latest_from_metadata('PD_LP00002_metadata.json','PD_LP00002.xlsx')
    sgis={
      'sgis_grid_population.zip':'https://link.mods.go.kr/census/reqdoc/1789222868357.zip',
      'sgis_grid_mara.zip':'https://link.mods.go.kr/grid_border/grid_2025/grid_%EB%A7%88%EB%9D%BC/grid_%EB%A7%88%EB%9D%BC.zip',
      'sgis_grid_mama.zip':'https://link.mods.go.kr/grid_border/grid_2025/grid_%EB%A7%88%EB%A7%88/grid_%EB%A7%88%EB%A7%88.zip',
      'sgis_dong.zip':'https://link.mods.go.kr/census/bnd_data/bnd_dong/bnd_dong_00_2025_2Q.zip',
      'sgis_codebook.zip':'https://link.mods.go.kr/contents/include/download.jsp?filename=ref_code.zip&path=/board/&type=board'}
    for name,url in sgis.items(): records[name]=get(url,RAW/name)
    records['osm']=get('https://download.geofabrik.de/asia/south-korea-latest.osm.pbf',OSM/'south-korea-260913.osm.pbf')
    (ROOT/'download_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    print('완료. 최신 파일은 기준 스냅샷과 값이 달라질 수 있습니다.')
if __name__=='__main__':main()
