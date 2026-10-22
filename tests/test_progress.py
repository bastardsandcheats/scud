import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from scud.scanner import Scanner
from scud.receipts import RexReceipts

class ScanTimingTests(unittest.TestCase):
    def setUp(self):
        self.scanner=Scanner(SimpleNamespace(db=Mock(),log=Mock(),config={}))
    def test_eta_uses_completed_files_and_freezes_when_scan_finishes(self):
        self.scanner.progress={'phase':'scanning','started':100,'processed':20,'total':100}
        status=self.scanner.scan_status(now=110)
        self.assertEqual(status['files_per_second'],2)
        self.assertEqual(status['remaining_seconds'],40)
        self.assertEqual(status['estimated_finish'],150)
        self.scanner.progress.update(phase='syncing',processed=100,scan_finished=150)
        status=self.scanner.scan_status(now=250)
        self.assertEqual(status['elapsed_seconds'],50)
        self.assertNotIn('estimated_finish',status)
    def test_no_eta_before_any_file_completes(self):
        self.scanner.progress={'phase':'scanning','started':100,'processed':0,'total':100}
        self.assertNotIn('estimated_finish',self.scanner.scan_status(now=110))

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.row={'id':'one','library_id':'tv','kind':'show','match_status':'matched','tmdb_id':1,'season':1,'episode':1}
        self.app=SimpleNamespace(config={'libraries':[{'id':'tv','rex_library_key':'4'}]},scanner=SimpleNamespace(publishable=Scanner.publishable,feed_id=lambda row:row.get('rex_feed_id') or row['id'],stop_evt=Mock(is_set=lambda:False)),log=Mock(),db=Mock())
        self.receipts=RexReceipts(self.app)
    def test_requires_receipt_in_correct_library(self):
        self.assertEqual(self.receipts.state(self.row),'unknown')
        self.receipts.checked=1
        self.assertEqual(self.receipts.state(self.row),'pending')
        self.receipts.locations={'one':'2'}
        self.assertEqual(self.receipts.state(self.row),'other_library')
        self.receipts.locations={'one':'4'}
        self.assertEqual(self.receipts.state(self.row),'received')
        self.assertEqual(self.receipts.state({**self.row,'match_status':'unmatched'}),'withheld')
        self.receipts.error='offline'
        self.assertEqual(self.receipts.state(self.row),'unknown')
    def test_deleted_receipts_are_not_present(self):
        response=Mock(ok=True);response.json.return_value={'items':[{'id':'one','ratingKey':'10','deleted':True}]}
        with patch('scud.receipts.RexClient') as client:
            client.return_value.session.get.return_value=response
            self.receipts.refresh()
        self.assertEqual(self.receipts.state(self.row),'pending')

class SendProgressTests(unittest.TestCase):
    def test_snapshot_updates_after_acknowledgements(self):
        from scud.rex import RexClient
        client=RexClient({'rex_url':'http://rex'},Mock());client.session=Mock()
        client.session.put.return_value=Mock(ok=True,content=b'{}')
        progress=[]
        client.snapshot([{'id':str(n)} for n in range(201)],lambda sent,total:progress.append((sent,total)))
        self.assertEqual(progress,[(0,201),(200,201),(201,201)])
    def test_failed_batch_does_not_report_completion(self):
        from scud.rex import RexClient,RexError
        client=RexClient({'rex_url':'http://rex'},Mock());client.session=Mock()
        good=Mock(ok=True,content=b'{}');good.json.return_value={}
        bad=Mock(ok=False,status_code=500,text='failed')
        client.session.put.side_effect=[good,good,bad]
        progress=[]
        with self.assertRaises(RexError):client.snapshot([{'id':str(n)} for n in range(201)],lambda sent,total:progress.append((sent,total)))
        self.assertEqual(progress,[(0,201),(200,201)])

class LibraryRelocationTests(unittest.TestCase):
    def test_relocation_uses_only_scud_ids_and_survives_a_failed_push(self):
        import json,tempfile
        from pathlib import Path
        from scud.db import Database
        from scud.scanner import Scanner
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'scud.db')
            with db.connect() as conn:conn.execute("INSERT INTO media(id,library_id,relpath,real_path,size,kind,match_status,tmdb_id,season,episode,updated_at) VALUES('scud-one','tv','Show/e.mkv','/tmp/e.mkv',1,'show','matched','1',1,1,0)")
            app=SimpleNamespace(db=db,log=Mock(),config={'libraries':[{'id':'tv','rex_library_key':'4'}]});scanner=Scanner(app);app.scanner=scanner
            present=set();scanner.receipts=Mock(error='',refresh=lambda:None);scanner.receipts.state.side_effect=lambda row:'received' if row and (row.get('rex_feed_id') or row['id']) in present else 'other_library'
            rex=Mock();rex.post_items.side_effect=RuntimeError('connection lost')
            with self.assertRaises(RuntimeError):scanner.repair_libraries(rex)
            self.assertEqual(json.loads(db.state_get('rex_relocation_pending')),['scud-one'])
            self.assertEqual(rex.delete_ids.call_args.args[0],['scud-one'])
            self.assertEqual(db.get_media('scud-one')['rex_feed_id'],'scud-one-lib-4')
            rex.post_items.side_effect=lambda items:present.update(item['id'] for item in items)
            scanner.repair_libraries(rex)
            self.assertEqual(json.loads(db.state_get('rex_relocation_pending')),[])
            self.assertEqual(rex.delete_ids.call_args.args[0],['scud-one-lib-4'])
