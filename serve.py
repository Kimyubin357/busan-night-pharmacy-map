"""웹용 dist 파일만 제공하는 정적 서버. gzip·ETag·내용 해시 파일 캐시를 지원합니다."""
import argparse
from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes, os, re
from pathlib import Path
from urllib.parse import unquote, urlsplit

def accepts_gzip(value):
    accepted={}
    for part in value.lower().split(','):
        coding,*parameters=part.strip().split(';');quality=1.0
        for parameter in parameters:
            if parameter.strip().startswith('q='):
                try:quality=float(parameter.strip()[2:])
                except ValueError:quality=0.0
        accepted[coding.strip()]=quality
    return accepted.get('gzip',accepted.get('*',0))>0

def handler_for(directory):
    root=Path(directory).resolve()
    class StaticHandler(BaseHTTPRequestHandler):
        def do_GET(self): self.respond(False)
        def do_HEAD(self): self.respond(True)
        def respond(self,head):
            relative=unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
            target=(root/relative).resolve()
            if not target.is_relative_to(root) or any(part.startswith('.') for part in Path(relative).parts) or not target.is_file():
                self.send_error(404);return
            compressed=False
            if target.suffix in {'.html','.js','.css'} and accepts_gzip(self.headers.get('Accept-Encoding','')):
                packed=target.with_name(target.name+'.gz')
                if packed.is_file():compressed=True;selected=packed
                else:selected=target
            else:selected=target
            stat=selected.stat();etag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
            cache='public, max-age=31536000, immutable' if re.search(r'\.[0-9a-f]{16}\.',target.name) else 'no-cache'
            code=304 if self.headers.get('If-None-Match')==etag else 200
            self.send_response(code);self.send_header('ETag',etag);self.send_header('Cache-Control',cache)
            self.send_header('Vary','Accept-Encoding');self.send_header('X-Content-Type-Options','nosniff')
            if code==304:self.end_headers();return
            mime=mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            # json.gz는 브라우저 로더가 해제합니다. HTTP gzip과 겹쳐 적용하지 않습니다.
            if target.name.endswith('.json.gz'):mime='application/octet-stream'
            self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') or target.suffix=='.js' else ''))
            self.send_header('Content-Length',str(stat.st_size))
            self.send_header('Last-Modified',format_datetime(datetime.fromtimestamp(stat.st_mtime,timezone.utc),usegmt=True))
            if compressed:self.send_header('Content-Encoding','gzip')
            self.end_headers()
            if not head:
                with selected.open('rb') as file:
                    while block:=file.read(128*1024):self.wfile.write(block)
    return StaticHandler

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8000')))
    parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent/'dist')
    args=parser.parse_args()
    print(f'http://{args.host}:{args.port}/',flush=True)
    ThreadingHTTPServer((args.host,args.port),handler_for(args.directory)).serve_forever()

if __name__=='__main__':main()
