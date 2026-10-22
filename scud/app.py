from __future__ import annotations
import argparse, logging, os, signal, sys, threading
from pathlib import Path
from .config import load_config
from .db import Database
from .scanner import Scanner
from .web import WebServer
from .compat import Compatibility

class App:
    def __init__(self,root:Path,config_path:Path):
        self.root=root; self.config_path=config_path
        self.config=load_config(config_path)
        logging.basicConfig(level=os.getenv('SCUD_LOG_LEVEL',self.config.get('log_level','INFO')).upper(),format='%(asctime)s %(levelname)-7s %(message)s',datefmt='%H:%M:%S')
        self.log=logging.getLogger('scud'); self.configure_logging(); self.db=Database(root/'data/scud.db'); self.scanner=Scanner(self); self.compat=Compatibility(self)
    def configure_logging(self):
        level=os.getenv('SCUD_LOG_LEVEL',self.config.get('log_level','INFO')).upper()
        logging.getLogger().setLevel(level)
        # HTTP-library debug logs may include credential-bearing query strings.
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
    def reload_config(self):
        self.config=load_config(self.config_path);self.configure_logging()

def main():
    p=argparse.ArgumentParser(description='Scud - local media source for Rex'); p.add_argument('--config',default=os.getenv('SCUD_CONFIG','config.yml')); args=p.parse_args()
    root=Path(__file__).resolve().parents[1]; cfg=Path(args.config); cfg=cfg if cfg.is_absolute() else root/cfg
    app=App(root,cfg)
    def boot():
        app.compat.run();app.scanner.start()
    threading.Thread(target=boot,name='scud-startup',daemon=True).start()
    def stop(*_): app.scanner.stop(); sys.exit(0)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    WebServer(app).serve()
