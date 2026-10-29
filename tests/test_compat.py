import json,tempfile,unittest,requests
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from scud.compat import Compatibility

class CompatibilityTests(unittest.TestCase):
 def test_recording_rejects_mismatched_isolated_receipts_without_requests(self):
  from scud.compat import main
  for field in ('state','rex_commit','build_fingerprint','checker_digest'):
   with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
    root=Path(directory);revision=root/'installed-revision';revision.write_text('a'*40)
    (root/'installed-build-fingerprint').write_text('build')
    receipt={'state':'passed','rex_commit':'a'*40,'build_fingerprint':'build','checker_digest':'digest'}
    receipt[field]='wrong';path=root/'receipt.json';path.write_text(json.dumps(receipt))
    with patch('sys.argv',['compat','--record','--receipt',str(path),'--revision-file',str(revision)]),patch('scud.config.load_config',return_value={}),patch('scud.compat.checker_digest',return_value='digest'),patch.object(Compatibility,'run') as run:
     with self.assertRaisesRegex(SystemExit,'does not match'):main()
     run.assert_not_called()
 def test_normal_startup_never_writes_to_production(self):
  check=Compatibility(self.app)
  def response(method,url,**kwargs):
   self.assertEqual(method,'GET')
   result=Mock(ok=True)
   result.json.return_value=({'MediaContainer':{'machineIdentifier':'server'}} if url.endswith('/identity') else {'size':0,'sources':[]} if url.endswith('/rex/sources') else {'MediaContainer':{'Directory':[]}})
   return result
  with patch('scud.compat.RexClient') as client:
   client.return_value.base='http://production-rex'
   client.return_value.session.request.side_effect=response
   check.rex_contract()
   self.assertEqual(client.return_value.session.request.call_count,3)
 def test_mutating_checks_refuse_a_production_url(self):
  check=Compatibility(self.app,isolated=True)
  with patch.object(check,'wait_for_rex'),patch('scud.compat.RexClient') as client:
   client.return_value.base='http://192.168.1.222:32401'
   result=Mock(ok=True);result.json.return_value={'size':0,'MediaContainer':{'Directory':[]}}
   client.return_value.session.request.return_value=result
   with self.assertRaisesRegex(RuntimeError,'loopback'):check.rex_contract()
   for call in client.return_value.session.request.call_args_list:self.assertEqual(call.args[0],'GET')
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
  self.app.config['rex_url']='http://127.0.0.1'
  check=Compatibility(self.app,isolated=True)
  def response(method,url,**kwargs):
   body=kwargs.get('json') or {};data={}
   if url.endswith('/identity'):data={'MediaContainer':{'machineIdentifier':'rex-test'}}
   elif url.endswith('/rex/sources'):data={'size':0}
   elif url.endswith('/library/sections'):data={'MediaContainer':{'Directory':[{'key':'1','type':'movie'}]}}
   elif method=='GET':data={'size':0,'items':[]}
   elif method=='POST':data={'created':'wrong'}
   elif method=='DELETE' and '/confirm/' not in url:data={'confirm':url.removeprefix('http://127.0.0.1')+'/confirm/abc123'}
   elif method=='DELETE':data={'deleted':True}
   result=Mock(ok=True);result.json.return_value=data;return result
  with patch('scud.compat.RexClient') as client:
   client.return_value.base='http://127.0.0.1';client.return_value.session.request.side_effect=response
   with self.assertRaisesRegex(RuntimeError,'acknowledgement schema'):check.rex_contract()
   calls=client.return_value.session.request.call_args_list
  self.assertTrue(any('/confirm/' in call.args[1] for call in calls))
  for call in calls:
   if call.args[0]!='GET':self.assertIn('scud-compat-',call.args[1])
  self.assertEqual(calls[0].args,('GET','http://127.0.0.1/identity'))
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
