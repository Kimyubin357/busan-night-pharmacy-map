"""SGIS 격자 출발점의 도보 15분 이내 거리 재계산.
기존 도로 구간에 투영하되 최근접 교차로로 점프하지 않습니다. 약국→출발점 역방향
다익스트라를 사용해 전체 경로 대신 필요한 1km 범위만 계산합니다. 1km 초과는
경로 미상과 구분하며, 연결 불확실성은 별도 배열에 남깁니다.
"""
from pathlib import Path
import sys,json,time
import numpy as np,pandas as pd
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra,connected_components
from shapely import linestrings,points,line_locate_point,line_interpolate_point,distance
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'dashboard_v3';UP=ROOT/'team2/update_20260915'

sys.path.insert(0,str(ROOT))

def main():
 ctx=__import__('pipeline_context').context();distance_limit=ctx['distance_limit_m']
 grid=pd.read_csv(UP/'sgis_grid_demand.csv',dtype={'dong_code':str});g=load_npz(ROOT/'team2/osm/graph.npz');xy=np.load(ROOT/'team2/osm/graph_xy.npy');snaps=pd.read_csv(ROOT/'team2/osm/snapping.csv')
 # 기존 출발점/약국의 직선 연결선은 새로운 격자가 붙을 도로가 아닙니다.
 actual=snaps.graph_node.to_numpy(int);coo=g.tocoo();ok=~np.isin(coo.row,actual)&~np.isin(coo.col,actual)
 u=np.minimum(coo.row[ok],coo.col[ok]);v=np.maximum(coo.row[ok],coo.col[ok]);pairs=np.unique(np.column_stack([u,v]),axis=0);u,v=pairs.T
 lines=linestrings(np.stack([xy[u],xy[v]],axis=1));tree=STRtree(lines);pts=points(grid[['x_5179','y_5179']].to_numpy());ix=tree.nearest(pts)
 sel=lines[ix];offset=line_locate_point(sel,pts);proj=line_interpolate_point(sel,offset);gap=distance(pts,proj);length=np.linalg.norm(xy[v[ix]]-xy[u[ix]],axis=1)
 gu,gv=u[ix],v[ix];forward=np.asarray(g[gu,gv]).ravel()>0;backward=np.asarray(g[gv,gu]).ravel()>0
 # 출발점에서 간선 양 끝까지의 비용. 보행 일방통행 방향을 보존합니다.
 cu=np.where(backward,gap+offset,np.inf);cv=np.where(forward,gap+length-offset,np.inf);valid=gap<=100;cu[~valid]=np.inf;cv[~valid]=np.inf
 np.savez(OUT/'grid_snap_edges.npz',gu=gu,gv=gv,cu=cu,cv=cv,valid=valid)
 _,components=connected_components(g,directed=True,connection='strong');component=components[gu]
 ps=snaps[snaps.entity_type.eq('pharmacy')].reset_index(drop=True);ends=ps.graph_node.to_numpy(int)
 matrix=np.lib.format.open_memmap(OUT/'grid_distance_m.npy',mode='w+',dtype='float32',shape=(len(grid),len(ends)))
 transpose=g.T.tocsr();start=time.time()
 for j,node in enumerate(ends):
  d=dijkstra(transpose,directed=True,indices=int(node),limit=distance_limit)
  values=np.minimum(d[gu]+cu,d[gv]+cv);values[values>distance_limit]=np.inf;matrix[:,j]=values
  if j%200==0:print('pharmacy',j,'/',len(ends),'seconds',round(time.time()-start),flush=True)
 matrix.flush()
 # 도로 연결 성분이 다르거나 도로에서 먼 점은 접근 불가능으로 단정하지 않습니다.
 unresolved=(~valid[:,None])|(component[:,None]!=components[ends][None,:])
 np.save(OUT/'grid_route_uncertain.npy',unresolved)
 grid['snap_distance_m']=gap;grid['route_snap_accepted']=valid;grid['road_component']=component
 grid.to_csv(OUT/'grid_nodes_routing.csv',index=False)
 meta=dict(grid_nodes=len(grid),pharmacies=len(ends),pair_count=int(matrix.size),within_limit_pairs=int(np.isfinite(matrix).sum()),within1km_pairs=int((matrix<=1000).sum()),snap_over100m=int((~valid).sum()),snap_over100m_population_share=float(grid.loc[~valid,'allocated_night_total_proxy'].sum()/grid.allocated_night_total_proxy.sum()),max_distance_m=distance_limit,speed_kmh=4,slope_included=False)
 (OUT/'grid_route_quality.json').write_text(json.dumps(meta,indent=2));print(meta,flush=True)
if __name__=='__main__':main()
