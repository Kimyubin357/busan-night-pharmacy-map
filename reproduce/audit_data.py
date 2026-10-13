"""보고서 근거용 원본 JSON·모든 시간 컬럼 전수 점검. python audit_data.py"""
from pathlib import Path
from collections import Counter
import json, hashlib, re
import pandas as pd
from pharmacy_data import START, END, DAY_NAMES, minute


def main():
    root=Path(__file__).resolve().parent
    q=json.loads((root/'reports/latest_run.json').read_text())
    raw_dir=root/'data/raw'/q['run_id']; out=root / q['output_dir']; report=root / q['report_dir']
    pages=[]; items=[]; key_orders=Counter(); keys=set()
    for file in sorted(raw_dir.glob('pharmacy_api_page_*.json')):
        body=json.loads(file.read_text())['response']['body']; rows=body['items']['item']
        if isinstance(rows,dict): rows=[rows]
        pages.append({'page':int(body['pageNo']),'rows':len(rows),
            'monday_start_key_absent':sum(START[0] not in x for x in rows),
            'monday_start_json_null':sum(START[0] in x and x[START[0]] is None for x in rows),
            'monday_start_nonempty':sum(x.get(START[0]) not in (None,'') for x in rows)})
        for row in rows:
            keys.update(row); key_orders[tuple(row)]+=1
        items.extend(rows)
    raw=pd.DataFrame(items)
    master=pd.read_csv(out/'pharmacy_master.csv',dtype='string')
    busan=raw[raw.pmcyId.isin(master.pharmacy_id)]
    designated=raw[raw.pmcyId.isin(master.loc[master.public_designation_status.eq('matched_designated'),'pharmacy_id'])]
    missing=[]; extended=[]; invalid=[]
    for scope,df in [('api_all',raw),('busan',busan),('designated',designated)]:
        for day,sc,ec in zip(DAY_NAMES,START,END):
            sm=df[sc].fillna('').astype(str).str.strip().eq(''); em=df[ec].fillna('').astype(str).str.strip().eq('')
            missing.append({'scope':scope,'day':day,'rows':len(df),'start_missing':int(sm.sum()),'end_missing':int(em.sum())})
        for role,fields in [('start',START),('end',END)]:
            for field in fields:
                for value,count in df[field].fillna('').astype(str).str.strip().value_counts().items():
                    if not value: continue
                    compact=value.replace(':','')
                    if re.fullmatch(r'\d{3,4}',compact) and int(compact)>=2400:
                        extended.append({'scope':scope,'role':role,'field':field,'raw_value':value,'cells':int(count)})
                    if minute(value,is_end=role=='end') is None:
                        invalid.append({'scope':scope,'role':role,'field':field,'raw_value':value,'cells':int(count)})
    pd.DataFrame(pages).to_csv(report/'api_page_audit.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(missing).to_csv(report/'weekday_missing_audit.csv',index=False,encoding='utf-8-sig')
    columns=['scope','role','field','raw_value','cells']
    ext=pd.DataFrame(extended,columns=columns)
    ext.to_csv(report/'extended_time_by_field.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(invalid,columns=columns).to_csv(report/'invalid_time_values.csv',index=False,encoding='utf-8-sig')
    counts=ext.groupby(['scope','role','raw_value'])['cells'].sum().reset_index()
    counts.to_csv(report/'extended_time_totals.csv',index=False,encoding='utf-8-sig')
    info={'api_pages':len(pages),'api_rows':len(raw),
        'monday_start_key_absent':sum(x['monday_start_key_absent'] for x in pages),
        'monday_start_json_null':sum(x['monday_start_json_null'] for x in pages),
        'item_key_order_patterns':len(key_orders),
        'monday_related_keys':sorted(k for k in keys if 'mon' in k.lower()),
        'day_code_like_keys':sorted(k for k in keys if any(s in k.lower() for s in ['dayofweek','weekday','daycode'])),
        'all_item_keys':sorted(keys),
        'cause_conclusion':'원본 JSON부터 월요일 시작 필드가 null. 제공 측 데이터/필드 매핑 문제 가능성은 있으나 원인 미상.',
        'extended_start_cells_all':int(ext.loc[(ext.scope=='api_all')&(ext.role=='start'),'cells'].sum()),
        'invalid_nonempty_cells_all':sum(x['cells'] for x in invalid if x['scope']=='api_all')}
    # 실자료 보완값을 원본 화~금에서 독립 대조합니다.
    a=pd.read_csv(out/'monday_imputation_audit.csv',dtype='string')
    assert len(a)==len(designated)
    for _,row in a.iterrows():
        original=designated[designated.pmcyId.eq(row.pharmacy_id)].iloc[0]
        assert original[START[0]] is None or pd.isna(original[START[0]])
        values=[minute(original[c]) for c in START[1:5]]
        assert None not in values and len(set(values))==1
        assert minute(row.monday_start_effective)==values[0]
    hours=pd.read_csv(out/'pharmacy_opening_hours_analysis.csv')
    imputed=hours[hours.start_imputed]
    assert len(imputed)==len(designated) and imputed.day_code.eq(1).all()
    assert set(imputed.pharmacy_id)==set(designated.pmcyId)
    assert imputed.start_raw.isna().all()
    info['imputation_independent_check']='PASS: 지정약국만 월요일 19행 보완, 원본 null 보존, 화~금 공통값과 일치'
    (report/'forensic_audit.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    # 팀원이 전달받은 CSV가 검증 버전과 같은지 확인할 수 있는 파일 해시입니다.
    lines=[hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name for f in sorted(out.glob('*.csv'))]
    (out/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False,indent=2))
    print(counts.to_string(index=False))
    print('분석용 보완 품질',json.dumps(q['monday_imputation'],ensure_ascii=False))

if __name__=='__main__': main()
