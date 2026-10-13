#!/usr/bin/env python3
"""큰 원천을 내려받거나 사용자가 제공한 원천 폴더에서 복사하고 SHA-256을 검사합니다."""
from pathlib import Path
from urllib.request import Request, urlopen
import argparse, json, shutil
from pipeline_context import ROOT, sha256, utc_now
from public_data import request_bytes, WAVE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['snapshot','latest'],default='snapshot')
    parser.add_argument('--local-inputs',type=Path,help='동일한 원천이 있는 폴더. 경로는 input_catalog.json 기준')
    args=parser.parse_args();catalog=json.loads((ROOT/'input_catalog.json').read_text());records={}
    for rel,entry in catalog.items():
        target=ROOT/rel;target.parent.mkdir(parents=True,exist_ok=True)
        url=entry['snapshot_url'];source='download'
        if args.mode=='latest':
            if entry.get('latest_metadata_pk'):
                metadata=json.loads(request_bytes(WAVE+'selectFileData.do',{'publicdatapk':entry['latest_metadata_pk']}))
                rows=[x for x in metadata['fileList'] if x.get('downurl')]
                url=max(rows,key=lambda x:str(x.get('updatedAt') or ''))['downurl']
            else:url=entry.get('latest_url',url)
        # 기준 연도/경계일을 고정한 SGIS 원천은 재사용해도 최신 API 조회와 모순되지 않습니다.
        pinned=args.mode=='latest' and not entry.get('latest_metadata_pk') and not entry.get('latest_url')
        if target.exists() and (args.mode=='snapshot' or pinned) and sha256(target)==entry['snapshot_sha256']:
            source='existing_verified'
        else:
            part=target.with_suffix(target.suffix+'.partial')
            if args.local_inputs:
                shutil.copy2(args.local_inputs/entry['local_path'],part);source='provided_original'
            else:
                print('download',rel,flush=True)
                try:
                    with urlopen(Request(url,headers={'User-Agent':'BusanPharmacyResearch/1.0'}),timeout=180) as response,part.open('wb') as stream:
                        while chunk:=response.read(1024*1024):stream.write(chunk)
                except Exception as error:
                    code=f' HTTP {error.code}' if hasattr(error,'code') else ''
                    raise SystemExit(f'{rel} 다운로드 실패: {type(error).__name__}{code}. 원천 서버가 과거 파일을 제공하지 않으면 동일 해시의 파일을 --local-inputs로 제공하거나 --mode latest를 사용하세요.') from None
            digest=sha256(part)
            if args.mode=='snapshot' and digest!=entry['snapshot_sha256']:
                raise ValueError(f'{rel}: 원천 스냅샷 해시 불일치. 최신 파일을 과거 파일로 사용하지 않습니다.')
            part.replace(target)
        records[rel]={'url':url,'source':source,'mode':args.mode,'checked_at':utc_now(),'sha256':sha256(target),'bytes':target.stat().st_size}
        print('verified',rel,flush=True)
    (ROOT/'download_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
