"""검토된 8개 주소 보정 및 전체 목록의 건물점 거리 차이 감사표를 생성합니다."""
import csv, gzip, json
import pandas as pd
from pharmacy_locations import review_config, validate_address_source, resolve_location, corrected_master, address_key, distance_m
from pipeline_context import ROOT, processed_source

def main():
    cfg = review_config(); lookup = validate_address_source(cfg)
    master_path = processed_source() / 'pharmacy_master.csv'
    frame = pd.read_csv(master_path).fillna('')
    # 도로망 계산도 지도와 동일한 보정 좌표를 입력으로 사용합니다.
    corrected_master(frame).to_csv(master_path, index=False, encoding='utf-8-sig')
    records = {}
    with (ROOT/'team2/update_20260915/nmc_busan_pharmacies.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            records[r['hpid']] = dict(id=r['hpid'],name=r['dutyName'],address=r['dutyAddr'],phone=r['dutyTel1'],lat=float(r['wgs84Lat']),lon=float(r['wgs84Lon']))
    for r in frame.to_dict('records'):
        records.setdefault(r['pharmacy_id'],dict(id=r['pharmacy_id'],name=r['name'],address=r['address'],phone=r['phone'],lat=r['latitude'],lon=r['longitude']))
    corrections, pending, matched = [], [], 0
    for r in records.values():
        lat, lon, meta = resolve_location(r['id'],r['name'],r['address'],r['phone'],r['lat'],r['lon'],cfg)
        if meta and meta['status']=='address_point_corrected':
            corrections.append(dict(**r,corrected_lat=lat,corrected_lon=lon,shift_m=round(distance_m(r['lat'],r['lon'],lat,lon),2),reviewed_at=cfg['reviewed_at'],source=cfg['source'],source_url=cfg['source_url']))
        points = lookup.get(address_key(r['address']), set())
        if len(points)!=1: continue
        matched += 1
        al,ao = next(iter(points)); gap=distance_m(lat,lon,al,ao)
        if gap>250:
            pending.append(dict(**r,address_point_lat=al,address_point_lon=ao,distance_m=round(gap,2),status='needs_location_review',reason='주소 건물점과 250m 초과 차이 · 오류 확정/자동 이동 아님'))
    def write(name, rows, fields):
        with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    write('coordinate_corrections.csv',corrections,list(corrections[0]) if corrections else ['id'])
    write('coordinate_building_review.csv',pending,list(pending[0]) if pending else ['id'])
    summary=dict(reviewed_at=cfg['reviewed_at'],address_source=cfg['source'],source_url=cfg['source_url'],source_sha256=cfg['source_sha256'],map_records=len(records),exact_address_matches=matched,corrected=len(corrections),building_distance_review=len(pending),review_threshold_m=250,note=cfg['method'])
    (ROOT/'coordinate_validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
