import tempfile,threading,time,unittest
from pathlib import Path
import requests
from scud.app import App
from scud.web import WebServer

class MediaHTTPTests(unittest.TestCase):
 def test_ranges_head_and_delete_refusal(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);media=root/'media';media.mkdir();file=media/'video.mkv';file.write_bytes(b'0123456789')
   app=App(root,root/'config.yml');app.config.update(host='127.0.0.1',port=0,libraries=[{'id':'tv','path':str(media)}]);web=WebServer(app);thread=threading.Thread(target=web.serve,daemon=True);thread.start()
   for _ in range(100):
    if web.httpd:break
    time.sleep(.01)
   session=requests.Session();session.trust_env=False;url=f'http://127.0.0.1:{web.httpd.server_port}/files/tv/video.mkv'
   try:
    response=session.get(url,headers={'Range':'bytes=2-4'},timeout=5);self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'234')
    response=session.head(url,timeout=5);self.assertEqual(response.status_code,200);self.assertEqual(response.headers['Content-Length'],'10');self.assertEqual(response.content,b'')
    response=session.delete(url,timeout=5);self.assertEqual(response.status_code,403);self.assertEqual(file.read_bytes(),b'0123456789')
    # Opt-in deletion removes only a registered file and withdraws its source ID.
    from unittest.mock import Mock
    app.config['allow_rex_delete']=True;app.scanner.sync=Mock()
    with app.db.connect() as conn:conn.execute("INSERT INTO media(id,library_id,relpath,real_path,size,kind,match_status,tmdb_id,updated_at) VALUES('video','tv','video.mkv',?,10,'movie','matched','603',0)",(str(file),))
    response=session.delete(url,timeout=5);self.assertEqual(response.status_code,204);self.assertFalse(file.exists());self.assertIsNone(app.db.get_media('video'));app.scanner.sync.assert_called_with([],['video'])
   finally:web.httpd.shutdown();web.httpd.server_close();thread.join()
