from __future__ import annotations
import requests,json

BASE_URL='https://api.themoviedb.org/3'
class TMDBError(RuntimeError): pass

class TMDBClient:
    def __init__(self,key,db=None):
        self.key=str(key or '').strip();self.db=db
        self.session=requests.Session()
    def get(self,path,params=None):
        if not self.key:raise TMDBError('Add your TMDB API key in Settings to search for titles.')
        cache_key='tmdb-details-v1:'+path+':'+json.dumps(params or {},sort_keys=True)
        if self.db is not None and path!='/configuration':
            cached=self.db.cache_get(cache_key,max_age=86400)
            if cached is not None:return cached
        params=dict(params or {});headers={'Accept':'application/json'}
        if len(self.key)==32 and all(c in '0123456789abcdefABCDEF' for c in self.key):params['api_key']=self.key
        else:headers['Authorization']='Bearer '+self.key
        try:response=self.session.get(BASE_URL+path,params=params,headers=headers,timeout=(4,12))
        except requests.RequestException:raise TMDBError('Could not reach TMDB. Try again shortly.') from None
        if response.status_code in (401,403):raise TMDBError('TMDB rejected the API key. Check it in Settings.')
        if response.status_code==429:raise TMDBError('TMDB is busy. Wait a moment and try again.')
        if not response.ok:raise TMDBError(f'TMDB search failed (HTTP {response.status_code}).')
        try:
            data=response.json()
            if self.db is not None and path!='/configuration':self.db.cache_put(cache_key,data)
            return data
        except ValueError:raise TMDBError('TMDB returned an unreadable response.') from None
    def test(self):
        try:self.get('/configuration');return {'ok':True}
        except TMDBError as exc:return {'ok':False,'error':str(exc)}
    def search(self,title,kind):
        data=self.get('/search/tv' if kind=='show' else '/search/movie',{'query':title,'language':'en-US','include_adult':'false','page':1})
        results=[]
        for row in data.get('results',[]):
            ident=row.get('id');name=row.get('name') if kind=='show' else row.get('title')
            if not ident or not name:continue
            date=str(row.get('first_air_date' if kind=='show' else 'release_date') or '')
            results.append({'tmdb_id':str(ident),'title':name,'searchTitle':name,'originalTitle':row.get('original_name' if kind=='show' else 'original_title'),'year':int(date[:4]) if date[:4].isdigit() else None,'type':kind,'poster':poster_url(row.get('poster_path'))})
        return {'results':results}

    def media_id(self,row):
        if str(row.get('tmdb_id') or '').isdigit():return str(row['tmdb_id'])
        kind='show' if row.get('kind')=='show' else 'movie'
        for field,source in (('imdb_id','imdb_id'),('tvdb_id','tvdb_id')):
            if row.get(field):
                data=self.get('/find/'+str(row[field]),{'external_source':source})
                found=data.get('tv_results' if kind=='show' else 'movie_results',[])
                if found:return str(found[0]['id'])
        raise TMDBError('Choose a TMDB show before selecting an episode.')
    def episode_context(self,row,show_id=None,season=None):
        ident=str(show_id or self.media_id(row)).removeprefix('tmdb://')
        if not ident.isdigit():raise TMDBError('Choose a valid TMDB show.')
        show=self.get('/tv/'+ident,{'language':'en-US'})
        seasons=[{'number':part['season_number'],'name':part.get('name') or 'Season '+str(part['season_number'])} for part in show.get('seasons',[])]
        number=int(season if season is not None else row['season'] if row.get('season') is not None else next((part['number'] for part in seasons if part['number']>0),0))
        episodes=self.get(f'/tv/{ident}/season/{number}',{'language':'en-US'}).get('episodes',[]) if any(part['number']==number for part in seasons) else []
        return {'show_id':ident,'title':show.get('name'),'year':int(show['first_air_date'][:4]) if str(show.get('first_air_date') or '')[:4].isdigit() else None,'poster':poster_url(show.get('poster_path')),'seasons':seasons,'season':number,'episode':row.get('episode'),'episode_end':row.get('episode_end'),'episodes':[{'number':episode['episode_number'],'title':episode.get('name') or '', 'id':episode.get('id'),'air_date':episode.get('air_date')} for episode in episodes]}

def poster_url(path):
    return 'https://image.tmdb.org/t/p/w185'+path if isinstance(path,str) and path.startswith('/') else None
