from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
import json, logging, mimetypes, os, re, threading
from .config import public_config, save_config, load_config, slugify
from .rex import RexClient
from .probe import test_media_tools
from .matcher import Matcher, guess_file, guess_name
from .extras import extra_type
from .tmdb import TMDBClient, TMDBError

class WebServer:
    def __init__(self,app): self.app=app; self.httpd=None
    def serve(self):
        app=self.app
        class Handler(BaseHTTPRequestHandler):
            server_version='Scud/0.1'
            def log_message(self,fmt,*args): app.log.debug('http %s - '+fmt,self.client_address[0],*args)
            def json_body(self):
                n=int(self.headers.get('Content-Length','0') or 0); raw=self.rfile.read(n) if n else b'{}'
                return json.loads(raw or b'{}')
            def send_json(self,obj,status=200):
                raw=json.dumps(obj,separators=(',',':'),default=str).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def send_asset(self,path:Path,head=False):
                if not path.is_file(): return self.send_error(404)
                data=path.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream'); self.send_header('Cache-Control','public,max-age=3600'); self.send_header('Content-Length',str(len(data))); self.end_headers();
                if not head:self.wfile.write(data)
            def do_HEAD(self): self.route(head=True)
            def do_GET(self): self.route()
            def do_POST(self): self.route()
            def do_PUT(self): self.route()
            def do_DELETE(self): self.route()
            def route(self,head=False):
                u=urlsplit(self.path); path=unquote(u.path); q=parse_qs(u.query)
                try:
                    if path.startswith('/files/'): return self.serve_media(path[len('/files/'):],head)
                    if path=='/api/configured': return self.send_json({'configured':bool(app.config.get('rex_url') and app.config.get('libraries'))})
                    if path=='/api/config' and self.command=='GET': return self.send_json(public_config(app.config))
                    if path=='/api/status' and self.command=='GET':
                        return self.send_json({'summary':app.db.count_summary(),'compatibility':app.compat.status,'scanner':app.scanner.scan_status(),'sending':dict(app.scanner.send_progress),'receipts':app.scanner.receipts.summary(),'last_scan':app.db.state_get('last_scan'),'last_scan_seconds':app.db.state_get('last_scan_seconds'),'last_snapshot':app.db.state_get('last_snapshot'),'rex_error':app.db.state_get('last_rex_error',''),'rex':RexClient(app.config,app.log).test() if app.config.get('rex_url') else {'ok':False}})
                    if path=='/api/items' and self.command=='GET':
                        listing=app.db.list_folder_media if (q.get('view') or [''])[0]=='folders' else app.db.list_media
                        rows=listing((q.get('kind') or [''])[0],(q.get('status') or [''])[0],(q.get('q') or [''])[0],int((q.get('limit') or [500])[0]),int((q.get('offset') or [0])[0]))
                        for r in rows:
                            r.pop('media_info',None)
                            r['rex_state']=app.scanner.receipts.state(r)
                            r['extra_type']=extra_type(r)
                            r['rex_current_library']=app.scanner.receipts.library_names.get(app.scanner.receipts.locations.get(app.scanner.feed_id(r)))
                            lib=next((lib for lib in app.config.get('libraries',[]) if lib['id']==r['library_id']),{})
                            r['rex_library']=lib.get('rex_library_name') or lib.get('name') or 'Rex library'
                        return self.send_json({'items':rows})
                    if path=='/api/compatibility' and self.command=='GET':return self.send_json(app.compat.status)
                    if path=='/api/rescan' and self.command=='POST': app.scanner.trigger(); return self.send_json({'ok':True})
                    if path=='/api/snapshot' and self.command=='POST':
                        threading.Thread(target=self._snapshot,daemon=True).start(); return self.send_json({'ok':True})
                    if path=='/api/rex/test' and self.command=='POST':
                        body=self.json_body(); cfg=dict(app.config); cfg['rex_url']=body.get('rex_url',cfg.get('rex_url')); return self.send_json(RexClient(cfg,app.log).test())
                    if path=='/api/tmdb/test' and self.command=='POST':
                        body=self.json_body(); key=body.get('tmdb_api_key')
                        if not key or key=='********': key=app.config.get('tmdb_api_key','')
                        return self.send_json(TMDBClient(key).test())
                    if path=='/api/ffmpeg/test' and self.command=='POST':
                        body=self.json_body()
                        return self.send_json(test_media_tools(body.get('ffmpeg_path',app.config.get('ffmpeg_path',''))))
                    if path=='/api/episodes/context' and self.command=='POST': return self.episode_context(self.json_body())
                    if path=='/api/episodes/metadata' and self.command=='POST': return self.episode_metadata(self.json_body())
                    if path=='/api/matches/suggestions' and self.command=='POST': return self.match_suggestions(self.json_body())
                    if path=='/api/folders/match' and self.command=='POST': return self.folder_match(self.json_body())
                    if path=='/api/setup' and self.command=='POST': return self.handle_setup(self.json_body())
                    if path=='/api/settings' and self.command=='POST': return self.handle_setup(self.json_body(),settings=True)
                    m=re.fullmatch(r'/api/items/([^/]+)/match',path)
                    if m and self.command=='POST': return self.manual_match(m.group(1),self.json_body())
                    m=re.fullmatch(r'/api/items/([^/]+)/reprobe',path)
                    if m and self.command=='POST': app.scanner.trigger(); return self.send_json({'ok':True})
                    if path.startswith('/static/'):
                        static_root=(app.root/'scud/static').resolve()
                        asset=(static_root/path[len('/static/'):]).resolve()
                        try: asset.relative_to(static_root)
                        except ValueError: return self.send_error(403)
                        return self.send_asset(asset,head)
                    if path=='/favicon.ico': return self.send_asset(app.root/'scud/static/favicon.ico',head)
                    if path in ('/','/setup','/settings'): return self.send_asset(app.root/'scud/static/index.html',head)
                    return self.send_error(404)
                except (BrokenPipeError,ConnectionResetError):return
                except Exception as e:
                    app.log.exception('request failed: %s %s',self.command,path); return self.send_json({'ok':False,'error':str(e)},500)
            def _snapshot(self):
                try: app.scanner.force_snapshot(); app.db.state_set('last_rex_error','')
                except Exception as e: app.db.state_set('last_rex_error',str(e)); app.log.exception('forced snapshot failed')
            def handle_setup(self,body,settings=False):
                cfg=dict(app.config)
                for k in ('host','port','source_url','rex_url','rex_source','rex_snapshot_every_hours','poll_every_secs','ffmpeg_path','log_level','allow_rex_delete'):
                    if k in body: cfg[k]=body[k]
                key=str(body.get('tmdb_api_key') or '').strip()
                key_changed=bool(key and key!='********' and key!=app.config.get('tmdb_api_key'))
                if key and key!='********':cfg['tmdb_api_key']=key
                libs=[]
                seen_ids=set()
                for i,x in enumerate(body.get('libraries',cfg.get('libraries',[]))):
                    if not str(x.get('path') or '').strip():return self.send_json({'error':'Enter a folder path for every library.'},400)
                    ident=slugify(str(x.get('id') or f'library-{i+1}'))
                    if ident in seen_ids:return self.send_json({'error':'Each library must have a unique ID.'},400)
                    seen_ids.add(ident)
                    p=os.path.abspath(os.path.expanduser(str(x.get('path') or ''))); typ='show' if x.get('type') in ('show','tv') else 'movie'; name=str(x.get('name') or ('Local TV' if typ=='show' else 'Local Movies'))
                    libs.append({'id':slugify(str(x.get('id') or f"{'tv' if typ=='show' else 'movies'}-{i+1}")),'type':typ,'name':name,'path':p,'rex_library_name':str(x.get('rex_library_name') or name),'rex_library_key':str(x.get('rex_library_key') or '')})
                cfg['libraries']=libs
                cfg=load_config_from_dict(cfg)
                # Save locally even when Rex is busy or offline. The durable
                # publisher creates libraries/registers the source and retries.
                needs_sync=any(cfg.get(key)!=app.config.get(key) for key in ('libraries','rex_url','rex_source','source_url'))
                old_ids={lib['id'] for lib in app.config.get('libraries',[])}
                removed=old_ids-{lib['id'] for lib in cfg['libraries']}
                gone=[app.scanner.feed_id(row) for row in app.db.list_media(limit=200000) if row['library_id'] in removed]
                save_config(app.config_path,cfg); app.reload_config()
                if removed:
                    with app.db.connect() as conn:
                        conn.executemany('DELETE FROM media WHERE library_id=?',[(ident,) for ident in removed])
                        conn.executemany('DELETE FROM folder_matches WHERE library_id=?',[(ident,) for ident in removed])
                if needs_sync or gone:app.scanner.publisher.enqueue([],gone,full=True)
                threading.Thread(target=app.compat.run,name='scud-connection-check',daemon=True).start()
                if key_changed:
                    with app.db.connect() as db:db.execute("UPDATE media SET match_method='tmdb-key-updated' WHERE match_status='error' AND match_method='folder-filename-tmdb-v1'")
                app.scanner.trigger()
                return self.send_json({'ok':True,'config':public_config(app.config)})
            def episode_context(self,body):
                row=app.db.get_media(str(body.get('item_id') or ''))
                if not row or row['kind']!='show':return self.send_json({'error':'Choose an episode file.'},400)
                try:
                    context=TMDBClient(app.config.get('tmdb_api_key'),app.db).episode_context(row,body.get('show_id'),body.get('season'))
                    return self.send_json(context)
                except (TMDBError,ValueError,TypeError) as exc:return self.send_json({'error':str(exc)},400)
            def episode_metadata(self,body):
                items={};client=TMDBClient(app.config.get('tmdb_api_key'),app.db)
                for ident in list(dict.fromkeys(body.get('items') or []))[:100]:
                    row=app.db.get_media(str(ident))
                    if not row or row['kind']!='show':continue
                    try:
                        context=client.episode_context(row)
                        episode=next((part for part in context['episodes'] if part['number']==row.get('episode')),None)
                        items[str(ident)]={'episode_title':episode['title'] if episode else None,'season':context['season'],'episode':row.get('episode'),'episode_end':row.get('episode_end'),'title':context['title'],'year':context['year'],'poster':context['poster']}
                    except (TMDBError,ValueError,TypeError):items[str(ident)]=None
                return self.send_json({'items':items})
            def match_suggestions(self,body):
                if body.get('item_id'):
                    row=app.db.get_media(str(body['item_id']))
                    if not row:return self.send_json({'error':'File not found.'},404)
                    rows=[row];count=1;library_id=row['library_id']
                else:
                    library_id=str(body.get('library_id') or '');folder=str(body.get('folder') or '')
                    if not folder:return self.send_json({'error':'Choose a folder.'},400)
                    rows,count=app.db.folder_items(library_id,folder)
                    if not rows:return self.send_json({'error':'No files found in this folder.'},404)
                library=next((lib for lib in app.config.get('libraries',[]) if lib['id']==library_id),None)
                if not library:return self.send_json({'error':'Library not found.'},404)
                kind='show' if library.get('type')=='show' else 'movie'
                guesses=[];seen=set()
                sources=[(guess_file(library,rows[0]['relpath']),'Folder')]
                sources.extend((guess_name(Path(row['relpath']).name,kind),'Filename') for row in rows[:10])
                if str(body.get('query') or '').strip():sources=[(guess_name(str(body['query'])[:200],kind),'Search')]
                for guess,source in sources:
                    key=(guess.title.lower(),guess.year)
                    if key not in seen:guesses.append((guess,source));seen.add(key)
                suggestions,errors=Matcher(app.db,app.log,app.config).suggestions(guesses) if body.get('search') else ([],[])
                return self.send_json({'files':[row['relpath'] for row in rows],'total_files':count,'parsed':[{'title':g.title,'year':g.year,'source':source} for g,source in guesses[:4]],'suggestions':suggestions,'errors':errors,'kind':kind,'has_match':bool(rows[0].get('match_status')=='matched' and any(rows[0].get(key) for key in ('tmdb_id','imdb_id','tvdb_id'))),'item_id':rows[0]['id'] if body.get('item_id') else None,'season':rows[0].get('season'),'episode':rows[0].get('episode')})
            def folder_match(self,body):
                library_id=str(body.get('library_id') or '')
                folder=str(body.get('folder') or '')
                if not folder or folder.startswith('/') or any(part in ('','.', '..') for part in folder.split('/')):
                    return self.send_json({'error':'Choose a media folder.'},400)
                if not any(lib['id']==library_id for lib in app.config.get('libraries',[])):
                    return self.send_json({'error':'Library not found.'},404)
                raw=str(body.get('id') or '').strip().lower()
                ids={'imdb_id':None,'tmdb_id':None,'tvdb_id':None}
                if re.fullmatch(r'tt[0-9]+',raw): ids['imdb_id']=raw
                elif re.fullmatch(r'tmdb://[0-9]+',raw): ids['tmdb_id']=raw[7:]
                elif re.fullmatch(r'tvdb://[0-9]+',raw): ids['tvdb_id']=raw[7:]
                elif raw.isdigit(): ids['tmdb_id']=raw
                else: return self.send_json({'error':'Use an IMDb, TMDB, or TVDB ID.'},400)
                try: year=int(body['year']) if body.get('year') else None
                except (ValueError,TypeError): return self.send_json({'error':'Enter a valid year.'},400)
                updated=app.db.match_folder(library_id,folder,str(body.get('title') or folder.split('/')[-1]),year,ids)
                if not updated:return self.send_json({'error':'No files found in this folder.'},404)
                def push():app.scanner.sync(updated,[])
                threading.Thread(target=push,daemon=True).start()
                return self.send_json({'ok':True,'updated':len(updated)})
            def manual_match(self,item_id,body):
                row=app.db.get_media(item_id)
                if not row:return self.send_json({'error':'not found'},404)
                raw=str(body.get('id') or '').strip().lower(); ids={'imdb_id':None,'tmdb_id':None,'tvdb_id':None}
                if re.fullmatch(r'tt[0-9]+',raw): ids['imdb_id']=raw
                elif re.fullmatch(r'tmdb://[0-9]+',raw): ids['tmdb_id']=raw[7:]
                elif re.fullmatch(r'tvdb://[0-9]+',raw): ids['tvdb_id']=raw[7:]
                elif raw.isdigit(): ids['tmdb_id']=raw
                else:return self.send_json({'error':'Use tt1234567, tmdb://123, tvdb://123, or a numeric TMDB ID'},400)
                numbering=None
                if row['kind']=='show' and ('season' in body or 'episode' in body):
                    try:
                        season=int(body['season']);episode=int(body['episode']);end=int(body['episode_end']) if body.get('episode_end') else None
                        if season<0 or episode<1 or (end is not None and end<episode):raise ValueError
                        selected=dict(row);selected.update(ids)
                        context=TMDBClient(app.config.get('tmdb_api_key'),app.db).episode_context(selected,season=season)
                        available={part['number'] for part in context['episodes']}
                        if episode not in available or (end is not None and end not in available):raise ValueError
                        numbering=(season,episode,end)
                    except (TMDBError,ValueError,TypeError,KeyError):return self.send_json({'error':'Choose a valid show, season and episode from TMDB.'},400)
                with app.db.connect() as db:
                    db.execute("UPDATE media SET match_status='matched',matched_title=?,matched_year=?,imdb_id=?,tmdb_id=?,tvdb_id=?,match_method='manual',confidence=1.0 WHERE id=?",(body.get('title') or row.get('title_guess'),body.get('year') or row.get('year_guess'),ids['imdb_id'],ids['tmdb_id'],ids['tvdb_id'],item_id))
                if numbering:
                    with app.db.connect() as db:db.execute('UPDATE media SET season=?,episode=?,episode_end=?,numbering_manual=1 WHERE id=?',(*numbering,item_id))
                try: app.scanner.sync([item_id],[])
                except Exception as e: app.db.state_set('last_rex_error',str(e))
                return self.send_json({'ok':True})
            def serve_media(self,virtual,head=False):
                if self.command=='DELETE' and not app.config.get('allow_rex_delete',False):return self.send_json({'error':'Deleting local files through Rex is disabled. Remove files on the Scud server instead.'},403)
                if self.command not in ('GET','HEAD','DELETE'):return self.send_error(405)
                parts=virtual.split('/',1)
                if len(parts)!=2:return self.send_error(404)
                lib=next((x for x in app.config.get('libraries',[]) if x['id']==parts[0]),None)
                if not lib:return self.send_error(404)
                root=Path(lib['path']).resolve(); target=(root/parts[1]).resolve()
                try: target.relative_to(root)
                except ValueError:return self.send_error(403)
                if not target.is_file():return self.send_error(404)
                if self.command=='DELETE':
                    with app.db.connect() as conn:
                        record=conn.execute('SELECT * FROM media WHERE library_id=? AND relpath=?',(lib['id'],parts[1])).fetchone()
                    if not record:return self.send_error(404)
                    row=app.db._row(record)
                    if not app.scanner.publishable(row):return self.send_error(403)
                    feed_id=app.scanner.feed_id(row)
                    (root/parts[1]).unlink()
                    with app.db.connect() as conn:conn.execute('DELETE FROM media WHERE id=?',(row['id'],))
                    app.log.info('Deleted local media requested by Rex: %s/%s',lib['id'],parts[1])
                    app.scanner.sync([],[feed_id]);app.scanner.trigger()
                    self.send_response(204);self.send_header('Content-Length','0');self.end_headers();return
                size=target.stat().st_size; start,end=0,size-1; status=200
                rng=self.headers.get('Range','')
                if rng.startswith('bytes='):
                    spec=rng[6:].split(',',1)[0].strip(); a,b=(spec.split('-',1)+[''])[:2]
                    if a: start=int(a); end=int(b) if b else size-1
                    elif b: start=max(0,size-int(b)); end=size-1
                    if start>=size or end<start:return self.send_error(416)
                    end=min(end,size-1); status=206
                self.send_response(status); self.send_header('Content-Type','application/octet-stream'); self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(end-start+1))
                if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                if head:return
                with target.open('rb') as f:
                    f.seek(start); remain=end-start+1
                    while remain:
                        buf=f.read(min(1024*1024,remain))
                        if not buf:break
                        self.wfile.write(buf); remain-=len(buf)
        self.httpd=ThreadingHTTPServer((self.app.config.get('host','0.0.0.0'),int(self.app.config.get('port',8788))),Handler)
        self.app.log.info('Scud UI listening on http://%s:%s',self.app.config.get('host','0.0.0.0'),self.app.config.get('port',8788)); self.httpd.serve_forever()

def load_config_from_dict(cfg):
    # Normalize through the same rules without an on-disk round trip.
    from .config import DEFAULT_CONFIG,slugify
    out=dict(DEFAULT_CONFIG); out.update(cfg); out['port']=int(out.get('port',8788)); out['poll_every_secs']=max(5,int(out.get('poll_every_secs',60))); out['rex_snapshot_every_hours']=max(1,int(out.get('rex_snapshot_every_hours',6)))
    out['log_level']=str(out.get('log_level','INFO')).upper()
    if out['log_level'] not in ('DEBUG','INFO','WARNING','ERROR','CRITICAL'):raise ValueError('Choose a valid log level.')
    if not isinstance(out.get('allow_rex_delete'),bool):raise ValueError('allow_rex_delete must be true or false.')
    return out
