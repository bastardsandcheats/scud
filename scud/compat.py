"""Live API contract checks using an isolated, empty Rex source."""
from __future__ import annotations
import argparse,json,re,time,uuid
from pathlib import Path
from .rex import RexClient,RexError
from .tmdb import TMDBClient

BASELINE=Path(__file__).with_name('rex_compatibility.json')

def baseline():
    try:return json.loads(BASELINE.read_text())
    except (OSError,ValueError):return {}

class Compatibility:
    def __init__(self,app):
        self.app=app;self.status={'state':'pending','checks':[],'tested':baseline()}
    def run(self):
        checks=[];self.status={**self.status,'state':'checking'}
        def check(name,callback):
            try:callback();checks.append({'name':name,'ok':True})
            except Exception as error:
                checks.append({'name':name,'ok':False,'error':str(error)})
                self.app.log.error('API compatibility check failed [%s]: %s',name,error)
        cfg=self.app.config
        if cfg.get('rex_url'):check('Rex source/feed contract',self.rex_contract)
        else:checks.append({'name':'Rex','ok':None,'error':'Configure Rex to run this check.'})
        if cfg.get('tmdb_api_key'):check('TMDB search and metadata contract',self.tmdb_contract)
        else:checks.append({'name':'TMDB','ok':None,'error':'Add a TMDB API key to run this check.'})
        state='failed' if any(item['ok'] is False for item in checks) else 'passed' if all(item['ok'] is True for item in checks) else 'unconfigured'
        self.status={'state':state,'checks':checks,'checked':time.time(),'tested':baseline()}
        if state=='passed':self.app.log.info('Rex and TMDB API compatibility checks passed')
        return self.status
    def rex_contract(self):
        rex=RexClient(self.app.config,self.app.log)
        def request(method,path,body=None):
            try:response=rex.session.request(method,rex.base+path,json=body,headers=rex.headers(),timeout=(4,25))
            except Exception:raise RexError('Rex could not be reached during the compatibility check.') from None
            if not response.ok:raise RexError(f'{method} {path} answered HTTP {response.status_code}.')
            try:return response.json()
            except ValueError:raise RexError(f'{method} {path} did not return JSON.') from None
        def require(condition,message):
            if not condition:raise RexError(message)
        sources=request('GET','/rex/sources')
        require(isinstance(sources,dict) and isinstance(sources.get('size'),int) and isinstance(sources.get('sources',[]),list),'Rex source listing schema changed.')
        sections=request('GET','/library/sections').get('MediaContainer',{})
        require(isinstance(sections,dict) and isinstance(sections.get('Directory',[]),list),'Rex library listing schema changed.')
        source='scud-compat-'+uuid.uuid4().hex[:12];source_path='/rex/sources/'+source;feed='/rex/feed/'+source;registered=False
        try:
            request('PUT',source_path,{'url':rex.source_url(),'mount':'/scud-compat'});registered=True
            for leaf in ('items','held'):
                listing=request('GET',feed+'/'+leaf)
                require(isinstance(listing,dict) and isinstance(listing.get('size'),int) and isinstance(listing.get('held' if leaf=='held' else 'items',[]),list),f'Rex {leaf} listing schema changed.')
            result=request('POST',feed+'/items',{'items':[]})
            require(isinstance(result,dict) and all(isinstance(result.get(key),int) for key in ('created','updated','held','unchanged')),'Rex item acknowledgement schema changed.')
            library=next((row for row in sections.get('Directory',[]) if row.get('type') in ('show','movie')),None)
            if library:
                item={'id':'contract-held','path':'__compat__/contract-video.mkv','library':str(library['key']),'kind':'episode' if library['type']=='show' else 'movie','ids':{'tmdb':2430 if library['type']=='show' else 603},'season':9,'episode':1,'size':1,'media_info':None}
                result=request('POST',feed+'/items',{'items':[item]})
                require(result.get('held')==1,'Rex no longer accepts an unprobed media item as held.')
                listing=request('GET',feed+'/held')
                require(any(row.get('id')=='contract-held' for row in listing.get('held',[])),'Rex held-item listing schema changed.')
                result=request('DELETE',feed+'/items',{'ids':['contract-held']})
                require(result.get('released')==1,'Rex held-item removal schema changed.')
            result=request('DELETE',feed+'/items',{'ids':[]})
            require(isinstance(result,dict) and all(isinstance(result.get(key),int) for key in ('trashed','deleted','released','unknown')),'Rex delete acknowledgement schema changed.')
            result=request('PUT',feed+'/snapshot',{'session':uuid.uuid4().hex,'part':0,'complete':True,'items':[]})
            require(isinstance(result,dict) and not result.get('error'),'Rex snapshot acknowledgement schema changed.')
        finally:
            if registered:
                confirmation=request('DELETE',source_path)
                path=confirmation.get('confirm','')
                require(isinstance(path,str) and path.startswith(source_path+'/confirm/') and re.fullmatch(r'[a-f0-9]+',path.rsplit('/',1)[-1]) is not None,'Rex source cleanup confirmation schema changed.')
                result=request('DELETE',path)
                require(result.get('deleted') is True,'Rex did not clean up its empty compatibility source.')
    def tmdb_contract(self):
        client=TMDBClient(self.app.config['tmdb_api_key'])
        config=client.get('/configuration')
        if not isinstance(config,dict) or not isinstance(config.get('images',{}).get('poster_sizes'),list):raise RuntimeError('TMDB configuration schema changed.')
        for path,title,field in [('/search/movie','The Matrix','title'),('/search/tv','Doc Martin','name')]:
            result=client.get(path,{'query':title,'language':'en-US','page':1})
            rows=result.get('results') if isinstance(result,dict) else None
            if not isinstance(rows,list) or not rows or not all(isinstance(row.get('id'),int) and isinstance(row.get(field),str) for row in rows):raise RuntimeError('TMDB search result schema changed.')
        season=client.get('/tv/2430/season/9',{'language':'en-US'})
        if not isinstance(season,dict) or not isinstance(season.get('episodes'),list) or not all(isinstance(row.get('episode_number'),int) and isinstance(row.get('name'),str) for row in season['episodes']):raise RuntimeError('TMDB episode metadata schema changed.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');parser.add_argument('--config',default='config.yml');parser.add_argument('--revision-file',default='/opt/Rex/config/installed-revision');args=parser.parse_args()
    revision=None
    if args.record:
        revision=Path(args.revision_file).read_text().strip()
        if not re.fullmatch(r'[0-9a-f]{40}',revision):raise SystemExit('The Rex installation does not expose a full commit in its revision marker.')
    import logging
    from types import SimpleNamespace
    from .config import load_config
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    app=SimpleNamespace(root=Path(__file__).resolve().parents[1],config=load_config(Path(args.config).resolve()),log=logging.getLogger('scud.compat'))
    result=Compatibility(app).run()
    for check in result['checks']:print(('PASS' if check['ok'] else 'FAIL')+' '+check['name']+(': '+check['error'] if check.get('error') else ''))
    if result['state']!='passed':raise SystemExit(1)
    if args.record:
        if Path(args.revision_file).read_text().strip()!=revision:raise SystemExit('Rex changed revision during the compatibility check; rerun the check.')
        data={'rex_commit':revision,'tested_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':[row['name'] for row in result['checks']]}
        BASELINE.write_text(json.dumps(data,indent=2)+'\n')
        readme=app.root/'README.md';text=readme.read_text();note=f'<!-- rex-compat-start -->\nLast live API compatibility test: Rex commit `{revision}` ({data["tested_at"]}).\n<!-- rex-compat-end -->'
        if '<!-- rex-compat-start -->' in text:text=re.sub(r'<!-- rex-compat-start -->.*?<!-- rex-compat-end -->',lambda _:note,text,flags=re.S)
        else:text+='\n'+note+'\n'
        readme.write_text(text);print('Recorded tested Rex commit '+revision)

if __name__=='__main__':main()
