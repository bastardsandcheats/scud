import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from scud.compat import Compatibility

class CompatibilityTests(unittest.TestCase):
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
   if url.endswith('/rex/sources'):data={'size':0}
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
