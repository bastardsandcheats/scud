# Zurg reference: /internal/rexfeed/feed.go (debouncing, bounded delivery and backoff).
"""Durable, debounced Rex delivery that never holds up filesystem scanning."""
from __future__ import annotations
import threading,time

SCHEMA='''CREATE TABLE IF NOT EXISTS publisher_jobs (
 key TEXT PRIMARY KEY, action TEXT NOT NULL, item_id TEXT NOT NULL, generation TEXT NOT NULL
)'''
FULL_KEY='publisher_full_pending'

class Publisher:
    def __init__(self,scanner):
        self.scanner=scanner;self.db=scanner.db;self.log=scanner.log
        self.wake=threading.Event();self.ready=threading.Event();self.running=False
        self.min_backoff=5;self.max_backoff=300;self.debounce=2
    def start(self):
        with self.db.connect() as db:db.execute(SCHEMA)
        self.db.state_set(FULL_KEY,str(time.time_ns()))
        self.running=True
        self.thread=threading.Thread(target=self.run,name='scud-publisher',daemon=True);self.thread.start()
    def enqueue(self,changed,gone,full=False):
        generation=str(time.time_ns())
        with self.db.connect() as db:
            db.execute(SCHEMA)
            jobs=[('item:'+str(ident),'item',str(ident),generation) for ident in changed]+[('delete:'+str(ident),'delete',str(ident),generation) for ident in gone]
            db.executemany('INSERT INTO publisher_jobs VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET generation=excluded.generation',jobs)
            if db.execute('SELECT COUNT(*) FROM publisher_jobs').fetchone()[0]>4096:
                db.execute('DELETE FROM publisher_jobs');full=True
            if full:db.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(FULL_KEY,generation))
        if changed or gone or full or self.scanner.snapshot_due:self.wake.set()
    def batch(self):
        with self.db.connect() as db:
            jobs=[dict(row) for row in db.execute('SELECT * FROM publisher_jobs ORDER BY generation,key LIMIT 500')]
            row=db.execute('SELECT value FROM state WHERE key=?',(FULL_KEY,)).fetchone();full=row[0] if row and row[0]!='0' else None
        return jobs,full
    def acknowledge(self,jobs,full):
        # Newer work queued during a network request must survive its acknowledgement.
        with self.db.connect() as db:
            db.executemany('DELETE FROM publisher_jobs WHERE key=? AND generation=?',[(row['key'],row['generation']) for row in jobs])
            if full:db.execute("UPDATE state SET value='0' WHERE key=? AND value=?",(FULL_KEY,full))
    def run(self):
        stop=self.scanner.stop_evt;backoff=0
        while not stop.is_set():
            if not self.ready.wait(.5):continue
            if not self.scanner.app.config.get('rex_url'):
                self.wake.wait(30);self.wake.clear();continue
            jobs,full=self.batch()
            last=float(self.db.state_get('last_snapshot','0') or 0)
            due=time.time()-last>=int(self.scanner.app.config.get('rex_snapshot_every_hours',6))*3600
            if not jobs and not full and not due and not self.scanner.snapshot_due:
                self.wake.wait(30);self.wake.clear();continue
            # Coalesce changes until quiet, with a five-second upper bound.
            deadline=time.monotonic()+5
            while not stop.is_set():
                self.wake.clear()
                if stop.wait(self.debounce):break
                if not self.wake.is_set() or time.monotonic()>=deadline:break
            if stop.is_set():break
            jobs,full=self.batch()
            changed=[row['item_id'] for row in jobs if row['action']=='item']
            gone=[row['item_id'] for row in jobs if row['action']=='delete']
            try:
                with self.scanner.sync_lock:
                    if full:self.scanner.snapshot_due=True
                    success=self.scanner._sync(changed,gone)
                if not success:raise RuntimeError(self.db.state_get('last_rex_error','Rex delivery failed'))
                self.acknowledge(jobs,full);backoff=0
                self.log.info('Rex delivery complete: %s changed files, %s removals',len(changed),len(gone))
            except Exception as error:
                self.scanner.snapshot_due=True
                backoff=min(self.max_backoff,max(self.min_backoff,backoff*2))
                self.log.warning('Rex delivery failed; retrying in %ss: %s',backoff,error)
                if stop.wait(backoff):break
        self.running=False
