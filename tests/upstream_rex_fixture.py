"""Disposable upstream Rex with a transparent, unauthenticated loopback proxy."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import ipaddress
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
import uuid

@contextmanager
def fresh_rex(image,claimed=True,prepare=None):
    name='scud-upstream-'+uuid.uuid4().hex[:12]
    requests=[]
    def docker(*args,**kwargs):return subprocess.check_output(['docker',*map(str,args)],text=True,**kwargs).strip()
    with tempfile.TemporaryDirectory(prefix=name+'-') as directory:
        state=Path(directory);machine=uuid.uuid4().hex
        (state/'catalog.json').write_text(json.dumps({'machineIdentifier':machine,'friendlyName':name,'sections':[],'items':[]}))
        if claimed:(state/'claim_state.json').write_text(json.dumps({'machine':machine,'token':'fixture-only-token'}))
        if prepare:prepare(state)
        server=None;thread=None
        try:
            docker('network','create','--internal',name)
            docker('run','-d','--name',name,'--network',name,'--memory','1g','--cpus','2','-v',str(state)+':/test','-e','REX_PLEXTV_URL=http://127.0.0.1:9','-e','REX_DIRECT_URL=off',image,'--host','0.0.0.0','--port','32400','--catalog','/test/catalog.json','--state','/test/rex.db','--gdm','off')
            network=json.loads(docker('inspect',name))[0]['NetworkSettings']['Networks'][name]
            bridge=str(ipaddress.ip_interface(network['IPAddress']+'/'+str(network['IPPrefixLen'])).network.network_address+1)
            (state/'connection.json').write_text(json.dumps({'bridge':bridge,'container':name}))
            target='http://'+network['IPAddress']+':32400'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            class Proxy(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def forward(self):
                    body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                    headers={key:value for key,value in self.headers.items() if key.lower() not in ('host','connection','content-length')}
                    headers['Accept-Encoding']='identity'
                    requests.append((self.command,self.path,dict(headers)))
                    request=urllib.request.Request(target+self.path,data=body or None,headers=headers,method=self.command)
                    try:
                        try:response=opener.open(request,timeout=65)
                        except urllib.error.HTTPError as error:response=error
                        with response:
                            data=response.read();self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                    except OSError:self.send_error(502)
                do_GET=do_POST=do_PUT=do_DELETE=forward
            server=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            yield 'http://127.0.0.1:'+str(server.server_port),state,requests
        finally:
            if server:server.shutdown();server.server_close();thread.join()
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            subprocess.run(['docker','network','rm',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
