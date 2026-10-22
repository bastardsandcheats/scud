import os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from scud.db import Database
from scud.inventory import FolderInventory

class FolderInventoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.db=Database(self.root/'state.db');self.lib={'id':'tv','type':'show','path':str(self.root/'media')};self.folder=self.root/'media'/'Show'/'Season 1';self.folder.mkdir(parents=True);self.file=self.folder/'S01E01.mkv';self.file.write_bytes(b'abcd')
  with self.db.connect() as db:db.execute("INSERT INTO media(id,library_id,relpath,real_path,kind,match_status,match_method,updated_at) VALUES('one','tv','Show/Season 1/S01E01.mkv',?,'show','matched','manual',0)",(str(self.file),))
 def inventory(self):return FolderInventory(self.db,{'.mkv'},Mock())
 def seed(self):
  first=self.inventory();self.assertEqual(len(first.library(self.lib,{})),1);first.save()
 def test_unchanged_directory_skips_files_and_preserves_rows(self):
  self.seed();second=self.inventory();self.assertEqual(second.library(self.lib,{}),[]);self.assertEqual(second.preserved,['one']);self.assertEqual(second.files_skipped,1)
 def test_in_place_file_edit_detected_without_parent_date_change(self):
  self.seed();stamp=self.folder.stat().st_mtime_ns;self.file.write_bytes(b'changed length');os.utime(self.folder,ns=(stamp,stamp));current=self.inventory();self.assertEqual(len(current.library(self.lib,{})),1)
 def test_same_size_new_mtime_detected(self):
  self.seed();stamp=self.file.stat().st_mtime_ns;self.file.write_bytes(b'efgh');os.utime(self.file,ns=(stamp,stamp+1000000));self.assertEqual(len(self.inventory().library(self.lib,{})),1)
 def test_add_remove_and_rename_detected(self):
  self.seed();self.file.rename(self.file.with_name('S01E02.mkv'));self.assertEqual(len(self.inventory().library(self.lib,{})),1);self.file.with_name('S01E02.mkv').unlink();current=self.inventory();current.library(self.lib,{});self.assertNotIn('one',current.preserved)
 def test_unavailable_root_preserves_library(self):
  self.lib['path']=str(self.root/'missing');current=self.inventory();self.assertEqual(current.library(self.lib,{}),[]);self.assertIn('tv',current.failed)
 def test_key_change_invalidates_cache(self):
  self.seed();self.assertEqual(len(self.inventory().library(self.lib,{'tmdb_api_key':'changed'})),1)

class ScannerInventoryIntegrationTests(unittest.TestCase):
 def test_unchanged_folders_do_not_match_or_probe_and_alias_removals_use_feed_id(self):
  from scud.app import App
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);media=root/'media';media.mkdir();file=media/'Movie.mkv';file.write_bytes(b'data');app=App(root,root/'config.yml');app.config['libraries']=[{'id':'movies','type':'movie','path':str(media)}];app.scanner.sync=Mock()
   with patch('scud.scanner.Matcher') as matcher,patch('scud.scanner.ffprobe',return_value=({'streams':[{'codec_type':'video'}]},None)) as probe:
    matcher.return_value.match_file.return_value={'status':'matched','title':'Movie','ids':{'tmdb':1},'method':'tmdb-title-search'}
    app.scanner.scan_once();row=app.db.list_media()[0];matcher.return_value.match_file.reset_mock();probe.reset_mock()
    app.scanner.scan_once();matcher.return_value.match_file.assert_not_called();probe.assert_not_called();self.assertEqual(app.scanner.progress['files_skipped'],1)
    with app.db.connect() as db:db.execute("UPDATE media SET rex_feed_id='scud-relocated' WHERE id=?",(row['id'],))
    file.unlink();app.scanner.scan_once();self.assertEqual(app.scanner.sync.call_args.args[1],['scud-relocated']);self.assertEqual(app.db.list_media(),[])
