import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from scud.db import Database
from scud.scanner import Scanner

class FolderMatchTests(unittest.TestCase):
    def test_folder_match_existing_future_files_and_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            media=root/'media'
            for path in ('DS9LD/Season 1/DS9LD.S01E01.mkv','DS9LD/Season 2/DS9LD.S02E01.mkv','DS9LD-other/S01E01.mkv'):
                file=media/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'test')
            db=Database(root/'db.sqlite')
            app=SimpleNamespace(db=db,log=logging.getLogger(),config={'libraries':[{'id':'tv','type':'show','path':str(media)}],'ffmpeg_path':''})
            scanner=Scanner(app);scanner.sync=Mock()
            with patch('scud.scanner.Matcher') as matcher,patch('scud.scanner.ffprobe',return_value=({'streams':[{}]},None)):
                matcher.return_value.match_file.return_value={'status':'unmatched','method':'folder-filename-tmdb-v1'}
                scanner.scan_once()
                ids={'imdb_id':'tt0106145','tmdb_id':None,'tvdb_id':None}
                updated=db.match_folder('tv','DS9LD','Star Trek: Deep Space Nine',1993,ids)
                self.assertEqual(len(updated),2)
                for item in updated:
                    row=db.get_media(item);self.assertEqual(row['imdb_id'],'tt0106145');self.assertEqual(row['match_method'],'folder')
                self.assertIsNone(db.folder_match('tv','DS9LD-other/S01E01.mkv'))
                self.assertIsNone(db.folder_match('other','DS9LD/S01E01.mkv'))
                next_file=media/'DS9LD/Season 1/DS9LD.S01E02.mkv';next_file.write_bytes(b'new')
                matcher.return_value.match_file.reset_mock()
                scanner.scan_once()
                matcher.return_value.match_file.assert_not_called()
                row=next(row for row in db.list_media() if row['relpath'].endswith('DS9LD.S01E02.mkv'))
                self.assertEqual(row['imdb_id'],'tt0106145');self.assertEqual(row['season'],1);self.assertEqual(row['episode'],2)
                reopened=Database(root/'db.sqlite')
                self.assertEqual(reopened.folder_match('tv',row['relpath'])['title'],'Star Trek: Deep Space Nine')
                nested={'imdb_id':None,'tmdb_id':'123','tvdb_id':None}
                db.match_folder('tv','DS9LD/Season 1','Override',None,nested)
                self.assertEqual(db.folder_match('tv',row['relpath'])['tmdb_id'],'123')
                self.assertEqual(db.match_folder('tv','Missing','Missing',None,ids),[])
