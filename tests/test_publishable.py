import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from scud.scanner import Scanner

class MatchedOnlyFeedTests(unittest.TestCase):
 def setUp(self):
  self.good={'id':'good','library_id':'movies','kind':'movie','relpath':'Movie/movie.mkv','size':1,'match_status':'matched','tmdb_id':'15289'}
  self.bad={**self.good,'id':'bad','match_status':'unmatched'}
  self.db=Mock();self.db.list_media.return_value=[self.good,self.bad]
  self.scanner=Scanner(SimpleNamespace(db=self.db,log=Mock(),config={'rex_url':'http://rex','libraries':[{'id':'movies'}]}))
  self.scanner.app.scanner=self.scanner
  self.scanner.receipts=Mock(checked=1,error='')
  self.scanner.receipts.state.side_effect=lambda row:'received' if self.scanner.publishable(row) else 'withheld'
 def test_only_confirmed_valid_ids_are_publishable(self):
  self.assertTrue(self.scanner.publishable(self.good))
  for row in (self.bad,{**self.good,'match_status':'error'},{**self.good,'tmdb_id':None},{**self.good,'tmdb_id':'bad'},None):self.assertFalse(self.scanner.publishable(row))
  self.assertIsNone(self.scanner.feed_item(self.bad))
  self.assertEqual([item['id'] for item in self.scanner.all_feed_items()],['good'])
 def test_episode_needs_season_and_episode(self):
  row={**self.good,'kind':'show','season':1,'episode':1};self.assertTrue(self.scanner.publishable(row))
  self.assertFalse(self.scanner.publishable({**row,'episode':None}));self.assertFalse(self.scanner.publishable({**row,'season':-1}))
 def test_incremental_sync_withdraws_unmatched_and_pushes_only_matched(self):
  self.db.get_media.side_effect=lambda ident:self.good if ident=='good' else self.bad
  self.db.state_get.return_value='9999999999'
  with patch('scud.scanner.RexClient') as client:
   client.return_value.ensure_libraries.return_value=False
   self.scanner.sync(['good','bad'],[])
   client.return_value.delete_ids.assert_called_with(['bad'])
   self.assertEqual([item['id'] for item in client.return_value.post_items.call_args.args[0]],['good'])
 def test_full_snapshot_is_filtered_and_withdraws_old_unmatched(self):
  with patch('scud.scanner.RexClient') as client:
   client.return_value.ensure_libraries.return_value=False
   self.scanner.force_snapshot()
   client.return_value.delete_ids.assert_called_with(['bad'])
   self.assertEqual([item['id'] for item in client.return_value.snapshot.call_args.args[0]],['good'])
