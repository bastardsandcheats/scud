from __future__ import annotations
import sqlite3, json, time
from pathlib import Path
from contextlib import contextmanager

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS media (
 id TEXT PRIMARY KEY,
 library_id TEXT NOT NULL,
 relpath TEXT NOT NULL,
 real_path TEXT NOT NULL,
 dev INTEGER NOT NULL DEFAULT 0,
 inode INTEGER NOT NULL DEFAULT 0,
 size INTEGER NOT NULL DEFAULT 0,
 mtime_ns INTEGER NOT NULL DEFAULT 0,
 kind TEXT NOT NULL,
 title_guess TEXT,
 year_guess INTEGER,
 season INTEGER,
 episode INTEGER,
 episode_end INTEGER,
 match_status TEXT NOT NULL DEFAULT 'unmatched',
 matched_title TEXT,
 matched_year INTEGER,
 imdb_id TEXT,
 tmdb_id TEXT,
 tvdb_id TEXT,
 match_method TEXT,
 confidence REAL,
 media_info TEXT,
 probe_error TEXT,
 seen_scan TEXT,
 updated_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS media_library_relpath ON media(library_id, relpath);
CREATE INDEX IF NOT EXISTS media_inode ON media(library_id,dev,inode);
CREATE INDEX IF NOT EXISTS media_status ON media(match_status);
CREATE INDEX IF NOT EXISTS media_kind ON media(kind);
CREATE TABLE IF NOT EXISTS title_cache (
 keyword TEXT PRIMARY KEY,
 response_json TEXT NOT NULL,
 fetched_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS folder_matches (
 library_id TEXT NOT NULL,
 folder TEXT NOT NULL,
 title TEXT,
 year INTEGER,
 imdb_id TEXT,
 tmdb_id TEXT,
 tvdb_id TEXT,
 PRIMARY KEY(library_id, folder)
);
"""

class Database:
    def __init__(self,path: Path):
        self.path=path; path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns={row['name'] for row in db.execute('PRAGMA table_info(media)')}
            if 'rex_feed_id' not in columns:db.execute("ALTER TABLE media ADD COLUMN rex_feed_id TEXT NOT NULL DEFAULT ''")
            if 'numbering_manual' not in columns:db.execute('ALTER TABLE media ADD COLUMN numbering_manual INTEGER NOT NULL DEFAULT 0')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30)
        db.row_factory=sqlite3.Row
        try:
            yield db; db.commit()
        finally: db.close()
    def state_get(self,key,default=None):
        with self.connect() as db:
            row=db.execute("SELECT value FROM state WHERE key=?",(key,)).fetchone()
        return row[0] if row else default
    def state_set(self,key,value):
        with self.connect() as db:
            db.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))
    def count_summary(self):
        with self.connect() as db:
            rows=db.execute("SELECT kind, match_status, COUNT(*) n FROM media GROUP BY kind,match_status").fetchall()
            total=db.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        out={"total":total,"movie":0,"show":0,"matched":0,"unmatched":0,"ambiguous":0,"error":0}
        out["by_kind"]={kind:{"total":0,"matched":0,"unmatched":0,"error":0} for kind in ("movie","show")}
        for r in rows:
            by_kind=out["by_kind"].setdefault(r["kind"],{"total":0})
            by_kind["total"]+=r["n"]
            by_kind[r["match_status"]]=by_kind.get(r["match_status"],0)+r["n"]
            out[r['kind']]=out.get(r['kind'],0)+r['n']
            out[r['match_status']]=out.get(r['match_status'],0)+r['n']
        with self.connect() as db:
            groups=db.execute("""SELECT kind,MIN(match_status='matched') all_matched,MAX(match_status='error') has_error
                FROM media GROUP BY library_id,kind,CASE WHEN instr(relpath,'/')=0 THEN 'file:'||id ELSE 'folder:'||substr(relpath,1,instr(relpath,'/')-1) END""").fetchall()
        folders={'total':len(groups),'movie':0,'show':0,'matched':0,'unmatched':0,'error':0,'by_kind':{kind:{'total':0,'matched':0,'unmatched':0,'error':0} for kind in ('movie','show')}}
        for group in groups:
            status='error' if group['has_error'] else 'matched' if group['all_matched'] else 'unmatched'
            kind=group['kind'];folders[kind]+=1;folders[status]+=1
            folders['by_kind'][kind]['total']+=1;folders['by_kind'][kind][status]+=1
        out['folders']=folders
        return out
    def list_media(self,kind="",status="",q="",limit=500,offset=0):
        where=[]; args=[]
        if kind: where.append("kind=?"); args.append(kind)
        if status: where.append("match_status=?"); args.append(status)
        if q:
            where.append("(relpath LIKE ? OR matched_title LIKE ? OR imdb_id LIKE ? OR tmdb_id LIKE ? OR tvdb_id LIKE ?)")
            term=f"%{q}%"; args += [term]*5
        sql="SELECT * FROM media"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY library_id, relpath LIMIT ? OFFSET ?"
        args += [min(max(int(limit),1),200000), max(int(offset),0)]
        with self.connect() as db: rows=db.execute(sql,args).fetchall()
        return [self._row(r) for r in rows]
    def list_folder_media(self,kind='',status='',q='',limit=200000,offset=0):
        groups={}
        for row in self.list_media(kind=kind,limit=200000):
            first,separator,_=row['relpath'].partition('/')
            key=(row['library_id'],first if separator else 'file:'+row['id'])
            groups.setdefault(key,[]).append(row)
        selected=[];term=q.casefold()
        for rows in groups.values():
            group_status='error' if any(row['match_status']=='error' for row in rows) else 'matched' if all(row['match_status']=='matched' for row in rows) else 'unmatched'
            if status and status!=group_status:continue
            if term and not any(term in str(row.get(field) or '').casefold() for row in rows for field in ('relpath','matched_title','imdb_id','tmdb_id','tvdb_id')):continue
            selected.extend(rows)
        return selected[max(0,offset):max(0,offset)+min(max(1,limit),200000)]
    def get_media(self,item_id):
        with self.connect() as db: r=db.execute("SELECT * FROM media WHERE id=?",(item_id,)).fetchone()
        return self._row(r) if r else None
    def folder_items(self,library_id,folder,limit=200000):
        with self.connect() as db:
            params=(library_id,len(folder)+1,folder+'/')
            count=db.execute("SELECT COUNT(*) FROM media WHERE library_id=? AND substr(relpath,1,?)=?",params).fetchone()[0]
            rows=db.execute("SELECT * FROM media WHERE library_id=? AND substr(relpath,1,?)=? ORDER BY relpath LIMIT ?",(*params,limit)).fetchall()
        return [self._row(row) for row in rows],count
    def folder_match(self,library_id,relpath):
        with self.connect() as db:
            row=db.execute("SELECT * FROM folder_matches WHERE library_id=? AND substr(?,1,length(folder)+1)=folder||'/' ORDER BY length(folder) DESC LIMIT 1",(library_id,relpath)).fetchone()
        return dict(row) if row else None
    def match_folder(self,library_id,folder,title,year,ids):
        with self.connect() as db:
            rows=db.execute("SELECT id FROM media WHERE library_id=? AND substr(relpath,1,?)=?",(library_id,len(folder)+1,folder+'/')).fetchall()
            if not rows:return []
            db.execute("INSERT INTO folder_matches VALUES(?,?,?,?,?,?,?) ON CONFLICT(library_id,folder) DO UPDATE SET title=excluded.title,year=excluded.year,imdb_id=excluded.imdb_id,tmdb_id=excluded.tmdb_id,tvdb_id=excluded.tvdb_id",(library_id,folder,title,year,ids['imdb_id'],ids['tmdb_id'],ids['tvdb_id']))
            db.execute("UPDATE media SET match_status='matched',matched_title=?,matched_year=?,imdb_id=?,tmdb_id=?,tvdb_id=?,match_method='folder',confidence=1.0,updated_at=? WHERE library_id=? AND substr(relpath,1,?)=?",(title,year,ids['imdb_id'],ids['tmdb_id'],ids['tvdb_id'],int(time.time()),library_id,len(folder)+1,folder+'/'))
        return [row['id'] for row in rows]
    def _row(self,r):
        if not r: return None
        d=dict(r)
        if d.get('media_info'):
            try: d['media_info']=json.loads(d['media_info'])
            except Exception: pass
        return d
    def cache_get(self,keyword,max_age=7*86400):
        with self.connect() as db: r=db.execute("SELECT response_json,fetched_at FROM title_cache WHERE keyword=?",(keyword,)).fetchone()
        if not r or int(time.time())-r['fetched_at']>max_age: return None
        try: return json.loads(r['response_json'])
        except Exception: return None
    def cache_put(self,keyword,data):
        with self.connect() as db:
            db.execute("INSERT INTO title_cache(keyword,response_json,fetched_at) VALUES(?,?,?) ON CONFLICT(keyword) DO UPDATE SET response_json=excluded.response_json,fetched_at=excluded.fetched_at",(keyword,json.dumps(data,separators=(',',':')),int(time.time())))
