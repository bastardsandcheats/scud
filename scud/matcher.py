# Zurg references: /internal/releasename/releasename.go and /internal/releasename/numbering.go; TMDB supplies local title matches.
from __future__ import annotations
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from pathlib import Path
from . import zurg_compat as zc
from .tmdb import TMDBClient, TMDBError

EXPLICIT_RE=re.compile(r"(?i)(tt\d{5,10}|(?:tmdb|tvdb)[:=_\-/ ]{1,3}(\d{1,10}))")

@dataclass
class Guess:
    title:str
    year:int|None
    kind:str
    season:int|None=None
    episode:int|None=None
    episode_end:int|None=None
    explicit_type:str|None=None
    explicit_id:str|None=None
    parsed:zc.ParsedName|None=None

def fold(s:str)->str:return zc.bare_title(s)

def explicit_id(name:str):
    m=EXPLICIT_RE.search(name)
    if not m:return None,None
    token=m.group(1).lower()
    if token.startswith('tt'):return 'imdb',token
    kind='tmdb' if token.startswith('tmdb') else 'tvdb'
    return kind,m.group(2)

def episode_numbers(name:str):
    eps=zc.episodes_in(name)
    if len(eps)!=1:return None,None,None
    season,items=next(iter(eps.items()))
    if not items:return None,None,None
    return season,items[0],items[-1] if items[-1]>items[0] else None

def guess_file(library:dict,relpath:str)->Guess:
    p=Path(relpath);kind='show' if library.get('type')=='show' else 'movie'; ex_type,ex_id=explicit_id(relpath)
    if kind=='show':
        parts=p.parts; series_source=parts[0] if len(parts)>1 else p.stem
        parsed=zc.absolute_episode(zc.parse_name(series_source))
        # The configured TV root supplies the show-kind marker that a Zurg release
        # normally carries in SxxEyy/Season syntax. File numbering still comes from
        # Zurg-compatible EpisodesIn.
        parsed.show=True
        s,e,end=episode_numbers(p.name)
        if s is None:s,e,end=episode_numbers(relpath)
        if s is None:
            # Local season directories supply context absent from a bare '02 - Title'.
            season=next((re.fullmatch(r'(?i)(?:season[ ._-]*|s)(\d{1,2})',part) for part in reversed(p.parts[:-1]) if re.fullmatch(r'(?i)(?:season[ ._-]*|s)(\d{1,2})',part)),None)
            number=re.match(r'(?i)^(?:episode[ ._-]*)?(\d{1,3})(?:[ ._]*[-~][ ._]*(\d{1,3}))?(?:[ ._-]+|$)',p.stem)
            if season and number and int(number[1])>0:
                s,e=int(season[1]),int(number[1]);end=int(number[2]) if number[2] and int(number[2])>e else None
        title=parsed.title_display or series_source
        return Guess(title,parsed.year or None,'show',s,e,end,ex_type,ex_id,parsed)
    source=p.parent.name if p.parent.name not in ('','.') else p.name
    parsed=zc.absolute_episode(zc.parse_name(source))
    parsed.show=False
    title=parsed.title_display or p.stem
    return Guess(title,parsed.year or None,'movie',explicit_type=ex_type,explicit_id=ex_id,parsed=parsed)

def guess_name(name:str,kind:str)->Guess:
    parsed=zc.absolute_episode(zc.parse_name(name))
    parsed.show=kind=='show'
    ex_type,ex_id=explicit_id(name)
    return Guess(parsed.title_display or Path(name).stem,parsed.year or None,kind,explicit_type=ex_type,explicit_id=ex_id,parsed=parsed)


class Matcher:
    def __init__(self,db,log,config=None):self.db=db;self.log=log;self.config=config or {}
    def keyword(self,g:Guess):
        p=g.parsed or zc.parse_name(g.title)
        p.show=(g.kind=='show');p.year=g.year or 0
        # Local roots already establish a trustworthy kind, so permit a TV title
        # folder with no year/quality (e.g. "24") to be searched as a show.
        if p.title:return f"{p.title} {g.kind}"
        return zc.title_search_keyword(p)
    def search(self,keyword:str,timeout=30):
        title,_,kind=keyword.rpartition(' ')
        if kind not in ('movie','show'):raise TMDBError('Choose a movie or TV library.')
        if not self.config.get('tmdb_api_key'):raise TMDBError('Add your TMDB API key in Settings to search for titles.')
        cache_key='tmdb-search-v2:'+keyword
        cached=self.db.cache_get(cache_key)
        if cached is not None:return cached
        data=TMDBClient(self.config['tmdb_api_key']).search(title,kind)
        self.db.cache_put(cache_key,data)
        return data
    def match(self,g:Guess):
        if g.explicit_id:
            return {'status':'matched','title':g.title,'year':g.year,'ids':{g.explicit_type:g.explicit_id},'method':'explicit-id','confidence':1.0}
        keyword=self.keyword(g)
        if not keyword:return {'status':'unmatched','method':'name'}
        try:data=self.search(keyword)
        except TMDBError as exc:
            self.log.warning('TMDB title search failed: %s',exc)
            return {'status':'error','method':'tmdb-title-search','error':str(exc)}
        candidates=[]
        for row in data.get('results',[]):
            if row.get('type')!=g.kind or not row.get('tmdb_id'):continue
            if not any(fold(str(title or ''))==fold(g.title) for title in (row.get('title'),row.get('originalTitle'))):continue
            year=row.get('year')
            if g.year and (not year or abs(year-g.year)>1):continue
            candidates.append(row)
        if not candidates:return {'status':'unmatched','method':'tmdb-title-search'}
        candidates.sort(key=lambda row:abs((row.get('year') or 0)-(g.year or row.get('year') or 0)))
        row=candidates[0]
        return {'status':'matched','title':row['title'],'year':row.get('year'),'ids':{'tmdb':row['tmdb_id']},'method':'tmdb-title-search','confidence':1.0}

    def match_file(self,library,relpath):
        folder=guess_file(library,relpath)
        result=self.match(folder)
        if result['status']=='matched':return result
        filename=guess_name(Path(relpath).name,folder.kind)
        if (fold(filename.title),filename.year)!=(fold(folder.title),folder.year):
            fallback=self.match(filename)
            if fallback['status']=='matched':
                fallback['method']='filename-'+fallback['method']
                return fallback
            if fallback['status']=='error':result=fallback
        result['method']='folder-filename-tmdb-v1'
        return result

    def suggestions(self,guesses):
        queries=[]
        for guess,source in guesses:
            variants=[guess.title]
            # Numbered sequels are commonly written as either II/III/IV or 2/3/4.
            roman={'ii':'2','iii':'3','iv':'4','v':'5','vi':'6'}
            parts=guess.title.split()
            if parts and parts[-1].lower() in roman:variants.append(' '.join(parts[:-1]+[roman[parts[-1].lower()]]))
            for title in variants:
                keyword=f"{zc.fold(title)} {guess.kind}"
                if keyword not in [q[0] for q in queries] and title.strip():queries.append((keyword,guess,source))
        choices={};errors=[]
        for keyword,guess,source in queries[:4]:
            try:data=self.search(keyword,timeout=8)
            except TMDBError as exc:
                errors.append(str(exc));continue
            for row in data.get('results',[]):
                ident='tmdb://'+str(row.get('tmdb_id') or '')
                if row.get('type')!=guess.kind or not re.fullmatch(r'tmdb://[0-9]+',ident):continue
                title=str(row.get('title') or row.get('searchTitle') or '').strip()
                if not title:continue
                try:year=int(row.get('year') or 0) or None
                except (ValueError,TypeError):year=None
                def normalized(value):
                    words=fold(value).split()
                    roman={'ii':'2','iii':'3','iv':'4','v':'5','vi':'6'}
                    return ' '.join(roman.get(word,word) for word in words)
                want=normalized(guess.title)
                score=max(SequenceMatcher(None,want,normalized(value)).ratio() for value in (row.get('searchTitle') or title,title.split(':')[0]))
                if guess.year and year:score+=max(0,.25-.02*abs(year-guess.year))
                choice={'id':ident,'title':title,'year':year,'kind':guess.kind,'source':source,'score':score,'poster':row.get('poster')}
                if ident not in choices or choices[ident]['score']<score:choices[ident]=choice
        ordered=sorted(choices.values(),key=lambda row:(-row['score'],row['title']))[:6]
        for row in ordered:row.pop('score')
        return ordered,list(dict.fromkeys(errors))
