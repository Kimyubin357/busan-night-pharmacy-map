"""접근성 분석 대상과 독립된 전체 약국 지도 목록을 구성합니다."""
from pathlib import Path
import csv
from shapely.geometry import Point, shape

P = Path(__file__).resolve().parent

def build_map_pharmacies(data):
    existing = {p['id']: p for p in data['pharmacies']}
    points = {}
    source = P.parent / 'team2/update_20260915/nmc_busan_pharmacies.csv'
    with source.open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            lat, lon = float(row['wgs84Lat']), float(row['wgs84Lon'])
            if not (34 < lat < 36 and 128 < lon < 130):
                raise ValueError(f"부산 지도 좌표 확인 필요: {row['hpid']}")
            original = existing.get(row['hpid'])
            points[row['hpid']] = dict(id=row['hpid'], name=row['dutyName'],
                address=row['dutyAddr'], phone=row['dutyTel1'], lat=lat, lon=lon,
                designated=bool(original and original['designated']),
                source='NMC '+data['meta']['pharmacy_collected_at'][:10]+' 조회')
    # 최신 API에서 누락된 기존 시설도 표시하되 확인 필요 상태를 명시합니다.
    for pid, p in existing.items():
        if pid not in points:
            points[pid] = {k: p[k] for k in ['id', 'name', 'address', 'phone', 'lat', 'lon', 'designated']}
            points[pid]['source'] = '기존 부산 약국 목록 · 최신 API 미조회, 운영 여부 확인 필요'
    from schedule_assumptions import build_schedules
    weekly,audit,_=build_schedules()
    dong_shapes=[(shape(f['geometry']),data['dongs'][f['properties']['i']]) for f in data['boundaries']['features']]
    for pid,p in points.items():
        p['schedule']=[weekly[pid][d] for d in range(1,8)]
        p['scheduleSources']={'monday':audit[pid]['monday_source'],'sunday':audit[pid]['sunday_source'],'saturday':audit[pid]['saturday_source']}
        area=next((d for geom,d in dong_shapes if geom.covers(Point(p['lon'],p['lat']))),None)
        p['district']=area['district'] if area else (existing.get(pid,{}).get('district') or '')
        p['dong']=area['name'] if area else ''
    return list(points.values())
