"""독립 정방향 최단경로 및 화면용 압축 데이터의 집계 일치 검증."""
from pathlib import Path
import json,gzip
import numpy as np,pandas as pd
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
P=Path(__file__).resolve().parent;R=P.parent
D=json.loads(gzip.decompress((P/'data.json.gz').read_bytes()));checks={}
w=np.array(D['grids']['weight']);di=np.array(D['grids']['dong']);assert w.shape==(3,21963) and set(di)==set(range(206));assert np.all(w>=0)
checks['grid_count']=w.shape[1]
for mode,m in D['models'].items():
 k=np.array(m['known']);p=np.array(m['possible']);W=w[np.arange(21)%3]
 for t in [5,10,15]:
  lo=(k>=0)&(k<=60*t);hi=(p>=0)&(p<=60*t);assert np.all(~lo|hi)
  assert abs((W*lo).sum()/21-m['summary'][str(t)]['lower'])<.1
  assert abs((W*hi).sum()/21-m['summary'][str(t)]['upper'])<.1
  for row in m['rankings'][str(t)]:
   ph=D['pharmacies'][row['j']];ix=np.array(ph['reach'],dtype=int)[np.array(ph['seconds'])<=t*60];ux=np.array(ph['uncertain'],dtype=int)[np.array(ph['uncertainSeconds'])<=t*60]
   a=(W[:,ix]*(~hi[:,ix])).sum()/21;b=(W[:,ix]*(~lo[:,ix])).sum()/21+(W[:,ux]*(~lo[:,ux])).sum()/21
   assert abs(a-row['low'])<.1 and abs(b-row['high'])<.1 and a<=b+.1
checks['all_10062_candidate_scores_recomputed']=True
G=load_npz(R/'team2/osm/graph.npz');snap=np.load(P/'grid_snap_edges.npz');ends=pd.read_csv(R/'team2/osm/snapping.csv');ends=ends.loc[ends.entity_type.eq('pharmacy'),'graph_node'].to_numpy(int);dist=np.load(P/'grid_distance_m.npy',mmap_mode='r')
ix=np.flatnonzero(np.isfinite(dist).any(axis=1));sample=ix[np.linspace(0,len(ix)-1,20,dtype=int)];error=0
for i in sample:
 a=dijkstra(G,indices=int(snap['gu'][i]),limit=1000)[ends]+snap['cu'][i];b=dijkstra(G,indices=int(snap['gv'][i]),limit=1000)[ends]+snap['cv'][i];v=np.minimum(a,b);v[v>1000]=np.inf
 assert np.array_equal(np.isfinite(v),np.isfinite(dist[i]));mask=np.isfinite(v);error=max(error,float(np.max(abs(v[mask]-dist[i,mask]),initial=0)))
assert error<.001
checks['forward_route_origins_checked']=len(sample);checks['max_distance_error_m']=error
old=json.loads((P/'model_summary_with_hira.json').read_text());delta={m:{t:{s:D['models'][m]['summary'][t][s]-old[m][t][s] for s in ['lower','upper']} for t in ['5','10','15']} for m in old}
checks['difference_from_hira_reference_includes_schedule_assumptions']=delta
(P/'validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));print(json.dumps(checks,ensure_ascii=False,indent=2))
