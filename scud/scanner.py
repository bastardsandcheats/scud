# Zurg reference: /internal/rexfeed/library.go (source-owned placement and feed items); local files replace provider releases.
from __future__ import annotations
import hashlib, json, os, re, threading, time, uuid
from pathlib import Path
from .matcher import guess_file, Matcher
from .probe import ffprobe
from .rex import RexClient
from .config import save_config
from .receipts import RexReceipts
from .inventory import FolderInventory
from .extras import extra_type,identity,group_key
from .publisher import Publisher

VIDEO_EXT={'.mkv','.mp4','.m4v','.avi','.mov','.ts','.m2ts','.mts','.webm','.wmv','.mpg','.mpeg','.flv','.divx','.iso'}
IGNORE_PARTS={'sample','samples','extras','featurettes'}

class Scanner:
    def __init__(self,app):
        self.app=app; self.db=app.db; self.log=app.log; self.stop_evt=threading.Event(); self.wake=threading.Event(); self.busy=False; self.progress={}; self.sync_lock=threading.Lock(); self.send_progress={}; self.snapshot_due=True; self.receipts=RexReceipts(app); self.publisher=Publisher(self)
        saved=self.db.state_get('scan_progress','{}')
        if isinstance(saved,str):
            try:self.progress=json.loads(saved)
            except ValueError:pass
    def start(self):
        self.publisher.start()
        self.thread=threading.Thread(target=self.run,name='scud-scanner',daemon=True); self.thread.start()
        threading.Thread(target=self.check_receipts,name='scud-receipts',daemon=True).start()
    def check_receipts(self):
        while not self.stop_evt.is_set():
            if self.app.config.get('rex_url') and not self.sync_lock.locked():self.receipts.refresh()
            self.stop_evt.wait(60)
    def send_update(self,sent,total):
        self.send_progress.update(phase='sending',sent=sent,total=total)
    def stop(self): self.stop_evt.set(); self.wake.set();self.publisher.wake.set()
    def trigger(self): self.wake.set()
    def run(self):
        while not self.stop_evt.is_set():
            try:
                cfg=self.app.config
                if cfg.get('libraries') and cfg.get('rex_url'): self.scan_once()
            except Exception: self.log.exception('scan failed')
            finally:self.publisher.ready.set()
            self.wake.wait(max(5,int(self.app.config.get('poll_every_secs',60)))); self.wake.clear()
    def stable_id(self,lib,st,rel):
        key=f"{lib['id']}:{getattr(st,'st_dev',0)}:{getattr(st,'st_ino',0)}"
        if not getattr(st,'st_ino',0): key=f"{lib['id']}:{rel}"
        return 'scud-'+hashlib.sha1(key.encode()).hexdigest()[:28]
    def scan_status(self, now=None):
        progress=dict(self.progress)
        now=time.time() if now is None else now
        started=progress.get('started')
        if started:
            end=progress.get('scan_finished') or progress.get('finished') or now
            elapsed=max(0,end-started)
            processed=progress.get('processed',0)
            rate=processed/elapsed if elapsed>0 else 0
            progress.update(elapsed_seconds=round(elapsed,1),files_per_second=round(rate,2))
            if progress.get('phase')=='scanning' and rate>0 and progress.get('total') is not None:
                remaining=max(0,progress['total']-processed)/rate
                progress.update(remaining_seconds=round(remaining),estimated_finish=int(now+remaining))
        return progress
    def scan_once(self):
        if self.busy:return
        self.busy=True; scan_id=uuid.uuid4().hex; started=time.time(); changed=[]; found=0; scanned_libraries=[]
        self.progress={'phase':'discovering','found':0,'processed':0,'current':'','started':started}
        matcher=Matcher(self.db,self.log,self.app.config)
        try:
            if self.db.state_get('numbering_parser_version')!='2':
                for row in self.db.list_media(kind='show',limit=200000):
                    if row.get('numbering_manual'):continue
                    library=next((lib for lib in self.app.config.get('libraries',[]) if lib['id']==row['library_id']),None)
                    if not library:continue
                    guess=guess_file(library,row['relpath'])
                    if guess.season is not None and guess.episode is not None and (guess.season,guess.episode,guess.episode_end)!=(row.get('season'),row.get('episode'),row.get('episode_end')):
                        with self.db.connect() as conn:conn.execute('UPDATE media SET season=?,episode=?,episode_end=? WHERE id=?',(guess.season,guess.episode,guess.episode_end,row['id']))
                        changed.append(row['id'])
                self.db.state_set('numbering_parser_version','2')
            folders=FolderInventory(self.db,VIDEO_EXT,self.log)
            inventory={library['id']:folders.library(library,self.app.config) for library in self.app.config.get('libraries',[])}
            found=folders.files_skipped
            with self.db.connect() as connection:
                connection.executemany('UPDATE media SET seen_scan=? WHERE id=?',[(scan_id,ident) for ident in folders.preserved])
            self.progress.update(phase='scanning',found=found,processed=found,total=found+sum(len(entries) for entries in inventory.values()),folders_skipped=folders.skipped,files_skipped=folders.files_skipped)
            for lib in self.app.config.get('libraries',[]):
                root=Path(lib['path'])
                if not root.is_dir():
                    self.log.warning('library path does not exist: %s; preserving its existing rows',root); continue
                if lib['id'] not in folders.failed:scanned_libraries.append(lib['id'])
                for p,st in inventory[lib['id']]:
                    self.progress.update(processed=found)
                    rel=p.relative_to(root).as_posix(); found+=1; self.progress.update(found=found,current=str(p))
                    item_id=self.stable_id(lib,st,rel); existing=self.db.get_media(item_id)
                    unchanged=existing and existing['size']==st.st_size and existing['mtime_ns']==st.st_mtime_ns
                    retry_name=unchanged and existing['match_status'] in ('unmatched','error') and existing.get('match_method')!='folder-filename-tmdb-v1'
                    if unchanged and not retry_name:
                        moved = existing.get('relpath') != rel or existing.get('real_path') != str(p)
                        with self.db.connect() as db: db.execute("UPDATE media SET seen_scan=?,real_path=?,relpath=?,updated_at=? WHERE id=?",(scan_id,str(p),rel,int(time.time()),item_id))
                        if moved: changed.append(item_id)
                        continue
                    g=guess_file(lib,rel)
                    media_info,probe_error=(existing.get('media_info'),existing.get('probe_error')) if unchanged else ffprobe(str(p),self.app.config.get('ffmpeg_path',''))
                    folder_match=self.db.folder_match(lib['id'],rel)
                    if folder_match:
                        match={'status':'matched','title':folder_match['title'],'year':folder_match['year'],'ids':{kind:folder_match[kind+'_id'] for kind in ('imdb','tmdb','tvdb')},'method':'folder','confidence':1.0}
                    else: match=matcher.match_file(lib,rel)
                    ids=match.get('ids') or {}
                    now=int(time.time())
                    with self.db.connect() as db:
                        db.execute("""INSERT INTO media(id,library_id,relpath,real_path,dev,inode,size,mtime_ns,kind,title_guess,year_guess,season,episode,episode_end,match_status,matched_title,matched_year,imdb_id,tmdb_id,tvdb_id,match_method,confidence,media_info,probe_error,seen_scan,updated_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(id) DO UPDATE SET library_id=excluded.library_id,relpath=excluded.relpath,real_path=excluded.real_path,dev=excluded.dev,inode=excluded.inode,size=excluded.size,mtime_ns=excluded.mtime_ns,kind=excluded.kind,title_guess=excluded.title_guess,year_guess=excluded.year_guess,season=CASE WHEN media.numbering_manual=1 THEN media.season ELSE excluded.season END,episode=CASE WHEN media.numbering_manual=1 THEN media.episode ELSE excluded.episode END,episode_end=CASE WHEN media.numbering_manual=1 THEN media.episode_end ELSE excluded.episode_end END,
                          match_status=CASE WHEN media.match_method='manual' THEN media.match_status ELSE excluded.match_status END,
                          matched_title=CASE WHEN media.match_method='manual' THEN media.matched_title ELSE excluded.matched_title END,
                          matched_year=CASE WHEN media.match_method='manual' THEN media.matched_year ELSE excluded.matched_year END,
                          imdb_id=CASE WHEN media.match_method='manual' THEN media.imdb_id ELSE excluded.imdb_id END,
                          tmdb_id=CASE WHEN media.match_method='manual' THEN media.tmdb_id ELSE excluded.tmdb_id END,
                          tvdb_id=CASE WHEN media.match_method='manual' THEN media.tvdb_id ELSE excluded.tvdb_id END,
                          match_method=CASE WHEN media.match_method='manual' THEN media.match_method ELSE excluded.match_method END,
                          confidence=CASE WHEN media.match_method='manual' THEN media.confidence ELSE excluded.confidence END,
                          media_info=excluded.media_info,probe_error=excluded.probe_error,seen_scan=excluded.seen_scan,updated_at=excluded.updated_at""",
                          (item_id,lib['id'],rel,str(p),int(st.st_dev),int(st.st_ino),st.st_size,st.st_mtime_ns,g.kind,g.title,g.year,g.season,g.episode,g.episode_end,match.get('status','unmatched'),match.get('title'),match.get('year'),ids.get('imdb'),ids.get('tmdb'),ids.get('tvdb'),match.get('method'),match.get('confidence'),json.dumps(media_info,separators=(',',':')) if media_info else None,probe_error,scan_id,now))
                    changed.append(item_id)
            with self.db.connect() as db:
                gone=[]
                if scanned_libraries:
                    marks=','.join('?' for _ in scanned_libraries)
                    removed_rows=db.execute(f"SELECT * FROM media WHERE library_id IN ({marks}) AND (seen_scan IS NULL OR seen_scan<>?)",(*scanned_libraries,scan_id)).fetchall()
                    gone=[self.feed_id(dict(row)) for row in removed_rows]
                    if removed_rows:db.executemany("DELETE FROM media WHERE id=?",[(row['id'],) for row in removed_rows])
            folders.save()
            self.progress.update(phase='syncing',found=found,processed=found,scan_finished=time.time(),changed=len(changed),removed=len(gone))
            self.sync(changed,gone)
            self.log.info('Scan complete: %s files, %s unchanged folders, %s changed, %s removed in %.2fs',found,folders.skipped,len(changed),len(gone),self.progress['scan_finished']-started)
            self.db.state_set('last_scan',int(time.time())); self.db.state_set('last_scan_seconds',f"{time.time()-started:.2f}")
        except Exception as error:
            self.progress.update(phase='error',error=str(error));raise
        finally:
            self.progress.update(phase='error' if self.progress.get('phase')=='error' else 'idle',found=found,processed=found,finished=time.time()); self.busy=False
            self.db.state_set('scan_progress',json.dumps(self.progress))
    @staticmethod
    def publishable(row):
        if not row or row.get('match_status')!='matched':return False
        valid=bool(re.fullmatch(r'tt[0-9]+',str(row.get('imdb_id') or '')) or any(str(row.get(field) or '').isdigit() and int(row[field])>0 for field in ('tmdb_id','tvdb_id')))
        if not valid:return False
        if extra_type(row):return True
        if row.get('kind')=='show':
            try:return row.get('season') is not None and int(row['season'])>=0 and row.get('episode') is not None and int(row['episode'])>=1
            except (ValueError,TypeError):return False
        return row.get('kind')=='movie'
    def feed_id(self,row):
        if extra_type(row):
            library=next((lib for lib in self.app.config.get('libraries',[]) if lib['id']==row['library_id']),{})
            key=json.dumps([sorted(identity(row)),library.get('rex_library_key')],sort_keys=True)
            return row['id']+'-extra-'+hashlib.sha1(key.encode()).hexdigest()[:10]
        return row.get('rex_feed_id') or row['id']
    def feed_parents(self,rows):
        parents={}
        for row in rows:
            if self.publishable(row) and not extra_type(row):parents.setdefault(group_key(row),[]).append(row)
        return parents
    def feed_items(self,rows):
        parents=self.feed_parents(self.db.list_media(limit=200000)) if any(extra_type(row) for row in rows if row) else {}
        return [item for row in sorted((row for row in rows if row),key=lambda row:bool(extra_type(row))) if (item:=self.feed_item(row,parents))]
    def feed_item(self,row,parents=None):
        if not self.publishable(row):return None
        lib=next((x for x in self.app.config.get('libraries',[]) if x['id']==row['library_id']),None) or {}
        item={'id':self.feed_id(row),'path':f"{row['library_id']}/{row['relpath']}",'name':row['relpath'],
              'release':f"{row['library_id']}/{Path(row['relpath']).parts[0] if len(Path(row['relpath']).parts)>1 else Path(row['relpath']).stem}",
              'folder':str(Path(row['relpath']).parent.as_posix()) if str(Path(row['relpath']).parent)!='.' else '',
              'size':row['size'],'media_info':row.get('media_info')}
        if lib.get('rex_library_key'): item['library']=str(lib['rex_library_key'])
        else: item['library']='show' if row['kind']=='show' else 'movie'
        if row.get('rex_feed_id'):
            item['file']=f"/scud/{row['library_id']}/library-{lib.get('rex_library_key')}/{row['relpath']}"
        ids={k:v for k,v in [('imdb',row.get('imdb_id')),('tmdb',row.get('tmdb_id')),('tvdb',row.get('tvdb_id'))] if v not in (None,'')}
        if ids:
            item['ids']=ids; item['kind']='episode' if row['kind']=='show' else 'movie'
            if row['kind']=='show' and row.get('season') is not None and row.get('episode') is not None:
                item['season']=int(row['season']); item['episode']=int(row['episode'])
                if row.get('episode_end'): item['episode_end']=int(row['episode_end'])
        extra=extra_type(row)
        if extra:
            if parents is None:parents=self.feed_parents(self.db.list_media(limit=200000))
            parent=next((candidate for candidate in parents.get(group_key(row),[]) if identity(candidate)&identity(row)),None)
            if parent is None:return None
            parent_item=self.feed_item(parent,{})
            parent_file=parent_item.get('file') or '/scud/'+parent_item['path']
            parts=Path(row['relpath']).parts[1:]
            if parts and parts[0].lower() in ('extras','specials','bonus'):parts=parts[1:]
            item['file']=str(Path(parent_file).parent / ' - '.join(parts))
            item['kind']='extra';item['extra_type']=extra
            item['name']=Path(row['relpath']).stem
            for key in ('season','episode','episode_end'):item.pop(key,None)
        return item
    def all_feed_items(self): return self.feed_items(self.db.list_media(limit=200000))
    def withdraw_unmatched(self,rex):
        ids=[self.feed_id(row) for row in self.db.list_media(limit=200000) if not self.publishable(row)]
        for offset in range(0,len(ids),1000):rex.delete_ids(ids[offset:offset+1000])
    def repair_libraries(self,rex):
        saved=self.db.state_get('rex_relocation_pending','[]')
        pending=json.loads(saved or '[]') if isinstance(saved,str) else []
        if not isinstance(pending,list):pending=[]
        misplaced=[row['id'] for row in self.db.list_media(limit=200000) if self.receipts.state(row) in ('other_library','pending') and not extra_type(row)]
        if not pending and not misplaced:return
        self.receipts.refresh()
        if self.receipts.error:raise RuntimeError('Cannot verify Rex libraries before moving files: '+self.receipts.error)
        candidates=set(pending)
        candidates.update(row['id'] for row in self.db.list_media(limit=200000) if self.receipts.state(row) in ('other_library','pending') and not extra_type(row))
        rows=[self.db.get_media(ident) for ident in sorted(candidates)]
        rows=[row for row in rows if self.publishable(row) and self.receipts.state(row)!='received']
        self.send_progress.update(phase='relocating',sent=0,total=len(rows))
        remaining=[row['id'] for row in rows]
        self.db.state_set('rex_relocation_pending',json.dumps(remaining))
        for offset in range(0,len(rows),50):
            batch=rows[offset:offset+50]
            # A manually matched Rex parent protects even a trashed old version.
            # Give this source version a fresh feed ID for its new library, leaving
            # the old parent's identity and other sources' versions untouched.
            rex.delete_ids([row.get('rex_feed_id') or row['id'] for row in batch])
            for row in batch:
                library=next(lib for lib in self.app.config['libraries'] if lib['id']==row['library_id'])
                row['rex_feed_id']=row['id']+'-lib-'+str(library['rex_library_key'])
            with self.db.connect() as connection:
                connection.executemany('UPDATE media SET rex_feed_id=? WHERE id=?',[(row['rex_feed_id'],row['id']) for row in batch])
            rex.post_items([self.feed_item(row) for row in batch])
            remaining=remaining[len(batch):]
            self.db.state_set('rex_relocation_pending',json.dumps(remaining))
            self.send_progress.update(phase='relocating',sent=offset+len(batch),total=len(rows))
            self.log.info('Moved %s/%s Scud files into their intended Rex libraries',offset+len(batch),len(rows))
        self.receipts.refresh()
        if self.receipts.error:raise RuntimeError('Moved files, but Rex receipt verification failed: '+self.receipts.error)
        unresolved=[row['id'] for row in rows if self.receipts.state(self.db.get_media(row['id']))!='received']
        self.db.state_set('rex_relocation_pending',json.dumps(unresolved))
        self.snapshot_due=True
        if unresolved:raise RuntimeError(f'{len(unresolved)} files still need library relocation; Scud will retry.')
    def sync(self,changed,gone):
        if self.publisher.running:
            full=bool(gone) or any(extra_type(self.db.get_media(ident)) for ident in changed)
            self.publisher.enqueue(changed,gone,full=full)
            return
        with self.sync_lock:return self._sync(changed,gone)
    def _sync(self,changed,gone):
        if not self.app.config.get('rex_url'): return
        rex=RexClient(self.app.config,self.log)
        items=self.feed_items([self.db.get_media(ident) for ident in changed])
        self.send_progress={'phase':'preparing','sent':0,'total':len(items),'started':time.time()}
        try:
            if rex.ensure_libraries():
                save_config(self.app.config_path,self.app.config)
                self.snapshot_due=True
            rex.register_source()
            self.withdraw_unmatched(rex)
            if self.receipts.checked is None:self.receipts.refresh()
            self.repair_libraries(rex)
            self.send_update(0,len(items))
            items=self.feed_items([self.db.get_media(ident) for ident in changed])
            for i in range(0,len(items),200):
                rex.post_items(items[i:i+200]);self.send_update(min(i+200,len(items)),len(items))
            for i in range(0,len(gone),1000): rex.delete_ids(gone[i:i+1000])
            last=int(self.db.state_get('last_snapshot',0) or 0); every=int(self.app.config.get('rex_snapshot_every_hours',6))*3600
            if self.snapshot_due or not last or time.time()-last>=every:
                rex.snapshot(self.all_feed_items(),progress=self.send_update); self.db.state_set('last_snapshot',int(time.time()));self.snapshot_due=False
            self.receipts.refresh()
            self.db.state_set('last_rex_error','')
            self.send_progress.update(phase='complete',finished=time.time())
            return True
        except Exception as e:
            self.snapshot_due=True
            self.log.warning('Rex sync failed; next scan/snapshot will heal it: %s',e); self.db.state_set('last_rex_error',str(e));self.send_progress.update(phase='error',error=str(e))
            return False
    def force_snapshot(self):
        if self.publisher.running:
            self.publisher.enqueue([],[],full=True);return
        with self.sync_lock:
            self.send_progress={'phase':'preparing','sent':0,'total':0,'started':time.time()}
            try:
                rex=RexClient(self.app.config,self.log);rex.register_source();self.withdraw_unmatched(rex)
                self.repair_libraries(rex)
                rex.snapshot(self.all_feed_items(),progress=self.send_update)
                self.db.state_set('last_snapshot',int(time.time()))
                self.send_progress.update(phase='complete',finished=time.time())
            except Exception as error:
                self.send_progress.update(phase='error',error=str(error));raise
