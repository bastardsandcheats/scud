import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from scud.app import App
from scud.web import WebServer

class EpisodeMatchTests(unittest.TestCase):
 def test_episode_picker_save_and_rescan_preserve_manual_number(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);media=root/'tv';file=media/'Doc Martin/Season 9/Doc.Martin.S09E01.mkv';file.parent.mkdir(parents=True);file.write_bytes(b'test')
   app=App(root,root/'config.yml');app.config.update(host='127.0.0.1',port=0,libraries=[{'id':'tv','type':'show','path':str(media)}])
   app.scanner.sync=Mock()
   match={'status':'matched','title':'Doc Martin','year':2004,'ids':{'tmdb':'9760'},'method':'tmdb-title-search'}
   with patch('scud.scanner.Matcher') as matcher,patch('scud.scanner.ffprobe',return_value=({'streams':[{}]},None)):
    matcher.return_value.match_file.return_value=match;app.scanner.scan_once()
    row=app.db.list_media()[0]
    web=WebServer(app);thread=threading.Thread(target=web.serve,daemon=True);thread.start()
    for _ in range(100):
     if web.httpd:break
     time.sleep(.01)
    session=requests.Session();session.trust_env=False;base=f'http://127.0.0.1:{web.httpd.server_port}'
    context={'show_id':'9760','title':'Doc Martin','year':2004,'poster':None,'seasons':[{'number':9,'name':'Season 9'}],'season':9,'episode':1,'episode_end':None,'episodes':[{'number':1,'title':'To the Lighthouse'},{'number':2,'title':'The Shock of the New'}]}
    try:
     with patch('scud.web.TMDBClient') as tmdb,patch('scud.web.RexClient'):
      tmdb.return_value.episode_context.return_value=context
      response=session.post(base+'/api/episodes/context',json={'item_id':row['id']},timeout=5);self.assertEqual(response.json()['episodes'][1]['title'],'The Shock of the New')
      payload={'id':'tmdb://9760','title':'Doc Martin','year':2004,'season':9,'episode':2}
      response=session.post(base+f"/api/items/{row['id']}/match",json=payload,timeout=5);self.assertEqual(response.status_code,200,response.text)
      payload['episode']=999
      response=session.post(base+f"/api/items/{row['id']}/match",json=payload,timeout=5);self.assertEqual(response.status_code,400)
     saved=app.db.get_media(row['id']);self.assertEqual(saved['episode'],2);self.assertEqual(saved['numbering_manual'],1)
     file.write_bytes(b'changed media')
     app.scanner.scan_once();saved=app.db.get_media(row['id']);self.assertEqual(saved['episode'],2)
     self.assertEqual(app.scanner.feed_item(saved)['episode'],2)
    finally:web.httpd.shutdown();web.httpd.server_close();thread.join()
