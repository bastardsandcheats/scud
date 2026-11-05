"""Opt-in real upstream integration: REX_UPSTREAM_IMAGE=<unpatched image>."""
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

import requests
from scud.app import App
from scud.compat import Compatibility
from scud.rex import RexClient
from scud.web import WebServer
from upstream_rex_fixture import fresh_rex

IMAGE=os.getenv('REX_UPSTREAM_IMAGE')
SOURCE=os.getenv('REX_UPSTREAM_SOURCE')

@unittest.skipUnless(IMAGE,'Set REX_UPSTREAM_IMAGE to an unpatched Rex image')
class UpstreamRexTests(unittest.TestCase):
    def test_native_contract_without_any_token_claimed_and_unclaimed(self):
        for claimed in (False,True):
            with self.subTest(claimed=claimed),fresh_rex(IMAGE,claimed) as (url,state,calls):
                app=SimpleNamespace(config={'rex_url':url,'source_url':'http://127.0.0.1:9/files'},log=logging.getLogger('upstream'))
                Compatibility(app).rex_contract()
                Compatibility(app,isolated=True).rex_contract()
                self.assertTrue(any(method=='DELETE' for method,_,_ in calls))
                for _,path,headers in calls:
                    self.assertTrue(path=='/identity' or path.startswith('/rex/'),path)
                    self.assertFalse(any(key.lower() in ('x-plex-token','authorization') for key in headers))

    @unittest.skipUnless(SOURCE,'Set REX_UPSTREAM_SOURCE for cached metadata fixtures')
    def test_existing_shared_library_keeps_its_keys_and_versions(self):
        def prepare(state):
            cache=json.loads((Path(SOURCE)/'tests/fixtures/feed/provider_cache.json').read_text())
            (state/'plex_cache.json').write_text(json.dumps(cache['plex']))
            catalog=json.loads((state/'catalog.json').read_text())
            catalog['sections']=[{'key':'4','type':'movie','title':'Existing Movies','uuid':'existing-movies','Location':[{'id':4,'path':'/scud/one'}]}]
            (state/'catalog.json').write_text(json.dumps(catalog))
        with fresh_rex(IMAGE,True,prepare) as (url,state,calls),tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            app=App(root,root/'config.yml')
            app.config.update(rex_url=url,source_url='http://127.0.0.1:9/files',rex_source='scud-legacy',libraries=[{'id':ident,'type':'movie','name':'Existing Movies','path':str(root/ident),'rex_library_key':'4'} for ident in ('one','two')])
            probe=json.loads((Path(SOURCE)/'tests/fixtures/zurg/entries.json').read_text())['entries']['movie']['entry']['media_info']
            with app.db.connect() as db:
                for ident in ('one','two'):
                    db.execute("INSERT INTO media(id,library_id,relpath,real_path,size,kind,match_status,tmdb_id,imdb_id,media_info,rex_feed_id,updated_at) VALUES(?,?,?,?,?,'movie','matched','31639','tt0103827',?,?,0)",(ident,ident,'movie.mkv',str(root/ident/'movie.mkv'),1,json.dumps(probe),'old-'+ident))
            self.assertTrue(app.scanner._sync(['one','two'],[]),app.db.state_get('last_rex_error'))
            for ident in ('one','two'):
                row=app.db.get_media(ident)
                self.assertEqual(app.scanner.feed_id(row),'old-'+ident)
                self.assertEqual(app.scanner.receipts.state(row),'received')
            for _,path,headers in calls:
                self.assertTrue(path=='/identity' or path.startswith('/rex/'),path)
                self.assertFalse(any(key.lower() in ('x-plex-token','authorization') for key in headers))
            # Scud is finished; inspect placement with a fixture credential only here.
            session=requests.Session();session.trust_env=False
            sections=session.get(url+'/library/sections',headers={'Accept':'application/json','X-Plex-Token':'fixture-only-token'},timeout=10).json()['MediaContainer']['Directory']
            self.assertEqual([(row['key'],row['title']) for row in sections],[('4','Existing Movies')])
            for _,path,headers in calls:
                if not path.startswith('/library/'):self.assertFalse(any(key.lower() in ('x-plex-token','authorization') for key in headers))
            session.close()

    @unittest.skipUnless(SOURCE,'Set REX_UPSTREAM_SOURCE for cached metadata fixtures')
    def test_scud_registration_publish_receipts_and_file_serving(self):
        def prepare(state):
            fixture=json.loads((Path(SOURCE)/'tests/fixtures/feed/provider_cache.json').read_text())
            (state/'plex_cache.json').write_text(json.dumps(fixture['plex']))
        with fresh_rex(IMAGE,True,prepare) as (url,state,calls),tempfile.TemporaryDirectory() as directory:
            root=Path(directory);media=root/'movies';media.mkdir();file=media/'movie.mp4'
            more=root/'more';more.mkdir()
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=64x64:d=0.2','-c:v','libx264','-pix_fmt','yuv420p',str(file)],check=True)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(file)]))
            bridge=json.loads((state/'connection.json').read_text())['bridge']
            config={'scud':'v1','host':bridge,'port':0,'rex_url':url,'rex_source':'scud-test','libraries':[{'id':'movies','type':'movie','name':'Scud Movies','path':str(media),'rex_library_key':'999'},{'id':'more-movies','type':'movie','name':'Scud Movies','path':str(more)}]}
            import yaml
            (root/'config.yml').write_text(yaml.safe_dump(config))
            app=App(root,root/'config.yml');web=WebServer(app)
            thread=threading.Thread(target=web.serve,daemon=True);thread.start()
            for _ in range(100):
                if web.httpd:break
                time.sleep(.01)
            session=requests.Session();session.trust_env=False
            try:
                address='http://'+bridge+':'+str(web.httpd.server_port)
                app.config['source_url']=address
                response=session.post(address+'/api/rex/test',json={'rex_url':url},timeout=10)
                self.assertTrue(response.json()['ok'])
                app.compat.rex_contract()
                with app.db.connect() as db:
                    db.execute("INSERT INTO media(id,library_id,relpath,real_path,size,kind,match_status,tmdb_id,imdb_id,media_info,rex_feed_id,updated_at) VALUES(?,?,?,?,?,'movie','matched','31639','tt0103827',?,'one-existing',0)",('one','movies',file.name,str(file),file.stat().st_size,json.dumps(probe)))
                self.assertTrue(app.scanner._sync(['one'],[]),app.db.state_get('last_rex_error'))
                row=app.db.get_media('one');self.assertEqual(app.scanner.receipts.state(row),'received')
                self.assertEqual(app.scanner.feed_id(row),'one-existing')
                registration=session.get(url+'/rex/sources/scud-test',timeout=10).json()
                self.assertEqual(len(registration['directories']),1)
                self.assertEqual(registration['directories'][0]['movies'],'Scud Movies')
                content=session.get(address+'/files/'+app.scanner.feed_item(row)['path'],headers={'Range':'bytes=0-15'},timeout=10)
                self.assertEqual(content.status_code,206);self.assertEqual(content.content,file.read_bytes()[:16])
                (more/'second.mp4').write_bytes(file.read_bytes())
                with app.db.connect() as db:
                    db.execute("INSERT INTO media(id,library_id,relpath,real_path,size,kind,match_status,tmdb_id,imdb_id,media_info,updated_at) VALUES(?,?,?,?,?,'movie','matched','31639','tt0103827',?,0)",('two','more-movies','second.mp4',str(more/'second.mp4'),file.stat().st_size,json.dumps(probe)))
                self.assertTrue(app.scanner._sync(['two'],[]),app.db.state_get('last_rex_error'))
                second=app.db.get_media('two');self.assertEqual(app.scanner.receipts.state(second),'received')
                content=session.get(address+'/files/'+app.scanner.feed_item(second)['path'],headers={'Range':'bytes=0-15'},timeout=10)
                self.assertEqual(content.status_code,206);self.assertEqual(content.content,file.read_bytes()[:16])
                denied=session.get(address+'/files/'+registration['directories'][0]['name']+'/not-a-library/secret',timeout=10)
                self.assertEqual(denied.status_code,404)
                for _,path,headers in calls:
                    self.assertTrue(path=='/identity' or path.startswith('/rex/'),path)
                    self.assertFalse(any(key.lower() in ('x-plex-token','authorization') for key in headers))
                # An authenticated inspection is a test assertion only. Scud never gets it.
                inspection=session.get(url+'/library/sections',headers={'Accept':'application/json','X-Plex-Token':'fixture-only-token'},timeout=10)
                sections=inspection.json()['MediaContainer']['Directory']
                self.assertEqual(sum(row['title']=='Scud Movies' for row in sections),1)
                section=next(row for row in sections if row['title']=='Scud Movies')
                listed=session.get(url+'/library/sections/'+str(section['key'])+'/all',headers={'Accept':'application/json','X-Plex-Token':'fixture-only-token'},timeout=10).json()
                self.assertTrue(listed['MediaContainer'].get('Metadata'))
                part=listed['MediaContainer']['Metadata'][0]['Media'][0]['Part'][0]
                playback=session.get(url+part['key'],headers={'X-Plex-Token':'fixture-only-token','Range':'bytes=0-15'},timeout=20)
                self.assertEqual(playback.status_code,206,playback.text[:200])
                self.assertEqual(playback.content,file.read_bytes()[:16])
                for _,path,headers in calls:
                    if path.startswith('/library/'):
                        self.assertEqual(next(value for key,value in headers.items() if key.lower()=='x-plex-token'),'fixture-only-token')
                    else:self.assertFalse(any(key.lower() in ('x-plex-token','authorization') for key in headers))
            finally:web.httpd.shutdown();web.httpd.server_close();thread.join();session.close()

if __name__=='__main__':unittest.main()
