import unittest,requests
from types import SimpleNamespace
from unittest.mock import Mock,patch
from scud.compat import Compatibility

class CompatibilityTests(unittest.TestCase):
 def test_busy_rex_has_a_longer_bounded_timeout_and_identifies_failed_request(self):
  check=Compatibility(self.app)
  with patch.object(check,'wait_for_rex'),patch('scud.compat.RexClient') as client:
   client.return_value.base='http://rex'
   client.return_value.session.request.side_effect=requests.exceptions.ReadTimeout('sensitive internal detail')
   with self.assertRaisesRegex(RuntimeError,r'GET /rex/sources timed out waiting 60 seconds for Rex\.'):
    check.rex_contract()
   self.assertEqual(client.return_value.session.request.call_args.kwargs['timeout'],(4,60))
 def test_connection_failure_identifies_request_without_exposing_credentials(self):
  check=Compatibility(self.app)
  with patch.object(check,'wait_for_rex'),patch('scud.compat.RexClient') as client:
   client.return_value.base='http://rex'
   client.return_value.session.request.side_effect=requests.exceptions.ConnectionError('sensitive internal detail')
   with self.assertRaisesRegex(RuntimeError,r'GET /rex/sources could not connect to Rex'):
    check.rex_contract()
 def setUp(self):self.app=SimpleNamespace(config={'rex_url':'http://rex','tmdb_api_key':'private-key'},log=Mock())
 def test_failures_are_logged_and_exposed_separately(self):
  check=Compatibility(self.app)
  with patch.object(check,'rex_contract',side_effect=RuntimeError('Rex item acknowledgement schema changed.')),patch.object(check,'tmdb_contract'):
   result=check.run()
  self.assertEqual(result['state'],'failed');self.assertFalse(result['checks'][0]['ok']);self.assertTrue(result['checks'][1]['ok']);self.app.log.error.assert_called_once()
 def test_missing_configuration_is_not_an_api_break(self):
  self.app.config={};result=Compatibility(self.app).run();self.assertEqual(result['state'],'unconfigured');self.app.log.error.assert_not_called()
 def test_checks_are_isolated_and_cleanup_even_when_contract_changes(self):
  check=Compatibility(self.app)
  def response(method,url,**kwargs):
   body=kwargs.get('json') or {};data={}
   if url.endswith('/identity'):data={'MediaContainer':{'machineIdentifier':'rex-test'}}
   elif url.endswith('/rex/sources'):data={'size':0}
   elif url.endswith('/library/sections'):data={'MediaContainer':{'Directory':[]}}
   elif method=='GET':data={'size':0,'items':[]}
   elif method=='POST':data={'created':'wrong'}
   elif method=='DELETE' and '/confirm/' not in url:data={'confirm':url.removeprefix('http://rex')+'/confirm/abc123'}
   elif method=='DELETE':data={'deleted':True}
   result=Mock(ok=True);result.json.return_value=data;return result
  with patch('scud.compat.RexClient') as client:
   client.return_value.base='http://rex';client.return_value.session.request.side_effect=response
   with self.assertRaisesRegex(RuntimeError,'acknowledgement schema'):check.rex_contract()
   calls=client.return_value.session.request.call_args_list
  self.assertTrue(any('/confirm/' in call.args[1] for call in calls))
  for call in calls:
   if call.args[0]!='GET':self.assertIn('scud-compat-',call.args[1])
  self.assertEqual(calls[0].args,('GET','http://rex/identity'))
 def test_readiness_retries_until_rex_has_an_identity(self):
  check=Compatibility(self.app);rex=Mock(base='http://rex')
  ready=Mock(ok=True);ready.json.return_value={'MediaContainer':{'machineIdentifier':'server'}}
  rex.session.request.side_effect=[requests.exceptions.ConnectionError(),Mock(ok=False,status_code=503),ready]
  with patch('scud.compat.time.sleep') as sleep:check.wait_for_rex(rex)
  self.assertEqual(sleep.call_count,2)
  self.assertEqual(rex.session.request.call_count,3)
  for call in rex.session.request.call_args_list:self.assertEqual(call.args,('GET','http://rex/identity'))
 def test_readiness_timeout_never_starts_feed_checks(self):
  check=Compatibility(self.app)
  with patch('scud.compat.RexClient') as client,patch('scud.compat.time.monotonic',side_effect=[0,91]):
   client.return_value.base='http://rex'
   client.return_value.session.request.side_effect=requests.exceptions.ConnectionError()
   with self.assertRaisesRegex(RuntimeError,'Feed checks were not started'):check.rex_contract()
   self.assertEqual(client.return_value.session.request.call_count,1)
   self.assertEqual(client.return_value.session.request.call_args.args,('GET','http://rex/identity'))
 def test_readiness_rejects_a_successful_response_from_another_page(self):
  check=Compatibility(self.app);rex=Mock(base='http://rex')
  rex.session.request.return_value.ok=True
  rex.session.request.return_value.json.return_value={'status':'ok'}
  with patch('scud.compat.time.monotonic',side_effect=[0,91]):
   with self.assertRaisesRegex(RuntimeError,'does not contain a server identity'):check.wait_for_rex(rex)
