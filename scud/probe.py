# Zurg reference: /internal/torrent/mediainfo.go (full ffprobe data passed to Rex, including chapters).
from __future__ import annotations
import json, subprocess
from pathlib import Path

def media_tools(ffmpeg_path: str = '') -> tuple[str, str]:
    value = str(ffmpeg_path or '').strip()
    if not value:
        return 'ffmpeg', 'ffprobe'
    path = Path(value).expanduser()
    if path.is_dir():
        return str(path/'ffmpeg'), str(path/'ffprobe')
    if path.name == 'ffmpeg' and path.parent == Path('.') and '/' not in value:
        return 'ffmpeg', 'ffprobe'
    return str(path), str(path.with_name('ffprobe'))

def test_media_tools(ffmpeg_path: str = '') -> dict:
    tools = media_tools(ffmpeg_path)
    versions = {}
    for name, executable in zip(('ffmpeg', 'ffprobe'), tools):
        try:
            result = subprocess.run([executable, '-version'], capture_output=True,
                                    text=True, timeout=8, check=False)
            version = (result.stdout or result.stderr).splitlines()
            if result.returncode != 0 or not version or not version[0].startswith(name+' version '):
                return {'ok':False, 'error':f'{name} test failed at {executable}. Select an FFmpeg installation containing both ffmpeg and ffprobe.'}
            versions[name] = version[0]
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'ok':False, 'error':f'Cannot run {name} at {executable}: {exc}'}
    return {'ok':True, 'versions':versions}

def ffprobe(path:str, ffmpeg_path:str='')->tuple[dict|None,str|None]:
    cmd=[media_tools(ffmpeg_path)[1],'-v','error','-print_format','json','-show_format','-show_streams','-show_chapters',path]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=300,check=False)
    except Exception as e: return None,str(e)
    if p.returncode!=0: return None,(p.stderr or f"ffprobe exited {p.returncode}").strip()
    try:
        data=json.loads(p.stdout)
        if not data.get('streams'): return None,'ffprobe returned no streams'
        return data,None
    except Exception as e: return None,f"invalid ffprobe JSON: {e}"
