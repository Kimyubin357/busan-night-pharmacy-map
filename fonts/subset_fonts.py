"""Wanted Sans를 KS X 1001 한글 + 화면·데이터에 쓰인 글자로 줄여 HTML 내장 크기를 낮춥니다.
사용: python3 fonts/subset_fonts.py <WantedSans OTF 폴더>"""
from pathlib import Path
import gzip,sys
from fontTools import subset
P=Path(__file__).resolve().parent.parent
chars=set(chr(c) for c in range(0x20,0x7f))|set('·–—…→←↗①②③④⑤×÷%‘’“”°※▶▸')
for b1 in range(0xB0,0xC9):
    for b2 in range(0xA1,0xFF):
        try:chars|=set(bytes([b1,b2]).decode('cp949'))
        except UnicodeDecodeError:pass
chars|=set(gzip.decompress((P/'dashboard_data.json.gz').read_bytes()).decode())
for name in ['app.js','finder.js','report.js','ui.js','report.css','ui.css','theme.css','build_html.py','dist/template.html']:
    chars|=set((P/name).read_text())
text=''.join(sorted(c for c in chars if ord(c)>=0x20))
for weight in ['Regular','SemiBold','Bold']:
    opts=subset.Options();opts.flavor='woff';opts.layout_features=['*'];opts.name_IDs=['*'];opts.notdef_outline=True
    font=subset.load_font(str(Path(sys.argv[1])/f'WantedSans-{weight}.otf'),opts)
    s=subset.Subsetter(opts);s.populate(text=text);s.subset(font)
    out=P/'fonts'/f'WantedSans-{weight}.subset.woff';subset.save_font(font,str(out),opts)
    print(out.name,out.stat().st_size)
