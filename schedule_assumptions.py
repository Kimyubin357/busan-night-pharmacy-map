"""원본을 보존하며 월요일 시간 및 일요일 휴무/공공심야 운영 가정을 적용합니다."""
from pathlib import Path
import json
import pandas as pd
from collections import Counter
P=Path(__file__).resolve().parent
UP=P.parent/'team2/update_20260915'

def build_schedules():
    source=Path(json.loads((P.parent/'reports/latest_run.json').read_text())['output_dir'])
    original=pd.read_csv(source/'pharmacy_opening_hours_analysis.csv').fillna('')
    merged=pd.read_csv(UP/'pharmacy_opening_hours_nmc.csv').fillna('')
    nmc=pd.read_csv(UP/'nmc_opening_hours_long.csv').fillna('')
    conflicts=pd.read_csv(UP/'nmc_hours_comparison.csv')
    conflict_keys={(r.pharmacy_id,r.day_code) for r in conflicts.itertuples() if r.conflict and not r.applied}
    raw={(r.pharmacy_id,int(r.day_code)):r for r in original.itertuples()}
    nm={(r.pharmacy_id,int(r.day_code)):r for r in nmc.itertuples()}
    rows={(r.pharmacy_id,int(r.day_code)):r for r in merged.itertuples()}
    policy=pd.read_csv(P.parent/'team2_handoff/public_policy_hours.csv').set_index('pharmacy_id')
    ids=sorted({k[0] for k in rows}|{k[0] for k in nm})
    weekly={};audit=[];counts=Counter();conflict_audit=[]
    route_ids={k[0] for k in rows}
    def interval(r):
        if r is None or r.start_minute=='' or r.end_minute_unwrapped=='':return None
        return [[float(r.start_minute),float(r.end_minute_unwrapped)]]
    def blank(r):return r is None or (r.start_raw=='' and r.end_raw=='')
    for pid in ids:
        w={};sources={}
        for day in range(1,8):
            key=(pid,day);r=rows.get(key,nm.get(key));iv=interval(r)
            if r is not None and getattr(r,'start_value_source','')=='hira_202606_supplement':iv=None
            status='observed' if iv is not None else 'unknown'
            if key in conflict_keys:
                old=iv;iv=interval(nm.get(key));status='nmc_conflict_resolved' if iv is not None else 'unknown'
                conflict_audit.append(dict(pharmacy_id=pid,day_code=day,previous=json.dumps(old),nmc=json.dumps(iv),status=status))
                counts['conflict_days_resolved_nmc' if iv is not None else 'conflict_days_error']+=1
            w[day]=iv;sources[day]=status
        weekdays=[w[d] for d in range(2,6)]
        equal=all(v is not None for v in weekdays) and all(v==weekdays[0] for v in weekdays)
        before_mon=w[1];before_sun=w[7];before_sat=w[6]
        if w[1] is None and equal:
            w[1]=[v[:] for v in weekdays[0]];sources[1]='assumed_monday_tue_fri_equal'
        origin_blank=blank(raw.get((pid,7)))
        nmc_blank=blank(nm.get((pid,7)))
        tue_fri_complete=all(w[d] is not None for d in range(2,6))
        weekend_blank=all(blank(raw.get((pid,d))) and blank(nm.get((pid,d))) for d in [6,7])
        if pid not in policy.index and tue_fri_complete and weekend_blank and w[6] is None and w[7] is None:
            w[6]=[];w[7]=[]
            sources[6]=sources[7]='assumed_weekend_closed_original_blank'
        tue_sat_complete=all(w[d] is not None for d in range(2,7))
        sat_equal=equal and w[6]==weekdays[0]
        if pid in policy.index:
            pol=policy.loc[pid];night=[float(pol.start_minute),float(pol.end_minute)]
            # 실제 기록을 유지하면서 공공심야 일요일 정책시간을 별도 가정합니다.
            if w[7] is None or not any(a<=night[0] and b>=night[1] for a,b in w[7]):
                w[7]=(w[7] or [])+[night];sources[7]='assumed_public_sunday_policy'
        elif w[7] is None and origin_blank and nmc_blank and tue_sat_complete:
            w[7]=[];sources[7]='assumed_sunday_closed_original_blank'
        weekly[pid]=w
        counts['total_pharmacies']+=1
        counts[sources[1]]+=1
        counts['sunday_'+sources[7]]+=1
        counts['saturday_'+sources[6]]+=1
        audit.append(dict(pharmacy_id=pid,monday_before=json.dumps(before_mon),monday_after=json.dumps(w[1]),monday_source=sources[1],tue_fri_equal=equal,saturday_complete=w[6] is not None,saturday_equals_weekdays=sat_equal,sunday_original_both_blank=origin_blank,sunday_nmc_both_blank=nmc_blank,sunday_before=json.dumps(before_sun),sunday_after=json.dumps(w[7]),sunday_source=sources[7],saturday_before=json.dumps(before_sat),saturday_after=json.dumps(w[6]),saturday_source=sources[6],conflict_days_resolved_nmc=json.dumps([d for d in range(1,8) if sources[d]=='nmc_conflict_resolved']),error_days=json.dumps([d for d in range(1,8) if w[d] is None]),in_route_model=pid in route_ids))
    pd.DataFrame(audit).to_csv(P/'schedule_assumptions_audit.csv',index=False)
    pd.DataFrame(conflict_audit).to_csv(P/'nmc_conflict_resolutions.csv',index=False)
    pd.DataFrame([r for r in audit if r['sunday_source']=='unknown']).to_csv(P/'remaining_sunday_errors.csv',index=False)
    edge_path=P/'sunday_109_edge_cases.csv'
    if edge_path.exists():
        edge=pd.read_csv(edge_path);by_id={r['pharmacy_id']:r for r in audit}
        for field in ['saturday_source','sunday_source','saturday_after','sunday_after','error_days']:
            edge['current_'+field]=edge['id'].map(lambda pid:by_id[pid][field])
        edge.to_csv(edge_path,index=False)
    (P/'schedule_assumptions_summary.json').write_text(json.dumps(dict(counts),ensure_ascii=False,indent=2))
    return weekly,{r['pharmacy_id']:r for r in audit},dict(counts)

if __name__=='__main__':
    print(json.dumps(build_schedules()[2],ensure_ascii=False,indent=2))
