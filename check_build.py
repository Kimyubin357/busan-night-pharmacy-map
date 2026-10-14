"""분리 데이터의 원본 일치, 초기 파일 예산, 단일 HTML 독립성을 검사합니다."""
from pathlib import Path
import base64, gzip, hashlib, json, re

P=Path(__file__).resolve().parent
manifest=json.loads((P/'build_manifest.json').read_text())
source=(P/'dashboard_data.json.gz').read_bytes()
D=json.loads(gzip.decompress(source))
assert hashlib.sha256(source).hexdigest()==manifest['source_payload_sha256']
for path,meta in manifest['files'].items():
    raw=(P/'dist'/path).read_bytes()
    assert len(raw)==meta['bytes'] and hashlib.sha256(raw).hexdigest()==meta['sha256'],path
def load(kind):return json.loads(gzip.decompress((P/'dist'/manifest['resources']['data'][kind]).read_bytes()))
finder=load('finder');analysis=load('analysis');reports=load('reports')
assert reports['mapPharmacyCount']==len(D['mapPharmacies'])
assert finder['mapPharmacies']==D['mapPharmacies'] and finder['boundaries']==D['boundaries']
for key in ['grids','dongs','pharmacies','models','boundaries']:assert analysis[key]==D[key],key
for key in ['api','policy']:
    for field in ['summary','rankings']:assert reports['models'][key][field]==D['models'][key][field]
for slot,known in enumerate(D['models']['api']['known']):
    weights=D['grids']['weight'][slot%3]
    expected=100*sum(w for w,seconds in zip(weights,known) if 0<=seconds<=900)/sum(weights)
    assert abs(reports['overviewWeek'][slot]-expected)<1e-10
html=(P/'dist/index.html').read_text()
assert hashlib.sha256(html.encode()).hexdigest()==manifest['sha256']
assert gzip.decompress((P/'dist/index.html.gz').read_bytes())==html.encode()
assert len(html.encode())<40000 and 'id="payload"' not in html
assert manifest['initial_web_bytes']<1_200_000
assert 'DecompressionStream' not in html # 구현과 대용량 데이터는 외부 파일에서 읽습니다.
offline=(P/'dist'/manifest['standalone']['file']).read_text()
assert hashlib.sha256(offline.encode()).hexdigest()==manifest['standalone']['sha256']
embedded=re.search(r'<script id="payload" type="application/octet-stream">(.*?)</script>',offline,re.S).group(1)
assert base64.b64decode(embedded)==source
assert 'id="payload"' in offline and '"mode": "standalone"' in offline
assert not re.search(r'<script[^>]+src=',offline)
assert not re.search(r'<link[^>]+rel="stylesheet"',offline)
assert not any(token in offline for token in ['/*DATA_GZIP*/','/*APP_JS*/'])
print(f"Build split: original data matched, initial {manifest['initial_web_bytes']:,} bytes, standalone self-contained.")
