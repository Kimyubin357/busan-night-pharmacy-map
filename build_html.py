"""탭별 데이터를 나눈 웹 화면과 독립 실행용 단일 HTML을 함께 생성합니다."""
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
s=s.replace('<h3>최종 지정 전 확인할 것</h3>', '<h3>약국 위치 대조</h3><p>동명 약국은 시설 ID·주소·전화번호로 각각 유지합니다. '+str(data['meta'].get('location_validation',{}).get('corrected',0))+'곳은 부산시 도로명주소의 구·도로명·건물번호 정확 일치 건물점으로 보정했습니다. 위치 검토일은 '+data['meta'].get('location_validation',{}).get('reviewed_at','미기록')+'입니다. 건물 대표 좌표이며 출입구 현장 확인이 아닙니다. 주소 건물점과 250m 이상 차이가 남은 시설은 위치 확인 필요로 표시합니다.</p><h3>최종 지정 전 확인할 것</h3>')

# 내용 해시가 파일명에 들어가므로 데이터 갱신 시 이전 브라우저 캐시와 섞이지 않습니다.
DIST=P/'dist';ASSETS=DIST/'assets';ASSETS.mkdir(exist_ok=True)
files={}
def asset(name,content,precompress=False):
    raw=content.encode() if isinstance(content,str) else content
    path=Path(name);tag=hashlib.sha256(raw).hexdigest()[:16]
    filename=f'{path.stem}.{tag}{path.suffix}';target=ASSETS/filename
    target.write_bytes(raw);relative='assets/'+filename
    files[relative]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    if precompress:
        packed=gzip.compress(raw,mtime=0);target.with_name(filename+'.gz').write_bytes(packed)
        files[relative+'.gz']={'bytes':len(packed),'sha256':hashlib.sha256(packed).hexdigest()}
    return relative

def data_asset(name,value):
    raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    return asset(name+'.json.gz',gzip.compress(raw,mtime=0))

meta={k:v for k,v in data['meta'].items() if k!='input_manifest'}
week=[]
for slot,row in enumerate(data['models']['api']['known']):
    weights=data['grids']['weight'][slot%3]
    total=sum(weights);known=sum(w for w,seconds in zip(weights,row) if 0<=seconds<=900)
    week.append(100*known/total if total else 0)
reports=dict(meta=meta,mapPharmacyCount=len(data.get('mapPharmacies',data['pharmacies'])),pharmacies=[{k:p[k] for k in ['id','name','district']} for p in data['pharmacies']],
    dongs=data['dongs'],models={key:{k:m[k] for k in ['summary','rankings']} for key,m in data['models'].items()},
    validation=data['validation'],sensitivity=data['sensitivity'],overviewWeek=week)
finder=dict(meta=meta,mapPharmacies=data.get('mapPharmacies',data['pharmacies']),boundaries=data['boundaries'])
analysis={k:data[k] for k in ['grids','dongs','pharmacies','models','boundaries']};analysis['meta']=meta
urls={key:data_asset(key,value) for key,value in [('reports',reports),('finder',finder),('analysis',analysis)]}
scripts={key:asset(name,(P/name).read_bytes(),True) for key,name in [('ui','ui.js'),('finder','finder.js'),('report','report.js'),('map','app.js'),('leaflet','leaflet.js')]}
bootstrap=asset('bootstrap.js',(P/'bootstrap.js').read_bytes(),True)
leaflet_style=asset('leaflet.css',(P/'leaflet.css').read_bytes(),True)
font_urls={name:asset('WantedSans-'+name+'.woff',(P/f'fonts/WantedSans-{name}.subset.woff').read_bytes()) for name in ['Regular','SemiBold','Bold']}
asset('OFL.txt',(P/'fonts/OFL.txt').read_bytes())
font_css=''.join("@font-face{font-family:'Wanted Sans';font-weight:%d;font-display:swap;src:url(%s) format('woff')}"%(weight,Path(font_urls[name]).name) for name,weight in [('Regular',400),('SemiBold',600),('Bold',700)])
css='\n'.join((P/name).read_text() for name in ['report.css','ui.css','theme.css'])
web_style=asset('dashboard.css',font_css+'\n'+css,True)
resources=dict(mode='web',scripts=scripts,data=urls,leafletStyle=leaflet_style)
tail='<script>/*LEAFLET_JS*/</script><script id="payload" type="application/octet-stream">/*DATA_GZIP*/</script><script>/*APP_JS*/</script>'
assert tail in s
standalone_name='busan-night-pharmacy.html'
web=s.replace('<style>/*LEAFLET_CSS*/</style>','').replace('</head>',f'<link id="dashboardStyles" rel="stylesheet" href="{web_style}"></head>')
web=web.replace(tail,'<script id="resources" type="application/json">'+json.dumps(resources,separators=(',',':'))+'</script>'+f'<script src="{bootstrap}" defer></script>')
# file:// 사용자는 데이터가 내장된 다운로드본으로 이동합니다.
web=web.replace('</head>',"<script>if(location.protocol==='file:')location.replace('./downloads/"+standalone_name+"'+location.hash)</script></head>")
web=web.replace('<h3>핵심 질문</h3>',f'<p><a href="downloads/{standalone_name}" download>데이터가 포함된 단일 HTML 다운로드</a></p><h3>핵심 질문</h3>')
standalone=s.replace('</head>','<style>'+font_face+'</style><style>'+css+'</style></head>')
standalone=standalone.replace('<script>/*APP_JS*/</script>','<script id="resources" type="application/json">'+json.dumps({'mode':'standalone','scripts':{},'data':{}})+'</script><script>/*APP_JS*/</script>')
standalone=standalone.replace('/*LEAFLET_CSS*/',(P/'leaflet.css').read_text()).replace('/*LEAFLET_JS*/',(P/'leaflet.js').read_text()).replace('/*DATA_GZIP*/',base64.b64encode(payload).decode()).replace('/*APP_JS*/','\n'.join((P/name).read_text() for name in ['ui.js','finder.js','report.js','app.js','bootstrap.js']))
for html in [web,standalone]:
    assert not any(x in html for x in ['/*LEAFLET_CSS*/','/*LEAFLET_JS*/','/*APP_JS*/','/*DATA_GZIP*/'])
(DIST/'index.html').write_text(web)
(DIST/'index.html.gz').write_bytes(gzip.compress(web.encode(),mtime=0))
(DIST/'downloads').mkdir(exist_ok=True);offline=DIST/'downloads'/standalone_name;offline.write_text(standalone)
if args.export:args.export.write_text(standalone)
first_assets=[bootstrap,web_style,scripts['report'],urls['reports'],*font_urls.values()]
def transfer_size(path):
    return files.get(path+'.gz',files[path])['bytes']
manifest={'file':'index.html','bytes':len(web.encode()),'sha256':hashlib.sha256(web.encode()).hexdigest(),
    'hira_in_primary_model':False,'source_payload_sha256':hashlib.sha256(payload).hexdigest(),
    'standalone':{'file':str(offline.relative_to(DIST)),'bytes':offline.stat().st_size,'sha256':hashlib.sha256(offline.read_bytes()).hexdigest()},
    'initial_web_bytes':len(web.encode())+sum(files[path]['bytes'] for path in first_assets),
    'initial_web_gzip_bytes':len(gzip.compress(web.encode(),mtime=0))+sum(transfer_size(path) for path in first_assets),
    'resources':resources,'files':files}
(P/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ['bytes','initial_web_bytes','initial_web_gzip_bytes','standalone']},ensure_ascii=False))
