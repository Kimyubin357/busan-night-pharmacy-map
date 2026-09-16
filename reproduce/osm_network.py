"""OSM 공개 보행망 → 전체 대표점×약국 거리. 원본 API 호출 없이 로컬 계산.

실행: .venv-osm/bin/python osm_network.py
좌표계를 EPSG:5179(m)로 바꾸어 길이를 계산합니다. 단절망을 직선으로 이어 붙이지
않습니다. 출발/도착점을 가까운 도로 구간에 투영하고 구간을 실제로 분할합니다.
도로 연결선은 100m 이하만 분석에 허용하는 모형 가정이며 실제 출입구 확인은 아닙니다.
"""
from pathlib import Path
import json,hashlib,pickle,collections
import numpy as np,pandas as pd,osmium
from pyproj import Transformer
from shapely.geometry import LineString,Point
from shapely.strtree import STRtree
from scipy.sparse import csr_matrix,save_npz
from scipy.sparse.csgraph import dijkstra,connected_components

ROOT=Path(__file__).resolve().parent; BASE=ROOT/'team2/osm'; BASE.mkdir(exist_ok=True)
PROJECT=Transformer.from_crs(4326,5179,always_xy=True)
UNPROJECT=Transformer.from_crs(5179,4326,always_xy=True)
BBOX=(128.55,34.75,129.55,35.65) # 부산 밖 우회 경로도 허용하는 버퍼. 행정경계 아님.
ALLOWED={'footway','pedestrian','steps','path','living_street','residential','service','unclassified','tertiary','tertiary_link','secondary','secondary_link','primary','primary_link','track','cycleway'}
DENIED={'no','private','use_sidepath'}

def walk_allowed(tags):
    h=tags.get('highway','');foot=tags.get('foot','')
    if h not in ALLOWED:return False
    if foot in DENIED:return False
    if not foot and tags.get('access','') in {'no','private','customers','delivery'}:return False
    if h=='cycleway' and foot not in {'yes','designated','permissive'}:return False
    # 시간 조건을 임의 해석하지 않고 보수적으로 제외. 제외 건수는 보고합니다.
    if tags.get('foot:conditional') or tags.get('access:conditional'):return False
    if tags.get('indoor')=='yes':return False
    return True

class Reader(osmium.SimpleHandler):
    def __init__(self):
        super().__init__();self.coords={};self.edges=[];self.blocked=set();self.counts=collections.Counter()
    def node(self,n):
        if not (BBOX[0]<=n.location.lon<=BBOX[2] and BBOX[1]<=n.location.lat<=BBOX[3]):return
        t=dict(n.tags)
        if t.get('foot') in DENIED or (t.get('access') in {'no','private'} and t.get('foot') not in {'yes','designated','permissive'}):self.blocked.add(n.id)
        if t.get('barrier') in {'wall','fence'} and t.get('foot') not in {'yes','designated'}:self.blocked.add(n.id)
        if t.get('barrier'):self.counts['barrier_nodes_seen']+=1
    def way(self,w):
        t=dict(w.tags)
        if 'highway' not in t:return
        if not any(n.location.valid() and BBOX[0]<=n.lon<=BBOX[2] and BBOX[1]<=n.lat<=BBOX[3] for n in w.nodes):return
        if not walk_allowed(t):self.counts['excluded_ways']+=1;return
        self.counts['accepted_ways']+=1;self.counts['highway_'+t['highway']]+=1
        direction=t.get('oneway:foot','no')
        wn=list(w.nodes)
        for a,b in zip(wn,wn[1:]):
            if a.ref in self.blocked or b.ref in self.blocked:continue
            if not a.location.valid() or not b.location.valid():continue
            if not all(BBOX[0]<=n.lon<=BBOX[2] and BBOX[1]<=n.lat<=BBOX[3] for n in (a,b)):continue
            self.coords[a.ref]=(a.lon,a.lat);self.coords[b.ref]=(b.lon,b.lat)
            self.edges.append((a.ref,b.ref,w.id,t['highway'],direction))

def sparse_minimum(arcs,n):
    # 여러 OSM way가 같은 점을 연결하면 길이를 합산하지 않고 최솟값을 사용합니다.
    best={}
    for u,v,d in arcs:
        if u==v:continue
        best[u,v]=min(best.get((u,v),float('inf')),max(float(d),.001))
    return csr_matrix(([d for d in best.values()],([k[0] for k in best],[k[1] for k in best])),shape=(n,n))

def main():
    meta=json.loads((ROOT/'reports/latest_run.json').read_text());source=Path(meta['output_dir'])
    demand=pd.read_csv(ROOT/'team2/outputs/demand_nodes.csv',dtype={'node_id':'string'})
    ph=pd.read_csv(source/'pharmacy_master.csv',dtype={'pharmacy_id':'string'})
    fp=BASE/'parsed.pkl'
    if fp.exists():
        with fp.open('rb') as f:coords,raw,counts=pickle.load(f)
    else:
        r=Reader();print('OSM parse start',flush=True)
        r.apply_file(str(BASE/'south-korea-260913.osm.pbf'),locations=True,idx='flex_mem')
        coords,raw,counts=r.coords,r.edges,dict(r.counts)
        with fp.open('wb') as f:pickle.dump((coords,raw,counts),f)
    print('OSM accepted',len(coords),len(raw),counts,flush=True)
    ids=list(coords);lookup={x:i for i,x in enumerate(ids)}
    lonlat=np.array([coords[i] for i in ids]);x,y=PROJECT.transform(lonlat[:,0],lonlat[:,1]);xy=list(zip(x,y))
    segments=[];geoms=[]
    for a,b,w,h,d in raw:
        u,v=lookup[a],lookup[b];g=LineString([xy[u],xy[v]])
        if g.length<.01:continue
        segments.append((u,v,w,h,d));geoms.append(g)
    tree=STRtree(geoms)
    # 도로에서100m 넘게 떨어진 대표점은 같은 행정동의 실제 주소점으로만 대체합니다.
    # 최대1km 이내에서 원래 대표점에 가장 가까운, 도로100m 이내 주소를 선택합니다.
    # 약국 위치는 임의 이동하지 않습니다. 변경 전후 주소·이동거리를 별도 기록합니다.
    changes=[];addresses=None
    for i,r in demand.iterrows():
        xx,yy=PROJECT.transform(r.longitude,r.latitude);pt=Point(xx,yy)
        if pt.distance(geoms[int(tree.nearest(pt))])<=100:continue
        if addresses is None:
            from team2_pipeline import normalize_dong
            addresses=pd.read_csv(ROOT/'team2/inputs/15028854.csv',encoding='cp949',dtype='string')
            addresses['key']=(addresses['시군구명'].fillna('')+addresses['관할행정동'].fillna('')).map(normalize_dong)
        from team2_pipeline import normalize_dong
        group=addresses[addresses.key.eq(normalize_dong(r.dong_name))].copy()
        group['lat']=pd.to_numeric(group['위도'],errors='coerce');group['lon']=pd.to_numeric(group['경도'],errors='coerce');group=group.dropna(subset=['lat','lon'])
        ax,ay=PROJECT.transform(group.lon.to_numpy(float),group.lat.to_numpy(float));group['displacement']=np.hypot(ax-xx,ay-yy)
        for _,a in group.sort_values('displacement').iterrows():
            if a.displacement>1000:break
            tx,ty=PROJECT.transform(a.lon,a.lat);ap=Point(tx,ty)
            gap=ap.distance(geoms[int(tree.nearest(ap))])
            if gap>100:continue
            newaddress=str(a['시군구명'])+' '+str(a['도로명'])+' '+str(a['본번'])+'-'+str(a['부번'])
            changes.append({'node_id':r.node_id,'dong_name':r.dong_name,'original_latitude':r.latitude,'original_longitude':r.longitude,'original_address':r.representative_address,'new_latitude':a.lat,'new_longitude':a.lon,'new_address':newaddress,'displacement_m':float(a.displacement),'new_snap_distance_m':float(gap),'reason':'nearest_actual_address_within_same_dong_and_100m_of_OSM; max_displacement1km'})
            demand.loc[i,['latitude','longitude','representative_address','point_method']]=[a.lat,a.lon,newaddress,'OSM_connectable_actual_address_fallback']
            break
    demand.to_csv(BASE/'demand_nodes_routing.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(changes).to_csv(BASE/'representative_adjustments.csv',index=False,encoding='utf-8-sig')
    print('representative adjustments',changes,flush=True)
    points=pd.concat([demand[['node_id','latitude','longitude']].rename(columns={'node_id':'entity_id'}).assign(entity_type='demand'),ph[['pharmacy_id','latitude','longitude']].rename(columns={'pharmacy_id':'entity_id'}).assign(entity_type='pharmacy')],ignore_index=True)
    splits=collections.defaultdict(list);snaps=[];arcs=[]
    for r in points.itertuples():
        xx,yy=PROJECT.transform(r.longitude,r.latitude);point=Point(xx,yy);edge=int(tree.nearest(point));g=geoms[edge]
        offset=g.project(point);snap=g.interpolate(offset);gap=point.distance(snap)
        virtual=len(xy);xy.append((snap.x,snap.y));actual=len(xy);xy.append((xx,yy))
        splits[edge].append((offset,virtual))
        if gap<=100:arcs.extend([(actual,virtual,gap),(virtual,actual,gap)])
        slon,slat=UNPROJECT.transform(snap.x,snap.y)
        snaps.append({'entity_id':r.entity_id,'entity_type':r.entity_type,'graph_node':actual,'snap_node':virtual,'snap_distance_m':gap,'snap_longitude':slon,'snap_latitude':slat,'osm_way_id':segments[edge][2],'snap_highway':segments[edge][3],'snap_status':'accepted_model_connector' if gap<=100 else 'review_over_100m'})
    for i,(u,v,w,h,direction) in enumerate(segments):
        path=[(0,u)]+sorted(splits[i])+[(geoms[i].length,v)]
        for (p,a),(q,b) in zip(path,path[1:]):
            if direction not in {'-1'}:arcs.append((a,b,q-p))
            if direction not in {'yes','1','true'}:arcs.append((b,a,q-p))
    graph=sparse_minimum(arcs,len(xy));ncomp,labels=connected_components(graph,directed=True,connection='weak');sizes=np.bincount(labels)
    snaps=pd.DataFrame(snaps);snaps['component_id']=labels[snaps.graph_node.to_numpy()];snaps['component_nodes']=sizes[snaps.component_id.to_numpy()]
    snaps.to_csv(BASE/'snapping.csv',index=False,encoding='utf-8-sig');save_npz(BASE/'graph.npz',graph);np.save(BASE/'graph_xy.npy',xy)
    starts=snaps.loc[snaps.entity_type.eq('demand'),'graph_node'].to_numpy();ends=snaps.loc[snaps.entity_type.eq('pharmacy'),'graph_node'].to_numpy()
    matrix=np.full((len(starts),len(ends)),np.inf)
    for i in range(0,len(starts),8):
        print('Dijkstra',i,'/',len(starts),flush=True)
        dist=dijkstra(graph,directed=True,indices=starts[i:i+8]);matrix[i:i+8]=dist[:,ends]
    np.save(BASE/'distance_matrix_m.npy',matrix)
    qa={'osm_source':'https://download.geofabrik.de/asia/south-korea-260913.osm.pbf','osm_date':'2026-09-13','pbf_sha256':hashlib.sha256((BASE/'south-korea-260913.osm.pbf').read_bytes()).hexdigest(),'bbox':BBOX,'graph_nodes':len(xy),'directed_arcs':graph.nnz,'weak_components':int(ncomp),'largest_component_nodes':int(sizes.max()),'counts':counts,'snap_status':snaps.snap_status.value_counts().to_dict(),'snap_distance_quantiles_m':snaps.snap_distance_m.quantile([.5,.9,.95,.99,1]).to_dict(),'pair_count':int(matrix.size),'finite_pairs':int(np.isfinite(matrix).sum()),'demand_count':len(demand),'pharmacy_count':len(ph),'route_model':'public outdoor OSM walking; steps included; no slope; foot direction respected; no turn-restriction relations; <=100m straight connector'}
    (BASE/'network_quality.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2));print(json.dumps(qa,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
