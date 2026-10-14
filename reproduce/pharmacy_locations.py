"""시설 ID를 유지한 주소 건물점 보정. 원본 API 좌표와 이름별 시설은 합치지 않습니다."""
from pathlib import Path
import csv, hashlib, json, math, re

ROOT = Path(__file__).resolve().parent

def review_config():
    return json.loads((ROOT / 'pharmacy_location_overrides.json').read_text())

def address_key(address):
    m = re.search(r'(\S+(?:구|군))\s+(?:(?:\S+(?:읍|면))\s+)?(\S+(?:로|길))\s+(\d+)(?:-(\d+))?', address)
    return (m[1], m[2], str(int(m[3])), str(int(m[4] or 0))) if m else None

def distance_m(lat, lon, other_lat, other_lon):
    a, b = math.radians(float(lat)), math.radians(float(other_lat))
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(float(other_lon)-float(lon))/2)**2
    return 12742000 * math.asin(min(1, math.sqrt(h)))

def resolve_location(pid, name, address, phone, lat, lon, cfg=None):
    cfg = cfg or review_config()
    r = next((r for r in cfg['corrections'] if r['id'] == pid), None)
    if not r:
        return float(lat), float(lon), None
    compact = lambda s: re.sub(r'\s+', '', str(s))
    digits = lambda s: re.sub(r'\D', '', str(s))
    if compact(name) != compact(r['name']) or address_key(address) != tuple(r['address_key']) or digits(phone) != digits(r['phone']):
        raise ValueError(f'{pid}: 검토한 시설의 이름·주소·전화가 바뀌어 위치 보정을 중단합니다.')
    original = distance_m(lat, lon, r['original_lat'], r['original_lon']) < 75
    corrected = distance_m(lat, lon, r['lat'], r['lon']) < 1
    if not original and not corrected:
        # 최신 원천이 스스로 올바른 주소 근처로 수정됐으면 제공기관 좌표를 유지합니다.
        if distance_m(lat, lon, r['lat'], r['lon']) <= 150:
            return float(lat), float(lon), dict(status='source_near_reviewed_address', reviewed_at=cfg['reviewed_at'])
        raise ValueError(f'{pid}: 원천 좌표가 바뀌어 위치 재검토가 필요합니다.')
    return r['lat'], r['lon'], dict(status='address_point_corrected', reviewed_at=cfg['reviewed_at'],
        source=cfg['source'], source_url=cfg['source_url'], original_lat=r['original_lat'], original_lon=r['original_lon'],
        note='도로명·건물번호 정확 일치 건물점으로 위치 보정 · 출입구 현장 확인 아님')

def validate_address_source(cfg=None):
    cfg = cfg or review_config()
    source = ROOT / cfg['source_path']
    if hashlib.sha256(source.read_bytes()).hexdigest() != cfg['source_sha256']:
        raise ValueError('검토한 도로명주소 원본 해시가 달라 위치를 재검토해야 합니다.')
    lookup = {}
    with source.open(encoding='cp949') as f:
        for r in csv.DictReader(f):
            key = (r['시군구명'], r['도로명'], str(int(r['본번'])), str(int(r['부번'] or 0)))
            lookup.setdefault(key, set()).add((float(r['위도']), float(r['경도'])))
    for r in cfg['corrections']:
        if lookup.get(tuple(r['address_key'])) != {(r['lat'], r['lon'])}:
            raise ValueError(r['id'] + ': 유일한 주소 건물점과 보정 좌표 불일치')
    return lookup

def corrected_master(frame):
    frame = frame.copy()
    cfg = review_config()
    for i, r in frame.iterrows():
        lat, lon, meta = resolve_location(r.pharmacy_id, r['name'], r.address, r.phone, r.latitude, r.longitude, cfg)
        frame.at[i, 'latitude'], frame.at[i, 'longitude'] = lat, lon
        if meta:
            frame.at[i, 'location_status'] = meta['status']
    return frame
