"""데이터·지도 라이브러리를 포함하는 단일 HTML을 생성합니다."""
from pathlib import Path
import base64,hashlib,json,gzip,argparse,re
P=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--export', type=Path, help='추가 HTML 저장 경로')
args=parser.parse_args()
payload=(P/'dashboard_data.json.gz').read_bytes()
data=json.loads(gzip.decompress(payload))
s=(P/'dist/template.html').read_text()
# 보고서 탭만 확장하며 기존 지도 기능과 분석 payload를 그대로 보존합니다.
# 화면 글꼴 Wanted Sans(OFL)를 내장해 다른 기기에서도 같은 글꼴로 보입니다. fonts/subset_fonts.py로 줄인 파일입니다.
font_face=''.join("@font-face{font-family:'Wanted Sans';font-weight:%d;font-display:swap;src:url(data:font/woff;base64,%s) format('woff')}"%(w,base64.b64encode((P/f'fonts/WantedSans-{n}.subset.woff').read_bytes()).decode()) for n,w in [('Regular',400),('SemiBold',600),('Bold',700)])
s=s.replace('</head>', '<style>'+font_face+'</style><style>'+(P/'report.css').read_text()+'</style><style>'+(P/'ui.css').read_text()+'</style><style>'+(P/'theme.css').read_text()+'</style></head>')
nav='<nav class="reportnav" aria-label="분석 화면"><div role="tablist" style="display:contents">'+''.join(f'<button role="tab" id="tab-{key}" aria-controls="{key}Pane" aria-selected="false" data-tab="{key}">{label}</button>' for key,label in [('overview','분석 요약'),('map','접근성 지도'),('compare','후보 비교'),('evidence','데이터·검증'),('finder','운영 약국 찾기')])+'</div><button class="print" id="printReport">현재 탭 인쇄 / PDF</button></nav>'
s=s.replace('</header>', '</header>'+nav+'<section class="viewpane" id="overviewPane" role="tabpanel" aria-labelledby="tab-overview" hidden></section><section class="viewpane" id="mapPane" role="tabpanel" aria-labelledby="tab-map"><div class="printlabel">부산 심야약국 접근성 · 시간표와 운영 가정 포함</div>')
s=s.replace('</main>', '</main></section><section class="viewpane" id="comparePane" role="tabpanel" aria-labelledby="tab-compare" hidden></section><section class="viewpane" id="evidencePane" role="tabpanel" aria-labelledby="tab-evidence" hidden></section><section class="viewpane" id="finderPane" role="tabpanel" aria-labelledby="tab-finder" hidden></section>')
s=s.replace('현재 확인된 접근률','현재 모형상 접근률').replace('확인된 접근 수요의 변화','모형상 접근 수요의 변화')
s=s.replace('분석 근거 및 변경사항 ↗','분석 방법')

s=s.replace('2026년 6월 보완값을 별도 표시. NMC와 기존 확정시간이 충돌한 23개 요일은 v3에서 미상 처리.','2026년 6월 자료는 비교 검토에만 사용하고 v3 주모형에서 제외했습니다. 단독 보완 일요일 7건은 제외한 뒤 아래 결측 처리 가정을 적용했습니다. 원본과 NMC 시간 충돌은 NMC 조회값을 우선 적용합니다.')
s=s.replace('‘API 시간표’는 NMC로 결측·추정값을 보완한 자료입니다.','‘API 시간표’는 부산 원본을 NMC로 보완한 자료이며 심평원 단독값은 제외했습니다. 원본과 NMC가 충돌하면 NMC 조회값을 적용합니다.')
s=s.replace('일요일·공휴일 공백은 남아 있습니다.','일요일의 공백은 남아 있습니다.')
s=s.replace('21개 시간대 평균 하한을 기준으로 계산하며','21개 시간대 평균 하한을 기준으로 계산하며')
s=s.replace('<p>하한은 기존 공급을','<p>경로가 불확실한 가까운 약국은 영업 여부와 무관하게 접근 가능 상한에 포함하므로 상한은 넓고 보수적인 범위입니다. 도로 연결선은 실제 보행로가 확인된 구간이 아닙니다.</p><p>하한은 기존 공급을')
# 화면의 방법 설명도 현재 payload의 기간/건수를 사용합니다.
collected=data['meta']['pharmacy_collected_at'][:10]
s=s.replace('2026-09-15',collected).replace('2026-09-13 도로망',(data['meta'].get('osm_date') or '기준일 미기록')+' 도로망')
month=data['meta']['population_month']
s=s.replace('2025년 12월 시간별 월평균',month[:4]+'년 '+str(int(month[5:7]))+'월 시간별 월평균')
nmc_note=f"{collected} 조회 {data['meta']['nmc_rows']:,}곳. 부산 원본과 보완한 지도 목록은 {len(data.get('mapPharmacies',data['pharmacies'])):,}곳이며, 후보·경로 분석 대상은 {len(data['pharmacies']):,}곳입니다. NMC 미조회 시설은 운영 여부 확인 필요로 표시합니다. 조회 시간표에 따른 판정이며 실시간 영업·폐업 상태를 확인한 것은 아닙니다."
s=re.sub(r'(href="https://www.data.go.kr/data/15000576/openapi.do".*?</a></td><td>).*?(</td>)',lambda m:m[1]+nmc_note+m[2],s,flags=re.S)
s=s.replace('/*LEAFLET_CSS*/',(P/'leaflet.css').read_text()).replace('/*LEAFLET_JS*/',(P/'leaflet.js').read_text()).replace('/*DATA_GZIP*/',base64.b64encode(payload).decode()).replace('/*APP_JS*/',(P/'ui.js').read_text()+'\n'+(P/'finder.js').read_text()+'\n'+(P/'report.js').read_text()+'\n'+(P/'app.js').read_text())
assert not any(x in s for x in ['/*APP_JS*/','/*DATA_GZIP*/'])
(P/'dist/index.html').write_text(s)
if args.export:args.export.write_text(s)
(P/'build_manifest.json').write_text(json.dumps({'file':'busan-night-pharmacy-v3-dashboard.html','bytes':len(s.encode()),'sha256':hashlib.sha256(s.encode()).hexdigest(),'hira_in_primary_model':False},indent=2))
print('HTML bytes',len(s.encode()))
