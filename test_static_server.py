"""정적 서버의 gzip·캐시·경로 경계를 로컬 HTTP로 검사합니다."""
import gzip, http.client, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from serve import handler_for

class StaticServer(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name);self.data=b'body{color:green}'*100
        (self.root/'index.html').write_bytes(self.data)
        (self.root/'index.html.gz').write_bytes(gzip.compress(self.data))
        (self.root/'app.0123456789abcdef.js').write_bytes(b'void 0;')
        (self.root/'reports.json.0123456789abcdef.gz').write_bytes(gzip.compress(b'{"ok":true}'))
        (self.root/'.env').write_text('not public')
        handler=handler_for(self.root);handler.log_message=lambda *args:None
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path='/',headers=None,method='GET'):
        client=http.client.HTTPConnection(*self.server.server_address)
        client.request(method,path,headers=headers or {});response=client.getresponse()
        result=(response.status,dict(response.headers),response.read());client.close();return result
    def test_gzip_etag_and_head(self):
        status,headers,body=self.request(headers={'Accept-Encoding':'gzip'})
        self.assertEqual(status,200);self.assertEqual(gzip.decompress(body),self.data)
        self.assertEqual(headers['Content-Encoding'],'gzip');self.assertEqual(headers['Cache-Control'],'no-cache')
        self.assertEqual(self.request(headers={'Accept-Encoding':'gzip','If-None-Match':headers['ETag']})[0],304)
        self.assertEqual(self.request(method='HEAD')[2],b'')
        for accept in ['gzip;q=0','gzip;q=0, *;q=1']:
            _,plain_headers,plain=self.request(headers={'Accept-Encoding':accept})
            self.assertNotIn('Content-Encoding',plain_headers);self.assertEqual(plain,self.data)
    def test_hashed_assets_cached_and_data_not_double_compressed(self):
        self.assertIn('immutable',self.request('/app.0123456789abcdef.js')[1]['Cache-Control'])
        status,headers,body=self.request('/reports.json.0123456789abcdef.gz',{'Accept-Encoding':'gzip'})
        self.assertEqual(status,200);self.assertNotIn('Content-Encoding',headers)
        self.assertEqual(gzip.decompress(body),b'{"ok":true}')
    def test_private_paths_and_directories_not_served(self):
        for path in ['/.env','/../serve.py','/%2e%2e/serve.py','/missing']:
            self.assertEqual(self.request(path)[0],404)

if __name__=='__main__':unittest.main()
