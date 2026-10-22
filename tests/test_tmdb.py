import unittest
from unittest.mock import Mock
import requests
from scud.tmdb import TMDBClient,TMDBError
from scud.config import public_config

class TMDBTests(unittest.TestCase):
 def test_v3_key_search_and_result_mapping(self):
  client=TMDBClient('a'*32);client.session=Mock()
  client.session.get.return_value=Mock(ok=True,status_code=200)
  client.session.get.return_value.json.return_value={'results':[{'id':15289,'title':'Babylon 5: The Lost Tales','release_date':'2007-07-31'}]}
  rows=client.search('Babylon 5','movie')['results']
  self.assertEqual(rows[0]['tmdb_id'],'15289');self.assertEqual(rows[0]['year'],2007)
  call=client.session.get.call_args;self.assertTrue(call.args[0].endswith('/search/movie'));self.assertEqual(call.kwargs['params']['api_key'],'a'*32)
 def test_read_access_token_uses_header(self):
  client=TMDBClient('read-access-token');client.session=Mock();client.session.get.return_value=Mock(ok=True,status_code=200)
  client.session.get.return_value.json.return_value={'results':[]};client.search('Show','show')
  call=client.session.get.call_args;self.assertTrue(call.args[0].endswith('/search/tv'));self.assertEqual(call.kwargs['headers']['Authorization'],'Bearer read-access-token');self.assertNotIn('api_key',call.kwargs['params'])
 def test_errors_do_not_expose_key(self):
  key='b'*32;client=TMDBClient(key);client.session=Mock()
  client.session.get.side_effect=requests.ConnectionError('secret URL '+key)
  result=client.test();self.assertFalse(result['ok']);self.assertNotIn(key,str(result))
  client.session.get.side_effect=None;client.session.get.return_value=Mock(ok=False,status_code=401)
  self.assertFalse(client.test()['ok']);self.assertEqual(public_config({'tmdb_api_key':key})['tmdb_api_key'],'********')
 def test_missing_key(self):
  self.assertFalse(TMDBClient('').test()['ok'])
