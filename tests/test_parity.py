import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from scud.scanner import Scanner
from scud.extras import extra_type
from scud.db import Database
from scud.publisher import Publisher,FULL_KEY
from scud.matcher import episode_numbers,guess_file
from scud.rex import RexClient,RexError,SnapshotSessionLost

class BonusTests(unittest.TestCase):
 def setUp(self):
  self.main={'id':'main','library_id':'tv','relpath':'Show/Season 1/Show.S01E01.mkv','kind':'show','season':1,'episode':1,'match_status':'matched','tmdb_id':1,'size':1}
  self.extra={**self.main,'id':'extra','relpath':'Show/Specials/Behind the Scenes.mkv','season':None,'episode':None}
  db=Mock();db.list_media.return_value=[self.extra,self.main];self.scanner=Scanner(SimpleNamespace(db=db,log=Mock(),config={'libraries':[{'id':'tv','rex_library_key':'4'}]}))
 def test_numbered_special_is_episode_and_unmatched_bonus_is_withheld(self):
  self.assertIsNone(extra_type({**self.extra,'season':0,'episode':1}));self.assertTrue(self.scanner.publishable(self.extra));self.assertFalse(self.scanner.publishable({**self.extra,'match_status':'unmatched'}))
 def test_extra_uses_its_parent_directory_but_original_source_path(self):
  main=self.scanner.feed_item(self.main);item=self.scanner.feed_item(self.extra)
  self.assertEqual(main['library'],'4');self.assertEqual(item['library'],'4');self.assertEqual(item['kind'],'extra');self.assertEqual(item['extra_type'],'behindthescenes');self.assertEqual(item['path'],'tv/'+self.extra['relpath']);self.assertEqual(str(Path(item['file']).parent),str(Path('/scud/'+main['path']).parent));self.assertNotIn('episode',item)
 def test_orphan_bonus_is_not_published_and_features_precede_clips(self):
  self.assertIsNone(self.scanner.feed_item(self.extra,{}));items=self.scanner.all_feed_items();self.assertEqual([item['kind'] for item in items],['episode','extra'])
 def test_movie_title_at_root_is_not_misclassified_as_extra(self):
  self.assertIsNone(extra_type({'kind':'movie','relpath':'Behind the Scenes (2020)/Behind the Scenes.mkv'}))

class NumberingTests(unittest.TestCase):
 def test_episode_forms_and_nonconsecutive_ambiguity(self):
  for text,expected in [('Show.S01EP02.mkv',(1,2,None)),('Show.S01E23.plus.EP24.mkv',(1,23,24)),('Show.S01E23.plus.EP25.mkv',(None,None,None)),('Show.S00E03.mkv',(0,3,None)),('Show.S01E01-E03.mkv',(1,1,3))]:
   with self.subTest(text=text):self.assertEqual(episode_numbers(text),expected)
  guess=guess_file({'type':'show'},'Show/Season 9/02 - Title.mkv');self.assertEqual((guess.season,guess.episode),(9,2))

class QueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=Database(Path(self.tmp.name)/'state.db');self.scanner=SimpleNamespace(db=self.db,log=Mock());self.publisher=Publisher(self.scanner)
 def test_newer_inflight_change_survives_ack_and_queue_survives_reopen(self):
  self.publisher.enqueue(['one'],[]);old,full=self.publisher.batch();self.publisher.enqueue(['one'],[]);self.publisher.acknowledge(old,full)
  reopened=Publisher(self.scanner);jobs,_=reopened.batch();self.assertEqual([row['item_id'] for row in jobs],['one'])
 def test_bounded_queue_becomes_durable_full_snapshot(self):
  self.publisher.enqueue([str(n) for n in range(4097)],[]);jobs,full=self.publisher.batch();self.assertEqual(jobs,[]);self.assertIsNotNone(full)
 def test_new_full_request_survives_old_acknowledgement(self):
  self.publisher.enqueue([],[],full=True);jobs,old=self.publisher.batch();self.publisher.enqueue([],[],full=True);self.publisher.acknowledge(jobs,old);self.assertNotEqual(self.db.state_get(FULL_KEY),'0')

class SnapshotRecoveryTests(unittest.TestCase):
 def test_lost_session_restarts_once_but_shrink_guard_never_retries(self):
  client=RexClient({'rex_url':'http://rex'},Mock());client.session=Mock();client.register_source=Mock()
  good=Mock(ok=True,content=b'{}');good.json.return_value={}
  lost=Mock(ok=False,status_code=409);lost.json.return_value={'error':'no such snapshot session at this part: start again from part 0'}
  client.session.put.side_effect=[good,lost,good,good]
  client.snapshot([{'id':str(n)} for n in range(201)])
  bodies=[call.kwargs['json'] for call in client.session.put.call_args_list];self.assertEqual([body['part'] for body in bodies],[0,1,0,1]);self.assertNotEqual(bodies[0]['session'],bodies[2]['session'])
  refused=Mock(ok=False,status_code=409);refused.json.return_value={'would_remove':100,'of':101};client.session.put.reset_mock();client.session.put.side_effect=None;client.session.put.return_value=refused
  with self.assertRaisesRegex(RexError,'shrink guard'):client.snapshot([])
  self.assertEqual(client.session.put.call_count,1)

class PublisherWorkerTests(unittest.TestCase):
 def test_retry_replays_durable_work_after_failure(self):
  import threading,time
  with tempfile.TemporaryDirectory() as directory:
   db=Database(Path(directory)/'state.db');scanner=SimpleNamespace(db=db,log=Mock(),stop_evt=threading.Event(),sync_lock=threading.Lock(),snapshot_due=True,app=SimpleNamespace(config={'rex_url':'http://rex'}))
   publisher=Publisher(scanner);publisher.min_backoff=.001;publisher.max_backoff=.002;publisher.debounce=.001;publisher.ready.set();publisher.enqueue(['one'],[]);calls=[]
   def deliver(changed,gone):
    calls.append(changed)
    if len(calls)==1:return False
    scanner.snapshot_due=False;scanner.stop_evt.set();return True
   scanner._sync=deliver;thread=threading.Thread(target=publisher.run);thread.start();thread.join(3)
   self.assertFalse(thread.is_alive());self.assertEqual(calls,[['one'],['one']]);self.assertEqual(publisher.batch()[0],[])
 def test_enqueue_does_not_enter_delivery_lock(self):
  import threading
  from scud.app import App
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);app=App(root,root/'config.yml');app.scanner.publisher.running=True;app.scanner.sync_lock.acquire()
   try:
    app.scanner.sync([],['removed'])
    jobs,_=app.scanner.publisher.batch();self.assertEqual(jobs[0]['item_id'],'removed')
   finally:app.scanner.sync_lock.release();app.scanner.publisher.running=False
