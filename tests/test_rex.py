import unittest
from unittest.mock import Mock

import requests

from scud.rex import RexClient


class RexNativeAPITests(unittest.TestCase):
    def setUp(self):
        self.client = RexClient({
            'rex_url': 'http://rex:32401',
            'rex_source': 'scud',
            'source_url': 'http://scud:8789',
            # Old configurations must not send a Plex credential to the feed.
            'rex_token': 'legacy-secret',
        }, Mock())
        self.client.session = Mock()

    def test_connection_uses_native_api_without_credentials(self):
        self.client.session.get.return_value = Mock(
            ok=True, status_code=200, json=lambda: {'size': 0})
        self.assertTrue(self.client.test()['ok'])
        self.client.session.get.assert_called_once_with(
            'http://rex:32401/rex/sources',
            headers={'Accept': 'application/json'}, timeout=8)

    def test_connection_requires_no_token(self):
        self.client.config.pop('rex_token')
        self.client.session.get.return_value = Mock(
            ok=True, status_code=200, json=lambda: {'size': 1, 'sources': []})
        self.assertTrue(self.client.test()['ok'])

    def test_rejects_wrong_server_and_private_network_refusal(self):
        for status in (403, 404, 500):
            self.client.session.get.return_value = Mock(ok=False, status_code=status)
            self.assertFalse(self.client.test()['ok'])
        for payload in ({'MediaContainer': {}}, [], {'size': 'invalid'}):
            self.client.session.get.return_value = Mock(
                ok=True, status_code=200, json=lambda: payload)
            self.assertFalse(self.client.test()['ok'])
        self.client.session.get.side_effect = requests.ConnectionError()
        self.assertFalse(self.client.test()['ok'])

    def test_registration_and_pushes_use_only_native_routes(self):
        self.client.session.put.return_value = Mock(content=b'{}', ok=True)
        self.client.session.post.return_value = Mock(content=b'{}', ok=True)
        self.client.session.delete.return_value = Mock(content=b'{}', ok=True)
        self.client.register_source()
        self.client.post_items([{'id': 'local-file', 'library': 'movie'}])
        self.client.delete_ids(['local-file'])
        self.client.snapshot([])
        for call in self.client.session.method_calls:
            self.assertTrue(call.args[0].startswith('http://rex:32401/rex/'))
            self.assertNotIn('X-Plex-Token', call.kwargs['headers'])
        self.client.session.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()

class RexLibraryCreationTests(unittest.TestCase):
 def test_legacy_shared_destination_is_not_redeclared(self):
  from scud.rex import directory_plan,legacy_shared_key
  config={'libraries':[{'id':'one','type':'movie','name':'Movies','rex_library_key':'4'},{'id':'two','type':'movie','name':'Movies','rex_library_key':'4'}]}
  self.assertEqual(directory_plan(config),([],{'one':'one','two':'two'}))
  self.assertEqual(legacy_shared_key(config,'two'),'4')
 def test_declares_libraries_through_source_api_without_credentials(self):
  config={'rex_url':'http://rex:32401','source_url':'http://scud:8788','libraries':[{'id':'movies','type':'movie','rex_library_name':'Local Movies','rex_library_key':'3'},{'id':'tv','type':'show','name':'Local TV'}]}
  client=RexClient(config,Mock());client.session=Mock()
  client.session.put.return_value=Mock(content=b'{}',ok=True);client.session.put.return_value.json.return_value={}
  client.register_source()
  call=client.session.put.call_args
  self.assertEqual(call.kwargs['json']['directories'],[{'name':'movies','movies':'Local Movies'},{'name':'tv','shows':'Local TV'}])
  self.assertEqual(call.kwargs['headers'],{'Accept':'application/json'})
  self.assertEqual(config['libraries'][0]['rex_library_key'],'3')
  client.session.get.assert_not_called();client.session.post.assert_not_called()
 def test_rejected_library_declaration_is_not_reported_as_success(self):
  from scud.rex import RexError
  client=RexClient({'rex_url':'http://rex','source_url':'http://scud'},Mock());client.session=Mock()
  client.session.put.return_value=Mock(content=b'{}',ok=True);client.session.put.return_value.json.return_value={'ignored':[{'reason':'invalid directory'}]}
  with self.assertRaisesRegex(RexError,'ignored a library declaration'):client.register_source()
