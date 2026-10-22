"""Cheap directory fingerprints; unchanged folders never reach matching/probing."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

class FolderInventory:
    def __init__(self,db,extensions,log):
        self.db=db;self.extensions=extensions;self.log=log
        self.cache=json.loads(db.state_get('folder_fingerprints','{}') or '{}')
        self.next={};self.skipped=0;self.files_skipped=0;self.preserved=[];self.failed=set()

    def library(self,lib,config):
        root=Path(lib['path']);paths=[]
        if not root.is_dir():self.failed.add(lib['id']);return paths
        with self.db.connect() as conn:
            old=[dict(row) for row in conn.execute('SELECT id,relpath,match_status,match_method FROM media WHERE library_id=?',(lib['id'],))]
        by_folder={}
        for row in old:by_folder.setdefault(str(Path(row['relpath']).parent),[]).append(row)
        policy=hashlib.sha256(json.dumps([str(root),lib['type'],config.get('tmdb_api_key'),config.get('ffmpeg_path'),'inventory-v1'],sort_keys=True).encode()).hexdigest()
        stack=[root]
        while stack:
            folder=stack.pop();relative=str(folder.relative_to(root));key=lib['id']+':'+relative
            entries=[];videos=[]
            try:
                with os.scandir(folder) as children:
                    for entry in children:
                        if entry.name.startswith('.'):continue
                        if entry.is_dir(follow_symlinks=False):stack.append(Path(entry.path));continue
                        if Path(entry.name).suffix.lower() not in self.extensions or 'sample' in Path(entry.name).stem.lower():continue
                        stat=entry.stat();entries.append((entry.name,stat.st_size,stat.st_mtime_ns,stat.st_ino,stat.st_dev));videos.append((Path(entry.path),stat))
            except OSError as error:
                self.failed.add(lib['id']);self.log.warning('Cannot read folder %s; preserving library entries: %s',folder,error);continue
            signature=hashlib.sha256(json.dumps([policy,sorted(entries)],separators=(',',':')).encode()).hexdigest()
            self.next[key]=signature
            rows=by_folder.get(relative,[])
            retry=any(row['match_status'] in ('unmatched','error') and row.get('match_method')!='folder-filename-tmdb-v1' for row in rows)
            if self.cache.get(key)==signature and len(rows)==len(videos) and not retry:
                self.skipped+=1;self.files_skipped+=len(rows);self.preserved.extend(row['id'] for row in rows)
            else:paths.extend(videos)
        return paths

    def save(self):
        # Failed libraries keep their old fingerprints; they are not used to infer deletions.
        for key,value in self.cache.items():
            if key.split(':',1)[0] in self.failed:self.next[key]=value
        self.db.state_set('folder_fingerprints',json.dumps(self.next,separators=(',',':')))
