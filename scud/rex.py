# Zurg reference: /internal/rexfeed/feed.go (source registration, batches and snapshot sessions).
from __future__ import annotations
import hashlib, json, socket, time, urllib.parse, requests

class RexError(RuntimeError): pass
class SnapshotSessionLost(RexError): pass

def legacy_shared_key(config,library_id):
    libraries=config.get('libraries',[])
    selected=next((library for library in libraries if library['id']==library_id),None)
    if not selected:return None
    def target(library):
        kind=library.get('type','movie')
        return kind,library.get('rex_library_name') or library.get('name') or ('Local TV' if kind=='show' else 'Local Movies')
    members=[library for library in libraries if target(library)==target(selected)]
    keys={str(library.get('rex_library_key') or '') for library in members}
    return next(iter(keys)) if len(members)>1 and len(keys)==1 and '' not in keys else None

def directory_plan(config):
    """Map local roots to native directories; roots with the same title share one."""
    groups={};routes={};directories=[]
    libraries=config.get('libraries',[]);ids={library['id'] for library in libraries}
    for library in libraries:
        kind='shows' if library.get('type')=='show' else 'movies'
        title=library.get('rex_library_name') or library.get('name') or ('Local TV' if kind=='shows' else 'Local Movies')
        groups.setdefault((kind,title),[]).append(library['id'])
    for (kind,title),members in groups.items():
        if legacy_shared_key(config,members[0]):
            # Older Scud deliberately put these roots in one existing section.
            # Keep that known destination without creating duplicate libraries.
            routes.update((member,member) for member in members)
            continue
        directory=members[0]
        if len(members)>1:
            directory='__scud_shared_'+hashlib.sha256((kind+'\0'+title).encode()).hexdigest()[:16]
            while directory in ids:directory+='_'  # never shadow a real local root
        directories.append({'name':directory,kind:title})
        routes.update((member,directory) for member in members)
    return directories,routes

def source_path(config,library_id,relpath):
    directory=directory_plan(config)[1].get(library_id,library_id)
    return directory+'/'+(library_id+'/' if directory!=library_id else '')+relpath

class RexClient:
    def __init__(self,config,log): self.config=config; self.log=log; self.session=requests.Session()
    @property
    def base(self): return str(self.config.get('rex_url') or '').rstrip('/')
    def headers(self):
        # Rex's native source/feed API uses private-network access, like Zurg.
        return {'Accept':'application/json'}
    def test(self):
        if not self.base: return {'ok':False,'error':'rex_url is empty'}
        try:
            r=self.session.get(self.base+'/rex/sources',headers=self.headers(),timeout=8)
            if not r.ok:
                return {'ok':False,'status':r.status_code,'error':
                        'Rex only accepts sources from private networks.' if r.status_code == 403
                        else f'Rex source API answered HTTP {r.status_code}. Check the Rex URL and port.'}
            data=r.json()
            if not isinstance(data,dict) or not isinstance(data.get('size'),int) or not isinstance(data.get('sources',[]),list):
                return {'ok':False,'error':'This URL did not return a Rex source listing. Check the Rex URL and port.'}
            return {'ok':True,'status':r.status_code}
        except Exception:
            return {'ok':False,'error':'Could not reach the Rex source API. Check the Rex URL and port.'}
    def source_url(self):
        explicit=str(self.config.get('source_url') or '').rstrip('/')
        if explicit: return explicit+'/files' if not explicit.endswith('/files') else explicit
        u=urllib.parse.urlsplit(self.base); host=u.hostname or '127.0.0.1'; port=u.port or (443 if u.scheme=='https' else 80)
        local='127.0.0.1'
        try:
            with socket.create_connection((host,port),timeout=5) as s: local=s.getsockname()[0]
        except Exception as e: self.log.warning('could not derive address Rex reaches Scud at: %s',e)
        if ':' in local: local=f'[{local}]'
        return f"http://{local}:{int(self.config.get('port',8788))}/files"
    def register_source(self):
        name=self.config.get('rex_source','scud'); body={'url':self.source_url(),'mount':'/scud'}
        body['directories']=directory_plan(self.config)[0]
        r=self.session.put(f"{self.base}/rex/sources/{urllib.parse.quote(str(name),safe='')}",json=body,headers=self.headers(),timeout=30)
        if not r.ok: raise RexError(f"source registration answered {r.status_code}: {r.text[:300]}")
        result=r.json() if r.content else {}
        if isinstance(result,dict) and result.get('ignored'):raise RexError('Rex ignored a library declaration. Check the library names and folder IDs.')
        return result
    def post_items(self,items):
        items=[item for item in items if item]
        if not items:return {}
        r=self.session.post(f"{self.base}/rex/feed/{self.config.get('rex_source','scud')}/items",json={'items':items},headers=self.headers(),timeout=600)
        if not r.ok: raise RexError(f"item push answered {r.status_code}: {r.text[:500]}")
        result=r.json() if r.content else {}
        if isinstance(result,dict) and result.get('rejected'):raise RexError(f"Rex rejected {len(result['rejected'])} files: {result['rejected'][0].get('reason','check the media details')}")
        return result
    def delete_ids(self,ids):
        if not ids:return {}
        r=self.session.delete(f"{self.base}/rex/feed/{self.config.get('rex_source','scud')}/items",json={'ids':ids},headers=self.headers(),timeout=600)
        if not r.ok: raise RexError(f"item delete answered {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}
    def snapshot(self,items,progress=None):
        for attempt in range(2):
            try:return self._snapshot_once(items,progress)
            except SnapshotSessionLost:
                if attempt:raise
                self.log.warning('Rex lost the snapshot session; restarting from part 0')
    def _snapshot_once(self,items,progress=None):
        self.register_source(); session=f"scud-{time.time_ns():x}"
        chunks=[items[i:i+200] for i in range(0,len(items),200)] or [[]]
        out=[]
        if progress:progress(0,len(items))
        for part,chunk in enumerate(chunks):
            body={'session':session,'part':part,'complete':part==len(chunks)-1,'items':chunk}
            r=self.session.put(f"{self.base}/rex/feed/{self.config.get('rex_source','scud')}/snapshot",json=body,headers=self.headers(),timeout=600)
            if not r.ok:
                # rex deliberately guards against snapshots that would remove > half.
                if r.status_code==409:
                    try:
                        j=r.json()
                        if 'no such snapshot session' in str(j.get('error','')).lower():raise SnapshotSessionLost('Rex lost the snapshot session.')
                        if 'would_remove' in j: raise RexError(f"Rex shrink guard refused snapshot: would remove {j.get('would_remove')} of {j.get('of')}")
                    except ValueError: pass
                raise RexError(f"snapshot part {part} answered {r.status_code}: {r.text[:500]}")
            result=r.json() if r.content else {}
            if isinstance(result,dict) and result.get('rejected'):raise RexError(f"Rex rejected {len(result['rejected'])} files in this batch.")
            out.append(result)
            if progress:progress(min((part+1)*200,len(items)),len(items))
        return out
