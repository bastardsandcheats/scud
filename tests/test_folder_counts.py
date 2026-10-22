import tempfile
import unittest
from pathlib import Path
from scud.db import Database
class FolderCountsTests(unittest.TestCase):
 def test_counts_and_filters_are_by_folder_and_type(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(Path(tmp)/'db.sqlite')
   with db.connect() as conn:
    for ident,kind,path,status in [('1','show','Show/E1.mkv','matched'),('2','show','Show/E2.mkv','unmatched'),('3','show','Other/E1.mkv','matched'),('4','movie','Movie/a.mkv','unmatched'),('5','movie','Movie/b.mkv','unmatched')]:
     conn.execute('INSERT INTO media(id,library_id,relpath,real_path,kind,match_status,updated_at) VALUES(?,?,?,?,?,?,0)',(ident,kind,path,path,kind,status))
   counts=db.count_summary()['folders']
   self.assertEqual(counts['total'],3);self.assertEqual(counts['show'],2);self.assertEqual(counts['unmatched'],2)
   self.assertEqual(counts['by_kind']['movie']['unmatched'],1)
   self.assertEqual(len(db.list_folder_media('movie','unmatched')),2)
   self.assertEqual(len(db.list_folder_media('show','unmatched')),2)
   self.assertEqual(len(db.list_folder_media('show','matched')),1)
