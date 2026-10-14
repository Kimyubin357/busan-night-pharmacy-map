"""주소·전화가 다른 동명 시설을 보정 규칙으로 합치지 않는 회귀 검사."""
import copy, unittest
from pharmacy_locations import review_config, resolve_location, address_key, distance_m

class PharmacyLocations(unittest.TestCase):
    def test_eight_reviewed_facilities_keep_id_and_use_exact_building_point(self):
        cfg=review_config()
        self.assertEqual(len({r['id'] for r in cfg['corrections']}),8)
        for r in cfg['corrections']:
            lat,lon,meta=resolve_location(r['id'],r['name'],r['address'],r['phone'],r['original_lat'],r['original_lon'],cfg)
            self.assertEqual((lat,lon),(r['lat'],r['lon']))
            self.assertEqual(meta['status'],'address_point_corrected')
            self.assertEqual(resolve_location(r['id'],r['name'],r['address'],r['phone'],lat,lon,cfg)[:2],(lat,lon))

    def test_same_name_is_not_a_match(self):
        lat,lon,meta=resolve_location('C1203068','송송약국','부산 동래구 석사로 47','051-916-1010',35.2005272590921,129.064161116661)
        self.assertIsNone(meta)
        self.assertEqual(lat,35.2005272590921)

    def test_changed_address_or_phone_needs_new_review(self):
        r=review_config()['corrections'][2]
        for address,phone in [('부산 동래구 석사로 47',r['phone']),(r['address'],'051-916-1010')]:
            with self.assertRaises(ValueError):resolve_location(r['id'],r['name'],address,phone,r['original_lat'],r['original_lon'])

    def test_changed_unreviewed_coordinate_is_rejected(self):
        r=review_config()['corrections'][0]
        with self.assertRaises(ValueError):resolve_location(r['id'],r['name'],r['address'],r['phone'],35.4,129.3)

    def test_new_source_point_near_address_is_kept(self):
        r=review_config()['corrections'][0]
        self.assertEqual(resolve_location(r['id'],r['name'],r['address'],r['phone'],r['lat']+.0001,r['lon'])[0],r['lat']+.0001)

    def test_building_key_excludes_floor_and_supports_town(self):
        self.assertEqual(address_key('부산광역시 해운대구 해운대로161번길 33, 지하1층 일부호'),('해운대구','해운대로161번길','33','0'))
        self.assertEqual(address_key('부산광역시 기장군 기장읍 차성동로 63, 1층'),('기장군','차성동로','63','0'))

if __name__=='__main__':unittest.main()
