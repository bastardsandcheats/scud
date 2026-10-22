import tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from scud.app import App
from scud.config import load_config
from scud.web import WebServer

class SettingsTests(unittest.TestCase):
 def test_setup_and_settings_persist_without_waiting_for_rex(self):
  for endpoint in ('setup','settings'):
   with self.subTest(endpoint=endpoint),tempfile.TemporaryDirectory() as directory:
    root=Path(directory);app=App(root,root/'config.yml')
    app.config.update(host='127.0.0.1',port=0);app.compat.run=Mock()
    web=WebServer(app);thread=threading.Thread(target=web.serve,daemon=True);thread.start()
    for _ in range(100):
     if web.httpd:break
     time.sleep(.01)
    body={'rex_url':'http://rex.invalid','libraries':[{'id':'movies','type':'movie','name':'Local Movies','path':str(root/'movies')}],'log_level':'WARNING'}
    session=requests.Session();session.trust_env=False
    try:
     with patch('scud.web.RexClient') as rex:
      rex.return_value.ensure_libraries.side_effect=requests.exceptions.ReadTimeout('Rex is busy')
      response=session.post(f'http://127.0.0.1:{web.httpd.server_port}/api/{endpoint}',json=body,timeout=2)
      self.assertEqual(response.status_code,200,response.text);self.assertTrue(response.json()['ok'])
      rex.assert_not_called()
     saved=load_config(root/'config.yml');self.assertEqual(saved['libraries'][0]['name'],'Local Movies');self.assertEqual(saved['log_level'],'WARNING')
     jobs,full=app.scanner.publisher.batch();self.assertIsNotNone(full)
     self.assertTrue(app.scanner.publisher.wake.is_set())
    finally:
     web.httpd.shutdown();web.httpd.server_close();thread.join();session.close()
