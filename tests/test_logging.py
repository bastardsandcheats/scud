import logging,tempfile,unittest
from pathlib import Path
from scud.app import App
from scud.config import load_config,save_config

class LogLevelTests(unittest.TestCase):
 def test_info_default_and_live_changes(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);app=App(root,root/'config.yml');self.assertEqual(app.config['log_level'],'INFO')
   cfg=dict(app.config);cfg['log_level']='DEBUG';save_config(app.config_path,cfg);app.reload_config();self.assertEqual(logging.getLogger().level,logging.DEBUG);self.assertGreaterEqual(logging.getLogger('urllib3').level,logging.WARNING)
   cfg['log_level']='INFO';save_config(app.config_path,cfg);app.reload_config();self.assertEqual(logging.getLogger().level,logging.INFO)
 def test_invalid_level_is_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'config.yml';path.write_text('log_level: verbose\n')
   with self.assertRaises(ValueError):load_config(path)
