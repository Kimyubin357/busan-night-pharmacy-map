"""지도·경로 분석이 같은 보정 좌표를 쓰고 동명 시설 ID가 유지되는지 검사합니다."""
import gzip, json, re
from pipeline_context import ROOT
from pharmacy_locations import review_config, resolve_location

def main():
    data=json.loads(gzip.decompress((ROOT.parent/'dashboard_data.json.gz').read_bytes()))
    mapped={p['id']:p for p in data['mapPharmacies']}
    analysis={p['id']:p for p in data['pharmacies']}
    assert len(mapped)==len(data['mapPharmacies']), '지도 시설 ID 중복'
    corrected=review_config()['corrections']
    for r in corrected:
        for table in [mapped,analysis]:
            p=table[r['id']]
            expected=resolve_location(p['id'],p['name'],p['address'],p['phone'],p['lat'],p['lon'])[:2]
            assert (p['lat'],p['lon'])==expected, r['id']+' 지도/경로 좌표 불일치'
            assert p['district']==r['address_key'][0], r['id']+' 주소 구·군 불일치'
    mismatches=[p['id'] for p in mapped.values() if (m:=re.search(r'(\S+(?:구|군))\s',p['address'])) and m[1]!=p['district']]
    assert not mismatches, '주소/지도 구·군 검토 필요: '+','.join(mismatches)
    assert mapped['C1202834']['district']=='해운대구' and mapped['C1203068']['district']=='동래구'
    assert mapped['C1202834']['phone']!=mapped['C1203068']['phone']
    print('Location publication: '+str(len(corrected))+' corrected facilities, separate same-name IDs, address districts passed.')

if __name__=='__main__':main()
