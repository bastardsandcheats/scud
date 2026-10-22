from __future__ import annotations
from pathlib import Path
from typing import Any
import os, re, tempfile
import yaml

CONFIG_VERSION = "v1"
DEFAULT_CONFIG = {
    "scud": CONFIG_VERSION,
    "host": "0.0.0.0",
    "port": 8788,
    "source_url": "",
    "rex_url": "",
    "rex_source": "scud",
    "rex_snapshot_every_hours": 6,
    "poll_every_secs": 60,
    "ffmpeg_path": "",
    "log_level": "INFO",
    "allow_rex_delete": False,
    "tmdb_api_key": "",
    "libraries": [],
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return value or "library"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(raw)
    if cfg.get("scud") != CONFIG_VERSION:
        raise ValueError(f"unsupported config version: {cfg.get('scud')!r}")
    cfg["port"] = int(cfg.get("port", 8788))
    cfg["poll_every_secs"] = max(5, int(cfg.get("poll_every_secs", 60)))
    cfg["rex_snapshot_every_hours"] = max(1, int(cfg.get("rex_snapshot_every_hours", 6)))
    cfg['log_level']=str(cfg.get('log_level','INFO')).upper()
    if cfg['log_level'] not in ('DEBUG','INFO','WARNING','ERROR','CRITICAL'):raise ValueError('Choose DEBUG, INFO, WARNING, ERROR or CRITICAL for log level.')
    if not isinstance(cfg.get('allow_rex_delete'),bool):raise ValueError('allow_rex_delete must be true or false.')
    libs=[]
    used=set()
    for i, lib in enumerate(cfg.get("libraries") or []):
        item=dict(lib or {})
        item["type"] = "show" if item.get("type") in ("show","tv") else "movie"
        item["name"] = str(item.get("name") or ("Local TV" if item["type"]=="show" else "Local Movies"))
        item["path"] = os.path.abspath(os.path.expanduser(str(item.get("path") or "")))
        base=slugify(str(item.get("id") or item["name"] or f"library-{i+1}"))
        ident=base; n=2
        while ident in used:
            ident=f"{base}-{n}"; n+=1
        used.add(ident); item["id"]=ident
        item["rex_library_name"] = str(item.get("rex_library_name") or item["name"])
        item["rex_library_key"] = str(item.get("rex_library_key") or "")
        libs.append(item)
    cfg["libraries"] = libs
    return cfg


def save_config(path: Path, cfg: dict[str, Any]) -> None:
    merged=dict(DEFAULT_CONFIG); merged.update(cfg); merged["scud"]=CONFIG_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="config.",suffix=".yml",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            yaml.safe_dump(merged,f,sort_keys=False,allow_unicode=True)
        os.chmod(tmp,0o600)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def public_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out=dict(cfg)
    if out.get("rex_token"):
        out["rex_token"]="********"
    if out.get("tmdb_api_key"):out["tmdb_api_key"]="********"
    return out
